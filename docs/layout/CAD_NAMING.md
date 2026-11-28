# CAD file naming: proposal

Proposal for issue #271, written 2026-11-25 and updated 2026-11-28. Nothing has been renamed yet. Names are from `origin/main` at `6cc44c8` (#270). Where each folder goes is in `README.md` in this folder.

## 1. The convention

The partner head-CAD repo that shares the ID space names its print files `ID_Part_version_Npcs_process.step`. In full:

`<group>-<nn>[P|S]_<Part_name>_v<NN>[a-z]_<feature tags>_<N>pcs_<process>[_<process note>].<ext>`

- Group number = subsystem folder. `P` = proposal, `S` = stand-in.
- The version is an integer per part (v24, v27, v29b).
- Process tokens: `N0.4_PETG`, `N0.2_PLA`, `N0.2_PETG_brim5mm`, `SLA_ClearV5`, `laser`, `laser_engrave`. When the material is open: `N0.4` alone (our 6-xx files).
- The name is the print list: ID, what, how many, how.

## 2. Proposed for RMR

One recommendation per point:

1. **One ID space with the partner head-CAD repo.** Groups 1 to 9 are taken: 1 to 5 by the head, 6 to 8 by the shared filter cartridge, mask and latch test, and 9 by the head proposal. RMR-only subsystems get groups 10 and up, so an ID never means two parts. The same part gets the same name in both repos (6-01 is 6-01 everywhere).
2. **Print files** (STEP/STL/DXF that someone prints or cuts) take the full name, with `Npcs` and process.
3. **Sources and companions** take `ID_Part_vNN` plus a role suffix and no pcs or process: `.FCStd`, `_assembly.step`, `_checks.txt`, `_sketch.png`, `_section.png`. Use group ID `-00` for a model that covers several parts. Use `_ref` for reference geometry nobody prints.
4. **Versions become integers per part, numbered in git history order.** Date stamps go (git keeps the dates). Mappings: `v20260914-A` to `v01`, `-B` to `v02`, and so on. LidDiffuser has an A in history (`4f2a1a2`), so B becomes `v02`.
5. **Folders move in the same PR as their files** (`README.md` in this folder, section 2), so each file is moved once and each generator is edited once.
6. **SolidWorks files (Gripper-A, PSU DIN mount, the catch basin, ResinMask) are renamed inside SolidWorks only** (Rename in the FeatureManager, or Pack and Go). An SLDASM finds its parts by file name, so `git mv` would break `gripper assembly.SLDASM` and `finger assembly.SLDASM`.

Groups:

| Group | Subsystem | RMR folders |
| --- | --- | --- |
| 6 | Filter cartridge (shared) | `Filter Cartridge/`, `Filter Sandwich Subassembly/` (superseded, 6-9x) |
| 7 | Mask (shared) | `Filter Cartridge/Lobe hold/` mask, `Exploratory Masks/` (7-9x, reference) |
| 8 | Latch test (shared) | `Filter Cartridge/Latch test/` |
| 10 | Dispense | `150 mL Syringe Adapter/`, `Tip Cap/` |
| 11 | Spin coater | `Spincoater/`, `Spincoater/Lid Diffuser/` |
| 12 | Frame and sensors | `Endstops/`, `PowerSwitch2020Mount`, `PSU DIN mount` |
| 13 | Control box and panel | `Control Box/`, `Operator Panel/` |
| 14 | Gripper-A | `Gripper-A/` (SolidWorks: rename in SolidWorks) |
| 15 | Storage towers | `Mask Stowage/`, `Belt Elevator/` (#267) |
| 90 | Superseded | `Filter Sandwich Subassembly/` (its files keep their 6-9x IDs) |

## 3. Mapping (current stem, then proposed stem)

Extensions stay. **Bold** = facts the repo does not state (count, nozzle or material); confirm these before a real run. "Refs" lists the text files outside the CAD tree that name the file. Most part exports are composed by their generator (`"%s-%s.step" % (Stem, name)`), so they show no refs but still change with the generator.

### 6 Filter cartridge (print names as in the shared print list)

| Now | Proposed | Process source | Refs |
| --- | --- | --- | --- |
| `Print 0.4mm nozzle/FilterCartridge-Body` | `6-01_Cartridge_body_v01_3pcs_N0.4` | shared print list | build_filter_cartridge.py, Assembly jig README |
| `Print 0.4mm nozzle/FilterCartridge-Collar-Gap-0.10` | `6-02_Collar_gap-0.10_printed_jaw_v01_3pcs_N0.4` | same | generator |
| `Print 0.4mm nozzle/FilterCartridge-CollarSpanner` | `6-03_Collar_spanner_v01_1pcs_N0.4` | same | generator |
| `FilterCartridge-Plate-G90-0.030in.dxf` | `6-04_Plate_G90_galvanized_0.030in_v02_4pcs_laser` | same | generator, Latch test README |
| `Print 0.4mm nozzle/FilterCartridge-PlateStandIn` | `6-05_Plate_standin_printed_fit_only_v02_1pcs_N0.4` | same | generator |
| `Print 0.4mm nozzle/FilterCartridge-Mask` | **no twin in the shared print list**: 7-01 there is the 0.2 mm nozzle print. Decide: a 7-01 variant (`_N0.4`) or retire | - | generator |
| `FilterCartridge-Shim` | `6-06_Shim_v01_**Npcs**_laser` (stainless 0.1 mm, option A per build_filter_cartridge.py:34) | generator comment | none |
| `Assembly jig/CartridgeAssemblyJig_White` / `_Black` | `6-07_Assembly_jig_v01_**1pcs**_N0.4_white` / `_black` | Assembly jig README:36 (PETG or PLA, so no material token) | Assembly jig README |
| `Assembly jig/CartridgeKnob_White` / `_Black` | `6-08_Assembly_jig_knob_v01_**1pcs**_N0.4_white` / `_black` | same | Assembly jig README |
| `Assembly jig/CartridgeAssemblyJig.FCStd` | `6-07_Assembly_jig_v01.FCStd` | model | build_cartridge_jig.py, README |
| `FilterCartridge.FCStd`, `-Body`, `-Collar`, `-Mask`, `-Plate` | `6-00_Cartridge_model_v01.FCStd`, `6-00_Cartridge_model_v01_Body.step`, ... | model exports, not prints | generator, both READMEs |
| `FilterCartridgePrintedFlange` (+ `-Body/-Collar/-Mask/-Plate`) | `6-00_Cartridge_model_printed_flange_v01` (+ `_Body` ...) | model | generator |
| `Lobe hold/FilterCartridgeLobeHold.FCStd` | `6-00_Cartridge_model_LobeHold_v01.FCStd` | model | generator |
| `Filter Sandwich Subassembly/FilterSandwich_v20260908` (.FCStd) | `6-90_Filter_sandwich_v01` | superseded by the cartridge | none |
| `FilterSandwich_v20260909` (.FCStd) | `6-90_Filter_sandwich_v02` | | build_filter_cartridge.py |
| `FilterSandwich_v20260908-00_LowerDisk`, `-01_UpperDisk` | `6-91_Sandwich_lower_disk_v01_**Npcs_process**`, `6-92_Sandwich_upper_disk_v01_**...**` | not stated | none |
| `FilterSandwich_v20260909-A-00/-01`, `-B-00/-01` | `6-91_..._v02` / `v03`, `6-92_..._v02` / `v03` | not stated | none |

### 7 Mask

| Now | Proposed | Process source | Refs |
| --- | --- | --- | --- |
| `Lobe hold/FilterCartridge-Mask-LobeHold` | `7-02_Mask_ThinMask20261016_LobeHold_v03_1pcs_N0.2` | Latch test README:311 | generator, Latch test README |
| `Exploratory Masks/ThinMask_20261016.STEP` | `7-90_Stencil_ThinMask20261016_v01_ref.STEP` | input pattern for every mask | **build_filter_cartridge.py:170 `StencilPattern`**, Latch test README; an external head build reads it through this generator |
| `Exploratory Masks/ResinMask_20261016` (.SLDPRT, .STEP) | `7-91_Stencil_ResinMask20261016_v01_ref` | dead end (Form 4L masks warped) | none; rename the SLDPRT in SolidWorks |

### 8 Latch test

| Now | Proposed | Process source |
| --- | --- | --- |
| `LatchTest-Mask-Recess0.0` / `0.5` / `1.0` | `8-01/8-02/8-03_Latch_mask_recess0.0/0.5/1.0_v03_1pcs_N0.2` | Latch test README:25-27 |
| `LatchTest-PullTool` | `8-04_Pull_tool_v02_1pcs_N0.4` | README:28 |
| `LatchTest-PileSeat` | `8-05_Pile_seat_v03_1pcs_N0.4` | README:29 |
| `LatchTest-Base-acrylic-3mm` / `-engrave` (.dxf) | `8-06_Base_acrylic_3mm_v02_1pcs_laser` / `_laser_engrave` | README:30-31 |
| `Lobe hold/LatchTest-LobeHold-PullTool` | `8-07_Pull_tool_LobeHold_v02_1pcs_N0.4` | README:310 |
| `Lobe hold/LatchTest-LobeHold-Mask-Recess0.0/0.5/1.0` | `8-08/8-09/8-10_Latch_mask_LobeHold_recess0.0/0.5/1.0_v02_1pcs_N0.2` | README:309 |
| `LatchTest.FCStd` | `8-00_Latch_test_model_v01.FCStd` | model |

Refs: `build_latch_test.py` (writes every name, lines 396-401), `Latch test/README.md`.

The version numbers in groups 6 to 8 come from the shared print list. #263 (the label ear) changed the lobe-hold mask after that list was read, so its version needs a recount. RMR `main` may be one version behind on the masks: the seated ball pockets are on the unmerged `claude/ball-pocket-seats` branch. A real run checks with checksums which files are identical.

### 10 Dispense

| Now | Proposed | Process source | Refs |
| --- | --- | --- | --- |
| `150mLSyringeAdapter_v20260914-A` (.FCStd) | `10-00_Syringe_adapter_150mL_v01.FCStd` | model | none |
| `..._v20260915-A`, `..._v20260916-A`, `..._v20261123-A` (.FCStd) | `10-00_..._v03`, `v04`, `v05` (0914-B has no FCStd but takes v02) | | build_plunger_wedge.py (0916-A, 1123-A) |
| `..._v20261123-A_Checks.txt`, `_Sketch.png` | `10-00_Syringe_adapter_150mL_v05_checks.txt`, `_sketch.png` | | generator |
| `-CylinderBodyClamp` at 0914-A, 0914-B, 0915-A, 0916-A | `10-01_Barrel_clamp_v01` ... `v04` + `_**Npcs_process**` | not stated | none |
| `-PlungerClamp` at 0914-A, 0914-B | `10-02_Plunger_clamp_v01`, `v02` + `_**Npcs_process**` (superseded by 10-03/10-04) | not stated | none |
| `..._v20261123-A-WedgeFrame` | `10-03_Plunger_wedge_frame_v01_**1pcs**_N0.4` | ratchet sized for 0.4 nozzle, build_plunger_wedge.py:88; material not stated | generator |
| `..._v20261123-A-WedgeSlider` | `10-04_Plunger_wedge_slider_v01_**1pcs**_N0.4_PETG` | Checks.txt:73 "PETG preferred for the slider" | generator |
| `Tip Cap/TipCap_v20261124-B` (.FCStd) | `10-10_Tip_cap_v02.FCStd` (A is in history) | model | build_tip_cap.py; open PR #259 changes it again |
| `_Assembly`, `_AssemblyOpen`, `_Checks`, `_Sketch` | `10-10_Tip_cap_v02_assembly`, `_assembly_open`, `_checks`, `_sketch` | | generator |
| `-CapArm`, `-CapYoke`, `-HornTube`, `-StopperCup`, `-StrutBody`, `-StrutEye` | `10-11_Cap_arm`, `10-13_Cap_yoke`, `10-14_Horn_tube`, `10-15_Stopper_cup`, `10-16_Strut_body`, `10-17_Strut_eye`, each `_v02_**1pcs**_**N0.4**_PETG` | TipCap Checks.txt:109-111 (PETG; nozzle not stated) | generator |
| `-CapShim` | removed in B (no file on `main`); 10-12 stays unused | | |

### 11 Spin coater

| Now | Proposed | Process source | Refs |
| --- | --- | --- | --- |
| `242mmCatchBasinSpincoater` (.SLDPRT, .STEP) | `11-01_Catch_basin_242mm_v01_**Npcs_process**` | not stated | build_basin_no_argon.py (`SourcePath`), its Checks.txt; rename the SLDPRT in SolidWorks |
| `242mmCatchBasinSpincoater_Checks.txt`, `_Sections.png` | `11-01_Catch_basin_242mm_v01_checks.txt`, `_sections.png` | | generator |
| `Lid Diffuser/LidDiffuser_v20261124-B` (.FCStd) | `11-10_Lid_diffuser_v02.FCStd` | model | build_lid_diffuser.py |
| `...-B-Cup` | `11-11_Lid_diffuser_cup_v02_**1pcs**_N0.4_ASA` | LidDiffuser Checks.txt:1 "ASA by FFF, 0.4 mm nozzle" | generator |
| `...-B-FacePart` | `11-12_Lid_diffuser_face_v02_**1pcs**_N0.4_ASA` | same | generator |
| `..._Assembly`, `_Checks`, `_Section` | `11-10_Lid_diffuser_v02_assembly`, `_checks`, `_section` | | generator |

### 12 Frame and sensors (no process stated anywhere; no text refs except PSU)

| Now | Proposed |
| --- | --- |
| `Endstops/Motor1EndStopBumper` (.FCStd), `-Body.step` | `12-01_Endstop_bumper_motor1_v01.FCStd`, `..._v01_**Npcs_process**.step` |
| `Endstops/Motor1EndStopMount` (.FCStd only) | `12-02_Endstop_mount_motor1_v01.FCStd` |
| `Endstops/Motor3EndStopBumper`, `-Body` | `12-03_Endstop_bumper_motor3_v01` |
| `Endstops/Motor3EndStopMount`, `-Body` | `12-04_Endstop_mount_motor3_v01` |
| `Endstops/SyringeAxisEndstop`, `-Body` | `12-05_Endstop_syringe_axis_v01` |
| `PowerSwitch2020Mount` (.FCStd), `-Body.step` | `12-06_Power_switch_mount_2020_v01` |
| `PSU DIN mount` (.SLDPRT, .STEP) | `12-07_PSU_DIN_mount_v01`. Refs: tools/draw_wiring.py, docs/adr/0010, docs/wiring/bom_frame.csv. Rename the SLDPRT in SolidWorks |

### 13 Control box and panel

| Now | Proposed | Process source | Refs |
| --- | --- | --- | --- |
| `Control Box/ControlBoxBlocks` (.FCStd, .step) | `13-00_Control_box_blocks_v01` | model | claude.md, docs/wiring/README.md, build_box_model.py |
| `Operator Panel/OperatorPanel` (.FCStd, .step) | `13-10_Operator_panel_v01` | model | claude.md, build_operator_panel.py, draw_wiring.py |
| `OperatorPanel_Bracket` | `13-11_Operator_panel_bracket_v01_**1pcs**_**N0.4**_PETG` | build_operator_panel.py:444 "all PETG" | claude.md |
| `OperatorPanel_CradleLeft` / `_CradleRight` | `13-12_Operator_panel_cradle_left` / `13-13_..._right`, `_v01_**1pcs**_**N0.4**_PETG` | same | claude.md |

### 14 Gripper-A (SolidWorks: rename inside SolidWorks, then commit)

| Now | Proposed |
| --- | --- |
| `gripper assembly.SLDASM` | `14-00_Gripper_A_assembly` |
| `gripper_base v37`, `gripper_top v14`...`v18`, `gripper mount v19`, `gripper knuckle v15`, `Gear Rack` | `14-01_Base_v37`, `14-02_Top_v14`...`v18`, `14-03_Mount_v19`, `14-04_Knuckle_v15`, `14-05_Gear_rack_v01` |
| `finger assembly.SLDASM`, `finger back v9`, `finger front v6`, `finger nail v10` | `14-10_Finger_assembly`, `14-11_Finger_back_v09`, `14-12_Finger_front_v06`, `14-13_Finger_nail_v10` |
| `PadOvermoldBase_v01`...`v04` | `14-20_Pad_overmold_base_v01`...`v04` |
| `RubberPadOvermold^gripper assembly` (+ `_20260921-A` ... `_v20261022-A`, 8 files) | `14-21_Pad_overmold_v01`...`v08` in date order (the undated one first) |
| `stress ball`, `Servo v1 (not printed)`, `servo geared screw adapter v1 (not printed)` | `14-90_Stress_ball_ref`, `14-91_Servo_v01_ref`, `14-92_Servo_screw_adapter_v01_ref` |

Gripper-A keeps its SolidWorks version numbers. Print processes and counts are not stated anywhere, so its print exports get pcs and process only once the owner states them.

### 15 Storage towers

| Now | Proposed | Refs |
| --- | --- | --- |
| `Mask Stowage/MaskStowage` (.FCStd), `_Checks.txt`, `_Sketch.png` | `15-00_Mask_stowage_v01.FCStd`, `_checks.txt`, `_sketch.png` | build_mask_stowage.py |
| `Belt Elevator/BeltElevator_v20261128-A` (.FCStd, `_Assembly.step`, `_Checks.txt`) | `15-10_Belt_elevator_v01.FCStd`, `_assembly.step`, `_checks.txt` | build_belt_elevator.py (#267, not on `main` yet) |
| `Belt Elevator/BeltElevator_v20261128-A-<Part>` (19 part STEPs) | `15-11` onward, one ID per part, with pcs and process from the generator | same |

## 4. What a real run would touch in RMR

- **10 generators** (`tools/build_*.py`; 11 once #267 lands). Each `Stem`/`DocName` and each composed `"%s-%s.step"` becomes a per-part table (ID, name, version, pcs, process). Then rebuild each one and diff the geometry, not just the names.
- **Docs:** `claude.md` (OperatorPanel parts, ControlBoxBlocks), `docs/wiring/README.md`, `docs/adr/0010-...`, `docs/wiring/bom_frame.csv`, `tools/draw_wiring.py`, `CAD/Filter Cartridge/Assembly jig/README.md`, `CAD/Filter Cartridge/Latch test/README.md`, and the generated `*_Checks.txt`.
- **Cross-repo:** `build_filter_cartridge.py:170` reads `ThinMask_20261016.STEP`, and an external head build runs that generator. Rename both together, or keep the old path as an alias for one release.
- **SolidWorks:** Gripper-A, PSU DIN mount, the catch basin and ResinMask are renamed in SolidWorks by the owner. Text refs to them get updated afterwards.
- **History:** `git mv` per file. `git log --follow` keeps each file's history.
- **Scope:** one issue, one branch, one PR per group (6-8, 10, 11, 12-13, 14, 15, 90), so each PR rebuilds one or two generators.

## 5. Open before a real run

- Counts and processes in bold above (endstops, syringe clamps, filter sandwich, catch basin, jig, tip cap nozzle, panel nozzle, Gripper-A prints).
- The 0.4 mm nozzle print-set mask: keep as a 7-01 variant or retire it.
- Group numbers 10 to 15 and 90: the partner head-CAD repo should agree, since the ID space is shared.
