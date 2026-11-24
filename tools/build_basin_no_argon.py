# Removes the floor-fed argon channel from the spin coater's catch basin (issue 251) and writes the edited STEP.
#
# The basin (CAD/Spincoater/242mmCatchBasinSpincoater, made in SolidWorks) is a body of revolution about z, plus four
# 10 mm x 2.5 mm blind pockets on its underside at r 65, plus the argon path: a 14 mm rib with a 5 mm bore that runs on
# the inside of the bowl from an outlet boss on the chimney's flank (x 0, y 43, z 18.4, 9 mm countersink, facing -x),
# down to a low point at z -1.5 inside the floor, along the floor, up the funnel and through the wall to an inlet stub
# on the outside (x 130, z 36, 6.75 mm socket). The lid diffuser (tools/build_lid_diffuser.py) replaces it.
#
# Method: cut the source solid with a half-plane through the axis at an angle the argon path and the pockets do not
# reach, revolve that profile 360 deg, and cut the four pockets again. Wall, floor and funnel thickness where the rib
# was are then those of the rest of the basin, and the inner surface is the bowl's own surface of revolution.
#
# The source is the STEP as committed in SOURCE_COMMIT, read through git, so a rerun gives the same result whatever is
# in the working tree. The SLDPRT is not touched and still carries the channel.
#
# Run with FreeCAD's console:  freecadcmd tools/build_basin_no_argon.py
# If that prints nothing (seen with FreeCAD 1.1 on Windows, where the file is imported and its errors are swallowed):
#   freecadcmd -c "import runpy; runpy.run_path(r'<full path>	oolsuild_basin_no_argon.py', run_name='__main__')"
# Writes CAD/Spincoater/242mmCatchBasinSpincoater.STEP (overwrites it), _Checks.txt and _Sections.png beside it. It
# refuses to write anything when a check fails.
#
# Units mm, frame as in the source STEP: z up, z 0 at the bowl's flat floor, the basin's axis on z.

import math
import os
import subprocess
import tempfile

import FreeCAD
import Part

V = FreeCAD.Vector
Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
OutDir = os.path.join(Root, "CAD", "Spincoater")
Stem = "242mmCatchBasinSpincoater"
SourceCommit = "4fa124f44656ea344c2ba78a3b81843e2efe2ff3"   # the commit that added the basin
SourcePath = "CAD/Spincoater/242mmCatchBasinSpincoater.STEP"

ProfileAngleDeg = 225.0          # half-plane for the profile: clear of the argon path (13..90 deg) and the pockets
CheckAnglesDeg = (135.0, 200.0, 250.0, 315.0)   # further clear half-planes; their sections must match the profile
PocketR, PocketDepth, PocketRingR = 5.0, 2.5, 65.0
PocketAnglesDeg = (0.0, 90.0, 180.0, 270.0)
# Box that holds the whole argon path (rib, bore, boss, stub, their blends). Every difference between the source and
# the result must lie inside it.
ArgonBox = FreeCAD.BoundBox(-1.0, 28.0, -6.0, 131.0, 57.0, 50.0)
SliverVol = 1e-3                 # mm^3: Boolean slivers below this are reported, not judged
BoreRadii = (2.5, 3.375)         # bore and inlet socket
Tol = 1e-6

Log = []


def Say(Text):
    Log.append(Text)
    print(Text)


def ReadSource():
    Blob = subprocess.run(["git", "show", "%s:%s" % (SourceCommit, SourcePath)], cwd=Root,
                          capture_output=True, check=True).stdout
    Fd, TmpPath = tempfile.mkstemp(suffix=".step")
    with os.fdopen(Fd, "wb") as F:
        F.write(Blob)
    try:
        Shape = Part.read(TmpPath)
    finally:
        os.remove(TmpPath)
    return Shape


def HalfPlane(AngleDeg, Reach=300.0, ZLo=-50.0, ZHi=200.0):
    A = math.radians(AngleDeg)
    D = V(math.cos(A), math.sin(A), 0)
    return Part.Face(Part.makePolygon([V(0, 0, ZLo), D * Reach + V(0, 0, ZLo), D * Reach + V(0, 0, ZHi),
                                       V(0, 0, ZHi), V(0, 0, ZLo)]))


def PlaneY(Y, XLo=-200.0, XHi=200.0, ZLo=-50.0, ZHi=200.0):
    return Part.Face(Part.makePolygon([V(XLo, Y, ZLo), V(XHi, Y, ZLo), V(XHi, Y, ZHi), V(XLo, Y, ZHi),
                                       V(XLo, Y, ZLo)]))


def Profile(Solid, AngleDeg):
    Faces = Solid.common(HalfPlane(AngleDeg)).Faces
    if len(Faces) != 1:
        raise RuntimeError("section at %.0f deg gives %d faces, expected 1" % (AngleDeg, len(Faces)))
    return Faces[0]


def Rebuild(Source):
    Prof = Profile(Source, ProfileAngleDeg)
    Body = Prof.revolve(V(0, 0, 0), V(0, 0, 1), 360.0)
    Body = Part.Solid(Part.Shell(Body.Faces)) if Body.ShapeType != "Solid" else Body
    Pockets = []
    for A in PocketAnglesDeg:
        R = math.radians(A)
        Base = V(PocketRingR * math.cos(R), PocketRingR * math.sin(R), Source.BoundBox.ZMin)
        Pockets.append(Part.makeCylinder(PocketR, PocketDepth, Base, V(0, 0, 1)))
    New = Body.cut(Part.makeCompound(Pockets)).removeSplitter()
    return Prof, New


def BoreCentreline(Source):
    # Each bore face is half a tube, split on the plane y 43 through its centreline, so the two ends of its "around"
    # parameter are diametrically opposite and their midpoint lies on the centreline.
    Pts = []
    for F in Source.Faces:
        S = F.Surface
        B = F.BoundBox
        if B.YMin < 39.0 or B.YMax > 47.0 or B.XMin < -0.1:
            continue
        Kind = type(S).__name__
        if Kind == "Cylinder" and min(abs(S.Radius - R) for R in BoreRadii) < 1e-3:
            pass
        elif Kind == "Toroid" and abs(S.MinorRadius - BoreRadii[0]) < 1e-3:
            pass
        elif Kind == "Cone" and B.XMax <= 2.01:
            pass
        else:
            continue
        U0, U1, V0, V1 = F.ParameterRange
        if abs((U1 - U0) - math.pi) < 1e-3:
            Ends = lambda T: (F.valueAt(U0, T), F.valueAt(U1, T))
            Lo, Hi = V0, V1
        elif abs((V1 - V0) - math.pi) < 1e-3:
            Ends = lambda T: (F.valueAt(T, V0), F.valueAt(T, V1))
            Lo, Hi = U0, U1
        else:
            continue
        for I in range(9):
            T = Lo + (Hi - Lo) * (I + 0.5) / 9.0
            P, Q = Ends(T)
            Pts.append((P + Q) * 0.5)
    return Pts


def ProbeLine(Solid, P0, P1):
    Hits = Solid.common(Part.makeLine(P0, P1)).Edges
    Spans = sorted((min(E.Vertexes[0].Point.sub(P0).Length, E.Vertexes[-1].Point.sub(P0).Length), E.Length)
                   for E in Hits)
    return ", ".join("%.2f+%.2f" % S for S in Spans) if Spans else "none"


def IsRevolutionFace(F):
    S = F.Surface
    Kind = type(S).__name__
    if Kind == "Plane":
        return abs(abs(S.Axis.z) - 1.0) < 1e-6
    if Kind in ("Cylinder", "Cone", "Toroid", "Sphere", "SurfaceOfRevolution"):
        Ax = S.Direction if Kind == "SurfaceOfRevolution" else (S.Axis if Kind != "Sphere" else V(0, 0, 1))
        C = S.Location if Kind == "SurfaceOfRevolution" else S.Center
        return abs(abs(Ax.z) - 1.0) < 1e-6 and math.hypot(C.x, C.y) < 1e-6
    return False


def IsPocketFace(F):
    S = F.Surface
    if type(S).__name__ != "Cylinder" or abs(S.Radius - PocketR) > 1e-6 or abs(abs(S.Axis.z) - 1) > 1e-6:
        return False
    return abs(math.hypot(S.Center.x, S.Center.y) - PocketRingR) < 1e-6


def Diff(A, B):
    Big, Slivers = [], []
    for S in A.cut(B).Solids:
        (Big if S.Volume >= SliverVol else Slivers).append(S)
    return Big, Slivers


def Check(Source, Prof, New):
    Bad = []

    def Judge(Ok, Text):
        Say("  [%s] %s" % ("ok" if Ok else "FAIL", Text))
        if not Ok:
            Bad.append(Text)

    Say("Source: %s at %s" % (SourcePath, SourceCommit[:10]))
    Say("  %d solid(s), %d shell(s), %d faces, volume %.1f mm^3, box x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f" % (
        len(Source.Solids), len(Source.Shells), len(Source.Faces), Source.Volume, Source.BoundBox.XMin,
        Source.BoundBox.XMax, Source.BoundBox.YMin, Source.BoundBox.YMax, Source.BoundBox.ZMin, Source.BoundBox.ZMax))
    Say("Result: %d solid(s), %d shell(s), %d faces, volume %.1f mm^3, box x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f" % (
        len(New.Solids), len(New.Shells), len(New.Faces), New.Volume, New.BoundBox.XMin, New.BoundBox.XMax,
        New.BoundBox.YMin, New.BoundBox.YMax, New.BoundBox.ZMin, New.BoundBox.ZMax))
    Say("Checks")
    Judge(len(New.Solids) == 1 and New.isValid() and New.Solids[0].isClosed(), "one valid closed solid")
    Judge(len(New.Shells) == 1, "one shell, so no internal void anywhere")

    # The basin outside the argon path is a body of revolution: other clear half-planes, turned onto the profile's
    # half-plane, give the same section (symmetric difference of the two faces).
    for A in CheckAnglesDeg:
        Other = Profile(Source, A).copy()
        Other.rotate(V(0, 0, 0), V(0, 0, 1), ProfileAngleDeg - A)
        XorArea = Other.cut(Prof).Area + Prof.cut(Other).Area
        Judge(XorArea < 1e-3 * Prof.Area, "source section at %.0f deg turned onto the profile at %.0f deg: "
              "differs by %.4f mm^2 of %.3f mm^2" % (A, ProfileAngleDeg, XorArea, Prof.Area))

    # Everything that changed lies in the argon box.
    Removed, RemovedSliv = Diff(Source, New)
    Added, AddedSliv = Diff(New, Source)
    RemVol = sum(S.Volume for S in Removed)
    AddVol = sum(S.Volume for S in Added)
    Say("  removed (source minus result): %d solid(s), %.1f mm^3; added (result minus source): %d solid(s), %.1f mm^3"
        % (len(Removed), RemVol, len(Added), AddVol))
    Say("  slivers below %.0e mm^3: %d removed, %d added" % (SliverVol, len(RemovedSliv), len(AddedSliv)))
    Outside = [S for S in Removed + Added if not ArgonBox.isInside(S.optimalBoundingBox())]
    Judge(not Outside, "every difference lies inside the argon path's box x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f" % (
        ArgonBox.XMin, ArgonBox.XMax, ArgonBox.YMin, ArgonBox.YMax, ArgonBox.ZMin, ArgonBox.ZMax))
    # Cross-check of the Boolean volumes: the cuts against source minus common and result minus common. They differ
    # by a few mm^3 where the result's surfaces coincide with the source's; allow 0.1 % of the removed volume.
    Common = Source.common(New).Volume
    Allow = 1e-3 * (Source.Volume - Common)
    Judge(abs(Source.Volume - Common - RemVol) < Allow and abs(New.Volume - Common - AddVol) < Allow,
          "volumes: source %.1f - removed %.1f + added %.1f = %.1f, result %.1f; by common: removed %.1f, added %.1f "
          "(agree within %.1f mm^3)" % (Source.Volume, RemVol, AddVol, Source.Volume - RemVol + AddVol, New.Volume,
                                        Source.Volume - Common, New.Volume - Common, Allow))

    # Centreline of the old bore: void in the source, material in the result.
    Pts = BoreCentreline(Source)
    Len = 0.0
    Order = sorted(Pts, key=lambda P: P.x)
    for P, Q in zip(Order, Order[1:]):
        Len += P.sub(Q).Length
    Say("  bore centreline: %d probe points, x %.2f..%.2f, z %.2f..%.2f, y %.3f..%.3f, polyline length about %.0f mm"
        % (len(Pts), min(P.x for P in Pts), max(P.x for P in Pts), min(P.z for P in Pts), max(P.z for P in Pts),
           min(P.y for P in Pts), max(P.y for P in Pts), Len))
    Judge(len(Pts) >= 60 and max(abs(P.y - 43.0) for P in Pts) < 1e-3, "probe points found, all on the plane y 43")
    InSource = sum(1 for P in Pts if Source.isInside(P, Tol, True))
    Judge(InSource == 0, "source: %d of %d probe points in material (the bore is void there)" % (InSource, len(Pts)))
    InNew = sum(1 for P in Pts if New.isInside(P, Tol, True))
    InStub = sum(1 for P in Pts if math.hypot(P.x, P.y) > 126.0 and not New.isInside(P, Tol, True))
    Say("  result: %d probe points in material, %d in the air beyond the wall (where the stub was), %d in the open "
        "bowl (where the rib stood above the floor and funnel)" % (InNew, InStub, len(Pts) - InNew - InStub))
    Judge(InNew > 0, "the old bore is filled where it ran inside the floor and the wall")
    Say("  bore volume for comparison: pi x 2.5^2 x %.0f mm = %.0f mm^3; the added %.1f mm^3 is the part of it inside "
        "the floor and wall" % (Len, math.pi * BoreRadii[0] ** 2 * Len, AddVol))

    # Surfaces: only surfaces of revolution about z, flat faces normal to z and the four pocket walls.
    Odd = [F for F in New.Faces if not (IsRevolutionFace(F) or IsPocketFace(F))]
    Judge(not Odd, "no face other than surfaces of revolution about z and the pockets (%d odd)" % len(Odd))
    Judge(sum(1 for F in New.Faces if IsPocketFace(F)) == len(PocketAnglesDeg), "four pocket walls kept")
    StubPts = [P for P in Pts if P.x > 118.0]
    Judge(StubPts and not any(New.isInside(P, Tol, True) for P in StubPts if math.hypot(P.x, P.y) > 126.0),
          "outer surface: no stub (%d bore probe points beyond r 126 are all in open air)" % sum(
              1 for P in StubPts if math.hypot(P.x, P.y) > 126.0))

    # Thickness where the rib was: material spans along lines through the argon path in the result must equal those
    # of the source along the same lines turned 180 deg about z, where the source has no rib (193..270 deg).
    Say("Line probes, start + length of each material span along the line (source | result | source turned 180 deg):")
    for Name, P0, P1 in (("floor, vertical at x 41.8", V(41.8, 43, -20), V(41.8, 43, 60)),
                         ("floor, vertical at x 60", V(60, 43, -20), V(60, 43, 60)),
                         ("funnel, vertical at x 90", V(90, 43, -20), V(90, 43, 60)),
                         ("outlet boss axis, horizontal at z 18.4", V(-10, 43, 18.4), V(40, 43, 18.4)),
                         ("wall at the stub, horizontal at z 35.98", V(100, 43, 35.98), V(140, 43, 35.98))):
        Q0, Q1 = V(-P0.x, -P0.y, P0.z), V(-P1.x, -P1.y, P1.z)
        Res, Ref = ProbeLine(New, P0, P1), ProbeLine(Source, Q0, Q1)
        Say("  %s: %s | %s | %s" % (Name, ProbeLine(Source, P0, P1), Res, Ref))
        Judge(Res == Ref, "%s: result matches the source turned 180 deg (%s)" % (
            Name, "no material on this line in either" if Res == "none" else "same spans"))
    return Bad, Removed, Added


def Sections(Source, New, Removed, Added, Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    # Paul Tol bright: blue material, red removed, green added
    Mat, Rem, Add, Edge = "#4477AA", "#EE6677", "#228833", "#222222"

    def Draw(Ax, Shape, Y, Fc, Ec, Lw=0.5, Ls="-", Fill=True):
        for F in Shape.common(PlaneY(Y)).Faces:
            for I, W in enumerate([F.OuterWire] + [W for W in F.Wires if not W.isSame(F.OuterWire)]):
                Pts = [(P.x, P.z) for P in W.discretize(Deflection=0.02)]
                Face = (Fc if I == 0 else "white") if Fill else "none"
                Ax.add_patch(Polygon(Pts, closed=True, fc=Face, ec=Ec, lw=Lw, ls=Ls))

    Fig, Axes = plt.subplots(2, 2, figsize=(20, 9.5))
    RemC, AddC = Part.makeCompound(Removed), Part.makeCompound(Added)
    for Row, Y in enumerate((0.0, 43.0)):
        for Col, (Title, Shape) in enumerate((("source (argon channel)", Source), ("result (no channel)", New))):
            Ax = Axes[Row][Col]
            Draw(Ax, Shape, Y, Mat, Edge)
            if Col == 1:
                Draw(Ax, AddC, Y, Add, Add, Lw=0.6)
                Draw(Ax, RemC, Y, Rem, Rem, Lw=1.0, Ls="--", Fill=False)
            Ax.set_xlim(-133, 133)
            Ax.set_ylim(-10, 100)
            Ax.set_aspect("equal")
            Ax.grid(True, lw=0.3)
            Ax.set_xlabel("x (mm)")
            Ax.set_ylabel("z (mm)")
            Ax.set_title("%s, section y = %.0f" % (Title, Y), fontsize=10)
    Fig.suptitle("%s (issue 251): blue material; in the result, green = filled bore, red dashed = removed rib, boss "
                 "and stub" % Stem, fontsize=11)
    Fig.tight_layout()
    Fig.savefig(Path, dpi=150)
    plt.close(Fig)


def Main():
    Source = ReadSource()
    if len(Source.Solids) != 1:
        raise SystemExit("source has %d solids, expected 1" % len(Source.Solids))
    Source = Source.Solids[0]
    Prof, New = Rebuild(Source)
    Say("%s: argon channel removed (issue 251); profile from the half-plane at %.0f deg, revolved 360 deg, "
        "%d pockets %.0f x %.1f at r %.0f cut again" % (Stem, ProfileAngleDeg, len(PocketAnglesDeg), 2 * PocketR,
                                                        PocketDepth, PocketRingR))
    Bad, Removed, Added = Check(Source, Prof, New)
    if Bad:
        raise SystemExit("basin checks failed: %s" % "; ".join(Bad))
    StepPath = os.path.join(OutDir, Stem + ".STEP")
    Fd, TmpStep = tempfile.mkstemp(suffix=".step")
    os.close(Fd)
    Doc = FreeCAD.newDocument("Basin")
    Obj = Doc.addObject("Part::Feature", Stem)
    Obj.Shape = New
    Obj.Label = Stem
    import Import
    Import.export([Obj], TmpStep)
    FreeCAD.closeDocument(Doc.Name)
    Back = Part.read(TmpStep)
    if len(Back.Solids) != 1 or not Back.isValid() or abs(Back.Volume - New.Volume) > 1e-4 * New.Volume:
        os.remove(TmpStep)
        raise SystemExit("the STEP round trip changed the solid; nothing written")
    os.replace(TmpStep, StepPath)
    Say("STEP round trip: 1 solid, volume %.1f mm^3" % Back.Volume)
    Sections(Source, New, Removed, Added, os.path.join(OutDir, Stem + "_Sections.png"))
    with open(os.path.join(OutDir, Stem + "_Checks.txt"), "w", newline="\n") as F:
        F.write("\n".join(Log) + "\n")
    print("Saved to", OutDir)


Main()
