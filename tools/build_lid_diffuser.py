# Builds the UV lid's argon diffuser (issue 251) as two FFF ASA parts that print without supports: a cup that sits
# in the free centre position of the lid's 8-LED acrylic plate and takes a PC4-M10 push-in fitting for 4 x 2 mm PTFE,
# and a face plate of 1 mm holes that carries a mushroom baffle in front of the inlet. The concept sheet is
# docs/spincoater/lid_diffuser_sketch.svg (tools/draw_lid_diffuser.py); this file turns it into printable parts.
# Two changes from that sheet, both for printing: the cup has a flat top with the M10 tap in it (no boss), so it
# prints top face down and the flange needs no support; and the baffle stands on a 45 deg stalk on the face plate
# instead of three thin posts, so it prints face plate down.
#
# Run with FreeCAD's console:  freecadcmd tools/build_lid_diffuser.py
# Writes CAD/Spincoater/Lid Diffuser/: one STEP per printed part in print orientation, the assembly with the LED
# plate stub and the fasteners (_Assembly.step), the FCStd, _Checks.txt and _Section.png. It refuses to write
# anything when a check fails.
#
# Gas path: PTFE tube -> push-in fitting -> 2.5 mm inlet -> the jet hits the baffle 1 mm below the plenum roof,
# turns and spreads radially -> plenum -> face holes -> down onto the substrate. The baffle keeps the inlet jet off
# the holes in line with it; the holes' pressure drop then spreads the flow over the face.
#
# Frame: z = 0 at the underside of the LED plate, z up; the axis is the lid's centre. Units mm. Assumed until
# measured (the parameters say so): the plate thickness, its centre hole, the gap to the substrate, the LED ring
# radius, the fitting's thread and how much height the lid leaves above the plate.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
OutDir = os.path.join(Root, "CAD", "Spincoater", "Lid Diffuser")
Stem = "LidDiffuser_v20261124-A"

P = dict(
    # LED plate (assumed: 1/8 in acrylic with a centre hole opened to fit)
    PlateThick=3.0, PlateHoleR=22.5, PlateStubR=40.0,
    LedRingR=50.0,         # ASSUMED radius of the 8 LEDs; only for the shading estimate
    GapToSubstrate=15.0,   # ASSUMED face to substrate
    # Cup
    BodyR=22.0,            # below the flange, through the plate hole
    FlangeR=31.0,          # rests on the plate's top face
    TopZ=16.0,             # flat top of the cup: the fitting's hex seats here
    CavityR=16.5,          # plenum
    RoofZ=6.0,             # plenum roof
    OpenZ=0.0,             # cup's open face, flush with the plate underside, so only the face plate hangs below
                           # it and the puck shades the LEDs as little as it can
    TapD=9.0, TapDepth=6.0,   # M10 x 1 tap drill and thread depth; tap it after printing
    InletD=2.5,            # bore from the tap's 90 deg point into the plenum
    FlangeScrewR=26.5, FlangeScrewD=3.4, FlangeScrewAngles=(0.0, 120.0, 240.0),   # 3 x M3 x 20 with nuts below the plate
    PilotD=1.7, PilotDepth=6.0,   # M2 self-tapping pilots in the cup's open face for the face plate
    # Face plate
    FaceThick=2.0,
    FaceScrewR=19.5, FaceScrewD=2.4, FaceScrewAngles=(60.0, 180.0, 300.0),
    CsinkD=4.0,            # 90 deg countersink for M2 flat heads (ISO 10642 dk 3.8)
    HoleD=1.0,             # face holes: printed at 1.0, then drilled through with a 1.0 bit
    HolePitch=4.0, HoleFieldR=15.0,
    # Baffle (mushroom on the face plate)
    BaffleR=7.0, BaffleGap=1.0, BaffleCapT=1.2,   # cap top BaffleGap below the roof; the stalk widens at 45 deg to it
    # Process and checks
    MinWall=1.2,           # three 0.4 mm perimeters
    PlateHoleClear=0.25,   # radial play of the body in the plate hole
    OverhangDeg=45.0,      # steepest overhang from vertical printed without support
    BedXY=256.0,           # Bambu P1S
    ArgonDensity=1.66, HoleCd=0.6, FlowsLpm=(2.0, 5.0),
)

FaceBotZ = P["OpenZ"] - P["FaceThick"]
CapTopZ = P["RoofZ"] - P["BaffleGap"]
CapBotZ = CapTopZ - P["BaffleCapT"]
StalkR = P["BaffleR"] - (CapBotZ - P["OpenZ"])   # 45 deg cone from the face plate's top to the cap
TapBotZ = P["TopZ"] - P["TapDepth"]
ConeBotZ = TapBotZ - (P["TapD"] - P["InletD"]) / 2   # 90 deg point from the tap to the inlet


def Polar(r, a):
    t = math.radians(a)
    return r * math.cos(t), r * math.sin(t)


def Cyl(r, z0, z1, x=0.0, y=0.0):
    return Part.makeCylinder(r, z1 - z0, V(x, y, z0))


def Cone(r0, r1, z0, z1, x=0.0, y=0.0):
    return Part.makeCone(r0, r1, z1 - z0, V(x, y, z0))


def FaceHoles():
    """Hole centres on a hexagonal pitch inside HoleFieldR, clear of the stalk's foot."""
    out = []
    pitch = P["HolePitch"]
    row = pitch * math.sqrt(3) / 2
    n = int(P["HoleFieldR"] / row) + 1
    for j in range(-n, n + 1):
        off = pitch / 2 if j % 2 else 0.0
        for i in range(-n - 1, n + 2):
            x, y = i * pitch + off, j * row
            r = math.hypot(x, y)
            if r <= P["HoleFieldR"] and r >= StalkR + P["HoleD"] / 2 + 0.6:
                out.append((x, y))
    return out


def BuildCup():
    cup = Cyl(P["FlangeR"], P["PlateThick"], P["TopZ"]).fuse(Cyl(P["BodyR"], P["OpenZ"], P["PlateThick"] + 0.01))
    voids = [Cyl(P["CavityR"], P["OpenZ"] - 1, P["RoofZ"]),
             Cyl(P["TapD"] / 2, TapBotZ, P["TopZ"] + 1),
             Cone(P["InletD"] / 2, P["TapD"] / 2, ConeBotZ, TapBotZ),
             Cyl(P["InletD"] / 2, P["RoofZ"] - 0.5, ConeBotZ + 0.01)]
    for a in P["FlangeScrewAngles"]:
        x, y = Polar(P["FlangeScrewR"], a)
        voids.append(Cyl(P["FlangeScrewD"] / 2, P["PlateThick"] - 1, P["TopZ"] + 1, x, y))
    for a in P["FaceScrewAngles"]:
        x, y = Polar(P["FaceScrewR"], a)
        voids.append(Cyl(P["PilotD"] / 2, P["OpenZ"] - 1, P["OpenZ"] + P["PilotDepth"], x, y))
    for v in voids:
        cup = cup.cut(v)
    return cup.removeSplitter()


def BuildFace(holes):
    face = Cyl(P["BodyR"], FaceBotZ, P["OpenZ"])
    face = face.fuse(Cone(StalkR, P["BaffleR"], P["OpenZ"] - 0.01, CapBotZ))
    face = face.fuse(Cyl(P["BaffleR"], CapBotZ - 0.01, CapTopZ))
    for x, y in holes:
        face = face.cut(Cyl(P["HoleD"] / 2, FaceBotZ - 1, P["OpenZ"] + 0.01, x, y))
    cs = P["CsinkD"] / 2
    for a in P["FaceScrewAngles"]:
        x, y = Polar(P["FaceScrewR"], a)
        face = face.cut(Cyl(P["FaceScrewD"] / 2, FaceBotZ - 1, P["OpenZ"] + 1, x, y))
        face = face.cut(Cone(cs + 0.5, P["FaceScrewD"] / 2, FaceBotZ - 0.5, FaceBotZ + cs - P["FaceScrewD"] / 2, x, y))
    return face.removeSplitter()


def BuildHardware():
    """Reference parts: the LED plate stub, M2 and M3 screws as plain cylinders, M3 nuts, the fitting's hex."""
    plate = Cyl(P["PlateStubR"], 0.0, P["PlateThick"]).cut(Cyl(P["PlateHoleR"], -1, P["PlateThick"] + 1))
    for a in P["FlangeScrewAngles"]:
        x, y = Polar(P["FlangeScrewR"], a)
        plate = plate.cut(Cyl(P["FlangeScrewD"] / 2, -1, P["PlateThick"] + 1, x, y))
    hw = {}
    for k, a in enumerate(P["FlangeScrewAngles"]):
        x, y = Polar(P["FlangeScrewR"], a)
        s = Cyl(1.5, -2.4 - 1.0, P["TopZ"]).fuse(Cyl(2.75, P["TopZ"], P["TopZ"] + 3.0))
        s.translate(V(x, y, 0))
        hw["M3Screw%d" % k] = s
        nut = Part.makePolygon([V(x + 3.175 * math.cos(math.radians(60 * i)), y + 3.175 * math.sin(math.radians(60 * i)), 0)
                                for i in range(7)])
        n = Part.Face(nut).extrude(V(0, 0, -2.4)).cut(Cyl(1.5, -3, 1, x, y))
        hw["M3Nut%d" % k] = n
    for k, a in enumerate(P["FaceScrewAngles"]):
        x, y = Polar(P["FaceScrewR"], a)
        cs = P["CsinkD"] / 2 - 0.1
        hw["M2Screw%d" % k] = Cone(cs, 1.0, FaceBotZ, FaceBotZ + cs - 1.0, x, y).fuse(
            Cyl(0.85, FaceBotZ + cs - 1.0 - 0.01, FaceBotZ + 8.0, x, y))
    hexR = 7.0
    hx = Part.Face(Part.makePolygon([V(hexR * math.cos(math.radians(60 * i + 30)), hexR * math.sin(math.radians(60 * i + 30)),
                                       P["TopZ"]) for i in range(7)])).extrude(V(0, 0, 4.0))
    hw["FittingHex"] = hx.cut(Cyl(2.05, P["TopZ"] - 1, P["TopZ"] + 6))
    hw["FittingThread"] = Cyl(5.0, TapBotZ + 0.5, P["TopZ"]).cut(Cyl(2.05, TapBotZ, P["TopZ"] + 1))
    return plate, hw


def Overhangs(shape):
    """Faces of a part in print orientation (bed at z = 0) that point down more steeply than OverhangDeg from
    vertical and do not lie on the bed. Returns the worst angle from vertical-down and the area involved."""
    lim = math.cos(math.radians(P["OverhangDeg"])) + 1e-3
    worst, area = 90.0, 0.0   # worst: the steepest down-facing sample found, beyond the limit or not
    for f in shape.Faces:
        if f.BoundBox.ZMax < 1e-3:
            continue
        u0, u1, v0, v1 = f.ParameterRange
        bad = False
        for i in range(5):
            for j in range(5):
                u = u0 + (u1 - u0) * (i + 0.5) / 5
                v = v0 + (v1 - v0) * (j + 0.5) / 5
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
    s.translate(V(0, 0, -s.BoundBox.ZMin))
    return s


def Check(cup, face, plate, hw, holes, log):
    bad = 0

    def Say(ok, text):
        nonlocal bad
        bad += not ok
        log.append(("  ok   " if ok else "  FAIL ") + text)

    for name, s in (("Cup", cup), ("FacePlate", face)):
        Say(len(s.Solids) == 1 and s.isValid(), "%s: %d solid, valid %s, %.1f cm^3" % (name, len(s.Solids), s.isValid(), s.Volume / 1000))
    # fit in the plate and on the face
    Say(P["PlateHoleR"] - P["BodyR"] >= P["PlateHoleClear"], "body r %.2f in the plate hole r %.2f: %.2f radial play"
        % (P["BodyR"], P["PlateHoleR"], P["PlateHoleR"] - P["BodyR"]))
    ov = cup.common(face).Volume
    Say(ov < 1e-3 and cup.distToShape(face)[0] < 1e-3, "face plate seats on the cup's open face: overlap %.4f" % ov)
    Say(cup.common(plate).Volume < 1e-3 and cup.distToShape(plate)[0] < 1e-3,
        "flange rests on the plate top: overlap %.4f, gap %.3f" % (cup.common(plate).Volume, cup.distToShape(plate)[0]))
    for n, s in hw.items():
        if n.startswith("Fitting"):
            continue
        o = max(s.common(cup).Volume, s.common(face).Volume, s.common(plate).Volume)
        Say(o < 0.02 or n.startswith("M2"), "%s overlap with the parts %.3f mm^3%s" % (
            n, o, " (self-tapping thread in the pilot)" if n.startswith("M2") else ""))
    # walls
    w1 = P["FaceScrewR"] - P["PilotD"] / 2 - P["CavityR"]
    w2 = P["BodyR"] - P["FaceScrewR"] - P["PilotD"] / 2
    Say(min(w1, w2) >= P["MinWall"], "M2 pilot walls: %.2f to the plenum, %.2f to the outside" % (w1, w2))
    w3 = P["FlangeR"] - P["FlangeScrewR"] - P["FlangeScrewD"] / 2
    Say(w3 >= P["MinWall"], "M3 hole to the flange edge %.2f" % w3)
    Say(P["FlangeScrewR"] - 3.175 >= P["PlateHoleR"] + 0.5, "M3 nut (6.35 across corners) bears on the plate, its nearest corner %.2f past the hole edge"
        % (P["FlangeScrewR"] - 3.175 - P["PlateHoleR"]))
    roof = ConeBotZ - P["RoofZ"]
    Say(roof >= 0.5, "inlet bore %.2f long between the tap's point and the plenum roof (z %.1f)" % (roof, P["RoofZ"]))
    capFace = P["CavityR"] - P["BaffleR"]
    Say(capFace >= 3 * P["BaffleGap"], "baffle edge to the plenum wall %.1f (>= 3 x the baffle gap, so the radial jet spreads)" % capFace)
    Say(abs(P["RoofZ"] - CapTopZ - P["BaffleGap"]) < 1e-6 and StalkR > 1.5,
        "baffle cap r %.1f, top %.2f below the roof; stalk r %.2f at the face, cap underside z %.2f" % (
            P["BaffleR"], P["RoofZ"] - CapTopZ, StalkR, CapBotZ))
    # gas path: the fluid inside the assembly is one connected volume from the tap to every face hole
    env = Cyl(P["BodyR"] - 0.01, FaceBotZ - 0.5, P["TopZ"] + 0.5)
    fluid = env.cut(cup.fuse(face))
    top = V(0, 0, P["TopZ"] - 0.5)
    main = [s for s in fluid.Solids if s.isInside(top, 1e-4, True)]
    if len(main) != 1:
        Say(False, "gas path: %d volumes contain the tap" % len(main))
    else:
        g = main[0]
        reach = [g.isInside(V(x, y, FaceBotZ + 0.2), 1e-4, True) for x, y in holes]
        Say(all(reach), "gas path: one volume of %.2f cm^3 joins the tap to %d of %d face holes" % (g.Volume / 1000, sum(reach), len(holes)))
    sight = Cyl(P["InletD"] / 2 + 1.0, CapBotZ + 0.05, CapTopZ - 0.05)
    Say(abs(face.common(sight).Volume - sight.Volume) < 1e-3,
        "baffle cap covers the inlet's projection with 1.0 to spare: the jet cannot reach the face holes directly")
    # flow numbers
    holeA = len(holes) * math.pi * (P["HoleD"] / 2000) ** 2
    fieldA = math.pi * (P["HoleFieldR"] / 1000) ** 2
    inletA = math.pi * (P["InletD"] / 2000) ** 2
    exitA = 2 * math.pi * (P["BaffleR"] / 1000) * (P["BaffleGap"] / 1000)
    rho = P["ArgonDensity"]
    for lpm in P["FlowsLpm"]:
        q = lpm / 60000
        vh = q / holeA
        dp = 0.5 * rho * vh ** 2 / P["HoleCd"] ** 2
        pb = 0.5 * rho * (q / exitA) ** 2
        log.append("  flow %.0f L/min: inlet %.1f m/s, baffle exit %.2f m/s (%.1f Pa), each hole %.2f m/s, hole drop %.1f Pa, "
                   "mean over the field %.0f mm/s" % (lpm, q / inletA, q / exitA, pb, vh, dp, 1000 * q / fieldA))
        Say(dp >= 2 * pb, "  at %.0f L/min the hole drop is %.1f x the baffle exit's dynamic pressure (>= 2 spreads the flow)" % (lpm, dp / pb))
    # shading: the part below the plate is a disc of BodyR standing out by OpenZ - FaceBotZ + |OpenZ|
    h = -FaceBotZ
    H = h + P["GapToSubstrate"]
    R, r = P["LedRingR"], P["BodyR"]
    if R > r:
        xs = (R * (1 - h / H) - r) * H / h
        log.append("  shading (assumed LED ring r %.0f, plate %.0f above the substrate): an LED's shadow of the puck starts %.0f mm "
                   "beyond the axis on the far side" % (R, H, xs))
        Say(xs >= 110.0, "  that is outside a 220 mm substrate (r 110); recheck once the LED ring is measured")
    # control: the overhang test must flag a 5 mm ledge 3 mm above the bed
    ctl = Part.makeBox(4, 4, 6).fuse(Part.makeBox(9, 4, 1, V(0, 0, 3)))
    cw, ca = Overhangs(ctl)
    Say(ca > 1.0 and cw < 1.0, "control: overhang test flags a flat ledge (%.1f deg, %.1f mm^2)" % (cw, ca))
    # printability, each part in its print pose
    for name, s, flip in (("Cup", cup, True), ("FacePlate", face, False)):
        pp = PrintPose(s, flip)
        worst, area = Overhangs(pp)
        bb = pp.BoundBox
        Say(area < 1.0 and max(bb.XLength, bb.YLength) <= P["BedXY"],
            "%s prints %s with no support: steepest down-facing surface %.1f deg from straight down (limit %.0f), area beyond the limit %.2f mm^2; %.0f x %.0f x %.1f mm"
            % (name, "top face down" if flip else "face down", worst, 90 - P["OverhangDeg"], area, bb.XLength, bb.YLength, bb.ZLength))
    log.append("  holes: %d x %.1f mm on a %.0f mm hexagonal pitch inside r %.0f (outside r %.1f, the stalk's foot)" % (
        len(holes), P["HoleD"], P["HolePitch"], P["HoleFieldR"], StalkR + P["HoleD"] / 2 + 0.6))
    log.append("  height: %.1f above the plate top (fitting hex not included), %.1f below the plate underside" % (
        P["TopZ"] - P["PlateThick"], -FaceBotZ))
    log.append("Checks failing: %d" % bad)
    return bad


def Section(cup, face, plate, hw, path):
    """Section at y = 0 with matplotlib, Paul Tol light fills."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
    except ImportError:
        print("  matplotlib missing: no section PNG")
        return
    fig, ax = plt.subplots(figsize=(11, 5.5))
    items = [(plate, "#DDDDDD"), (cup, "#77AADD"), (face, "#44BB99")] + [
        (s, "#EEDD88" if n.startswith("Fitting") else "#BBBBBB") for n, s in hw.items()]
    for s, col in items:
        sec = s.slice(V(0, 1, 0), 0.0)
        for w in sec:
            if not w.isClosed():
                continue
            pts = w.discretize(Deflection=0.02)
            ax.add_patch(Polygon([(p.x, p.z) for p in pts], closed=True, fc=col, ec="#222222", lw=0.6))
    ax.annotate("", xy=(0, CapTopZ + 0.1), xytext=(0, P["TopZ"] + 6),
                arrowprops=dict(arrowstyle="->", color="#AA3377", lw=1.4))
    for x in (-12, 12):
        ax.annotate("", xy=(x, FaceBotZ - 5), xytext=(x, FaceBotZ),
                    arrowprops=dict(arrowstyle="->", color="#AA3377", lw=1.2))
    ax.axhline(FaceBotZ - P["GapToSubstrate"], color="#4477AA", lw=1.0, ls="--")
    ax.text(-38, FaceBotZ - P["GapToSubstrate"] + 0.6, "substrate (gap assumed %.0f mm)" % P["GapToSubstrate"], color="#4477AA", fontsize=8)
    ax.set_xlim(-42, 42)
    ax.set_ylim(FaceBotZ - P["GapToSubstrate"] - 2, P["TopZ"] + 8)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm), 0 = LED plate underside")
    ax.set_title("%s, section y = 0: cup (blue), face plate with baffle (green), LED plate (grey), PC4-M10 fitting (yellow)" % Stem, fontsize=9)
    ax.grid(True, lw=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def Main():
    holes = FaceHoles()
    cup = BuildCup()
    face = BuildFace(holes)
    plate, hw = BuildHardware()
    log = ["%s: UV lid argon diffuser (issue 251), ASA by FFF, 0.4 mm nozzle" % Stem]
    bad = Check(cup, face, plate, hw, holes, log)
    print("\n".join(log))
    if bad:
        raise SystemExit("lid diffuser checks failed")
    os.makedirs(OutDir, exist_ok=True)
    for name, s, flip in (("Cup", cup, True), ("FacePlate", face, False)):
        pp = PrintPose(s, flip)
        path = os.path.join(OutDir, "%s-%s.step" % (Stem, name))
        pp.exportStep(path)
        back = Part.read(path)
        if len(back.Solids) != 1 or abs(back.Volume - pp.Volume) > 1e-3 * pp.Volume:
            raise RuntimeError("%s fails after the STEP round trip" % name)
        print("  wrote %s" % os.path.basename(path))
    doc = FreeCAD.newDocument("LidDiffuser")
    objs = []
    for n, s in [("Cup", cup), ("FacePlate", face), ("LedPlateStub", plate)] + sorted(hw.items()):
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
    Section(cup, face, plate, hw, os.path.join(OutDir, Stem + "_Section.png"))
    print("Saved to", OutDir)


Main()
