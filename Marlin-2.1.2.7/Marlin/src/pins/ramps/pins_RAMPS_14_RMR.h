/**
 * pins_RAMPS_14_RMR.h — Robot-Making Robot
 *
 * Based on RAMPS 1.4 with no heaters/fans and custom pin assignments.
 *
 * Architecture (v2 — axis conversion):
 *   Gantry X:        X axis   (PUL=A0, DIR=A1, ENA=38)    endstop: pin 3  (X_MIN)
 *   Gantry Y:        Y axis   (PUL=A6, DIR=A7, ENA=A2)    endstop: pin 14 (Y_MIN)
 *   Gantry Y2:       Y2 clone (PUL=36, DIR=34, ENA=30)    (follows Y)
 *   Gantry Z:        Z axis   (PUL=46, DIR=48, ENA=A8)    endstop: pin 18 (Z_MIN)
 *   Filter Feed:     I axis   (PUL=2,  DIR=9,  ENA=12)    endstop: pin 15 (I_MIN)
 *   Syringe:         E0       (PUL=13, DIR=19, ENA=20)    no endstop
 *   Syringe Height:  J axis   (PUL=21, DIR=22, ENA=31)    endstop: pin 17 (J_MIN)
 *   Gripper:         Servo 0 on GPIO 5
 *   Lid:             Servo 1 on GPIO 6 (TBD — placeholder)
 *   Solenoid:        Use M42 at runtime on your chosen pin
 *
 * G-code quick-ref (AXIS4_NAME='A', AXIS5_NAME='B'):
 *   G1 X_ Y_ F_      gantry XY
 *   G1 Z_ F_          gantry Z
 *   G1 A_ F_          filter feed      (was: T0, G1 E_)
 *   G1 E_ F_          syringe          (was: T1, G1 E_)
 *   G1 B_ F_          syringe height   (was: T2, G1 E_)
 *   G28 X Y Z A B     home all axes with endstops
 *
 * Install path:  Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h
 */

// ==========================================================
//  Disable all MOSFET outputs before RAMPS include
//  (no heaters, no fans on this machine)
// ==========================================================
#define MOSFET_A_PIN   -1   // No hotend heater
#define MOSFET_B_PIN   -1   // No fan  (pin 9 reused for I-axis DIR)
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
//  I-axis: Filter Feed (Motor 1)
//  Formerly E0 — now a homeable linear axis
// ==========================================================
#define I_STEP_PIN      2    // PUL  (stock RAMPS: X_MAX — conflict resolved below)
#define I_DIR_PIN       9    // DIR  (stock RAMPS: FAN — disabled via MOSFET_B above)
#define I_ENABLE_PIN   12    // ENA  (stock RAMPS: PS_ON — conflict resolved below)

// ==========================================================
//  E0: Syringe (Motor 2)
//  Formerly E1 — now the sole extruder
// ==========================================================
#undef  E0_STEP_PIN
#undef  E0_DIR_PIN
#undef  E0_ENABLE_PIN
#define E0_STEP_PIN    13    // PUL  (also Mega onboard LED — will flicker during moves)
#define E0_DIR_PIN     19    // DIR  (Mega RX1 — OK if Serial1 unused)
#define E0_ENABLE_PIN  20    // ENA  (Mega SDA — OK if I2C unused)

// ==========================================================
//  J-axis: Syringe Height (Motor 3)
//  Formerly E2 — now a homeable linear axis
// ==========================================================
#define J_STEP_PIN     21    // PUL  (Mega SCL — OK if I2C unused)
#define J_DIR_PIN      22    // DIR
#define J_ENABLE_PIN   31    // ENA

// ==========================================================
//  Pin conflict resolution
// ==========================================================

// Pin 2 is X_MAX_PIN on stock RAMPS — repurposed for I-axis STEP
#undef  X_MAX_PIN
#define X_MAX_PIN      -1

// Pin 19 is Z_MAX_PIN on stock RAMPS — repurposed for E0 DIR
#undef  Z_MAX_PIN
#define Z_MAX_PIN      -1

// Pin 12 is PS_ON_PIN on stock RAMPS — repurposed for I-axis ENABLE
#undef  PS_ON_PIN
#define PS_ON_PIN      -1

// Pin 13 is LED_PIN on many Mega configs — repurposed for E0 STEP
#ifdef LED_PIN
  #undef  LED_PIN
#endif
#define LED_PIN        -1

// Stock RAMPS E1 pins (36/34/30) are physically wired to Y2.
// Undef them so they don't collide with Y2 definitions above.
#undef  E1_STEP_PIN
#undef  E1_DIR_PIN
#undef  E1_ENABLE_PIN
#define E1_STEP_PIN    -1
#define E1_DIR_PIN     -1
#define E1_ENABLE_PIN  -1

// Stock RAMPS E2 pins — no longer used (J-axis has its own defines)
#undef  E2_STEP_PIN
#undef  E2_DIR_PIN
#undef  E2_ENABLE_PIN
#define E2_STEP_PIN    -1
#define E2_DIR_PIN     -1
#define E2_ENABLE_PIN  -1

// ==========================================================
//  Endstops
// ==========================================================

// Z endstop: pin 18 on RAMPS Z- header
#undef  Z_MIN_PIN
#define Z_MIN_PIN      18    // Gantry Z endstop

// Disable Y_MAX (pin 15 repurposed for I-axis endstop)
#undef  Y_MAX_PIN
#define Y_MAX_PIN      -1

// I-axis (Filter Feed) endstop: pin 15 on RAMPS Y+ header
#define I_MIN_PIN      15

// J-axis (Syringe Height) endstop: pin 17 (Mega TX2)
#define J_MIN_PIN      17

// ==========================================================
//  Servo pins
// ==========================================================

// Stock RAMPS assigns SERVO2 to pin 5 — undef to avoid duplicate claim
#undef  SERVO2_PIN

// Gripper on GPIO 5 (RAMPS SERVO2 slot — remapped to SERVO0)
#undef  SERVO0_PIN
#define SERVO0_PIN      5    // M280 P0 S<angle>

// Lid on GPIO 6 (standard RAMPS SERVO1 slot — uncomment when wired)
// #undef  SERVO1_PIN
// #define SERVO1_PIN   6    // M280 P1 S<angle>
