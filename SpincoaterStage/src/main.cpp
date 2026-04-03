/**
 * SpincoaterStage — Arduino Nano RP2040 Connect test firmware (v2.6)
 *
 * Drives an ODrive S1 over hardware UART (Serial1) with parameterized
 * spin cycles and real-time telemetry.
 *
 * v2.6 changes:
 *   - Removed ODriveUART library entirely — all communication is raw ASCII.
 *     The library uses property paths (axis0.encoder.vel_estimate, etc.) that
 *     return "invalid property" on ODrive S1, causing serial timeouts that
 *     corrupt the UART buffer and kill telemetry during ramp-down.
 *   - measureSpeed() now uses 'f 0' for Welford sampling (same as telemetry),
 *     eliminating bus contention from dual reads on Serial1.
 *   - All ODrive interactions go through odriveReadRaw(), odriveWriteRaw(),
 *     odriveFeedback(), odriveSetVelocity(), odriveGetState(), odriveSetState(),
 *     odriveClearErrors() — thin wrappers around Serial1 ASCII commands.
 *
 * Hardware (Nano RP2040 Connect):
 *   Nano pin 0  (TX1) ──► ODrive RX  (J11 pin 4, GPIO7)
 *   Nano pin 1  (RX1) ──► ODrive TX  (J11 pin 3, GPIO6)
 *   ODrive ISOVDD/ISOGND ──► Nano 3.3 V / GND
 *
 * Serial protocol (115200 baud, newline-terminated):
 *
 *   SPIN <rpm> <dur_s> <accel> <decel> <home 0|1>
 *   START           — run with current defaults
 *   SET <param> <value>  — RPM, DUR, ACCEL, DECEL, HOME
 *   STATUS          — report params + ODrive state
 *   STOP            — emergency velocity zero (works mid-cycle)
 *   HOME            — encoder index search (does NOT reset degree datum)
 *   SETHOME         — set current position as 0° datum + emit TELEM
 *
 * Telemetry output (every ~200 ms during active phases):
 *   TELEM: RPM=<val> POS=<val> DEG=<val>
 */

#include <Arduino.h>
#include <cmath>

// ── ODrive serial link (raw ASCII, no library) ──
static const unsigned long ODRIVE_BAUD = 115200;

// ODrive axis states (from ODrive firmware — these are stable across versions)
#define AXIS_STATE_UNDEFINED                0
#define AXIS_STATE_IDLE                     1
#define AXIS_STATE_FULL_CALIBRATION_SEQUENCE 3
#define AXIS_STATE_ENCODER_INDEX_SEARCH     6
#define AXIS_STATE_CLOSED_LOOP_CONTROL      8

// ── Default spin parameters (mutable via SET command) ──
static int     cfg_rpm       = 5000;
static int     cfg_duration  = 30;      // seconds
static float   cfg_accel     = 15.0f;   // rev/s²
static float   cfg_decel     = 100.0f;  // rev/s²
static bool    cfg_home      = true;    // encoder index search after spin

// ── Telemetry ──
static const unsigned long TELEM_INTERVAL = 200;  // ms
static unsigned long lastTelem = 0;

// ── Runtime state ──
static bool    running       = false;
static bool    stopRequested = false;
static float   lastTelemRPM  = 0.0f;   // cached from last telemetry read
static float   homePos       = 0.0f;   // encoder pos at last home (turns)

// ── Forward declarations ──
void handleCommand(const String& cmd);
void runCycle(int rpm, int dur_s, float accel, float decel, bool home);
void measureSpeed(int dur_s);
bool doHome();
void doSetHome();
bool ensureClosedLoop();
void reportStatus();
void readEncoderPosition();
void sendTelemetry();
void sendTelemNow();
void checkStop();

// Raw ASCII ODrive communication (no library)
String odriveReadRaw(const char* property);
void   odriveWriteRaw(const char* property, float value);
bool   odriveFeedback(float &pos, float &vel);
void   odriveSetVelocity(float rps);
int    odriveGetState();
void   odriveSetState(int state);
void   odriveClearErrors();

void sendState(const char* msg);
void sendOK(const char* msg);
void sendErr(const char* msg);

// ═══════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial1.begin(ODRIVE_BAUD);

  while (!Serial) { delay(10); }

  Serial.println("SpincoaterStage v2.5 [Nano RP2040]");
  Serial.println("Commands: SPIN, START, SET, STATUS, STOP, HOME, SETHOME");

  // ── Wait for ODrive UART to come alive ──
  // The ODrive S1 takes several seconds to boot after power-on.
  // Poll with raw 'r vbus_voltage' (works even before encoder cal).
  sendState("WAITING_ODRIVE");
  unsigned long bootStart = millis();
  bool odriveReady = false;
  while (millis() - bootStart < 10000) {  // 10s timeout
    String vb = odriveReadRaw("vbus_voltage");
    if (vb.length() > 0 && vb.toFloat() > 1.0f) {
      Serial.print("DATA: Vbus="); Serial.print(vb); Serial.println("V");
      odriveReady = true;
      break;
    }
    delay(500);
  }

  if (!odriveReady) {
    sendErr("ODrive not detected on UART — check wiring and power");
    sendOK("READY_NO_ODRIVE");
    return;  // skip index search, let user debug
  }

  // ── Auto encoder index search ──
  // The AMT102 incremental encoder loses position on power cycle.
  // The ODrive MUST run an index search before it can enter closed-loop
  // control or return valid encoder readings.
  sendState("INDEX_SEARCH_BOOT");
  Serial.println("DATA: Auto index search (required after every power cycle)");

  // Ensure IDLE first
  odriveClearErrors();
  odriveSetState(AXIS_STATE_IDLE);
  delay(200);

  odriveSetState(AXIS_STATE_ENCODER_INDEX_SEARCH);

  // Wait for search to start
  unsigned long searchStart = millis();
  bool searching = false;
  while (millis() - searchStart < 5000) {
    int st = odriveGetState();
    if (st == AXIS_STATE_ENCODER_INDEX_SEARCH) {
      searching = true;
      sendState("INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - searchStart > 1000 && st == AXIS_STATE_IDLE) {
      // Retry — might need error clear
      odriveClearErrors();
      odriveSetState(AXIS_STATE_ENCODER_INDEX_SEARCH);
    }
    delay(50);
  }

  if (searching) {
    // Wait for completion (returns to IDLE)
    unsigned long homeWait = millis();
    while (odriveGetState() != AXIS_STATE_IDLE) {
      if (millis() - homeWait > 30000) {
        sendErr("Index search timeout (30s) — encoder may need attention");
        break;
      }
      delay(100);
    }
  } else {
    sendErr("Could not start index search — ODrive may need full calibration");
  }

  delay(300);  // let encoder settle

  // ── Return precisely to index position (same as doHome settle) ──
  // Use trapezoidal trajectory mode so the return is slow and gentle
  // instead of a violent snap from the position PID.
  sendState("INDEX_SETTLE_BOOT");
  odriveWriteRaw("axis0.controller.config.control_mode", 3.0f);  // POSITION
  odriveWriteRaw("axis0.controller.config.input_mode", 5.0f);    // TRAP_TRAJ
  odriveWriteRaw("axis0.trap_traj.config.vel_limit", 0.25f);     // 0.25 rev/s = 15 RPM
  odriveWriteRaw("axis0.trap_traj.config.accel_limit", 0.5f);    // rev/s²
  odriveWriteRaw("axis0.trap_traj.config.decel_limit", 0.5f);    // rev/s²
  delay(10);
  odriveSetState(AXIS_STATE_CLOSED_LOOP_CONTROL);
  delay(100);

  if (odriveGetState() == AXIS_STATE_CLOSED_LOOP_CONTROL) {
    // Command move to position 0 (the index mark)
    while (Serial1.available()) Serial1.read();
    Serial1.println("t 0 0.0");
    Serial1.flush();

    unsigned long settleStart = millis();
    while (millis() - settleStart < 8000) {
      float pos, vel;
      if (odriveFeedback(pos, vel)) {
        if (fabs(pos) < 0.003f && fabs(vel) < 0.05f) {
          Serial.print("DATA: BootSettleErr=");
          Serial.print(fabs(pos) * 360.0f, 2);
          Serial.println(" deg");
          break;
        }
      }
      delay(50);
    }
  }

  odriveSetState(AXIS_STATE_IDLE);
  delay(100);
  odriveWriteRaw("axis0.controller.config.control_mode", 2.0f);  // VELOCITY
  odriveWriteRaw("axis0.controller.config.input_mode", 2.0f);    // VEL_RAMP
  delay(10);

  // Read initial position via 'f 0'
  float initPos, initVel;
  if (odriveFeedback(initPos, initVel)) {
    homePos = initPos;
    Serial.print("DATA: InitialPos="); Serial.println(homePos, 4);
  }

  sendOK("READY");
}

// ═══════════════════════════════════════════════════════════════════════════
void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      handleCommand(cmd);
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Send a telemetry line: current RPM and position
//  Rate-limited to TELEM_INTERVAL ms.  Call from tight loops.
// ═══════════════════════════════════════════════════════════════════════════
void sendTelemetry() {
  unsigned long now = millis();
  if (now - lastTelem < TELEM_INTERVAL) return;
  lastTelem = now;

  // Read both velocity and position via raw ASCII to avoid
  // getParameterAsFloat's broken sscanf on RP2040 mbed.
  // Use the ODrive 'f' command which returns both in one shot:
  //   "f <axis>\n"  →  "<pos> <vel>\n"
  // This is a single round-trip instead of two separate reads.

  while (Serial1.available()) Serial1.read();  // drain stale

  Serial1.println("f 0");
  Serial1.flush();

  unsigned long t0 = millis();
  String response = "";
  while (millis() - t0 < 100) {
    if (Serial1.available()) {
      char c = Serial1.read();
      if (c == '\n') break;
      if (c != '\r') response += c;
    }
  }
  response.trim();

  // Parse "pos vel" response
  int spaceIdx = response.indexOf(' ');
  if (spaceIdx > 0) {
    String posStr = response.substring(0, spaceIdx);
    String velStr = response.substring(spaceIdx + 1);
    float pos = posStr.toFloat();
    float vel = velStr.toFloat();
    float rpm = vel * 60.0f;
    lastTelemRPM = rpm;  // cache for decel exit check

    // Compute absolute degrees from home position
    float relTurns = pos - homePos;
    // Normalize to [0, 360)
    float deg = fmod(relTurns * 360.0f, 360.0f);
    if (deg < 0) deg += 360.0f;

    Serial.print("TELEM: RPM=");
    Serial.print(rpm, 1);
    Serial.print(" POS=");
    Serial.print(pos, 4);
    Serial.print(" DEG=");
    Serial.println(deg, 2);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Force-send a telemetry line immediately (bypasses rate limit).
//  Used after homing to push the updated homePos to the dashboard.
// ═══════════════════════════════════════════════════════════════════════════
void sendTelemNow() {
  lastTelem = 0;  // reset rate-limiter
  sendTelemetry();
}

// ═══════════════════════════════════════════════════════════════════════════
//  Poll USB serial for STOP command during blocking loops.
//  Must be called frequently from any long-running loop in runCycle(),
//  measureSpeed(), and doHome().
// ═══════════════════════════════════════════════════════════════════════════
void checkStop() {
  if (stopRequested) return;  // already flagged
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd == "STOP") {
    stopRequested = true;
    odriveSetVelocity(0);
    sendState("EMERGENCY STOP");
  }
  // Ignore all other commands mid-cycle — they'll get ERR after cycle ends
}

// ═══════════════════════════════════════════════════════════════════════════
//  Command parser
// ═══════════════════════════════════════════════════════════════════════════
void handleCommand(const String& cmd) {

  if (cmd == "STOP") {
    stopRequested = true;
    odriveSetVelocity(0);
    sendState("EMERGENCY STOP");
    return;
  }

  if (running && cmd != "STOP") {
    sendErr("Cycle in progress. Send STOP to abort.");
    return;
  }

  // ── SPIN <rpm> <dur> <accel> <decel> <home> ──
  if (cmd.startsWith("SPIN ")) {
    String rest = cmd.substring(5);
    rest.trim();

    String tokens[5];
    int tIdx = 0;
    while (rest.length() > 0 && tIdx < 5) {
      int sp = rest.indexOf(' ');
      if (sp < 0) { tokens[tIdx++] = rest; rest = ""; }
      else { tokens[tIdx++] = rest.substring(0, sp); rest = rest.substring(sp + 1); rest.trim(); }
    }

    if (tIdx == 5) {
      int   rpm   = tokens[0].toInt();
      int   dur   = tokens[1].toInt();
      float accel = tokens[2].toFloat();
      float decel = tokens[3].toFloat();
      int   home  = tokens[4].toInt();
      if (rpm > 0 && dur > 0 && accel > 0 && decel > 0) {
        runCycle(rpm, dur, accel, decel, home != 0);
      } else {
        sendErr("All values must be > 0. Usage: SPIN <rpm> <dur_s> <accel> <decel> <home 0|1>");
      }
    } else {
      sendErr("Need 5 args. Usage: SPIN <rpm> <dur_s> <accel> <decel> <home 0|1>");
    }
    return;
  }

  if (cmd == "START") {
    runCycle(cfg_rpm, cfg_duration, cfg_accel, cfg_decel, cfg_home);
    return;
  }

  // ── SET <param> <value> ──
  if (cmd.startsWith("SET ")) {
    String rest = cmd.substring(4);
    rest.trim();
    int spaceIdx = rest.indexOf(' ');
    if (spaceIdx < 0) {
      sendErr("Usage: SET <RPM|DUR|ACCEL|DECEL|HOME> <value>");
      return;
    }
    String param = rest.substring(0, spaceIdx);
    String valStr = rest.substring(spaceIdx + 1);
    param.toUpperCase();

    if (param == "RPM") {
      int v = valStr.toInt();
      if (v > 0) { cfg_rpm = v; sendOK("RPM set"); }
      else sendErr("RPM must be > 0");
    }
    else if (param == "DUR") {
      int v = valStr.toInt();
      if (v > 0) { cfg_duration = v; sendOK("DUR set"); }
      else sendErr("DUR must be > 0");
    }
    else if (param == "ACCEL") {
      float v = valStr.toFloat();
      if (v > 0) { cfg_accel = v; sendOK("ACCEL set"); }
      else sendErr("ACCEL must be > 0");
    }
    else if (param == "DECEL") {
      float v = valStr.toFloat();
      if (v > 0) { cfg_decel = v; sendOK("DECEL set"); }
      else sendErr("DECEL must be > 0");
    }
    else if (param == "HOME") {
      cfg_home = (valStr.toInt() != 0);
      sendOK(cfg_home ? "HOME enabled" : "HOME disabled");
    }
    else {
      sendErr("Unknown param. Use: RPM, DUR, ACCEL, DECEL, HOME");
    }
    return;
  }

  if (cmd == "STATUS") {
    reportStatus();
    return;
  }

  if (cmd == "HOME") {
    doHome();
    return;
  }

  if (cmd == "SETHOME") {
    doSetHome();
    return;
  }

  // ── DIAG — raw UART diagnostic ──
  if (cmd == "DIAG") {
    Serial.println("DATA: === UART DIAGNOSTIC ===");
    Serial.print("DATA: Serial1 baud="); Serial.println(ODRIVE_BAUD);

    // Drain any stale data
    int stale = 0;
    while (Serial1.available()) { Serial1.read(); stale++; }
    Serial.print("DATA: Stale bytes drained="); Serial.println(stale);

    // Send a simple command and dump raw response
    const char* testCmd = "r vbus_voltage";
    Serial.print("DATA: Sending: '"); Serial.print(testCmd); Serial.println("'");
    Serial1.print("r ");
    Serial1.println("vbus_voltage");
    Serial1.flush();

    // Wait up to 2 seconds, print every byte that comes back
    unsigned long t0 = millis();
    int byteCount = 0;
    Serial.print("DATA: Response bytes: ");
    while (millis() - t0 < 2000) {
      if (Serial1.available()) {
        int b = Serial1.read();
        byteCount++;
        // Print printable chars normally, others as hex
        if (b >= 32 && b < 127) {
          Serial.print((char)b);
        } else if (b == '\n') {
          Serial.print("\\n");
        } else if (b == '\r') {
          Serial.print("\\r");
        } else {
          Serial.print("[0x");
          if (b < 16) Serial.print("0");
          Serial.print(b, HEX);
          Serial.print("]");
        }
        // Stop after newline (complete response)
        if (b == '\n') break;
      }
    }
    Serial.println();
    Serial.print("DATA: Total bytes received="); Serial.println(byteCount);
    Serial.print("DATA: Elapsed ms="); Serial.println(millis() - t0);

    if (byteCount == 0) {
      Serial.println("DATA: >>> NO RESPONSE — check: wiring, ODrive power, UART GPIO config, baud rate");
    }

    Serial.println("DATA: === END DIAGNOSTIC ===");
    return;
  }

  sendErr("Unknown command. Try: SPIN, START, SET, STATUS, STOP, HOME, SETHOME, DIAG");
}

// ═══════════════════════════════════════════════════════════════════════════
//  Read an ODrive property via raw ASCII protocol
// ═══════════════════════════════════════════════════════════════════════════
String odriveReadRaw(const char* property) {
  while (Serial1.available()) Serial1.read();

  Serial1.print("r ");
  Serial1.println(property);
  Serial1.flush();

  unsigned long t0 = millis();
  String response = "";
  while (millis() - t0 < 500) {
    if (Serial1.available()) {
      char c = Serial1.read();
      if (c == '\n') break;
      if (c != '\r') response += c;
    }
  }
  response.trim();
  return response;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Read and report encoder position (does NOT change homePos)
// ═══════════════════════════════════════════════════════════════════════════
void readEncoderPosition() {
  // Use 'f 0' instead of 'r axis0.encoder.pos_estimate' — the latter
  // returns "invalid property" on ODrive S1.
  while (Serial1.available()) Serial1.read();
  Serial1.println("f 0");
  Serial1.flush();

  unsigned long t0 = millis();
  String resp = "";
  while (millis() - t0 < 300) {
    if (Serial1.available()) {
      char c = Serial1.read();
      if (c == '\n') break;
      if (c != '\r') resp += c;
    }
  }
  resp.trim();

  int sp = resp.indexOf(' ');
  if (sp > 0) {
    float pos = resp.substring(0, sp).toFloat();

    Serial.print("DATA: EncoderPos=");
    Serial.println(pos, 4);

    float deg = fmod((pos - homePos) * 360.0f, 360.0f);
    if (deg < 0) deg += 360.0f;
    Serial.print("DATA: DegFromHome=");
    Serial.println(deg, 2);
  } else {
    Serial.println("DATA: EncoderPos=read_error");
  }

  Serial.print("DATA: HomeRef=");
  Serial.println(homePos, 6);
}

// ═══════════════════════════════════════════════════════════════════════════
//  SETHOME — set current encoder position as the 0° datum.
//  This is the user-facing "Set Home" action.
// ═══════════════════════════════════════════════════════════════════════════
void doSetHome() {
  // Try up to 5 times to read ODrive position (handles slow boot)
  String resp = "";
  for (int attempt = 0; attempt < 5; attempt++) {
    while (Serial1.available()) Serial1.read();
    Serial1.println("f 0");
    Serial1.flush();

    unsigned long t0 = millis();
    resp = "";
    while (millis() - t0 < 300) {
      if (Serial1.available()) {
        char c = Serial1.read();
        if (c == '\n') break;
        if (c != '\r') resp += c;
      }
    }
    resp.trim();
    if (resp.indexOf(' ') > 0) break;
    delay(200);
  }

  int sp = resp.indexOf(' ');
  if (sp > 0) {
    float pos = resp.substring(0, sp).toFloat();
    float vel = resp.substring(sp + 1).toFloat();
    homePos = pos;

    Serial.print("DATA: HomePos=");
    Serial.println(pos, 6);

    // Emit TELEM with DEG=0.00
    Serial.print("TELEM: RPM=");
    Serial.print(vel * 60.0f, 1);
    Serial.print(" POS=");
    Serial.print(pos, 4);
    Serial.println(" DEG=0.00");
    lastTelemRPM = vel * 60.0f;
  } else {
    sendErr("Could not read ODrive position");
    return;
  }

  sendOK("HOME_SET");
}

// ═══════════════════════════════════════════════════════════════════════════
//  Report current defaults + ODrive state
// ═══════════════════════════════════════════════════════════════════════════
void reportStatus() {
  Serial.print("DATA: RPM=");      Serial.print(cfg_rpm);
  Serial.print(" DUR=");           Serial.print(cfg_duration);
  Serial.print(" ACCEL=");         Serial.print(cfg_accel, 1);
  Serial.print(" DECEL=");         Serial.print(cfg_decel, 1);
  Serial.print(" HOME=");          Serial.println(cfg_home ? 1 : 0);

  Serial.print("DATA: ODrive state=");
  Serial.println(odriveGetState());

  String vbus = odriveReadRaw("vbus_voltage");
  Serial.print("DATA: Vbus=");
  Serial.print(vbus);
  Serial.println("V");

  float pos, vel;
  if (odriveFeedback(pos, vel)) {
    Serial.print("DATA: Velocity=");
    Serial.print(vel * 60.0f, 1);
    Serial.println(" RPM");
  } else {
    Serial.println("DATA: Velocity=read_error");
  }

  readEncoderPosition();
}

// ═══════════════════════════════════════════════════════════════════════════
//  Full spin cycle — now with telemetry during ramp-up, measure, ramp-down
// ═══════════════════════════════════════════════════════════════════════════
void runCycle(int rpm, int dur_s, float accel, float decel, bool home) {
  running       = true;
  stopRequested = false;
  lastTelem     = 0;  // reset so first telem fires immediately

  Serial.print("OK: Cycle starting — RPM="); Serial.print(rpm);
  Serial.print(" DUR=");   Serial.print(dur_s);
  Serial.print("s ACCEL="); Serial.print(accel, 1);
  Serial.print(" DECEL="); Serial.print(decel, 1);
  Serial.print(" HOME=");  Serial.println(home ? "ON" : "OFF");

  // ── Connect to ODrive ──
  sendState("CONNECTING");
  unsigned long t0 = millis();
  while (odriveGetState() == AXIS_STATE_UNDEFINED) {
    if (millis() - t0 > 5000) {
      sendErr("ODrive not responding (5 s timeout)");
      running = false;
      return;
    }
    delay(100);
  }
  sendState("ODRIVE_FOUND");

  String vbus = odriveReadRaw("vbus_voltage");
  Serial.print("DATA: Vbus="); Serial.print(vbus); Serial.println("V");

  // ── Enter closed-loop ──
  sendState("CALIBRATING");
  if (!ensureClosedLoop()) {
    sendErr("Failed to enter closed-loop control");
    running = false;
    return;
  }
  sendState("CLOSED_LOOP");

  if (stopRequested) { sendState("ABORTED"); running = false; return; }

  // ── Ramp up (with telemetry) ──
  sendState("RAMP_UP");
  Serial1.print("w axis0.controller.config.vel_ramp_rate ");
  Serial1.println(accel, 1);
  Serial1.flush();
  delay(10);

  float targetRPS = (float)(rpm + 10) / 60.0f;
  float threshRPM = (float)rpm * 0.98f;
  odriveSetVelocity(targetRPS);

  // Ramp-up: use telemetry's cached RPM for exit check (avoids
  // conflicting serial reads on the ODrive UART).
  // Safety: abort if RPM plateaus (motor can't reach target) or
  // if ramp takes longer than expected + generous margin.
  lastTelemRPM = 0;
  float stallRPM = 0;                       // RPM at last stall-check
  unsigned long stallCheck = millis();       // timestamp of last stall-check
  unsigned long rampStart  = millis();
  // Expected ramp time = targetRPS / accel, with 3x margin + 10s floor
  float expectedSec = targetRPS / accel;
  unsigned long rampTimeout = (unsigned long)(expectedSec * 3000.0f);
  if (rampTimeout < 10000) rampTimeout = 10000;

  while (lastTelemRPM < threshRPM) {
    checkStop();
    if (stopRequested) { sendState("ABORTED"); running = false; return; }
    sendTelemetry();

    // Hard timeout
    if (millis() - rampStart > rampTimeout) {
      Serial.print("ERR: Ramp-up timeout ("); Serial.print(rampTimeout / 1000);
      Serial.print("s) — reached "); Serial.print(lastTelemRPM, 0);
      Serial.print(" of "); Serial.print(threshRPM, 0); Serial.println(" RPM");
      sendState("RAMP_TIMEOUT");
      odriveSetVelocity(0);
      running = false;
      return;
    }

    // Stall detection: if RPM hasn't increased by >50 in last 3s, motor
    // is at its limit and can't reach the target.
    if (millis() - stallCheck > 3000) {
      if (lastTelemRPM > 100 && (lastTelemRPM - stallRPM) < 50.0f) {
        Serial.print("ERR: RPM stalled at "); Serial.print(lastTelemRPM, 0);
        Serial.print(" — target "); Serial.print(threshRPM, 0);
        Serial.println(" RPM unreachable");
        sendState("RAMP_STALL");
        odriveSetVelocity(0);
        running = false;
        return;
      }
      stallRPM = lastTelemRPM;
      stallCheck = millis();
    }

    delay(20);
  }

  // ── Measure (telemetry integrated into Welford loop) ──
  sendState("MEASURING");
  measureSpeed(dur_s);

  if (stopRequested) { sendState("ABORTED"); running = false; return; }

  // ── Ramp down (with telemetry) ──
  sendState("RAMP_DOWN");
  Serial1.print("w axis0.controller.config.vel_ramp_rate ");
  Serial1.println(decel, 1);
  Serial1.flush();

  odriveSetVelocity(0);

  // Use telemetry's cached RPM for exit (same reason as ramp-up)
  while (abs(lastTelemRPM) > 6.0f) {  // ~0.1 rps = 6 RPM
    checkStop();
    if (stopRequested) { sendState("ABORTED"); running = false; return; }
    sendTelemetry();
    delay(50);
  }
  // Continue telemetry during 1s settling so dashboard stays live
  sendState("SETTLING");
  unsigned long settleStart = millis();
  while (millis() - settleStart < 1000) {
    checkStop();
    if (stopRequested) { sendState("ABORTED"); running = false; return; }
    sendTelemetry();
    delay(50);
  }
  sendState("STOPPED");

  // ── Homing (optional) ──
  if (home && !stopRequested) {
    doHome();
  }

  sendOK("CYCLE_COMPLETE");
  running = false;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Welford's online mean/variance — now also emits telemetry
// ═══════════════════════════════════════════════════════════════════════════
void measureSpeed(int dur_s) {
  const unsigned long sampleInterval = 100;
  const unsigned long duration = (unsigned long)dur_s * 1000UL;

  unsigned long startTime  = millis();
  unsigned long lastSample = startTime;
  long          n          = 0;
  float         mean       = 0.0f;
  float         m2         = 0.0f;
  float         minRPM     = 1e9f;
  float         maxRPM     = -1e9f;

  while (millis() - startTime < duration) {
    checkStop();
    if (stopRequested) return;

    unsigned long now = millis();
    if (now - lastSample >= sampleInterval) {
      lastSample = now;

      // Use 'f 0' for sampling — same command as telemetry.
      // This replaces odrive.getVelocity() which used a broken
      // property path on ODrive S1, causing serial timeouts.
      float pos, vel;
      if (odriveFeedback(pos, vel)) {
        float rpm = vel * 60.0f;
        lastTelemRPM = rpm;  // keep telemetry cache fresh

        n++;
        float delta  = rpm - mean;
        mean        += delta / (float)n;
        float delta2 = rpm - mean;
        m2          += delta * delta2;

        if (rpm < minRPM) minRPM = rpm;
        if (rpm > maxRPM) maxRPM = rpm;

        // Emit telemetry from same read (no second Serial1 round-trip)
        float relTurns = pos - homePos;
        float deg = fmod(relTurns * 360.0f, 360.0f);
        if (deg < 0) deg += 360.0f;

        Serial.print("TELEM: RPM=");
        Serial.print(rpm, 1);
        Serial.print(" POS=");
        Serial.print(pos, 4);
        Serial.print(" DEG=");
        Serial.println(deg, 2);

        lastTelem = millis();  // reset rate limiter
      }
    }
    // No separate sendTelemetry() call — sampling IS the telemetry
    // during measurement, avoiding bus contention on Serial1.
  }

  float variance = (n > 1) ? m2 / (float)n : 0.0f;
  float stddev   = sqrt(variance);

  Serial.print("DATA: Samples=");    Serial.println(n);
  Serial.print("DATA: MeanRPM=");    Serial.println(mean, 3);
  Serial.print("DATA: StdDevRPM=");  Serial.println(stddev, 3);
  Serial.print("DATA: MinRPM=");     Serial.println(minRPM, 3);
  Serial.print("DATA: MaxRPM=");     Serial.println(maxRPM, 3);
  Serial.print("DATA: Range=");      Serial.println(maxRPM - minRPM, 3);
}

// ═══════════════════════════════════════════════════════════════════════════
//  Encoder index search with proper IDLE→SEARCH transition
// ═══════════════════════════════════════════════════════════════════════════
bool doHome() {
  sendState("HOMING");

  // Make sure ODrive is responding
  unsigned long t0 = millis();
  while (odriveGetState() == AXIS_STATE_UNDEFINED) {
    if (millis() - t0 > 5000) {
      sendErr("ODrive not responding");
      return false;
    }
    delay(100);
  }

  // Step 1: Ensure we're in IDLE first (can't go CL → INDEX_SEARCH directly)
  int currentState = odriveGetState();
  if (currentState != AXIS_STATE_IDLE) {
    Serial.print("DATA: PreHomeState="); Serial.println(currentState);
    sendState("ENTERING_IDLE");
    odriveSetState(AXIS_STATE_IDLE);

    unsigned long idleStart = millis();
    while (odriveGetState() != AXIS_STATE_IDLE) {
      if (millis() - idleStart > 3000) {
        sendErr("Could not enter IDLE before homing");
        return false;
      }
      delay(50);
    }
    delay(200);
  }

  // Step 2: Command encoder index search
  odriveSetState(AXIS_STATE_ENCODER_INDEX_SEARCH);

  // Wait for state to transition out of IDLE
  unsigned long transitionStart = millis();
  bool enteredSearch = false;
  while (millis() - transitionStart < 3000) {
    int st = odriveGetState();
    if (st == AXIS_STATE_ENCODER_INDEX_SEARCH) {
      enteredSearch = true;
      sendState("INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - transitionStart > 500 && st == AXIS_STATE_IDLE) {
      odriveClearErrors();
      odriveSetState(AXIS_STATE_ENCODER_INDEX_SEARCH);
    }
    delay(50);
  }

  if (!enteredSearch) {
    int st = odriveGetState();
    if (st == AXIS_STATE_IDLE) {
      sendState("INDEX_FOUND_INSTANT");
    } else {
      Serial.print("ERR: Stuck in state="); Serial.println(st);
      return false;
    }
  } else {
    // Wait for completion (returns to IDLE), with telemetry
    unsigned long homeStart = millis();
    while (odriveGetState() != AXIS_STATE_IDLE) {
      if (millis() - homeStart > 30000) {
        sendErr("Homing timeout (30 s)");
        return false;
      }
      sendTelemetry();
      delay(100);
    }
  }

  delay(300);  // Let encoder settle after index found

  // ── Step 3: Return precisely to index position ──
  // The index search overshoots due to motor inertia.  Use trapezoidal
  // trajectory mode to crawl back slowly instead of a violent PID snap.
  sendState("INDEX_SETTLE");

  // Control modes: 2 = VELOCITY, 3 = POSITION
  // Input modes:   2 = VEL_RAMP, 5 = TRAP_TRAJ
  odriveWriteRaw("axis0.controller.config.control_mode", 3.0f);   // POSITION
  odriveWriteRaw("axis0.controller.config.input_mode", 5.0f);     // TRAP_TRAJ
  odriveWriteRaw("axis0.trap_traj.config.vel_limit", 0.25f);      // 0.25 rev/s = 15 RPM
  odriveWriteRaw("axis0.trap_traj.config.accel_limit", 0.5f);     // rev/s²
  odriveWriteRaw("axis0.trap_traj.config.decel_limit", 0.5f);     // rev/s²
  delay(10);

  // Enter closed-loop position control
  odriveSetState(AXIS_STATE_CLOSED_LOOP_CONTROL);
  delay(100);

  // Verify we got into closed loop
  if (odriveGetState() != AXIS_STATE_CLOSED_LOOP_CONTROL) {
    Serial.println("DATA: Could not enter position mode for settle — skipping");
  } else {
    // Command trajectory move to position 0 (the index mark)
    while (Serial1.available()) Serial1.read();
    Serial1.println("t 0 0.0");
    Serial1.flush();

    // Wait for position to converge (< 0.003 turns ≈ 1°)
    unsigned long settleStart = millis();
    bool settled = false;
    while (millis() - settleStart < 8000) {
      float pos, vel;
      if (odriveFeedback(pos, vel)) {
        float err = fabs(pos);
        if (err < 0.003f && fabs(vel) < 0.05f) {
          settled = true;
          Serial.print("DATA: IndexSettleErr=");
          Serial.print(err * 360.0f, 2);
          Serial.println(" deg");
          break;
        }
      }
      sendTelemetry();
      delay(50);
    }
    if (!settled) {
      Serial.println("DATA: IndexSettle timeout (8s) — position may not be exact");
    }
  }

  // Return to IDLE, then restore velocity control mode for spin cycles
  odriveSetState(AXIS_STATE_IDLE);
  delay(100);
  odriveWriteRaw("axis0.controller.config.control_mode", 2.0f);   // VELOCITY
  odriveWriteRaw("axis0.controller.config.input_mode", 2.0f);     // VEL_RAMP
  delay(10);

  readEncoderPosition();

  // Emit a telemetry update so the dashboard shows the real position
  // relative to the existing datum (does NOT reset homePos)
  sendTelemNow();

  sendOK("INDEX_COMPLETE");
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Enter closed-loop control, calibrating if needed
// ═══════════════════════════════════════════════════════════════════════════
bool ensureClosedLoop() {
  int attempts = 0;
  while (odriveGetState() != AXIS_STATE_CLOSED_LOOP_CONTROL) {
    if (stopRequested) return false;
    if (++attempts > 50) return false;

    odriveClearErrors();
    odriveSetState(AXIS_STATE_CLOSED_LOOP_CONTROL);
    delay(100);

    if (odriveGetState() == AXIS_STATE_IDLE) {
      sendState("FULL_CALIBRATION");
      odriveSetState(AXIS_STATE_FULL_CALIBRATION_SEQUENCE);
      while (odriveGetState() != AXIS_STATE_IDLE) {
        checkStop();
        if (stopRequested) return false;
        delay(100);
      }
    }
  }
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
//  Raw ASCII ODrive communication layer
//  Replaces ODriveUART library entirely — the library uses property paths
//  like axis0.encoder.vel_estimate that don't exist on ODrive S1.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Write a property: "w <property> <value>\n"
 */
void odriveWriteRaw(const char* property, float value) {
  while (Serial1.available()) Serial1.read();  // drain stale
  Serial1.print("w ");
  Serial1.print(property);
  Serial1.print(" ");
  Serial1.println(value, 4);
  Serial1.flush();
}

/**
 * Read position + velocity via "f 0\n" → "<pos> <vel>\n"
 * Returns true on success, fills pos and vel.
 * This is the ONLY reliable way to read encoder data on ODrive S1.
 */
bool odriveFeedback(float &pos, float &vel) {
  while (Serial1.available()) Serial1.read();  // drain stale
  Serial1.println("f 0");
  Serial1.flush();

  unsigned long t0 = millis();
  String resp = "";
  while (millis() - t0 < 200) {
    if (Serial1.available()) {
      char c = Serial1.read();
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

/**
 * Command velocity: "v 0 <rps> 0\n"
 * The trailing 0 is the feed-forward torque (none).
 */
void odriveSetVelocity(float rps) {
  while (Serial1.available()) Serial1.read();
  Serial1.print("v 0 ");
  Serial1.print(rps, 4);
  Serial1.println(" 0");
  Serial1.flush();
}

/**
 * Read axis state: "r axis0.current_state\n" → "<int>\n"
 * Returns AXIS_STATE_UNDEFINED (0) on timeout/error.
 */
int odriveGetState() {
  String resp = odriveReadRaw("axis0.current_state");
  if (resp.length() > 0) {
    int st = resp.toInt();
    // Sanity check — valid states are 0–14 ish
    if (st >= 0 && st <= 20) return st;
  }
  return AXIS_STATE_UNDEFINED;
}

/**
 * Set axis state: "w axis0.requested_state <state>\n"
 */
void odriveSetState(int state) {
  odriveWriteRaw("axis0.requested_state", (float)state);
}

/**
 * Clear errors: "sc\n" (system clear)
 */
void odriveClearErrors() {
  while (Serial1.available()) Serial1.read();
  Serial1.println("sc");
  Serial1.flush();
  delay(10);  // give ODrive a moment to process
}

// ═══════════════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════════════
void sendState(const char* msg) {
  Serial.print("STATE: "); Serial.println(msg);
}
void sendOK(const char* msg) {
  Serial.print("OK: "); Serial.println(msg);
}
void sendErr(const char* msg) {
  Serial.print("ERR: "); Serial.println(msg);
}
