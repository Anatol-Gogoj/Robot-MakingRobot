# ADR index

Durable design decisions for this repo, one file each. ADRs 0001 to 0006 carry handoff decisions 1, 3,
4, 5, 6, 7, 9, 10 and 11, first recorded in the session handoffs of August 2026. Those handoffs left the
repo in issue #129; each ADR gives the handoff decision number it came from, so older comments and notes
can still be traced. Decision 2 (`M112` needs a board reset) is `claude.md` gotcha 6. Decision 8 was a
one-off status note, 12 and 15 are bench-access and process rules kept outside the repo, and 13 and 14
belong to the unmerged PR #78 and travel with its redo.

ID | title | status | scope
---|---|---|---
0001 | Spin coater E-stop disarms the ODrive to IDLE; no commanded braking | Accepted | spincoater firmware, `kill()`
0002 | An existing spin-coater datum is never moved silently | Accepted | `spincoater.cpp` datum and homing
0003 | An unreadable `procedure_result` means unverified, not failed | Accepted | `spincoater.cpp` index search
0004 | No write passthrough to the ODrive from G-code | Accepted | M75x commands
0005 | The two HTML pages are the only UIs, and process parameters live in them | Accepted | `RMR_Controller.html`, `RMR_Touch.html`, G-code programs
0006 | Over Web Serial the Touch UI reconnects by itself and the Controller does not | Accepted | both UIs, serial transport

Format: a title line, then `Status; Date; Scope`, then `Context`, `Decision`, `Rejected`,
`Consequences` and `Revisit if`, one line each. Add a new file for a new decision; do not edit an
accepted one except to mark it superseded.
