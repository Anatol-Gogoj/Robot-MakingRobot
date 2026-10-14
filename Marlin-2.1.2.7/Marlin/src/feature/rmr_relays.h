/**
 * rmr_relays.h - RMR UV lamp and solenoid valve relays: force both OFF
 *
 * Called early in setup(), in kill() and minkill() (M112), and from motor_power::task()
 * when motor power drops, so neither relay stays energized after an E-stop or relights
 * when the motor contactor is reset. Issue #131. Pins and OFF levels: Configuration_adv.h.
 *
 * Header-only, so it needs no build_src_filter entry in ini/features.ini.
 */
#pragma once

#include "../inc/MarlinConfig.h"

#if ENABLED(UV_LID_INTERLOCK)
  #include "uv_interlock.h"
#endif

namespace RmrRelays {

  // The same calls M42 uses (digitalWrite, then pinMode OUTPUT), so this also detaches a
  // PWM duty that M42 S2..254 left on pin 4 (OC0B); a fastio WRITE would not. Level first,
  // then direction: a pin that is still an input goes straight to the OFF level without
  // passing through the ON level. No serial, no delay, and no interrupts needed, so it is
  // safe before the HAL is up and after minkill()'s cli().
  inline void allOff() {
    #if PIN_EXISTS(UV_LAMP)
      extDigitalWrite(UV_LAMP_PIN, UV_LAMP_OFF_LEVEL);
      pinMode(UV_LAMP_PIN, OUTPUT);
    #endif
    #if PIN_EXISTS(SOLENOID_VALVE)
      extDigitalWrite(SOLENOID_VALVE_PIN, SOLENOID_VALVE_OFF_LEVEL);
      pinMode(SOLENOID_VALVE_PIN, OUTPUT);
    #endif
    // The lamp is off now, so the lid interlock has no cure left to cut (and no
    // "lid opened" line to print) if the lid opens afterwards.
    TERN_(UV_LID_INTERLOCK, uv_interlock::note_uv(false));
  }

}
