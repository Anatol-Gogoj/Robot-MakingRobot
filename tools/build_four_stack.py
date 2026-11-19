# Builds a layout sketch of the four stacks in the strip left of the control box:
#   P   pile 1, the P-electrode mask stored as a combo (mask with its next fresh cartridge seated)
#   N   pile 2, the same for the N-electrode mask
#   C   fresh cartridges, a column whose top the I-axis elevator holds at one pick height
#   D   spent cartridges, a bin the head ejects into from above
# The masks and cartridges are the lobe hold variant (issue 230), taken from
# build_filter_cartridge.py so the sketch follows any change made there.
#
# Run with FreeCAD's console:  freecadcmd tools/build_four_stack.py
# Writes CAD/Four Stack/FourStack.FCStd, FourStack_Sketch.png and FourStack_Checks.txt.
#
# Frame: x = mm from the strip's left edge (machine +X to the right), y = mm from the inner
# front wall (toward the back), z = mm above the table. Every value below is a layout proposal
# unless a comment names its source. The head is a coarse envelope, not a model of Gripper-B.

import math
import os

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

IN = 25.4

L = dict(
    # Strip (owner, 2026-11-16): the control box and feeder area is about 24 in in X by
    # 18 1/16 in front to back; the 13.5 in control box goes to the right, leaving 10.5 in.
    StripW=10.5 * IN,
    StripD=(18 + 1 / 16) * IN,
    BoxW=13.5 * IN,
    BoxDepth=457.0,         # tools/draw_wiring.py BoxD
    BoxH=279.4,             # tools/draw_wiring.py BoxH (11 in)
    # Head reach in Y (owner, 2026-11-16): at the rearmost Y the head axis is 6.5 in from the
    # inner back wall; Y travel 200 mm (Configuration.h Y_MAX_POS; claude.md: 150 mm unless X >= 350). The strip is
    # believed to sit at machine X >= 350 (owner, 2026-11-19, not measured), so the full 200 mm applies.
    RearAxisFromBack=6.5 * IN,
    ReachY=200.0,
    # Head Z range (owner, 2026-11-16): Gripper-B ring face 396.7 above the table at Z0, about
    # 10 in of mechanical Z travel; the firmware's Z_MAX_POS 186 is legacy (#222). The owner expects
    # the travel to reach the first pile pick (2026-11-19); the firmware limit still has to move.
    RingFaceAtZ0=396.7,
    ZTravel=10 * IN,
    ZMaxLegacy=186.0,
    # Release slide of a combo off the one below it (latch test, issue 226): 10 mm in +Y.
    # Which way machine +Y points in this frame is not known, so both directions are checked.
    SlideY=10.0,
    # Plan positions. Piles in the left column, one row near each end of the reach band, kept
    # SlideY inside it; C and D in the right column. C sits in from the back row so that its
    # centre stays HeadMidR + ColR clear of either pile pose after a slide. At a pile the head
    # overhangs the strip's left edge by HeadMidR - PileX; that is acceptable (owner, 2026-11-19).
    PileX=69.0,
    ColX=205.0,
    ColYFromBackRow=-50.0,
    SpentX=205.0,
    # Pile stand: a printed seat with a G90 steel ring flush in a recess in its top (as the latch
    # test's pile seat 8-05), on a 2020 post. The seat carries the mask frame (r 56) and the latch
    # magnets over the ring; the ears (r 66.5) overhang it.
    StandTop=200.0,
    SeatOD=120.0,
    SeatT=8.0,
    PostW=20.0,
    FootW=110.0,
    FootT=6.0,
    PileMax=16,             # stage 2 library: up to 16 combos per pile
    PileShown=1,            # stage 1: P and N only, one combo per pile
    # C column: bare cartridges stacked plate on body, top plate held at ColPick by the I axis.
    # The I axis, formerly the filter feeder, is reused as C's elevator (owner, 2026-11-19):
    # 343 mm travel, 320 steps/mm on a 5 mm lead screw, homes to I_MAX, and A- raises the stack
    # (Configuration.h; the Stamp block's feederJog). The rods, screw and motor drawn here are
    # placeholders until the feeder's hardware is measured.
    ITravel=343.0,
    IStepsPerMm=320.0,
    ColPick=300.0,          # top cartridge's plate face: above a full pile, so the head at C clears both piles
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
    # D: spent bin. The head's envelope at pile N overlaps D in plan, so the rim must stay below
    # the first pile pick less the legs' 0.7 mm and the head margin; the head check enforces it.
    SpentRim=200.0,
    SpentClear=3.5,         # radial, plate OD 109 to the bore. The bore is wider than a cartridge's section
                            # diagonal, so a dropped cartridge can land tilted: the flat count is an upper bound
    SpentWall=2.5,
    SpentFloor=4.0,
    EjectFace=320.0,        # ring face height over D when the head pushes a spent cartridge off
    # Head envelope around the ring face H (coarse, conservative; from the Gripper-B v33
    # preview: legs at r 65.5 hang 0.7 below the face, the carriage is r 81 wide above it).
    HeadLowR=77.5,
    HeadLowZ0=-0.7,
    HeadLowZ1=19.8,
    HeadMidR=81.0,
    HeadMidZ1=61.3,
    HeadTopR=50.0,
    HeadTopZ1=111.3,
    HeadMastR=50.0,         # the Z carriage above the head, carried up to the top of the frame
    MastTop=520.0,
    # Margins
    PlanMargin=1.0,         # between stack footprints
    HeadMargin=2.0,         # the head envelope is grown by this, radially and downward, for the checks
    TransitMargin=5.0,      # above the highest fixture or stack, plus the legs and a carried combo
    ShownSpent=3,
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


def Layout(c):
    """Derived positions and heights from L and the cartridge levels c."""
    d = {}
    d["ReachFront"] = L["StripD"] - L["RearAxisFromBack"] - L["ReachY"]
    d["ReachBack"] = L["StripD"] - L["RearAxisFromBack"]
    d["BackY"] = d["ReachBack"] - L["SlideY"]
    d["FrontY"] = d["ReachFront"] + L["SlideY"]
    d["P"] = (L["PileX"], d["BackY"])
    d["N"] = (L["PileX"], d["FrontY"])
    d["C"] = (L["ColX"], d["BackY"] + L["ColYFromBackRow"])
    d["D"] = (L["SpentX"], d["FrontY"])
    d["ComboPitch"] = c["RingFace"]                 # mask bottom to plate face: the next mask sits on the plate
    d["CartPitch"] = c["StackPitch"]                # cartridge bottom to plate face
    d["CartH"] = c["StackPitch"]
    d["PileFirst"] = L["StandTop"] + d["ComboPitch"]
    d["PileFull"] = L["StandTop"] + L["PileMax"] * d["ComboPitch"]
    d["ColR"] = CartP["PlateOD"] / 2 + L["ColClear"] + L["ColWall"]
    d["ColBore"] = CartP["PlateOD"] / 2 + L["ColClear"]
    d["ColRim"] = L["ColPick"] - d["CartH"] - L["ColRimBelowTop"]
    d["ColLow"] = L["ColPick"] - L["ColCap"] * d["CartPitch"]   # carriage top when C is full
    d["SpentFlatCap"] = int((L["SpentRim"] - L["SpentFloor"]) / d["CartPitch"])
    d["SpentBore"] = CartP["PlateOD"] / 2 + L["SpentClear"]
    d["SpentR"] = d["SpentBore"] + L["SpentWall"]
    d["FaceMin"] = L["RingFaceAtZ0"] - L["ZTravel"]
    d["FaceMinLegacy"] = L["RingFaceAtZ0"] - L["ZMaxLegacy"]
    return d


def Fixtures(d):
    """The stands, the C column with its elevator, the D bin: everything that does not move with a layer."""
    items = []
    for key, label in (("P", "Pile1"), ("N", "Pile2")):
        x, y = d[key]
        g = "Stand" + key
        items.append(BoxItem(label + "Foot", g, x - L["FootW"] / 2, x + L["FootW"] / 2, y - L["FootW"] / 2,
                             y + L["FootW"] / 2, 0, L["FootT"], TolGrey))
        items.append(BoxItem(label + "Post", g, x - L["PostW"] / 2, x + L["PostW"] / 2, y - L["PostW"] / 2,
                             y + L["PostW"] / 2, L["FootT"], L["StandTop"] - L["SeatT"], TolGrey))
        seat = Cyl(L["SeatOD"] / 2, L["StandTop"] - L["SeatT"], L["StandTop"], x, y).cut(
            Tube(CartP["PlateID"] / 2, CartP["PlateOD"] / 2, L["StandTop"] - CartP["PlateT"], L["StandTop"] + 1, x, y))
        items.append(Item(label + "Seat", g, seat, "cyl", (x, y, 0, L["SeatOD"] / 2, L["StandTop"] - L["SeatT"],
                                                            L["StandTop"]), TolGreen))
        items.append(CylItem(label + "SeatRing", g, x, y, CartP["PlateID"] / 2, CartP["PlateOD"] / 2,
                             L["StandTop"] - CartP["PlateT"], L["StandTop"], Dark, 0.8))
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
    # control box envelope (tools/draw_wiring.py: BoxD, BoxW, BoxH = 457.0, 342.9, 279.4), centred front to back
    y0 = (L["StripD"] - L["BoxDepth"]) / 2
    items.append(BoxItem("ControlBox", "ControlBox", L["StripW"], L["StripW"] + L["BoxW"], y0, y0 + L["BoxDepth"], 0,
                         L["BoxH"], TolGrey, 0.25))
    x, y = d["D"]
    items.append(CylItem("SpentBin", "BinD", x, y, d["SpentBore"], d["SpentR"], L["SpentFloor"], L["SpentRim"],
                         TolGrey, 0.35))
    items.append(CylItem("SpentBinFloor", "BinD", x, y, 0, d["SpentR"], 0, L["SpentFloor"], TolGrey, 0.35))
    return items


def Carriage(d, top):
    """The elevator carriage and its arm with the carriage top at the given height."""
    x, y = d["C"]
    ry = y + L["RodOffset"]
    return [CylItem("ElevatorCarriage", "ColumnC", x, y, 0, d["ColBore"] - 0.5, top - L["CarriageT"], top, TolBlue),
            BoxItem("ElevatorArm", "ColumnC", x - 8, x + 8, y, ry, top - L["CarriageT"], top, TolBlue)]


def StackEnvelopes(d, c):
    """Worst-case stack contents for the clearance checks (full piles, full column)."""
    env = []
    for key in ("P", "N"):
        x, y = d[key]
        env.append(CylItem("Pile%sFull" % key, "Stack" + key, x, y, 0, CartP["LobeEarOuterR"], L["StandTop"],
                           d["PileFull"], TolCyan, 0.12, "--"))
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
    for key in ("P", "N"):
        x, y = d[key]
        for n, face in ((1, d["PileFirst"]), (L["PileMax"], d["PileFull"])):
            for dy in (0.0, L["SlideY"], -L["SlideY"]):
                poses.append(("%s, %d combo%s, slide %+.0f" % (key, n, "s" if n > 1 else "", dy), key, x, y + dy, face))
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


def Checks(d, fixtures, envelopes):
    out, bad, warn = [], 0, 0
    obstacles = fixtures + envelopes
    out.append("Head clearance at every pick pose (envelope grown by %.0f mm vs everything not on the worked "
               "stack; gap = nominal envelope to the nearest level item)" % L["HeadMargin"])
    for label, key, x, y, face in PickPoses(d):
        head, _ = HeadEnvelope(x, y, face, L["HeadMargin"])
        _, parts = HeadEnvelope(x, y, face)
        worst, worstName, hits = 1e9, "", []
        for it in obstacles:
            # the worked stack's own contents and stand are the head's to touch; the coupling is
            # checked by build_filter_cartridge.py. C's tube and rods and D's rim still count.
            if it.Group in ("Stack" + key, "Stand" + key):
                continue
            if key == "C" and it.Name in ("ElevatorCarriage", "ElevatorArm"):
                continue
            if head.common(it.Shape).Volume > 1e-3:
                hits.append(it.Name)
            # plan gap to the part of the envelope that is level with the item
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
        out.append("  %-34s face %6.1f  %s  min plan gap %6.1f mm (%s)%s%s" % (
            label, face, "ok  " if ok else "HIT ", worst if worst < 1e8 else float("nan"), worstName or "-",
            "" if not hits else "  hits: " + ", ".join(sorted(set(hits))),
            "" if faceOk else "  OUT OF Z RANGE"))
    out.append("")
    out.append("Elevator sweep: carriage and arm against the tube and both piles, from full to the last cartridge")
    tube = [it for it in fixtures if it.Name == "ColumnTube"][0]
    others = [tube] + [it for it in envelopes if it.Group in ("StackP", "StackN")]
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
    out.append("Footprints (plan, at the table and in the air)")
    keys = (("P", CartP["LobeEarOuterR"]), ("N", CartP["LobeEarOuterR"]), ("C", d["ColR"]), ("D", d["SpentR"]))
    for k, r in keys:
        x, y = d[k]
        inStrip = (x - r >= -1e-6 and x + r <= L["StripW"] + 1e-6 and y - r >= 0 and y + r <= L["StripD"])
        inReach = d["ReachFront"] <= y <= d["ReachBack"]
        bad += 0 if (inStrip and inReach) else 1
        out.append("  %s at (%.1f, %.1f) r %.1f: x %.1f..%.1f, y %.1f..%.1f  %s, %s" % (
            k, x, y, r, x - r, x + r, y - r, y + r, "inside the strip" if inStrip else "OUTSIDE THE STRIP",
            "centre in reach" if inReach else "CENTRE OUT OF REACH"))
    for i, (a, ra) in enumerate(keys):
        for b, rb in keys[i + 1:]:
            g = math.hypot(d[a][0] - d[b][0], d[a][1] - d[b][1]) - ra - rb
            bad += 0 if g >= L["PlanMargin"] else 1
            out.append("  %s to %s: %.1f mm apart in plan%s" % (a, b, g, "" if g >= L["PlanMargin"] else "  OVERLAP"))
    out.append("")
    out.append("Heights")
    out.append("  combo pitch %.3f (mask bottom to plate face; the next mask sits on that plate)" % d["ComboPitch"])
    out.append("  cartridge pitch %.3f (cartridge bottom to plate face)" % d["CartPitch"])
    out.append("  pile pick: 1 combo %.1f, %d combos %.1f" % (d["PileFirst"], L["PileMax"], d["PileFull"]))
    out.append("  C pick %.1f, tube rim %.1f, carriage %.1f when full (%d cartridges, %.1f mm)" % (
        L["ColPick"], d["ColRim"], d["ColLow"], L["ColCap"], L["ColCap"] * d["CartPitch"]))
    need = (L["ColCap"] - 1) * d["CartPitch"]
    fits = need <= L["ITravel"]
    bad += 0 if fits else 1
    out.append("  I axis as C's elevator: %.1f mm of its %.0f mm travel from full to last cartridge%s;" % (
        need, L["ITravel"], "" if fits else "  EXCEEDS THE TRAVEL"))
    out.append("    one pick = A-%.3f (%.2f steps; absolute targets round per move, so no drift)" % (
        d["CartPitch"], d["CartPitch"] * L["IStepsPerMm"]))
    out.append("  D rim %.1f, eject from ring face %.1f (drop %.1f to the rim)" % (
        L["SpentRim"], L["EjectFace"], L["EjectFace"] - L["SpentRim"]))
    capOk = d["SpentFlatCap"] >= L["ColCap"]
    bad += 0 if capOk else 1
    out.append("  D holds at most %d cartridges lying flat (column %d)%s; tilted landings hold fewer: empty D "
               "between devices" % (d["SpentFlatCap"], L["ColCap"], "" if capOk else "  TOO SMALL"))
    out.append("  ring face range: %.1f..%.1f mechanical, down to %.1f with the legacy Z_MAX_POS %.0f" % (
        d["FaceMin"], L["RingFaceAtZ0"], d["FaceMinLegacy"], L["ZMaxLegacy"]))
    low = d["PileFirst"] < d["FaceMinLegacy"]
    mech = d["PileFirst"] >= d["FaceMin"]
    bad += 0 if mech else 1
    warn += 1 if low else 0
    out.append("  first pile pick %.1f: %s the mechanical Z travel; %s the legacy Z limit (%.1f)%s" % (
        d["PileFirst"], "within" if mech else "OUTSIDE", "below" if low else "above", d["FaceMinLegacy"],
        ": Z_MAX_POS must move (#222), WARNING" if low else ""))
    return out, bad, warn


def Combo(parts, z, x, y, withCart=True):
    names = ["Mask", "MaskBall1", "MaskBall2", "MaskBall3", "EarMagnet1", "EarMagnet2", "EarMagnet3"]
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

    fig = plt.figure(figsize=(17, 19))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 0.62, 0.55], hspace=0.18, wspace=0.12, top=0.95)
    fig.suptitle("Four stacks in the 10.5 in strip: P and N mask piles, C fresh column, D spent bin (layout sketch)",
                 fontsize=15, y=0.985)

    # ---- plan
    ax = fig.add_subplot(gs[0, 0])
    ax.add_patch(Rectangle((0, 0), L["StripW"] + L["BoxW"], L["StripD"], fc="#FAFAFA", ec=Dark, lw=1.8))
    ax.text(L["StripW"] + 60, L["StripD"] / 2, "control box", fontsize=9)
    ax.add_patch(Rectangle((-60, d["ReachFront"]), L["StripW"] + 120, L["ReachY"], fc=TolBlue, ec="none", alpha=0.07))
    for yy in (d["ReachFront"], d["ReachBack"]):
        ax.plot([-60, L["StripW"] + 60], [yy, yy], color=TolBlue, ls="--", lw=0.9)
    ax.text(-55, d["ReachBack"] + 4, "head axis reach in Y", color=TolBlue, fontsize=8)
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
    for key in ("P", "N"):
        x, y = d[key]
        for a in Gen["EarAngles"]:
            t = math.radians(a)
            ax.add_patch(Circle((x + CartP["LobeMagR"] * math.cos(t), y + CartP["LobeMagR"] * math.sin(t)), 2.5,
                                fc=TolRed, ec=Dark, lw=0.4))
    for key, txt in (("P", "P\npile 1"), ("N", "N\npile 2"), ("C", "C\nfresh"), ("D", "D\nspent")):
        ax.text(d[key][0], d[key][1], txt, ha="center", va="center", fontsize=10, weight="bold")
    for label, key, x, y, face in PickPoses(d):
        if "slide" in label and not label.endswith("+0"):
            continue
        if "16" in label:
            continue
        ax.add_patch(Circle((x, y), L["HeadMidR"], fc="none", ec=TolBlue, lw=0.7, ls=":"))
    ax.text(5, -40, "dotted: head envelope (r %.0f) at each stack; red: ear magnets; dark ring: steel ring;\n"
                    "dashed: full pile (r %.1f ears) and full column" % (L["HeadMidR"], CartP["LobeEarOuterR"]),
            fontsize=8, color=TolBlue)
    ax.set_xlim(-60, L["StripW"] + 130)
    ax.set_ylim(-55, L["StripD"] + 10)
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.set_xlabel("x, mm from the strip's left edge")
    ax.set_ylabel("y, mm from the inner front wall")
    ax.set_title("A  Plan", loc="left", fontsize=11)

    # ---- elevations: front (XZ) and side (YZ) projections
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
        for key in ("P", "N"):
            cen = d[key][axis]
            for n in range(L["PileShown"]):
                z = L["StandTop"] + n * d["ComboPitch"]
                ax.add_patch(Rectangle((cen - CartP["FrameOD"] / 2, z), CartP["FrameOD"], c["FrameTop"], fc=TolCyan,
                                       ec=Dark, lw=0.4))
                ax.add_patch(Rectangle((cen - CartP["BodyOD"] / 2, z + c["CartridgeBottom"]), CartP["BodyOD"],
                                       c["RingFace"] - CartP["PlateT"] - c["CartridgeBottom"], fc=TolPurple, ec=Dark,
                                       lw=0.3, alpha=0.8))
                ax.add_patch(Rectangle((cen - CartP["PlateOD"] / 2, z + c["RingFace"] - CartP["PlateT"]),
                                       CartP["PlateOD"], CartP["PlateT"], fc=Dark, lw=0))
        cen = d["C"][axis]
        for n in range(L["ColCap"]):
            z = L["ColPick"] - (n + 1) * d["CartPitch"]
            ax.add_patch(Rectangle((cen - CartP["BodyOD"] / 2, z), CartP["BodyOD"], d["CartPitch"] - CartP["PlateT"],
                                   fc=TolPurple, ec=Dark, lw=0.15, alpha=0.6))
            ax.add_patch(Rectangle((cen - CartP["PlateOD"] / 2, z + d["CartPitch"] - CartP["PlateT"]), CartP["PlateOD"],
                                   CartP["PlateT"], fc=Dark, lw=0))
        # head at pile 1 with one combo, and at C
        for key, face in (("P", d["PileFirst"]), ("C", L["ColPick"])):
            cen = d[key][axis]
            _, parts = HeadEnvelope(d[key][0], d[key][1], face)
            for r, z0, z1 in parts:
                ax.add_patch(Rectangle((cen - r, z0), 2 * r, z1 - z0, fc=TolBlue, ec=TolBlue, lw=0.6, alpha=0.12))
        ax.axhline(0, color=Dark, lw=1.5)
        for zz, t in ((d["FaceMin"], "lowest ring face (10 in of Z)"), (d["FaceMinLegacy"], "legacy Z_MAX_POS 186")):
            ax.axhline(zz, color=TolRed, lw=0.8, ls="--")
            ax.text((L["StripW"] if axis == 0 else L["StripD"]) - 5, zz + 3, t, color=TolRed, fontsize=7.5, ha="right")
        lim = L["StripW"] if axis == 0 else L["StripD"]
        ax.axvline(0, color=Dark, lw=0.8)
        ax.axvline(lim, color=Dark, lw=0.8)
        ax.set_xlim(-60, lim + 40)
        ax.set_ylim(-5, 540)
        ax.set_aspect("equal")
        ax.grid(alpha=0.2)
        ax.set_xlabel("x, mm" if axis == 0 else "y, mm from the inner front wall")
        ax.set_ylabel("z, mm above the table")
        ax.set_title(title, loc="left", fontsize=11)

    Elev(fig.add_subplot(gs[0, 1]), 0, "B  Front view (looking toward the back wall); head shown at P (1 combo) and at C")
    Elev(fig.add_subplot(gs[1, :]), 1, "C  Side view from the left (front wall at y = 0)")

    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    ax.text(0.0, 1.0, "D  Checks (from FourStack_Checks.txt)\n\n" + "\n".join(checks), va="top", ha="left",
            family="monospace", fontsize=8.6, transform=ax.transAxes)
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def Main():
    q = dict(CartP)
    q.update(PrintedFlange=True, MaskHold="lobe")
    parts, c = Build(q)
    d = Layout(c)
    fixtures = Fixtures(d)
    envelopes = StackEnvelopes(d, c)
    checks, bad, warn = Checks(d, fixtures, envelopes)
    print("\n".join(checks))
    outDir = os.path.join(Root, "CAD", "Four Stack")
    os.makedirs(outDir, exist_ok=True)
    open(os.path.join(outDir, "FourStack_Checks.txt"), "w", encoding="ascii", newline="\n").write(
        "\n".join(checks) + "\n\n%d check(s) failed, %d warning(s)\n" % (bad, warn))
    Draw(d, c, fixtures, envelopes, checks, os.path.join(outDir, "FourStack_Sketch.png"))

    doc = FreeCAD.newDocument("FourStack")
    groups = {}

    def Add(name, group, shape):
        if group not in groups:
            groups[group] = doc.addObject("App::DocumentObjectGroup", group)
        o = doc.addObject("Part::Feature", name)
        o.Shape = shape
        groups[group].addObject(o)

    for it in fixtures:
        Add(it.Name, it.Group, it.Shape)
    for key in ("P", "N"):
        x, y = d[key]
        for n in range(L["PileShown"]):
            Add("Combo%s%d" % (key, n + 1), "Stack" + key, Combo(parts, L["StandTop"] + n * d["ComboPitch"], x, y))
    x, y = d["C"]
    for n in range(L["ColCap"]):
        Add("Fresh%02d" % (n + 1), "StackC", Cartridge(parts, c, L["ColPick"] - (n + 1) * d["CartPitch"], x, y))
    x, y = d["D"]
    for n in range(L["ShownSpent"]):
        Add("Spent%d" % (n + 1), "StackD", Cartridge(parts, c, L["SpentFloor"] + 5 + 8 * n, x, y, tilt=(-1) ** n * 4.0))
    for it in envelopes:
        Add(it.Name, "Envelopes", it.Shape)
    head, _ = HeadEnvelope(d["P"][0], d["P"][1], d["PileFirst"])
    Add("HeadEnvelopeAtP", "Envelopes", head)
    doc.recompute()
    doc.saveAs(os.path.join(outDir, "FourStack.FCStd"))
    FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed, %d warning(s); wrote %s" % (bad, warn, outDir))


Main()
