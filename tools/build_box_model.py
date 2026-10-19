"""Build the RMR control box as a 3D block model in FreeCAD, from tools/draw_wiring.py.

Every solid comes from the generator that draws sheets 3 and 4 and writes the plate and panel DXFs:
the frame stack (BoxD, LowBay, the post and ring heights), DeckSolids() for every DIN rail, part,
duct and the shield clamp, PlateGeom() for the two deck plates, PanelGeom() for the side and top
panels and GrommetAt() for the cable entries. Nothing is read off a drawing, so a change in the
generator moves the model on the next run. Parts are blocks at their real size; a part whose size
the generator marks as assumed (dashed on sheet 3) is drawn translucent and carries
SizeSource = assumed.

The generator's x runs front to back and its y left to right, with z up: seen from above that is a
left-handed set. FreeCAD's is right-handed, so the model takes the generator's y as X and its x as
Y. X then runs left to right and Y front to back, and FreeCAD's Front view shows the box's front.

Run it inside FreeCAD 1.x, from the Python console or a macro:
    import runpy; runpy.run_path(r"<repo>/tools/build_box_model.py", run_name="__main__")
It builds the document, refuses to save it if two solids overlap (Overlaps()), and writes
CAD/Control Box/ControlBoxBlocks.FCStd and ControlBoxBlocks.step. Run headless (freecadcmd, with
stdin closed) it builds and checks the same solids, but its files carry no fills and its STEP has no
module tree, so commit only what a GUI run wrote.
"""

import importlib
import os
import sys

import FreeCAD as App
import Part

Here = os.path.dirname(os.path.abspath(__file__))
if Here not in sys.path:
    sys.path.insert(0, Here)
import draw_wiring as W  # noqa: E402

importlib.reload(W)        # take the generator as it is on disk now, not as an earlier run left it

OutDir = os.path.join(os.path.dirname(Here), "CAD", "Control Box")
DocName = "ControlBoxBlocks"
V = App.Vector

BracketW = W.BracketW              # cast corner bracket across, from the generator (the kit's listing)
GantryOverhang = 60.0              # the gantry members are drawn this far past the box on each side
# What the generator does not size. Each is drawn and flagged SizeSource = assumed.
FootD = 20.0                       # rubber foot diameter; sheet 4 draws the feet 20 wide
StudD, StudH = 5.0, 15.0           # M5 PE stud and how far it stands off its plate or panel
GrommetTall = 0.83 * 25.4          # grommet with its flange, from the listing's drawing (draw_wiring)
SleeveIn = 16.0                    # sleeve standing inside a 3 mm wall (draw_wiring)
GrommetWall = 2.0                  # the sleeve's wall
GlandBody = (26.0, 28.0)           # M20 door cable gland outside the back panel: across, long
GlandNutT = 5.0                    # its locknut inside, DoorGland[2] across

# Paul Tol light fills come from the generator (ZoneFill and the frame fills); the rest are greys.
AcrylicFill, AcrylicTransp = "#DDDDDD", 80
AssumedTransp, DuctTransp, ZoneTransp = 40, 50, 85
RubberFill, StudFill, ClipFill = "#444444", "#444444", W.PostFill

# The packing study's block names (DeckSolids' block) as the rails are named in UpperRails() and
# LowerRails().
RailName = {"FIELD": "field terminal rail", "LOGIC": "logic rail", "SSR": "SSR rail",
            "DRV": "driver rail", "SHIELD": "shield clamp", "RFB": "fuse rail", "R24": "24 V rail",
            "PS6": "servo PSU rail", "PS5": "5 V PSU rail", "PSU": "24 V PSU rail", "R110": "110 V rail"}
KeyName = {"Stop": "end clamp", "Cover": "end cover"}

Doc = None
Count = {}


def Rgb(hexColor):
    h = hexColor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def Fc(x, y, z):
    """FreeCAD point of a generator point (x front to back, y left to right, z up)."""
    return V(y, x, z)


def Name(prefix):
    Count[prefix] = Count.get(prefix, 0) + 1
    return "%s%03d" % (prefix, Count[prefix])


def Finish(o, parent, label, fill, transp, props):
    o.Label = label
    for k, v in props.items():
        o.addProperty("App::PropertyString", k, "RMR", "")
        setattr(o, k, str(v))
    parent.addObject(o)
    if App.GuiUp:
        o.ViewObject.ShapeColor = Rgb(fill)
        o.ViewObject.Transparency = transp
        if transp >= AcrylicTransp:    # see-through sheet and the zone: no edge lines across the view
            o.ViewObject.DisplayMode = "Shaded"
    return o


def AddBox(parent, prefix, label, box, fill, transp=0, **props):
    """A Part::Box over the generator box (x0, y0, z0, x1, y1, z1), so it can be dragged and resized."""
    x0, y0, z0, x1, y1, z1 = box
    o = Doc.addObject("Part::Box", Name(prefix))
    o.Length, o.Width, o.Height = y1 - y0, x1 - x0, z1 - z0
    o.Placement.Base = Fc(x0, y0, z0)
    return Finish(o, parent, label, fill, transp, props)


def AddShape(parent, prefix, label, shape, fill, transp=0, **props):
    o = Doc.addObject("Part::Feature", Name(prefix))
    o.Shape = shape
    return Finish(o, parent, label, fill, transp, props)


def Group(parent, label, kind="App::DocumentObjectGroup"):
    g = Doc.addObject(kind, Name("Part" if kind == "App::Part" else "Group"))
    g.Label = label
    if parent is not None:
        parent.addObject(g)
    return g


def Prism(pts, z0, h):
    """A closed polygon [(a, b)] in an XY plane at z0, extruded h along +Z."""
    vs = [V(a, b, z0) for a, b in pts]
    return Part.Face(Part.makePolygon(vs + [vs[0]])).extrude(V(0, 0, h))


def Obround(a0, b0, a1, b1, z0, h):
    """A slot with full-round ends on its short sides, a along X and b along Y, from z0 up h: the
    shape of ObroundPts()."""
    if a1 - a0 >= b1 - b0:
        r = (b1 - b0) / 2
        parts = [Part.makeCylinder(r, h, V(a, b0 + r, z0)) for a in (a0 + r, a1 - r)]
        core = (a1 - a0 - 2 * r, b1 - b0, h, V(a0 + r, b0, z0))
    else:
        r = (a1 - a0) / 2
        parts = [Part.makeCylinder(r, h, V(a0 + r, b, z0)) for b in (b0 + r, b1 - r)]
        core = (a1 - a0, b1 - b0 - 2 * r, h, V(a0, b0 + r, z0))
    if core[0] > 1e-6 and core[1] > 1e-6:
        parts.append(Part.makeBox(*core))
    return parts[0].fuse(parts[1:]).removeSplitter() if len(parts) > 1 else parts[0]


def Ring(a, b, od, bore, z0, h):
    """A disc od across with a bore, centred at (a, b) in an XY plane, from z0 up h."""
    s = Part.makeCylinder(od / 2, h, V(a, b, z0))
    return s.cut(Part.makeCylinder(bore / 2, h + 2, V(a, b, z0 - 1))) if bore > 0 else s


def Rotated(shape, rows, base):
    """shape turned by the rotation whose matrix rows are `rows`, then moved by base."""
    m = App.Matrix(rows[0][0], rows[0][1], rows[0][2], base.x,
                   rows[1][0], rows[1][1], rows[1][2], base.y,
                   rows[2][0], rows[2][1], rows[2][2], base.z,
                   0, 0, 0, 1)
    s = shape.copy()
    s.transformShape(m)
    return s


# ---------------------------------------------------------------- frame

Corners = [("front left", 0, 0), ("front right", 0, 1), ("back left", 1, 0), ("back right", 1, 1)]


def RailSolid(box):
    """A 2020 rail (RailProfile()) filling the generator box (x0, y0, z0, x1, y1, z1), along its
    longest side. The profile is square and symmetric, so any proper turn of it fits."""
    x0, y0, z0, x1, y1, z1 = box
    pts = W.RailProfile()
    lx, ly, lz = x1 - x0, y1 - y0, z1 - z0
    length = max(lx, ly, lz)
    s = Prism(pts, 0.0, length)
    if length == lz:
        rows = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    elif length == ly:             # along the generator's y, FreeCAD's X
        rows = ((0, 0, 1), (1, 0, 0), (0, 1, 0))
    else:                          # along the generator's x, FreeCAD's Y
        rows = ((0, 1, 0), (0, 0, 1), (1, 0, 0))
    return Rotated(s, rows, Fc(x0, y0, z0))


def RingRails(z0, full):
    """[(label, box)] of one ring at z0: the long rails along x, full length (mid and lid ring) or
    between the posts (bottom ring), and the short rails between the long ones."""
    F, D, Wd = W.Frame, W.BoxD, W.BoxW
    a0, a1 = (0.0, D) if full else (F, D - F)
    return [("long, left", (a0, 0.0, z0, a1, F, z0 + F)), ("long, right", (a0, Wd - F, z0, a1, Wd, z0 + F)),
            ("short, front", (0.0, F, z0, F, Wd - F, z0 + F)), ("short, back", (D - F, F, z0, D, Wd - F, z0 + F))]


def Posts(z0, z1):
    F, D, Wd = W.Frame, W.BoxD, W.BoxW
    return [(name, (i * (D - F), j * (Wd - F), z0, i * (D - F) + F, j * (Wd - F) + F, z1))
            for name, i, j in Corners]


def BracketSolid(p, a, b, w):
    """A cast corner bracket as an L: its inside corner at the generator point p, legs Frame long
    along the generator unit vectors a and b, each lying on the face the other one leaves,
    BracketLegT thick, BracketW wide along w and centred on p."""
    L, t = W.Frame, W.BracketLegT
    pts = []
    for s, u in ((0, 0), (L, 0), (L, t), (t, t), (t, L), (0, L)):
        q = [p[k] + a[k] * s + b[k] * u - w[k] * BracketW / 2 for k in range(3)]
        pts.append(Fc(*q))
    face = Part.Face(Part.makePolygon(pts + [pts[0]]))
    return face.extrude(Fc(*[w[k] * BracketW for k in range(3)]))


def Brackets():
    """[(set, label, shape)]: the 32 corner brackets of the BoM, where sheet 4 puts them. Bottom
    ring to lower posts (8) on the ring's top face; lower posts to the mid ring (8) under it; the mid
    ring's inside corners (4); the upper posts (8), rail leg on the upper plate over the ring; the lid
    ring's inside corners (4). Every one stays over its ring rail or inside the ring's corner, clear
    of the deck strip RingClear in from the ring."""
    F, D, Wd = W.Frame, W.BoxD, W.BoxW
    out = []
    for name, i, j in Corners:
        dx, dy = (1, -1)[i], (1, -1)[j]
        xi, yi = (F, D - F)[i], (F, Wd - F)[j]
        xc, yc = (F / 2, D - F / 2)[i], (F / 2, Wd - F / 2)[j]
        for z, up, kit in ((W.LoDeck + F, 1, "bottom ring to lower post"),
                           (W.MidF0, -1, "lower post to mid ring"),
                           (W.UpDeck, 1, "upper post on the upper plate")):
            out.append((kit, "%s, %s, long rail" % (kit, name),
                        BracketSolid((xi, yc, z), (dx, 0, 0), (0, 0, up), (0, 1, 0))))
            out.append((kit, "%s, %s, short rail" % (kit, name),
                        BracketSolid((xc, yi, z), (0, dy, 0), (0, 0, up), (1, 0, 0))))
        for z, kit in ((W.MidF0 + F / 2, "mid ring corner"), (W.TopIn + F / 2, "lid ring corner")):
            out.append((kit, "%s, %s" % (kit, name),
                        BracketSolid((xi, yi, z), (dx, 0, 0), (0, dy, 0), (0, 0, 1))))
    return out


def MountBracketSolids():
    """[(label, shape)]: the four gantry mount brackets (MountBrackets()), each with its inside corner
    on its panel's outer face at a lower member's top face, the horizontal leg out over the member and
    the vertical leg up the panel."""
    out = []
    for wall, u in W.MountBrackets():
        face, out_ = (-W.PanelT, -1) if wall == "front" else (W.BoxD + W.BasePlateT, 1)
        out.append(("mount bracket, %s, at the %s post" % (wall, "left" if u < W.BoxW / 2 else "right"),
                    BracketSolid((face, u, W.Frame), (out_, 0, 0), (0, 0, 1), (0, 1, 0))))
    return out


def GantryRails():
    """[(label, box)]: the gantry members of GantryMembers, in the planes of the box's front and back
    faces (the lower panels' outer faces), drawn GantryOverhang past the box on each side."""
    F = W.Frame
    out = []
    for wall, name, z0 in W.GantryMembers:
        x0 = -W.PanelT - F if wall == "front" else W.BoxD + W.BasePlateT
        out.append(("%s %s" % (wall, name),
                    (x0, -GantryOverhang, z0, x0 + F, W.BoxW + GantryOverhang, z0 + F)))
    return out


def PlateSolid(kind, z0, t):
    """A deck plate from PlateGeom(): the outline with every hole and slot of its DXF."""
    outline, holes, slots = W.PlateGeom(kind)
    s = Prism([(y, x) for x, y in outline], z0, t)
    cuts = [Part.makeCylinder(d / 2, t + 2, Fc(x, y, z0 - 1)) for x, y, d in holes]
    cuts += [Obround(y0, x0, y1, x1, z0 - 1, t + 2) for x0, y0, x1, y1 in slots]
    return s.cut(cuts)


# ---------------------------------------------------------------- panels

def PanelThick(name):
    return W.BasePlateT if W.PanelSpec(name)[4] == "aluminum" else W.PanelT


def PanelFrame(name):
    """(rows, base, inward): the turn and the offset that take panel-local (u, v, w), with u and v as
    PanelGeom() draws them and w = u x v through the panel, to FreeCAD; inward says whether w points
    into the box. Being right-handed, w points in on the left, back and top panels and out on the
    right and front ones."""
    wall, z0 = W.PanelWall[name]
    t = PanelThick(name)
    if wall in ("left", "right"):
        return ((0, 0, 1), (1, 0, 0), (0, 1, 0)), V(-t if wall == "left" else W.BoxW, 0, z0), wall == "left"
    if wall in ("front", "back"):
        return ((1, 0, 0), (0, 0, -1), (0, 1, 0)), V(0, 0 if wall == "front" else W.BoxD + t, z0), wall == "back"
    return ((0, 1, 0), (1, 0, 0), (0, 0, -1)), V(0, 0, W.BoxH + t), True


def PanelW(name, d0, d1):
    """(w0, length) in panel-local w of the span d0..d1, measured outward from the panel's inner
    face (the frame's outer face): negative d is inside the box."""
    t = PanelThick(name)
    inward = PanelFrame(name)[2]
    return (t - d1, d1 - d0) if inward else (d0, d1 - d0)


def OnPanel(name, shape):
    rows, base, _ = PanelFrame(name)
    return Rotated(shape, rows, base)


def PanelSolid(name):
    """A side or top panel from PanelGeom(): its outline with every hole, slot and cut-out."""
    t = PanelThick(name)
    outline, holes, slots, polys = W.PanelGeom(name)
    s = Prism(outline, 0.0, t)
    cuts = [Part.makeCylinder(d / 2, t + 2, V(u, v, -1)) for u, v, d in holes]
    cuts += [Obround(u0, v0, u1, v1, -1, t + 2) for u0, v0, u1, v1 in slots]
    cuts += [Prism(p, -1, t + 2) for p in polys]
    return OnPanel(name, s.cut(cuts) if cuts else s)


def GrommetSolids(name, u, v):
    """(grommet, ring) at (u, v) on a panel: the flange outside, the sleeve through the 50 mm hole
    and SleeveIn past the wall, and the acrylic ring pressed onto the sleeve behind the wall."""
    t = PanelThick(name)
    sleeve = min(W.GrommetSleeve, W.GrommetHole)       # drawn at the hole, so the two do not overlap
    bore = sleeve - 2 * GrommetWall
    w0, h = PanelW(name, t, GrommetTall - SleeveIn)
    flange = Ring(u, v, W.GrommetFlange, bore, w0, h)
    w0, h = PanelW(name, -SleeveIn, t)
    body = flange.fuse(Ring(u, v, sleeve, bore, w0, h)).removeSplitter()
    w0, h = PanelW(name, -W.PanelT, 0.0)
    ring = Ring(u, v, W.RingOD, sleeve, w0, h)
    return OnPanel(name, body), OnPanel(name, ring)


# ---------------------------------------------------------------- the model

def DeckBox(s):
    """(z0, z1) of a DeckSolids() entry over FreeCAD's floor, and the clip box under it if it has one.
    A part on a rail or with the rail included starts at the rail's top face; one on a clip starts
    Clip higher, over a clip the width of the rail and as long as the part along it."""
    floor = W.LoDeck if s["deck"] == "lower" else W.UpDeck
    x0, y0, x1, y1 = s["box"]
    if s["kind"] != "part":
        return floor, floor + s["top"], None
    base = {"rail": W.DinRailH, "incl": W.DinRailH, "clip": W.DinRailH + W.Clip, "plate": 0.0}[s["mount"]]
    clip = None
    if s["mount"] == "clip":
        r0, r1 = W.DinRailH, W.DinRailH + W.Clip
        if s["alongX"]:
            c = (y0 + y1) / 2
            clip = (x0, c - 17.5, floor + r0, x1, c + 17.5, floor + r1)
        else:
            c = (x0 + x1) / 2
            clip = (c - 17.5, y0, floor + r0, c + 17.5, y1, floor + r1)
    return floor + base, floor + s["top"], clip


def PartLabel(s):
    key, label = s["key"], s["label"]
    if s["kind"] == "rail":
        return "DIN rail, " + RailName.get(s["block"], s["block"])
    if s["kind"] != "part":
        return label or s["kind"]
    if key in ("Term", "PETerm"):
        n = round((s["box"][2] - s["box"][0] if s["alongX"] else s["box"][3] - s["box"][1]) / W.PartSize[key][0])
        return "%s x%d [%s]" % (label, n, key)
    return "%s [%s]" % (label or KeyName.get(key, key), key)


def DeckGroups(module, deck):
    """Every DeckSolids() entry of one deck, a group per rail with its parts and clips, and one for
    the ducts."""
    deckGroup = Group(module, "%s deck" % deck.capitalize())
    groups = {}
    for s in W.DeckSolids():
        if s["deck"] != deck:
            continue
        x0, y0, x1, y1 = s["box"]
        z0, z1, clip = DeckBox(s)
        if s["kind"] == "duct":
            g = groups.setdefault("ducts", Group(deckGroup, "Wire ducts"))
        else:
            g = groups.get(s["block"])
            if g is None:
                g = groups[s["block"]] = Group(deckGroup, RailName.get(s["block"], s["block"]).capitalize())
        assumed = s["dashed"]
        transp = DuctTransp if s["kind"] == "duct" else AssumedTransp if assumed else 0
        AddBox(g, {"rail": "DinRail"}.get(s["kind"], s["kind"].capitalize()), PartLabel(s),
               (x0, y0, z0, x1, y1, z1), s["fill"], transp,
               Deck=deck, Kind=s["kind"], Key=s["key"] or "", Block=s["block"] or "", Mount=s["mount"],
               TopOverDeck="%.1f" % s["top"], SizeSource="assumed" if assumed else "sourced",
               Mains="yes" if s["mains"] else "no")
        if clip:
            AddBox(g, "Clip", "printed clip under %s" % PartLabel(s), clip, ClipFill,
                   Deck=deck, Kind="clip", SizeSource="assumed")


def PanelGroup(module, names):
    g = Group(module, "Panels")
    for name in names:
        material = W.PanelSpec(name)[4]
        fill, transp = (W.PlateFill, 0) if material == "aluminum" else (AcrylicFill, AcrylicTransp)
        AddShape(g, "Panel", name, PanelSolid(name), fill, transp, Kind="panel", Material=material,
                 SizeSource="sourced")
    for name, u, v, cables in W.GrommetAt():
        if name not in names:
            continue
        body, ring = GrommetSolids(name, u, v)
        AddShape(g, "Grommet", "grommet, %s at %s: %s" % (name, W.Mm(u), cables), body, RubberFill,
                 Kind="grommet", SizeSource="assumed")
        AddShape(g, "GrommetRing", "grommet ring, %s at %s" % (name, W.Mm(u)), ring, AcrylicFill,
                 AcrylicTransp, Kind="grommet ring", SizeSource="sourced")
    if W.BackPanel in names:
        t = PanelThick(W.BackPanel)
        _, w1, _, w3 = W.PanelWindow(W.BackPanel)
        u, v = W.DoorGland[0], (w1 + w3) / 2
        w0, h = PanelW(W.BackPanel, t, t + GlandBody[1])
        gland = Part.makeCylinder(GlandBody[0] / 2, h, V(u, v, w0))
        w0, h = PanelW(W.BackPanel, -GlandNutT, 0.0)
        gland = gland.fuse(Part.makeCylinder(W.DoorGland[2] / 2, h, V(u, v, w0)))
        AddShape(g, "Gland", "M20 gland: 110 V door cable", OnPanel(W.BackPanel, gland), RubberFill,
                 Kind="gland", SizeSource="assumed")
        u, v = W.BackPeStud
        w0, h = PanelW(W.BackPanel, -StudH, 0.0)
        AddShape(g, "Stud", "PE stud, back panel", OnPanel(W.BackPanel, Part.makeCylinder(StudD / 2, h, V(u, v, w0))),
                 StudFill, Kind="PE stud", SizeSource="assumed")
    return g


def FrameGroup(module, label, rails, fill):
    g = Group(module, label)
    for name, box in rails:
        AddShape(g, "Rail", "%s, %s" % (label.lower().rstrip("s"), name), RailSolid(box), fill,
                 Kind="2020 rail", Length="%.1f" % max(box[3] - box[0], box[4] - box[1], box[5] - box[2]),
                 SizeSource="sourced")
    return g


def BracketGroup(module, label, kits):
    g = Group(module, label)
    for kit, name, shape in Brackets():
        if kit in kits:
            AddShape(g, "Bracket", name, shape, W.BracketFill, Kind="corner bracket", SizeSource="assumed")
    return g


def PeStud(module, kind, z0):
    x, y = W.PeStud[kind]
    AddShape(module, "Stud", "PE stud, %s plate" % kind, Part.makeCylinder(StudD / 2, StudH, Fc(x, y, z0)),
             StudFill, Kind="PE stud", SizeSource="assumed")


def Build():
    """The document: a root App::Part with the lower module, the upper module and its lid, the
    eight brackets that join the modules, and the gantry members around the box. Returns (root, every
    solid)."""
    global Doc
    if DocName in App.listDocuments():
        App.closeDocument(DocName)
    Doc = App.newDocument(DocName)
    Count.clear()
    F, D, Wd = W.Frame, W.BoxD, W.BoxW
    root = Group(None, "Control box", "App::Part")

    lower = Group(root, "Lower module: 110 VAC and 24 V power", "App::Part")
    feet = Group(lower, "Feet")
    for name, i, j in Corners:
        x, y = W.PostCentres[2 * i + j]
        AddShape(feet, "Foot", "rubber foot, " + name, Part.makeCylinder(FootD / 2, W.FootH, Fc(x, y, -W.FootH)),
                 RubberFill, Kind="foot", SizeSource="assumed")
    AddShape(lower, "Plate", "base plate, 1/16 in 5052", PlateSolid("base", 0.0, W.BasePlateT), W.PlateFill,
             Kind="deck plate", SizeSource="sourced")
    PeStud(lower, "base", W.LoDeck)
    FrameGroup(lower, "Lower posts", Posts(W.LoDeck, W.MidF0), W.PostFill)
    FrameGroup(lower, "Bottom ring", RingRails(W.LoDeck, False), W.ZoneFill["frame"])
    BracketGroup(lower, "Bottom ring brackets", ("bottom ring to lower post",))
    DeckGroups(lower, "lower")
    zone = Group(lower, "110 VAC zone (no wall, ADR-0013)")
    AddBox(zone, "Zone", "110 VAC zone: MainsGap outside the mains parts to the ring",
           (W.MainsZoneX, W.MainsZoneY, W.LoDeck, D - F, Wd - F, W.UpPlate0), W.ZoneFill["110"], ZoneTransp,
           Kind="zone", SizeSource="sourced")
    PanelGroup(lower, [n for n, wz in W.PanelWall.items() if wz[1] == 0.0])
    mounts = Group(lower, "Gantry mount brackets (come out with the box)")
    for label, shape in MountBracketSolids():
        AddShape(mounts, "Bracket", label, shape, W.BracketFill, Kind="corner bracket", SizeSource="assumed")

    BracketGroup(root, "Module joint: lower posts to mid ring", ("lower post to mid ring",))

    upper = Group(root, "Upper module: drives and logic", "App::Part")
    FrameGroup(upper, "Mid ring", RingRails(W.MidF0, True), W.ZoneFill["frame"])
    BracketGroup(upper, "Mid ring brackets", ("mid ring corner",))
    AddShape(upper, "Plate", "upper plate, 1/16 in 5052", PlateSolid("upper", W.UpPlate0, W.UpPlateT),
             W.PlateFill, Kind="deck plate", SizeSource="sourced")
    PeStud(upper, "upper", W.UpDeck)
    FrameGroup(upper, "Upper posts", Posts(W.UpDeck, W.TopIn), W.PostFill)
    BracketGroup(upper, "Upper post brackets", ("upper post on the upper plate",))
    DeckGroups(upper, "upper")
    PanelGroup(upper, [n for n, wz in W.PanelWall.items() if 0.0 < wz[1] < W.BoxH])
    lid = Group(upper, "Lid: off alone with 4 screws", "App::Part")
    FrameGroup(lid, "Lid ring", RingRails(W.TopIn, True), W.LidFill)
    BracketGroup(lid, "Lid ring brackets", ("lid ring corner",))
    PanelGroup(lid, [W.TopPanel])

    FrameGroup(root, "Gantry members", GantryRails(), "#CCCCCC")

    notes = Doc.addObject("App::TextDocument", "Notes")
    notes.Label = "Notes"
    notes.Text = NotesText()
    Doc.recompute()
    solids = [o for o in Doc.Objects if o.isDerivedFrom("Part::Feature")]
    return root, solids


def NotesText():
    legend = ", ".join("%s %s" % (k, v) for k, v in W.ZoneFill.items())
    return "\n".join([
        "RMR control box, block model. Built by tools/build_box_model.py from tools/draw_wiring.py:",
        "the same frame stack, DeckSolids(), PlateGeom(), PanelGeom() and GrommetAt() as sheets 3 and 4",
        "and the plate and panel DXFs. Rebuild it after any change there; do not edit this file by hand.",
        "",
        "Axes: X left to right (the generator's y), Y front to back (its x), Z up from the base plate's",
        "underside. Box %s x %s x %s mm (depth x width x height), lower bay %s, upper deck at %s."
        % (W.Mm(W.BoxD), W.Mm(W.BoxW), W.Mm(W.BoxH), W.Mm(W.LowBay), W.Mm(W.UpDeck)),
        "",
        "Fills: Paul Tol light, as on sheet 3 (%s); frame greys; lid ring pear." % legend,
        "Translucent deck parts have an assumed size (dashed on sheet 3); every solid carries",
        "SizeSource. Acrylic panels are drawn 80 % transparent, the aluminum back panel opaque.",
        "The pink volume is the 110 VAC zone of ADR-0013, not a part.",
        "",
        "Assumed here, not in the generator: foot diameter %s, PE stud %s long,"
        % (W.Mm(FootD), W.Mm(StudH)),
        "grommet sleeve wall %s, door gland body and locknut size." % W.Mm(GrommetWall),
        "",
        "The gantry (sheet 5, issue #158): its members in the box's face planes, %s past the box on each"
        % W.Mm(GantryOverhang),
        "side, at the owner's heights of 2026-10-19 with the front middle member raised to %s over the"
        % W.Mm(W.GantryMidGap),
        "lower one; the four mount brackets belong to the lower module and come out with the box.",
        "Not modeled: wires, screws, T-nuts, nuts and tails under the plates, the locating studs,",
        "ground bars, the IEC inlet and the PSU vent (both still open in PanelOpen()).",
    ])


def Overlaps(solids, tol=1e-3):
    """[(a, b, volume)] for every pair of solids sharing more than tol mm^3, in assembled
    positions. The 110 VAC zone is a volume, not a part, and is left out."""
    items = []
    for o in solids:
        if getattr(o, "Kind", "") == "zone":
            continue
        s = o.Shape.copy()
        s.Placement = o.getGlobalPlacement()
        items.append((o, s, s.BoundBox))
    out = []
    for i, (a, sa, ba) in enumerate(items):
        for b, sb, bb in items[i + 1:]:
            if not ba.intersect(bb):
                continue
            v = sa.common(sb).Volume
            if v > tol:
                out.append((a, b, v))
    return out


def Clearances():
    """{what: (least gap, part)}: the lower parts under the upper plate and the upper parts under the
    lid ring, from the same DeckSolids() tops the generator checks."""
    out = {}
    for s in W.DeckSolids():
        if s["kind"] == "rail":
            continue
        if s["deck"] == "lower":
            key, gap = "lower part to the upper plate", W.UpPlate0 - W.LoDeck - s["top"]
        else:
            key, gap = "upper part to the lid ring (wire room)", W.TopIn - W.UpDeck - s["top"]
        if key not in out or gap < out[key][0]:
            out[key] = (gap, PartLabel(s))
    return out


def Save(root, solids):
    os.makedirs(OutDir, exist_ok=True)
    fcstd = os.path.join(OutDir, DocName + ".FCStd")
    step = os.path.join(OutDir, DocName + ".step")
    Doc.saveAs(fcstd)
    if App.GuiUp:
        import ImportGui
        ImportGui.export([root], step)         # the module tree, with the fills
    else:
        import Import
        Import.export(solids, step)            # without the GUI the tree is written twice over: go flat
    return fcstd, step


def Main():
    root, solids = Build()
    print("%d solids" % len(solids))
    for what, (gap, part) in Clearances().items():
        print("least gap, %s: %.1f mm (%s)" % (what, gap, part))
    bad = Overlaps(solids)
    if bad:
        for a, b, v in bad:
            print("OVERLAP %.2f mm^3: %s / %s" % (v, a.Label, b.Label))
        raise ValueError("%d pairs of solids overlap; nothing saved" % len(bad))
    print("no two solids overlap")
    if App.GuiUp:
        import FreeCADGui as Gui
        view = Gui.getDocument(Doc.Name).activeView()
        view.viewIsometric()
        view.fitAll()
    for path in Save(root, solids):
        print("wrote", path)


if __name__ == "__main__":
    Main()
