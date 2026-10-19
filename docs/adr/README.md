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
0008 | The control box is a 2020 frame in two modules, not off-the-shelf enclosures | Accepted; materials and sourcing superseded by 0009 | `docs/wiring` sheets 3 and 4, plate DXFs, `bom_frame.csv`
0009 | The control box is built from Amazon parts: shop-cut 6 mm-slot 2020, 1/16 in aluminum decks, acrylic walls, every metal part home-run to PE | Accepted; ground bar sourcing superseded by 0014 | `docs/wiring` sheets 3 and 4, `bom_frame.csv`
0010 | The control box layout lays the 24 V PSU flat and follows the CP-SAT packing study | Accepted, on the PSU mounting flat | `docs/wiring` sheets 3 and 4, plate and panel DXFs
0011 | The lower bay is set by the lower wall's grommet, not by the tallest lower part | Accepted | `tools/draw_wiring.py` frame stack, `docs/wiring` sheets 3 and 4, plate and panel DXFs
0012 | A bent 5052 wall closes the 110 VAC compartment, and the 110 V door cable leaves through the back panel | Rejected by the owner; see 0013 | `tools/draw_wiring.py`, `docs/wiring` sheets 3 to 5, base plate, back panel and wall DXFs
0013 | No wall around the 110 VAC parts: the compartment is a zone of the lower deck | Accepted | `tools/draw_wiring.py`, `docs/wiring` sheets 3 and 4, base plate DXF, `bom_frame.csv`
0014 | The control box is drawn and bought for the parts actually ordered: a 12-way FB1, aluminum DIN rail, and the ground bars, PE blocks and copper power wire bought | Proposed (issue #158) | `tools/draw_wiring.py`, `tools/layout_study/`, `docs/wiring` sheets 1 to 3, the lower left panel DXF, `bom_frame.csv`
0015 | The box is held to the gantry by four spare cast brackets on its lower posts, and it comes out by lifting 38 mm and sliding forward under a raised middle member | Proposed (issue #158) | `tools/draw_wiring.py`, `tools/build_box_model.py`, `docs/wiring` sheets 4 and 5, the lower front and back panel DXFs, `bom_frame.csv`

Format: a title line, then `Status; Date; Scope`, then `Context`, `Decision`, `Rejected`,
`Consequences` and `Revisit if`, one line each. Add a new file for a new decision; do not edit an
accepted one except to mark it superseded.
