/**
 * uv_interlock.h — RMR UV lamp lid interlock
 *
 * Firmware-side safeguard that only permits the UV lamp to be energized when a
 * lid-closed switch reads closed, and cuts UV if the lid opens mid-cure. This is
 * defense-in-depth behind a HARDWARE interlock (switch in series with the UV relay
 * coil / lamp supply), which remains the primary safety layer.
 *
 * See Configuration_adv.h (UV_LID_INTERLOCK) for pins, polarity, and wiring.
 */
#pragma once

#include "../inc/MarlinConfig.h"

#if ENABLED(UV_LID_INTERLOCK)

namespace uv_interlock {
  void init();                    // configure the lid-switch input (lazy on first use)
  bool lid_closed();              // true = lid closed (UV permitted); false = open/fault
  bool permit_uv_on();            // M42 gate: may the UV lamp be energized right now?
  void note_uv(const bool on);    // record the last commanded UV state (from M42)
  void task();                    // periodic (idle): cut UV if the lid opens while on
}

#endif // UV_LID_INTERLOCK
