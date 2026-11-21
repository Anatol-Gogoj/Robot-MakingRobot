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
# Positive lock. A ratchet backs up the friction: sawtooth notches in a rebate on the slider's +v
# side (full height, short, so the slider's full-width back still runs in the frame's +v guide),
# and a flexure pawl cut into the frame's +v side block. Pushing the slider in clicks it past
# each notch; the pawl's square face blocks any movement back out. The arm's root is at the back,
# so a retract load compresses it off-centre and pushes the pawl deeper into the notch instead of
# levering it out. To release, the operator pulls the release tab (in front of the frame, on the
# open side) outward, which lifts the pawl out of the notches, and pulls the slider back by its lip
# until the rebate's end wall stops it at the open position.
# The tab's travel is limited by the slot behind the arm, so the pawl can never clear that end
# wall, even with the slider at either side of its guide clearance: the slider is captive. For cleaning, unscrew the frame; the slider then lifts out upward.
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
    # Ratchet, sized for FFF with a 0.4 mm nozzle (design values)
    RatchetPitch=2.0,      # lock step along the slider: 2.0 x tan(6 deg) = 0.21 mm of lift per tooth
    NotchDepth=0.8,        # notch depth below the rebate floor
    NotchFloor=0.8,        # flat at the bottom of each notch (two 0.4 mm lines)
    ToothTip=0.6,          # flat at the pawl tip
    GrooveDepth=2.0,       # rebate in the slider's +v side face; its back-out end wall is the open stop
    PawlPreload=0.4,       # relaxed pawl tip past a notch floor; equals the guide float, so it still
                           # seats fully when the pawl pushes the slider to its -v wall
    PawlU=-8.0,            # frame u of the pawl's square (locking) face
    PawlRampDeg=45.0,      # pawl ramp face; steeper than the notch ramp (38.7 deg) so it seats fully
    ArmRootU=20.0,         # the flexure arm is fixed to the side block here (back) and free toward -u
    ArmGap=0.5,            # gap between the arm and the base / guide wall
    ArmT=2.0,              # arm thickness (bends in v)
    ArmSlot=2.25,          # slot behind the arm from the pawl's square face back to the root; the arm
                           # meets its wall at the pawl, which sets the pawl's largest deflection
    ArmSlotFront=6.5,      # wider slot in front of the pawl, where the arm swings further
    ArmTopClear=0.3,       # arm top below the carriage underside, so it does not rub
    TabU=(-33.0, -30.0),   # release tab in front of the frame's front face (the open side); 6 mm out, so
                           # it still clears the face when it tilts at the stop
    TabOuterV=50.0,        # tab reaches past the side block (outer face at 38)
    HookV=(46.0, 49.0),    # finger hook: a rib on the tab's +u face beyond the block, pulled outward
    HookDepth=3.0,
    ToothClear=0.5,        # base relief around the pawl tooth
    BedRelief=0.3,         # extra 0.3 x 0.3 mm relief at the bed where the tooth and arm meet the base
                           # (first-layer squish would otherwise weld them); use elephant-foot compensation
    Eprint=2500.0,         # MPa, printed PLA or PETG along the layers; assumed
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


ArmIn = WallIn + P["ArmGap"]                                   # arm inner face
Pen = P["GrooveDepth"] + P["NotchDepth"] + P["PawlPreload"]   # relaxed pawl tip, past the slider face
TipV = P["SliderHalf"] - Pen
GrooveStart = P["PawlU"] - P["Stroke"][1]                     # slider u' of the open-position stop wall
ToothEnd = P["PawlU"] + P["ToothTip"] + (ArmIn - TipV) / math.tan(math.radians(P["PawlRampDeg"]))
GrooveEnd = ToothEnd - P["Stroke"][0] + 0.8                     # rebate ends just past the tooth's reach
Float = P["WallGap"]                                            # slider play to either guide wall
ToothTop = SliderTop(P["Stroke"][1]) - 0.3                     # below the slider top at every position


def LockPositions():
    """Slider u' of each notch's square wall, and the offset p at which the pawl locks there."""
    out, k = [], 1
    # the last notch sits 0.3 before the push-in stop, so it clicks despite print tolerance
    while GrooveStart + k * P["RatchetPitch"] <= P["PawlU"] - P["Stroke"][0] - 0.3 + 1e-9:
        w = GrooveStart + k * P["RatchetPitch"]
        out.append((w, P["PawlU"] - w))
        k += 1
    return out


def ProfileSolid(pts, v0, v1):
    """Polygon in the u-z plane extruded from v0 to v1."""
    w = Part.makePolygon([V(u, v0, z) for u, z in pts] + [V(pts[0][0], v0, pts[0][1])])
    return Part.Face(w).extrude(V(0, v1 - v0, 0))


def Box(u0, u1, v0, v1, z0, z1):
    return Part.makeBox(u1 - u0, v1 - v0, z1 - z0, V(u0, v0, z0))


def ArmY(x):
    """End-loaded cantilever shape, x from the root toward the tab (free end at ArmLen)."""
    return x * x * (3 * ArmLen - x)


def ArmSlope(x):
    return 6 * ArmLen * x - 3 * x * x


ArmLen = P["ArmRootU"] - sum(P["TabU"]) / 2
XTip = P["ArmRootU"] - P["PawlU"]               # the pawl's square face, where the slot stops the arm
TipAtStop = P["ArmSlot"]                         # deflection at the pawl when the arm meets the slot


def Tooth(shift=0.0, slider=0.0):
    """The pawl tooth with the arm deflected outward by shift at the pawl's square face (beam shape:
    the tooth also tilts, its back end moving less), seen relative to a slider moved by slider in v."""
    pts = [V(P["PawlU"], ArmIn, 0), V(P["PawlU"], TipV, 0), V(P["PawlU"] + P["ToothTip"], TipV, 0), V(ToothEnd, ArmIn, 0)]
    prism = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, ToothTop + 30))
    prism.translate(V(0, 0, -30))
    ua, ub = P["PawlU"] - 1, ToothEnd + 1
    bed = ProfileSolid([(ua, ToothTop), (ub, ToothTop), (ub, FrameBottom(ub)), (ua, FrameBottom(ua))], TipV - 1, ArmIn + 1)
    t = prism.common(bed)
    if shift:
        slope = shift * ArmSlope(XTip) / ArmY(XTip)
        t.rotate(V(P["PawlU"], TipV, 0), V(0, 0, 1), -math.degrees(math.atan(slope)))
    t.translate(V(0, shift - slider, 0))
    return t


def Frame(withTooth=True):
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
    # flexure pawl in the +v side block: free the arm from the base and the block, keep its root
    f0, r0 = u0 - 0.01, P["ArmRootU"]
    armOut = ArmIn + P["ArmT"]
    narrowFrom = P["PawlU"]
    frame = frame.cut(Box(f0, r0, WallIn, ArmIn, ZBottom - 1, 1))
    frame = frame.cut(Box(narrowFrom, r0, armOut, armOut + P["ArmSlot"], ZBottom - 1, 1))
    frame = frame.cut(Box(f0, narrowFrom, armOut, armOut + P["ArmSlotFront"], ZBottom - 1, 1))
    frame = frame.cut(Box(f0, r0, ArmIn, armOut, -P["ArmTopClear"], 1))
    # relief in the base under the pawl tooth, which runs down to the bed
    frame = frame.cut(Box(P["PawlU"] - P["ToothClear"], ToothEnd + P["ToothClear"], TipV - P["ToothClear"], WallIn + 0.01,
                          ZBottom - 1, 1))
    # bed relief: widen the tooth relief and the arm gap by BedRelief over the first BedRelief of height
    br = P["BedRelief"]

    def BedStrip(ua, ub, v0, v1):
        return ProfileSolid([(ua, FrameBottom(ua) + br), (ub, FrameBottom(ub) + br), (ub, FrameBottom(ub) - 1),
                             (ua, FrameBottom(ua) - 1)], v0, v1)
    frame = frame.cut(BedStrip(P["PawlU"] - P["ToothClear"] - br, ToothEnd + P["ToothClear"] + br,
                               TipV - P["ToothClear"] - br, WallIn + 0.01))
    frame = frame.cut(BedStrip(f0, r0, WallIn - br, ArmIn + 0.01))
    # arm extension past the front face and the release tab, both standing on the bed plane
    ta, tb = P["TabU"]

    def Bed(ua, ub):
        return [(ua, -P["ArmTopClear"]), (ub, -P["ArmTopClear"]), (ub, FrameBottom(ub)), (ua, FrameBottom(ua))]
    frame = frame.fuse(ProfileSolid(Bed(ta, u0 + 0.01), ArmIn, armOut))
    frame = frame.fuse(ProfileSolid(Bed(ta, tb), ArmIn, P["TabOuterV"]))
    frame = frame.fuse(ProfileSolid(Bed(tb - 0.01, tb + P["HookDepth"]), P["HookV"][0], P["HookV"][1]))
    if withTooth:
        frame = frame.fuse(Tooth())
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
    # ratchet: a full-height rebate in the +v side face from GrooveStart (its end wall is the open
    # stop) to GrooveEnd, with sawtooth notches in its floor; each notch's square wall faces +u'
    gf = P["SliderHalf"] - P["GrooveDepth"]
    nf = gf - P["NotchDepth"]
    s = s.cut(Box(GrooveStart, GrooveEnd, gf, P["SliderHalf"] + 1, -30, 1))
    for w, _ in LockPositions():
        pts = [V(w, gf + 0.01, 0), V(w, nf, 0), V(w + P["NotchFloor"], nf, 0), V(w + P["RatchetPitch"], gf + 0.01, 0)]
        notch = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, 31))
        notch.translate(V(0, 0, -30))
        s = s.cut(notch)
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
    frame = Frame(withTooth=False)   # the pawl tooth is checked on its own below
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
    out.append("Ratchet (positive lock)")
    locks = LockPositions()
    seatBad, blockBad, rideBad = [], [], []
    half = P["RatchetPitch"] / 2
    for w, p in locks:
        s = Slider(p)
        # seated: the pawl pushes the slider to its -v wall and still sits on the notch floor
        if Tooth(P["PawlPreload"] - Float + 0.03, -Float).common(s).Volume > 1e-3:
            seatBad.append(p)
        # a pull-back of 0.3 is blocked with the slider at either side of its guide clearance
        for f in (-Float, Float):
            if Tooth(max(0.0, P["PawlPreload"] + f) + 0.03, f).common(Slider(p + 0.3)).Volume < 1e-3:
                blockBad.append((p, f))
        if p - half >= a and Tooth(P["PawlPreload"] + P["NotchDepth"] + Float + 0.03, Float).common(Slider(p - half)).Volume > 1e-3:
            rideBad.append(p)
    ok = not (seatBad or blockBad or rideBad)
    bad += 0 if ok else 1
    out.append("  %d lock positions, p = %.1f .. %.1f every %.1f (%.3f mm of lift per tooth); nominal pad locks at p = 0%s" % (
        len(locks), locks[-1][1], locks[0][1], P["RatchetPitch"], P["RatchetPitch"] * Tan, "" if ok else "  FAIL"))
    out.append("  seats in every notch, blocks a 0.3 mm pull-back at every notch at either side of the +-%.1f guide float,"
               % Float)
    out.append("    and rides over the notches on push-in%s" % (
        "" if ok else ": seat %s block %s ride %s" % (seatBad, blockBad, rideBad)))
    relBad = []
    for k in range(37):
        p = a + (b - a) * k / 36
        if Tooth(TipAtStop, Float).common(Slider(p)).Volume > 1e-3:
            relBad.append(round(p, 2))
    captive = Tooth(TipAtStop, -Float).common(Slider(b + 0.3)).Volume > 1e-3
    ok = not relBad and captive
    bad += 0 if ok else 1
    out.append("  release tab pulled to its stop (pawl lifted %.2f): the slider pulls back freely from p %.0f to %.0f," % (
        TipAtStop, a, b))
    out.append("    checked with the slider at its +v side%s" % ("" if not relBad else "  BLOCKED at %s" % relBad))
    out.append("    and the rebate's end wall still stops it at p = %.0f with the slider at its -v side: captive%s" % (
        b, "" if captive else "  NOT CAPTIVE"))
    relM = TipAtStop - P["NotchDepth"] - P["PawlPreload"] - Float
    capM = Pen - Float - TipAtStop
    ok = relM >= 0.5 and capM >= 0.5
    bad += 0 if ok else 1
    out.append("  margins at the tab stop, worst side of the float: clears the notches by %.2f; overlaps the end wall by %.2f%s" % (
        relM, capM, "" if ok else "  THIN"))
    # arm: cantilever from the root (back) with the pull at the tab (front); the slot stops it at the pawl
    x = XTip
    L = ArmLen
    mid = (P["ArmRootU"] + P["FrameU"][0]) / 2
    h = -P["ArmTopClear"] - FrameBottom(mid)
    I = h * P["ArmT"] ** 3 / 12
    E = P["Eprint"]

    def TabForce(dPawl):
        return 6 * E * I * dPawl / (x ** 2 * (3 * L - x))
    clear = P["NotchDepth"] + P["PawlPreload"]
    fStop = TabForce(TipAtStop)
    tipAtStop = TipAtStop * ArmY(L) / ArmY(x)
    frontAtStop = TipAtStop * ArmY(P["ArmRootU"] - P["FrameU"][0]) / ArmY(x)
    ok = frontAtStop < P["ArmSlotFront"] - 0.5
    bad += 0 if ok else 1
    out.append("  arm %.1f long (pawl %.1f from the root) x %.1f thick x %.1f high, E %.0f MPa assumed" % (L, x, P["ArmT"], h, E))
    out.append("  tab pull to clear the notches: about %.1f N; to the stop: about %.1f N; the tab moves about %.1f mm" % (
        TabForce(clear + Float), fStop, tipAtStop))
    out.append("  the arm at the front face moves %.1f in its %.1f slot%s" % (frontAtStop, P["ArmSlotFront"], "" if ok else "  TIGHT"))
    tilt = math.atan(TipAtStop * ArmSlope(L) / ArmY(x))
    gap0 = P["FrameU"][0] - P["TabU"][1]
    gapStop = gap0 - (P["BlockOuter"] - ArmIn) * math.tan(tilt)
    ok = gapStop >= 0.8
    bad += 0 if ok else 1
    out.append("  the tab tilts %.1f deg at the stop; its gap to the frame's front face closes from %.1f to %.1f%s" % (
        math.degrees(tilt), gap0, gapStop, "" if ok else "  TOO SMALL"))
    strain = fStop * L * (P["ArmT"] / 2) / (E * I)
    ok = strain < 0.008
    bad += 0 if ok else 1
    out.append("  root strain at the tab stop %.2f %% (%.0f MPa)%s" % (100 * strain, strain * E, "" if ok else "  HIGH"))
    pcr = math.pi ** 2 * E * I / (4 * x ** 2)
    fu = P["RetractN"] * Tan
    ok = pcr > 3 * fu
    bad += 0 if ok else 1
    out.append("  the %.0f N retract load acts on the pad in z; along u the slider sees at most %.0f x tan(alpha) = %.1f N," % (
        P["RetractN"], P["RetractN"], fu))
    out.append("    and none while friction holds. That load compresses the arm off-centre toward the slider, which")
    out.append("    pushes the pawl deeper; buckling of the root-to-pawl span %.0f N%s" % (pcr, "" if ok else "  LOW"))
    contactH = min(ToothTop, SliderTop(b)) - BaseTop(P["PawlU"])
    out.append("  bearing on one notch wall (%.1f x %.1f mm): %.1f MPa" % (P["NotchDepth"], contactH, fu / (P["NotchDepth"] * contactH)))
    out.append("  friction still holds the preload; the ratchet stops creep beyond one tooth")
    out.append("")
    out.append("Use")
    out.append("  lock: push the slider in by its lip until the pad is tight; it clicks past each tooth and stays")
    out.append("  release: hook a fingertip behind the rib at the tab's outer end and pull it outward until it stops")
    out.append("    (about %.0f mm); with the other hand pull the slider back by its lip until it stops; let go of the tab;" % tipAtStop)
    out.append("    slide the syringe out through the open side")
    out.append("  cleaning: unscrew the frame's two screws; the slider lifts out upward")
    out.append("")
    out.append("Printing")
    out.append("  frame: base bottom on the bed, so the part sits tilted %.1f deg and the ramp is a flat top face (iron it);" % P["Alpha"])
    out.append("    the slider's stepped underside then rides a smooth ramp and cannot lock into matching layer steps")
    out.append("  slider: flat top on the bed; its notch walls are vertical, so the teeth print as drawn")
    out.append("  the pawl tooth and the release tab stand on the bed plane with the arm; no supports; turn on")
    out.append("    elephant-foot compensation (the arm gap and the tooth relief are %.1f and %.1f wide, %.1f more at the bed)" % (
        P["ArmGap"], P["ToothClear"], P["BedRelief"]))
    out.append("  PETG preferred for the frame (the flexure); PLA works at this strain but fatigues sooner")
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
    out.append("  the release tab, its hook and the arm extension sit in front of the frame's front face, u %.0f to %.0f" % P["TabU"])
    out.append("    and out to %.0f in v: check the carriage, the C drive and the syringe's way out there" % P["TabOuterV"])
    return out, bad


def Draw(frame, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tol = {"frame": "#BBBBBB", "slider": "#4477AA", "pad": "#228833", "rod": "#CCBB44"}
    fig = plt.figure(figsize=(20, 14))
    gs = fig.add_gridspec(2, 3)
    axs = [[fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])],
           [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1:])]]

    def Sect(ax, shp, normal, off, ua, va, color, fill=True):
        for f in shp.slice(V(*normal), off):
            pts = f.discretize(Distance=0.25)
            xs, ys = [getattr(q, ua) for q in pts], [getattr(q, va) for q in pts]
            if fill:
                ax.fill(xs, ys, color=color, alpha=0.55, lw=0)
            ax.plot(xs, ys, color="#222222", lw=0.6)

    pad, cross = Pad()
    for ax, p, title in ((axs[0][0], 0.0, "Locked (p = 0, nominal pad)"), (axs[0][1], P["Stroke"][1], "Pulled back (p = +12): pad free")):
        Sect(ax, frame, (0, 1, 0), 17.0, "x", "z", tol["frame"])
        Sect(ax, Slider(p), (0, 1, 0), 17.0, "x", "z", tol["slider"])
        Sect(ax, pad, (0, 1, 0), 17.0, "x", "z", tol["pad"])
        ax.axhline(0, color="#222222", lw=2)
        ax.text(-30, 0.6, "carriage underside (z 0)", fontsize=8)
        ax.annotate("pull back to release", xy=(40, SliderTop(p) - 3), xytext=(46, -18), fontsize=8,
                    arrowprops=dict(arrowstyle="->", color="#EE6677"))
        ax.set_title(title + "; section v = 17 (u-z)", fontsize=10)
        ax.set_xlim(-32, 52)
        ax.set_ylim(-22, 4)
    ax = axs[0][2]
    Sect(ax, frame, (0, 0, 1), -5.0, "x", "y", tol["frame"])
    Sect(ax, Slider(0.0), (0, 0, 1), -5.0, "x", "y", tol["slider"])
    ax.annotate("hook and pull outward\nto release", xy=(-25.5, 47.5), xytext=(-12, 50), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#EE6677"))
    ax.annotate("pawl", xy=(P["PawlU"] + 0.5, 17.6), xytext=(2, 12), fontsize=8, arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.annotate("open stop\n(slider u' %.0f)" % GrooveStart, xy=(GrooveStart, 18.8), xytext=(-30, 12), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.annotate("arm root", xy=(P["ArmRootU"], 22), xytext=(10, 30), fontsize=8, arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.set_title("Ratchet detail, plan at z -5, locked at p = 0", fontsize=10)
    ax.set_xlim(-34, 26)
    ax.set_ylim(10, 54)
    ax = axs[1][0]
    Sect(ax, frame, (0, 0, 1), -6.0, "x", "y", tol["frame"])
    Sect(ax, Slider(0.0), (0, 0, 1), -3.0, "x", "y", tol["slider"])
    Sect(ax, cross, (0, 0, 1), -10.0, "x", "y", tol["rod"])
    th = [math.radians(k) for k in range(0, 361, 3)]
    ax.plot([P["PadD"] / 2 * math.cos(t) for t in th], [P["PadD"] / 2 * math.sin(t) for t in th], color=tol["pad"], lw=1.5, ls="--")
    ax.annotate("channel opens this way:\nslide the syringe out here", xy=(-26, 0), xytext=(-60, 22), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#EE6677"))
    ax.set_title("Plan, local frame (frame z -6, slider z -3, rod cross, pad dashed); holes at v +-32.5", fontsize=10)
    ax.set_xlim(-62, 50)
    ax.set_ylim(-42, 54)
    ax = axs[1][1]
    ax.axis("off")
    ax.text(0, 1, "\n".join(Checks(frame)[0]), va="top", family="monospace", fontsize=7.2, transform=ax.transAxes)
    for a in (axs[0][0], axs[0][1], axs[0][2], axs[1][0]):
        a.set_aspect("equal")
        a.grid(alpha=0.25)
    fig.suptitle("Screwless plunger clamp (issue 241): wedge slider under the thumb pad with a ratchet lock, frame screwed to the carriage. mm.", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
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
