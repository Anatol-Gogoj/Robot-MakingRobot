# Dispense retune — 150 mL catheter-tip syringe

Status: **implemented in the Process Sequencer's Syringe block on 2026-09-14** (both UIs), as a
device preset the Run Log can push into the sequencer in a few clicks. **Not yet run on the
machine.** The analysis below came from a separate discussion of drooling and dose precision with
the acrylic (CN9018 7.5 % HDDA); this file records the numbers, what they became in the UI, and
how each item maps onto this machine, whose plunger is the **C axis** (a homed linear axis, 1 mm/rev
lead screw, 1600 steps/mm, soft endstops 0–135 mm) and whose syringe height is the **B axis**.

## 1. The three defects the retune fixes

1. **Retract was in millimetres, not microsteps** — the root cause of air ingestion. The pull-back
   must be about 2 mm of the *tip bore*, which is a few hundredths of a millimetre of plunger.
2. **Dose rate was fast enough** that elastic storage in the plunger train and barrel was a few
   percent of the delivered volume.
3. **Nothing severed the viscous strand**, and no dwell let the stored pressure bleed off before
   the retract fired.

## 2. Measured hardware constants

| parameter | value | source |
|---|---|---|
| Barrel ID | 40.0 mm | calipers |
| Plunger area A | 1256.6 mm² | π/4 · ID² |
| Barrel stroke | 119.4 mm | 150 mL / A |
| Tip exit ID | 3.8 mm | calipers |
| Tip entry ID | 6.5 mm | calipers |
| Tip taper length | 33 mm | calipers |
| Tip internal volume | 0.70 mL | (π·L/3)(r1² + r1·r2 + r2²) |
| **C axis steps/mm (this machine)** | **1600** | 1 mm/rev screw, 1/8 µstep (`DEFAULT_AXIS_STEPS_PER_UNIT`) |
| **Volume per microstep (this machine)** | **0.785 µL** | A / 1600 |
| mm of plunger per mL | 0.7958 | 1000 / A |

The original analysis assumed a 5 mm/rev screw at 1/32 µstep (1280 steps/mm, 0.982 µL per
microstep). Every quantity below is in millimetres of plunger travel, which does not depend on the
steps/mm; only the microstep counts change.

## 3. Derivation (summary)

Tip resistance, conical, at η = 20 Pa·s:
R = (8·η·L / 3π) · (r1² + r1·r2 + r2²) / (r1³ · r2³) = 4.84 × 10¹⁰ Pa·s/m³.

Fluidic compliance, dominated by the barrel hoop rather than the plunger rod:
C_barrel = 2π·r³·L / (E·t) = 2.00 × 10⁻¹² m³/Pa · C_rod = A²/k = 1.25 × 10⁻¹² · C_liquid = V/K = 0.075 × 10⁻¹²
→ C_total = 3.32 × 10⁻¹² m³/Pa; **τ = R·C = 0.16 s at η = 20, 0.24 s at η = 30**.

Stored volume per dose is ΔP·C with ΔP = Q·R:

| dose time | ΔP | plunger force | stored volume | % of 5 mL |
|---|---|---|---|---|
| 5 s | 0.484 bar | 60.8 N | 0.161 mL | 3.2 % |
| 15 s | 0.161 bar | 20.3 N | 0.054 mL | 1.1 % |

Retract sizing: 1 mm of the 3.8 mm bore is 11.34 µL. Target pull-back 2 mm of bore:
retract = π·1.9²·2 / 1256.6 = **0.0180 mm of plunger** (29 microsteps at 1600 steps/mm).

Strand pinch-off is viscous-dominated (Oh ≈ 100): t_v = η·D / (2σ) ≈ 1.19 s at η = 20 — too slow to
wait out, hence a mechanical sever.

Air ingestion is structural: the critical bore for buoyant counter-flow is
D_crit = √(0.84·σ / (ρ·g)) = 1.62 mm, and the 3.8 mm tip is well above it, so air climbs at roughly
4.5 mm/min. It is self-clearing only because each 5 mL dose flushes the 0.70 mL tip seven times over
— hence the idle purge guard.

## 4. What each item became on this machine

| Analysis item | Implementation (Syringe block, both UIs) | Note |
|---|---|---|
| `RetractE = 0.0180` mm | **Pullback (mL)** = 0.0227 mL × 0.7958 mm/mL = 0.0181 mm; **max retract guard** 0.05 mm refuses anything larger before a byte is sent | 29 microsteps; a retract > 0.05 mm (62.8 µL) ingests air |
| `DoseFeedE = 15.9` mm/min (5 mL in 15 s) | **Dispense feed** 15.9 mm/min (feeds accept decimals) — 424 steps/s, inside the planner's budget; the hint shows the dose time | `DEFAULT_MINIMUMFEEDRATE` is 0.0 and `MIN_STEPS_PER_SEGMENT` 6, so a 6366-step dose is never clamped |
| `G4 P800` after the dose, **before** the retract | **Dwell after dispense**, default **2 s** (owner's choice; ~3τ ≈ 0.8 s is the physics floor), a browser-side abortable sleep after the dose's `M400` | order matters: retracting a still-pressurised system nets a suck when it relaxes |
| `G1 E-0.0180 F1.0` | retract at its own **retract feed** (1 mm/min in the preset) | the planner never steps below 120 steps/s (`MINIMAL_STEP_RATE`) = 4.5 mm/min on C, so the retract effectively runs at ~4.5 mm/min (0.24 s) — still gentle |
| Z snap (fast 50 mm/s lift) | **Snap lift after retract**: `G1 B-4 F3000` (B max is 3000 mm/min = 50 mm/s exactly), then the normal raise to B0 | B = 0 is up; the lift is clamped to the dispense height |
| Lateral shear `G1 X1.5` | **not available** | the syringe is fixed over the chuck: only B (height) and C (plunger) move; the snap lift alone severs the strand |
| Wiper drag at a park XY | **not available** | no wiper hardware and no XY motion at the syringe |
| `PurgeBarrel` at start of run and after idle > `IdleLimit` | **Purge** button (2 mL at 60 mm/min → same dwell / retract / snap) and **Purge before the first dose of a Run All** (opt-in); **idle limit** 300 s → a dose after longer idle *warns* (toast + journal) but never blocks | there is no waste position: the purge dispenses onto whatever is under the tip — put a waste cup there first (the button asks; the run-all option is the consent) |
| Generator-side E caps | **Max dose** (4.18 mm = 5.25 mL), **max retract** (0.05 mm), **barrel stroke** (119.4 mm, checked against the last `M114` C position) — enforced in the UI before sending | the C axis also has firmware soft endstops 0–135 mm, but the barrel is shorter than the axis |

All of these are inputs in the Syringe block, so they travel with a Run Log preset: the built-in
**`CN9018 7.5% HDDA · 150 mL syringe`** preset sets calibration 0.7958 mm/mL (barrel ID 40),
dose 5 mL, pullback 0.0227 mL, dose feed 15.9, retract feed 1, dwell 2 s, snap 4 mm at 3000,
max dose 4.18 mm, max retract 0.05 mm, stroke 119.4 mm, purge 2 mL at 60 mm/min, idle limit 300 s,
spin 1000 RPM / 50 s / 3 / 3 / H1, cure 480 s with the lid closed, Stamp block disabled (hand
pressing). New device → preset → Apply → Create pushes all of it into the Process Sequencer.

## 5. Open items from the analysis, answered for this machine

- **`M82` / `M83` global across E axes** — not applicable: the plunger is the C axis; the block uses
  `G91` for the relative dose / retract and `G90` after, exactly as before.
- **`DISABLE_OTHER_EXTRUDERS` must stay disabled** — not applicable (`EXTRUDERS 0`). The equivalent
  concern, the syringe-height lead screw (B, 5 mm/rev, on the self-locking boundary) de-energising
  while the plunger runs, is already covered: `DISABLE_IDLE_J` and `DISABLE_IDLE_K` are **off** in
  `Configuration_adv.h`, so B and C stay energised (only X and Y idle-off).
- **Stopper stick-slip** — 15 s gives 0.27 mm/s of stopper travel, in the stick-slip regime for a dry
  PP barrel. If the bead pulses, raise the dose feed to ~24–30 mm/min (8–10 s) and accept ~2 %
  stored volume. Do **not** silicone-lubricate the stopper.
- **E-stop drops the plunger driver enable** — `kill()` ends in `stepper.disable_all_steppers()`,
  which releases every axis including C (pin 20 ENA).

## 6. Test plan (unchanged, with this machine's numbers)

1. **Retract audit.** Every `G1 C-` the sequencer emits is ≤ 0.05 mm (the guard makes a larger one
   impossible; the Node test asserts `G1 C-0.0181 F1`).
2. **Dry run.** One dose with an empty barrel; confirm the 15.9 mm/min move is not clipped (watch the
   dose take ~15 s).
3. **Gravimetric calibration.** n = 20 doses at 80 %, 50 % and 20 % fill on a 0.01 g balance; target
   5.25 g at ρ ≈ 1.05; accept if CV < 2 % at every fill level **and** no trend with fill level (a trend
   means residual gas in the barrel).
4. **Strand check.** 20 consecutive doses, visual; no strand on the substrate. If strands persist, raise
   the snap lift or its feed (already at the B maximum) — there is no lateral shear on this machine.
5. **Drain test.** Park the loaded tip over a tared weigh boat for 10 min and weigh; bounds are
   0.05 mL/min (air-ingress limited) to 1.52 mL/min (tube-resistance limited). The measurement sets the
   **idle limit**; 300 s is a placeholder.

## 7. Safety notes

- The dose / retract / stroke caps live in the UI. Hand-written G-code bypasses them (the firmware
  soft endstops 0–135 mm on C still apply).
- The 150 mL barrel is roughly 30 doses of residence time in the machine: wrap it against ambient UV
  and confirm the material has equilibrated to room temperature — η is strongly temperature dependent
  and every number above assumes η ≈ 20–30 Pa·s.
- A purge dispenses onto whatever is under the tip. Put the waste cup there before pressing Purge or
  ticking purge-on-run.
