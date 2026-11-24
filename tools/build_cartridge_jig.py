# Builds the filter cartridge assembly jig (issue 253): a bench base that holds the collar by its six rim notches,
# as the collar spanner does, with its bore open under the CNT area. One person then assembles a cartridge with both
# hands on the body: collar into the jig, filter into the collar, body down until its bayonet legs drop over the lugs,
# then the body turns clockwise (seen from above) to lock. The jig needs no guide for the body: once the body rests on
# the lug tops its sleeve is already inside the collar bore (0.25 mm radial play), which centres it.
#
# Run with FreeCAD's console:  freecadcmd tools/build_cartridge_jig.py
# Writes CAD/Filter Cartridge/Assembly jig/: the jig in print orientation (STEP) and a model of the jig with a
# cartridge in it (FCStd). The procedure is that folder's README.md.
#
# The cartridge geometry comes from tools/build_filter_cartridge.py (its P dict and Build()), printed-flange
# variant, with the collar as printed (Squeeze from PrintSqueezes). Frame: the cartridge generator's, z = 0 at
# the mask bottom, so the collar's bottom (the flange's underside) is at zc = StencilT + SeatGap. Units mm.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))

# ---- load the cartridge generator's parameters and builders without running its Main()
Src = open(os.path.join(Here, "build_filter_cartridge.py"), encoding="utf-8").read()
Gen = {"__file__": os.path.join(Here, "build_filter_cartridge.py")}
exec(compile(Src[:Src.rindex("\nMain()")], "build_filter_cartridge.py", "exec"), Gen)
P, Build, Annulus, Sector, Rotated, GeometryErrors, ArcDeg, LiftAt = (
    Gen[n] for n in ("P", "Build", "Annulus", "Sector", "Rotated", "GeometryErrors", "ArcDeg", "LiftAt"))

J = dict(
    RingID=80.0,           # under the flange from r 40: clear of the CNT film (r 37.5); the bore is open to the bench
    RingH=2.0,             # tooth ring above the base; its top carries the flange (under the filter band) while it is clamped
    BaseT=4.0,
    BaseOD=150.0,
    ToothFull=1.0,         # each tooth keeps its full width up to here above the collar bottom, then narrows to its tip
                           # (the spanner's teeth narrow from 0.7): the locking torque bears on 0.7 mm of flank, above the
                           # 0.3 mm mouth flare of each notch, instead of 0.5
    HoleR=66.0,            # bench screw holes (M4)
    HoleAngles=(0.0, 90.0, 180.0, 270.0),
    HoleD=4.5,
    ArrowR=68.0,           # engraved arrow on the base top: the way the body turns to lock
    ArrowSpan=(150.0, 115.0),   # from, to (deg): clockwise seen from above
    ArrowW=1.6,
    ArrowDepth=0.6,
    PrintBed=256.0,        # Bambu P1S
)
Out = os.path.join(os.path.dirname(Here), "CAD", "Filter Cartridge", "Assembly jig")
JigName = "CartridgeAssemblyJig"


def Cartridge():
    """The printed-flange cartridge as assembled, with the collar as printed. Returns (parts, levels, p)."""
    p = dict(P)
    p["PrintedFlange"] = True
    parts, lv = Build(p)
    q = dict(p)
    q["Squeeze"] = p["PrintSqueezes"][0]
    parts["CollarPrinted"] = Build(q)[0]["Collar"]
    return parts, lv, p


def Teeth(p, zTop):
    """The spanner's teeth (BuildSpanner in the cartridge generator: the same notch clearances, lead-in and tip
    height), standing on a ring whose top is zTop, kept full width up to ToothFull."""
    rc, sc = p["ToothRadialClear"], p["ToothSideClear"]
    notchMidR = (p["CollarID"] + p["CollarOD"]) / 4
    toothDeg = ArcDeg(p["NotchWidth"] - 2 * sc, notchMidR)
    tipDeg = ArcDeg(p["NotchWidth"] - 2 * sc - 2 * p["ToothTipNarrow"], notchMidR)
    zTip = zTop + p["NotchDepth"] - 0.2              # 0.2 short of the notch roof
    out = []
    for i in range(p["NotchCount"]):
        a = i * 360.0 / p["NotchCount"]
        zFull = zTop + J["ToothFull"]
        out.append(Sector(p["CollarID"] / 2 + rc, p["CollarOD"] / 2 - rc, zTop - 0.5, zFull,
                          a - toothDeg / 2, a + toothDeg / 2))
        out.append(Sector(p["CollarID"] / 2 + rc, p["CollarOD"] / 2 - rc, zFull - 0.1, zTip,
                          a - tipDeg / 2, a + tipDeg / 2))
    return out


def BuildJig(p, lv):
    zc = lv["CartridgeBottom"]
    zRing0 = zc - J["RingH"]
    zBase0 = zRing0 - J["BaseT"]
    base = Annulus(J["RingID"] / 2, J["BaseOD"] / 2, zBase0, zRing0)
    ring = Annulus(J["RingID"] / 2, p["CollarOD"] / 2 - 0.25, zRing0, zc)
    jig = base.fuse(ring)
    for t in Teeth(p, zc):
        jig = jig.fuse(t)
    for a in J["HoleAngles"]:
        h = Part.makeCylinder(J["HoleD"] / 2, J["BaseT"] + 2, V(J["HoleR"], 0, zBase0 - 1))
        jig = jig.cut(Rotated(h, a))
    # arrow groove: an arc and a head at its clockwise end
    a0, a1 = J["ArrowSpan"]
    r, w, d = J["ArrowR"], J["ArrowW"], J["ArrowDepth"]
    arc = Sector(r - w / 2, r + w / 2, zRing0 - d, zRing0 + 1, min(a0, a1) + 2.0, max(a0, a1))
    t = math.radians(min(a0, a1))
    tip = V(r * math.cos(t), r * math.sin(t), 0)
    back = math.radians(min(a0, a1) + 6.0)
    pts = [tip, V((r - 2.5) * math.cos(back), (r - 2.5) * math.sin(back), 0),
           V((r + 2.5) * math.cos(back), (r + 2.5) * math.sin(back), 0), tip]
    head = Part.Face(Part.makePolygon(pts)).extrude(V(0, 0, d + 1))
    head.translate(V(0, 0, zRing0 - d))
    jig = jig.cut(arc).cut(head)
    return jig.removeSplitter(), dict(zBase0=zBase0, zRing0=zRing0)


def Moved(shape, rot=0.0, dz=0.0, dx=0.0):
    s = shape.copy()
    if rot:
        s.rotate(V(0, 0, 0), V(0, 0, 1), rot)
    if dz or dx:
        s.translate(V(dx, 0, dz))
    return s


def Check(jig, k, parts, lv, p):
    bad = 0
    collar, body, plate = parts["CollarPrinted"], parts["Body"], parts["Plate"]
    squeeze = p["PrintSqueezes"][0]
    print("Jig: %d solid, valid %s, %.1f x %.1f x %.1f mm (bed %.0f)" % (
        len(jig.Solids), jig.isValid(), jig.BoundBox.XLength, jig.BoundBox.YLength, jig.BoundBox.ZLength, J["PrintBed"]))
    err = GeometryErrors(jig)
    bad += len(jig.Solids) != 1 or not jig.isValid() or bool(err) or max(jig.BoundBox.XLength, jig.BoundBox.YLength) > J["PrintBed"]
    # 1. the collar as printed sits on the ring, teeth in its notches, and cannot turn
    ov = jig.common(collar).Volume
    gap = jig.distToShape(collar)[0]
    turned = [jig.common(Moved(collar, rot=s * 0.5)).Volume for s in (1, -1)]
    lifted = jig.common(Moved(collar, dz=-0.05)).Volume
    print("  collar on the jig: overlap %.4f, gap %.3f (the flange rests on the ring); turned 0.5 deg either way: "
          "overlap %.3f / %.3f (both must be > 0); 0.05 lower: %.3f (must be > 0)" % (ov, gap, turned[0], turned[1], lifted))
    bad += ov > 1e-3 or gap > 0.01 or min(turned) <= 0 or lifted <= 0
    # 2. the body along the whole twist, at the height the bayonet holds it; locked it sits Squeeze lower than nominal
    # the sleeve face clamps the filter band onto the flange right above the ring: that gap is the flange, measured
    # on its own; everything else of the jig must keep 0.3 from the body
    zc = lv["CartridgeBottom"]
    under = Annulus(p["SleeveID"] / 2, p["CollarOD"] / 2 - 0.2, zc - 0.5, zc + 0.001)
    rest = jig.cut(under)
    worst, dmin, dring = 0.0, 99.0, 99.0
    phi = -p["TwistDeg"]
    while phi <= 1e-9:
        b = Moved(body, rot=-phi, dz=(p["RampRise"] - LiftAt(p, phi)) - squeeze)
        worst = max(worst, jig.common(b).Volume)
        dmin = min(dmin, rest.distToShape(b)[0])
        dring = min(dring, jig.common(under).distToShape(b)[0])
        phi += 1.0
    print("  body along the twist (entry %+.0f deg to lock, clockwise seen from above): worst overlap %.4f; nearest "
          "%.3f to the teeth and base; sleeve face to the ring top %.3f (the flange, %.1f less the %.1f squeeze)"
          % (p["TwistDeg"], worst, dmin, dring, p["FlangeT"], squeeze))
    bad += worst > 1e-3 or dmin < 0.3 or dring < p["FlangeT"] - squeeze - 0.01
    # 3. the body resting on the lug tops while its legs are searched for: clear of the jig, and centred by the collar
    lugTop = p["LugZ1"] - squeeze                    # above the collar bottom
    rise = lugTop - p["FlangeT"]
    rests = []
    for rot in (5.0, 15.0, 30.0, 45.0):
        b = Moved(body, rot=rot, dz=rise)
        rests.append((jig.common(b).Volume, jig.distToShape(b)[0], b.common(collar).Volume))
    onLugs = Moved(body, rot=45.0, dz=rise).distToShape(collar)[0]   # 45 deg: solid wall over every lug
    print("  body on the lug tops (turned 5..45 deg): worst jig overlap %.4f, nearest %.3f; body/collar overlap %.4f; "
          "at 45 deg %.3f to the collar (it rests on the lugs)" % (
              max(r[0] for r in rests), min(r[1] for r in rests), max(r[2] for r in rests), onLugs))
    bad += max(r[0] for r in rests) > 1e-3 or max(r[2] for r in rests) > 1e-3 or onLugs > 0.01
    # control: resting there, its sleeve is already inside the collar bore, so 0.3 mm off centre it hits the collar
    off = Moved(body, rot=45.0, dz=rise + 0.01, dx=0.3).common(collar).Volume
    print("  control: resting body 0.3 off centre: collar overlap %.3f (must be > 0: the collar bore centres it)" % off)
    bad += off <= 0
    # 4. the filter and CNT film clear the jig; nothing of the jig rises past the collar top near the body
    dc = jig.distToShape(parts["CntFilm"])[0]
    df = jig.distToShape(parts["Filter"])[0]
    dt = jig.common(Annulus(p["SleeveID"] / 2 - 1, p["CollarOD"] / 2, zc + 0.001, zc + 5)).distToShape(parts["Filter"])[0]
    print("  CNT film to the jig %.2f; filter to the jig %.2f (the flange between them), to the teeth %.2f" % (dc, df, dt))
    bad += dc < 1.5 or df < p["FlangeT"] - 1e-3 or dt < 0.3
    knurl = p["BodyTop"] - p["FlangeT"] - squeeze
    print("  the whole body (%.1f of knurl) and the plate edge are free to grip; base top %.2f under the body" %
          (knurl, (zc + p["FlangeT"] - squeeze) - k["zRing0"]))
    print("Checks failing: %d" % bad)
    return bad


def Main():
    parts, lv, p = Cartridge()
    jig, k = BuildJig(p, lv)
    print("zc %.2f; base %.2f..%.2f, ring top %.2f" % (lv["CartridgeBottom"], k["zBase0"], k["zRing0"], lv["CartridgeBottom"]))
    if Check(jig, k, parts, lv, p):
        raise SystemExit("cartridge jig checks failed")
    os.makedirs(Out, exist_ok=True)
    pr = jig.copy()
    pr.translate(V(0, 0, -pr.BoundBox.ZMin))          # base on the bed, teeth up
    step = os.path.join(Out, JigName + ".step")
    pr.exportStep(step)
    back = Part.read(step)
    if GeometryErrors(back) or len(back.Solids) != 1 or abs(back.Volume - pr.Volume) > 1e-3 * pr.Volume:
        raise RuntimeError("jig fails after STEP round trip")
    print("  wrote %s: %.1f x %.1f x %.2f mm, self-check ok, re-import ok" % (
        os.path.basename(step), pr.BoundBox.XLength, pr.BoundBox.YLength, pr.BoundBox.ZLength))
    doc = FreeCAD.newDocument("CartridgeJig")
    items = [("Jig", jig), ("Collar", parts["CollarPrinted"]), ("Filter", parts["Filter"]), ("CntFilm", parts["CntFilm"]),
             ("Body", Moved(parts["Body"], dz=-p["PrintSqueezes"][0])),
             ("Plate", Moved(parts["Plate"], dz=-p["PrintSqueezes"][0]))]
    for n, s in items:
        doc.addObject("Part::Feature", n).Shape = s
    doc.recompute()
    fc = os.path.join(Out, JigName + ".FCStd")
    doc.saveAs(fc)
    FreeCAD.closeDocument(doc.Name)
    print("Saved", fc)


Main()
