# Archived E-axis syringe programs

These files are kept for reference only. They are not maintained, `tests/run.mjs` does not run
them, and nothing in the live repo reads them. Do not send them to the machine.

## What each file was

| file | what it was |
|---|---|
| `fullcode.gcode` | Production DEA layer program: home, `M753` / `M752` / `M751` spincoater start-up, dispense, lid close, `M750 S1000 D50 A3 C3 H1`, UV cure, then the filter pick, press and dispose moves. |
| `LayerCycle.gcode` | Spin-coating layer cycle (PR #82), checked 2026-08-19. |
| `LayerCycle.segments.gcode` | `LayerCycle.gcode` with `;SEGMENT` markers and `{placeholder}` parameters, for the Segment Runner (PR #85). |
| `RMR_SegmentRunner.html` | Standalone Web Serial segment runner with named recipes (PRs #85, #88, issue #62). It shared no code with `RMR_Controller.html` or `RMR_Touch.html` and was never run against this firmware. |
| `SpinCoatUVCure.gcode` | The April 2026 protocol from the GitHub Copilot agent: 2000, 3000, 4000 and 5000 RPM, five cycles each. Never run on the machine. |
| `tests/segment-runner.test.mjs` | The Segment Runner's checks (#62): validation, parameter substitution, layer expansion, execution, guards, recipes. |
| `tests/layercycle-equivalence.test.mjs` | Checked that `LayerCycle.segments.gcode` sent the same executable lines as `LayerCycle.gcode` at default parameters. |

## Why they were archived

1. **The syringe moves do nothing.** Since commit `3d7ab2c` the syringe is the homeable C axis
   (Marlin K) and there is no E axis. `G92 E0` and `G1 E...` are silently ignored with no error
   (`claude.md` gotcha 1), so these programs move every axis except the one that dispenses.
2. **Their comments and values disagree.** Issue #49 recorded two cases in `fullcode.gcode`:
   `G1 E-6` carries the comment "push 4 mm", and `G4 S480` carries "cure for 8.5 minutes (510
   seconds)". Hand-editing a G-code file per material produced those mismatches.

The owner decided on 2026-10-20 to archive them instead of porting them to `C` (issue #173).

## What replaced them

The Process Sequencer in `RMR_Controller.html` and `RMR_Touch.html` runs the Homing, Syringe,
Spin Coater, UV and Stamp blocks. Per-material values (dispense volume, spin recipe, cure time)
live in the Run Log device presets, not in G-code. See `docs/adr/0005`.

`DemoProgram.gcode` stays in the repo root: it has no E moves, and the Stamp block's defaults
come from it.

## The moved tests do not run

`tests/segment-runner.test.mjs` and `tests/layercycle-equivalence.test.mjs` import
`./harness.mjs`, which lives in the repo's `tests/` folder. From here the import does not
resolve, and the runner and G-code paths they take as arguments have moved. To revive them, move
the files back first.
