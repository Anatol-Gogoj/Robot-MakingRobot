/**
 * motor_power.h — RMR motor-power (E-stop) sense
 *
 * Watches the motor-contactor aux contact. When the layered E-stop removes motor
 * power (logic stays live), the firmware aborts motion, marks all axes unhomed, and
 * refuses moves until re-homed. See Configuration_adv.h (MOTOR_POWER_SENSE) for wiring.
 */
#pragma once

#include "../inc/MarlinConfig.h"

#if ENABLED(MOTOR_POWER_SENSE)

namespace motor_power {
  void task();           // periodic (idle): detect a motor-power drop
  bool ok();             // true = motor power present
  bool needs_rehome();   // true = a loss occurred; re-home (G28) required before moving
  void clear_rehome();   // cleared by G28 once homing restores position
}

#endif // MOTOR_POWER_SENSE
