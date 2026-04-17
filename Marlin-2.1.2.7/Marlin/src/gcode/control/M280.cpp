/**
 * Marlin 3D Printer Firmware
 * Copyright (c) 2020 MarlinFirmware [https://github.com/MarlinFirmware/Marlin]
 *
 * Based on Sprinter and grbl.
 * Copyright (c) 2011 Camiel Gubbels / Erik van der Zalm
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 */

#include "../../inc/MarlinConfig.h"

#if HAS_SERVOS

#include "../gcode.h"
#include "../../module/servo.h"
#include "../../module/planner.h"

/**
 * M280: Get or set servo position.
 *  P<index> - Servo index
 *  S<angle> - Angle to set, omit to read current angle, or use -1 to detach
 *
 * With POLARGRAPH:
 *  T<ms>    - Duration of servo move
 */
void GcodeSuite::M280() {

  if (!parser.seenval('P')) return;

  TERN_(POLARGRAPH, planner.synchronize());

  const int servo_index = parser.value_int();
  if (WITHIN(servo_index, 0, NUM_SERVOS - 1)) {
    if (parser.seenval('S')) {
      int anew = parser.value_int();
      if (anew >= 0) {
        // RMR patches:
        //  - Firmware servo clamp removed; HTML enforces soft limits.
        //  - POLARGRAPH gate removed so any M280 can use T<ms> for timed ramp
        //    (e.g. M280 P1 S30 T1500 to open the lid over 1.5 s).
        //    Uses write() in the loop — move() would invoke attach + safe_delay(SERVO_DELAY)
        //    + detach per step, blocking ~2 s per 50 ms iteration with SERVO_DELAY=2000.
        //    When T is used, skip move() entirely to avoid the extra SERVO_DELAY block.
        bool did_ramp = false;
        if (parser.seenval('T')) {
          const int16_t t = constrain(parser.value_int(), 0, 10000);
          if (t > 0) {
            const int aold = servo[servo_index].read();
            servo[servo_index].attach(0);     // keep PWM alive across the ramp
            millis_t now = millis();
            const millis_t start = now, end = start + t;
            while (PENDING(now, end)) {
              safe_delay(50);                 // drives thermalManager.task() internally
              now = _MIN(millis(), end);
              servo[servo_index].write(LROUND(aold + (anew - aold) * (float(now - start) / t)));
            }
            servo[servo_index].write(anew);   // ensure exact final angle
            safe_delay(250);                  // brief settle before detach
            TERN_(DEACTIVATE_SERVOS_AFTER_MOVE, servo[servo_index].detach());
            did_ramp = true;
          }
        }
        if (!did_ramp) servo[servo_index].move(anew);  // no T or T=0: normal move with SERVO_DELAY
      }
      else
        servo[servo_index].detach();
    }
    else
      SERIAL_ECHO_MSG(" Servo ", servo_index, ": ", servo[servo_index].read());
  }
  else
    SERIAL_ERROR_MSG("Servo ", servo_index, " out of range");

}

#endif // HAS_SERVOS
