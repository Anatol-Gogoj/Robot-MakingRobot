# ADR-0005: The two HTML pages are the only UIs, and process parameters live in them
Status: Accepted; Date: 2026-08-05 (owner decision on #49; handoff decisions 5 and 6); Scope: `RMR_Controller.html`, `RMR_Touch.html`, the G-code programs
Context: The machine makes DEAs from different elastomers, and dispense volume, spin recipe and UV cure time depend on the material. Hardcoding them in G-code meant hand-editing `fullcode.gcode` per material. Separately, several side UIs existed or were proposed (the Nano dashboard, the Segment Runner).
Decision: `RMR_Controller.html` (debugging and tuning) and `RMR_Touch.html` (operation) are the machine's UI; no third UI is started. Elastomer-dependent parameters are user-editable fields in those pages (the Process Sequencer and its presets), not constants in G-code.
Rejected: Per-material G-code files edited by hand: error-prone and invisible to the operator
Rejected: A new purpose-built GUI: splits the serial contract across more pages and doubles every UI fix
Consequences: `RMR_SegmentRunner.html` (#85, #88) is the one exception that exists: a standalone segment runner built in August for #62, never run against this firmware, sharing no code with the two pages. It is not a third machine UI, and its recipes do not reach the two pages.
Consequences: Easier: one place to change a recipe; presets carry the whole process. Harder: both pages must stay in step (the Run Log module is synced by `tools/sync_runlog.py`; the rest is patched by hand in each file).
Revisit if: the UIs are rebuilt on a shared code base.
