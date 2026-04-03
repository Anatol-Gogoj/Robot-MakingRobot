/**
 * SpincoaterStage — Arduino Nano RP2040 Connect test firmware (v2.5)
 *
 * Drives an ODrive S1 over hardware UART (Serial1) with parameterized
 * spin cycles and real-time telemetry.
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
 *   TELEM: RPM=<val> POS=<val>
 */

#include <Arduino.h>
#include <cmath>
#include <ODriveUART.h>

// ── ODrive serial link ──
static const unsigned long ODRIVE_BAUD = 115200;
ODriveUART odrive(Serial1);

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
String odriveReadRaw(const char* property);
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
    odrive.setVelocity(0);
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
    odrive.setVelocity(0);
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

  sendErr("Unknown command. Try: SPIN, START, SET, STATUS, STOP, HOME, SETHOME");
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
  String posStr = odriveReadRaw("axis0.encoder.pos_estimate");
  float pos = posStr.toFloat();

  Serial.print("DATA: EncoderPos=");
  Serial.println(posStr);

  float deg = fmod((pos - homePos) * 360.0f, 360.0f);
  if (deg < 0) deg += 360.0f;
  Serial.print("DATA: DegFromHome=");
  Serial.println(deg, 2);

  Serial.print("DATA: HomeRef=");
  Serial.println(homePos, 6);
}

// ═══════════════════════════════════════════════════════════════════════════
//  SETHOME — set current encoder position as the 0° datum.
//  This is the user-facing "Set Home" action.
// ═══════════════════════════════════════════════════════════════════════════
void doSetHome() {
  // Single 'f 0' read for atomic pos + vel
  while (Serial1.available()) Serial1.read();
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
  Serial.println(odrive.getState());

  String vbus = odriveReadRaw("vbus_voltage");
  Serial.print("DATA: Vbus=");
  Serial.print(vbus);
  Serial.println("V");

  float vel = odrive.getVelocity();
  Serial.print("DATA: Velocity=");
  Serial.print(vel * 60.0f, 1);
  Serial.println(" RPM");

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
  while (odrive.getState() == AXIS_STATE_UNDEFINED) {
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
  odrive.setVelocity(targetRPS);

  // Ramp-up: use telemetry's cached RPM for exit check (avoids
  // conflicting serial reads on the ODrive UART)
  lastTelemRPM = 0;
  while (lastTelemRPM < threshRPM) {
    checkStop();
    if (stopRequested) { sendState("ABORTED"); running = false; return; }
    sendTelemetry();
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

  odrive.setVelocity(0);

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

      float rps = odrive.getVelocity();
      float rpm = rps * 60.0f;

      n++;
      float delta  = rpm - mean;
      mean        += delta / (float)n;
      float delta2 = rpm - mean;
      m2          += delta * delta2;

      if (rpm < minRPM) minRPM = rpm;
      if (rpm > maxRPM) maxRPM = rpm;
    }

    // Telemetry at TELEM_INTERVAL (doesn't interfere with sampling
    // because getVelocity() above is the sampling call, this one is
    // purely for the dashboard readout between samples)
    sendTelemetry();
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
  while (odrive.getState() == AXIS_STATE_UNDEFINED) {
    if (millis() - t0 > 5000) {
      sendErr("ODrive not responding");
      return false;
    }
    delay(100);
  }

  // Step 1: Ensure we're in IDLE first (can't go CL → INDEX_SEARCH directly)
  int currentState = odrive.getState();
  if (currentState != AXIS_STATE_IDLE) {
    Serial.print("DATA: PreHomeState="); Serial.println(currentState);
    sendState("ENTERING_IDLE");
    odrive.setState(AXIS_STATE_IDLE);

    unsigned long idleStart = millis();
    while (odrive.getState() != AXIS_STATE_IDLE) {
      if (millis() - idleStart > 3000) {
        sendErr("Could not enter IDLE before homing");
        return false;
      }
      delay(50);
    }
    delay(200);
  }

  // Step 2: Command encoder index search
  odrive.setState(AXIS_STATE_ENCODER_INDEX_SEARCH);

  // Wait for state to transition out of IDLE
  unsigned long transitionStart = millis();
  bool enteredSearch = false;
  while (millis() - transitionStart < 3000) {
    int st = odrive.getState();
    if (st == AXIS_STATE_ENCODER_INDEX_SEARCH) {
      enteredSearch = true;
      sendState("INDEX_SEARCH_ACTIVE");
      break;
    }
    if (millis() - transitionStart > 500 && st == AXIS_STATE_IDLE) {
      odrive.clearErrors();
      odrive.setState(AXIS_STATE_ENCODER_INDEX_SEARCH);
    }
    delay(50);
  }

  if (!enteredSearch) {
    int st = odrive.getState();
    if (st == AXIS_STATE_IDLE) {
      sendState("INDEX_FOUND_INSTANT");
    } else {
      Serial.print("ERR: Stuck in state="); Serial.println(st);
      return false;
    }
  } else {
    // Wait for completion (returns to IDLE), with telemetry
    unsigned long homeStart = millis();
    while (odrive.getState() != AXIS_STATE_IDLE) {
      if (millis() - homeStart > 30000) {
        sendErr("Homing timeout (30 s)");
        return false;
      }
      sendTelemetry();
      delay(100);
    }
  }

  delay(300);  // Let encoder settle after index found

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
  while (odrive.getState() != AXIS_STATE_CLOSED_LOOP_CONTROL) {
    if (stopRequested) return false;
    if (++attempts > 50) return false;

    odrive.clearErrors();
    odrive.setState(AXIS_STATE_CLOSED_LOOP_CONTROL);
    delay(100);

    if (odrive.getState() == AXIS_STATE_IDLE) {
      sendState("FULL_CALIBRATION");
      odrive.setState(AXIS_STATE_FULL_CALIBRATION_SEQUENCE);
      while (odrive.getState() != AXIS_STATE_IDLE) {
        checkStop();
        if (stopRequested) return false;
        delay(100);
      }
    }
  }
  return true;
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
