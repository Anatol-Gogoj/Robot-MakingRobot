"""Read back an R12 DXF written by draw_wiring.py: closed polylines and circles on layer CUT.
Checks that every hole and slot lies inside the outline with a web of at least 2 mm to the edge
and to every other cut."""
import math
import sys

MinWeb = 2.0


def Load(path):
    lines = [l.strip() for l in open(path, encoding="ascii").read().splitlines()]
    pairs = list(zip(lines[0::2], lines[1::2]))
    polys, circles, cur = [], [], None
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if code == "0" and val == "POLYLINE":
            cur = {"pts": [], "closed": False}
            polys.append(cur)
        elif code == "0" and val == "VERTEX":
            v = {}
            j = i + 1
            while j < len(pairs) and pairs[j][0] != "0":
                v[pairs[j][0]] = float(pairs[j][1]) if pairs[j][0] in ("10", "20", "42") else pairs[j][1]
                j += 1
            cur["pts"].append((v["10"], v["20"], v.get("42", 0.0)))
            i = j - 1
        elif code == "70" and cur is not None and not cur["pts"]:
            cur["closed"] = val == "1"
        elif code == "0" and val == "CIRCLE":
            c = {}
            j = i + 1
            while j < len(pairs) and pairs[j][0] != "0":
                c[pairs[j][0]] = pairs[j][1]
                j += 1
            circles.append((float(c["10"]), float(c["20"]), float(c["40"])))
            i = j - 1
        i += 1
    return polys, circles


def Bbox(poly):
    """Bounding box of an obround or rectangle (bulge arcs are half circles on the short side)."""
    xs = [p[0] for p in poly["pts"]]
    ys = [p[1] for p in poly["pts"]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if any(p[2] for p in poly["pts"]):
        if x1 - x0 > y1 - y0:
            r = (y1 - y0) / 2
            x0, x1 = x0 - r, x1 + r
        else:
            r = (x1 - x0) / 2
            y0, y1 = y0 - r, y1 + r
    return x0, y0, x1, y1


def Main(path):
    polys, circles = Load(path)
    bad = [p for p in polys if not p["closed"]]
    outline = max(polys, key=lambda p: (Bbox(p)[2] - Bbox(p)[0]) * (Bbox(p)[3] - Bbox(p)[1]))
    ox0, oy0, ox1, oy1 = Bbox(outline)
    cuts = [("hole", x - r, y - r, x + r, y + r, (x, y, r)) for x, y, r in circles]
    cuts += [("slot",) + Bbox(p) + (None,) for p in polys if p is not outline]
    errs = ["open polyline"] * len(bad)
    for kind, x0, y0, x1, y1, c in cuts:
        web = min(x0 - ox0, y0 - oy0, ox1 - x1, oy1 - y1)
        if web < MinWeb:
            errs.append("%s at (%.1f, %.1f): edge web %.2f" % (kind, (x0 + x1) / 2, (y0 + y1) / 2, web))
    for i, a in enumerate(cuts):
        for b in cuts[i + 1:]:
            if a[5] and b[5]:
                gap = math.hypot(a[5][0] - b[5][0], a[5][1] - b[5][1]) - a[5][2] - b[5][2]
            else:
                dx = max(b[1] - a[3], a[1] - b[3], 0.0)
                dy = max(b[2] - a[4], a[2] - b[4], 0.0)
                gap = math.hypot(dx, dy)
            if gap < MinWeb:
                errs.append("%s and %s too close: %.2f" % (a[0], b[0], gap))
    print("%s: outline %.1f x %.1f, %d holes, %d slots, %s"
          % (path.split("/")[-1], ox1 - ox0, oy1 - oy0, len(circles), len(polys) - 1,
             "PASS" if not errs else "FAIL"))
    for e in errs:
        print("   ", e)
    return not errs


if __name__ == "__main__":
    ok = all([Main(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
