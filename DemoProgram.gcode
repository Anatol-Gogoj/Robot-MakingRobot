; ============================================
; RMR Demo Program
; Pick-and-place cycle: left filters → spincoater → dispose,
;                       right filters → spincoater → dispose
;
; M400 is used before every servo/dwell command to drain
; the motion planner queue — ensures moves complete before
; the servo fires. Without M400, M280 executes immediately
; when parsed, not when the planner finishes preceding G1s.
; ============================================

; --- PreDemo: Home all axes ---
G28                       ; home all (Z → Y → J → X → I)

; --- Hover over left filters ---
G1 Z0 F3000
G1 X607 F24000
G1 Y143 F24000
M400                      ; wait for XY move to complete
M280 P0 S170              ; gripper open
G1 A26 F2000              ; advance filter feed to first row

; --- Grab left filter ---
G1 Z41 F3000
M400                      ; wait for Z descent to complete
M280 P0 S90               ; gripper close

; --- Raise grippers & move to safe area ---
G1 Z0 F3000
G1 Y0 F24000

; --- Hover over spincoater ---
G1 Y0 F24000
G1 X117 F24000
G1 Y24 F24000
G1 Z0 F3000

; --- Press filter onto spincoater ---
G1 Z150 F3000             ; fast approach
G1 Z180 F300              ; slow press
M400                      ; wait for press to complete
G4 P2000                  ; hold 2s for filter to adhere

; --- Release & dispose used filter ---
G1 Z0 F3000               ; raise to safe height
G1 Y0 F24000              ; move gantry out of way
G1 X674 F24000
G1 Z15 F3000
M400                      ; wait for Z to settle
M280 P0 S170              ; gripper open
G1 Z0 F3000

; --- Hover over right filters ---
M400                      ; ensure Z raise complete
M280 P0 S170              ; gripper open (confirm)
G1 Z0 F3000
G1 X747 F24000
G1 Y143 F24000
G1 A26 F2000              ; advance filter feed to first row

; --- Grab right filter ---
G1 Z43 F3000
M400                      ; wait for Z descent to complete
M280 P0 S90               ; gripper close

; --- Raise grippers & move to safe area ---
G1 Z0 F3000
G1 Y0 F24000

; --- Hover over spincoater ---
G1 Y0 F24000
G1 X117 F24000
G1 Y24 F24000
G1 Z0 F3000

; --- Press filter onto spincoater ---
G1 Z150 F3000             ; fast approach
G1 Z180 F300              ; slow press
M400                      ; wait for press to complete
G4 P2000                  ; hold 2s for filter to adhere

; --- Release & dispose used filter ---
G1 Z0 F3000               ; raise to safe height
G1 Y0 F24000              ; move gantry out of way
G1 X674 F24000
G1 Z15 F3000
M400                      ; wait for Z to settle
M280 P0 S170              ; gripper open
G4 P500                   ; hold for servo travel
G1 Z0 F3000

; --- Return to pseudo home ---
G1 Z0 F3000
G1 Y0 F24000
G1 X650 F24000

; ============================================
; Program complete
; ============================================
