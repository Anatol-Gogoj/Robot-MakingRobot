/**
 * M753.cpp — Spincoater UART diagnostic
 *
 * Sends "r vbus_voltage\n" on Serial2 and dumps every byte that comes back
 * (printable chars normally, control chars as hex). This is identical to the
 * DIAG command on the Nano RP2040 test firmware.
 *
 * Use to verify Serial2 ↔ ODrive S1 wiring before running M750.
 */

#include "../../inc/MarlinConfig.h"

#if ENABLED(SPINCOATER)

#include "../gcode.h"
#include "../../feature/spincoater.h"
#include "../../MarlinCore.h"

#define ODRIVE_SERIAL SPINCOATER_SERIAL

void GcodeSuite::M753() {

  // Ensure serial is initialized
  Spincoater::init();

  SERIAL_ECHOLNPGM("echo:SPIN DIAG: === UART DIAGNOSTIC ===");
  SERIAL_ECHOPGM("echo:SPIN DIAG: Serial2 baud=");
  SERIAL_ECHOLN(SPINCOATER_BAUD);

  // Drain any stale data
  int stale = 0;
  while (ODRIVE_SERIAL.available()) { ODRIVE_SERIAL.read(); stale++; }
  SERIAL_ECHOPGM("echo:SPIN DIAG: Stale bytes drained=");
  SERIAL_ECHOLN(stale);

  // Send a simple command and dump raw response
  // NOTE: Use write('\n') not println() — AVR println sends \r\n,
  // but ODrive ASCII protocol expects bare \n.
  SERIAL_ECHOLNPGM("echo:SPIN DIAG: Sending 'r vbus_voltage'");
  ODRIVE_SERIAL.print("r vbus_voltage");
  ODRIVE_SERIAL.write('\n');
  ODRIVE_SERIAL.flush();

  // Wait up to 2 seconds, print every byte that comes back
  const millis_t t0 = millis();
  int byteCount = 0;
  String resp = "";

  while (millis() - t0 < 2000) {
    idle();  // keep watchdog happy
    if (ODRIVE_SERIAL.available()) {
      int b = ODRIVE_SERIAL.read();
      byteCount++;
      if (b >= 32 && b < 127) {
        resp += (char)b;
      } else if (b == '\n') {
        resp += "\\n";
      } else if (b == '\r') {
        resp += "\\r";
      } else {
        resp += "[0x";
        if (b < 16) resp += "0";
        resp += String(b, HEX);
        resp += "]";
      }
      // Stop after newline (complete response)
      if (b == '\n') break;
    }
  }

  SERIAL_ECHOPGM("echo:SPIN DIAG: Response bytes: ");
  SERIAL_ECHOLN(resp.c_str());
  SERIAL_ECHOPGM("echo:SPIN DIAG: Total bytes=");
  SERIAL_ECHO(byteCount);
  SERIAL_ECHOPGM(" elapsed=");
  SERIAL_ECHO((int)(millis() - t0));
  SERIAL_ECHOLNPGM("ms");

  if (byteCount == 0) {
    SERIAL_ECHOLNPGM("echo:SPIN DIAG: >>> NO RESPONSE <<<");
    SERIAL_ECHOLNPGM("echo:SPIN DIAG: Check: TX/RX swap, ISOVDD+ISOGND connected, ODrive power, baud rate");
    SERIAL_ECHOLNPGM("echo:SPIN DIAG: Mega pin 16 (TX2) -> ODrive J11 pin 4 (RX)");
    SERIAL_ECHOLNPGM("echo:SPIN DIAG: Mega pin 17 (RX2) -> ODrive J11 pin 3 (TX)");
  }

  SERIAL_ECHOLNPGM("echo:SPIN DIAG: === END DIAGNOSTIC ===");
}

#endif // SPINCOATER
