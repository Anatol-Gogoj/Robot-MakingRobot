# Robot-Making Robot (RMR)

A custom 3-axis gantry robot driven by Marlin firmware on an Arduino Mega 2560. This is **not** a 3D printer — it's a pick-and-place / dispensing system with three auxiliary linear actuators, two servos, and a solenoid valve. Marlin is repurposed here purely as a motion controller because it provides production-grade G-code parsing, trapezoidal motion planning, and multi-axis stepper coordination out of the box.

## Repository Structure

```
Robot-MakingRobot/
├── Marlin-2.1.2.7/              # Full Marlin 2.1.2.7 source tree
│   └── Marlin/
│       ├── Configuration.h          # Main firmware config (heavily customized)
│       ├── Configuration_adv.h      # Advanced config + SPINCOATER feature flag
│       └── src/
│           ├── pins/ramps/
│           │   └── pins_RAMPS_14_RMR.h  # Custom pin mapping (J endstop on pin 23, Serial2 freed)
│           ├── core/boards.h            # Board ID registration (patched)
│           ├── pins/pins.h              # Board routing (patched)
│           ├── feature/
│           │   ├── spincoater.h         # ODrive S1 communication namespace
│           │   └── spincoater.cpp       # ODrive Serial2 raw ASCII protocol layer
│           ├── gcode/calibrate/G28.cpp  # Custom homing order (patched)
│           ├── gcode/control/
│           │   ├── M42.cpp              # DIRECT_PIN_CONTROL (patched: S<=1 guard)
│           │   ├── M280.cpp             # Servo handling (patched)
│           │   ├── M750.cpp             # Spincoater spin cycle
│           │   ├── M751_M752.cpp        # Spincoater home datum / index search
│           │   └── M753.cpp             # ODrive UART diagnostic
│           └── inc/SanityCheck.h        # Servo deactivation check bypass (patched)
├── SpincoaterStage/              # Benchtop test firmware (Nano RP2040 — reference only)
│   ├── src/main.cpp                 # Standalone spincoater firmware v2.6
│   ├── SpincoaterDashboard.html     # Standalone spincoater Web Serial dashboard
│   └── INTEGRATION_PLAN.md         # Integration design rationale
├── RMR_Controller.html           # Unified Web Serial controller (gantry + spincoater)
├── SpincoaterPinMap.jfif         # ODrive S1 J11 connector pinout reference image
├── PIN_MAP.md                    # Consolidated pin map + wiring reference (authoritative bench doc)
├── claude.md                     # Detailed firmware architecture & project docs
└── README.md                     # This file
```

## Hardware Overview

### Motion System

The gantry has three Cartesian axes (X, Y, Z) plus three auxiliary linear actuators. The Filter Feed and Syringe Height are mapped as Marlin I/J linear axes (with full homing and endstop support), while the Syringe is the sole extruder (E0). All stepper drivers are external DM556T units (optoisolated PUL/DIR/ENA inputs) driven directly from Mega GPIO pins — there is no RAMPS shield, though the pin mapping inherits from RAMPS 1.4 for the gantry axes.

| Marlin Axis | G-Code | Function       | Drive           | Steps/mm |
|-------------|--------|----------------|-----------------|----------|
| X           | X      | Gantry X       | GT2-14 belt     | 57.14    |
| Y + Y2      | Y      | Gantry Y       | GT2-14 belt (2 motors, 2 drivers, firmware-synchronized via `Y2_DRIVER_TYPE`) | 57.14 |
| Z           | Z      | Gantry Z       | 5 mm lead screw | 320 |
| I           | A      | Filter Feed    | 5 mm lead screw | 320      |
| E0          | E      | Syringe        | 1 mm lead screw | 1600     |
| J           | B      | Syringe Height | 5 mm lead screw | 320      |

Steps/mm formula: `(motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev`. All drivers are set to 1/8 microstepping (1600 steps/rev with 200-step motors).

### Tuned Motion Parameters

| Parameter | X | Y | Z | A (Filter) | B (Syr.Ht) | E (Syringe) |
|-----------|---|---|---|------------|------------|-------------|
| Max feedrate (mm/s) | 400 | 333 | 50 | 33 | 50 | 8 |
| Max feedrate (mm/min) | 24000 | 20000 | 3000 | 2000 | 3000 | 500 |
| Max acceleration (mm/s²) | 500 | 200 | 100 | 150 | 50 | 500 |
| Travel limit (mm) | 770 | 150 | 186 | 343 | 304 | — |

### End Effectors and Peripherals

- **Gripper servo** — GPIO 5, `M280 P0 S<angle>`, range 90° (closed) to 170° (open)
- **Lid servo** — GPIO 6, `M280 P1 S<angle>`, 0–180° range
- **UV lamp relay** — GPIO 4, `M42 P4 S1` = ON / `M42 P4 S0` = OFF (current active-HIGH modules)
- **Solenoid valve relay** — GPIO 42, `M42 P42 S1` = ON / `M42 P42 S0` = OFF (current active-HIGH modules)

Both relays are opto-isolated modules powered from a dedicated 3.3 V buck converter rail (shared ground with the Mega). The current modules are active-HIGH (S1 = energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (S0 = energize). The HTML UI uses explicit ON/OFF button pairs with hardcoded S values, so correct polarity is handled by which button the user presses.

Servos deactivate 2 seconds after positioning (`DEACTIVATE_SERVOS_AFTER_MOVE`) to prevent PWM jitter.

### Limit Switches

All five homing axes have endstops:
- X endstop on pin 3 (X_MIN, interrupt-capable)
- Y endstop on pin 14 (Y_MIN)
- Z endstop on pin 40 (Z_MIN — moved from pin 18/TX1 due to EMI)
- I (Filter Feed) endstop on pin 15 (I_MAX — homes to far end)
- J (Syringe Height) endstop on pin 23 (J_MIN — moved from pin 17/TX2 to free Serial2 for ODrive)
- Syringe (E0) has no endstop

All switches are normally-open, wired common→GND / NO→signal, with internal pullups enabled. `G28` (home all) is safe to send.

## Firmware Details

### Custom Board Definition

A custom board `BOARD_RAMPS_14_RMR` (ID 1020) inherits from stock RAMPS 1.4 and overrides pin assignments for the I/J linear axes and E0 extruder. The following Marlin source files are modified:

| File | Change |
|------|--------|
| `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` | Custom pin map, conflict resolution, J endstop on pin 23 |
| `Marlin/src/core/boards.h` | Board ID `1020` registration |
| `Marlin/src/pins/pins.h` | Routing `MB(RAMPS_14_RMR)` → pins file |
| `Marlin/src/gcode/calibrate/G28.cpp` | Custom homing order Z→Y→J→X→I, gripper close before X |
| `Marlin/src/gcode/control/M42.cpp` | Added `pin_status <= 1` early return so digital-only writes skip `hal.set_pwm_duty()` on AVR (prevents Timer0/Timer1 conflicts) |
| `Marlin/src/gcode/control/M280.cpp` | Servo clamp removed (soft limits in HTML only). POLARGRAPH gate on T parameter removed — `M280 Px S<angle> T<ms>` now works on all servos for timed linear interpolation. |
| `Marlin/src/gcode/control/M750.cpp` | Spincoater spin cycle handler |
| `Marlin/src/gcode/control/M751_M752.cpp` | Spincoater home datum / index search |
| `Marlin/src/gcode/control/M753.cpp` | ODrive UART diagnostic |
| `Marlin/src/feature/spincoater.h/.cpp` | ODrive S1 Serial2 raw ASCII communication layer |
| `Marlin/src/inc/SanityCheck.h` | DEACTIVATE_SERVOS_AFTER_MOVE check bypassed |
| `Marlin/Configuration_adv.h` | SPINCOATER feature flag; `DIRECT_PIN_CONTROL` enabled for M42 relay triggering |
| `ini/features.ini` | Build system registration for spincoater source files |

Several stock RAMPS pins are reassigned to free GPIOs for the auxiliary motors (e.g., pin 2 repurposed from X_MAX to I_STEP, pin 9 from FAN to I_DIR). Pins 16/17 are occupied by Serial2 (ODrive link). Pins 19/20/21 conflict with Serial1 and I2C — those peripherals cannot be used without rewiring.

### Key Configuration Choices

- `EXTRUDERS 1` — syringe only; Filter Feed and Syringe Height are I/J linear axes with full homing support
- `AXIS4_NAME 'A'`, `AXIS5_NAME 'B'` — G-code letters for I/J axes
- All temperature sensors disabled (`TEMP_SENSOR_* 0`) — no heaters on this machine
- `EXTRUDE_MINTEMP 0` — allows extruder moves without temperature checks
- `INVERT_Z_DIR`, `INVERT_I_DIR`, `INVERT_J_DIR` all `true` — verified by physical testing
- Custom homing order: lid open (30°) → Z → Y → J(Syr.Ht) → gripper close (90°) → X → I(Filter Feed)
- `DEACTIVATE_SERVOS_AFTER_MOVE` with 2-second hold — prevents servo jitter

## Spin Coater Subsystem

The spin coater uses an ODrive S1 motor controller driving a D5312s-330kV brushless motor with an AMT102 incremental encoder. The ODrive is controlled directly from the Mega 2560 over Serial2 (pins 16/17) at 115200 baud using the ODrive raw ASCII protocol — there is no second Arduino.

```
Mega 2560 (Marlin + M750/M751/M752)  ──Serial2 (115200)──►  ODrive S1  ──►  Motor
```

### Spincoater G-Codes

```gcode
M750 S5000 D30 A5 C1 H1   ; spin cycle: 5000 RPM, 30s dwell, 5s ramp-up, 1s ramp-down, home after
M751                       ; set current position as 0° home datum
M752                       ; encoder index search (preserves existing datum)
M753                       ; UART diagnostic — probes ODrive link, reports raw response
```

M750 is a blocking command that runs the full cycle (boot → index search → ramp → measure → ramp-down → settle → optional home). It emits real-time telemetry and Welford's online statistics (mean, std dev, min, max RPM) over serial. The ODrive boot sequence is deferred — it only runs on the first M750/M751/M752 call, so Marlin startup isn't blocked if the ODrive isn't powered.

The `SpincoaterStage/` directory contains the original standalone firmware (Nano RP2040 Connect) and dashboard used for benchtop testing. These are reference files only — the production system uses the integrated Marlin M-codes.

## Building and Uploading

### Prerequisites

- [VS Code](https://code.visualstudio.com/) with the [PlatformIO](https://platformio.org/) extension
- USB cable to the Arduino Mega 2560

### Build Steps

1. Open the `Marlin-2.1.2.7/` directory in VS Code with PlatformIO.
2. Ensure `platformio.ini` has `default_envs = mega2560`.
3. Build: click the PlatformIO checkmark button, or run:
   ```
   pio run -e mega2560
   ```
4. Upload: click the PlatformIO arrow button, or run:
   ```
   pio run -e mega2560 -t upload
   ```

### Serial Connection

Connect via the included `RMR_Controller.html` web UI (Chrome/Edge, Web Serial API), Pronterface, or any serial terminal at **250000 baud**. Port is typically `/dev/ttyACM0` on Linux or `COM3` on Windows.

## Using the Machine

### Startup Sequence

```gcode
G28              ; home all axes (lid open → Z → Y → J → X → I) — safe, all have endstops
G92 E0           ; reset syringe position
```

### Moving the Gantry

```gcode
G1 X100 Y50 F3000    ; move to (100, 50) at 50 mm/s
G1 Z10 F600          ; lower Z 10 mm at 10 mm/s
```

Feedrates are in mm/min. Max recommended: X 24000, Y 20000, Z 3000.

### Driving Auxiliary Motors

Each auxiliary motor has its own G-code axis letter — no tool switching needed:

```gcode
G1 A50 F1000     ; move Filter Feed to 50 mm at 1000 mm/min
G1 B20 F600      ; move Syringe Height to 20 mm
G92 E0           ; reset syringe position
G1 E5 F300       ; extrude syringe 5 mm
```

### Servos, UV Lamp, and Solenoid

```gcode
M280 P0 S90      ; close gripper (90°)
M280 P0 S170     ; open gripper (170°)
M280 P1 S0       ; set lid servo to 0°
M280 P1 S30 T800 ; open lid over 800ms (timed linear interpolation)

; Relays (current modules are ACTIVE-HIGH):
M42 P4  S1       ; UV lamp ON        (active-high)
M42 P4  S0       ; UV lamp OFF
M42 P42 S1       ; solenoid valve OPEN  (active-high)
M42 P42 S0       ; solenoid valve CLOSED
```

The current relay modules are active-HIGH (S1 = energize, S0 = de-energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (S0 = ON, S1 = OFF). Always comment the intent in production G-code (e.g. `M42 P4 S1 ; UV_ON`) because the S-value meaning depends on which relay module is installed.

### Spin Coating

```gcode
M750 S3000 D10 A5 C1 H1   ; 3000 RPM, 10s, 5s ramp, 1s decel, home after
M751                       ; set current position as 0° datum
M752                       ; encoder index search (preserves datum)
M753                       ; UART diagnostic
```

M750 is blocking — Marlin will not process further commands until the cycle completes. Use within G-code programs to sequence spin coating after gantry positioning.

### Runtime Tuning (no rebuild needed)

```gcode
M201 X500 Y200 Z100 A150 B50 E500   ; set max acceleration (mm/s²)
M203 X400 Y333 Z50 A33 B50 E8       ; set max feedrate (mm/s)
M500             ; save to EEPROM
M501             ; load from EEPROM
M503             ; report all settings
```

### Diagnostics

```gcode
M119             ; report endstop states
M114             ; report current position
M999             ; reset firmware after emergency stop (M112)
```

## Web Controller

`RMR_Controller.html` is a standalone browser-based UI for controlling the machine over Web Serial (Chrome/Edge required). Features include:

- XY/Z jog pads with configurable step sizes and per-axis feed sliders
- Per-axis auxiliary motor controls with individual feed sliders (A, B, E)
- Collapsible acceleration tuning panel (M201) with per-axis sliders and EEPROM save
- Gripper servo slider (90°–170°) with Open/Close buttons and full-range override textbox
- Spincoater panel — RPM/Duration/Rise/Sink inputs, Start/Stop/Set Home/Index Home buttons, live RPM gauge, SVG circular position dial, Welford stats cards, phase indicator
- E-Stop (M112) with M999 Reset button for recovery without USB replug
- Position readout with auto-report polling
- G-code program runner with Load .gcode, Run/Pause/Stop, and wait-for-ok sequencing
- Raw G-code input with command history
- Keyboard shortcuts: Arrow keys = XY, PgUp/PgDn = Z, Esc = E-Stop

## Important Gotchas

1. **Axis naming:** G-code uses `A` and `B` for the Filter Feed and Syringe Height axes (not `I`/`J`). This applies to all commands: `G1`, `M201`, `M203`, `G28`, etc.
2. **Cold extrusion:** `EXTRUDE_MINTEMP` is 0, so E moves work without temperature checks. `M302 S0` is not compiled in and returns "Unknown command" — it is not needed.
3. **Filter Feed homes to MAX:** Unlike all other axes which home to MIN, the Filter Feed (A axis) homes to its far-end endstop (I_MAX, pin 15).
4. **Servo deactivation:** Servos go limp 2 seconds after positioning. If the gripper needs to actively hold force, `DEACTIVATE_SERVOS_AFTER_MOVE` must be disabled (requires rebuild) or an external servo controller used.
5. **E-Stop recovery:** After sending `M112`, send `M999` to reset firmware instead of unplugging USB.
6. **Pins 16/17 (Serial2)** are occupied by the ODrive S1 link. **Pins 19/20/21** conflict with Serial1 and I2C. Adding an I2C LCD or additional serial device requires rewiring motors.
7. **Direction inversions:** Z, I, and J axes all have `INVERT_*_DIR true`. If a new axis is added or a motor is rewired, verify direction during first test.
8. **AVR `println()` and ODrive:** On AVR, `Serial.println()` sends `\r\n`. The ODrive ASCII protocol expects bare `\n` — the stray `\r` causes "unknown command" errors. All ODrive UART writes use `print()` + `write('\n')` instead.
9. **M42 hijacks hardware timers on AVR:** Stock Marlin's `M42.cpp` always falls through to `hal.set_pwm_duty(pin, pin_status)` on AVR, which maps to `analogWrite()` and grabs the pin's hardware timer compare unit — even for `S0` and `S1`. On pins tied to Timer1 (e.g. pin 11 = OC1A, used by Marlin's stepper ISR) this causes intermittent pin-fighting where `M42` appears to work once and then stops. Our patched `M42.cpp` adds a `pin_status <= 1` early return so digital-only writes always take the pure `digitalWrite` path. For relay pins, prefer pure-GPIO pads with no timer compare unit (pin 42 = PL7 is used for the solenoid valve; pin 4 = OC0B is tolerable only because of the patch).
10. **Relay module polarity:** The current relay modules are active-HIGH (`M42 Pxx S1` = energize, `M42 Pxx S0` = de-energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (reversed polarity). The HTML UI uses explicit ON/OFF button pairs with hardcoded S values, so the correct polarity is handled by button choice regardless of module type.
11. **`Servo::move()` vs `Servo::write()` in interpolation loops:** `move()` calls `attach + safe_delay(SERVO_DELAY) + detach` per invocation — with SERVO_DELAY=2000, that is 2s per step. For tight ramp loops, use `write()` with manual `attach(0)` before and `write(final)+safe_delay(250)+detach` after. The M280 T parameter uses this approach. Default lid ramp time in the HTML UIs is 800ms.

## AI Attribution

Portions of this project's documentation, firmware configuration, and supporting code were generated or edited with the assistance of Claude (Anthropic). All AI-generated content was reviewed and validated by the project author. See [AI_ATTRIBUTION.md](AI_ATTRIBUTION.md) for details.

## License

The Marlin firmware is licensed under the GPL v3. See the `Marlin-2.1.2.7/` directory for full license text. Project-specific files (pin map, controller UI, configurations) are provided as-is for this specific machine build.
