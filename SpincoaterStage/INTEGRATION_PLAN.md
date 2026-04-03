# Spincoater → Marlin/Mega Integration Plan

**Status:** Draft v1 — April 2026
**Context:** The benchtop test firmware (Nano RP2040 + ODrive S1) validates the spin cycle logic. The next step is to eliminate the second MCU entirely and have the Mega 2560 (running Marlin) drive the ODrive S1 directly over UART.

---

## 1. The Serial Port Problem

The Mega 2560 has four hardware UARTs. Here's the current allocation:

| UART    | TX Pin | RX Pin | Current Use                          | Available? |
|---------|--------|--------|--------------------------------------|------------|
| Serial0 | 0      | 1      | USB ↔ PC (Marlin G-code)            | No         |
| Serial1 | 18     | 19     | Pin 18 free; Pin 19 = E0_DIR        | **No** — RX occupied |
| Serial2 | 16     | 17     | Pin 16 free; Pin 17 = J_MIN endstop | **Partially** |
| Serial3 | 14     | 15     | Pin 14 = Y_MIN; Pin 15 = I_MAX      | **No** — both occupied |

**Resolution: Free Serial2 by relocating J endstop.**

Pin 17 (Mega TX2) is currently the J-axis (Syringe Height) endstop. Move it to any free GPIO on the Mega. Good candidates: pins 23, 25, 27, 29, 32, 33, 35, 37, 39, 41, 43, 45, 47, or 49 — all are standard digital I/O with no alternate-function conflicts.

**Recommended: Pin 23** (or any pin physically convenient for your wiring). This frees both pin 16 (TX2) and pin 17 (RX2) for ODrive UART.

### Wiring changes

1. Move J endstop wire from pin 17 → pin 23 (or chosen GPIO)
2. Update `pins_RAMPS_14_RMR.h`:
   ```cpp
   // J-axis endstop: moved from pin 17 (TX2) to free Serial2 for ODrive
   #define J_MIN_PIN      23
   ```
3. Connect Mega ↔ ODrive S1 J11:
   - Mega pin 16 (TX2) → ODrive J11 pin 4 (RX / GPIO7)
   - Mega pin 17 (RX2) → ODrive J11 pin 3 (TX / GPIO6)
   - Mega GND → ODrive J11 ISOGND
   - Mega 5V → ODrive J11 ISOVDD (isolator accepts 3.3–5V)

4. Update `CLAUDE.md` pin conflict table and gotcha #7.

---

## 2. Architecture Decision: Blocking Custom M-Code

Three integration approaches were considered:

| Approach | Complexity | Pros | Cons |
|----------|-----------|------|------|
| **A. Blocking M-code** | Low | Simple, self-contained, reuses proven ODrive ASCII protocol | Blocks Marlin G-code parser for cycle duration (30–60s) |
| B. Non-blocking state machine | High | Marlin stays responsive, could process other commands | Requires hooking into Marlin's idle loop, complex state management |
| C. Keep slave MCU | Medium | Offloads blocking, Mega just sends trigger | Extra board, extra serial link, more failure modes |

**Recommendation: Approach A (blocking M-code).**

Rationale:
- During spin coating, the gantry must not move. There is no benefit to Marlin being "responsive" during a spin cycle.
- The G-code Program Runner in `RMR_Controller.html` already uses "wait for ok" — it will simply wait for the spin to finish before sending the next line.
- The ODrive ASCII protocol is proven and identical to what's running on the Nano right now.
- If emergency stop is needed during a spin, the hardware E-stop (or M112 if the serial buffer allows it) can be used. Alternatively, the ODrive's own watchdog/error handling will trigger on loss of communication.

**Timeout consideration:** Marlin's host keepalive feature (`HOST_KEEPALIVE_FEATURE`, `DEFAULT_KEEPALIVE_INTERVAL`) sends `busy: processing` messages to the host during long-running commands. This prevents the host from timing out. It's already enabled by default in Marlin. The M750 handler should call `idle()` periodically during its blocking loops to allow keepalive messages to be sent.

---

## 3. Custom M-Code: M750

### Why M750?

The M700–M799 range is mostly unused in stock Marlin 2.1.x. M3/M4/M5 (spindle/laser) are conceptually related but architecturally wrong — they're designed for continuous on/off control with planner synchronization, not for autonomous timed cycles. A dedicated M-code is cleaner.

### Syntax

```gcode
M750 [S<rpm>] [D<seconds>] [A<accel_rps2>] [C<decel_rps2>] [H<0|1>]
```

| Param | Description | Default | Units |
|-------|-------------|---------|-------|
| S | Spin speed | 5000 | RPM |
| D | Hold duration (measurement period) | 30 | seconds |
| A | Ramp-up acceleration | 15.0 | rev/s² (ODrive vel_ramp_rate) |
| C | Ramp-down deceleration | 100.0 | rev/s² |
| H | Encoder index search (home) after spin | 1 | boolean |

Example G-code sequence:
```gcode
G1 X385 Y75 F6000    ; move gantry to spincoater position
M400                  ; wait for motion to complete
M750 S5000 D30 A15 C100 H1  ; spin cycle: 5000 RPM, 30s, ramp 15 rps², decel 100 rps², home after
G1 X100 Y50 F6000    ; next operation (only runs after spin completes)
```

### Execution Flow (mirrors Nano firmware)

1. **Connect:** Verify ODrive is responding on Serial2 (timeout 5s)
2. **Read Vbus:** `r vbus_voltage\n` — report via `SERIAL_ECHOLNPGM`
3. **Enter closed-loop:** Clear errors → command `AXIS_STATE_CLOSED_LOOP_CONTROL`. If IDLE, run full calibration sequence first.
4. **Set ramp rate:** `w axis0.controller.config.vel_ramp_rate <accel>\n`
5. **Command velocity:** `f 0` feedback command for position/velocity, `v 0 <target_rps>\n` or `setVelocity()` equivalent
6. **Wait for ramp-up:** Poll velocity via `f 0` until RPM ≥ 98% of target. Call `idle()` between polls.
7. **Measure:** Welford's algorithm for `D` seconds at 100ms intervals. Call `idle()` each iteration.
8. **Report stats:** Mean, std dev, min, max via `SERIAL_ECHOLNPAIR`
9. **Ramp down:** Set decel rate, command velocity 0, poll until RPM < 6
10. **Settle:** 1s dwell
11. **Home (if H1):** IDLE → ENCODER_INDEX_SEARCH → wait for IDLE
12. **Return:** Send `ok` to host

### Critical: `idle()` Calls

Every blocking loop in M750 **must** call Marlin's `idle()` function. This:
- Sends keepalive messages to the host
- Processes emergency stop (M112)
- Updates the watchdog timer
- Runs temperature management (though we have no heaters, the idle loop expects to run)

Without `idle()`, Marlin's watchdog will reset the Mega after ~4 seconds.

---

## 4. File Changes Required

### New files

| File | Purpose |
|------|---------|
| `Marlin/src/gcode/control/M750.cpp` | Spin cycle M-code handler |
| `Marlin/src/feature/spincoater.h` | ODrive UART communication helpers (Serial2) |
| `Marlin/src/feature/spincoater.cpp` | Implementation: connect, setVelocity, getVelocity, setState, etc. |

### Modified files

| File | Change |
|------|--------|
| `Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h` | Move `J_MIN_PIN` from 17 to 23 |
| `Marlin/src/gcode/gcode.cpp` | Add `case 750: M750(); break;` in M-code switch |
| `Marlin/src/gcode/gcode.h` | Add `static void M750();` declaration |
| `Marlin/Configuration.h` or `Configuration_adv.h` | Add `#define SPINCOATER` feature flag, `#define SPINCOATER_SERIAL Serial2`, `#define SPINCOATER_BAUD 115200` |
| `CLAUDE.md` | Update pin map, add M750 to G-code reference, update TODO list |

### Feature flag pattern

```cpp
// In Configuration_adv.h:
#define SPINCOATER
#define SPINCOATER_SERIAL     Serial2
#define SPINCOATER_BAUD       115200

// In M750.cpp:
#include "../../inc/MarlinConfig.h"
#if ENABLED(SPINCOATER)
  #include "../gcode.h"
  #include "../../feature/spincoater.h"

  void GcodeSuite::M750() {
    // ... implementation
  }
#endif
```

This keeps the spincoater code completely conditional — it won't compile for anyone else's Marlin build.

---

## 5. ODrive Communication Layer

The `spincoater.h/cpp` module wraps raw Serial2 ASCII commands. It does NOT use the ODriveUART Arduino library (that library's `getParameterAsFloat()` uses `sscanf("%f")` which works fine on ATmega but we want to keep the raw ASCII approach for consistency with the tested Nano code and to avoid library dependency issues).

Key functions:

```cpp
namespace Spincoater {
  void init();                          // Serial2.begin(SPINCOATER_BAUD)
  String readRaw(const char* property); // "r <property>\n" → response
  void writeRaw(const char* prop, float val); // "w <prop> <val>\n"
  bool sendFeedback(float &pos, float &vel);  // "f 0\n" → parse pos, vel
  void setVelocity(float rps);          // "v 0 <rps> 0\n"
  int getState();                       // "r axis0.current_state\n"
  void setState(int state);             // "w axis0.requested_state <state>\n"
  void clearErrors();                   // "sc\n"
}
```

Using raw ASCII instead of the ODriveUART library:
- No external library dependency in Marlin
- No sscanf issues (we use `String.toFloat()` / `String.toInt()`)
- Minimal flash/RAM footprint
- Exact same protocol as the tested Nano firmware

---

## 6. SRAM Budget

The Mega 2560 has 8 KB SRAM vs. the Nano RP2040's 264 KB. Marlin itself uses a significant portion. Key considerations:

- **No sample array:** Welford's online algorithm (already implemented on Nano) uses O(1) memory — just a few floats.
- **Serial2 buffer:** Arduino's default 64-byte HardwareSerial buffer is sufficient for ODrive ASCII responses (typically < 30 chars).
- **String temporaries:** The `readRaw()` function builds a String response. These are short-lived and small (< 50 chars). Acceptable.
- **No ODriveUART library:** Avoids the library's internal buffers.

Estimated additional SRAM usage for M750: ~100–200 bytes. Should be fine given the Mega's 8 KB and Marlin's typical ~4–5 KB usage.

---

## 7. Implementation Sequence

### Step 1: Hardware rewire (15 min)
- Move J endstop from pin 17 to pin 23
- Wire Serial2 (16/17) to ODrive J11
- Verify J endstop still triggers correctly: `M119` after flashing

### Step 2: Pin file update + build test
- Update `J_MIN_PIN` in `pins_RAMPS_14_RMR.h`
- Build Marlin, flash, verify all axes home correctly (`G28`)

### Step 3: Implement spincoater communication layer
- Create `spincoater.h` / `spincoater.cpp`
- Add `SPINCOATER` feature flag to Configuration_adv.h
- Standalone test: add a temporary M751 that just reads Vbus and prints it, to verify Serial2 ↔ ODrive link

### Step 4: Implement M750
- Port the cycle logic from the Nano's `runCycle()` into M750
- Replace `Serial.print` → `SERIAL_ECHOLNPAIR` / `SERIAL_ECHO` macros
- Replace `Serial1.*` → `SPINCOATER_SERIAL.*`
- Add `idle()` calls in all blocking loops
- Add parameter parsing via `parser.floatval('S')`, etc.

### Step 5: Integration test
- Flash updated Marlin
- Test from serial terminal: `M750 S3000 D10 A15 C100 H1`
- Test from Program Runner with a multi-line G-code sequence
- Verify M112 E-stop works during spin (via `idle()` processing)

### Step 6: Production G-code
- Write full pick-and-place → spin-coat → dispose workflow
- Test end-to-end

---

## 8. What Stays on the Dashboard

The `SpincoaterDashboard.html` remains useful for direct ODrive testing from a PC — it bypasses Marlin entirely (PC → Nano → ODrive). Once the Mega integration is complete, spin cycles will be triggered via `RMR_Controller.html`'s G-code input or Program Runner.

Telemetry during Mega-driven spin cycles will appear as `echo:` messages in the serial console of `RMR_Controller.html` — same as any other Marlin debug output. The circular dial and RPM gauge from the Spincoater Dashboard won't be available during Mega operation unless we add telemetry parsing to the RMR controller (a nice-to-have, not essential for functionality).

---

## 9. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Marlin watchdog reset during long spin | High if `idle()` missed | Mega resets mid-spin | Audit every loop for `idle()` calls |
| Serial2 interrupt conflicts with stepper ISR | Low | Corrupted ODrive comms | Hardware UART has dedicated interrupt; Marlin disables steppers during M750 since gantry is idle |
| ODrive brownout during motor spin-up | Low | ODrive faults | Vbus check before spin, adequate PSU sizing |
| Host timeout during long M750 | Medium | Host disconnects | `HOST_KEEPALIVE_FEATURE` sends busy messages via `idle()` |
| J endstop EMI on new pin | Low | False triggers during homing | Same mitigation as Z endstop: 100nF cap, `ENDSTOP_NOISE_THRESHOLD 7` |

---

## 10. Open Questions

1. **Pin 23 accessibility:** Is pin 23 physically accessible on your board/wiring? If not, pick another free GPIO from the list above.
2. **ODrive calibration persistence:** Is `startup_motor_calibration_sequence` configured on the ODrive to skip full calibration on every power cycle? If not, M750 will need to run calibration each time, adding ~10s.
3. **Concurrent E-stop:** Does your setup have a hardware E-stop button that cuts power to the ODrive independently of Marlin? If not, the `idle()` + M112 path is the only software E-stop during spin.
4. **Telemetry in RMR_Controller.html:** Do you want RPM readout during Mega-driven spins in the main dashboard? If yes, we'd need to add an `echo:TELEM:` parser and a gauge widget to `RMR_Controller.html`.
