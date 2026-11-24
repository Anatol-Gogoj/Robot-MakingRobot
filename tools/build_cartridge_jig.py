# Builds the filter cartridge assembly jig (issue 253) and the knob that turns the body (issue 257).
#
# The jig is a bench base that holds the collar by its six rim notches, as the collar spanner does, with its bore
# open under the CNT area. The knob sits on the body: six pegs on its underside go into the six notches in the
# body's roof, inside the bonded steel plate, so the body is turned by the knob and nobody grips the plate. A lip
# on the knob's rim reaches down past the plate, so no hand reaches the plate's cut edge either.
#
# Assembly: collar into the jig, filter into the collar (CNT side down), knob onto the body (plate up), then the body
# onto the collar with the knob's pointer (the grip rib's ends) at an OPEN mark on the jig: the body's bayonet legs
# are then over the collar's lugs and the body drops. Turn the knob clockwise, seen from above, to the LOCK mark,
# TwistDeg further. The procedure is CAD/Filter Cartridge/Assembly jig/README.md.
#
# Both parts print in two colors on a Bambu P1S with an AMS: the marks and text are inlays, flush with the top
# faces and InlayDepth deep, exported as a separate black solid in the same coordinates as the white part.
#
# Run with FreeCAD's console:  freecadcmd tools/build_cartridge_jig.py
# Writes CAD/Filter Cartridge/Assembly jig/: <part>_White.step and <part>_Black.step for the jig and the knob, in
# print orientation, and CartridgeAssemblyJig.FCStd (jig, knob and a locked cartridge, for checking the fit).
#
# The cartridge geometry comes from tools/build_filter_cartridge.py (its P dict and Build()), printed-flange
# variant, with the collar as printed (Squeeze from PrintSqueezes). Frame: the cartridge generator's, z = 0 at
# the mask bottom, so the collar's bottom (the flange's underside) is at zc = StencilT + SeatGap. Units mm.
# The text needs a bold TrueType font (FontCandidates); the committed files were made with Arial Bold.

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

DEG = chr(176)
J = dict(
    RingID=80.0,           # under the flange from r 40: clear of the CNT film (r 37.5); the bore is open to the bench
    RingH=2.0,             # tooth ring above the base; its top carries the flange (under the filter band) while it is clamped
    BaseT=4.0,
    BaseOD=160.0,          # the marks sit outside the knob (r 60), r 61..78
    ToothFull=1.0,         # each tooth keeps its full width up to here above the collar bottom, then narrows to its tip
                           # (the spanner's teeth narrow from 0.7): the locking torque bears on 0.7 mm of flank, above the
                           # 0.3 mm mouth flare of each notch, instead of 0.5
    HoleR=55.5,            # bench screw holes (M4), under the knob's lip, clear of the marks
    HoleAngles=(30.0, 150.0, 270.0),
    HoleD=4.5,
    HeadD=8.0,             # screw head envelope checked against the cartridge and the knob (M4 socket or pan head)
    HeadH=4.0,
    TickR=(61.0, 66.5),    # OPEN and LOCK ticks on the base top
    TickW=1.6,
    ArcR=63.75,            # arrow from OPEN to LOCK, between the ticks
    ArcW=1.4,
    LabelR=70.5,           # OPEN / LOCK
    LabelCap=4.0,
    AngleR=76.0,           # the twist angle, between OPEN and LOCK
    AngleCap=3.5,
    HintR=72.0,            # CNT DOWN / PLATE UP, in the gaps between mark pairs
    HintCap=3.5,
    PrintBed=256.0,        # Bambu P1S
)
K = dict(
    KnobOD=120.0,
    Height=24.0,           # knob top above the body roof
    PegR=(40.2, 44.0),     # in the roof notches (r 40.0..44.2): 0.2 mm radial clearance each side
    PegW=4.6,              # 0.2 mm side clearance in the 5.0 mm notch
    PegTipChamfer=0.3,
    PlugR=37.6,            # centre boss in the body bore (r 39), down to the peg tip plane
    BearR=(38.6, 40.4),    # flat ring that rests on the roof between the bore and the notches; from 40.4 the
                           # underside rises at 45 deg, so the knob prints upright without supports
    LipR=57.0,             # lip inner radius: 2.5 mm outside the plate edge, down to the peg tip plane
    TopChamfer=2.0,
    DishR=44.0,
    DishDepth=14.0,
    RibHalfDeg=5.5,        # grip rib across the dish, its top flush with the knob top, its ends the pointer. Its
                           # sides are planes through the knob axis (8.5 mm wide at the dish rim, narrower inward)
    HubR=8.0,              # and it grows from a centre hub. Both cut the spherical dish along exact iso-curves
                           # (meridians, a latitude): a rib with parallel sides fails the BOP check after a STEP
                           # round trip in FreeCAD 1.1, with the sphere's axis on z or across the rib
    StripeHalfDeg=2.0,     # black line along the rib top, from StripeR0 out to the pointers
    StripeR0=16.0,
    PointerR=(50.0, 57.5),
    PointerW=7.0,
    WordR=50.5,            # LOCK / OPEN on the rim: corners at r 53.9, 0.9 inside the turn arrows
    WordCap=5.0,
    TurnArcR=55.5,         # turn arrows on the rim
    TurnArcW=1.4,
)
InlayDepth = 0.6           # three 0.2 mm layers of black
FontCandidates = ("C:/Windows/Fonts/arialbd.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                  "/Library/Fonts/Arial Bold.ttf")
Out = os.path.join(os.path.dirname(Here), "CAD", "Filter Cartridge", "Assembly jig")
JigName, KnobName = "CartridgeAssemblyJig", "CartridgeKnob"


def Cartridge():
    """The printed-flange cartridge as assembled, with the collar as printed. Returns (parts, levels, p)."""
    p = dict(P)
    p["PrintedFlange"] = True
    parts, lv = Build(p)
    q = dict(p)
    q["Squeeze"] = p["PrintSqueezes"][0]
    parts["CollarPrinted"] = Build(q)[0]["Collar"]
    return parts, lv, p


def MarkAngles(p):
    """(LOCK, OPEN) angles of the six mark pairs, jig frame, deg. With the body locked a roof notch, and the knob
    peg in it, is at RoofNotchAngle0 (+60k): that is LOCK. At bayonet entry the body sits TwistDeg anticlockwise of
    lock (its legs are over the lugs): that is OPEN. OPEN is always LOCK + TwistDeg, never wrapped, so the arrow
    between them always runs the short way."""
    n = p["RoofNotchCount"]
    lock = [p["RoofNotchAngle0"] % (360.0 / n) + i * 360.0 / n for i in range(n)]
    return [(a, a + p["TwistDeg"]) for a in lock]


# ------------------------------------------------------------------ 2D marks and text, extruded into inlays
def FontPath():
    for f in FontCandidates:
        if os.path.exists(f):
            return f
    raise RuntimeError("no bold TrueType font found; add one to FontCandidates")


def TextFaces(text, cap):
    """Faces of text in the XY plane, cap height cap, centred on the origin."""
    font = FontPath()
    probe = Part.makeWireString("H", font, 10.0, 0)
    capH = Part.makeCompound([w for ch in probe for w in ch]).BoundBox.YLength
    size = 10.0 * cap / capH
    faces = []
    for wires in Part.makeWireString(text, font, size, 0):
        if wires:
            f = Part.makeFace(wires, "Part::FaceMakerBullseye")
            faces.extend(f.Faces)
    comp = Part.makeCompound(faces)
    bb = comp.BoundBox
    comp.translate(V(-(bb.XMin + bb.XMax) / 2, -cap / 2, 0))
    return comp


def Placed(shape, theta, r, z):
    """Puts flat text at angle theta (deg) and radius r, reading tangentially: its top points outward on the upper
    half and inward on the lower half, so it reads upright from the near side of the part."""
    s = shape.copy()
    lower = math.sin(math.radians(theta)) < -1e-9
    s.rotate(V(0, 0, 0), V(0, 0, 1), theta + 90.0 if lower else theta - 90.0)
    t = math.radians(theta)
    s.translate(V(r * math.cos(t), r * math.sin(t), z))
    return s


def Inlay(faces, zTop):
    """Solids InlayDepth deep under the flat faces, ending flush at zTop."""
    sols = []
    for f in faces.Faces:
        g = f.copy()
        g.translate(V(0, 0, zTop - InlayDepth - g.BoundBox.ZMin))
        sols.append(g.extrude(V(0, 0, InlayDepth)))
    return sols


def Text(text, cap, theta, r, zTop):
    return Inlay(Placed(TextFaces(text, cap), theta, r, 0.0), zTop)


def Bar(r0, r1, w, theta, zTop):
    b = Part.makeBox(r1 - r0, w, InlayDepth, V(r0, -w / 2, zTop - InlayDepth))
    return [Rotated(b, theta)]


def Triangle(rTip, rBase, w, theta, zTop):
    """Arrowhead pointing radially, tip at rTip."""
    pts = [V(rTip, 0, 0), V(rBase, -w / 2, 0), V(rBase, w / 2, 0), V(rTip, 0, 0)]
    f = Part.Face(Part.makePolygon(pts))
    f.translate(V(0, 0, zTop - InlayDepth))
    return [Rotated(f.extrude(V(0, 0, InlayDepth)), theta)]


def ArcArrow(r, w, a0, a1, zTop, head=4.0):
    """Arc band from a0 to a1 (deg) with an arrowhead at a1, the head pointing along the arc."""
    d = 1.0 if a1 > a0 else -1.0
    headDeg = math.degrees(head / r)
    lo, hi = sorted((a0, a1 - d * headDeg * 0.9))
    out = [Sector(r - w / 2, r + w / 2, zTop - InlayDepth, zTop, lo, hi)]
    t1, tb = math.radians(a1), math.radians(a1 - d * headDeg)
    hw = w * 1.4
    pts = [V(r * math.cos(t1), r * math.sin(t1), 0),
           V((r - hw) * math.cos(tb), (r - hw) * math.sin(tb), 0),
           V((r + hw) * math.cos(tb), (r + hw) * math.sin(tb), 0),
           V(r * math.cos(t1), r * math.sin(t1), 0)]
    f = Part.Face(Part.makePolygon(pts))
    f.translate(V(0, 0, zTop - InlayDepth))
    out.append(f.extrude(V(0, 0, InlayDepth)))
    return out


def Wedges(halfDeg, r0, r1, z0, z1):
    """Two opposite wedges along x (angles 0 and 180), sides through the z axis, from r0 to r1 (along x)."""
    t = math.tan(math.radians(halfDeg))
    out = []
    for s in (1.0, -1.0):
        pts = [V(s * r0, r0 * t, z0), V(s * r1, r1 * t, z0), V(s * r1, -r1 * t, z0), V(s * r0, -r0 * t, z0)]
        if r0 <= 0:
            pts = pts[1:3] + [V(0, 0, z0)]
        f = Part.Face(Part.makePolygon(pts + [pts[0]]))
        out.append(f.extrude(V(0, 0, z1 - z0)))
    return out


def Fused(solids):
    s = solids[0]
    for t in solids[1:]:
        s = s.fuse(t)
    return s.removeSplitter()


# ------------------------------------------------------------------ jig
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


def JigMarks(p, zTop):
    """Black inlays on the base top: per bayonet position an OPEN and a LOCK tick, an arrow from OPEN to LOCK,
    the words and the twist angle; in the gaps, CNT DOWN and PLATE UP alternately."""
    out = []
    pairs = MarkAngles(p)
    for i, (lock, opn) in enumerate(pairs):
        out += Bar(J["TickR"][0], J["TickR"][1], J["TickW"], lock, zTop)
        out += Bar(J["TickR"][0], J["TickR"][1], J["TickW"], opn, zTop)
        # the arrow ends 2 deg short of each tick: 1.4 mm of white at r 63.75, more than three 0.4 mm lines
        out += ArcArrow(J["ArcR"], J["ArcW"], opn - 2.0, lock + 2.0, zTop)
        out += Text("LOCK", J["LabelCap"], lock, J["LabelR"], zTop)
        out += Text("OPEN", J["LabelCap"], opn, J["LabelR"], zTop)
        out += Text("%.0f%s" % (p["TwistDeg"], DEG), J["AngleCap"], lock + p["TwistDeg"] / 2, J["AngleR"], zTop)
        gap = lock + p["TwistDeg"] + (360.0 / len(pairs) - p["TwistDeg"]) / 2
        out += Text("CNT DOWN" if i % 2 == 0 else "PLATE UP", J["HintCap"], gap, J["HintR"], zTop)
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
    jig = jig.removeSplitter()
    marks = Fused(JigMarks(p, zRing0))
    black = marks.common(jig)
    return jig, black, dict(zBase0=zBase0, zRing0=zRing0, marksVolume=marks.Volume)


# ------------------------------------------------------------------ knob
def BuildKnob(p, lv):
    """The knob on the body at nominal height (unsqueezed), pointer at knob angle 0 turned to RoofNotchAngle0:
    the locked pose. Returns (knob, black inlays, levels)."""
    zc = lv["CartridgeBottom"]
    roof = zc + p["BodyTop"]
    pegH = p["RoofNotchDepth"] - 0.2
    zb = roof - pegH                                   # peg tips, plug and lip end on this plane: the print bed
    top = roof + K["Height"]
    R, br0, br1 = K["KnobOD"] / 2, K["BearR"][0], K["BearR"][1]
    rise = K["LipR"] - br1                             # 45 deg underside from the bearing ring to the lip
    prof = [(0.0, zb), (K["PlugR"], zb), (br0, roof), (br1, roof), (K["LipR"], roof + rise), (K["LipR"], zb),
            (R, zb), (R, top - K["TopChamfer"]), (R - K["TopChamfer"], top), (0.0, top)]
    face = Part.Face(Part.makePolygon([V(r, 0, z) for r, z in prof] + [V(prof[0][0], 0, prof[0][1])]))
    knob = face.revolve(V(0, 0, 0), V(0, 0, 1), 360)
    knob = Part.Solid(knob) if knob.ShapeType == "Shell" else knob
    # dish: a spherical cap from the top, DishDepth deep, meeting the top face at DishR
    a, h = K["DishR"], K["DishDepth"]
    sr = (a * a + h * h) / (2 * h)
    sph = Part.makeSphere(sr, V(0, 0, top - h + sr))
    knob = knob.cut(sph.common(Part.makeCylinder(a, h + 2, V(0, 0, top - h - 1))))
    # grip rib across the dish, its top flush with the knob top: two wedges with sides through the axis and a hub
    z0 = top - h - 0.5
    rib = Part.makeCylinder(K["HubR"], top - z0, V(0, 0, z0))
    for w in Wedges(K["RibHalfDeg"], 0.0, a + 2.0, z0, top):
        rib = rib.fuse(w)
    knob = knob.fuse(rib.common(Part.makeCylinder(a + 0.5, top - z0, V(0, 0, z0))))
    # pegs (knob angles 0, 60, ...), tips chamfered
    n = p["RoofNotchCount"]
    for i in range(n):
        r0, r1 = K["PegR"]
        # up to roof + 4: inside the knob above its 45 deg underside (roof + 3.6 at the peg's outer face)
        peg = Part.makeBox(r1 - r0, K["PegW"], pegH + 4.0, V(r0, -K["PegW"] / 2, zb))
        edges = [e for e in peg.Edges if abs(e.BoundBox.ZMax - zb) < 1e-6 and abs(e.BoundBox.ZMin - zb) < 1e-6]
        peg = peg.makeChamfer(K["PegTipChamfer"], edges)
        knob = knob.fuse(Rotated(peg, i * 360.0 / n))
    knob = knob.removeSplitter()
    # inlays on the top: rib line with a pointer at each end, LOCK with a clockwise arrow, OPEN with an
    # anticlockwise one
    marks = Wedges(K["StripeHalfDeg"], K["StripeR0"], K["PointerR"][0] + 0.5, top - InlayDepth, top)
    for th in (0.0, 180.0):
        marks += Triangle(K["PointerR"][1], K["PointerR"][0], K["PointerW"], th, top)
    marks += Text("LOCK", K["WordCap"], 90.0, K["WordR"], top)
    marks += ArcArrow(K["TurnArcR"], K["TurnArcW"], 120.0, 60.0, top)
    marks += Text("OPEN", K["WordCap"], 270.0, K["WordR"], top)
    marks += ArcArrow(K["TurnArcR"], K["TurnArcW"], 240.0, 300.0, top)
    marks = Fused(marks)
    black = marks.common(knob)
    # locked pose: pointer and pegs at the roof notches
    knob.rotate(V(0, 0, 0), V(0, 0, 1), p["RoofNotchAngle0"])
    black.rotate(V(0, 0, 0), V(0, 0, 1), p["RoofNotchAngle0"])
    return knob, black, dict(zb=zb, roof=roof, top=top, marksVolume=marks.Volume)


def Moved(shape, rot=0.0, dz=0.0, dx=0.0):
    s = shape.copy()
    if rot:
        s.rotate(V(0, 0, 0), V(0, 0, 1), rot)
    if dz or dx:
        s.translate(V(dx, 0, dz))
    return s


# ------------------------------------------------------------------ checks
def CheckInlay(name, part, black, zTop, marksVolume):
    """Every mark lies whole on the flat top face: nothing of it was trimmed off by a chamfer, the dish or a hole
    (the drawn marks and the black inlay have the same volume), and each piece ends flush with the face. The white
    part is the part less the inlay."""
    white = part.cut(black)
    trimmed = marksVolume - black.Volume
    tops = max(abs(s.BoundBox.ZMax - zTop) for s in black.Solids)
    sumErr = abs(white.Volume + black.Volume - part.Volume)
    print("  %s inlays: %d black solids, %.0f mm^3; trimmed off the face %.4f; worst top off the face %.4f; "
          "white + black - part %.4f" % (name, len(black.Solids), black.Volume, trimmed, tops, sumErr))
    return white, (trimmed > 1e-3 or tops > 1e-6 or sumErr > 1e-2 or black.Volume <= 0
                   or bool(GeometryErrors(white)) or not white.isValid())


def Check(jig, jigBlack, k, knob, knobBlack, kk, parts, lv, p):
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
    # 2. the body, with the knob on it, along the whole twist at the height the bayonet holds it; locked it sits
    # Squeeze lower than nominal. The sleeve face clamps the filter band onto the flange right above the ring: that
    # gap is the flange, measured on its own; everything else of the jig must keep 0.3 from the body
    zc = lv["CartridgeBottom"]
    under = Annulus(p["SleeveID"] / 2, p["CollarOD"] / 2 - 0.2, zc - 0.5, zc + 0.001)
    rest = jig.cut(under)
    worst, dmin, dring, kWorst, kJig, kCol = 0.0, 99.0, 99.0, 0.0, 99.0, 99.0
    phi = -p["TwistDeg"]
    while phi <= 1e-9:
        dz = (p["RampRise"] - LiftAt(p, phi)) - squeeze
        b, kn = Moved(body, rot=-phi, dz=dz), Moved(knob, rot=-phi, dz=dz)
        worst = max(worst, jig.common(b).Volume)
        dmin = min(dmin, rest.distToShape(b)[0])
        dring = min(dring, jig.common(under).distToShape(b)[0])
        kWorst = max(kWorst, kn.common(jig).Volume, kn.common(collar).Volume)
        kJig, kCol = min(kJig, kn.distToShape(jig)[0]), min(kCol, kn.distToShape(collar)[0])
        phi += 1.0
    print("  body along the twist (entry %+.0f deg to lock, clockwise seen from above): worst overlap %.4f; nearest "
          "%.3f to the teeth and base; sleeve face to the ring top %.3f (the flange, %.1f less the %.1f squeeze)"
          % (p["TwistDeg"], worst, dmin, dring, p["FlangeT"], squeeze))
    print("  knob along the twist: worst overlap with the jig or collar %.4f; nearest %.3f to the jig, %.3f to the collar"
          % (kWorst, kJig, kCol))
    bad += worst > 1e-3 or dmin < 0.3 or dring < p["FlangeT"] - squeeze - 0.01
    bad += kWorst > 1e-3 or kJig < 1.0 or kCol < 0.5
    # 3. the body resting on the lug tops while its legs are searched for: clear of the jig, and centred by the collar
    lugTop = p["LugZ1"] - squeeze                    # above the collar bottom
    rise = lugTop - p["FlangeT"]
    rests = []
    for rot in (5.0, 15.0, 30.0, 45.0):
        b, kn = Moved(body, rot=rot, dz=rise), Moved(knob, rot=rot, dz=rise)
        rests.append((jig.common(b).Volume, jig.distToShape(b)[0], b.common(collar).Volume,
                      kn.common(jig).Volume + kn.common(collar).Volume))
    onLugs = Moved(body, rot=45.0, dz=rise).distToShape(collar)[0]   # 45 deg: solid wall over every lug
    print("  body on the lug tops (turned 5..45 deg): worst jig overlap %.4f, nearest %.3f; body/collar overlap %.4f; "
          "at 45 deg %.3f to the collar (it rests on the lugs); knob overlap %.4f" % (
              max(r[0] for r in rests), min(r[1] for r in rests), max(r[2] for r in rests), onLugs,
              max(r[3] for r in rests)))
    bad += max(r[0] for r in rests) > 1e-3 or max(r[2] for r in rests) > 1e-3 or onLugs > 0.01
    bad += max(r[3] for r in rests) > 1e-3
    # control: resting there, its sleeve is already inside the collar bore, so 0.3 mm off centre it hits the collar
    off = Moved(body, rot=45.0, dz=rise + 0.01, dx=0.3).common(collar).Volume
    print("  control: resting body 0.3 off centre: collar overlap %.3f (must be > 0: the collar bore centres it)" % off)
    bad += off <= 0
    # 4. the marks: at OPEN the body's legs are over the lugs, so it drops from the lug tops to the entry height.
    # Half way down, 5 deg either side of OPEN, the lugs run into the body (the groove ceiling or the wall): the
    # body can drop only at OPEN
    dzEntry = (p["RampRise"] - LiftAt(p, -p["TwistDeg"])) - squeeze
    dzHalf = (rise + dzEntry) / 2
    atOpen = max(Moved(body, rot=p["TwistDeg"], dz=d).common(collar).Volume for d in (dzEntry, dzHalf))
    offOpen = [Moved(body, rot=p["TwistDeg"] + s, dz=dzHalf).common(collar).Volume for s in (-5.0, 5.0)]
    pairs = MarkAngles(p)
    print("  marks: LOCK at %s deg, OPEN %.0f deg anticlockwise of each; body at OPEN, half way down and dropped: "
          "collar overlap %.4f (must be 0); half way down 5 deg either side of OPEN: %.3f / %.3f (both must be > 0)" % (
              ", ".join("%.0f" % a for a, _ in pairs), p["TwistDeg"], atOpen, offOpen[0], offOpen[1]))
    bad += atOpen > 1e-3 or min(offOpen) <= 0
    # 5. the filter and CNT film clear the jig and the knob
    dc = jig.distToShape(parts["CntFilm"])[0]
    df = jig.distToShape(parts["Filter"])[0]
    dt = jig.common(Annulus(p["SleeveID"] / 2 - 1, p["CollarOD"] / 2, zc + 0.001, zc + 5)).distToShape(parts["Filter"])[0]
    print("  CNT film to the jig %.2f; filter to the jig %.2f (the flange between them), to the teeth %.2f" % (dc, df, dt))
    bad += dc < 1.5 or df < p["FlangeT"] - 1e-3 or dt < 0.3
    # 6. the knob on the locked body: rests on the roof, pegs in the notches, clear of the plate, filter, collar, jig
    kl = Moved(knob, dz=-squeeze)
    bl, pl = Moved(body, dz=-squeeze), Moved(plate, dz=-squeeze)
    print("Knob: %d solid, valid %s, %.1f x %.1f x %.1f mm (bed %.0f)" % (
        len(knob.Solids), knob.isValid(), knob.BoundBox.XLength, knob.BoundBox.YLength, knob.BoundBox.ZLength,
        J["PrintBed"]))
    bad += len(knob.Solids) != 1 or not knob.isValid() or bool(GeometryErrors(knob))
    kov, kgap = kl.common(bl).Volume, kl.distToShape(bl)[0]
    kturn = [Moved(kl, rot=s * 0.5).common(bl).Volume for s in (1, -1)]
    klow = Moved(kl, dz=-0.05).common(bl).Volume
    print("  knob on the body: overlap %.4f, gap %.3f (it rests on the roof); turned 0.5 deg either way: %.3f / %.3f "
          "(both must be > 0: the pegs drive the body); 0.05 lower: %.3f (must be > 0)" % (kov, kgap, kturn[0], kturn[1], klow))
    bad += kov > 1e-3 or kgap > 0.01 or min(kturn) <= 0 or klow <= 0
    dPlate = kl.distToShape(pl)[0]
    dFilter, dCnt = kl.distToShape(parts["Filter"])[0], kl.distToShape(parts["CntFilm"])[0]
    lipLow = kk["zb"] - squeeze
    print("  knob to the plate %.2f, to the filter %.2f, to the CNT film %.2f; lip bottom %.2f below the plate's "
          "underside, %.1f outside its edge (no hand reaches the edge)" % (
              dPlate, dFilter, dCnt, (p["BodyTop"] + zc - squeeze) - lipLow, K["LipR"] - p["PlateOD"] / 2))
    bad += dPlate < 0.5 or dFilter < 2.0 or dCnt < 2.0 or lipLow >= zc + p["BodyTop"] - squeeze
    # the print bed plane carries the plug, every peg and the lip
    zb = knob.BoundBox.ZMin
    pts = [V(0, 0, zb + 0.05), V(K["LipR"] + 1.5, 0, zb + 0.05)]
    for i in range(p["RoofNotchCount"]):
        t = math.radians(p["RoofNotchAngle0"] + i * 360.0 / p["RoofNotchCount"])
        rm = sum(K["PegR"]) / 2
        pts.append(V(rm * math.cos(t), rm * math.sin(t), zb + 0.05))
    onBed = sum(1 for v in pts if knob.isInside(v, 1e-6, True))
    print("  knob bed plane z %.2f: plug, lip and %d pegs on it (%d of %d points inside)" % (
        zb, p["RoofNotchCount"], onBed, len(pts)))
    bad += onBed != len(pts)
    # 7. bench screw heads under the knob's lip: clear of the cartridge and the knob at lock and at entry
    heads = [Rotated(Part.makeCylinder(J["HeadD"] / 2, J["HeadH"], V(J["HoleR"], 0, k["zRing0"])), a)
             for a in J["HoleAngles"]]
    hc = Part.makeCompound(heads)
    poses = [(0.0, -squeeze), (p["TwistDeg"], rise)]
    dh = min(min(hc.distToShape(Moved(s, rot=r, dz=d))[0] for s in (body, plate, knob)) for r, d in poses)
    print("  screw heads (%.0f x %.0f) to the body, plate and knob: %.2f" % (J["HeadD"], J["HeadH"], dh))
    bad += dh < 0.5
    # 8. inlays
    jigWhite, b1 = CheckInlay("jig", jig, jigBlack, k["zRing0"], k["marksVolume"])
    knobWhite, b2 = CheckInlay("knob", knob, knobBlack, kk["top"], kk["marksVolume"])
    bad += b1 + b2
    print("Checks failing: %d" % bad)
    return bad, jigWhite, knobWhite


# ------------------------------------------------------------------ export
def Export(name, white, black):
    """Writes <name>_White.step and <name>_Black.step in print orientation (the white part's lowest point on the
    bed), checks both read back, and returns the bed-placed pair."""
    dz = -white.BoundBox.ZMin
    pair = []
    for color, s in (("White", white), ("Black", black)):
        t = s.copy()
        t.translate(V(0, 0, dz))
        path = os.path.join(Out, "%s_%s.step" % (name, color))
        t.exportStep(path)
        back = Part.read(path)
        if GeometryErrors(back) or abs(back.Volume - t.Volume) > 1e-3 * t.Volume or len(back.Solids) != len(t.Solids):
            raise RuntimeError("%s fails after STEP round trip" % path)
        bb = t.BoundBox
        print("  wrote %s: %.1f x %.1f x %.2f mm, %d solid(s), re-import ok" % (
            os.path.basename(path), bb.XLength, bb.YLength, bb.ZLength, len(t.Solids)))
        pair.append(t)
    return pair


def Main():
    parts, lv, p = Cartridge()
    jig, jigBlack, k = BuildJig(p, lv)
    knob, knobBlack, kk = BuildKnob(p, lv)
    print("zc %.2f; base %.2f..%.2f, ring top %.2f; knob bed %.2f, roof %.2f, top %.2f; font %s" % (
        lv["CartridgeBottom"], k["zBase0"], k["zRing0"], lv["CartridgeBottom"], kk["zb"], kk["roof"], kk["top"],
        os.path.basename(FontPath())))
    bad, jigWhite, knobWhite = Check(jig, jigBlack, k, knob, knobBlack, kk, parts, lv, p)
    if bad:
        raise SystemExit("cartridge jig checks failed")
    os.makedirs(Out, exist_ok=True)
    for old in os.listdir(Out):                        # a renamed or retired export must not linger
        if old.endswith(".step"):
            os.remove(os.path.join(Out, old))
    Export(JigName, jigWhite, jigBlack)
    Export(KnobName, knobWhite, knobBlack)
    sq = p["PrintSqueezes"][0]
    doc = FreeCAD.newDocument("CartridgeJig")
    items = [("Jig", jigWhite), ("JigMarks", jigBlack), ("Collar", parts["CollarPrinted"]), ("Filter", parts["Filter"]),
             ("CntFilm", parts["CntFilm"]), ("Body", Moved(parts["Body"], dz=-sq)), ("Plate", Moved(parts["Plate"], dz=-sq)),
             ("Knob", Moved(knobWhite, dz=-sq)), ("KnobMarks", Moved(knobBlack, dz=-sq))]
    for n, s in items:
        doc.addObject("Part::Feature", n).Shape = s
    doc.recompute()
    fc = os.path.join(Out, JigName + ".FCStd")
    doc.saveAs(fc)
    FreeCAD.closeDocument(doc.Name)
    print("Saved", fc)


Main()
