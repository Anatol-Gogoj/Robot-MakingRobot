"""Render the layout study: each case as lower and upper deck plans, to scale, Paul Tol colours."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ZoneColour = {"mains": "#FFAABB", "dc": "#EEDD88", "drv": "#77AADD", "log": "#99DDFF"}   # Tol light
Exits = {"UL": (70.0, 0.0, "upper"), "UF": (0.0, 191.6, "upper"), "UR": (395.0, 330.0, "upper"),
         "LL": (260.0, 0.0, "lower"), "INLET": (457.0, 129.0, "lower")}


def Deck(ax, run, deck, title):
    D, W = run["deck"]
    ax.add_patch(Rectangle((0, 0), D, W, fill=False, lw=1.0))
    ax.add_patch(Rectangle((20, 20), D - 40, W - 40, fill=False, lw=0.6, ls="--", color="#555555"))
    for b, p in run["place"].items():
        if p["deck"] != deck:
            continue
        ax.add_patch(Rectangle((p["x"], p["y"]), p["w"], p["h"], facecolor=ZoneColour[p["zone"]],
                               edgecolor="black", lw=0.8))
        ax.text(p["x"] + p["w"] / 2, p["y"] + p["h"] / 2, "%s\n%d tall" % (b, round(p["height"])),
                ha="center", va="center", fontsize=6.5)
    if deck == "lower" and "mains box" in run:
        x0, y0, x1, y1 = run["mains box"]
        ax.add_patch(Rectangle((x0 - 5, y0 - 5), x1 - x0 + 10, y1 - y0 + 10, fill=False, lw=1.4,
                               edgecolor="#CC3311", ls="--"))
    ex = dict(Exits)
    for e, xy in run.get("exits", {}).items():
        ex[e] = (xy[0], xy[1], Exits[e][2])
    for n, (x, y, d) in ex.items():
        if d == deck and x <= D:
            ax.plot(x, y, marker="o", color="#CC3311", ms=5)
            ax.text(x, y, " " + n, fontsize=6, color="#CC3311", va="bottom")
    ax.set_xlim(-15, D + 15)
    ax.set_ylim(-15, W + 15)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    ax.set_xlabel("x: front (0) to back, mm", fontsize=6)
    ax.set_ylabel("y: left (0) to right, mm", fontsize=6)
    ax.tick_params(labelsize=6)


def Main():
    runs = json.load(open(sys.argv[1]))["runs"]
    keep = [r for r in runs if r.get("place") and (len(sys.argv) < 4 or r["label"] in sys.argv[3].split("|"))]
    fig, axes = plt.subplots(len(keep), 2, figsize=(11, 3.6 * len(keep)))
    for i, r in enumerate(keep):
        h = r["heights"]
        decks = ["lower", "upper"] if any(p["deck"] == "upper" for p in r["place"].values()) else ["lower"]
        for j, deck in enumerate(["lower", "upper"]):
            ax = axes[i][j]
            if deck not in decks:
                ax.axis("off")
                continue
            Deck(ax, r, deck, "%s: %s deck" % (r["label"], deck) + chr(10) +
                 "wire %s conductor-mm; lower bay %s mm; wire room %s mm"
                 % ("{:,}".format(r["wire"]), h["lower bay"], h["wire room"]))
    fig.tight_layout()
    fig.savefig(sys.argv[2], dpi=150)
    print("wrote", sys.argv[2])


if __name__ == "__main__":
    Main()
