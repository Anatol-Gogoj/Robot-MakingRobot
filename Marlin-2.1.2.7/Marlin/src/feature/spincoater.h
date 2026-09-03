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
   */
  bool feedback(float &pos, float &vel);

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
   */
  void clearErrors();

  /**
   * Enter closed-loop control, running full calibration if needed.
   * Calls idle() internally. Returns true on success.
   */
  bool ensureClosedLoop();

  /**
   * Encoder index search with trapezoidal settle back to index mark.
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
   * Cooperative abort flag: set by the M410/quickstop path (temperature.cpp) and
   * polled by M750 so a running spin cycle can be stopped from the UI (sequencer
   * Stop) without a full machine kill. M750 zeroes the rotor and returns.
   */
  extern volatile bool abortRequested;
  void requestAbort();

  /** Stop the rotor, but ONLY if the ODrive was initialised — safe to call from
   * kill(): if no spin ran this session the ODrive serial isn't begun and a
   * setVelocity() would block forever in Serial.flush(). */
  void safeStop();

} // namespace Spincoater

#endif // SPINCOATER
