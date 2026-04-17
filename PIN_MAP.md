# Robot-Making Robot — Pin Map and Wiring Reference

**Platform:** Arduino Mega 2560 running Marlin 2.1.2.7, custom board `BOARD_RAMPS_14_RMR` (ID 1020).

**Authoritative source:** `Marlin-2.1.2.7/Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` (plus inherited assignments from stock `pins_RAMPS.h`). This document consolidates and mirrors those headers for bench/wiring use. If the two disagree, the `.h` file wins — update this document.

**Last updated:** 2026-04-16 (relay modules changed to active-HIGH, M280 T parameter documented)

---

## Quick physical summary

- 6 stepper drivers (DM556T externals): X, Y (1 driver / 2 motors), Z, Filter Feed (I), Syringe Height (J), Syringe (E0)
- 5 homing endstops: X, Y, Z, I, J (E0 has no endstop)
- 2 servos: gripper (pin 5), lid (pin 6)
- 2 opto-isolated relays: UV lamp, solenoid valve (current modules: active-HIGH; original Bestep JQC3F-03VDC-C were active-LOW; 3.3 V buck rail)
- 1 spincoater: ODrive S1 on Serial2 (115200 baud raw ASCII)

---

## Stepper drivers (all DM556T externals, 1/8 microstepping, 1600 steps/rev)

Pin columns show the Mega GPIO number in decimal. For analog pins, the `Ax` alias is shown first with the digital-equivalent number in parentheses (e.g. `A0 (54)`).

| Marlin Axis | G-code Letter | Function        | Driver     | PUL       | DIR       | ENA       | Steps/mm | Travel (mm) | Notes |
|-------------|---------------|-----------------|------------|-----------|-----------|-----------|----------|-------------|-------|
| X           | X             | Gantry X        | DM556T #1  | A0 (54)   | A1 (55)   | 38        | 57.14    | 770         | GT2-14 pulley (28 mm/rev) |
| Y           | Y             | Gantry Y1       | DM556T #2a | A6 (60)   | A7 (61)   | A2 (56)   | 57.14    | 150         | GT2-14 pulley. Drives the first Y motor. |
| Y2          | —             | Gantry Y2       | DM556T #2b | 36        | 34        | 30        | (follows Y) | —        | Second Y motor on its **own** DM556T driver with its own PUL/DIR/ENA signal set. `Y2_DRIVER_TYPE` is defined in `Configuration.h` so Marlin pulses this pin set in lockstep with the Y pin set — step/direction signals are synchronized by the firmware, not by a splicing the Mega outputs together. Auto-squaring (`Y_DUAL_ENDSTOPS`) is possible in principle since each motor has an independent driver, but it would require adding a second Y endstop (currently only pin 14 / Y_MIN is populated). |
| Z           | Z             | Gantry Z        | DM556T #3  | 46        | 48        | A8 (62)   | 320      | 186         | 5 mm/rev lead screw. `INVERT_Z_DIR true`. |
| I           | A             | Filter Feed     | DM556T #4  | 2         | 9         | 12        | 320      | 343         | 5 mm/rev lead screw. `AXIS4_NAME='A'`. Homes to MAX. `INVERT_I_DIR true`. |
| J           | B             | Syringe Height  | DM556T #5  | 21        | 22        | 31        | 320      | 304         | 5 mm/rev lead screw. `AXIS5_NAME='B'`. `INVERT_J_DIR true`. |
| E0          | E             | Syringe (sole extruder) | DM556T #6 | 13 | 19        | 20        | 1600     | —           | 1 mm/rev lead screw. `EXTRUDERS 1`, `EXTRUDE_MINTEMP 0` (cold extrusion allowed). |

Steps/mm derivation: `(motor_steps_per_rev × microstepping) ÷ linear_travel_per_rev` = `(200 × 8) ÷ travel_per_rev`.

---

## Homing endstops

All endstops are NO (normally-open), wired **COM → Mega GND, NO → signal pin**. Internal pullups via `ENDSTOPPULLUPS`. Logic: untriggered = HIGH, triggered = LOW, `*_ENDSTOP_INVERTING true`.

| Axis | G-code | Pin | Marlin Define   | Home Direction | Notes |
|------|--------|-----|-----------------|----------------|-------|
| X    | X      | 3   | `X_MIN_PIN`     | MIN (-1)       | Hardware-interrupt capable |
| Y    | Y      | 14  | `Y_MIN_PIN`     | MIN (-1)       | — |
| Z    | Z      | 40  | `Z_STOP_PIN`    | MIN (-1)       | **Moved from pin 18 (TX1) due to EMI false triggers.** Uses `Z_STOP_PIN` (not `Z_MIN_PIN`) so `pins_postprocess.h` can't override. 100 nF cap from pin 40 to GND recommended. `ENDSTOP_NOISE_THRESHOLD 7`. |
| I    | A      | 15  | `I_MAX_PIN`     | **MAX (+1)**   | Filter Feed homes to the far end. RAMPS Y+ header. |
| J    | B      | 23  | `J_MIN_PIN`     | MIN (-1)       | **Moved from pin 17 (TX2) to free Serial2 for ODrive.** |
| E0   | E      | —   | —               | (no endstop)   | Syringe has no endstop. |

Homing order (`G28`, via patched `G28.cpp`): **lid open (servo 1 → 30°) → Z → Y → J → gripper close (servo 0 → 90°) → X → I**. `HOME_Z_FIRST` enabled, `Z_SAFE_HOMING` disabled.

---

## Servos

| Servo | Slot     | Pin | Command         | Range                                 | Notes |
|-------|----------|-----|-----------------|---------------------------------------|-------|
| 0     | Gripper  | 5   | `M280 P0 S<angle>` | 90° closed, 170° open (soft limits in HTML; firmware clamp removed) | Remapped from stock RAMPS SERVO2 slot to SERVO0 index. `M280.cpp` patched to allow full 0–180° via override textbox. |
| 1     | Lid      | 6   | `M280 P1 S<angle>` | 0–180° (no soft limits)               | Stock RAMPS SERVO1 slot. Full 0–180° range; no firmware clamp. |

`NUM_SERVOS 2`, `DEACTIVATE_SERVOS_AFTER_MOVE` enabled with 2-second hold (`SERVO_DELAY { 2000, 2000 }`) to prevent PWM jitter. Servo goes limp 2 s after each `M280` — gripper must be mechanically self-holding.

**T parameter (timed ramp):** `M280 Px S<angle> T<ms>` performs a linear interpolation from the current angle to the target over T milliseconds (plus 250ms settle). Available on all servos (POLARGRAPH gate removed). When T=0 or omitted, falls through to normal `move()` with full SERVO_DELAY. Default lid ramp in the HTML UIs is 800ms.

**Important:** In G-code programs, place `M400` before `M280` to drain the motion planner queue first. `G4` (dwell) alone is not a reliable substitute. When using `T<ms>`, the ramp itself is blocking (T + 250ms), so a `G4` after `M280` may not be necessary.

---

## Relay outputs

Both modules share a dedicated 3.3 V buck converter rail (grounded to the Mega). `DIRECT_PIN_CONTROL` enabled in `Configuration_adv.h`. `M42.cpp` patched with `pin_status <= 1` early return to prevent AVR timer hijack — see gotcha #12 in `claude.md`.

| Function    | Pin | AVR Port | Timer Unit | Command (ON)    | Command (OFF)   | Notes |
|-------------|-----|----------|------------|-----------------|-----------------|-------|
| UV lamp     | 4   | PG5      | OC0B (Timer0) | `M42 P4 S1`  | `M42 P4 S0`  | RAMPS SERVO3 slot. Only safe with the M42.cpp patch because OC0B shares Timer0 with `millis()`. |
| Solenoid valve | 42 | PL7      | **none**      | `M42 P42 S1` | `M42 P42 S0` | AUX2_08 header. Pure GPIO — no timer compare unit. Preferred for future relay expansion. |

**Current modules (active-HIGH):** `S1` = energize (ON), `S0` = de-energize (OFF). The HTML UI uses explicit ON/OFF button pairs with hardcoded S values — no internal state tracking.

**Original modules (Bestep JQC3F-03VDC-C, active-LOW, replaced):** The opto LED cathode tied to the IN pin with anode on VCC, so pulling IN to GND lit the opto and energized the coil. `S0` = energized, `S1` = de-energized. Boot-time floating inputs were pulled HIGH by the module's internal pullup (safe de-energized state, no chatter on Mega reset).

**Why not pin 11 or pin 28:** Pin 11 = OC1A, used by Marlin's stepper ISR (Timer1) — continuous fighting. Pin 28 = `E0_DIR_PIN`, actively driven by the stepper subsystem on every syringe move.

---

## Spincoater (ODrive S1 via Serial2)

| Signal          | Mega Pin | ODrive Pin            | Notes |
|-----------------|----------|-----------------------|-------|
| UART TX (Mega → ODrive RX) | 16 (TX2) | J11 pin 4 (GPIO7 / RX) | 115200 baud raw ASCII protocol |
| UART RX (Mega ← ODrive TX) | 17 (RX2) | J11 pin 3 (GPIO6 / TX) | — |
| GND             | GND      | J11 GND               | Common ground required |
| (5 V logic)     | —        | J11 5V                | ODrive provides its own 5V logic supply |

Motor: D5312s-330kV BLDC with AMT102 incremental encoder. G-codes: `M750` (spin cycle), `M751` (set home datum), `M752` (index search), `M753` (UART diagnostic). See `SpincoaterPinMap.jfif` for the J11 connector pinout image.

**ODrive protocol note:** On AVR, `Serial.println()` sends `\r\n` — the ODrive rejects the stray `\r`. All ODrive UART writes in `spincoater.cpp` use `print()` + `write('\n')` instead of `println()`. See gotcha #11 in `claude.md`.

---

## Mega / RAMPS pin reassignments (conflicts resolved in pins_RAMPS_14_RMR.h)

Several stock RAMPS 1.4 pin assignments had to be freed for our auxiliary axes and spincoater UART. These are the overrides applied in the custom pins file:

| Pin | Stock RAMPS Function | Reassigned To            | Resolution                                 |
|-----|---------------------|--------------------------|--------------------------------------------|
| 2   | X_MAX_PIN           | I STEP (Filter Feed)     | `X_MAX_PIN → -1`                           |
| 9   | FAN (MOSFET_B)      | I DIR (Filter Feed)      | `MOSFET_B_PIN → -1`                        |
| 12  | PS_ON_PIN           | I ENABLE (Filter Feed)   | `PS_ON_PIN → -1`                           |
| 13  | LED_PIN             | E0 STEP (Syringe)        | `LED_PIN → -1`                             |
| 15  | Y_MAX_PIN           | I_MAX endstop (Filter Feed) | `Y_MAX_PIN → -1`                        |
| 16  | Serial2 TX          | ODrive S1 UART TX        | Repurposed for spincoater link             |
| 17  | Serial2 RX / J_MIN  | ODrive S1 UART RX        | J endstop relocated from pin 17 → pin 23   |
| 19  | Serial1 RX / Z_MAX  | E0 DIR (Syringe)         | `Z_MAX_PIN → -1`, OK if Serial1 unused     |
| 20  | I2C SDA             | E0 ENABLE (Syringe)      | OK if I2C unused                           |
| 21  | I2C SCL             | J STEP (Syringe Height)  | OK if I2C unused                           |
| 23  | (free)              | J endstop (Syringe Height) | New assignment, ex-pin-17                |
| 40  | (free)              | Z endstop                | Moved from pin 18 (TX1) due to EMI         |

---

## Reserved / known-unusable pins

Pins to avoid reclaiming without careful review:

| Pin | Why avoid | Consequence of using anyway |
|-----|-----------|-----------------------------|
| 0, 1 | USB Serial0 (`Serial`) | Host communication at 250000 baud — breaks Marlin console if used |
| 11  | **Timer1 OC1A — Marlin stepper ISR** | `analogWrite(11)` or timer PWM fights the stepper ISR continuously. Digital writes also unreliable. |
| 16, 17 | Serial2 / ODrive | Breaks spincoater link |
| 18  | Formerly Z endstop (TX1 / Serial1 TX) | Free now, but historically EMI-sensitive during stepper motion — not recommended for any analog/digital input |
| 19, 20, 21 | E0 driver (DIR/ENA/STEP) + former Serial1 RX / I2C | Breaks syringe extruder; blocks adding I2C or Serial1 devices |
| 28  | `E0_DIR_PIN` — actively driven by stepper subsystem | Pin state changes on every syringe move |
| 44, 45, 46 | Timer5 (OC5C/B/A). Pin 46 = Z_PUL, 44/45 free but Timer5 is used by Marlin servo library when `NUM_SERVOS > 0` | `analogWrite` / PWM conflicts with servo refresh |

---

## Known-free GPIO for future expansion

Pins below are verified free in the current build (`pins_RAMPS.h` + custom `pins_RAMPS_14_RMR.h` + `Configuration.h` with no LCD, no `SDSUPPORT`, `TEMP_SENSOR_0 0`). `pins_postprocess.h` grepped for all 14 pin numbers — no matches, so no late-stage derivation will claim them.

| Pin | AVR Port | Timer?        | Header / Label | Status in this build | Would become claimed if… |
|-----|----------|---------------|----------------|----------------------|--------------------------|
| 18  | PD3      | OC3A (Timer3) | Serial1 TX     | Free (EMI-sensitive — avoid for inputs; OK for slow outputs) | A Z or I MIN endstop is re-enabled without undef |
| 37  | PC0      | none          | AUX4_09        | Free                 | LCD display defined (becomes `EXP2_05_PIN` / `EXP1_01_PIN`) |
| 39  | PG2      | none          | AUX4_08        | Free                 | — (label only in stock RAMPS) |
| 41  | PG0      | none          | AUX4_07        | Free                 | LCD display defined (becomes `EXP2_08_PIN`) |
| 42  | **PL7**  | **none**      | AUX2_08        | **Used: solenoid valve relay** | — |
| 43  | PL6      | none          | AUX4_06        | Free                 | — (label only in stock RAMPS) |
| 47  | PL2      | none          | AUX4_04        | Free                 | — (label only in stock RAMPS) |
| 49  | PL0      | none          | AUX3_02        | Free                 | LCD + SDSUPPORT enabled (becomes `SD_DETECT_PIN` / `EXP2_07_PIN`) |
| 57  | PF3 (A3) | none          | AUX1_05        | Free                 | — (label only in stock RAMPS) |
| 58  | PF4 (A4) | none          | AUX1_07        | Free                 | — (label only in stock RAMPS) |
| 59  | PF5 (A5) | none          | AUX2_03        | Free                 | — (label only in stock RAMPS) |
| 63  | PK1 (A9) | none          | AUX2_04        | Free                 | — (label only in stock RAMPS) |
| 64  | PK2 (A10)| none          | AUX2_05        | Free                 | — (label only in stock RAMPS) |
| 65  | PK3 (A11)| none          | AUX2_10        | Free                 | LCD defined with software-controllable backlight (stock RAMPS defines `LCD_BACKLIGHT_PIN -1` anyway) |
| 66  | PK4 (A12)| none          | AUX2_09        | Free                 | `TEMP_SENSOR_0` set to a Max6675/Max31855 thermocouple type (becomes `TEMP_0_CS_PIN`) |

**Recommendation for new relay / output channels:** Prefer pins with no timer compare unit at all (the "Timer? = none" rows above). Avoid any pin labeled `OCxY` in the Mega2560 datasheet (Timer compare outputs) unless you've verified the M42.cpp patch is present *and* that specific timer is not used by Marlin (Timer0 = `millis()`, Timer1 = stepper ISR, Timer3/4 = servo library when `NUM_SERVOS > 0`, Timer5 = alternate servo).

**Before wiring to any "conditional" pin above:** verify the relevant `#define` is still off in `Configuration.h` — LCD displays, SDSUPPORT, and thermocouple temperature sensors are the three config changes that would reclaim pins in this table.

---

## Cross-references

- Firmware pin overrides: `Marlin-2.1.2.7/Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h`
- Board registration: `Marlin-2.1.2.7/Marlin/src/core/boards.h` (ID 1020)
- Board routing: `Marlin-2.1.2.7/Marlin/src/pins/pins.h`
- Main config: `Marlin-2.1.2.7/Marlin/Configuration.h`
- Advanced config (SPINCOATER, DIRECT_PIN_CONTROL): `Marlin-2.1.2.7/Marlin/Configuration_adv.h`
- Gotchas and bring-up notes: `claude.md`
- User-facing usage: `README.md`
- ODrive J11 connector pinout image: `SpincoaterPinMap.jfif`
