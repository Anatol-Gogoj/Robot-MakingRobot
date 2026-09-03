/**
 * uv_interlock.cpp — RMR UV lamp lid interlock
 *
 * - permit_uv_on(): gate used by M42 so the UV lamp cannot be turned on with the lid open.
 * - task(): called from idle() to cut UV if the lid opens while the lamp is energized.
 *
 * Defense-in-depth behind a hardware series interlock, which remains the primary safety
 * layer for the UV hazard. See Configuration_adv.h (UV_LID_INTERLOCK) for wiring/polarity.
 */
#include "../inc/MarlinConfig.h"

#if ENABLED(UV_LID_INTERLOCK)

#include "uv_interlock.h"

namespace uv_interlock {

  static bool ready = false;   // lid-switch input configured yet?
  static bool uv_on = false;   // last commanded UV state (tracked from M42)

  void init() {
    SET_INPUT_PULLUP(LID_SWITCH_PIN);
    ready = true;
  }

  bool lid_closed() {
    if (!ready) init();
    return READ(LID_SWITCH_PIN) == LID_CLOSED_STATE;
  }

  bool permit_uv_on() { return lid_closed(); }

  void note_uv(const bool on) { uv_on = on; }

  void task() {
    if (!ready) init();

    // Rate-limit to ~10 Hz; this runs from idle() which is called very frequently.
    static millis_t next_ms = 0;
    const millis_t now = millis();
    if (PENDING(now, next_ms)) return;
    next_ms = now + 100;

    if (uv_on && !lid_closed()) {
      OUT_WRITE(UV_LAMP_PIN, !UV_LAMP_ON_LEVEL);   // force UV off (fail-safe)
      uv_on = false;
      SERIAL_ECHO_MSG("UV cut: lid opened during cure (interlock)");
    }
  }

} // namespace uv_interlock

#endif // UV_LID_INTERLOCK
