# Robot-Making Robot (RMR)

Associated with https://arxiv.org/abs/2608.00369

A custom 3-axis gantry robot driven by Marlin firmware on an Arduino Mega 2560. It is **not** a 3D printer. It is a pick-and-place and dispensing system with three auxiliary linear actuators (filter feed, syringe height, syringe plunger), two servos, a UV lamp, a solenoid valve and a spin coater. Marlin serves only as the motion controller, because it already provides G-code parsing, trapezoidal motion planning and multi-axis stepper coordination.

## Repository Structure

```
Robot-MakingRobot/
├── Marlin-2.1.2.7/              # Full Marlin 2.1.2.7 source tree
│   └── Marlin/
│       ├── Configuration.h          # Main firmware config (heavily customized)
│       ├── Configuration_adv.h      # Advanced config: SPINCOATER, UV_LID_INTERLOCK, MOTOR_POWER_SENSE
│       └── src/
│           ├── pins/ramps/
│           │   └── pins_RAMPS_14_RMR.h  # Custom pin mapping (K syringe axis, J endstop on pin 23, Serial2 freed)
│           ├── core/boards.h            # Board ID registration (patched)
│           ├── pins/pins.h              # Board routing (patched)
│           ├── feature/
│           │   ├── spincoater.h/.cpp    # ODrive S1 raw ASCII protocol layer over Serial2
│           │   ├── uv_interlock.h/.cpp  # UV lamp lid interlock (compiled out today, see below)
│           │   └── motor_power.h/.cpp   # Motor-power (E-stop contactor) sense
│           ├── gcode/calibrate/G28.cpp  # Custom homing order (patched)
│           ├── gcode/motion/G0_G1.cpp   # Refuses moves after a motor-power loss until re-homed (patched)
│           ├── gcode/control/
│           │   ├── M42.cpp              # DIRECT_PIN_CONTROL (patched: S<=1 guard, UV interlock hook)
│           │   ├── M280.cpp             # Servo handling (patched)
│           │   ├── M750.cpp             # Spincoater spin cycle
│           │   ├── M751_M752.cpp        # Spincoater home datum / index search
│           │   ├── M753.cpp             # ODrive UART diagnostic
│           │   └── M754.cpp             # ODrive encoder configuration dump (read-only)
│           ├── MarlinCore.cpp           # Patched: spincoater stop in kill() and setup(), interlock idle tasks
│           └── inc/SanityCheck.h        # Servo deactivation check bypass (patched)
├── SpincoaterStage/              # Benchtop test firmware (Nano RP2040, reference only)
│   ├── platformio.ini               # PlatformIO config for the Nano RP2040 Connect
│   ├── src/main.cpp                 # Standalone spincoater firmware v2.6
│   ├── SpincoaterDashboard.html     # Standalone spincoater Web Serial dashboard
│   └── INTEGRATION_PLAN.md          # Integration design rationale (stale, see the note below)
├── SpincoaterStage.ino           # Original Arduino IDE spincoater sketch (reference only)
├── RMR_Controller.html           # Web controller (click-optimized, for debugging and tuning)
├── RMR_Touch.html                # Touchscreen web UI (for operation)
├── RMR_SegmentRunner.html        # Standalone segment runner + named recipes (E-axis dispense, port before use)
├── fullcode.gcode                # Production DEA layer program (dispense step still E-axis, port before use)
├── LayerCycle.gcode              # Spin-coating layer cycle (E-axis dispense, port before use)
├── LayerCycle.segments.gcode     # LayerCycle with segment markers + parameters for the Segment Runner
├── SpinCoatUVCure.gcode          # April 2026 Copilot protocol, never run (E-axis)
├── DemoProgram.gcode             # Demo pick-and-place cycle
├── tests/                        # Node checks for the browser pages (see tests/README.md)
├── tools/
│   ├── contrast_check.py            # WCAG contrast checker for the UI color themes
│   └── sync_runlog.py               # Copies the shared Run Log module from the Controller to the Touch UI
├── pi-panel/                     # Raspberry Pi touch-panel bridge, GPIO config, systemd unit, README
├── PIN_MAP.md                    # Consolidated pin map + wiring reference (authoritative bench doc)
├── SpincoaterPinMap.jfif         # ODrive S1 J11 connector pinout image
├── ODRIVE_CONFIG.md              # ODrive S1 configuration as recorded 2026-08-13
├── RUN_SHEET.md                  # Bench run sheet (four lanes, Tasks 1 to 15) with dated results
├── RUN_LOG_PLAN.md               # Design notes for the Run Log tab
├── DISPENSE_150ML.md             # Constants and derivation for the 150 mL syringe retune
├── docs/adr/                     # Architecture decision records (index in docs/adr/README.md)
├── AI_ATTRIBUTION.md             # AI assistance disclosure
├── CAD/                          # Printed-part CAD: FreeCAD and SolidWorks sources, STEP exports
├── claude.md                     # Detailed firmware architecture and project docs
└── README.md                     # This file
```

`RMR_Controller.html` and `RMR_Touch.html` **are** the machine's UI: the Controller for
debugging and tuning, the Touch UI for operation. Do not start a third one.

`SpincoaterStage/INTEGRATION_PLAN.md` is a historical design record, not a plan. Its M750
parameter table is wrong: it documents `A`/`C` as accelerations in rev/s², but the firmware
parses them as ramp *times* in seconds. Treat `claude.md` as authoritative.

## Current State

The spincoater firmware stack that was open all summer (#38, #39, #51, #56, #57 and #58, plus
#70 for M754 and #76) was merged into `main` on 2026-09-14 as one consolidation, PR #106. The
September UI work (sequencer homing gate, argon purge, color themes, Touch UI syringe C-axis
port) followed as PR #107, and the Run Log as #109.

The run sheet's spincoater tasks were last run on hardware on 2026-08-19, before the
consolidation. Later September changes were made at the machine (the UV lid interlock was
disabled on 2026-09-17 after it refused every UV-on), but no run-sheet task has been repeated
on the merged firmware. `RUN_SHEET.md` lists what to repeat. The Spin Coater Subsystem section
below describes `main`.

Session state is not kept in the repo; the August and September handoffs were moved out in
issue #129. Durable decisions are in `docs/adr/`, durable bench findings are in `claude.md`, and
`RUN_SHEET.md` is the bench checklist.

## Hardware Overview

### Motion System

The gantry has three Cartesian axes (X, Y, Z) plus three auxiliary linear axes. The Filter Feed, Syringe Height and Syringe are Marlin's I, J and K linear axes (G-code letters `A`, `B` and `C`), each with an endstop and homing. There is no extruder (`EXTRUDERS 0`). All stepper drivers are external DM556T units (optoisolated PUL/DIR/ENA inputs) driven directly from Mega GPIO pins. There is no RAMPS shield, though the pin mapping inherits from RAMPS 1.4 for the gantry axes.

| Marlin Axis | G-Code | Function       | Drive           | Steps/mm |
|-------------|--------|----------------|-----------------|----------|
| X           | X      | Gantry X       | GT2-14 belt     | 57.14    |
| Y + Y2      | Y      | Gantry Y       | GT2-14 belt (2 motors, 2 drivers, firmware-synchronized via `Y2_DRIVER_TYPE`) | 57.14 |
| Z           | Z      | Gantry Z       | 5 mm lead screw | 320      |
| I           | A      | Filter Feed    | 5 mm lead screw | 320      |
| J           | B      | Syringe Height | 5 mm lead screw | 320      |
| K           | C      | Syringe        | 1 mm lead screw | 1600     |

Steps/mm formula: `(motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev`. All drivers are set to 1/8 microstepping (1600 steps/rev with 200-step motors).

### Tuned Motion Parameters

| Parameter | X | Y | Z | A (Filter) | B (Syr.Ht) | C (Syringe) |
|-----------|---|---|---|------------|------------|-------------|
| Max feedrate (mm/s) | 400 | 333 | 50 | 33 | 50 | 8 |
| Max feedrate (mm/min) | 24000 | 20000 | 3000 | 2000 | 3000 | 480 |
| Max acceleration (mm/s²) | 500 | 200 | 100 | 150 | 50 | 500 |
| Travel limit (mm) | 770 | 200 | 186 | 343 | 295 | 125 |

> Y travel reaches 200 mm only on the right half (X ≥ 350); on the left half keep Y ≤ 150 mm to clear fixtures. The firmware does not enforce this: its Y limit is 200 mm everywhere.

### End Effectors and Peripherals

- **Gripper servo:** GPIO 5, `M280 P0 S<angle>`, 90° (closed) to 170° (open)
- **Lid servo:** GPIO 6, `M280 P1 S<angle>`, 0 to 180° in firmware; the UIs use 30° (open) and 115° (closed over the spincoater)
- **UV lamp relay:** GPIO 4, `M42 P4 S1` = ON, `M42 P4 S0` = OFF (current active-HIGH modules)
- **Solenoid valve relay:** GPIO 42, `M42 P42 S1` = OPEN, `M42 P42 S0` = CLOSED (current active-HIGH modules)

Both relays are opto-isolated modules powered from a dedicated 3.3 V buck converter rail (shared ground with the Mega). The current modules are active-HIGH (S1 = energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (S0 = energize). The web UIs use explicit ON/OFF button pairs with hardcoded S values, so the button the user presses sets the polarity.

Servos deactivate 2 seconds after positioning (`DEACTIVATE_SERVOS_AFTER_MOVE`) to prevent PWM jitter.

### Safety Inputs

- **Motor-power sense (`MOTOR_POWER_SENSE`, enabled):** pin 43 reads the aux contact of the motor contactor (LOW = motors powered). When motor power drops, the firmware stops the planner, clears the queue, marks every axis unhomed, prints `MOTOR POWER LOST`, and refuses `G0`/`G1` moves until a `G28`. It arms only after it first sees motor power, so an unwired pin 43 does not fault at boot.
- **UV lid interlock (`UV_LID_INTERLOCK`, disabled):** with a lid-closed microswitch on pin 39, the firmware would refuse `M42 P4 S1` while the lid is open and cut the lamp if the lid opens. It was disabled on 2026-09-17 because no switch is fitted, so it refused every UV-on. Re-enable it only once the switch is wired. Either way it is defense in depth; a hardware interlock in series with the lamp supply is the real safety layer.

### Limit Switches

All six homing axes have endstops:
- X endstop on pin 3 (X_MIN, interrupt-capable)
- Y endstop on pin 14 (Y_MIN)
- Z endstop on pin 40 (Z_MIN, moved from pin 18/TX1 because of EMI)
- I (Filter Feed) endstop on pin 15 (I_MAX, homes to the far end)
- J (Syringe Height) endstop on pin 23 (J_MIN, moved from pin 17/TX2 to free Serial2 for the ODrive)
- K (Syringe) endstop on pin 63 / A9 (K_MIN, the fully-open plunger end)

All switches are normally-open, wired common→GND and NO→signal, with internal pullups enabled. A bare `G28` homes every axis including the syringe, so the pin-63 switch must be wired before you send it, and `INVERT_K_DIR` must be checked on first use (a `G1 C-5` jog must move toward fully open).

## Firmware Details

### Custom Board Definition

A custom board `BOARD_RAMPS_14_RMR` (ID **1025**) inherits from stock RAMPS 1.4 and overrides pin assignments for the I, J and K linear axes. **ID 1020 is stock `BOARD_RAMPS_14_EFB`; using it silently selects the wrong pin file.** The following Marlin source files are modified:

| File | Change |
|------|--------|
| `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` | Custom pin map, conflict resolution, J endstop on pin 23, K (syringe) pins and endstop on pin 63 |
| `Marlin/src/core/boards.h` | Board ID `1025` registration (`boards.h:50`) |
| `Marlin/src/pins/pins.h` | Routing `MB(RAMPS_14_RMR)` → pins file |
| `Marlin/src/gcode/calibrate/G28.cpp` | Custom homing order: lid open, Z, Y, J, gripper close, X, I, K. A completed `G28` also clears the motor-power move lock |
| `Marlin/src/gcode/motion/G0_G1.cpp` | Refuses moves after a motor-power loss until re-homed (`Move refused: re-home (G28) after motor power loss`) |
| `Marlin/src/gcode/control/M42.cpp` | Added a `pin_status <= 1` early return so digital-only writes skip `hal.set_pwm_duty()` on AVR (prevents Timer0/Timer1 conflicts); UV lid interlock hook |
| `Marlin/src/gcode/control/M280.cpp` | Servo clamp removed (soft limits in the HTML only). POLARGRAPH gate on the T parameter removed, so `M280 Px S<angle> T<ms>` does timed linear interpolation on any servo |
| `Marlin/src/gcode/control/M750.cpp` | Spincoater spin cycle handler |
| `Marlin/src/gcode/control/M751_M752.cpp` | Spincoater home datum / index search |
| `Marlin/src/gcode/control/M753.cpp` | ODrive UART diagnostic |
| `Marlin/src/gcode/control/M754.cpp` | ODrive encoder configuration dump (read-only) |
| `Marlin/src/gcode/gcode.cpp`, `gcode.h` | Dispatch and declarations for M750 to M754 |
| `Marlin/src/feature/spincoater.h/.cpp` | ODrive S1 Serial2 raw ASCII communication layer |
| `Marlin/src/feature/uv_interlock.h/.cpp` | UV lid interlock (`UV_LID_INTERLOCK`) |
| `Marlin/src/feature/motor_power.h/.cpp` | Motor-power sense (`MOTOR_POWER_SENSE`) |
| `Marlin/src/module/temperature.cpp` | An `M410` also asks a running `M750` to stop the rotor (`Spincoater::requestAbort()`) |
| `Marlin/src/MarlinCore.cpp` | Spincoater `safeStop()` and `emergencyStop()` in `kill()`, startup safety disarm in `setup()`, UV interlock and motor-power idle tasks |
| `Marlin/src/inc/SanityCheck.h` | DEACTIVATE_SERVOS_AFTER_MOVE check bypassed |
| `Marlin/Configuration_adv.h` | `SPINCOATER` flag + defaults; `DIRECT_PIN_CONTROL` for M42 relays; `EMERGENCY_PARSER` so M112 bypasses the queue during a blocking M750; `UV_LID_INTERLOCK` (disabled) and `MOTOR_POWER_SENSE` (enabled) |
| `ini/features.ini` | Build registration for the spincoater, UV interlock and motor-power source files |

Several stock RAMPS pins are reassigned to free GPIOs for the auxiliary motors (for example, pin 2 is repurposed from X_MAX to I_STEP and pin 9 from FAN to I_DIR). Pins 16/17 are occupied by Serial2 (the ODrive link). Pins 19/20/21 conflict with Serial1 and I2C, so those peripherals cannot be used without rewiring.

### Key Configuration Choices

- `EXTRUDERS 0`: no extruder. The syringe is the homeable K axis (G-code `C`); Filter Feed and Syringe Height are the I/J linear axes (`A`/`B`); all have endstops and homing
- `AXIS4_NAME 'A'`, `AXIS5_NAME 'B'`, `AXIS6_NAME 'C'`: G-code letters for the I/J/K axes
- All temperature sensors disabled (`TEMP_SENSOR_* 0`): there are no heaters on this machine
- `EXTRUDE_MINTEMP 0`: moot with `EXTRUDERS 0`, since there is no E axis and no cold-extrusion check
- `INVERT_Z_DIR`, `INVERT_I_DIR`, `INVERT_J_DIR` and `INVERT_K_DIR` all `true`. Z/I/J were verified by physical testing; K (syringe) is flipped so that `-C` homes toward the open end, which still needs checking on first use
- Custom homing order: lid open (30°) → Z → Y → J (Syr.Ht) → gripper close (90°) → X → I (Filter Feed) → K (Syringe)
- `DEACTIVATE_SERVOS_AFTER_MOVE` with a 2-second hold, to prevent servo jitter
- `EEPROM_SETTINGS` disabled: runtime tuning is lost on every reset (see Runtime Tuning below)

## Spin Coater Subsystem

The spin coater uses an ODrive S1 motor controller driving a D5312s-330kV brushless motor with an AMT102 incremental encoder. The Mega 2560 controls the ODrive directly over Serial2 (pins 16/17) at 115200 baud using the ODrive raw ASCII protocol. There is no second Arduino.

```
Mega 2560 (Marlin + M750/M751/M752/M753/M754)  ──Serial2 (115200)──►  ODrive S1  ──►  Motor
```

### Spincoater G-Codes

```gcode
M750 S5000 D30 A5 C1 H1   ; spin cycle: 5000 RPM, 30 s dwell, 5 s ramp-up, 1 s ramp-down, home after
M751                       ; set current position as the 0° home datum
M752                       ; encoder index search, then move back to the saved datum
M753                       ; UART diagnostic: probes the ODrive link, reports the raw response
M754                       ; encoder configuration dump (read-only), answers the index-reference question over UART
```

**M750** is a blocking spin cycle. `S` = RPM, `D` = dwell seconds, `A` = ramp-up **time in
seconds**, `C` = ramp-down **time in seconds**, `H` = home after (0/1). Defaults are
S5000 D30 A5 C1 H1. All four numeric values must be > 0 or the command aborts with
`ERR: All values must be > 0`. `A`/`C` are converted internally to ODrive ramp rates
(`accel = (rpm/60)/A` rev/s²); they are *not* accelerations.

The phase order is: boot (first call only), CONNECTING, Vbus read, CALIBRATING/CLOSED_LOOP,
RAMP_UP, MEASURING, RAMP_DOWN, SETTLING, STOPPED, then the optional index home. The cycle emits
real-time telemetry and Welford's online statistics (mean, std dev, min and max RPM) over serial.
It can abort at several points, and every abort still returns a bare `ok` to the host
(see gotcha 13). Judge success only by the terminal line:
`OK: CYCLE_COMPLETE` vs `ERR: CYCLE_COMPLETE_NO_HOME`. An `M410` (the Process Sequencer's Stop)
asks a running M750 to stop the rotor; it then prints `STATE:STOPPED` and `OK: ABORTED`. That
path has not been run on hardware.

**M751** sets the current encoder position as the 0° datum. It can fail: it refuses
without two consistent position reads, and refuses if the axis is turning faster than about
3 RPM. Success prints `OK: HOME_SET`; a failure *after the ODrive boots* prints a reason plus
`ERR: HOME_SET_FAILED`. If the deferred `boot()` itself fails, M751 prints only
`ERR: ODrive boot failed` and emits **no terminal marker at all**.

**M752** runs the ODrive encoder index search, verifies `axis0.procedure_result`, then
re-arms closed loop and commands a slow trapezoidal move **back to the saved datum**
(vel_limit 0.25 turns/s ≈ 15 RPM, 8 s watchdog). **The chuck physically rotates.** It never
moves an existing datum, and with no datum it refuses the move (`ERR: No valid home datum -- refusing
settle. Run M751 (Set Home).`). Success prints `OK: INDEX_COMPLETE`; any failure *after the
ODrive boots* prints `ERR: INDEX_HOME_FAILED` (and, if the settle timed out,
`ERR: INDEX_INCOMPLETE -- datum not reached` immediately before it). If the deferred `boot()`
itself fails (a dead link is the most likely bench failure), M752 prints only
`ERR: ODrive boot failed` and emits **no terminal marker at all**.

The index search references position modulo one turn: it corrects the fractional turn and leaves
the turn count accumulating. So before the move, M752 drops whole turns from the datum
(`DATA: DatumNormalised turns=…`), which keeps the angle and makes the settle a sub-turn move.
This replaced the old `>1 turn from home datum` refusal, which fired on every post-spin home.

**M753** is a UART diagnostic only. It calls `Spincoater::init()`, sends `r vbus_voltage`, and
dumps raw bytes as `DIAG:` lines for up to 2 s. It does not boot the ODrive, does not touch
the datum, and does not move anything, so it is the correct first command on a cold bench.

**M754** reads the ODrive encoder settings and prints them as `CFG:` lines. Like M753 it only
calls `Spincoater::init()`, and it moves nothing.

The ODrive *probe and boot* sequence is deferred to the first M750/M751/M752. Serial2 itself is
opened during Marlin `setup()`, which transmits two ODrive IDLE requests on **every** board
reset (startup safety disarm), so pin 16 is not idle at power-on.

The `SpincoaterStage/` directory contains the original standalone firmware (Nano RP2040 Connect) and dashboard used for benchtop testing. They are reference files only. The machine uses the integrated Marlin M-codes, and none of the Nano's `SPIN`/`STOP`/`HOME` text commands exist in Marlin.

## Building and Uploading

### Prerequisites

- [VS Code](https://code.visualstudio.com/) with the [PlatformIO](https://platformio.org/) extension
- USB cable to the Arduino Mega 2560

### Build Steps

1. Open the `Marlin-2.1.2.7/` directory in VS Code with PlatformIO.
2. Check that `platformio.ini` has `default_envs = mega2560`.
3. Build: click the PlatformIO checkmark button, or run:
   ```
   pio run -e mega2560
   ```
4. Upload: click the PlatformIO arrow button, or run:
   ```
   pio run -e mega2560 -t upload
   ```

Build from a short path: the AVR toolchain fails on paths over 260 characters. After an
incremental build, `M115` and the boot banner can still show the previous build's timestamp;
avrdude's post-write verify is the reliable check that the upload worked.

### Serial Connection

Connect with the included `RMR_Controller.html` or `RMR_Touch.html` web UI, Pronterface, or any serial terminal at **250000 baud**. The port is typically `/dev/ttyACM0` on Linux or `COM3` on Windows. Opening the port resets the Mega (DTR).

## Using the Machine

### Startup Sequence

```gcode
G28              ; home all axes: lid open → Z → Y → J → gripper close → X → I → K (syringe)
G28 X Y Z A B    ; home the gantry + aux axes WITHOUT retracting the syringe
```

A bare `G28` also homes the syringe (Marlin K axis, G-code letter `C`) and leaves the plunger fully open at `C0`, so no `G92` reset is needed: the syringe is a homed absolute axis.

### Moving the Gantry

```gcode
G1 X100 Y50 F3000    ; move to (100, 50) at 50 mm/s
G1 Z10 F600          ; lower Z 10 mm at 10 mm/s
```

Feedrates are in mm/min. Maximums: X 24000, Y 20000, Z 3000.

### Driving Auxiliary Motors

Each auxiliary motor has its own G-code axis letter, so no tool switching is needed:

```gcode
G1 A50 F1000     ; move Filter Feed to 50 mm at 1000 mm/min
G1 B20 F600      ; move Syringe Height to 20 mm
G1 C5 F300       ; push the syringe plunger to 5 mm from home (+C = dispense; C0 = fully open)

G91              ; relative mode
G1 C5 F300       ; dispense a further 5 mm from the current plunger position
G90              ; back to absolute mode
```

The syringe is a homed absolute axis (Marlin K axis, G-code letter `C`; `C0` = plunger fully open, soft-endstop limit 125 mm). Do **not** use `G92 C0` to re-zero it, because that defeats the soft endstops. For a relative "dispense N mm" nudge, wrap the move in `G91` / `G90` as shown. The old extruder idioms `G1 E…` / `G92 E0` are silently ignored by the current firmware (there is no E axis).

### Servos, UV Lamp, and Solenoid

```gcode
M280 P0 S90      ; close gripper (90°)
M280 P0 S170     ; open gripper (170°)
M280 P1 S115     ; close lid over the spincoater (115°)
M280 P1 S30 T800 ; open lid over 800 ms (timed linear interpolation)

; Relays (current modules are ACTIVE-HIGH):
M42 P4  S1       ; UV lamp ON        (active-high)
M42 P4  S0       ; UV lamp OFF
M42 P42 S1       ; solenoid valve OPEN  (active-high)
M42 P42 S0       ; solenoid valve CLOSED
```

The current relay modules are active-HIGH (S1 = energize, S0 = de-energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (S0 = ON, S1 = OFF). Always comment the intent in production G-code (for example `M42 P4 S1 ; UV_ON`), because the meaning of the S value depends on which relay module is installed.

### Spin Coating

```gcode
M753                       ; UART diagnostic: safe first command, does not boot or move
M752                       ; index search + return to datum: THE CHUCK ROTATES
M751                       ; set current position as 0° datum (refuses if the rotor is moving)
M750 S3000 D10 A5 C1 H1    ; 3000 RPM, 10 s dwell, 5 s ramp-up, 1 s ramp-down, home after
```

`A` and `C` are ramp **times in seconds**, not accelerations. `A5 C1` means a 5-second
ramp-up and a 1-second ramp-down.

M750 is blocking: Marlin processes no further commands until the cycle completes, except
`M112`/`M108`/`M410`, which `EMERGENCY_PARSER` dispatches straight from the serial RX path.
Anything else sent during the cycle waits in the 128-byte serial buffer, and bytes past that
are dropped silently. Use M750 inside G-code programs to sequence spin coating after gantry
positioning (see `fullcode.gcode`).

Watch the serial log, not the phase indicator. Success and failure are distinguished only by
the terminal line:

| Command | Success | Failure |
|---------|---------|---------|
| M750 | `OK: CYCLE_COMPLETE` | `ERR: CYCLE_COMPLETE_NO_HOME` (H1 home failed), or no terminal line at all on an earlier abort |
| M751 | `OK: HOME_SET` | `ERR: HOME_SET_FAILED` |
| M752 | `OK: INDEX_COMPLETE` | `ERR: INDEX_HOME_FAILED` |

`WARN:` lines carry every datum-integrity message (datum preserved, datum established,
"run M751"). Neither UI highlights them, so read them in the console.

### Runtime Tuning (no rebuild needed)

```gcode
M201 X500 Y200 Z100 A150 B50 C500   ; set max acceleration (mm/s²); C = Syringe
M203 X400 Y333 Z50 A33 B50 C8       ; set max feedrate (mm/s); C = Syringe
M500             ; NOT AVAILABLE: EEPROM_SETTINGS is disabled (Configuration.h:2220).
                 ;   Reports "EEPROM disabled" and saves nothing.
M501             ; DESTRUCTIVE: does NOT load from EEPROM. It resets every setting to the
                 ;   compiled-in Configuration.h defaults, discarding all runtime tuning.
M503             ; report all active settings (works)
```

Runtime changes last only until the next reset, and opening the serial port resets the Mega.

### Diagnostics

```gcode
M119             ; report endstop states
M114             ; report current position
M999             ; recover from "stopped" errors (NOT from M112; after M112, reset/reconnect the board)
```

## Web Controller

There are two UIs, both standalone browser pages: `RMR_Controller.html` (click-optimized, full
control, for debugging and tuning) and `RMR_Touch.html` (touchscreen-optimized, tabbed layout,
for operation). Both speak the same serial contract, and their spincoater parsing is functionally
equivalent but not identical (the Touch UI also raises toasts), so patch each file separately.

Each page reaches the Mega in one of two ways, chosen by how the page is loaded:

- **Web Serial** (opened as a local `file://`): the browser opens the USB port directly. Chrome or Edge required.
- **Pi bridge** (served over `http(s)://`, for example from the Raspberry Pi panel): the page talks WebSocket to `pi-panel/rmr_bridge.py`, which owns the port, so any browser works. See `pi-panel/README.md`.

Override with `?transport=serial|ws` or `?ws=ws://host:port`. The Controller also has a Web Serial / Pi Bridge selector in its header.

`RMR_Controller.html` features:

- XY/Z jog pads with configurable step sizes and per-axis feed sliders
- Per-axis auxiliary motor controls with individual feed sliders (A, B, C)
- Collapsible acceleration tuning panel (M201) with per-axis sliders. Its "Save to EEPROM (M500)" button and the "Save/Load EEPROM" quick buttons do not work with this firmware (EEPROM is disabled), and **Load EEPROM sends `M501`, which resets all runtime tuning to the compiled defaults.** Do not use them
- Gripper servo slider (90° to 170°) and lid servo slider (30° open to 115° closed), each with Open/Close buttons and a full-range override textbox; the lid also takes a T<ms> ramp time (default 800 ms)
- UV lamp and solenoid valve ON/OFF button pairs. If the firmware refuses or cuts the UV lamp (`UV inhibited: lid open`, `UV cut: lid opened`), the page raises an error and shows the lamp OFF
- Spincoater panel: RPM/Duration/Rise/Sink inputs, live RPM gauge, SVG circular position dial, Welford stats cards, phase indicator, and four buttons:
  - **Start** (M750), **Set Home** (M751), **Index Home** (M752, which rotates the chuck)
  - **Stop** sends **M112**. This is not a soft stop: it kills the firmware, freewheels the chuck, needs a board reset to recover, and loses the datum. The Process Sequencer's Stop is the soft one: it sends `M410`, which a running `M750` polls and honors by zeroing the rotor (`STATE:STOPPED` + `OK: ABORTED`, untested on hardware).
- E-Stop (M112): recover with a board reset (disconnect and reconnect USB). There is no Reset (M999) button (#133), because `M999` cannot recover from `M112`; type it in the console for the softer "stopped" state
- Position readout with auto-report polling
- G-code Program Runner with Load .gcode, Run/Pause/Stop, and wait-for-ok sequencing (it advances on any `ok`; see gotcha 13 and issue #48)
- Raw G-code input with command history
- Keyboard shortcuts (both UIs): arrow keys = XY, PgUp/PgDn = Z, Esc = E-Stop
- **Process Sequencer** tab: Homing / Syringe / Spin Coater / UV / Stamp recipe blocks with per-block Run, Run All and Repeat. A `MOTOR POWER LOST`, `Move refused: re-home`, UV refusal or `Error:` line from the firmware fails the running sequence at once.
  - **Syringe block:** doses with a post-dose dwell (2 s default) before a pullback at its own feed (sized on the bench to stop the drip; the max-retract cap defaults to 2 mm), with dose, retract and barrel-stroke guards, a purge routine and an idle warning. The numbers for the 150 mL catheter-tip syringe are in `DISPENSE_150ML.md`.
  - **Homing gate:** Syringe, UV and Stamp stay locked until a full home (a bare `G28`, or one naming all six axes) has completed; Spin Coater and Homing are always available. See gotcha 17 for what re-locks it.
  - **Argon purge:** the UV block can open the argon solenoid a set number of seconds before UV-on and close it a set number of seconds after UV-off (negative values allowed). The lamp and solenoid always end off and closed, even on Stop.
  - UV progress is drawn on a canvas showing the argon / UV / argon segments. Click it to cycle bar → wave → snake.
- **Run Log** tab: a per-device manufacturing log for multilayer DEAs that mirrors the MLDEA reference sheet. It has one row per dielectric layer (dispense time, volume, RPM set and settled, UV on, cure set and actual, nominal height) and one per electrode (P/N, filter pressed, hold, feeder side). The sequencer fills it in automatically, and every cell can be edited (the recorded value is kept underneath). **Hold** / **Break** buttons pause a run between commands at the end of the layer (or after the next cure or the current block) and record the pause as a row. It also has a **Log on/off** switch, manual "mark now" buttons (all filter pressing is by hand today), a journal of every event including re-runs, and Excel / CSV / JSON export; the `.xlsx` reproduces the reference sheet's layout and formulas. The log is saved in the browser and can also be auto-saved to a folder you pick. Design notes: `RUN_LOG_PLAN.md`
- **Color themes** (header selector; Touch UI: Advanced tab): Auto, Midnight, Tol dark, Tol light and Tol high-contrast. They use Paul Tol's colorblind-safe palettes, and `tools/contrast_check.py` checks every text/surface pair against WCAG AA. Keyboard focus rings and reduced-motion support are included.

`RMR_Touch.html` is the touch-panel variant of the same UI (large controls; Jog, Recipe, Log, Spin, Console, Program and Advanced tabs), with the same sequencer, Run Log, themes and Pi-bridge transport.

## Important Gotchas

1. **Axis naming:** G-code uses `A`, `B` and `C` for the Filter Feed, Syringe Height and Syringe axes (not `I`/`J`/`K`). This applies to all commands: `G1`, `M201`, `M203`, `G28` and the rest.
2. **The syringe is the C axis, not an extruder:** `EXTRUDERS 0`; the plunger is Marlin's K axis with G-code letter `C` (`+C` = dispense, `C0` = fully open, homed, soft-endstop 0 to 125 mm). `G92 E0` / `G1 E…` are silently ignored with no error, so any program still using them dispenses nothing. `fullcode.gcode`, `LayerCycle*.gcode`, `SpinCoatUVCure.gcode` and `RMR_SegmentRunner.html` still do.
3. **Filter Feed homes to MAX:** unlike every other axis, which homes to MIN, the Filter Feed (A axis) homes to its far-end endstop (I_MAX, pin 15). Advancing the stack is therefore a move toward MIN (`G1 A-…`).
4. **Servo deactivation:** servos go limp 2 seconds after positioning. If the gripper needs to hold force actively, `DEACTIVATE_SERVOS_AFTER_MOVE` must be disabled (requires a rebuild) or an external servo controller used.
5. **E-Stop recovery:** `M112` fully kills the firmware and **cannot** be recovered with `M999`. Reset the board (disconnect and reconnect USB, or power-cycle). On reboot the firmware automatically disarms the spincoater. `M999` only recovers from the softer "stopped" state. `EMERGENCY_PARSER` is enabled, so `M112`/`M108`/`M410` act immediately from the serial RX path instead of queueing behind a blocking M750. Side effect: `M0`/`M1` are now compiled in and **pause until an `M108` arrives**, where they previously returned "Unknown command". Any production G-code containing `M0`/`M1` will stall. **This side effect has not been bench-checked.**
6. **Pins 16/17 (Serial2)** are occupied by the ODrive S1 link. **Pins 19/20/21** conflict with Serial1 and I2C. Adding an I2C LCD or another serial device requires rewiring motors.
7. **Direction inversions:** Y, Z, I, J and K all have `INVERT_*_DIR true`. If an axis is added or a motor is rewired, verify its direction on the first test.
8. **AVR `println()` and ODrive:** on AVR, `Serial.println()` sends `\r\n`. The ODrive ASCII protocol expects a bare `\n`, and the stray `\r` causes "unknown command" errors. All ODrive UART writes use `print()` + `write('\n')` instead.
9. **M42 hijacks hardware timers on AVR:** stock Marlin's `M42.cpp` always falls through to `hal.set_pwm_duty(pin, pin_status)` on AVR, which maps to `analogWrite()` and takes over the pin's hardware timer compare unit, even for `S0` and `S1`. On pins tied to Timer1 (for example pin 11 = OC1A, used by Marlin's stepper ISR) this causes intermittent pin-fighting where `M42` appears to work once and then stops. The patched `M42.cpp` adds a `pin_status <= 1` early return so digital-only writes always take the plain `digitalWrite` path. For relay pins, prefer GPIO pads with no timer compare unit (pin 42 = PL7 is used for the solenoid valve; pin 4 = OC0B is tolerable only because of the patch).
10. **Relay module polarity:** the current relay modules are active-HIGH (`M42 Pxx S1` = energize, `M42 Pxx S0` = de-energize). The original Bestep JQC3F-03VDC-C modules were active-LOW (reversed polarity). The web UIs use explicit ON/OFF button pairs with hardcoded S values, so the button choice sets the polarity regardless of module type.
11. **`Servo::move()` vs `Servo::write()` in interpolation loops:** `move()` calls `attach + safe_delay(SERVO_DELAY) + detach` on every call. With SERVO_DELAY=2000, that is 2 s per step. For tight ramp loops, use `write()` with a manual `attach(0)` before and `write(final)+safe_delay(250)+detach` after. The M280 T parameter uses this approach. The default lid ramp time in the web UIs is 800 ms.
12. **M752 and `M750 ... H1` physically rotate the chuck.** After the index search the firmware re-arms closed loop and commands a slow trapezoidal move back to the saved datum, at up to about 15 RPM for up to 8 seconds. Do not run either with the lid open or with anything resting on the chuck.
13. **`ok` does not mean a spincoater command succeeded.** Every M750/M751/M752 failure path returns normally, so Marlin still emits `ok`. The Program Runner's wait-for-ok continues to the next layer after a failed home. Judge success only by the terminal marker (`OK: CYCLE_COMPLETE` / `OK: INDEX_COMPLETE` / `OK: HOME_SET`).
14. **Spincoater failure tokens used to render as successes.** Until 2026-09-14 both UIs matched tokens by substring, so `ERR: CYCLE_COMPLETE_NO_HOME` showed a green "Cycle complete" and `ERR: HOME_SET_FAILED` showed "Home datum set". `main` now dispatches `ERR:` / `OK:` by message class (PR #84's commit, merged with #106): any `ERR:` sets the error phase, and the Touch UI toasts it. `STATE:` tokens match by longest key, the failure states (`MEASURE_LINK_LOST`, `DECEL_LINK_LOST`, `DECEL_STALL`) show as errors, and an unmapped state is shown by name. Still unhandled by the spincoater panel: `WARN:` lines (the Run Log journals them while logging is on), and `OK: ABORTED`, so after a Process Sequencer Stop the panel reads "Motor stopped", the same as a normal stop. Read the console.
15. **The spincoater datum is RAM-only.** `_homePos` is not stored in EEPROM, so it is lost on every board reset, including the DTR reset the browser triggers when it connects and the reset that is the only recovery from `M112`. After any reconnect or E-stop, re-run `M751` before any layer that depends on angular registration.
16. **`M112` disarms the spincoater; it does not brake it.** `kill()` requests ODrive IDLE, so the rotor **freewheels** to a stop. This is deliberate: there is no confirmed brake resistor, and regen from a high-RPM chuck could overvolt the DC bus. Coast-down time from full speed has never been measured on this machine.
17. **Sequencer homing gate:** the web UIs track "all axes homed" in the browser. A manual bare `G28` is followed by `M118 RMR:HOMED_ALL`, which Marlin prints back only after the homing finishes; that line unlocks the Syringe, UV and Stamp blocks on every client of the Pi bridge. A `G28` naming all six axes counts as a full home too; partial homing (`G28 X Z`) does not unlock. E-stop (software or the physical one reported by the Pi bridge), `M999`, `M18`/`M84`, connect or disconnect, a firmware restart, `MOTOR POWER LOST` or `Move refused: re-home` re-locks.
18. **Pulling the USB cable mid-spin does not stop the chuck.** `M750` has no host-presence check, so the cycle runs to the end. Keep the master power switch within reach (issue #81).

## AI Attribution

Portions of this project's documentation, firmware configuration, and supporting code were written or edited with the help of Claude (Anthropic), and one April 2026 contribution came from the GitHub Copilot coding agent. The project author reviewed all AI-assisted work before it was merged; some merged changes have not yet run on hardware. See [AI_ATTRIBUTION.md](AI_ATTRIBUTION.md) for details.

## License

The Marlin firmware is licensed under the GPL v3. See the `Marlin-2.1.2.7/` directory for full license text. Project-specific files (pin map, controller UI, configurations) are provided as-is for this specific machine build.
