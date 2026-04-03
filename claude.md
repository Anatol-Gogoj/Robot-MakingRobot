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
| Y | Y | Gantry Y | A6 (60) | A7 (61) | A2 (56) | 57.14 | GT2-14 pulley, 1 driver controls 2 parallel motors |
| Y2 | — | Gantry Y clone | 36 | 34 | 30 | (follows Y) | Second Y motor, same driver signal via Y2_DRIVER_TYPE |
| Z | Z | Gantry Z | 46 | 48 | A8 (62) | 320 | 5 mm/rev lead screw, 1600 steps/rev (1/8 µstep) |
| I | A | Filter Feed | 2 | 9 | 12 | 320 | 5 mm/rev lead screw — homeable linear axis (AXIS4_NAME='A') |
| E0 | E | Syringe | 13 | 19 | 20 | 1600 | 1 mm/rev lead screw — sole extruder |
| J | B | Syringe Height | 21 | 22 | 31 | 320 | 5 mm/rev lead screw — homeable linear axis (AXIS5_NAME='B') |

**Steps/mm formula:** (motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev
- Belt axes: 200 × 8 ÷ 28mm (GT2 × 14 teeth) = 57.14 steps/mm
- 5 mm lead screw axes: 200 × 8 ÷ 5mm = 320 steps/mm
- 1 mm lead screw (syringe): 200 × 8 ÷ 1mm = 1600 steps/mm

### Limit Switches
- X endstop: pin 3 (X_MIN, hardware interrupt capable)
- Y endstop: pin 14 (Y_MIN)
- Z endstop: pin 40 (Z_MIN — moved from pin 18/TX1 due to EMI sensitivity)
- I endstop (Filter Feed): pin 15 (I_MAX, RAMPS Y+ header) — homes to MAX (far end)
- J endstop (Syringe Height): pin 17 (J_MIN, Mega TX2)
- Syringe (E0): **no endstop**

Switch type: normally-open, wired common→GND, NO→signal pin. Internal pullups enabled via `ENDSTOPPULLUPS`. Logic: untriggered=HIGH, triggered=LOW, `*_ENDSTOP_INVERTING true`.

### Servos
- Servo 0 (gripper): GPIO 5 — `M280 P0 S<angle>`, soft limits 90°–170° in HTML slider, full 0–180° via override textbox
- Servo 1 (lid): GPIO TBD (placeholder pin 6) — `M280 P1 S<angle>`
- `DEACTIVATE_SERVOS_AFTER_MOVE` enabled — PWM signal cuts after 2 seconds to prevent jitter
- `SERVO_DELAY { 2000, 2000 }` — hold time before deactivation

### Solenoid Valve
- No dedicated pin defined in firmware. Driven at runtime via `M42 P<pin> S<0|255>`. Pick any free GPIO.

### Dual-Y Configuration
The two Y-axis motors are physically spliced to a single DM556T driver. In Marlin, `Y2_DRIVER_TYPE` is defined so Marlin sends step signals to both the Y and Y2 pin sets, but since they share a physical driver this is redundant (both pin sets pulse the same driver). Auto-squaring (`Y_DUAL_ENDSTOPS`) is NOT possible with this wiring — it requires independent drivers per motor.

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

**Warning:** Pins 19/20/21 conflict with Serial1 and I2C. If an I2C device (LCD, sensor) or a second serial device is ever added, those motors must be rewired to free GPIOs.

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
Z_HOME_DIR               -1          (home to Z_MIN endstop, pin 18)
I_HOME_DIR                1          (home to I_MAX endstop, pin 15 — far end)
J_HOME_DIR               -1          (home to J_MIN endstop, pin 17)
Z_SAFE_HOMING            disabled    (Z homes first via HOME_Z_FIRST)
HOME_Z_FIRST             enabled     (in Configuration_adv.h)
Homing order             Z → Y → J → [gripper close] → X → I  (G28.cpp patched)
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
Travel limits (mm):      X=770  Y=150  Z=250  I=347  J=304
```

### Patched Marlin Source Files

| File | Modification |
|------|-------------|
| `src/gcode/calibrate/G28.cpp` | Custom homing order: Z→Y→J→gripper close→X→I. Servo 0 closes to 90° before X homing to prevent collision. SECONDARY_AXIS_CODE I/J entries replaced with NOOP. |
| `src/gcode/control/M280.cpp` | Firmware-side servo clamp removed — soft limits enforced in HTML slider only. Override textbox allows full 0–180°. |
| `src/inc/SanityCheck.h` | Sanity check for DEACTIVATE_SERVOS_AFTER_MOVE commented out — stock Marlin requires Z_PROBE_SERVO_NR or switching toolhead, which don't apply here. |

### Critical Gotchas
1. **Cold extrusion:** `EXTRUDE_MINTEMP` is set to 0, so E-axis moves work without temperature checks. `M302 S0` is **not compiled in** (returns "Unknown command") and is not needed.
2. **Custom homing order (G28.cpp patched):** A bare `G28` homes in order: Z → Y → J(Syr.Ht) → [gripper servo closes to 90°] → X → I(Filter Feed). HOME_Z_FIRST is enabled, Z_SAFE_HOMING is disabled.
3. **Gripper closes before X homing:** Servo 0 is commanded to 90° with a 300ms delay before X homing begins, to prevent the gripper from colliding with the frame.
4. **Filter Feed homes to MAX:** I_HOME_DIR=1, endstop is on the far end (I_MAX, pin 15). All other axes home to MIN.
5. **Servo jitter prevention:** `DEACTIVATE_SERVOS_AFTER_MOVE` cuts PWM signal 2 seconds after `M280` command. Servo goes limp after that — fine if grip is mechanically self-holding.
6. **E-Stop recovery:** Send `M999` to reset firmware after `M112` emergency stop, instead of unplugging USB.
7. **Pin 17 (J endstop):** This is Mega TX2. If Mega↔UNO communication uses Serial2 (pins 16/17), the J endstop must move to a different pin.
8. **Axis name mapping:** G-code uses A/B for the I/J axes (set via AXIS4_NAME/AXIS5_NAME). Marlin restricts these names to A,B,C,U,V,W — 'I' and 'J' are not valid axis names.

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

### Solenoid
```gcode
M42 P<pin> S255  # solenoid ON
M42 P<pin> S0    # solenoid OFF
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

Browser-based control interface using Web Serial API (Chrome/Edge required).

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
- **Keyboard shortcuts:** Arrow keys = XY, PgUp/PgDn = Z, Esc = E-Stop

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

## Spin Coater Subsystem

### Overview
A separate spin coater stage uses an ODrive motor controller commanded over UART from a dedicated **Arduino UNO**. The firmware is in `SpincoaterStage.ino`. This is independent of the Marlin gantry firmware on the Mega. The intended system architecture is: Mega (Marlin) → UART or I2C → UNO → UART → ODrive.

### ODrive Wiring (UNO side)
- UNO → ODrive J11 UART: pin 8 RX (G07), pin 7 TX (G06)
- Baud rate: 115200 (but see SoftwareSerial note below)
- Library: `ODriveUART` (Arduino)
- ODrive ISOVDD/ISOGND must be connected to Arduino 5V and GND

**Serial1 issue:** The sketch currently uses `HardwareSerial& odrive_serial = Serial1;` which is Mega-specific. The UNO has only one hardware UART (pins 0/1, shared with USB). To run on an UNO, the ODrive link must switch to `SoftwareSerial` (recommended baud: 19200) or the hardware serial must be dedicated to the ODrive (sacrificing USB debug). The `SoftwareSerial.h` include is already in the sketch but commented out.

### Mega ↔ UNO Communication (TBD)
The gantry Mega needs to trigger spin coater cycles on the UNO. Options:
- **UART:** Mega Serial3 (pins 14/15) to UNO SoftwareSerial. Serial1 (pins 18/19) conflicts with Z endstop and E0 DIR. Serial2 (pins 16/17) conflicts with J endstop on pin 17 — would require moving J endstop to a free GPIO.
- **I2C:** UNO as I2C slave. Requires remapping E0_ENA (pin 20) and J_STEP (pin 21) on the Mega to free up SDA/SCL — not practical with current wiring.

### Sketch Behavior
The sketch (`SpincoaterStage.ino`) runs a single-shot cycle: wait for `START` over USB serial → calibrate ODrive if needed → ramp to 5000 RPM at 15 rev/s² → measure velocity (100 ms sampling for 30 s, reports mean ± σ) → decelerate at 100 rev/s² → encoder index re-home → return to idle. Target RPM is hardcoded as `int RPM = 5000`. Currently the `START` command comes over USB serial; in the final system it would come from the Mega over the inter-board link.

### Migrating SpincoaterStage.ino to PlatformIO

The `.ino` file is currently an Arduino IDE sketch. To bring it into the PlatformIO ecosystem (consistent with the Marlin build):

#### Directory Structure
```
SpincoaterStage/
├── platformio.ini
├── src/
│   └── main.cpp          # renamed from SpincoaterStage.ino
└── lib/
    └── (ODriveUART goes here if not using lib_deps)
```

#### platformio.ini
```ini
[env:uno]
platform = atmelavr
board = uno
framework = arduino
monitor_speed = 115200
lib_deps =
    odriverobotics/ODriveArduino @ ^0.1.0
    ; Or use the library's GitHub URL if the PlatformIO registry version is stale:
    ; https://github.com/odriverobotics/ODrive.git#master
```

**Note:** The ODrive Arduino library's PlatformIO registry name may vary. If `odriverobotics/ODriveArduino` doesn't resolve, use the GitHub URL directly or manually place the library source in `lib/ODriveUART/`.

#### Conversion Steps
1. **Rename:** Copy `SpincoaterStage.ino` → `SpincoaterStage/src/main.cpp`.
2. **Add Arduino.h include:** PlatformIO does not implicitly include `Arduino.h` like the Arduino IDE. Add `#include <Arduino.h>` as the first line.
3. **Switch from Serial1 to SoftwareSerial:** The UNO has no `Serial1`. Uncomment the `SoftwareSerial` lines in the sketch (pins 8/9 as suggested, or pick other free pins), set baud to 19200, and replace `HardwareSerial& odrive_serial = Serial1;` with the SoftwareSerial instance. Update `baudrate` accordingly.
4. **Forward-declare functions:** The Arduino IDE auto-generates forward declarations; PlatformIO/GCC does not. Add `void MS();` before `setup()` (or move the `MS()` definition above `setup()`/`loop()`).
5. **Create `platformio.ini`** as shown above.
6. **Fix SRAM usage (critical):** The `float samples[300]` array in `MS()` uses ~1.2 KB. The UNO's ATmega328P has only 2 KB total SRAM. With the stack, ODrive library buffers, and SoftwareSerial buffers, this will almost certainly overflow. Replace the array with Welford's online algorithm for running mean and variance — this reduces memory usage to a few floats regardless of sample count.
7. **Build:** `pio run -e uno`
8. **Upload:** `pio run -e uno -t upload`

#### Gotchas
- The `ODriveUART` library header might be `<ODriveArduino.h>` vs `<ODriveUART.h>` depending on the library version. Check the installed library's actual header filename.
- `SoftwareSerial` on the UNO is unreliable above 19200 baud. The ODrive docs confirm 19200 as the recommended rate for SoftwareSerial. This means the ODrive must also be configured to 19200 baud (via `odrv0.config.uart_baudrate = 19200` in odrivetool, then `odrv0.save_configuration()`).
- `monitor_speed` in platformio.ini should match the USB serial baud (115200), which is separate from the ODrive SoftwareSerial baud.
- The UNO's ATmega328P has 2 KB SRAM vs the Mega's 8 KB. Every buffer matters. Profile with `pio run -e uno -t checkprogsize` after building.

## What's Left To Do

- [ ] Confirm DIP switch settings on ALL DM556T drivers (verify 1600 steps/rev = 1/8 µstep on all drivers)
- [ ] Wire and assign lid servo GPIO (currently TBD, placeholder pin 6)
- [ ] Choose and wire solenoid valve pin
- [x] ~~Test each axis individually after first flash (direction, distance, endstop logic)~~ — all axes verified, directions corrected
- [x] ~~Determine if `DISABLE_OTHER_EXTRUDERS` needs to be commented out~~ (N/A — only 1 extruder now)
- [x] ~~Calibrate servo angles for gripper open/close positions~~ (90° closed, 170° open)
- [x] ~~Set actual travel limits~~ (X=770, Y=150, Z=250, I=347, J=304)
- [x] ~~Add Z endstop if repeatable Z homing is needed~~ (Z endstop on pin 18, Z_HOME_DIR=-1)
- [x] ~~Tune feedrates and accelerations~~ (tested, production values set)
- [ ] Write production G-code sequences for the actual robot workflow
- [ ] Migrate `SpincoaterStage.ino` to PlatformIO project structure targeting UNO (see migration steps above)
- [ ] **Critical:** Replace `Serial1` with `SoftwareSerial` for UNO compatibility and configure ODrive to 19200 baud
- [ ] **Critical:** Replace `float samples[300]` array with Welford's online algorithm — 1.2 KB array will overflow UNO's 2 KB SRAM
- [ ] Verify ODriveUART library version compatibility and correct header name
- [ ] Design and implement Mega ↔ UNO communication protocol (UART vs I2C, command format)
- [ ] Make target RPM configurable via inter-board command instead of hardcoded constant
