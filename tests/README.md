# UI checks

Behavioural checks for the three browser UIs. They exist because PR bodies in
this repo make quantitative claims — "13 of 17 checks fail before this change"
— and a claim nobody can re-run is not evidence.

```bash
node tests/run.mjs        # all checks against the HTML files in the repo root
node tests/run.mjs -v     # ...with each check's own output
```

Node 18 or newer. No dependencies, no install step, nothing to build.

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

| branch | expectation |
|---|---|
| `main` | `#48` and `#47` checks fail — those bugs are present |
| `fix/48-program-runner-ok-attribution` | `#48` passes, `#47` still fails |
| `fix/47-ui-error-markers` | `#48` and `#47` pass |
| `feature/62-segment-runner` | `#62` passes; it is based on `#82`, so the `#48`/`#47` checks run against the unfixed UIs and fail |

A check whose target file is not on the branch is skipped, not failed.

## What each check covers

| file | issue | asserts |
|---|---|---|
| `ok-attribution.test.mjs` | #48 | Only a program line's own `ok` advances the Program Runner. Covers foreign traffic mid-program, pause/resume in both orderings, a write that throws, ledger overflow halting the run, and E-stop clearing the ledger. |
| `homing-indicator.test.mjs` | #48 | `RMR_Touch`'s homing indicator clears on `G28`'s own `ok`, not on whichever arrives first. |
| `spin-markers.test.mjs` | #47 | `OK:`/`ERR:` are read by message class. `STATE:HOME_SETTLE` does not latch "Home datum set"; `ERR: HOME_SET_FAILED` does not read as success; `ERR: CYCLE_COMPLETE_NO_HOME` is not green; an unmapped `ERR:` still shows as an error. Marker text is taken verbatim from the firmware sources. |
| `segment-runner.test.mjs` | #62 | Load-time validation, parameter substitution and bounds, layer expansion, execution and pausing, `ERR:` failing a segment, the four guards, preview, session split/merge, and that the plan cannot be rebuilt under a running program. |
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
