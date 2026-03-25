# AI Attribution

This project used **Claude** (Anthropic) as a development tool. This document describes what was AI-assisted and how.

## What Claude Was Used For

- **Documentation** — README.md, claude.md (project reference), and Configurations.txt were drafted and/or edited with Claude's assistance.
- **Firmware configuration** — Configuration.h values (steps/mm, feedrates, acceleration) were reviewed and updated in collaboration with Claude. Claude did not generate the hardware design or wiring; it translated known hardware parameters into Marlin configuration values.
- **Custom pin mapping** — pins_RAMPS_14_RMR.h conflict resolution and pin assignments were developed with Claude's assistance.
- **Web controller UI** — RMR_Controller.html was generated with Claude.

## What Claude Was NOT Used For

- Hardware design, mechanical engineering, and physical wiring decisions were made by the project author.
- DM556T driver DIP switch settings and motor selection are based on the author's hardware choices.
- All firmware values were validated against physical hardware by the project author.

## Verification

All AI-generated code and configuration was reviewed, tested, and validated by the project author before being committed. Claude's outputs were treated as drafts subject to human review — not as authoritative engineering decisions.

## Model

Claude (Anthropic) — primarily Claude Opus 4.6 and Claude Sonnet 4.6, accessed via Claude Desktop (Cowork mode) and Claude chat (Claude.ai).
