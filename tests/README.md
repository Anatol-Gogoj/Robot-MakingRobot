# UI checks

Behavioural checks for the three browser UIs. They exist because PR bodies in
this repo make quantitative claims — "13 of 17 checks fail before this change"
— and a claim nobody can re-run is not evidence.

```bash
node tests/run.mjs        # all checks against the HTML files in the repo root
node tests/run.mjs -v     # ...with each check's own output
```

Node 18 or newer. No dependencies, no install step, nothing to build.

`harness.mjs` runs **every** inline `<script>` of a page in one vm scope, in page
order — the pre-paint theme applier, the main UI script and the shared Run Log
module at the end of the page — the way a browser does. (An earlier version took
only the first script, which after the theme work was the ten-line theme applier.)

## What they actually run

The shipped `<script>` is extracted from the HTML file and executed in a Node
`vm` context under a stub DOM, then its **real functions** are called. Nothing
is re-implemented, so a check that passes is a statement about what ships.

Two things make that work:

- `let` and `const` at the top of a `<script>` live in the script's own lexical
  scope, not on the global object, so a test cannot reach them by property
  access. The harness appends `globalThis.__ev = (s) => eval(s)` to the same
  scope; a direct `eval` sees those bindings. Tests use `ev('okLedger')` to read
  and `ev('isConnected = true')` to write.
- Elements register themselves in the stub when their `id` is assigned, so a
  test can reach an input the page built at runtime with `createElement`. The
  stub is also seeded from the markup, so defaults declared as HTML attributes
  (`checked`, `value`) are visible — the Program Runner reads several at load.

The serial port is a stub writer that appends to an array. `processLine()` is
called directly to feed a line in. That is the whole of it: no browser, no
headless Chrome, no mock framework.

## Running them on an unfixed branch

**`node tests/run.mjs` on `main` reports failures, and that is the point.** The
checks assert the fixed behaviour, so on a branch without the fix they are the
reproductions. Expected results:

| branch | result |
|---|---|
| `main` | 2 passed, 5 failed, 3 skipped — the `#48` and `#47` bugs are present |
| `fix/48-program-runner-ok-attribution` | 5 passed, 2 failed, 3 skipped — `#48` fixed, `#47` still open |
| `fix/47-ui-error-markers` | **7 passed, 0 failed**, 3 skipped |
| `feature/62-segment-runner` | 5 passed, 5 failed — based on `#82`, so the `#48`/`#47` checks run against the unfixed UIs |
| `feature/62-recipes` | 5 passed, 5 failed — same lineage, with the recipe checks included |

These numbers were produced by running the suite against each branch, not
estimated. A check whose target file is not on the branch is **skipped**; a
section covering a feature the branch predates is skipped too, which is why the
recipe checks do not fail `feature/62-segment-runner`.

## What each check covers

| file | issue | asserts |
|---|---|---|
| `ok-attribution.test.mjs` | #48 | Only a program line's own `ok` advances the Program Runner. Covers foreign traffic mid-program, pause/resume in both orderings, a write that throws, ledger overflow halting the run, and E-stop clearing the ledger. |
| `homing-indicator.test.mjs` | #48 | `RMR_Touch`'s homing indicator clears on `G28`'s own `ok`, not on whichever arrives first. |
| `runlog.test.mjs` | — | The Run Log module in either UI: the real Syringe block records the dispense at its `M400`; spin statistics are captured only between `spin.start` and `spin.done` (a `Samples=0` measure leaves the cell blank); UV on/off/aborted; hand-pressed electrodes alternate P/N and close the layer; an edited cell survives a later automatic value; Hold / Break pause between commands and a Stop during a hold rejects with `RunLogAbort`; logging off / on notes the gap; CSV and XLSX exports; localStorage persistence. |
| `runlog-sync.test.mjs` | — | The shared `RMR-RUNLOG` block is byte-identical in both pages and each page carries its glue (containers, host object, every hook, and the Touch `tabNames` order). |
| `syringe-dose.test.mjs` | — | The retuned Syringe block: exact command order (lower · dose · `M400` · dwell · retract at its own feed · snap lift · raise), the dose / retract / stroke guards refusing before anything is sent, the purge routine, barrel calibration from the bore, and the Run Log's preset → Process Sequencer apply path. |
| `spin-markers.test.mjs` | #47 | `OK:`/`ERR:` are read by message class. `STATE:HOME_SETTLE` does not latch "Home datum set"; `ERR: HOME_SET_FAILED` does not read as success; `ERR: CYCLE_COMPLETE_NO_HOME` is not green; an unmapped `ERR:` still shows as an error. Marker text is taken verbatim from the firmware sources. |
| `segment-runner.test.mjs` | #62 | Load-time validation, parameter substitution and bounds, layer expansion, execution and pausing, `ERR:` failing a segment, the four guards, preview, session split/merge, the plan-rebuild guards, and recipes — save/load/delete, export/import round trip, clamping a saved value against tightened bounds, the modified flag, and the provenance block each run writes to the log. |
| `layercycle-equivalence.test.mjs` | #62 | At default parameters and one layer, `LayerCycle.segments.gcode` sends the same executable lines, in the same order, as `LayerCycle.gcode`. This is what makes the annotated copy trustworthy. |
| `syntax-check.mjs` | — | Every `<script>` block parses. Cheap, and catches the edit that broke a 1700-line file. |

## What they do not cover

Everything that needs the machine. No check here proves a servo moved, an
endstop triggered, or the ODrive answered — a stub writer accepts anything. The
serial contract they assert is Marlin's *documented* one (one `ok` per accepted
command, in order); if the firmware ever violates it, these pass and the bench
fails.

Treat a green run as "the UI logic does what we think", never as "it works on
the machine". Bench steps live in the PR bodies.
