# Builds a layout sketch of the mask stowage: a device-agnostic library of bare masks that
# the head searches layer by layer, with the cartridges kept apart until a prep tower.
#   L1, L2  library piles of bare masks, in no particular order (two piles, so a buried mask
#           can be dug out by moving the masks above it onto the other pile)
#   T1, T2  prep towers on the control box lid: a mask is armed with a cartridge here, stamped
#           from here, stripped of its spent cartridge here, and waits here while the next mask
#           is found, so it goes back only after the search
#   C       fresh cartridges, a column whose top the I axis (formerly the filter feeder) holds at
#           one pick height
#   D       spent cartridges, a bin the head ejects into from above
# The masks and cartridges are the lobe hold variant (issue 230), taken from
# build_filter_cartridge.py so the sketch follows any change made there. The script also
# simulates the search (moves per layer) for a few device recipes.
#
# Run with FreeCAD's console:  freecadcmd tools/build_mask_stowage.py
# Writes CAD/Mask Stowage/MaskStowage.FCStd, MaskStowage_Sketch.png and MaskStowage_Checks.txt.
#
# Frame: x = mm from the strip's left edge (machine +X to the right), y = mm from the inner
# front wall (toward the back), z = mm above the table. Every value below is a layout proposal
# unless a comment names its source. The head is a coarse envelope, not a model of Gripper-B.

import math
import os
import random
import statistics

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)

# ---- load the cartridge generator's parameters and builders without running its Main()
Src = open(os.path.join(Here, "build_filter_cartridge.py"), encoding="utf-8").read()
Cut = Src.rindex("\nMain()")
Gen = {"__file__": os.path.join(Here, "build_filter_cartridge.py")}
exec(compile(Src[:Cut], "build_filter_cartridge.py", "exec"), Gen)
CartP, Build = Gen["P"], Gen["Build"]
MaskP = dict(CartP)
MaskP.update(Gen["LobeVariant"])     # the lobe hold mask as build_filter_cartridge.py exports it

IN = 25.4

L = dict(
    # Strip (owner, 2026-11-16): the control box and feeder area is about 24 in in X by
    # 18 1/16 in front to back; the 13.5 in control box goes to the right, leaving 10.5 in.
    StripW=10.5 * IN,
    StripD=(18 + 1 / 16) * IN,
    BoxW=13.5 * IN,
    BoxDepth=457.0,         # tools/draw_wiring.py BoxD
    BoxH=279.4,             # tools/draw_wiring.py BoxH (11 in): the 2020 frame
    PanelT=3.175,           # tools/draw_wiring.py PanelT: acrylic side and top panels outside the frame
    HeadM5H=5.0,            # tools/draw_wiring.py HeadM5H: panel screw heads stand this far proud
    # ADR-0015: the box comes out by lifting 37.95 and sliding forward under the front middle member,
    # whose underside is at z 335. Anything standing on the lid must come off first if it would not pass.
    BoxLift=37.95,
    MiddleMemberZ=335.0,
    # Head reach in Y (owner, 2026-11-16): at the rearmost Y the head axis is 6.5 in from the
    # inner back wall; Y travel 200 mm (Configuration.h Y_MAX_POS; claude.md: 150 mm unless X >= 350).
    # The strip is believed to sit at machine X >= 350 (owner, 2026-11-19, not measured).
    RearAxisFromBack=6.5 * IN,
    ReachY=200.0,
    # Head reach in X: the head reaches partly over the control box (owner, 2026-11-19). How far
    # is not measured; this assumes the strip's left edge at machine X 350 and X travel to 770
    # (Configuration.h X_MAX_POS), so the head axis reaches x = 420 here. Measure it.
    HeadXMax=770.0 - 350.0,
    # Head Z range (owner, 2026-11-16): Gripper-B ring face 396.7 above the table at Z0, about
    # 10 in of mechanical Z travel; the firmware's Z_MAX_POS 186 is legacy (#222). The owner expects
    # the travel to reach the low picks (2026-11-19); the firmware limit still has to move.
    RingFaceAtZ0=396.7,
    ZTravel=10 * IN,
    ZMaxLegacy=186.0,
    # Release slide of a mask or combo off what is under it (latch test, issue 226): 10 mm in +Y.
    # Which way machine +Y points in this frame is not known, so both directions are checked.
    SlideY=10.0,
    # Plan positions. Library piles in the strip's left column, one row near each end of the reach
    # band, kept SlideY inside it; C and D in the right column, C in from the back row so that its
    # tube stays clear of the head at L1 after a slide, D on the front edge of the reach band (it
    # takes no slide); the prep towers on the control box lid.
    # At L1 and L2 the head overhangs the strip's left edge; that is acceptable (owner, 2026-11-19).
    PileX=67.5,             # ears 1 mm inside the strip's left edge
    ColX=196.0,             # C and D clear of the box's left panel and its screw heads (x 258.5)
    ColYFromBackRow=-70.0,
    SpentX=196.0,
    TowerX=345.0,
    # Library: every mask of the machine, bare, in two piles. A bare mask rests on the balls and ear
    # bosses of the one below (BarePitch, taken from the mask model). Either pile may have to take the
    # whole library during a search, so each is sized for LibMax.
    LibMax=32,
    LibStandTop=180.0,      # lowest pick (one mask) inside the mechanical Z travel; full pile below C's pick
    LibSeatOD=120.0,        # plain printed seat, no steel ring: the bottom mask has nothing to latch to
    SeatT=8.0,
    PostW=20.0,
    FootW=110.0,
    FootT=6.0,
    # Prep towers: a printed seat with a G90 steel ring flush in a recess in its top (as the latch
    # test's pile seat 8-05) on a short post standing on the control box lid. A tower holds one mask,
    # bare or armed with a cartridge.
    TowerStandH=20.0,
    TowerSeatOD=120.0,
    # C column: bare cartridges stacked plate on body, top plate held at ColPick by the I axis.
    # The I axis, formerly the filter feeder, is reused as C's elevator (owner, 2026-11-19):
    # 343 mm travel, 320 steps/mm on a 5 mm lead screw, homes to I_MAX, and A- raises the stack
    # (Configuration.h; the Stamp block's feederJog). The rods, screw and motor drawn here are
    # placeholders until the feeder's hardware is measured.
    ColPick=350.0,          # above a full L1, which the head at C overlaps in plan
    ColCap=40,              # about 31 layers per device (Run Log preset) plus spares
    ColClear=1.5,           # radial, plate OD 109 to the tube bore
    ColWall=2.0,
    ColRimBelowTop=1.0,     # tube rim this far below the top cartridge's bottom: the top one stands free
    ColSlotW=24.0,          # slot in the tube wall for the elevator arm, facing +Y
    CarriageT=6.0,
    RodOffset=95.0,         # elevator rods and screw behind C (+Y): outside the head envelope at C
    RodSpacing=60.0,
    RodD=8.0,
    ScrewD=8.0,
    RodTopAbovePick=15.0,
    ITravel=343.0,
    IStepsPerMm=320.0,
    # D: spent bin. The head's envelope at L2 overlaps D in plan, so the rim stays below L2's lowest
    # pick less the legs and the head margin; the head check enforces it. The head ejects from above
    # C's top cartridge, which its envelope at D overlaps in plan, and so above a full L2 too.
    SpentRim=180.0,
    SpentClear=3.5,         # radial, plate OD 109 to the bore. The bore is wider than a cartridge's section
                            # diagonal, so a dropped cartridge can land tilted: the flat count is an upper bound
    SpentWall=2.5,
    SpentFloor=4.0,
    EjectFace=355.0,
    DeviceLayers=32,        # D must take one spent cartridge per layer of the largest device
    # Head envelope around the ring face H (coarse, conservative; from the Gripper-B v33
    # preview: legs at r 65.5 hang 0.7 below the face, the carriage is r 81 wide above it; the
    # head's ball pairs hang 1.5 below the face, build_filter_cartridge.py BallProtrusion).
    HeadLowR=77.5,
    HeadLowZ0=-1.5,
    HeadLowZ1=19.8,
    HeadMidR=81.0,
    HeadMidZ1=61.3,
    HeadTopR=50.0,
    HeadTopZ1=111.3,
    HeadMastR=50.0,         # the Z carriage above the head, carried up to the top of the frame
    MastTop=560.0,
    # Margins
    PlanMargin=1.0,         # between stack footprints
    HeadMargin=2.0,         # the head envelope is grown by this, radially and downward, for the checks
    TransitMargin=5.0,      # above the highest fixture or stack, plus the legs and a carried combo
    # Search planner (simulation only)
    MoveSeconds=6.5,
    HandlingMoves=3,        # per layer besides the pile moves: mask to its tower, cartridge from C, spent cartridge to D        # one mask moved pile to pile: the November sketch's estimate, NOT measured
    SpinCureSeconds=530.0,  # Run Log preset CN9018: 50 s spin hold + 480 s cure; ramps and dispense not counted
    PlanRuns=300,
    PlanSeed=1,
    ShownL1=10,
    ShownL2=6,
)


def Cyl(r, z0, z1, x, y):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def Tube(ri, ro, z0, z1, x, y):
    return Cyl(ro, z0, z1, x, y).cut(Cyl(ri, z0 - 1, z1 + 1, x, y))


def Box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


class Item:
    """One sketch primitive: a FreeCAD solid plus what the 2D views need to draw it."""

    def __init__(self, name, group, shape, kind, geo, color, alpha=0.55, ls="-"):
        self.Name, self.Group, self.Shape = name, group, shape
        self.Kind, self.Geo, self.Color, self.Alpha, self.Ls = kind, geo, color, alpha, ls


def CylItem(name, group, x, y, ri, ro, z0, z1, color, alpha=0.55, ls="-"):
    shape = Tube(ri, ro, z0, z1, x, y) if ri > 0 else Cyl(ro, z0, z1, x, y)
    return Item(name, group, shape, "cyl", (x, y, ri, ro, z0, z1), color, alpha, ls)


def BoxItem(name, group, x0, x1, y0, y1, z0, z1, color, alpha=0.55):
    return Item(name, group, Box(x0, x1, y0, y1, z0, z1), "box", (x0, x1, y0, y1, z0, z1), color, alpha)


# Paul Tol bright
TolBlue, TolCyan, TolGreen, TolYellow = "#4477AA", "#66CCEE", "#228833", "#CCBB44"
TolRed, TolPurple, TolGrey = "#EE6677", "#AA3377", "#BBBBBB"
Dark = "#222222"

StackKeys = ("L1", "L2", "C", "D", "T1", "T2")


def Layout(c, bare):
    """Derived positions and heights from L, the cartridge levels c and the bare mask height."""
    d = {}
    d["ReachFront"] = L["StripD"] - L["RearAxisFromBack"] - L["ReachY"]
    d["ReachBack"] = L["StripD"] - L["RearAxisFromBack"]
    d["BackY"] = d["ReachBack"] - L["SlideY"]
    d["FrontY"] = d["ReachFront"] + L["SlideY"]
    d["L1"] = (L["PileX"], d["BackY"])
    d["L2"] = (L["PileX"], d["FrontY"])
    d["C"] = (L["ColX"], d["BackY"] + L["ColYFromBackRow"])
    d["D"] = (L["SpentX"], d["ReachFront"])
    d["T1"] = (L["TowerX"], d["BackY"])
    d["T2"] = (L["TowerX"], d["FrontY"])
    d["ComboPitch"] = c["RingFace"]                 # mask bottom to plate face
    d["BarePitch"] = bare                           # mask bottom to the top of its balls and ear bosses
    d["CartPitch"] = c["StackPitch"]                # cartridge bottom to plate face
    # the head couples at the ring face, ComboPitch above the mask bottom, bare or armed
    d["LibFirst"] = L["LibStandTop"] + d["ComboPitch"]
    d["LibFullPick"] = L["LibStandTop"] + (L["LibMax"] - 1) * d["BarePitch"] + d["ComboPitch"]
    d["LibFull"] = L["LibStandTop"] + L["LibMax"] * d["BarePitch"]          # top of a full pile
    d["BoxTop"] = L["BoxH"] + L["PanelT"]
    d["BoxTopHeads"] = d["BoxTop"] + L["HeadM5H"]
    d["BoxLeft"] = L["StripW"] - L["PanelT"] - L["HeadM5H"]
    d["TowerTop"] = d["BoxTop"] + L["TowerStandH"]
    d["TowerPick"] = d["TowerTop"] + d["ComboPitch"]
    d["TowerCombo"] = d["TowerTop"] + d["ComboPitch"]
    d["ColR"] = CartP["PlateOD"] / 2 + L["ColClear"] + L["ColWall"]
    d["ColBore"] = CartP["PlateOD"] / 2 + L["ColClear"]
    d["ColRim"] = L["ColPick"] - d["CartPitch"] - L["ColRimBelowTop"]
    d["ColLow"] = L["ColPick"] - L["ColCap"] * d["CartPitch"]   # carriage top when C is full
    d["SpentBore"] = CartP["PlateOD"] / 2 + L["SpentClear"]
    d["SpentR"] = d["SpentBore"] + L["SpentWall"]
    d["SpentFlatCap"] = int((L["SpentRim"] - L["SpentFloor"]) / d["CartPitch"])
    d["FaceMin"] = L["RingFaceAtZ0"] - L["ZTravel"]
    d["FaceMinLegacy"] = L["RingFaceAtZ0"] - L["ZMaxLegacy"]
    d["Radius"] = {"L1": CartP["LobeEarOuterR"], "L2": CartP["LobeEarOuterR"], "C": d["ColR"], "D": d["SpentR"],
                   "T1": CartP["LobeEarOuterR"], "T2": CartP["LobeEarOuterR"]}
    return d


def Carriage(d, top):
    """The elevator carriage and its arm with the carriage top at the given height."""
    x, y = d["C"]
    ry = y + L["RodOffset"]
    return [CylItem("ElevatorCarriage", "ColumnC", x, y, 0, d["ColBore"] - 0.5, top - L["CarriageT"], top, TolBlue),
            BoxItem("ElevatorArm", "ColumnC", x - 8, x + 8, y, ry, top - L["CarriageT"], top, TolBlue)]


def Stand(items, label, group, x, y, top, seatOD, ring, base=0.0):
    """A seat on a 2020 post with a foot; with ring, a steel ring flush in a recess in the seat top."""
    items.append(BoxItem(label + "Foot", group, x - L["FootW"] / 2, x + L["FootW"] / 2, y - L["FootW"] / 2,
                         y + L["FootW"] / 2, base, base + L["FootT"], TolGrey))
    items.append(BoxItem(label + "Post", group, x - L["PostW"] / 2, x + L["PostW"] / 2, y - L["PostW"] / 2,
                         y + L["PostW"] / 2, base + L["FootT"], top - L["SeatT"], TolGrey))
    seat = Cyl(seatOD / 2, top - L["SeatT"], top, x, y)
    if ring:
        seat = seat.cut(Tube(CartP["PlateID"] / 2, CartP["PlateOD"] / 2, top - CartP["PlateT"], top + 1, x, y))
    items.append(Item(label + "Seat", group, seat, "cyl", (x, y, 0, seatOD / 2, top - L["SeatT"], top), TolGreen))
    if ring:
        items.append(CylItem(label + "SeatRing", group, x, y, CartP["PlateID"] / 2, CartP["PlateOD"] / 2,
                             top - CartP["PlateT"], top, Dark, 0.8))


def Fixtures(d):
    """Stands, towers, the C column with its elevator, the D bin and the control box."""
    items = []
    for key in ("L1", "L2"):
        Stand(items, key, "Stand" + key, d[key][0], d[key][1], L["LibStandTop"], L["LibSeatOD"], False)
    for key in ("T1", "T2"):
        Stand(items, key, "Stand" + key, d[key][0], d[key][1], d["TowerTop"], L["TowerSeatOD"], True, base=d["BoxTop"])
    x, y = d["C"]
    tubeLow = d["ColLow"] - L["CarriageT"] - 10
    tube = Tube(d["ColBore"], d["ColR"], tubeLow, d["ColRim"], x, y)
    # the arm slot runs the tube's full height: the carriage rises to within one pitch of the pick
    tube = tube.cut(Box(x - L["ColSlotW"] / 2, x + L["ColSlotW"] / 2, y, y + d["ColR"] + 1, tubeLow - 1,
                        d["ColRim"] + 1))
    items.append(Item("ColumnTube", "ColumnC", tube, "cyl", (x, y, d["ColBore"], d["ColR"], tubeLow, d["ColRim"]),
                      TolGrey, 0.35))
    # the carriage is drawn at its lowest position (C full); it rises one pitch per pick
    for it in Carriage(d, d["ColLow"]):
        items.append(it)
    ry = y + L["RodOffset"]
    rodTop = L["ColPick"] + L["RodTopAbovePick"]
    for k, dx in enumerate((-L["RodSpacing"] / 2, L["RodSpacing"] / 2)):
        items.append(CylItem("ElevatorRod%d" % (k + 1), "ColumnC", x + dx, ry, 0, L["RodD"] / 2, 0, rodTop, TolGrey,
                             0.8))
    items.append(CylItem("ElevatorScrew", "ColumnC", x, ry, 0, L["ScrewD"] / 2, 0, rodTop, TolYellow, 0.8))
    items.append(BoxItem("ElevatorMotor", "ColumnC", x - 21, x + 21, ry - 21, ry + 21, 0, 48, TolGrey, 0.8))
    # control box envelope (tools/draw_wiring.py: BoxD, BoxW, BoxH = 457.0, 342.9, 279.4), centred front to back,
    # with its side panels and their screw heads; its top is the top panel, on which the towers stand between
    # the panel's screws (their heads, 5 proud, are not drawn)
    y0 = (L["StripD"] - L["BoxDepth"]) / 2
    o = L["PanelT"] + L["HeadM5H"]
    items.append(BoxItem("ControlBox", "ControlBox", d["BoxLeft"], L["StripW"] + L["BoxW"] + o, y0 - o,
                         y0 + L["BoxDepth"] + o, 0, d["BoxTop"], TolGrey, 0.25))
    x, y = d["D"]
    items.append(CylItem("SpentBin", "BinD", x, y, d["SpentBore"], d["SpentR"], L["SpentFloor"], L["SpentRim"],
                         TolGrey, 0.35))
    items.append(CylItem("SpentBinFloor", "BinD", x, y, 0, d["SpentR"], 0, L["SpentFloor"], TolGrey, 0.35))
    return items


MaskKeys = ("L1", "L2", "T1", "T2")


def LabelEarBoxes(x, y):
    """Plan bounding boxes (x0, x1, y0, y1) of the label ear of a mask centred at (x, y), one per way the mask
    can seat: the coupling is three-fold symmetric, so a mask loaded 120 deg off seats as well, and a pile must
    have room for it until the tower camera catches it. Each ear rectangle is rotated and boxed, so a box is exact
    at a multiple of 90 deg and conservative otherwise. The mask's orientation in this frame is the one Draw()
    uses for the ear magnets. Empty without a label ear."""
    if not (MaskP["MaskHold"] == "lobe" and MaskP["LabelEar"]):
        return []
    e = Gen["LabelEarDims"](MaskP)
    boxes = []
    for k in range(3):
        a = math.radians(MaskP["LabelAngle"] + 120.0 * k)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(x + r * ca - w * sa, y + r * sa + w * ca) for r in (e["EarR0"], e["EarR1"])
               for w in (-e["Width"] / 2, e["Width"] / 2)]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        boxes.append((min(xs), max(xs), min(ys), max(ys)))
    return boxes


def Footprint(d, k):
    """A stack's plan footprint as ('cyl', (x, y, r)) and ('box', (x0, x1, y0, y1)) pieces."""
    x, y = d[k]
    pieces = [("cyl", (x, y, d["Radius"][k]))]
    for box in (LabelEarBoxes(x, y) if k in MaskKeys else []):
        pieces.append(("box", box))
    return pieces


def PieceGap(a, b):
    """Plan distance between two footprint pieces; negative = overlap (exact for circles, -1 for boxes)."""
    (ka, ga), (kb, gb) = a, b
    if ka == "cyl" and kb == "cyl":
        return math.hypot(ga[0] - gb[0], ga[1] - gb[1]) - ga[2] - gb[2]
    if ka == "box" and kb == "box":
        dx = max(ga[0] - gb[1], gb[0] - ga[1], 0.0)
        dy = max(ga[2] - gb[3], gb[2] - ga[3], 0.0)
        return math.hypot(dx, dy) if dx or dy else -1.0
    (cx, cy, r), (x0, x1, y0, y1) = (ga, gb) if ka == "cyl" else (gb, ga)
    return math.hypot(max(x0 - cx, 0, cx - x1), max(y0 - cy, 0, cy - y1)) - r


def StackEnvelopes(d):
    """Worst-case stack contents for the clearance checks: each library pile holding the whole library,
    each tower holding an armed mask, the column full."""
    env = []
    for key in ("L1", "L2"):
        x, y = d[key]
        env.append(CylItem("%sFull" % key, "Stack" + key, x, y, 0, CartP["LobeEarOuterR"], L["LibStandTop"],
                           d["LibFull"], TolCyan, 0.12, "--"))
        for n, box in enumerate(LabelEarBoxes(x, y)):
            env.append(BoxItem("%sFullLabelEars%d" % (key, n + 1), "Stack" + key, *box, L["LibStandTop"], d["LibFull"],
                               TolCyan, 0.12))
    for key in ("T1", "T2"):
        x, y = d[key]
        env.append(CylItem("%sArmed" % key, "Stack" + key, x, y, 0, CartP["LobeEarOuterR"], d["TowerTop"],
                           d["TowerCombo"], TolCyan, 0.12, "--"))
        for n, box in enumerate(LabelEarBoxes(x, y)):
            env.append(BoxItem("%sArmedLabelEar%d" % (key, n + 1), "Stack" + key, *box, d["TowerTop"], d["TowerCombo"],
                               TolCyan, 0.12))
    x, y = d["C"]
    env.append(CylItem("ColumnFull", "StackC", x, y, 0, CartP["PlateOD"] / 2, d["ColLow"], L["ColPick"], TolPurple,
                       0.12, "--"))
    return env


def HeadEnvelope(x, y, face, margin=0.0):
    parts = [(L["HeadLowR"] + margin, face + L["HeadLowZ0"] - margin, face + L["HeadLowZ1"]),
             (L["HeadMidR"] + margin, face + L["HeadLowZ1"], face + L["HeadMidZ1"]),
             (L["HeadTopR"] + margin, face + L["HeadMidZ1"], face + L["HeadTopZ1"]),
             (L["HeadMastR"] + margin, face + L["HeadTopZ1"], max(L["MastTop"], face + L["HeadTopZ1"] + 1))]
    shape = None
    for r, z0, z1 in parts:
        s = Cyl(r, z0, z1, x, y)
        shape = s if shape is None else shape.fuse(s)
    return shape, parts


def PickPoses(d):
    """Every pose at which the head comes down onto a stack, with the stack it works on."""
    poses = []
    for key in ("L1", "L2"):
        x, y = d[key]
        for n, face in ((1, d["LibFirst"]), (L["LibMax"], d["LibFullPick"])):
            for dy in (0.0, L["SlideY"], -L["SlideY"]):
                poses.append(("%s, %d mask%s, slide %+.0f" % (key, n, "s" if n > 1 else "", dy), key, x, y + dy, face))
    for key in ("T1", "T2"):
        x, y = d[key]
        for dy in (0.0, L["SlideY"], -L["SlideY"]):
            poses.append(("%s, mask, slide %+.0f" % (key, dy), key, x, y + dy, d["TowerPick"]))
    x, y = d["C"]
    poses.append(("C, pick top cartridge", "C", x, y, L["ColPick"]))
    x, y = d["D"]
    poses.append(("D, eject spent cartridge", "D", x, y, L["EjectFace"]))
    return poses


def PlanGap(x, y, r, item):
    """Plan distance from a circle (x, y, r) to an item's footprint; negative = overlap."""
    if item.Kind == "cyl":
        cx, cy, ri, ro = item.Geo[:4]
        return math.hypot(x - cx, y - cy) - r - ro
    x0, x1, y0, y1 = item.Geo[:4]
    dx = max(x0 - x, 0, x - x1)
    dy = max(y0 - y, 0, y - y1)
    return math.hypot(dx, dy) - r


# ---------------------------------------------------------------- search planner
def NextUse(seq, i, m):
    for j in range(i, len(seq)):
        if seq[j] == m:
            return j
    return 10 ** 6


def PileScore(pile, seq, i):
    """How late the masks near a pile's top are needed: masks go onto the pile whose top is needed last."""
    return min([NextUse(seq, i, m) for m in pile[-3:]] or [10 ** 6])


def PlanDevice(nLib, seq, rng):
    """Moves per layer to find each mask of seq in two library piles of nLib masks in random order.
    The used mask waits on a prep tower and goes back only after the next one is found. Counts pile
    moves only: digging and putting the used mask back."""
    lib = list(range(nLib))
    rng.shuffle(lib)
    piles = [lib[0::2], lib[1::2]]
    held, moves, tallest = None, [], max(len(p) for p in piles)
    for i, x in enumerate(seq):
        m = 0
        if held == x:
            moves.append(0)
            continue
        a = 0 if x in piles[0] else 1
        b = 1 - a
        while piles[a][-1] != x:
            piles[b].append(piles[a].pop())
            m += 1
            tallest = max(tallest, len(piles[b]))
        piles[a].pop()
        if held is not None:
            k = max((0, 1), key=lambda j: PileScore(piles[j], seq, i + 1))
            piles[k].append(held)
            m += 1
            tallest = max(tallest, len(piles[k]))
        held = x
        moves.append(m)
    return moves, tallest


def Planner():
    rng = random.Random(L["PlanSeed"])
    n, layers = L["LibMax"], L["DeviceLayers"]
    recipes = (("2 masks, alternating (P, N)", lambda: [0, 1] * (layers // 2)),
               ("16 masks, each used twice", lambda: list(range(16)) * (layers // 16)),
               ("any mask, random", lambda: [rng.randrange(n) for _ in range(layers)]))
    rows, tallest = [], 0
    for name, gen in recipes:
        allMoves = []
        for _ in range(L["PlanRuns"]):
            mv, t = PlanDevice(n, gen(), rng)
            allMoves += mv
            tallest = max(tallest, t)
        allMoves.sort()
        rows.append((name, statistics.mean(allMoves), allMoves[int(0.95 * len(allMoves))], allMoves[-1]))
    return rows, tallest


def Checks(d, fixtures, envelopes):
    out, bad, warn = [], 0, 0
    obstacles = fixtures + envelopes
    carriageTop = Carriage(d, L["ColPick"] - d["CartPitch"])     # the carriage and arm at their highest
    for it in carriageTop:
        it.Name += "AtTop"
    out.append("Head clearance at every pick pose (envelope grown by %.0f mm vs everything not on the worked "
               "stack; gap = nominal envelope to the nearest level item)" % L["HeadMargin"])
    for label, key, x, y, face in PickPoses(d):
        head, _ = HeadEnvelope(x, y, face, L["HeadMargin"])
        _, parts = HeadEnvelope(x, y, face)
        worst, worstName, hits = 1e9, "", []
        for it in obstacles + carriageTop:
            # the worked stack's own contents and stand are the head's to touch; the coupling is
            # checked by build_filter_cartridge.py. C's tube and rods and D's rim still count.
            if it.Group in ("Stack" + key, "Stand" + key):
                continue
            if key == "C" and it.Name.startswith(("ElevatorCarriage", "ElevatorArm")):
                continue
            if head.common(it.Shape).Volume > 1e-3:
                hits.append(it.Name)
            z0, z1 = it.Geo[4], it.Geo[5]
            for r, hz0, hz1 in parts:
                if hz1 > z0 and hz0 < z1:
                    g = PlanGap(x, y, r, it)
                    if g < worst:
                        worst, worstName = g, it.Name
        ok = not hits
        bad += 0 if ok else 1
        faceOk = d["FaceMin"] <= face <= L["RingFaceAtZ0"]
        bad += 0 if faceOk else 1
        reachOk = x <= L["HeadXMax"] and d["ReachFront"] - 1e-6 <= y <= d["ReachBack"] + 1e-6
        bad += 0 if reachOk else 1
        gapText = "min plan gap %6.1f mm (%s)" % (worst if worst < 1e8 else float("nan"), worstName or "-")
        out.append("  %-26s face %6.1f  %s  %s%s%s" % (
            label, face, "ok  " if ok else "HIT ", gapText if ok else "hits: " + ", ".join(sorted(set(hits))),
            "" if faceOk else "  OUT OF Z RANGE", "" if reachOk else "  OUT OF REACH"))
    out.append("")
    out.append("Elevator sweep: carriage and arm against the tube and both library piles, from full to the last cartridge")
    tube = [it for it in fixtures if it.Name == "ColumnTube"][0]
    others = [tube] + [it for it in envelopes if it.Group in ("StackL1", "StackL2")]
    worstVol, worstN = 0.0, 0
    for n in range(1, L["ColCap"] + 1):
        for it in Carriage(d, L["ColPick"] - n * d["CartPitch"]):
            for o in others:
                v = it.Shape.common(o.Shape).Volume
                if v > worstVol:
                    worstVol, worstN = v, n
    bad += 0 if worstVol <= 1e-3 else 1
    out.append("  %s" % ("ok, no overlap at any of %d positions" % L["ColCap"] if worstVol <= 1e-3 else
                         "HIT: %.0f mm3 with %d cartridge(s) left" % (worstVol, worstN)))
    out.append("")
    out.append("Fixtures against each other (every pair from different groups, stacks at their worst case)")
    clash = []
    for i, a in enumerate(obstacles):
        for b in obstacles[i + 1:]:
            if a.Group == b.Group or {a.Group, b.Group} == {"ColumnC", "StackC"}:
                continue
            if a.Shape.common(b.Shape).Volume > 1e-3:
                clash.append("%s/%s" % (a.Name, b.Name))
    bad += len(clash)
    out.append("  %s" % ("ok, no overlaps" if not clash else "OVERLAP: " + ", ".join(clash)))
    out.append("")
    out.append("Transit between stacks")
    tops = [(it.Geo[5], it.Name) for it in obstacles]
    top, topName = max(tops)
    transit = top - L["HeadLowZ0"] + d["ComboPitch"] + L["TransitMargin"]
    tOk = transit <= L["RingFaceAtZ0"]
    bad += 0 if tOk else 1
    out.append("  ring face at least %.1f for straight moves between stacks: highest item %s at %.1f, legs %.1f below "
               "the face, a carried combo %.3f, margin %.0f%s" % (
                   transit, topName, top, -L["HeadLowZ0"], d["ComboPitch"], L["TransitMargin"],
                   "" if tOk else "  ABOVE Z0"))
    out.append("")
    out.append("Footprints (plan)")
    y0 = (L["StripD"] - L["BoxDepth"]) / 2
    for k in StackKeys:
        x, y = d[k]
        r = d["Radius"][k]
        pieces = Footprint(d, k)
        # extent of the whole footprint, the label ear included
        xa = min(g[0] - g[2] if kind == "cyl" else g[0] for kind, g in pieces)
        xb = max(g[0] + g[2] if kind == "cyl" else g[1] for kind, g in pieces)
        ya = min(g[1] - g[2] if kind == "cyl" else g[2] for kind, g in pieces)
        yb = max(g[1] + g[2] if kind == "cyl" else g[3] for kind, g in pieces)
        if k in ("T1", "T2"):
            where = (xa >= L["StripW"] and xb <= L["StripW"] + L["BoxW"] and ya >= y0 and yb <= y0 + L["BoxDepth"])
            whereText = "on the box lid" if where else "OFF THE BOX LID"
        else:
            where = (xa >= -1e-6 and xb <= d["BoxLeft"] - L["PlanMargin"] and ya >= 0 and yb <= L["StripD"])
            whereText = "inside the strip, clear of the box" if where else "OUTSIDE THE STRIP OR INTO THE BOX"
        inReach = d["ReachFront"] <= y <= d["ReachBack"] and x <= L["HeadXMax"]
        bad += 0 if (where and inReach) else 1
        out.append("  %-2s at (%.1f, %.1f) r %.1f%s: x %.1f..%.1f, y %.1f..%.1f  %s, %s" % (
            k, x, y, r, " + label ear (3 seatings)" if len(pieces) > 1 else "", xa, xb, ya, yb, whereText,
            "centre in reach" if inReach else "CENTRE OUT OF REACH"))
    for i, a in enumerate(StackKeys):
        for b in StackKeys[i + 1:]:
            g = min(PieceGap(pa, pb) for pa in Footprint(d, a) for pb in Footprint(d, b))
            bad += 0 if g >= L["PlanMargin"] else 1
            if g < 60 or g < L["PlanMargin"]:
                out.append("  %s to %s: %.1f mm apart in plan%s" % (a, b, g, "" if g >= L["PlanMargin"] else "  OVERLAP"))
    out.append("")
    out.append("Heights")
    out.append("  combo pitch %.3f, bare mask pitch %.3f, cartridge pitch %.3f" % (
        d["ComboPitch"], d["BarePitch"], d["CartPitch"]))
    out.append("  library pick (ring face): 1 mask %.1f, %d masks %.1f; full pile top %.1f (each pile sized for the "
               "whole library)" % (d["LibFirst"], L["LibMax"], d["LibFullPick"], d["LibFull"]))
    out.append("  prep towers: seat %.1f on the box's top panel (%.1f); pick %.1f, bare or armed" % (
        d["TowerTop"], d["BoxTop"], d["TowerPick"]))
    passTop = d["TowerCombo"] + L["BoxLift"]
    if passTop > L["MiddleMemberZ"]:
        warn += 1
        out.append("  box removal (ADR-0015, lift %.2f under the member at %.0f): an armed tower would reach %.1f, so the "
                   "towers must come off the lid first, WARNING" % (L["BoxLift"], L["MiddleMemberZ"], passTop))
    else:
        out.append("  box removal (ADR-0015): towers pass under the middle member (%.1f < %.0f)" % (
            passTop, L["MiddleMemberZ"]))
    out.append("  C pick %.1f, tube rim %.1f, carriage %.1f when full (%d cartridges, %.1f mm)" % (
        L["ColPick"], d["ColRim"], d["ColLow"], L["ColCap"], L["ColCap"] * d["CartPitch"]))
    need = (L["ColCap"] - 1) * d["CartPitch"]
    fits = need <= L["ITravel"]
    bad += 0 if fits else 1
    out.append("  I axis as C's elevator: %.1f mm of its %.0f mm travel from full to last cartridge%s; carriage top"
               " %.1f..%.1f above the table (where its travel sits is not measured)" % (
                   need, L["ITravel"], "" if fits else "  EXCEEDS THE TRAVEL", d["ColLow"], L["ColPick"] - d["CartPitch"]))
    out.append("    one pick = A-%.3f (%.2f steps; absolute targets round per move, so no drift)" % (
        d["CartPitch"], d["CartPitch"] * L["IStepsPerMm"]))
    out.append("  D rim %.1f, eject from ring face %.1f (drop %.1f to the rim)" % (
        L["SpentRim"], L["EjectFace"], L["EjectFace"] - L["SpentRim"]))
    capOk = d["SpentFlatCap"] >= L["DeviceLayers"]
    bad += 0 if capOk else 1
    warn += 1 if capOk else 0
    out.append("  D holds at most %d cartridges lying flat (device of %d layers)%s" % (
        d["SpentFlatCap"], L["DeviceLayers"], "  TOO SMALL" if not capOk else
        "; an upper bound: the bore is wider than a cartridge's diagonal, so after the drop one can land tilted"
        " or on edge, WARNING"))
    out.append("  ring face range: %.1f..%.1f mechanical, down to %.1f with the legacy Z_MAX_POS %.0f" % (
        d["FaceMin"], L["RingFaceAtZ0"], d["FaceMinLegacy"], L["ZMaxLegacy"]))
    low = d["LibFirst"] < d["FaceMinLegacy"]
    mech = d["LibFirst"] >= d["FaceMin"]
    bad += 0 if mech else 1
    warn += 1 if low else 0
    out.append("  lowest library pick %.1f: %s the mechanical Z travel; %s the legacy Z limit (%.1f)%s" % (
        d["LibFirst"], "within" if mech else "OUTSIDE", "below" if low else "above", d["FaceMinLegacy"],
        ": Z_MAX_POS must move (#222), WARNING" if low else ""))
    warn += 1
    out.append("  head X reach assumed to x %.0f (strip left edge at machine X 350): NOT MEASURED, WARNING" % L["HeadXMax"])
    out.append("")
    rows, tallest = Planner()
    out.append("Search planner: %d-mask library in two piles, random order, %d-layer devices, %d runs each" % (
        L["LibMax"], L["DeviceLayers"], L["PlanRuns"]))
    out.append("  pile moves per layer (digging plus putting the used mask back); seconds add %d handling moves "
               "(mask to tower, cartridge from C, spent cartridge to D)" % L["HandlingMoves"])
    for name, mean, p95, mx in rows:
        t95 = (p95 + L["HandlingMoves"]) * L["MoveSeconds"]
        slow = t95 > L["SpinCureSeconds"]
        warn += 1 if slow else 0
        out.append("  %-28s mean %4.1f, 95th %2d (%3.0f s), max %2d (%3.0f s)%s" % (
            name, mean, p95, t95, mx, (mx + L["HandlingMoves"]) * L["MoveSeconds"],
            "  95TH SLOWER THAN SPIN + CURE, WARNING" if slow else ""))
    out.append("  tallest pile reached %d masks; %.1f s per move is an estimate, spin + cure %.0f s" % (
        tallest, L["MoveSeconds"], L["SpinCureSeconds"]))
    out.append("")
    out.append("Not modelled")
    out.append("  latch magnets: a tower's steel ring holds a mask only through latch magnets in its bottom (the latch")
    out.append("    test masks); the lobe hold mask from build_filter_cartridge.py has none yet, so the strip at a tower")
    out.append("    depends on adding them")
    out.append("  two bare masks lifting together: the ear magnets of stacked bare masks attract (latch test README)")
    out.append("  the top panel's screw heads under the tower feet, and anything else on the box lid")
    return out, bad, warn


def Combo(parts, z, x, y, withCart=True):
    names = ["Mask", "MaskBall1", "MaskBall2", "MaskBall3", "EarMagnet1", "EarMagnet2", "EarMagnet3", "LabelTag"]
    if withCart:
        names += ["Collar", "Body", "Plate", "Filter", "CntFilm"]
    shapes = [parts[n].copy() for n in names if n in parts]
    comp = Part.makeCompound(shapes)
    comp.translate(V(x, y, z))
    return comp


def Cartridge(parts, c, z, x, y, tilt=0.0):
    shapes = [parts[n].copy() for n in ("Collar", "Body", "Plate", "Filter", "CntFilm") if n in parts]
    comp = Part.makeCompound(shapes)
    comp.translate(V(0, 0, -c["CartridgeBottom"]))
    if tilt:
        comp.rotate(V(0, 0, 0), V(1, 0, 0), tilt)
    comp.translate(V(x, y, z))
    return comp


def Draw(d, c, fixtures, envelopes, checks, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle, Wedge

    fig = plt.figure(figsize=(18, 23))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 0.62, 0.95], hspace=0.16, wspace=0.10, top=0.955)
    fig.suptitle("Mask stowage: library piles L1 and L2, prep towers T1 and T2 on the box lid, fresh column C, "
                 "spent bin D (layout sketch)", fontsize=15, y=0.985)
    shown = {"L1": L["ShownL1"], "L2": L["ShownL2"]}

    # ---- plan
    ax = fig.add_subplot(gs[0, 0])
    ax.add_patch(Rectangle((0, 0), L["StripW"] + L["BoxW"], L["StripD"], fc="#FAFAFA", ec=Dark, lw=1.8))
    ax.add_patch(Rectangle((-60, d["ReachFront"]), L["HeadXMax"] + 60, L["ReachY"], fc=TolBlue, ec="none", alpha=0.07))
    for yy in (d["ReachFront"], d["ReachBack"]):
        ax.plot([-60, L["HeadXMax"]], [yy, yy], color=TolBlue, ls="--", lw=0.9)
    ax.plot([L["HeadXMax"]] * 2, [d["ReachFront"], d["ReachBack"]], color=TolBlue, ls="--", lw=0.9)
    ax.text(-55, d["ReachBack"] + 4, "head axis reach (X end assumed)", color=TolBlue, fontsize=8)
    for it in fixtures + envelopes:
        if it.Kind == "cyl":
            x, y, ri, ro = it.Geo[:4]
            if ri > 0:
                ax.add_patch(Wedge((x, y), ro, 0, 360, width=ro - ri, fc=it.Color, ec=Dark, lw=0.5, alpha=it.Alpha))
            else:
                ax.add_patch(Circle((x, y), ro, fc=it.Color, ec=Dark, lw=0.5, alpha=it.Alpha, ls=it.Ls))
        else:
            x0, x1, y0, y1 = it.Geo[:4]
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=it.Color, ec=Dark, lw=0.5, alpha=it.Alpha))
    ax.text(L["StripW"] + 200, 20, "control box lid (z %.1f)" % L["BoxH"], fontsize=9)
    for key in ("L1", "L2", "T1", "T2"):
        x, y = d[key]
        for a in Gen["EarAngles"]:
            t = math.radians(a)
            ax.add_patch(Circle((x + CartP["LobeMagR"] * math.cos(t), y + CartP["LobeMagR"] * math.sin(t)), 2.5,
                                fc=TolRed, ec=Dark, lw=0.4))
    labels = {"L1": "L1\nlibrary", "L2": "L2\nlibrary", "C": "C\nfresh", "D": "D\nspent", "T1": "T1\nprep",
              "T2": "T2\nprep"}
    for key, txt in labels.items():
        ax.text(d[key][0], d[key][1], txt, ha="center", va="center", fontsize=10, weight="bold")
    for key in StackKeys:
        ax.add_patch(Circle(d[key], L["HeadMidR"], fc="none", ec=TolBlue, lw=0.7, ls=":"))
    ax.text(5, -40, "dotted: head envelope (r %.0f) at each stack; red: ear magnets; dark ring: steel ring;\n"
                    "dashed: full library pile (r %.1f ears) and full column; pale boxes: label ear, 3 seatings" % (
                        L["HeadMidR"], CartP["LobeEarOuterR"]),
            fontsize=8, color=TolBlue)
    ax.set_xlim(-60, L["StripW"] + L["BoxW"] + 10)
    ax.set_ylim(-55, L["StripD"] + 10)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.set_xlabel("x, mm from the strip's left edge")
    ax.set_ylabel("y, mm from the inner front wall")
    ax.set_title("A  Plan", loc="left", fontsize=11)

    def MaskSide(ax, cen, z):
        ax.add_patch(Rectangle((cen - CartP["FrameOD"] / 2, z), CartP["FrameOD"], c["FrameTop"], fc=TolCyan, ec=Dark,
                               lw=0.3))

    def CartSide(ax, cen, zb, color=TolPurple):
        ax.add_patch(Rectangle((cen - CartP["BodyOD"] / 2, zb), CartP["BodyOD"], d["CartPitch"] - CartP["PlateT"],
                               fc=color, ec=Dark, lw=0.15, alpha=0.7))
        ax.add_patch(Rectangle((cen - CartP["PlateOD"] / 2, zb + d["CartPitch"] - CartP["PlateT"]), CartP["PlateOD"],
                               CartP["PlateT"], fc=Dark, lw=0))

    def Elev(ax, axis, title):
        other = 1 - axis
        order = sorted(fixtures + envelopes, key=lambda it: -(it.Geo[other] if it.Kind == "cyl"
                                                               else 0.5 * (it.Geo[2 * other] + it.Geo[2 * other + 1])))
        for it in order:
            if axis == 1 and it.Group == "ControlBox":
                continue
            if it.Kind == "cyl":
                cen, ro, z0, z1 = it.Geo[axis], it.Geo[3], it.Geo[4], it.Geo[5]
                a0, a1 = cen - ro, cen + ro
            else:
                a0, a1, z0, z1 = it.Geo[2 * axis], it.Geo[2 * axis + 1], it.Geo[4], it.Geo[5]
            ax.add_patch(Rectangle((a0, z0), a1 - a0, z1 - z0, fc=it.Color, ec=Dark, lw=0.4, alpha=it.Alpha, ls=it.Ls))
        for key in ("L1", "L2"):
            for n in range(shown[key]):
                MaskSide(ax, d[key][axis], L["LibStandTop"] + n * d["BarePitch"])
        MaskSide(ax, d["T1"][axis], d["TowerTop"])
        CartSide(ax, d["T1"][axis], d["TowerTop"] + c["CartridgeBottom"])
        MaskSide(ax, d["T2"][axis], d["TowerTop"])
        for n in range(L["ColCap"]):
            CartSide(ax, d["C"][axis], L["ColPick"] - (n + 1) * d["CartPitch"])
        for key, face in (("L1", L["LibStandTop"] + (shown["L1"] + 1) * d["BarePitch"]), ("C", L["ColPick"])):
            cen = d[key][axis]
            _, parts = HeadEnvelope(d[key][0], d[key][1], face)
            for r, z0, z1 in parts:
                ax.add_patch(Rectangle((cen - r, z0), 2 * r, z1 - z0, fc=TolBlue, ec=TolBlue, lw=0.6, alpha=0.12))
        ax.axhline(0, color=Dark, lw=1.5)
        lim = (L["StripW"] + L["BoxW"]) if axis == 0 else L["StripD"]
        for zz, t in ((d["FaceMin"], "lowest ring face (10 in of Z)"), (d["FaceMinLegacy"], "legacy Z_MAX_POS 186")):
            ax.axhline(zz, color=TolRed, lw=0.8, ls="--")
            ax.text(lim - 5, zz + 3, t, color=TolRed, fontsize=7.5, ha="right")
        ax.axvline(0, color=Dark, lw=0.8)
        ax.axvline(lim, color=Dark, lw=0.8)
        ax.set_xlim(-60, lim + 20)
        ax.set_ylim(-5, 580)
        ax.set_aspect("equal")
        ax.grid(alpha=0.2)
        ax.set_xlabel("x, mm" if axis == 0 else "y, mm from the inner front wall")
        ax.set_ylabel("z, mm above the table")
        ax.set_title(title, loc="left", fontsize=11)

    Elev(fig.add_subplot(gs[0, 1]), 0, "B  Front view; head at L1 (%d masks) and at C" % (shown["L1"] + 1))
    Elev(fig.add_subplot(gs[1, :]), 1, "C  Side view from the left (front wall at y = 0)")

    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    ax.text(0.0, 1.0, "D  Checks (from MaskStowage_Checks.txt)\n\n" + "\n".join(checks), va="top", ha="left",
            family="monospace", fontsize=8.2, transform=ax.transAxes)
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def Main():
    parts, c = Build(MaskP)
    bare = max(parts[n].BoundBox.ZMax for n in ("Mask", "MaskBall1", "MaskBall2", "MaskBall3", "EarMagnet1",
                                                 "EarMagnet2", "EarMagnet3") if n in parts)
    d = Layout(c, bare)
    fixtures = Fixtures(d)
    envelopes = StackEnvelopes(d)
    checks, bad, warn = Checks(d, fixtures, envelopes)
    print("\n".join(checks))
    outDir = os.path.join(Root, "CAD", "Mask Stowage")
    os.makedirs(outDir, exist_ok=True)
    open(os.path.join(outDir, "MaskStowage_Checks.txt"), "w", encoding="ascii", newline="\n").write(
        "\n".join(checks) + "\n\n%d check(s) failed, %d warning(s)\n" % (bad, warn))
    Draw(d, c, fixtures, envelopes, checks, os.path.join(outDir, "MaskStowage_Sketch.png"))

    doc = FreeCAD.newDocument("MaskStowage")
    groups = {}

    def Add(name, group, shape):
        if group not in groups:
            groups[group] = doc.addObject("App::DocumentObjectGroup", group)
        o = doc.addObject("Part::Feature", name)
        o.Shape = shape
        groups[group].addObject(o)

    for it in fixtures:
        Add(it.Name, it.Group, it.Shape)
    for key, n in (("L1", L["ShownL1"]), ("L2", L["ShownL2"])):
        x, y = d[key]
        for k in range(n):
            Add("Mask%s_%02d" % (key, k + 1), "Stack" + key, Combo(parts, L["LibStandTop"] + k * d["BarePitch"], x, y,
                                                                   withCart=False))
    Add("ArmedMaskT1", "StackT1", Combo(parts, d["TowerTop"], d["T1"][0], d["T1"][1]))
    Add("BareMaskT2", "StackT2", Combo(parts, d["TowerTop"], d["T2"][0], d["T2"][1], withCart=False))
    x, y = d["C"]
    for n in range(L["ColCap"]):
        Add("Fresh%02d" % (n + 1), "StackC", Cartridge(parts, c, L["ColPick"] - (n + 1) * d["CartPitch"], x, y))
    for it in envelopes:
        Add(it.Name, "Envelopes", it.Shape)
    head, _ = HeadEnvelope(d["L1"][0], d["L1"][1], L["LibStandTop"] + (L["ShownL1"] + 1) * d["BarePitch"])
    Add("HeadEnvelopeAtL1", "Envelopes", head)
    doc.recompute()
    doc.saveAs(os.path.join(outDir, "MaskStowage.FCStd"))
    FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed, %d warning(s); wrote %s" % (bad, warn, outDir))


Main()
