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
| — | — | Spincoater | — | — | — | — | ODrive S1 on Serial2 (pins 16/17) — M750/M751/M752 |

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
Two opto-isolated relay modules (Bestep JQC3F-03VDC-C) control the UV cure lamp and the dispense solenoid valve. Both modules are powered from a dedicated 3.3 V buck converter rail sharing ground with the Mega. Triggered via `M42` from G-code (`DIRECT_PIN_CONTROL` enabled in `Configuration_adv.h`).

- **UV lamp:** pin 4 (RAMPS SERVO3 slot, AVR OC0B / Timer0)
- **Solenoid valve:** pin 42 (AUX2_08 header, AVR PL7, pure GPIO — no timer compare unit)
- **Logic:** ACTIVE-LOW. The opto LED cathode ties to the IN pin, so pulling IN to GND energizes the coil.
  - `M42 P4 S0` = UV ON, `M42 P4 S1` = UV OFF
  - `M42 P42 S0` = valve OPEN, `M42 P42 S1` = valve CLOSED
- **Boot-time behavior:** Mega inputs float at reset. The relay module's internal pullup pulls IN high, keeping both relays de-energized until Marlin drives the pins — no chatter and no unsafe state during bootloader handoff.

**Why pin 42 and not pin 11 or pin 28:** pin 11 = OC1A collides with Marlin's stepper ISR (Timer1); `analogWrite(11, ...)` fights the stepper timer continuously. Pin 28 is `E0_DIR_PIN` and is actively driven by the stepper subsystem on every syringe move. Pin 42 (PL7) has no hardware timer compare unit and no stepper/endstop/servo claim. See gotcha #12 for the underlying M42.cpp bug that caused the initial pin-11 failure and the patch that fixes it.

### Dual-Y Configuration
The two Y-axis motors are each on their own DM556T driver, with independent PUL/DIR/ENA signal sets coming from the Mega. Pin set Y (A6/A7/A2) drives the first Y motor and pin set Y2 (36/34/30) drives the second. `Y2_DRIVER_TYPE` is defined in `Configuration.h`, which is what tells Marlin to pulse both pin sets in lockstep so the motors stay synchronized — the synchronization happens in firmware, not by splicing the Mega outputs together externally. Because each motor has its own driver, auto-squaring (`Y_DUAL_ENDSTOPS`) is possible in principle, but only if a second Y endstop is added (currently only pin 14 / Y_MIN is populated).

## Firmware Architecture

### Board Definition
Custom board `BOARD_RAMPS_14_RMR` (ID 1020) inherits from stock RAMPS 1.4 and overrides pin assignments for I/J linear axes and E0 extruder, plus resolves conflicts.

**Files that define the board:**
- `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` — pin overrides and conflict resolution
- `Marlin/src/core/boards.h` — board ID registration (add `#define BOARD_RAMPS_14_RMR 1020`)
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
| `src/gcode/control/M280.cpp` | Firmware-side servo clamp removed — soft limits enforced in HTML slider only. Override textbox allows full 0–180°. |
| `src/inc/SanityCheck.h` | Sanity check for DEACTIVATE_SERVOS_AFTER_MOVE commented out — stock Marlin requires Z_PROBE_SERVO_NR or switching toolhead, which don't apply here. |

### Critical Gotchas
1. **Cold extrusion:** `EXTRUDE_MINTEMP` is set to 0, so E-axis moves work without temperature checks. `M302 S0` is **not compiled in** (returns "Unknown command") and is not needed.
2. **Custom homing order (G28.cpp patched):** A bare `G28` homes in order: [lid servo opens to 30°] → Z → Y → J(Syr.Ht) → [gripper servo closes to 90°] → X → I(Filter Feed). HOME_Z_FIRST is enabled, Z_SAFE_HOMING is disabled.
3. **Gripper closes before X homing:** Servo 0 is commanded to 90° with a 300ms delay before X homing begins, to prevent the gripper from colliding with the frame.
4. **Filter Feed homes to MAX:** I_HOME_DIR=1, endstop is on the far end (I_MAX, pin 15). All other axes home to MIN.
5. **Servo jitter prevention:** `DEACTIVATE_SERVOS_AFTER_MOVE` cuts PWM signal 2 seconds after `M280` command. Servo goes limp after that — fine if grip is mechanically self-holding. SanityCheck.h patched to allow this without a Z probe defined.
6. **E-Stop recovery:** Send `M999` to reset firmware after `M112` emergency stop, instead of unplugging USB.
7. **Pin 17 freed for Serial2:** J endstop moved from pin 17 (TX2) to pin 23. Serial2 (pins 16/17) now connects to the ODrive S1 for spincoater control. Pin 16 = TX2 → ODrive RX, Pin 17 = RX2 → ODrive TX.
8. **Axis name mapping:** G-code uses A/B for the I/J axes (set via AXIS4_NAME/AXIS5_NAME). Marlin restricts these names to A,B,C,U,V,W — 'I' and 'J' are not valid axis names. This affects ALL G-code commands: M201, M203, G28, G1, etc. must use A/B, not I/J.
9. **Z endstop EMI history:** Pin 18 (Mega TX1) suffered severe false triggers from stepper EMI during homing. Noise threshold, 100nF cap on signal→GND, and external pullup resistor were insufficient. Moved to pin 40 (plain GPIO, no alternate function) using `Z_STOP_PIN` in pins file (not `Z_MIN_PIN`) because `pins_postprocess.h` can override `Z_MIN_PIN`. The `Z_STOP_PIN` approach lets postprocess derive `Z_MIN_PIN` automatically. Hardware: 100nF ceramic cap from pin 40 to GND recommended. Pin 18 is now free.
10. **M400 before servos in G-code programs:** M280 (servo) executes immediately when parsed, not when the motion planner finishes preceding G1 moves. Always place `M400` before `M280` in G-code sequences to drain the planner queue first. G4 (dwell) alone is NOT a reliable substitute.
11. **AVR Serial.println() sends `\r\n`, ODrive expects bare `\n`:** On AVR (Mega 2560), `Serial.println()` appends `\r\n` (0x0D 0x0A). The ODrive S1 ASCII protocol expects only `\n` as the command terminator — the stray `\r` makes commands fail with "unknown command." All ODrive UART writes in spincoater.cpp use `print()` + `write('\n')` instead of `println()`. The Nano RP2040 (mbed/ARM) `println()` sends only `\n`, which is why the standalone spincoater firmware worked without this issue.
12. **Stock M42.cpp calls analogWrite on AVR, even for S0/S1:** The stock implementation calls `extDigitalWrite(pin, pin_status)` and then unconditionally falls through to `hal.set_pwm_duty(pin, pin_status)`. On AVR that maps to `analogWrite()`, which attaches the pin to its hardware timer compare unit — so `M42 P11 S1` ends up configuring Timer1 OC1A at 1/255 duty, fighting Marlin's stepper ISR (Timer1) continuously. Symptom: relay fires once, then M42 "stops working" until the Mega resets via DTR. The STM32 path already had a `pin_status <= 1 && !PWM_PIN(pin)` guard; we extended it to all architectures as `if (pin_status <= 1) return;` so digital-only writes always take the pure `digitalWrite` path. When choosing pins for `M42` relay triggers, prefer pads with no hardware timer compare unit at all (pin 42 = PL7 is clean; pin 4 = OC0B is only safe because of this patch).
13. **Bestep relay modules are active-low:** The UV lamp (pin 4) and solenoid valve (pin 42) Bestep JQC3F-03VDC-C modules energize on IN=LOW. G-code convention: `M42 Pxx S0` = ON, `M42 Pxx S1` = OFF. The opto LED cathode is tied to the IN pin with the anode on VCC, so pulling IN to GND lights the opto and drives the coil transistor. Side benefit: a floating input at Mega reset is pulled HIGH by the module's internal pullup, which is the safe de-energized state — no chatter on boot. Document this convention near every M42 call in production G-code (e.g. `M42 P4 S0 ; UV_ON`) because S0-means-on is counter-intuitive and will confuse any future reader.

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
```

### Relays (UV lamp + solenoid valve — ACTIVE-LOW)
```gcode
M42 P4  S0       # UV lamp ON       (pin 4,  Bestep active-low)
M42 P4  S1       # UV lamp OFF
M42 P42 S0       # solenoid valve OPEN  (pin 42, Bestep active-low)
M42 P42 S1       # solenoid valve CLOSED
```
S0 = energized, S1 = off. Requires `DIRECT_PIN_CONTROL` (enabled in `Configuration_adv.h`).

### Spincoater (ODrive S1 via Serial2)
```gcode
M750 S5000 D30 A5 C1 H1   # spin cycle: 5000 RPM, 30s, 5s ramp-up, 1s ramp-down, home after
M750                       # spin with defaults (S5000 D30 A5 C1 H1)
M751                       # set current position as 0° home datum
M752                       # encoder index search (preserves existing datum)
M753                       # UART diagnostic — probes ODrive Serial2 link, reports raw response
```

### Motion Tuning (runtime, no rebuild needed)
```gcode
M201 X500 Y200 Z100 A150 B50 E500   # set max acceleration (mm/s²)
M203 X400 Y333 Z50 A33 B50 E8       # set max feedrate (mm/s)
M500             # save settings to EEPROM
M501             # load settings from EEPROM
```

### Diagnostics
```gcode
M119             # report endstop states (use to verify wiring)
M503             # report all active firmware settings
M92              # report steps/mm (M92 X57.14 Y57.14 Z320 A320 B320 E1600 to override)
M999             # reset firmware after emergency stop (M112)
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
- **Gripper servo** — slider (90°–170°), Open/Close quick buttons, override textbox (0–180°)
- **Lid servo** — slider (0°–180°)
- **Solenoid** toggle with configurable pin
- **Position readout** with auto-report (1s polling via M114)
- **E-Stop** button (M112) with **Reset (M999)** button for recovery without USB replug
- **Raw G-code** input with command history
- **Spincoater panel** (collapsible, starts open) — M750/M751/M752 controls:
  - Parameter inputs: RPM, Duration, Rise Time, Sink Time, Encoder homing toggle
  - Start Spin / Stop / Set Home / Index Home buttons
  - Live RPM gauge with progress bar, SVG circular position dial with shortest-path needle rotation
  - Stats cards: mean, std dev, min, max, range, samples, bus voltage, home position
  - Phase indicator with color-coded status dot
  - Parses `echo:SPIN TELEM:`, `echo:SPIN DATA:`, `echo:SPIN STATE:` prefixes from Marlin serial
- **Program Runner** — textarea for G-code programs, Load .gcode button, Run/Pause/Stop controls, line counter, Wait-for-ok checkbox. Sends lines sequentially, waits for Marlin `ok` before sending next line.
- **Keyboard shortcuts:** Arrow keys = XY, PgUp/PgDn = Z, Esc = E-Stop (disabled when textarea focused)

## File Inventory

| File | Location in Marlin Tree | Purpose |
|------|------------------------|---------|
| Configuration.h | `Marlin/` | Main firmware config |
| Configuration_adv.h | `Marlin/` | Advanced config |
| pins_RAMPS_14_RMR.h | `Marlin/src/pins/ramps/` | Custom pin mapping |
| boards.h | `Marlin/src/core/boards.h` | Needs 1 line added (board ID) |
| pins.h | `Marlin/src/pins/pins.h` | Needs 2 lines added (routing) |
| G28.cpp | `Marlin/src/gcode/calibrate/` | Patched for custom homing order + gripper close |
| M280.cpp | `Marlin/src/gcode/control/` | Patched — firmware servo clamp removed |
| SanityCheck.h | `Marlin/src/inc/` | Patched — DEACTIVATE_SERVOS_AFTER_MOVE check bypassed |
| RMR_Controller.html | repo root | Browser-based Web Serial controller UI |
| DemoProgram.gcode | repo root | Demo pick-and-place cycle: left/right filters → spincoater → dispose |

## Spin Coater Subsystem

### Overview

The spin coater uses an ODrive S1 motor controller driving a D5312s-330kV motor with an AMT102 encoder. In the **final system**, the Mega 2560 (running Marlin) drives the ODrive S1 directly over UART — there is NO second Arduino. The current benchtop test setup uses an Arduino Nano RP2040 Connect as a stand-in for the Mega, connected to a PC via the `SpincoaterDashboard.html` Web Serial interface.

### Architecture

```
Final system:     Mega (Marlin + custom M750) ──Serial2──► ODrive S1 ──► Motor
Benchtop test:    PC (SpincoaterDashboard.html) ──USB──► Nano RP2040 ──Serial1──► ODrive S1 ──► Motor
```

### Hardware

- **Motor:** D5312s-330kV brushless outrunner
- **Controller:** ODrive S1
- **Encoder:** AMT102 (incremental with index pulse)
- **ODrive control mode:** Ramped Velocity Control (vel_ramp_rate for accel/decel)
- **UART baud:** 115200

### Benchtop Test Setup (Nano RP2040 Connect)

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

### Firmware (SpincoaterStage/src/main.cpp — v2.5)

#### Serial Protocol (115200 baud, newline-terminated)

| Command | Description |
|---------|-------------|
| `SPIN <rpm> <dur_s> <accel> <decel> <home 0\|1>` | Run a full spin cycle with specified parameters |
| `START` | Run with current default parameters |
| `SET <param> <value>` | Set default: RPM, DUR, ACCEL, DECEL, HOME |
| `STATUS` | Report params + ODrive state + bus voltage + position |
| `STOP` | Emergency velocity zero — works mid-cycle (checked in all blocking loops) |
| `HOME` | Encoder index search — does NOT reset degree datum |
| `SETHOME` | Set current position as 0° datum — dial snaps to 0° |

#### Output Prefixes

All firmware output is prefixed for machine parsing:
- `OK:` — success messages
- `ERR:` — error messages
- `STATE:` — phase transitions (CONNECTING, RAMP_UP, MEASURING, RAMP_DOWN, SETTLING, HOMING, etc.)
- `DATA:` — measurement results and status data
- `TELEM:` — real-time telemetry (RPM, position, degrees from home)

#### Telemetry

Emitted every 200ms during active phases via the ODrive `f 0` command (returns pos and vel in a single round-trip):
```
TELEM: RPM=<val> POS=<val> DEG=<val>
```
- `RPM` — current motor speed (vel × 60)
- `POS` — raw encoder position in turns
- `DEG` — absolute degrees from last SETHOME datum, normalized to [0, 360)

#### Spin Cycle Phases
1. **CONNECTING** — verify ODrive responding (5s timeout)
2. **CALIBRATING** — enter closed-loop control (full calibration if needed)
3. **RAMP_UP** — set vel_ramp_rate to accel, command target velocity, wait for 98% RPM
4. **MEASURING** — Welford's online algorithm for mean/variance at 100ms intervals
5. **RAMP_DOWN** — set vel_ramp_rate to decel, command velocity 0, wait for RPM < 6
6. **SETTLING** — 1s active telemetry dwell
7. **HOMING** (optional) — encoder index search, does NOT reset degree datum

#### Homing vs Set Home
- **`HOME` / post-cycle auto-home:** Runs ODrive encoder index search (IDLE → ENCODER_INDEX_SEARCH → IDLE). Corrects encoder position for accuracy. Does NOT overwrite the degree datum (`homePos`). The dial shows the actual angular position relative to the original Set Home.
- **`SETHOME`:** Reads current encoder position, stores it as `homePos` (the 0° reference). Emits `TELEM: DEG=0.00`. This is a datum-setting operation — the user declares "this is my zero."

#### Key Implementation Details
- **E-stop works mid-cycle:** `checkStop()` polls USB serial for STOP commands inside every blocking loop (ramp-up, measure, ramp-down, settling, calibration). Previously STOP was ignored until cycle completion.
- **No `sscanf` with `%f`:** The RP2040 mbed platform's C library doesn't link float support for scanf/sscanf. All parsing uses Arduino `String.toFloat()` / `String.toInt()`.
- **No `getParameterAsFloat()`:** The ODriveUART library's getter uses `sscanf` internally — broken on RP2040. All ODrive reads use raw ASCII commands (`r <property>`, `f 0`) with manual String parsing.
- **Serial bus contention avoidance:** `lastTelemRPM` is cached from telemetry reads and used for ramp-up/ramp-down exit conditions, eliminating separate `odrive.getVelocity()` calls that would conflict with telemetry's `f 0` reads on the same UART.
- **ODrive state machine:** Cannot go directly from CLOSED_LOOP_CONTROL to ENCODER_INDEX_SEARCH. `doHome()` explicitly transitions to IDLE first, waits for the transition, then commands the index search.

### Dashboard (SpincoaterDashboard.html — v2.5)

Web Serial dashboard (Chrome/Edge only, 115200 baud). Dark theme matching RMR_Controller.html.

#### Features
- **Connection management** — connect/disconnect with status indicator
- **Parameter inputs** — RPM, Duration, Accel, Decel, Encoder homing toggle
- **Buttons:** Start, Stop, Set Home (yellow — sets 0° datum), Index Home (blue — encoder search, preserves datum), Status
- **Live RPM gauge** — progress bar scaled to target RPM, zeroes on stale (2s no telemetry)
- **SVG circular position dial** — needle rotates to show degrees from home, tick marks at 30° intervals, cardinal labels at 0/90/180/270. Needle dims to grey during high-speed spinning (> 60 RPM) where angular position is aliased. Shortest-path rotation logic prevents wraparound animation glitches (350°→10° doesn't animate 340° backwards).
- **Stats cards** — mean, std dev, min, max, range, samples, bus voltage, home position (displayed in degrees)
- **Serial console** — color-coded log levels, telemetry display toggle (default OFF), auto-scroll toggle
- **Raw command input** — send arbitrary commands to firmware

### Marlin/Mega Integration (COMPLETED)

The spincoater is now integrated into the Mega/Marlin firmware. The Nano RP2040 is eliminated from the final system. Detailed design rationale is in `SpincoaterStage/INTEGRATION_PLAN.md`.

#### Serial Port: Serial2 freed by relocating J endstop
J endstop moved from pin 17 (TX2) to pin 23. Serial2 (pins 16/17) now connects to the ODrive S1 at 115200 baud.

**Wiring: Mega ↔ ODrive S1 J11:**
- Mega pin 16 (TX2) → ODrive J11 pin 4 (RX / GPIO7)
- Mega pin 17 (RX2) → ODrive J11 pin 3 (TX / GPIO6)
- Mega GND → ODrive J11 ISOGND
- Mega 5V → ODrive J11 ISOVDD

#### Custom M-Codes: M750, M751, M752

```gcode
M750 [S<rpm>] [D<seconds>] [A<rise_seconds>] [C<sink_seconds>] [H<0|1>]
```
Blocking spin cycle. S=RPM (default 5000), D=duration (30s), A=ramp-up time (5s), C=ramp-down time (1s), H=auto-home after (1). Rise/Sink times are converted to ODrive vel_ramp_rate internally. Calls `idle()` in all blocking loops.

```gcode
M751    ; Set current encoder position as 0° home datum
M752    ; Encoder index search (does NOT reset home datum)
```

#### Implementation Files
- `Marlin/src/gcode/control/M750.cpp` — spin cycle handler
- `Marlin/src/gcode/control/M751_M752.cpp` — datum set + index home handlers
- `Marlin/src/gcode/control/M753.cpp` — UART diagnostic (probes ODrive Serial2 link)
- `Marlin/src/feature/spincoater.h` — ODrive communication namespace declaration
- `Marlin/src/feature/spincoater.cpp` — ODrive Serial2 raw ASCII communication layer
- Modified: `pins_RAMPS_14_RMR.h` (J_MIN_PIN 17→23), `gcode.cpp`, `gcode.h`, `Configuration_adv.h` (SPINCOATER feature flag)

#### Feature Flag
`#define SPINCOATER` in Configuration_adv.h. All spincoater code is conditional — removing this define removes all spincoater functionality from the build.

#### ODrive Boot Sequence (runs on first M750/M751/M752 call)
1. Serial2.begin(115200)
2. Probe `r vbus_voltage` with 15s timeout
3. Auto encoder index search (AMT102 loses position on power cycle)
4. Trapezoidal position return to index mark (slow, gentle)
5. Restore velocity control mode

This deferred boot avoids blocking Marlin startup if the ODrive isn't powered.

## File Inventory

| File | Location | Purpose |
|------|----------|---------|
| Configuration.h | `Marlin/` | Main firmware config |
| Configuration_adv.h | `Marlin/` | Advanced config + SPINCOATER feature flag + DIRECT_PIN_CONTROL (relays) |
| pins_RAMPS_14_RMR.h | `Marlin/src/pins/ramps/` | Custom pin mapping (J_MIN_PIN=23, relay pin reservations D4/D42) |
| boards.h | `Marlin/src/core/boards.h` | Board ID registration |
| pins.h | `Marlin/src/pins/pins.h` | Board routing |
| G28.cpp | `Marlin/src/gcode/calibrate/` | Patched for custom homing order + gripper close |
| M42.cpp | `Marlin/src/gcode/control/` | Patched — early return on S<=1 to skip hal.set_pwm_duty (AVR timer hijack fix) |
| M280.cpp | `Marlin/src/gcode/control/` | Patched — firmware servo clamp removed |
| M750.cpp | `Marlin/src/gcode/control/` | Spincoater spin cycle handler |
| M751_M752.cpp | `Marlin/src/gcode/control/` | Spincoater datum set + index home |
| M753.cpp | `Marlin/src/gcode/control/` | ODrive UART diagnostic (Serial2 probe) |
| spincoater.h | `Marlin/src/feature/` | ODrive raw ASCII communication namespace |
| spincoater.cpp | `Marlin/src/feature/` | ODrive Serial2 communication implementation |
| gcode.cpp | `Marlin/src/gcode/` | M-code dispatch (M750/M751/M752 cases added) |
| gcode.h | `Marlin/src/gcode/` | M-code declarations (M750/M751/M752 added) |
| SanityCheck.h | `Marlin/src/inc/` | Patched — DEACTIVATE_SERVOS_AFTER_MOVE check bypassed |
| PIN_MAP.md | repo root | Consolidated pin map + wiring reference (authoritative bench doc) |
| RMR_Controller.html | repo root | Unified Web Serial controller (gantry + spincoater) |
| DemoProgram.gcode | repo root | Demo pick-and-place cycle |
| SpincoaterStage/platformio.ini | `SpincoaterStage/` | PlatformIO config for Nano RP2040 Connect (benchtop test) |
| SpincoaterStage/src/main.cpp | `SpincoaterStage/src/` | Spincoater test firmware v2.6 (Nano — reference) |
| SpincoaterStage/SpincoaterDashboard.html | `SpincoaterStage/` | Standalone spincoater dashboard v2.5 (benchtop test) |
| SpincoaterStage/INTEGRATION_PLAN.md | `SpincoaterStage/` | Marlin/Mega integration design doc |
| SpincoaterStage.ino | repo root | Original Arduino IDE sketch (reference only, superseded) |
| SpincoaterPinMap.jfif | repo root | ODrive S1 J11 connector pinout image |

## What's Left To Do

### Gantry / Marlin
- [ ] Confirm DIP switch settings on ALL DM556T drivers (verify 1600 steps/rev = 1/8 µstep on all drivers)
- [x] ~~Wire and assign lid servo GPIO~~ (pin 6, SERVO1_PIN enabled, 0–180° no clamp)
- [x] ~~Choose and wire solenoid valve pin~~ (pin 42, Bestep active-low relay on 3.3V buck rail)
- [x] ~~Wire UV lamp relay~~ (pin 4, Bestep active-low relay on 3.3V buck rail)
- [x] ~~Enable DIRECT_PIN_CONTROL for M42~~ (Configuration_adv.h, plus M42.cpp patch for timer-hijack bug)
- [ ] Write production G-code sequences for the actual robot workflow (use UV_ON/UV_OFF labeled macros — see gotcha #13)
- [ ] Bench-verify the solenoid valve relay with actual gas connection (UV lamp already visibly confirmed)
- [x] ~~Test each axis individually after first flash (direction, distance, endstop logic)~~ — all axes verified, directions corrected
- [x] ~~Determine if `DISABLE_OTHER_EXTRUDERS` needs to be commented out~~ (N/A — only 1 extruder now)
- [x] ~~Calibrate servo angles for gripper open/close positions~~ (90° closed, 170° open)
- [x] ~~Set actual travel limits~~ (X=770, Y=150, Z=250, I=347, J=304)
- [x] ~~Add Z endstop if repeatable Z homing is needed~~ (Z endstop on pin 40 via Z_STOP_PIN)
- [x] ~~Tune feedrates and accelerations~~ (tested, production values set)

### Spincoater — Benchtop Testing (Nano RP2040)
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

### Spincoater — Marlin/Mega Integration (see INTEGRATION_PLAN.md)
- [x] ~~**Hardware:** Move J endstop from pin 17 to pin 23~~ — `J_MIN_PIN` updated in pins file
- [x] ~~**Firmware:** SPINCOATER feature flag, spincoater.h/.cpp, M750/M751/M752/M753~~ — all implemented
- [x] ~~**Dashboard:** Merge spincoater panel into RMR_Controller.html~~ — RPM gauge, dial, stats, params all integrated
- [x] ~~**Hardware:** Wire Serial2 (pins 16/17) to ODrive J11~~ — TX2→J11 pin 4, RX2→J11 pin 3, GND, 5V
- [x] ~~**Test:** Flash updated Marlin, verify `G28 B` with J endstop on pin 23~~ — pass
- [x] ~~**Test:** Verify `M119` shows J endstop correctly on new pin~~ — pass
- [x] ~~**Test:** M753 UART diagnostic~~ — ODrive responds with Vbus voltage (24.07V), 11 bytes in 4ms
- [x] ~~**Test:** `M750 S3000 D10 A5 C1 H1` — first integrated spin cycle~~ — pass
- [x] ~~**Debug:** AVR `println()` sends `\r\n`, ODrive expects bare `\n`~~ — fixed with `print()` + `write('\n')`
- [ ] **Test:** M751 (set home) and M752 (index home) standalone
- [ ] **Test:** Verify M112 E-stop works during M750 spin (via idle() processing)
- [ ] **Test:** Dashboard spincoater panel telemetry display
- [ ] Write production G-code sequences with spin coating steps