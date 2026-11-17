# Builds the latch test set for the "combo pile" mask library: masks stored with a fresh
# cartridge seated in them, stacked in piles, each mask held to the steel plate below it by two
# latch magnets in its bottom and released by a 10 mm slide in +Y.
#
# Run with FreeCAD's console:  freecadcmd tools/build_latch_test.py
# Writes print-ready STEP files and an acrylic DXF to CAD/Filter Cartridge/Latch test/.
#
# The mask, cartridge and coupling geometry come from tools/build_filter_cartridge.py (its P
# dict and Build()), so the test pieces follow any change made there. Frame for the mask:
# z = 0 is the mask bottom, +Y is the release slide direction. Dimensions in mm.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))

# ---- load the cartridge generator's parameters and builders without running its Main()
Src = open(os.path.join(Here, "build_filter_cartridge.py"), encoding="utf-8").read()
Cut = Src.rindex("\nMain()")
Gen = {"__file__": os.path.join(Here, "build_filter_cartridge.py")}
exec(compile(Src[:Cut], "build_filter_cartridge.py", "exec"), Gen)
P, Build, Annulus, Sector, Rotated, GeometryErrors = (Gen[n] for n in
                                                      ("P", "Build", "Annulus", "Sector", "Rotated", "GeometryErrors"))

# ---- latch test parameters
L = dict(
    LatchMagD=3.0,          # 3 x 2 mm N52 disc, the same part as the mask's weak magnets
    LatchMagT=2.0,
    LatchR=53.0,            # under the plate ring (r 46..54.5); 0.7 mm wall to the frame bore
    LatchAngles=(90.0, 270.0),
    PocketClear=0.1,        # pocket radius over the magnet radius
    Recesses=(0.0, 0.5, 1.0),   # magnet face height above the mask bottom: brackets the latch force
    Slide=10.0,             # release slide in +Y
    # Gripper-B pick magnets, measured from the Gripper-B preview assembly STEP (not in the repo)
    HoldR=51.5,
    HoldAngles=(50.0, 70.0, 170.0, 190.0, 290.0, 310.0),
    HoldMagD=6.0,
    HoldMagT=3.5,           # two 6 x 1.75 discs stacked
    HoldFloor=1.375,        # magnet face above the ring face (Gripper-B: 379.8 - 378.425)
    ToolT=8.0,
    ToolRingRI=43.0,        # Gripper-B ring bore r 43
    ToolRingRO=56.0,
    LobeW=14.0,             # lobes carrying the ball pairs out to r 62
    HubD=22.0,
    HubHoleD=8.0,
    SpokeW=8.0,
    # pile seat: holds one steel plate ring flush with its top
    SeatOD=132.0,
    SeatH=12.0,
    SeatBoreD=80.0,
    SeatScrewR=60.0,
    SeatScrewAngles=(30.0, 150.0, 270.0),
    # acrylic base
    BaseW=160.0,
    FootHoleD=5.0,
)


def Levels(p):
    """Held-state levels of Build(), mask frame."""
    return Build(p)[1]


def LatchPocket(recess, a):
    rp = L["LatchMagD"] / 2 + L["PocketClear"]
    s = Part.makeCylinder(rp, L["LatchMagT"] + recess + 0.01, V(L["LatchR"], 0, -0.01))
    return Rotated(s, a)


def LatchMagnet(recess, a, dy=0.0):
    s = Part.makeCylinder(L["LatchMagD"] / 2, L["LatchMagT"], V(L["LatchR"], 0, recess))
    s = Rotated(s, a)
    s.translate(V(0, dy, 0))
    return s


def TestMask(p, recess):
    mask = Build(p)[0]["Mask"].copy()
    for a in L["LatchAngles"]:
        mask = mask.cut(LatchPocket(recess, a))
    # recess code on the frame top: 0, 1 or 2 dots at 150 deg, clear of the magnets (60/90/180/
    # 270/300) and the ears (0/120/240), so the three prints can be told apart
    lv = Levels(p)
    n = L["Recesses"].index(recess)
    for i in range(n):
        a = 150.0 + (i - (n - 1) / 2) * 4.0
        dot = Part.makeCylinder(0.8, 0.31, V(53.4, 0, lv["FrameTop"] - 0.3))
        mask = mask.cut(Rotated(dot, a))
    return mask.removeSplitter()


def PullTool(p):
    """Stand-in for the Gripper-B ring face: six pick magnets, three ball pairs, a cord hub.
    Frame: z = 0 is the ring face, the tool body is above it, print face-down."""
    T = L["ToolT"]
    rb = p["BallD"] / 2
    k = math.radians(p["ContactDeg"])
    half = (rb + p["MaskBallD"] / 2) * math.sin(k)
    zBallC = rb - p["BallProtrusion"]                      # ball centre above the face (0.5)
    body = Annulus(L["ToolRingRI"], L["ToolRingRO"], 0, T)
    for a in (0.0, 120.0, 240.0):
        lobe = Part.makeBox(p["EarOuterR"] - L["ToolRingRO"] + 1.0, L["LobeW"], T,
                            V(L["ToolRingRO"] - 1.0, -L["LobeW"] / 2, 0))
        body = body.fuse(Rotated(lobe, a))
    # spokes and hub for the cord
    hub = Part.makeCylinder(L["HubD"] / 2, T, V(0, 0, 0))
    for a in (90.0, 210.0, 330.0):
        sp = Part.makeBox(L["ToolRingRI"] + 1.0, L["SpokeW"], T, V(0, -L["SpokeW"] / 2, 0))
        hub = hub.fuse(Rotated(sp, a))
    body = body.fuse(hub)
    body = body.cut(Part.makeCylinder(L["HubHoleD"] / 2, T + 1, V(0, 0, -0.5)))
    # pick magnet pockets, open at the top, floor HoldFloor above the face
    for a in L["HoldAngles"]:
        pk = Part.makeCylinder(L["HoldMagD"] / 2 + L["PocketClear"], T, V(L["HoldR"], 0, L["HoldFloor"]))
        body = body.cut(Rotated(pk, a))
    # ball pockets, open at the face; a pressed ball protrudes BallProtrusion below it
    balls = []
    for a in (0.0, 120.0, 240.0):
        for off in (-half, half):
            pk = Part.makeCylinder(rb + p["MaskBallPocketClear"], zBallC + rb, V(p["BallR"], off, -0.01))
            body = body.cut(Rotated(pk, a))
            balls.append(Rotated(Part.makeSphere(rb, V(p["BallR"], off, zBallC)), a))
    # +Y direction notch on the outer rim
    notch = Part.makeBox(4, 4, T + 1, V(-2, L["ToolRingRO"] - 2.5, -0.5))
    body = body.cut(notch)
    return body.removeSplitter(), balls


def PileSeat(p):
    H = L["SeatH"]
    s = Part.makeCylinder(L["SeatOD"] / 2, H)
    s = s.cut(Part.makeCylinder(L["SeatBoreD"] / 2, H + 1, V(0, 0, -0.5)))
    # recess for the steel plate ring, flush with the top
    s = s.cut(Annulus(p["PlateID"] / 2 - 0.2, p["PlateOD"] / 2 + 0.2, H - p["PlateT"], H + 0.1))
    for a in L["SeatScrewAngles"]:
        hole = Part.makeCylinder(1.7, H + 1, V(L["SeatScrewR"], 0, -0.5))
        cb = Part.makeCylinder(3.1, H - 4.0 + 0.01, V(L["SeatScrewR"], 0, 4.0))   # head from the top
        s = s.cut(Rotated(hole.fuse(cb), a))
    # ear marks (0/120/240) and +Y mark on the outer rim
    for a in (0.0, 120.0, 240.0):
        m = Part.makeBox(3, 1.2, 1.0, V(L["SeatOD"] / 2 - 2.5, -0.6, H - 1.0))
        s = s.cut(Rotated(m, a))
    s = s.cut(Part.makeBox(4, 6, 1.0, V(-2, L["SeatOD"] / 2 - 5, H - 1.0)))
    return s.removeSplitter()


# ---------------------------------------------------------------- acrylic base (DXF R12)
def DxfBase(path, engravePath):
    """Cut file (layer CUT, checked by tools/check_dxf.py) and a separate engrave file, because
    check_dxf.py reads every circle as a hole whatever its layer."""
    W = L["BaseW"]
    c = W / 2
    ents, eng = [], []
    def Poly(pts, layer):
        out = ["0", "POLYLINE", "8", layer, "66", "1", "10", "0.0", "20", "0.0", "30", "0.0", "70", "1"]
        for x, y in pts:
            out += ["0", "VERTEX", "8", layer, "10", "%.4f" % x, "20", "%.4f" % y, "30", "0.0"]
        return out + ["0", "SEQEND", "8", layer]
    def Circle(x, y, d, layer):
        return ["0", "CIRCLE", "8", layer, "10", "%.4f" % x, "20", "%.4f" % y, "30", "0.0", "40", "%.4f" % (d / 2)]
    def Line(x0, y0, x1, y1, layer):
        return ["0", "LINE", "8", layer, "10", "%.4f" % x0, "20", "%.4f" % y0, "30", "0.0",
                "11", "%.4f" % x1, "21", "%.4f" % y1, "31", "0.0"]
    ents += Poly([(0, 0), (W, 0), (W, W), (0, W)], "CUT")
    for a in L["SeatScrewAngles"]:
        ents += Circle(c + L["SeatScrewR"] * math.cos(math.radians(a)),
                       c + L["SeatScrewR"] * math.sin(math.radians(a)), 3.4, "CUT")
    for x, y in ((8, 8), (W - 8, 8), (W - 8, W - 8), (8, W - 8)):
        ents += Circle(x, y, L["FootHoleD"], "CUT")
    # engraved: seat outline, and the pull tool's +Y notch at 0 and at the 10 mm release slide
    eng += Circle(c, c, L["SeatOD"], "ENGRAVE")
    y0 = c + L["ToolRingRO"]
    for dy in (0.0, L["Slide"]):
        eng += Line(c - 6.0, y0 + dy, c + 6.0, y0 + dy, "ENGRAVE")
    eng += Line(c, y0, c, y0 + L["Slide"], "ENGRAVE")
    for target, body in ((path, ents), (engravePath, eng)):
        out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "9", "$INSUNITS", "70", "4",
               "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
               "9", "$EXTMAX", "10", "%.4f" % W, "20", "%.4f" % W, "30", "0.0",
               "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"] + body + ["0", "ENDSEC", "0", "EOF"]
        open(target, "w", encoding="ascii", newline="\n").write("\n".join(out) + "\n")


# ---------------------------------------------------------------- checks
def OverlapArea(disc_c, r, ri, ro, n=400):
    """Area of a disc (centre, radius) lying inside the annulus ri..ro, by grid sampling."""
    cx, cy = disc_c
    hit = tot = 0
    for i in range(n):
        for j in range(n):
            x = cx - r + 2 * r * (i + 0.5) / n
            y = cy - r + 2 * r * (j + 0.5) / n
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                tot += 1
                rr = math.hypot(x, y)
                if ri <= rr <= ro:
                    hit += 1
    return hit / tot


def Checks(p, masks, tool, toolBalls, seat):
    lv = Levels(p)
    parts, _ = Build(p)
    print("Levels: FrameTop %.3f  RingFace %.3f  HeadBallCentre %.3f  MaskBallCentre %.3f" %
          (lv["FrameTop"], lv["RingFace"], lv["HeadBallCentre"], lv["MaskBallCentre"]))
    bad = 0
    # 1. latch pockets keep printable walls and miss the weak-magnet pockets
    for rec, m in masks.items():
        for a in L["LatchAngles"]:
            pk = LatchPocket(rec, a)
            wall_bore = L["LatchR"] - (L["LatchMagD"] / 2 + L["PocketClear"]) - p["FrameID"] / 2
            skin = lv["FrameTop"] - (L["LatchMagT"] + rec)
            dmin = min(pk.distToShape(parts["WeakMagnet%d" % i])[0] for i in (1, 2, 3))
            print("  recess %.1f @%3.0f: wall to bore %.2f, skin to frame top %.2f, to weak magnets %.2f" %
                  (rec, a, wall_bore, skin, dmin))
            if wall_bore < 0.6 or skin < 0.5 or dmin < 1.0:
                bad += 1
    # 2. magnet over the plate ring below: aligned vs after the release slide
    rM = L["LatchMagD"] / 2
    for a in L["LatchAngles"]:
        c0 = (L["LatchR"] * math.cos(math.radians(a)), L["LatchR"] * math.sin(math.radians(a)))
        for dy in (0.0, L["Slide"]):
            f = OverlapArea((c0[0], c0[1] + dy), rM, p["PlateID"] / 2, p["PlateOD"] / 2)
            print("  latch magnet @%3.0f, slide %4.1f: %5.1f %% over the plate ring" % (a, dy, 100 * f))
            if dy == 0.0 and f < 0.9:
                bad += 1
            if dy > 0 and f > 0.0:
                bad += 1
    # 3. pull tool on a combo in the held geometry: no overlaps, ball pairs straddle the mask balls
    t = tool.copy(); t.translate(V(0, 0, lv["RingFace"]))
    tb = [b.copy() for b in toolBalls]
    for b in tb:
        b.translate(V(0, 0, lv["RingFace"]))
    for name in ("Mask", "Plate", "Body", "Collar"):
        vol = t.common(parts[name]).Volume
        d = t.distToShape(parts[name])[0]
        print("  tool vs %-6s overlap %.4f, gap %.3f" % (name, vol, d))
        if vol > 1e-3:
            bad += 1
    for i, b in enumerate(tb[:2]):
        d = b.distToShape(parts["MaskBall1"])[0]
        print("  tool ball %d to mask ball: %.3f (contact expected)" % (i + 1, d))
        if d > 0.02:
            bad += 1
    # control: the tool 0.05 lower must hit the mask balls
    t2 = [b.copy() for b in tb[:2]]
    for b in t2:
        b.translate(V(0, 0, -0.05))
    ctl = sum(b.common(parts["MaskBall1"]).Volume for b in t2)
    print("  control: tool 0.05 lower, ball overlap %.4f (must be > 0)" % ctl)
    if ctl <= 0:
        bad += 1
    # 4. pick magnets over the plate ring
    for a in L["HoldAngles"][:2]:
        c0 = (L["HoldR"] * math.cos(math.radians(a)), L["HoldR"] * math.sin(math.radians(a)))
        f = OverlapArea(c0, L["HoldMagD"] / 2, p["PlateID"] / 2, p["PlateOD"] / 2)
        print("  pick magnet @%3.0f: %5.1f %% over the plate ring" % (a, 100 * f))
    # 5. seat: the plate ring sits flush, the bore clears the stencil margin
    print("  seat: ring recess depth %.2f = plate %.2f; seat bore r %.1f vs plate ID r %.1f" %
          (p["PlateT"], p["PlateT"], L["SeatBoreD"] / 2, p["PlateID"] / 2))
    print("Checks failing: %d" % bad)
    return bad


def ToBed(shape, flip=False):
    s = shape.copy()
    if flip:
        s.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    s.translate(V(0, 0, -s.BoundBox.ZMin))
    return s


def Export(files, outDir):
    os.makedirs(outDir, exist_ok=True)
    for name, shape in files.items():
        err = GeometryErrors(shape)
        if err:
            raise RuntimeError("%s fails the geometry self-check: %s" % (name, err))
        target = os.path.join(outDir, name)
        shape.exportStep(target)
        back = Part.read(target)
        err = GeometryErrors(back)
        if err or len(back.Solids) != 1 or abs(back.Volume - shape.Volume) > 1e-3 * shape.Volume:
            raise RuntimeError("%s fails after STEP round trip: solids=%d; %s" % (name, len(back.Solids), err[:200]))
        bb = shape.BoundBox
        print("  %-36s %6.1f x %6.1f x %5.2f mm  self-check ok, re-import ok" %
              (name, bb.XLength, bb.YLength, bb.ZLength))


def Main():
    p = dict(P)
    p["PrintedFlange"] = True          # the cartridges printed for the owner have the printed jaw
    masks = {r: TestMask(p, r) for r in L["Recesses"]}
    tool, toolBalls = PullTool(p)
    seat = PileSeat(p)
    bad = Checks(p, masks, tool, toolBalls, seat)
    if bad:
        raise SystemExit("latch test checks failed: %d" % bad)
    outDir = os.path.join(os.path.dirname(Here), "CAD", "Filter Cartridge", "Latch test")
    files = {}
    for r, m in masks.items():
        files["LatchTest-Mask-Recess%.1f.step" % r] = ToBed(m)          # stencil on the bed
    files["LatchTest-PullTool.step"] = ToBed(tool)                       # face on the bed
    files["LatchTest-PileSeat.step"] = ToBed(seat)                       # ring recess up
    Export(files, outDir)
    DxfBase(os.path.join(outDir, "LatchTest-Base-acrylic-3mm.dxf"),
            os.path.join(outDir, "LatchTest-Base-acrylic-3mm-engrave.dxf"))
    print("  LatchTest-Base-acrylic-3mm.dxf (cut) and -engrave.dxf written, same origin")
    doc = FreeCAD.newDocument("LatchTest")
    for name, shape in list(files.items()):
        o = doc.addObject("Part::Feature", name.replace("LatchTest-", "").replace(".step", "").replace(".", "_"))
        o.Shape = shape
    doc.saveAs(os.path.join(outDir, "LatchTest.FCStd"))
    FreeCAD.closeDocument(doc.Name)
    print("Saved", outDir)


Main()
