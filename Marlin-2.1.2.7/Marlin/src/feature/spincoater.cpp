/**
 * spincoater.cpp — ODrive S1 raw ASCII communication layer
 *
 * Direct port of SpincoaterStage/src/main.cpp v2.6 ODrive wrappers.
 * All Serial1 calls → SPINCOATER_SERIAL, all Serial.print → Marlin serial macros.
 *
 * IMPORTANT: Every cycle-level blocking loop calls idle()/safe_delay() to
 * feed the watchdog, dispatch M112, and emit HOST_KEEPALIVE busy messages.
 * The short reply-wait loops (<= 500 ms) instead poll
 * emergency_parser.killed_by_M112 directly and bail out early so the
 * caller's next idle() can dispatch the kill.
 */

#include "../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "spincoater.h"
#include "../MarlinCore.h"       // idle()

#if ENABLED(EMERGENCY_PARSER)
  #include "e_parser.h"          // emergency_parser.killed_by_M112
#endif

#include <limits.h>              // INT_MAX / INT_MIN for strict int parsing

// Shorthand for the ODrive serial port
#define ODRIVE_SERIAL SPINCOATER_SERIAL

// AVR println() sends \r\n but ODrive ASCII protocol expects bare \n.
// This helper sends just \n after a print().
#define ODRIVE_NEWLINE() ODRIVE_SERIAL.write('\n')

// Module state
static bool     _initialized = false;
static bool     _ready       = false;
static float    _homePos     = 0.0f;   // encoder position (turns) at last home datum
// True once a real datum has been established (M751, boot, or an adopted
// fallback). While false, _homePos is just its 0.0f initial value and is not a
// meaningful reference. Callers use this to decide whether a failed home may
// re-datum: an existing operator-set datum must never be silently overwritten
// by whatever position a failed home happened to stop at. Issue #41.
static bool     _datumSet    = false;

// ═══════════════════════════════════════════════════════════════════════════
//  Strict numeric parsing  (issue #44)
//
//  Arduino's String::toFloat()/toInt() silently return 0 for non-numeric
//  text, and the only gate on an "f 0" reply used to be "contains a space".
//  One corrupted byte therefore produced a perfectly plausible pos=0/vel=0
//  reading — and this machine has documented stepper-EMI history while the
//  ODrive ASCII protocol carries no checksum, so application-level validation
//  is the only defence. Reject anything that is not a complete, well-formed
//  number rather than laundering it into a zero.
// ═══════════════════════════════════════════════════════════════════════════

static bool parseStrictFloat(const String &s, float &out) {
  const unsigned int len = s.length();
  if (len == 0) return false;
  unsigned int i = (s[0] == '+' || s[0] == '-') ? 1 : 0;
  bool digits = false, dot = false, expSeen = false;
  for (; i < len; ++i) {
    const char c = s[i];
    if (c >= '0' && c <= '9') { digits = true; continue; }
    if (c == '.' && !dot && !expSeen) { dot = true; continue; }
    if ((c == 'e' || c == 'E') && digits && !expSeen) {
      expSeen = true;
      digits  = false;                      // exponent needs its own digits
      if (i + 1 < len && (s[i + 1] == '+' || s[i + 1] == '-')) ++i;
      continue;
    }
    return false;                           // any other character invalidates
  }
  if (!digits) return false;
  out = s.toFloat();
  return true;
}

static bool parseStrictInt(const String &s, int &out) {
  const unsigned int len = s.length();
  if (len == 0 || len > 11) return false;      // 11 = sign + 10 digits (long)
  unsigned int i = (s[0] == '+' || s[0] == '-') ? 1 : 0;
  if (i >= len) return false;
  for (; i < len; ++i) if (s[i] < '0' || s[i] > '9') return false;

  // Range-check before narrowing. int is 16-bit on AVR, so without this a
  // corrupted all-digit reply could wrap into a valid-looking axis state, or
  // into procedure_result == 0 (SUCCESS). Issue #44.
  const long v = s.toInt();
  if (v > (long)INT_MAX || v < (long)INT_MIN) return false;
  out = (int)v;
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Init / Boot
// ═══════════════════════════════════════════════════════════════════════════

void Spincoater::init() {
  if (_initialized) return;
  ODRIVE_SERIAL.begin(SPINCOATER_BAUD);
  _initialized = true;
}

void Spincoater::emergencyStop() {
  init();
  // Request IDLE twice — the ASCII link has no acknowledgements, so a single
  // write can be lost. No replies are read and no idle()/safe_delay is called:
  // this must be safe from inside kill() (see spincoater.h).
  for (uint8_t i = 0; i < 2; ++i) {
    ODRIVE_SERIAL.print("w axis0.requested_state ");
    ODRIVE_SERIAL.print(ODRIVE_STATE_IDLE);
    ODRIVE_NEWLINE();
    ODRIVE_SERIAL.flush();  // Blocks (~2.3 ms) until TX complete. The AVR core
                            // self-polls if interrupts are off, but run this
                            // before minkill()'s cli() so TX drains promptly.
  }
}

void Spincoater::startupSafetyDisarm() {
  emergencyStop();
}

bool Spincoater::boot() {
  init();

  // Flush any stale data from previous session / brown-out
  ODRIVE_SERIAL.print(""); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();
  safe_delay(50);
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();

  // ── Probe ODrive UART (15s timeout) ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:WAITING_ODRIVE");
  const millis_t bootStart = millis();
  bool odriveFound = false;
  while (millis() - bootStart < 15000) {
    idle();
    String vb = readRaw("vbus_voltage");
    float vbv;
    // Strict parse: a garbled reply must not be accepted as a live ODrive.
    // Issue #44.
    if (parseStrictFloat(vb, vbv) && vbv > 1.0f) {
      SERIAL_ECHOPGM("echo:SPIN DATA: Vbus=");
      SERIAL_ECHO(vb.c_str());
      SERIAL_ECHOLNPGM("V");
      odriveFound = true;
      break;
    }
    safe_delay(500);
  }

  if (!odriveFound) {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive not detected (15s timeout)");
    _ready = false;
    return false;
  }

  // ── Auto encoder index search ──
  // AMT102 incremental encoder loses position on power cycle.
  SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SEARCH_BOOT");

  clearErrors();
  setState(ODRIVE_STATE_IDLE);
  safe_delay(200);

  setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);

  // Wait for search to start
  const millis_t searchStart = millis();
  bool searching = false;
  while (millis() - searchStart < 5000) {
    idle();
    const int st = getState();
    if (st == ODRIVE_STATE_ENCODER_INDEX_SEARCH) {
      searching = true;
      SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - searchStart > 1000 && st == ODRIVE_STATE_IDLE) {
      clearErrors();
      setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);
    }
    safe_delay(50);
  }

  bool bootHomed = false;
  if (searching) {
    bool reachedIdle = false;
    const millis_t homeWait = millis();
    while (millis() - homeWait < 30000) {
      idle();
      if (getState() == ODRIVE_STATE_IDLE) { reachedIdle = true; break; }
      safe_delay(100);
    }

    if (!reachedIdle) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Index search timeout (30s)");
      forceIdle();
    }
    else {
      // Reaching IDLE proves NOTHING. The axis returns to IDLE after both
      // success and failure; procedure_result is the only discriminator.
      // This is the #43 trap. doIndexHome() was hardened against it in
      // PR #56 and boot() was not.
      //
      // Observed 2026-08-13: a floating thermistor input disarmed the axis
      // mid-search, the axis duly returned to IDLE, and boot() announced
      // "datum established at the index mark" over a search that never
      // happened. Issue #69.
      const int pr = getProcedureResult();
      if (pr == 0) {
        bootHomed = true;
      }
      else if (pr < 0) {
        // Unreadable means UNVERIFIED, not failed: an ODrive firmware
        // lacking the property must not brick a working machine.
        // HANDOFF decision 7.
        SERIAL_ECHOLNPGM("echo:SPIN WARN: procedure_result unreadable -- boot index search UNVERIFIED");
        bootHomed = true;
      }
      else {
        SERIAL_ECHOPGM("echo:SPIN ERR: Boot index search failed, procedure_result=");
        SERIAL_ECHOLN(pr);
        reportFault("boot index search procedure_result != 0");
        forceIdle();
      }
    }
  } else {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not start index search");
  }

  safe_delay(300);  // let encoder settle

  // ── Trapezoidal settle to the nearest index-equivalent position ──
  bool bootSettled = false;
  if (bootHomed) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SETTLE_BOOT");

    writeRaw("axis0.controller.config.control_mode", 3.0f);  // POSITION
    writeRaw("axis0.controller.config.input_mode", 5.0f);    // TRAP_TRAJ
    writeRaw("axis0.trap_traj.config.vel_limit", 0.25f);     // 15 RPM
    writeRaw("axis0.trap_traj.config.accel_limit", 0.5f);
    writeRaw("axis0.trap_traj.config.decel_limit", 0.5f);
    safe_delay(10);

    setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);

    // Bounded arm poll WITH an else. Previously a single sample 100 ms after
    // the request and no failure branch, so a refused arm silently skipped
    // the entire settle and boot() still declared a datum. Same shape as the
    // bug PR #56 fixed in doIndexHome(). Issue #69.
    bool armed = false;
    const millis_t armStart = millis();
    while (millis() - armStart < 2000) {
      idle();
      if (getState() == ODRIVE_STATE_CLOSED_LOOP_CONTROL) { armed = true; break; }
      safe_delay(50);
    }

    if (!armed) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not arm for boot settle -- no datum established");
      reportFault("closed-loop arm refused before boot settle");
      forceIdle();
    }
    else {
      // Target the NEAREST index-equivalent position, not absolute zero.
      // The index search references position modulo one turn, and
      // pos_estimate keeps accumulating turns (issue #55). After a spin the
      // rotor can sit hundreds of turns from zero, so 't 0 0.0' would command
      // a move of that many turns at vel_limit 0.25 turns/s -- minutes of
      // crawling, guaranteed to be cut off by the 8 s watchdog below.
      // With index_offset 0.0 the index marks sit at integer positions, so
      // the nearest one is simply roundf(current).
      float p0, v0;
      float target = 0.0f;
      if (feedbackStable(p0, v0)) target = roundf(p0);

      while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
      ODRIVE_SERIAL.print("t 0 "); ODRIVE_SERIAL.print(target, 4); ODRIVE_NEWLINE();
      ODRIVE_SERIAL.flush();

      const millis_t settleStart = millis();
      while (millis() - settleStart < 8000) {
        idle();
        float pos, vel;
        if (feedback(pos, vel)) {
          if (fabs(pos - target) < 0.003f && fabs(vel) < 0.05f) {
            bootSettled = true;
            SERIAL_ECHOPGM("echo:SPIN DATA: BootSettleErr=");
            SERIAL_ECHO(fabs(pos - target) * 360.0f);
            SERIAL_ECHOLNPGM(" deg");
            break;
          }
        }
        safe_delay(50);
      }

      // The 8 s timeout previously had no else at all: a settle that never
      // converged fell straight through to "datum established". Issue #69.
      if (!bootSettled)
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Boot settle did not converge in 8s -- no datum established");
    }
  }

  // Return to IDLE, restore velocity control mode
  setState(ODRIVE_STATE_IDLE);
  safe_delay(100);
  writeRaw("axis0.controller.config.control_mode", 2.0f);  // VELOCITY
  writeRaw("axis0.controller.config.input_mode", 2.0f);    // VEL_RAMP
  safe_delay(10);

  // Read initial position
  float initPos, initVel;
  // Stable read — this writes the datum. Issue #44.
  if (feedbackStable(initPos, initVel)) {
    _homePos = initPos;
    // A datum is meaningful only if the index search completed AND the rotor
    // actually reached the index mark. Either alone is not enough: without
    // the search the AMT102 frame is anchored to wherever the rotor sat at
    // ODrive power-up (#41), and without the settle the rotor is parked at
    // an arbitrary angle no matter how good the reference is (#69).
    _datumSet = bootHomed && bootSettled;
    SERIAL_ECHOPGM("echo:SPIN DATA: InitialPos=");
    SERIAL_ECHOLN(initPos);
    if (_datumSet)
      SERIAL_ECHOLNPGM("echo:SPIN WARN: datum established at the index mark on boot -- re-run M751 if layer registration matters");
    else if (bootHomed)
      SERIAL_ECHOLNPGM("echo:SPIN WARN: boot settle did not reach the index mark -- no valid datum, run M751 before relying on angles");
    else
      SERIAL_ECHOLNPGM("echo:SPIN WARN: boot index search did not complete -- no valid datum, run M751 before relying on angles");
  }
  else {
    // Never leave a stale datum behind a failed read, and never let OK: READY
    // be the only thing the operator sees when no datum was captured.
    _datumSet = false;
    SERIAL_ECHOLNPGM("echo:SPIN WARN: could not read a consistent initial position -- no datum, run M751 before relying on angles");
  }

  SERIAL_ECHOLNPGM("echo:SPIN OK: READY");
  _ready = true;
  return true;
}

bool Spincoater::isReady() { return _ready; }

// ═══════════════════════════════════════════════════════════════════════════
//  Raw ASCII ODrive communication
// ═══════════════════════════════════════════════════════════════════════════

String Spincoater::readRaw(const char* property) {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();  // drain stale

  ODRIVE_SERIAL.print("r ");
  ODRIVE_SERIAL.print(property); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();

  const millis_t t0 = millis();
  String response = "";
  bool gotLine = false;
  while (millis() - t0 < 500) {
    // Bail on M112 so the caller's next idle() can dispatch kill() (issue #40)
    if (TERN0(EMERGENCY_PARSER, emergency_parser.killed_by_M112)) break;
    if (ODRIVE_SERIAL.available()) {
      char c = ODRIVE_SERIAL.read();
      if (c == '\n') { gotLine = true; break; }
      if (c != '\r') response += c;
    }
  }
  // A timeout part-way through a line is a FAILED read, not a short one. The
  // old code returned whatever bytes had arrived, so a truncated reply became
  // a truncated *value*. Issue #44.
  if (!gotLine) return "";

  response.trim();
  return response;
}

void Spincoater::writeRaw(const char* property, float value) {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("w ");
  ODRIVE_SERIAL.print(property);
  ODRIVE_SERIAL.print(" ");
  ODRIVE_SERIAL.print(value, 4); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();
}

bool Spincoater::feedback(float &pos, float &vel) {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("f 0"); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();

  const millis_t t0 = millis();
  String resp = "";
  bool gotLine = false;
  while (millis() - t0 < 200) {
    // Bail on M112 so the caller's next idle() can dispatch kill() (issue #40)
    if (TERN0(EMERGENCY_PARSER, emergency_parser.killed_by_M112)) break;
    if (ODRIVE_SERIAL.available()) {
      char c = ODRIVE_SERIAL.read();
      if (c == '\n') { gotLine = true; break; }
      if (c != '\r') resp += c;
    }
  }
  if (!gotLine) return false;          // truncated reply is a failed read

  resp.trim();
  const int sp = resp.indexOf(' ');
  if (sp <= 0) return false;

  String tokPos = resp.substring(0, sp);   tokPos.trim();
  String tokVel = resp.substring(sp + 1);  tokVel.trim();

  float p, v;
  if (!parseStrictFloat(tokPos, p)) return false;
  if (!parseStrictFloat(tokVel, v)) return false;

  pos = p;
  vel = v;
  return true;
}

bool Spincoater::feedbackStable(float &pos, float &vel) {
  // Two consecutive CONSISTENT reads. Strict parsing rejects malformed lines,
  // but a corrupted line can still be well-formed by chance; requiring two
  // reads to agree makes a one-off corruption harmless for decisions that move
  // the datum or judge whether the rotor has stopped.
  //
  // The agreement window is derived from the MEASURED velocity rather than
  // being a fixed position tolerance. A fixed window is really a stationarity
  // test — at a ~4 ms round trip, 0.01 turns is a hard ~150 RPM ceiling — and
  // these calls happen right after an index search, when the ODrive has
  // disarmed and the chuck is freewheeling well above that. Predicting the
  // expected travel keeps this a pure corruption check that works at any
  // speed: a chance-well-formed corrupt sample disagrees by orders of
  // magnitude, while a smoothly coasting rotor agrees. Issue #44.
  float p1, v1, p2, v2;
  for (uint8_t attempt = 0; attempt < 3; ++attempt) {
    idle();
    const millis_t t1 = millis();
    if (feedback(p1, v1)) {
      const millis_t t2 = millis();
      if (feedback(p2, v2)) {
        const millis_t t3 = millis();
        // Generous span: both round trips, plus a floor for millis() coarseness.
        const float dt     = (float)(t3 - t1) * 0.001f + 0.002f;
        const float posTol = 0.01f + fabs(v1) * dt * 3.0f;   // 3x slack
        const float velTol = 0.05f + fabs(v1) * 0.2f;        // allows decel
        if (fabs(p2 - p1) < posTol && fabs(v2 - v1) < velTol) {
          pos = p2;
          vel = v2;
          return true;
        }
      }
    }
    safe_delay(50);
  }
  return false;
}

void Spincoater::setVelocity(float rps) {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("v 0 ");
  ODRIVE_SERIAL.print(rps, 4);
  ODRIVE_SERIAL.print(" 0"); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();
}

int Spincoater::getState() {
  String resp = readRaw("axis0.current_state");
  int st;
  // Strict parse: a garbled reply must land on UNDEFINED explicitly rather
  // than via toInt()'s silent 0-for-garbage. Issue #44.
  if (parseStrictInt(resp, st) && st >= 0 && st <= 20) return st;
  return ODRIVE_STATE_UNDEFINED;
}

void Spincoater::setState(int state) {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("w axis0.requested_state ");
  ODRIVE_SERIAL.print(state); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();
}

void Spincoater::clearErrors() {
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("sc"); ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();
  safe_delay(50);
  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();  // drain response
}

// ═══════════════════════════════════════════════════════════════════════════
//  Fault introspection and safe shutdown  (issues #41, #43)
// ═══════════════════════════════════════════════════════════════════════════

int Spincoater::getProcedureResult() {
  String r = readRaw("axis0.procedure_result");
  r.trim();
  int v;
  if (!parseStrictInt(r, v)) return -1;   // unreadable/non-numeric → unverified
  return v;
}

void Spincoater::reportFault(const char* context) {
  // Read BEFORE any clearErrors(): "sc" wipes active_errors and disarm_reason.
  SERIAL_ECHOPGM("echo:SPIN ERR: fault @ ");
  SERIAL_ECHOLN(context);

  String pr = readRaw("axis0.procedure_result");
  String ae = readRaw("axis0.active_errors");
  String dr = readRaw("axis0.disarm_reason");

  SERIAL_ECHOPGM("echo:SPIN DATA: procedure_result=");
  if (pr.length()) SERIAL_ECHO(pr.c_str()); else SERIAL_ECHOPGM("<no reply>");
  SERIAL_EOL();
  SERIAL_ECHOPGM("echo:SPIN DATA: active_errors=");
  if (ae.length()) SERIAL_ECHO(ae.c_str()); else SERIAL_ECHOPGM("<no reply>");
  SERIAL_EOL();
  SERIAL_ECHOPGM("echo:SPIN DATA: disarm_reason=");
  if (dr.length()) SERIAL_ECHO(dr.c_str()); else SERIAL_ECHOPGM("<no reply>");
  SERIAL_EOL();
}

bool Spincoater::forceIdle(uint16_t timeout_ms/*=3000*/) {
  setState(ODRIVE_STATE_IDLE);
  const millis_t t0 = millis();
  while (millis() - t0 < timeout_ms) {
    idle();
    if (getState() == ODRIVE_STATE_IDLE) return true;
    setState(ODRIVE_STATE_IDLE);   // re-issue; ASCII writes are unacknowledged
    safe_delay(100);
  }
  SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not confirm ODrive IDLE -- axis may still be executing");
  return false;
}

// Best-effort unwind used by every exit of doIndexHome() after the control
// mode may have been switched to POSITION/TRAP_TRAJ: stop the axis and put
// it back in the velocity mode the rest of the firmware expects.
static void idleAndRestoreVelocityMode() {
  Spincoater::forceIdle();
  Spincoater::writeRaw("axis0.controller.config.control_mode", 2.0f);  // VELOCITY
  Spincoater::writeRaw("axis0.controller.config.input_mode", 2.0f);    // VEL_RAMP
  safe_delay(10);
}

// ═══════════════════════════════════════════════════════════════════════════
//  Enter closed-loop control, calibrating if needed
// ═══════════════════════════════════════════════════════════════════════════

bool Spincoater::ensureClosedLoop() {
  int attempts = 0, calAttempts = 0;
  // Wall-clock bound on the OUTER retry loop. The attempt counter alone was
  // not a real bound once the inner calibration wait could take ~60 s: 50
  // attempts x ~60 s is ~50 minutes of blocked Marlin, indistinguishable from
  // the hang #42 describes. Issue #42.
  const millis_t clStart = millis();
  while (getState() != ODRIVE_STATE_CLOSED_LOOP_CONTROL) {
    idle();
    if (++attempts > 50) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not enter closed loop (50 attempts)");
      forceIdle();
      return false;
    }
    if (millis() - clStart > 90000) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Closed-loop entry timeout (90s)");
      reportFault("closed-loop entry timeout");
      forceIdle();
      return false;
    }

    clearErrors();
    setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);
    safe_delay(100);

    if (getState() == ODRIVE_STATE_IDLE) {
      // A full calibration physically energises and rotates the motor. If one
      // completes and the axis still refuses to arm, that is a hard fault --
      // do not re-run it up to 50 times (the clearErrors() above also wipes
      // the evidence each round). Issue #42.
      if (calAttempts >= 2) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Axis will not arm after 2 full calibrations");
        reportFault("closed-loop refused after full calibration");
        forceIdle();
        return false;
      }
      calAttempts++;
      SERIAL_ECHOLNPGM("echo:SPIN STATE:FULL_CALIBRATION");
      setState(ODRIVE_STATE_FULL_CALIBRATION_SEQUENCE);

      // Bounded wait. This was unbounded: after a comms loss getState()
      // returns ODRIVE_STATE_UNDEFINED forever, which never equals IDLE, so
      // Marlin hung here indefinitely with the watchdog fed by idle() and no
      // error emitted. Motor + encoder calibration takes tens of seconds;
      // 60 s is generous. Issue #42.
      const millis_t calStart = millis();
      while (getState() != ODRIVE_STATE_IDLE) {
        idle();
        if (millis() - calStart > 60000) {
          SERIAL_ECHOLNPGM("echo:SPIN ERR: Full calibration timeout (60s)");
          reportFault("full calibration timeout");
          forceIdle();
          return false;
        }
        safe_delay(100);
      }
    }
  }
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Encoder index search with trapezoidal settle
//  Does NOT reset home datum (_homePos)
// ═══════════════════════════════════════════════════════════════════════════

bool Spincoater::doIndexHome() {
  init();  // ensure serial is up

  SERIAL_ECHOLNPGM("echo:SPIN STATE:HOMING");

  // Verify ODrive responding
  const millis_t t0 = millis();
  while (getState() == ODRIVE_STATE_UNDEFINED) {
    idle();
    if (millis() - t0 > 5000) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive not responding");
      return false;
    }
    safe_delay(100);
  }

  // Step 1: Ensure IDLE (can't go CL → INDEX_SEARCH directly)
  if (getState() != ODRIVE_STATE_IDLE) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:ENTERING_IDLE");
    if (!forceIdle(3000)) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not enter IDLE before index search");
      return false;
    }
    safe_delay(200);
  }

  // Step 2: Command encoder index search
  setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);

  const millis_t transitionStart = millis();
  millis_t extraWindow = 0;         // credit back time spent reporting a fault
  bool enteredSearch = false, faultReported = false;
  while (millis() - transitionStart < 3000 + extraWindow) {
    idle();
    int st = getState();
    if (st == ODRIVE_STATE_ENCODER_INDEX_SEARCH) {
      enteredSearch = true;
      SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - transitionStart > 500 && st == ODRIVE_STATE_IDLE) {
      // Capture why it was refused BEFORE clearErrors() wipes the evidence.
      if (!faultReported) {
        faultReported = true;
        const millis_t snapStart = millis();
        reportFault("index search request refused (axis stayed IDLE)");
        extraWindow += millis() - snapStart;
      }
      clearErrors();
      setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);
    }
    safe_delay(50);
  }

  if (!enteredSearch) {
    // A real index search is a multi-second physical rotation, so this is
    // never "the search completed between polls" — the request was refused.
    // Previously reported as STATE:INDEX_FOUND_INSTANT and treated as
    // success, which is what let a failed home look like a good one. #43.
    SERIAL_ECHOPGM("echo:SPIN ERR: Index search never started, state=");
    SERIAL_ECHOLN(getState());
    if (!faultReported) reportFault("index search never entered state 6");
    forceIdle();
    return false;
  }

  // Wait for completion. The axis returns to IDLE after BOTH a successful and
  // a failed procedure, so reaching IDLE proves nothing on its own —
  // procedure_result is the discriminator, checked immediately below. #43.
  const millis_t homeStart = millis();
  while (getState() != ODRIVE_STATE_IDLE) {
    idle();
    if (millis() - homeStart > 30000) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Index search timeout (30s)");
      reportFault("index search timeout");
      // The axis is STILL executing the search. Stop it before returning, or
      // the caller's fallback will take a datum from a rotating axis. #41.
      forceIdle();
      return false;
    }
    safe_delay(100);
  }

  // Verify the procedure actually succeeded.
  {
    const int pr = getProcedureResult();
    if (pr > 0) {                    // read successfully, and not SUCCESS
      SERIAL_ECHOPGM("echo:SPIN ERR: Index search failed, procedure_result=");
      SERIAL_ECHOLN(pr);
      reportFault("index search procedure_result != 0");
      forceIdle();
      return false;
    }
    if (pr < 0)                      // unreadable → unverified, NOT failed
      SERIAL_ECHOLNPGM("echo:SPIN WARN: Could not read axis0.procedure_result -- index result unverified");
  }

  safe_delay(300);  // encoder settle

  // Bring the datum into the current encoder frame before settling to it.
  {
    float guard_pos, guard_vel;
    // Fail closed: the old form short-circuited, so a failed read SKIPPED the
    // guard entirely and let the doomed move proceed. Issue #44.
    if (!feedbackStable(guard_pos, guard_vel)) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: No stable position read before settle -- refusing to move");
      forceIdle();
      return false;
    }

    // Settling to a datum that does not exist would invent one from wherever
    // the rotor happens to be sitting -- precisely the destructive behaviour
    // issue #41 removed. Refuse instead.
    if (!isDatumValid()) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: No valid home datum -- refusing settle. Run M751 (Set Home).");
      forceIdle();
      return false;
    }

    // The index search references position MODULO ONE TURN. It corrects the
    // fractional position within a revolution and leaves the integer turn
    // count accumulating, because pos_estimate is a continuous multi-turn
    // value (pos_vel_mapper.config.circular == false).
    //
    // Measured on the bench 2026-08-13: two index searches, several hand
    // turns apart, both landed at fractional position 0.38 -- 0.38 and
    // 0.3757, agreeing within 1.8 deg against a measured settle error of
    // 0.86 deg.
    //
    // So an ABSOLUTE multi-turn comparison against the datum is meaningless.
    // fullcode.gcode:36 spins ~833 turns, after which the datum is always
    // hundreds of turns away in absolute terms and a fraction of a turn away
    // in the only sense that matters. The old >1-turn guard therefore refused
    // every post-spin home on a completely healthy machine. Issue #55.
    //
    // Normalise the datum into the current frame by dropping whole turns.
    // This is NOT the destructive auto-re-datuming that #41 removed: the
    // angular meaning is preserved EXACTLY. Only the accumulated turn count
    // changes, and fmod((pos - _homePos) * 360, 360) -- what DEG reports --
    // is invariant under it.
    //
    // Relaxing only the COMPARISON would have been wrong. 't 0 <_homePos>'
    // would still command a trapezoidal move to a position hundreds of turns
    // away at vel_limit 0.25 turns/s: the doomed multi-thousand-turn crawl
    // the original guard existed to prevent. Normalising fixes the comparison
    // AND the target.
    const float whole_turns = roundf(_homePos - guard_pos);
    if (whole_turns != 0.0f) {
      _homePos -= whole_turns;
      SERIAL_ECHOPGM("echo:SPIN DATA: DatumNormalised turns=");
      SERIAL_ECHO((int)whole_turns);
      SERIAL_ECHOPGM(" newHomePos=");
      SERIAL_ECHOLN(_homePos);
    }
    // After this, |_homePos - guard_pos| <= 0.5 by construction, so the
    // settle below is always a sub-turn move.
  }

  // Step 3: Re-enter position mode and return to the saved home datum.
  SERIAL_ECHOLNPGM("echo:SPIN STATE:HOME_SETTLE");

  writeRaw("axis0.controller.config.control_mode", 3.0f);   // POSITION
  writeRaw("axis0.controller.config.input_mode", 5.0f);     // TRAP_TRAJ
  writeRaw("axis0.trap_traj.config.vel_limit", 0.25f);
  writeRaw("axis0.trap_traj.config.accel_limit", 0.5f);
  writeRaw("axis0.trap_traj.config.decel_limit", 0.5f);
  safe_delay(10);

  setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);

  // Bounded poll for arming. This was a single getState() sample taken 100 ms
  // after the request with no else branch: a slow or refused arm silently
  // skipped the entire return-to-datum move and still reported success. #43.
  bool armed = false;
  const millis_t armStart = millis();
  while (millis() - armStart < 2000) {
    idle();
    if (getState() == ODRIVE_STATE_CLOSED_LOOP_CONTROL) { armed = true; break; }
    safe_delay(50);
  }

  if (!armed) {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not enter closed loop -- return to datum skipped");
    reportFault("closed-loop arm refused before settle");
    idleAndRestoreVelocityMode();
    return false;
  }

  bool homed = true;   // gates OK: INDEX_COMPLETE and the return value

  while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
  ODRIVE_SERIAL.print("t 0 ");
  ODRIVE_SERIAL.print(_homePos, 4);
  ODRIVE_NEWLINE();
  ODRIVE_SERIAL.flush();

  const millis_t settleStart = millis();
  bool settled = false;
  while (millis() - settleStart < 8000) {
    idle();
    float pos, vel;
    if (feedback(pos, vel)) {
      if (fabs(pos - _homePos) < 0.003f && fabs(vel) < 0.05f) {
        settled = true;
        SERIAL_ECHOPGM("echo:SPIN DATA: HomeSettleErr=");
        SERIAL_ECHO(fabs(pos - _homePos) * 360.0f);
        SERIAL_ECHOLNPGM(" deg");
        break;
      }
    }
    safe_delay(50);
  }

  if (!settled) {
    SERIAL_ECHOLNPGM("echo:SPIN DATA: HomeSettle timeout (8s)");
    homed = false;   // the axis did not reach the datum — say so

    // An EXISTING datum is never moved by a failed settle. The original
    // VanVersion fallback adopted the stop position unconditionally, which
    // silently re-zeroed the machine on whatever angle the rotor happened to
    // reach — destroying layer-to-layer registration on the most common
    // failure path. A datum is only ESTABLISHED here when none exists yet, so
    // the machine still ends up with a usable reference from a cold start.
    // Refuses a MOVING axis either way: a datum captured mid-rotation is
    // meaningless. Issue #41.
    // Stable read: this branch either writes the datum or reports the miss a
    // bench operator will use to diagnose the settle, so a single corrupted
    // line must not decide either. Issue #44.
    float fallback_pos, fallback_vel;
    const bool haveStable = feedbackStable(fallback_pos, fallback_vel);

    if (_datumSet) {
      if (haveStable) {
        float off = fmod((fallback_pos - _homePos) * 360.0f, 360.0f);
        if (off < 0) off += 360.0f;
        SERIAL_ECHOPGM("echo:SPIN WARN: Settle failed — datum PRESERVED at ");
        SERIAL_ECHO(_homePos);
        SERIAL_ECHOPGM(" turns; rotor stopped ");
        SERIAL_ECHO(off);
        SERIAL_ECHOLNPGM(" deg away");
      }
      else {
        SERIAL_ECHOLNPGM("echo:SPIN WARN: Settle failed — datum PRESERVED (rotor position unreadable)");
      }
    }
    else if (!haveStable) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not read ODrive position after settle failure");
    }
    else if (fabs(fallback_vel) > 0.05f) {
      SERIAL_ECHOPGM("echo:SPIN ERR: Refusing to establish datum, axis still moving at ");
      SERIAL_ECHO(fallback_vel * 60.0f);
      SERIAL_ECHOLNPGM(" RPM");
    }
    else {
      _homePos = fallback_pos;
      _datumSet = true;
      SERIAL_ECHOPGM("echo:SPIN WARN: Settle failed and no datum existed — establishing one at pos=");
      SERIAL_ECHOLN(fallback_pos);
      SERIAL_ECHOLNPGM("echo:SPIN WARN: run M751 to set your intended zero");
    }
  }

  // Return to IDLE, restore velocity mode
  idleAndRestoreVelocityMode();

  // Report position
  float pos, vel;
  if (feedback(pos, vel)) {
    float deg = fmod((pos - _homePos) * 360.0f, 360.0f);
    if (deg < 0) deg += 360.0f;
    SERIAL_ECHOPGM("echo:SPIN TELEM: RPM=");
    SERIAL_ECHO(vel * 60.0f);
    SERIAL_ECHOPGM(" POS=");
    SERIAL_ECHO(pos);
    SERIAL_ECHOPGM(" DEG=");
    SERIAL_ECHOLN(deg);
  }

  if (homed) SERIAL_ECHOLNPGM("echo:SPIN OK: INDEX_COMPLETE");
  else       SERIAL_ECHOLNPGM("echo:SPIN ERR: INDEX_INCOMPLETE -- datum not reached");
  return homed;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Set current position as 0° datum
// ═══════════════════════════════════════════════════════════════════════════

bool Spincoater::doSetHome() {
  init();

  // Setting the datum is the single most consequential read in the subsystem:
  // one bad value silently redefines zero for every layer that follows. Use a
  // stable double-read rather than the bespoke single-shot parse this used to
  // carry (which had the same "space means valid" weakness as feedback()).
  // Issue #44.
  float pos, vel;
  if (!feedbackStable(pos, vel)) {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not obtain a stable ODrive position -- home NOT set");
    return false;
  }

  // Refuse to datum a moving axis. M750's H1 fallback calls this right
  // after a failed index home, where the rotor may still be turning — a
  // datum captured mid-rotation is meaningless. Issue #41.
  if (fabs(vel) > 0.05f) {
    SERIAL_ECHOPGM("echo:SPIN ERR: Refusing to set home, axis moving at ");
    SERIAL_ECHO(vel * 60.0f);
    SERIAL_ECHOLNPGM(" RPM");
    return false;
  }

  _homePos = pos;
  _datumSet = true;

  SERIAL_ECHOPGM("echo:SPIN DATA: HomePos=");
  SERIAL_ECHOLN(pos);

  // Emit telemetry with DEG=0.00
  SERIAL_ECHOPGM("echo:SPIN TELEM: RPM=");
  SERIAL_ECHO(vel * 60.0f);
  SERIAL_ECHOPGM(" POS=");
  SERIAL_ECHO(pos);
  SERIAL_ECHOLNPGM(" DEG=0.00");

  SERIAL_ECHOLNPGM("echo:SPIN OK: HOME_SET");
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Utility getters
// ═══════════════════════════════════════════════════════════════════════════

float Spincoater::getDegreesFromHome() {
  float pos, vel;
  if (feedback(pos, vel)) {
    float deg = fmod((pos - _homePos) * 360.0f, 360.0f);
    if (deg < 0) deg += 360.0f;
    return deg;
  }
  return -1.0f;
}

float Spincoater::getHomePos() { return _homePos; }

bool Spincoater::isDatumValid() { return _datumSet; }

#endif // SPINCOATER
