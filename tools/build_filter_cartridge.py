# Builds the concept model of the filter cartridge, a mask with a thin stencil,
# and the head's floating-ring interface, checks fits, and exports print-ready
# STEP files for a 0.4 mm nozzle.
#
# Run with FreeCAD's console:  freecadcmd tools/build_filter_cartridge.py
# Writes CAD/Filter Cartridge/<variant>.FCStd, one STEP per part, and the
# print set in CAD/Filter Cartridge/Print 0.4mm nozzle/.
#
# Frame: z = 0 is the mask bottom (the elastomer surface), z up, axis = Z.
# All dimensions in mm. Every value below is a design proposal except where a
# comment names its source. Heights that a slicer must resolve are kept on a
# 0.1 mm grid so the collar and body print true at 0.1 mm layers.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector

# ---------------------------------------------------------------- parameters
P = dict(
    # Filter and CNT film (owner, 2026-11-04: 90 mm PTFE, some shrink to ~89 mm,
    # 75 mm CNT area, 80 um membrane)
    FilterD=90.0,
    FilterT=0.08,
    CntD=75.0,
    CntT=0.02,             # drawn only so the film is visible
    # Mask stencil thickness: ThinMask_20261016/20261030 STEP are 0.5 mm
    StencilT=0.5,
    # Gap between cartridge bottom and stencil face when the balls are seated
    SeatGap=0.2,
    # Lower jaw, option A: laser-cut 0.1 mm stainless shim bonded to the collar
    ShimT=0.1,
    ShimID=78.0,           # owner, 2026-11-04: 3 mm more radial support than 84;
                           # matches the sleeve bore, 1.5 mm clear of the CNT edge
    # Lower jaw, option B: flange printed on the collar
    PrintedFlange=False,
    FlangeT=0.3,           # 0.2 mm first layer + one 0.1 mm layer, printed flange-down
    FlangeID=78.0,         # as ShimID; 6.3 mm cantilever from the collar bore
    # Spanner notches in the collar's outer rim (recessed: no effect on the seat gap)
    NotchCount=6,
    NotchWidth=18.0,       # owner, 2026-11-05: 3x the 6 mm arc after misaligned teeth tore off
    NotchDepth=1.5,        # leaves 1.1 mm of collar wall above each notch
    NotchMouthFlare=0.8,   # per side, over the bottom 0.3 mm: funnels a misaligned tooth in
    ToothTipNarrow=0.8,    # per side, over the top 0.5 mm of each tooth: lead-in
    ToothRadialClear=0.15,  # per side, tooth to notch
    ToothSideClear=0.2,     # per side, tooth to notch
    SpannerT=4.0,           # spanner ring thickness
    # Knurl on the body's outer face, for the hand that holds the body
    KnurlCount=24,
    KnurlWidth=1.2,
    KnurlDepth=0.4,
    # Gap between the lower jaw and the sleeve face once locked (membrane 0.08);
    # at bayonet entry the gap is ClampGap + RampRise
    ClampGap=0.0,
    Squeeze=0.0,           # lowers the collar lugs: locked gap = ClampGap - Squeeze
                           # (0 in the assembly model, so the checks see nominal parts)
    PrintSqueezes=(0.1,),  # collars in the print set: locked gap -0.10 (owner, 2026-11-05)
    # Bayonet: owner, 2026-11-04: six lugs, groove floor flat then ramped
    LugCount=6,
    RampRise=0.2,          # floor climbs this much from entry to lock
    RampDeg=8.0,           # twist over which the floor rises
    DwellMargin=0.5,       # flat floor past the ramp before the locked lug, deg
    # Bottom collar (printed)
    CollarID=90.6,         # 0.3 mm radial clearance to a 90 mm filter
    CollarOD=93.3,         # 1.35 mm wall = 3 lines at 0.45 mm
    CollarTop=2.6,         # above the cartridge bottom
    LugOD=95.7,
    LugZ0=1.0,
    LugZ1=2.2,
    LugWidth=5.0,          # arc length at the lug mid radius
    # Body (printed): clamp sleeve + bridge + outer wall
    SleeveID=78.0,         # proven bore: FilterSandwich_v20260909 STEP, 78.0 mm
    SleeveOD=90.1,         # covers the band to the 90 mm filter edge; 0.25 mm to the collar
    WallID=94.1,           # 0.4 mm radial clearance to the collar
    BodyOD=100.4,
    BodyTop=4.0,           # above the cartridge bottom
    CavityTop=3.0,         # collar pocket height: 0.3 mm over the collar at Squeeze +0.1
    BodyChamfer=0.8,       # 45 deg lead-in on the body's bottom outer edge
    GrooveOD=96.3,         # 0.3 mm radial clearance to the lugs
    GrooveClear=0.8,       # extra arc length of the vertical leg over the lug
    GrooveTopClear=0.3,    # groove ceiling above the lug top
    TwistDeg=22.0,         # bayonet twist to lock
    # Steel target plate, bonded once: G90 galvanized steel 0.030 in (0.762 mm), the magnetic sheet
    # SendCutSend stocks near 0.8 mm (its 304 is not magnetic; 430 is not offered), 2026-11-16
    PlateID=92.0,
    PlateOD=109.0,
    PlateT=0.762,
    # Mask frame (printed together with the stencil)
    FrameID=101.4,         # 0.5 mm radial clearance to the body
    FrameOD=112.0,         # widened so each magnet pocket has printable walls
    FrameBoreChamfer=0.5,  # 45 deg lead-in on the frame bore for the cartridge
    EarOuterR=62.0,
    EarWidth=9.0,
    # owner, 2026-11-05: flipped Maxwell coupling. Each mask ear carries one steel
    # ball pressed into a printed pocket; the head's floating ring carries a
    # tangential pair of balls above each ear. Two contacts per ear, six in all,
    # and each pair leaves only the radial direction free, like a radial V-groove.
    MaskBallD=4.0,
    ContactDeg=45.0,       # contact normal from vertical: a 90 deg "V"
    MaskBallPocketClear=0.075,  # pocket radius over the ball radius (press fit)
    MaskBallSink=0.4,      # mask ball centre below the ear top
    WeakMagD=3.0,
    WeakMagT=2.0,
    WeakMagR=53.0,         # pocket r 51.3..54.7: 0.6 mm to the bore (0.1 under the bore's top chamfer, as
                           # before); the magnet (r 51.5..54.5) sits under the plate
    MagPocketClear=0.2,    # pocket radius over the magnet radius: printed holes come out small, and at
                           # 0.1 the magnets had to be hammered in (bench, 2026-11-19); they are glued
    # How the head holds the mask (issue 230). "plate": the three weak magnets pull the mask up to the
    # cartridge's steel plate across a 1.17 mm gap, at most about 1 N in all. "lobe": a magnet in each
    # ear sits on a boss under a magnet flush in the head's ball lobe, LobeGap apart, so the mask is
    # held by the head itself (about 2.4 N per lobe with 3 x 2 N52 pairs). Stepped pushers on the head
    # (agreed with the head's designer, 2026-11-19; two 30-deg arc feet 180 deg apart in the current
    # proposal) push it off: each foot's lower step lands on the push flange and pushes the mask down by
    # the stage 1 travel before its upper step reaches the cartridge plate and pushes it off. The flange
    # runs all the way round, so the feet can sit at any angle clear of the ears; it is cut away around
    # +Y, where the pile seat's slide scale has to stay visible, and its underside is lifted so it never
    # touches the layer. The lobe variant drops the weak magnets.
    MaskHold="plate",
    LobeMagD=3.0,
    LobeMagT=2.0,
    LobeMagR=63.5,         # outside the head ball pair (r 56.5..60.5) and the plate ring (r 54.5)
    LobeGap=0.33,          # ear magnet top to the head lobe magnet face
    LobeBossWall=1.2,      # boss wall around the ear magnet pocket
    LobeEarOuterR=66.5,    # ears grow from EarOuterR to carry the magnet
    PushFlangeR=58.8,      # flange at the frame top out to here; a pusher's lower step lands at r 55..58.3, outside the plate (r 54.5)
    PushFlangeGap=(78.0, 102.0),   # cut away around +Y for the pile seat's slide scale (r 56..66, x 2.5..9.5)
    PushFlangeLift=0.3,    # the flange's underside starts this high at the frame wall and rises at 45 deg: it never
                           # touches the layer and prints stencil-down without support
    # Head floating ring (reference only, not a design of the head)
    BallD=4.0,
    BallR=58.5,
    BallProtrusion=1.5,
    RingID=91.0,
    RingOD=124.0,
    RingT=4.0,
    StrongMagD=6.0,
    StrongMagT=3.0,
    StrongMagR=50.0,
    # Stencil pattern, relative to the repo root: the owner's ThinMask_20261016 (0.5 mm rim, thinned
    # to 0.1 mm over the Ø75 CNT area, two L-shaped electrode openings), used as drawn and centred
    # on the mask axis. None falls back to a solid stencil with the OpenW x OpenH placeholder.
    StencilPattern="CAD/Exploratory Masks/ThinMask_20261016.STEP",
    OpenW=45.0,
    OpenH=40.0,
)

EarAngles = (0.0, 120.0, 240.0)
MagAngles = (60.0, 180.0, 300.0)


def LugAngles(p):
    """Locked lug angles; 30 deg off the spanner notches (0, 60, ...)."""
    n = p["LugCount"]
    return [30.0 + i * 360.0 / n for i in range(n)]


def RampCut(ri, ro, a0, a1, z0, z1, zTop):
    """Groove segment whose floor rises from z0 at angle a0 to z1 at a1.

    The floor is a tilted plane through the mid-radius points at a0 and a1 and
    level across the radius. Against a true helical ramp it differs by
    (ro - ri) * sin(span / 2) * slope, about 5 um here. A plane cut through the
    cylinders is exact geometry, so the STEP round-trips cleanly; the lofted
    B-spline version it replaced failed the self-check after re-import.
    """
    rm = (ri + ro) / 2
    t0, t1, tm = math.radians(a0), math.radians(a1), math.radians((a0 + a1) / 2)
    p0 = V(rm * math.cos(t0), rm * math.sin(t0), z0)
    p1 = V(rm * math.cos(t1), rm * math.sin(t1), z1)
    radial = V(math.cos(tm), math.sin(tm), 0)
    n = (p1 - p0).cross(radial)
    if n.z < 0:
        n = n * -1
    below = Part.makeBox(300, 300, 30, V(-150, -150, -30))      # top face at z = 0
    below.Placement = FreeCAD.Placement(p0, FreeCAD.Rotation(V(0, 0, 1), n))
    return Sector(ri, ro, z0, zTop, a0, a1).cut(below)


def LugGeometry(p):
    """Angular sizes shared by the collar, the body grooves and the checks."""
    lugMidR = (p["CollarOD"] + p["LugOD"]) / 4
    lugDeg = ArcDeg(p["LugWidth"], lugMidR)
    grooveMidR = (p["WallID"] + p["GrooveOD"]) / 4
    legDeg = ArcDeg(p["LugWidth"] + p["GrooveClear"], grooveMidR)
    rampEnd = -lugDeg / 2 - p["DwellMargin"]          # relative to the locked lug
    rampStart = rampEnd - p["RampDeg"]
    return lugDeg, legDeg, rampStart, rampEnd


def LiftAt(p, phi):
    """Collar lift when the lug centre is phi deg from its locked angle (phi <= 0)."""
    lugDeg, _, rs, re = LugGeometry(p)
    lead = phi + lugDeg / 2                           # leading edge rides highest
    if lead <= rs:
        return 0.0
    if lead >= re:
        return p["RampRise"]
    return p["RampRise"] * (lead - rs) / (re - rs)


def Annulus(ri, ro, z0, z1):
    h = z1 - z0
    outer = Part.makeCylinder(ro, h, V(0, 0, z0))
    if ri <= 0:
        return outer
    return outer.cut(Part.makeCylinder(ri, h, V(0, 0, z0)))


def Sector(ri, ro, z0, z1, a0, a1):
    """Annular sector from angle a0 to a1 (degrees, a1 > a0)."""
    h = z1 - z0
    span = a1 - a0
    outer = Part.makeCylinder(ro, h, V(0, 0, z0), V(0, 0, 1), span)
    inner = Part.makeCylinder(ri, h, V(0, 0, z0), V(0, 0, 1), span)
    s = outer.cut(inner)
    s.rotate(V(0, 0, 0), V(0, 0, 1), a0)
    return s


def ArcDeg(length, r):
    return math.degrees(length / r)


def Rotated(shape, deg):
    s = shape.copy()
    s.rotate(V(0, 0, 0), V(0, 0, 1), deg)
    return s


def StencilPattern(p):
    """The pattern solid and its openings (planar faces in its bottom plane), or None."""
    if not p.get("StencilPattern"):
        return None, []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pat = Part.read(os.path.join(root, p["StencilPattern"]))
    bb = pat.BoundBox
    if len(pat.Solids) != 1 or abs(bb.ZMin) > 1e-6 or abs(bb.ZMax - p["StencilT"]) > 1e-6:
        raise ValueError("%s: need one solid from z 0 to StencilT (%.2f), got %d solids, z %.3f..%.3f"
                         % (p["StencilPattern"], p["StencilT"], len(pat.Solids), bb.ZMin, bb.ZMax))
    if max(bb.XMax, -bb.XMin, bb.YMax, -bb.YMin) > p["FrameID"] / 2 - 0.5:
        raise ValueError("%s is wider than the frame bore" % p["StencilPattern"])
    bottom = max((f for f in pat.Faces if abs(f.BoundBox.ZMax) < 1e-6), key=lambda f: f.Area)
    holes = [Part.Face(w) for w in bottom.Wires if not w.isSame(bottom.OuterWire)]
    return pat.Solids[0], holes


def Stencil(p):
    """Stencil inside the frame bore, flat bottom at z = 0. With a pattern, the pattern disc as
    drawn plus a ring that fills from its rim to the frame bore (overlapping the rim by 0.3 so the
    fuse is not tangent); without one, a solid disc with the placeholder opening."""
    zS = p["StencilT"]
    pat, _ = StencilPattern(p)
    if pat is not None:
        bb = pat.BoundBox
        rim = max(bb.XMax, -bb.XMin, bb.YMax, -bb.YMin)
        return pat.fuse(Annulus(rim - 0.3, p["FrameID"] / 2, 0, zS)).removeSplitter()
    s = Part.makeCylinder(p["FrameID"] / 2, zS, V(0, 0, 0))
    return s.cut(Part.makeBox(p["OpenW"], p["OpenH"], zS + 1, V(-p["OpenW"] / 2, -p["OpenH"] / 2, -0.5)))


def Build(p):
    zc = p["StencilT"] + p["SeatGap"]           # cartridge bottom
    zb = p["FlangeT"] if p["PrintedFlange"] else p["ShimT"]   # lower jaw thickness
    parts = {}

    # ---- cartridge
    jaw = p["FlangeID"] if p["PrintedFlange"] else p["ShimID"]
    lowerJaw = Annulus(jaw / 2, p["CollarOD"] / 2, zc, zc + zb)
    collar = Annulus(p["CollarID"] / 2, p["CollarOD"] / 2, zc + zb, zc + p["CollarTop"])
    if p["PrintedFlange"]:
        collar = collar.fuse(lowerJaw)
    else:
        parts["Shim"] = lowerJaw
    lugDeg, legDeg, rampStart, rampEnd = LugGeometry(p)
    for a in LugAngles(p):
        collar = collar.fuse(Sector(p["CollarOD"] / 2 - 0.2, p["LugOD"] / 2,
                                    zc + p["LugZ0"] - p["Squeeze"],
                                    zc + p["LugZ1"] - p["Squeeze"],
                                    a - lugDeg / 2, a + lugDeg / 2))
    # notches are annular sectors: a flat box face tangent to the collar bore
    # leaves self-intersecting faces that break later booleans
    notchMidR = (p["CollarID"] + p["CollarOD"]) / 4
    notchDeg = ArcDeg(p["NotchWidth"], notchMidR)
    mouthDeg = ArcDeg(p["NotchWidth"] + 2 * p["NotchMouthFlare"], notchMidR)
    for i in range(p["NotchCount"]):
        a = i * 360.0 / p["NotchCount"]
        collar = collar.cut(Sector(p["CollarID"] / 2, p["CollarOD"] / 2 + 0.5,
                                   zc - 0.1, zc + p["NotchDepth"],
                                   a - notchDeg / 2, a + notchDeg / 2))
        # flared mouth through the flange layer (outside the filter edge)
        collar = collar.cut(Sector(p["CollarID"] / 2, p["CollarOD"] / 2 + 0.5,
                                   zc - 0.1, zc + 0.3, a - mouthDeg / 2, a + mouthDeg / 2))
    parts["Collar"] = collar.removeSplitter()

    body = Annulus(p["SleeveID"] / 2, p["BodyOD"] / 2, zc + zb, zc + p["BodyTop"])
    # collar pocket, open at the bottom
    body = body.cut(Annulus(p["SleeveOD"] / 2, p["WallID"] / 2, zc, zc + p["CavityTop"]))
    # sleeve face sits ClampGap above the lower jaw: it clamps the band
    body = body.cut(Annulus(p["SleeveID"] / 2 - 0.01, p["SleeveOD"] / 2,
                            zc, zc + zb + p["ClampGap"]))
    # the model shows the locked state: the dwell floor is at LugZ0 and the entry
    # floor RampRise lower, so the locked band height does not change with the ramp
    zTop = zc + p["LugZ1"] + p["GrooveTopClear"]
    ri, ro = p["WallID"] / 2 - 0.1, p["GrooveOD"] / 2
    zFloor = zc + p["LugZ0"] - p["RampRise"]
    for a in LugAngles(p):
        entry = a - p["TwistDeg"]
        # vertical leg: from the body bottom up past the lug top
        body = body.cut(Sector(ri, ro, zc, zTop, entry - legDeg / 2, entry + legDeg / 2))
        # horizontal leg in three parts: flat floor, ramp up, flat dwell under the
        # locked lug. The band compression pushes the lug down onto the floor, so a
        # rising floor pulls the flange up against the sleeve as the collar turns.
        rs, re = a + rampStart, a + rampEnd
        body = body.cut(Sector(ri, ro, zFloor, zTop, entry - legDeg / 2, rs + 0.01))
        body = body.cut(RampCut(ri, ro, rs, re, zFloor, zFloor + p["RampRise"], zTop))
        body = body.cut(Sector(ri, ro, zFloor + p["RampRise"], zTop, re - 0.01, a + legDeg / 2))
    for i in range(p["KnurlCount"]):
        k = Part.makeBox(p["KnurlDepth"] + 1.0, p["KnurlWidth"], p["BodyTop"] + 1.0,
                         V(p["BodyOD"] / 2 - p["KnurlDepth"], -p["KnurlWidth"] / 2, zc - 0.5))
        body = body.cut(Rotated(k, (i + 0.5) * 360.0 / p["KnurlCount"]))
    # 45 deg lead-in on the bottom outer edge (into the magazine and the mask bore)
    R, c, z0 = p["BodyOD"] / 2, p["BodyChamfer"], zc + zb
    chamfer = Part.makeCylinder(R + 1.0, c, V(0, 0, z0)).cut(Part.makeCone(R - c, R, c, V(0, 0, z0)))
    body = body.cut(chamfer)
    parts["Body"] = body.removeSplitter()

    zPlate0 = zc + p["BodyTop"]
    parts["Plate"] = Annulus(p["PlateID"] / 2, p["PlateOD"] / 2, zPlate0, zPlate0 + p["PlateT"])
    zFace = zPlate0 + p["PlateT"]               # floating-ring face

    zFilter0 = zc + zb
    parts["Filter"] = Part.makeCylinder(p["FilterD"] / 2, p["FilterT"], V(0, 0, zFilter0))
    parts["CntFilm"] = Part.makeCylinder(p["CntD"] / 2, p["CntT"], V(0, 0, zFilter0 - p["CntT"]))

    # ---- mask
    zStencil = p["StencilT"]
    rb, rs = p["BallD"] / 2, p["MaskBallD"] / 2
    zBall = zFace - p["BallProtrusion"] + rb      # head ball pair centres
    # mask ball under a tangential pair of head balls, contact normals at
    # ContactDeg from vertical
    k = math.radians(p["ContactDeg"])
    halfSpacing = (rb + rs) * math.sin(k)
    zMaskBall = zBall - (rb + rs) * math.cos(k)
    zFrameTop = zMaskBall + p["MaskBallSink"]
    stencil = Stencil(p)
    frame = Annulus(p["FrameID"] / 2, p["FrameOD"] / 2, 0, zFrameTop)
    lobe = p["MaskHold"] == "lobe"
    earOuter = p["LobeEarOuterR"] if lobe else p["EarOuterR"]
    for a in EarAngles:
        # start the ear inside the frame wall, not tangent to its bore
        earR0 = p["FrameID"] / 2 + 1.0
        ear = Part.makeBox(earOuter - earR0, p["EarWidth"], zFrameTop,
                           V(earR0, -p["EarWidth"] / 2, 0))
        frame = frame.fuse(Rotated(ear, a))
    zBossTop = zFace - p["LobeGap"]
    rBoss = p["LobeMagD"] / 2 + p["MagPocketClear"] + p["LobeBossWall"]
    if lobe:
        for a in EarAngles:
            boss = Part.makeCylinder(rBoss, zBossTop - zFrameTop + 0.01, V(p["LobeMagR"], 0, zFrameTop - 0.01))
            frame = frame.fuse(Rotated(boss, a))
        g0, g1 = p["PushFlangeGap"]
        r0 = p["FrameOD"] / 2 - 0.01            # fused to the frame wall, lifted off the layer
        r1, z0 = p["PushFlangeR"], p["PushFlangeLift"]
        prof = Part.Face(Part.makePolygon([V(r0, 0, z0), V(r1, 0, z0 + (r1 - r0)), V(r1, 0, zFrameTop),
                                           V(r0, 0, zFrameTop), V(r0, 0, z0)]))
        flange = prof.revolve(V(0, 0, 0), V(0, 0, 1), 360.0 - (g1 - g0))
        flange.rotate(V(0, 0, 0), V(0, 0, 1), g1)
        frame = frame.fuse(flange)
    mask = stencil.fuse(frame)
    # 45 deg lead-in on the frame bore, where the cartridge drops in
    rb0, cb = p["FrameID"] / 2, p["FrameBoreChamfer"]
    mask = mask.cut(Part.makeCone(rb0, rb0 + cb, cb, V(0, 0, zFrameTop - cb)))
    maskBalls = []
    rPocket = rs + p["MaskBallPocketClear"]
    for a in EarAngles:
        # pocket floor sets the ball height; the ball presses in from the top
        pocket = Part.makeCylinder(rPocket, zFrameTop - (zMaskBall - rs) + 0.1,
                                   V(p["BallR"], 0, zMaskBall - rs))
        mask = mask.cut(Rotated(pocket, a))
        maskBalls.append(Rotated(Part.makeSphere(rs, V(p["BallR"], 0, zMaskBall)), a))
    weak, earMags = [], []
    for a in (EarAngles if lobe else ()):
        rp = p["LobeMagD"] / 2 + p["MagPocketClear"]
        pocket = Part.makeCylinder(rp, p["LobeMagT"] + 0.01, V(p["LobeMagR"], 0, zBossTop - p["LobeMagT"]))
        mask = mask.cut(Rotated(pocket, a))
        earMags.append(Rotated(Part.makeCylinder(p["LobeMagD"] / 2, p["LobeMagT"],
                                                 V(p["LobeMagR"], 0, zBossTop - p["LobeMagT"])), a))
    for a in (() if lobe else MagAngles):
        m = Part.makeCylinder(p["WeakMagD"] / 2, p["WeakMagT"],
                              V(p["WeakMagR"], 0, zFrameTop - p["WeakMagT"]))
        m = Rotated(m, a)
        pocket = Part.makeCylinder(p["WeakMagD"] / 2 + p["MagPocketClear"], p["WeakMagT"] + 0.01,
                                   V(p["WeakMagR"], 0, zFrameTop - p["WeakMagT"]))
        mask = mask.cut(Rotated(pocket, a))
        weak.append(m)
    parts["Mask"] = mask.removeSplitter()
    for i, s in enumerate(maskBalls):
        parts["MaskBall%d" % (i + 1)] = s
    for i, s in enumerate(weak):
        parts["WeakMagnet%d" % (i + 1)] = s
    for i, s in enumerate(earMags):
        parts["EarMagnet%d" % (i + 1)] = s

    # ---- head floating ring (reference)
    ringOD = max(p["RingOD"], 2 * (p["LobeMagR"] + p["LobeMagD"] / 2 + 1.5)) if lobe else p["RingOD"]
    ring = Annulus(p["RingID"] / 2, ringOD / 2, zFace, zFace + p["RingT"])
    balls, strong = [], []
    for a in EarAngles:
        for off in (-halfSpacing, halfSpacing):        # tangential pair per ear
            b = Rotated(Part.makeSphere(rb, V(p["BallR"], off, zBall)), a)
            ring = ring.cut(b)
            balls.append(b)
    for a in MagAngles:
        m = Rotated(Part.makeCylinder(p["StrongMagD"] / 2, p["StrongMagT"],
                                      V(p["StrongMagR"], 0, zFace)), a)
        ring = ring.cut(m)
        strong.append(m)
    lobeMags = []
    for a in (EarAngles if lobe else ()):
        m = Rotated(Part.makeCylinder(p["LobeMagD"] / 2, p["LobeMagT"], V(p["LobeMagR"], 0, zFace)), a)
        ring = ring.cut(m)
        lobeMags.append(m)
    parts["HeadRingRef"] = ring.removeSplitter()
    for i, s in enumerate(lobeMags):
        parts["HeadLobeMagnet%d" % (i + 1)] = s
    for i, s in enumerate(balls):
        parts["Ball%d" % (i + 1)] = s
    for i, s in enumerate(strong):
        parts["StrongMagnet%d" % (i + 1)] = s

    levels = dict(CartridgeBottom=zc, FilterBottom=zFilter0,
                  BandAboveStencil=zFilter0 - p["StencilT"], RingFace=zFace,
                  HeadBallCentre=zBall, MaskBallCentre=zMaskBall, FrameTop=zFrameTop,
                  StackPitch=zFace - zc)
    return parts, levels


def GeometryErrors(shape):
    """Boolean-algorithm self-check. isValid() alone misses self-intersecting
    faces, and booleans on such a shape can return empty without an error."""
    try:
        shape.check(True)
        return ""
    except Exception as e:
        return str(e).replace("\n", "; ")


def Check(parts, levels, p):
    print("Geometry self-check:")
    badGeo = 0
    for name, shape in parts.items():
        err = GeometryErrors(shape)
        if err:
            badGeo += 1
            print("  BAD %s: %s" % (name, err))
    print("  parts failing: %d" % badGeo)
    print("Levels (z, mm):")
    for k, v in levels.items():
        print("  %-16s %.3f" % (k, v))
    names = list(parts)
    bad = 0
    # the membrane is drawn uncompressed: its overlap with the jaws is the squeeze
    squeezed = {("Filter", "Body"), ("Body", "Filter"), ("Filter", "Collar"), ("Collar", "Filter")}
    print("Membrane squeeze when locked: %.2f mm" %
          (p["FilterT"] - (p["ClampGap"] - p["Squeeze"])))
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if (names[i], names[j]) in squeezed:
                continue
            a, b = parts[names[i]], parts[names[j]]
            if not a.BoundBox.intersect(b.BoundBox):
                continue
            vol = a.common(b).Volume
            if vol > 1e-3:
                bad += 1
                print("  OVERLAP %s / %s: %.4f mm^3" % (names[i], names[j], vol))
    print("Overlaps above 0.001 mm^3: %d" % bad)
    print("Clearances (min distance, mm):")
    cartNames = [n for n in ("Shim", "Collar", "Body", "Plate") if n in parts]
    # a compound, not a fuse: parts that touch face to face make the fuse fail
    cart = Part.makeCompound([parts[n] for n in cartNames])
    pairs = [
        ("cartridge to mask", cart, parts["Mask"]),
        ("ball to plate", parts["Ball1"], parts["Plate"]),
        ("head ball A to mask ball", parts["Ball1"], parts["MaskBall1"]),
        ("head ball B to mask ball", parts["Ball2"], parts["MaskBall1"]),
        ("head pair apart", parts["Ball1"], parts["Ball2"]),
        ("head ball to ear top", parts["Ball1"], parts["Mask"]),
        ("head ring to mask", parts["HeadRingRef"], parts["Mask"]),
        ("CNT film to cartridge", parts["CntFilm"], cart),
        ("filter to body sleeve", parts["Filter"], parts["Body"]),
    ]
    if "WeakMagnet1" in parts:
        pairs.insert(1, ("plate to weak magnet", parts["Plate"], parts["WeakMagnet1"]))
    boss = None
    if "EarMagnet1" in parts:
        # the boss alone: the mask material inside the boss cylinder above the frame top
        rBoss = p["LobeMagD"] / 2 + p["MagPocketClear"] + p["LobeBossWall"]
        zTop = levels["RingFace"] - p["LobeGap"]
        cyl = Part.makeCylinder(rBoss + 0.01, zTop - levels["FrameTop"] + 0.01, V(p["LobeMagR"], 0, levels["FrameTop"] + 0.001))
        boss = parts["Mask"].common(cyl)
        pairs += [("ear magnet to head magnet", parts["EarMagnet1"], parts["HeadLobeMagnet1"]),
                  ("ear magnet to plate", parts["EarMagnet1"], parts["Plate"]),
                  ("head ball to ear boss", parts["Ball1"], boss),
                  ("head ring to ear boss", parts["HeadRingRef"], boss)]
    for label, a, b in pairs:
        print("  %-24s %.3f" % (label, a.distToShape(b)[0]))
    if "EarMagnet1" in parts:
        # combo pile: the next combo's mask rests on this combo's plate, one ring-face height up
        pitch = levels["RingFace"]
        up = parts["Mask"].copy()
        up.translate(V(0, 0, pitch))
        low = Part.makeCompound([parts[n] for n in cartNames + ["Mask"]])
        upMag = parts["EarMagnet1"].copy()
        upMag.translate(V(0, 0, pitch))
        ov = up.common(low).Volume
        bossGap = up.distToShape(boss)[0]
        print("  %-24s %.4f (the next mask rests on this plate)" % ("pile: mask overlap", ov))
        print("  %-24s %.3f" % ("pile: boss to next mask", bossGap))
        print("  %-24s %.3f" % ("pile: ear magnet to next", parts["EarMagnet1"].distToShape(upMag)[0]))
        if ov > 1e-3 or bossGap < 0.2:
            raise ValueError("lobe hold: the next mask in a pile collides with this one (overlap %.4f, boss gap %.3f)"
                             % (ov, bossGap))
    # stencil pattern: openings must lie inside the CNT area; report the film's clearance to the stencil
    pat, holes = StencilPattern(p)
    if pat is not None:
        rmax = max(math.hypot(v.X, v.Y) for h in holes for v in h.Vertexes)
        area = sum(h.Area for h in holes)
        print("  stencil pattern          %s: %d openings, %.1f mm^2, reach r %.2f (CNT r %.1f)" %
              (os.path.basename(p["StencilPattern"]), len(holes), area, rmax, p["CntD"] / 2))
        if rmax > p["CntD"] / 2:
            raise ValueError("stencil openings reach r %.2f, outside the CNT area r %.1f" % (rmax, p["CntD"] / 2))
    print("  %-24s %.3f" % ("CNT film to stencil", parts["CntFilm"].distToShape(parts["Mask"])[0]))
    # control: a mask ball 0.05 mm too high must run into both head balls
    mb = parts["MaskBall1"].copy()
    mb.translate(V(0, 0, 0.05))
    print("  %-24s %.4f / %.4f (both must be > 0)" % (
        "control: mask ball +0.05", mb.common(parts["Ball1"]).Volume, mb.common(parts["Ball2"]).Volume))
    # collar along the whole twist, at the height the ramp holds it: must not hit
    worst = 0.0
    phi = -p["TwistDeg"]
    while phi <= 1e-9:
        c = parts["Collar"].copy()
        c.rotate(V(0, 0, 0), V(0, 0, 1), phi)
        c.translate(V(0, 0, -(p["RampRise"] - LiftAt(p, phi))))
        worst = max(worst, c.common(parts["Body"]).Volume)
        phi += 0.5
    print("  %-24s %.4f" % ("twist path max overlap", worst))
    # controls: at lock, a collar 0.1 mm lower must sit in the dwell floor; at
    # entry, a collar 0.1 mm lower must still be free (the floor is low there)
    c = parts["Collar"].copy()
    c.translate(V(0, 0, -0.1))
    print("  %-24s %.4f (must be > 0)" % ("control: locked, -0.1", c.common(parts["Body"]).Volume))
    c = parts["Collar"].copy()
    c.rotate(V(0, 0, 0), V(0, 0, 1), -p["TwistDeg"])
    c.translate(V(0, 0, -p["RampRise"] + 0.0))
    print("  %-24s %.4f (must be 0)" % ("control: entry, on floor", c.common(parts["Body"]).Volume))
    # two cartridges stacked in the magazine
    pitch = levels["StackPitch"]
    upper = [parts[n].copy() for n in cartNames + ["CntFilm"]]
    for s in upper:
        s.translate(V(0, 0, pitch))
    lowerAll = Part.makeCompound([parts[n] for n in cartNames + ["Filter"]])
    stackBad = sum(1 for s in upper[:-1] for n in cartNames + ["Filter"]
                   if s.common(parts[n]).Volume > 1e-3)
    print("  %-24s %d" % ("stack overlaps", stackBad))
    print("  %-24s %.3f" % ("stacked CNT to lower", upper[-1].distToShape(lowerAll)[0]))


def Save(parts, outDir, docName, stepNames=("Body", "Collar", "Shim", "Plate", "Mask")):
    os.makedirs(outDir, exist_ok=True)
    doc = FreeCAD.newDocument(docName)
    for name, shape in parts.items():
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
    doc.recompute()
    fcstd = os.path.join(outDir, docName + ".FCStd")
    doc.saveAs(fcstd)
    for name in stepNames:
        if doc.getObject(name):
            Part.export([doc.getObject(name)], os.path.join(outDir, "%s-%s.step" % (docName, name)))
    print("Saved", fcstd)
    FreeCAD.closeDocument(doc.Name)


def BuildSpanner(p):
    """Hand tool that turns the collar through its rim notches.

    Built in place, below the cartridge, as it engages during assembly: ring face
    on the flange underside, teeth up in the notches, wings 1 mm clear of the body.
    """
    zc = p["StencilT"] + p["SeatGap"]
    ringID, ringOD, t = 80.0, p["CollarOD"] - 0.5, p["SpannerT"]
    s = Annulus(ringID / 2, ringOD / 2, zc - t, zc)
    rc, sc = p["ToothRadialClear"], p["ToothSideClear"]
    notchMidR = (p["CollarID"] + p["CollarOD"]) / 4
    toothDeg = ArcDeg(p["NotchWidth"] - 2 * sc, notchMidR)
    tipDeg = ArcDeg(p["NotchWidth"] - 2 * sc - 2 * p["ToothTipNarrow"], notchMidR)
    zTip = zc + p["NotchDepth"] - 0.2              # tooth top, 0.2 mm short of the notch roof
    for i in range(p["NotchCount"]):
        a = i * 360.0 / p["NotchCount"]
        s = s.fuse(Sector(p["CollarID"] / 2 + rc, p["CollarOD"] / 2 - rc,
                          zc - 0.5, zTip - 0.5, a - toothDeg / 2, a + toothDeg / 2))
        s = s.fuse(Sector(p["CollarID"] / 2 + rc, p["CollarOD"] / 2 - rc,
                          zTip - 0.6, zTip, a - tipDeg / 2, a + tipDeg / 2))
    for a in (30.0, 210.0):        # between notches
        wing = Part.makeBox(66.0 - 44.0, 22.0, t - 1.0, V(44.0, -11.0, zc - t))
        s = s.fuse(Rotated(wing, a))
    return s.removeSplitter()


def ToBed(shape, flip=False):
    s = shape.copy()
    if flip:
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    s.translate(V(0, 0, -s.BoundBox.ZMin))
    return s


def ExportPrintSet(p, outDir):
    """Print-oriented STEP files: each part sits on z = 0 as it should be printed."""
    os.makedirs(outDir, exist_ok=True)
    parts, _ = Build(p)
    spanner = BuildSpanner(p)
    print("  spanner/collar overlap %.4f, spanner/body overlap %.4f, spanner to body %.3f, "
          "spanner to CNT %.3f" % (spanner.common(parts["Collar"]).Volume,
                                   spanner.common(parts["Body"]).Volume,
                                   spanner.distToShape(parts["Body"])[0],
                                   spanner.distToShape(parts["CntFilm"])[0]))
    files = {
        "FilterCartridge-Body.step": ToBed(parts["Body"], flip=True),     # plate face on the bed
        "FilterCartridge-Mask.step": ToBed(parts["Mask"]),                 # stencil on the bed
        "FilterCartridge-PlateStandIn.step": ToBed(parts["Plate"]),       # printed fit-test stand-in
        "FilterCartridge-CollarSpanner.step": ToBed(spanner),             # back on the bed, teeth up
    }
    # remove collars from earlier exports so a stale gap value cannot be printed
    for old in os.listdir(outDir):
        if old.startswith("FilterCartridge-Collar-Gap") and old.endswith(".step"):
            os.remove(os.path.join(outDir, old))
    # owner, 2026-11-05: the six-lug ramped collar at locked gap -0.10 has the right
    # feel, so it is the one collar exported (Squeeze 0.1 against ClampGap 0.0).
    # Add values here to print a bracket again.
    for s in p["PrintSqueezes"]:
        q = dict(p)
        q["Squeeze"] = s
        collar = Build(q)[0]["Collar"]
        gap = p["ClampGap"] - s
        files["FilterCartridge-Collar-Gap%+.2f.step" % gap] = ToBed(collar)  # flange on the bed
    for name, shape in files.items():
        err = GeometryErrors(shape)
        if err:
            raise RuntimeError("%s fails the geometry self-check: %s" % (name, err))
        target = os.path.join(outDir, name)
        shape.exportStep(target)
        # read the file back: a shape can pass in memory and fail after STEP export
        back = Part.read(target)
        err = GeometryErrors(back)
        if err or len(back.Solids) != 1 or abs(back.Volume - shape.Volume) > 1e-3 * shape.Volume:
            raise RuntimeError("%s fails after STEP round trip: solids=%d vol %.1f vs %.1f; %s" %
                               (name, len(back.Solids), back.Volume, shape.Volume, err[:200]))
        bb = shape.BoundBox
        print("  %-40s %6.1f x %6.1f x %5.2f mm  self-check ok, re-import ok" %
              (name, bb.XLength, bb.YLength, bb.ZLength))


def ExportLobeMask(p, outDir):
    """The lobe hold mask in print orientation (stencil on the bed, 0.2 mm nozzle)."""
    parts, _ = Build(p)
    name = "FilterCartridge-Mask-LobeHold.step"
    shape = ToBed(parts["Mask"])
    err = GeometryErrors(shape)
    if err:
        raise RuntimeError("%s fails the geometry self-check: %s" % (name, err))
    target = os.path.join(outDir, name)
    shape.exportStep(target)
    back = Part.read(target)
    if GeometryErrors(back) or len(back.Solids) != 1 or abs(back.Volume - shape.Volume) > 1e-3 * shape.Volume:
        raise RuntimeError("%s fails after STEP round trip" % name)
    bb = shape.BoundBox
    print("  %-40s %6.1f x %6.1f x %5.2f mm  self-check ok, re-import ok" % (name, bb.XLength, bb.YLength, bb.ZLength))


def PlateDxf(p, path):
    """Flat pattern of the steel plate for a metal laser-cutting service: an ASCII R12 DXF
    in mm on layer CUT, the format tools/check_dxf.py reads back. The bore is a circle; the outline
    is a closed 360-segment polygon (chord error under 0.002 mm), because check_dxf.py reads bulged
    polylines as obrounds and cannot size a full-circle outline. Cut from PlateT sheet: G90
    galvanized steel 0.030 in (any magnetic steel of that thickness works)."""
    ro, d = p["PlateOD"] / 2, p["PlateID"]
    n = 360
    out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4",
           "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
           "9", "$EXTMAX", "10", "%.4f" % (2 * ro), "20", "%.4f" % (2 * ro), "30", "0.0",
           "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES",
           "0", "POLYLINE", "8", "CUT", "66", "1", "10", "0.0", "20", "0.0", "30", "0.0", "70", "1"]
    for i in range(n):
        a = 2 * math.pi * i / n
        out += ["0", "VERTEX", "8", "CUT", "10", "%.4f" % (ro + ro * math.cos(a)),
                "20", "%.4f" % (ro + ro * math.sin(a)), "30", "0.0"]
    out += ["0", "SEQEND", "8", "CUT",
            "0", "CIRCLE", "8", "CUT", "10", "%.4f" % ro, "20", "%.4f" % ro, "30", "0.0", "40", "%.4f" % (d / 2),
            "0", "ENDSEC", "0", "EOF"]
    open(path, "w", encoding="ascii", newline="\n").write("\n".join(out) + "\n")
    print("  %s: OD %.1f, ID %.1f, %.3f mm magnetic steel" % (os.path.basename(path), 2 * ro, d, p["PlateT"]))


Variants = (
    ("FilterCartridge", {}),                                    # bonded stainless shim
    ("FilterCartridgePrintedFlange", {"PrintedFlange": True}),  # collar with printed jaw
)


def Main():
    here = os.path.dirname(os.path.abspath(__file__))
    outDir = os.path.join(os.path.dirname(here), "CAD", "Filter Cartridge")
    for docName, override in Variants:
        p = dict(P)
        p.update(override)
        print("==== %s" % docName)
        parts, levels = Build(p)
        Check(parts, levels, p)
        Save(parts, outDir, docName)
    print("==== print set (printed flange, 0.4 mm nozzle)")
    p = dict(P)
    p["PrintedFlange"] = True
    ExportPrintSet(p, os.path.join(outDir, "Print 0.4mm nozzle"))
    print("==== plate flat pattern (laser-cut steel)")
    for old in os.listdir(outDir):          # a renamed or re-thicknessed plate must not linger
        if old.startswith("FilterCartridge-Plate-") and old.endswith(".dxf"):
            os.remove(os.path.join(outDir, old))
    PlateDxf(p, os.path.join(outDir, "FilterCartridge-Plate-G90-0.030in.dxf"))
    print("==== lobe hold variant (issue 230)")
    q = dict(P)
    q.update(PrintedFlange=True, MaskHold="lobe")
    parts, levels = Build(q)
    Check(parts, levels, q)
    lobeDir = os.path.join(outDir, "Lobe hold")
    Save(parts, lobeDir, "FilterCartridgeLobeHold", stepNames=())   # the cartridge is unchanged; mask STEP below
    ExportLobeMask(q, lobeDir)


Main()
