/**
 * spincoater.cpp — ODrive S1 raw ASCII communication layer
 *
 * Direct port of SpincoaterStage/src/main.cpp v2.6 ODrive wrappers.
 * All Serial1 calls → SPINCOATER_SERIAL, all Serial.print → Marlin serial macros.
 *
 * IMPORTANT: Every blocking loop calls idle() to feed the watchdog,
 * process M112 e-stop, and emit HOST_KEEPALIVE busy messages.
 */

#include "../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "spincoater.h"
#include "../MarlinCore.h"       // idle()

// Shorthand for the ODrive serial port
#define ODRIVE_SERIAL SPINCOATER_SERIAL

// AVR println() sends \r\n but ODrive ASCII protocol expects bare \n.
// This helper sends just \n after a print().
#define ODRIVE_NEWLINE() ODRIVE_SERIAL.write('\n')

// Module state
static bool     _initialized = false;
static bool     _ready       = false;
static float    _homePos     = 0.0f;   // encoder position (turns) at last home datum

// ═══════════════════════════════════════════════════════════════════════════
//  Init / Boot
// ═══════════════════════════════════════════════════════════════════════════

volatile bool Spincoater::abortRequested = false;
void Spincoater::requestAbort() { abortRequested = true; }

void Spincoater::init() {
  if (_initialized) return;
  ODRIVE_SERIAL.begin(SPINCOATER_BAUD);
  _initialized = true;
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

  if (searching) {
    // Wait for completion (returns to IDLE)
    const millis_t homeWait = millis();
    while (getState() != ODRIVE_STATE_IDLE) {
      idle();
      if (millis() - homeWait > 30000) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Index search timeout (30s)");
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
    SERIAL_ECHOPGM("echo:SPIN DATA: InitialPos=");
    SERIAL_ECHOLN(initPos);
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
//  Enter closed-loop control, calibrating if needed
// ═══════════════════════════════════════════════════════════════════════════

bool Spincoater::ensureClosedLoop() {
  int attempts = 0;
  while (getState() != ODRIVE_STATE_CLOSED_LOOP_CONTROL) {
    idle();
    if (++attempts > 50) return false;

    clearErrors();
    setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);
    safe_delay(100);

    if (getState() == ODRIVE_STATE_IDLE) {
      SERIAL_ECHOLNPGM("echo:SPIN STATE:FULL_CALIBRATION");
      setState(ODRIVE_STATE_FULL_CALIBRATION_SEQUENCE);
      while (getState() != ODRIVE_STATE_IDLE) {
        idle();
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
  int currentState = getState();
  if (currentState != ODRIVE_STATE_IDLE) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:ENTERING_IDLE");
    setState(ODRIVE_STATE_IDLE);

    const millis_t idleStart = millis();
    while (getState() != ODRIVE_STATE_IDLE) {
      idle();
      if (millis() - idleStart > 3000) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Could not enter IDLE");
        return false;
      }
      safe_delay(50);
    }
    safe_delay(200);
  }

  // Step 2: Command encoder index search
  setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);

  const millis_t transitionStart = millis();
  bool enteredSearch = false;
  while (millis() - transitionStart < 3000) {
    idle();
    int st = getState();
    if (st == ODRIVE_STATE_ENCODER_INDEX_SEARCH) {
      enteredSearch = true;
      SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - transitionStart > 500 && st == ODRIVE_STATE_IDLE) {
      clearErrors();
      setState(ODRIVE_STATE_ENCODER_INDEX_SEARCH);
    }
    safe_delay(50);
  }

  if (!enteredSearch) {
    int st = getState();
    if (st == ODRIVE_STATE_IDLE) {
      SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_FOUND_INSTANT");
    } else {
      SERIAL_ECHOPGM("echo:SPIN ERR: Stuck in state=");
      SERIAL_ECHOLN(st);
      return false;
    }
  } else {
    // Wait for completion
    const millis_t homeStart = millis();
    while (getState() != ODRIVE_STATE_IDLE) {
      idle();
      if (millis() - homeStart > 30000) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: Homing timeout (30s)");
        return false;
      }
      safe_delay(100);
    }
  }

  safe_delay(300);  // encoder settle

  // Step 3: Trapezoidal return to index position
  SERIAL_ECHOLNPGM("echo:SPIN STATE:INDEX_SETTLE");

  writeRaw("axis0.controller.config.control_mode", 3.0f);   // POSITION
  writeRaw("axis0.controller.config.input_mode", 5.0f);     // TRAP_TRAJ
  writeRaw("axis0.trap_traj.config.vel_limit", 0.25f);
  writeRaw("axis0.trap_traj.config.accel_limit", 0.5f);
  writeRaw("axis0.trap_traj.config.decel_limit", 0.5f);
  safe_delay(10);

  setState(ODRIVE_STATE_CLOSED_LOOP_CONTROL);
  safe_delay(100);

  if (getState() == ODRIVE_STATE_CLOSED_LOOP_CONTROL) {
    while (ODRIVE_SERIAL.available()) ODRIVE_SERIAL.read();
    ODRIVE_SERIAL.print("t 0 0.0"); ODRIVE_NEWLINE();
    ODRIVE_SERIAL.flush();

    const millis_t settleStart = millis();
    bool settled = false;
    while (millis() - settleStart < 8000) {
      idle();
      float pos, vel;
      if (feedback(pos, vel)) {
        if (fabs(pos) < 0.003f && fabs(vel) < 0.05f) {
          settled = true;
          SERIAL_ECHOPGM("echo:SPIN DATA: IndexSettleErr=");
          SERIAL_ECHO(fabs(pos) * 360.0f);
          SERIAL_ECHOLNPGM(" deg");
          break;
        }
      }
      safe_delay(50);
    }
    if (!settled) {
      SERIAL_ECHOLNPGM("echo:SPIN DATA: IndexSettle timeout (8s)");
    }
  }

  // Return to IDLE, restore velocity mode
  setState(ODRIVE_STATE_IDLE);
  safe_delay(100);
  writeRaw("axis0.controller.config.control_mode", 2.0f);
  writeRaw("axis0.controller.config.input_mode", 2.0f);
  safe_delay(10);

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

  SERIAL_ECHOLNPGM("echo:SPIN OK: INDEX_COMPLETE");
  return true;
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
    _homePos = pos;

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

#endif // SPINCOATER
