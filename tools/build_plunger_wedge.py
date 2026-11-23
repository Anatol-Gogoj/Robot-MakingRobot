# Builds a screwless plunger clamp for the 150 mL syringe adapter (issues 241 and 246): a frame that
# stays screwed to the acrylic C carriage, and a wedge slider pushed in by hand that lifts the
# syringe's thumb pad against the carriage. It replaces the PlungerClamp of
# CAD/150 mL Syringe Adapter/150mLSyringeAdapter_v20260916-A.FCStd, whose two thumbscrews are hard
# to tighten (owner, 2026-11-20). The barrel clamp (CylinderBodyClamp) is unchanged.
#
# Run with FreeCAD's console:  freecadcmd tools/build_plunger_wedge.py
# Writes CAD/150 mL Syringe Adapter/150mLSyringeAdapter_v20261123-A.FCStd, one STEP per printed
# part, _Checks.txt and _Sketch.png.
#
# How it works. The thumb pad sits in a gap under the carriage. The rod passes through a channel
# open to one side (today's channel, 29.0 mm wide). Under the pad rides the slider: flat on top,
# tapered underneath at Alpha, on a base ramp of the same angle. Pushing the slider toward the open
# side lifts its flat top and presses the pad up against the carriage; pulling it back drops the
# top and frees the pad to slide out through the open side. The shallow angle is self-locking.
# Dispensing pushes the pad up into the carriage, so the dose load never passes through the slider;
# the slider carries only the pull-back (retract) load.
#
# Positive lock, released with one hand (issue 246). A ratchet backs up the friction. The pawl is on
# the slider: a flexure arm along the slider's +v edge, rooted at the slider's front tip and free
# toward the back, with a tooth that reaches into a rebate in the frame's +v guide wall. The rebate
# floor carries sawtooth notches. Pushing the slider in clicks the tooth past each notch; the square
# faces stop it backing out. The arm's root is ahead of (at -u from) the pawl, so a retract load
# compresses the arm off-centre and pushes the tooth deeper into the notch instead of levering it
# out. The arm runs past the slider's back end into a thumb trigger; a rigid finger ear sits on the
# slider's -v side opposite it. To release, pinch the trigger toward the ear with one hand: the tooth
# leaves the notches; keep pinching and pull the slider back. The slot between the arm and the
# slider body is a curved stop wall shaped like the arm at the design deflection, so a hard squeeze
# lifts the tooth clear of the notches but never out of the rebate: the rebate's back end wall stops
# the slider at the open position (captive) at either side of the guide float. A rigid push block
# and the ear are the slider's rearmost faces, so pushing it in never loads the arm. For cleaning,
# unscrew the frame; the slider then lifts out upward.
#
# Frame: local (u, v, z). z = 0 is the carriage underside, z down is negative. The syringe axis is
# at u = v = 0. u points into the channel's closed end, so the channel opens toward -u. v is across
# the channel; the two carriage holes sit at v = +-32.5 (today's 65 mm hole spacing, Sketch004).
# Slider parts are drawn in the slider's own u' (u' = u - p, where p is the slider offset).
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
Stem = "150mLSyringeAdapter_v20261123-A"

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
    SliderU=(-22.0, 34.0),  # slider body extent in its own u'
    SlotEnd=21.0,          # slider slot runs from its front tips to u' = 21
    SlotHalf=14.75,        # slider and base slot half-width (today's channel + 0.25 per side)
    SliderHalf=22.5,       # slider half-width; wide enough to carry the pawl arm beside the pad
    WallGap=0.4,           # per side, slider to guide wall
    LipU=(30.0, 34.0),     # grip lip under the slider's back end; its front face is the push-in stop
    LipDrop=6.0,           # how far the lip hangs below the slider bottom
    Stroke=(-6.0, 12.0),   # slider offset p: -6 = pushed fully in (stop), +12 = pulled back (open)
    # Frame
    FrameU=(-24.0, 24.0),
    BaseT=3.0,             # frame base thickness, constant: its bottom is parallel to the ramp, so the
                           # frame prints tilted by Alpha with the ramp as a flat, ironable top face
    BlockOuter=39.5,       # side block outer v; leaves 2.25 outside the screw counterbores
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
    ToothTip=0.6,          # flat at the tooth tip
    GrooveDepth=2.0,       # rebate in the frame's +v guide wall; its back end wall is the open stop
    EndClear=1.0,          # end wall this far past the open position: a squeezed tooth tilts toward it
    RebateClear=0.3,       # the rebate floor runs this far below the ramp, under the tooth's bottom
    PawlPreload=0.6,       # relaxed tooth tip past a notch floor; 0.2 more than the guide float, so the
                           # tooth still presses on the floor with the slider at its -v wall
    PawlU=8.0,             # slider u' of the tooth's square (locking) face, which faces +u
    PawlRampDeg=45.0,      # tooth ramp face; steeper than the notch ramp so it seats fully
    ArmRootU=-20.0,        # the flexure arm leaves the slider's front tip here and is free toward +u
    ArmT=1.7,              # arm thickness (bends in v); the root is only 2.9 high at the wedge's thin
                           # front, which sets the strain
    ArmGap=0.8,            # smallest gap between the arm and the slider body (near the root), wide
                           # enough not to weld on the first layer; the slot ends round at the root
    PawlStop=2.3,          # tooth deflection at which the arm lies on the curved stop wall
    ArmEndU=40.0,          # the arm runs past the body's back end (34) to here
    TrigU=(34.5, 40.0),    # thumb trigger on the arm's outer face, behind the body
    TrigOuterV=30.0,       # trigger outer face (pressed toward -v)
    EarU=(30.0, 42.0),     # rigid finger ear on the slider's -v side, opposite the trigger
    EarV=(-30.0, -18.0),   # ear outer face at -30; it overlaps the body back to -18
    PushU=(34.0, 42.0),    # rigid push block behind the body, the rearmost face with the ear: pushing
    PushV=(-18.0, 12.0),   # in never loads the arm (it would buckle); clear of the squeezed arm
    RidgeU=1.5,            # finger ridge along the front edge of the trigger's and the ear's outer faces,
    RidgeH=1.8,            # so a pinch pulls against an edge, not by skin friction alone
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


def SliderBot(u):
    """Slider bottom in its own frame (top at z = 0), at slider u'."""
    return -(P["T0"] + u * Tan)


Float = P["WallGap"]                                            # slider play to either guide wall
ArmInV = P["SliderHalf"] - P["ArmT"]                            # arm inner face (undeflected)
RebateFloor = WallIn + P["GrooveDepth"]                          # frame v of the rebate floor
NotchV = RebateFloor + P["NotchDepth"]                           # frame v of the notch floors
TipV = NotchV + P["PawlPreload"]                                 # relaxed tooth tip, slider centred
Pen = TipV - P["SliderHalf"]                                     # tooth height from the arm's outer face
ToothStart = P["PawlU"] - P["ToothTip"] - Pen / math.tan(math.radians(P["PawlRampDeg"]))
NotchRef = P["PawlU"] + P["Stroke"][1]       # the square face at the open position; the notch walls sit at
                                             # NotchRef - k x pitch (k >= 1), NotchRef itself is no wall
OpenStopU = NotchRef + P["EndClear"]                              # frame u of the rebate's back end wall
RebateU = (ToothStart + P["Stroke"][0] - 0.8, OpenStopU)          # rebate runs just past the tooth's reach


def LockPositions():
    """Frame u of each notch's square wall, and the offset p at which the tooth locks there."""
    out, k = [], 1
    # notches down to the last one at least 0.3 before the push-in stop, so it still clicks with print
    # tolerance; pads thin enough to need the last 2 mm of stroke are held by friction alone
    while NotchRef - k * P["RatchetPitch"] >= P["PawlU"] + P["Stroke"][0] + 0.3 - 1e-9:
        w = NotchRef - k * P["RatchetPitch"]
        out.append((w, w - P["PawlU"]))
        k += 1
    return out


# ---- the arm as a tapered cantilever (height = slider thickness at u'), loaded at the trigger ----

LoadX = sum(P["TrigU"]) / 2 - P["ArmRootU"]      # load point, measured from the root
PawlX = P["PawlU"] - P["ArmRootU"]
EndX = P["ArmEndU"] - P["ArmRootU"]
NBeam = 4000


def ArmH(x):
    return P["T0"] + (P["ArmRootU"] + x) * Tan


def ArmI(x):
    return ArmH(x) * P["ArmT"] ** 3 / 12


def BeamShape(loadX):
    """Deflection and slope along the arm for 1 N at loadX (mm/N, rad/N), sampled at NBeam + 1 points
    from the root to the arm's end; straight beyond the load point."""
    dx = EndX / NBeam
    xs = [k * dx for k in range(NBeam + 1)]
    th, y = [0.0], [0.0]
    for k in range(1, NBeam + 1):
        a, b = xs[k - 1], xs[k]
        ka = max(0.0, loadX - a) / (P["Eprint"] * ArmI(a))
        kb = max(0.0, loadX - b) / (P["Eprint"] * ArmI(b))
        th.append(th[-1] + 0.5 * (ka + kb) * dx)
        y.append(y[-1] + 0.5 * (th[-2] + th[-1]) * dx)
    return xs, y, th


def Interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    k = int(x / (xs[1] - xs[0]))
    k = min(k, len(xs) - 2)
    t = (x - xs[k]) / (xs[k + 1] - xs[k])
    return ys[k] + t * (ys[k + 1] - ys[k])


BeamX, BeamY, BeamTh = BeamShape(LoadX)
StopScale = P["PawlStop"] / Interp(BeamX, BeamY, PawlX)      # trigger force (N) at the stop


def Ystop(u):
    """Inward deflection of the arm at slider u' when it lies on the stop wall."""
    return StopScale * Interp(BeamX, BeamY, u - P["ArmRootU"])


def StopWallV(u):
    """Slider body edge beside the arm (the curved stop wall)."""
    return ArmInV - max(P["ArmGap"], Ystop(u))


def ProfileSolid(pts, v0, v1):
    """Polygon in the u-z plane extruded from v0 to v1."""
    w = Part.makePolygon([V(u, v0, z) for u, z in pts] + [V(pts[0][0], v0, pts[0][1])])
    return Part.Face(w).extrude(V(0, v1 - v0, 0))


def PlanSolid(pts, z0, z1):
    """Polygon in the u-v plane extruded from z0 to z1."""
    w = Part.makePolygon([V(u, v, z0) for u, v in pts] + [V(pts[0][0], pts[0][1], z0)])
    return Part.Face(w).extrude(V(0, 0, z1 - z0))


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
    # ratchet rebate in the +v guide wall, open at the top, its floor a little below the ramp; the
    # notches are cut into its floor, each square wall facing -u (it blocks the tooth moving +u)
    ra, rb = RebateU
    plan = [(ra, WallIn - 0.01), (rb, WallIn - 0.01), (rb, RebateFloor)]
    for w, _ in LockPositions():
        plan += [(w, RebateFloor), (w, NotchV), (w - P["NotchFloor"], NotchV), (w - P["RatchetPitch"], RebateFloor)]
    plan += [(ra, RebateFloor)]
    clean = []
    for q in plan:
        if not clean or abs(clean[-1][0] - q[0]) > 1e-9 or abs(clean[-1][1] - q[1]) > 1e-9:
            clean.append(q)
    prism = PlanSolid(clean, ZBottom - 1, 1.0)
    c = P["RebateClear"]
    region = ProfileSolid([(ra - 1, 1.0), (rb + 1, 1.0), (rb + 1, BaseTop(rb + 1) - c), (ra - 1, BaseTop(ra - 1) - c)],
                          WallIn - 1, NotchV + 1)
    frame = frame.cut(prism.common(region))
    return frame.removeSplitter()


def SliderBody():
    """The slider without its tooth, in its own frame (top at z = 0, u' along u)."""
    a, b = P["SliderU"]
    Bot = SliderBot
    s = ProfileSolid([(a, 0.0), (b, 0.0), (b, Bot(b)), (a, Bot(a))], -P["SliderHalf"], P["SliderHalf"])
    l0, l1 = P["LipU"]
    s = s.fuse(ProfileSolid([(l0, Bot(l0)), (l1, Bot(l1)), (l1, Bot(l1) - P["LipDrop"]), (l0, Bot(l0) - P["LipDrop"])],
                            -P["SliderHalf"], StopWallV(l1) - 0.01))
    # finger ear on the -v side, rigid, hanging as deep as the lip
    e0, e1 = P["EarU"]
    s = s.fuse(ProfileSolid([(e0, 0.0), (e1, 0.0), (e1, Bot(e1) - P["LipDrop"]), (e0, Bot(e0) - P["LipDrop"])],
                            P["EarV"][0], P["EarV"][1]))
    # finger ridge along the ear's front edge, on its outer face
    s = s.fuse(ProfileSolid([(e0, 0.0), (e0 + P["RidgeU"], 0.0), (e0 + P["RidgeU"], Bot(e0 + P["RidgeU"]) - P["LipDrop"]),
                             (e0, Bot(e0) - P["LipDrop"])], P["EarV"][0] - P["RidgeH"], P["EarV"][0] + 0.01))
    # rigid push block behind the body: with the ear it is the rearmost face, so pushing in never loads the arm
    k0, k1 = P["PushU"]
    s = s.fuse(ProfileSolid([(k0 - 0.01, 0.0), (k1, 0.0), (k1, Bot(k1) - P["LipDrop"]), (k0 - 0.01, Bot(k0) - P["LipDrop"])],
                            P["PushV"][0], P["PushV"][1]))
    h = P["SlotHalf"]
    s = s.cut(Box(a - 1, P["SlotEnd"] - h, -h, h, -30, 1))
    s = s.cut(Part.makeCylinder(h, 32, V(P["SlotEnd"] - h, 0, -30)))
    # curved slot that frees the arm from the body; its inner wall is the release stop
    us = [P["ArmRootU"] + (b + 1 - P["ArmRootU"]) * k / 120 for k in range(121)]
    slot = [(P["ArmRootU"], ArmInV), (b + 1, ArmInV)] + [(u, StopWallV(u)) for u in reversed(us)]
    s = s.cut(PlanSolid(slot, -30, 1))
    s = s.cut(Part.makeCylinder(P["ArmGap"] / 2, 31, V(P["ArmRootU"], ArmInV - P["ArmGap"] / 2, -30)))   # round slot end
    # the arm past the body's back end, and the thumb trigger on its outer face
    s = s.fuse(ProfileSolid([(b - 0.01, 0.0), (P["ArmEndU"], 0.0), (P["ArmEndU"], Bot(P["ArmEndU"])), (b - 0.01, Bot(b))],
                            ArmInV, P["SliderHalf"]))
    t0, t1 = P["TrigU"]
    s = s.fuse(ProfileSolid([(t0, 0.0), (t1, 0.0), (t1, Bot(t1) - P["LipDrop"]), (t0, Bot(t0) - P["LipDrop"])],
                            P["SliderHalf"] - 0.01, P["TrigOuterV"]))
    s = s.fuse(ProfileSolid([(t0, 0.0), (t0 + P["RidgeU"], 0.0), (t0 + P["RidgeU"], Bot(t0 + P["RidgeU"]) - P["LipDrop"]),
                             (t0, Bot(t0) - P["LipDrop"])], P["TrigOuterV"] - 0.01, P["TrigOuterV"] + P["RidgeH"]))
    return s.removeSplitter()


def ToothLocal():
    """The tooth on the arm's outer face, undeflected, in the slider frame."""
    pts = [V(P["PawlU"], P["SliderHalf"] - 0.01, 0), V(P["PawlU"], TipV, 0), V(P["PawlU"] - P["ToothTip"], TipV, 0),
           V(ToothStart, P["SliderHalf"] - 0.01, 0)]
    prism = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, 31))
    prism.translate(V(0, 0, -30))
    ua, ub = ToothStart - 1, P["PawlU"] + 1
    body = ProfileSolid([(ua, 0.0), (ub, 0.0), (ub, SliderBot(ub)), (ua, SliderBot(ua))], P["SliderHalf"] - 1, TipV + 1)
    return prism.common(body)


ToothShape = ToothLocal()


def Place(shape, p, vshift=0.0):
    s = shape.copy()
    s.translate(V(p, vshift, SliderTop(p)))
    return s


def Slider(p, vshift=0.0):
    return Place(SliderBody().fuse(ToothShape).removeSplitter(), p, vshift)


BodyShape = SliderBody()


def Tooth(p, defl=0.0, vshift=0.0, lift=0.05):
    """The tooth with the arm deflected inward (-v) by defl at the tooth's square face (beam shape:
    the tooth also tilts), on a slider at offset p moved by vshift in v. Lifted 0.05 by default, as
    the body is in the checks, so its sliding contact on the ramp does not count as overlap."""
    t = ToothShape.copy()
    if defl:
        slope = defl * Interp(BeamX, BeamTh, PawlX) / Interp(BeamX, BeamY, PawlX)
        t.rotate(V(P["PawlU"], P["SliderHalf"], 0), V(0, 0, 1), -math.degrees(math.atan(slope)))
        t.translate(V(0, -defl, 0))
    t = Place(t, p, vshift)
    t.translate(V(0, 0, lift))
    return t


def Pad():
    pad = Part.makeCylinder(P["PadD"] / 2, P["PadT"], V(0, 0, -P["PadT"]))
    rib = 2.0
    half = P["RodChannel"] / 2 - 0.2
    cross = Box(-half, half, -rib / 2, rib / 2, -40, -P["PadT"]).fuse(Box(-rib / 2, rib / 2, -half, half, -40, -P["PadT"]))
    return pad, cross


def Checks(frame):
    out, bad = [], 0
    a, b = P["Stroke"]
    out.append("Screwless plunger clamp (issues 241, 246), alpha %.1f deg, pad %.2f x %.2f (thickness assumed)" % (
        P["Alpha"], P["PadD"], P["PadT"]))
    out.append("")
    out.append("Slider against the frame over the stroke (slider lifted 0.05 to ignore the sliding contact; tooth checked below)")
    worst = 0.0
    for k in range(13):
        p = a + (b - a) * k / 12
        for f in (-Float, Float):
            s = Place(BodyShape, p, f)
            s.translate(V(0, 0, 0.05))
            worst = max(worst, s.common(frame).Volume)
    ok = worst < 1e-3
    bad += 0 if ok else 1
    out.append("  %s (largest overlap %.4f mm3 over 13 positions, each side of the float)" % ("ok" if ok else "OVERLAP", worst))
    stopGap = P["FrameU"][1] - (a + P["LipU"][0])
    earGap = P["FrameU"][1] - (a + P["EarU"][0])
    trigGap = (a + P["TrigU"][0]) - P["FrameU"][1]
    behind = min(P["PushU"][1], P["EarU"][1]) - max(P["ArmEndU"], P["TrigU"][1])
    clearPush = min(ArmInV - Ystop(u) for u in (P["SliderU"][1], P["ArmEndU"])) - P["PushV"][1]
    ok = abs(stopGap) < 1e-6 and abs(earGap) < 1e-6 and trigGap > 0 and behind >= 1.5 and clearPush >= 1.0
    bad += 0 if ok else 1
    out.append("  push-in stop: lip and ear front faces meet the frame's back face at p = %.1f (gaps %.3f, %.3f);" % (a, stopGap, earGap))
    out.append("    the trigger clears that face by %.1f; the push block and the ear stand %.1f behind the arm's end, so a" % (
        trigGap, behind))
    out.append("    push lands on rigid parts, and the squeezed arm clears the push block by %.1f%s" % (clearPush, "" if ok else "  CHECK"))
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
    lk = LockPositions()
    out.append("    the ratchet backs up pads from %.2f (p %.0f) to %.2f (p %.0f); thinner pads, down to %.2f, are held by friction alone" % (
        -SliderTop(lk[-1][1]), lk[-1][1], -SliderTop(lk[0][1]), lk[0][1], thin))
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
    # the arm's slot must not take the pad's support away: smallest margin from the pad's rim to the
    # stop wall (negative = the rim overhangs the slot), with the pad centred and moved +v by the rod's play
    r = P["PadD"] / 2
    play = P["SlotHalf"] - (P["RodChannel"] / 2 - 0.2)
    marg = {}
    for dv in (0.0, play):
        m = 99.0
        for k in range(37):
            p = a + (b - a) * k / 36
            for j in range(401):
                u = P["ArmRootU"] + (P["SliderU"][1] - P["ArmRootU"]) * j / 400
                uf = u + p
                if abs(uf) < r:
                    m = min(m, StopWallV(u) - (math.sqrt(r * r - uf * uf) + dv))
        marg[dv] = m
    ok = marg[play] >= -0.5
    bad += 0 if ok else 1
    out.append("  pad rim to the arm's slot, worst over the stroke: %+.2f with the pad centred, %+.2f with it %.2f off centre" % (
        marg[0.0], marg[play], play))
    out.append("    (the rod's play); negative is a rim overhang, harmless at this size%s" % ("" if ok else "  TOO MUCH"))
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
    out.append("Ratchet (positive lock), tooth on the slider, notches in the frame")
    locks = LockPositions()
    seatBad, blockBad, rideBad = [], [], []
    half = P["RatchetPitch"] / 2
    for w, p in locks:
        # seated: the tooth pushes the slider to its -v wall and still sits on the notch floor (0.05
        # ahead of the square wall, so the two faces do not touch)
        if Tooth(p - 0.05, P["PawlPreload"] - Float + 0.03, -Float).common(frame).Volume > 1e-3:
            seatBad.append(p)
        # a pull-back of 0.3 is blocked with the slider at either side of its guide clearance
        for f in (-Float, Float):
            if Tooth(p + 0.3, max(0.0, P["PawlPreload"] + f) + 0.03, f).common(frame).Volume < 1e-3:
                blockBad.append((p, f))
        if p - half >= a and Tooth(p - half, P["PawlPreload"] + P["NotchDepth"] + Float + 0.03, Float).common(frame).Volume > 1e-3:
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
        if Tooth(p, P["PawlStop"], Float).common(frame).Volume > 1e-3:
            relBad.append(round(p, 2))
    captive = Tooth(b + P["EndClear"] + 0.3, P["PawlStop"], -Float).common(frame).Volume > 1e-3
    ok = not relBad and captive
    bad += 0 if ok else 1
    out.append("  trigger squeezed to the stop (tooth lifted %.2f): the slider pulls back freely from p %.0f to %.0f," % (
        P["PawlStop"], a, b))
    out.append("    checked with the slider at its +v side%s" % ("" if not relBad else "  BLOCKED at %s" % relBad))
    out.append("    and the rebate's end wall still stops it by p = %.1f with the slider at its -v side: captive%s" % (
        b + P["EndClear"], "" if captive else "  NOT CAPTIVE"))
    # margins with the tooth's tilt at the stop: it turns about the arm face's corner, so the tip flat's
    # back corner rises by ToothTip x sin, the square-face tip drops by Pen x (1 - cos) and leads by Pen x sin
    th = math.atan(P["PawlStop"] * Interp(BeamX, BeamTh, PawlX) / Interp(BeamX, BeamY, PawlX))
    top = P["SliderHalf"] + Pen * math.cos(th) + P["ToothTip"] * math.sin(th) - P["PawlStop"]
    relM = RebateFloor - (top + Float)
    capM = (P["SliderHalf"] + Pen * math.cos(th) - P["PawlStop"] - Float) - WallIn
    lead = Pen * math.sin(th)
    ok = relM >= 0.4 and capM >= 0.5 and P["EndClear"] - lead >= 0.3
    bad += 0 if ok else 1
    out.append("  margins at the stop, worst side of the float, with the tooth's %.1f deg tilt: clears the notches by %.2f;" % (
        math.degrees(th), relM))
    out.append("    overlaps the end wall by %.2f; the tilt leads the tip by %.2f, so a squeezed slider meets the wall at p %.2f%s" % (
        capM, lead, b + P["EndClear"] - lead, "" if ok else "  THIN"))
    # arm: tapered cantilever (height = slider thickness) from the root at the front tip, loaded at the trigger
    fStop = StopScale
    yTrig = Ystop(P["ArmRootU"] + LoadX)
    E, t = P["Eprint"], P["ArmT"]
    strains = [(LoadX - x) * (t / 2) / ArmI(x) / E * fStop for x in BeamX if x <= LoadX]
    xs = [x for x in BeamX if x <= LoadX]
    kmax = max(range(len(strains)), key=lambda k: strains[k])
    out.append("  arm %.0f long from its root (u' %.0f) to the trigger, %.1f thick, %.1f to %.1f high (the slider's taper)," % (
        LoadX, P["ArmRootU"], t, ArmH(0), ArmH(LoadX)))
    out.append("    tooth %.0f from the root; E %.0f MPa assumed" % (PawlX, E))
    _, yp, _ = BeamShape(PawlX)
    kSeat = 1.0 / Interp(BeamX, yp, PawlX)
    out.append("  squeeze to clear the notches: about %.1f N; to the stop: about %.1f N; the trigger moves about %.1f mm" % (
        fStop * (P["NotchDepth"] + P["PawlPreload"] + Float) / P["PawlStop"], fStop, yTrig))
    out.append("  tooth spring: %.2f N/mm at the tooth; it holds the tooth on a notch floor with %.2f N (slider at its -v wall)" % (
        kSeat, kSeat * (P["PawlPreload"] - Float)))
    out.append("    to %.2f N (+v wall), and rides a crest at up to %.2f N" % (
        kSeat * (P["PawlPreload"] + Float), kSeat * (P["PawlPreload"] + P["NotchDepth"] + Float)))
    strain = strains[kmax]
    ok = strain < 0.008
    bad += 0 if ok else 1
    out.append("  largest bending strain at the stop %.2f %% (%.0f MPa), %.0f from the root%s" % (
        100 * strain, strain * E, xs[kmax], "" if ok else "  HIGH"))
    out.append("  a harder squeeze lays the arm on the curved stop wall, so the strain cannot grow past this")
    # past the stop, the arm behind the body (u' 34 to the trigger) carries the whole pinch as a short cantilever
    hard = 20.0
    xb = P["SliderU"][1] - P["ArmRootU"]
    hs = hard * (LoadX - xb) * (t / 2) / (E * ArmI(xb))
    ok = hs < 0.008
    bad += 0 if ok else 1
    out.append("  a hard %.0f N pinch past the stop bends the arm's free end over the body's back edge: strain %.2f %%%s" % (
        hard, 100 * hs, "" if ok else "  HIGH"))
    fu = P["RetractN"] * Tan
    # buckling of the tapered root-to-tooth span as a free cantilever (Rayleigh, with the static shape of a
    # side load at the tooth as the trial shape); conservative, since the notch floor blocks the tooth
    # from moving outward, the way the eccentric load drives it
    bx, _, bth = BeamShape(PawlX)
    num = den = 0.0
    for k in range(1, len(bx)):
        x0, x1 = bx[k - 1], bx[k]
        if x1 > PawlX:
            break
        xm = 0.5 * (x0 + x1)
        num += (PawlX - xm) ** 2 / (E * ArmI(xm)) * (x1 - x0)
        den += (0.5 * (bth[k - 1] + bth[k])) ** 2 * (x1 - x0)
    pcr = num / den
    ok = pcr > 3 * fu
    bad += 0 if ok else 1
    out.append("  the %.0f N retract load acts on the pad in z; along u the slider sees at most %.0f x tan(alpha) = %.1f N," % (
        P["RetractN"], P["RetractN"], fu))
    out.append("    and none while friction holds. That load reaches the tooth from the notch wall and compresses the arm")
    out.append("    off-centre toward its outer side, which pushes the tooth deeper; buckling of the root-to-tooth span,")
    out.append("    as a free cantilever on its real taper (Rayleigh): %.0f N%s" % (pcr, "" if ok else "  LOW"))
    contactH = ArmH(PawlX)
    out.append("  bearing on one notch wall (%.1f x %.1f mm): %.1f MPa" % (P["NotchDepth"], contactH, fu / (P["NotchDepth"] * contactH)))
    out.append("  friction still holds the preload; the ratchet stops creep beyond one tooth")
    # wall left between the rebate / notches and the +v counterbore
    hv, rc = P["HoleSpacing"] / 2, P["CboreD"] / 2
    wmin = 99.0
    for j in range(201):
        u = -rc + 2 * rc * j / 200
        if RebateU[0] <= u <= RebateU[1]:
            edge = hv - math.sqrt(max(0.0, rc * rc - u * u))
            floor = NotchV if any(w - P["RatchetPitch"] <= u <= w for w, _ in locks) else RebateFloor
            wmin = min(wmin, edge - floor)
    ok = wmin >= 1.2
    bad += 0 if ok else 1
    out.append("  wall between the notches and the +v screw counterbore: %.2f at least%s" % (wmin, "" if ok else "  THIN"))
    out.append("")
    out.append("Use")
    out.append("  lock: push the slider in by the push block and the ear (its rearmost faces, never the trigger) until the")
    out.append("    pad is tight; it clicks past each tooth and stays")
    out.append("  release, one hand: pinch the thumb trigger (+v side, behind the frame) toward the finger ear (-v side);")
    out.append("    the pinch span is %.0f mm outside to outside, %.0f mm when squeezed to the stop; keep pinching and pull" % (
        P["TrigOuterV"] - P["EarV"][0], P["TrigOuterV"] - yTrig - P["EarV"][0]))
    out.append("    the slider back, the finger pads against the ridges on the front edges, until it stops; stop pulling")
    out.append("    there (a yank loads the squeezed arm in compression); slide the syringe out through the open side")
    out.append("  cleaning: unscrew the frame's two screws; the slider lifts out upward")
    out.append("")
    out.append("Printing")
    out.append("  frame: base bottom on the bed, so the part sits tilted %.1f deg and the ramp is a flat top face (iron it);" % P["Alpha"])
    out.append("    the slider's stepped underside then rides a smooth ramp and cannot lock into matching layer steps;")
    out.append("    the ratchet rebate is a slot open at the top, so it needs no support; the counterbore ceilings")
    out.append("    print as short bridges")
    out.append("  slider: flat top on the bed; the arm, its tooth and the notch-facing walls are vertical, so they print")
    out.append("    as drawn; the arm's slot is %.1f wide at its narrowest; turn on elephant-foot compensation" % P["ArmGap"])
    out.append("  PETG preferred for the slider (the flexure); PLA works at this strain but fatigues sooner")
    out.append("")
    out.append("Not modelled or not known")
    out.append("  the pad thickness (2.0 taken from the old clamp's spacer bosses), its diameter, and the rod width under it")
    out.append("  the screw thread into the carriage: today's holes are 5.3 mm (M5 clearance, or an M4 insert hole)")
    out.append("  the carriage underside: the frame's side blocks rise to it (z 0) at |v| %.1f..%.1f, including the channel's" % (
        WallIn, P["BlockOuter"]))
    out.append("    open side, where today's plate has no material; check carriage hardware and the barrel clamp's swing there")
    out.append("  depth below the carriage: frame bottom %.1f and the push block down to %.1f (today's clamp: -9.0); check the" % (
        ZBottom, SliderTop(P["Stroke"][1]) + SliderBot(max(P["PushU"][1], P["EarU"][1])) - P["LipDrop"]))
    out.append("    pad-to-flange distance at full plunger insertion")
    out.append("  which way the channel must open (it must face the barrel clamp half that is unsnapped for a swap);")
    out.append("    the frame mounts in two orientations 180 deg apart on the same two holes")
    out.append("  behind the frame: the trigger, the ear, the push block and the lip reach u %.0f..%.0f (slider in) to %.0f" % (
        a + P["LipU"][0], a + P["PushU"][1], b + P["PushU"][1]))
    out.append("    (pulled back) and v %.1f..%.1f; check the carriage, the C drive and a hand's way in there" % (
        P["EarV"][0] - P["RidgeH"], P["TrigOuterV"] + P["RidgeH"]))
    return out, bad


def Draw(frame, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tol = {"frame": "#BBBBBB", "slider": "#4477AA", "pad": "#228833", "rod": "#CCBB44", "note": "#EE6677"}
    fig = plt.figure(figsize=(20, 14))
    gs = fig.add_gridspec(2, 3)
    axs = [[fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])],
           [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1:])]]

    def Sect(ax, shp, normal, off, ua, va, color, fill=True, ls="-"):
        for f in shp.slice(V(*normal), off):
            pts = f.discretize(Distance=0.25)
            xs, ys = [getattr(q, ua) for q in pts], [getattr(q, va) for q in pts]
            if fill:
                ax.fill(xs, ys, color=color, alpha=0.55, lw=0)
            ax.plot(xs, ys, color="#222222", lw=0.6, ls=ls)

    pad, cross = Pad()
    for ax, p, title in ((axs[0][0], 0.0, "Locked (p = 0, nominal pad)"), (axs[0][1], P["Stroke"][1], "Pulled back (p = +12): pad free")):
        Sect(ax, frame, (0, 1, 0), -17.0, "x", "z", tol["frame"])
        Sect(ax, Slider(p), (0, 1, 0), -17.0, "x", "z", tol["slider"])
        Sect(ax, pad, (0, 1, 0), -17.0, "x", "z", tol["pad"])
        ax.axhline(0, color="#222222", lw=2)
        ax.text(-30, 0.6, "carriage underside (z 0)", fontsize=8)
        ax.annotate("pinch and pull back\nto release", xy=(44 + p * 0.3, SliderTop(p) - 4), xytext=(36, -21), fontsize=8,
                    arrowprops=dict(arrowstyle="->", color=tol["note"]))
        ax.set_title(title + "; section v = -17 (u-z)", fontsize=10)
        ax.set_xlim(-32, 62)
        ax.set_ylim(-24, 4)
    ax = axs[0][2]
    Sect(ax, frame, (0, 0, 1), -5.0, "x", "y", tol["frame"])
    Sect(ax, Slider(0.0), (0, 0, 1), -5.0, "x", "y", tol["slider"])
    Sect(ax, Tooth(0.0, P["PawlStop"]), (0, 0, 1), -5.0, "x", "y", tol["note"], fill=False, ls="--")
    us = [P["ArmRootU"] + (P["ArmEndU"] - P["ArmRootU"]) * k / 200 for k in range(201)]
    ax.plot(us, [ArmInV - Ystop(u) for u in us], color=tol["note"], lw=0.9, ls="--")
    ax.plot(us, [P["SliderHalf"] - Ystop(u) for u in us], color=tol["note"], lw=0.9, ls="--")
    ax.annotate("tooth (square face +u)", xy=(P["PawlU"] - 0.3, TipV - 0.3), xytext=(-8, 29), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.annotate("open stop wall\n(frame u %.1f)" % OpenStopU, xy=(OpenStopU, RebateFloor), xytext=(14, 29.5), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.annotate("arm root", xy=(P["ArmRootU"], 21.5), xytext=(-26, 14), fontsize=8, arrowprops=dict(arrowstyle="->", color="#222222"))
    ax.annotate("arm squeezed to the\ncurved stop (dashed)", xy=(26, ArmInV - Ystop(26)), xytext=(18, 10.5), fontsize=8,
                arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax.set_title("Ratchet detail, plan at z -5, locked at p = 0", fontsize=10)
    ax.set_xlim(-28, 44)
    ax.set_ylim(8, 34)
    ax = axs[1][0]
    Sect(ax, frame, (0, 0, 1), -6.0, "x", "y", tol["frame"])
    Sect(ax, Slider(0.0), (0, 0, 1), -3.0, "x", "y", tol["slider"])
    Sect(ax, cross, (0, 0, 1), -10.0, "x", "y", tol["rod"])
    th = [math.radians(k) for k in range(0, 361, 3)]
    ax.plot([P["PadD"] / 2 * math.cos(q) for q in th], [P["PadD"] / 2 * math.sin(q) for q in th], color=tol["pad"], lw=1.5, ls="--")
    ax.annotate("channel opens this way:\nslide the syringe out here", xy=(-26, 0), xytext=(-62, 26), fontsize=8,
                arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax.annotate("thumb trigger", xy=(40, 27), xytext=(30, 40), fontsize=8, arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax.annotate("finger ear", xy=(40, -27), xytext=(30, -40), fontsize=8, arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax.annotate("push block", xy=(41, 0), xytext=(28, 8), fontsize=8, arrowprops=dict(arrowstyle="->", color=tol["note"]))
    ax.set_title("Plan, local frame (frame z -6, slider z -3, rod cross, pad dashed); holes at v +-32.5", fontsize=10)
    ax.set_xlim(-64, 50)
    ax.set_ylim(-44, 46)
    ax = axs[1][1]
    ax.axis("off")
    ax.text(0, 1, "\n".join(Checks(frame)[0]), va="top", family="monospace", fontsize=7.0, transform=ax.transAxes)
    for a in (axs[0][0], axs[0][1], axs[0][2], axs[1][0]):
        a.set_aspect("equal")
        a.grid(alpha=0.25)
    fig.suptitle("Screwless plunger clamp (issues 241, 246): wedge slider with a one-hand ratchet release, frame screwed to the carriage. mm.",
                 fontsize=12)
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
            ps.translate(V(0, 0, -ps.optimalBoundingBox().ZMin))   # BoundBox is loose on rotated cylinders
            assert ps.isValid() and len(ps.Solids) == 1, "%s is not one valid solid" % name
            ps.exportStep(os.path.join(OutDir, "%s-%s.step" % (Stem, name)))
    doc.recompute()
    doc.saveAs(os.path.join(OutDir, Stem + ".FCStd"))
    FreeCAD.closeDocument(doc.Name)
    print("\n%d check(s) failed; wrote %s" % (bad, OutDir))


Main()
