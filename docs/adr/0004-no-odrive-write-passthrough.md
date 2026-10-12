# ADR-0004: No write passthrough to the ODrive from G-code
Status: Accepted; Date: 2026-08-14 (handoff decision 10); Scope: M750-M754 and any future ODrive command
Context: The ODrive's native USB link failed on 2026-08-13, so its configuration had to be read over the Mega's Serial2 instead. A general G-code passthrough to the ODrive would have been the quickest way to do that.
Decision: The Mega exposes only purpose-built commands. `M754` reads a fixed set of encoder properties and writes nothing. No G-code forwards arbitrary text, and in particular no `w` writes, to the ODrive.
Rejected: A raw passthrough (for example an `M7xx` that forwards its argument): it puts `w axis0.requested_state 8` one text box away from spinning the chuck, with no interlock in the path
Consequences: Easier: every write to the drive is in reviewed firmware with its own guards. Harder: ODrive tuning and configuration need `odrivetool` over the ODrive's own USB, and a new read needs a firmware change.
Revisit if: a write path is needed and can carry its own interlocks (lid closed, motor power known, axis idle).
