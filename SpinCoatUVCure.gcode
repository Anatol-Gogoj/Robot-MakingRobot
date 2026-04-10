; ============================================================
; SpinCoatUVCure.gcode
; UV spin-coat protocol – 4 speed tiers × 5 cycles each
;
; Sequence per cycle:
;   1. Move E syringe -3 mm (relative dispense)
;   2. Spin cycle (40 s, specified RPM, 5 s accel, 5 s decel)
;   3. Open lid servo to 90°
;   4. UV lamp ON for 6 minutes
;   5. Close lid servo to 0°
;
; Tier 1 (cycles 1-5):  2000 RPM
; Tier 2 (cycles 6-10): 3000 RPM
; Tier 3 (cycles 11-15):4000 RPM
; Tier 4 (cycles 16-20):5000 RPM
;
; M400 is used before every servo/relay/dwell command to drain
; the motion planner queue – ensures moves complete before
; the next command fires.
; ============================================================

; --- Setup ---
G28 B                     ; home syringe height (J axis → B in G-code)
G1 B304 F3000             ; move syringe height to 304 mm (max travel, slow feed)
M83                       ; set E to relative mode (all E moves are incremental)

; ============================================================
; TIER 1 – 2000 RPM × 5 cycles
; ============================================================

; --- Tier 1 / Cycle 1 ---
G1 E-3 F500               ; 1. dispense: syringe -3 mm
M750 S2000 D40 A5 C5 H1  ; 2. spin 40 s @ 2000 RPM, 5 s accel, 5 s decel, home after
M400                      ; wait for any queued moves to complete
M280 P1 S90               ; 3. open lid (90°)
M400
M42 P4 S0                 ; 4. UV lamp ON  (active-low: S0 = energised)
G4 P360000                ;    dwell 6 minutes (360 000 ms)
M42 P4 S1                 ;    UV lamp OFF
M400
M280 P1 S0                ; 5. close lid (0°)

; --- Tier 1 / Cycle 2 ---
G1 E-3 F500
M750 S2000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 1 / Cycle 3 ---
G1 E-3 F500
M750 S2000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 1 / Cycle 4 ---
G1 E-3 F500
M750 S2000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 1 / Cycle 5 ---
G1 E-3 F500
M750 S2000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; ============================================================
; TIER 2 – 3000 RPM × 5 cycles
; ============================================================

; --- Tier 2 / Cycle 1 ---
G1 E-3 F500
M750 S3000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 2 / Cycle 2 ---
G1 E-3 F500
M750 S3000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 2 / Cycle 3 ---
G1 E-3 F500
M750 S3000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 2 / Cycle 4 ---
G1 E-3 F500
M750 S3000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 2 / Cycle 5 ---
G1 E-3 F500
M750 S3000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; ============================================================
; TIER 3 – 4000 RPM × 5 cycles
; ============================================================

; --- Tier 3 / Cycle 1 ---
G1 E-3 F500
M750 S4000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 3 / Cycle 2 ---
G1 E-3 F500
M750 S4000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 3 / Cycle 3 ---
G1 E-3 F500
M750 S4000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 3 / Cycle 4 ---
G1 E-3 F500
M750 S4000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 3 / Cycle 5 ---
G1 E-3 F500
M750 S4000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; ============================================================
; TIER 4 – 5000 RPM × 5 cycles
; ============================================================

; --- Tier 4 / Cycle 1 ---
G1 E-3 F500
M750 S5000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 4 / Cycle 2 ---
G1 E-3 F500
M750 S5000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 4 / Cycle 3 ---
G1 E-3 F500
M750 S5000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 4 / Cycle 4 ---
G1 E-3 F500
M750 S5000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; --- Tier 4 / Cycle 5 ---
G1 E-3 F500
M750 S5000 D40 A5 C5 H1
M400
M280 P1 S90
M400
M42 P4 S0
G4 P360000
M42 P4 S1
M400
M280 P1 S0

; ============================================================
; Program complete – 20 spin-coat/UV cycles across 4 tiers
; Total syringe travel: 60 mm retraction (20 × −3 mm)
; Total UV time: 120 minutes (20 × 6 min)
; ============================================================
