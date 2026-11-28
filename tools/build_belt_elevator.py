# Builds the belt drive of both storage towers (issue 267) and checks it in 3D.
#   Library tower (mask columns A and B, new U axis) and cartridge tower (C fresh, D spent, I axis) are built
#   the same way: a 17HS08 pancake stepper turns a home-built 50:1 worm stage (McMaster 57545K633 steel worm,
#   McMaster 4037N133 nylon wheel, run dry), the wheel sits on an 8 mm common shaft along y, and the shaft
#   carries two GT2 60T loops. One column's carriage clamps the rising run of its loop, the other column's
#   carriage the falling run, so the two pads move in opposite directions by the same amount. The worm holds
#   both stacks with the motor unpowered.
# Design basis: the 2026-11-27 belt elevator study (local, not in the repo) and its two predecessors, the
# 2026-11-20 storage study lanes L-E (library columns, cage) and C (cartridge tower). Every value below names
# its source or says ASSUMED. Changes this model makes to the study are marked CHANGED with the reason.
#
# Run with FreeCAD's console:  freecadcmd tools/build_belt_elevator.py
# Writes CAD/Belt Elevator/: the FCStd (snapshot state, every part in a group tree), an assembly STEP, one STEP
# per printed or cut part (placed at the origin, in model orientation) and the check report.
#
# Frame: as tools/build_mask_stowage.py: x = mm from the strip's left edge (machine +X to the right), y = mm from
# the inner front wall (toward the back), z = mm above the table. Column positions come from that generator's
# Layout(): library column A sits at its L2 position, B at L1, C and D at C and D.
#
# Integrated design (2026-11-28 "lego" redesign; belts kept). It merges two design lanes, each marked in the
# CHANGED notes below by its lane name:
#   Library tower, lane lib-rearrange. CHANGED: the library's two loops no longer stand in the gap between columns
#   A and B, where two 60T stacks with their bearing cheeks need about 71 mm of y and the pad rings leave about 60.
#   Loop A stands in front of column A (between A and the inner front wall) and loop B behind column B (behind the
#   cartridge tower's worm stage), both on one common 8 mm shaft along y at x 114, so the pads still move opposite
#   ways by equal amounts with one motor. Each loop has its own idler bracket. The gap between the columns is empty,
#   which also clears B's label ear at its 270 deg seating: LabelAngle stays 270 (build_filter_cartridge.py is not
#   edited). The drive keeps the study's part types (60T stacks, 608 cheek brackets, LM8UU on 8 mm rods); the
#   library shaft is longer (404, cut from the 0.5 m stock) and runs in two more pillow blocks. Two parts are new or
#   reshaped: the bias steel is one stepped plate on carriage A's front face, and the reference cages' top-ring arm
#   slots follow the new riser angles (A -45, B +60 deg instead of +40 and -40), a change to L-E's cage.
#   Cartridge tower, lane cart-d. CHANGED: D's landing top (and tube rim) comes down from 353 to 339.5, under the
#   grown head envelope at library and C picks; the eject face stays 355, so a spent cartridge drops 15.5 mm, with
#   a 1.5 mm lead-in on D's rim. The clamp drop is set per column (D 64.4). D's idler runs on two 688ZZ in 6 mm
#   cheeks, so its bracket stands in front of D's whole tube (no notch), and D's riser moves to (250, 26).
#   Checks ADDED in the merge (grafted from lane lib-compact): belts against every stack zone, free runs against
#   their own carriage's window, and the library stack zones inside the strip.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)

# ---- load build_mask_stowage.py (and through it build_filter_cartridge.py) without running its Main()
Src = open(os.path.join(Here, "build_mask_stowage.py"), encoding="utf-8").read()
Cut = Src.rindex("\nMain()")
Sto = {"__file__": os.path.join(Here, "build_mask_stowage.py")}
exec(compile(Src[:Cut], "build_mask_stowage.py", "exec"), Sto)
SL, CartP, MaskP = Sto["L"], Sto["CartP"], Sto["MaskP"]

Version = "v20261128-A"

P = dict(
    # ---- process numbers (2026-11-20 study constraints; build_mask_stowage.py)
    NLib=32,                # masks in the library (constraints process.library_size)
    NCart=40,               # cartridges in C when full (build_mask_stowage.py ColCap)
    S0=344.0,               # L-E: the placement surface every library pick and place is set up at
    LibCeiling=337.0,       # L-E: fixed hardware near a library column stays below S0 - 7 (informational check)
    TransitLib=354.0,       # L-E: ring face for the L1 <-> L2 transit
    CPick=350.0,            # #233: ring face at a C pick = top plate face of C's top cartridge
    DEject=355.0,           # #233: ring face at the eject over D
    # CHANGED from the belt study's 2.0 (lane cart-d): D's landing top (the plate face of a spent cartridge landed on
    # a D at its highest) comes down from 353 to 339.5, under the grown head envelope's bottom at an A pick (340.8)
    # and at a C pick (346.5); both envelopes overlap D in plan. Cost: the spent cartridge drops 15.5 mm, not 2, and
    # the first 10.74 of it (release bottom 350.24 to the rim at 339.5) is unguided. The rim's lead-in captures a plate
    # released up to 3.0 mm off centre; one released further lands on the rim's 0.5 mm flat and can cock. It cannot
    # wedge across the bore: the plate's section diagonal sqrt(109^2 + 4.76^2) = 109.1 < 112. Checked: the drop path.
    DLandGap=15.5,
    # ---- drive shaft and pulleys
    ShaftZ=40.0,            # belt study: common shaft axis
    ShaftD=8.0,             # Phidgets TRM4000_0 8 mm ground shaft, 0.5 m (belt study parts table); each common shaft
                            # (library 404, cartridge 367) and the idler axles are cut from it
    PulleyTeeth=60,         # Phidgets TRM4105_0 GT2 60T, 8 mm bore
    PulleyOD=37.69,         # TRM4105_0 mechanical drawing: tooth tip diameter 37.69
    PulleyToothW=11.0,      # drawing: toothed width 11
    PulleyHubD=24.0,        # drawing: hub diameter 24
    PulleyHubL=5.0,         # drawing: total length 16 less the toothed 11
    FlangeOD=43.0,          # printed belt guide flange (the pulley has none): ASSUMED, sets the idler top
    FlangeT=1.5,
    CollarOD=16.0,          # 8 mm set screw shaft collar, ASSUMED (not read)
    CollarL=8.0,
    SpacerOD=12.0,          # printed spacer between an idler's plain-side flange and its bearing
    SpacerL=2.0,
    # ---- belt: GT2, 2 mm pitch, 6 mm wide, about 1.38 thick (belt study, ASSUMED from listings)
    BeltW=6.0,
    BeltT=1.38,
    # ---- idler. CHANGED: the library idlers sit 6.9 lower than the study's 314.9, so their flanges and bracket stay
    # under the cage's top ring (z 332.5); the cartridge tower keeps 314.9
    IdlerZ={"lib": 308.0, "cart": 314.9},
    CheekT=8.0,             # printed cheek around a 608 (7 wide)
    # CHANGED (lane cart-d): D's idler runs on two 688ZZ (8 x 16 x 5, ASSUMED: ISO 15 dimension series 18, not read)
    # in 6 mm cheeks and sliders, so its bracket fits in front of D's tube (y 0..35.7) with no notch in the tube
    IdlerBearing={"A": "B608", "B": "B608", "C": "B608", "D": "B688"},
    IdlerCheekT={"A": 8.0, "B": 8.0, "C": 8.0, "D": 6.0},
    CheekBar=(4.0, 3.0),    # bracket material under and over the slider slot
    SliderW=30.0,           # printed axle slider holding the 608, in a slot in each cheek
    SliderH=26.0,
    TakeUp=4.0,             # slot length beyond the slider, each way: +-4 on the axle, +-8 on the loop
    RodBlockHalfX=6.0,      # rod block around each guide rod top, x half width
    # ---- guide rods and carriages
    RodD=8.0,
    RodDx=30.0,             # belt study: rods at +-30 from the loop centre
    LmOD=15.0,              # LM8UU 8 x 15 x 24
    LmL=24.0,
    CarHalfX=39.5,          # CHANGED from the study's 36: two LM8UU (OD 15) at +-30 need 37.5 plus a wall
    CarHalfY=10.0,
    CarH=30.0,              # CHANGED from the study's 36 (drawn) to keep the carriage clear of both pulleys
    WindowX=6.0,            # free run window through the carriage (study sheet d: 6 mm)
    WindowY=10.0,
    FootW=16.0,             # printed rod foot on the table
    FootH=20.0,
    # ---- pads and arms
    # CHANGED from the study's 66: pad top to carriage centre; see the clamp window check. CHANGED (lane cart-d): per
    # column, since D's lower landing moves D's travel down 13.5 mm and 76 would put D's carriage into its drive
    # flanges; D's window is 58.3..70.5, the other columns keep 76
    ClampDrop={"A": 76.0, "B": 76.0, "C": 76.0, "D": 64.4},
    PadT=6.0,               # L-E PlatformT
    LibPadR0=47.0,          # belt study sheet e: library pad ring r 47..58 under the bottom mask's frame
    LibPadR1=58.0,
    CartPadR=54.0,          # belt study: disc d 108 under the bottom cartridge's plate
    ArmW=8.0,
    JogT=6.0,               # horizontal jog from the carriage to the riser, at the carriage top
    # riser positions (plan): outside each idler bracket and outside the cage or tube (CHANGED: the study's arm
    # ran straight from the carriage, through the idler bracket's footprint)
    LibRiserR=74.0,         # library riser centre radius from its column axis, outside the cage's top ring (r 72)
    # CHANGED (lane lib-rearrange): per column, angle from the column axis toward its own loop. A: -45, so the riser
    # stands 6.9 mm behind loop A's idler bracket (y <= 40.5) and inside carriage A's x range; B: +60, midway between
    # B's cage rods at 0 and 120 deg, 18.7 mm in front of loop B's bracket (y >= 370.5), inside carriage B's x range.
    # Was A: +40, B: -40, toward the old loops in the gap.
    LibRiserDeg={"A": -45.0, "B": 60.0},
    CRiser=(196.0, 280.0),  # between C's tube (y <= 271.7) and C's idler bracket (y >= 289.2)
    # beside D's idler bracket on +x, clear of the control box (x 258.5). CHANGED from (244, 26) (lane cart-d): the
    # arm from D's pad to (244, 26) touched the bracket's back corner; to (250, 26) it passes about 5 mm from it, and
    # the riser (x 246..254) stays 3.5 mm off the box's screw heads
    DRiser=(250.0, 26.0),
    # ---- library bias weight on carriage A (belt study section 5: 6 N, 612 g of steel)
    BiasG=612.0,
    SteelDensity=7.85e-3,   # g/mm^3
    # CHANGED (lane lib-rearrange): the bias is one stepped steel plate on carriage A's -y face (toward the front
    # wall), since carriage A now runs between column A and the wall. Its body lies in front of the drive pulley's
    # hub end and the shaft end, so it can hang far below the carriage; a 2 mm lip over the hub joins it to the
    # carriage. Was two blocks, on the +y and -y faces of the old carriage A in the gap.
    BiasT=8.0,              # plate body thickness in y
    BiasHubGap=2.0,         # plate body to the drive hub end and the shaft end, in y
    BiasFloor=2.0,          # lowest the plate body may reach over the table, with carriage A at its lowest
    BiasEndX=1.5,           # plate inset from each end of the carriage, in x
    # ---- worm stage, local frame (u along the worm axis toward the motor, v along the wheel axis, z up)
    WormPD=16.0, WormOD=18.0, WormL=32.0, WormBore=6.0,      # McMaster 57545K633
    WheelOD=53.0, WheelFace=10.0, WheelHubD=30.0, WheelHubL=10.0, WheelBore=8.0,   # McMaster 4037N133 = KHK PG1-50R1
    CentreDist=33.0,        # KHK PG1-50R1 mounting distance 33 (print the housing at 33.1, belt study)
    RollPinD=2.0,
    B626=(6.0, 19.0, 6.0), B608=(8.0, 22.0, 7.0),            # bore, OD, width
    B688=(8.0, 16.0, 5.0),  # 688ZZ, ASSUMED (ISO 15 dimension series 18; no datasheet read). CHANGED: new, D's idler
    CouplerD=14.0, CouplerL=20.0,                            # 5-to-6 mm coupler, ASSUMED
    MotorSide=42.3, MotorL=22.0, MotorShaftD=5.0, MotorShaftL=24.0,   # 17HS08-1004S, ASSUMED (body length not read)
    MotorPilotD=22.0, MotorPilotH=2.0, MotorHoleSpacing=31.0,         # NEMA 17 face
    # housing outside. The -v wall stands 2 mm off the worm (OD 18); the motor wall is a 13 mm standoff, so the
    # 17HS08's 24 mm shaft (ASSUMED) starts where the worm shaft ends, in the coupler's middle
    Hu=(-37.0, 63.0), Hv=(-18.0, 24.0), Hz=(0.0, 95.0),
    HLeftWall=8.0, HMotorWall=13.0, HFloor=12.0, HRoof=4.0, HWallV=7.0,
    RibU=(19.0, 27.0), RibZ0=62.0,                            # rib carrying the motor-side 626
    SplitZ=73.0,            # housing halves split at the worm axis
    # ---- placement (belt study section 3; the wheel planes are this model's)
    # CHANGED (lane lib-rearrange): LibShaftX 96 -> 114. Loop A's idler bracket (x 78..150) then clears A's label ear
    # at its 270 deg seating (x <= 74.7) by 3.3 mm, and carriage A (x 74.5..153.5) clears carriage D (x >= 156.5) by
    # 3.0 mm where both run in front of their columns.
    LibShaftX=114.0, LibWheelY=136.0, LibMotorSign=1,
    CartShaftX=196.0, CartWheelY=351.0, CartMotorSign=-1,
    # CHANGED (lane lib-rearrange): A 177.69 -> 23.5 (in front of column A: the bracket runs y 4..40.5, 6 mm off A's
    # pad ring at its nearest corner and 4 mm off the front wall; the bias plate body ends 3 mm off the wall);
    # B 209.69 -> 390.0 (behind column B: carriage B, which runs down to z 88.7, clears the cartridge worm motor
    # (y <= 372.2, z <= 94.2) by 7.8 mm in y)
    # D: CHANGED from 18 (lane cart-d): with the 688 cheeks D's bracket spans y 1..33.5, 2.2 mm in front of D's tube
    LoopY={"A": 23.5, "B": 390.0, "C": 308.69, "D": 16.0},
    # which side of each pulley the hub faces (+1 = +y); the bracket and the risers depend on it
    # CHANGED (lane lib-rearrange): B 1 -> -1. Both library hubs now face -y: loop A's hub faces the front wall and
    # its collar and pillow block face column A; loop B's collar and pillow block face the back, its hub column B
    HubSide={"A": -1, "B": -1, "C": -1, "D": 1},
    # which run (-1 = -x, +1 = +x) each carriage clamps; the other run passes through its window
    ClampRun={"A": -1, "B": 1, "C": -1, "D": 1},
    # CHANGED (lane lib-rearrange): the library shaft runs from loop A's hub end (flush) to past loop B's pillow block
    LibShaftY=(13.0, 417.0), CartShaftY=(2.0, 369.0),
    # CHANGED (lane lib-rearrange): (222,) -> a block outboard of each loop's collar and one under column B, so the
    # 8 mm shaft (now 404 long, y 13..417) has no span over 160 mm; none sits under the cartridge worm motor (y 330..372)
    LibShaftBlocks=(39.5, 280.0, 406.0),  # y of the low face of each 608 pillow block beside the housing's own two
    CartShaftBlocks=(286.0, 30.0),
    ShaftBlockT=9.0, ShaftBlockW=30.0,
    # ---- reference solids (not part of this design)
    CageRodD=6.0, CageRodR=62.5, CageRodT=7.75,     # L-E: six rods, two straddling each ear
    CageZ0=130.0,           # L-E sketch: spider top
    CageRingR=(60.0, 72.0), CageRingZ=(332.5, 337.0),
    SpiderZ=(125.0, 130.0), SpiderArmW=20.0, SpiderR=66.0, SpiderPostW=20.0,
    TubeBore=112.0, TubeWall=2.0,      # #233 C: bore 3 over the 109 plate; D gets the same tube (belt study)
    # D's rim: CHANGED from 350 (lane cart-d): it is D's landing top now (Layout DLandTop), so a full D stands inside
    # its tube; a 1.5 mm 45 deg lead-in on the rim's inside edge (CHANGED, new) widens the capture of a dropped plate
    # from 1.5 to 3.0 mm radial
    TubeZ0=140.0, DRimChamfer=1.5, TubeSlotW=24.0,
    # ---- checks
    MinGap=1.0,             # moving parts to anything they are not designed to touch, over the whole travel
    HeadMargin=SL["HeadMargin"],
    SweepSteps=12,
    WheelTorqueNm=1.96,     # KHK PG1-50R1 allowable torque (Lewis), catalog section 9 pp. 344-345
    MotorTorqueNcm=16.0,    # 17HS08-1004S holding torque, omc-stepperonline listing (belt study)
    MuDryLow=0.2,           # belt study: assumed run-in lower bound of dry nylon on steel
)

# Paul Tol bright and muted
TolBlue, TolCyan, TolGreen, TolYellow = (0x44, 0x77, 0xAA), (0x66, 0xCC, 0xEE), (0x22, 0x88, 0x33), (0xCC, 0xBB, 0x44)
TolRed, TolPurple, TolGrey = (0xEE, 0x66, 0x77), (0xAA, 0x33, 0x77), (0xBB, 0xBB, 0xBB)
Dark = (0x33, 0x33, 0x33)


class Item:
    """One solid. Role: printed, bought, steel, belt or ref. Mover: None for fixed parts, else the column key."""

    def __init__(self, name, group, shape, role, color, mover=None, partKey=None):
        self.Name, self.Group, self.Shape, self.Role = name, group, shape, role
        self.Color, self.Mover, self.PartKey = color, mover, partKey


def Cyl(r, z0, z1, x, y):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def CylY(r, y0, y1, x, z):
    return Part.makeCylinder(r, y1 - y0, V(x, y0, z), V(0, 1, 0))


def CylX(r, x0, x1, y, z):
    return Part.makeCylinder(r, x1 - x0, V(x0, y, z), V(1, 0, 0))


def Box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def RingY(ri, ro, y0, y1, x, z):
    s = CylY(ro, y0, y1, x, z)
    return s.cut(CylY(ri, y0 - 1, y1 + 1, x, z)) if ri > 0 else s


def TowerOf(key):
    return "lib" if key in ("A", "B") else "cart"


def IdlerZ(key):
    return P["IdlerZ"][TowerOf(key)]


def ClampDrop(key):
    """CHANGED, new (lane cart-d): the clamp drop is set per column."""
    return P["ClampDrop"][key]


def CheekZ(key):
    """Idler bracket bottom and top: the slider slot (slider plus take-up each way) and a bar under and over it."""
    z = IdlerZ(key)
    half = P["SliderH"] / 2 + P["TakeUp"]
    return z - half - P["CheekBar"][0], z + half + P["CheekBar"][1]


def Bar(p0, p1, w, z0, z1):
    """A box of width w from plan point p0 to p1 (both ends square)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    b = Part.makeBox(length, w, z1 - z0, V(0, -w / 2, z0))
    b.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(math.atan2(dy, dx)))
    b.translate(V(p0[0], p0[1], 0))
    return b


# ---------------------------------------------------------------------------------------------------- layout
def Layout():
    parts, c = Sto["Build"](MaskP)
    bare = max(parts[n].BoundBox.ZMax for n in ("Mask", "MaskBall1", "MaskBall2", "MaskBall3", "EarMagnet1",
                                                 "EarMagnet2", "EarMagnet3") if n in parts)
    d = Sto["Layout"](c, bare)
    g = dict(d=d)
    g["Col"] = {"A": d["L2"], "B": d["L1"], "C": d["C"], "D": d["D"]}
    g["LibP"] = d["BarePitch"]
    g["CartP"] = d["CartPitch"]
    g["Combo"] = d["ComboPitch"]
    g["PulleyPD"] = P["PulleyTeeth"] * 2.0 / math.pi
    g["R"] = g["PulleyPD"] / 2
    g["BeltR0"] = P["PulleyOD"] / 2                   # belt back on the tooth tips (teeth not modelled)
    g["BeltR1"] = g["BeltR0"] + P["BeltT"]
    g["LibK"] = 2 * P["S0"] - P["NLib"] * g["LibP"]   # L-E: PA + PB = K
    g["LibPMin"] = P["S0"] - P["NLib"] * g["LibP"]
    g["LibPMax"] = P["S0"]
    g["CPMin"] = P["CPick"] - P["NCart"] * g["CartP"]
    g["CPMax"] = P["CPick"] - g["CartP"]
    g["DPMax"] = P["DEject"] - g["CartP"] - P["DLandGap"]
    g["DLandTop"] = P["DEject"] - P["DLandGap"]       # CHANGED, new: plate face of a cartridge landed on D at its highest
    # CHANGED, new: bottom of the grown head envelope at a library pick and at a C pick (both overlap D in plan)
    g["HeadBotLib"] = P["S0"] - g["LibP"] + g["Combo"] + SL["HeadLowZ0"] - P["HeadMargin"]
    g["HeadBotC"] = P["CPick"] + SL["HeadLowZ0"] - P["HeadMargin"]
    g["CartK"] = g["CPMin"] + g["DPMax"]              # C full and D empty
    g["LibFace"] = P["S0"] - g["LibP"] + g["Combo"]   # L-E LibFace: pick and place
    g["FlangeTopDrive"] = P["ShaftZ"] + P["FlangeOD"] / 2
    g["FlangeBotIdler"] = {t: z - P["FlangeOD"] / 2 for t, z in P["IdlerZ"].items()}
    g["LoopLen"] = {t: 2 * (z - P["ShaftZ"]) + math.pi * g["PulleyPD"] for t, z in P["IdlerZ"].items()}
    return g


def PadRange(g, key):
    if key in ("A", "B"):
        return g["LibPMin"], g["LibPMax"]
    if key == "C":
        return g["CPMin"], g["CPMax"]
    return g["CartK"] - g["CPMax"], g["DPMax"]


def Pads(g, tower, t):
    """Pad tops of both columns of a tower; t in 0..1 runs the first column from its low to its high end."""
    if tower == "lib":
        pa = g["LibPMin"] + t * (g["LibPMax"] - g["LibPMin"])
        return {"A": pa, "B": g["LibK"] - pa}
    pc = g["CPMin"] + t * (g["CPMax"] - g["CPMin"])
    return {"C": pc, "D": g["CartK"] - pc}


def LoopX(key):
    return P["LibShaftX"] if key in ("A", "B") else P["CartShaftX"]


# ---------------------------------------------------------------------------------------------------- worm stage
def WormStage(g, tower):
    """Housing halves, worm, wheel, bearings, coupler and motor, built in the local frame (u, v, z) and placed."""
    u0, u1 = P["Hu"]
    v0, v1 = P["Hv"]
    z0, z1 = P["Hz"]
    zs, zw = P["ShaftZ"], P["ShaftZ"] + P["CentreDist"]
    # housing: outer block less the cavity, with bearing bores
    outer = Box(u0, u1, v0, v1, z0, z1)
    cav = Box(u0 + P["HLeftWall"], u1 - P["HMotorWall"], v0 + P["HWallV"], v1 - P["HWallV"], z0 + P["HFloor"],
              z1 - P["HRoof"])
    h = outer.cut(cav)
    rib = Box(P["RibU"][0], P["RibU"][1], v0 + P["HWallV"], v1 - P["HWallV"], P["RibZ0"], z1 - P["HRoof"])
    h = h.fuse(rib)
    b626, b608 = P["B626"], P["B608"]
    h = h.cut(CylX(b626[1] / 2, u0 - 1, u0 + P["HLeftWall"] + 1, 0, zw))          # left 626 bore
    h = h.cut(CylX(b626[1] / 2, P["RibU"][0] - 1, P["RibU"][1] + 1, 0, zw))         # rib 626 bore
    h = h.cut(CylY(b608[1] / 2, v0 - 1, v1 + 1, 0, zs))                             # both 608 bores
    h = h.cut(CylX(P["MotorPilotD"] / 2 + 0.1, u1 - P["HMotorWall"] - 1, u1 + 1, 0, zw))
    hs = P["MotorHoleSpacing"] / 2
    for dv in (-hs, hs):
        for dz in (-hs, hs):
            h = h.cut(CylX(1.7, u1 - P["HMotorWall"] - 1, u1 + 1, dv, zw + dz))
    h = h.removeSplitter()
    lowerKeep = Box(u0 - 1, u1 + 1, v0 - 1, v1 + 1, z0 - 1, P["SplitZ"]).fuse(
        Box(u1 - P["HMotorWall"], u1 + 1, v0 - 1, v1 + 1, z0 - 1, z1 + 1))
    lower = h.common(lowerKeep).removeSplitter()
    upper = h.cut(lowerKeep).removeSplitter()
    items = [("HousingLower", lower, "printed", TolYellow, "WormHousingLower"),
             ("HousingUpper", upper, "printed", TolYellow, "WormHousingUpper")]
    # wheel (teeth band centred on the worm, hub toward +v) and its roll pin hole
    wheel = RingY(P["WheelBore"] / 2, P["WheelOD"] / 2, -P["WheelFace"] / 2, P["WheelFace"] / 2, 0, zs).fuse(
        RingY(P["WheelBore"] / 2, P["WheelHubD"] / 2, P["WheelFace"] / 2, P["WheelFace"] / 2 + P["WheelHubL"], 0, zs))
    pinV = P["WheelFace"] / 2 + P["WheelHubL"] / 2
    pin = CylX(P["RollPinD"] / 2, -P["WheelHubD"] / 2, P["WheelHubD"] / 2, pinV, zs)
    wheel = wheel.cut(pin).removeSplitter()
    items += [("Wheel", wheel, "bought", TolBlue, None), ("RollPin", pin, "bought", Dark, None)]
    # worm on its shaft, two 626, coupler, motor
    worm = CylX(P["WormOD"] / 2, -P["WormL"] / 2, P["WormL"] / 2, 0, zw).cut(
        CylX(P["WormBore"] / 2, -P["WormL"] / 2 - 1, P["WormL"] / 2 + 1, 0, zw))
    cpl0 = u1 - P["HMotorWall"] - 1.0 - P["CouplerL"]
    wshaft = CylX(P["WormBore"] / 2, u0 + 1.0, cpl0 + P["CouplerL"] / 2, 0, zw)
    items += [("Worm", worm, "bought", Dark, None), ("WormShaft", wshaft, "bought", TolGrey, None)]
    for nm, ua in (("Bearing626Left", u0 + 1.0), ("Bearing626Rib", P["RibU"][0] + 1.0)):
        items.append((nm, CylX(b626[1] / 2, ua, ua + b626[2], 0, zw).cut(CylX(b626[0] / 2, ua - 1, ua + b626[2] + 1,
                                                                                0, zw)), "bought", TolGrey, None))
    cpl = CylX(P["CouplerD"] / 2, cpl0, cpl0 + P["CouplerL"], 0, zw).cut(
        CylX(P["WormBore"] / 2, cpl0 - 1, cpl0 + P["CouplerL"] / 2, 0, zw)).cut(
        CylX(P["MotorShaftD"] / 2, cpl0 + P["CouplerL"] / 2, cpl0 + P["CouplerL"] + 1, 0, zw))
    items.append(("Coupler", cpl, "bought", TolGrey, None))
    ms = P["MotorSide"] / 2
    motor = Box(u1, u1 + P["MotorL"], -ms, ms, zw - ms, zw + ms).fuse(
        CylX(P["MotorPilotD"] / 2, u1 - P["MotorPilotH"], u1, 0, zw)).fuse(
        CylX(P["MotorShaftD"] / 2, u1 - P["MotorShaftL"], u1 - P["MotorPilotH"], 0, zw))
    items.append(("Motor17HS08", motor, "bought", Dark, None))
    for nm, va in (("Bearing608WallLow", v0), ("Bearing608WallHigh", v1 - b608[2])):
        items.append((nm, RingY(b608[0] / 2, b608[1] / 2, va, va + b608[2], 0, zs), "bought", TolGrey, None))
    # place: rotate 180 deg about z for a motor on -x, then move the wheel axis to (shaft x, wheel plane y)
    sx = P["LibShaftX"] if tower == "lib" else P["CartShaftX"]
    wy = P["LibWheelY"] if tower == "lib" else P["CartWheelY"]
    sign = P["LibMotorSign"] if tower == "lib" else P["CartMotorSign"]
    out = []
    for nm, shp, role, col, pk in items:
        s = shp.copy()
        if sign < 0:
            s.rotate(V(0, 0, 0), V(0, 0, 1), 180)
        s.translate(V(sx, wy, 0))
        out.append(Item("%s%s" % ("Lib" if tower == "lib" else "Cart", nm), "WormStage" + tower.capitalize(), s,
                        role, col, None, pk))
    return out, pin, sx, wy, sign


# ---------------------------------------------------------------------------------------------------- pulleys
def PulleyStack(g, key, z, idler):
    """Pulley (teeth and hub), its two flanges, and a collar (drive) or a spacer (idler) on the plain side."""
    x, yl = LoopX(key), P["LoopY"][key]
    hs = P["HubSide"][key]
    tw, fl = P["PulleyToothW"], P["FlangeT"]
    t0, t1 = yl - tw / 2, yl + tw / 2
    hub = (t0 - P["PulleyHubL"], t0) if hs < 0 else (t1, t1 + P["PulleyHubL"])
    pulley = RingY(P["ShaftD"] / 2, P["PulleyOD"] / 2, t0, t1, x, z).fuse(
        RingY(P["ShaftD"] / 2, P["PulleyHubD"] / 2, hub[0], hub[1], x, z)).removeSplitter()
    hubFace = t0 if hs < 0 else t1
    plainFace = t1 if hs < 0 else t0
    fh = (hubFace - fl, hubFace) if hs < 0 else (hubFace, hubFace + fl)
    fp = (plainFace, plainFace + fl) if hs < 0 else (plainFace - fl, plainFace)
    flHub = RingY(P["PulleyHubD"] / 2 + 0.1, P["FlangeOD"] / 2, fh[0], fh[1], x, z)
    flPlain = RingY(P["ShaftD"] / 2, P["FlangeOD"] / 2, fp[0], fp[1], x, z)
    outer = fp[1] if hs < 0 else fp[0]
    L = P["SpacerL"] if idler else P["CollarL"]
    od = P["SpacerOD"] if idler else P["CollarOD"]
    sp = (outer, outer + L) if hs < 0 else (outer - L, outer)
    keeper = RingY(P["ShaftD"] / 2, od / 2, sp[0], sp[1], x, z)
    tag = "Idler" if idler else "Drive"
    grp = "Loop" + key
    span = dict(hubEnd=(hub[0] if hs < 0 else hub[1]), plainEnd=(sp[1] if hs < 0 else sp[0]))
    return [Item("Pulley%s%s" % (tag, key), grp, pulley, "bought", TolGrey),
            Item("FlangeHub%s%s" % (tag, key), grp, flHub, "printed", TolGreen, None, "FlangeHubSide"),
            Item("FlangePlain%s%s" % (tag, key), grp, flPlain, "printed", TolGreen, None, "FlangePlainSide"),
            Item(("Spacer" if idler else "Collar") + "%s%s" % (tag, key), grp, keeper,
                 "printed" if idler else "bought", TolGrey, None, "IdlerSpacer" if idler else None)], span


# ---------------------------------------------------------------------------------------------------- idler brackets
def IdlerBracket(g, keys, spans):
    """One printed bracket per tower end: cheeks with slider slots around the 608s, rod blocks between cheeks.
    keys: the loops it carries. Returns items and the cheek y ranges."""
    x = LoopX(keys[0])
    # CHANGED (lane cart-d): bearing and cheek thickness per bracket (D: 688 in 6 mm cheeks, the rest unchanged)
    bName = P["IdlerBearing"][keys[0]]
    b608 = P[bName]
    cheekT = P["IdlerCheekT"][keys[0]]
    cheeks = []        # (y0, y1, loop keys whose bearings sit in it)
    for k in keys:
        yl, hs = P["LoopY"][k], P["HubSide"][k]
        hubEnd, plainEnd = spans[k]["hubEnd"], spans[k]["plainEnd"]
        hubCheek = (hubEnd - 1.0 - cheekT, hubEnd - 1.0) if hs < 0 else (hubEnd + 1.0, hubEnd + 1.0 + cheekT)
        plainCheek = (plainEnd, plainEnd + cheekT) if hs < 0 else (plainEnd - cheekT, plainEnd)
        cheeks += [hubCheek, plainCheek]
    # merge cheeks that touch or overlap (the library's middle cheek carries both loops' plain-side bearings)
    cheeks.sort()
    merged = []
    for c in cheeks:
        if merged and c[0] <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], c[1]))
        else:
            merged.append(c)
    hx = P["RodDx"] + P["RodBlockHalfX"]
    z0, z1 = CheekZ(keys[0])
    zi = IdlerZ(keys[0])
    br = None
    for (y0, y1) in merged:
        s = Box(x - hx, x + hx, y0, y1, z0, z1)
        br = s if br is None else br.fuse(s)
    # rod blocks between neighbouring cheeks, at each guide rod
    for k in keys:
        yl = P["LoopY"][k]
        lo = max(c[1] for c in merged if c[1] <= yl)
        hi = min(c[0] for c in merged if c[0] >= yl)
        for sx in (-1, 1):
            rx = x + sx * P["RodDx"]
            br = br.fuse(Box(rx - P["RodBlockHalfX"], rx + P["RodBlockHalfX"], lo, hi, z0, z1))
            br = br.cut(Cyl(P["RodD"] / 2, z0 - 1, z1 - 4, rx, yl))
    # slider slots through every cheek, and an M4 tension screw hole under each slot
    sw, sh, tu = P["SliderW"], P["SliderH"], P["TakeUp"]
    for (y0, y1) in merged:
        br = br.cut(Box(x - sw / 2, x + sw / 2, y0 - 1, y1 + 1, zi - sh / 2 - tu, zi + sh / 2 + tu))
        br = br.cut(Cyl(1.7, z0 - 1, zi - sh / 2 - tu + 1, x, (y0 + y1) / 2))
    br = br.removeSplitter()
    name = "IdlerBracket" + "".join(keys)
    items = [Item(name, "Bracket" + "".join(keys), br, "printed", TolYellow, None, name)]
    # sliders with their 608s, axles
    for (y0, y1) in merged:
        sl = Box(x - sw / 2, x + sw / 2, y0, y1, zi - sh / 2, zi + sh / 2).cut(
            CylY(b608[1] / 2, y0 - 1, y1 + 1, x, zi))
        items.append(Item("IdlerSlider%s_y%.0f" % ("".join(keys), y0), "Bracket" + "".join(keys), sl, "printed",
                          TolGreen, None, "IdlerSlider%.0f" % (y1 - y0)))
    for k in keys:
        yl, hs = P["LoopY"][k], P["HubSide"][k]
        hubEnd, plainEnd = spans[k]["hubEnd"], spans[k]["plainEnd"]
        if hs < 0:
            ya, yb = hubEnd - 1.0 - b608[2], plainEnd + b608[2]
            bearings = [(hubEnd - 1.0 - b608[2], hubEnd - 1.0), (plainEnd, plainEnd + b608[2])]
        else:
            ya, yb = plainEnd - b608[2], hubEnd + 1.0 + b608[2]
            bearings = [(plainEnd - b608[2], plainEnd), (hubEnd + 1.0, hubEnd + 1.0 + b608[2])]
        items.append(Item("IdlerAxle" + k, "Loop" + k, CylY(P["ShaftD"] / 2, ya, yb, x, zi), "bought", TolGrey))
        for n, (b0, b1) in enumerate(bearings):
            items.append(Item("Idler%s%s%d" % (bName[1:], k, n + 1), "Loop" + k,
                              RingY(b608[0] / 2, b608[1] / 2, b0, b1, x, zi), "bought", TolGrey))
    return items, merged


def RodsAndFeet(key):
    x, yl = LoopX(key), P["LoopY"][key]
    items = []
    for n, sx in enumerate((-1, 1)):
        rx = x + sx * P["RodDx"]
        f = P["FootW"] / 2
        foot = Box(rx - f, rx + f, yl - f, yl + f, 0, P["FootH"]).cut(Cyl(P["RodD"] / 2, 4.0, P["FootH"] + 1, rx, yl))
        items.append(Item("RodFoot%s%d" % (key, n + 1), "Loop" + key, foot, "printed", TolYellow, None, "RodFoot"))
        items.append(Item("GuideRod%s%d" % (key, n + 1), "Loop" + key,
                          Cyl(P["RodD"] / 2, 4.0, CheekZ(key)[1] - 4, rx, yl), "bought", TolGrey))
    return items


def ShaftAndBlocks(g, tower, pin, sx, wy, sign):
    y0, y1 = P["LibShaftY"] if tower == "lib" else P["CartShaftY"]
    shaft = CylY(P["ShaftD"] / 2, y0, y1, sx, P["ShaftZ"])
    pinW = pin.copy()
    if sign < 0:
        pinW.rotate(V(0, 0, 0), V(0, 0, 1), 180)
    pinW.translate(V(sx, wy, 0))
    shaft = shaft.cut(pinW)
    grp = "Shaft" + tower.capitalize()
    items = [Item(("Lib" if tower == "lib" else "Cart") + "CommonShaft", grp, shaft, "bought", TolGrey)]
    b608 = P["B608"]
    for yb in (P["LibShaftBlocks"] if tower == "lib" else P["CartShaftBlocks"]):
        t, w = P["ShaftBlockT"], P["ShaftBlockW"] / 2
        blk = Box(sx - w, sx + w, yb, yb + t, 0, P["ShaftZ"] + b608[1] / 2 + 4).cut(
            CylY(b608[1] / 2, yb + 1, yb + 1 + b608[2], sx, P["ShaftZ"])).cut(
            CylY(P["ShaftD"] / 2 + 1, yb - 1, yb + t + 1, sx, P["ShaftZ"]))
        items.append(Item("ShaftBlock%s_y%.0f" % (tower.capitalize(), yb), grp, blk, "printed", TolYellow, None,
                          "ShaftBlock"))
        items.append(Item("Shaft608%s_y%.0f" % (tower.capitalize(), yb), grp,
                          RingY(b608[0] / 2, b608[1] / 2, yb + 1, yb + 1 + b608[2], sx, P["ShaftZ"]), "bought",
                          TolGrey))
    return items


# ---------------------------------------------------------------------------------------------------- moving parts
def RiserPoint(g, key):
    if key in ("A", "B"):
        cx, cy = g["Col"][key]
        a = math.radians(P["LibRiserDeg"][key])     # CHANGED: one angle per column (lane lib-rearrange)
        return cx + P["LibRiserR"] * math.cos(a), cy + P["LibRiserR"] * math.sin(a)
    return P["CRiser"] if key == "C" else P["DRiser"]


def ArmAngle(g, key):
    cx, cy = g["Col"][key]
    rx, ry = RiserPoint(g, key)
    return math.degrees(math.atan2(ry - cy, rx - cx))


def Carriage(g, key, pad):
    """Carriage body (with LM8UU bores and the free-run window), two LM8UU, pad arm, bias blocks on A."""
    x, yl = LoopX(key), P["LoopY"][key]
    zc = pad - ClampDrop(key)
    hz = P["CarH"] / 2
    zt = zc + hz
    hx, hy = P["CarHalfX"], P["CarHalfY"]
    body = Box(x - hx, x + hx, yl - hy, yl + hy, zc - hz, zt)
    for sx in (-1, 1):
        body = body.cut(Cyl(P["LmOD"] / 2, zc - hz - 1, zt + 1, x + sx * P["RodDx"], yl))
    free = -P["ClampRun"][key]
    wx = x + free * (g["BeltR0"] + g["BeltR1"]) / 2
    body = body.cut(Box(wx - P["WindowX"] / 2, wx + P["WindowX"] / 2, yl - P["WindowY"] / 2, yl + P["WindowY"] / 2,
                        zc - hz - 1, zt + 1)).removeSplitter()
    items = [Item("Carriage" + key, "Moving" + key, body, "printed", TolBlue, key, "Carriage")]
    for n, sx in enumerate((-1, 1)):
        lm = Cyl(P["LmOD"] / 2, zc - P["LmL"] / 2, zc + P["LmL"] / 2, x + sx * P["RodDx"], yl).cut(
            Cyl(P["RodD"] / 2, zc - P["LmL"], zc + P["LmL"], x + sx * P["RodDx"], yl))
        items.append(Item("LM8UU%s%d" % (key, n + 1), "Moving" + key, lm, "bought", TolGrey, key))
    # pad arm: jog at the carriage top from a carriage face to the riser, riser up to the pad, arm into the pad
    rx, ry = RiserPoint(g, key)
    w = P["ArmW"] / 2
    # CHANGED (lane lib-rearrange): the jog runs out of the carriage face that looks toward the riser (it was chosen
    # by column key: B toward +y, A and C toward -y; that is the same rule for B and C, and loop A now needs +y)
    if key == "D":
        jog = Box(x + hx - 0.5, rx + w, ry - w, ry + w, zt - P["JogT"], zt)
    elif ry > yl:
        jog = Box(rx - w, rx + w, yl + hy - 0.5, ry + w, zt - P["JogT"], zt)
    else:
        jog = Box(rx - w, rx + w, ry - w, yl - hy + 0.5, zt - P["JogT"], zt)
    if key != "D" and not (x - hx + w <= rx <= x + hx - w):
        raise ValueError("riser of %s at x %.1f is outside its carriage (x %.1f..%.1f)" % (key, rx, x - hx, x + hx))
    riser = Box(rx - w, rx + w, ry - w, ry + w, zt - P["JogT"], pad)
    cx, cy = g["Col"][key]
    a = math.atan2(ry - cy, rx - cx)
    if key in ("A", "B"):
        r0 = (P["LibPadR0"] + P["LibPadR1"]) / 2
        pad3 = Cyl(P["LibPadR1"], pad - P["PadT"], pad, cx, cy).cut(Cyl(P["LibPadR0"], pad - P["PadT"] - 1, pad + 1,
                                                                        cx, cy))
    else:
        r0 = P["CartPadR"] - 6.0
        pad3 = Cyl(P["CartPadR"], pad - P["PadT"], pad, cx, cy)
    arm = Bar((cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (rx, ry), P["ArmW"], pad - P["PadT"], pad)
    padArm = jog.fuse(riser).fuse(arm).fuse(pad3).removeSplitter()
    items.append(Item("PadArm" + key, "Moving" + key, padArm, "printed", TolGreen, key, "PadArm" + key))
    if key == "A":
        items += BiasBlocks(g, zt)
    return items


def BiasExtents(g):
    """CHANGED (lane lib-rearrange): extents of carriage A's bias plate relative to carriage A's top: the lip (over
    the drive hub) reaches down by aLip, 2 mm over the drive flanges; the body (in front of the hub end and the
    shaft end) by aBody, to BiasFloor over the table; both reach up by b, 2 mm under the idler bracket. All over
    carriage A's whole travel. Was the two blocks' extents, limited by the drive flanges and the worm housing."""
    ztMin = g["LibPMin"] - ClampDrop("A") + P["CarH"] / 2
    ztMax = g["LibPMax"] - ClampDrop("A") + P["CarH"] / 2
    b = CheekZ("A")[0] - 2.0 - ztMax
    aLip = ztMin - (g["FlangeTopDrive"] + 2.0)
    aBody = ztMin - P["BiasFloor"]
    return aLip, aBody, b


def BiasPlan():
    """Plan extents of the bias plate: x0, x1, the body's y0..y1 and the lip's y1..y2 (lip ends at carriage A's -y
    face). The body ends BiasHubGap in front of the drive hub, which faces -y on loop A."""
    if P["HubSide"]["A"] != -1:
        raise ValueError("the bias plate needs loop A's drive hub on its -y side")
    x, yl = LoopX("A"), P["LoopY"]["A"]
    hubEnd = yl - P["PulleyToothW"] / 2 - P["PulleyHubL"]
    y1 = hubEnd - P["BiasHubGap"]
    y2 = yl - P["CarHalfY"]
    x0, x1 = x - P["CarHalfX"] + P["BiasEndX"], x + P["CarHalfX"] - P["BiasEndX"]
    return x0, x1, y1 - P["BiasT"], y1, y2


def BiasBlocks(g, zt):
    """CHANGED (lane lib-rearrange): one stepped plate of BiasG grams on carriage A's -y face; the body height is
    solved for the mass and must fit its extents."""
    aLip, aBody, b = BiasExtents(g)
    x0, x1, y0, y1, y2 = BiasPlan()
    lipVol = (x1 - x0) * (y2 - y1) * (aLip + b)
    hBody = (P["BiasG"] / P["SteelDensity"] - lipVol) / ((x1 - x0) * (y1 - y0))
    if hBody > aBody + b:
        raise ValueError("bias plate body needs %.1f of height, has %.1f" % (hBody, aBody + b))
    if P["LibShaftY"][0] < y1 + P["BiasHubGap"] - 1e-6:
        raise ValueError("library shaft starts in front of the drive hub end, under the bias plate")
    plate = Box(x0, x1, y1, y2, zt - aLip, zt + b).fuse(Box(x0, x1, y0, y1, zt + b - hBody, zt + b)).removeSplitter()
    return [Item("BiasPlateA", "MovingA", plate, "steel", Dark, "A", "BiasPlate")]


def FreeRun(g, key):
    """ADDED (integrated): the free run alone, shaft to idler, for the free-run-to-own-carriage check. Same solid as
    the free run inside Belt()."""
    x, yl = LoopX(key), P["LoopY"][key]
    fs = -P["ClampRun"][key]
    xa, xb = sorted((x + fs * g["BeltR0"], x + fs * g["BeltR1"]))
    return Box(xa, xb, yl - P["BeltW"] / 2, yl + P["BeltW"] / 2, P["ShaftZ"], IdlerZ(key))


def Belt(g, key, pad):
    """The loop: free run, two clamped pieces ending at the carriage, and the two arcs."""
    x, yl = LoopX(key), P["LoopY"][key]
    r0, r1 = g["BeltR0"], g["BeltR1"]
    y0, y1 = yl - P["BeltW"] / 2, yl + P["BeltW"] / 2
    zb, zt = P["ShaftZ"], IdlerZ(key)
    zc = pad - ClampDrop(key)
    hz = P["CarH"] / 2
    cs = P["ClampRun"][key]
    fs = -cs

    def Run(side, za, zb_):
        xa, xb = sorted((x + side * r0, x + side * r1))
        return Box(xa, xb, y0, y1, za, zb_)

    lowArc = RingY(r0, r1, y0, y1, x, zb).common(Box(x - r1 - 1, x + r1 + 1, y0 - 1, y1 + 1, zb - r1 - 1, zb))
    topArc = RingY(r0, r1, y0, y1, x, zt).common(Box(x - r1 - 1, x + r1 + 1, y0 - 1, y1 + 1, zt, zt + r1 + 1))
    belt = lowArc.fuse(topArc).fuse(Run(fs, zb, zt)).fuse(Run(cs, zb, zc - hz)).fuse(Run(cs, zc + hz, zt))
    return [Item("Belt" + key, "Moving" + key, belt.removeSplitter(), "belt", TolRed, key)]


# ---------------------------------------------------------------------------------------------------- references
def References(g):
    items = []
    for key in ("A", "B"):
        cx, cy = g["Col"][key]
        arm = ArmAngle(g, key)
        for a in (0.0, 120.0, 240.0):
            t = math.radians(a)
            for s in (-1, 1):
                rx = cx + P["CageRodR"] * math.cos(t) - s * P["CageRodT"] * math.sin(t)
                ry = cy + P["CageRodR"] * math.sin(t) + s * P["CageRodT"] * math.cos(t)
                items.append(Item("CageRod%s_%03.0f%s" % (key, a, "p" if s > 0 else "m"), "Ref" + key,
                                  Cyl(P["CageRodD"] / 2, P["CageZ0"], P["CageRingZ"][0], rx, ry), "ref", TolGrey))
        ring = Cyl(P["CageRingR"][1], P["CageRingZ"][0], P["CageRingZ"][1], cx, cy).cut(
            Cyl(P["CageRingR"][0], P["CageRingZ"][0] - 1, P["CageRingZ"][1] + 1, cx, cy))
        wedge = Part.makeCylinder(P["CageRingR"][1] + 5, P["CageRingZ"][1] - P["CageRingZ"][0] + 2,
                                  V(cx, cy, P["CageRingZ"][0] - 1), V(0, 0, 1), 24.0)
        wedge.rotate(V(cx, cy, 0), V(0, 0, 1), arm - 12.0)
        items.append(Item("CageRing" + key, "Ref" + key, ring.cut(wedge), "ref", TolGrey))
        sp = Cyl(15.0, P["SpiderZ"][0], P["SpiderZ"][1], cx, cy)
        for a in (0.0, 120.0, 240.0):
            sp = sp.fuse(Bar((cx, cy), (cx + P["SpiderR"] * math.cos(math.radians(a)),
                                        cy + P["SpiderR"] * math.sin(math.radians(a))), P["SpiderArmW"],
                             P["SpiderZ"][0], P["SpiderZ"][1]))
        items.append(Item("Spider" + key, "Ref" + key, sp, "ref", TolGrey))
        w = P["SpiderPostW"] / 2
        items.append(Item("SpiderPost" + key, "Ref" + key, Box(cx - w, cx + w, cy - w, cy + w, 0, P["SpiderZ"][0]),
                          "ref", TolGrey))
    rb, ro = P["TubeBore"] / 2, P["TubeBore"] / 2 + P["TubeWall"]
    for key, rim in (("C", P["CPick"] - g["CartP"] - 1.0), ("D", g["DLandTop"])):
        cx, cy = g["Col"][key]
        tube = Cyl(ro, P["TubeZ0"], rim, cx, cy).cut(Cyl(rb, P["TubeZ0"] - 1, rim + 1, cx, cy))
        if key == "D":
            # CHANGED, new (lane cart-d): 45 deg lead-in on the inside of D's rim, inside the 2 mm wall
            ch = P["DRimChamfer"]
            tube = tube.cut(Part.makeCone(rb, rb + ch + 0.5, ch + 0.5, V(cx, cy, rim - ch)))
        a = ArmAngle(g, key)
        slot = Part.makeBox(ro + 5, P["TubeSlotW"], rim - P["TubeZ0"] + 2, V(0, -P["TubeSlotW"] / 2, P["TubeZ0"] - 1))
        slot.rotate(V(0, 0, 0), V(0, 0, 1), a)
        slot.translate(V(cx, cy, 0))
        tube = tube.cut(slot)
        items.append(Item("Tube" + key, "Ref" + key, tube.removeSplitter(), "ref", TolGrey))
    return items


def StackZones(g):
    """Where masks and cartridges can be, over every state: frame r 56, three ears to r 66.5 and the label ear's three
    seatings (build_mask_stowage.py LabelEarBoxes) from the lowest pad to S0 for the library columns; the plate
    (r 54.5) from the lowest pad to the top for C and D. Item.Group carries the column key as 'Zone<key>'."""
    items = []
    frameR, earR = CartP["FrameOD"] / 2, CartP["LobeEarOuterR"]
    for key in ("A", "B"):
        cx, cy = g["Col"][key]
        z0, z1 = g["LibPMin"], P["S0"]
        z = Cyl(frameR, z0, z1, cx, cy)
        for a in (0.0, 120.0, 240.0):
            t = math.radians(a)
            z = z.fuse(Bar((cx + (frameR - 2) * math.cos(t), cy + (frameR - 2) * math.sin(t)),
                           (cx + earR * math.cos(t), cy + earR * math.sin(t)), 9.0, z0, z1))
        for b in Sto["LabelEarBoxes"](cx, cy):
            z = z.fuse(Box(b[0], b[1], b[2], b[3], z0, z1))
        items.append(Item("StackZone" + key, "Zone" + key, z.removeSplitter(), "zone", TolCyan))
    plateR = CartP["PlateOD"] / 2
    for key, z0, z1 in (("C", g["CPMin"], P["CPick"]), ("D", g["CartK"] - g["CPMax"], g["DPMax"] + g["CartP"])):
        cx, cy = g["Col"][key]
        items.append(Item("StackZone" + key, "Zone" + key, Cyl(plateR, z0, z1, cx, cy), "zone", TolCyan))
    return items


# ---------------------------------------------------------------------------------------------------- assembly
def Fixed(g):
    items, spans = [], {}
    for tower in ("lib", "cart"):
        ws, pin, sx, wy, sign = WormStage(g, tower)
        items += ws
        items += ShaftAndBlocks(g, tower, pin, sx, wy, sign)
    for key in ("A", "B", "C", "D"):
        drv, _ = PulleyStack(g, key, P["ShaftZ"], False)
        idl, span = PulleyStack(g, key, IdlerZ(key), True)
        spans[key] = span
        items += drv + idl + RodsAndFeet(key)
    brackets = {}
    # CHANGED (lane lib-rearrange): the library loops are 367 mm apart now, so each gets its own bracket (was one
    # bracket AB with a shared middle cheek)
    for keys in (("A",), ("B",), ("C",), ("D",)):
        it, merged = IdlerBracket(g, keys, spans)
        items += it
        brackets["".join(keys)] = merged
    refs = References(g) + StackZones(g)
    # CHANGED (lane cart-d): D's tube keeps its whole wall; the notch for D's idler bracket is gone (narrower bracket)
    notch = None
    return items, refs, brackets, notch


def Moving(g, tower, t):
    pads = Pads(g, tower, t)
    out = []
    for key, pad in pads.items():
        out += Carriage(g, key, pad) + Belt(g, key, pad)
    return out, pads


# ---------------------------------------------------------------------------------------------------- checks
def Near(a, b, gap):
    ba, bb = a.BoundBox, b.BoundBox
    return not (ba.XMax + gap < bb.XMin or bb.XMax + gap < ba.XMin or ba.YMax + gap < bb.YMin or
                bb.YMax + gap < ba.YMin or ba.ZMax + gap < bb.ZMin or bb.ZMax + gap < ba.ZMin)


def Overlap(a, b):
    if not Near(a, b, 0.0):
        return 0.0
    return a.common(b).Volume


def Gap(a, b):
    return a.distToShape(b)[0]


def AllowedStatic(a, b):
    n = {a.Name, b.Name}
    return any(("Worm" in x and "Shaft" not in x) for x in n) and any("Wheel" in x for x in n)


def AllowedContact(m, o):
    """Moving item m may touch o: its own carriage group, the rods it slides on, the pulleys its belt wraps."""
    if o.Mover == m.Mover:
        belt = [x for x in (m, o) if x.Role == "belt"]
        return not belt or any(x.Name.startswith("Carriage") for x in (m, o))
    k = m.Mover
    if m.Name.startswith("LM8UU") and o.Name.startswith("GuideRod" + k):
        return True
    if m.Name == "Belt" + k and (o.Name in ("PulleyDrive" + k, "PulleyIdler" + k)):
        return True
    return False


def Checks(g, fixed, refs, brackets, notch):
    out, bad, warn = [], 0, 0

    def Line(s=""):
        out.append(s)

    Line("Belt elevator %s: checks (tools/build_belt_elevator.py)" % Version)
    Line("=" * 100)
    Line()
    Line("Geometry")
    Line("  60T pitch diameter %.2f; belt on the tooth tips r %.3f..%.3f (teeth not modelled)" % (
        g["PulleyPD"], g["BeltR0"], g["BeltR1"]))
    for t, nm in (("lib", "library"), ("cart", "cartridge")):
        z0, z1 = CheekZ("A" if t == "lib" else "C")
        Line("  %s: shaft z %.1f, idler axle z %.1f, loop length %.1f mm (both ends in the carriage clamp);" % (
            nm, P["ShaftZ"], P["IdlerZ"][t], g["LoopLen"][t]))
        Line("    idler flanges z %.1f..%.1f (OD %.0f, ASSUMED), idler bracket z %.1f..%.1f" % (
            g["FlangeBotIdler"][t], P["IdlerZ"][t] + P["FlangeOD"] / 2, P["FlangeOD"], z0, z1))
    Line("  drive flange top z %.1f" % g["FlangeTopDrive"])
    Line("  library pad top %.2f..%.2f (PA + PB = %.2f); C %.2f..%.2f, D %.2f..%.2f (PC + PD = %.2f)" % (
        g["LibPMin"], g["LibPMax"], g["LibK"], g["CPMin"], g["CPMax"], g["CartK"] - g["CPMax"], g["DPMax"],
        g["CartK"]))
    Line()
    # CHANGED (lane cart-d): the clamp drop is per column, so each column's drop is checked against its own window
    # (the same carriage limits as before: 2 mm over the drive flanges, 2 mm under the idler flanges and the bracket)
    Line("Clamp window (carriage of height %.0f, centre = pad top - clamp drop, set per column)" % P["CarH"])
    lo = g["FlangeTopDrive"] + 2.0 + P["CarH"] / 2
    his = {k: min(g["FlangeBotIdler"][TowerOf(k)], CheekZ(k)[0]) - 2.0 - P["CarH"] / 2 for k in "ABCD"}
    Line("  carriage centre at least %.1f (2 mm over the drive flanges) and at most %.1f (library) or %.1f (cartridge"
         % (lo, his["A"], his["C"]))
    Line("  tower), 2 mm under the idler flanges and the bracket")
    Line("  the study's 66 puts every carriage top into its idler pulley at the top of its travel: CHANGED")
    for k in "ABCD":
        p0, p1 = PadRange(g, k)
        dLo, dHi = p1 - his[k], p0 - lo
        okDrop = dLo <= ClampDrop(k) <= dHi
        bad += 0 if okDrop else 1
        c0, c1 = p0 - ClampDrop(k), p1 - ClampDrop(k)
        ok = lo <= c0 and c1 <= his[k]
        bad += 0 if ok else 1
        Line("    %s pad %.2f..%.2f, drop window %.2f..%.2f, drop %.1f %s -> carriage centre %.2f..%.2f %s" % (
            k, p0, p1, dLo, dHi, ClampDrop(k), "ok" if okDrop else "OUTSIDE", c0, c1, "inside" if ok else "OUTSIDE"))
    Line()

    # ---- D's landing (CHANGED, new, lane cart-d)
    Line("D's landing (lane cart-d): eject face %.1f, landing top %.2f, so a spent cartridge drops %.1f mm" % (
        P["DEject"], g["DLandTop"], P["DLandGap"]))
    for nm, zb in (("library pick", g["HeadBotLib"]), ("C pick", g["HeadBotC"])):
        m = zb - g["DLandTop"]
        ok = m >= P["MinGap"] - 1e-6
        bad += 0 if ok else 1
        Line("  grown head envelope bottom at a %s %.2f: D's top (landing top = tube rim) %.2f under it %s" % (
            nm, zb, m, "ok" if ok else "FAIL (under %.1f)" % P["MinGap"]))
    tubeD = [r for r in refs if r.Name == "TubeD"][0]
    near = []
    for a in fixed:
        if Near(a.Shape, tubeD.Shape, 5.0):
            near.append((Gap(a.Shape, tubeD.Shape), a.Name))
    near.sort()
    okT = not near or near[0][0] >= P["MinGap"] - 1e-6
    bad += 0 if okT else 1
    Line("  fixed parts to D's whole tube (no notch): nearest %s %s" % (
        ", ".join("%s %.2f" % (n, d) for d, n in near[:4]) if near else "none within 5 mm",
        "ok" if okT else "FAIL (under %.1f)" % P["MinGap"]))
    # ADDED: the drop path. The stack zone ends at D's landing top, so nothing else looks at the 15.5 mm fall: a
    # cylinder of the plate's radius from the release (eject face less one cartridge pitch) down to the landing top,
    # against every part of this design over the cartridge tower's travel, with the library at both ends
    relBot = P["DEject"] - g["CartP"]
    dx, dy = g["Col"]["D"]
    path = Cyl(CartP["PlateOD"] / 2, g["DLandTop"], relBot, dx, dy)
    dropHits, dropNear = [], (1e9, "")
    for i in range(P["SweepSteps"] + 1):
        t = i / float(P["SweepSteps"])
        parts = fixed + Moving(g, "cart", t)[0] + Moving(g, "lib", 0.0)[0] + Moving(g, "lib", 1.0)[0]
        for a in parts:
            if not Near(a.Shape, path, 5.0):
                continue
            gd = Gap(a.Shape, path)
            if gd < dropNear[0]:
                dropNear = (gd, "%s at t %.2f" % (a.Name, t))
            if gd < P["MinGap"] - 1e-6:
                dropHits.append("%s %.2f at t %.2f" % (a.Name, gd, t))
    bad += len(set(dropHits))
    Line("  drop path (r %.1f, z %.2f..%.2f, unguided above the rim): %s" % (
        CartP["PlateOD"] / 2, g["DLandTop"], relBot,
        ("ok; nearest %.2f (%s)" % dropNear if dropNear[0] < 1e8 else "ok; nothing within 5 mm") if not dropHits
        else "FAIL: " + "; ".join(sorted(set(dropHits))[:10])))
    Line()

    # ---- static interference among fixed parts
    Line("Fixed parts against each other (snapshot; overlap volume > 0.01 mm^3)")
    clash = []
    for i, a in enumerate(fixed):
        for b in fixed[i + 1:]:
            v = Overlap(a.Shape, b.Shape)
            if v > 0.01 and not AllowedStatic(a, b):
                clash.append("%s/%s %.2f" % (a.Name, b.Name, v))
    bad += len(clash)
    Line("  %s" % ("ok, no overlaps (the worm and wheel share their tooth depth by design)" if not clash else
                   "OVERLAP: " + "; ".join(clash)))
    Line()
    for title, sel in (("the reference cages and tubes", lambda b: b.Role == "ref"),
                       ("the stack zones (where masks and cartridges can be)", lambda b: b.Role == "zone")):
        Line("Fixed parts against %s" % title)
        clash = []
        for a in fixed:
            for b in refs:
                if sel(b) and Overlap(a.Shape, b.Shape) > 0.01:
                    clash.append("%s/%s" % (a.Name, b.Name))
        bad += len(clash)
        Line("  %s" % ("ok" if not clash else "OVERLAP: " + ", ".join(clash)))
    # ADDED (lane lib-rearrange): the overlap test above lets a fixed part touch a stack zone or a cage; for the
    # library tower's fixed parts this also asks for MinGap to every stack zone, cage and tube, and reports the nearest
    libGroups = ("BracketA", "BracketB", "LoopA", "LoopB", "ShaftLib", "WormStageLib")
    near, tooClose = [], []
    for a in fixed:
        if not a.Group.startswith(libGroups):
            continue
        for b in refs:
            if not Near(a.Shape, b.Shape, 10.0):
                continue
            dd = Gap(a.Shape, b.Shape)
            near.append((dd, a.Name, b.Name))
            if dd < P["MinGap"] - 1e-6:
                tooClose.append("%s/%s %.2f" % (a.Name, b.Name, dd))
    bad += len(tooClose)
    Line("  library fixed parts to every stack zone, cage and tube, at least %.1f: %s" % (
        P["MinGap"], "ok" if not tooClose else "TOO CLOSE: " + ", ".join(tooClose)))
    for dd, an, bn in sorted(near)[:6]:
        Line("    %-26s %-22s %6.2f mm" % (an, bn, dd))
    if notch:
        Line("  D's tube is cut open in front (y < %.1f, z > %.1f) for D's idler bracket: CHANGED from the study,"
             % notch)
        Line("    a spent cartridge (plate 109) cannot pass that %.0f mm opening" % (
            2 * math.sqrt((P["TubeBore"] / 2) ** 2 - (g["Col"]["D"][1] - notch[0]) ** 2)))
    Line()

    # ---- travel sweep
    Line("Travel sweep: moving parts against everything else, %d states per tower, other tower at both ends" % (
        P["SweepSteps"] + 1))
    worst = {}
    fails = []
    statics = fixed + refs
    for tower, other in (("lib", "cart"), ("cart", "lib")):
        for i in range(P["SweepSteps"] + 1):
            t = i / float(P["SweepSteps"])
            mv, _ = Moving(g, tower, t)
            for to in (0.0, 1.0):
                om, _ = Moving(g, other, to)
                for m in mv:
                    for o in statics + om + [x for x in mv if x.Mover != m.Mover]:
                        if o.Group == "Zone" + m.Mover:
                            continue      # a column's own parts stay under its own pad, so its stack never meets them
                        if not Near(m.Shape, o.Shape, P["MinGap"] + 0.01):
                            continue
                        if AllowedContact(m, o):
                            v = Overlap(m.Shape, o.Shape)
                            if v > 0.01:
                                fails.append("%s/%s overlap %.2f at t %.2f" % (m.Name, o.Name, v, t))
                            continue
                        d = Gap(m.Shape, o.Shape)
                        key = (m.Name, o.Name)
                        if key not in worst or d < worst[key][0]:
                            worst[key] = (d, t)
                        if d < P["MinGap"] - 1e-6:
                            fails.append("%s/%s gap %.2f at t %.2f" % (m.Name, o.Name, d, t))
    fails = sorted(set(fails))
    bad += len(fails)
    if fails:
        Line("  FAIL (gap under %.1f mm):" % P["MinGap"])
        for f in fails[:60]:
            Line("    " + f)
        if len(fails) > 60:
            Line("    ... %d more" % (len(fails) - 60))
    else:
        Line("  ok, every gap >= %.1f mm" % P["MinGap"])
    Line("  tightest gaps (moving part / other, smallest over the travel, t = position of the first column):")
    for (mn, on), (d, t) in sorted(worst.items(), key=lambda kv: kv[1][0])[:14]:
        Line("    %-22s %-30s %6.2f mm at t %.2f" % (mn, on, d, t))
    # CHANGED, new (lane cart-d): the cartridge tower's own tightest gaps, so they are not hidden by the library's
    movers = {}
    for it in Moving(g, "cart", 0.0)[0]:
        movers[it.Name] = it.Mover
    Line("  tightest gaps of the cartridge tower's moving parts (C and D):")
    cart = [(kv[0], kv[1]) for kv in worst.items() if movers.get(kv[0][0]) in ("C", "D")]
    for (mn, on), (d, t) in sorted(cart, key=lambda kv: kv[1][0])[:10]:
        Line("    %-22s %-30s %6.2f mm at t %.2f" % (mn, on, d, t))
    Line()

    # ---- ADDED (integrated, grafted from lane lib-compact): three checks the sweep above does not make
    zones = [o for o in refs if o.Role == "zone"]
    Line("Belts against every stack zone, their own column's included, gap >= %.1f (ADDED: a belt runs the whole"
         % P["MinGap"])
    Line("  height beside its own stack, so the travel sweep's own-zone exemption does not hold for it)")
    bz, nearB = [], (1e9, "")
    for tower in ("lib", "cart"):
        for t in (0.0, 0.5, 1.0):
            for m in Moving(g, tower, t)[0]:
                if m.Role != "belt":
                    continue
                for o in zones:
                    if not Near(m.Shape, o.Shape, P["MinGap"] + 5.0):
                        continue
                    dd = Gap(m.Shape, o.Shape)
                    if dd < nearB[0]:
                        nearB = (dd, "%s/%s at %s t %.1f" % (m.Name, o.Name, tower, t))
                    if dd < P["MinGap"] - 1e-6:
                        bz.append("%s/%s gap %.2f at %s t %.1f" % (m.Name, o.Name, dd, tower, t))
    bz = sorted(set(bz))
    bad += len(bz)
    Line("  %s; nearest %s" % ("ok" if not bz else "FAIL: " + "; ".join(bz),
                              ("%.2f mm (%s)" % nearB) if nearB[0] < 1e8 else "over 6 mm"))
    Line("Free runs against their own carriage's window, over the travel, gap >= %.1f (ADDED: the travel sweep never"
         % P["MinGap"])
    Line("  pairs a belt with its own carriage)")
    fr, frMin = [], {}
    for tower in ("lib", "cart"):
        for i in range(P["SweepSteps"] + 1):
            t = i / float(P["SweepSteps"])
            mv, pads = Moving(g, tower, t)
            for k in pads:
                car = [m for m in mv if m.Name == "Carriage" + k][0]
                dd = Gap(FreeRun(g, k), car.Shape)
                if k not in frMin or dd < frMin[k][0]:
                    frMin[k] = (dd, t)
                if dd < P["MinGap"] - 1e-6:
                    fr.append("free run %s / Carriage%s gap %.2f at t %.2f" % (k, k, dd, t))
    bad += len(fr)
    Line("  %s; tightest %s" % ("ok" if not fr else "FAIL: " + "; ".join(fr),
                               ", ".join("%s %.2f" % (k, frMin[k][0]) for k in "ABCD")))
    Line("Library stack zones inside the strip, x 1.0..%.1f, y 0..%.1f (ADDED: build_mask_stowage.py PileX keeps the"
         % (g["d"]["BoxLeft"] - 1.0, SL["StripD"]))
    Line("  ears 1 mm inside the strip's left edge; the same 1 mm holds here for the label ear's seatings: the 150")
    Line("  deg seating starts at x 1.09, so LabelAngle cannot grow past 270 without moving the columns)")
    for o in zones:
        if o.Group not in ("ZoneA", "ZoneB"):
            continue
        bb = o.Shape.BoundBox
        ok = bb.XMin >= 1.0 - 1e-6 and bb.XMax <= g["d"]["BoxLeft"] - 1.0 and bb.YMin >= 0 and bb.YMax <= SL["StripD"]
        bad += 0 if ok else 1
        Line("  %s x %.2f..%.2f, y %.2f..%.2f  %s" % (o.Name, bb.XMin, bb.XMax, bb.YMin, bb.YMax,
                                                     "ok" if ok else "OUTSIDE THE STRIP"))
    Line()

    # ---- head envelope
    Line("Head envelope (build_mask_stowage.py HeadEnvelope, grown by %.1f) against every part at the matching state"
         % P["HeadMargin"])
    poses = []
    for key in ("A", "B"):
        cx, cy = g["Col"][key]
        for n in (1, 2, 16, 31, 32):
            pad = P["S0"] - n * g["LibP"]
            pa = pad if key == "A" else g["LibK"] - pad
            t = (pa - g["LibPMin"]) / (g["LibPMax"] - g["LibPMin"])
            for dy in (0.0, SL["SlideY"], -SL["SlideY"]):
                poses.append(("%s pick, %d mask%s, slide %+.0f" % (key, n, "s" if n > 1 else "", dy), cx, cy + dy,
                              g["LibFace"], "lib", t))
    for n in (1, 2, 20, 39, 40):
        pc = P["CPick"] - n * g["CartP"]
        t = (pc - g["CPMin"]) / (g["CPMax"] - g["CPMin"])
        cx, cy = g["Col"]["C"]
        poses.append(("C pick, %d cartridge%s" % (n, "s" if n > 1 else ""), cx, cy, P["CPick"], "cart", t))
        dx, dy = g["Col"]["D"]
        poses.append(("D eject, C holding %d" % n, dx, dy, P["DEject"], "cart", t))
    d = g["d"]
    for key in ("T1", "T2"):
        for t in (0.0, 1.0):
            poses.append(("%s pick, cartridge tower t %.0f" % (key, t), d[key][0], d[key][1], d["TowerPick"], "cart", t))
    ya, yb = g["Col"]["A"][1], g["Col"]["B"][1]
    for k in range(9):
        y = ya + (yb - ya) * k / 8.0
        for t in (0.0, 1.0):
            poses.append(("transit A-B at y %.0f, library t %.0f" % (y, t), g["Col"]["A"][0], y, P["TransitLib"], "lib",
                          t))
    hits, nearest, layout = [], (1e9, ""), []
    # ADDED (lane lib-rearrange): the nearest library-tower part to the grown envelope, and to the real legs
    # (Gripper-B legs at r 65.5 hanging 0.7 under the ring face; the head above them as the coarse envelope, not grown)
    libNear, legNear = (1e9, ""), (1e9, "")

    def IsLib(o):
        return o.Mover in ("A", "B") or o.Group.startswith(("BracketA", "BracketB", "LoopA", "LoopB", "ShaftLib",
                                                            "WormStageLib"))

    for name, x, y, face, tower, t in poses:
        head, _ = Sto["HeadEnvelope"](x, y, face, P["HeadMargin"])
        legs = Cyl(65.5, face - 0.7, face + SL["HeadLowZ1"], x, y).fuse(
            Cyl(SL["HeadMidR"], face + SL["HeadLowZ1"], face + SL["HeadMidZ1"], x, y)).fuse(
            Cyl(SL["HeadTopR"], face + SL["HeadMidZ1"], max(SL["MastTop"], face + SL["HeadTopZ1"] + 1), x, y))
        mv, _ = Moving(g, tower, t)
        om, _ = Moving(g, "cart" if tower == "lib" else "lib", 0.5)
        own = name[0] if name[0] in "ABCD" else None
        for o in fixed + mv + om:
            if IsLib(o) and Near(head, o.Shape, 20.0):
                gl = Gap(head, o.Shape)
                if gl < libNear[0]:
                    libNear = (gl, "%s, %s" % (name, o.Name))
                gg = Gap(legs, o.Shape)
                if gg < legNear[0]:
                    legNear = (gg, "%s, %s" % (name, o.Name))
            if not Near(head, o.Shape, 5.0):
                continue
            if Overlap(head, o.Shape) > 1e-3:
                hits.append("%s: %s" % (name, o.Name))
            else:
                gd = Gap(head, o.Shape)
                if gd < nearest[0]:
                    nearest = (gd, "%s, %s" % (name, o.Name))
        for o in refs:
            if own and o.Group in ("Ref" + own, "Zone" + own):
                continue
            if Near(head, o.Shape, 0.0) and Overlap(head, o.Shape) > 1e-3:
                layout.append("%s: %s" % (name, o.Name))
    bad += len(hits) + len(layout)
    Line("  %d poses: library picks and places at S0 with the latch slide, C picks, D ejects, T1/T2, the A-B transit" %
         len(poses))
    Line("  this design's parts: %s" % ("ok, none inside the grown envelope" if not hits else
                                       "HIT: " + "; ".join(hits[:20])))
    if nearest[0] < 1e8:
        Line("  nearest part outside the grown envelope: %.2f mm (%s)" % nearest)
    Line("  library tower only: nearest part to the grown envelope %s; to the real legs %s" % (
        ("%.2f mm (%s)" % libNear) if libNear[0] < 1e8 else "over 20 mm",
        ("%.2f mm (%s)" % legNear) if legNear[0] < 1e8 else "over 20 mm"))
    Line("  the study's layout (other columns' cages, tubes and stack zones): %s" % (
        "ok" if not layout else "HIT (%d): " % len(layout) + "; ".join(sorted(set(layout)))))   # CHANGED: list all
    Line()

    # ---- bounds and the L-E ceiling
    Line("Bounds")
    xs, ys, zs = [], [], []
    allMv = []
    for tower in ("lib", "cart"):
        for t in (0.0, 1.0):
            allMv += Moving(g, tower, t)[0]
    for it in fixed + allMv:
        bb = it.Shape.BoundBox
        xs += [bb.XMin, bb.XMax]
        ys += [bb.YMin, bb.YMax]
        zs += [bb.ZMin, bb.ZMax]
    boxLeft = d["BoxLeft"]
    okB = min(xs) >= 0 and max(xs) <= boxLeft - 1.0 and min(ys) >= 0 and max(ys) <= SL["StripD"] and min(zs) >= -1e-6
    bad += 0 if okB else 1
    Line("  all parts x %.1f..%.1f (strip 0..%.1f less 1 mm to the box's screw heads), y %.1f..%.1f (0..%.1f), "
         "z %.1f..%.1f  %s" % (min(xs), max(xs), boxLeft, min(ys), max(ys), SL["StripD"], min(zs), max(zs),
                               "ok" if okB else "OUT OF BOUNDS"))
    legs = P["TransitLib"] - 1.5 - P["HeadMargin"]
    tallLib = max(it.Shape.BoundBox.ZMax for it in fixed if it.Group.startswith(("BracketA", "BracketB", "LoopA",
                                                                                  "LoopB")))
    Line("  tallest library-side fixed part z %.2f: L-E ceiling %.1f %s; A-B transit legs with margin %.1f" % (
        tallLib, P["LibCeiling"], "met" if tallLib <= P["LibCeiling"] + 1e-6 else "EXCEEDED, WARNING", legs))
    warn += 0 if tallLib <= P["LibCeiling"] + 1e-6 else 1
    Line()

    # ---- drive numbers
    Line("Worm stage")
    lam = math.atan(1.0 / P["WormPD"])     # module 1, single start: lead pi, so tan(lead angle) = 1 / pitch dia
    for mu in (P["MuDryLow"], 0.4):
        phi = math.atan(mu / math.cos(math.radians(20.0)))
        eta = math.tan(lam) / math.tan(lam + phi)
        tq = P["MotorTorqueNcm"] / 100.0 * 50 * eta
        marg = P["WheelTorqueNm"] / tq
        Line("  mu %.1f: forward efficiency %.3f; a stalled 17HS08 (%.0f N.cm) puts %.2f N.m on the wheel, against KHK's"
             " %.2f N.m (PG1-50R1, Lewis): margin %.2f%s" % (mu, eta, P["MotorTorqueNcm"], tq, P["WheelTorqueNm"], marg,
                                                              "" if marg >= 1.5 else ", WARNING"))
        warn += 0 if marg >= 1.5 else 1
    run = (P["NCart"] * 0.310 + 5.0 + 0.5) * g["R"] / 1000.0
    Line("  running: worst cartridge load %.1f N at r %.2f = %.2f N.m on the wheel shaft, margin %.1f" % (
        P["NCart"] * 0.310 + 5.5, g["R"], run, P["WheelTorqueNm"] / run))
    Line("  centre distance %.1f modelled (KHK mounting distance); print the housing at %.1f for backlash" % (
        P["CentreDist"], P["CentreDist"] + 0.1))
    aLip, aBody, b = BiasExtents(g)
    steel = [it for it in Carriage(g, "A", g["LibPMin"]) if it.Role == "steel"]
    vol = sum(it.Shape.Volume for it in steel)
    sbb = steel[0].Shape.BoundBox
    Line("  library bias: %.0f g of steel in one stepped plate on carriage A's front face (study: 612 g, 6 N); "
         "%.1f x %.1f x %.1f overall, lowest point z %.1f" % (vol * P["SteelDensity"], sbb.XLength, sbb.YLength,
                                                             sbb.ZLength, sbb.ZMin))
    Line()
    Line("Not modelled")
    Line("  belt teeth, the toothed belt clamp (slots, plate, 2 x M3), set screws, the housing's joining screws and")
    Line("  its fixing to the table, the feet's and blocks' fixing, any cover over the pulley nips and the worm mesh,")
    Line("  the tubes' and cages' supports, the beams B1/B2 and the library beams, the masks and cartridges")
    Line("  bearing retention and the worm's thrust path are drawn only as bores in the housing")
    return out, bad, warn


# ---------------------------------------------------------------------------------------------------- output
def Main():
    g = Layout()
    fixed, refs, brackets, notch = Fixed(g)
    checks, bad, warn = Checks(g, fixed, refs, brackets, notch)
    print("\n".join(checks))
    outDir = os.path.join(Root, "CAD", "Belt Elevator")
    os.makedirs(outDir, exist_ok=True)
    base = os.path.join(outDir, "BeltElevator_" + Version)
    open(base + "_Checks.txt", "w", encoding="ascii", newline="\n").write(
        "\n".join(checks) + "\n\n%d check(s) failed, %d warning(s)\n" % (bad, warn))

    # snapshot: library columns level (16 and 16), C full and D empty
    libT = ((P["S0"] - 16 * g["LibP"]) - g["LibPMin"]) / (g["LibPMax"] - g["LibPMin"])
    moving = Moving(g, "lib", libT)[0] + Moving(g, "cart", 0.0)[0]
    doc = FreeCAD.newDocument("BeltElevator")
    groups, objs = {}, []

    def Add(it):
        if it.Group not in groups:
            groups[it.Group] = doc.addObject("App::DocumentObjectGroup", it.Group)
        o = doc.addObject("Part::Feature", it.Name)
        o.Shape = it.Shape
        groups[it.Group].addObject(o)
        if FreeCAD.GuiUp:
            o.ViewObject.ShapeColor = tuple(c / 255.0 for c in it.Color)
        if it.Role != "zone":
            objs.append(o)
        return o

    for it in fixed + moving + refs:
        Add(it)
    head, _ = Sto["HeadEnvelope"](g["Col"]["A"][0], g["Col"]["A"][1], g["LibFace"], 0.0)
    h = doc.addObject("Part::Feature", "HeadEnvelopeAtA")
    h.Shape = head
    doc.recompute()
    doc.saveAs(base + ".FCStd")
    import Import
    Import.export(objs, base + "_Assembly.step")
    # one STEP per printed or cut part, at the origin
    done = set()
    for it in fixed + moving:
        if it.Role not in ("printed", "steel") or not it.PartKey or it.PartKey in done:
            continue
        done.add(it.PartKey)
        s = it.Shape.copy()
        bb = s.BoundBox
        s.translate(V(-bb.XMin, -bb.YMin, -bb.ZMin))
        s.exportStep(base + "-" + it.PartKey + ".step")
    FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed, %d warning(s); wrote %s" % (bad, warn, outDir))


Main()
