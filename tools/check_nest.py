"""Independent read-back of the nest DXFs written by draw_wiring.py: several parts per file.
Every closed polyline not inside another is a part outline; a circle outside every outline is a
ring's outer edge, and a smaller concentric circle is its bore. Each cut is assigned to the part
that contains it. Checks: web >= 2 mm from each cut to its part's edge and to the other cuts of
that part, >= 2 mm between parts, and everything inside the sheet and the laser bed."""
import math
import sys

sys.path.insert(0, sys.argv[0].rsplit("/", 1)[0] if "/" in sys.argv[0] else ".")
from check_dxf import Load, Bbox  # noqa: E402

MinWeb, Sheet, Bed = 2.0, (609.6, 457.2), (813.0, 457.0)


def Inside(inner, outer):
    return (inner[0] >= outer[0] - 1e-6 and inner[1] >= outer[1] - 1e-6 and
            inner[2] <= outer[2] + 1e-6 and inner[3] <= outer[3] + 1e-6)


def RectGap(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def CircRectGap(c, r):
    x, y, rad = c
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy) - rad


def Main(path):
    polys, circles = Load(path)
    # a closed polyline of two half-circle arcs is a full circle: a ring's outer edge
    arcs = [q for q in polys if len(q['pts']) == 2 and all(v[2] == 1.0 for v in q['pts'])]
    polys = [q for q in polys if q not in arcs]
    outerRings = [((q['pts'][0][0] + q['pts'][1][0]) / 2, (q['pts'][0][1] + q['pts'][1][1]) / 2,
                   math.hypot(q['pts'][1][0] - q['pts'][0][0], q['pts'][1][1] - q['pts'][0][1]) / 2) for q in arcs]
    circles = circles + outerRings
    boxes = [Bbox(p) for p in polys]
    outlines = [b for i, b in enumerate(boxes)
                if not any(j != i and Inside(b, o) and o != b for j, o in enumerate(boxes))]
    cuts = {i: [] for i in range(len(outlines))}
    rings = []
    for b in boxes:
        if b in outlines:
            continue
        host = min((i for i, o in enumerate(outlines) if Inside(b, o)),
                   key=lambda i: (outlines[i][2] - outlines[i][0]) * (outlines[i][3] - outlines[i][1]))
        cuts[host].append(("slot", b))
    loose = []
    for c in circles:
        cb = (c[0] - c[2], c[1] - c[2], c[0] + c[2], c[1] + c[2])
        hosts = [i for i, o in enumerate(outlines) if Inside(cb, o)]
        if hosts:
            cuts[hosts[0]].append(("hole", c))
        else:
            loose.append(c)
    for c in sorted(loose, key=lambda c: -c[2]):
        bore = [d for d in loose if d is not c and d[2] < c[2] and math.hypot(d[0] - c[0], d[1] - c[1]) < 1e-6]
        if bore:
            rings.append((c, bore[0]))
    errs, webs = [], []
    for i, o in enumerate(outlines):
        items = cuts[i]
        for kind, g in items:
            b = g if kind == "slot" else (g[0] - g[2], g[1] - g[2], g[0] + g[2], g[1] + g[2])
            web = min(b[0] - o[0], b[1] - o[1], o[2] - b[2], o[3] - b[3])
            webs.append(web)
            if web < MinWeb:
                errs.append("%s at (%.1f, %.1f): edge web %.2f" % (kind, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, web))
        for j, (ka, ga) in enumerate(items):
            for kb, gb in items[j + 1:]:
                if ka == "hole" and kb == "hole":
                    gap = math.hypot(ga[0] - gb[0], ga[1] - gb[1]) - ga[2] - gb[2]
                elif ka == "hole":
                    gap = CircRectGap(ga, gb)
                elif kb == "hole":
                    gap = CircRectGap(gb, ga)
                else:
                    gap = RectGap(ga, gb)
                webs.append(gap)
                if gap < MinWeb:
                    errs.append("cuts too close in part %d: %.2f" % (i, gap))
    for outer, bore in rings:
        webs.append(outer[2] - bore[2])
    for i, a in enumerate(outlines):
        for b in outlines[i + 1:]:
            if RectGap(a, b) < MinWeb:
                errs.append("parts too close: %.2f" % RectGap(a, b))
        for outer, _ in rings:
            if CircRectGap(outer, a) < MinWeb:
                errs.append("ring too close to a part: %.2f" % CircRectGap(outer, a))
    xs = [o[2] for o in outlines] + [c[0] + c[2] for c, _ in rings]
    ys = [o[3] for o in outlines] + [c[1] + c[2] for c, _ in rings]
    x0 = min([o[0] for o in outlines] + [c[0] - c[2] for c, _ in rings])
    y0 = min([o[1] for o in outlines] + [c[1] - c[2] for c, _ in rings])
    ext = (max(xs), max(ys))
    if x0 < 0 or y0 < 0 or ext[0] > Sheet[0] or ext[1] > Sheet[1]:
        errs.append("runs off the 24 x 18 in sheet: extent %.1f x %.1f" % ext)
    if ext[0] > Bed[0] or ext[1] > Bed[1]:
        errs.append("outside the laser bed")
    print("%s: %d parts, %d rings, %d cuts, extent %.1f x %.1f, least web %.2f mm: %s"
          % (path.split("/")[-1], len(outlines), len(rings), sum(len(v) for v in cuts.values()),
             ext[0], ext[1], min(webs) if webs else float("nan"), "PASS" if not errs else "FAIL"))
    for e in errs:
        print("   ", e)
    return not errs


if __name__ == "__main__":
    sys.exit(0 if all([Main(p) for p in sys.argv[1:]]) else 1)
