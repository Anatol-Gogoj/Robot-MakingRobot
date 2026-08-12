/**
 * M750.cpp — Spincoater spin cycle
 *
 * Blocking M-code that runs a full spin cycle on the ODrive S1 via Serial2.
 * Ported from SpincoaterStage/src/main.cpp v2.6 runCycle() + measureSpeed().
 *
 * Syntax:
 *   M750 [S<rpm>] [D<seconds>] [A<rise_seconds>] [C<sink_seconds>] [H<0|1>]
 *
 *   S = target RPM              (default: SPINCOATER_DEFAULT_RPM)
 *   D = hold/measure duration   (default: SPINCOATER_DEFAULT_DURATION)
 *   A = ramp-up time in seconds (default: SPINCOATER_DEFAULT_RISE)
 *   C = ramp-down time in sec   (default: SPINCOATER_DEFAULT_SINK)
 *   H = auto-home after spin    (default: SPINCOATER_DEFAULT_HOME)
 *
 * Rise/Sink times are converted to ODrive vel_ramp_rate (rev/s²) internally:
 *   accel = (rpm/60) / rise_s
 *   decel = (rpm/60) / sink_s
 *
 * Calls idle() in every blocking loop to maintain watchdog, keepalive, and M112.
 * Returns ok to host when cycle completes (or on abort).
 */

#include "../../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "../gcode.h"
#include "../../feature/spincoater.h"
#include "../../MarlinCore.h"  // idle()
#include <math.h>

// Telemetry rate limiting
#define SPIN_TELEM_INTERVAL 200  // ms

/**
 * Emit a telemetry line: echo:SPIN TELEM: RPM=<val> POS=<val> DEG=<val>
 * Rate-limited to SPIN_TELEM_INTERVAL. Updates lastTelemRPM.
 * Returns the RPM read (or previous cached value if rate-limited).
 */
static float lastTelemRPM = 0.0f;
static millis_t lastTelemTime = 0;

static void spinTelemetry() {
  const millis_t now = millis();
  if (now - lastTelemTime < SPIN_TELEM_INTERVAL) return;
  lastTelemTime = now;

  float pos, vel;
  if (Spincoater::feedback(pos, vel)) {
    const float rpm = vel * 60.0f;
    lastTelemRPM = rpm;

    const float relTurns = pos - Spincoater::getHomePos();
    float deg = fmod(relTurns * 360.0f, 360.0f);
    if (deg < 0) deg += 360.0f;

    SERIAL_ECHOPGM("echo:SPIN TELEM: RPM=");
    SERIAL_ECHO(rpm);
    SERIAL_ECHOPGM(" POS=");
    SERIAL_ECHO(pos);
    SERIAL_ECHOPGM(" DEG=");
    SERIAL_ECHOLN(deg);
  }
}

/**
 * Welford's online mean/variance with integrated telemetry.
 * Samples at 100ms intervals for dur_s seconds.
 * Reports stats via echo:SPIN DATA: lines.
 */
static void measureSpeed(const int dur_s) {
  const millis_t sampleInterval = 100;
  const millis_t duration = (millis_t)dur_s * 1000UL;

  const millis_t startTime = millis();
  millis_t lastSample = startTime;
  long   n      = 0;
  float  mean   = 0.0f;
  float  m2     = 0.0f;
  float  minRPM = 1e9f;
  float  maxRPM = -1e9f;

  while (millis() - startTime < duration) {
    idle();  // CRITICAL: feed watchdog, process M112, send keepalive

    const millis_t now = millis();
    if (now - lastSample >= sampleInterval) {
      lastSample = now;

      float pos, vel;
      if (Spincoater::feedback(pos, vel)) {
        const float rpm = vel * 60.0f;
        lastTelemRPM = rpm;

        n++;
        const float delta  = rpm - mean;
        mean              += delta / (float)n;
        const float delta2 = rpm - mean;
        m2                += delta * delta2;

        if (rpm < minRPM) minRPM = rpm;
        if (rpm > maxRPM) maxRPM = rpm;

        // Emit telemetry from same read (no second UART round-trip)
        const float relTurns = pos - Spincoater::getHomePos();
        float deg = fmod(relTurns * 360.0f, 360.0f);
        if (deg < 0) deg += 360.0f;

        SERIAL_ECHOPGM("echo:SPIN TELEM: RPM=");
        SERIAL_ECHO(rpm);
        SERIAL_ECHOPGM(" POS=");
        SERIAL_ECHO(pos);
        SERIAL_ECHOPGM(" DEG=");
        SERIAL_ECHOLN(deg);

        lastTelemTime = millis();
      }
    }
  }

  const float variance = (n > 1) ? m2 / (float)n : 0.0f;
  const float stddev   = sqrt(variance);

  SERIAL_ECHOPGM("echo:SPIN DATA: Samples=");    SERIAL_ECHOLN(n);
  SERIAL_ECHOPGM("echo:SPIN DATA: MeanRPM=");    SERIAL_ECHOLN(mean);
  SERIAL_ECHOPGM("echo:SPIN DATA: StdDevRPM=");  SERIAL_ECHOLN(stddev);
  SERIAL_ECHOPGM("echo:SPIN DATA: MinRPM=");     SERIAL_ECHOLN(minRPM);
  SERIAL_ECHOPGM("echo:SPIN DATA: MaxRPM=");     SERIAL_ECHOLN(maxRPM);
  SERIAL_ECHOPGM("echo:SPIN DATA: Range=");       SERIAL_ECHOLN(maxRPM - minRPM);
}

void GcodeSuite::M750() {

  // ── Parse parameters ──
  const int   rpm    = parser.intval('S', SPINCOATER_DEFAULT_RPM);
  const int   dur_s  = parser.intval('D', SPINCOATER_DEFAULT_DURATION);
  const float rise_s = parser.floatval('A', SPINCOATER_DEFAULT_RISE);
  const float sink_s = parser.floatval('C', SPINCOATER_DEFAULT_SINK);
  const bool  home   = parser.boolval('H', SPINCOATER_DEFAULT_HOME);

  if (rpm <= 0 || dur_s <= 0 || rise_s <= 0 || sink_s <= 0) {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: All values must be > 0");
    return;
  }

  // ── Boot ODrive on first call ──
  if (!Spincoater::isReady()) {
    SERIAL_ECHOLNPGM("echo:SPIN STATE:BOOTING");
    if (!Spincoater::boot()) {
      SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive boot failed — check wiring and power");
      return;
    }
  }

  // ── Compute ramp rates ──
  const float targetRPS = (float)rpm / 60.0f;
  const float accel = targetRPS / rise_s;   // rev/s² for ramp-up
  const float decel = targetRPS / sink_s;   // rev/s² for ramp-down

  SERIAL_ECHOPGM("echo:SPIN OK: Cycle — RPM="); SERIAL_ECHO(rpm);
  SERIAL_ECHOPGM(" DUR=");  SERIAL_ECHO(dur_s);
  SERIAL_ECHOPGM("s RISE="); SERIAL_ECHO(rise_s);
  SERIAL_ECHOPGM("s SINK="); SERIAL_ECHO(sink_s);
  SERIAL_ECHOPGM("s HOME="); SERIAL_ECHOLN(home ? "ON" : "OFF");
  SERIAL_ECHOPGM("echo:SPIN DATA: accel="); SERIAL_ECHO(accel);
  SERIAL_ECHOPGM(" decel="); SERIAL_ECHO(decel); SERIAL_ECHOLNPGM(" rev/s2");

  // Reset telemetry state
  lastTelemRPM  = 0.0f;
  lastTelemTime = 0;

  // ── Connect to ODrive ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:CONNECTING");
  {
    const millis_t t0 = millis();
    while (Spincoater::getState() == ODRIVE_STATE_UNDEFINED) {
      idle();
      if (millis() - t0 > 5000) {
        SERIAL_ECHOLNPGM("echo:SPIN ERR: ODrive not responding (5s)");
        return;
      }
      safe_delay(100);
    }
  }
  SERIAL_ECHOLNPGM("echo:SPIN STATE:ODRIVE_FOUND");

  // Read Vbus
  {
    String vbus = Spincoater::readRaw("vbus_voltage");
    SERIAL_ECHOPGM("echo:SPIN DATA: Vbus=");
    SERIAL_ECHO(vbus.c_str());
    SERIAL_ECHOLNPGM("V");
  }

  // ── Enter closed-loop ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:CALIBRATING");
  if (!Spincoater::ensureClosedLoop()) {
    SERIAL_ECHOLNPGM("echo:SPIN ERR: Failed to enter closed-loop");
    return;
  }
  SERIAL_ECHOLNPGM("echo:SPIN STATE:CLOSED_LOOP");

  // ── Ramp up ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:RAMP_UP");
  Spincoater::writeRaw("axis0.controller.config.vel_ramp_rate", accel);
  safe_delay(10);

  const float cmdRPS    = (float)(rpm + 10) / 60.0f;  // slight overshoot
  const float threshRPM = (float)rpm * 0.98f;
  Spincoater::setVelocity(cmdRPS);

  // Ramp-up polling with stall detection
  lastTelemRPM = 0;
  float stallRPM = 0;
  millis_t stallCheck = millis();
  const millis_t rampStart = millis();
  millis_t rampTimeout = (millis_t)(rise_s * 3000.0f);
  if (rampTimeout < 10000) rampTimeout = 10000;

  while (lastTelemRPM < threshRPM) {
    idle();
    spinTelemetry();

    // Hard timeout
    if (millis() - rampStart > rampTimeout) {
      SERIAL_ECHOPGM("echo:SPIN ERR: Ramp-up timeout — reached ");
      SERIAL_ECHO(lastTelemRPM);
      SERIAL_ECHOPGM(" of "); SERIAL_ECHO(threshRPM); SERIAL_ECHOLNPGM(" RPM");
      SERIAL_ECHOLNPGM("echo:SPIN STATE:RAMP_TIMEOUT");
      Spincoater::setVelocity(0);
      return;
    }

    // Stall detection: RPM hasn't increased by >50 in 3s
    if (millis() - stallCheck > 3000) {
      if (lastTelemRPM > 100 && (lastTelemRPM - stallRPM) < 50.0f) {
        SERIAL_ECHOPGM("echo:SPIN ERR: RPM stalled at ");
        SERIAL_ECHO(lastTelemRPM);
        SERIAL_ECHOPGM(" — target "); SERIAL_ECHO(threshRPM);
        SERIAL_ECHOLNPGM(" unreachable");
        SERIAL_ECHOLNPGM("echo:SPIN STATE:RAMP_STALL");
        Spincoater::setVelocity(0);
        return;
      }
      stallRPM = lastTelemRPM;
      stallCheck = millis();
    }

    safe_delay(20);
  }

  // ── Measure ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:MEASURING");
  measureSpeed(dur_s);

  // ── Ramp down ──
  SERIAL_ECHOLNPGM("echo:SPIN STATE:RAMP_DOWN");
  Spincoater::writeRaw("axis0.controller.config.vel_ramp_rate", decel);
  Spincoater::setVelocity(0);

  while (fabs(lastTelemRPM) > 6.0f) {
    idle();
    spinTelemetry();
    safe_delay(50);
  }

  // Settling
  SERIAL_ECHOLNPGM("echo:SPIN STATE:SETTLING");
  {
    const millis_t settleStart = millis();
    while (millis() - settleStart < 1000) {
      idle();
      spinTelemetry();
      safe_delay(50);
    }
  }
  SERIAL_ECHOLNPGM("echo:SPIN STATE:STOPPED");

  // ── Homing (optional) ──
  bool homeFailed = false;
  if (home) {
    // Snapshot the datum so we can tell truthfully whether it survived:
    // doIndexHome()'s settle-timeout fallback may adopt a new one internally.
    const float datumBefore = Spincoater::getHomePos();
    bool ok = Spincoater::doIndexHome();
    if (!ok) {
      homeFailed = true;
      const float datumAfter = Spincoater::getHomePos();

      if (datumAfter != datumBefore) {
        // doIndexHome() only changes the datum when none existed, so this is
        // a first datum being established rather than an operator zero moving.
        SERIAL_ECHOPGM("echo:SPIN WARN: Index homing failed; a first datum was established at ");
        SERIAL_ECHO(datumAfter);
        SERIAL_ECHOLNPGM(" turns — run M751 to set your intended zero");
      }
      else if (Spincoater::isDatumValid()) {
        // Re-datuming here would silently re-zero the machine on wherever the
        // rotor stopped — typically the index mark, up to a full turn from the
        // operator's M751 datum — destroying layer registration. Issue #41.
        SERIAL_ECHOPGM("echo:SPIN WARN: Index homing failed — datum PRESERVED at ");
        SERIAL_ECHO(datumAfter);
        SERIAL_ECHOLNPGM(" turns (not re-datuming)");
      }
      else {
        SERIAL_ECHOLNPGM("echo:SPIN WARN: Index homing failed and no datum set — attempting fallback set-home");
        if (Spincoater::doSetHome()) {
          SERIAL_ECHOLNPGM("echo:SPIN WARN: Fallback home set OK");
        } else {
          SERIAL_ECHOLNPGM("echo:SPIN ERR: Fallback home failed — manual intervention required");
        }
      }
    }
  }

  // Terminal line must not claim success when the rotor never reached the
  // datum. The token still contains CYCLE_COMPLETE so existing UI handlers
  // still close out the phase; rendering it as an error is tracked in #47.
  if (homeFailed)
    SERIAL_ECHOLNPGM("echo:SPIN ERR: CYCLE_COMPLETE_NO_HOME — rotor parked off datum, angular registration unverified");
  else
    SERIAL_ECHOLNPGM("echo:SPIN OK: CYCLE_COMPLETE");
}

#endif // SPINCOATER
