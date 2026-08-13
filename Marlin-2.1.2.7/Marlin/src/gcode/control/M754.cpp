/**
 * M754.cpp — Spincoater encoder configuration dump
 *
 * Reads the ODrive properties that decide whether the encoder is
 * index-referenced for POSITION, and prints them in one block.
 *
 * WHY THIS EXISTS
 *   Run sheet Task 2 answers the question the spin coater's homing bug hangs
 *   on: after an index search, does pos_estimate return to ~0, or hold its
 *   pre-search value? Answering it normally means odrivetool over the ODrive's
 *   native USB.
 *
 *   On 2026-08-13 that USB link failed with "can't set config #1, error -71"
 *   and no software reset would recover it, while the Serial2 UART link stayed
 *   healthy (M753 returned 24.118456 V in 5 ms). The ODrive's processor was
 *   fine; only its USB peripheral was broken.
 *
 *   This command reads the same properties over the link that still works, so
 *   a dead USB port cannot block the investigation. It is also simply more
 *   convenient: the answer arrives in the same serial session already open.
 *
 * SAFETY
 *   Read-only, by construction. It calls Spincoater::init() — which only opens
 *   the port — never boot(), and issues only 'r' queries. Nothing is armed,
 *   nothing is written, and the motor does not turn.
 *
 *   A general write passthrough was deliberately NOT built. It would let
 *   anyone type 'w axis0.requested_state 8' into the UI's raw G-code box and
 *   spin the chuck, on a machine whose mechanical E-stop is still issue #20.
 *
 * READING THE OUTPUT
 *   index_offset_valid is the one that matters. If it is False, the encoder
 *   was never position-referenced, 't 0 <x>' drives to the power-on shaft
 *   angle rather than to a fixed datum, and the two-phase homing design rests
 *   on a false premise — see issues #45, #52, #54 and #55.
 *
 *   gpio10_mode must be 0 (DIGITAL). 17 (AUTO) means the Z pulse is never
 *   sampled at all, a documented S1 + AMT-10x failure mode.
 */

#include "../../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "../gcode.h"
#include "../../feature/spincoater.h"
#include "../../MarlinCore.h"       // idle()

// Property names live in PROGMEM: RAM is the tighter constraint on this board
// (43.9% at the stack tip) and these strings total several hundred bytes.
static const char P00[] PROGMEM = "fw_version_major";
static const char P01[] PROGMEM = "fw_version_minor";
static const char P02[] PROGMEM = "fw_version_revision";
static const char P03[] PROGMEM = "config.gpio10_mode";
static const char P04[] PROGMEM = "axis0.commutation_mapper.config.use_index_gpio";
static const char P05[] PROGMEM = "axis0.commutation_mapper.config.index_gpio";
static const char P06[] PROGMEM = "axis0.pos_vel_mapper.config.use_index_gpio";
static const char P07[] PROGMEM = "axis0.pos_vel_mapper.config.index_gpio";
static const char P08[] PROGMEM = "axis0.pos_vel_mapper.config.index_offset";
static const char P09[] PROGMEM = "axis0.pos_vel_mapper.config.index_offset_valid";
static const char P10[] PROGMEM = "axis0.config.startup_encoder_index_search";
static const char P11[] PROGMEM = "inc_encoder0.config.cpr";
static const char P12[] PROGMEM = "axis0.pos_vel_mapper.pos_estimate";
static const char P13[] PROGMEM = "axis0.current_state";

static const char* const SPIN_CFG_PROPS[] PROGMEM = {
  P00, P01, P02, P03, P04, P05, P06, P07, P08, P09, P10, P11, P12, P13
};

// Longest name above is 45 characters; 64 leaves headroom without being
// careless with a stack buffer on a board with 8 KB of RAM.
#define SPIN_PROP_BUFLEN 64

void GcodeSuite::M754() {

  // init() only opens the port. It does NOT boot(), so no index search and
  // no motion. This is what makes the command safe to run unattended.
  Spincoater::init();

  SERIAL_ECHOLNPGM("echo:SPIN CFG: === ENCODER CONFIGURATION ===");

  const uint8_t count = sizeof(SPIN_CFG_PROPS) / sizeof(SPIN_CFG_PROPS[0]);
  uint8_t failures = 0;

  for (uint8_t i = 0; i < count; ++i) {
    // Each readRaw can wait up to its own timeout. Pet the watchdog between
    // queries rather than relying on the short reply loops to do it.
    idle();

    char prop[SPIN_PROP_BUFLEN];
    strncpy_P(prop, (const char*)pgm_read_ptr(&SPIN_CFG_PROPS[i]), SPIN_PROP_BUFLEN - 1);
    prop[SPIN_PROP_BUFLEN - 1] = '\0';

    String value = Spincoater::readRaw(prop);

    SERIAL_ECHOPGM("echo:SPIN CFG: ");
    SERIAL_ECHO(prop);
    SERIAL_ECHOPGM(" = ");
    if (value.length() == 0) {
      // An empty reply means no answer within the read timeout, or a property
      // this firmware version does not have. Both are reported as-is rather
      // than guessed at -- an ODrive lacking a property must not be confused
      // with a dead link.
      SERIAL_ECHOLNPGM("<no reply>");
      failures++;
    }
    else {
      SERIAL_ECHOLN(value.c_str());
    }
  }

  if (failures == count) {
    SERIAL_ECHOLNPGM("echo:SPIN CFG: >>> NO REPLIES AT ALL <<<");
    SERIAL_ECHOLNPGM("echo:SPIN CFG: The UART link is down. Run M753 first.");
  }
  else if (failures) {
    SERIAL_ECHOPGM("echo:SPIN CFG: ");
    SERIAL_ECHO(failures);
    SERIAL_ECHOLNPGM(" propertie(s) gave no reply -- check the ODrive firmware version above.");
  }

  SERIAL_ECHOLNPGM("echo:SPIN CFG: === END ===");
}

#endif // SPINCOATER
