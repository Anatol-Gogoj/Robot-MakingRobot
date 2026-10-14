# AI Attribution

This project used **Claude** (Anthropic) as its main AI development tool, and GitHub **Copilot** once (see below). This document describes what was AI-assisted and how. Commits with AI help carry a `Co-Authored-By` trailer that names the model, so `git log` is the per-change record.

## What Claude Was Used For

- **Documentation**: README.md, claude.md (project reference), PIN_MAP.md (wiring reference), RUN_SHEET.md, RUN_LOG_PLAN.md, DISPENSE_150ML.md and the decision records under `docs/adr/` were drafted and/or edited with Claude's assistance.
- **Firmware configuration**: Configuration.h and Configuration_adv.h values (steps/mm, feedrates, acceleration, travel limits) were reviewed and updated in collaboration with Claude. Claude translated known hardware parameters into Marlin configuration values. It did not choose the hardware.
- **Custom pin mapping**: pins_RAMPS_14_RMR.h conflict resolution and pin assignments were developed with Claude's assistance.
- **Firmware features and patches**: the conversion of the syringe from the E0 extruder to the homeable K (`C`) axis, the UV lid interlock and motor-power sense features, the M280 timed servo ramp, and the August spincoater fixes (e-stop disarm, bounded waits, strict ODrive reply parsing, datum preservation) were written with Claude.
- **Web UIs**: RMR_Controller.html was generated with Claude. RMR_Touch.html, the Process Sequencer, the Run Log module, the colour themes, and the later fixes to both pages were written with Claude.
- **Pi touch panel**: the serial-to-WebSocket bridge and its GPIO buttons, status tower and e-stop sense (`pi-panel/`) were written with Claude.
- **Tooling and tests**: `tools/sync_runlog.py`, `tools/contrast_check.py` and the browser test harness under `tests/` were written with Claude.
- **Repository maintenance**: Claude Code did the September 2026 consolidation, which merged the August spincoater pull-request stack and the September UI work into `main` (PRs #106 and #107), including the conflict resolutions recorded in their merge commits. It also did the later documentation refreshes and the October 2026 move of session handoffs out of the repository (issue #129).
- **CAD commits**: Claude Code committed the files under `CAD/`. The models themselves were designed by the project author (see below).

## What GitHub Copilot Was Used For

- The GitHub Copilot coding agent contributed to the April to August 2026 work that was squashed into PR #106 (it is a co-author on that commit). That includes the `SpinCoatUVCure.gcode` protocol, which has never been run on the machine.

## What AI Was NOT Used For

- Hardware design, mechanical engineering, CAD modelling and physical wiring decisions were made by the project author.
- DM556T driver DIP switch settings and motor selection are based on the author's hardware choices.
- Bench testing was done by the project author on the physical machine.

## Verification

The project author reviewed all AI-assisted code and configuration before it was merged. Claude's outputs were treated as drafts subject to human review, not as authoritative engineering decisions.

Review is not the same as hardware validation. Some merged changes have not yet run on the machine. Examples at the time of writing are the M410 cooperative spin abort, the Run Log against real hardware, and a re-flash of `main` since the September consolidation. RUN_SHEET.md and the "What's Left To Do" section of claude.md record what has and has not been bench-verified.

## Models

Claude (Anthropic):
- Claude Opus 4.6 and Claude Sonnet 4.6 (to April 2026), via Claude Desktop (Cowork mode), Claude chat (Claude.ai) and Claude Code.
- Claude Opus 5 (August 2026), via Claude Code.
- Claude Opus 4.8 and Claude Fable 5.1 (September 2026), via Claude Code.
- Claude Opus 5.5 (from October 2026), via Claude Code.

GitHub Copilot coding agent (`copilot-swe-agent`), on work merged in PR #106.
