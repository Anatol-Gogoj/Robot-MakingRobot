# Robot-Making Robot (RMR)

A custom 3-axis gantry robot driven by Marlin firmware on an Arduino Mega 2560. This is **not** a 3D printer — it's a pick-and-place / dispensing system with three auxiliary linear actuators, two servos, and a solenoid valve. Marlin is repurposed here purely as a motion controller because it provides production-grade G-code parsing, trapezoidal motion planning, and multi-axis stepper coordination out of the box.

## Repository Structure

```
Robot-MakingRobot/
├── Marlin-2.1.2.7/              # Full Marlin 2.1.2.7 source tree
│   └── Marlin/
│       ├── Configuration.h          # Main firmware config (heavily customized)
│       ├── Configuration_adv.h      # Advanced config
│       └── src/pins/ramps/
│           └── pins_RAMPS_14_RMR.h  # Custom pin mapping for this machine
├── RMR_Controller.html           # Browser-based serial G-code controller UI
├── Configurations.txt            # Quick-reference pin map and steps/mm notes
└── README.md                     # This file
```

## Hardware Overview

### Motion System

The gantry has three Cartesian axes (X, Y, Z) plus three auxiliary linear actuators mapped to Marlin's extruder axes (E0, E1, E2). All stepper drivers are external DM556T units (optoisolated PUL/DIR/ENA inputs) driven directly from Mega GPIO pins — there is no RAMPS shield, though the pin mapping inherits from RAMPS 1.4 for the gantry axes.

| Marlin Axis | Function       | Drive           | Steps/mm |
|-------------|----------------|-----------------|----------|
| X           | Gantry X       | GT2-14 belt     | 57.14    |
| Y + Y2      | Gantry Y       | GT2-14 belt (2 motors, 1 driver) | 57.14 |
| Z           | Gantry Z       | 5 mm lead screw | 320      |
| E0          | Filter Feed    | 5 mm lead screw | 320      |
| E1          | Syringe        | 1 mm lead screw | 1600     |
| E2          | Syringe Height | 5 mm lead screw | 320      |

Steps/mm formula: `(motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev`. All drivers are set to 1/8 microstepping (1600 steps/rev with 200-step motors).

### End Effectors and Peripherals

- **Gripper servo** — GPIO 5, controlled via `M280 P0 S<angle>`
- **Lid servo** — GPIO TBD (placeholder pin 6), controlled via `M280 P1 S<angle>`
- **Solenoid valve** — no dedicated pin in firmware; driven at runtime with `M42 P<pin> S<0|255>`

### Limit Switches

- X endstop on pin 3 (X_MIN, interrupt-capable)
- Y endstop on pin 14 (Y_MIN)
- Z has **no endstop** — Z origin is set manually with `G92 Z0`

All switches are normally-open, wired common→GND / NO→signal, with internal pullups enabled.

## Firmware Details

### Custom Board Definition

A custom board `BOARD_RAMPS_14_RMR` (ID 1020) inherits from stock RAMPS 1.4 and overrides E0/E1/E2 pin assignments. The following Marlin source files are modified:

| File | Change |
|------|--------|
| `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` | Custom pin map, conflict resolution |
| `Marlin/src/core/boards.h` | Board ID `1020` registration |
| `Marlin/src/pins/pins.h` | Routing `MB(RAMPS_14_RMR)` → pins file |

Several stock RAMPS pins are reassigned to free GPIOs for the auxiliary motors (e.g., pin 2 repurposed from X_MAX to E0_STEP, pin 9 from FAN to E0_DIR). Pins 19/20/21 conflict with Serial1 and I2C — those peripherals cannot be used without rewiring.

### Key Configuration Choices

- `EXTRUDERS 3` — three auxiliary linear axes mapped as extruders
- All temperature sensors disabled (`TEMP_SENSOR_* 0`) — no heaters on this machine
- `EXTRUDE_MINTEMP 0` — allows extruder-axis moves without a hotend
- `Z_HOME_DIR 0` — Z homing disabled (no endstop)
- `NUM_SERVOS 2`

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

Connect via Pronterface, the included `RMR_Controller.html` web UI, or any serial terminal at **250000 baud**. The port is typically `/dev/ttyACM0` on Linux or `COM3` on Windows.

## Using the Machine

### Startup Sequence

```gcode
G28 X Y          ; home X and Y (NEVER send bare G28 — no Z endstop)
G92 Z0           ; set current Z position as zero
M302 S0          ; allow cold extrusion (safety override for extruder axes)
G92 E0           ; reset extruder position
```

### Moving the Gantry

```gcode
G1 X100 Y50 F3000    ; move to (100, 50) at 50 mm/s
G1 Z10 F600          ; lower Z 10 mm at 10 mm/s
```

Feedrates are in mm/min. Max recommended: X/Y 150 mm/s (F9000), Z 5 mm/s (F300), E axes 10 mm/s (F600).

### Driving Auxiliary Motors

Each auxiliary motor is selected with a tool-change command, then moved via the E axis:

```gcode
T0               ; select Filter Feed (E0)
G92 E0           ; reset E position
G1 E10 F600      ; move 10 mm at 10 mm/s

T1               ; select Syringe (E1)
G92 E0
G1 E5 F300       ; move 5 mm

T2               ; select Syringe Height (E2)
G92 E0
G1 E-20 F600     ; retract 20 mm
```

Always reset E position (`G92 E0`) after each tool switch.

### Servos and Solenoid

```gcode
M280 P0 S90      ; set gripper servo to 90°
M280 P1 S0       ; set lid servo to 0°
M42 P<pin> S255  ; solenoid ON
M42 P<pin> S0    ; solenoid OFF
```

### Diagnostics

```gcode
M119             ; report endstop states
M503             ; dump all active firmware settings
M92              ; report steps/mm
```

## Web Controller

`RMR_Controller.html` is a standalone browser-based UI for sending G-code to the machine over Web Serial. Open it in Chrome (or any browser supporting the Web Serial API), click connect, select the Mega's serial port, and use the on-screen controls for jogging, homing, and sending raw G-code.

## Important Gotchas

1. **Never send bare `G28`** — there is no Z endstop, so the Z axis will crash into its physical limit. Always specify axes: `G28 X Y`.
2. **Cold extrusion lockout** — Marlin silently ignores E-axis moves if the hotend temperature is below `EXTRUDE_MINTEMP`. The firmware sets this to 0, but sending `M302 S0` in your G-code preamble is a belt-and-suspenders safeguard.
3. **`DISABLE_OTHER_EXTRUDERS`** is currently enabled, meaning selecting T1 de-energizes E0 and E2. If the syringe height motor (E2) needs to hold position while the syringe (E1) runs, this must be disabled in `Configuration_adv.h`.
4. **Max feedrate** — X/Y limited to 150 mm/s (~8.6 kHz step rate at 57.14 steps/mm). Z limited to 5 mm/s, E axes to 10 mm/s. Don't increase without testing for missed steps.
5. **Pins 19/20/21 conflict** with Serial1 and I2C. Adding an I2C LCD or a second serial device requires rewiring those motors.

## AI Attribution

Portions of this project's documentation, firmware configuration, and supporting code were generated or edited with the assistance of Claude (Anthropic). All AI-generated content was reviewed and validated by the project author. See [AI_ATTRIBUTION.md](AI_ATTRIBUTION.md) for details.

## License

The Marlin firmware is licensed under the GPL v3. See the `Marlin-2.1.2.7/` directory for full license text. Project-specific files (pin map, controller UI, configurations) are provided as-is for this specific machine build.
