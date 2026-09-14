# Run Log — DEA per-layer manufacturing log (design + decisions + what was built)

Status: **built 2026-09-14 on branch `claude/dea-progress-tracker-e9a3c4`, unmerged.** Verified in a
browser (Chrome, Controller and Touch pages) against a fake Marlin that acknowledges every command
and prints the spin statistics; **never run against the machine** — see §9. Written against `main`
at `ec98399`. Function names are the citations; line numbers drift.

## 0. TL;DR

A per-device **Run Log** that mirrors the operator's `MLDEA Reference Sheet.xlsx`: one row per
dielectric layer and one row per electrode (P/N), filled in automatically by the Process Sequencer as
it runs — time of dispense, settled (mean) RPM, UV on / cure set and actual, time of filter application
— and editable by the operator at any time. It is a **Run Log** tab in `RMR_Controller.html` and a
**Log** tab in `RMR_Touch.html` (no new page), with a one-line progress strip inside the sequencer
toolbar. **Hold** / **Break** pause a run at a chosen safe point *between* two commands and record the
pause as a row; **Log on/off** mutes recording without stopping the machine. Everything persists in
the browser (`localStorage`) and, optionally, in a folder the operator picks (JSON + CSV + XLSX kept
up to date on every change). The XLSX reproduces the reference sheet's layout and formulas. **No
firmware change**, and the log never sends G-code.

## 1. What the reference sheet says (the data model)

`Z:\Anatol Gogoj\Alex White CuttleBot Fins\MLDEA Reference Sheet.xlsx`, sheet `Template`:

| Cell | Content | Meaning for the log |
|---|---|---|
| B2:F2 | `Layer`, `Time of Dispense`, `UV dur (sec)?`, `Nominal Height (µm)`, `Notes` | the visible columns |
| B3…B63 | `31, N, 30, P, 29, N, … 2, P, 1` | **stack order, top-down**: newest layer at the top; electrode rows alternate between dielectric layers; layer 1 is followed by P, layer 2 by N — odd layers → P, even → N |
| E63 `=$I$3`, E62 `=E63`, E61 `=E62+$I$3` … | cumulative nominal height | dielectric rows add one `Layer Thickness`; electrode rows add 0 |
| H3:J7 | `Layer Thickness (µm)` 70 ± 10, `Material` CN9018 7.5% HDDA, `Material Type` Acrylic, `RPM`, `RPM Hold Time (s)` | the **device header / specs block** |

The sheet had no column for settled RPM or time of filter application; the log adds them. The `?` in
`UV dur (sec)?` reads as "was it really that long?", so the log carries cure **set** and **actual**.

## 2. Owner decisions (2026-09-14)

| # | Question | Decision |
|---|---|---|
| 1 | Pause semantics | Hold the run at a safe boundary **and** record the hold (plus the Log on/off switch) |
| 2 | Safe hold points | **Operator's choice**: end of layer (default) · after the next UV cure · after the current block |
| 3 | Where the log lives | **The Pi is not in service** — the complete HTML (Controller) is the station, sometimes the Touch page. Browser-side persistence; the bridge design (§4 of the original plan) is deferred |
| 4 | Exports | CSV + JSON always; **XLSX reproduces the Template layout** (top-down stack, P/N rows, nominal-height formulas, Specs block) |
| 5 | Row order | **Newest on top** (toggle to chronological) |
| 6 | Electrode rule | **Odd → P, even → N**, with a checkbox for whether the feeder side sets the polarity (L = P or N) |
| 7 | Columns | HomeSettleErr added; **nominal and real** for RPM (set / settled) and cure (set / actual); **measured values sit to the right of the human-readable columns** behind a Details toggle |
| 8 | Log drives the run | Prefill Run All cycles from the remaining layers (button + preference); device **presets** (save / apply / delete); stamp side stays decided before the run; **always warn on an incomplete row, never block**; **elapsed and estimated remaining time** shown |
| 9 | Shared module vs paste | Impartial → **one shared block pasted into both pages**, Controller canonical, `tools/sync_runlog.py` keeps the Touch copy identical, a test fails on drift. Chosen over a `<script src>` because the HTML files travel alone (USB stick, another laptop) and must stay self-contained |
| 10 | Arming | **Logging starts when the operator presses Start logging.** Jumping back a step (re-running a block) updates the open row and is recorded in the **Journal**, not as a new row on the sheet |
| — | Hand pressing | All pressing is by hand today: the built-in **CN9018 7.5% HDDA** preset carries the note "Electrodes pressed by hand", electrode rows added with **Filter pressed** get the note `hand press` |
| — | Persistence | Must survive a power cycle or restart: `localStorage` + optional save folder + export/import |
| — | Operator break | A **Break** button (same mechanism as Hold, recorded as a break, default reason "operator break"); pressing it while idle starts the break at once |

## 3. What the machine already gives us (event sources)

A production layer runs **home → dispense → lid close → spin (M750) → UV cure → lid open → stamp a
filter** (electrode). Every moment the log needs is an `await` the sequencer already performs:

| Log field | Hook (both UIs) | Why this instant |
|---|---|---|
| Time of dispense, volume | `runSyringeBlock`: `rlEvent('dispense', …)` right after the `await seqCmd('M400')` that follows the `G1 C<mm>` push | the `G1`'s `ok` means "queued"; `M400` returns when the plunger has stopped |
| Spin setpoint, D/A/C, H; settled RPM, σ, n, min/max, HomeSettleErr, Vbus, result | `runSpinBlock`: `spin.start` before `M750`, `spin.done` in a `finally`; `rmrLog.rx()` captures `echo:SPIN DATA:` keys and the `OK:`/`ERR:` markers **only inside that window** | M750 prints its statistics before its `ok`; a `Samples=0` measure leaves the cell blank instead of showing the previous layer's number |
| UV on / off / actual s | `runUvBlock`: `uv.on` after the `M42 P<pin> S1` ok, `uv.off` after `S0`, and from the `finally` that turns the lamp off on Stop / fault (flagged `aborted`) | the `finally` path is the only honest "actual" for a cut-short cure |
| Time of filter application, hold, side, press Z | `runStampBlock`: `stamp.pick` after the gripper closes, `stamp.press` after the `M400` that follows the slow press | contact begins when the press completes |
| Layer / cycle boundaries, faults, aborts | `seqRunAll` (`run.begin`, `cycle.begin`, `block.*`, `cycle.end`, `run.end` / `run.fail`), `seqRunBlock` (`block.*`), `seqStop` (`seq.stop`), `seqFault` (`seq.fault`), `emergencyStop` (`estop`), `processLine` → `rlRx(line)` | an aborted layer is flagged `aborted at UV` / `fault: …` instead of staying half-filled |

Constraints honoured: the log **never sends G-code** (the Mega drops serial input during a blocking
command); `ok` ≠ success (spin outcome comes from the marker); every module entry point is wrapped in
try/catch and the Touch `readLoop` now isolates each line (a throwing hook used to kill the reader);
both HTML files are patched, the Touch `seqCmd` / `seqAwaitOk` gained the Controller's timeouts.

## 4. Behaviour as built

- **Device** = one multilayer DEA = one sheet: ID (default `YYYYMMDD-A`), operator, material, type,
  thickness ± tol, target layers, RPM, hold s, cure s, dispense mL, electrode after layer 1 (P/N),
  feeder-side-sets-polarity + which polarity the left feeder holds, hand-press note, notes. Presets
  (built-in CN9018 7.5% HDDA; save / apply / delete). New device seeds from the preset and the current
  Recipe-tab settings. Open / New / Delete / Import JSON.
- **Table** (stack view): `Layer · Dispensed · Vol mL · RPM set / settled · UV on · Cure set / actual s ·
  Filter applied · Hold s · Side · Nominal µm · Result · Notes`, then behind **Details**: σ RPM, n,
  min / max, HomeSettleErr °, Vbus, spin start, UV off, retract mL, height B, press Z, flags.
  Dielectric rows (`31`, `30`, …), electrode rows (`P` / `N` with the layer number), hold / break rows
  (from → to · duration · reason), note rows. The row being built is highlighted; the cure "actual"
  counts up live; the result chip reads ok · no home · no samples · aborted at … · fault: … · curing ·
  in progress · manual · polarity ≠ feeder.
- **Layer rules**: one Run All cycle = one layer; a dispense or spin after a cured layer opens the next
  layer; the electrode row (Stamp block, or **Filter pressed**) closes it; nominal height = layer ×
  thickness; re-runs update the open row, flag it (`re-dispensed`, `re-spun`, `re-cured`, `re-pressed`)
  and go to the Journal.
- **Editing**: tap a cell (Edit lock: locked by default on Touch, unlocked in the Controller); the
  recorded value stays underneath the ✎ mark with a revert button; auto-fill never overwrites an edited
  cell; add rows by hand (layer / electrode / hold / note), delete rows.
- **Hold / Break**: point selector (end of layer · after next UV cure · after current block); while a run
  is active the request is queued and `seqRunAll` / `seqRunBlock` honour it at the next matching
  boundary by awaiting `rlHoldPoint()` **between** commands; the sequencer status line and the strip
  count the hold; **Resume** continues; Stop, E-STOP or a fault end the hold and abort the run; a hold
  requested while idle starts at once; a request still pending when the run finishes becomes an idle
  hold. **Log on/off** mutes recording; re-arming adds a note with the number of dispenses missed.
- **Quick reference**: the strip in the sequencer toolbar (device · log on/off · layer n / target ·
  next step · last spin · last cure · elapsed · est. remaining · Hold / Break / Resume · Log ▸) and the
  device card (now / next, elapsed, ETA from the median layer-to-layer time or from the block settings,
  progress bar, nominal height, `cycles ← remaining` button).
- **Persistence**: `rmr.runlog.index`, `rmr.runlog.dev.<id>`, `rmr.runlog.prefs`, `rmr.runlog.presets`
  in `localStorage` (shared by both pages on the same origin, e.g. both opened as `file://`); **Pick save
  folder…** (File System Access API) mirrors `<id>.json` / `.csv` / `.xlsx` into the folder on every
  change (1.5 s debounce), re-asks for permission after a browser restart; **Export…** downloads the same
  three files; **Import…** restores a JSON.
- **XLSX** built in-page with no library: sheet `Template` = the reference layout (B2:F2 headers, rows
  top-down `31, N, 30, P … 1`, `=E(n+1)+$I$3` formulas, Specs at H2:J7 plus device / operator / target /
  started / exported rows below, `G = Time of Filter`, measured columns from `L` rightward, times as
  Excel times `hh:mm:ss`); sheet `Log` = every row and field, chronological; sheet `Journal`.

## 5. Files

| File | Change |
|---|---|
| `RMR_Controller.html` | Run Log tab (`#tabbtn-runlog` / `#tab-runlog` / `#rlRoot`), strip `#rlStrip` in the sequencer toolbar, `window.rmrLogHost`, shims `rlEvent` / `rlRx` / `rlHoldPoint`, hooks in the block runners / `seqRunAll` / `seqRunBlock` / `seqStop` / `seqFault` / `emergencyStop` / `processLine`, and the **canonical** `RMR-RUNLOG` block (≈1200 lines) before `</body>` |
| `RMR_Touch.html` | Log tab (`tabNames` + button + `#tab-log`), the same glue and hooks, per-line try/catch in `readLoop`, `seqCmd` / `seqAwaitOk` timeouts (90 s default, `G28` 240 s, `M750` computed), and the synced copy of the block |
| `tools/sync_runlog.py` | Controller → Touch block sync; `--check`; `--from FILE` |
| `tests/harness.mjs` | runs every inline script of a page (the old first-script regex loaded only the theme applier) |
| `tests/runlog.test.mjs`, `tests/runlog-sync.test.mjs`, `tests/run.mjs`, `tests/README.md` | new checks |
| `claude.md`, `README.md` | Run Log section, gotcha #29, file inventory, to-do |

## 6. Gotchas (also in `claude.md` #29)

1. Edit the Controller's block only; run `python tools/sync_runlog.py`; the Touch copy is never hand-edited.
2. `rlHoldPoint()` is awaited **between** sequencer commands in `seqRunAll` / `seqRunBlock` — never inside a block runner, never while a command is in flight.
3. Spin numbers are trusted only inside the `spin.start` → `spin.done` window.
4. The log never sends G-code; a bug in it must never fault a run (every entry point is guarded; only a `RunLogAbort` propagates, and only from a hold that the run itself aborted).
5. No page-level `let` / `const` may be named `rmrLog`, `rlEvent`, `rlRx`, `rlHoldPoint`.

## 7. Verification done (2026-09-14, browser only)

Served both pages from a local static server (`?transport=serial`), replaced `writer` with a fake
Marlin (`ok` after every command; `echo:SPIN STATE/DATA/OK` lines before the `M750` ok; `M118` echoed):

- Controller: Run All × 2 cycles with all five blocks → rows `layer 1 · P · break · layer 2 · N` with
  dispense times, `MeanRPM 1009.88 (σ 4.47, n 99)`, `HomeSettleErr 0.40`, cure 3.0 / 3 s, feeder L then
  R; a Break requested mid-cycle applied at the end of cycle 1 (`Stamp — pressing` at the time of the
  request), the sequencer waited, Resume continued, the hold row shows from / to / duration / reason.
- In-place edit through the real click path: cell → input → Enter → ✎ with the recorded value and a
  revert button; journal entry written.
- Touch: same device visible (shared storage), Edit locked by default, `seqRunBlock('syringe')`
  emitted `G90 · G1 B0 · M400 · G91 · G1 C5 · M400 · G1 C-0.5 · M400 · G90 · G1 B0 · M400` and opened
  layer 3; **Filter pressed** added its P electrode with the `hand press` note; an idle Break was
  recorded live and closed on Resume.
- Exports: the XLSX opens with openpyxl — sheets `Template` / `Log` / `Journal`, headers, the
  top-down `31, N, 30, P … 1` column, the `=E(n+1)+$I$3` formulas, the Specs block, Excel time cells;
  CSV parses (one row per log row); JSON round-trips.
- No console errors on either page. `tests/*.mjs` were **not** run (no Node on this machine).

## 8. Not built / deferred

- **Pi-bridge persistence** (a shared log across screens with the bridge as the writer of record) —
  designed, not built; the Pi is not in service. When it is: a JSON gate in `ws_handler` (today every
  inbound message is written to serial), a `RunLogStore` on disk, `{"_rmr":"log", …}` messages both ways,
  the `BridgeStore` counterpart of the module's storage functions.
- Wire markers (`M118 RMR:LOG …`) for serial-trace forensics — not needed for correctness.
- Clock-skew warning — only meaningful with the bridge.

## 9. Before trusting it on the machine

1. Run one real layer with logging armed and compare the dispense / spin / cure times with the console.
2. Run `node tests/run.mjs` on a machine with Node 18+ (expect the pre-existing `#47` / `#48` failures
   plus the three new `run log` checks passing).
3. Open an exported `.xlsx` in Excel (formulas recalculate on load) and paste it beside the reference
   sheet.
4. On the bench laptop, pick a save folder on the Z: share and confirm the three files update after a
   layer.
5. Request a Hold during a real spin and confirm the run pauses only after the chosen boundary and that
   Stop / E-STOP still work during the hold.

## 10. Follow-up, same day (owner requests)

- **Presets set up the whole process.** A preset now carries a snapshot of every Process Sequencer input (`sequencer`, keyed by element id) beside the device specs. New device → preset → Apply → Create writes every sequencer field and saves them into the device; the device card's **Set up sequencer** re-applies them, **Capture sequencer** saves the current set-up, **Save as preset** always captures the current sequencer. Two built-in presets: `CN9018 7.5% HDDA` and `CN9018 7.5% HDDA · 150 mL syringe`.
- **Dwell after dispense**, default 2 s, between the dose's `M400` and the retract (browser-side, abortable).
- **150 mL catheter-tip syringe retune** (`DISPENSE_150ML.md`): retract in the right units (0.018 mm with a 0.05 mm guard), 15.9 mm/min dose feed, retract at its own feed, a fast B snap lift that severs the strand, dose / retract / barrel-stroke guards refused before anything is sent, a purge routine (button, or before the first dose of a Run All) and an idle warning. No lateral shear or wiper — the syringe is fixed over the chuck.
- Verified in the browser exactly as §7: the dose sequence `G90 · G1 B304 · M400 · G91 · G1 C3.9790 F15.9 · M400 · (dwell) · G1 C-0.0181 F1 · M400 · G1 B-4.000 F3000 · M400 · G90 · G1 B0 · M400` on both pages; the guard refuses an oversize retract with nothing sent; the Run All purge precedes the first dose; the preset writes 36 fields and every derived display refreshes.
