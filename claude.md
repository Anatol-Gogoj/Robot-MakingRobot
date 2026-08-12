# Robot-Making Robot — Marlin Firmware Project

## What This Project Is

A custom gantry-based robot driven by Marlin firmware on an Arduino Mega 2560. It is NOT a 3D printer — it's a pick-and-place / dispensing system with a 3-axis gantry, three auxiliary linear actuators, two servos, and a solenoid valve. Marlin is used as the motion controller because it provides production-grade G-code parsing, trapezoidal motion planning, and multi-axis stepper coordination out of the box.

## Hardware

### Stepper Drivers
All drivers are DM556T-style (external, optoisolated PUL/DIR/ENA inputs). They are driven directly from Mega GPIO pins — there is no RAMPS shield, but the pin mapping mirrors RAMPS 1.4 for the gantry axes.

**Wiring convention:** PUL+ and DIR+ connect to Mega digital out. PUL- and DIR- connect to Mega GND. ENA is active-low (LOW = motor enabled).

### Axis Map

| Marlin Axis | G-Code Letter | Function | PUL Pin | DIR Pin | ENA Pin | Steps/mm | Notes |
|---|---|---|---|---|---|---|---|
| X | X | Gantry X | A0 (54) | A1 (55) | 38 | 57.14 | GT2-14 pulley (28 mm/rev), 1600 steps/rev (1/8 µstep) |
| Y | Y | Gantry Y1 | A6 (60) | A7 (61) | A2 (56) | 57.14 | GT2-14 pulley — drives the first Y motor via its own DM556T |
| Y2 | — | Gantry Y2 | 36 | 34 | 30 | (follows Y) | Second Y motor on its own DM556T; `Y2_DRIVER_TYPE` makes Marlin pulse this pin set in lockstep with Y |
| Z | Z | Gantry Z | 46 | 48 | A8 (62) | 320 | 5 mm/rev lead screw, 1600 steps/rev (1/8 µstep) |
| I | A | Filter Feed | 2 | 9 | 12 | 320 | 5 mm/rev lead screw — homeable linear axis (AXIS4_NAME='A') |
| E0 | E | Syringe | 13 | 19 | 20 | 1600 | 1 mm/rev lead screw — sole extruder |
| J | B | Syringe Height | 21 | 22 | 31 | 320 | 5 mm/rev lead screw — homeable linear axis (AXIS5_NAME='B') |
| — | — | Spincoater | — | — | — | — | ODrive S1 on Serial2 (pins 16/17) — M750/M751/M752/M753 |

**Steps/mm formula:** (motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev
- Belt axes: 200 × 8 ÷ 28mm (GT2 × 14 teeth) = 57.14 steps/mm
- 5 mm lead screw axes: 200 × 8 ÷ 5mm = 320 steps/mm
- 1 mm lead screw (syringe): 200 × 8 ÷ 1mm = 1600 steps/mm

### Limit Switches
- X endstop: pin 3 (X_MIN, hardware interrupt capable)
- Y endstop: pin 14 (Y_MIN)
- Z endstop: pin 40 (Z_MIN — moved from pin 18/TX1 due to EMI sensitivity)
- I endstop (Filter Feed): pin 15 (I_MAX, RAMPS Y+ header) — homes to MAX (far end)
- J endstop (Syringe Height): pin 23 (J_MIN, moved from pin 17/TX2 to free Serial2 for ODrive)
- Syringe (E0): **no endstop**

Switch type: normally-open, wired common→GND, NO→signal pin. Internal pullups enabled via `ENDSTOPPULLUPS`. Logic: untriggered=HIGH, triggered=LOW, `*_ENDSTOP_INVERTING true`.

### Servos
- Servo 0 (gripper): GPIO 5 — `M280 P0 S<angle>`, soft limits 90°–170° in HTML slider, full 0–180° via override textbox
- Servo 1 (lid): GPIO 6 — `M280 P1 S<angle>`, full 0–180° range, no firmware clamp
- `DEACTIVATE_SERVOS_AFTER_MOVE` enabled — PWM signal cuts after 2 seconds to prevent jitter
- `SERVO_DELAY { 2000, 2000 }` — hold time before deactivation

### Relay Outputs (UV Lamp + Solenoid Valve)
Two opto-isolated relay modules control the UV cure lamp and the dispense solenoid valve. Both modules are powered from a dedicated 3.3 V buck converter rail sharing ground with the Mega. Triggered via `M42` from G-code (`DIRECT_PIN_CONTROL` enabled in `Configuration_adv.h`).

- **UV lamp:** pin 4 (RAMPS SERVO3 slot, AVR OC0B / Timer0)
- **Solenoid valve:** pin 42 (AUX2_08 header, AVR PL7, pure GPIO — no timer compare unit)
- **Current modules (active-HIGH):** `M42 Pxx S1` = energize (ON), `M42 Pxx S0` = de-energize (OFF).
  - `M42 P4 S1` = UV ON, `M42 P4 S0` = UV OFF
  - `M42 P42 S1` = valve OPEN, `M42 P42 S0` = valve CLOSED
- **Original modules (Bestep JQC3F-03VDC-C, active-LOW, replaced):** The opto LED cathode tied to the IN pin, so pulling IN to GND energized the coil. `M42 Pxx S0` = ON, `M42 Pxx S1` = OFF. Boot-time floating inputs were pulled HIGH by the module's internal pullup (safe de-energized state).
- **HTML UI:** Uses explicit ON/OFF button pairs (not a stateful toggle) that send hardcoded S values, so the correct polarity is handled by which button the user presses regardless of module type.

**Why pin 42 and not pin 11 or pin 28:** pin 11 = OC1A collides with Marlin's stepper ISR (Timer1); `analogWrite(11, ...)` fights the stepper timer continuously. Pin 28 is `E0_DIR_PIN` and is actively driven by the stepper subsystem on every syringe move. Pin 42 (PL7) has no hardware timer compare unit and no stepper/endstop/servo claim. See gotcha #12 for the underlying M42.cpp bug that caused the initial pin-11 failure and the patch that fixes it.

### Dual-Y Configuration
The two Y-axis motors are each on their own DM556T driver, with independent PUL/DIR/ENA signal sets coming from the Mega. Pin set Y (A6/A7/A2) drives the first Y motor and pin set Y2 (36/34/30) drives the second. `Y2_DRIVER_TYPE` is defined in `Configuration.h`, which is what tells Marlin to pulse both pin sets in lockstep so the motors stay synchronized — the synchronization happens in firmware, not by splicing the Mega outputs together externally. Because each motor has its own driver, auto-squaring (`Y_DUAL_ENDSTOPS`) is possible in principle, but only if a second Y endstop is added (currently only pin 14 / Y_MIN is populated).

## Firmware Architecture

### Board Definition
Custom board `BOARD_RAMPS_14_RMR` (ID **1025**) inherits from stock RAMPS 1.4 and overrides pin assignments for I/J linear axes and E0 extruder, plus resolves conflicts.

> **Do not use 1020.** That ID is stock `BOARD_RAMPS_14_EFB` (`boards.h:45`). Registering RMR as 1020 is *not* a compile error — the macro names differ — so it fails silently: `pins.h` reaches its `RAMPS_14_EFB` branch before `#elif MB(RAMPS_14_RMR)`, and the board is flashed with stock RAMPS pin assignments instead of `pins_RAMPS_14_RMR.h`. The J endstop lands back on pin 17 (Serial2 TX to the ODrive) and heater/fan MOSFETs are driven where steppers should be.

**Files that define the board:**
- `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` — pin overrides and conflict resolution
- `Marlin/src/core/boards.h` — board ID registration (`boards.h:50`, `#define BOARD_RAMPS_14_RMR 1025`)
- `Marlin/src/pins/pins.h` — routing `MB(RAMPS_14_RMR)` to the pins file

### Pin Conflicts Resolved in pins_RAMPS_14_RMR.h
| Pin | Stock RAMPS Function | Our Use | Resolution |
|-----|---------------------|---------|------------|
| 2 | X_MAX_PIN | I STEP (Filter Feed) | X_MAX_PIN → -1 |
| 9 | FAN (MOSFET_B) | I DIR (Filter Feed) | MOSFET_B_PIN → -1 |
| 12 | PS_ON_PIN | I ENABLE (Filter Feed) | PS_ON_PIN → -1 |
| 13 | LED_PIN | E0 STEP (Syringe) | LED_PIN → -1 |
| 15 | Y_MAX_PIN | I_MAX endstop (Filter Feed) | Y_MAX_PIN → -1 |
| 19 | Serial1 RX / Z_MAX | E0 DIR (Syringe) | Z_MAX_PIN → -1, OK if Serial1 unused |
| 20 | I2C SDA | E0 ENABLE (Syringe) | OK if I2C unused |
| 21 | I2C SCL | J STEP (Syringe Height) | OK if I2C unused |
| 16 | Serial2 TX | ODrive S1 UART TX | J endstop moved from pin 17 to pin 23 |
| 17 | Serial2 RX | ODrive S1 UART RX | Was J_MIN_PIN, now Serial2 RX for spincoater |

**Warning:** Pins 19/20/21 conflict with Serial1 and I2C. Pin 18 (Serial1 TX) is now free after Z endstop moved to pin 40, but pin 19 (Serial1 RX) is still occupied by E0 DIR. If an I2C device (LCD, sensor) or a second serial device is ever added, those motors must be rewired to free GPIOs. Pins 16/17 are now occupied by Serial2 (ODrive S1 link).

### Key Configuration.h Settings
```
MOTHERBOARD              BOARD_RAMPS_14_RMR
EXTRUDERS                1           (syringe only; filter feed & syringe height are I/J axes)
AXIS4_NAME               'A'         (G-code letter for I axis — Filter Feed)
AXIS5_NAME               'B'         (G-code letter for J axis — Syringe Height)
I_DRIVER_TYPE            A4988       (Filter Feed — linear axis)
J_DRIVER_TYPE            A4988       (Syringe Height — linear axis)
TEMP_SENSOR_0            0           (disabled — no heaters)
EXTRUDE_MINTEMP          0           (allows E moves without hotend — M302 not needed)
NUM_SERVOS               2
DEACTIVATE_SERVOS_AFTER_MOVE  enabled (anti-jitter, 2s hold)
SERVO_DELAY              { 2000, 2000 }
X_HOME_DIR / Y_HOME_DIR  -1          (home to min endstop)
Z_HOME_DIR               -1          (home to Z_MIN endstop, pin 40)
I_HOME_DIR                1          (home to I_MAX endstop, pin 15 — far end)
J_HOME_DIR               -1          (home to J_MIN endstop, pin 23 — moved from 17 to free Serial2)
Z_SAFE_HOMING            disabled    (Z homes first via HOME_Z_FIRST)
HOME_Z_FIRST             enabled     (in Configuration_adv.h)
Homing order             [lid open] → Z → Y → J → [gripper close] → X → I  (G28.cpp patched)
INVERT_Z_DIR             true        (verified by physical test)
INVERT_I_DIR             true        (verified by physical test)
INVERT_J_DIR             true        (verified by physical test)
```

### Motion Parameters
```
Max Feedrate (mm/s):     X=400  Y=333  Z=50  I(A)=33  J(B)=50  E=8
  (mm/min equivalents):  X=24000 Y=20000 Z=3000 A=2000 B=3000 E=500
Max Acceleration (mm/s²): X=500  Y=200  Z=100  I(A)=150  J(B)=50  E=500
Steps/mm:                X=57.14 Y=57.14 Z=320 I=320 J=320 E=1600
Travel limits (mm):      X=770  Y=150  Z=186  I=343  J=304
Homing feedrates (mm/s): X=50  Y=50  Z=15  I(A)=25  J(B)=25
Homing bump (mm):        X=5   Y=5   Z=10  I=2     J=2
Homing bump divisor:     X=2   Y=2   Z=4   I=4     J=4
ENDSTOP_NOISE_THRESHOLD  7     (max — required for EMI rejection on Z)
```

### Patched Marlin Source Files

| File | Modification |
|------|-------------|
| `src/gcode/calibrate/G28.cpp` | Custom homing order: Z→Y→J→gripper close→X→I. Servo 0 closes to 90° before X homing to prevent collision. SECONDARY_AXIS_CODE I/J entries replaced with NOOP. |
| `src/gcode/control/M42.cpp` | Added `if (pin_status <= 1) return;` early exit so digital-only writes never fall through to `hal.set_pwm_duty()`. Stock Marlin's AVR path unconditionally calls `analogWrite()` on every M42, which hijacks the pin's timer compare unit (catastrophic on pin 11 = OC1A / stepper ISR). See gotcha #12. |
| `src/gcode/control/M280.cpp` | Firmware-side servo clamp removed — soft limits enforced in HTML slider only. Override textbox allows full 0–180°. POLARGRAPH gate on T parameter removed — any servo can now use `M280 Px S<angle> T<ms>` for timed linear interpolation. Uses `servo[i].write()` (not `move()`) in the interpolation loop to avoid per-step 2s SERVO_DELAY blocks; explicit `attach(0)` before the loop and `write()+safe_delay(250)+detach` after. |
| `src/inc/SanityCheck.h` | Sanity check for DEACTIVATE_SERVOS_AFTER_MOVE commented out — stock Marlin requires Z_PROBE_SERVO_NR or switching toolhead, which don't apply here. |

### Critical Gotchas
1. **Cold extrusion:** `PREVENT_COLD_EXTRUSION` **is** enabled (`Configuration.h:853`), but `EXTRUDE_MINTEMP` is 0 and a missing sensor reports 0 °C, so the `degHotend() < extrude_min_temp` test never fires and E moves work without a hotend. `M302` **is** compiled in (`features.ini:182`, `gcode.cpp:813`) and will answer normally — it is simply not needed.
2. **Custom homing order (G28.cpp patched):** A bare `G28` homes in order: [lid servo opens to 30°] → Z → Y → J(Syr.Ht) → [gripper servo closes to 90°] → X → I(Filter Feed). HOME_Z_FIRST is enabled, Z_SAFE_HOMING is disabled.
3. **Gripper closes before X homing:** Servo 0 is commanded to 90° with a 300ms delay before X homing begins, to prevent the gripper from colliding with the frame.
4. **Filter Feed homes to MAX:** I_HOME_DIR=1, endstop is on the far end (I_MAX, pin 15). All other axes home to MIN.
5. **Servo jitter prevention:** `DEACTIVATE_SERVOS_AFTER_MOVE` cuts PWM signal 2 seconds after `M280` command. Servo goes limp after that — fine if grip is mechanically self-holding. SanityCheck.h patched to allow this without a Z probe defined.
6. **E-Stop recovery:** `M112` fully kills the firmware (`kill()` → interrupts off, terminal loop) — it **cannot** be recovered with `M999`. Recover by resetting the board: reconnect USB (DTR toggles a reset) or power-cycle. On reboot the firmware automatically disarms the spincoater ODrive (startup safety disarm). `M999` only recovers from the softer "stopped" state (after `stop()`-class errors). Note: with `EMERGENCY_PARSER` enabled, `M108`/`M112`/`M410` act immediately from the serial RX path (bypassing the queue), and `M0`/`M1` are now compiled in — they pause awaiting `M108`.
7. **Pin 17 freed for Serial2:** J endstop moved from pin 17 (TX2) to pin 23. Serial2 (pins 16/17) now connects to the ODrive S1 for spincoater control. Pin 16 = TX2 → ODrive RX, Pin 17 = RX2 → ODrive TX.
8. **Axis name mapping:** G-code uses A/B for the I/J axes (set via AXIS4_NAME/AXIS5_NAME). Marlin restricts these names to A,B,C,U,V,W — 'I' and 'J' are not valid axis names. This affects ALL G-code commands: M201, M203, G28, G1, etc. must use A/B, not I/J.
9. **Z endstop EMI history:** Pin 18 (Mega TX1) suffered severe false triggers from stepper EMI during homing. Noise threshold, 100nF cap on signal→GND, and external pullup resistor were insufficient. Moved to pin 40 (plain GPIO, no alternate function) using `Z_STOP_PIN` in pins file (not `Z_MIN_PIN`) because `pins_postprocess.h` can override `Z_MIN_PIN`. The `Z_STOP_PIN` approach lets postprocess derive `Z_MIN_PIN` automatically. Hardware: 100nF ceramic cap from pin 40 to GND recommended. Pin 18 is now free.
10. **M400 before servos in G-code programs:** M280 (servo) executes immediately when parsed, not when the motion planner finishes preceding G1 moves. Always place `M400` before `M280` in G-code sequences to drain the planner queue first. G4 (dwell) alone is NOT a reliable substitute. When using `M280 Px S<angle> T<ms>`, the ramp itself takes T ms plus a 250ms settle, so `M400` is still needed before the `M280` but a `G4` after it may not be necessary since the ramp is inherently blocking.
11. **AVR Serial.println() sends `\r\n`, ODrive expects bare `\n`:** On AVR (Mega 2560), `Serial.println()` appends `\r\n` (0x0D 0x0A). The ODrive S1 ASCII protocol expects only `\n` as the command terminator — the stray `\r` makes commands fail with "unknown command." All ODrive UART writes in spincoater.cpp use `print()` + `write('\n')` instead of `println()`. The Nano RP2040 (mbed/ARM) `println()` sends only `\n`, which is why the standalone spincoater firmware worked without this issue.
12. **Stock M42.cpp calls analogWrite on AVR, even for S0/S1:** The stock implementation calls `extDigitalWrite(pin, pin_status)` and then unconditionally falls through to `hal.set_pwm_duty(pin, pin_status)`. On AVR that maps to `analogWrite()`, which attaches the pin to its hardware timer compare unit — so `M42 P11 S1` ends up configuring Timer1 OC1A at 1/255 duty, fighting Marlin's stepper ISR (Timer1) continuously. Symptom: relay fires once, then M42 "stops working" until the Mega resets via DTR. The STM32 path already had a `pin_status <= 1 && !PWM_PIN(pin)` guard; we extended it to all architectures as `if (pin_status <= 1) return;` so digital-only writes always take the pure `digitalWrite` path. When choosing pins for `M42` relay triggers, prefer pads with no hardware timer compare unit at all (pin 42 = PL7 is clean; pin 4 = OC0B is only safe because of this patch).
13. **Relay module polarity — original vs current:** The original Bestep JQC3F-03VDC-C modules were active-LOW (`M42 Pxx S0` = ON, `M42 Pxx S1` = OFF). The opto LED cathode tied to the IN pin, so GND energized the coil; boot-time floating inputs were pulled HIGH by the module's internal pullup (safe de-energized state). **The current relay modules are active-HIGH** (`M42 Pxx S1` = energize, `M42 Pxx S0` = de-energize). The HTML UI now uses explicit ON/OFF button pairs that send hardcoded S values, so the correct polarity is handled by which button the user presses. When writing production G-code, always comment the intent (e.g. `M42 P4 S1 ; UV_ON`) because the S-value meaning depends on which relay module is installed.
14. **`Servo::move()` vs `Servo::write()` in interpolation loops:** `move()` calls `attach + safe_delay(SERVO_DELAY) + detach` per invocation. With `SERVO_DELAY=2000`, that would be 2 seconds per step — unusable for smooth ramps. For tight interpolation loops, use `write()` with a manual `attach(0)` before the loop and `write(final_angle) + safe_delay(250) + detach` after. The M280 T parameter (timed servo ramp) uses this approach. Default lid move time in the HTML UIs is 800ms.
15. **UI token matching is substring-based, first-match-wins — a new token must never be a superstring of an existing one.** Both UIs dispatch `STATE:` through `for (const [key,[phase,label]] of Object.entries(stateMap)) { if (state.includes(key)) { spinSetPhase(...); break; } }` (`RMR_Controller.html:1006-1008`, `RMR_Touch.html:1041`) — `includes()`, insertion-ordered, `break` on first hit. The four completion markers are separate un-`else`-guarded `spinMsg.includes(...)` checks that run **after** the state block (`Controller:1012-1015`, `Touch:1043-1046`). Three live false-positives at the stack tip: `ERR: CYCLE_COMPLETE_NO_HOME` contains `CYCLE_COMPLETE` → both UIs show green "Cycle complete" and the Touch UI fires `showToast('Spin cycle complete','success')`; `ERR: HOME_SET_FAILED` contains `HOME_SET` → "Home datum set" on a failed M751; `STATE:HOME_SETTLE` also contains `HOME_SET` → the UI declares the datum set while the return-to-datum move is still running. (Verified safe: `INDEX_INCOMPLETE` does **not** contain `INDEX_COMPLETE`.) Consequence for firmware authors: **never name a new token so that it contains an existing token as a substring**, and never judge a cycle by the phase indicator — read the `ERR:`/`WARN:` lines. Fix tracked in issue #47.
16. **Datum rules — an existing datum is never silently moved.** `_homePos` (`spincoater.cpp:37`) is only a meaningful reference when `_datumSet` (`:43`) is true. It becomes true via M751 (`:833-834`), or at boot **only if the boot index search actually completed** (`:258`; otherwise the AMT102 frame is anchored to wherever the rotor sat at ODrive power-up and the position is an arbitrary shaft angle), or as a last-resort first datum adopted when a settle fails and none exists yet (`:776-777`). A **failed** index home never overwrites an existing operator datum — that was the original VanVersion behaviour and it destroyed layer-to-layer registration on the most common failure path (issue #41). A datum is never captured from a moving axis: both `doSetHome()` (`:826`) and the settle fallback (`:770`) refuse above `|vel| > 0.05` rev/s (~3 RPM). Every datum-writing read goes through `feedbackStable()` (two consistent reads), never a single `feedback()`.
17. **The spincoater datum is RAM-only and does not survive a reset.** `_homePos`/`_datumSet` are plain file-scope statics; `settings.cpp` contains no spincoater state (grep-verified: zero hits). Every board reset — including the DTR reset a browser triggers on connect, and the reset that is the only way to recover from M112 — loses the operator's zero. The next M750/M751/M752 re-runs the full `boot()` including a fresh index search and re-datums at wherever the boot settle got to, with a `WARN:`. Re-run M751 after every reconnect if layer registration matters. Tracked as issue #54.
18. **The >1-turn settle guard latches.** If `|pos − _homePos| > 1.0` turns, `doIndexHome()` refuses the settle move (`spincoater.cpp:665-677`) and keeps refusing — nothing re-normalises `_homePos` into a new encoder frame automatically, because doing so used to mean silently destroying the operator's datum. The only exit is M751. The firmware says so on the wire: `WARN: datum lies >1 turn outside the current encoder frame -- run M751 (Set Home) to re-establish it`. Tracked as issue #55. **UNVERIFIED:** whether an ODrive 0.6.x index search re-references `pos_estimate` is exactly issue #46 and has never been observed on this machine — if it does not, this guard will fire on essentially every post-spin home.
19. **EMERGENCY_PARSER side effects.** (a) `kill()` calls `Spincoater::emergencyStop()` (`MarlinCore.cpp:904`) **before** `minkill()`'s `cli()` (`:932`). (b) IDLE means **disarm/freewheel, not brake** — chosen deliberately: no confirmed brake resistor, and regen from a high-RPM chuck could overvolt the DC bus (`spincoater.h:130-131`, issue #40). Coast-down time from full speed has never been measured — **UNVERIFIED**. (c) `emergencyStop()` must never call `idle()`/`safe_delay()` — `kill()` is reached from `idle()`, so it would recurse. (d) Every short ODrive reply-wait (`readRaw` 500 ms `:296`, `feedback` 200 ms `:331`) polls `emergency_parser.killed_by_M112` and bails, so **after M112 every ODrive read fails**: `readRaw()` returns `""` and `getState()` returns `ODRIVE_STATE_UNDEFINED`. That is intentional — it unwinds the blocking M750 so the caller's next `idle()` can dispatch the kill. (e) `M0`/`M1` are compiled in as a side effect (`HAS_RESUME_CONTINUE`, `Conditionals_adv.h:882-884`) and, with no display on this machine, **pause until an `M108` arrives** where they previously returned "Unknown command" — a real regression risk for existing production G-code, **not yet bench-checked**.
20. **ODrive ASCII writes are unacknowledged — a lost write is invisible.** The protocol returns nothing for `w`, `v`, `t` or `sc`; there is no checksum and no ack. The firmware compensates by *verifying the effect* rather than the write: `forceIdle()` re-issues `w axis0.requested_state 1` each poll round until `getState()` confirms IDLE (`spincoater.cpp:458-469`), `emergencyStop()` sends IDLE **twice** (`:110-117`), M750's ramp-down re-issues `setVelocity(0)` every 1000 ms (`M750.cpp:318-321`), and the index-search request is re-sent if the axis is still IDLE after 500 ms (`:591-601`). When adding any new ODrive command, assume the write may be dropped and poll for the resulting state — never assume "I sent it, so it happened."
21. **`clearErrors()` (`sc`) destroys the evidence.** It wipes `active_errors` and `disarm_reason`, so `reportFault()` must always run first (`spincoater.h:95-98`). `doIndexHome()` does this and credits the snapshot time back to its own transition window (`extraWindow`, `spincoater.cpp:581,597`) so fault reporting cannot itself cause the timeout it is reporting on. Issue #43.
22. **A corrupted ODrive reply is now a failed read, not a zero.** `String::toFloat()/toInt()` silently return 0 for garbage, and the old `f 0` gate was merely "contains a space" — one bad byte produced a plausible `pos=0/vel=0`. At the stack tip: `readRaw()` returns `""` on a timeout mid-line (a truncated reply is a failed read, never a truncated value, `:306`); `feedback()` returns false unless both tokens are strictly numeric (`:338-349`); `getState()` returns `ODRIVE_STATE_UNDEFINED` rather than laundering garbage into a state (`:402-409`); `getProcedureResult()` returns **-1 for unreadable, which callers must treat as UNVERIFIED, not as failure** (`:434`) so an older ODrive firmware lacking the property cannot brick a working machine; `parseStrictInt()` range-checks before narrowing because `int` is 16-bit on AVR and a corrupted all-digit reply could otherwise wrap into `procedure_result == 0` (SUCCESS) (`:79-93`). Operator-visible effect: occasional *missing* telemetry lines where you previously got wrong ones, and hard refusals where you previously got a silently wrong datum. Issue #44.
23. **`ok` does not mean the spincoater command succeeded.** Every M750/M751/M752 failure path returns from the handler normally, so Marlin emits a bare `ok` regardless of outcome. Both UIs' Program Runners advance on any `ok`, so a production program will run every subsequent layer after a `CYCLE_COMPLETE_NO_HOME`, `INDEX_HOME_FAILED` or `HOME_SET_FAILED` without pausing. Judge success only by the terminal marker (see the serial-protocol table below). Runner correctness is tracked as issue #48; no firmware token currently gates it.
24. **M752 and `M750 ... H1` physically rotate the chuck.** After the index search, `doIndexHome()` switches to POSITION/TRAP_TRAJ with `vel_limit 0.25` turns/s (~15 RPM) and commands `t 0 <_homePos>` (`spincoater.cpp:683-716`) — the chuck turns for up to 8 s. Do not run M752 with the lid open or with anything resting on the chuck. On every exit path the control mode is restored to VELOCITY/VEL_RAMP via `idleAndRestoreVelocityMode()`.
25. **The spincoater panel's "Stop" button sends M112.** `RMR_Controller.html:691` and `RMR_Touch.html:671` are both `onclick="emergencyStop()"` → `sendCmd('M112')`. There is **no soft stop for a running spin** anywhere in the UI or the firmware. Pressing Stop kills the whole firmware, freewheels the chuck, requires a board reset, and destroys the datum (gotcha #17).

## G-Code Reference for This Machine

### Homing & Positioning
```gcode
G28              # home all axes (Z → Y → J → X → I) — safe, all have endstops
G28 X Y          # home gantry XY only
G28 Z            # home Z only
G28 A            # home Filter Feed only (homes to MAX end)
G28 B            # home Syringe Height only
G92 E0           # reset extruder (syringe) position counter
G1 X_ Y_ F_     # move gantry (F in mm/min: F3000 = 50mm/s)
G1 Z_ F_         # move Z
```

### Aux Motors (I/J linear axes + E0 extruder)
```gcode
G1 A_ F_         # move Filter Feed
G1 E_ F_         # move Syringe — sole extruder, no T-switch needed
G1 B_ F_         # move Syringe Height
G92 E0           # reset syringe position
```

### Servos
```gcode
M280 P0 S_       # gripper servo (angle 0-180, soft limits 90-170 in HTML)
M280 P1 S_       # lid servo (angle 0-180)
M280 P1 S30 T800 # lid servo open over 800ms (timed linear interpolation)
```
T parameter: optional ramp time in milliseconds. When T>0, the servo interpolates linearly from its current angle to the target over T ms plus a 250ms settle. When T=0 or omitted, falls through to normal `move()` with full SERVO_DELAY. Available on all servos (POLARGRAPH gate removed).

### Relays (UV lamp + solenoid valve — current modules ACTIVE-HIGH)
```gcode
M42 P4  S1       # UV lamp ON       (pin 4,  active-high)
M42 P4  S0       # UV lamp OFF
M42 P42 S1       # solenoid valve OPEN  (pin 42, active-high)
M42 P42 S0       # solenoid valve CLOSED
```
Current modules are active-HIGH: S1 = energize, S0 = de-energize. Requires `DIRECT_PIN_CONTROL` (enabled in `Configuration_adv.h`). Note: the original Bestep JQC3F-03VDC-C modules were active-LOW (S0 = ON, S1 = OFF) — see gotcha #13 for history.

### Spincoater (ODrive S1 via Serial2)
```gcode
M750 S5000 D30 A5 C1 H1   # spin cycle: 5000 RPM, 30s, 5s ramp-up, 1s ramp-down, home after
M750                       # spin with defaults (S5000 D30 A5 C1 H1)
M751                       # set current position as 0° home datum (can fail — ERR: HOME_SET_FAILED)
M752                       # index search, then MOVES the chuck back to the datum (can fail — ERR: INDEX_HOME_FAILED)
M753                       # UART diagnostic — probes ODrive Serial2 link, reports raw response
```
**A/C are TIMES IN SECONDS, not rates.** `A5 C1` = 5 s ramp-up, 1 s ramp-down; the firmware derives `accel = (rpm/60)/rise_s` internally (`M750.cpp:183-184`). All four numeric params must be > 0 or M750 aborts with `echo:SPIN ERR: All values must be > 0`.

M753 is the only one of the four that neither boots the ODrive nor moves anything — it calls `Spincoater::init()` only (`M753.cpp:24`), so it is the correct first command on a cold bench. See the Spin Coater Subsystem section below for every failure mode and terminal marker.

### Motion Tuning (runtime, no rebuild needed)
```gcode
M201 X500 Y200 Z100 A150 B50 E500   # set max acceleration (mm/s²)
M203 X400 Y333 Z50 A33 B50 E8       # set max feedrate (mm/s)
M500             # NOT AVAILABLE — EEPROM_SETTINGS is disabled (Configuration.h:2217).
                 #   settings.cpp:2970 compiles the stub: reports "EEPROM disabled", saves nothing.
M501             # DESTRUCTIVE — does NOT load from EEPROM. settings.h:90 compiles
                 #   load() { reset(); report(); }, which discards all runtime M201/M203/M92
                 #   tuning and reverts to the compiled-in Configuration.h defaults.
M503             # report all active settings (this one works)
```

### Diagnostics
```gcode
M119             # report endstop states (use to verify wiring)
M503             # report all active firmware settings
M92              # report steps/mm (M92 X57.14 Y57.14 Z320 A320 B320 E1600 to override)
M999             # recover from "stopped" state (NOT from M112 — after M112, reset/reconnect the board)
```

## Build & Upload

### Toolchain
- PlatformIO in VS Code
- Build target: `mega2560` (set `default_envs = mega2560` in platformio.ini)
- Baud rate: 250000 (Marlin default)

### Build Steps
1. Clone Marlin 2.1.x
2. Copy Configuration.h, Configuration_adv.h into `Marlin/`
3. Copy pins_RAMPS_14_RMR.h into `Marlin/src/pins/ramps/`
4. Add board ID to `Marlin/src/core/boards.h`
5. Add routing to `Marlin/src/pins/pins.h`
6. Build with PlatformIO (checkmark button or `pio run -e mega2560`)
7. Upload (arrow button or `pio run -e mega2560 -t upload`)

### Serial Interface
Connect via the included `RMR_Controller.html` web UI, Pronterface, or any serial terminal at 250000 baud. Port is typically `/dev/ttyACM0` (Linux) or `COM3` (Windows).

## Web Controller (RMR_Controller.html)

Browser-based unified control interface using Web Serial API (Chrome/Edge required). Controls both the gantry and spincoater over a single serial connection.

### Features
- **XY jog pad** with configurable step sizes (0.1–50 mm) and feed slider (max 24000 mm/min)
- **Z jog** with feed slider (max 3000 mm/min), arrows inverted to match physical reality (up arrow = platform down)
- **Y axis arrows** swapped to match physical motion direction
- **Per-axis auxiliary feed sliders:** A (max 2000), B (max 3000), E (max 500 mm/min)
- **Acceleration tuning panel** (collapsible) — per-axis M201 sliders with Set/Set All/Save to EEPROM
- **Gripper servo** — slider (90°-170°), Open/Close quick buttons, override textbox (0-180°)
- **Lid servo** — slider (0°-180°) with T<ms> timed ramp (default 800ms)
- **Relay controls** — explicit ON/OFF button pairs for solenoid valve (OPEN/SHUT) and UV lamp (ON/OFF), with configurable pin numbers. Last-pressed button highlights via CSS. No internal state tracking — each button sends a hardcoded S value.
- **Position readout** with auto-report (1s polling via M114)
- **E-Stop** button (M112) — recovery requires a board reset (disconnect/reconnect USB); the **Reset (M999)** button only clears the softer "stopped" state
- **Raw G-code** input with command history
- **Spincoater panel** (collapsible, starts open) — M750/M751/M752 controls:
  - Parameter inputs: RPM, Duration, Rise Time, Sink Time, Encoder homing toggle
  - Start Spin / **Stop (sends M112 — this KILLS the firmware; recovery needs a board reset and the spincoater datum is lost — see gotcha #25)** / Set Home (M751) / Index Home (M752 — rotates the chuck)
  - Live RPM gauge with progress bar, SVG circular position dial with shortest-path needle rotation
  - Stats cards: mean, std dev, min, max, range, samples, bus voltage, home position
  - Phase indicator with color-coded status dot
  - Parses `echo:SPIN TELEM:`, `echo:SPIN DATA:`, `echo:SPIN STATE:` prefixes plus the `OK:`/`ERR:` completion markers `CYCLE_COMPLETE` / `INDEX_COMPLETE` / `HOME_SET` / `READY`. **`echo:SPIN WARN:` is parsed by neither UI** — every datum-integrity message lands there and renders as ordinary grey console text (gotcha #15, issue #47). `echo:SPIN DIAG:` (M753) is console-log only.
- **Program Runner** — textarea for G-code programs, Load .gcode button, Run/Pause/Stop controls, line counter, Wait-for-ok checkbox. Sends lines sequentially, waits for Marlin `ok` before sending next line.
- **Keyboard shortcuts:** Arrow keys = XY, PgUp/PgDn = Z, Esc = E-Stop (disabled when textarea focused)

### Touch UI Layout
The Touch GUI variant organizes controls into tabs:
- **Jog tab:** XY pad, Z controls, auxiliary axis controls. Single Home All (G28) button in XY center; per-axis home buttons removed from this tab.
- **Advanced tab** (formerly "Config"): individual axis homing (Home XY, Home Z, Home A, Home B), acceleration tuning, servo override (M280) with raw angle inputs for Gripper (P0) and Lid (P1) that bypass slider limits and T ramp.
- **Connect/Disconnect** button in always-visible header ribbon (not inside a drawer).

### Touch UI file
The touchscreen variant is `RMR_Touch.html` at repo root. Its spincoater parsing is **functionally equivalent but not byte-identical** to `RMR_Controller.html` (`Controller:968-1039` vs `Touch:1018-1064`): same stateMap keys in the same insertion order, same four substring completion checks, same DATA regex and card mapping, same Program Runner ok-advance rule — but reflowed onto single lines, with different local identifiers (`rpmM`/`degM`/`dataM` vs `rpmMatch`/`degMatch`/`dataMatch`), and `Touch:1043` additionally fires `showToast('Spin cycle complete','success')` where `Controller:1012` does not. **Patch each file separately** — pasting one over the other silently deletes the Touch UI's toast. Every serial-contract defect in gotchas #15 and #23 applies to both. `RMR_Controller.html` and `RMR_Touch.html` **are** the machine's UI — never start a new one.

> The single authoritative file list is the **File Inventory** near the end of this document. (A second, stale copy used to live here; it was a strict subset and has been removed.)

## Spin Coater Subsystem

> **This section describes the code at the tip of an unmerged PR stack.** Nothing in it has run on the machine. See "Status: Unmerged PR Stack" immediately below.

### Status: Unmerged PR Stack

Everything in this section reflects branch `fix/44-feedback-numeric-validation`, the tip of a six-PR stack that is **open, unmerged and un-bench-verified**. Every commit compiles (`pio run -e mega2560`) and has passed adversarial review; none has run on hardware.

The PRs are a strict stack of bases, not six independent branches off `main` — they must be merged bottom-up in exactly this order:

| Order | PR | Commits | What it does |
|---|---|---|---|
| 1 | #38 | `ac20bc5` | Merge VanVersion spincoater updates: settle to saved home datum |
| 2 | #39 | `c7940fe`, `33c8f45` | VanVersion follow-ups: fallback DEG, >1-turn settle guard, UV relay S-value; delete stale `DispenseCureDemo1.gcode` |
| 3 | #51 (issue #40) | `b81c8a1`, `f85257c` | Spincoater e-stop: `EMERGENCY_PARSER` + ODrive IDLE disarm in `kill()` and `setup()`; M112/M999 doc correction |
| 4 | #56 (issues #41, #43) | `092baf8`, `d9dc4f4` | `doIndexHome()` honest failure exits, fault introspection, datum preservation |
| 5 | #57 (issue #42) | `bd3058c` | Bound every blocking wait in the spin cycle; detect a dead link directly |
| 6 | #58 (issue #44) | `757fdad` | Reject corrupted ODrive replies instead of laundering them into zeros |

Aggregate `main..HEAD`: 12 files, +811/−480. Firmware surface is `spincoater.{h,cpp}`, `M750.cpp`, `M751_M752.cpp`, `Configuration_adv.h`, `MarlinCore.cpp`. `M753.cpp` is **unchanged across the whole stack**. The two HTML UIs were touched only for the M112/M999 recovery wording — **neither UI's serial parser was updated**, which is why gotcha #15 exists.

### Overview

The spin coater uses an ODrive S1 motor controller driving a D5312s-330kV motor with an AMT102 encoder. The Mega 2560 running Marlin drives the ODrive S1 directly over Serial2 — there is no second Arduino. `SpincoaterStage/` holds the retired Nano RP2040 bring-up firmware and its standalone dashboard; they are historical reference and are not part of the machine.

### Architecture

```
Machine:          Mega (Marlin + M750/M751/M752/M753) ──Serial2──► ODrive S1 ──► Motor
Retired reference: PC (SpincoaterDashboard.html) ──USB──► Nano RP2040 ──Serial1──► ODrive S1 ──► Motor
                   (hardware no longer wired — kept for rationale only)
```

### Hardware

- **Motor:** D5312s-330kV brushless outrunner
- **Controller:** ODrive S1
- **Encoder:** AMT102 (incremental with index pulse)
- **ODrive control mode:** Ramped Velocity Control (vel_ramp_rate for accel/decel)
- **UART baud:** 115200

### Benchtop Test Setup (Nano RP2040 Connect) — RETIRED REFERENCE

> **RETIRED REFERENCE — none of the commands, prefixes or phases in the next four subsections exist in the Marlin firmware.** The machine's spincoater interface is exactly `M750`/`M751`/`M752`/`M753` (`gcode.cpp:972-975`). In particular there is no `STOP` command on this machine — see gotcha #25. For the machine's actual contract see "Marlin/Mega Integration" below.

#### Wiring
- Nano pin 0 (TX1) → ODrive J11 pin 4 (RX / GPIO7)
- Nano pin 1 (RX1) → ODrive J11 pin 3 (TX / GPIO6)
- ODrive J11 ISOVDD → Nano 3.3V
- ODrive J11 ISOGND → Nano GND

#### PlatformIO Config
```ini
[env:nanorp2040connect]
platform = raspberrypi
board = nanorp2040connect
framework = arduino
monitor_speed = 115200
lib_deps =
    https://github.com/odriverobotics/ODriveArduino.git#master
```

The ODriveUART library must be pulled from GitHub — the PlatformIO registry name `odriverobotics/ODriveArduino @ ^0.1.0` does not resolve. The full firmware repo URL (`odriverobotics/ODrive.git`) is the wrong repo (that's the ODrive firmware, not the Arduino library).

#### Upload Method
The Nano RP2040 uses UF2 drag-and-drop: double-tap the reset button, a `RPI-RP2` USB drive appears, drag `firmware.uf2` onto it. PlatformIO's `picotool` upload protocol is unreliable.

### Reference firmware (SpincoaterStage/src/main.cpp — v2.6, retired)

#### Serial Protocol (115200 baud, newline-terminated) — Nano only, NOT this machine

| Command | Description |
|---------|-------------|
| `SPIN <rpm> <dur_s> <accel> <decel> <home 0\|1>` | Run a full spin cycle with specified parameters |
| `START` | Run with current default parameters |
| `SET <param> <value>` | Set default: RPM, DUR, ACCEL, DECEL, HOME |
| `STATUS` | Report params + ODrive state + bus voltage + position |
| `STOP` | Emergency velocity zero — works mid-cycle (checked in all blocking loops) |
| `HOME` | Encoder index search — does NOT reset degree datum |
| `SETHOME` | Set current position as 0° datum — dial snaps to 0° |

#### Output Prefixes (Nano)

The Nano prefixes output as `OK:` / `ERR:` / `STATE:` / `DATA:` / `TELEM:` with no envelope. **On this machine every line is wrapped as `echo:SPIN <PREFIX>` and there are two additional prefixes (`WARN:`, `DIAG:`)** — see "Serial Protocol Reference" below, which is the authoritative contract.

#### Telemetry (Nano)

Emitted every 200ms during active phases via the ODrive `f 0` command (returns pos and vel in a single round-trip):
```
TELEM: RPM=<val> POS=<val> DEG=<val>
```
- `RPM` — current motor speed (vel × 60)
- `POS` — raw encoder position in turns
- `DEG` — absolute degrees from last SETHOME datum, normalized to [0, 360)

The Marlin form is identical apart from the `echo:SPIN ` envelope.

#### Spin Cycle Phases (Nano)

The Nano's seven phases were CONNECTING → CALIBRATING → RAMP_UP → MEASURING → RAMP_DOWN → SETTLING → HOMING. **The Marlin phase list is longer and includes five failure states the Nano never had** — see "Spin Cycle Phases (Marlin)" below. Do not use this list to write a UI.

#### Homing vs Set Home (Nano)

On the Nano, `HOME` ran a bare index search and `SETHOME` captured the datum. **The Marlin semantics are materially different — M752 physically moves the chuck back to the saved datum and can fail in nine distinct ways.** See "Datum Model" and "M752" below. Do not carry the Nano's "HOME does not overwrite the datum, full stop" model over; the Marlin rule is conditional on `_datumSet`.

#### Key Implementation Details
- **E-stop works mid-cycle:** `checkStop()` polls USB serial for STOP commands inside every blocking loop (ramp-up, measure, ramp-down, settling, calibration). Previously STOP was ignored until cycle completion.
- **No `sscanf` with `%f`:** The RP2040 mbed platform's C library doesn't link float support for scanf/sscanf. All parsing uses Arduino `String.toFloat()` / `String.toInt()`.
- **No `getParameterAsFloat()`:** The ODriveUART library's getter uses `sscanf` internally — broken on RP2040. All ODrive reads use raw ASCII commands (`r <property>`, `f 0`) with manual String parsing.
- **Serial bus contention avoidance:** `lastTelemRPM` is cached from telemetry reads and used for ramp-up/ramp-down exit conditions, eliminating separate `odrive.getVelocity()` calls that would conflict with telemetry's `f 0` reads on the same UART.
- **ODrive state machine:** Cannot go directly from CLOSED_LOOP_CONTROL to ENCODER_INDEX_SEARCH. `doHome()` explicitly transitions to IDLE first, waits for the transition, then commands the index search.

### Dashboard (SpincoaterDashboard.html — v2.5, retired)

Web Serial dashboard (Chrome/Edge only, 115200 baud). Dark theme matching RMR_Controller.html. Speaks the Nano protocol above, not Marlin's — it cannot drive this machine.

#### Features
- **Connection management** — connect/disconnect with status indicator
- **Parameter inputs** — RPM, Duration, Accel, Decel, Encoder homing toggle
- **Buttons:** Start, Stop, Set Home (yellow — sets 0° datum), Index Home (blue — encoder search, preserves datum), Status
- **Live RPM gauge** — progress bar scaled to target RPM, zeroes on stale (2s no telemetry)
- **SVG circular position dial** — needle rotates to show degrees from home, tick marks at 30° intervals, cardinal labels at 0/90/180/270. Needle dims to grey during high-speed spinning (> 60 RPM) where angular position is aliased. Shortest-path rotation logic prevents wraparound animation glitches (350°→10° doesn't animate 340° backwards).
- **Stats cards** — mean, std dev, min, max, range, samples, bus voltage, home position (displayed in degrees)
- **Serial console** — color-coded log levels, telemetry display toggle (default OFF), auto-scroll toggle
- **Raw command input** — send arbitrary commands to firmware

### Marlin/Mega Integration (IMPLEMENTED — stack unmerged, nothing bench-verified)

The spincoater is integrated into the Mega/Marlin firmware; the Nano RP2040 is eliminated. `SpincoaterStage/INTEGRATION_PLAN.md` holds the original design rationale, but **its parameter semantics are out of date and its M750 `A`/`C` table is wrong** (it documents them as rev/s² rates; they are seconds). Everything below is authoritative; that document is not.

#### Serial Port: Serial2 freed by relocating J endstop
J endstop moved from pin 17 (TX2) to pin 23. Serial2 (pins 16/17) now connects to the ODrive S1 at 115200 baud.

**Wiring: Mega ↔ ODrive S1 J11:**
- Mega pin 16 (TX2) → ODrive J11 pin 4 (RX / GPIO7)
- Mega pin 17 (RX2) → ODrive J11 pin 3 (TX / GPIO6)
- Mega GND → ODrive J11 ISOGND
- Mega 5V → ODrive J11 ISOVDD

> **UNVERIFIED — the docs disagree on J11 logic power.** This section and `INTEGRATION_PLAN.md:36-37` say the Mega feeds `ISOVDD`/`ISOGND`; `PIN_MAP.md:95` says "ODrive provides its own 5V logic supply". J11 is the *isolated* connector, so these are mutually exclusive wirings, and getting it wrong leaves the isolator unpowered — which presents exactly as the dead-link symptom class in issue #46. **Confirm on the bench before rewiring.** No firmware source can settle a wiring question.

#### Custom M-Codes: M750, M751, M752, M753

##### M750 — spin cycle

```gcode
M750 [S<rpm>] [D<seconds>] [A<rise_seconds>] [C<sink_seconds>] [H<0|1>]
```
Blocking spin cycle. Defaults from `Configuration_adv.h:3511-3515`: `S=5000`, `D=30`, `A=5.0`, `C=1.0`, `H=true`.

**A and C are TIMES IN SECONDS, not rates.** `M750.cpp:183-184` derives `accel = (rpm/60)/rise_s` and `decel = (rpm/60)/sink_s` in rev/s² and writes them to `axis0.controller.config.vel_ramp_rate`. Every blocking loop calls `idle()`/`safe_delay()`.

Phase order (`M750.cpp:158-414`): parse+validate → deferred `boot()` (first use only) → echo params → CONNECTING → Vbus read → CALIBRATING/CLOSED_LOOP → RAMP_UP → MEASURING → RAMP_DOWN → SETTLING → STOPPED → optional index home (H1) → terminal line.

Ramp-up detail: the commanded velocity is `(rpm+10)/60` rev/s (deliberate overshoot, `:234`) and the exit threshold is `rpm × 0.98` (`:235`). The loop condition is a **signed** compare on `lastTelemRPM` (`:246`), so reverse rotation never satisfies it and exits via the hard timeout instead. There is **no telemetry-liveness check in ramp-up** — a link that dies at the start of ramp-up leaves `lastTelemRPM` at 0 and exits as `RAMP_TIMEOUT`, not as a link-lost token. The stall detector is gated on `lastTelemRPM > 100` (`:262`) so it cannot fire on a dead link.

Statistics (success path only, `:149-154`): `Samples`, `MeanRPM`, `StdDevRPM`, `MinRPM`, `MaxRPM`, `Range`. Variance is **population** (`/n`, `:146`), not sample.

**Every way M750 can fail:**

| Exit | Terminal marker | Source | Side effects |
|---|---|---|---|
| Bad params (`rpm/dur/rise/sink <= 0`) | **none** | `:167-170` | none |
| `boot()` failed | **none** | `:175-178` | `_ready` stays false |
| ODrive silent 5 s at CONNECTING | **none** | `:204-207` | none — **no forceIdle** |
| Closed loop refused | **none** | `:223-226` | `forceIdle()` already done inside `ensureClosedLoop()` |
| Ramp-up timeout | `STATE:RAMP_TIMEOUT` | `:251-258` | `setVelocity(0)`; no forceIdle, no wait for stop |
| RPM stall | `STATE:RAMP_STALL` | `:261-270` | `setVelocity(0)`; no forceIdle, no wait for stop |
| Link dead ≥3 s during measure | `STATE:MEASURE_LINK_LOST` | `:97-101`, `:281` | `setVelocity(0)` |
| Zero samples over the whole dwell | *none* (`DATA: Samples=0`) | `:140-143`, `:281` | `setVelocity(0)` |
| Link dead ≥3 s during ramp-down | `STATE:DECEL_LINK_LOST` | `:324-333` | `setVelocity(0)` re-issued; **deliberately does NOT forceIdle** — with the link down neither command reaches the drive, and a standing zero-velocity command is the better thing to leave |
| No RPM progress during ramp-down | `STATE:DECEL_STALL` | `:342-353` | `setVelocity(0)` **and** `forceIdle()` → freewheel |
| H1 and index home failed | `ERR: CYCLE_COMPLETE_NO_HOME` | `:377-411` | one of three WARN branches first |
| Success | `OK: CYCLE_COMPLETE` | `:413` | — |

**Critical:** on **all ten abort rows** (every row above `H1 and index home failed`) **M750 emits no `CYCLE_COMPLETE`-family token at all** — there is no machine-readable "the cycle ended" signal on those paths. The only emitters are `M750.cpp:411` (`ERR: CYCLE_COMPLETE_NO_HOME`) and `:413` (`OK: CYCLE_COMPLETE`); every earlier failure returns before that block. Marlin still returns a bare `ok` in every case (gotcha #23).

**Known weakness (unfixed):** the Vbus read at `:215-218` prints raw `readRaw("vbus_voltage")` with **no strict parse**. Since `readRaw()` now returns `""` on a dead link, that path prints the literal line `echo:SPIN DATA: Vbus=V` and the cycle **continues**. Only `boot()` strict-parses Vbus (`spincoater.cpp:143`). Both UIs render that as a Vbus card reading `NaN`.

##### M751 — set datum

Boots the ODrive if needed (`M751_M752.cpp:25-31`), then `doSetHome()` (`spincoater.cpp:809-848`):
1. `feedbackStable()` — up to 3 attempts, each two `f 0` round trips that must agree. Failure → `ERR: Could not obtain a stable ODrive position -- home NOT set`.
2. Velocity gate: `fabs(vel) > 0.05` rev/s (~3 RPM) → `ERR: Refusing to set home, axis moving at <n> RPM`. **M751 now refuses a spinning rotor.**
3. Success: writes `_homePos = pos`, `_datumSet = true`; emits `DATA: HomePos=`, `TELEM: ... DEG=0.00`, `OK: HOME_SET`.

**Terminal markers:** `OK: HOME_SET` / `ERR: HOME_SET_FAILED` (`M751_M752.cpp:36`) / **none** if the boot failed.

##### M752 — encoder index search + return to datum

**M752 physically rotates the chuck** (gotcha #24). `M751_M752.cpp:39-56` wraps `doIndexHome()` (`spincoater.cpp:551-803`):

1. `STATE:HOMING`.
2. Liveness: poll `getState()` until != UNDEFINED, ≤5000 ms.
3. If not IDLE: `STATE:ENTERING_IDLE`, `forceIdle(3000)`, then `safe_delay(200)`.
4. Request `ENCODER_INDEX_SEARCH`; poll ≤3000 ms (plus credited fault-report time) for state 6. After 500 ms, if still IDLE, `reportFault()` once, then `clearErrors()` + re-request. On entry: `STATE:INDEX_SEARCH_ACTIVE`.
5. Wait for return to IDLE, ≤30000 ms. **The axis returns to IDLE after both a successful and a failed procedure, so reaching IDLE proves nothing** (`:617-619`).
6. **Verify `axis0.procedure_result`**: `>0` = failure; `<0` = unreadable → WARN only, continue.
7. `safe_delay(300)` encoder settle.
8. **>1-turn guard:** `feedbackStable()` must succeed, and `fabs(pos - _homePos)` must be ≤ 1.0 turn (gotcha #18).
9. `STATE:HOME_SETTLE`; switch to POSITION/TRAP_TRAJ, `vel_limit 0.25` rev/s (~15 RPM), accel/decel 0.5.
10. Arm closed loop, poll ≤2000 ms.
11. `t 0 <_homePos>` — trapezoidal move **to the saved datum**, poll ≤8000 ms for `|pos-_homePos| < 0.003` turns (1.08°) and `|vel| < 0.05`. Success → `DATA: HomeSettleErr=<deg> deg`.
12. Unwind: `idleAndRestoreVelocityMode()`.
13. Position report `TELEM: RPM= POS= DEG=`.
14. `OK: INDEX_COMPLETE` or `ERR: INDEX_INCOMPLETE -- datum not reached`.

**Every failure exit of `doIndexHome()`:**

| # | Condition | Emitted | Source | Unwind |
|---|---|---|---|---|
| 1 | ODrive silent 5 s | `ERR: ODrive not responding` | `:560-563` | **none** |
| 2 | Cannot reach IDLE in 3 s | `ERR: Could not confirm ODrive IDLE...` + `ERR: Could not enter IDLE before index search` | `:467`, `:570-572` | forceIdle already attempted |
| 3 | Never entered state 6 | `ERR: Index search never started, state=<n>` + fault dump | `:605-615` | `forceIdle()` |
| 4 | Search ran >30 s | `ERR: Index search timeout (30s)` + fault dump | `:621-630` | `forceIdle()` |
| 5 | `procedure_result > 0` | `ERR: Index search failed, procedure_result=<n>` + fault dump | `:636-643` | `forceIdle()` |
| 6 | No stable position read before settle | `ERR: No stable position read before settle -- refusing to move` | `:660-664` | `forceIdle()` |
| 7 | >1 turn from datum | `ERR: Position <n> is >1 turn from home datum <n> -- refusing settle (encoder not index-referenced?)` + `WARN: ... run M751` | `:665-677` | `forceIdle()` |
| 8 | Arm refused in 2 s | `ERR: Could not enter closed loop -- return to datum skipped` + fault dump | `:703-708` | `idleAndRestoreVelocityMode()` |
| 9 | Settle timeout 8 s | `DATA: HomeSettle timeout (8s)` + one of four datum branches + `TELEM:` + `ERR: INDEX_INCOMPLETE -- datum not reached` | `:735-782`, `:801` | `idleAndRestoreVelocityMode()` |

**Only exit 9 emits `INDEX_INCOMPLETE`** — exits 1–8 return before line 800. M752 supplies the universal terminal marker `ERR: INDEX_HOME_FAILED` on all nine (`M751_M752.cpp:55`). **Ordering trap:** on exit 9 the operator sees `ERR: INDEX_INCOMPLETE` immediately followed by `ERR: INDEX_HOME_FAILED` — two error lines for one failure.

**Terminal markers:** `OK: INDEX_COMPLETE` / `ERR: INDEX_HOME_FAILED` (always, on any failure) / additionally `ERR: INDEX_INCOMPLETE` on exit 9 only / **none** if the boot failed.

##### M753 — UART diagnostic

`M753.cpp` — **untouched by the entire PR stack.** Sends `r vbus_voltage\n` on Serial2 and dumps every byte for up to 2000 ms, printing `DIAG:` lines only. It uses raw `SPINCOATER_SERIAL` directly, does **not** go through the strict parsers, and emits no `STATE:`/`OK:`/`ERR:` tokens — so neither UI's spincoater panel reacts to it beyond logging. It calls `Spincoater::init()` only; it never boots, never touches the datum, never moves the chuck. **This makes it the correct first command on a cold bench.**

#### `reportFault()` output shape

`spincoater.cpp:438-456`. Always four lines, read **before** any `clearErrors()` (gotcha #21):
```
echo:SPIN ERR: fault @ <context>
echo:SPIN DATA: procedure_result=<raw or <no reply>>
echo:SPIN DATA: active_errors=<raw or <no reply>>
echo:SPIN DATA: disarm_reason=<raw or <no reply>>
```
Contexts in use: `closed-loop entry timeout`, `full calibration timeout`, `closed-loop refused after full calibration`, `index search request refused (axis stayed IDLE)`, `index search never entered state 6`, `index search timeout`, `index search procedure_result != 0`, `closed-loop arm refused before settle`.

#### Datum Model

| Symbol | Where | Meaning |
|---|---|---|
| `_homePos` | `spincoater.cpp:37` | Absolute ODrive encoder position in **turns** at which the operator's 0° is defined |
| `_datumSet` | `spincoater.cpp:43` | True once a *meaningful* reference exists. While false, `_homePos` is its 0.0f initial value or a stale leftover and `getHomePos()` must not be trusted |

Both are file-scope statics in RAM (gotcha #17). Accessors: `getHomePos()` (`:864`), `isDatumValid()` (`:866`), `getDegreesFromHome()` (`:854` — **defined but never called anywhere in the firmware**; grep-verified dead code).

**Every write site — exhaustive, 5 sites (grep-verified):**

| Line | Write | Guard |
|---|---|---|
| `:253` | `_homePos = initPos` | inside `boot()`, only when `feedbackStable()` succeeded |
| `:258` | `_datumSet = bootHomed` | same branch; `bootHomed` is true only if the boot index search entered state 6 **and** returned to IDLE within 30 s (`:187-200`) |
| `:269` | `_datumSet = false` | `boot()`, when `feedbackStable()` failed. **`_homePos` is NOT cleared on this path** |
| `:776-777` | `_homePos = fallback_pos; _datumSet = true` | `doIndexHome()` settle-timeout fallback, only when `!_datumSet` **and** a stable read succeeded **and** `fabs(vel) <= 0.05` |
| `:833-834` | `_homePos = pos; _datumSet = true` | `doSetHome()` (M751), after `feedbackStable()` and the velocity gate |

**ESTABLISHES a datum:** M751 on a stationary axis with a stable read; `boot()` when the boot index search completed (emits `WARN: datum established at the index mark on boot...`); `doIndexHome()`'s settle-timeout fallback **only if no datum existed**.

**PRESERVES an existing datum (never moves it):** `doIndexHome()` normal operation — the routine moves the *rotor* to `_homePos`, never `_homePos` to the rotor; `doIndexHome()` settle-timeout when `_datumSet` is true; all eight early failure exits of `doIndexHome()`; M750's H1 fallback block, which snapshots `getHomePos()` before and after and reports one of three outcomes, calling `doSetHome()` only in the `!isDatumValid()` branch (`M750.cpp:396-402`).

**REFUSES to datum:** M751 on a moving axis; the `doIndexHome()` fallback on a moving axis; either, on an unstable/unreadable position; and `doIndexHome()` refuses the *settle move itself* when the position is >1 turn from `_homePos`.

**Known weaknesses in `boot()` (flagged, not fixed):**
- `boot()` still has a **single-sample arm check** (`:218-220`: `safe_delay(100); if (getState() == CLOSED_LOOP) {...}` with no `else`). If the arm is slow or refused, the boot settle-to-index is **silently skipped with no message** and boot still reports `OK: READY`. This is the exact defect fixed at `:695-708` for `doIndexHome()`.
- `boot()` **does not check `procedure_result`** after its index search. A boot search that ran and *failed* still yields `_datumSet = true` and the WARN text "datum established at the index mark on boot".
- **The boot settle timeout is silent.** If the 8 s loop at `:227` expires, nothing is emitted. `_homePos` is then taken at wherever the rotor actually is (`:253`) while the WARN asserts it is "at the index mark". **Do not document the boot datum as being at the index mark — it is at wherever the boot settle got to.**
- Issue #45 is untouched: M750/M751/M752 each call `boot()` on first use, which runs an index search, and an immediately following M752 runs a second one.

#### Spin Cycle Phases (Marlin)

Every `STATE:` token M750 and the spincoater layer can emit, in rough order of appearance. Failure states are marked.

| STATE token | Emitted by | Meaning / exit condition |
|---|---|---|
| `BOOTING` | `M750.cpp:174`, `M751_M752.cpp:26,42` | About to run the deferred `boot()` (first use only) |
| `WAITING_ODRIVE` | `spincoater.cpp:134` | Probing `r vbus_voltage`, 15 s budget |
| `INDEX_SEARCH_BOOT` | `spincoater.cpp:161` | Boot-time index search requested |
| `INDEX_SEARCH_ACTIVE` | `spincoater.cpp:177`, `:588` | Axis confirmed in state 6 |
| `INDEX_SETTLE_BOOT` | `spincoater.cpp:208` | Boot trap-traj move to `t 0 0.0` (the index mark), 8 s watchdog |
| `CONNECTING` | `M750.cpp:199` | Polling `getState()`, 5 s budget |
| `ODRIVE_FOUND` | `M750.cpp:211` | A non-UNDEFINED state was read |
| `CALIBRATING` | `M750.cpp:222` | `ensureClosedLoop()` running (50 attempts / 90 s wall clock) |
| `FULL_CALIBRATION` | `spincoater.cpp:522` | Full motor+encoder calibration, ≤60 s, max 2 attempts |
| `CLOSED_LOOP` | `M750.cpp:227` | Armed |
| `RAMP_UP` | `M750.cpp:230` | Exits at `rpm × 0.98`; hard timeout `max(3×rise_s, 10 s)` |
| `RAMP_TIMEOUT` | `M750.cpp:255` | **FAILURE** — never reached 98% within the hard timeout |
| `RAMP_STALL` | `M750.cpp:267` | **FAILURE** — <50 RPM gain in 3 s while above 100 RPM |
| `MEASURING` | `M750.cpp:279` | Welford sampling at 100 ms for D seconds |
| `MEASURE_LINK_LOST` | `M750.cpp:99` | **FAILURE** — no successful `feedback()` for 3 s |
| `RAMP_DOWN` | `M750.cpp:287` | Exits at `|RPM| <= 6.0`; stop re-issued every 1000 ms |
| `DECEL_LINK_LOST` | `M750.cpp:328` | **FAILURE** — no successful `feedback()` for 3 s. Rotor may still be spinning |
| `DECEL_STALL` | `M750.cpp:346` | **FAILURE** — no 0.5 RPM of progress within `max(3×sink_s, 10 s)`. Disarms → freewheel |
| `SETTLING` | `M750.cpp:359` | 1 s active telemetry dwell |
| `STOPPED` | `M750.cpp:368` | Ramp-down complete |
| `HOMING` | `spincoater.cpp:554` | `doIndexHome()` entered |
| `ENTERING_IDLE` | `spincoater.cpp:569` | Axis was not IDLE; `forceIdle(3000)` running |
| `HOME_SETTLE` | `spincoater.cpp:681` | **The chuck is moving** — trap-traj back to `_homePos`, 8 s watchdog |

Removed by this stack and no longer emitted anywhere: `STATE:INDEX_SETTLE` (renamed `HOME_SETTLE`) and `STATE:INDEX_FOUND_INSTANT` (deleted in `092baf8` — it used to report a refused index search as success). Both are still dead keys in both UIs' `stateMap`.

#### Serial Protocol Reference (authoritative)

Every line the Marlin spincoater layer emits is wrapped as `echo:SPIN <PREFIX>`. This is the contract both UIs parse — grep-verified against `spincoater.cpp`, `M750.cpp`, `M751_M752.cpp`, `M753.cpp` at the stack tip.

**Prefixes:** `STATE:` phase transitions · `OK:` success · `ERR:` failure · `WARN:` non-fatal but registration-relevant (new in this stack; **parsed by neither UI**) · `DATA:` key=value results · `TELEM:` live telemetry · `DIAG:` M753 only.

**`OK:` lines**

| Line | Emitted by | Meaning |
|---|---|---|
| `OK: READY` | `spincoater.cpp:273` | `boot()` completed. Note: reached even if the boot settle was skipped or timed out |
| `OK: Cycle — RPM=… DUR=…s RISE=…s SINK=…s HOME=ON/OFF` | `M750.cpp:186-190` | Parameter echo, not a result |
| `OK: HOME_SET` | `spincoater.cpp:846` | **Terminal, M751 success** |
| `OK: INDEX_COMPLETE` | `spincoater.cpp:800` | **Terminal, M752 success** — rotor reached the datum |
| `OK: CYCLE_COMPLETE` | `M750.cpp:413` | **Terminal, M750 success** |

**`ERR:` lines — terminal markers first**

| Line | Emitted by | Meaning |
|---|---|---|
| `ERR: HOME_SET_FAILED` | `M751_M752.cpp:36` | **Terminal** — M751 failed |
| `ERR: INDEX_HOME_FAILED` | `M751_M752.cpp:55` | **Terminal** — M752 failed (any of nine exits) |
| `ERR: INDEX_INCOMPLETE -- datum not reached` | `spincoater.cpp:801` | Settle-timeout exit only; always followed by `INDEX_HOME_FAILED` |
| `ERR: CYCLE_COMPLETE_NO_HOME — rotor parked off datum, angular registration unverified` | `M750.cpp:411` | **Terminal** — cycle ran, H1 home failed |

**`ERR:` lines — diagnostic**

| Line | Emitted by |
|---|---|
| `ERR: All values must be > 0` | `M750.cpp:168` |
| `ERR: ODrive boot failed — check wiring and power` | `M750.cpp:176` |
| `ERR: ODrive boot failed` | `M751_M752.cpp:28,44` |
| `ERR: ODrive not detected (15s timeout)` | `spincoater.cpp:154` |
| `ERR: Could not start index search` | `spincoater.cpp:202` |
| `ERR: Index search timeout (30s)` | `spincoater.cpp:195` (boot), `:624` (M752) |
| `ERR: ODrive not responding (5s)` | `M750.cpp:205` |
| `ERR: ODrive not responding` | `spincoater.cpp:561` |
| `ERR: Could not enter closed loop (50 attempts)` | `spincoater.cpp:495` |
| `ERR: Closed-loop entry timeout (90s)` | `spincoater.cpp:500` |
| `ERR: Axis will not arm after 2 full calibrations` | `spincoater.cpp:516` |
| `ERR: Full calibration timeout (60s)` | `spincoater.cpp:534` |
| `ERR: Failed to enter closed-loop` | `M750.cpp:224` |
| `ERR: Ramp-up timeout — reached <n> of <n> RPM` | `M750.cpp:252-254` |
| `ERR: RPM stalled at <n> — target <n> unreachable` | `M750.cpp:263-266` |
| `ERR: No ODrive telemetry for 3s during measure -- link lost` | `M750.cpp:98` |
| `ERR: No telemetry samples during measure -- statistics unavailable` | `M750.cpp:141` |
| `ERR: Measure phase aborted -- stopping spin` | `M750.cpp:281` |
| `ERR: Ramp-down aborted, no ODrive telemetry for 3s -- last seen <n> RPM; rotor may still be spinning` | `M750.cpp:325-327` |
| `ERR: Ramp-down stalled at <n> RPM -- not decelerating` | `M750.cpp:343-345` |
| `ERR: Could not confirm ODrive IDLE -- axis may still be executing` | `spincoater.cpp:467` |
| `ERR: Could not enter IDLE before index search` | `spincoater.cpp:571` |
| `ERR: Index search never started, state=<n>` | `spincoater.cpp:610-611` |
| `ERR: Index search failed, procedure_result=<n>` | `spincoater.cpp:638-639` |
| `ERR: No stable position read before settle -- refusing to move` | `spincoater.cpp:661` |
| `ERR: Position <n> is >1 turn from home datum <n> -- refusing settle (encoder not index-referenced?)` | `spincoater.cpp:666-670` |
| `ERR: Could not enter closed loop -- return to datum skipped` | `spincoater.cpp:704` |
| `ERR: Could not read ODrive position after settle failure` | `spincoater.cpp:768` |
| `ERR: Refusing to establish datum, axis still moving at <n> RPM` | `spincoater.cpp:771-773` |
| `ERR: Could not obtain a stable ODrive position -- home NOT set` | `spincoater.cpp:819` |
| `ERR: Refusing to set home, axis moving at <n> RPM` | `spincoater.cpp:827-829` |
| `ERR: Fallback home failed — manual intervention required` | `M750.cpp:401` |
| `ERR: fault @ <context>` | `spincoater.cpp:440-441` |

**`WARN:` lines — 13 in total, all new in this stack, none handled by either UI**

| Line | Emitted by | Meaning |
|---|---|---|
| `WARN: datum established at the index mark on boot -- re-run M751 if layer registration matters` | `spincoater.cpp:262` | Boot search completed; datum is valid but is not the operator's zero |
| `WARN: boot index search did not complete -- no valid datum, run M751 before relying on angles` | `spincoater.cpp:264` | `_datumSet` is false |
| `WARN: could not read a consistent initial position -- no datum, run M751 before relying on angles` | `spincoater.cpp:270` | Stable read failed; `_homePos` retains a stale value behind an invalid flag |
| `WARN: Could not read axis0.procedure_result -- index result unverified` | `spincoater.cpp:645` | `getProcedureResult()` returned -1 → unverified, **not** failed |
| `WARN: datum lies >1 turn outside the current encoder frame -- run M751 (Set Home) to re-establish it` | `spincoater.cpp:674` | The latching guard, gotcha #18 |
| `WARN: Settle failed — datum PRESERVED at <n> turns; rotor stopped <n> deg away` | `spincoater.cpp:757-761` | Operator datum intact |
| `WARN: Settle failed — datum PRESERVED (rotor position unreadable)` | `spincoater.cpp:764` | Operator datum intact |
| `WARN: Settle failed and no datum existed — establishing one at pos=<n>` | `spincoater.cpp:778-779` | First datum adopted |
| `WARN: run M751 to set your intended zero` | `spincoater.cpp:780` | Follows the line above |
| `WARN: Index homing failed; a first datum was established at <n> turns — run M751 to set your intended zero` | `M750.cpp:384-386` | H1 path, datum changed |
| `WARN: Index homing failed — datum PRESERVED at <n> turns (not re-datuming)` | `M750.cpp:392-394` | H1 path, datum intact |
| `WARN: Index homing failed and no datum set — attempting fallback set-home` | `M750.cpp:397` | H1 path, about to call `doSetHome()` |
| `WARN: Fallback home set OK` | `M750.cpp:399` | H1 fallback succeeded |

**`DATA:` keys**

| Key | Emitted by | Units / meaning | UI card |
|---|---|---|---|
| `Vbus` | `spincoater.cpp:144` (strict-parsed), `M750.cpp:216` (**unvalidated**) | Volts | Bus voltage |
| `BootSettleErr` | `spincoater.cpp:232` | degrees | — |
| `InitialPos` | `spincoater.cpp:259` | turns | — |
| `Samples` | `M750.cpp:149`, `:142` | count | Samples |
| `MeanRPM` | `M750.cpp:150` | RPM | Mean |
| `StdDevRPM` | `M750.cpp:151` | RPM (population σ) | Std dev |
| `MinRPM` / `MaxRPM` / `Range` | `M750.cpp:152-154` | RPM | Min / Max / Range |
| `accel` / `decel` | `M750.cpp:191-192` | rev/s² — one line, two keys | — |
| `HomePos` | `spincoater.cpp:836` | turns | Home position (×360 for degrees) |
| `HomeSettleErr` | `spincoater.cpp:726` | degrees | — |
| `procedure_result` / `active_errors` / `disarm_reason` | `spincoater.cpp:447-455` | raw ODrive strings, or `<no reply>` | — |

**Irregularities a UI author must know:**
- `echo:SPIN DATA: HomeSettle timeout (8s)` (`spincoater.cpp:736`) is `DATA:`-prefixed but has **no `key=value`**, so it does not match the UIs' `/DATA:\s*(\w+)=(.*)/` regex. It is semantically an error, not data.
- `DATA: accel=… decel=…` is a single line carrying two keys; the regex captures only the first.
- On a dead link the M750 Vbus line degenerates to `echo:SPIN DATA: Vbus=V`, which both UIs render as the literal string `NaN`.
- `DegFromHome` is a **key the firmware never emits**, yet both UIs key their Home card on it (`Controller:1028`, `Touch:1057`). Tracked in issue #47.
- On the zero-sample measure path only `Samples=0` is emitted, so the other five stat cards keep the **previous** cycle's numbers. On the `MEASURE_LINK_LOST` path not even `Samples` is emitted and the whole stat block is stale.

**`TELEM:`**
```
echo:SPIN TELEM: RPM=<val> POS=<val> DEG=<val>
```
Rate-limited to 200 ms during RAMP_UP / RAMP_DOWN / SETTLING (`M750.cpp:34,51`), emitted per sample (100 ms) during MEASURING, and once each at the end of `doIndexHome()` and `doSetHome()`. `RPM` = `vel × 60`; `POS` = raw encoder turns; `DEG` = `fmod((pos − _homePos) × 360, 360)` normalized to [0, 360). **`DEG` is only meaningful when `isDatumValid()` is true** — nothing in the telemetry line says whether it is.

**`DIAG:`** — M753 only. Not a `STATE:`/`OK:`/`ERR:` producer; neither UI's spincoater panel reacts to it beyond logging.

#### Every bounded wait and its timeout

Nothing in the subsystem can hang forever at the stack tip — that was the point of PR #57.

`spincoater.cpp`: stale-flush dwell 50 ms (`:130`) · boot Vbus probe **15000 ms** (`:137`) · boot index search enters state 6 **5000 ms** (`:172`) · boot index search completes **30000 ms** (`:194`) · boot encoder settle 300 ms (`:205`) · boot arm dwell 100 ms then a **single sample** (`:218`) · boot trap-traj settle **8000 ms** (`:227`) · post-IDLE dwell 100 ms (`:244`) · `readRaw()` reply **500 ms** (`:294`) · `feedback()` reply **200 ms** (`:329`) · `feedbackStable()` **3 attempts** ≈1.35 s worst case (`:371-389`) · `clearErrors()` drain 50 ms (`:422`) · `forceIdle()` **3000 ms** default (`:461`, `spincoater.h:121`) · `ensureClosedLoop()` **50 attempts** (`:494`) and **90000 ms** wall clock (`:499`) · full-calibration cap **2 calibrations** (`:515`) · full-calibration completion **60000 ms** (`:533`) · `doIndexHome()` liveness **5000 ms** (`:560`) · enter IDLE **3000 ms** (`:570`) · index search enters state 6 **3000 ms + extraWindow** (`:583`) · index search completes **30000 ms** (`:623`) · encoder settle 300 ms (`:648`) · closed-loop arm **2000 ms** (`:697`) · trap-traj settle **8000 ms** (`:720`), success window `<0.003` turns and `<0.05` rev/s (`:724`).

`M750.cpp`: telemetry rate limit 200 ms (`:34`) · measure sample interval 100 ms (`:79`) · **measure telemetry liveness 3000 ms** (`:97`) · CONNECTING **5000 ms** (`:204`) · ramp-up hard timeout `rise_s × 3000`, **floor 10000 ms** (`:243-244`) · ramp-up stall window **3000 ms** with <50 RPM gain, gated on `>100` RPM (`:261-262`) · ramp-down no-progress timeout `sink_s × 3000`, **floor 10000 ms** (`:305-306`) · ramp-down exit threshold `|RPM| <= 6.0` (`:313`) · stop re-issue every **1000 ms** (`:318`) · **ramp-down telemetry liveness 3000 ms** (`:324`) · progress increment 0.5 RPM (`:338`) · SETTLING dwell 1000 ms (`:362`).

`M753.cpp`: diagnostic byte collection **2000 ms** (`:49`) — unchanged.

**Worst-case blocking time for one M750** is roughly boot (15 + 30 + 8 s) + closed-loop 90 s + ramp-up `max(10 s, 3×rise)` + measure `D` s + ramp-down `max(10 s, 3×sink)` + settle 1 s + index home (5+3+3+30+2+8 s). All bounded.

#### Implementation Files
- `Marlin/src/gcode/control/M750.cpp` — spin cycle handler
- `Marlin/src/gcode/control/M751_M752.cpp` — datum set + index home handlers
- `Marlin/src/gcode/control/M753.cpp` — UART diagnostic (probes ODrive Serial2 link)
- `Marlin/src/feature/spincoater.h` — ODrive communication namespace declaration (22 exported functions)
- `Marlin/src/feature/spincoater.cpp` — ODrive Serial2 raw ASCII communication layer
- Modified: `pins_RAMPS_14_RMR.h` (J_MIN_PIN 17→23), `gcode.cpp` (`:972-975`, four cases), `gcode.h` (`:1132-1135`), `Configuration_adv.h` (`SPINCOATER` flag `:3506` **and** `EMERGENCY_PARSER` `:2454`, enabled *for* the spincoater), `MarlinCore.cpp` (`kill()` disarm `:904`, `setup()` `startupSafetyDisarm()` `:1284`), `ini/features.ini:255` (build-src-filter registration for all four source files)

#### Feature Flag
`#define SPINCOATER` in Configuration_adv.h. All spincoater code is conditional — removing this define removes all spincoater functionality from the build. Note that `EMERGENCY_PARSER` is a **separate** define and does not disappear with it.

#### ODrive Boot Sequence (`spincoater.cpp:124-276`)

`boot()` runs on the first M750/M751/M752 call. **M753 does not boot** — it calls `Spincoater::init()` only.

0. **`init()`** — `Serial2.begin(115200)` if not already open, then a stale-buffer flush: send a bare newline, `flush()`, `safe_delay(50)`, drain everything waiting (`:128-131`).
1. **`STATE:WAITING_ODRIVE`** — probe `r vbus_voltage` in a 15 s loop. The reply is **strict-parsed and must be > 1.0 V** (`:143`); a garbled reply no longer counts as "found". Success emits `DATA: Vbus=<raw>V`. Failure → `ERR: ODrive not detected (15s timeout)`, `boot()` returns **false** and the calling M-code aborts.
2. **`STATE:INDEX_SEARCH_BOOT`** — `clearErrors()`, force IDLE, request `ENCODER_INDEX_SEARCH`. Poll ≤5 s for state 6, re-requesting after 1 s. On entry: `STATE:INDEX_SEARCH_ACTIVE`. (AMT102 is incremental and loses position on power cycle.)
3. Wait for return to IDLE, ≤30 s. `bootHomed` is true only if both step 2 and step 3 succeeded. **`procedure_result` is NOT checked here** — see the known weaknesses above.
4. `safe_delay(300)` encoder settle.
5. **`STATE:INDEX_SETTLE_BOOT`** — switch to POSITION/TRAP_TRAJ at `vel_limit 0.25` rev/s, arm closed loop, and command `t 0 0.0` (the index mark). 8 s watchdog; success emits `DATA: BootSettleErr=<deg> deg`. **Both the arm check and the timeout are silent on failure.**
6. Return to IDLE, restore VELOCITY/VEL_RAMP control mode.
7. `feedbackStable()` for the initial position → `DATA: InitialPos=`, then `_homePos = initPos` and `_datumSet = bootHomed`, plus one of three mutually exclusive `WARN:` lines (`:262`, `:264`, `:270`).
8. **`OK: READY`**, `_ready = true`.

**The ODrive *probe* is deferred; Serial2 itself is not.** `MarlinCore.cpp:1284` runs `Spincoater::startupSafetyDisarm()` during Marlin `setup()` — positioned **before** `SETUP_RUN(hal.init_board())` (`:1287`) — which calls `emergencyStop()` → `init()` → `Serial2.begin()` and transmits two `w axis0.requested_state 1` lines. **Pin 16 is therefore driven on every Mega power-on or reset**, including the DTR reset a browser triggers on connect. Issue #40.

#### E-Stop Path, End to End

1. `EMERGENCY_PARSER` is enabled (`Configuration_adv.h:2454`). The serial RX ISR pattern-matches `M112` and sets `EmergencyParser::killed_by_M112` **without the command entering the 4-slot queue** (`BUFSIZE 4`). That is the whole point: a blocking M750 never drains the queue.
2. Dispatch happens in `Temperature::task()`, reached from `idle()` and from `safe_delay()` (which calls it every ≤50 ms slice). Every cycle-level loop in `spincoater.cpp` and `M750.cpp` calls one or both. The two short reply-wait loops that do not call `idle()` poll the flag directly and break early (`spincoater.cpp:296`, `:331`), so worst-case added latency is one truncated reply wait, not a full 500 ms.
3. `kill()` (`MarlinCore.cpp:897`) runs, in order: `disable_all_heaters()` → `cutter.kill()` → **`Spincoater::emergencyStop()` (`:904`)** → `Error:Printer halted. kill() called!` → `minkill(true)`.
4. `emergencyStop()` writes `w axis0.requested_state 1` **twice** with a `flush()` after each (~2.3 ms per write) and reads no reply. **The ODrive is DISARMED, not braked — the rotor freewheels** (gotcha #19). Coast-down time from full speed has **never been measured**.
5. `minkill(true)` (`MarlinCore.cpp:927-967`): ~600 ms message drain → `cli()` → ~250 ms → heaters off again → `stepper.disable_all_steppers()` → **`for (;;) hal.watchdog_refresh();`**. The watchdog is deliberately *petted*, so the board **never self-resets**. The `hal.reboot()` branch is compiled out — it needs `HAS_KILL` or `SOFT_RESET_ON_KILL`, and neither is defined (no kill button is wired).

**Recovery is a hardware reset, never M999** (gotcha #6): reconnect the serial port in the UI (the ATmega16U2 bridge pulses RESET on DTR), press the board's RESET button, or power-cycle. On reboot, `startupSafetyDisarm()` disarms the ODrive as early as the UART can transmit. **Recovery destroys the datum** — re-run M751 before any layer that depends on angular registration.

With `EMERGENCY_PARSER` enabled there is **no queued M112 handler at all** — `M108_M112_M410.cpp` is entirely `#if DISABLED(EMERGENCY_PARSER)`, and `gcode.cpp:607-608` compiles `case 108: case 112: case 410:` to a bare `break;`. An M112 reaching the queue would be silently discarded. The RX-path flag checked in `Temperature::task()` (`temperature.cpp:1880`) is the only path to `kill()`. That is fine in practice — the parser scans the RX stream, so M112 cannot actually arrive via the queue — but there is no second, redundant handler.

#### Where the firmware's tokens and the two HTML UIs currently DISAGREE

Both UIs carry functionally equivalent — not byte-identical — spincoater parsing (`RMR_Controller.html:968-1039`, `RMR_Touch.html:1018-1064`) and **neither was updated by this stack**. All of the following apply to both files and are tracked in issue #47.

| # | Defect | Effect |
|---|---|---|
| A | `HOME_SETTLE` has no `stateMap` key and falls through to `includes('HOME_SET')` | While the rotor is actively crawling back to the datum, both UIs display phase = idle, "Home datum set" |
| B | `ERR: HOME_SET_FAILED` contains `HOME_SET` | A **failed** M751 renders as success |
| C | `ERR: CYCLE_COMPLETE_NO_HOME` contains `CYCLE_COMPLETE` | A failed post-spin home renders as success; the Touch UI additionally fires a green success toast (`Touch:1043`) |
| D | `MEASURE_LINK_LOST`, `DECEL_LINK_LOST`, `DECEL_STALL` match nothing, and M750 then returns with no completion marker | The phase indicator is left stuck on "Measuring speed..." or "Decelerating..." **permanently**, with a stale RPM gauge |
| E | `INDEX_INCOMPLETE` and `INDEX_HOME_FAILED` match nothing | A failed M752 produces no phase change at all (no false success either — `INDEX_INCOMPLETE` does not contain `INDEX_COMPLETE`) |
| F | `INDEX_FOUND_INSTANT` and `INDEX_SETTLE` are dead `stateMap` keys | Harmless, but misleading to anyone reading the UI as a spec of the serial contract |
| G | `WARN:` is entirely unhandled | Every datum-integrity message renders as ordinary grey console text — no toast, no phase change, no card update |
| H | `ERR:` lines route to `logRx()`, not `logErr()` | The spincoater panel has no error styling for firmware-originated errors at all |
| I | Stat cards go stale rather than clearing on an aborted measure | See the `DATA:` irregularities above |
| J | `procedure_result`, `active_errors`, `disarm_reason`, `HomeSettleErr`, `BootSettleErr`, `InitialPos`, `accel` parse but hit no branch | Console log only |
| K | Both Program Runners advance on any bare `ok` | A production program continues past every spincoater failure (gotcha #23, issue #48) |
| L | After M112 the firmware never sends another `ok` | A running program stalls silently; neither UI detects the halt or the `Error:Printer halted` line |

## File Inventory

| File | Location | Purpose |
|------|----------|---------|
| Configuration.h | `Marlin/` | Main firmware config |
| Configuration_adv.h | `Marlin/` | Advanced config + `SPINCOATER` flag and its five defaults (`:3506-3516`) + `EMERGENCY_PARSER` (`:2454`) + DIRECT_PIN_CONTROL (relays) |
| pins_RAMPS_14_RMR.h | `Marlin/src/pins/ramps/` | Custom pin mapping (J_MIN_PIN=23, relay pin reservations D4/D42) |
| boards.h | `Marlin/src/core/boards.h` | Board ID registration — needs 1 line added |
| pins.h | `Marlin/src/pins/pins.h` | Board routing — needs 2 lines added |
| G28.cpp | `Marlin/src/gcode/calibrate/` | Patched for custom homing order + gripper close |
| M42.cpp | `Marlin/src/gcode/control/` | Patched — early return on S<=1 to skip hal.set_pwm_duty (AVR timer hijack fix) |
| M280.cpp | `Marlin/src/gcode/control/` | Patched — firmware servo clamp removed, POLARGRAPH gate on T<ms> removed |
| M750.cpp | `Marlin/src/gcode/control/` | Spincoater spin cycle handler |
| M751_M752.cpp | `Marlin/src/gcode/control/` | Spincoater datum set + index home |
| M753.cpp | `Marlin/src/gcode/control/` | ODrive UART diagnostic (Serial2 probe) |
| spincoater.h | `Marlin/src/feature/` | ODrive raw ASCII communication namespace |
| spincoater.cpp | `Marlin/src/feature/` | ODrive Serial2 communication implementation |
| gcode.cpp | `Marlin/src/gcode/` | M-code dispatch (M750/M751/M752/M753 cases added, `:972-975`) |
| gcode.h | `Marlin/src/gcode/` | M-code declarations (M750/M751/M752/M753 added, `:1132-1135`) |
| MarlinCore.cpp | `Marlin/src/` | Patched — `Spincoater::emergencyStop()` in `kill()` (`:904`); `Spincoater::startupSafetyDisarm()` in `setup()` (`:1284`). Issue #40 |
| features.ini | `Marlin-2.1.2.7/ini/` | `SPINCOATER` build-src-filter registration (`:255`) for spincoater.cpp + M750/M751_M752/M753.cpp |
| SanityCheck.h | `Marlin/src/inc/` | Patched — DEACTIVATE_SERVOS_AFTER_MOVE check bypassed |
| PIN_MAP.md | repo root | Consolidated pin map + wiring reference (authoritative bench doc). **Not updated by this stack** — it does not yet reflect the e-stop / homing / bounded-wait / strict-parsing changes, and it contradicts this file on J11 logic power (see the UNVERIFIED note above) |
| RMR_Controller.html | repo root | Unified Web Serial controller (gantry + spincoater) — click-optimised, full control, for debugging/tuning |
| RMR_Touch.html | repo root | Touchscreen-optimised Web Serial UI — for operation. Functionally equivalent (not byte-identical) spincoater parsing to the Controller — patch both files separately |
| fullcode.gcode | repo root | Production DEA layer program — `M753` → `M752` → `M751` → dispense → lid close → `M750 S1000 D50 A3 C3 H1` → UV cure → lid open |
| DemoProgram.gcode | repo root | Demo pick-and-place cycle |
| AI_ATTRIBUTION.md | repo root | AI contribution record |
| SpincoaterStage/platformio.ini | `SpincoaterStage/` | PlatformIO config for Nano RP2040 Connect (retired reference) |
| SpincoaterStage/src/main.cpp | `SpincoaterStage/src/` | Spincoater test firmware v2.6 (Nano — retired reference) |
| SpincoaterStage/SpincoaterDashboard.html | `SpincoaterStage/` | Standalone spincoater dashboard v2.5 (retired reference — speaks the Nano protocol, not Marlin's) |
| SpincoaterStage/INTEGRATION_PLAN.md | `SpincoaterStage/` | Historical Marlin/Mega integration design doc. **Its §3 M750 parameter table is WRONG** — it documents A/C as rev/s² rates; they are seconds. Use this file, not that one |
| SpincoaterStage.ino | repo root | Original Arduino IDE sketch (reference only, superseded) |
| ~~SpincoaterPinMap.jfif~~ | repo root | **MISSING** — referenced here, in `README.md` and twice in `PIN_MAP.md` as the ODrive J11 pinout image, but `git ls-files` finds no such file and it is not on disk. The remote-owner/on-site-colleague split makes this a real gap; either restore the image or delete all four references |

## What's Left To Do

### Gantry / Marlin
- [ ] Confirm DIP switch settings on ALL DM556T drivers (verify 1600 steps/rev = 1/8 µstep on all drivers)
- [x] ~~Wire and assign lid servo GPIO~~ (pin 6, SERVO1_PIN enabled, 0–180° no clamp)
- [x] ~~Choose and wire solenoid valve pin~~ (pin 42, current active-HIGH module on the 3.3 V buck rail — the original Bestep active-LOW part was replaced, see gotcha #13)
- [x] ~~Wire UV lamp relay~~ (pin 4, current active-HIGH module on the 3.3 V buck rail — see gotcha #13)
- [x] ~~Enable DIRECT_PIN_CONTROL for M42~~ (Configuration_adv.h, plus M42.cpp patch for timer-hijack bug)
- [ ] Write production G-code sequences for the actual robot workflow (use UV_ON/UV_OFF labeled macros — see gotcha #13)
- [ ] Bench-verify the solenoid valve relay with actual gas connection (UV lamp already visibly confirmed)
- [x] ~~Test each axis individually after first flash (direction, distance, endstop logic)~~ — all axes verified, directions corrected
- [x] ~~Determine if `DISABLE_OTHER_EXTRUDERS` needs to be commented out~~ (N/A — only 1 extruder now)
- [x] ~~Calibrate servo angles for gripper open/close positions~~ (90° closed, 170° open)
- [x] ~~Set actual travel limits~~ (X=770, Y=150, Z=186, I=343, J=304 — matching `Configuration.h:1741,1743,1745`)
- [x] ~~Add Z endstop if repeatable Z homing is needed~~ (Z endstop on pin 40 via Z_STOP_PIN)
- [x] ~~Tune feedrates and accelerations~~ (tested, production values set)

### Spincoater — Benchtop Testing (Nano RP2040) — RETIRED, hardware no longer in the machine
The two open items at the bottom of this list have been re-issued against the Marlin path in the section below; they still matter there.
- [x] ~~PlatformIO project setup~~ — targeting nanorp2040connect
- [x] ~~Parameterized spin commands~~ — SPIN, START, SET, STATUS, STOP, HOME, SETHOME
- [x] ~~Real-time telemetry~~ — RPM + position via ODrive `f 0` command
- [x] ~~Absolute degree display~~ — degrees from SETHOME datum on circular dial
- [x] ~~E-stop works mid-cycle~~ — checkStop() in all blocking loops
- [x] ~~Homing vs Set Home separation~~ — HOME preserves datum, SETHOME resets it
- [x] ~~Web Serial dashboard~~ — SpincoaterDashboard.html v2.5
- [x] ~~Welford's online algorithm~~ — replaced float array with O(1) streaming stats
- [ ] Verify dial behavior after multiple consecutive spin cycles
- [ ] Long-duration stability test (>60s cycles)

### Spincoater — Marlin/Mega Integration
- [x] ~~**Hardware:** Move J endstop from pin 17 to pin 23~~ — `J_MIN_PIN` updated in pins file
- [x] ~~**Firmware:** SPINCOATER feature flag, spincoater.h/.cpp, M750/M751/M752/M753~~ — all implemented
- [x] ~~**Dashboard:** Merge spincoater panel into RMR_Controller.html~~ — RPM gauge, dial, stats, params all integrated
- [x] ~~**Hardware:** Wire Serial2 (pins 16/17) to ODrive J11~~ — TX2→J11 pin 4, RX2→J11 pin 3, GND, 5V
- [x] ~~**Test:** Flash updated Marlin, verify `G28 B` with J endstop on pin 23~~ — pass
- [x] ~~**Test:** Verify `M119` shows J endstop correctly on new pin~~ — pass
- [x] ~~**Test:** M753 UART diagnostic~~ — ODrive responds with Vbus voltage (24.07V), 11 bytes in 4ms
- [x] ~~**Test:** `M750 S3000 D10 A5 C1 H1` — first integrated spin cycle~~ — pass
- [x] ~~**Debug:** AVR `println()` sends `\r\n`, ODrive expects bare `\n`~~ — fixed with `print()` + `write('\n')`
- [ ] **Test:** M751 (set home) and M752 (index home) standalone — note M752 now **rotates the chuck** back to the datum (gotcha #24)
- [ ] **Test (bench, issue #40):** M112 during M750 at ≥3000 RPM. The mechanism changed in `b81c8a1` — it is no longer "via idle() processing". Confirm (a) the kill is dispatched within one poll interval from the RX path, (b) the ODrive receives IDLE and the chuck **FREEWHEELS** to a stop (no braking — no confirmed brake resistor), (c) the board is dead afterwards and only a reset/reconnect recovers it, (d) on reboot `startupSafetyDisarm()` fires. The datum is LOST across this reset (issue #54)
- [ ] **Test:** Spincoater telemetry, phase indicator and stat cards in **both** `RMR_Controller.html` and `RMR_Touch.html` — including the failure tokens (see gotcha #15 and issue #47)
- [ ] **Test:** dial behaviour after multiple consecutive spin cycles — re-issued from the retired Nano list; issue #55's latching >1-turn guard is exactly what this would expose
- [ ] **Test:** long-duration stability (>60 s cycles) — re-issued from the retired Nano list
- [ ] Write production G-code sequences with spin coating steps

### Spincoater — UNMERGED AND UNVERIFIED (as of this revision)
Nothing in the PR stack below is merged, and **none of it has run on the machine**. Every item compiles (`pio run -e mega2560`; flash 29.7%, RAM 42.7%) and has passed adversarial review only. Merge order is forced: 38 → 39 → 51 → 56 → 57 → 58 (each PR's base is its predecessor's branch, not `main`).
- [ ] Bench-verify PR #38/#39 — settle to saved home datum, fallback DEG, >1-turn guard, UV relay S-value
- [ ] Bench-verify PR #51 (issue #40) — `EMERGENCY_PARSER` e-stop + ODrive IDLE disarm. **Highest-consequence change in the stack:** it alters the serial RX hot path for *every* command, so confirm normal G-code still streams at 250000 baud before trusting M112 itself
- [ ] Bench-verify PR #56 (issues #41, #43) — honest `doIndexHome()` exits, fault introspection, datum preservation. Expect runs that *appeared* to work before to now report failures; that is the intent, not a regression
- [ ] Bench-verify PR #57 (issue #42) — every blocking wait bounded, dead-link detection. The timeout constants are guesses; characterise real sink time for a loaded chuck before trusting them
- [ ] Bench-verify PR #58 (issue #44) — strict ODrive reply parsing (no laundered zeros)
- [ ] **#46 BENCH TASK — leading root cause:** ODrive 0.6.x index/encoder config on the S1. The decisive observation is **after an index search, does `pos_estimate` return near 0 (re-referenced) or hold its pre-search value?** That single answer decides the design of #52, #54, #55 and the datum half of #45. Blocked by nothing; can start today. **Gap:** the `odrive_report.py` one-shot script referenced by the issue is not in this repo (verified — no file matching `*odrive*report*`); it must be recovered or rewritten first
- [ ] #45 boot performs a second index search and overwrites the datum — unstarted
- [ ] #47 UI serial contract — both UIs mis-render the new failure tokens (gotcha #15) — unstarted. Must be written against the stack-tip token list even though it merges independently
- [ ] #48 Program Runner wait-for-ok is defeated by auto-report M114 `ok`s — unstarted. Present in **both** UIs, not just the Controller
- [ ] #54 datum is RAM-only, lost on every reset — no EEPROM persistence (gotcha #17)
- [ ] #55 the >1-turn guard latches; only M751 clears it (gotcha #18). **Do not resolve this by restoring automatic re-datuming** — that self-healing *was* bug #41
- [ ] #52 post-spin homing design review — blocked by #46
- [ ] #53 gripper servo shudder — bench diagnosis first
- [ ] #49 elastomer-dependent dispense volume and UV cure time in the touchscreen GUI — extend `RMR_Touch.html`; **no new GUI**

**Open questions only the bench or the owner can answer:** is a braking resistor fitted on the S1 (determines whether active braking on e-stop is ever viable)? Which end supplies J11 logic power (this file vs `PIN_MAP.md` disagree)? What is the datum fundamentally — an absolute multi-turn encoder position, or a fractional offset from the index mark? The `DEG` maths already assumes the latter (`fmod((pos − _homePos) × 360, 360)`), so the representation and its use currently disagree; #46 must answer first.