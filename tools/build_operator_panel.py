"""Build the RMR operator panel in FreeCAD: the display, the front plate, the cradle and the VESA bracket.

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
the front, locates it; a printed bracket standing on the ring presses it against the plate through
closed-cell foam pads on the rear housing's back face (OpBracketGap). No screw goes into the VESA holes,
which would fix the display's depth a second time.

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
Fill = {"plate": "#DDDDDD", "display": "#333333", "lit": "#4477AA", "cradle": "#77AADD", "bracket": "#EEDD88",
        "pad": "#444444", "ports": "#EE8866", "rear": "#BBBBBB", "legend": "#CCBB44",
        "estop": "#EE6677", "red": "#EE6677", "green": "#228833", "blue": "#4477AA", "selector": "#228833"}
Transp = {"plate": 60, "ports": 70, "rear": 60}
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
CradleScrews, LegScrews, Mounts = W.OpCradleScrews(), W.OpLegScrews(), W.OpMounts()


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
    for x, z in Mounts:
        p = p.cut(CylY(W.OpPlateMount[1], -T - 1.0, T + 2.0, x, z))
    return p


def Cradle():
    c = RoundBox(OW, OH, OR, 0.0, Depth).cut(RoundBox(IW, IH, IR, -1.0, Depth + 2.0))
    for x, z in CradleScrews:
        c = c.cut(CylY(W.OpInsertD, -0.01, W.OpInsertL, x, z))
    for x, z in LegScrews:
        c = c.cut(CylY(W.OpInsertD, Depth - W.OpInsertL, W.OpInsertL + 0.01, x, z))
    return c


def Bracket():
    b = RoundBox(BrSide, BrSide, 6.0, BrY0, BrT)
    b = b.fuse(RoundBox(BrArm, OH, 3.0, BrY0, BrT))   # the arm runs out over the ring's sides, Z = +-OH/2
    for sz in (1, -1):
        b = b.fuse(Part.makeBox(BrArm, BrY0 - Depth, Wall, V(-BrArm / 2, Depth, sz * RingZ - Wall / 2)))
    b = b.removeSplitter()
    for x, z in LegScrews:     # M3 x OpLegScrewL down the leg, its head on the arm
        b = b.cut(CylY(W.OpScrewD, Depth - 1.0, BrY0 - Depth + BrT + 2.0, x, z))
    return b


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
    leg = IH / 2 - BH / 2      # the bracket's legs stand on the ring's top and bottom sides, outside the pocket
    if leg <= 0.0:
        bad.append("the bracket's legs touch the display")
    wall = (Wall - W.OpInsertD) / 2
    print("insert wall %.1f mm each side; leg clearance to the display %.1f mm" % (wall, leg))
    if wall < 2.5:
        bad.append("only %.1f mm of ring round a heat-set insert" % wall)
    # screw reach: M3 x OpCradleScrewL through the plate, M3 x OpLegScrewL down a leg, into inserts OpInsertL deep
    front = W.OpCradleScrewL - T
    legtip = BrY0 + BrT - W.OpLegScrewL
    print("cradle screw %.1f mm into its insert; leg screw tip at Y %.1f in an insert from Y %.1f to %.1f" % (
        front, legtip, Depth - W.OpInsertL, Depth))
    if not (3.0 <= front <= W.OpInsertL - 0.3):
        bad.append("M3 x %.0f gives %.1f mm in a %.1f mm insert hole" % (W.OpCradleScrewL, front, W.OpInsertL))
    if not (Depth - W.OpInsertL + 0.3 <= legtip <= Depth - 3.0):
        bad.append("M3 x %.0f down the leg ends at Y %.1f" % (W.OpLegScrewL, legtip))
    # acrylic webs: control holes, screw and mount holes against each other, the window and the edge
    holes = [(x, z, W.OpHoleD / 2, n) for n, _, x, z in W.OpControls] + \
            [(x, z, W.OpScrewD / 2, "cradle screw") for x, z in CradleScrews] + \
            [(x, z, W.OpPlateMount[1] / 2, "mount") for x, z in Mounts]
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
        for sx, sz in CradleScrews + Mounts:
            gap = math.hypot(sx - x, sz - z) - W.OpLegendPlate[0] / 2 - 2.75
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
    parts = [("Display", Display(), "display", "scan 2026-11-11"),
             ("PortZone", PortZone(), "ports", "assumed"),
             ("FrontPlate", Plate(), "plate", "layout"),
             ("Cradle", Cradle(), "cradle", "layout"),
             ("Bracket", Bracket(), "bracket", "layout")]
    for i, p in enumerate(Pads()):
        parts.append(("Pad%d" % (i + 1), p, "pad", "assumed"))
    for n, kind, x, z in W.OpControls:
        rear, front = Control(kind, x, z)
        parts.append((n + "_Rear", rear, "rear", "assumed"))
        for tag, s in front:
            parts.append((n + "_" + ("Legend" if tag == "legend" else "Front"), s, tag, "assumed"))
    bad = Checks() + Overlaps([(n, s) for n, s, _, _ in parts])
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
