/**
 * pins_RAMPS_14_RMR.h — Robot-Making Robot
 *
 * Based on RAMPS 1.4 with no heaters/fans and custom extruder pins.
 *
 * Gantry:   X (A0/A1/38), Y (A6/A7/A2), Y2 (36/34/30), Z (46/48/A8)
 * Motor 1:  Filter Feed  → E0  (PUL=2, DIR=9, ENA=12)
 * Motor 2:  Syringe      → E1  (PUL=13, DIR=19, ENA=20)
 * Motor 3:  Syringe Ht   → E2  (PUL=21, DIR=22, ENA=31)
 * Gripper:  Servo 0 on GPIO 5
 * Lid:      Servo 1 on GPIO 6 (TBD — placeholder)
 * Solenoid: Use M42 at runtime on your chosen pin
 *
 * Install path:  Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h
 */

// No heaters, no fans — disable all MOSFET outputs before RAMPS include
#define MOSFET_A_PIN   -1   // No hotend heater
#define MOSFET_B_PIN   -1   // No fan  (pin 9 reused for Motor 1 DIR)
#define MOSFET_C_PIN   -1   // No heated bed

// Pull in base RAMPS 1.4 pin definitions
#include "pins_RAMPS.h"

// Marlin sanity check requires HEATER_0_PIN >= 0 when EXTRUDERS > 0,
// even though we have no heaters. Assign to an unconnected pin.
// With TEMP_SENSOR_0 = 0 the firmware will never drive this pin.
#undef  HEATER_0_PIN
#define HEATER_0_PIN    7   // RAMPS SERVO3 slot — not physically connected

// ==========================================================
//  Y2 dual-stepper pins (explicit — prevent auto-assignment
//  from E slots in pins_postprocess.h)
// ==========================================================
#undef  Y2_STEP_PIN
#undef  Y2_DIR_PIN
#undef  Y2_ENABLE_PIN
#define Y2_STEP_PIN    36   // Stock RAMPS E1 STEP slot
#define Y2_DIR_PIN     34   // Stock RAMPS E1 DIR slot
#define Y2_ENABLE_PIN  30   // Stock RAMPS E1 ENABLE slot

// ==========================================================
//  Extruder pin overrides — custom wiring for aux motors
// ==========================================================

// --- E0 → Filter Feed (Motor 1) ---
#undef  E0_STEP_PIN
#undef  E0_DIR_PIN
#undef  E0_ENABLE_PIN
#define E0_STEP_PIN     2    // PUL  (stock RAMPS: X_MAX — see conflict fix below)
#define E0_DIR_PIN      9    // DIR  (stock RAMPS: FAN — disabled via MOSFET_B above)
#define E0_ENABLE_PIN  12    // ENA  (stock RAMPS: PS_ON — see conflict fix below)

// --- E1 → Syringe (Motor 2) ---
//     Stock E1 pins (36/34/30) are physically wired to Y2.
//     Marlin's pins_postprocess.h auto-assigns Y2 to E1 slot when
//     Y2_DRIVER_TYPE is defined and Y2_STEP_PIN is not.
//     We override E1 here so the syringe gets its own pins.
#undef  E1_STEP_PIN
#undef  E1_DIR_PIN
#undef  E1_ENABLE_PIN
#define E1_STEP_PIN    13    // PUL  (also Mega onboard LED — will flicker during moves)
#define E1_DIR_PIN     19    // DIR  (Mega RX1 — OK if Serial1 unused)
#define E1_ENABLE_PIN  20    // ENA  (Mega SDA — OK if I2C unused)

// --- E2 → Syringe Height (Motor 3) ---
#define E2_STEP_PIN    21    // PUL  (Mega SCL — OK if I2C unused)
#define E2_DIR_PIN     22    // DIR
#define E2_ENABLE_PIN  31    // ENA

// ==========================================================
//  Pin conflict resolution
// ==========================================================

// Pin 2 is X_MAX_PIN on stock RAMPS — repurposed for E0 step
#undef  X_MAX_PIN
#define X_MAX_PIN      -1

// Pin 19 is Z_MAX_PIN on stock RAMPS — repurposed for E1 DIR
// Pin 18 is Z_MIN_PIN on stock RAMPS — no Z endstop, free the pin
#undef  Z_MAX_PIN
#define Z_MAX_PIN      -1
#undef  Z_MIN_PIN
#define Z_MIN_PIN      -1

// Pin 12 is PS_ON_PIN on stock RAMPS — repurposed for E0 enable
#undef  PS_ON_PIN
#define PS_ON_PIN      -1

// Pin 13 is LED_PIN on many Mega configs — repurposed for E1 step
#ifdef LED_PIN
  #undef  LED_PIN
#endif
#define LED_PIN        -1

// ==========================================================
//  Servo pins
// ==========================================================

// Stock RAMPS assigns SERVO2 to pin 5 — undef to avoid duplicate claim
#undef  SERVO2_PIN

// Gripper on GPIO 5 (RAMPS SERVO2 slot — remapped to SERVO0 for convenience)
#undef  SERVO0_PIN
#define SERVO0_PIN      5    // M280 P0 S<angle>

// Lid on GPIO 6 (standard RAMPS SERVO1 slot — assign when wired)
// #undef  SERVO1_PIN
// #define SERVO1_PIN   6    // M280 P1 S<angle>  — uncomment when lid GPIO is confirmed
