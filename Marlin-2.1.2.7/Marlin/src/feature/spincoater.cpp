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
    if (vb.length() > 0 && vb.toFloat() > 1.0f) {
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
    // Wait for completion (returns to IDLE)
    bootHomed = true;
    const millis_t homeWait = millis();
    while (getState() != ODRIVE_STATE_IDLE) {
      idle();
      if (millis() - homeWait > 30000) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Index search timeout (30s)");
        bootHomed = false;
        break;
      }
      safe_delay(100);
    }
  } else {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not start index search");
  }

  safe_delay(300);  // let encoder settle

  // ── Trapezoidal settle to index position ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SETTLE_BOOT");

  writeRaw("axis0.controller.config.control_mode", 3.0f);  // POSITION
  writeRaw("axis0.controller.config.input_mode", 5.0f);    // TRAP_TRAJ
  writeRaw("axis0.trap_traj.config.vel_limit", 0.25f);     // 15 RPM
  writeRaw("axis0.trap_traj.config.accel_limit", 0.5f);
  writeRaw("axis0.trap_traj.config.decel_limit", 0.5f);
  safe_delay(10);

  setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);
  safe_delay(100);

  if (getState() == ODRIVE_STATE_CLOSED_LOOP_CONTROL) {
    // Command move to position 0 (index mark)
    while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
    ODRIVE_SERIAL.print("t 0 0.0"); ODRIVE_NEWLINE();
    ODRIVE_SERIAL.flush();

    const millis_t settleStart = millis();
    while (millis() - settleStart < 8000) {
      idle();
      float pos, vel;
      if (feedback(pos, vel)) {
        if (fabs(pos) < 0.003f && fabs(vel) < 0.05f) {
          SERIAL_ECHOPGM("echo:SPIN DATA: BootSettleErr=");
          SERIAL_ECHO(fabs(pos) * 360.0f);
          SERIAL_ECHOLNPGM(" deg");
          break;
        }
      }
      safe_delay(50);
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
  if (feedback(initPos, initVel)) {
    _homePos = initPos;
    // Only a MEANINGFUL reference if the boot index search actually completed.
    // Without it the AMT102 frame is anchored to wherever the rotor happened
    // to sit at ODrive power-up, so initPos is an arbitrary shaft angle and
    // must not masquerade as an operator datum. Issue #41.
    _datumSet = bootHomed;
    SERIAL_ECHOPGM("echo:SPIN DATA: InitialPos=");
    SERIAL_ECHOLN(initPos);
    if (bootHomed)
      SERIAL_ECHOLNPGM("echo:SPIN WARN: datum established at the index mark on boot -- re-run M751 if layer registration matters");
    else
      SERIAL_ECHOLNPGM("echo:SPIN WARN: boot index search did not complete -- no valid datum, run M751 before relying on angles");
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
  while (millis() - t0 < 500) {
    // Bail on M112 so the caller's next idle() can dispatch kill() (issue #40)
    if (TERN0(EMERGENCY_PARSER, emergency_parser.killed_by_M112)) break;
    if (ODRIVE_SERIAL.available()) {
      char c = ODRIVE_SERIAL.read();
      if (c == '\n') break;
      if (c != '\r') response += c;
    }
  }
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
  while (millis() - t0 < 200) {
    // Bail on M112 so the caller's next idle() can dispatch kill() (issue #40)
    if (TERN0(EMERGENCY_PARSER, emergency_parser.killed_by_M112)) break;
    if (ODRIVE_SERIAL.available()) {
      char c = ODRIVE_SERIAL.read();
      if (c == '\n') break;
      if (c != '\r') resp += c;
    }
  }
  resp.trim();

  int sp = resp.indexOf(' ');
  if (sp > 0) {
    pos = resp.substring(0, sp).toFloat();
    vel = resp.substring(sp + 1).toFloat();
    return true;
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
  if (resp.length() > 0) {
    int st = resp.toInt();
    if (st >= 0 && st <= 20) return st;
  }
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
  if (r.length() == 0) return -1;
  for (uint8_t i = 0; i < r.length(); ++i) {
    const char c = r[i];
    const bool sign = (i == 0 && (c == '-' || c == '+'));
    if (!sign && (c < '0' || c > '9')) return -1;   // non-numeric → unverified
  }
  return r.toInt();
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

  // Guard: if the reported position is more than one turn from the datum,
  // the position estimate was not re-referenced by the index search (e.g.
  // multi-turn accumulation left over from a spin cycle). A trap-traj move
  // to _homePos would then crawl for thousands of turns at vel_limit and be
  // killed mid-move by the 8s settle watchdog. Refuse it and fail loudly
  // so the caller's fallback can run without commanding a doomed move.
  {
    float guard_pos, guard_vel;
    if (feedback(guard_pos, guard_vel) && fabs(guard_pos - _homePos) > 1.0f) {
      SERIAL_ECHOPGM("echo:SPIN ERR: Position ");
      SERIAL_ECHO(guard_pos);
      SERIAL_ECHOPGM(" is >1 turn from home datum ");
      SERIAL_ECHO(_homePos);
      SERIAL_ECHOLNPGM(" -- refusing settle (encoder not index-referenced?)");
      // This condition latches: nothing re-normalises _homePos into the
      // current encoder frame automatically (that used to happen only by
      // silently destroying the operator's datum). Tell them the way out.
      SERIAL_ECHOLNPGM("echo:SPIN WARN: datum lies >1 turn outside the current encoder frame -- run M751 (Set Home) to re-establish it");
      forceIdle();
      return false;
    }
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
    float fallback_pos, fallback_vel;
    if (_datumSet) {
      if (feedback(fallback_pos, fallback_vel)) {
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
    else if (!feedback(fallback_pos, fallback_vel)) {
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

  // Try up to 5 times to read position
  String resp = "";
  for (int attempt = 0; attempt < 5; attempt++) {
    while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
    ODRIVE_SERIAL.print("f 0"); ODRIVE_NEWLINE();
    ODRIVE_SERIAL.flush();

    const millis_t t0 = millis();
    resp = "";
    while (millis() - t0 < 300) {
      // Bail on M112 so the caller's next idle() can dispatch kill() (issue #40)
      if (TERN0(EMERGENCY_PARSER, emergency_parser.killed_by_M112)) break;
      if (ODRIVE_SERIAL.available()) {
        char c = ODRIVE_SERIAL.read();
        if (c == '\n') break;
        if (c != '\r') resp += c;
      }
    }
    resp.trim();
    if (resp.indexOf(' ') > 0) break;
    safe_delay(200);
  }

  int sp = resp.indexOf(' ');
  if (sp > 0) {
    float pos = resp.substring(0, sp).toFloat();
    float vel = resp.substring(sp + 1).toFloat();

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

  SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not read ODrive position");
  return false;
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
