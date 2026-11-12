"""Build the RMR operator panel in FreeCAD: the display, the front plate, its cradle and bracket, and its 2020 frame.

Every size comes from the operator panel layout in tools/draw_wiring.py (OpDisplay, OpHousing,
OpWindow, OpPlate, OpControls and the constants round them), which sheet 2D draws too, so the
drawing and the model cannot drift apart. The display is a fit-check envelope taken from the owner's
3D scan of 2026-11-11 (the scan itself stays out of git, in CAD/DisplayScan): its body, the straight
sides and the rounded edge, the back, the rear housing with its VESA 75 holes, and the zone where its
ports and their plugs are. The controls' bodies behind the plate and their parts in front of it are
assumed sizes (OpRearBody, OpFront); they are drawn translucent and carry SizeSource = assumed.

Frame: X to the right and Z up as the operator sees the panel, Y into the machine. The display's
front face is the plane Y = 0 and the plate lies in front of it (Y < 0), so FreeCAD's Front view
shows the panel as the operator sees it.

The display is held like this: the plate's window is smaller than the display's front face, so the
display cannot pass through; a printed cradle ring round its straight sides, screwed to the plate from
the front and printed in two PETG pieces joined by half laps (OpCradleLap), locates it; a printed bracket standing on the ring presses it against the plate through
closed-cell foam pads on the rear housing's back face (OpBracketGap). No screw goes into the VESA holes,
which would fix the display's depth a second time.

A ring of 2020 extrusion on the plate's back edge stiffens it, and two vertical 2020 spines behind the
display, standing on four risers off the ring's top and bottom rails, carry a monitor spring arm's VESA
100 plate on their back slots (OpFrameScrews, OpSpineX, OpArmVesa). The extrusions are drawn as plain
20 x 20 bars: their slots and the drilled and tapped joints are described in draw_wiring.py, not modelled.
Not placed yet: the Pi 5, which the wiring sheets put behind the display, where the spines and the arm's
plate now are; Clearances() cannot see a part that is not modelled.

Run it inside FreeCAD 1.x, from the Python console or a macro:
    import runpy; runpy.run_path(r"<repo>/tools/build_operator_panel.py", run_name="__main__")
It builds the document, checks the fits (Checks()) and refuses to save if one fails or two solids
overlap, and writes CAD/Operator Panel/OperatorPanel.FCStd and OperatorPanel.step. Set RMR_CAD_OUT to
write somewhere else. Run headless (freecadcmd) it builds and checks the same solids, but its files
carry no colors, so commit only what a GUI run wrote.
"""

import importlib
import math
import os
import sys

import FreeCAD as App
import Part

Here = os.path.dirname(os.path.abspath(__file__))
if Here not in sys.path:
    sys.path.insert(0, Here)
import draw_wiring as W  # noqa: E402

importlib.reload(W)        # take the layout as it is on disk now, not as an earlier run left it

OutDir = os.environ.get("RMR_CAD_OUT") or os.path.join(os.path.dirname(Here), "CAD", "Operator Panel")
DocName = "OperatorPanel"
V = App.Vector

# Paul Tol colors: Bright for the controls, Light for the printed parts, greys for the rest.
Fill = {"plate": "#DDDDDD", "display": "#333333", "frame": "#999999", "arm": "#555555", "lit": "#4477AA", "cradle": "#77AADD", "bracket": "#EEDD88",
        "pad": "#444444", "ports": "#EE8866", "rear": "#BBBBBB", "legend": "#CCBB44",
        "estop": "#EE6677", "red": "#EE6677", "green": "#228833", "blue": "#4477AA", "selector": "#228833"}
Transp = {"plate": 60, "ports": 70, "rear": 60, "arm": 50}
MinWeb = 5.0                       # least acrylic between two cut-outs, or a cut-out and the edge


def RoundBox(w, h, r, y0, depth, cx=0.0, cz=0.0):
    """A w (X) by h (Z) rectangle with corner radius r, from Y = y0 to y0 + depth."""
    b = Part.makeBox(w, depth, h, V(cx - w / 2, y0, cz - h / 2))
    if r > 0.01:
        b = b.makeFillet(r, [e for e in b.Edges if abs(e.tangentAt(e.FirstParameter).y) > 0.999])
    return b


def CylY(d, y0, depth, x, z):
    return Part.makeCylinder(d / 2, depth, V(x, y0, z), V(0, 1, 0))


# ---- the layout, read once
BW, BH, BR = W.OpDisplay
HW, HH, HR, HT = W.OpHousing
WW, WH = W.OpWindow
PW, PH, PR = W.OpPlate
T = W.OpPlateT
Wall, Depth = W.OpCradleWall, W.OpCradleDepth
(IW, IH, IR), (OW, OH, OR), (RingX, RingZ) = W.OpRing()        # pocket, outside, centre lines of its sides
BrSide, BrT, BrArm = W.OpBracket
BrY0 = HT + W.OpBracketGap                                       # bracket's face against the foam pads
CradleScrews, LegScrews, FrameScrews = W.OpCradleScrews(), W.OpLegScrews(), W.OpFrameScrews()
P = W.OpProfile


def Display():
    body = RoundBox(BW, BH, BR, 0.0, W.OpDisplayEdge)
    back = [e for e in body.Edges if all(abs(v.Point.y - W.OpDisplayEdge) < 1e-6 for v in e.Vertexes)]
    body = body.makeFillet(W.OpDisplayEdge - W.OpDisplayWall, back)
    # the back rises from the edge toward the housing: a slab at its highest, inset past the rounded edge
    slab = RoundBox(BW - 8.0, BH - 8.0, BR - 4.0, W.OpDisplayEdge - 1.0, W.OpDisplayBack - W.OpDisplayEdge + 1.0)
    house = RoundBox(HW, HH, HR, W.OpDisplayBack - 1.0, HT - W.OpDisplayBack + 1.0)
    d = body.fuse(slab).fuse(house).removeSplitter()
    for sx in (1, -1):
        for sz in (1, -1):
            d = d.cut(CylY(W.OpVesaHoleD, HT - 8.0, 8.1, sx * W.OpVesaHalf, sz * W.OpVesaHalf))
    return d


def LitArea():
    aw, ah = W.OpLit
    y = -0.02
    pts = [V(-aw / 2, y, -ah / 2), V(aw / 2, y, -ah / 2), V(aw / 2, y, ah / 2), V(-aw / 2, y, ah / 2)]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))


def PortZone():
    z0, z1, y0, y1 = W.OpPorts
    plug = 45.0                    # assumed: a plug and the start of its cable's bend
    return Part.makeBox(plug, y1 - y0, z1 - z0, V(-HW / 2 - plug, y0, z0))


def Plate():
    p = RoundBox(PW, PH, PR, -T, T)
    p = p.cut(RoundBox(WW, WH, 1.0, -T - 1.0, T + 2.0))
    for _, _, x, z in W.OpControls:
        p = p.cut(CylY(W.OpHoleD, -T - 1.0, T + 2.0, x, z))
    for x, z in CradleScrews:
        p = p.cut(CylY(W.OpScrewD, -T - 1.0, T + 2.0, x, z))
    for x, z in FrameScrews:
        p = p.cut(CylY(W.OpFrameScrewD, -T - 1.0, T + 2.0, x, z))
    return p


def Frame():
    """[(name, solid, fill, source)] for the 2020 ring, risers, spines, corner brackets and the arm's plate."""
    out = []
    rz = PH / 2 - P / 2                            # the rails' centre lines
    for n, sz in (("RailTop", 1), ("RailBottom", -1)):
        out.append((n, Part.makeBox(PW, P, P, V(-PW / 2, 0.0, sz * rz - P / 2)), "frame", "2020"))
    for n, sx in (("PostRight", 1), ("PostLeft", -1)):
        out.append((n, Part.makeBox(P, P, PH - 2 * P, V(sx * (PW / 2 - P / 2) - P / 2, 0.0, -PH / 2 + P)), "frame", "2020"))
    sy, sx0 = W.OpSpineY, W.OpSpineX
    k = W.OpBracketKit
    i = 0
    for sx in (1, -1):
        out.append(("Spine" + ("Right" if sx > 0 else "Left"),
                    Part.makeBox(P, P, PH, V(sx * sx0 - P / 2, sy, -PH / 2)), "frame", "2020"))
        for sz in (1, -1):
            i += 1
            out.append(("Riser%d" % i, Part.makeBox(P, sy - P, P, V(sx * sx0 - P / 2, P, sz * rz - P / 2)), "frame", "2020"))
            # cast corner brackets on both sides of the riser, against the rail's back face
            for j, side in enumerate((1, -1)[:W.OpRiserBrackets]):
                x0 = sx * sx0 + side * P / 2 + (0 if side > 0 else -k)
                out.append(("CornerBracket%d%s" % (i, "ab"[j]), Part.makeBox(k, k, P, V(x0, P, sz * rz - P / 2)),
                            "frame", "assumed"))
    a, at = W.OpArmPlate
    out.append(("ArmPlate", Part.makeBox(a, at, a, V(-a / 2, sy + P, -a / 2)), "arm", "assumed"))
    return out


def Cradle():
    c = RoundBox(OW, OH, OR, 0.0, Depth).cut(RoundBox(IW, IH, IR, -1.0, Depth + 2.0))
    for x, z in CradleScrews:
        c = c.cut(CylY(W.OpInsertD, -0.01, W.OpInsertL, x, z))
    for x, z in LegScrews:
        c = c.cut(CylY(W.OpInsertD, Depth - W.OpInsertL, W.OpInsertL + 0.01, x, z))
    return c


def CradleHalves():
    """The cradle in two pieces with a half lap on its top and bottom sides (OpCradleLap): the left piece
    keeps the back layer of the lap, the right piece the front layer, each tongue OpCradleLap[2] short of
    the other piece's shoulder."""
    c = Cradle()
    x0, x1, e = W.OpCradleLap
    big, half = 400.0, Depth / 2

    def Slab(xa, xb, ya, yb):
        return Part.makeBox(xb - xa, yb - ya, big, V(xa, ya, -big / 2))
    left = c.common(Slab(-big, x0, -1.0, Depth + 1.0).fuse(Slab(x0, x1 - e, half, Depth + 1.0)))
    right = c.common(Slab(x1, big, -1.0, Depth + 1.0).fuse(Slab(x0 + e, x1, -1.0, half)))
    return left.removeSplitter(), right.removeSplitter()


def Bracket():
    b = RoundBox(BrSide, BrSide, 6.0, BrY0, BrT)
    b = b.fuse(RoundBox(BrArm, OH, 3.0, BrY0, BrT))   # the arm runs out over the ring's sides, Z = +-OH/2
    for sz in (1, -1):
        b = b.fuse(Part.makeBox(BrArm, BrY0 - Depth, Wall, V(-BrArm / 2, Depth, sz * RingZ - Wall / 2)))
    b = b.removeSplitter()
    for x, z in LegScrews:     # M3 x OpLegScrewL down the leg, its head on the arm
        b = b.cut(CylY(W.OpScrewD, Depth - 1.0, BrY0 - Depth + BrT + 2.0, x, z))
    for x, z in W.OpFans:      # leave the display's fans open: the pad plate keeps its arm and its bands
        b = b.cut(CylY(W.OpFanD + 2 * W.OpFanClear, BrY0 - 1.0, BrT + 2.0, x, z))
    return b.removeSplitter()


def Pads():
    """Closed-cell foam, drawn squeezed to the gap; no hole, since no screw goes into the VESA holes."""
    return [CylY(W.OpPadD, HT, W.OpBracketGap, sx * W.OpVesaHalf, sz * W.OpVesaHalf)
            for sx in (1, -1) for sz in (1, -1)]


def Control(kind, x, z):
    """(rear body, front parts) of one control, assumed sizes."""
    side, deep = W.OpRearBody[kind]
    rear = Part.makeBox(side, deep, side, V(x - side / 2, 0.0, z - side / 2))
    d, h = W.OpFront[kind]
    front = []
    y = -T
    if kind == "estop":
        ld, lt = W.OpLegendPlate
        front.append(("legend", CylY(ld, y - lt, lt, x, z)))
        y -= lt
    front.append((kind, CylY(d, y - h, h, x, z)))
    return rear, front


def Checks():
    """Fits that overlap checks cannot see. Returns a list of failures; prints what it measured."""
    bad = []
    over = ((BW - WW) / 2, (BH - WH) / 2)
    print("window %.1f x %.1f in a %.1f x %.1f front face: the plate overlaps the bezel by %.1f (short sides) "
          "and %.1f (long sides)" % (WW, WH, BW, BH, over[0], over[1]))
    if min(over) < 5.0:        # the owner counted the casing's edge bevel as bezel: keep a flat seat past it
        bad.append("the plate overlaps the bezel by less than 5 mm")
    if Depth >= W.OpDisplayWall:
        bad.append("the cradle (%.1f deep) reaches the display's rounded edge at %.1f" % (Depth, W.OpDisplayWall))
    lap = W.OpCradleLap
    if any(lap[0] - 1.0 < abs(x) < lap[1] + 1.0 + W.OpInsertD for x, _ in CradleScrews + LegScrews):
        bad.append("a cradle screw falls in the lap joint")
    if abs(LegScrews[0][0]) + W.OpInsertD / 2 + 1.0 > lap[0]:
        bad.append("the bracket's leg screws reach the lap joint")
    leg = IH / 2 - BH / 2      # the bracket's legs stand on the ring's top and bottom sides, outside the pocket
    if leg <= 0.0:
        bad.append("the bracket's legs touch the display")
    if Depth - W.OpInsertL < 1.0:
        bad.append("insert holes %.1f deep leave %.1f mm of floor in the %.1f mm ring" % (W.OpInsertL, Depth - W.OpInsertL, Depth))
    wall = (Wall - W.OpInsert[1]) / 2              # plastic round the insert's knurl, not round the drilled hole
    if W.OpInsert[0] > W.OpInsertL - 1.0:
        bad.append("a %.0f mm insert leaves no room below it in a %.1f mm hole" % (W.OpInsert[0], W.OpInsertL))
    print("insert wall %.1f mm each side; leg clearance to the display %.1f mm" % (wall, leg))
    if wall < 2.5:
        bad.append("only %.1f mm of ring round a heat-set insert" % wall)
    # screw reach: M3 x OpCradleScrewL through the plate, M3 x OpLegScrewL down a leg, into inserts OpInsertL deep
    front = W.OpCradleScrewL - T
    legtip = BrY0 + BrT - W.OpLegScrewL
    for what, caught in (("cradle screw", min(front, W.OpInsert[0])), ("leg screw", min(Depth - legtip, W.OpInsert[0]))):
        if caught < 3.0:
            bad.append("the %s catches only %.1f mm of a %.0f mm insert" % (what, caught, W.OpInsert[0]))
    print("cradle screw %.1f mm into its insert; leg screw tip at Y %.1f in an insert from Y %.1f to %.1f" % (
        front, legtip, Depth - W.OpInsertL, Depth))
    if not (3.0 <= front <= W.OpInsertL - 0.3):
        bad.append("M3 x %.0f gives %.1f mm in a %.1f mm insert hole" % (W.OpCradleScrewL, front, W.OpInsertL))
    if not (Depth - W.OpInsertL + 0.3 <= legtip <= Depth - 3.0):
        bad.append("M3 x %.0f down the leg ends at Y %.1f" % (W.OpLegScrewL, legtip))
    # screws into slot T-nuts, by the frame's rule (draw_wiring ScrewFits): SlotLip + 3 pitches <= tip <= SlotDepth - 0.5
    for what, thread, length, stack in (("plate to the ring", "M5", W.OpFrameScrewL, T),
                                        ("arm's plate to a spine", "M4", W.OpArmScrewL, W.OpArmPlate[1])):
        tip = length - stack
        lo, hi = W.SlotLip + 3 * W.ThreadPitch[thread], W.SlotDepth - 0.5
        print("%s x %.0f, %s: %.2f mm past the slot face (%.2f to %.2f)" % (thread, length, what, tip, lo, hi))
        if not lo <= tip <= hi:
            bad.append("%s x %.0f for the %s leaves %.2f mm past the slot face" % (thread, length, what, tip))
    # acrylic webs: control holes, screw and mount holes against each other, the window and the edge
    holes = [(x, z, W.OpHoleD / 2, n) for n, _, x, z in W.OpControls] + \
            [(x, z, W.OpScrewD / 2, "cradle screw") for x, z in CradleScrews] + \
            [(x, z, W.OpFrameScrewD / 2, "frame screw") for x, z in FrameScrews]
    least = (1e9, "")
    for i, (x, z, r, n) in enumerate(holes):
        edge = min(PW / 2 - abs(x), PH / 2 - abs(z)) - r
        win = max(abs(x) - WW / 2, abs(z) - WH / 2) - r if (abs(x) > WW / 2 or abs(z) > WH / 2) else -1.0
        for web, what in ((edge, n + " to the plate edge"), (win, n + " to the window")):
            if web < least[0]:
                least = (web, what)
        for x2, z2, r2, n2 in holes[i + 1:]:
            web = math.hypot(x - x2, z - z2) - r - r2
            if web < least[0]:
                least = (web, n + " to " + n2)
    print("least acrylic web: %.1f mm (%s)" % least)
    if least[0] < MinWeb:
        bad.append("acrylic web %.1f mm < %.1f (%s)" % (least[0], MinWeb, least[1]))
    # S2's legend plate and the cradle screw heads (M3 pan head, 5.5 across) on the plate's front
    for n, kind, x, z in W.OpControls:
        if kind != "estop":
            continue
        for (sx, sz), head in [(c, W.OpScrewHeadD) for c in CradleScrews] + [(c, W.OpFrameScrewHeadD) for c in FrameScrews]:
            gap = math.hypot(sx - x, sz - z) - W.OpLegendPlate[0] / 2 - head / 2
            if gap < 1.0:
                bad.append("%s's legend plate covers a screw head at (%.1f, %.1f)" % (n, sx, sz))
    # what each collar clamps: the plate, plus S2's legend plate
    for n, kind, _, _ in W.OpControls:
        stack = T + (W.OpLegendPlate[1] if kind == "estop" else 0.0)
        if stack > W.OpPlateMaxT:
            bad.append("%s clamps %.2f mm, its collar reaches %.1f at most" % (n, stack, W.OpPlateMaxT))
    print("S2 clamps %.2f mm (plate %.3f + legend plate %.1f) of %.1f" % (
        T + W.OpLegendPlate[1], T, W.OpLegendPlate[1], W.OpPlateMaxT))
    return bad


def FanChecks(parts):
    """Nothing covers a fan grille, and the first part behind each is at least OpFanExhaust away."""
    bad = []
    names = [(n, s) for n, s, f, _ in parts if f not in ("display", "ports", "plate", "rear", "legend",
                                                          "estop", "red", "green", "blue", "selector")]
    for x, z in W.OpFans:
        reach = CylY(W.OpFanD, HT, 200.0, x, z)
        hits = [(s.common(reach).BoundBox.YMin - HT, n) for n, s in names if s.common(reach).Volume > 1e-3]
        gap, what = min(hits) if hits else (999.0, "nothing")
        print("fan at (%.0f, %.0f): free air behind it %.1f mm (%s)" % (x, z, gap, what))
        if gap < W.OpFanExhaust:
            bad.append("%s sits %.1f mm behind the fan at (%.0f, %.0f)" % (what, gap, x, z))
    return bad


def Clearances(parts):
    """The frame must clear the controls' bodies, the cradle and the display bracket by OpFrameGap."""
    bad = []
    frame = [(n, s) for n, s, f, src in parts if f == "frame"]
    others = [(n, s) for n, s, f, _ in parts if f in ("rear", "cradle", "bracket", "display", "pad", "ports")]
    least = (1e9, "")
    for n1, s1 in frame:
        for n2, s2 in others:
            d = s1.distToShape(s2)[0]
            if d < least[0]:
                least = (d, n1 + " to " + n2)
    print("least frame clearance: %.1f mm (%s)" % least)
    if least[0] < W.OpFrameGap:
        bad.append("frame clearance %.1f mm < %.1f (%s)" % (least[0], W.OpFrameGap, least[1]))
    return bad


def Overlaps(solids):
    bad = []
    for i, (n1, s1) in enumerate(solids):
        for n2, s2 in solids[i + 1:]:
            if not s1.BoundBox.intersect(s2.BoundBox):
                continue
            v = s1.common(s2).Volume
            if v > 1e-3:
                bad.append("%s and %s overlap by %.3f mm3" % (n1, n2, v))
    return bad


def Build():
    Doc = App.newDocument(DocName)
    halves = CradleHalves()
    parts = [("Display", Display(), "display", "scan 2026-11-11"),
             ("PortZone", PortZone(), "ports", "assumed"),
             ("FrontPlate", Plate(), "plate", "layout"),
             ("CradleLeft", halves[0], "cradle", "layout"),
             ("CradleRight", halves[1], "cradle", "layout"),
             ("Bracket", Bracket(), "bracket", "layout")]
    parts += Frame()
    for i, p in enumerate(Pads()):
        parts.append(("Pad%d" % (i + 1), p, "pad", "assumed"))
    for n, kind, x, z in W.OpControls:
        rear, front = Control(kind, x, z)
        parts.append((n + "_Rear", rear, "rear", "assumed"))
        for tag, s in front:
            parts.append((n + "_" + ("Legend" if tag == "legend" else "Front"), s, tag, "assumed"))
    bad = Checks() + Clearances(parts) + FanChecks(parts) + Overlaps([(n, s) for n, s, _, _ in parts])
    print("2020 cut list: " + "; ".join("%d x %.0f mm %s" % (c, l, n) for n, c, l in W.OpFrameCuts()))
    for n, s, fill, src in parts:
        o = Doc.addObject("Part::Feature", n)
        o.Shape = s
        o.addProperty("App::PropertyString", "SizeSource", "RMR", "where the size comes from")
        o.SizeSource = src
        if App.GuiUp:
            vo = o.ViewObject
            c = Fill[fill]
            vo.ShapeColor = tuple(int(c[k:k + 2], 16) / 255.0 for k in (1, 3, 5))
            vo.Transparency = Transp.get(fill, 40 if src == "assumed" else 0)
    lit = Doc.addObject("Part::Feature", "LitArea")
    lit.Shape = LitArea()
    if App.GuiUp:
        lit.ViewObject.ShapeColor = (0x44 / 255.0, 0x77 / 255.0, 0xAA / 255.0)
    Doc.recompute()
    return Doc, parts, bad


def Save(Doc, parts):
    os.makedirs(OutDir, exist_ok=True)
    fcstd = os.path.join(OutDir, DocName + ".FCStd")
    step = os.path.join(OutDir, DocName + ".step")
    Doc.saveAs(fcstd)
    objs = [Doc.getObject(n) for n, _, _, _ in parts]
    if App.GuiUp:
        import ImportGui
        ImportGui.export(objs, step)
    else:
        import Import
        Import.export(objs, step)
    print("wrote", fcstd)
    print("wrote", step)
    SavePrintables(parts)


# Each printed part (all PETG) and the face that goes on the bed: "front" (Y low) or "back" (Y high).
# Every part lies on the face that leaves nothing overhanging: each cradle piece on the face its lap
# tongue is part of, the bracket on its back face with its legs up.
Printables = [("CradleLeft", "back"), ("CradleRight", "front"), ("Bracket", "back")]


def PrintPose(name, shape, down):
    """The part as it goes on the printer's bed, lowest face at Z = 0 and centred on X and Y."""
    s = shape.copy()
    m = App.Matrix()
    if down == "front":            # Y (depth) becomes Z: the front face on the bed
        m.rotateX(math.pi / 2)
    else:                          # Y becomes -Z: the back face on the bed
        m.rotateX(-math.pi / 2)
    s = s.transformGeometry(m)
    bb = s.BoundBox
    s.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, -bb.ZMin))
    return s


def SavePrintables(parts):
    """One STEP AP214 file per 3D-printed part (Printables), in print orientation, named
    OperatorPanel_<part>.step. Refuses a file whose header names another schema or a part that does
    not fit the bed (OpPrintBed)."""
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part/STEP").SetString("Scheme", "AP214IS")
    shapes = {n: s for n, s, _, _ in parts}
    for name, down in Printables:
        s = PrintPose(name, shapes[name], down)
        if max(s.BoundBox.XLength, s.BoundBox.YLength) > W.OpPrintBed - 6.0:
            raise RuntimeError("%s is %.1f x %.1f mm: too big for the %.0f mm bed" % (
                name, s.BoundBox.XLength, s.BoundBox.YLength, W.OpPrintBed))
        path = os.path.join(OutDir, "%s_%s.step" % (DocName, name))
        s.exportStep(path)
        head = open(path, encoding="ascii", errors="replace").read(2000)
        if "10303 214" not in head:
            raise RuntimeError("%s is not STEP AP214: %s" % (path, head[head.find("FILE_SCHEMA"):][:80]))
        bb = s.BoundBox
        print("wrote %s (AP214, PETG, %s face down, %.1f x %.1f x %.1f mm, %.1f cm3)" % (
            path, down, bb.XLength, bb.YLength, bb.ZLength, s.Volume / 1000.0))


def Main():
    Doc, parts, bad = Build()
    for n, s, _, src in parts:
        bb = s.BoundBox
        print("%-12s %-16s X %7.1f..%7.1f  Y %6.1f..%6.1f  Z %7.1f..%7.1f" % (
            n, src, bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax))
    if bad:
        for b in bad:
            print("FAIL:", b)
        print("not saved")
        return False
    Save(Doc, parts)
    return True


if __name__ == "__main__":
    Main()
