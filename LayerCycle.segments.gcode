; ============================================================================
; RMR Layer Cycle — annotated for the Segment Runner (RMR_SegmentRunner.html)
;
; This is LayerCycle.gcode with segment markers and parameter declarations
; added. The executable lines are the same moves in the same order; every
; ;PARAM: default below is the literal that LayerCycle.gcode carries, so at
; default settings the two files command the machine identically.
;
; WHY THERE ARE TWO FILES
;   The {placeholder} substitution this file uses is done by the Segment Runner
;   at send time. Any other sender — RMR_Controller.html's Program Runner,
;   Pronterface, a pyserial script — would transmit "M750 S{spin_rpm}" verbatim
;   and Marlin would reject it. LayerCycle.gcode therefore stays as the plain,
;   runnable-anywhere copy.
;
;   That is a drift hazard and it is deliberate rather than accidental: keeping
;   two copies in sync is a chore, and collapsing them is a decision for the
;   owner once this runner has been proven on the bench. Until then, edit
;   LayerCycle.gcode first and mirror the change here.
;
; The Segment Runner's Preview pane expands this file with the current
; parameter values and no placeholders left in it — that is how you produce a
; plain file for any other sender.
;
; Derived from LayerCycle.gcode as checked on 2026-08-19.
; ============================================================================

; ── Spin settings ───────────────────────────────────────────────────────────
; M750 commands S+10 internally, so the chuck holds ~1010 RPM at spin_rpm=1000.
;PARAM: spin_rpm      label="Spin RPM"          default=1000 min=100  max=5000 unit=RPM scope=layer
;PARAM: spin_dwell    label="Spin dwell"        default=50   min=1    max=600  unit=s   scope=layer
;PARAM: spin_rise     label="Spin rise time"    default=3    min=1    max=30   unit=s
;PARAM: spin_sink     label="Spin sink time"    default=3    min=1    max=30   unit=s

; ── UV cure ─────────────────────────────────────────────────────────────────
;PARAM: cure_s        label="UV cure"           default=5    min=1    max=600  unit=s   scope=layer

; ── Dispense ────────────────────────────────────────────────────────────────
; Both are ABSOLUTE E targets, not relative distances: G-code cannot do
; arithmetic, so the runner cannot compute "push minus retract" for you.
; Net material dispensed = push_to - retract_to. At the defaults that is 4 mm.
;PARAM: push_to       label="Push to E-"        default=6    min=0.5  max=20   unit=mm  scope=layer
;PARAM: retract_to    label="Retract to E-"     default=2    min=0    max=20   unit=mm  scope=layer
;PARAM: dispense_feed label="Dispense feedrate" default=300  min=30   max=500  unit=mm/min

; ── Holds and settles ───────────────────────────────────────────────────────
;PARAM: presoak_s     label="Pre-spin soak"     default=10   min=0    max=300  unit=s   scope=layer
;PARAM: adhere_s      label="Adhesion hold"     default=50   min=5    max=300  unit=s
;PARAM: lift_hold_ms  label="Post-lift hold"    default=6000 min=0    max=30000 unit=ms
;PARAM: lid_settle_ms label="Lid settle"        default=1000 min=200  max=5000 unit=ms
;PARAM: grip_settle_ms label="Gripper settle"   default=300  min=100  max=5000 unit=ms
;PARAM: spin_settle_s label="Post-M752 settle"  default=2    min=1    max=30   unit=s


;SEGMENT: Home all axes
;PROVIDES: homed
G28                          ; home all (Z -> Y -> J -> X -> I)


;SEGMENT: Spincoater startup and datum
;REQUIRES: homed
;PROVIDES: spin-datum
M753                         ; UART diagnostic to ODrive link
M752                         ; encoder index search (fresh spin home reference)
G4 S{spin_settle_s}          ; let the rotor settle before the datum is taken
M751                         ; set current spin position as home datum
; M572                       ; no-op: LIN_ADVANCE is not compiled in, so this
;                             returns "Unknown command" then ok. Commented out
;                             rather than deleted in case it was a placeholder.


;SEGMENT: Lower syringe to dispensing height
;REQUIRES: homed
G1 B304 F3000                ; lower syringe height to dispensing position


; ════════════════════════════════════════════════════════════════════════════
; The per-layer block. Set the layer count in the runner; a blank cell in the
; layer table inherits the global value. LayerCycle.gcode's header claims
; "layer 1 of 5" while defining exactly one layer — this is the gap that closes.
; ════════════════════════════════════════════════════════════════════════════

;LAYER-SEGMENT: Dispense
;REQUIRES: homed
G92 E0                       ; reset syringe position
G1 E-{push_to} F{dispense_feed}      ; push syringe
G4 P{grip_settle_ms}                 ; let the pressure equalise
G1 E-{retract_to} F{dispense_feed}   ; retract to the hold position
G4 S{presoak_s}                      ; soak before spinning


;LAYER-SEGMENT: Spin and cure
;REQUIRES: homed spin-datum
M400                         ; drain planner before servo command
M280 P1 S116                 ; CLOSE lid before spinning
G4 P{lid_settle_ms}          ; lid settle
M750 S{spin_rpm} D{spin_dwell} A{spin_rise} C{spin_sink} H1   ; spin, then return to the saved datum
M42 P4 S1                    ; UV_ON  (active-high: S1 = energized. Never S255 — that bypasses
;                              the M42 digital-write patch and hijacks Timer0, CLAUDE.md gotcha #12)
G4 S{cure_s}                 ; cure
M42 P4 S0                    ; UV_OFF (active-high: S0 = de-energized)
M400                         ; drain planner before servo command
M280 P1 S30                  ; OPEN lid after cure
M400                         ; wait before syringe-height homing
G28 B                        ; home syringe height axis


;SEGMENT: Hover over left filters
;REQUIRES: homed
G1 Z0 F3000
G1 X607 F24000
G1 Y145 F24000
M400                         ; wait for XY move to complete
M280 P0 S170                 ; gripper open
G1 A73 F2000                 ; advance filter feed to first row


;SEGMENT: Grab left filter
;REQUIRES: homed
;PROVIDES: gripper-loaded
G1 Z43.7 F3000
M400                         ; wait for Z descent to complete
M280 P0 S85                  ; gripper close (slightly tighter hold)
G4 P{grip_settle_ms}         ; let the gripper settle before moving away


;SEGMENT: Raise and move to safe area
;REQUIRES: gripper-loaded
G1 Z0 F3000
G4 P{lift_hold_ms}           ; hold after grabbing and lifting the filter
G1 Y0 F24000


;SEGMENT: Hover over spincoater
;REQUIRES: gripper-loaded
G1 Y0 F24000
G1 X122.5 F24000
G1 Y21.5 F24000
G1 Z0 F3000


;SEGMENT: Press filter onto spincoater
;REQUIRES: gripper-loaded
G1 Z140 F3000                ; fast approach to contact height
G1 Z165 F300                 ; slow press
M400                         ; wait for press to complete
G4 S{adhere_s}               ; hold for the filter to adhere


;SEGMENT: Release and dispose used filter
;REQUIRES: gripper-loaded
G1 Z0 F3000                  ; raise to safe height
G1 Y0 F24000                 ; move gantry out of way
G1 X674 F24000
G1 Z15 F3000
M400                         ; wait for Z to settle
M280 P0 S170                 ; gripper open
G1 Z0 F3000
