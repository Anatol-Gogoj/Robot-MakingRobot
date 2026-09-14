# ODrive S1 Configuration — Spin Coater

**Why this file exists.** The spin coater's ODrive configuration lives **only in the ODrive's
non-volatile memory**. Nothing in this repository sets it, and nothing would restore it. A factory
reset, an ODrive firmware update that clears config, or a replacement board loses it silently — and
the machine would then exhibit exactly the homing fault that took a full day to diagnose and rule
out (issue #46), with the diagnosis already closed.

Values below were read from the hardware on **2026-08-13**, over native USB with `odrivetool` and
independently over the Mega's UART with `M754`. Both agreed.

---

## Take a real backup as well

This table records the values that were *looked at*. It is **not** a complete config dump.
`odrivetool` can capture everything:

```bash
odrivetool backup-config ~/odrive-backup-$(date +%Y%m%d).json
```

Do that, keep it somewhere durable, and treat this file as the human-readable record of which
settings are load-bearing and why. Restoring is:

```bash
odrivetool restore-config ~/odrive-backup-YYYYMMDD.json
```

---

## Hardware

| Item | Value |
|---|---|
| Controller | ODrive S1, firmware **0.6.11** |
| Serial number | `006274725C90` |
| Motor | D5312s-330kV brushless outrunner, 7 pole pairs |
| Encoder | AMT102 incremental, 2048 PPR → **8192 CPR** |
| Index (Z) pulse | ODrive **GPIO 10** |
| DC bus | ~24 V (measured 24.07–24.12 V) |
| Motor thermistor | **None fitted, and never was** |

---

## Configuration

### Top level

| Property | Value | Notes |
|---|---|---|
| `config.gpio10_mode` | `0` (DIGITAL) | **Load-bearing.** `17` (AUTO) is a documented S1 + AMT-10x failure mode in which the Z pulse is never sampled at all. |

### `axis0.pos_vel_mapper.config` — position estimate

| Property | Value | Notes |
|---|---|---|
| `use_index_gpio` | `True` | **Load-bearing.** Without this, position is never index-referenced and `t 0 <x>` drives to the power-on shaft angle. |
| `index_gpio` | `10` | |
| `index_offset` | `0.0` | The index mark is position zero. |
| `index_offset_valid` | `True` | |
| `circular` | `False` | `pos_estimate` is a continuous multi-turn accumulator. See the note below — this is why issue #55 exists. |
| `circular_output_range` | `1.0` | |
| `scale` | `1.0` | |
| `offset` | `0.0` | |
| `offset_valid` | `False` | Distinct from `index_offset`; unused here. |
| `approx_init_pos` | `0.0` | |
| `approx_init_pos_valid` | `False` | |
| `passive_index_search` | `False` | |
| `use_endstop` | `False` | |

### `axis0.commutation_mapper.config` — commutation

| Property | Value | Notes |
|---|---|---|
| `use_index_gpio` | `True` | |
| `index_gpio` | `10` | |
| `index_offset` | `3.576504707336426` | Electrical alignment. Motor-specific — do not copy to another motor. |
| `index_offset_valid` | `True` | |
| `circular` | `True` | |
| `circular_output_range` | `1.0` | |
| `scale` | `7.0` | Pole pairs of the D5312s. |
| `offset` / `offset_valid` | `0.0` / `False` | |

### `axis0.config`

| Property | Value | Notes |
|---|---|---|
| `startup_encoder_index_search` | `False` | The ODrive does **not** index-search on power-up, so the absolute position frame is undefined after every ODrive power cycle until something crosses the index. Marlin's `Spincoater::boot()` performs that search instead. |

### `inc_encoder0.config`

| Property | Value | Notes |
|---|---|---|
| `enabled` | `True` | |
| `cpr` | `8192` | 4 × 2048 PPR. Must match the AMT102's DIP-switch resolution setting. |
| `filter` | `0` | |

### Motor thermistor — **changed 2026-08-13**

| Property | Value | Notes |
|---|---|---|
| motor thermistor `enabled` | **`False`** (was `True`) | See below. |

---

## The thermistor change, and why

**Symptom.** `ODriveError.THERMISTOR_DISCONNECTED` disarmed the axis mid-procedure, producing
`procedure_result = 3 (DISARMED)` on every index search. `clear_errors()` did not clear it — the
condition was live, not latched.

**Cause.** The check was enabled against hardware that was never fitted. The D5312s is a hobby-grade
outrunner with no built-in thermistor, and the ODrive's thermistor input was left floating. A
floating analog input drifts on noise and temperature, wandering across the disconnect threshold —
which is why the fault appeared **intermittently** after the machine had been running a while, and
why earlier spin cycles had succeeded.

**This is the leading explanation for the original "spin coater does not home properly" report.** An
intermittent fault that disarms the axis mid-search produces exactly that symptom: sometimes it
works, sometimes it doesn't, with no discernible pattern.

**Consequence of disabling it.** There is now no motor over-temperature protection. Since no
thermistor exists, that protection was never real — but it is now explicitly absent rather than
absent by accident. Spin cycles are short and the chuck is unloaded, so thermal risk is low.

**Still worth doing:** tie the thermistor input to a defined level rather than leaving it floating.
With the check disabled it no longer matters functionally, but a floating analog input on a machine
with this much stepper EMI is worth eliminating properly rather than muting. Tracked with #69.

---

## The one behaviour that surprised everyone

**The index search references position modulo one turn.** It corrects the fractional position within
a revolution and leaves the integer turn count accumulating, because `pos_vel_mapper.config.circular`
is `False` and `pos_estimate` is therefore a continuous multi-turn value.

Measured 2026-08-13 — two index searches, several hand turns apart:

| Search | Final `pos_estimate` | Fractional part |
|---|---|---|
| first | `0.38` | **0.38** |
| second | `10.375702` | **0.3757** |

Agreeing within 1.8°, against a measured settle error of 0.86°.

This is why `index_offset_valid: True` and a `pos_estimate` that never returns to zero are **not** a
contradiction, and why the old `>1 turn` guard rejected a perfectly healthy machine after every spin
(issue #55). Firmware comparing datum to position must compare **angularly**, not absolutely.

---

## What is NOT captured here

Everything not listed above — motor calibration values, current limits, velocity limits, CAN
settings, GPIO modes other than 10, controller gains. Those were never read, so their values are
unknown and this file cannot restore them.

**That is the argument for `odrivetool backup-config`.** This table tells a human which settings
matter; only a full dump can put the board back.

---

## Re-capturing this table

Over native USB:

```bash
odrivetool
```

```python
odrv0.config.gpio10_mode
odrv0.axis0.pos_vel_mapper.config
odrv0.axis0.commutation_mapper.config
odrv0.axis0.config.startup_encoder_index_search
odrv0.inc_encoder0.config
odrv0.fw_version_major, odrv0.fw_version_minor, odrv0.fw_version_revision
```

Or over the Mega's UART, with no USB involved at all:

```gcode
M754
```

`M754` covers the load-bearing subset and needs neither the ODrive's USB port nor a second tool. It
was written because that USB link failed hard (#68) while the UART stayed healthy.

---

## Related

- **#46** — the encoder index-reference investigation these values answered.
- **#55** — the >1-turn guard, explained by the modulo-one-turn behaviour above.
- **#68** — the USB isolator that made `odrivetool` unreachable.
- **#69** — the thermistor fault and the `boot()` false-success it exposed.
