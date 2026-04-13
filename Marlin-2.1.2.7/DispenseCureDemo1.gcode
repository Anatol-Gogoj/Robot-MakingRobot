G28                          ; home all axes (lid opens first, then Z→Y→J→gripper close→X→I)

M751                         ; set current spin position as 0 degree home datum
M752                         ; encoder index search (keeps datum)
M753                         ; UART diagnostic to ODrive link

G1 B304 F3000                ; lower syringe height to dispensing position

; =========================
; 2000 RPM — layer 1 of 5
; =========================
; First layer: push 3 mm, pause, retract 2 mm, pause
G92 E0                       ; reset syringe position
G1 E-3 F300                  ; push syringe 3 mm
G4 P300                      ; 300 ms pause
G1 E-1 F300                  ; retract 2 mm (E goes from -3 to -1)
G4 S2                        ; 2 s pause
M400                         ; drain planner before servo command
M280 P1 S110                 ; CLOSE lid before spinning
G4 P1000                     ; lid settle 1000 ms
M750 S2000 D20 A3 C3 H1     ; spin: 2000 RPM, 20s dwell, 3s accel, 3s decel, home after
M42 P4 S0                    ; UV ON  (active-low: S0 = energized)
G4 S420                      ; cure for 7 minutes
M42 P4 S1                    ; UV OFF (active-low: S1 = de-energized)
M400                         ; drain planner before servo command
M280 P1 S30                  ; OPEN lid after cure

; 2000 RPM — layer 2 of 5
; Subsequent layers: push 5 mm (2 mm re-cover + 3 mm new), retract 2 mm
G92 E0
G1 E-5 F300                  ; push syringe 5 mm
G4 P300
G1 E-3 F300                  ; retract 2 mm (E goes from -5 to -3)
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S2000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 2000 RPM — layer 3 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S2000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 2000 RPM — layer 4 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S2000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 2000 RPM — layer 5 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S2000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; =========================
; 3000 RPM — layer 1 of 5
; =========================
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S3000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 3000 RPM — layer 2 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S3000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 3000 RPM — layer 3 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S3000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 3000 RPM — layer 4 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S3000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 3000 RPM — layer 5 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S3000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; =========================
; 4000 RPM — layer 1 of 5
; =========================
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S4000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 4000 RPM — layer 2 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S4000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 4000 RPM — layer 3 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S4000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 4000 RPM — layer 4 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S4000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 4000 RPM — layer 5 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S4000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; =========================
; 5000 RPM — layer 1 of 5
; =========================
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S5000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 5000 RPM — layer 2 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S5000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 5000 RPM — layer 3 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S5000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 5000 RPM — layer 4 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S5000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; 5000 RPM — layer 5 of 5
G92 E0
G1 E-5 F300
G4 P1000
G1 E-3 F300
G4 S2
M400
M280 P1 S110
G4 P1000
M750 S5000 D20 A3 C3 H1
M42 P4 S0
G4 S420
M42 P4 S1
M400
M280 P1 S30

; =========================
; End
; =========================
M42 P4 S1                    ; safety: UV OFF at end (active-low)
M400                         ; wait until all queued commands complete
