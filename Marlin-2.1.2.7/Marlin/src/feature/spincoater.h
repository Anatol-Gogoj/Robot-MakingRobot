/**
 * spincoater.h — ODrive S1 raw ASCII communication layer
 *
 * Talks to an ODrive S1 over SPINCOATER_SERIAL (Serial2 on Mega 2560)
 * using the ODrive ASCII protocol. No ODriveUART library dependency.
 *
 * Ported from SpincoaterStage/src/main.cpp v2.6 (Nano RP2040 test firmware).
 * Serial1 → SPINCOATER_SERIAL, Serial.print → Marlin SERIAL_ECHO macros.
 */

#pragma once

#include "../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

// ODrive axis states (stable across firmware versions)
#define ODRIVE_STATE_UNDEFINED                  0
#define ODRIVE_STATE_IDLE                       1
#define ODRIVE_STATE_FULL_CALIBRATION_SEQUENCE  3
#define ODRIVE_STATE_ENCODER_INDEX_SEARCH       6
#define ODRIVE_STATE_CLOSED_LOOP_CONTROL        8

namespace Spincoater {

  /**
   * Initialize Serial2 at SPINCOATER_BAUD.
   * Called once on first M750/M751/M752 invocation.
   */
  void init();

  /**
   * Full boot sequence: probe ODrive UART (15s timeout),
   * auto encoder index search, trapezoidal settle to index mark,
   * restore velocity control mode.
   * Returns true if ODrive is ready for spin cycles.
   */
  bool boot();

  /** True after successful boot(). */
  bool isReady();

  /**
   * Read an ODrive property: sends "r <property>\n", returns response string.
   * Timeout 500ms. Returns empty string on failure.
   */
  String readRaw(const char* property);

  /**
   * Write an ODrive property: sends "w <property> <value>\n".
   */
  void writeRaw(const char* property, float value);

  /**
   * Read position + velocity via "f 0\n" → "<pos> <vel>\n".
   * Returns true on success, fills pos (turns) and vel (turns/s).
   *
   * Requires a complete newline-terminated reply and strictly numeric tokens:
   * a truncated or corrupted line is a FAILED read, never a pos=0/vel=0
   * reading. Issue #44.
   */
  bool feedback(float &pos, float &vel);

  /**
   * feedback() twice, requiring the two reads to be CONSISTENT with each
   * other and with the measured velocity. A pure corruption filter — it works
   * at any rotor speed, including a freewheeling coast-down, because the
   * position window is predicted from the velocity rather than fixed.
   *
   * For one-shot decisions that move the datum or judge whether the rotor has
   * stopped; too slow for telemetry loops (up to 6 UART round trips). Retries
   * three times and calls idle(). Returns false only when no consistent pair
   * could be obtained, which callers must treat as "refuse to act". Issue #44.
   */
  bool feedbackStable(float &pos, float &vel);

  /**
   * Command velocity: "v 0 <rps> 0\n"
   */
  void setVelocity(float rps);

  /**
   * Read axis state: "r axis0.current_state\n" → int.
   * Returns ODRIVE_STATE_UNDEFINED on timeout.
   */
  int getState();

  /**
   * Set axis state: "w axis0.requested_state <state>\n"
   */
  void setState(int state);

  /**
   * Clear ODrive errors: "sc\n"
   * NOTE: this wipes active_errors and disarm_reason — always call
   * reportFault() BEFORE this if you need to know why something failed.
   */
  void clearErrors();

  /**
   * Read axis0.procedure_result (ODrive 0.6.x). 0 == SUCCESS.
   * Returns -1 if the value could not be read or was not numeric — callers
   * must treat -1 as "unverified", NOT as failure, so an older firmware that
   * lacks the property cannot brick a working machine. Issue #43.
   */
  int getProcedureResult();

  /**
   * Dump axis0.procedure_result / active_errors / disarm_reason to serial.
   * MUST be called before any clearErrors(). Issue #43.
   */
  void reportFault(const char* context);

  /**
   * Command IDLE and verify the axis actually reached it, re-issuing the
   * request (ASCII writes are unacknowledged). Called on every failure exit
   * so a bailing routine never leaves the ODrive executing a procedure —
   * e.g. still rotating in ENCODER_INDEX_SEARCH. Issue #41.
   * Returns true if IDLE was confirmed within timeout_ms.
   */
  bool forceIdle(uint16_t timeout_ms = 3000);

  /**
   * Emergency stop: request ODrive IDLE (disarm → freewheel).
   * Fire-and-forget by design — callable from kill(), where blocking on a
   * reply is not allowed. Never calls idle()/safe_delay: kill() is reached
   * from idle(), so re-entering idle() here would recurse. Run before
   * minkill()'s cli() so TX drains promptly (the AVR core self-polls if
   * interrupts are off, so even a late call completes).
   * Freewheel was chosen over commanded decel: no confirmed brake resistor,
   * so regen from a high-RPM chuck could overvolt the DC bus (issue #40).
   */
  void emergencyStop();

  /**
   * Startup safety disarm, called once from setup(): if the Mega was reset
   * mid-spin (host reconnect DTR, watchdog, power blip), the ODrive keeps
   * spinning at the last commanded velocity. Request IDLE so a reboot never
   * leaves the rotor running unattended (issue #40).
   */
  void startupSafetyDisarm();

  /**
   * Enter closed-loop control, running full calibration if needed.
   * Calls idle() internally. Returns true on success.
   */
  bool ensureClosedLoop();

  /**
    * Encoder index search with trapezoidal settle back to the saved home datum.
   * Does NOT reset the home datum (homePos).
   * Calls idle() internally. Returns true on success.
   */
  bool doIndexHome();

  /**
   * Set current encoder position as 0° datum.
   * Returns true on success.
   */
  bool doSetHome();

  /**
   * Get current absolute degrees from home datum, normalized to [0, 360).
   */
  float getDegreesFromHome();

  /**
   * Get the home position reference (turns).
   */
  float getHomePos();

  /**
   * True once a real 0° datum has been established (M751, boot, or an adopted
   * fallback). False means getHomePos() is only its 0.0f initial value.
   *
   * A failed doIndexHome() leaves any EXISTING datum untouched, so callers
   * must not re-datum on failure unless this returns false — otherwise a
   * failed home silently re-zeroes the machine on wherever the rotor stopped
   * (typically the index mark, up to a full turn from the operator's datum).
   * Issue #41.
   */
  bool isDatumValid();

} // namespace Spincoater

#endif // SPINCOATER
