# Builds a screwless plunger clamp for the 150 mL syringe adapter (issue 241): a frame that stays
# screwed to the acrylic C carriage, and a wedge slider pushed in by hand that lifts the syringe's
# thumb pad against the carriage. It replaces the PlungerClamp of
# CAD/150 mL Syringe Adapter/150mLSyringeAdapter_v20260916-A.FCStd, whose two thumbscrews are hard
# to tighten (owner, 2026-11-20). The barrel clamp (CylinderBodyClamp) is unchanged.
#
# Run with FreeCAD's console:  freecadcmd tools/build_plunger_wedge.py
# Writes CAD/150 mL Syringe Adapter/150mLSyringeAdapter_v20261120-A.FCStd, one STEP per printed
# part, _Checks.txt and _Sketch.png.
#
# How it works. The thumb pad sits in a gap under the carriage. The rod passes through a channel
# open to one side (today's channel, 28.3 mm wide). Under the pad rides the slider: flat on top,
# tapered underneath at Alpha, on a base ramp of the same angle. Pushing the slider toward the open
# side lifts its flat top and presses the pad up against the carriage; pulling it back drops the
# top and frees the pad to slide out through the open side. The shallow angle is self-locking.
# Dispensing pushes the pad up into the carriage, so the dose load never passes through the slider;
# the slider carries only the pull-back (retract) load.
#
# Frame: local (u, v, z). z = 0 is the carriage underside, z down is negative. The syringe axis is
# at u = v = 0. u points into the channel's closed end, so the channel opens toward -u. v is across
# the channel; the two carriage holes sit at v = +-32.5 (today's 65 mm hole spacing, Sketch004).
# Output is rotated 45 deg about z so that u lies along (1, 1) as in today's PlungerClamp, where the
# holes are at (23, -23) and (-23, 23). Dimensions in mm. Values marked "from v20260916-A" were read
# from today's file; everything else is a design value.

import math
import os

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
OutDir = os.path.join(Root, "CAD", "150 mL Syringe Adapter")
Stem = "150mLSyringeAdapter_v20261120-A"

P = dict(
    # Syringe (from v20260916-A, Sketch004 reference circle; pad thickness taken from the 2 mm
    # spacer bosses there, NOT measured)
    PadD=36.75,
    PadT=2.0,
    RodChannel=29.0,       # today's channel width (from v20260916-A: walls at v = +-14.50, measured by section)
    # Carriage holes (from v20260916-A: Hole and Hole001 are 5.3 mm, 65 mm apart). The screws come up
    # from below through the frame into the carriage, as today's thumbscrews do; their thread is not known
    HoleSpacing=65.0,
    HoleD=5.3,             # same as today's clamp
    CboreD=9.5,            # counterbore for a socket head (M5 head 8.5, M4 7.0)
    CboreDepth=5.5,
    # Wedge
    Alpha=6.0,             # deg; self-locking for any friction coefficient above tan(6) = 0.105
    T0=5.0,                # slider thickness at its u' = 0
    SliderU=(-22.0, 34.0),  # slider extent in its own u'
    SlotEnd=21.0,          # slider slot runs from its front tips to u' = 21
    SlotHalf=14.75,        # slider and base slot half-width (today's channel + 0.25 per side)
    SliderHalf=19.6,       # slider half-width (pad radius 18.375 is fully supported)
    WallGap=0.4,           # per side, slider to guide wall
    LipU=(30.0, 34.0),     # grip lip under the slider's back end; its front face is the push-in stop
    LipDrop=6.0,           # how far the lip hangs below the slider bottom
    Stroke=(-6.0, 12.0),   # slider offset p: -6 = pushed fully in (stop), +12 = pulled back (open)
    # Frame
    FrameU=(-24.0, 24.0),
    BaseT=3.0,             # frame base thickness, constant: its bottom is parallel to the ramp, so the
                           # frame prints tilted by Alpha with the ramp as a flat, ironable top face
    BlockOuter=38.0,       # side block outer v
    # Checks
    MuPetg=0.30,           # PETG on PETG, dry; assumed for the self-locking and push-force checks
    MuPad=0.20,            # PETG on polypropylene (thumb pad); assumed
    RetractN=34.0,         # largest pull-back load on the slider: the seal breakaway bound of the
                           # 2026-11-20 compact dispenser study (2.5 x the high seal glide); not measured
    PreloadN=20.0,         # pad preload the operator sets by hand (design value)
)

Tan = math.tan(math.radians(P["Alpha"]))
Zr = -P["PadT"] - P["T0"]          # base ramp height at u = 0
WallIn = P["SliderHalf"] + P["WallGap"]


def BaseTop(u):
    return Zr - u * Tan


def FrameBottom(u):
    return BaseTop(u) - P["BaseT"]


ZBottom = FrameBottom(P["FrameU"][1])       # lowest point of the frame


def SliderTop(p):
    """Height of the slider's flat top at offset p (negative p = pushed in, higher)."""
    return Zr + P["T0"] - p * Tan


def ProfileSolid(pts, v0, v1):
    """Polygon in the u-z plane extruded from v0 to v1."""
    w = Part.makePolygon([V(u, v0, z) for u, z in pts] + [V(pts[0][0], v0, pts[0][1])])
    return Part.Face(w).extrude(V(0, v1 - v0, 0))


def Box(u0, u1, v0, v1, z0, z1):
    return Part.makeBox(u1 - u0, v1 - v0, z1 - z0, V(u0, v0, z0))


def Frame():
    u0, u1 = P["FrameU"]
    base = ProfileSolid([(u0, BaseTop(u0)), (u1, BaseTop(u1)), (u1, FrameBottom(u1)), (u0, FrameBottom(u0))], -WallIn, WallIn)
    blk = [(u0, 0.0), (u1, 0.0), (u1, FrameBottom(u1)), (u0, FrameBottom(u0))]
    blocks = ProfileSolid(blk, WallIn, P["BlockOuter"]).fuse(ProfileSolid(blk, -P["BlockOuter"], -WallIn))
    frame = base.fuse(blocks)
    # rod channel through the base, open toward -u, closed end round and centred on the syringe axis
    h = P["SlotHalf"]
    frame = frame.cut(Box(u0 - 1, 0.0, -h, h, ZBottom - 1, 1.0))
    frame = frame.cut(Part.makeCylinder(h, -ZBottom + 2, V(0, 0, ZBottom - 1)))
    hv = P["HoleSpacing"] / 2
    for s in (1, -1):
        frame = frame.cut(Part.makeCylinder(P["HoleD"] / 2, -ZBottom + 2, V(0, s * hv, ZBottom - 1)))
        zb = FrameBottom(0.0)
        frame = frame.cut(Part.makeCylinder(P["CboreD"] / 2, P["CboreDepth"] + 1, V(0, s * hv, zb - 1)))
    return frame.removeSplitter()


def Slider(p):
    a, b = P["SliderU"]

    def Bot(u):
        return -(P["T0"] + u * Tan)
    s = ProfileSolid([(a, 0.0), (b, 0.0), (b, Bot(b)), (a, Bot(a))], -P["SliderHalf"], P["SliderHalf"])
    l0, l1 = P["LipU"]
    s = s.fuse(ProfileSolid([(l0, Bot(l0)), (l1, Bot(l1)), (l1, Bot(l1) - P["LipDrop"]), (l0, Bot(l0) - P["LipDrop"])],
                            -P["SliderHalf"], P["SliderHalf"]))
    h = P["SlotHalf"]
    s = s.cut(Box(a - 1, P["SlotEnd"] - h, -h, h, -20, 1))
    s = s.cut(Part.makeCylinder(h, 22, V(P["SlotEnd"] - h, 0, -20)))
    s = s.removeSplitter()
    s.translate(V(p, 0, SliderTop(p)))
    return s


def Pad():
    pad = Part.makeCylinder(P["PadD"] / 2, P["PadT"], V(0, 0, -P["PadT"]))
    rib = 2.0
    half = P["RodChannel"] / 2 - 0.2
    cross = Box(-half, half, -rib / 2, rib / 2, -40, -P["PadT"]).fuse(Box(-rib / 2, rib / 2, -half, half, -40, -P["PadT"]))
    return pad, cross


def Checks(frame):
    out, bad = [], 0
    a, b = P["Stroke"]
    out.append("Screwless plunger clamp (issue 241), alpha %.1f deg, pad %.2f x %.2f (thickness assumed)" % (
        P["Alpha"], P["PadD"], P["PadT"]))
    out.append("")
    out.append("Slider against the frame over the stroke (slider lifted 0.05 to ignore the sliding contact)")
    worst = 0.0
    for k in range(13):
        p = a + (b - a) * k / 12
        s = Slider(p)
        s.translate(V(0, 0, 0.05))
        worst = max(worst, s.common(frame).Volume)
    ok = worst < 1e-3
    bad += 0 if ok else 1
    out.append("  %s (largest overlap %.4f mm3 over 13 positions)" % ("ok" if ok else "OVERLAP", worst))
    stopGap = P["FrameU"][1] - (a + P["LipU"][0])
    ok = abs(stopGap) < 1e-6
    bad += 0 if ok else 1
    out.append("  push-in stop: lip front face meets the frame's back face at p = %.1f (gap %.3f)%s" % (a, stopGap, "" if ok else "  CHECK"))
    out.append("")
    out.append("Pad gap and preload range")
    openGap = -P["PadT"] - SliderTop(b)
    ok = openGap >= 0.8
    bad += 0 if ok else 1
    out.append("  pulled back (p = %.0f): slider top %.2f below the pad, so the pad slides out freely%s" % (b, openGap, "" if ok else "  TOO TIGHT"))
    thin = -SliderTop(a)
    thick = -SliderTop(b) - 0.3
    out.append("  locks pads from %.2f (slider fully in) to %.2f thick (0.3 left for sliding in); nominal %.2f locks at p = 0" % (
        thin, thick, P["PadT"]))
    out.append("  rise per mm of slider travel %.3f mm; 0.1 mm of pad tolerance is %.1f mm of travel" % (Tan, 0.1 / Tan))
    out.append("")
    out.append("Rod and pad clearances")
    rod = P["RodChannel"] / 2
    ok = P["SlotHalf"] - rod >= 0.2
    bad += 0 if ok else 1
    out.append("  slots %.2f wide against today's %.2f channel (+%.2f per side); the rod itself is not measured%s" % (
        2 * P["SlotHalf"], P["RodChannel"], P["SlotHalf"] - rod, "" if ok else "  TIGHT"))
    ledge = P["PadD"] / 2 - P["SlotHalf"]
    ok = ledge >= 3.0
    bad += 0 if ok else 1
    out.append("  pad ledge on the slider beside the slot: %.2f per side%s" % (ledge, "" if ok else "  SMALL"))
    side = WallIn - P["PadD"] / 2
    ok = side >= 0.5
    bad += 0 if ok else 1
    out.append("  pad edge to the guide walls: %.2f per side (the pad slides out between them)%s" % (side, "" if ok else "  TIGHT"))
    out.append("  slider to the guide walls: %.2f per side" % P["WallGap"])
    out.append("")
    out.append("Forces (friction coefficients assumed: PETG/PETG %.2f, PETG/pad %.2f)" % (P["MuPetg"], P["MuPad"]))
    phiB = math.degrees(math.atan(P["MuPetg"]))
    phiT = math.degrees(math.atan(P["MuPad"]))
    margin = phiB + phiT - P["Alpha"]
    ok = margin > 5.0
    bad += 0 if ok else 1
    out.append("  self-locking: alpha %.1f deg against friction angles %.1f + %.1f deg; margin %.1f deg%s" % (
        P["Alpha"], phiB, phiT, margin, "" if ok else "  THIN"))
    out.append("    if the pad slid along with the slider, only the bottom face would hold it: margin %.1f deg" % (phiB - P["Alpha"]))
    out.append("    a pull-back load presses the slider down; with no friction it would push the slider out with only")
    out.append("    %.1f N per 10 N of load (tan alpha)" % (10 * Tan))
    push = P["PreloadN"] * (math.tan(math.radians(P["Alpha"] + phiB)) + P["MuPad"])
    pull = P["PreloadN"] * (math.tan(math.radians(phiB - P["Alpha"])) + P["MuPad"])
    out.append("  hand force to reach %.0f N of preload: about %.0f N push; to release: about %.0f N pull" % (P["PreloadN"], push, pull))
    out.append("  retract load %.0f N (study bound, not measured) goes through the slider into the base ramp;" % P["RetractN"])
    out.append("    dispensing loads the carriage directly, not the slider")
    out.append("")
    out.append("Printing")
    out.append("  frame: base bottom on the bed, so the part sits tilted %.1f deg and the ramp is a flat top face (iron it);" % P["Alpha"])
    out.append("    the slider's stepped underside then rides a smooth ramp and cannot lock into matching layer steps")
    out.append("  slider: flat top on the bed")
    out.append("")
    out.append("Not modelled or not known")
    out.append("  the pad thickness (2.0 taken from the old clamp's spacer bosses), its diameter, and the rod width under it")
    out.append("  the screw thread into the carriage: today's holes are 5.3 mm (M5 clearance, or an M4 insert hole)")
    out.append("  the carriage underside: the frame's side blocks rise to it (z 0) at |v| 20..38, including the channel's open")
    out.append("    side, where today's plate has no material; check carriage hardware and the barrel clamp's swing there")
    out.append("  depth below the carriage: frame bottom %.1f and grip lip down to %.1f (today's clamp: -9.0); check the" % (
        ZBottom, SliderTop(P["Stroke"][1]) - (P["T0"] + P["LipU"][1] * Tan) - P["LipDrop"]))
    out.append("    pad-to-flange distance at full plunger insertion")
    out.append("  which way the channel must open (it must face the barrel clamp half that is unsnapped for a swap);")
    out.append("    the frame mounts in two orientations 180 deg apart on the same two holes")
    out.append("  no captive stop when pulling back: with the syringe out the slider can leave through the back; a snap tab")
    out.append("    at p = +12 would make it captive. During a dose the pad unloads the slider, so check for creep on the bench")
    return out, bad


def Draw(frame, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tol = {"frame": "#BBBBBB", "slider": "#4477AA", "pad": "#228833", "rod": "#CCBB44"}
    fig, axs = plt.subplots(2, 2, figsize=(15, 10))

    def Sect(ax, shp, normal, off, ua, va, color, fill=True):
        for f in shp.slice(V(*normal), off):
            pts = f.discretize(Distance=0.25)
            xs, ys = [getattr(q, ua) for q in pts], [getattr(q, va) for q in pts]
            if fill:
                ax.fill(xs, ys, color=color, alpha=0.55, lw=0)
            ax.plot(xs, ys, color="#222222", lw=0.6)

    pad, cross = Pad()
    for ax, p, title in ((axs[0, 0], 0.0, "Locked (p = 0, nominal pad)"), (axs[0, 1], P["Stroke"][1], "Pulled back (p = +12): pad free")):
        Sect(ax, frame, (0, 1, 0), 17.0, "x", "z", tol["frame"])
        Sect(ax, Slider(p), (0, 1, 0), 17.0, "x", "z", tol["slider"])
        Sect(ax, pad, (0, 1, 0), 17.0, "x", "z", tol["pad"])
        ax.axhline(0, color="#222222", lw=2)
        ax.text(-30, 0.6, "carriage underside (z 0)", fontsize=8)
        ax.annotate("pull back to release", xy=(40, SliderTop(p) - 3), xytext=(46, -18), fontsize=8,
                    arrowprops=dict(arrowstyle="->", color="#EE6677"))
        ax.set_title(title + "; section v = 17 (u-z), u toward the closed end", fontsize=10)
        ax.set_xlim(-32, 52)
        ax.set_ylim(-22, 4)
    ax = axs[1, 0]
    Sect(ax, frame, (0, 0, 1), -6.0, "x", "y", tol["frame"])
    Sect(ax, Slider(0.0), (0, 0, 1), -3.0, "x", "y", tol["slider"])
    Sect(ax, cross, (0, 0, 1), -10.0, "x", "y", tol["rod"])
    th = [math.radians(k) for k in range(0, 361, 3)]
    ax.plot([P["PadD"] / 2 * math.cos(t) for t in th], [P["PadD"] / 2 * math.sin(t) for t in th], color=tol["pad"], lw=1.5, ls="--")
    ax.annotate("channel opens this way:\nslide the syringe out here", xy=(-26, 0), xytext=(-60, 22), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#EE6677"))
    ax.set_title("Plan in the local frame (frame at z -6, slider at z -3, rod cross, pad dashed); holes at v +-32.5", fontsize=10)
    ax.set_xlim(-62, 50)
    ax.set_ylim(-42, 42)
    ax = axs[1, 1]
    ax.axis("off")
    ax.text(0, 1, "\n".join(Checks(frame)[0]), va="top", family="monospace", fontsize=7.4, transform=ax.transAxes)
    for a in axs.flat[:3]:
        a.set_aspect("equal")
        a.grid(alpha=0.25)
    fig.suptitle("Screwless plunger clamp (issue 241): wedge slider under the thumb pad, frame screwed to the carriage. mm.", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=95)
    plt.close(fig)


def Main():
    frame = Frame()
    checks, bad = Checks(frame)
    print("\n".join(checks))
    os.makedirs(OutDir, exist_ok=True)
    open(os.path.join(OutDir, Stem + "_Checks.txt"), "w", encoding="ascii", newline="\n").write(
        "\n".join(checks) + "\n\n%d check(s) failed\n" % bad)
    Draw(frame, os.path.join(OutDir, Stem + "_Sketch.png"))

    rot = FreeCAD.Placement(V(0, 0, 0), FreeCAD.Rotation(V(0, 0, 1), 45))
    parts = {"WedgeFrame": frame, "WedgeSlider": Slider(0.0)}
    pad, cross = Pad()
    doc = FreeCAD.newDocument("PlungerWedge")
    for name, shp in list(parts.items()) + [("ThumbPadRef", pad), ("RodCrossRef", cross)]:
        s = shp.copy()
        s.Placement = rot.multiply(s.Placement)
        o = doc.addObject("Part::Feature", name)
        o.Shape = s
        if name in parts:
            # print orientation: frame tilted so its base bottom lies on the bed; slider flat top down
            ps = shp.copy()
            if name == "WedgeSlider":
                ps.rotate(V(0, 0, 0), V(1, 0, 0), 180)
            else:
                ps.rotate(V(0, 0, 0), V(0, 1, 0), -P["Alpha"])
                a0 = V(P["FrameU"][0], 0, FrameBottom(P["FrameU"][0]))
                a1 = V(P["FrameU"][1], 0, FrameBottom(P["FrameU"][1]))
                r = FreeCAD.Rotation(V(0, 1, 0), -P["Alpha"])
                assert abs(r.multVec(a0).z - r.multVec(a1).z) < 1e-6, "frame bottom not level for printing"
            ps.translate(V(0, 0, -ps.BoundBox.ZMin))
            ps.exportStep(os.path.join(OutDir, "%s-%s.step" % (Stem, name)))
    doc.recompute()
    doc.saveAs(os.path.join(OutDir, Stem + ".FCStd"))
    FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed; wrote %s" % (bad, OutDir))


Main()
