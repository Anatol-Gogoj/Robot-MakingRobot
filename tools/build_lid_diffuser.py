# Builds the UV lid's argon diffuser (issue 251) as two FFF ASA parts that print without supports and clamp the LED
# plate between them by a printed thread, sized for the free centre of the lid's 3 x 3 LED grid (30 mm pitch, centre
# position empty, a heatsink on each LED).
#
#   Cup (above the plate): sits on the plate's top face inside the free centre cell. Its flat top takes a PC4-M10
#   push-in fitting for 4 x 2 mm PTFE (tap it M10 x 1 after printing); the tube's end seats on the 90 deg point below
#   the thread, which narrows to the inlet into the plenum. Its bore carries an internal thread.
#   Face part (below the plate): a thin knurled disc under the plate with a threaded spigot that rises through the
#   plate's existing centre hole and screws into the cup. The disc holds the 1 mm face holes; a stalk on it carries
#   a 45 deg mushroom baffle 1 mm below the inlet. Screwing the face part in by hand clamps the plate between the
#   disc and the cup; unscrewing it from below opens the diffuser for cleaning with the cup and tube left in place.
#
# The concept sheet docs/spincoater/lid_diffuser_sketch.svg (tools/draw_lid_diffuser.py) assumed a 45 mm hole and a
# flange on the plate; the measured 30 mm LED pitch leaves no room for either, hence this layout.
#
# Run with FreeCAD's console:  freecadcmd tools/build_lid_diffuser.py
# Writes CAD/Spincoater/Lid Diffuser/: one STEP per printed part in print orientation, the assembly with the LED
# plate and the fitting (_Assembly.step), the FCStd, _Checks.txt and _Section.png. It refuses to write anything
# when a check fails.
#
# Frame: z = 0 at the underside of the LED plate, z up; x and y along the LED rows; the axis is the plate's centre.
# Units mm. The thread is a 90 deg (45 deg flank) profile, not ISO metric, so its flanks print at the 45 deg limit.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
OutDir = os.path.join(Root, "CAD", "Spincoater", "Lid Diffuser")
Stem = "LidDiffuser_v20261124-B"

P = dict(
    # LED plate (owner, 2026-11-24): 1/16 in acrylic, 22.8 mm centre hole, LEDs on a 3 x 3 grid at 30 mm pitch
    # (the outer two of a row 60 mm apart), centre empty, a heatsink module on each LED
    PlateThick=1.5875, PlateHoleD=22.8, LedPitch=30.0,
    LedCutoutD=22.8,       # ASSUMED: each LED's cutout the size of the centre hole; only for the clearance checks
    HeatsinkMax=30.0,      # a heatsink can be at most one pitch wide, or its neighbours would overlap: so a square of
                           # +-(pitch - HeatsinkMax / 2) about the centre is free above the plate
    TopMargin=0.5,         # cup outline kept this far inside that free square
    GapToSubstrate=15.0,   # ASSUMED face to substrate
    # Thread (both parts printed): 90 deg profile, pitch 2, 0.8 deep, crest and root flats 0.2
    Pitch=2.0, ThreadDepth=0.8, ThreadHalfRoot=0.9, ThreadClear=0.25,   # radial offset of the cup's groove
    SpigotCrestR=11.1,     # 0.3 radial play in the 22.8 hole
    Engage=6.0,            # thread length in the cup above the plate's top face: 3 turns
    SpigotWall=1.2,        # from the thread's root to the spigot bore
    # Cup
    CupR=14.5,
    RoofAboveSpigot=4.4,   # plenum roof above the spigot's top
    TapD=9.0, TapDepth=6.0, InletD=2.5, InletLen=0.75,
    # Face part
    DiscR=14.0, DiscT=1.5, KnurlCount=24, KnurlR=0.8,
    HoleD=1.0, HolePitch=2.5,   # face holes: printed at 1.0, then drilled through with a 1.0 bit
    StalkR=2.5, BaffleR=7.0, BaffleGap=1.0, BaffleCapT=1.2,
    # Process and checks
    MinWall=1.2, OverhangDeg=45.0, BedXY=256.0,
    ArgonDensity=1.66, HoleCd=0.6, FlowsLpm=(2.0, 5.0),
)

Tp = P["PlateThick"]
RootR = P["SpigotCrestR"] - P["ThreadDepth"]          # spigot thread root
BoreR = RootR - P["SpigotWall"]                       # spigot bore
SpigotTopZ = Tp + P["Engage"]
CupBoreR = RootR + P["ThreadClear"]                   # cup's thread crest (its bore)
GrooveR = P["SpigotCrestR"] + P["ThreadClear"]        # cup's thread root
GrooveTopZ = SpigotTopZ + 1.0                         # the spigot never bottoms
RoofZ = SpigotTopZ + P["RoofAboveSpigot"]
CapTopZ = RoofZ - P["BaffleGap"]
CapBotZ = CapTopZ - P["BaffleCapT"]
StalkConeZ = CapBotZ - (P["BaffleR"] - P["StalkR"])  # 45 deg cone from the stalk up to the cap
ConeTopZ = RoofZ + P["InletLen"]                      # the inlet bore runs from the roof up to the tap's point
TapBotZ = ConeTopZ + (P["TapD"] - P["InletD"]) / 2
TopZ = TapBotZ + P["TapDepth"]
DiscBotZ = -P["DiscT"]
FreeHalf = P["LedPitch"] - P["HeatsinkMax"] / 2


def Cyl(r, z0, z1, x=0.0, y=0.0):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def Cone(r0, r1, z0, z1, x=0.0, y=0.0):
    return Part.makeCone(r0, r1, z1 - z0, V(x, y, z0))


def Ridge(rootR, zStart, length, depth, halfRoot, perTurn=48):
    """A helical 45 deg flank ridge on a core of radius rootR, right hand, its profile centred at zStart at angle 0.
    Built as a ruled loft through perTurn profiles per turn: FreeCAD 1.1's helix sweep (makePipeShell) put the
    profile out to r 16.8 and its fuse with the core came back empty, and a smooth loft overshoots the crest; the
    ruled loft keeps the crest radius exact and fuses cleanly. The profile sinks 0.3 into the core; adjacent turns
    leave a root flat of Pitch - 2 * halfRoot."""
    pitch = P["Pitch"]
    hc = halfRoot - depth                       # crest half width for 45 deg flanks
    x0 = rootR - 0.3
    n = int(round((length / pitch + 2) * perTurn))
    wires = []
    for k in range(n + 1):
        t = 2 * math.pi * k / perTurn
        z = zStart - pitch + pitch * k / perTurn
        c, s = math.cos(t), math.sin(t)
        pts = [(x0, z - halfRoot), (rootR, z - halfRoot), (rootR + depth, z - hc), (rootR + depth, z + hc),
               (rootR, z + halfRoot), (x0, z + halfRoot), (x0, z - halfRoot)]
        wires.append(Part.makePolygon([V(x * c, x * s, zz) for x, zz in pts]))
    return Part.makeLoft(wires, True, True)


def Trimmed(ridge, rootR, z0, z1, depth):
    """Keep the ridge between z0 and z1 with 45 deg run-outs at both ends."""
    h = depth + 0.2
    big = rootR + depth + 1.0
    keep = Cyl(big, z0 + h, z1 - h).fuse(Cone(rootR - 0.2, rootR + h, z0, z0 + h + 0.2)).fuse(
        Cone(rootR + h, rootR - 0.2, z1 - h - 0.2, z1))
    return ridge.common(keep)


def FaceHoles():
    out = []
    pitch = P["HolePitch"]
    row = pitch * math.sqrt(3) / 2
    rMin = P["StalkR"] + P["HoleD"] / 2 + 0.6
    rMax = BoreR - P["HoleD"] / 2 - 0.6
    n = int(rMax / row) + 1
    for j in range(-n, n + 1):
        off = pitch / 2 if j % 2 else 0.0
        for i in range(-n - 1, n + 2):
            x, y = i * pitch + off, j * row
            if rMin <= math.hypot(x, y) <= rMax:
                out.append((x, y))
    return out


def BuildFace(holes):
    disc = Cyl(P["DiscR"], DiscBotZ, 0.0)
    for k in range(P["KnurlCount"]):
        a = 2 * math.pi * k / P["KnurlCount"]
        disc = disc.cut(Cyl(P["KnurlR"], DiscBotZ - 1, 1, P["DiscR"] * math.cos(a), P["DiscR"] * math.sin(a)))
    spigot = Cyl(RootR, -0.01, SpigotTopZ).cut(Cyl(BoreR, -1, SpigotTopZ + 1))
    thread = Trimmed(Ridge(RootR, 0.0, SpigotTopZ + 2, P["ThreadDepth"], P["ThreadHalfRoot"]), RootR, 0.3, SpigotTopZ,
                     P["ThreadDepth"])
    face = disc.fuse(spigot).fuse(thread)
    face = face.fuse(Cyl(P["StalkR"], -0.01, StalkConeZ + 0.01))
    face = face.fuse(Cone(P["StalkR"], P["BaffleR"], StalkConeZ, CapBotZ + 0.01))
    face = face.fuse(Cyl(P["BaffleR"], CapBotZ, CapTopZ))
    for x, y in holes:
        face = face.cut(Cyl(P["HoleD"] / 2, DiscBotZ - 1, 0.5, x, y))
    return face.removeSplitter()


def BuildCup():
    cup = Cyl(P["CupR"], Tp, TopZ)
    cutter = Cyl(CupBoreR, Tp - 2.0, RoofZ)
    groove = Ridge(RootR + P["ThreadClear"], 0.0, GrooveTopZ + 2, P["ThreadDepth"], P["ThreadHalfRoot"])
    groove = Trimmed(groove, CupBoreR, Tp - 3.0, GrooveTopZ, P["ThreadDepth"])
    cutter = cutter.fuse(groove)
    cutter = cutter.fuse(Cone(GrooveR + 0.5, CupBoreR - 0.2, Tp - 0.01, Tp + GrooveR + 0.7 - CupBoreR))   # 45 deg lead-in
    cutter = cutter.fuse(Cyl(P["TapD"] / 2, TapBotZ, TopZ + 1)).fuse(Cone(P["InletD"] / 2, P["TapD"] / 2, ConeTopZ, TapBotZ))
    cutter = cutter.fuse(Cyl(P["InletD"] / 2, RoofZ - 0.5, ConeTopZ + 0.01))
    return cup.cut(cutter).removeSplitter()


def BuildRefs():
    half = P["LedPitch"] + 15
    plate = Part.makeBox(2 * half, 2 * half, Tp, V(-half, -half, 0))
    plate = plate.cut(Cyl(P["PlateHoleD"] / 2, -1, Tp + 1))
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            if i or j:
                plate = plate.cut(Cyl(P["LedCutoutD"] / 2, -1, Tp + 1, i * P["LedPitch"], j * P["LedPitch"]))
    hexR = 7.0
    hx = Part.Face(Part.makePolygon([V(hexR * math.cos(math.radians(60 * i + 30)), hexR * math.sin(math.radians(60 * i + 30)), TopZ)
                                     for i in range(7)])).extrude(V(0, 0, 4.0))
    fitting = hx.fuse(Cyl(5.0, TapBotZ + 0.5, TopZ)).cut(Cyl(2.05, TapBotZ, TopZ + 6))
    return plate, fitting


def Overhangs(shape):
    """Down-facing surfaces of a part in print orientation (bed at z = 0), not on the bed. Returns the steepest
    angle from straight down found and the area of faces with any sample beyond OverhangDeg."""
    lim = math.cos(math.radians(P["OverhangDeg"])) + 1e-3
    worst, area = 90.0, 0.0
    for f in shape.Faces:
        if f.BoundBox.ZMax < 1e-3:
            continue
        u0, u1, v0, v1 = f.ParameterRange
        bad = False
        for i in range(7):
            for j in range(7):
                u = u0 + (u1 - u0) * (i + 0.5) / 7
                v = v0 + (v1 - v0) * (j + 0.5) / 7
                if not f.isInside(f.valueAt(u, v), 1e-4, True):
                    continue
                n = f.normalAt(u, v)
                if n.z < -1e-6:
                    worst = min(worst, math.degrees(math.acos(min(1.0, -n.z))))
                if n.z < -lim:
                    bad = True
        if bad:
            area += f.Area
    return worst, area


def PrintPose(shape, flip):
    s = shape.copy()
    if flip:
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    s.translate(V(0, 0, -s.optimalBoundingBox().ZMin))   # the plain BoundBox is loose around the lofted thread
    return s


def Moved(shape, dz=0.0, rot=0.0):
    s = shape.copy()
    if rot:
        s.rotate(V(0, 0, 0), V(0, 0, 1), rot)
    if dz:
        s.translate(V(0, 0, dz))
    return s


def Check(cup, face, plate, holes, log):
    bad = 0

    def Say(ok, text):
        nonlocal bad
        bad += not ok
        log.append(("  ok   " if ok else "  FAIL ") + text)

    for name, s in (("Cup", cup), ("FacePart", face)):
        Say(len(s.Solids) == 1 and s.isValid(), "%s: %d solid, valid %s, %.1f cm^3" % (name, len(s.Solids), s.isValid(), s.Volume / 1000))
    # room on the plate
    lim = FreeHalf - P["TopMargin"]
    Say(P["CupR"] <= lim, "cup r %.1f inside the free centre square +-%.1f (heatsinks at most %.0f wide on a %.0f pitch), %.1f to spare"
        % (P["CupR"], FreeHalf, P["HeatsinkMax"], P["LedPitch"], FreeHalf - P["CupR"]))
    cutEdge = P["LedPitch"] - P["LedCutoutD"] / 2
    Say(P["DiscR"] <= cutEdge - 2.0, "disc r %.1f under the plate, %.1f from the nearest LED cutout edge (r %.1f, cutout size assumed)"
        % (P["DiscR"], cutEdge - P["DiscR"], cutEdge))
    Say(P["PlateHoleD"] / 2 - P["SpigotCrestR"] >= 0.2, "spigot thread crest r %.2f in the %.1f plate hole: %.2f radial play"
        % (P["SpigotCrestR"], P["PlateHoleD"], P["PlateHoleD"] / 2 - P["SpigotCrestR"]))
    # walls
    Say(P["CupR"] - GrooveR >= P["MinWall"], "cup wall outside the thread groove %.2f" % (P["CupR"] - GrooveR))
    Say(P["SpigotWall"] >= P["MinWall"], "spigot wall from the thread root to the bore %.2f" % P["SpigotWall"])
    Say(BoreR - P["BaffleR"] >= 2.0, "baffle cap r %.1f passes the spigot bore r %.2f and the cup bore r %.2f when screwed in"
        % (P["BaffleR"], BoreR, CupBoreR))
    # clamp and thread: assembled, the disc's top is on the plate's underside and the cup's bottom on its top
    ov = (face.common(cup).Volume, face.common(plate).Volume, cup.common(plate).Volume)
    d = face.distToShape(cup)[0]
    Say(max(ov) < 1e-3, "assembled with the plate clamped: overlaps face/cup %.4f, face/plate %.4f, cup/plate %.4f" % ov)
    Say(d >= 0.12, "nearest face part to cup %.3f (thread flank clearance %.3f nominal)" % (d, P["ThreadClear"] * math.sqrt(0.5)))
    Say(face.distToShape(plate)[0] < 1e-3 and cup.distToShape(plate)[0] < 1e-3, "disc and cup both bear on the plate")
    pulled = Moved(face, dz=-0.5).common(cup).Volume
    Say(pulled > 1.0, "control: face part pulled 0.5 down without turning hits the cup's thread (%.1f mm^3): the thread holds it" % pulled)
    turned = max(Moved(face, dz=-P["Pitch"] * a / 360.0, rot=-a).common(cup).Volume for a in (30, 90, 180, 270))
    Say(turned < 1e-3, "unscrewing the face part 30 to 270 deg (dz = -pitch x turn): worst overlap %.4f" % turned)
    Say(SpigotTopZ + 0.9 <= GrooveTopZ, "spigot top z %.2f below the groove's end z %.2f: the plate, not the thread, stops it" % (SpigotTopZ, GrooveTopZ))
    # gas path
    env = Cyl(P["CupR"] - 0.01, DiscBotZ - 0.5, TopZ + 0.5)
    fluid = env.cut(cup.fuse(face).fuse(plate))
    top = V(0, 0, TopZ - 0.5)
    main = [s for s in fluid.Solids if s.isInside(top, 1e-4, True)]
    if len(main) != 1:
        Say(False, "gas path: %d volumes contain the tap" % len(main))
    else:
        g = main[0]
        reach = [g.isInside(V(x, y, DiscBotZ + 0.2), 1e-4, True) for x, y in holes]
        Say(all(reach), "gas path: one volume of %.2f cm^3 joins the tap to %d of %d face holes" % (g.Volume / 1000, sum(reach), len(holes)))
    sight = Cyl(P["InletD"] / 2 + 1.0, CapBotZ + 0.05, CapTopZ - 0.05)
    Say(abs(face.common(sight).Volume - sight.Volume) < 1e-3, "baffle cap covers the inlet's projection with 1.0 to spare")
    Say(CupBoreR - P["BaffleR"] >= 3 * P["BaffleGap"], "baffle edge to the plenum wall %.2f (>= 3 x the baffle gap)" % (CupBoreR - P["BaffleR"]))
    # flow
    holeA = len(holes) * math.pi * (P["HoleD"] / 2000) ** 2
    fieldA = math.pi * ((BoreR - 0.6) / 1000) ** 2
    inletA = math.pi * (P["InletD"] / 2000) ** 2
    exitA = 2 * math.pi * (P["BaffleR"] / 1000) * (P["BaffleGap"] / 1000)
    rho = P["ArgonDensity"]
    for lpm in P["FlowsLpm"]:
        q = lpm / 60000
        vh = q / holeA
        dp = 0.5 * rho * vh ** 2 / P["HoleCd"] ** 2
        pb = 0.5 * rho * (q / exitA) ** 2
        log.append("  flow %.0f L/min: inlet %.1f m/s, baffle exit %.2f m/s (%.1f Pa), each hole %.2f m/s, hole drop %.1f Pa, "
                   "mean over the face %.0f mm/s" % (lpm, q / inletA, q / exitA, pb, vh, dp, 1000 * q / fieldA))
        Say(dp >= 2 * pb, "  at %.0f L/min the hole drop is %.1f x the baffle exit's dynamic pressure (>= 2 spreads the flow)" % (lpm, dp / pb))
    # shading by the disc below the plate, for the four nearest and the four corner LEDs
    h, H = P["DiscT"], P["DiscT"] + P["GapToSubstrate"]
    for R in (P["LedPitch"], P["LedPitch"] * math.sqrt(2)):
        xs = (R * (1 - h / H) - P["DiscR"]) * H / h
        Say(xs >= 110.0, "shading: an LED at r %.1f (plate %.1f above the substrate) is shadowed by the disc only beyond %.0f mm on "
            "the far side, outside a 220 mm substrate" % (R, H, xs))
    # printability
    ctl = Part.makeBox(4, 4, 6).fuse(Part.makeBox(9, 4, 1, V(0, 0, 3)))
    cw, ca = Overhangs(ctl)
    Say(ca > 1.0 and cw < 1.0, "control: the overhang test flags a flat ledge (%.1f deg, %.1f mm^2)" % (cw, ca))
    for name, s, flip in (("Cup", cup, True), ("FacePart", face, False)):
        pp = PrintPose(s, flip)
        worst, area = Overhangs(pp)
        bb = pp.optimalBoundingBox()
        Say(area < 1.0 and max(bb.XLength, bb.YLength) <= P["BedXY"],
            "%s prints %s with no support: steepest down-facing surface %.1f deg from straight down (limit %.0f), area beyond "
            "the limit %.2f mm^2; %.1f x %.1f x %.1f mm" % (name, "top face down" if flip else "disc down", worst,
                                                            90 - P["OverhangDeg"], area, bb.XLength, bb.YLength, bb.ZLength))
    log.append("  holes: %d x %.1f mm on a %.1f mm hexagonal pitch, r %.1f to %.1f" % (
        len(holes), P["HoleD"], P["HolePitch"], P["StalkR"] + P["HoleD"] / 2 + 0.6, BoreR - P["HoleD"] / 2 - 0.6))
    log.append("  height: cup %.1f above the plate top (fitting hex not included); disc %.1f below the plate underside" % (TopZ - Tp, P["DiscT"]))
    log.append("Checks failing: %d" % bad)
    return bad


def Section(cup, face, plate, fitting, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
    except ImportError:
        print("  matplotlib missing: no section PNG")
        return
    fig, ax = plt.subplots(figsize=(11, 6))
    for s, col in ((plate, "#DDDDDD"), (cup, "#77AADD"), (face, "#44BB99"), (fitting, "#EEDD88")):
        for w in s.slice(V(0, 1, 0), 0.0):
            if w.isClosed():
                pts = w.discretize(Deflection=0.01)
                ax.add_patch(Polygon([(p.x, p.z) for p in pts], closed=True, fc=col, ec="#222222", lw=0.5))
    ax.annotate("", xy=(0, CapTopZ + 0.1), xytext=(0, TopZ + 7), arrowprops=dict(arrowstyle="->", color="#AA3377", lw=1.4))
    for x in (-6, 6):
        ax.annotate("", xy=(x, DiscBotZ - 5), xytext=(x, DiscBotZ), arrowprops=dict(arrowstyle="->", color="#AA3377", lw=1.2))
    for x in (-P["LedPitch"], P["LedPitch"]):
        ax.plot([x, x], [Tp + 1, Tp + 8], color="#4477AA", lw=1.0)
        ax.text(x, Tp + 8.5, "LED r %.0f" % abs(x), color="#4477AA", fontsize=8, ha="center")
    for x in (-FreeHalf, FreeHalf):
        ax.plot([x, x], [Tp, TopZ + 4], color="#4477AA", lw=0.8, ls=":")
    ax.text(0, TopZ + 9.5, "dotted: free centre square +-%.0f mm above the plate" % FreeHalf, color="#4477AA", fontsize=8, ha="center")
    ax.axhline(DiscBotZ - P["GapToSubstrate"], color="#4477AA", lw=1.0, ls="--")
    ax.text(-44, DiscBotZ - P["GapToSubstrate"] + 0.6, "substrate (gap assumed %.0f mm)" % P["GapToSubstrate"], color="#4477AA", fontsize=8)
    ax.set_xlim(-46, 46)
    ax.set_ylim(DiscBotZ - P["GapToSubstrate"] - 2, TopZ + 12)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm), along an LED row")
    ax.set_ylabel("z (mm), 0 = LED plate underside")
    ax.set_title("%s, section y = 0: cup (blue), face part (green), LED plate 1/16 in (grey), PC4-M10 fitting (yellow)" % Stem, fontsize=9)
    ax.grid(True, lw=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def Main():
    holes = FaceHoles()
    face = BuildFace(holes)
    cup = BuildCup()
    plate, fitting = BuildRefs()
    log = ["%s: UV lid argon diffuser (issue 251), ASA by FFF, 0.4 mm nozzle" % Stem,
           "  z: plate %.4f thick; spigot top %.2f, groove end %.2f, roof %.2f, baffle cap %.2f..%.2f, tap %.2f..%.2f" % (
               Tp, SpigotTopZ, GrooveTopZ, RoofZ, CapBotZ, CapTopZ, TapBotZ, TopZ),
           "  thread: pitch %.1f, 90 deg, spigot crest r %.2f root r %.2f; cup bore r %.2f groove r %.2f" % (
               P["Pitch"], P["SpigotCrestR"], RootR, CupBoreR, GrooveR)]
    bad = Check(cup, face, plate, holes, log)
    print("\n".join(log))
    if bad:
        raise SystemExit("lid diffuser checks failed")
    os.makedirs(OutDir, exist_ok=True)
    for name, s, flip in (("Cup", cup, True), ("FacePart", face, False)):
        pp = PrintPose(s, flip)
        path = os.path.join(OutDir, "%s-%s.step" % (Stem, name))
        pp.exportStep(path)
        back = Part.read(path)
        if len(back.Solids) != 1 or abs(back.Volume - pp.Volume) > 1e-3 * pp.Volume:
            raise RuntimeError("%s fails after the STEP round trip" % name)
        print("  wrote %s" % os.path.basename(path))
    doc = FreeCAD.newDocument("LidDiffuser")
    objs = []
    for n, s in (("Cup", cup), ("FacePart", face), ("LedPlate", plate), ("FittingPC4M10", fitting)):
        o = doc.addObject("Part::Feature", n)
        o.Shape = s
        objs.append(o)
    doc.recompute()
    import Import
    Import.export(objs, os.path.join(OutDir, Stem + "_Assembly.step"))
    doc.saveAs(os.path.join(OutDir, Stem + ".FCStd"))
    FreeCAD.closeDocument(doc.Name)
    with open(os.path.join(OutDir, Stem + "_Checks.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(log) + "\n")
    Section(cup, face, plate, fitting, os.path.join(OutDir, Stem + "_Section.png"))
    print("Saved to", OutDir)


Main()
