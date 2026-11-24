"""Draw the concept sketch of the UV lid's argon diffuser (issue #251).

Writes docs/spincoater/lid_diffuser_sketch.svg: a section through the axis and
a view from below of a two-part FFF ASA diffuser that sits in the free centre
position of the lid's 8-LED acrylic plate. It is a concept sketch, not a shop
drawing: values marked "assumed" wait for measurements.

Run:   python tools/draw_lid_diffuser.py
PNG:   render the SVG with headless Edge, for example
       msedge --headless=new --disable-gpu --hide-scrollbars
              --window-size=1485,1050 --screenshot=<png> <svg as a file:/// URL>
"""

import math
import os

# ---------------------------------------------------------------- parameters
# All lengths in mm. z = 0 is the underside of the LED plate, z grows upward.
PlateThick = 3.0          # LED plate (1/8 in acrylic), assumed
PlateHoleR = 22.5         # centre hole in the LED plate, enlarged to fit
PlateDrawR = 38.0         # how much of the LED plate the section shows
BodyR = 22.0              # cup outer radius below the flange
CavityR = 17.0            # plenum radius
FlangeR = 30.0            # flange resting on the plate's top face
FlangeThick = 3.0
BossR = 8.0               # boss for the push-in fitting
BossTop = 14.0
TapR = 4.5                # M10 x 1 tap drill 9.0 mm
TapDepth = 6.0
InletR = 1.25             # 2.5 mm inlet bore into the plenum
RoofZ = 4.0               # plenum roof
CupBottomZ = -2.0         # cup's open face, where the face plate seats
FaceThick = 2.0           # face plate
FaceBottomZ = CupBottomZ - FaceThick
BaffleR = 7.0
BaffleGap = 1.0           # roof to baffle top
BaffleThick = 1.2
PostR = 1.0               # three posts on the face plate carry the baffle
PostPcdR = 5.0
HoleD = 1.0               # face holes, drilled to 1.0 after printing
HolePitch = 4.0           # hexagonal pattern
HoleFieldR = 15.0
ScrewPcdR = 19.5          # 3 x M2 countersunk, face plate to cup
FlangeScrewPcdR = 26.0    # 3 x M3 through flange and LED plate, nuts below
GapToSubstrate = 15.0     # face to substrate, assumed

ArgonDensity = 1.66       # kg/m^3 at 20 C, 1 atm
HoleCd = 0.6              # discharge coefficient of a short printed hole, assumed
FlowsLpm = (2.0, 5.0)

Dia = chr(216)            # diameter sign, kept out of the source as a literal

# Paul Tol schemes: light for fills, bright for lines and labels
FillCup = "#77AADD"
FillFace = "#44BB99"
FillPlate = "#DDDDDD"
FillFitting = "#EEDD88"
FillScrew = "#BBBBBB"
LineFlow = "#AA3377"
LineDim = "#4477AA"
LineInk = "#222222"
LineHidden = "#555555"

BaffleTopZ = RoofZ - BaffleGap
BaffleBottomZ = BaffleTopZ - BaffleThick
PostAngles = (0.0, 120.0, 240.0)
ScrewAngles = (60.0, 180.0, 300.0)
FlangeScrewAngles = (0.0, 120.0, 240.0)
SubstrateZ = FaceBottomZ - GapToSubstrate


# ---------------------------------------------------------------- geometry
def PolarXY(R, AngleDeg):
    A = math.radians(AngleDeg)
    return R * math.cos(A), R * math.sin(A)


def FaceHoles():
    """Hole centres (x, y) of the hexagonal field, clear of the posts."""
    Holes = []
    RowStep = HolePitch * math.sqrt(3.0) / 2.0
    Rows = int(HoleFieldR / RowStep) + 1
    Cols = int(HoleFieldR / HolePitch) + 2
    for Row in range(-Rows, Rows + 1):
        Y = Row * RowStep
        Offset = (HolePitch / 2.0) if (Row % 2) else 0.0
        for Col in range(-Cols, Cols + 1):
            X = Col * HolePitch + Offset
            if math.hypot(X, Y) > HoleFieldR:
                continue
            Clear = True
            for A in PostAngles:
                Px, Py = PolarXY(PostPcdR, A)
                if math.hypot(X - Px, Y - Py) < PostR + HoleD / 2.0 + 1.0:
                    Clear = False
            if Clear:
                Holes.append((X, Y))
    return Holes


def FlowNumbers(Holes):
    """Velocities (m/s) and pressures (Pa) at each flow."""
    Out = []
    HoleArea = len(Holes) * math.pi * (HoleD / 2000.0) ** 2
    FieldArea = math.pi * (HoleFieldR / 1000.0) ** 2
    InletArea = math.pi * (InletR / 1000.0) ** 2
    BaffleExitArea = 2.0 * math.pi * (BaffleR / 1000.0) * (BaffleGap / 1000.0)
    for Lpm in FlowsLpm:
        Q = Lpm / 60000.0
        VHole = Q / HoleArea
        VBaffle = Q / BaffleExitArea
        Out.append({
            "Lpm": Lpm,
            "VInlet": Q / InletArea,
            "VFace": Q / FieldArea,
            "VHole": VHole,
            "DpHole": 0.5 * ArgonDensity * VHole ** 2 / HoleCd ** 2,
            "PBaffle": 0.5 * ArgonDensity * VBaffle ** 2,
        })
    return Out


# ---------------------------------------------------------------- svg
class Sheet:
    def __init__(self, WidthMm, HeightMm, PxPerMm):
        self.W = WidthMm
        self.H = HeightMm
        self.Px = PxPerMm
        self.Items = []

    def Add(self, Text):
        self.Items.append(Text)

    def Poly(self, Pts, Fill, Stroke=LineInk, Width=0.25, Dash=None):
        P = " ".join("%.3f,%.3f" % (X, Y) for X, Y in Pts)
        D = (' stroke-dasharray="%s"' % Dash) if Dash else ""
        self.Add('<polygon points="%s" fill="%s" stroke="%s" stroke-width="%.2f"%s/>' % (P, Fill, Stroke, Width, D))

    def Line(self, X1, Y1, X2, Y2, Stroke=LineInk, Width=0.25, Dash=None):
        D = (' stroke-dasharray="%s"' % Dash) if Dash else ""
        self.Add('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="%s" stroke-width="%.2f"%s/>'
                 % (X1, Y1, X2, Y2, Stroke, Width, D))

    def PolyLine(self, Pts, Stroke, Width=0.4, Arrow=False):
        P = " ".join("%.3f,%.3f" % (X, Y) for X, Y in Pts)
        M = ' marker-end="url(#flow)"' if Arrow else ""
        self.Add('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.2f"%s/>' % (P, Stroke, Width, M))

    def Circle(self, X, Y, R, Fill="none", Stroke=LineInk, Width=0.25, Dash=None):
        D = (' stroke-dasharray="%s"' % Dash) if Dash else ""
        self.Add('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="%s" stroke="%s" stroke-width="%.2f"%s/>'
                 % (X, Y, R, Fill, Stroke, Width, D))

    def Text(self, X, Y, S, Size=2.8, Anchor="start", Fill=LineInk, Weight="normal"):
        S = S.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.Add('<text x="%.3f" y="%.3f" font-size="%.2f" text-anchor="%s" fill="%s" font-weight="%s">%s</text>'
                 % (X, Y, Size, Anchor, Fill, Weight, S))

    def Arrowheads(self, X1, Y1, X2, Y2):
        for Xa, Ya, Xb, Yb in ((X1, Y1, X2, Y2), (X2, Y2, X1, Y1)):
            L = math.hypot(Xb - Xa, Yb - Ya)
            Ux, Uy = (Xb - Xa) / L, (Yb - Ya) / L
            Nx, Ny = -Uy, Ux
            self.Poly([(Xa, Ya), (Xa + Ux * 1.6 + Nx * 0.5, Ya + Uy * 1.6 + Ny * 0.5),
                       (Xa + Ux * 1.6 - Nx * 0.5, Ya + Uy * 1.6 - Ny * 0.5)], LineDim, LineDim, 0.1)

    def DimH(self, X1, X2, YRef, YDim, Label):
        Ext = 0.8 if YDim > YRef else -0.8
        self.Line(X1, YRef, X1, YDim + Ext, LineDim, 0.18)
        self.Line(X2, YRef, X2, YDim + Ext, LineDim, 0.18)
        self.Line(X1, YDim, X2, YDim, LineDim, 0.18)
        self.Arrowheads(X1, YDim, X2, YDim)
        self.Text((X1 + X2) / 2.0, YDim - 0.8, Label, 2.5, "middle", LineDim)

    def DimV(self, Y1, Y2, XRef, XDim, Label, Side):
        Ext = 0.8 if XDim > XRef else -0.8
        self.Line(XRef, Y1, XDim + Ext, Y1, LineDim, 0.18)
        self.Line(XRef, Y2, XDim + Ext, Y2, LineDim, 0.18)
        self.Line(XDim, Y1, XDim, Y2, LineDim, 0.18)
        self.Arrowheads(XDim, Y1, XDim, Y2)
        if Side == "right":
            self.Text(XDim + 1.2, (Y1 + Y2) / 2.0 + 0.9, Label, 2.5, "start", LineDim)
        else:
            self.Text(XDim - 1.2, (Y1 + Y2) / 2.0 + 0.9, Label, 2.5, "end", LineDim)

    def Balloon(self, Tx, Ty, Bx, By, Number):
        L = math.hypot(Tx - Bx, Ty - By)
        R = 2.4
        Ex, Ey = Bx + (Tx - Bx) / L * R, By + (Ty - By) / L * R
        self.Line(Ex, Ey, Tx, Ty, LineInk, 0.18)
        self.Circle(Tx, Ty, 0.45, LineInk, LineInk, 0.1)
        self.Circle(Bx, By, R, "#FFFFFF", LineInk, 0.25)
        self.Text(Bx, By + 1.05, str(Number), 2.9, "middle", LineInk, "bold")

    def Svg(self):
        Head = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %g %g" '
                'font-family="Arial, Helvetica, sans-serif">\n' % (self.W * self.Px, self.H * self.Px, self.W, self.H))
        Defs = ('<defs><marker id="flow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" '
                'orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="%s"/></marker></defs>\n' % LineFlow)
        Bg = '<rect x="0" y="0" width="%g" height="%g" fill="#FFFFFF"/>\n' % (self.W, self.H)
        return Head + Defs + Bg + "\n".join(self.Items) + "\n</svg>\n"


# ---------------------------------------------------------------- views
CALLOUTS = [
    "PTFE tube 4 x 2, argon in",
    "PC4-M10 push-in fitting (M10 x 1; check the fitting)",
    "M10 x 1 tapped 6 deep, " + Dia + "2.5 inlet to the plenum",
    "Cup, ASA by FFF, printed boss up; plenum " + Dia + "34 x 6",
    "Baffle " + Dia + "14 on 3 posts " + Dia + "2, 1.0 below the roof",
    "3 x M2 countersunk: the face plate comes off for cleaning",
    "Face plate, ASA, " + Dia + "1 holes drilled after printing",
    "3 x M3 on " + Dia + "52, nuts under the LED plate",
    "LED plate, acrylic t 3 (assumed), centre hole opened to " + Dia + "45",
]


def DrawSection(Sh, Cx, Cy, Scale):
    """Section through the axis in the x-z plane. Sheet y grows downward."""

    def P(X, Z):
        return (Cx + X * Scale, Cy - Z * Scale)

    def Mirror(Pts, Side):
        return [P(Side * R, Z) for R, Z in Pts]

    for Side in (-1, 1):
        Sh.Poly(Mirror([(PlateHoleR, 0.0), (PlateDrawR, 0.0), (PlateDrawR, PlateThick), (PlateHoleR, PlateThick)], Side), FillPlate)

    CupRight = [(TapR, BossTop), (BossR, BossTop), (BossR, PlateThick + FlangeThick),
                (FlangeR, PlateThick + FlangeThick), (FlangeR, PlateThick), (BodyR, PlateThick),
                (BodyR, CupBottomZ), (CavityR, CupBottomZ), (CavityR, RoofZ), (InletR, RoofZ),
                (InletR, BossTop - TapDepth), (TapR, BossTop - TapDepth)]
    for Side in (-1, 1):
        Sh.Poly(Mirror(CupRight, Side), FillCup)

    # Face plate, cut through the hole row on the x axis
    Cuts = sorted(X for X, Y in FaceHoles() if abs(Y) < 1e-6)
    Edges = [-BodyR]
    for X in Cuts:
        Edges += [X - HoleD / 2.0, X + HoleD / 2.0]
    Edges.append(BodyR)
    for I in range(0, len(Edges), 2):
        Sh.Poly([P(Edges[I], FaceBottomZ), P(Edges[I + 1], FaceBottomZ),
                 P(Edges[I + 1], CupBottomZ), P(Edges[I], CupBottomZ)], FillFace)

    # Post at 0 deg and the baffle
    Sh.Poly([P(PostPcdR - PostR, CupBottomZ), P(PostPcdR + PostR, CupBottomZ),
             P(PostPcdR + PostR, BaffleBottomZ), P(PostPcdR - PostR, BaffleBottomZ)], FillFace)
    Sh.Poly([P(-BaffleR, BaffleBottomZ), P(BaffleR, BaffleBottomZ), P(BaffleR, BaffleTopZ), P(-BaffleR, BaffleTopZ)], FillFace)

    # M2 countersunk screw at 180 deg
    Sx = -ScrewPcdR
    Sh.Poly([P(Sx - 1.9, FaceBottomZ), P(Sx + 1.9, FaceBottomZ), P(Sx + 1.0, FaceBottomZ + 1.0),
             P(Sx + 1.0, FaceBottomZ + 6.0), P(Sx - 1.0, FaceBottomZ + 6.0), P(Sx - 1.0, FaceBottomZ + 1.0)], FillScrew)

    # M3 screw and nut at 0 deg
    Fx = FlangeScrewPcdR
    Top = PlateThick + FlangeThick
    Sh.Poly([P(Fx - 2.75, Top), P(Fx + 2.75, Top), P(Fx + 2.75, Top + 2.0), P(Fx - 2.75, Top + 2.0)], FillScrew)
    Sh.Poly([P(Fx - 1.5, -2.4), P(Fx + 1.5, -2.4), P(Fx + 1.5, Top), P(Fx - 1.5, Top)], FillScrew)
    Sh.Poly([P(Fx - 2.75, -2.4), P(Fx + 2.75, -2.4), P(Fx + 2.75, 0.0), P(Fx - 2.75, 0.0)], FillScrew)

    # Push-in fitting (schematic) and PTFE tube
    Sh.Poly([P(-4.9, BossTop - TapDepth), P(4.9, BossTop - TapDepth), P(4.9, BossTop), P(-4.9, BossTop)],
            FillFitting, LineHidden, 0.2, "0.8,0.5")
    Sh.Poly([P(-6.0, BossTop), P(6.0, BossTop), P(6.0, BossTop + 6.0), P(-6.0, BossTop + 6.0)], FillFitting)
    Sh.Poly([P(-4.5, BossTop + 6.0), P(4.5, BossTop + 6.0), P(4.5, BossTop + 9.0), P(-4.5, BossTop + 9.0)], FillFitting)
    Sh.Poly([P(-2.0, BossTop + 9.0), P(2.0, BossTop + 9.0), P(2.0, BossTop + 19.0), P(-2.0, BossTop + 19.0)], "#FFFFFF")
    for X in (-1.0, 1.0):
        Sh.Line(*P(X, BossTop + 9.0), *P(X, BossTop + 19.0), LineHidden, 0.15, "0.6,0.4")

    # Substrate
    Sh.Line(*P(-PlateDrawR, SubstrateZ), *P(PlateDrawR, SubstrateZ), LineInk, 0.35, "2,1")
    Lx, Ly = P(-PlateDrawR, SubstrateZ)
    Sh.Text(Lx, Ly + 4.0, "substrate (up to about " + Dia + "220), wet film on top", 2.4)

    # Argon flow
    Sh.PolyLine([P(0, BossTop + 18.0), P(0, BaffleTopZ + 0.3)], LineFlow, 0.45, True)
    for Side in (-1, 1):
        Sh.PolyLine([P(Side * 1.5, RoofZ - BaffleGap / 2.0), P(Side * (BaffleR + 3.5), RoofZ - BaffleGap / 2.0),
                     P(Side * (BaffleR + 4.5), CupBottomZ + 0.6)], LineFlow, 0.4, True)
        for X in (8.0, 12.0):
            Sh.PolyLine([P(Side * X, FaceBottomZ - 0.4), P(Side * X, FaceBottomZ - 5.0)], LineFlow, 0.35, True)
        Sh.PolyLine([P(Side * 14.0, SubstrateZ + 1.2), P(Side * 34.0, SubstrateZ + 1.2)], LineFlow, 0.35, True)
    Tx, Ty = P(14.0, SubstrateZ + 1.2)
    Sh.Text(Tx, Ty - 1.3, "out over the edge to the lid gaps", 2.3, "start", LineFlow)

    # Callouts: (target r, z), (balloon r, z)
    Spots = [
        ((2.0, BossTop + 15.0), (-12.0, BossTop + 17.0)),
        ((-6.0, BossTop + 3.0), (-17.0, BossTop + 9.0)),
        ((-3.0, BossTop - 3.0), (-20.0, BossTop + 1.0)),
        ((-24.0, PlateThick + 2.0), (-36.0, 12.5)),
        ((-6.5, BaffleBottomZ + 0.6), (-36.0, 6.5)),
        ((-ScrewPcdR, FaceBottomZ + 0.5), (-30.0, -11.0)),
        ((-12.0, FaceBottomZ + 0.3), (-30.0, -16.0)),
        ((Fx + 2.0, Top + 1.5), (34.0, 12.0)),
        ((33.0, 1.5), (36.0, -6.0)),
    ]
    for I, ((Tr, Tz), (Br, Bz)) in enumerate(Spots):
        Tx, Ty = P(Tr, Tz)
        Bx, By = P(Br, Bz)
        Sh.Balloon(Tx, Ty, Bx, By, I + 1)

    # Dimensions
    Sh.DimH(*[Cx - FlangeR * Scale, Cx + FlangeR * Scale], Cy - Top * Scale, Cy - (BossTop + 22.0) * Scale, Dia + "60 flange")
    Sh.DimH(Cx - BodyR * Scale, Cx + BodyR * Scale, Cy - FaceBottomZ * Scale, Cy - (FaceBottomZ - 5.0) * Scale, Dia + "44 body")
    Xr = Cx + (PlateDrawR + 4.0) * Scale
    Sh.DimV(Cy - BossTop * Scale, Cy - FaceBottomZ * Scale, Cx + BossR * Scale, Xr, "%g" % (BossTop - FaceBottomZ), "right")
    Sh.DimV(Cy - FaceBottomZ * Scale, Cy - SubstrateZ * Scale, Cx + BodyR * Scale, Xr, "gap %g (assumed)" % GapToSubstrate, "right")
    Xl = Cx - (BodyR + 3.0) * Scale
    Sh.DimV(Cy, Cy - FaceBottomZ * Scale, Cx - BodyR * Scale, Xl, "%g" % (-FaceBottomZ), "left")
    Xc = Cx - (CavityR - 2.0) * Scale
    Sh.DimV(Cy - RoofZ * Scale, Cy - CupBottomZ * Scale, Cx - CavityR * Scale, Xc, "%g" % (RoofZ - CupBottomZ), "right")

    Tx, Ty = P(-PlateDrawR, 0.0)
    Sh.Text(Tx, 22.0, "SECTION THROUGH THE AXIS (scale 2:1)", 3.2, "start", LineInk, "bold")


def DrawBottom(Sh, Cx, Cy, Scale):
    """View from below, looking up at the face plate."""

    def P(X, Y):
        return (Cx + X * Scale, Cy + Y * Scale)

    Sh.Circle(*P(0, 0), FlangeR * Scale, "none", LineHidden, 0.2, "1,0.6")
    Sh.Circle(*P(0, 0), PlateHoleR * Scale, FillPlate, LineInk, 0.2)
    Sh.Circle(*P(0, 0), BodyR * Scale, FillFace, LineInk, 0.3)
    Sh.Circle(*P(0, 0), CavityR * Scale, "none", LineHidden, 0.18, "1,0.6")
    Sh.Circle(*P(0, 0), BaffleR * Scale, "none", LineHidden, 0.18, "1,0.6")
    for A in PostAngles:
        Sh.Circle(*P(*PolarXY(PostPcdR, A)), PostR * Scale, "none", LineHidden, 0.18, "0.6,0.4")
    Holes = FaceHoles()
    for X, Y in Holes:
        Sh.Circle(*P(X, Y), HoleD / 2.0 * Scale, "#FFFFFF", LineInk, 0.15)
    for A in ScrewAngles:
        X, Y = PolarXY(ScrewPcdR, A)
        Sh.Circle(*P(X, Y), 1.9 * Scale, FillScrew, LineInk, 0.2)
        Sh.Circle(*P(X, Y), 0.5 * Scale, "none", LineInk, 0.15)
    for A in FlangeScrewAngles:
        X, Y = PolarXY(FlangeScrewPcdR, A)
        Hx = [P(X + 2.75 / math.cos(math.radians(30)) * math.cos(math.radians(30 + 60 * K)),
                Y + 2.75 / math.cos(math.radians(30)) * math.sin(math.radians(30 + 60 * K))) for K in range(6)]
        Sh.Poly(Hx, FillScrew, LineInk, 0.2)
        Sh.Circle(*P(X, Y), 1.5 * Scale, "none", LineInk, 0.15)
    Sh.Text(Cx, Cy - (FlangeR + 8.0) * Scale, "VIEW FROM BELOW (scale 1.5:1)", 3.2, "middle", LineInk, "bold")
    Sh.Text(Cx, Cy + (FlangeR + 6.0) * Scale, "%d holes %s%g on a %g mm hex pitch inside %s%g"
            % (len(Holes), Dia, HoleD, HolePitch, Dia, 2 * HoleFieldR), 2.4, "middle")
    Sh.Text(Cx, Cy + (FlangeR + 6.0) * Scale + 3.5, "dashed: flange, plenum, baffle and posts (hidden)", 2.4, "middle", LineHidden)


def DrawLegend(Sh, X, Y):
    Sh.Text(X, Y, "CALLOUTS", 3.2, "start", LineInk, "bold")
    for I, S in enumerate(CALLOUTS):
        Sh.Text(X, Y + 5.0 + I * 4.0, "%d   %s" % (I + 1, S), 2.55)


def DrawNotes(Sh, X, Y):
    Holes = FaceHoles()
    Nums = FlowNumbers(Holes)
    Lines = [
        "1. Concept sketch, not a shop drawing. Assumed until measured: LED plate thickness, the lid-to-substrate gap,",
        "    the LED ring (keep the puck nearly flush so it shades no LED) and the push-in fitting's thread.",
        "2. Two ASA parts by FFF: the cup boss up, with support under the flange (8 mm overhang); the plenum roof bridges " + Dia + "34,",
        "    where sag is harmless. The face plate prints flat with its posts and baffle.",
        "    ASA is UV stable next to the 365 to 405 nm LEDs. Clean with IPA: acetone dissolves ASA.",
        "3. The baffle turns the inlet jet before the face, so the holes in line with the inlet do not take most of the flow.",
    ]
    N = 4
    for F in Nums:
        Lines.append("%d. At %g L/min: inlet %.1f m/s, each hole %.1f m/s, mean over the hole field %.0f mm/s;"
                     % (N, F["Lpm"], F["VInlet"], F["VHole"], F["VFace"] * 1000.0))
        Lines.append("    hole drop about %.0f Pa against %.1f Pa dynamic pressure at the baffle exit."
                     % (F["DpHole"], F["PBaffle"]))
        N += 1
    Lines.append("%d. If the face flows unevenly on the bench, lay a fine stainless mesh on the face plate inside the plenum."
                 % N)
    Lines.append("%d. Argon %g kg/m^3 (20 C, 1 atm); hole discharge coefficient %g assumed." % (N + 1, ArgonDensity, HoleCd))
    Sh.Text(X, Y, "NOTES", 3.2, "start", LineInk, "bold")
    for I, S in enumerate(Lines):
        Sh.Text(X, Y + 5.0 + I * 3.7, S, 2.45)
    return Holes, Nums


def Main():
    Here = os.path.dirname(os.path.abspath(__file__))
    OutDir = os.path.join(Here, "..", "docs", "spincoater")
    os.makedirs(OutDir, exist_ok=True)
    Sh = Sheet(297.0, 210.0, 5)
    Sh.Text(10.0, 11.0, "Spin coater UV lid: argon diffuser, concept (issue #251)", 5.0, "start", LineInk, "bold")
    DrawSection(Sh, 96.0, 102.0, 2.0)
    DrawBottom(Sh, 238.0, 72.0, 1.5)
    DrawLegend(Sh, 190.0, 139.0)
    Holes, Nums = DrawNotes(Sh, 10.0, 158.0)
    Path = os.path.join(OutDir, "lid_diffuser_sketch.svg")
    with open(Path, "w", newline="\n", encoding="ascii", errors="xmlcharrefreplace") as F:
        F.write(Sh.Svg())
    print("wrote", os.path.normpath(Path), "holes", len(Holes))
    for F in Nums:
        print("%g L/min: inlet %.1f m/s, hole %.2f m/s, face %.0f mm/s, hole dp %.1f Pa, baffle exit %.1f Pa"
              % (F["Lpm"], F["VInlet"], F["VHole"], F["VFace"] * 1000.0, F["DpHole"], F["PBaffle"]))


if __name__ == "__main__":
    Main()
