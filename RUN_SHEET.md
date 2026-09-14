# Run Sheet — Debug and Repair of the Gantry Machine

**Issue date:** 2026-08-12
**Language:** ASD-STE100 Simplified Technical English.
**For:** the on-site colleagues at the bench. The owner is remote.

---

## 1. What this sheet is

This sheet gives the tasks in sequence. It tells you what to do, in which order, to find and
correct the faults in the machine.

The machine has one primary fault: **the spin coater does not go to the home position correctly.**

Nine changes to the firmware are written. Six pull requests hold them. All of them build. All of
them had a review. **No one installed them on the machine.** No one tested them on hardware.

Your work makes these changes true or false. Until you test them, they are only text.

---

## 2. Words used in this sheet

| Word | Meaning in this sheet |
|---|---|
| Stack | The six pull requests. They are in sequence. Each one contains the changes of the one before it. |
| Tip | The last branch in the stack: `fix/44-feedback-numeric-validation`. It contains all nine changes. |
| Datum | The 0-degree reference position of the chuck. The command `M751` sets it. |
| Index search | A movement of the motor to find the index pulse of the encoder. |
| Index reference | The condition where the position count of the encoder starts at the index pulse. |
| Marker | The last line that a spin command writes. It starts with `OK:` or with `ERR:`. |
| Lane | A group of tasks. Four lanes can run at the same time. |

---

## 3. Safety

Read this section before you touch the machine.

> **WARNING — INJURY TO PERSONS**
> Do not look at the UV lamp. The UV light can cause injury to the eyes and the skin.
> Put on UV eye protection before you energize the lamp.

> **WARNING — INJURY TO PERSONS**
> Keep your hands away from the chuck. The chuck turns at 5000 RPM.
> Close the lid before each spin cycle.

> **WARNING — INJURY TO PERSONS**
> The commands `M752` and `M750 H1` turn the chuck. They turn the chuck at approximately
> 15 RPM for as long as 8 seconds. Remove all items from the chuck before you send these commands.
> Close the lid.

> **CAUTION — DAMAGE TO EQUIPMENT**
> The button `Stop` in the spin coater panel of the UI sends `M112`. `M112` stops the firmware.
> The chuck then turns freely with no control. Do not use this button as a usual stop.

> **CAUTION — DAMAGE TO EQUIPMENT**
> The machine has no brake resistor that anyone confirmed. A fast stop from a high speed can
> put a high voltage on the DC bus. Do not command a fast stop. Task 12 examines this.

> **NOTE**
> After `M112`, the board is dead. The command `M999` does not start it again on this machine.
> To recover, disconnect the USB cable and connect it again, or remove the power and apply it again.
> A recovery of this type erases the datum. Send `M751` again after each recovery.

---

## 4. Tools and materials

| Item | Used for |
|---|---|
| Ubuntu laptop with PlatformIO | Tasks 3 to 11 |
| USB cable to the Mega 2560 | Tasks 3 to 11 |
| USB cable to the native USB port of the ODrive | Task 2 |
| `odrivetool` on the laptop | Task 2 |
| Chrome browser or Edge browser | All tasks that use the UI |
| Oscilloscope | Task 13 |
| Multimeter | Tasks 1, 12 and 13 |
| Stopwatch | Task 9 |

---

## 5. Rules for all tasks

1. Do the tasks in the sequence of this sheet.
2. Do one step at a time.
3. Record the result of each step. Record the full text of each `ERR:` line and each `WARN:` line.
4. If a step fails, stop that lane. Tell the owner. Do not go to the next step of that lane.
5. Do not judge a spin cycle by the phase indicator of the UI. The phase indicator is not correct.
   Read the marker line.
6. The word `ok` from Marlin does not mean that the command was a success. Read the marker line.
7. The success markers are `OK: CYCLE_COMPLETE`, `OK: INDEX_COMPLETE` and `OK: HOME_SET`.
8. The failure markers are `ERR: CYCLE_COMPLETE_NO_HOME`, `ERR: INDEX_HOME_FAILED`,
   `ERR: HOME_SET_FAILED` and `ERR: INDEX_INCOMPLETE`.
9. Some failures write no marker. If no marker comes, this is also a failure. Record it.

---

## 6. The four lanes and their sequence

Four lanes exist. The lanes do not share files. Different persons can do different lanes at the
same time.

| Lane | Tasks | Start condition |
|---|---|---|
| **A — ODrive** | 1, 2 | Start now. This lane has the highest value. |
| **B — Firmware** | 3 to 11 | Start after Task 1. |
| **D — Shop** | 12, 13 | Start now. Task 12 needs the firmware of Task 4. |
| **C — User interface** | 14, 15 | Start now. This lane needs no hardware. |

**Do Lane A first if you have only one person.** Task 2 gives an answer that four other tasks need.

Inside Lane B, the sequence is fixed. Do not change it.

```
Task 1  (baseline)
   |
   +--> Lane A:  Task 2  ------------------> (result gates the future design work)
   |
   +--> Lane B:  Task 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11
   |
   +--> Lane D:  Task 12, Task 13  (no sequence between these two)
   |
   +--> Lane C:  Task 14 -> Task 15
```

---

# LANE A — THE ODRIVE

## Task 1 — Record the initial state

Do this task before you change anything.

Use the file `SpincoaterPinMap.jfif` in the repository. It shows the connector J11 of the ODrive S1.
This is the authoritative pinout.

| J11 pin | Function | J11 pin | Function |
|---|---|---|---|
| 1 | CAN_H | 2 | CAN_L |
| 3 | CAN_H | 4 | CAN_L |
| 5 | 12 V IN | 6 | 3.3 V |
| **7** | **UART TX (GPIO6)** | **8** | **UART RX (GPIO7)** |
| **9** | **ISO VDD** | **10** | **ISO GND** |
| 11 | DIR (GPIO5) | 12 | STEP (GPIO8) |

**Step 1.1** — Do not apply power to the machine yet. Look at the connector J11 of the ODrive.

**Step 1.2** — Record which pin of the Mega goes to which pin of J11. Take a photograph of the
connector. Compare the photograph with the table above.

> **NOTE — a fault in three documents**
> `PIN_MAP.md`, `claude.md` and `SpincoaterStage/INTEGRATION_PLAN.md` all say that the UART is on
> J11 pin 3 and J11 pin 4. The pinout image shows CAN on pin 3 and pin 4. The image shows the
> UART on pin 7 and pin 8.
> The serial link operates on the machine today. Thus the wires are probably correct and the three
> documents are probably incorrect. Record what the machine has. Do not change the wires.

**Step 1.3** — Make sure that the Mega pin 16 (TX2) goes to J11 pin 8 (UART RX).

**Step 1.4** — Make sure that the Mega pin 17 (RX2) goes to J11 pin 7 (UART TX).

**Step 1.5** — Find which wire supplies the pin `ISOVDD` (J11 pin 9).

> **NOTE — the isolated block needs external power**
> The pinout image says this in red text: "ISOLATED IO. Requires external power."
> Thus the Mega must supply 5 V to `ISOVDD`, and the Mega GND must go to `ISOGND`.
> `claude.md` and `INTEGRATION_PLAN.md` are correct. `PIN_MAP.md` line 95 says that the ODrive
> supplies its own 5 V logic. This is incorrect.
> If the isolator has no power, the serial link is dead. A dead link gives the same symptoms as an
> encoder fault. Find this before you look for a firmware fault.

**Step 1.6** — Measure the voltage between `ISOVDD` and `ISOGND` with the power on. Record the value.
The correct value is between 3.3 V and 5 V.

**Step 1.7** — Send the photograph and the measurements to the owner. The owner will then correct
the four documents.

> **NOTE — the same fault is in the firmware**
> The command `M753` writes these two lines: "Mega pin 16 (TX2) -> ODrive J11 pin 4 (RX)" and
> "Mega pin 17 (RX2) -> ODrive J11 pin 3 (TX)". These lines are text only. The firmware does not
> know the connector. Do not use these lines as proof. `M753.cpp` must also be corrected.

### Find which firmware is on the Mega

Do these steps after the wiring inspection. Apply the power.

**Step 1.8** — Connect to the machine. Send `M752`.

**Step 1.9** — Look at the `STATE:` lines. Use this table to find the firmware:

| The machine writes | The firmware is |
|---|---|
| `STATE:INDEX_SETTLE` | the production firmware (April 2026). This is expected. |
| `STATE:HOME_SETTLE` | the new stack tip. Tell the owner immediately. |

**Step 1.10** — Record the answer. Tell the owner before you start Lane B.

> **NOTE**
> The two firmware builds write different words for the same phase. This is the quickest way to
> find which firmware is on the board. The owner expects the production firmware.

---

## Task 2 — Check the index reference of the encoder

This task has the highest value in this sheet. Four other tasks wait for its result.

This task uses only the ODrive and the laptop. Marlin is not part of this task.

> **NOTE**
> A script with the name `odrive_report.py` is not in the repository. Do the steps by hand.

> **IMPORTANT — the Mega is not the cause**
> Two compiled firmware files were examined: the production firmware (April 2026) and the new
> stack tip (August 2026). **Neither one writes any index configuration to the ODrive.**
> Neither file contains `pos_vel_mapper`, `commutation_mapper`, `use_index_gpio`, `index_offset`,
> `gpio10`, `inc_encoder` or `save_configuration`.
> Both files only request an index search (`w axis0.requested_state 6`) and then command an
> absolute position (`t 0 <value>`).
> Thus the index configuration exists only in the memory of the ODrive. The Mega never writes it.
> The Mega never reads it back.
> The machine made good parts before. The Mega firmware did not change. Therefore look for a
> change in the ODrive, not in the Mega. Steps 2.10 to 2.12 examine this.

**Step 2.1** — Remove power from the Mega, or disconnect the Mega from the ODrive.

**Step 2.2** — Connect the native USB port of the ODrive to the laptop.

**Step 2.3** — Start `odrivetool`.

**Step 2.4** — Record the firmware version of the ODrive. All the steps that follow are correct
only for version 0.6.x.

**Step 2.5** — Read and record these values:

| Property | Correct value |
|---|---|
| `odrv0.config.gpio10_mode` | `0` (DIGITAL). The value `17` (AUTO) is not correct. |
| `axis0.commutation_mapper.config.use_index_gpio` | `True` |
| `axis0.commutation_mapper.config.index_gpio` | `10` |
| `axis0.pos_vel_mapper.config.use_index_gpio` | `True` |
| `axis0.pos_vel_mapper.config.index_gpio` | `10` |
| `axis0.pos_vel_mapper.config.index_offset` | A value is set |
| `axis0.pos_vel_mapper.config.index_offset_valid` | `True` |
| `axis0.config.startup_encoder_index_search` | Record the value |
| `inc_encoder0.config.cpr` | 4 multiplied by the PPR of the AMT102 |

> **WARNING — INJURY TO PERSONS**
> Step 2.6 turns the motor. An encoder index search rotates the shaft.
> Steps 2.1 to 2.5 only read data and move nothing. You can do them alone.
> **Do step 2.6 only when a person is in the room.** Remove all items from the chuck.
> Close the lid.

**Step 2.6** — Do the empirical test. This test is the most important part of the task.

> **NOTE — you must move the shaft first**
> The encoder counts from 0 when the ODrive gets power. If nobody turned the chuck,
> `pos_estimate` is already near 0. Then a result of near 0 after the index search tells you
> nothing: you cannot see the difference between "the encoder found the index mark" and "the
> chuck never moved". Move the chuck first, so the value is clearly not 0.

1. Send `M754`. Read `axis0.current_state`. It must be `1` (IDLE). The motor is then free.
2. Turn the chuck by hand. Two or three full turns.
3. Send `M754`. Read `axis0.pos_estimate`. Record it. Call it **P1**.
   P1 must now be near 2 or 3, not near 0. If P1 is still near 0, the encoder does not count.
   Stop and tell the owner.
4. Do an index search. Send `M752`, or use `odrivetool`.
5. Send `M754`. Read `axis0.pos_estimate`. Record it. Call it **P2**.

**Step 2.7** — Read the result:

- If **P2** is near 0, the encoder **has** an index reference. The design of the firmware is correct.
- If **P2** is the same as **P1**, the encoder **does not have** an index reference. The design of
  the firmware is built on an incorrect assumption.

**Step 2.8** — Send **P1**, **P2** and all the values of Step 2.5 to the owner.

**Step 2.9** — If you change a property, send `odrv0.save_configuration()`.

### Find what changed in the ODrive

The Mega firmware did not change between good production and the fault. Thus something in the
ODrive changed. These three steps look for it.

**Step 2.10** — Record the exact firmware version of the ODrive. Ask the owner which version the
machine used during production. A version change can erase the configuration, or can move the
property to a new name.

**Step 2.11** — Read `odrv0.axis0.config.startup_encoder_index_search` and
`odrv0.config.gpio10_mode`. If both hold their default values, the configuration was probably
erased. An erase can happen after a firmware update, after `erase_configuration()`, or after a
`save_configuration()` that did not complete.

**Step 2.12** — Look for a record of the first ODrive setup. Look for a script, a text file, or a
log of an `odrivetool` session. This record is the recipe to build the configuration again.
Nothing in this repository holds it. Ask each colleague.

> **NOTE**
> The AMT102 is an incremental encoder. It loses its position at each power-off. The index pulse
> is the only absolute reference. If `gpio10_mode` is not `0` (DIGITAL), the ODrive never reads
> the index pulse. The command `t 0 <value>` then moves to a position that has no meaning.
> This agrees with the fault that you see.

> **STOP CONDITION**
> If the encoder does not have an index reference, tell the owner and stop. Four future tasks
> (issues #45, #52, #54 and #55) are built on the opposite assumption. The owner must plan again.
> Lane B does not stop. Continue with Task 3.

### Results — 2026-08-13, steps 2.1 to 2.5

**The encoder HAS an index reference. The stop condition above did not occur.**

ODrive firmware v0.6.11, read with `odrivetool` on the native USB port.

| Property | Value | Correct? |
|---|---|---|
| `config.gpio10_mode` | `0` (DIGITAL) | Yes |
| `axis0.commutation_mapper.config.use_index_gpio` | `True` | Yes |
| `axis0.commutation_mapper.config.index_gpio` | `10` | Yes |
| `axis0.commutation_mapper.config.index_offset` | `3.5765047` | Set |
| `axis0.pos_vel_mapper.config.use_index_gpio` | `True` | Yes |
| `axis0.pos_vel_mapper.config.index_gpio` | `10` | Yes |
| `axis0.pos_vel_mapper.config.index_offset` | `0.0` | Set |
| `axis0.pos_vel_mapper.config.index_offset_valid` | `True` | Yes |
| `axis0.config.startup_encoder_index_search` | `False` | See the note |
| `inc_encoder0.config.cpr` | `8192` | Yes (2048 PPR × 4) |

Step 2.6 is not done. It turns the motor and needs a person in the room.

> **NOTE — the ODrive does not search for the index when it starts**
> `startup_encoder_index_search` is `False`. Thus the ODrive does not know its absolute position
> after each power cycle. It knows where the index mark is, but not where the motor is, until
> something crosses the index mark. The firmware does this search in `boot()`.

> **CAUTION — this configuration is in the ODrive only**
> These values are in the memory of the ODrive. They are not in the repository. If somebody does a
> factory reset, installs new ODrive firmware, or replaces the board, the values are lost. Nothing
> puts them back. Record them before you do any of these three things.

---

# LANE B — THE FIRMWARE

## Task 3 — Build the firmware

**Step 3.1** — Get the branch `fix/44-feedback-numeric-validation`. This branch is the tip. It
contains all nine changes.

```bash
git fetch origin && git checkout fix/44-feedback-numeric-validation
```

**Step 3.2** — Build the firmware.

```bash
cd Marlin-2.1.2.7 && pio run -e mega2560
```

**Step 3.3** — Record the flash percentage and the RAM percentage. The expected values are
flash 29.7 % and RAM 42.7 %. If your values are very different, stop and tell the owner.

**Step 3.4** — If the build fails, stop. Send the full output of the build to the owner.

---

## Task 4 — Install the firmware and do the first test

> **CAUTION — DAMAGE TO EQUIPMENT**
> Remove all items from the chuck before this task. Close the lid.

**Step 4.1** — Install the firmware on the Mega.

```bash
pio run -e mega2560 -t upload
```

**Step 4.2** — Open `RMR_Controller.html` in Chrome. Connect at 250000 baud.

**Step 4.3** — Send `M753`. This command examines the serial link to the ODrive. It does not move
anything. It is the correct first command on a cold machine.

**Step 4.4** — Make sure that `M753` reports the bus voltage. The expected value is about 24 V.

**Step 4.5** — If `M753` gives no reply, the serial link is dead. Go back to Task 1. Do not
continue in this lane.

---

## Task 5 — Test the normal G-code (the most important test)

This test has the highest consequence in Lane B. The change `EMERGENCY_PARSER` alters the serial
receive path for **every** command, not only for the spin coater commands.

**Step 5.1** — Send `G28`. Make sure that all the axes go to the home position in the correct
sequence: Z, then Y, then B, then X, then A.

**Step 5.2** — Move each axis with `G1`. Make sure that each axis moves the correct distance in
the correct direction.

**Step 5.3** — Send `M119`. Make sure that each end stop reports the correct condition.

**Step 5.4** — Load `DemoProgram.gcode` into the Program Runner. Run it. Make sure that it
completes with no lost line and no incorrect line.

**Step 5.5** — Send many jog commands quickly. Make sure that Marlin does not lose a command.

> **NOTE**
> The change `EMERGENCY_PARSER` also compiles the commands `M0` and `M1` into the firmware.
> Before this change, `M0` gave the reply "Unknown command". Now `M0` stops the program until an
> `M108` command comes. The files `fullcode.gcode` and `DemoProgram.gcode` contain no `M0` and no
> `M1`. If you use a different G-code file, look for `M0` and `M1` in it first.

**Step 5.6** — If any part of Task 5 fails, stop Lane B. Tell the owner immediately.

### Results — 2026-08-13, partial

The new firmware is on the Mega. `M115` reports the build date `Aug 12 2026 16:21:55` and
`Cap:EMERGENCY_PARSER:1`. Before this, the board had firmware from `Aug 6 2026` with
`Cap:EMERGENCY_PARSER:0`.

> **NOTE — how to know which firmware is on the board**
> Send `M115`. Read the two values below. If they are not correct, the board has the old firmware
> and the test result is not valid.
> `Cap:EMERGENCY_PARSER:1` and a build date of the day you installed it.

| Step | Result | Note |
|---|---|---|
| 5.1 `G28` | **PASS** | Homing operated correctly in the full sequence. |
| 5.2 `G1` each axis | **PASS** | All axes moved and reported correctly. |
| 5.3 `M119` | **PASS** | All five end stops reported `open` when clear of the limits. |
| 5.4 `DemoProgram.gcode` | **PART** | The program ran. Nobody counted the lines for losses. |
| 5.5 Many jog commands | **NOT DONE** | — |

Also correct at 250000 baud with the new firmware: `M115`, `M503`, `M114`. The serial link does not
lose data.

**`EMERGENCY_PARSER` did not break the gantry.** Homing, motion and the serial path all operate. This
was the largest risk in the stack.

The first `M119` reported `y_min: TRIGGERED`. This was correct: the gantry was parked at the Y
minimum. When the axis was moved off the limit, the end stop reported `open`. There is no fault.

`M114` reported `A:343.00`. This is correct. The A axis homes to MAX, so Marlin uses the maximum
travel as its start position.

`M115` also reported `Cap:EEPROM:0`. This is issue #59. The buttons `M500` and `M501` in both UIs
cannot do anything. Do not use them.

> **NOTE — the serial port stops after you install firmware**
> The Mega gets a new device number when the new firmware starts. The browser keeps the old one.
> The UI then cannot connect, and the name `/dev/rmr-mega` can be absent.
> You do not have to remove the USB cable. Do this on the laptop instead:
> ```
> DEV=$(basename $(dirname $(grep -l 2341 /sys/bus/usb/devices/*/idVendor)))
> echo "$DEV" | sudo tee /sys/bus/usb/drivers/usb/unbind
> sleep 2
> echo "$DEV" | sudo tee /sys/bus/usb/drivers/usb/bind
> ```
> Then push **Connect** in the UI again and select the port again. Issues #64 and #65.

---

## Task 6 — Test the emergency stop (pull request #51, issue #40)

> **WARNING — INJURY TO PERSONS**
> Close the lid. The chuck turns freely after `M112`. It takes time to stop.

**Step 6.1** — Send `M750 S1000 D30 A3 C3 H0`.

**Step 6.2** — Send `M112` while the chuck turns. The chuck must turn freely and then stop.
Marlin stops. This is correct.

**Step 6.3** — Disconnect the USB cable. Connect it again. Marlin must start. The chuck must stay
stopped.

**Step 6.4** — Start a spin cycle again. Disconnect the USB cable while the chuck turns. Do not
send `M112`. Connect the cable again. The chuck must stop in a few seconds.

**Step 6.5** — Start a spin cycle again. Send many jog commands. Then send `M112`. The chuck must
stop.

**Step 6.6** — Send `M750`, `M751` and `M752` in the usual way. Make sure that they operate as before.

**Step 6.7** — Record all the results.

---

## Task 7 — Test the honest failure exits (pull request #56, issues #41 and #43)

> **NOTE**
> This change makes some failures loud that were silent before. You will see failures on
> operations that looked correct before. This is the intended result. Do not report it as a new fault.

**Step 7.1** — Send `M750 S1000 D10 A3 C3 H1`. Make sure that it ends with `OK: CYCLE_COMPLETE`.

**Step 7.2** — Send `M752` on a good machine. Make sure that it ends with `OK: INDEX_COMPLETE`.

**Step 7.3** — Record the value of `procedure_result` that the firmware writes.

> **QUESTION FOR THE OWNER**
> If a home operation that looks correct reports a `procedure_result` that is not 0, tell the owner.
> The firmware treats a non-zero value as a hard failure. That rule must then change.

**Step 7.4** — Make a failure on purpose. Disconnect the index wire of the encoder.

**Step 7.5** — Send `M752`. Make sure that:
- The firmware writes `ERR:` lines with `procedure_result`, `active_errors` and `disarm_reason`.
- The chuck stops.
- The datum does **not** change. Read the Home value before and after.

**Step 7.6** — Send `M750 S1000 D10 A3 C3 H1` with the same failure. Make sure that the last line
is `ERR: CYCLE_COMPLETE_NO_HOME`. Make sure that the datum does not change.

**Step 7.7** — Connect the index wire again.

**Step 7.8** — Remove the power from the machine. Apply the power again. Send `M752`. Make sure
that a new `WARN:` line comes. The line tells you which type of datum the firmware made.

---

## Task 8 — Test the bounded waits (pull request #57, issue #42)

**Step 8.1** — Send `M750 S1000 D10 A3 C3 H1`. Make sure that it operates as before. This is the
most important check of this task.

**Step 8.2** — Disconnect the serial cable of the ODrive while the firmware measures the speed.
Make sure that `MEASURE_LINK_LOST` comes in about 3 seconds. Make sure that **no** statistics
block comes. A value of `MinRPM=1000000000` is a fault.

**Step 8.3** — Connect the cable again. Send `M750 S1000 D10 A3 C3 H0`. Disconnect the cable
while the chuck slows down. Make sure that `DECEL_LINK_LOST` comes in about 3 seconds. Marlin
must not stop for a long time.

**Step 8.4** — Make sure that `M750` never stops the machine for more than 2 minutes in any of
the tests above.

---

## Task 9 — Measure the coast time (a question that the owner needs)

**Step 9.1** — Remove all items from the chuck. Close the lid.

**Step 9.2** — Send `M750 S5000 D30 A5 C1 H0`.

**Step 9.3** — Use the stopwatch. Measure the time from the start of the slow-down to the stop of
the chuck. Record the time in seconds.

**Step 9.4** — Make sure that the cycle either completes, or reports `DECEL_STALL` correctly.

**Step 9.5** — Send the measured time to the owner. The time limits in the firmware are estimates
today. The owner needs a real value.

---

## Task 10 — Test the strict parser (pull request #58, issue #44)

**Step 10.1** — Send `M750 S1000 D10 A3 C3 H0`. Then send `M752` immediately after it. This is the
most important check of this task. `M752` must complete correctly. It must **not** report
`no consistent position read`.

**Step 10.2** — Send `M750 S1000 D10 A3 C3 H1`. Make sure that it operates as before.

**Step 10.3** — Send `M751`. Make sure that it operates as before.

**Step 10.4** — Send `M753`. Make sure that it reports the bus voltage.

**Step 10.5** — If any command reports `no consistent position read` on a good machine, record the
full log. Send the log to the owner.

---

## Task 11 — Merge the stack

Do this task only after Tasks 4 to 10 pass.

> **CAUTION — DAMAGE TO THE RECORD**
> The six pull requests are in sequence. Each one uses the one before it as its base. Merge them
> in this sequence only. Do not change the base of a pull request to `main`. Do not put the six
> into one.

**Step 11.1** — Merge in this sequence:

```
#38  ->  #39  ->  #51  ->  #56  ->  #57  ->  #58
```

**Step 11.2** — After each merge, change the base of the next pull request to the branch that you
just merged into.

**Step 11.3** — Tell the owner after the last merge.

> **QUESTION FOR THE OWNER**
> Ask the owner to choose: merge all six after all the tests pass, or merge each one as its own
> tests pass.

---

# LANE D — THE SHOP

## Task 12 — Test the relays (issue #18)

Someone replaced the relay modules. The new modules are active-HIGH. The old modules were
active-LOW. Each load is on the contact `NO`.

> **WARNING — INJURY TO PERSONS**
> Put on UV eye protection before Step 12.3.

**Step 12.1** — Connect the gas supply to the solenoid valve.

**Step 12.2** — Send `M42 P42 S1`. The valve must open. Send `M42 P42 S0`. The valve must close.

**Step 12.3** — Send `M42 P4 S1`. The UV lamp must come on. Send `M42 P4 S0`. The lamp must go off.

**Step 12.4** — Remove the power from the machine. Apply the power again. Make sure that both
relays stay de-energized at power-on. This is a safety condition.

**Step 12.5** — Send each command 20 times. Make sure that the relay operates every time. A relay
that operates one time and then stops is the fault of gotcha 12.

**Step 12.6** — Find if a brake resistor is fitted to the ODrive. Look at the terminals `AUX`.
Record the answer. Find what absorbs the regenerated energy on this power supply.

**Step 12.7** — Send the answer of Step 12.6 to the owner. This answer controls a future decision
about the emergency stop.

---

## Task 13 — Diagnose the gripper servo (issue #53)

The gripper servo shakes while it holds a position. Do the steps in this sequence. The cheapest
step is first.

**Step 13.1** — Connect the oscilloscope to the signal wire of Servo 0 at the connector.

**Step 13.2** — Send `M280 P0 S120`. Look at the pulse while the servo holds the position.
Measure the change in the pulse width. Record the value.

- A large and irregular change shows a firmware timing fault.
- A clean and stable pulse shows a fault in the servo or in the mechanism.

**Step 13.3** — Connect the oscilloscope to the 5 V supply at the servo connector. Look at the
voltage while the servo shakes. Record the value.

**Step 13.4** — Compare the shake when the machine is not moving with the shake when an axis moves
quickly. If the shake changes with the step rate, the fault is in the firmware timing.

**Step 13.5** — Send `M280 P1 S90` to the lid servo with no load. Find if the lid servo shakes in
the same way. This step separates an electrical fault from a mechanical fault.

**Step 13.6** — Install a digital servo in place of the analog servo. Find if the shake stops.

**Step 13.7** — Send all the measurements to the owner.

---

# LANE C — THE USER INTERFACE

These two tasks need no hardware. A person with a laptop can do them at the same time as the
other lanes.

## Task 14 — Correct the serial contract of the two UI files (issue #47)

Both UI files find the tokens of the firmware with `String.includes()`. The first match wins. Some
failure tokens contain a success token inside them. The operator then sees a green success for a
red failure.

| The firmware writes | The UI finds | The operator sees |
|---|---|---|
| `ERR: CYCLE_COMPLETE_NO_HOME` | `CYCLE_COMPLETE` | "Cycle complete", in green |
| `ERR: HOME_SET_FAILED` | `HOME_SET` | "Home datum set" |
| `STATE:HOME_SETTLE` | `HOME_SET` | "Home datum set", while the chuck still moves |

**Step 14.1** — Change the two files to find the exact token. Do not use `includes()`.

**Step 14.2** — Add the tokens that are absent: `HOME_SETTLE`, `MEASURE_LINK_LOST`,
`DECEL_LINK_LOST` and `DECEL_STALL`.

**Step 14.3** — Remove the token `INDEX_SETTLE`. The firmware does not write it now.

**Step 14.4** — Show the `ERR:` lines and the `WARN:` lines to the operator.

> **NOTE**
> To add a new entry to the map is not a correction. The map is in the sequence of insertion and
> the first match wins. You must change the method of comparison.

**Step 14.5** — Do this work against the tokens of the stack tip, not the tokens of `main`.

**Step 14.6** — Do not make a new UI file. `RMR_Controller.html` and `RMR_Touch.html` are the UI
of the machine.

---

## Task 15 — Correct the Program Runner (issue #48)

The Program Runner waits for `ok` before it sends the next line. The automatic position report
(`M114`, one time each second) also writes `ok`. The runner counts those. It then sends many lines
quickly after a long `M750` command.

**Step 15.1** — Correct this in `RMR_Controller.html` **and** in `RMR_Touch.html`. The issue names
only the first file. The same fault is in both.

> **QUESTION FOR THE OWNER**
> Ask the owner to choose one method:
> 1. Stop the automatic `M114` report while a program runs. This is simple. The operator loses the
>    live position during a run.
> 2. Use line numbers to match each `ok` to its command. This is more work. The operator keeps the
>    live position.

---

## 7. What to send to the owner

Send one report for each task. Put this in each report:

1. The task number.
2. The date and the time.
3. Pass or fail for each step.
4. The full text of each `ERR:` line and each `WARN:` line. Do not summarize them.
5. All measured values.
6. A photograph if the task asks for one.

---

## 8. The questions that only the bench can answer

Send an answer to each of these. The owner cannot continue without them.

| No. | Question | Task |
|---|---|---|
| 1 | After an index search, does `pos_estimate` go to near 0, or hold its value? | 2 |
| 2 | How many seconds does the chuck need to stop from 5000 RPM? | 9 |
| 3 | Does a good `M752` ever report a `procedure_result` that is not 0? | 7 |
| 4 | Is a brake resistor fitted? What absorbs the regenerated energy? | 12 |
| 5 | Does normal G-code still operate correctly at 250000 baud? **Part answered 2026-08-13: the serial link is correct. Motion is not tested.** | 5 |
| 6 | Does `M112` stop the chuck? Does the board start correctly after it? | 6 |
| 7 | Does `M752` operate correctly immediately after `M750`? | 10 |
| 8 | Does the lid servo shake in the same way as the gripper servo? | 13 |
| 9 | Do both relays operate correctly, and stay off at power-on? | 12 |
| 10 | Does the Mega supply 5 V to `ISOVDD` on J11 pin 9? | 1 |
| 11 | Is the UART on J11 pin 7 and pin 8, and not on pin 3 and pin 4? | 1 |
| 12 | Which firmware is on the Mega — `INDEX_SETTLE` or `HOME_SETTLE`? | 1 |
| 13 | Which ODrive firmware version did the machine use during production? | 2 |
| 14 | Does any record of the first ODrive setup exist anywhere? | 2 |

---

## 9. Conditions that stop the work

Stop and tell the owner if one of these happens:

1. Task 5 fails. Normal G-code has a new fault.
2. Task 2 shows that the encoder has no index reference. Lane B continues, but no new firmware
   design work can start.
3. A good machine reports `no consistent position read`.
4. A good `M752` reports a `procedure_result` that is not 0.
5. The build gives a flash percentage of more than 90 %.
6. A relay stays energized at power-on.

---

## 10. Rules for a change to the firmware

If you write a change to the firmware, obey these rules:

1. One issue, one branch, one pull request. Do not put unrelated corrections together.
2. Build the firmware before you push it.
3. Write the bench steps in the body of the pull request. Write them for a person who does not
   know the history.
4. Correctness is more important than speed. The machine makes real parts.
5. Before you commit, answer these four questions:
   - What was silently correct before, and will now fail loudly? Who handles that failure?
   - Does a new limit imply a physical limit (a speed, a time or a distance) that I did not calculate?
   - Does this change make a document, a comment or a UI text false?
   - Would a good machine now report a fault?

---

## 11. Decisions that you must not change

| No. | Decision | Reason |
|---|---|---|
| 1 | The emergency stop lets the chuck turn freely. It does not command a fast stop. | No one confirmed a brake resistor. A fast stop can damage the DC bus. |
| 2 | After `M112`, recovery is a reset of the board. `M999` does not work. | The firmware stops the interrupts and never receives `M999`. |
| 3 | A failed home operation never moves an existing datum. | The old automatic correction erased the operator datum silently. |
| 4 | A datum is never taken from a chuck that moves. | An incorrect datum breaks the registration between layers. |
| 5 | The dispense volume and the UV cure time belong in the GUI, not in the G-code. | These values change with each elastomer. |
| 6 | `RMR_Controller.html` and `RMR_Touch.html` are the UI. Do not make a new one. | Owner decision. |
