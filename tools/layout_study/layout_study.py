"""Packing study for the RMR control box: compare deck architectures with CP-SAT.

Each architecture places rigid blocks (a DIN-rail group or a loose part, at its real footprint from
tools/draw_wiring.py PartSize) on one or two decks inside the frame, with wiring channels around
every block, a closed mains compartment at the inlet, and fixed cable exits at the grommets.
The objective is wire length: sum over nets of conductors x Manhattan distance between block
centres (plus the deck-to-deck rise for nets that change deck). Usage:

    python layout_study.py out_dir
"""

import json
import math
import os
import sys


# ---------------------------------------------------------------- frame and stack (mm)
BoxD, BoxW, BoxH = 457.0, 342.9, 279.4   # 13.5 in wide since 2026-10-21 (ADR-0018, issue #202)
Frame, PlateT, Rail, Clip = 20.0, 1.5875, 7.5, 10.0
Inner = (Frame, BoxD - Frame, Frame, BoxW - Frame)     # usable x0, x1, y0, y1 on either deck
Edge = 3                                                # part to ring clearance
Channel = 9                                             # wiring channel on every side of a block
PsuGap = 3.0                                            # PSU top to the plate above (standing)

# ---------------------------------------------------------------- blocks
# name: (length along its rail, depth across, mounted height, zone, may rotate). Lengths include
# 5 mm of rail past each end. The driver block carries its 1 x 1 1/2 in motor duct on one side.
Blocks = {
    "R110": (154.5, 82.0, 72.5, "mains", True),    # X0, F0, K1, X1, PE blocks on the 110 V rail
    "PSU": (240.0, 65.0, 143.5, "mains", True),    # 24 V 1200 W standing on a 240 x 65 face
    "R24": (180.1, 85.1, 75.6, "dc", True),        # F3 (issue #205), K2, Star S, two 0V-P bars
    "RFB": (322.0, 47.8, 50.7, "dc", True),        # FB2 and FB1, both 12-way (issue #158)
    "PS6": (63.0, 58.0, 40.5, "dc", True),         # servo PSU
    "PS5": (76.0, 76.0, 49.5, "dc", True),         # 5 V PSU for the Pi
    "DRV": (242.0, 124.4, 85.5, "drv", True),      # 7 TB6600 + motor duct
    "SSR": (46.6, 88.1, 78.4, "drv", True),        # 6 SSR sockets
    "LOGIC": (211.6, 53.0, 52.5, "log", True),     # Mega on its carrier + 0V-S groups
    "FIELD": (284.0, 42.5, 42.0, "log", True),     # field terminal rail
    "SHIELD": (124.0, 22.0, 40.0, "drv", True),    # motor shield clamp bar (assumed)
}
PsuFlat = (240.0, 126.0, 65.0 + Rail + Clip)        # the PSU lying on its 240 x 126 face; measured
                                                    # 240 x 126 x 65 (2026-10-21, issue #202)

# ---------------------------------------------------------------- cable exits (x, y, deck)
# Grommets chosen by the owner (sheet 4): upper left, front, right; lower left; mains at the back.
# Wall and slide range of each exit when exits are free: the grommet can sit anywhere along its wall.
ExitWall = {"UL": ("y", 0.0, 40.0, 417.0), "UF": ("x", 0.0, 40.0, 290.0), "UR": ("y", BoxW, 40.0, 417.0),
            "LL": ("y", 0.0, 40.0, 417.0), "INLET": ("x", BoxD, 40.0, 290.0)}
Exits = {
    "UL": (70.0, 0.0, "upper"), "UF": (0.0, 191.6, "upper"), "UR": (395.0, BoxW, "upper"),
    "LL": (260.0, 0.0, "lower"), "INLET": (BoxD, 129.0, "lower"),
}

# ---------------------------------------------------------------- nets: (a, b, conductors)
# From sheet 1's circuits (2026-10-06 panel reference); a cable to an exit counts its conductors.
Nets = [
    ("INLET", "R110", 3), ("R110", "PSU", 3),                       # mains, K1, PE
    ("PSU", "R24", 4), ("R24", "RFB", 4),                            # V+ to F3, F3 and K2 out, 0V
    ("RFB", "DRV", 7), ("R24", "DRV", 7),                            # driver feeds and returns
    ("RFB", "PS6", 1), ("PS6", "R24", 1), ("PS6", "FIELD", 2),       # servo supply
    ("RFB", "LL", 2),                                                # ODrive 24 V feed
    ("RFB", "SSR", 3), ("SSR", "R24", 2), ("SSR", "FIELD", 8),       # UV, valve, tower feeds/outputs
    ("RFB", "PS5", 2), ("PS5", "LL", 2),                             # Pi supply
    ("RFB", "FIELD", 1), ("FIELD", "R24", 2), ("FIELD", "LL", 5),    # E-stop latch, door cable
    ("LOGIC", "DRV", 28), ("LOGIC", "FIELD", 16), ("LOGIC", "SSR", 4),
    ("FIELD", "SSR", 5), ("LOGIC", "R24", 2),                        # tower inputs, pin 43 sense
    ("LOGIC", "UF", 4),                                              # USB and J11
    ("DRV", "SHIELD", 28), ("SHIELD", "UL", 24), ("SHIELD", "UR", 4),  # motor cables
    ("FIELD", "UL", 30), ("FIELD", "UR", 8),                         # field cables
]


def Arch(name):
    """Deck of each block, the PSU pose, and the box height rules for an architecture."""
    up = ["DRV", "SSR", "LOGIC", "FIELD", "SHIELD"]
    lo = ["R110", "PSU", "R24", "RFB", "PS6", "PS5"]
    if name in ("A", "A*"):
        return {"deck": {**{b: "lower" for b in lo}, **{b: "upper" for b in up}}, "psu": "standing"}
    if name == "B":
        return {"deck": {**{b: "lower" for b in lo}, **{b: "upper" for b in up}}, "psu": "flat"}
    if name == "C":
        return {"deck": {b: "lower" for b in lo + up}, "psu": "flat"}
    raise ValueError(name)


def Geometry(arch):
    blocks = dict(Blocks)
    if arch["psu"] == "flat":
        L, d, h = PsuFlat
        blocks["PSU"] = (L, d, h, "mains", True)
    return blocks


def Heights(arch, blocks):
    """Bay heights and the wire room over the drivers, for the stacked architectures."""
    lower = [b for b, deck in arch["deck"].items() if deck == "lower"]
    lowBay = max(blocks[b][2] for b in lower) + (PsuGap if arch["psu"] == "standing" else 3.0)
    upDeck = PlateT + lowBay + PlateT
    topIn = BoxH - Frame
    if arch["deck"]["DRV"] == "lower":
        # one deck: plate, tallest part, 47 mm of wire room, lid ring
        box = PlateT + max(b[2] for b in blocks.values()) + 47.0 + Frame
        return {"lower bay": round(lowBay, 1), "wire room": 47.0, "deck rise": 0.0,
                "box height for 47 mm wire room": round(box, 1)}
    room = topIn - upDeck - blocks["DRV"][2]
    rise = lowBay + PlateT
    return {"lower bay": round(lowBay, 1), "wire room": round(room, 1), "deck rise": round(rise, 1),
            "box height for 47 mm wire room": round(BoxH - (room - 47.0), 1)}


def Solve(name, deckD=BoxD, deckW=BoxW, fixed=None, seconds=60.0, mainsRule=True, fanRule=True,
          freeExits=False):
    """Place every block; `fixed` = {block: (cx, cy, rot)} scores a given layout instead."""
    from ortools.sat.python import cp_model   # only the solver needs OR-Tools; Score() runs without it
    arch = Arch(name)
    blocks = Geometry(arch)
    h = Heights(arch, blocks)
    x0i, x1i, y0i, y1i = Frame, deckD - Frame, Frame, deckW - Frame
    m = cp_model.CpModel()
    S = 2   # half-millimetre grid: every coordinate below is doubled
    var = {}
    rects = {"lower": [], "upper": []}
    for b, (L, d, ht, zone, rot) in blocks.items():
        deck = arch["deck"][b]
        r = m.NewBoolVar(b + "_r")
        if not rot:
            m.Add(r == 0)
        w = m.NewIntVar(int(min(L, d) * S), int(max(L, d) * S), b + "_w")
        hh = m.NewIntVar(int(min(L, d) * S), int(max(L, d) * S), b + "_h")
        m.Add(w == int(L * S)).OnlyEnforceIf(r.Not())
        m.Add(hh == int(d * S)).OnlyEnforceIf(r.Not())
        m.Add(w == int(d * S)).OnlyEnforceIf(r)
        m.Add(hh == int(L * S)).OnlyEnforceIf(r)
        x = m.NewIntVar(int((x0i + Edge) * S), int((x1i - Edge) * S), b + "_x")
        y = m.NewIntVar(int((y0i + Edge) * S), int((y1i - Edge) * S), b + "_y")
        xe = m.NewIntVar(int((x0i + Edge) * S), int((x1i - Edge) * S), b + "_xe")
        ye = m.NewIntVar(int((y0i + Edge) * S), int((y1i - Edge) * S), b + "_ye")
        m.Add(xe == x + w)
        m.Add(ye == y + hh)
        # padded footprint for the no-overlap test: a wiring channel on every side
        c = Channel * S
        px = m.NewIntVar(-10000, 10000, b + "_px")
        pxe = m.NewIntVar(-10000, 10000, b + "_pxe")
        py = m.NewIntVar(-10000, 10000, b + "_py")
        pye = m.NewIntVar(-10000, 10000, b + "_pye")
        m.Add(px == x - c)
        m.Add(pxe == xe + c)
        m.Add(py == y - c)
        m.Add(pye == ye + c)
        pw = m.NewIntVar(0, 20000, b + "_pw")
        ph = m.NewIntVar(0, 20000, b + "_ph")
        ix = m.NewIntervalVar(px, pw, pxe, b + "_ix")
        iy = m.NewIntervalVar(py, ph, pye, b + "_iy")
        rects[deck].append((ix, iy, b))
        var[b] = dict(r=r, x=x, y=y, xe=xe, ye=ye, w=w, h=hh, deck=deck, zone=zone)
        if fixed and b in fixed:
            cx, cy, rr = fixed[b]
            m.Add(r == rr)
            m.Add(x + xe == int(2 * cx * S))
            m.Add(y + ye == int(2 * cy * S))
    for deck in rects:
        if rects[deck]:
            m.AddNoOverlap2D([r[0] for r in rects[deck]], [r[1] for r in rects[deck]])
    # mains compartment: the bounding box of the mains blocks, plus a 10 mm wall, keeps every other
    # lower-deck block out, and it touches the back wall where the inlet is
    mains = [b for b in blocks if var[b]["zone"] == "mains"]
    others = [b for b in blocks if var[b]["zone"] != "mains" and var[b]["deck"] == "lower"]
    mx0 = m.NewIntVar(0, 20000, "mx0")
    my0 = m.NewIntVar(0, 20000, "my0")
    mx1 = m.NewIntVar(0, 20000, "mx1")
    my1 = m.NewIntVar(0, 20000, "my1")
    m.AddMinEquality(mx0, [var[b]["x"] for b in mains])
    m.AddMinEquality(my0, [var[b]["y"] for b in mains])
    m.AddMaxEquality(mx1, [var[b]["xe"] for b in mains])
    m.AddMaxEquality(my1, [var[b]["ye"] for b in mains])
    if mainsRule:
        m.Add(mx1 >= int((x1i - Edge - 10) * S))
    wall = 10 * S
    for b in (others if mainsRule else []):
        v = var[b]
        sides = [m.NewBoolVar(b + "_ms%d" % k) for k in range(4)]
        m.Add(v["xe"] + wall <= mx0).OnlyEnforceIf(sides[0])
        m.Add(v["x"] >= mx1 + wall).OnlyEnforceIf(sides[1])
        m.Add(v["ye"] + wall <= my0).OnlyEnforceIf(sides[2])
        m.Add(v["y"] >= my1 + wall).OnlyEnforceIf(sides[3])
        m.AddBoolOr(sides)
    # a flat PSU blows sideways: its fan face (one long side) must sit within 30 mm of a wall
    if arch["psu"] == "flat" and fanRule:
        v = var["PSU"]
        k = 30 * S
        f = [m.NewBoolVar("fan%d" % i) for i in range(4)]
        m.Add(v["y"] <= int((y0i + Edge) * S) + k).OnlyEnforceIf([f[0], v["r"].Not()])
        m.Add(v["ye"] >= int((y1i - Edge) * S) - k).OnlyEnforceIf([f[1], v["r"].Not()])
        m.Add(v["x"] <= int((x0i + Edge) * S) + k).OnlyEnforceIf([f[2], v["r"]])
        m.Add(v["xe"] >= int((x1i - Edge) * S) - k).OnlyEnforceIf([f[3], v["r"]])
        m.AddBoolOr([f[0], f[1]]).OnlyEnforceIf(v["r"].Not())
        m.AddBoolOr([f[2], f[3]]).OnlyEnforceIf(v["r"])
    # objective: conductor-weighted Manhattan distance between centres (doubled twice: x + xe)
    exitVar = {}
    if freeExits:
        for e, (axis, at, lo, hi) in ExitWall.items():
            v = m.NewIntVar(int(2 * lo * S), int(2 * hi * S), "exit_" + e)
            fixedC = int(2 * at * S) if at < 400 else int(2 * (deckD if axis == "x" else deckW) * S)
            exitVar[e] = (fixedC, v, Exits[e][2]) if axis == "x" else (v, fixedC, Exits[e][2])
    rise = h["deck rise"]
    terms, total_rise = [], 0.0
    for a, b, n in Nets:
        pa = exitVar.get(a) or Point(m, var, a, S)
        pb = exitVar.get(b) or Point(m, var, b, S)
        dx = m.NewIntVar(0, 40000, "dx_%s_%s" % (a, b))
        dy = m.NewIntVar(0, 40000, "dy_%s_%s" % (a, b))
        m.AddAbsEquality(dx, pa[0] - pb[0])
        m.AddAbsEquality(dy, pa[1] - pb[1])
        terms += [n * dx, n * dy]
        if pa[2] != pb[2]:
            total_rise += n * rise
    m.Minimize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = 8
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"arch": name, "status": solver.StatusName(st), "heights": h}
    place = {}
    for b, v in var.items():
        place[b] = dict(x=solver.Value(v["x"]) / S, y=solver.Value(v["y"]) / S,
                        w=solver.Value(v["w"]) / S, h=solver.Value(v["h"]) / S,
                        deck=v["deck"], zone=v["zone"], height=blocks[b][2])
    plan = solver.ObjectiveValue() / (2 * S)
    exitsAt = {e: [solver.Value(c) / (2 * S) if not isinstance(c, int) else c / (2 * S) for c in ev[:2]]
               for e, ev in exitVar.items()}
    return {"arch": name, "status": solver.StatusName(st), "plan wire": round(plan), "exits": exitsAt,
            "rise wire": round(total_rise), "wire": round(plan + total_rise),
            "bound": round(solver.BestObjectiveBound() / (2 * S)), "heights": h, "place": place,
            "mains box": [solver.Value(v) / S for v in (mx0, my0, mx1, my1)],
            "deck": [deckD, deckW]}


def Point(m, var, name, S):
    """(2 * centre x, 2 * centre y, deck) of a block or an exit, in grid units."""
    if name in Exits:
        x, y, deck = Exits[name]
        return (int(2 * x * S), int(2 * y * S), deck)
    v = var[name]
    return (v["x"] + v["xe"], v["y"] + v["ye"], v["deck"])


# The hand layout on sheet 3 (2026-10-17): block centres and rotation (1 = long side along y).
Current = {
    "R110": (391.5, 230.25, 1), "PSU": (261.0, 199.5, 1), "R24": (65.5, 82.05, 1),
    "RFB": (157.0, 151.0, 1), "PS6": (59.5, 279.0, 0), "PS5": (334.0, 62.0, 0),
    "DRV": (146.0, 84.2, 0), "SSR": (288.3, 98.4, 0), "LOGIC": (127.8, 197.6, 0),
    "FIELD": (169.0, 273.8, 0), "SHIELD": (421.0, 84.0, 1),
}


def Score(name, fixed, exits=None, nets=None, rise=None):
    """Wire length of a given layout, no constraints: {block: (cx, cy, rot)}. exits and nets replace
    Exits and Nets, and rise the deck rise of Heights(), for a layout drawn elsewhere
    (tools/draw_wiring.py StudyScore())."""
    arch = Arch(name)
    blocks = Geometry(arch)
    h = Heights(arch, blocks)
    pts = {b: (cx, cy, arch["deck"][b]) for b, (cx, cy, _) in fixed.items()}
    pts.update(Exits if exits is None else exits)
    step = h["deck rise"] if rise is None else rise
    plan = rise = 0.0
    for a, b, n in (Nets if nets is None else nets):
        (xa, ya, da), (xb, yb, db) = pts[a], pts[b]
        plan += n * (abs(xa - xb) + abs(ya - yb))
        rise += n * step if da != db else 0.0
    place = {}
    for b, (cx, cy, r) in fixed.items():
        L, d = blocks[b][0], blocks[b][1]
        w, hh = (d, L) if r else (L, d)
        place[b] = dict(x=cx - w / 2, y=cy - hh / 2, w=w, h=hh, deck=arch["deck"][b],
                        zone=blocks[b][3], height=blocks[b][2])
    return {"arch": name, "status": "GIVEN", "plan wire": round(plan), "rise wire": round(rise),
            "wire": round(plan + rise), "heights": h, "place": place, "deck": [BoxD, BoxW]}


def Breakdown(run):
    """Conductor-mm per net for a placed run (centres from the placement, exits fixed or solved)."""
    pts = {b: (p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, p["deck"]) for b, p in run["place"].items()}
    for e, (x, y, d) in Exits.items():
        pts[e] = (x, y, d)
    for e, xy in run.get("exits", {}).items():
        pts[e] = (xy[0], xy[1], Exits[e][2])
    rise = run["heights"]["deck rise"]
    out = []
    for a, b, n in Nets:
        (xa, ya, da), (xb, yb, db) = pts[a], pts[b]
        out.append(("%s-%s" % (a, b), n, round(n * (abs(xa - xb) + abs(ya - yb) + (rise if da != db else 0)))))
    return out


def Main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    runs = [("current (hand)", Score("A", Current)),
            ("A*: stacked, PSU standing, solver", Solve("A")),
            ("B: stacked, PSU flat, solver", Solve("B")),
            ("C: one deck in %g x %g" % (BoxD, BoxW), Solve("C", seconds=30))]
    # C does not fit the footprint: find the shortest deck depth that holds everything at BoxW wide
    for d in (520, 560, 600, 640):
        r = Solve("C", deckD=d, seconds=30)
        runs.append(("C: one deck, %d x %g" % (d, BoxW), r))
        if r["status"] in ("OPTIMAL", "FEASIBLE"):
            break
    summary = []
    for label, r in runs:
        row = {"case": label, "status": r["status"], **r["heights"]}
        for k in ("wire", "plan wire", "rise wire", "bound"):
            if k in r:
                row[k] = r[k]
        summary.append(row)
        print(json.dumps(row))
    json.dump({"runs": [{"label": l, **r} for l, r in runs]}, open(os.path.join(out, "runs.json"), "w"),
              indent=1)


if __name__ == "__main__":
    Main()
