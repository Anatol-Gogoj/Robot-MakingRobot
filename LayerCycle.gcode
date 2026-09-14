; ============================================
; RMR Layer Cycle - checked 20260819
; Pick-and-place cycle: left filters -> spincoater -> dispose
;
; M400 is used before every servo/dwell command to drain
; the motion planner queue - ensures moves complete before
; the servo fires. Without M400, M280 executes immediately
; when parsed, not when the planner finishes preceding G1s.
; ============================================

; --- Prelude: Home all axes ---
G28                       ; home all (Z -> Y -> J -> X -> I)

; --- Spincoater startup diagnostics & home ---
M753                         ; UART diagnostic to ODrive link
M752                         ; encoder index search (fresh spin home reference)
G4 S2                        ; wait 2 seconds for settling
M751                         ; set current spin position as home datum
; M572                       ; no-op: LIN_ADVANCE is not compiled in, so this
;                             returns "Unknown command" then ok. Commented out
;                             rather than deleted in case it was a placeholder.

G1 B304 F3000                ; lower syringe height to dispensing position

; =========================
; 1000 RPM - layer 1 of 5
; M750 commands S+10 internally, so the chuck holds ~1010 RPM
; =========================
; First layer: push 6 mm, pause, retract 4 mm, pause
G92 E0                       ; reset syringe position
G1 E-6 F300                  ; push syringe 6 mm
G4 P300                      ; 300 ms pause
G1 E-2 F300                  ; retract 4 mm (E goes from -6 to -2)
G4 S10                       ; 10 s pause
M400                         ; drain planner before servo command
M280 P1 S116                 ; CLOSE lid before spinning
G4 P1000                     ; lid settle 1000 ms
M750 S1000 D50 A3 C3 H1      ; spin: 1000 RPM, 50s dwell, 3s accel, 3s decel, return to saved home
M42 P4 S1                    ; UV ON  (active-high: S1 = energized; S255 would bypass the M42 digital-write patch and hijack Timer0 - see CLAUDE.md gotcha #12)
G4 S5                        ; cure for 5 s
M42 P4 S0                    ; UV OFF (active-high: S0 = de-energized)
M400                         ; drain planner before servo command
M280 P1 S30                  ; OPEN lid after cure
M400                         ; wait before syringe-height homing
G28 B                        ; home syringe height axis

; --- Hover over left filters ---
G1 Z0 F3000
G1 X607 F24000
G1 Y145 F24000
M400                      ; wait for XY move to complete
M280 P0 S170              ; gripper open
G1 A73 F2000              ; advance filter feed to first row

; --- Grab left filter ---
G1 Z43.7 F3000
M400                      ; wait for Z descent to complete
M280 P0 S85               ; gripper close (slightly tighter hold)
G4 P300                   ; let the gripper settle before moving away

; --- Raise grippers & move to safe area ---
G1 Z0 F3000
G4 P6000                  ; hold 6 s after grabbing and lifting the filter
G1 Y0 F24000

; --- Hover over spincoater ---
G1 Y0 F24000
G1 X122.5 F24000
G1 Y21.5 F24000
G1 Z0 F3000

; --- Press filter onto spincoater ---
G1 Z140 F3000             ; fast approach to contact height
G1 Z165 F300              ; slow press
M400                      ; wait for press to complete
G4 S50                    ; hold 50 s for filter to adhere

; --- Release & dispose used filter ---
G1 Z0 F3000               ; raise to safe height
G1 Y0 F24000              ; move gantry out of way
G1 X674 F24000
G1 Z15 F3000
M400                      ; wait for Z to settle
M280 P0 S170              ; gripper open
G1 Z0 F3000

; ============================================
; Program complete
; ============================================
