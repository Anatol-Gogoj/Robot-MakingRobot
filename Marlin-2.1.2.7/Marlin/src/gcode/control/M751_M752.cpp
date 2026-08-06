/**
 * M751_M752.cpp — Spincoater datum and homing commands
 *
 * M751: Set current encoder position as 0° datum (Set Home)
 *   - Reads current ODrive position, stores as homePos
 *   - Emits TELEM with DEG=0.00
 *   - Dashboard dial snaps to 0°
 *
 * M752: Encoder index search (Index Home)
 *   - Runs ODrive ENCODER_INDEX_SEARCH
 *   - Trapezoidal settle back to the saved home datum
 *   - Does NOT reset home datum
 *   - Preserves the existing 0° reference from last M751
 */

#include "../../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "../gcode.h"
#include "../../feature/spincoater.h"

void GcodeSuite::M751() {
  // Boot ODrive if not already initialized
  if (!Spincoater::isReady()) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:BOOTING");
    if (!Spincoater::boot()) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive boot failed");
      return;
    }
  }

  // doSetHome() emits its own DATA/TELEM/ERR detail; add a terminal marker so
  // a failed M751 is visible to the UIs and to program runners. Issue #41.
  if (!Spincoater::doSetHome())
    SERIAL_ECHOLNPGM("echo:SPIN ERR: HOME_SET_FAILED");
}

void GcodeSuite::M752() {
  // Boot ODrive if not already initialized
  if (!Spincoater::isReady()) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:BOOTING");
    if (!Spincoater::boot()) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive boot failed");
      return;
    }
  }

  // doIndexHome() emits its own STATE/DATA/TELEM detail. Its return value is
  // now meaningful (issues #41/#43), so a failure must produce a terminal
  // marker rather than being silently discarded — fullcode.gcode runs M752
  // before M751, and a silent failure there means every layer is coated
  // against a datum that was never index-referenced.
  if (!Spincoater::doIndexHome())
    SERIAL_ECHOLNPGM("echo:SPIN ERR: INDEX_HOME_FAILED");
}

#endif // SPINCOATER
