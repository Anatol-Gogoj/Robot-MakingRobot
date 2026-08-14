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

  if (Spincoater::doSetHome()) {
    // doSetHome() already emits DATA and TELEM lines
  }
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

  if (Spincoater::doIndexHome()) {
    // doIndexHome() already emits STATE, DATA, and TELEM lines
  }
}

#endif // SPINCOATER
