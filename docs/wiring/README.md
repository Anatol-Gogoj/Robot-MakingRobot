# Control panel wiring drawings

Five legal-size sheets (14 x 8.5 in, landscape) of the planned layered E-stop control panel, and the two
deck plates, the side and top panels and the mains wall as DXF:

| File | What it shows |
|---|---|
| `wiring_schematic_legal.pdf` | Sheet 1: every circuit on one page: mains and K1, PSU, K2 and the E-stop latch, FB1 and FB2 with fuse values, the seven drivers and the ODrive, Mega and Pi I/O, star ground S and PE. |
| `wiring_din_rails_legal.pdf` | Sheet 2: the same circuits on five DIN rails with wire ducts, terminal blocks X0 to X8, and the route of every wire. |
| `packing_study_legal.pdf` | Sheet 3: packing study for an 18 x 13 x 11 in box (depth x width x height): a 2020 frame with two decks on 1/16 in aluminum plates and acrylic walls, the lower deck (110 VAC and 24 V power) on a base plate under the frame, the upper one (drives and logic) on the mid ring, at 1:3.5, every part at its real size (measured, or read from its datasheet or listing drawing; sources in the generator's `PartSize`). Dashed parts have assumed sizes. The arrangement is layout 3b of the CP-SAT packing study (ADR-0010): the 24 V PSU lies flat along the right wall with its fan toward a vent in the lower right panel, every rail runs along the depth except the short SSR rail, and the motor cables leave by a back run behind every rail. The generator holds each block centre to `tools/layout_study/layout3b_build.json`, rescores the drawn layout with the study's `Score()` (no solver needed), and refuses any overlap, any plate slot over the 110 VAC compartment, and any part taller than its bay. The lower bay is 106 mm because the lower left grommet sets it (ADR-0011). |
| `frame_plates_legal.pdf` | Sheet 4: the frame in two modules, like a platform-framed house: the upper module (mid ring, upper plate, upper posts, lid ring) is built on the bench and drops onto four locating studs in the lower posts. Both plates with every hole, the frame from the left and from the front, a 2:1 detail of a plate screwed to a ring rail, the checked screw lengths, PE bonding, the cut list from 1000 mm sticks, the plates and panels with the nest sheet of each and their cut-outs, and the assembly order. |
| `mains_wall_legal.pdf` | Sheet 5: the mains compartment wall that closes the 110 VAC compartment on the lower deck (issue #146). It is two pieces of 1/16 in 5052 cut from the upper plate sheet's offcut, drawn as flat patterns with bend lines and hole ordinates at 1:2, on the base plate at 1:5, and in section at a flange screw. Wall A runs along the depth and wall B across it, with a corner tab bent onto A. Each piece has a foot flange screwed to the base plate, and an end tab that closes the gap between the bottom and mid rings up to the panel. A 40 x 13 mm edge-trimmed pass-through in A takes the PSU's DC leads. The 110 V door cable does not cross the wall: it leaves through an M20 gland in the aluminum back panel. |
| `bom_frame.csv` | Bill of materials for the frame, plates, panels and PE bonding (ADR-0009), with a source, part number or ASIN, pack size, price and link per line: 6 mm-slot 2020 rail as 1000 mm sticks cut in the shop, brackets, roll-in spring T-nuts, screws, feet, aluminum and cast acrylic sheet, 12 AWG wire and lugs from Amazon (prices read 2026-10-17), the slotted duct from McMaster (prices of 2026-10-15), and the ground bars, M5 tap and some 12 AWG from the owner's stock. A Cutting tools section prices what it takes to cut the 1000 mm sticks in house (prices read 2026-10-18). The saw is a Metabo HPT C10FCG2 10 in miter saw, whose owner's manual lists aluminum sash among its applications, fitted with a Diablo D10100N 100-tooth thin-aluminum blade. A Kinex DIN 875/1 try square sets the blade and checks each end. The length stop is a spare stick clamped in line with the fence, with a spare corner bracket as the stop. A deburring tool and a face shield complete the set; the generator checks the blade against the saw and the cut list's kerf. Check prices before ordering. Quantities come from the same constants as sheets 3 and 4: the cut list, the panel nest and the bond points. The electrical parts are on the original BoM. |
| `deck_base_plate.dxf`, `deck_upper_plate.dxf` | The two 1/16 in aluminum plates. Cut the upper one from 1/8 in acrylic on the laser as a template, then drill and nibble both plates through it (the base plate has the same post and ring holes, plus its own PE stud): ASCII DXF R12, millimetres, one layer `CUT`, closed polylines for the outline and the slots, circles for the holes. The origin is the plate's front-left corner seen from above. DIN-rail holes are not in them. |
| `wall_mains_flat.dxf` | Both wall flat patterns, seen from the mains side: outlines, holes and the pass-through on layer `CUT`, fold lines on layer `BEND` (LINE entities). The bend deduction assumes a K factor of 0.42, so bend a test strip first. The generator reads it back like the panel DXFs. |
| `panels_acrylic_1.dxf` to `panels_acrylic_3.dxf`, `panel_lower_back_template.dxf` | The side and top panels, one file per 24 x 18 in sheet of 1/8 in cast acrylic, each part where `NestPlan()` puts it (origin at the sheet's corner, every part inside the 813 x 457 mm laser bed), and the aluminum lower back panel alone as a template: cut it from the spare acrylic sheet beside the upper plate's template, then drill and nibble the 1/16 in aluminum through it. Each part has its outline and its M5 screw holes (5.5 mm) on the rail slot centre lines; the top also has the vent slots over the TB6600 row and a 10 mm hole over each of the four lid screws, and the back panel its PE stud and the 20.5 mm hole for the door cable's M20 gland. The cables leave through five desk grommets (50 mm holes, two 4-packs): two in the upper left panel (the field cables, and the motor cables at the end of their back run), one each in the upper front, upper right and lower left panels; a 64 mm acrylic ring, nested on acrylic 2's offcut, presses onto each grommet's sleeve behind the wall. The hole and the ring bore come from the listing's drawing: caliper one grommet before cutting. Parts are drawn from outside: u along x with the front at 0 (side panels and top) or along y with the left at 0 (front and back), v up; turn a part over to match. The same DXF format as the plates, with each part's inner cuts before its outline. The generator reads every file back and refuses a web under 2 mm between two cuts, a cut and an edge, or two parts. **Not in them yet, placeholders until the owner's data:** the PSU vent in the lower right side panel (the fan's diameter sets its slot count) and the IEC inlet's cut-out in the back panel. Hold `panels_acrylic_3.dxf` and the template until those are in. |

The design comes from the control panel wiring reference of 2026-10-06. It is the planned panel, not the
machine as it is wired today. Open items (tower common polarity, lid feed, valve coil, servo 6 V rating,
which side powers ODrive J11 logic) and the firmware gap on pins 4 and 42 are listed in sheet 1's notes.

Every wire is drawn with horizontal and vertical segments only; `Sheet.Wire()` in the generator refuses a
diagonal. Colors are Paul Tol's vibrant scheme.

## Print

Paper: Legal. Orientation: landscape. Scale: 100 % (actual size), not "fit to page". The drawings keep a
4.5 mm margin inside the paper edge.

## Regenerate

```bash
python tools/draw_wiring.py
```

That rewrites the five SVGs, the seven DXFs and the BoM here, reads each panel DXF back to check its webs, and
lists the panel cut-outs that are still placeholders (`PanelOpen()`). Sheets 3 and 4 and the DXFs share one set
of frame dimensions in the generator (`BoxD`, `LowBay`, `DeckSolids()`, `PlateGeom()`, `PanelGeom()` and the
constants around them), so a change there moves all of them together. To make the PDFs, open each SVG in Edge or Chrome and print it to PDF on
Legal landscape with no margins, or use headless Edge with `--print-to-pdf` on a page whose
`@page` size is `14in 8.5in`.

```bash
python tools/check_wiring_pins.py
```

That checks every Mega pin on both sheets against `pins_RAMPS_14_RMR.h`, `pins_RAMPS.h` and
`Configuration_adv.h`, and confirms each pin label is present in both SVGs.
