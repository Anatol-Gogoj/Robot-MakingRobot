# UI checks

Behavioral checks for the three browser UIs (`RMR_Controller.html`, `RMR_Touch.html` and
`RMR_SegmentRunner.html`). They exist because PR bodies in this repo make quantitative claims,
such as "13 of 17 checks fail before this change", and a claim nobody can re-run is not evidence.

```bash
node tests/run.mjs        # all checks against the HTML files in the repo root
node tests/run.mjs -v     # the same, with each check's own output
```

Node 18 or newer. No dependencies, no install step, nothing to build.

On a Windows machine without Node, VS Code's bundled Electron runs the suite:

```bash
ELECTRON_RUN_AS_NODE=1 "$LOCALAPPDATA/Programs/Microsoft VS Code/Code.exe" tests/run.mjs > out.txt 2>&1
```

`Code.exe` is a GUI-subsystem program, so redirect its output or nothing prints. Write
`out.txt` outside the repo, or it shows up as an untracked file.

`harness.mjs` runs **every** inline `<script>` of a page in one vm scope, in page order, the way
a browser does: the pre-paint theme applier, the main UI script, and the shared Run Log module
at the end of the page. (An earlier version took only the first script, which after the theme
work was the ten-line theme applier.)

## What they actually run

The shipped `<script>` is extracted from the HTML file and executed in a Node `vm` context under
a stub DOM, and then its **real functions** are called. Nothing is re-implemented, so a check
that passes is a statement about what ships.

Two things make that work:

- `let` and `const` at the top of a `<script>` live in the script's own lexical scope, not on
  the global object, so a test cannot reach them by property access. The harness appends
  `globalThis.__ev = (s) => eval(s)` to the same scope, and a direct `eval` sees those bindings.
  Tests use `ev('isConnected')` to read and `ev('isConnected = true')` to write.
- Elements register themselves in the stub when their `id` is assigned, so a test can reach an
  input the page built at runtime with `createElement`. The stub is also seeded from the markup,
  so defaults declared as HTML attributes (`checked`, `value`) are visible; the Program Runner
  reads several at load. Radio groups (a `name`, no `id`) are seeded too, with browser-style
  exclusivity, so `document.querySelector('input[name="stampSide"]:checked')` resolves. That is
  how the Stamp block reads its feeder side.

The serial port is a stub writer that appends to an array, and `processLine()` is called directly
to feed a line in. That is all of it: no browser, no headless Chrome, no mock framework.

## Expected result on `main`

**`node tests/run.mjs` on `main` reports 23 passed, 0 failed, 0 skipped** (measured 2026-10-20,
with #48 fixed). Any failure, or a change in that count, is a regression.

Until #48 was fixed, `ok attribution: Controller`, `ok attribution: Touch` and
`homing indicator: Touch` failed on `main` as its reproductions: a foreign `ok` (for example from
the auto-report `M114`) advanced the Program Runner and cleared the Touch homing indicator.

A check whose target file is not on the branch is **skipped**. A section covering a feature the
branch predates is skipped too. The August branches `fix/47-ui-error-markers` and
`fix/48-program-runner-ok-attribution` predate the September UI rebuild, so their old pass
counts no longer describe anything that would merge.

## What each check covers

| file | issue | asserts |
|---|---|---|
| `ok-attribution.test.mjs` | #48 | Only a program line's own `ok` advances the Program Runner. Covers foreign traffic mid-program, pause/resume in both orderings, a write that throws, ledger overflow halting the run, and E-stop clearing the ledger. Also the Pi bridge (entries from the TX echo, another client's poll and a two-line button counted, a dropped write or a closed port halting the run), the firmware lines that clear the ledger (`start`, `kill() called`, `MOTOR POWER LOST`, `Resend:`), which lines earn an entry (not a comment-only line, not `M112`), a stopped run's late `ok`, Resume on the Pause button, and the auto-report poll waiting for an empty ledger. |
| `homing-indicator.test.mjs` | #48 | `RMR_Touch`'s homing indicator clears on `G28`'s own `ok`, not on whichever arrives first, and a firmware restart drops it without a "Homing complete" toast. |
| `runlog.test.mjs` | none | The Run Log module in either UI: the real Syringe block records the dispense at its `M400`; spin statistics are captured only between `spin.start` and `spin.done` (a `Samples=0` measure leaves the cell blank); UV on/off/aborted; hand-pressed electrodes alternate P/N and close the layer; an edited cell survives a later automatic value; Hold / Break pause between commands, and a Stop during a hold rejects with `RunLogAbort`; turning logging off and on notes the gap; CSV and XLSX exports; localStorage persistence. |
| `runlog-sync.test.mjs` | none | The shared `RMR-RUNLOG` block is identical in both pages (line endings aside, so a CRLF checkout passes), and each page carries its glue (containers, host object, every hook, and the Touch `tabNames` order). |
| `syringe-dose.test.mjs` | none | The retuned Syringe block: exact command order (`M114` position query, lower, dose, `M400`, dwell, retract at its own feed, raise; the B snap lift is gone); the dose and retract guards refusing with nothing sent (max retract defaults to 2 mm, and a 0.5 mL drip-stopping pullback passes); the stroke guard checking the fresh `M114` position rather than the readout, and refusing when the reply has no C; the purge and prime routines; `G90` still sent when a Stop or fault lands inside the relative-mode section (a Stop sends `M410` then `G90` in both UIs); barrel calibration from the bore; and the Run Log's preset-to-sequencer apply path. |
| `stamp-block.test.mjs` | none | The Stamp block in either UI: exact command order (travel, `M400`, gripper open, feeder advance, grab, transit, press, three-step retreat, dispose); the filter feeder advances toward MIN (`G1 A-`, since the axis homes to MAX) once per pick in left-only or right-only mode and once per L+R pair when alternating; the lift-Z guard refusing a lift at or below the press or approach depth before anything is sent, without consuming the alternating side; the filter-feeder jog buttons (Advance = `A-`, Retract = `A+`, locked until homed, refused while a sequence runs). |
| `lid-angle.test.mjs` | none | Every lid-close path in either UI uses the same 115 degree angle as the UV block: the Manual-tab slider and Close preset (Controller), the Lid CLOSE button and long-press servo sheet (Touch), the UV block default, and the built-in presets. The raw override stays 0 to 180 in both. A last check has the UV block report a cure the firmware's lid interlock refused instead of counting it. |
| `uv-refusal-feedback.test.mjs` | none | When the firmware's UV lid interlock refuses a UV-on (`UV inhibited: lid open`) or cuts the lamp mid-cure (`UV cut: lid opened`), both UIs raise an error toast, log a console line, show the UV pair as OFF, and set the sequencer's refusal flag. |
| `relay-off-by-firmware.test.mjs` | #141 | The relay pairs drop to OFF, with nothing sent, on the firmware's own lines for the events on which the #131 firmware turns the UV lamp and valve relays off by itself: `start`, `echo:MOTOR POWER LOST` and `kill() called`. `kill() called` still fails a running sequence. A sent `M112` alone (E-STOP, console, or the bridge's echo of a dropped write) changes nothing until the `kill() called` line arrives. A pair last driven on a pin other than 4 or 42 keeps its highlight. Unknown-command echoes of the words, ordinary traffic, `Motor power restored`, a refused move, other `Error:` lines, `M999` / `M18` / `M84`, and the bridge's E-stop sense on its own leave an ON highlight alone. |
| `spin-markers.test.mjs` | #47 | `OK:` and `ERR:` are read by message class. `STATE:HOME_SETTLE` does not latch "Home datum set"; `ERR: HOME_SET_FAILED` does not read as success; `ERR: CYCLE_COMPLETE_NO_HOME` is not green; an unmapped `ERR:` still shows as an error. Marker text is taken verbatim from the firmware sources. |
| `segment-runner.test.mjs` | #62 | Load-time validation, parameter substitution and bounds, layer expansion, execution and pausing, `ERR:` failing a segment, the four guards, preview, session split/merge, the plan-rebuild guards, and recipes: save/load/delete, export/import round trip, clamping a saved value against tightened bounds, the modified flag, and the provenance block each run writes to the log. |
| `layercycle-equivalence.test.mjs` | #62 | At default parameters and one layer, `LayerCycle.segments.gcode` sends the same executable lines, in the same order, as `LayerCycle.gcode`. This is what makes the annotated copy trustworthy. |
| `syntax-check.mjs` | none | Every `<script>` block parses. It is cheap, and it catches the edit that broke a 1700-line file. |

## What they do not cover

Anything that needs the machine. No check here proves that a servo moved, an endstop triggered,
or the ODrive answered, because a stub writer accepts anything. The serial contract they assert
is Marlin's *documented* one (one `ok` per accepted command, in order). If the firmware ever
breaks that contract, these checks pass and the bench fails.

Treat a passing run as "the UI logic does what we think", never as "it works on the machine".
Bench steps live in the PR bodies and in `RUN_SHEET.md`.
