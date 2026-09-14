# HANDOFF — Robot-MakingRobot spin coater work

**Written:** 2026-08-11. **Branch at the time of writing:** `fix/44-feedback-numeric-validation` (commit `757fdad`), plus the documentation commit that introduced this file. Line citations into `claude.md` and `README.md` refer to those files as committed alongside this one.

You are taking over a body of firmware work on a 3-axis gantry that manufactures multilayer dielectric
elastomer actuators (DEAs). The spin coater is an ODrive S1 + D5312s-330kV motor + AMT102 incremental
encoder, driven by Marlin 2.1.2.7 on an Arduino Mega 2560 over `Serial2` at 115200 using the ODrive raw
ASCII protocol. The ODrive runs firmware 0.6.x.

Read sections 1, 2 and 7 before you touch anything. Fifteen minutes there will save you a day.

Claims about **firmware behaviour** in this document were read out of the source in this repo. Claims
sourced from GitHub (`gh`), from PR bodies, from bench observation, or from ODrive's own documentation are
what they say they are and were not re-derived from this repo's source — treat them accordingly. Anything
that could not be verified at all is marked **UNVERIFIED** in place. Do not delete those markers — replace
them with an answer.

---

## 1. Where things stand

### Nothing is merged. Nothing has run on hardware.

Six open PRs form a **linear stack**. Every one of them compiles (`pio run -e mega2560`) and every one has
been through an adversarial multi-lens review. **None of them has been flashed onto the machine.** The owner
is remote from the hardware; bench work happens through a colleague at an on-site Ubuntu laptop.

Do not describe any of this work as "done". It is *written and reviewed*, which is a different thing.

### The stack

Commits, oldest first (`git log --oneline main..HEAD`):

| SHA | Commit | PR |
|---|---|---|
| `ac20bc5` | Merge VanVersion spincoater updates: settle to saved home datum | #38 |
| `c7940fe` | Fix VanVersion follow-ups: fallback DEG, settle guard, UV relay S-value | #39 |
| `33c8f45` | Remove stale DispenseCureDemo1.gcode (active-LOW UV polarity) | #39 |
| `b81c8a1` | Spincoater e-stop: EMERGENCY_PARSER + ODrive IDLE disarm in kill() and setup() | #51 |
| `f85257c` | Correct M112 recovery docs: M999 cannot recover a killed board | #51 |
| `092baf8` | doIndexHome: honest failure exits, fault introspection, datum preservation | #56 |
| `d9dc4f4` | A failed settle never moves an existing datum | #56 |
| `bd3058c` | Bound every blocking wait in the spin cycle; detect a dead link directly | #57 |
| `757fdad` | Reject corrupted ODrive replies instead of laundering them into zeros | #58 |

### PR bases — this is a stack, not six independent branches

Verified with `gh pr view <n> --json baseRefName`:

| PR | Head branch | **Base branch** | Issue(s) | What it contains |
|---|---|---|---|---|
| #38 | `merge/vanversion-spincoater-home-settle` | `main` | — | VanVersion drop. `doIndexHome()` settles to the **saved datum** (`t 0 <_homePos>`) instead of encoder zero (`t 0 0.0`). Renames `STATE:INDEX_SETTLE`→`HOME_SETTLE`, `DATA:IndexSettleErr`→`HomeSettleErr`. Adds `fullcode.gcode`. |
| #39 | `fix/vanversion-followups` | `merge/vanversion-…` | (closes #50) | Fallback `DEG` readout was always `0.00` (value subtracted from itself); the >1-turn settle guard; `M42 P4 S255`→`S1` in `fullcode.gcode`; deletes the stale active-LOW `DispenseCureDemo1.gcode`. |
| #51 | `fix/40-estop-idles-spincoater` | `fix/vanversion-followups` | #40 | `EMERGENCY_PARSER` enabled; `Spincoater::emergencyStop()`; `kill()` hook; `startupSafetyDisarm()` in `setup()`; M999/M112 doc + UI truth correction. |
| #56 | `fix/41-43-indexhome-honest-exits` | `fix/40-estop-idles-…` | #41, #43 | Honest failure exits from `doIndexHome()`; `getProcedureResult()`; `reportFault()`; `forceIdle()`; `_datumSet`/`isDatumValid()`; datum preservation on failure. |
| #57 | `fix/42-unbounded-blocking-waits` | `fix/41-43-…` | #42 | Every blocking wait bounded; telemetry-liveness vs. no-progress as *two separate* discriminators; `measureSpeed()` returns `bool` and refuses to print stats on zero samples. |
| #58 | `fix/44-feedback-numeric-validation` | `fix/42-unbounded-…` | #44 | `parseStrictFloat`/`parseStrictInt`; `feedbackStable()`; strict newline-terminated reads; fail-closed >1-turn guard. |

All six report `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`.

### Why it is a stack, and what that forces on you

**All six** PRs edit `Marlin/src/feature/spincoater.cpp`, and several edit **the same functions** —
`doIndexHome()` is restructured by #38, #39, #56 and #58 in turn; `ensureClosedLoop()` by #57;
`boot()` by #56 and #58; `feedback()`/`readRaw()` by #51 and #58. Rebasing them onto `main` independently would produce overlapping
diffs and destroy the one-issue-one-PR review record.

**Merge order is forced: #38 → #39 → #51 → #56 → #57 → #58.** Merging out of order, or retargeting any PR's
base to `main` without rebasing, will give you a PR whose diff contains its ancestors' changes.
Do not "simplify" this by flattening the stack.

Aggregate `main..HEAD`: 12 files, +811 / −480.

Firmware surface: `spincoater.cpp`, `spincoater.h`, `M750.cpp`, `M751_M752.cpp`, `Configuration_adv.h`,
`MarlinCore.cpp`. `M753.cpp` is **unchanged across the entire stack**.
Doc/UI surface: `README.md`, `claude.md`, `RMR_Controller.html`, `RMR_Touch.html` — and the HTML edits are
**only** the M112/M999 recovery wording. Neither UI's serial parser was touched. See §7 and issue #47.

### The recommended sequence

1. Flash the stack **tip** on the bench and confirm normal G-code still streams at 250000 baud.
   `EMERGENCY_PARSER` (#51) changes the serial RX hot path for *every* command, not just the spincoater.
   This is the single highest-consequence unverified change in the stack.
2. Walk each PR's bench-validation checklist (they are in the PR bodies).
3. Merge bottom-up in the forced order.

---

## 2. The bug that started this

**The spin coater does not home properly.**

### Leading hypothesis: the encoder was never index-referenced for *position*

ODrive firmware 0.6.0 deleted `axis0.encoder.*`. Index referencing moved to
`axis0.commutation_mapper` and `axis0.pos_vel_mapper` (`use_index_gpio`, `index_gpio`, `index_offset`,
`index_offset_valid`).

**A repo-wide grep finds zero hits for `pos_vel_mapper`, `commutation_mapper`, `use_index_gpio` or
`index_offset` anywhere in this project** (verified 2026-08-11). The only `axis0.encoder` matches in the repo
are comments in the retired Nano bring-up firmware (`SpincoaterStage/src/main.cpp:9, :528, :1034`) recording
that those property paths *do not exist* on the S1.

The ODrive docs mark the `pos_vel_mapper` index settings "optional, only required for absolute position
setpoints" — and `t 0 <x>`, which is what **both** settle paths command, **is** an absolute position
setpoint. If only commutation is index-configured, the index search fixes commutation while `t 0` drives to
the *power-on shaft angle*: repeatable within a session, different after every power cycle. A documented
S1 + AMT-10x failure mode is `gpio10_mode` left at `AUTO (17)`, so the Z pulse is never sampled at all.

### Issue #46 is the bench task that settles it

It is ODrive-side configuration over native USB with the Mega out of the loop — no Marlin code is involved,
so it competes with nothing and **can start today**. Its checklist:

- Firmware version (everything above is 0.6.x-specific)
- `odrv0.config.gpio10_mode == DIGITAL (0)`, not `AUTO (17)`
- `axis0.commutation_mapper.config.use_index_gpio == True`, `index_gpio == 10`
- `axis0.pos_vel_mapper.config.{use_index_gpio, index_gpio, index_offset, index_offset_valid}`
- `axis0.config.startup_encoder_index_search`; `inc_encoder0.config.cpr == 4 × AMT102 PPR`
- `odrv0.save_configuration()` after any change
- **The empirical check that matters most:** after an index search, does `pos_estimate` return near 0
  (re-referenced) or hold its pre-search value?

**Gap to close before handing #46 over:** the issue references a ready-made one-shot script
`odrive_report.py`, "prepared in the 2026-08-05 diagnosis session". **It is not in this repo** — a
repo-wide `find -iname "*odrive*report*"` returns nothing. It must be recovered or rewritten.

### If #46 comes back "not index-referenced", stop and re-plan

That single observation is load-bearing for four issues, and all four say so in their own text:

- **#52** (post-spin homing design review) — if the position estimate is not index-referenced, the entire
  two-phase search-then-return model is built on a false premise.
- **#55** (the >1-turn guard latches) — the guard exists precisely to catch "not index-referenced". If that
  is the normal state, the guard fires on essentially every post-spin home and the fix is not in the guard.
- **#54** (datum not persisted) — persisting a datum is meaningless if the encoder frame is not stable
  across power cycles.
- **#45** (boot double index search), datum half — what `boot()` should do with `_homePos` depends on
  whether the index search establishes a frame at all.

Do not write Tier-3 firmware (§5) before #46 answers. The ordering there assumes the datum model is
basically sound and only its *lifecycle* is broken. If it is not, that assumption has to be revisited first.

---

## 3. How to work here

The owner's standing process. It is not ceremony — §8 documents what it has caught.

1. **One issue → one branch → one PR. Never batch unrelated fixes.** The single intentional exception in the
   stack is #56 (issues #41 and #43 rewrite the same exit paths in the same function and are inseparable).
2. **Correctness over efficiency.** Production runs real G-code on real DEA layers. A regression breaks a
   real manufacturing run, not a test.
3. **Every firmware change must build before push.**
4. **Every change gets an adversarial multi-lens review BEFORE commit.** Multiple independent review passes
   with different lenses (control flow, failure semantics, protocol, AVR resources, timing/arithmetic,
   regression risk). Not optional, not skippable for "small" changes.
5. **Every PR body carries bench-validation steps** written for the on-site colleague, who does not have
   the conversation context. Look at PRs #51/#56/#57/#58 for the expected shape.

### Build

```
cd "C:/Users/Anatol Gogoj/Desktop/Robot Making Robot/Robot-MakingRobot/Marlin-2.1.2.7"
pio run -e mega2560
```

`platformio.ini:16` sets `default_envs = mega2560`; the env is defined at `ini/avr.ini:25`
(`board = megaatmega2560`).

Firmware lands at `Marlin-2.1.2.7/.pio/build/mega2560/firmware.hex` (and `firmware.elf`).

Stack-tip build figures recorded in the PR bodies: **flash 29.7 %, RAM 42.7 %**. Quote your own build's
numbers in your PR body; flash is the constraint to watch on this board.

### The UI

`RMR_Controller.html` (click-optimised, full control, debugging/tuning) and `RMR_Touch.html`
(touchscreen-optimised, operation) **are** the machine's UI. **Never start a new one.** Extend these.

---

## 4. Decisions already made — do not relitigate

| # | Decision | Reason |
|---|---|---|
| 1 | **E-stop requests IDLE (freewheel), not commanded deceleration.** | Owner decision 2026-08-05 on #40. Whether a brake resistor is fitted is unknown; regen from a high-RPM chuck could overvolt the DC bus. Active braking is the eventual goal, gated on that bench answer. Do not "improve" the e-stop into a commanded decel. |
| 2 | **After M112, recovery is a board reset — not M999.** | `minkill()` ends in `for (;;) hal.watchdog_refresh();` (`MarlinCore.cpp:964`) with interrupts already off (`cli()` at `:932`). The `hal.reboot()` branch at `:960` is compiled out — it needs `HAS_KILL` or `SOFT_RESET_ON_KILL`, and `Configuration_adv.h:4302-4303` has both commented out. `M999.cpp` only sets `marlin_state = MF_RUNNING`; the CPU never gets there. Recovery: reconnect the serial port (the ATmega16U2 pulses RESET on DTR), press RESET, or power-cycle. This was documented wrongly in the docs **and both UIs** and is corrected in the stack. Never reintroduce "press M999 to recover". |
| 3 | **A failed home never moves an existing datum.** | The old blanket `doSetHome()` fallback made the machine "self-heal" after a guard failure — that self-healing *was* bug #41, and it silently destroyed the operator's layer-to-layer registration. #55 records this explicitly: the resolution is to stop the bad datum existing, or to normalise frames properly — **not** to restore automatic re-datuming. A future agent reading "it used to self-heal" will be tempted. Don't. |
| 4 | **A datum is never captured from a moving axis.** | `doSetHome()` and the settle fallback both refuse above `|vel| > 0.05` turns/s (~3 RPM) — `spincoater.cpp:826`. All datum-writing reads go through `feedbackStable()` (two consistent reads), never a single `feedback()`. |
| 5 | **Dispense volume and UV cure time are elastomer-dependent and belong in the GUI, not in G-code.** | Owner decision 2026-08-05 (#49). No hardcoded values, no per-material hand-editing of `fullcode.gcode`. |
| 6 | **`RMR_Controller.html` and `RMR_Touch.html` are the UI. No new GUI.** | Stated in #47's fix checklist and again in #49. |
| 7 | **`getProcedureResult()` returning −1 (unreadable) means UNVERIFIED, not FAILED.** | An ODrive firmware lacking the property must not brick a working machine. Only a successfully-read non-zero value hard-fails (`spincoater.cpp:635-646`). |
| 8 | **Expect post-spin behaviour to change on first flash of #39.** | The >1-turn guard may replace the long return crawl with an explicit refusal. That is intentional, and the error text is diagnostic for #46. **Do not report it as a regression.** |

---

## 5. Work queue

### Tier 0 — start immediately, parallel to everything

- **#46 (BENCH).** See §2. Highest information value in the backlog; gates the correct design of #52, #54,
  #55 and the datum half of #45. Prerequisite: recover or rewrite `odrive_report.py`.
- **#53** (gripper servo shudder — bench diagnosis first), **#18** (re-test relays after the module swap),
  and the mechanical/shop backlog (#2, #4, #7, #20, #21, #22, #27, #33, #34, #35, #36, #37). No firmware
  coupling, no shared files.

### Tier 1 — land the stack, bottom-up

Bench-flash the tip, verify, then merge **#38 → #39 → #51 → #56 → #57 → #58**. Do not start new firmware
work in `spincoater.cpp` before this lands — #45, #52, #54 and #55 all edit the same file and in several
cases the same functions.

### Tier 2 — UI, genuinely parallel to all firmware

**#47 first, then #48.** These touch only the two HTML files, and the stack's HTML edits are confined to the
M112/M999 wording — nowhere near the spin state map (`Controller:988-1057`, `Touch:1031-1060`) or the
program runner. A UI branch off `main` will not conflict with the stack.

Caveat: **#47's correctness depends on the token inventory that only exists at the stack tip.** Write it
against the tip's tokens (`INDEX_INCOMPLETE`, `INDEX_HOME_FAILED`, `HOME_SET_FAILED`,
`CYCLE_COMPLETE_NO_HOME`, the `WARN:` class) even though it merges independently — otherwise you ship a UI
that is correct for a firmware nobody is running.

Note on #48: the issue body cites only `RMR_Controller.html`, but **the identical pattern is in
`RMR_Touch.html`** (`:1078` → `progOnOk()`, 1 s M114 poll at `:1236`, `progOnOk()` at `:1332`). Fix both or
production keeps the bug.

### Tier 3 — new firmware, strictly serial, one agent one issue

**#45 → #54 → #55 → #52.** These **cannot** be parallelised:

- `boot()` — #45 (no-search variant, drop the `_homePos` write) and #54 (restore a persisted datum) both
  rewrite it.
- `doIndexHome()` — #55 (the guard at `spincoater.cpp:665`) and #52 (whether both phases are needed) both
  restructure it; #41/#43 and #44 already restructured it in the stack (#42 touched `ensureClosedLoop()`,
  not `doIndexHome()`).
- `doSetHome()` — #55's option 4 (guard M751 against capturing a multi-turn position).
- The `_homePos` / `_datumSet` **representation** — all four depend on what the datum fundamentally *is*
  (absolute multi-turn vs. fractional offset from the index mark). Changing it in one issue silently
  changes the meaning of the other three.

Order rationale: #45 first because persisting (#54) a datum that `boot()` still overwrites is pointless, and
because #45 is the only one of the four that is well-specified today. #54 second — it is the operator-visible
daily pain (every USB reconnect re-zeroes the machine). #55 third; its correct option depends on #46's answer
*and* on whether #54 changed the representation. #52 last, because it is a design review that will re-open
decisions the previous three just made — better as the consolidation step than the opening move.

### Tier 4

**#49** (elastomer parameters in the GUI). Depends on #48's runner correctness and on an owner decision about
the parameter set. Largest greenfield item and the least specified — guard against scope creep into a new GUI
(decision 6).

### Truly concurrent lanes

`#46 (bench)` ‖ `stack merge (firmware)` ‖ `#47 → #48 (HTML)` ‖ `#53 + mechanical backlog (shop)`.
Four lanes, no shared files. Everything inside Tier 3 is one lane.

### Issue-number correction

The issue numbers **#48 and #49 have been transposed in some earlier notes**. Verified against `gh`:

- **#48** = `[ui][major] Program Runner wait-for-ok is defeated by auto-report M114 oks`
- **#49** = `[enhancement] Elastomer-dependent dispense volume and UV cure time must be user-editable in the touchscreen GUI`

Use the GitHub numbering.

---

## 6. Open questions — only the owner or the bench can answer

### For the bench (on-site, hardware present)

1. **#46, the whole checklist in §2** — especially: *after an index search, does `pos_estimate` return near
   zero, or hold its pre-search value?* One observation, four issues unblocked.
2. **Time an actual spin-down from `M750 S5000 ... C1`.** Requested in PR #57's bench steps. #57's ramp-down
   progress/timeout constants are currently guesses; a real coast time is needed to sanity-check them. A
   constant set too tight will declare a healthy long spin-down a failure and emit `DECEL_STALL` /
   `DECEL_LINK_LOST` on good hardware.
3. **Does a visibly-good `M752` ever report a non-zero `procedure_result`?** Requested in PR #56's bench
   steps. #56 hard-fails on any successfully-read non-zero value. If a healthy home reports non-zero, that
   hard-fail must be demoted — report it rather than working around it.
4. **Is a brake resistor fitted on the S1, and what absorbs regen on this PSU?** Requested in PR #51's bench
   steps. Explicitly flagged unknown in the owner's #40 comment. Determines whether active braking on e-stop
   is ever viable (decision 1).
5. **Does the flashed tip still stream normal G-code correctly at 250000 baud with `EMERGENCY_PARSER`
   enabled?** Highest-consequence unverified change in the stack.
6. **Does M112 mid-spin actually stop the rotor**, and does the board come back cleanly on USB reconnect
   with the spincoater auto-disarmed?
7. **`M752` immediately after an `M750` spin** — PR #58's flagged regression check. Must complete normally,
   not abort with "no consistent position read".
8. **#53:** pulse-width variation on the servo signal line while holding; 5 V rail quality at the servo
   connector; does the shudder change with step rate; does the lid servo (P1) shudder identically unloaded?
9. **#18:** relay behaviour after the module swap (both loads on NO, active-HIGH).
10. **ODrive J11 logic supply — two "authoritative" docs disagree and neither is verified.** `PIN_MAP.md:95`
    says the ODrive provides its own 5 V logic supply; `claude.md:405-406` and
    `SpincoaterStage/INTEGRATION_PLAN.md:36-37` say Mega 5 V → J11 `ISOVDD` and Mega GND → `ISOGND`. These
    are mutually exclusive wirings, and getting it wrong either leaves the isolator unpowered (dead link —
    exactly the #46 symptom class) or back-feeds a rail. **UNVERIFIED — no firmware source can settle a
    wiring question.** Resolve on the bench, then delete the wrong row.

### For the owner (process / product decisions)

11. **Does the DEA process require the chuck to return to a known angle after every layer, or only at
    defined points?** (#52 Q1.) Decides whether the post-spin dance should exist at all, and whether `H`
    should default to 0.
12. **What is the datum, fundamentally — an absolute multi-turn encoder position, or a fractional offset
    from the index mark?** (#52 Q2, #55 option 3.) The `DEG` maths already assumes the latter
    (`fmod((pos − _homePos) * 360, 360)`), so representation and use currently disagree. Needs #46 first.
13. **Is `trap_traj.config.vel_limit = 0.25` turns/s (~15 RPM) the right return speed with a wet coated
    substrate on the chuck?** (#52 Q4.)
14. **#54: what should happen on restore if the ODrive was power-cycled independently of the Mega?** A
    persisted datum is meaningless in a new encoder frame, and nothing today can detect an ODrive restart.
    Accept-and-warn, refuse-and-require-M751, or persist a frame fingerprint?
15. **#47: `DegFromHome`** — emit it from firmware after homing, or re-key the Home stat card on `HomePos`?
    Both UIs display a key the Marlin build never emits (`Controller:1028`, `Touch:1057`).
16. **#49: what is the per-elastomer parameter set?** Minimum named in the issue: dispense push mm, retract
    mm, cure seconds; likely also spin RPM/duration per layer. Which elastomers, and what values?
17. **#49: which values are authoritative in `fullcode.gcode`, the code or the comments?** The audit found
    `G1 E-6` against a comment saying "push 4 mm", and `G4 S480` against "510 seconds".
18. **#49: where is the "started touchscreen GUI elsewhere"** the issue refers to? In-repo the touch UI is
    `RMR_Touch.html`. If a different file is the real target, an agent will otherwise extend the wrong one.
19. **#46: does `odrive_report.py` still exist anywhere?** Not in this repo (verified).
20. **#48: which fix?** Suspend the M114 auto-report while a program runs (simple, loses live position during
    runs), or strict line-numbered ok-attribution (more work, keeps telemetry)?
21. **Merge policy:** merge all six once the bench signs off, or incrementally as each PR's checklist passes?
    Incremental merging requires retargeting each surviving PR's base as its parent lands.
22. **`SpincoaterPinMap.jfif`** is referenced by `claude.md:468`, `README.md:34` and `PIN_MAP.md:97,177` but
    **is not in the repo** (`git ls-files | grep -i jfif` is empty). The remote colleague is being pointed at
    a wiring reference that cannot be opened. Restore it or delete the four references.

---

## 7. Traps — discovered the hard way

### 7.1 The UI substring-matching trap — failures render as green successes

Both UIs dispatch spincoater tokens with `String.includes()`, first match wins. The firmware's **failure**
tokens contain the **success** tokens as substrings. Verified in source:

| Firmware emits | UI matches | Operator sees |
|---|---|---|
| `ERR: CYCLE_COMPLETE_NO_HOME` (`M750.cpp:411`) | `includes('CYCLE_COMPLETE')` (`Controller:1012`, `Touch:1043`) | phase idle, "Cycle complete" — plus a **green success toast** in Touch |
| `ERR: HOME_SET_FAILED` (`M751_M752.cpp:36`) | `includes('HOME_SET')` (`Controller:1014`, `Touch:1045`) | "Home datum set" on a failed M751 |
| `STATE:HOME_SETTLE` (`spincoater.cpp:681`) | `includes('HOME_SET')` | "Home datum set" **while the rotor is still crawling back to the datum** |

Also live: both `stateMap`s still carry the removed `INDEX_SETTLE` key (`Controller:988-989`,
`Touch:1031`) and lack `HOME_SETTLE`, `MEASURE_LINK_LOST`, `DECEL_LINK_LOST`, `DECEL_STALL` — so a
comms-loss abort leaves the phase indicator parked on "Decelerating…" forever.

Verified non-issue: `"INDEX_INCOMPLETE"` does **not** contain `"INDEX_COMPLETE"`.

**Rules that follow:**
- Never add a firmware token that contains an existing token as a substring.
- When fixing #47, use exact-token matching, not `includes()`. Appending map entries is not a fix — the
  dispatcher is insertion-ordered and first-match-wins, so a new key registered after `RAMP_DOWN` would
  never be reached.
- Never judge a cycle by the phase indicator. Read the `ERR:` / `WARN:` lines.

### 7.2 ODrive ASCII writes are unacknowledged

The protocol has no acknowledgements and no checksum. A single write can simply be lost.
Consequences already baked into the code, and required of anything you add:
- `emergencyStop()` sends `w axis0.requested_state 1` **twice** (`spincoater.cpp:109-118`).
- `forceIdle()` re-issues IDLE each poll round and *verifies* the state.
- M750's ramp-down re-asserts the stop command every 1000 ms.
- Fire-and-forget means fire-and-forget: nothing confirms the ODrive received the e-stop.

### 7.3 The axis returns to IDLE after BOTH success and failure

Reaching IDLE after an index search proves **nothing**. `spincoater.cpp:617-619` says so in a comment.
`axis0.procedure_result` is the **only** discriminator. This was bug #43: the old code treated IDLE as
success and reported `OK: INDEX_COMPLETE` for a home that never happened.

Related trap in the same family: the deleted `INDEX_FOUND_INSTANT` branch. A real index search is a
multi-second physical rotation, so "the axis is still IDLE right after the request" was always a
**refusal**, never a search that finished between polls. It was reported as success.

### 7.4 `String::toFloat()` / `toInt()` return 0 for garbage

This is the root of #44. The old `feedback()` gate was "the reply contains a space", so one corrupted byte
produced a plausible `pos=0, vel=0` with `return true` — feeding the spin-down exit test, the >1-turn
guard, and the fallback datum. A truncated line became a truncated *value*.

At the tip: `readRaw()` and `feedback()` require a complete newline-terminated line; both tokens are
strict-parsed; `getState()` returns `ODRIVE_STATE_UNDEFINED` rather than laundering garbage into a state;
`parseStrictInt()` **range-checks before narrowing** `toInt()`'s `long` into a 16-bit AVR `int`, so a
corrupted all-digit reply cannot wrap into `procedure_result == 0` (SUCCESS).

Operator-visible effect: occasional *missing* telemetry lines where you previously got wrong ones, and hard
refusals where you previously got a silently wrong datum. That is the intent.

### 7.5 A fixed position tolerance is a stationarity test in disguise

The first version of `feedbackStable()` used a flat 0.01-turn agreement window. At the bench-measured ~4 ms
round trip, 0.01 turns is a hard **~150 RPM ceiling** — and these calls happen right after an index search,
when the ODrive has disarmed and the chuck is freewheeling well above that. It would have hard-failed `M752`
and `M750 H1` **on a mechanically healthy machine**.

The shipped version derives the window from the measured velocity (`spincoater.cpp:379-381`:
`posTol = 0.01f + fabs(v1) * dt * 3.0f`), which keeps it a pure corruption check at any speed. The general
lesson: **any threshold on a position delta is implicitly a speed limit.** Check what speed it implies before
you pick the number.

### 7.6 `kill()` is terminal — M999 cannot recover it

See decision 2 in §4 for the source lines. `minkill()` deliberately *pets* the watchdog in its final loop, so
the board never self-resets. Interrupts are off; the command is never even received.

Corollaries operators must be told:
- **Recovery from E-STOP destroys the datum.** `_homePos` / `_datumSet` are plain RAM statics
  (`spincoater.cpp:37, :43`) with no EEPROM backing anywhere in the subsystem. Re-run M751 after any reset
  before any layer that depends on angular registration. That is issue #54.
- **The spincoater panel's "Stop" button is M112** (`RMR_Controller.html:691`, same in Touch). There is no
  soft stop for a running spin cycle anywhere in the UI or the firmware. Pressing Stop kills the whole
  firmware, freewheels the chuck, requires a board reset, and loses the datum.

### 7.7 Other traps worth knowing before you touch the subsystem

- **`clearErrors()` (`sc`) destroys the evidence.** It wipes `active_errors` and `disarm_reason`. Always
  `reportFault()` first. `doIndexHome()` credits the snapshot time back to its own transition window so
  diagnostics cannot cause the timeout they are reporting on.
- **`ok` does not mean the command succeeded.** Every M750/M751/M752 failure path returns normally, so
  Marlin emits a bare `ok`. Both program runners advance on it. Judge success only by the terminal marker:
  `OK: CYCLE_COMPLETE` / `OK: INDEX_COMPLETE` / `OK: HOME_SET` versus `ERR: CYCLE_COMPLETE_NO_HOME` /
  `ERR: INDEX_HOME_FAILED` / `ERR: HOME_SET_FAILED` / `ERR: INDEX_INCOMPLETE`. Several abort paths emit
  **no** terminal marker at all. Issue #48/#49 territory.
- **M752 and `M750 ... H1` physically rotate the chuck** — after the index search they re-arm closed loop
  and command a trapezoidal move at `vel_limit = 0.25` turns/s (~15 RPM) for up to 8 s. Do not run them with
  the lid open or anything resting on the chuck.
- **The >1-turn guard latches.** Nothing re-normalises `_homePos` into a new encoder frame. Once it trips,
  every subsequent M752 and every H1 cycle trips identically until M751 is run. The firmware says so on the
  wire. Issue #55 — and see decision 3 before you "fix" it.
- **`EMERGENCY_PARSER` compiled `M0`/`M1` in** as a side effect (`HAS_RESUME_CONTINUE`). With no display on
  this machine, an `M0`/`M1` in a G-code program will now **pause until an `M108` arrives**, where it
  previously returned "Unknown command". `fullcode.gcode` and `DemoProgram.gcode` were checked and contain
  none — but this is a real regression risk for any other production G-code and has **not** been
  bench-checked.
- **`Serial2` is opened during Marlin `setup()`** by `startupSafetyDisarm()` (`MarlinCore.cpp:1284`), which
  transmits two ODrive IDLE requests on **every** board reset — including the DTR reset a browser triggers
  on connect. Pin 16 is not idle at power-on. The *ODrive probe* is still deferred to the first
  M750/M751/M752; `M753` calls `init()` only and neither boots nor moves anything, which makes it the right
  first command on a cold bench.
- **The docs are not trustworthy yet.** A prior audit found `SpincoaterStage/INTEGRATION_PLAN.md:74-89`
  still documenting M750's `A`/`C` as accelerations in rev/s² (defaults 15.0 / 100.0). They are **times in
  seconds** (`M750.cpp:163-164`; `SPINCOATER_DEFAULT_RISE 5.0f` / `SPINCOATER_DEFAULT_SINK 1.0f` at
  `Configuration_adv.h:3513-3514`). Following that table gives a 15-second ramp-up and a 100-second
  ramp-down on a real DEA layer. Verify any doc claim against source before acting on it.

---

## 8. Review findings that keep recurring

The adversarial pre-commit review is the reason this stack is not worse. **Three of the four fix PRs had a
self-inflicted regression caught by review before commit** — in each case a change that was *correct in
isolation* and *harmful in context*. Expect the same class of mistake in your own work.

| PR | Review outcome | The self-inflicted regression | The class |
|---|---|---|---|
| **#51** (#40 e-stop) | 4 lenses, 3 green / 1 red | The red was not a new regression: it was stale M999 recovery claims across the docs and **both UIs**, which the change made actively dangerous. Fixed by adding commit `f85257c` to the same PR. | **A code change invalidated documentation elsewhere in the repo.** Grep the docs and both UIs for anything the change makes false. |
| **#56** (#41/#43 honest exits) | 2 rounds, 8 agents. Round 1: 3 green / 1 red | Making `doIndexHome()` return an honest `false` from the arm-refusal exit routed M750's H1 fallback into `doSetHome()` — **destroying the operator's datum on a path where the index search had succeeded and the rotor was parked correctly.** Fixed with `isDatumValid()`. | **Making an error path honest changed which caller branch runs.** When you start reporting a failure that was previously silent, audit every caller's failure handling. |
| **#57** (#42 bounded waits) | 3 lenses, 1 green / 2 red, 4 blocking findings | A plain wall-clock cap on ramp-down would have aborted a **mechanically healthy** machine: if the drive self-disarms on regen overvoltage, the chuck coasts down from 5000 RPM with comms perfectly alive. The previously-passing bench test `M750 S3000 D10 A5 C1 H1` would have started failing. Fixed by separating *link liveness* from *lack of progress* as two independent discriminators. | **A single timeout conflated "the link died" with "this is taking a while".** Only one of those is a fault. |
| **#58** (#44 strict parsing) | 3 lenses, 1 green / 2 red; both blocking findings were the same defect | The flat 0.01-turn agreement window in `feedbackStable()` — a ~150 RPM ceiling that would have hard-failed `M752` and `M750 H1` on healthy hardware right after an index search. See §7.5. | **A tolerance chosen without computing what physical limit it implies.** |

The pattern across all four: **the danger is not in the bug being fixed, it is in what the fix does to a
previously-passing path.** Before you commit, ask specifically:

1. What was silently succeeding that will now loudly fail — and who handles that failure?
2. Does any threshold I introduced imply a physical limit (speed, time, distance) I have not calculated?
3. Does this make any doc, comment, PR body or UI string elsewhere in the repo false?
4. Would a mechanically healthy machine, under a plausible but non-fault condition, now be reported as
   broken?

One more consequence to communicate to the bench: **#56 converts previously-silent successes into hard
failures.** Expect the colleague to start seeing failures on runs that *appeared* to work before. That is
the intent — tell them in advance so it is not reported as a regression.
