# Builds the servo-driven, bistable tip cap for the 150 mL syringe (issue 243): an arm that presses
# a standard size 00 solid silicone stopper onto the syringe tip between doses, a yoke that carries
# the arm's pivot, the micro servo and the over-centre strut, and a bracket that hangs the yoke
# from the dispenser shelf rail: a 2020 aluminium drop post on two corner brackets, the yoke bolted
# to its slot. The machine carries the cap; every run uses one syringe type, so it is set up once. Concept and owner decisions: the 2026-11-21 B-driven flip study,
# section 9 (cap chosen over any flip, a common silicone stopper as the seal, tool-less swap).
# Owner 2026-11-23: the stopper's big end faces the tip; its small end sits in a tapered socket.
#
# Run with FreeCAD's console:  freecadcmd tools/build_tip_cap.py
# Writes CAD/Tip Cap/TipCap_v20261123-A.FCStd, one STEP per printed part (print orientation),
# _Checks.txt and _Sketch.png, and the whole assembly with its hardware, bracket and the machine's
# reference parts: _Assembly.step (closed) and _AssemblyOpen.step (open, with the bowl at the dispense
# pose). Run it in the FreeCAD GUI for the colours and the group tree in the STEP files (a headless run
# writes them flat and grey); for example: freecad.exe with a macro that runs this file.
#
# How it works. The arm swings in the vertical plane through the syringe axis, about a pivot beside
# the catheter tip, below the barrel's shoulder. Closed, the stopper's big end presses up on the tip
# end; open, the arm has swung 170 deg and stands up beside the syringe with the stopper face
# pointing down, high enough to clear the spin coater bowl's rim during a dose. A coilover strut
# (a compression spring on a guide rod, from the owner's spring kit) pushes from an anchor on the
# yoke against a crank on the arm. It passes dead centre at 60 deg, near closed, so it presses the
# arm shut (the tip itself is the stop) and holds it open (a stop block on the yoke) with the servo
# limp (DEACTIVATE_SERVOS_AFTER_MOVE). The rod is fixed in the strut's eye on the crank and slides in
# a blind bore in the strut's body on the anchor, inside the spring, so the spring cannot buckle.
# The servo drives the arm through a lost-motion slot: a pin on the servo horn rides in an arc slot
# in the arm, so the servo only has to push the arm past dead centre, and at either rest pose the pin
# sits near the middle of the slot, never loading the servo.
#
# The arm's pivot dowel comes from the yoke's cheek and ends at the arm; the servo shaft comes from
# the other side. The strut runs between the arm and the horn and never crosses the pivot axis. The
# horn pin sits on a ray of the arm the strut never sweeps. The pin is a metal sleeve clamped between
# the horn's spacer tube and a washer, 0.3 longer than the arm is thick, so it holds the arm on the
# dowel axially without clamping it.
#
# Frame (cap frame): origin at the nominal tip end centre; z up along the syringe axis; x horizontal
# toward the pivot (along the shelf, toward the B post, away from the side the syringe leaves by);
# y toward the shelf rail the bracket hangs from. Angles in the x-z plane are measured from +x toward
# +z. The arm angle phi is 0 closed and Swing open (counter-clockwise in x-z). Dimensions in mm.
# Every machine and syringe dimension here is a photo estimate (2026-11-20 flip study, dims.md) or a
# typical catalogue value; nothing is measured. The bracket slides in x and z, and shims set y,
# so the cap is set on the bench with a syringe fitted.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
OutDir = os.path.join(Root, "CAD", "Tip Cap")
Stem = "TipCap_v20261123-A"

P = dict(
    # Syringe tip (photo estimates; owner: the tip end OD is under 8 mm). The checks use the largest
    # plausible outline: tip end r 4.0, catheter tip to r 4.5, a cone from z ConeZ0 up to the shoulder,
    # barrel r 21.5 + 2.0 (Kapton and photo uncertainty).
    TipR=4.0, TipBaseR=4.5, ConeZ0=30.0, ShoulderZ=40.7, BarrelR=23.5, BarrelTopZ=151.0,
    # Tip end errors left after the bench set-up (height by sliding the yoke along the post, x by sliding the
    # post along the rail, y by the yoke's land thickness), from one syringe to the next: one syringe type
    # for every run, located by the barrel clamp and the flange seat; these allow for that and the set-up
    TipXYTol=1.5, TipZTol=1.5, TipXTol=1.0,
    # Stopper: size 00 solid silicone, PUL FACTORY listing 15 / 11 x 21 mm (Amazon B074RHKP62); the big
    # end is the face on the tip, the small end goes into the socket. Re-run with the delivered sizes.
    StopBigD=15.0, StopSmallD=11.0, StopL=21.0,
    Proud=9.0,             # stopper length standing out of the cup, nominal fit
    Interf=0.2,            # bore smaller than the stopper by this much on diameter (light press fit)
    FloorClear=1.0,        # gap below the small end, so the taper locates the stopper, not the floor
    EdgeR=0.3,             # allowance for the moulded edge radius of the stopper's face
    SiliconeE=2.5,         # MPa, Shore 50A class (Gent's relation); for the face tilt estimate only
    CupWall=2.4, CupFloor=2.5, VentD=3.0,
    LugX=9.0, LugHalfY=7.0,   # the cup's side lug that takes the arm's tang (two M3 screws along y)
    # Arm
    Pivot=(30.0, 20.0),    # x, z of the pivot: beside the catheter tip, below the shoulder, so the arm is
                           # short and the open cap stays inside the bowl
    ArmT=6.0,              # arm plate, y -3..+3
    HubR=7.0, HubY0=-5.0,  # hub runs from the arm plate down to y -5 on the cheek side (8 long on the dowel)
    DowelD=4.0, DowelBore=4.1, DowelSlip=4.05,   # 4 mm: its hole in the cheek also lets a PH0 driver reach the
                           # horn's centre screw; a slip fit held by a radial M3 grub screw, because pressing it
                           # in would load the cheek's thin column with the arm in place
    NutRelief=(10.5, 19.5, 1.5),   # annular groove in the cheek face under the pin's nut: r0, r1, depth
    Swing=170.0,           # closed to open
    OverTravel=8.0,        # closed stop without a syringe, past the nominal closed pose
    # Over-centre strut (coilover). Spring from the owner's Pianrui K-P-051-300 kit (304 stainless):
    # 0.7 wire x 7 OD x 25 free, 12 laps (the box label)
    WireD=0.7, SpringOD=7.0, SpringLf=25.0, SpringLaps=12,
    GMod=69000.0,          # MPa, 302/304 stainless spring wire (SMI handbook, 10.0e6 psi). The rate is an
                           # ESTIMATE with active coils = laps - 2 (closed ends assumed): measure it
    TauAllow=650.0,        # MPa, ASSUMED allowable shear at dead centre, about a third of the tensile strength
                           # typical of 302/304 spring wire this size; the kit does not state its wire grade
    SolidMargin=1.0,
    DCAngle=60.0,          # arm angle at which the strut passes dead centre: near closed, so the closed end gets
                           # the force and the open end, which only holds the arm's own weight, gets the stroke
    AnchorDir=75.0,        # direction of the anchor from the pivot: up beside the barrel, above the arm and clear of
                           # the parked cup (at 55 deg the open cup ran into it), and beside the bridge
    CrankR=8.0,            # crank screw on the arm (an M3 heat-set insert), on the ray that points at the anchor at
                           # dead centre
    SpringDCLen=11.9,      # spring length at dead centre with no seat shim: stays 1.4 off solid even if the box's
                           # "laps" are active coils with unground ends (solid 10.5); a printed shim on the eye's
                           # seat then raises the preload once the spring is measured
    SeatShim=0.0,          # shim thickness on the eye's seat, set after measuring the spring
    AltSpring=dict(Na=12, Solid=10.5),   # the other reading of the box label: 12 active coils, unground ends
    StrutY=7.5,            # the strut's axis plane
    SeatD=7.6, BodyD=7.6, RodD=4.0, RodPress=4.5,   # seats just over the 7.0 spring OD
    EyeCT=8.6,             # crank pivot to the eye's spring seat: leaves a 2 mm web between the rod's press bore and
                           # the pivot hole
    PinClr=4.5,            # anchor pivot centre to the bottom of the body's rod bore: a 2.45 web
    RodEngage=4.0,         # least rod engagement in the body's bore, at the longest strut
    BoreSpare=2.0,         # extra bore depth past the rod's deepest point, for the rod's cut length and press depth
    RodTol=0.3,            # cut the rod to length +0 / -RodTol
    # Both strut ends turn on a 4 mm OD brass sleeve (3.3 ID, 6.3 long) clamped by the M3 screw, so tightening
    # never clamps the eye or the body; each rides on its sleeve with 0.3 of axial play
    SleeveOD=4.0, PivotHoleD=4.1,
    CrankWasherY=(3.0, 4.5), CrankSleeveY=(4.5, 10.8), CrankHeadY=(10.8, 12.45), CrankHeadR=2.85,
    AnchorBossY0=10.8, AnchorSleeveY=(4.5, 10.8), AnchorWasherY=(4.0, 4.5), AnchorNutY=(2.2, 4.0),
    InsertD=4.0,           # M3 heat-set insert hole in the arm for the crank screw
    # Servo: MG90S class micro servo, typical catalogue dimensions, NOT measured. Its ears sit on the
    # plate's +y face; it goes in from +y through the plate's window
    ServoL=22.8, ServoW=12.2, ServoH=22.7, ShaftFromEnd=5.9,
    EarSpan=32.3, EarT=2.5, EarOff=4.0, EarHoleSpacing=27.8,
    CaseTopY=17.0,         # servo case top (shaft side) faces -y here
    HornY=(12.0, 14.0),    # horn arm
    HornCentreScrew=(11.0, 12.0, 2.25),   # the horn's centre screw head below the horn hub: y0, y1, radius
    HornHoleR=15.0,        # horn hole used for the pin; bench-check on the real horn
    PinRel=-60.0,          # the pin's ray from the stopper face's ray: a part of the arm the strut never sweeps
    HornW=5.0,
    StallNm=0.18,          # MG90S class stall torque from seller listings at 4.8 V, as in the concept
    ServoTravel=180.0,     # nominal; Marlin's default pulse range; bench-check
    LostMotion=20.0,       # deg of free play of the pin in the arm's arc slot
    SleeveD=3.0, SlotClear=0.4, TubeD=5.0, WasherD=7.0,
    PeelN=1.0,             # allowance for the stopper sticking to the tip, N at the face, for the servo check
    # Yoke
    CheekY=(-14.0, -6.0),
    StopR=(20.5, 24.0),    # radial band of the two stop blocks, outside the arm's ear and tail lobes
    StopSpan=14.0,         # angular size of each stop block
    StopY1=2.5,            # stop blocks reach into the arm plane to here
    ColumnX=(27.0, 33.0),  # the cheek's column up to the bridge: straight above the pivot, between the open
                           # arm (its edge at about 79 deg) and the barrel; the arm never sweeps there
    BridgeZ=(59.0, 77.0),  # 18 deep (its deflection goes as 1/depth^3), its top level with the plate top, so the
                           # yoke prints upside down on both
    PlateY=(17.0, 21.0), PlateX=(26.0, 71.0), PlateZ0=6.0, PlateTopZ=77.0,   # bottom above the chuck during a dose;
                           # the top carries the strut's anchor boss
    AnchorBossR=4.5,
    # Bracket: a 2020 aluminium post hung under the +v shelf rail (2020, rail bottom z 151 above the tip end,
    # photo) on two 2020 corner brackets, one on each x face. The yoke's land bolts to the post's -y slot with
    # two M5 drop-in T-nuts; side lips on its land hug the post: x slides along the rail, z slides along the post
    PostX=(48.5, 68.5),    # clear of the anchor screw's head and washer (x up to 47.0) and of the servo
    PostY=(23.0, 43.0),    # under the rail's footprint
    PostBottomZ=48.0,      # above the bowl rim during a dose (photo: the rim 42 above the tip end then)
    YokeBoltZ=(60.0, 71.0),  # the land then runs z 54..77: about 6 of height adjustment each way
    LandT=1.0, ShimNom=1.0,  # land on the plate, then printed 0.5 shims (two nominally) to the post face:
                             # y is set with the arm closed on a fitted syringe, by adding or removing shims
    LipT=2.0, LipDepth=3.0, LipGap=0.15,   # side lips on the land hug the post's outer x faces: they keep the
                             # yoke square to the post (the T-nuts' slot is left to the T-nuts)
    LipMinusZ=(54.0, 63.0),  # the -x lip stops below the anchor screw's head
    RailY=(23.0, 43.0), RailBottomZ=151.0,
    PostI=6982.0,          # mm4, 2020 profile (Misumi HFS5-2020 catalogue, 0.70 cm4)
    AluE=69000.0,
    PetgE=1800.0,          # MPa, PETG for long-term (creep) deflection; assumed
    TipZUnc=7.0,           # photo uncertainty of the tip end height below the rail
    # Bowl and chuck (photo estimates) for the envelope check
    BowlRimR=95.0, BowlRimUnc=12.5, RimAboveChuck=52.0, DispenseAboveChuck=10.0,
    ChuckClear=5.0,        # least clearance of anything on the syringe above the chuck top during a dose
)

Px, Pz = P["Pivot"]
Rad = math.radians
Deg = math.degrees


def Polar(r, a, c=(Px, Pz)):
    return (c[0] + r * math.cos(Rad(a)), c[1] + r * math.sin(Rad(a)))


def Rot2(p, phi, c=(Px, Pz)):
    a = Rad(phi)
    dx, dz = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * math.cos(a) - dz * math.sin(a), c[1] + dx * math.sin(a) + dz * math.cos(a))


def Cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


FaceDir0 = Deg(math.atan2(0.0 - Pz, 0.0 - Px))      # pivot to the face centre, closed
ArmR = math.hypot(Px, Pz)
CrankRel = P["AnchorDir"] - FaceDir0 - P["DCAngle"]   # the crank's ray points at the anchor at dead centre
CrankAng0 = FaceDir0 + CrankRel
CrankPt0 = (Px + P["CrankR"] * math.cos(math.radians(CrankAng0)), Pz + P["CrankR"] * math.sin(math.radians(CrankAng0)))
EarAng0 = FaceDir0 + P["PinRel"]
SpringDm = P["SpringOD"] - P["WireD"]
SpringNa = P["SpringLaps"] - 2
SpringK = P["GMod"] * P["WireD"] ** 4 / (8 * SpringDm ** 3 * SpringNa)
SpringSolid = P["SpringLaps"] * P["WireD"]


def StrutLen(phi, D):
    a = Rot2(CrankPt0, phi)
    A = (Px + D * math.cos(math.radians(P["AnchorDir"])), Pz + D * math.sin(math.radians(P["AnchorDir"])))
    return math.hypot(a[0] - A[0], a[1] - A[1])


def StrutRange(D):
    Ls = [StrutLen(-P["OverTravel"] + (P["Swing"] + P["OverTravel"]) * k / 356, D) for k in range(357)]
    return min(Ls), max(Ls)


# The body's length follows from the rod's travel over the swing; the anchor distance follows from the
# spring length wanted at dead centre (fixed point, a few passes). One anchor hole: the seal is tuned with a
# printed shim on the eye's seat (it shortens the spring), not by moving the anchor
BodyCA = 25.0
for _ in range(8):
    DNom = P["CrankR"] + P["EyeCT"] + P["SpringDCLen"] + BodyCA
    lo_, hi_ = StrutRange(DNom)
    BodyCA = P["PinClr"] + P["BoreSpare"] + P["RodEngage"] + (hi_ - lo_)
DNom = P["CrankR"] + P["EyeCT"] + P["SpringDCLen"] + BodyCA
AnchorDs = (DNom,)
LandZ = (min(P["YokeBoltZ"]) - 6.0, P["PlateTopZ"])   # the land reaches the plate top, so it prints on the bed
# rod length out of the eye's seat: the gap to the body's seat at the longest strut, plus the engagement
RodOut = StrutRange(DNom)[1] - P["EyeCT"] - BodyCA + P["RodEngage"]


def StopDia(d):
    """Stopper diameter at depth d below its big-end face."""
    return P["StopBigD"] + (P["StopSmallD"] - P["StopBigD"]) * d / P["StopL"]


MouthZ = -P["Proud"]
CupOutR = StopDia(P["Proud"]) / 2 + P["CupWall"]
CupBotZ = -P["StopL"] - P["FloorClear"] - P["CupFloor"]
LugScrews = [(CupOutR + 4.5, CupBotZ + 4.0), (CupOutR + 4.5, CupBotZ + 11.5)]


# ---------------------------------------------------------------- geometry helpers

def XZSolid(pts, y0, y1):
    w = Part.makePolygon([V(x, y0, z) for x, z in pts] + [V(pts[0][0], y0, pts[0][1])])
    return Part.Face(w).extrude(V(0, y1 - y0, 0))


def CylY(c, r, y0, y1):
    return Part.makeCylinder(r, y1 - y0, V(c[0], y0, c[1]), V(0, 1, 0))


def Box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def Hull(pts):
    pts = sorted(set((round(x, 6), round(z, 6)) for x, z in pts))
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and Cross((lo[-1][0] - lo[-2][0], lo[-1][1] - lo[-2][1]), (p[0] - lo[-2][0], p[1] - lo[-2][1])) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and Cross((hi[-1][0] - hi[-2][0], hi[-1][1] - hi[-2][1]), (p[0] - hi[-2][0], p[1] - hi[-2][1])) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def CirclePts(c, r, n=48):
    return [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def Sector(r0, r1, a0, a1, n=24, c=(Px, Pz)):
    out = [Polar(r1, a0 + (a1 - a0) * k / n, c) for k in range(n + 1)]
    if r0 <= 1e-9:
        return out + [c]
    return out + [Polar(r0, a1 - (a1 - a0) * k / n, c) for k in range(n + 1)]


def RotY(shape, phi):
    """Rotate a cap-frame shape by the arm angle phi about the pivot (counter-clockwise in x-z)."""
    s = shape.copy()
    s.rotate(V(Px, 0, Pz), V(0, -1, 0), phi)
    return s


# ---------------------------------------------------------------- the parts, closed pose

def Stopper():
    return Part.makeCone(P["StopSmallD"] / 2, P["StopBigD"] / 2, P["StopL"], V(0, 0, -P["StopL"]))


def Cup():
    cup = Part.makeCylinder(CupOutR, MouthZ - CupBotZ, V(0, 0, CupBotZ))
    lug = Box(CupOutR - 2.0, CupOutR + P["LugX"], -P["LugHalfY"], P["LugHalfY"], CupBotZ, MouthZ)
    cup = cup.fuse(lug)
    i = P["Interf"]
    rm = (StopDia(P["Proud"]) - i) / 2
    rs = (P["StopSmallD"] - i) / 2
    bore = Part.makeCone(rs, rm, P["StopL"] - P["Proud"], V(0, 0, -P["StopL"]))
    bore = bore.fuse(Part.makeCylinder(rs, P["FloorClear"] + 0.01, V(0, 0, -P["StopL"] - P["FloorClear"])))
    bore = bore.fuse(Part.makeCylinder(rm, 1.0, V(0, 0, MouthZ - 0.01)))
    cup = cup.cut(bore)
    cup = cup.cut(Part.makeCylinder(P["VentD"] / 2, P["CupFloor"] + 2, V(0, 0, CupBotZ - 1)))
    # slot for the arm's tang, open at the top and at +x
    h = P["ArmT"] / 2 + 0.15
    cup = cup.cut(Box(CupOutR - 1.5, CupOutR + P["LugX"] + 1, -h, h, CupBotZ + 2.0, MouthZ + 1))
    for x, z in LugScrews:
        cup = cup.cut(CylY((x, z), 1.6, -P["LugHalfY"] - 1, P["LugHalfY"] + 1))
    return cup.removeSplitter()


TangRect = [(CupOutR - 1.3, CupBotZ + 2.2), (CupOutR + P["LugX"] + 3.0, CupBotZ + 2.2),
            (CupOutR + P["LugX"] + 3.0, MouthZ - 0.5), (CupOutR - 1.3, MouthZ - 0.5)]
EarEnds0 = [Polar(P["HornHoleR"], EarAng0 + s * P["LostMotion"] / 2) for s in (-1, 1)]
SlotW = P["SleeveD"] + P["SlotClear"]


def ArmProfile():
    hub = CirclePts((Px, Pz), P["HubR"])
    link = Hull(hub + TangRect)
    tail = Hull(hub + CirclePts(CrankPt0, 4.5))      # crank lobe
    ear = Hull(hub + CirclePts(EarEnds0[0], SlotW / 2 + 2.0) + CirclePts(EarEnds0[1], SlotW / 2 + 2.0))
    return link, tail, ear


def Arm():
    y0, y1 = -P["ArmT"] / 2, P["ArmT"] / 2
    link, tail, ear = ArmProfile()
    arm = XZSolid(link, y0, y1).fuse(XZSolid(tail, y0, y1)).fuse(XZSolid(ear, y0, y1))
    arm = arm.fuse(CylY((Px, Pz), P["HubR"] - 0.02, P["HubY0"], y0 + 1.0))   # hub, longer on the cheek side
    arm = arm.cut(CylY((Px, Pz), P["DowelBore"] / 2, P["HubY0"] - 1, y1 + 1))
    # lost-motion arc slot for the pin sleeve
    w = SlotW / 2
    a0, a1 = EarAng0 - P["LostMotion"] / 2, EarAng0 + P["LostMotion"] / 2
    arm = arm.cut(XZSolid(Sector(P["HornHoleR"] - w, P["HornHoleR"] + w, a0, a1), y0 - 1, y1 + 1))
    for e in EarEnds0:
        arm = arm.cut(CylY(e, w, y0 - 1, y1 + 1))
    for x, z in LugScrews:
        arm = arm.cut(CylY((x, z), 1.6, y0 - 1, y1 + 1))
    arm = arm.cut(CylY(CrankPt0, P["InsertD"] / 2, y0 - 1, y1 + 1))        # M3 heat-set insert for the crank screw
    return arm.removeSplitter()


def ArmHardware():
    """Crank screw with its washers, moving with the arm (the strut's eye sits between them)."""
    t = CrankPt0
    return CylY(t, 1.5, -2.5, P["CrankHeadY"][1]).fuse(CylY(t, 3.5, *P["CrankWasherY"])).fuse(
        CylY(t, P["SleeveOD"] / 2, *P["CrankSleeveY"])).fuse(CylY(t, P["CrankHeadR"], *P["CrankHeadY"]))


def StopAngles():
    """Angles of the two stop faces in the stop band: the arm's outline at the open pose (most
    counter-clockwise) and at the over-travel pose (most clockwise)."""
    link, tail, ear = ArmProfile()
    pts = []
    for poly in (link, tail, ear):
        for k in range(len(poly)):
            a, b = poly[k], poly[(k + 1) % len(poly)]
            for j in range(21):
                pts.append((a[0] + (b[0] - a[0]) * j / 20, a[1] + (b[1] - a[1]) * j / 20))
    r0, r1 = P["StopR"]

    def Angles(phi):
        out = []
        for p in pts:
            q = Rot2(p, phi)
            r = math.hypot(q[0] - Px, q[1] - Pz)
            if r0 - 0.5 <= r <= r1 + 0.5:
                out.append(Deg(math.atan2(q[1] - Pz, q[0] - Px)))
        return out
    return max(Angles(P["Swing"])), min(Angles(-P["OverTravel"]))


StopOpenA, StopClosedA = StopAngles()
AnchorPts = [Polar(d, P["AnchorDir"]) for d in AnchorDs]
AnchorPt = AnchorPts[0]


def Teardrop(c, r):
    """A circle with a 45 deg point toward +z: prints without support upside down (z down)."""
    return CirclePts(c, r, 64) + [(c[0], c[1] + r * math.sqrt(2))]


def Yoke():
    cy0, cy1 = P["CheekY"]
    r0, r1 = P["StopR"]
    cx0, cx1 = P["ColumnX"]
    cheek = XZSolid(CirclePts((Px, Pz), 8.0), cy0, cy1)
    cheek = cheek.fuse(XZSolid([(cx0, Pz), (cx1, Pz), (cx1, P["BridgeZ"][1]), (cx0, P["BridgeZ"][1])], cy0, cy1))
    for (a0, a1), rc in (((StopOpenA, StopOpenA + P["StopSpan"]), 7.9), ((StopClosedA - P["StopSpan"], StopClosedA), 7.8)):
        # each hull on its own circle radius: shared polygon edges make the boolean invalid
        cheek = cheek.fuse(XZSolid(Hull(CirclePts((Px, Pz), rc, 47) + Sector(0.0, r1, a0, a1)), cy0, cy1))
        # the stop block itself; 1 mm into the cheek and a hair inside its outline, so the boolean has no
        # coincident edges to trip on
        cheek = cheek.fuse(XZSolid(Sector(r0, r1 - 0.05, a0 + 0.02, a1 - 0.02), cy1 - 1.0, P["StopY1"]))
    yoke = cheek.cut(CylY((Px, Pz), P["DowelSlip"] / 2, cy0 - 1, cy1 + 0.5))
    # radial M3 grub screw from below into the dowel hole
    yoke = yoke.cut(Part.makeCylinder(1.25, 8.5, V(Px, 0.5 * (cy0 + cy1), Pz - 9.0), V(0, 0, 1)))
    # relief under the pin's nut and the screw end
    r0, r1, dep = P["NutRelief"]
    ring = CylY((Px, Pz), r1, cy1 - dep, cy1 + 0.01).cut(CylY((Px, Pz), r0, cy1 - dep - 1, cy1 + 1))
    yoke = yoke.cut(ring)
    # bridge over to the servo plate
    yoke = yoke.fuse(Box(cx0, cx1, cy0, P["PlateY"][1], P["BridgeZ"][0], P["BridgeZ"][1]))
    # servo plate: the body goes through the window from +y, the ears sit on the +y face
    px0, px1 = P["PlateX"]
    plate = Box(px0, px1, P["PlateY"][0], P["PlateY"][1], P["PlateZ0"], P["PlateTopZ"])
    sz0 = Pz - P["ShaftFromEnd"]
    plate = plate.cut(Box(Px - P["ServoW"] / 2 - 0.4, Px + P["ServoW"] / 2 + 0.4, P["PlateY"][0] - 1, P["PlateY"][1] + 1,
                          sz0 - 0.4, sz0 + P["ServoL"] + 0.4))
    zc = sz0 + P["ServoL"] / 2
    for s in (-1, 1):
        plate = plate.cut(CylY((Px, zc + s * P["EarHoleSpacing"] / 2), 0.85, P["PlateY"][0] - 1, P["PlateY"][1] + 1))
    yoke = yoke.fuse(plate)
    # mounting land on the plate's +y face (shims go between it and the post), and side lips that hug the
    # post's outer x faces
    x0, x1 = P["PostX"]
    sx = 0.5 * (x0 + x1)
    z0, z1 = LandZ
    yl = P["PlateY"][1] + P["LandT"]
    yoke = yoke.fuse(Box(x0, x1, P["PlateY"][1] - 0.01, yl, z0, z1))
    ly1 = P["PostY"][0] + P["LipDepth"]
    g, t = P["LipGap"], P["LipT"]
    yoke = yoke.fuse(Box(x1 + g, x1 + g + t, P["PlateY"][1] - 0.01, ly1, z0, z1))
    yoke = yoke.fuse(Box(x0 - g - t, x0 - g, P["PlateY"][1] - 0.01, ly1, P["LipMinusZ"][0], P["LipMinusZ"][1]))
    for z in P["YokeBoltZ"]:
        yoke = yoke.cut(CylY((sx, z), 2.75, P["PlateY"][0] - 1, ly1 + 1))
    # anchor boss: the anchor hole (one per entry of AnchorDs), teardrop outline
    boss = XZSolid(Hull(sum((Teardrop(a, P["AnchorBossR"]) for a in AnchorPts), [])), P["AnchorBossY0"], P["PlateY"][0] + 0.01)
    yoke = yoke.fuse(boss)
    for a in AnchorPts:
        yoke = yoke.cut(CylY(a, 1.3, P["AnchorBossY0"] - 1, P["PlateY"][1] + 1))
    return yoke.removeSplitter()


def Shim():
    """Printed 0.5 shim between the land and the post (print several; the stack sets y)."""
    x0, x1 = P["PostX"]
    z0, z1 = LandZ
    sh = Box(x0 + 0.3, x1 - 0.3, 0.0, 0.5, z0 + 0.3, z1 - 0.3)
    for z in P["YokeBoltZ"]:
        sh = sh.cut(CylY((0.5 * (x0 + x1), z), 2.75, -1, 2))
    return sh


def Post():
    """2020 aluminium post (bought, cut to length), simplified: four 6.2 x 6 slots and the centre bore."""
    x0, x1 = P["PostX"]
    y0, y1 = P["PostY"]
    z0, z1 = P["PostBottomZ"], P["RailBottomZ"]
    p = Box(x0, x1, y0, y1, z0, z1)
    sx, sy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    for bx0, bx1, by0, by1 in ((sx - 3.1, sx + 3.1, y0 - 1, y0 + 6), (sx - 3.1, sx + 3.1, y1 - 6, y1 + 1),
                               (x0 - 1, x0 + 6, sy - 3.1, sy + 3.1), (x1 - 6, x1 + 1, sy - 3.1, sy + 3.1)):
        p = p.cut(Box(bx0, bx1, by0, by1, z0 - 1, z1 + 1))
    return p.cut(Part.makeCylinder(2.1, z1 - z0 + 2, V(sx, sy, z0 - 1)))


def Brackets():
    """Two 2020 corner brackets (bought), on the post's x faces, their other legs under the rail."""
    x0, x1 = P["PostX"]
    y0, y1 = P["PostY"]
    zt = P["RailBottomZ"]
    out = None
    for xf, sd in ((x0, -1), (x1, 1)):
        a, b = sorted((xf, xf + sd * 3.0))
        c, d = sorted((xf, xf + sd * 20.0))
        br = Box(a, b, y0 + 1, y1 - 1, zt - 20.0, zt).fuse(Box(c, d, y0 + 1, y1 - 1, zt - 3.0, zt))
        out = br if out is None else out.fuse(br)
    return out


# ---------------------------------------------------------------- reference parts (not printed)

def Syringe():
    s = Part.makeCone(P["TipR"], P["TipBaseR"], P["ConeZ0"], V(0, 0, 0))
    s = s.fuse(Part.makeCone(P["TipBaseR"], P["BarrelR"], P["ShoulderZ"] - P["ConeZ0"], V(0, 0, P["ConeZ0"])))
    s = s.fuse(Part.makeCylinder(P["BarrelR"], P["BarrelTopZ"] - P["ShoulderZ"], V(0, 0, P["ShoulderZ"])))
    return s


def Servo():
    sz0 = Pz - P["ShaftFromEnd"]
    body = Box(Px - P["ServoW"] / 2, Px + P["ServoW"] / 2, P["CaseTopY"], P["CaseTopY"] + P["ServoH"], sz0, sz0 + P["ServoL"])
    e = (P["EarSpan"] - P["ServoL"]) / 2
    ey = P["CaseTopY"] + P["EarOff"]
    ears = Box(Px - P["ServoW"] / 2, Px + P["ServoW"] / 2, ey, ey + P["EarT"], sz0 - e, sz0 + P["ServoL"] + e)
    dome = CylY((Px, Pz), 5.9, P["HornY"][1] + 1.6, P["CaseTopY"] + 0.01)
    return body.fuse(ears).fuse(dome)


def HornStack(psi):
    """Horn with its centre screw, the pin screw, spacer tube, sleeve, washer and nut, at the absolute
    horn angle psi."""
    y0, y1, rr = P["HornCentreScrew"]
    hub = CylY((Px, Pz), 3.5, P["HornY"][0], P["CaseTopY"]).fuse(CylY((Px, Pz), rr, y0, y1 + 0.01))
    L = P["HornHoleR"] + 3.0
    bar = XZSolid(Hull(CirclePts((Px, Pz), P["HornW"] / 2) + CirclePts(Polar(L - P["HornW"] / 2, psi), P["HornW"] / 2)),
                  P["HornY"][0], P["HornY"][1])
    pin = Polar(P["HornHoleR"], psi)
    h = P["ArmT"] / 2 + 0.15
    head = CylY(pin, 1.9, P["HornY"][1], P["HornY"][1] + 1.4)
    tube = CylY(pin, P["TubeD"] / 2, h, P["HornY"][0])
    sleeve = CylY(pin, P["SleeveD"] / 2, -h, h)
    washer = CylY(pin, P["WasherD"] / 2, -h - 0.5, -h)
    nut = CylY(pin, 2.3, -h - 0.5 - 1.6, -h - 0.5)
    screw = CylY(pin, 1.0, -h - 0.5 - 1.6, P["HornY"][1])
    return hub.fuse(bar).fuse(head).fuse(tube).fuse(sleeve).fuse(washer).fuse(nut).fuse(screw)


def AnchorHardware(a):
    screw = CylY(a, 1.5, P["AnchorNutY"][0], P["PlateY"][1])
    head = CylY(a, 3.5, P["PlateY"][1], P["PlateY"][1] + 0.5).fuse(CylY(a, 2.75, P["PlateY"][1] + 0.5, P["PlateY"][1] + 3.5))
    return screw.fuse(head).fuse(CylY(a, 3.2, *P["AnchorNutY"])).fuse(CylY(a, 3.5, *P["AnchorWasherY"])).fuse(
        CylY(a, P["SleeveOD"] / 2, *P["AnchorSleeveY"]))


def CylX(x0, x1, r):
    """Cylinder along the strut's local x, on the strut's axis plane."""
    return Part.makeCylinder(r, x1 - x0, V(x0, P["StrutY"], 0), V(1, 0, 0))


def PinHoleY(x, r=None):
    r = P["PivotHoleD"] / 2 if r is None else r
    return Part.makeCylinder(r, 20, V(x, P["StrutY"] - 10, 0), V(0, 1, 0))


def SlabCut(x0, x1):
    """Removes material outside y 4.5..10.5 between x0 and x1, around a pivot."""
    y0, y1 = P["StrutY"] - 3.0, P["StrutY"] + 3.0
    return Box(x0, x1, y0 - 10, y0, -10, 10).fuse(Box(x0, x1, y1, y1 + 10, -10, 10))


def StrutEye():
    """The eye on the crank, in the strut's local frame: crank pivot at x 0, the strut along +x."""
    rs = P["SeatD"] / 2
    e = CylX(-4.0, P["EyeCT"], rs).cut(PinHoleY(0.0)).cut(SlabCut(-5.0, 4.0))
    e = e.cut(CylX(P["EyeCT"] - P["RodPress"], P["EyeCT"] + 1, P["RodD"] / 2 - 0.05))   # rod press bore
    return e.removeSplitter()


def StrutBody():
    """The guide body on the anchor, local frame: anchor pivot at x 0, the strut along -x."""
    b = CylX(-BodyCA, 4.0, P["BodyD"] / 2).cut(PinHoleY(0.0)).cut(SlabCut(-6.5, 5.0))   # flat under the boss
    b = b.cut(CylX(-BodyCA - 1, -P["PinClr"], P["RodD"] / 2 + 0.1))                     # blind rod bore
    return b.removeSplitter()


def PlaceStrut(shape, origin, u):
    s = shape.copy()
    s.rotate(V(0, 0, 0), V(0, -1, 0), Deg(math.atan2(u[1], u[0])))
    s.translate(V(origin[0], 0, origin[1]))
    return s


def StrutAt(phi, anchor=None, parts=("eye", "rod", "spring", "body")):
    """The strut at arm angle phi, in the cap frame."""
    A = AnchorPt if anchor is None else anchor
    T = Rot2(CrankPt0, phi)
    d = (A[0] - T[0], A[1] - T[1])
    L = math.hypot(*d)
    u = (d[0] / L, d[1] / L)
    out = []
    if "eye" in parts:
        out.append(PlaceStrut(StrutEye(), T, u))
    if "rod" in parts:
        out.append(PlaceStrut(CylX(P["EyeCT"] - P["RodPress"], P["EyeCT"] + RodOut, P["RodD"] / 2), T, u))
    if "spring" in parts:
        s0, s1 = P["EyeCT"], L - BodyCA
        sp = CylX(s0, s1, P["SpringOD"] / 2).cut(CylX(s0 - 1, s1 + 1, P["SpringOD"] / 2 - P["WireD"]))
        out.append(PlaceStrut(sp, T, u))
    if "body" in parts:
        b = StrutBody()
        b.translate(V(L, 0, 0))
        out.append(PlaceStrut(b, T, u))
    sh = out[0]
    for o in out[1:]:
        sh = sh.fuse(o)
    return sh


# ---------------------------------------------------------------- mechanics

ArmGravity = {}   # filled once by Checks: mass (g) and centre of mass (x, z) of arm, cup and stopper, closed


def GravityM(phi):
    """Moment of the arm's own weight about the pivot (counter-clockwise positive)."""
    if not ArmGravity:
        return 0.0
    c = Rot2(ArmGravity["cog"], phi)
    return -ArmGravity["m"] / 1000 * 9.81 * (c[0] - Px)


def SpringState(phi, anchor=None, k=None, shim=None):
    """Spring length, its force and its moment on the arm plus the arm's weight (counter-clockwise,
    opening, positive)."""
    a = AnchorPt if anchor is None else anchor
    k = SpringK if k is None else k
    shim = P["SeatShim"] if shim is None else shim
    t = Rot2(CrankPt0, phi)
    d = (t[0] - a[0], t[1] - a[1])              # the strut pushes the crank away from the anchor
    L = math.hypot(*d)
    s = L - P["EyeCT"] - BodyCA - shim
    F = k * (P["SpringLf"] - s) if s < P["SpringLf"] else 0.0
    M = Cross((t[0] - Px, t[1] - Pz), (F * d[0] / L, F * d[1] / L)) + GravityM(phi)
    return s, F, M


def FaceState(phi):
    """Face centre and the face normal (pointing out of the face, toward the tip when closed)."""
    return Rot2((0.0, 0.0), phi), (-math.sin(Rad(phi)), math.cos(Rad(phi)))


def ContactGap(phi, tip):
    """Smallest signed distance of the tip end ring above the face plane (in the x-z section)."""
    c, n = FaceState(phi)
    return min(n[0] * (tip[0] + s * P["TipR"] - c[0]) + n[1] * (tip[1] - c[1]) for s in (-1, 1))


def SolveContact(tip, anchor=None, k=None, shim=None):
    """Arm angle where the face meets the tip end; the tip force with the load at the touching edge
    and at the ring's centre (the two ends of its range as the silicone takes up the tilt); the
    offset of the tip centre from the face centre. None if the arm reaches its over-travel stop first."""
    lo, hi = -P["OverTravel"], 25.0
    if ContactGap(lo, tip) > 0:
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if ContactGap(mid, tip) > 0:
            hi = mid
        else:
            lo = mid
    phi = 0.5 * (lo + hi)
    c, n = FaceState(phi)
    _, _, Ms = SpringState(phi, anchor, k, shim)
    Fs = []
    for q in ((tip[0] + (1 if n[0] < 0 else -1) * P["TipR"], tip[1]), tip):
        Fs.append(Ms / Cross((q[0] - Px, q[1] - Pz), n))
    off = math.hypot((tip[0] - c[0]) * n[1] - (tip[1] - c[1]) * n[0], P["TipXYTol"])
    return phi, min(Fs), max(Fs), off


# ---------------------------------------------------------------- checks

def MinDist(a, b):
    return a.distToShape(b)[0]


def MaxRadius(shape):
    pts, _ = shape.tessellate(0.1)
    return max(math.hypot(p.x, p.y) for p in pts)


def Overhang(shape):
    """Area of flat faces off the bed that face downward at more than 45 deg from vertical."""
    a = 0.0
    for f in shape.Faces:
        if f.Surface.__class__.__name__ != "Plane" or f.BoundBox.ZMin < 1e-3:
            continue
        u0, u1, v0, v1 = f.ParameterRange
        n = f.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
        if n.z < -0.7071:
            a += f.Area
    return a


def BedArea(shape):
    """Area of the faces lying on z = 0 (the build plate)."""
    return sum(f.Area for f in shape.Faces if f.BoundBox.ZMax < 1e-3)


def Checks(parts):
    out, bad = [], 0

    def Flag(ok):
        nonlocal bad
        bad += 0 if ok else 1
        return "" if ok else "  FAIL"

    arm, cup, yoke = parts["CapArm"], parts["StopperCup"], parts["CapYoke"]
    stopper, syr, servo = Stopper(), Syringe(), Servo()
    post, brk = Post(), Brackets()
    pieces = [(arm, 1.27e-3), (cup, 1.27e-3), (stopper, 1.15e-3)]      # PETG; silicone about 1.15 g/cm3
    m_ = sum(sh.Volume * rho for sh, rho in pieces)
    ArmGravity.update(m=m_, cog=(sum(sh.Solids[0].CenterOfMass.x * sh.Volume * rho for sh, rho in pieces) / m_,
                                 sum(sh.Solids[0].CenterOfMass.z * sh.Volume * rho for sh, rho in pieces) / m_))
    out.append("Tip cap (issue 243): pivot (%.1f, %.1f) from the tip end, arm %.1f to the face, swing %.0f deg" % (Px, Pz, ArmR, P["Swing"]))
    out.append("All syringe and machine dimensions are photo estimates; servo and spring are typical or required values.")
    out.append("")
    out.append("Stopper and cup (size 00 silicone %.0f / %.0f x %.0f, big end on the tip)" % (P["StopBigD"], P["StopSmallD"], P["StopL"]))
    mouth = StopDia(P["Proud"])
    sink = P["Interf"] / ((P["StopBigD"] - P["StopSmallD"]) / P["StopL"])
    out.append("  bore: 1:%.1f taper on diameter, %.2f at the mouth to %.2f at the small end (%.1f under the stopper)," % (
        P["StopL"] / (P["StopBigD"] - P["StopSmallD"]), mouth - P["Interf"], P["StopSmallD"] - P["Interf"], P["Interf"]))
    out.append("    so a pushed-in stopper stands about %.1f proud (%.0f nominal + %.1f from the press fit); %.1f clear below its" % (
        P["Proud"] + sink, P["Proud"], sink, P["FloorClear"]))
    out.append("    small end, so the taper, not the floor, locates it; vent hole %.0f in the floor" % P["VentD"])
    cover = P["StopBigD"] / 2 - P["TipR"]
    out.append("  face %.0f over a tip end of at most %.0f: %.1f of overlap all round when centred" % (P["StopBigD"], 2 * P["TipR"], cover))
    out.append("  the seal force pushes the stopper deeper into its taper; uncapping pulls the tip away and")
    out.append("    puts no load on the fit")
    out.append("")
    out.append("Seal force on the tip (strut spring %.1f x %.0f x %.0f, %d laps, seat shim %.1f; the arm's own %.0f g included)" % (
        P["WireD"], P["SpringOD"], P["SpringLf"], P["SpringLaps"], P["SeatShim"], ArmGravity["m"]))
    rows = []
    fLo, fHi, worstOff, worstPhi = 9e9, -9e9, 0.0, 0.0
    for dz in (-P["TipZTol"], 0.0, P["TipZTol"]):
        for dx in (-P["TipXTol"], 0.0, P["TipXTol"]):
            r = SolveContact((dx, dz))
            rows.append(r)
            if r is None:
                continue
            phi, f0, f1, off = r
            fLo, fHi = min(fLo, f0), max(fHi, f1)
            worstOff = max(worstOff, off)
            worstPhi = max(worstPhi, abs(phi))
    nom = SolveContact((0.0, 0.0))
    ok = nom is not None and 1.6 <= nom[1] and nom[2] <= 3.0
    out.append("  nominal: closes at phi %.2f deg with %.2f to %.2f N on the tip (load at the ring edge or centre)%s" % (
        nom[0], nom[1], nom[2], Flag(ok)))
    ok = all(r is not None for r in rows) and fLo >= 1.3 and fHi <= 4.0
    out.append("  tip end +-%.1f in z and +-%.1f in x: %.2f to %.2f N, closing within +-%.1f deg%s" % (
        P["TipZTol"], P["TipXTol"], fLo, fHi, worstPhi, Flag(ok)))
    ok = worstOff <= cover - P["EdgeR"]
    out.append("  worst offset of the tip centre from the face centre (with +-%.1f in y): %.2f; the ring stays on" % (
        P["TipXYTol"], worstOff))
    out.append("    the face up to %.1f, less %.1f for the stopper's moulded edge%s" % (cover, P["EdgeR"], Flag(ok)))
    # tilt: the face meets the tip at phi_c, not square; the ring then touches at one edge first
    wedge = 2 * P["TipR"] * math.tan(Rad(worstPhi))
    perMm = SolveContact((0.0, 1.0))[0]
    a = math.pi * P["TipR"] ** 2
    indent = nom[2] / a / P["SiliconeE"] * 2 * P["TipR"] * math.pi / 4   # flat punch on a half-space, rough
    out.append("  face tilt: %.1f deg per mm of tip height error, so +-%.1f deg over the tolerance: a %.2f wedge across the" % (
        abs(perMm), worstPhi, wedge))
    out.append("    ring, against about %.2f of indentation at 2 N (E %.1f MPa, flat punch, rough). RISK, not checked:" % (
        indent, P["SiliconeE"]))
    out.append("    the seal needs the tip height to repeat within about +-%.1f from one syringe to the next, or a" % (
        math.degrees(math.atan(indent / (2 * P["TipR"]))) / abs(perMm)))
    out.append("    self-aligning cup; bench T4 decides")
    kAlt = P["GMod"] * P["WireD"] ** 4 / (8 * SpringDm ** 3 * P["AltSpring"]["Na"])
    shims = (0.0, 0.5, 1.0, 1.5)
    out.append("  seal by seat shim (ring centre to edge), as estimated (k %.3f) / if 12 coils are active (k %.3f):" % (SpringK, kAlt))
    out.append("    " + "; ".join("%.1f: %.2f..%.2f / %.2f..%.2f N" % (
        t, SolveContact((0.0, 0.0), shim=t)[1], SolveContact((0.0, 0.0), shim=t)[2],
        SolveContact((0.0, 0.0), k=kAlt, shim=t)[1], SolveContact((0.0, 0.0), k=kAlt, shim=t)[2]) for t in shims))
    out.append("")
    out.append("Coilover strut (the spring rides on a %.0f mm steel rod that slides in the body's blind bore)" % P["RodD"])
    phis = [P["Swing"] * k / 340 for k in range(341)]
    states = [SpringState(f) for f in phis]
    Ls = [s_[0] for s_ in states]
    kdc = min(range(len(phis)), key=lambda k: Ls[k])
    phiDC = phis[kdc]
    out.append("  spring rate %.3f N/mm from G %.0f GPa and %d active coils: an ESTIMATE, measure it (a 500 g mass should" % (
        SpringK, P["GMod"] / 1000, SpringNa))
    out.append("    compress it about %.1f mm); solid length %.1f" % (0.5 * 9.81 / SpringK, SpringSolid))
    out.append("  spring length %.1f closed, %.1f at dead centre (phi %.1f), %.1f open; force %.1f / %.1f / %.1f N" % (
        Ls[0], Ls[kdc], phiDC, Ls[-1], states[0][1], states[kdc][1], states[-1][1]))
    allF = phis + [-P["OverTravel"]]
    sMin = min(SpringState(f)[0] for f in allF)
    sMax = max(SpringState(f)[0] for f in allF)
    ok = sMin >= SpringSolid + P["SolidMargin"] and sMin >= P["AltSpring"]["Solid"] + 0.5 and sMax <= P["SpringLf"] - 0.5
    out.append("  shortest %.1f: %.1f off solid as estimated (%.1f), %.1f if 12 coils are active with unground ends (%.1f);" % (
        sMin, sMin - SpringSolid, SpringSolid, sMin - P["AltSpring"]["Solid"], P["AltSpring"]["Solid"]))
    out.append("    longest %.1f against %.1f free: always preloaded%s" % (sMax, P["SpringLf"], Flag(ok)))
    Cs = SpringDm / P["WireD"]
    Kw = (4 * Cs - 1) / (4 * Cs - 4) + 0.615 / Cs
    Ks = 1 + 0.5 / Cs
    Fmax = SpringK * (P["SpringLf"] - sMin)
    tau = 8 * Fmax * SpringDm * Kw / (math.pi * P["WireD"] ** 3)
    ok = tau <= P["TauAllow"]
    out.append("  shear at the shortest: %.0f MPa static (Ks %.2f), %.0f with the Wahl factor (%.2f, %.1f N) against %.0f" % (
        tau * Ks / Kw, Ks, tau, Kw, Fmax, P["TauAllow"]))
    out.append("    assumed; every cap cycle loads it, so it has a finite life: a wear part, swap it if it loses over 0.5 of")
    out.append("    free length%s" % Flag(ok))
    insMin, insMax, bore = RodOut - sMax, RodOut - sMin, BodyCA - P["PinClr"]
    ok = insMin >= P["RodEngage"] - P["RodTol"] - 1e-6 and insMax <= bore - P["BoreSpare"] + 1e-6
    out.append("  rod %.0f x %.1f +0/-%.1f (%.1f pressed into the eye; cut to length) runs %.1f to %.1f deep in the body's" % (
        P["RodD"], P["RodPress"] + RodOut, P["RodTol"], P["RodPress"], insMin, insMax))
    out.append("    %.1f bore: %.1f spare at the bottom%s" % (bore, bore - insMax, Flag(ok)))
    webE = P["EyeCT"] - P["RodPress"] - P["PivotHoleD"] / 2
    webB = P["PinClr"] - P["PivotHoleD"] / 2
    ok = webE >= 1.9 and webB >= 1.9
    out.append("  webs between the rod bores and the pivot holes: eye %.2f, body %.2f%s" % (webE, webB, Flag(ok)))
    mOpen, mClosed, mOver = states[-1][2], states[0][2], SpringState(-P["OverTravel"])[2]
    gM = abs(GravityM(P["Swing"]))
    mOpenAlt = SpringState(P["Swing"], k=kAlt)[2]
    ok = mOpen > 2 * gM and mOpenAlt > 1.5 * gM and mClosed < -30.0 and mOver < -30.0
    out.append("  net of the arm's weight (%.1f N mm open): holds open with %.1f N mm (%.1f if 12 coils are active), closed with" % (
        gM, mOpen, mOpenAlt))
    out.append("    %.0f, and at the over-travel stop (no syringe) with %.0f%s" % (-mClosed, -mOver, Flag(ok)))
    peelM = P["PeelN"] * ArmR
    need = max(abs(s[2]) + (peelM if f < 10 else 0.0) for f, s in zip(phis, states))
    springOnly = max(abs(s[2]) for s in states)
    margin = P["StallNm"] * 1000 / need
    ok = margin >= 1.3
    out.append("Servo (MG90S class, %.2f N m stall from seller listings)" % P["StallNm"])
    out.append("  largest spring moment over the swing %.0f N mm; with %.1f N of peel at the face near closed %.0f N mm;" % (
        springOnly, P["PeelN"], need))
    out.append("    stall margin %.1f%s" % (margin, Flag(ok)))
    lm = P["LostMotion"] / 2
    ok = phiDC + lm + 5 <= P["Swing"] and worstPhi + 3 <= lm and P["OverTravel"] + 1 <= lm and P["Swing"] <= P["ServoTravel"] - 5
    out.append("  lost motion +-%.0f deg: opening, the pin drags the arm past dead centre at a horn angle of %.0f; closing" % (
        lm, phiDC + lm))
    out.append("    at %.0f; at rest the pin sits within %.1f deg of mid-slot (tip tolerance), %.0f deg with no syringe;" % (
        phiDC - lm, worstPhi, P["OverTravel"]))
    out.append("    the servo turns %.0f of its nominal %.0f deg%s" % (P["Swing"], P["ServoTravel"], Flag(ok)))
    needT = P["Swing"] - (lm - worstPhi - 1.0)
    out.append("  the servo must really travel at least %.0f deg between S-closed and S-open, or at rest the pin reaches" % needT)
    out.append("    a slot end and the servo holds the arm against the spring; MEASURE it on the bench")
    s0 = (180 - P["Swing"]) / 2
    out.append("  M280 P2: closed S%.0f, open S%.0f; which way S grows turns the arm, and the real travel, are to be" % (s0, s0 + P["Swing"]))
    out.append("    bench-checked: with less travel the spring still snaps the arm home, but the pin then rests up to")
    out.append("    the shortfall off mid-slot")
    out.append("")
    out.append("Clearances over the swing (sampled every 2.5 deg from -%.0f to %.0f)" % (P["OverTravel"], P["Swing"]))
    armHW = ArmHardware()
    moving = arm.fuse(cup).fuse(stopper).fuse(armHW)
    fixedHW = yoke.fuse(servo).fuse(AnchorHardware(AnchorPt)).fuse(post).fuse(brk)
    worst = {"yoke": 9e9, "syringe": 9e9, "spring": 9e9, "horn": 9e9}
    # the body bears on the boss face by design (0.3 of axial play on its sleeve); check the rest of the yoke
    yokeNoBoss = yoke.cut(CylY(AnchorPt, P["AnchorBossR"] + 2.5, P["AnchorBossY0"] - 0.5, P["PlateY"][0] + 0.5))
    contactOpen = contactClosed = None
    n = int((P["Swing"] + P["OverTravel"]) / 2.5)
    for k in range(n + 1):
        f = -P["OverTravel"] + (P["Swing"] + P["OverTravel"]) * k / n
        m = RotY(moving, f)
        dy = MinDist(m, fixedHW)
        if k == 0:
            contactClosed = dy
        elif k == n:
            contactOpen = dy
        elif -P["OverTravel"] + 3.0 <= f <= P["Swing"] - 3.0:   # the arm closes on a stop by design near each end
            worst["yoke"] = min(worst["yoke"], dy)
        if f >= 3.0:
            worst["syringe"] = min(worst["syringe"], MinDist(m, syr))
        sp = StrutAt(f)
        others = RotY(cup.fuse(stopper).fuse(arm), f).fuse(servo).fuse(syr)
        worst["spring"] = min(worst["spring"], MinDist(sp, others))
        worst["strutYoke"] = min(worst.get("strutYoke", 9e9), MinDist(sp, yokeNoBoss))
        # pin offset d from mid-slot: before dead centre the pin leads (it pushes the arm there opening; the
        # spring snaps the arm ahead of it closing), past dead centre it trails; at a rest pose it sits where
        # the servo stopped (servo angle 0 closed, Swing open), so near closed d >= -phi and near open
        # d <= Swing - phi
        if f < phiDC:
            lo = max(-lm, -f) if f < 5.0 else 0.0
            ds = sorted(set((lo, max(lo, 0.0), lm)))
        else:
            hi = min(lm, P["Swing"] - f) if f > P["Swing"] - 5.0 else 0.0
            ds = sorted(set((-lm, min(hi, 0.0), hi)))
        for d in ds:
            hs = HornStack(EarAng0 + f + d)
            worst["horn"] = min(worst["horn"], MinDist(hs, yoke.fuse(sp).fuse(syr).fuse(RotY(armHW, f))))
    ok = worst["yoke"] >= 0.5
    out.append("  arm, cup, stopper and crank screw to the yoke, servo, anchor, post and brackets, more than 3 deg from a stop: %.2f%s" % (
        worst["yoke"], Flag(ok)))
    so = MinDist(RotY(moving, P["Swing"]), yoke)
    sc = MinDist(RotY(moving, -P["OverTravel"]), yoke)
    ok = so <= 0.05 and sc <= 0.05
    out.append("  the arm meets the open stop at %.0f deg (gap %.2f) and the closed stop at -%.0f deg (gap %.2f)%s" % (
        P["Swing"], so, P["OverTravel"], sc, Flag(ok)))
    ok = worst["syringe"] >= 1.0
    out.append("  arm, cup and stopper to the syringe once 3 deg open: %.2f%s" % (worst["syringe"], Flag(ok)))
    ok = worst["spring"] >= 0.5
    out.append("  strut (eye, rod, spring, body) to the arm, cup, stopper, servo and syringe: %.2f%s" % (worst["spring"], Flag(ok)))
    ok = worst["strutYoke"] >= 0.5
    out.append("  strut to the yoke away from the anchor boss: %.2f (at the boss the body has 0.3 of axial play by design)%s" % (
        worst["strutYoke"], Flag(ok)))
    out.append("  the spring has 0.8 of radial play on the rod, so it may brush the arm's face near open (rub only)")
    ok = worst["horn"] >= 0.5
    out.append("  horn stack (pin where the motion puts it in its slot) to the yoke, strut, crank screw, syringe: %.2f%s" % (
        worst["horn"], Flag(ok)))
    for nm, shp in (("yoke", yoke), ("post and brackets", post.fuse(brk)), ("servo", servo)):
        d = MinDist(shp, syr)
        ok = d >= 1.5
        out.append("  %s to the syringe: %.2f%s" % (nm, d, Flag(ok)))
    out.append("")
    out.append("Envelope (relative to the tip end)")
    lowest = min(RotY(moving, P["Swing"] * k / 68).BoundBox.ZMin for k in range(69))
    rimR = P["BowlRimR"] - P["BowlRimUnc"]
    lowOut = 9e9
    for k in range(69):
        pts, _ = RotY(moving, P["Swing"] * k / 68).tessellate(0.3)
        for q in pts:
            if math.hypot(q.x, q.y) >= rimR:
                lowOut = min(lowOut, q.z)
    uncap = max(-lowest + 5.0, P["RimAboveChuck"] - lowOut + 5.0 if lowOut < 9e8 else 0.0)
    ob = RotY(moving, P["Swing"])
    rmax = MaxRadius(ob)
    obb = ob.BoundBox
    out.append("  the swing reaches %.1f below the tip end, and beyond the rim's smallest photo radius %.1f it reaches" % (
        -lowest, rimR))
    out.append("    %.1f below the tip end; so uncap and recap with the tip at least %.0f above the chuck top (rim %.0f above it," % (
        -lowOut if lowOut < 9e8 else float("nan"), uncap, P["RimAboveChuck"]))
    out.append("    photo, and 5 to spare); the uncap height is a B value, set on the bench from the measured rim")
    out.append("  parked open: cap at x %.0f..%.0f, z %.0f..%.0f, at most %.1f from the syringe axis (tessellated)" % (
        obb.XMin, obb.XMax, obb.ZMin, obb.ZMax, rmax))
    rimZ = P["RimAboveChuck"] - P["DispenseAboveChuck"]
    ok = rmax <= P["BowlRimR"] - P["BowlRimUnc"] - 2.0
    out.append("  during a dose (tip %.0f above the chuck, rim about %.0f above the tip, photo) the parked cap stays inside" % (
        P["DispenseAboveChuck"], rimZ))
    out.append("    the rim's smallest photo radius %.1f%s" % (P["BowlRimR"] - P["BowlRimUnc"], Flag(ok)))
    ok = obb.ZMin > -P["DispenseAboveChuck"] + 2
    out.append("  parked open, its lowest point is %.1f above the chuck during a dose%s" % (obb.ZMin + P["DispenseAboveChuck"], Flag(ok)))
    out.append("  open, the stopper face points down (%.0f deg), so a drop from it falls into the bowl beside the chuck" % (
        90 + P["Swing"] - 360 if 90 + P["Swing"] > 180 else 90 + P["Swing"]))
    onSyringe = {"yoke": yoke, "post": post, "servo": servo, "anchor screw": AnchorHardware(AnchorPt),
                 "horn": HornStack(EarAng0 + P["Swing"]), "arm, cup and stopper": ob, "strut": StrutAt(P["Swing"])}
    lowName, lowZ = min(((k_, v.BoundBox.ZMin) for k_, v in onSyringe.items()), key=lambda t: t[1])
    ok = lowZ >= -P["DispenseAboveChuck"] + P["ChuckClear"]
    out.append("  during a dose nothing on the syringe comes closer than %.1f to the chuck top (lowest: the %s)%s" % (
        lowZ + P["DispenseAboveChuck"], lowName, Flag(ok)))
    out.append("")
    # below the rim's height during a dose, everything must sit inside the rim's smallest radius
    rimTop = P["RimAboveChuck"] - P["DispenseAboveChuck"]
    rOut, who = 0.0, ""
    for k_, v in onSyringe.items():
        pts, _ = v.tessellate(0.3)
        for q in pts:
            if q.z < rimTop + P["ChuckClear"]:
                r_ = math.hypot(q.x, q.y)
                if r_ > rOut:
                    rOut, who = r_, k_
    ok = rOut <= rimR - 2.0
    pr = max(math.hypot(x, y) for x in P["PostX"] for y in P["PostY"])
    out.append("  during a dose, below the rim's height (+%.0f) nothing reaches past r %.1f (the %s), inside the rim's" % (
        P["ChuckClear"], rOut, who))
    out.append("    smallest photo radius %.1f; the post ends %.1f above the rim (photo) and reaches r %.1f%s" % (
        rimR, P["PostBottomZ"] - rimTop, pr, Flag(ok and P["PostBottomZ"] - rimTop >= P["ChuckClear"])))
    out.append("")
    out.append("Bracket (2020 post on two corner brackets under the +v shelf rail; the yoke bolted to the post's slot)")
    L = P["RailBottomZ"] - P["PostBottomZ"]
    sx = 0.5 * sum(P["PostX"])
    zb = 0.5 * sum(P["YokeBoltZ"])
    F = 2.0
    My, Mx = F * sx, F * 0.5 * sum(P["PostY"])
    th = math.hypot(Mx, My) * L / (P["AluE"] * P["PostI"])
    dPost = th * math.hypot(sx, zb)
    # the compliant part is the PETG yoke: its bridge carries the strut's closed force plus the seal from the cheek
    # (the pivot) to the plate, as a cantilever across y
    Fb = SpringState(0.0)[1] + 2.0
    Lb = P["PlateY"][0] - P["CheekY"][1]
    hb = P["BridgeZ"][1] - P["BridgeZ"][0]
    bb = P["ColumnX"][1] - P["ColumnX"][0]
    dB = Fb * Lb ** 3 / (3 * P["PetgE"] * bb * hb ** 3 / 12)
    sB = Fb * Lb * (hb / 2) / (bb * hb ** 3 / 12)
    ok = dB <= 0.05 and dPost <= 0.01
    out.append("  under the closed load (%.1f N from the strut and the seal) the PETG bridge, %.0f deep over %.0f, deflects about" % (
        Fb, hb, Lb))
    out.append("    %.3f mm at %.1f MPa (E %.0f MPa, long-term, assumed); the aluminium post adds %.4f; the bolted joints, with" % (
        dB, sB, P["PetgE"], dPost))
    out.append("    M5 preload far above these loads, are taken as rigid%s" % Flag(ok))
    up = (P["RailBottomZ"] - 20.0) - LandZ[1]
    down = LandZ[0] - P["PostBottomZ"]
    ok = down >= 3.0 and up >= 3.0
    out.append("  height: the post's bottom must stay above the rim during a dose, a fixed height above the tip end, so the")
    out.append("    post's cut length is the set-up: measure the rail's bottom face to the tip end (photo %.0f +-%.0f), cut the" % (
        P["RailBottomZ"], P["TipZUnc"]))
    out.append("    post square to that less %.0f; then the yoke's T-nuts slide %.0f down and %.0f up in the slot for the fine" % (
        P["PostBottomZ"], down, up))
    out.append("    setting, against about +-1.5 of measuring and cutting error%s" % Flag(ok))
    out.append("  square: the land's side lips hug the post's outer faces (%.2f clearance a side), so the yoke cannot turn on" % P["LipGap"])
    out.append("    the post; along the shelf: the corner brackets' T-nuts slide in the rail's bottom slot")
    out.append("  across (y): the land is %.1f; %.1f of 0.5 printed shims sits between it and the post nominally, so y moves" % (
        P["LandT"], P["ShimNom"]))
    out.append("    -%.1f (fewer) or + (more); set it with the arm closed on a fitted syringe, face centred on the tip" % P["ShimNom"])
    grip = P["PlateY"][1] - P["PlateY"][0] + P["LandT"] + P["ShimNom"] + 1.0
    out.append("  M5 bolt length: washer + plate + land + shims (%.0f nominally) + 5, so M5 x %.0f; its tip stays above the" % (
        grip, grip + 5))
    out.append("    slot floor")
    out.append("Printing (each STEP in its print orientation): bed contact, and flat faces facing down off the bed")
    for nm in ("CapArm", "StopperCup", "CapYoke", "StrutEye", "StrutBody", "CapShim"):
        s = PrintPose(nm, parts[nm])
        ba, oh = BedArea(s), Overhang(s)
        down = [f.Area for f in s.Faces if f.Surface.__class__.__name__ == "Plane" and f.BoundBox.ZMin >= 1e-3
                and f.normalAt(*f.ParameterRange[0::2]).z < -0.99]
        ok = ba >= max([0.0] + down) and oh <= 600.0   # the part stands on its largest downward face
        out.append("  %-10s bed %5.0f mm2, overhang %4.0f mm2 (steeper than 45 deg)%s" % (nm, ba, oh, Flag(ok)))
    out.append("  CapArm: +y face down, hub up. StopperCup: mouth up. CapYoke: upside down on its bridge and plate top,")
    out.append("    with a brim. StrutEye and StrutBody: standing on their spring seats, with a brim (small beds). CapShim:")
    out.append("    flat, print four. PETG.")
    out.append("")
    out.append("Parts and hardware")
    out.append("  stopper: size 00 solid silicone, the PUL FACTORY pack (any size 00; re-run with its sizes)")
    out.append("  servo: MG90S class micro servo with its single-arm horn, on a third servo output (NUM_SERVOS 3);")
    out.append("    it goes in from +y through the plate's window, ears on the plate's +y face, 2 x M2 self-tapping")
    out.append("  strut: spring %.1f x %.0f x %.0f (%d laps) from the Pianrui K-P-051-300 kit; a %.0f mm steel rod cut to %.1f" % (
        P["WireD"], P["SpringOD"], P["SpringLf"], P["SpringLaps"], P["RodD"], P["RodPress"] + RodOut))
    out.append("    +0/-%.1f, pressed fully into the printed StrutEye; the printed StrutBody guides it. Drill the body's rod" % P["RodTol"])
    out.append("    bore to %.1f and both pivot holes to %.1f after printing (they print undersize)" % (P["RodD"] + 0.2, P["PivotHoleD"]))
    out.append("  pivot: dowel pin %.0f x 16, a slip fit through the cheek into the arm's hub, held by an M3 x 6 grub screw" % P["DowelD"])
    out.append("    from below")
    out.append("  horn pin: M2 x 20 through the horn, a printed spacer tube %.0f OD, a %.0f x %.1f metal sleeve (it rides in" % (
        P["TubeD"], P["SleeveD"], P["ArmT"] + 0.3))
    out.append("    the slot; the stack clamps on it, not on the arm), a %.0f mm washer and a nut with thread locker; the" % P["WasherD"])
    out.append("    screw's end runs in a relief groove in the cheek face")
    out.append("  crank: M3 x 12 button head, a 4 x 6.3 brass sleeve (3.3 ID) through the eye, three M3 washers under it,")
    out.append("    into an M3 heat-set insert in the arm; anchor: M3 x 20 from the plate's +y face through the boss and a 4 x 6.3 sleeve in")
    out.append("    the body, an M3 washer and a thin nut (thread locker). The screws clamp the sleeves, never the strut")
    out.append("  cup to arm: 2 x M3 x 18 and nuts")
    out.append("  bracket: 2020 aluminium extrusion cut square to %.0f nominally (see height); 2 x 2020 corner brackets with" % (
        P["RailBottomZ"] - P["PostBottomZ"]))
    out.append("    4 x M5 x 10 and drop-in T-nuts (two in the rail's bottom slot, one in each of the post's x slots); yoke")
    out.append("    to post: 2 x M5 x 12 with washers into spring-loaded drop-in T-nuts in the post's -y slot; CapShim x 4")
    out.append("  assembly: (0) post and corner brackets on the rail; yoke on the post (bolts reachable before the arm is")
    out.append("    in, or with it closed); (1) servo into the plate from +y, ears screwed on the +y face; (2) the strut's eye (rod")
    out.append("    pressed in) on the crank screw on the arm; (3) arm in at the closed pose, hub on the cheek's dowel hole,")
    out.append("    sleeve in the slot, spacer tube on it; (4) M2 pin screw through the horn, horn onto the spline and")
    out.append("    the screw through tube and sleeve; centre screw through the cheek hole and the hub bore; (5) washer")
    out.append("    and nut on the pin screw, thread locker; (6) dowel in, grub screw; (7) arm to the open pose (the spring is")
    out.append("    softest there): spring and shim over the rod, body over rod and spring with its sleeve in, line the sleeve")
    out.append("    up with the boss, drive the M3 x 20 from the plate's +y face, washer and nut from -y; (8) stopper cup on")
    out.append("    the arm, stopper in. Measure the spring first (free length, coils, end type, rate) and set the seat shim")
    out.append("")
    out.append("Not known (bench, before printing)")
    out.append("  the stopper sizes as delivered; the tip end OD and the shape of the catheter tip and cone below the")
    out.append("  shoulder: the swing passes within about 2 of the modelled cone, which has no allowance, so MEASURE it")
    out.append("  before printing; the tip end below the rail; the barrel's place in the rail gap; what else is")
    out.append("  under the rail at x %.0f..%.0f (and whether the barrel clamp wraps under it there); the servo's sizes, its" % (
        P["PostX"][0] - 20, P["PostX"][1] + 20))
    out.append("  real travel and its horn's holes; the spring's rate;")
    out.append("  the bowl rim's radius and height and the chuck against the dispense pose")
    return out, bad


# ---------------------------------------------------------------- assembly

# Paul Tol's bright scheme, plus its pale grey for the reference parts
TolColor = dict(blue="#4477AA", cyan="#66CCEE", green="#228833", yellow="#CCBB44", red="#EE6677", purple="#AA3377",
                grey="#BBBBBB", pale="#DDDDDD")


def Rail2020X(x0, x1, y0, z0):
    """A 2020 profile along x (the shelf rail), simplified like Post(): four 6.2 x 6 slots and the centre bore."""
    y1, z1 = y0 + 20.0, z0 + 20.0
    r = Box(x0, x1, y0, y1, z0, z1)
    sy, sz = y0 + 10.0, z0 + 10.0
    for by0, by1, bz0, bz1 in ((sy - 3.1, sy + 3.1, z0 - 1, z0 + 6), (sy - 3.1, sy + 3.1, z1 - 6, z1 + 1),
                               (y0 - 1, y0 + 6, sz - 3.1, sz + 3.1), (y1 - 6, y1 + 1, sz - 3.1, sz + 3.1)):
        r = r.cut(Box(x0 - 1, x1 + 1, by0, by1, bz0, bz1))
    return r.cut(Part.makeCylinder(2.1, x1 - x0 + 2, V(x0 - 1, sy, sz), V(1, 0, 0)))


def Dowel():
    """4 x 16 dowel pin, from the cheek's outer face into the arm's hub."""
    y0 = P["CheekY"][0]
    return CylY((Px, Pz), P["DowelD"] / 2, y0, y0 + 16.0)


def GrubScrew():
    """M3 x 6 grub screw from below into the dowel hole (modelled at the tap drill size)."""
    yc = 0.5 * sum(P["CheekY"])
    return Part.makeCylinder(1.2, 6.0, V(Px, yc, Pz - P["DowelD"] / 2 - 6.0), V(0, 0, 1))


def CrankInsert():
    """M3 heat-set insert in the arm for the crank screw (simplified to a tube through the arm plate)."""
    return CylY(CrankPt0, P["InsertD"] / 2, -P["ArmT"] / 2, P["ArmT"] / 2).cut(
        CylY(CrankPt0, 1.5, -P["ArmT"] / 2 - 1, P["ArmT"] / 2 + 1))


def CupScrews():
    """2 x M3 x 18 through the cup's lug and the arm's tang, button heads on +y, nuts on -y."""
    h = P["LugHalfY"]
    out = None
    for c in LugScrews:
        s = CylY(c, 1.5, h - 18.0, h).fuse(CylY(c, 2.85, h, h + 1.65)).fuse(CylY(c, 3.2, -h - 2.4, -h))
        out = s if out is None else out.fuse(s)
    return out


def YokeBolts():
    """2 x M5 x 12 socket head with washers, from the plate's -y face into the post's -y slot."""
    sx = 0.5 * sum(P["PostX"])
    yb = P["PlateY"][0]
    out = None
    for z in P["YokeBoltZ"]:
        s = CylY((sx, z), 2.5, yb - 1.0, yb - 1.0 + 12.0).fuse(CylY((sx, z), 5.0, yb - 1.0, yb)).fuse(
            CylY((sx, z), 4.25, yb - 6.0, yb - 1.0))
        out = s if out is None else out.fuse(s)
    return out


def YokeTNuts():
    """2 x M5 drop-in T-nuts in the post's -y slot (simplified to a block with a clearance hole)."""
    sx = 0.5 * sum(P["PostX"])
    y0 = P["PostY"][0]
    out = None
    for z in P["YokeBoltZ"]:
        n = Box(sx - 3.0, sx + 3.0, y0 + 1.8, y0 + 5.8, z - 5.0, z + 5.0).cut(CylY((sx, z), 2.55, y0, y0 + 7.0))
        out = n if out is None else out.fuse(n)
    return out


def BowlRef():
    """The spin coater bowl at the dispense pose (photo estimates): wall and rim, plus the chuck's level."""
    rimZ = P["RimAboveChuck"] - P["DispenseAboveChuck"]
    chuckZ = -P["DispenseAboveChuck"]
    r = P["BowlRimR"]
    wall = Part.makeCylinder(r + 2.0, rimZ - chuckZ + 5.0, V(0, 0, chuckZ - 5.0)).cut(
        Part.makeCylinder(r, rimZ - chuckZ + 7.0, V(0, 0, chuckZ - 6.0)))
    return wall, Part.makeCylinder(r, 1.0, V(0, 0, chuckZ - 1.0))


def AssemblyParts(phi, parts, dispense):
    """Every solid of the cap in place at arm angle phi, as (group, name, shape, colour, transparency).
    dispense adds the bowl and the chuck's level at the dispense pose (only meaningful with the arm open)."""
    out = []

    def Add(group, name, shape, colour, transp=0):
        out.append((group, name, shape, TolColor[colour], transp))

    arm = "Arm (swings)"
    Add(arm, "CapArm", RotY(parts["CapArm"], phi), "blue")
    Add(arm, "StopperCup", RotY(parts["StopperCup"], phi), "cyan")
    Add(arm, "Stopper_size00", RotY(Stopper(), phi), "pale")
    Add(arm, "CupScrews_M3x18", RotY(CupScrews(), phi), "grey")
    Add(arm, "CrankScrew_M3", RotY(ArmHardware(), phi), "grey")
    Add(arm, "CrankInsert_M3", RotY(CrankInsert(), phi), "grey")
    Add(arm, "StrutEye", StrutAt(phi, parts=("eye",)), "yellow")
    Add(arm, "GuideRod_4mm", StrutAt(phi, parts=("rod",)), "grey")
    Add(arm, "Spring_0p7x7x25", StrutAt(phi, parts=("spring",)), "red")
    yoke = "Yoke"
    Add(yoke, "CapYoke", parts["CapYoke"], "green")
    Add(yoke, "StrutBody", StrutAt(phi, parts=("body",)), "yellow")
    Add(yoke, "AnchorScrew_M3", AnchorHardware(AnchorPt), "grey")
    Add(yoke, "Dowel_4x16", Dowel(), "grey")
    Add(yoke, "GrubScrew_M3x6", GrubScrew(), "grey")
    Add(yoke, "Servo_MG90S", Servo(), "purple")
    Add(yoke, "HornAndPin", HornStack(EarAng0 + phi), "grey")
    for k in range(int(round(P["ShimNom"] / 0.5))):
        s = parts["CapShim"].copy()
        s.translate(V(0, P["PlateY"][1] + P["LandT"] + 0.5 * k, 0))
        Add(yoke, "CapShim_%d" % (k + 1), s, "red")
    br = "Bracket"
    Add(br, "Post_2020", Post(), "grey")
    Add(br, "CornerBrackets_2020", Brackets(), "grey")
    Add(br, "YokeBolts_M5x12", YokeBolts(), "grey")
    Add(br, "TNuts_M5", YokeTNuts(), "grey")
    mach = "Machine (photo estimates)"
    Add(mach, "Syringe_150mL", Syringe(), "pale", 60)
    rx0, rx1 = P["PostX"][0] - 110.0, P["PostX"][1] + 80.0
    Add(mach, "ShelfRail_2020", Rail2020X(rx0, rx1, P["RailY"][0], P["RailBottomZ"]), "grey", 50)
    if dispense:
        wall, chuck = BowlRef()
        Add(mach, "Bowl", wall, "pale", 70)
        Add(mach, "ChuckLevel", chuck, "pale", 80)
    return out


# Pairs that overlap by design (a press or a thread, or a reference model that stands in for a fitted pair),
# each with its expected volume in mm3 from the fit; more than 10 % over it is a clash and fails
OverlapOK = {
    frozenset(("Stopper_size00", "StopperCup")): (45.4, "the stopper is a press fit in the cup's taper"),
    frozenset(("GuideRod_4mm", "StrutEye")): (2.8, "the rod is pressed into the eye"),
    frozenset(("AnchorScrew_M3", "CapYoke")): (17.9, "the anchor screw cuts its thread in the boss's 2.6 mm hole"),
    frozenset(("HornAndPin", "Servo_MG90S")): (53.9, "the horn's hub sits on the servo's spline"),
}


def Interferences(items):
    """Volume shared by every pair of solids in the assembly, with the pairs allowed above."""
    hits = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if not a[2].BoundBox.intersect(b[2].BoundBox):
                continue
            v = a[2].common(b[2]).Volume
            if v > 0.05:
                hits.append((a[1], b[1], v))
    return hits


def AssemblyChecks(asms):
    out, bad = ["", "Assembly: the printed parts, stopper, servo, horn, strut, pivot and fasteners, bracket and machine",
                 "  references in place. Not modelled: the corner brackets' M5 screws and T-nuts, the servo's M2 screws"], 0
    for label, items in asms:
        bad0 = bad
        for a, b, v in Interferences(items):
            ok = OverlapOK.get(frozenset((a, b)))
            if ok and v <= 1.1 * ok[0]:
                out.append("  %s: %s / %s share %.1f mm3 by design (%s)" % (label, a, b, v, ok[1]))
            else:
                bad += 1
                out.append("  %s: %s / %s share %.1f mm3  <-- FAIL" % (label, a, b, v))
        out.append("  %s: %d solids, no other two share volume" % (label, len(items)) if bad == bad0 else
                   "  %s: %d solids" % (label, len(items)))
    return out, bad


def BuildAssembly(doc, title, items, visible=True, suffix=""):
    """An App::Part tree of the items; labels get the suffix, since a document's labels are unique."""
    import FreeCAD as App
    root = doc.addObject("App::Part", title.replace(" ", "_"))
    root.Label = title
    groups, objs = {}, []
    for g, name, shp, colour, transp in items:
        if g not in groups:
            grp = doc.addObject("App::Part", (title + "_" + g).replace(" ", "_").replace("(", "").replace(")", ""))
            grp.Label = g + suffix
            root.addObject(grp)
            groups[g] = grp
        o = doc.addObject("Part::Feature", name)
        o.Label = name + suffix
        o.Shape = shp
        groups[g].addObject(o)
        objs.append(o)
        if App.GuiUp:
            o.ViewObject.ShapeColor = tuple(int(colour[k:k + 2], 16) / 255.0 for k in (1, 3, 5))
            o.ViewObject.Transparency = transp
    if App.GuiUp and not visible:
        root.ViewObject.Visibility = False
    return root, objs


def ExportAssembly(root, objs, path):
    import FreeCAD as App
    if App.GuiUp:
        import ImportGui
        ImportGui.export([root], path)         # the group tree, with the colours
    else:
        import Import
        Import.export(objs, path)              # without the GUI the tree is written twice over: go flat


# ---------------------------------------------------------------- drawing and output

def Draw(parts, checks, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tol = {"arm": "#4477AA", "cup": "#66CCEE", "stop": "#CCBB44", "yoke": "#BBBBBB", "syr": "#DDDDDD", "spring": "#228833",
           "note": "#EE6677", "servo": "#AA3377"}
    fig = plt.figure(figsize=(21, 16))
    gs = fig.add_gridspec(2, 3)
    ax1, ax2, ax3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])
    ax4, ax5 = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1:])

    def Sect(ax, shp, normal, off, a, b, color, alpha=0.6, lw=0.6):
        for f in shp.slice(V(*normal), off):
            pts = f.discretize(Distance=0.3)
            xs, ys = [getattr(q, a) for q in pts], [getattr(q, b) for q in pts]
            ax.fill(xs, ys, color=color, alpha=alpha, lw=0)
            ax.plot(xs, ys, color="#222222", lw=lw)

    arm, cup, yoke = parts["CapArm"], parts["StopperCup"], parts["CapYoke"]
    post = Post().fuse(Brackets())
    syr = Syringe()
    for ax, phi, title in ((ax1, 0.0, "Closed (phi 0): section y 0"), (ax2, P["Swing"], "Open (phi %.0f): section y 0" % P["Swing"])):
        Sect(ax, syr, (0, 1, 0), 0.0, "x", "z", tol["syr"], 1.0)
        Sect(ax, post, (0, 1, 0), 0.5 * sum(P["PostY"]), "x", "z", tol["yoke"], 0.25, 0.4)
        Sect(ax, yoke, (0, 1, 0), -10.0, "x", "z", tol["yoke"], 0.35, 0.4)
        Sect(ax, RotY(arm, phi), (0, 1, 0), 0.0, "x", "z", tol["arm"])
        Sect(ax, RotY(cup, phi), (0, 1, 0), 0.0, "x", "z", tol["cup"])
        Sect(ax, RotY(Stopper(), phi), (0, 1, 0), 0.0, "x", "z", tol["stop"])
        Sect(ax, StrutAt(phi), (0, 1, 0), P["StrutY"], "x", "z", tol["spring"], 0.45)
        fp = [Rot2((0.0, 0.0), P["Swing"] * k / 60) for k in range(61)]
        ax.plot([p[0] for p in fp], [p[1] for p in fp], ls="--", color=tol["note"], lw=0.8)
        ax.plot([Px], [Pz], "o", color="k", ms=4)
        ax.axvline(P["BowlRimR"] - P["BowlRimUnc"], color=tol["note"], ls=":", lw=0.8)
        ax.set_title(title + " (cheek at y -10 shaded)", fontsize=10)
        ax.set_xlim(-45, 100)
        ax.set_ylim(-50, 160)
    ax1.annotate("stopper face on the tip end", xy=(0, 0), xytext=(-43, 25), fontsize=8, arrowprops=dict(arrowstyle="->"))
    ax1.annotate("coilover strut (section y %.1f)" % P["StrutY"], xy=AnchorPt, xytext=(48, -25), fontsize=8, arrowprops=dict(arrowstyle="->"))
    ax2.annotate("face path", xy=Rot2((0, 0), 80), xytext=(55, -40), fontsize=8, arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax2.text(P["BowlRimR"] - P["BowlRimUnc"] - 1, 78, "smallest photo\nrim radius", fontsize=7, ha="right", color=tol["note"])
    phis = [P["Swing"] * k / 170 for k in range(171)]
    ax3.plot(phis, [SpringState(f)[2] for f in phis], color=tol["spring"], label="spring moment, N mm (+ opens)")
    ax3.plot(phis, [SpringState(f)[1] * 10 for f in phis], color=tol["arm"], ls="--", label="spring force x 10, N")
    ax3.axhline(0, color="k", lw=0.6)
    ax3.axhline(-P["StallNm"] * 1000, color=tol["note"], ls=":", label="servo stall (MG90S class)")
    ax3.axhline(P["StallNm"] * 1000, color=tol["note"], ls=":")
    ax3.set_xlabel("arm angle from closed, deg")
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.3)
    ax3.set_title("Strut over the swing", fontsize=10)
    for shp, col in ((yoke, tol["yoke"]), (arm, tol["arm"]), (Servo(), tol["servo"]), (HornStack(EarAng0), tol["note"]),
                     (ArmHardware(), tol["note"]), (syr, tol["syr"])):
        Sect(ax4, shp, (0, 0, 1), Pz + 0.3, "x", "y", col, 0.5)
    Sect(ax4, StrutAt(0.0), (0, 0, 1), Pz + 0.3, "x", "y", tol["spring"], 0.5)
    for shp, col in ((yoke, tol["yoke"]), (post, tol["yoke"])):
        Sect(ax4, shp, (0, 0, 1), 0.5 * sum(P["YokeBoltZ"]), "x", "y", col, 0.25, 0.3)
    ax4.set_title("Plan at the pivot (z %.0f), with the post, land and side lips at the bolts (z %.0f) faint" % (
        Pz, 0.5 * sum(P["YokeBoltZ"])), fontsize=10)
    ax4.set_xlim(-30, 75)
    ax4.set_ylim(-20, 48)
    for a in (ax1, ax2, ax4):
        a.set_aspect("equal")
        a.grid(alpha=0.25)
    ax5.axis("off")
    ax5.text(0, 1, "\n".join(checks), va="top", family="monospace", fontsize=6.0, transform=ax5.transAxes)
    fig.suptitle("Tip cap (issue 243): servo-driven bistable arm with a size 00 silicone stopper (big end on the tip). "
                 "Cap frame: tip end at 0, mm. Photo-estimated machine.", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=90)
    plt.close(fig)


def PrintPose(name, shp):
    s = shp.copy()
    if name == "CapArm":
        s.rotate(V(0, 0, 0), V(1, 0, 0), -90)          # +y face (y 3) down, the hub up
    elif name == "CapYoke":
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)          # upside down, the bridge top on the bed
    elif name == "CapShim":
        s.rotate(V(0, 0, 0), V(1, 0, 0), -90)          # flat
    elif name == "StrutEye":
        s.rotate(V(0, 0, 0), V(0, 1, 0), 90)           # spring seat down, the pivot end up
    elif name == "StrutBody":
        s.rotate(V(0, 0, 0), V(0, 1, 0), -90)          # spring seat down, the pivot end up
    b = s.optimalBoundingBox()
    s.translate(V(-b.XMin, -b.YMin, -b.ZMin))
    return s


def Main():
    parts = {"CapArm": Arm(), "StopperCup": Cup(), "CapYoke": Yoke(), "StrutEye": StrutEye(), "StrutBody": StrutBody(),
             "CapShim": Shim()}
    for k, s in parts.items():
        assert s.isValid() and len(s.Solids) == 1, "%s is not one valid solid (%d)" % (k, len(s.Solids))
    checks, bad = Checks(parts)
    closed = AssemblyParts(0.0, parts, dispense=False)
    opened = AssemblyParts(P["Swing"], parts, dispense=True)
    more, bad2 = AssemblyChecks((("closed", closed), ("open at the dispense pose", opened)))
    checks += more
    bad += bad2
    print("\n".join(checks))
    os.makedirs(OutDir, exist_ok=True)
    open(os.path.join(OutDir, Stem + "_Checks.txt"), "w", encoding="ascii", newline="\n").write(
        "\n".join(checks) + "\n\n%d check(s) failed\n" % bad)
    Draw(parts, checks, os.path.join(OutDir, Stem + "_Sketch.png"))
    for name, shp in parts.items():
        PrintPose(name, shp).exportStep(os.path.join(OutDir, "%s-%s.step" % (Stem, name)))
    doc = FreeCAD.newDocument("TipCap")
    rc, oc = BuildAssembly(doc, "Tip cap closed", closed)
    ro, oo = BuildAssembly(doc, "Tip cap open at the dispense pose", opened, visible=False, suffix="_open")
    doc.recompute()
    doc.saveAs(os.path.join(OutDir, Stem + ".FCStd"))
    ExportAssembly(rc, oc, os.path.join(OutDir, Stem + "_Assembly.step"))
    ExportAssembly(ro, oo, os.path.join(OutDir, Stem + "_AssemblyOpen.step"))
    if not FreeCAD.GuiUp:
        FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed; wrote %s" % (bad, OutDir))


Main()
