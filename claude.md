# Robot-Making Robot — Marlin Firmware Project

## What This Project Is

A custom gantry-based robot driven by Marlin firmware on an Arduino Mega 2560. It is NOT a 3D printer — it's a pick-and-place / dispensing system with a 3-axis gantry, three auxiliary linear actuators, two servos, and a solenoid valve. Marlin is used as the motion controller because it provides production-grade G-code parsing, trapezoidal motion planning, and multi-axis stepper coordination out of the box.

## Hardware

### Stepper Drivers
All drivers are DM556T-style (external, optoisolated PUL/DIR/ENA inputs). They are driven directly from Mega GPIO pins — there is no RAMPS shield, but the pin mapping mirrors RAMPS 1.4 for the gantry axes.

**Wiring convention:** PUL+ and DIR+ connect to Mega digital out. PUL- and DIR- connect to Mega GND. ENA is active-low (LOW = motor enabled).

### Axis Map

| Marlin Axis | Function | PUL Pin | DIR Pin | ENA Pin | Steps/mm | Notes |
|---|---|---|---|---|---|---|
| X | Gantry X | A0 (54) | A1 (55) | 38 | 57.14 | GT2-14 pulley (28 mm/rev), 1600 steps/rev (1/8 µstep) |
| Y | Gantry Y | A6 (60) | A7 (61) | A2 (56) | 57.14 | GT2-14 pulley, 1 driver controls 2 parallel motors |
| Y2 | Gantry Y clone | 36 | 34 | 30 | (follows Y) | Second Y motor, same driver signal via Y2_DRIVER_TYPE |
| Z | Gantry Z | 46 | 48 | A8 (62) | 320 | 5 mm/rev lead screw, 1600 steps/rev (1/8 µstep) |
| E0 | Filter Feed | 2 | 9 | 12 | 320 | 5 mm/rev lead screw |
| E1 | Syringe | 13 | 19 | 20 | 1600 | 1 mm/rev lead screw |
| E2 | Syringe Height | 21 | 22 | 31 | 320 | 5 mm/rev lead screw |

**Steps/mm formula:** (motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev
- Belt axes: 200 × 8 ÷ 28mm (GT2 × 14 teeth) = 57.14 steps/mm
- 5 mm lead screw axes: 200 × 8 ÷ 5mm = 320 steps/mm
- 1 mm lead screw (syringe): 200 × 8 ÷ 1mm = 1600 steps/mm

### Limit Switches
- X endstop: pin 3 (X_MIN, hardware interrupt capable)
- Y endstop: pin 14 (Y_MIN)
- Z: **no endstop** — Z_HOME_DIR is set to 0 (homing disabled). Z origin is set manually with `G92 Z0`.

Switch type: normally-open mechanical, wired common→GND, NO→signal pin. Internal pullups enabled via `ENDSTOPPULLUPS`. Logic: untriggered=HIGH, triggered=LOW, `*_ENDSTOP_INVERTING false`.

### Servos
- Servo 0 (gripper): GPIO 5 — `M280 P0 S<angle>`
- Servo 1 (lid): GPIO TBD (placeholder pin 6) — `M280 P1 S<angle>`

### Solenoid Valve
- No dedicated pin defined in firmware. Driven at runtime via `M42 P<pin> S<0|255>`. Pick any free GPIO.

### Dual-Y Configuration
The two Y-axis motors are physically spliced to a single DM556T driver. In Marlin, `Y2_DRIVER_TYPE` is defined so Marlin sends step signals to both the Y and Y2 pin sets, but since they share a physical driver this is redundant (both pin sets pulse the same driver). Auto-squaring (`Y_DUAL_ENDSTOPS`) is NOT possible with this wiring — it requires independent drivers per motor.

## Firmware Architecture

### Board Definition
Custom board `BOARD_RAMPS_14_RMR` (ID 1020) inherits from stock RAMPS 1.4 and overrides E0/E1/E2 pins plus resolves conflicts.

**Files that define the board:**
- `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` — pin overrides and conflict resolution
- `Marlin/src/core/boards.h` — board ID registration (add `#define BOARD_RAMPS_14_RMR 1020`)
- `Marlin/src/pins/pins.h` — routing `MB(RAMPS_14_RMR)` to the pins file

### Pin Conflicts Resolved in pins_RAMPS_14_RMR.h
| Pin | Stock RAMPS Function | Our Use | Resolution |
|-----|---------------------|---------|------------|
| 2 | X_MAX_PIN | E0 STEP (Filter Feed) | X_MAX_PIN → -1 |
| 9 | FAN (MOSFET_B) | E0 DIR (Filter Feed) | MOSFET_B_PIN → -1 |
| 12 | PS_ON_PIN | E0 ENABLE (Filter Feed) | PS_ON_PIN → -1 |
| 13 | LED_PIN | E1 STEP (Syringe) | LED_PIN → -1 |
| 19 | Serial1 RX | E1 DIR | OK if Serial1 unused |
| 20 | I2C SDA | E1 ENABLE | OK if I2C unused |
| 21 | I2C SCL | E2 STEP | OK if I2C unused |

**Warning:** Pins 19/20/21 conflict with Serial1 and I2C. If an I2C device (LCD, sensor) or a second serial device is ever added, those motors must be rewired to free GPIOs.

### Key Configuration.h Settings
```
MOTHERBOARD              BOARD_RAMPS_14_RMR
EXTRUDERS                3
TEMP_SENSOR_0/1/2        0 (all disabled — no heaters)
EXTRUDE_MINTEMP          0 (allows E moves without hotend)
PREVENT_COLD_EXTRUSION   defined but mintemp=0 disables it
NUM_SERVOS               2
X_HOME_DIR / Y_HOME_DIR  -1 (home to min endstop)
Z_HOME_DIR               0 (no Z homing)
```

### Critical Gotchas
1. **Cold extrusion:** Marlin silently refuses E-axis moves if temperature < EXTRUDE_MINTEMP. Set to 0 in firmware AND/OR send `M302 S0` in G-code preamble.
2. **DISABLE_OTHER_EXTRUDERS** (line 1668): Currently enabled. Selecting T1 de-energizes E0 and E2 motors. If the syringe height (E2) needs to hold position while syringe (E1) runs, comment this out.
3. **No Z endstop:** `G28` without axis arguments tries to home Z and will crash. Always use `G28 X Y` explicitly.
4. **Max feedrate:** X/Y limited to 150 mm/s (~8.6 kHz step rate at 57.14 steps/mm). Well within the Mega's ISR limit, but mechanical resonance and missed steps are the practical ceiling. Z limited to 5 mm/s, E axes to 10 mm/s.
5. **Acceleration:** X/Y set to 1000 mm/s², Z and E axes to 500 mm/s². Tune up carefully — missed steps are the failure mode.

## G-Code Reference for This Machine

### Homing & Positioning
```gcode
G28 X Y          # home gantry (NEVER bare G28 — no Z endstop)
G92 Z0           # set current Z as origin
G92 E0           # reset extruder position counter
G1 X_ Y_ F_     # move gantry (F in mm/min: F3000 = 50mm/s)
G1 Z_ F_         # move Z
```

### Aux Motors (via extruder axes)
```gcode
M302 S0          # allow cold extrusion (belt-and-suspenders)
T0               # select Filter Feed (E0)
T1               # select Syringe (E1)
T2               # select Syringe Height (E2)
G1 E_ F_         # move active extruder axis
G92 E0           # reset E position (do this after each T-switch)
```

### Servos
```gcode
M280 P0 S_       # gripper servo (angle 0-180)
M280 P1 S_       # lid servo (angle 0-180)
```

### Solenoid
```gcode
M42 P<pin> S255  # solenoid ON
M42 P<pin> S0    # solenoid OFF
```

### Diagnostics
```gcode
M119             # report endstop states (use to verify wiring)
M503             # report all active firmware settings
M92              # report steps/mm (M92 X57.14 Y57.14 Z320 E320 to override)
M500             # save settings to EEPROM
M501             # load settings from EEPROM
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
Connect via Pronterface (or any serial terminal) at 250000 baud. Port is typically `/dev/ttyACM0` (Linux) or `COM3` (Windows).

## File Inventory

| File | Location in Marlin Tree | Purpose |
|------|------------------------|---------|
| Configuration.h | `Marlin/` | Main firmware config |
| Configuration_adv.h | `Marlin/` | Advanced config (unmodified from base) |
| pins_RAMPS_14_RMR.h | `Marlin/src/pins/ramps/` | Custom pin mapping |
| boards.h | `Marlin/src/core/boards.h` | Needs 1 line added (board ID) |
| pins.h | `Marlin/src/pins/pins.h` | Needs 2 lines added (routing) |

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
- **UART:** Mega Serial2 (pins 16/17) or Serial3 (pins 14/15) to UNO SoftwareSerial. Serial1 (pins 18/19) conflicts with gantry E1 motor.
- **I2C:** UNO as I2C slave. Requires remapping E1_ENA (pin 20) and E2_STEP (pin 21) on the Mega to free up SDA/SCL.

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
- [ ] Test each axis individually after first flash (direction, distance, endstop logic)
- [ ] Determine if `DISABLE_OTHER_EXTRUDERS` needs to be commented out for the use case
- [ ] Calibrate servo angles for gripper open/close positions
- [ ] Set actual travel limits (X_BED_SIZE, Y_BED_SIZE, Z_MAX_POS — currently 200×200×200 defaults)
- [ ] Add Z endstop if repeatable Z homing is needed
- [ ] Write production G-code sequences for the actual robot workflow
- [ ] Migrate `SpincoaterStage.ino` to PlatformIO project structure targeting UNO (see migration steps above)
- [ ] **Critical:** Replace `Serial1` with `SoftwareSerial` for UNO compatibility and configure ODrive to 19200 baud
- [ ] **Critical:** Replace `float samples[300]` array with Welford's online algorithm — 1.2 KB array will overflow UNO's 2 KB SRAM
- [ ] Verify ODriveUART library version compatibility and correct header name
- [ ] Design and implement Mega ↔ UNO communication protocol (UART vs I2C, command format)
- [ ] Make target RPM configurable via inter-board command instead of hardcoded constant
