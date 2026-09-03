/**
 * motor_power.cpp — RMR motor-power (E-stop) sense
 *
 * On the layered E-stop, the second contactor removes 24V from the drivers + ODrive
 * while logic (Mega, Pi, tower) stays live. This feature reads the contactor aux so the
 * firmware reacts in software: abort motion, drop the queue, mark axes unhomed, and block
 * further moves until re-homed. See Configuration_adv.h (MOTOR_POWER_SENSE).
 */
#include "../inc/MarlinConfig.h"

#if ENABLED(MOTOR_POWER_SENSE)

#include "motor_power.h"
#include "../module/planner.h"
#include "../module/motion.h"
#include "../gcode/queue.h"

namespace motor_power {

  static bool ready  = false;   // input configured yet?
  static bool armed  = false;   // have we confirmed motor power present at least once?
  static bool rehome = false;   // a loss happened → re-home required before moving

  static void init() {
    SET_INPUT_PULLUP(MOTOR_POWER_SENSE_PIN);
    ready = true;
  }

  bool ok() {
    if (!ready) init();
    return READ(MOTOR_POWER_SENSE_PIN) == MOTOR_POWER_OK_STATE;
  }

  bool needs_rehome() { return rehome; }
  void clear_rehome() { rehome = false; }

  void task() {
    if (!ready) init();

    static millis_t next_ms = 0;
    const millis_t now = millis();
    if (PENDING(now, next_ms)) return;
    next_ms = now + 50;   // ~20 Hz

    const bool present = ok();

    if (!armed) {
      // Only start watching once we've actually seen motor power (boot-safe: an
      // unwired pin reads "lost" forever and never arms, so it can't false-fault).
      if (present) {
        armed = true;
        if (rehome) SERIAL_ECHO_MSG("Motor power restored — re-home (G28) before moving");
      }
      return;
    }

    if (!present) {
      // Motor power just dropped (E-stop). Steppers are already de-energized; stop the
      // firmware from stepping into dead drivers and invalidate the now-unknown position.
      planner.quick_stop();
      queue.clear();
      set_all_unhomed();
      rehome = true;
      armed  = false;
      SERIAL_ECHO_MSG("MOTOR POWER LOST — motion halted; re-home (G28) required");
    }
  }

} // namespace motor_power

#endif // MOTOR_POWER_SENSE
