"""Draw the RMR control panel wiring diagrams as legal-size (14 x 8.5 in) SVG sheets.

Sheet 1: wiring schematic (every circuit on one page).
Sheets 2A and 2B: the same circuits on the lower and upper decks of the box, every part where sheet 3
puts it and every wire routed through the ducts and channels from terminal to terminal. Sheet 2C: what
each name means, and the terminal plan read from the same wire lists. Sheet 2D: the operator panel.
Sheet 3: packing study, two decks in a 2020 frame.
Sheet 4: the frame and its two deck plates; the plates, and the side and top panels on their nest
sheets, are also written as DXF for laser cutting.

Every wire is a polyline of horizontal and vertical segments only; Sheet.Wire()
refuses anything else. Colors are Paul Tol's vibrant scheme. Units are mm.

Usage: python tools/draw_wiring.py [out_dir]   (default docs/wiring)
"""

import csv
import io
import json
import math
import os
import sys
import textwrap

PageW = 355.6   # 14 in
PageH = 215.9   # 8.5 in

# Paul Tol vibrant
TolBlue = "#0077BB"
TolCyan = "#33BBEE"
TolTeal = "#009988"
TolOrange = "#EE7733"
TolRed = "#CC3311"
TolMagenta = "#EE3377"
TolGrey = "#BBBBBB"

Css = """
text{font-family:Arial,Helvetica,sans-serif;fill:#000}
path,line{fill:none;stroke-linecap:butt;stroke-linejoin:miter}
.ac{stroke:%(red)s;stroke-width:.6}
.va{stroke:%(blue)s;stroke-width:.5}
.ve{stroke:%(mag)s;stroke-width:.5}
.zp{stroke:#000;stroke-width:.55}
.zs{stroke:%(cyan)s;stroke-width:.5}
.pe{stroke:%(teal)s;stroke-width:.45;stroke-dasharray:2.4 .7 .5 .7}
.lv{stroke:%(orange)s;stroke-width:.42}
.sg{stroke:#000;stroke-width:.22}
.zl{stroke:#000;stroke-width:.3}
.cb{stroke:#000;stroke-width:.85}
.sgc{stroke:#000;stroke-width:.5}
.mo{stroke:#000;stroke-width:.3}
.un{stroke-dasharray:1.1 .8}
.mech{stroke:#000;stroke-width:.2;stroke-dasharray:.8 .6}
.sym{stroke:#000;stroke-width:.32;fill:none}
.symf{stroke:#000;stroke-width:.32;fill:#fff}
.bx{fill:#fff;stroke:#000;stroke-width:.3}
.bxl{fill:#fff;stroke:#000;stroke-width:.22}
.frame{fill:none;stroke:#000;stroke-width:.4}
.zone{fill:none;stroke:#888;stroke-width:.2;stroke-dasharray:1.5 1}
.rail{fill:#d9d9d9;stroke:#666;stroke-width:.2}
.duct{fill:#f3f3f3;stroke:#999;stroke-width:.2}
.dot{stroke:none}
""" % dict(red=TolRed, blue=TolBlue, mag=TolMagenta, cyan=TolCyan, teal=TolTeal, orange=TolOrange)

ClassColor = {"ac": TolRed, "va": TolBlue, "ve": TolMagenta, "zp": "#000", "zs": TolCyan,
              "pe": TolTeal, "lv": TolOrange, "sg": "#000", "mo": "#000",
              "zl": "#000", "cb": "#000", "sgc": "#000"}

# Mega pins as the breakout labels them (A0 = D54 ... A9 = D63). Source of truth is
# Marlin/src/pins/ramps/pins_RAMPS_14_RMR.h on top of pins_RAMPS.h; tools/check_wiring_pins.py
# compares these tables with those headers.
DriverPins = {  # drawn axis: (PUL+ = STEP, DIR+ = DIR, ENA+ = ENABLE)
    "X": ("A0", "A1", "38"), "Y1": ("A6", "A7", "A2"), "Y2": ("36", "34", "30"),
    "Z": ("46", "48", "A8"), "A": ("2", "9", "12"), "B": ("21", "22", "31"),
    "C": ("13", "19", "20")}
EndstopPins = [("X", "3"), ("Y", "14"), ("Z", "40"), ("A", "15"), ("B", "23"), ("C", "A9")]
OtherPins = {"servo gripper": "5", "servo lid": "6", "UV SSR": "4", "valve SSR": "42",
             "lid switch S5": "39", "motor power sense": "43", "ODrive TX2": "16",
             "ODrive RX2": "17"}


def Fmt(v):
    s = "%.2f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s != "-0" else "0"


def Esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Sheet:
    def __init__(self, title):
        self.Title = title
        self.Parts = []
        self.TextParts = []   # drawn last, so a haloed label sits on top of every wire
        self.CssExtra = ""

    def Add(self, s):
        self.Parts.append(s)

    def Wire(self, pts, cls, extra=""):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if abs(x1 - x2) > 1e-6 and abs(y1 - y2) > 1e-6:
                raise ValueError("diagonal segment %r -> %r" % ((x1, y1), (x2, y2)))
        d = "M" + " L".join("%s %s" % (Fmt(x), Fmt(y)) for x, y in pts)
        self.Add('<path class="%s" d="%s"%s/>' % (cls, d, extra))

    def Rect(self, x, y, w, h, cls="bx", rx=0.0):
        r = ' rx="%s"' % Fmt(rx) if rx else ""
        self.Add('<rect class="%s" x="%s" y="%s" width="%s" height="%s"%s/>'
                 % (cls, Fmt(x), Fmt(y), Fmt(w), Fmt(h), r))

    def FillRect(self, x, y, w, h, fill):
        self.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="none"/>'
                 % (Fmt(x), Fmt(y), Fmt(w), Fmt(h), fill))

    def Text(self, x, y, s, size=2.0, anchor="start", weight="normal", rot=0, fill=None,
             italic=False, mono=False, halo=False):
        attrs = 'x="%s" y="%s" font-size="%s"' % (Fmt(x), Fmt(y), Fmt(size))
        if halo:
            attrs += ' stroke="#fff" stroke-width="%s" paint-order="stroke"' % Fmt(size * 0.45)
        if anchor != "start":
            attrs += ' text-anchor="%s"' % anchor
        if weight != "normal":
            attrs += ' font-weight="%s"' % weight
        if italic:
            attrs += ' font-style="italic"'
        if mono:
            attrs += ' font-family="Consolas,\'Courier New\',monospace"'
        if fill:
            attrs += ' fill="%s"' % fill
        if rot:
            attrs += ' transform="rotate(%s %s %s)"' % (Fmt(rot), Fmt(x), Fmt(y))
        self.TextParts.append("<text %s>%s</text>" % (attrs, Esc(s)))

    def Lines(self, x, y, lines, size=2.0, lead=None, **kw):
        lead = lead or size * 1.22
        for i, s in enumerate(lines):
            self.Text(x, y + i * lead, s, size=size, **kw)

    def Dot(self, x, y, cls="zp", r=0.6):
        self.Add('<circle class="dot" cx="%s" cy="%s" r="%s" fill="%s"/>'
                 % (Fmt(x), Fmt(y), Fmt(r), ClassColor.get(cls, "#000")))

    def Circle(self, x, y, r, cls="symf"):
        self.Add('<circle class="%s" cx="%s" cy="%s" r="%s"/>' % (cls, Fmt(x), Fmt(y), Fmt(r)))

    def Svg(self):
        body = "\n".join(self.Parts + self.TextParts)
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" width="14in" height="8.5in" '
                'viewBox="0 0 %s %s">\n<title>%s</title>\n<style>%s</style>\n'
                '<rect x="0" y="0" width="%s" height="%s" fill="#fff"/>\n%s\n</svg>\n'
                % (Fmt(PageW), Fmt(PageH), Esc(self.Title), Css + self.CssExtra, Fmt(PageW), Fmt(PageH),
                   body))


# ---------------------------------------------------------------- symbols
# Symbols draw only their own body; the caller draws the wires up to them.

def FuseV(sh, x, yTop, yBot, cls):
    """Fuse on a vertical wire from yTop to yBot."""
    sh.Wire([(x, yTop), (x, yBot)], cls)
    ym = (yTop + yBot) / 2
    sh.Rect(x - 1.0, ym - 2.0, 2.0, 4.0, "symf")
    sh.Wire([(x, ym - 2.0), (x, ym + 2.0)], "sym")


def FuseH(sh, x0, x1, y, cls):
    sh.Wire([(x0, y), (x1, y)], cls)
    xm = (x0 + x1) / 2
    sh.Rect(xm - 2.0, y - 1.0, 4.0, 2.0, "symf")
    sh.Wire([(xm - 2.0, y), (xm + 2.0, y)], "sym")


def ContactV(sh, x, y, kind="NO", gap=1.8, w=3.2):
    """Contact on a vertical wire: the wire must stop at y and resume at y+gap."""
    sh.Wire([(x - w / 2, y), (x + w / 2, y)], "sym")
    sh.Wire([(x - w / 2, y + gap), (x + w / 2, y + gap)], "sym")
    if kind == "NC":
        sh.Wire([(x + w / 2 - 0.4, y), (x + w / 2 - 0.4, y + gap)], "sym")


def ContactH(sh, x, y, kind="NO", gap=1.8, h=3.2):
    """Contact on a horizontal wire: the wire must stop at x and resume at x+gap."""
    sh.Wire([(x, y - h / 2), (x, y + h / 2)], "sym")
    sh.Wire([(x + gap, y - h / 2), (x + gap, y + h / 2)], "sym")
    if kind == "NC":
        sh.Wire([(x, y - h / 2 + 0.4), (x + gap, y - h / 2 + 0.4)], "sym")


def ResistorH(sh, x0, x1, y, cls):
    sh.Wire([(x0, y), (x1, y)], cls)
    xm = (x0 + x1) / 2
    sh.Rect(xm - 2.4, y - 0.9, 4.8, 1.8, "symf")


def ResistorV(sh, x, y0, y1, cls):
    sh.Wire([(x, y0), (x, y1)], cls)
    ym = (y0 + y1) / 2
    sh.Rect(x - 0.9, ym - 2.4, 1.8, 4.8, "symf")


def CapV(sh, x, y, cls):
    """Capacitor on a vertical wire; wire must stop at y and resume at y+1.0."""
    sh.Wire([(x - 1.6, y), (x + 1.6, y)], "sym")
    sh.Wire([(x - 1.6, y + 1.0), (x + 1.6, y + 1.0)], "sym")


def DiodeV(sh, x, y0, y1, cathodeTop=True):
    """Diode body on a vertical wire, drawn like the part: a body with a cathode band."""
    sh.Wire([(x, y0), (x, y1)], "sg")
    ym = (y0 + y1) / 2
    sh.Rect(x - 0.9, ym - 2.0, 1.8, 4.0, "symf")
    yb = ym - 2.0 if cathodeTop else ym + 1.2
    sh.FillRect(x - 0.9, yb, 1.8, 0.8, "#000")


def Coil(sh, x, y, label, r=2.4):
    sh.Circle(x, y, r)
    sh.Text(x, y + 0.75, label, size=2.0, anchor="middle", weight="bold")


def Motor(sh, x, y, r=3.2, label="M"):
    sh.Circle(x, y, r)
    sh.Text(x, y + 0.8, label, size=2.3, anchor="middle", weight="bold")


def Tag(sh, x, y, label, cls, side="right", size=1.8, bold=False):
    """Net tag: a small rectangle carrying a net name, attached at (x, y)."""
    w = len(label) * size * 0.52 + 1.4
    h = size + 1.0
    x0 = x if side == "right" else x - w
    sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="#fff" stroke="%s" stroke-width=".25"/>'
           % (Fmt(x0), Fmt(y - h / 2), Fmt(w), Fmt(h), ClassColor.get(cls, "#000")))
    sh.Text(x0 + w / 2, y + size * 0.36, label, size=size, anchor="middle",
            weight="bold" if bold else "normal")
    return w


def RailTag(sh, x, y, label, cls, size=1.8):
    """Return/ground tag: a bar across the end of a vertical wire, label below."""
    sh.Wire([(x - 1.6, y), (x + 1.6, y)], cls)
    sh.Wire([(x - 1.0, y + 0.7), (x + 1.0, y + 0.7)], cls)
    sh.Text(x, y + 0.7 + size + 0.3, label, size=size, anchor="middle")


def LegendBlock(sh, x, y, w):
    sh.Text(x, y, "Legend", size=2.4, weight="bold")
    y += 3.2
    items = [("ac", "Mains 110 VAC, L and N"),
             ("va", "+24 V always on (FB1)"),
             ("ve", "+24 V cut by the E-stop (FB2)"),
             ("zp", "0 V power, returns to star S"),
             ("zs", "0 V signal bus 0V-S (Mega GND only)"),
             ("pe", "Protective earth PE"),
             ("lv", "Logic supply: 5 V, 5.1 V, 6 V, 3V3"),
             ("sg", "Signal")]
    col = w / 2
    for i, (cls, label) in enumerate(items):
        cx = x + (i % 2) * col
        cy = y + (i // 2) * 3.0
        sh.Wire([(cx, cy - 0.6), (cx + 7, cy - 0.6)], cls)
        sh.Text(cx + 8.2, cy, label, size=1.9)
    y += 4 * 3.0 + 0.6
    # symbols
    sx = x
    ContactH(sh, sx + 2, y - 0.6, "NO")
    sh.Wire([(sx, y - 0.6), (sx + 2, y - 0.6)], "sg")
    sh.Wire([(sx + 3.8, y - 0.6), (sx + 5.8, y - 0.6)], "sg")
    sh.Text(sx + 6.8, y, "NO contact", size=1.9)
    sx = x + col
    ContactH(sh, sx + 2, y - 0.6, "NC")
    sh.Wire([(sx, y - 0.6), (sx + 2, y - 0.6)], "sg")
    sh.Wire([(sx + 3.8, y - 0.6), (sx + 5.8, y - 0.6)], "sg")
    sh.Text(sx + 6.8, y, "NC contact (closed at rest)", size=1.9)
    y += 3.4
    FuseH(sh, x, x + 6, y - 0.6, "sg")
    sh.Text(x + 6.8, y, "Fuse", size=1.9)
    sh.Circle(x + col + 2.6, y - 0.6, 1.5)
    sh.Text(x + col + 6.8, y, "Coil, lamp or motor (letter inside)", size=1.9)
    y += 3.4
    Tag(sh, x, y - 0.6, "F2-1", "ve")
    sh.Text(x + 7.6, y, "Net tag: same name = same wire", size=1.9)
    sh.Dot(x + col + 2.6, y - 0.6)
    sh.Wire([(x + col, y - 0.6), (x + col + 5.2, y - 0.6)], "sg")
    sh.Wire([(x + col + 2.6, y - 0.6), (x + col + 2.6, y + 0.9)], "sg")
    sh.Text(x + col + 6.8, y, "Dot = joined; crossing without a dot = not joined", size=1.9)
    return y


# ---------------------------------------------------------------- sheet 1

def DrawFrame(sh, title, subtitle):
    sh.Rect(4.5, 4.5, PageW - 9, PageH - 9, "frame")
    sh.Text(8, 11.2, title, size=4.2, weight="bold")
    sh.Text(8, 15.4, subtitle, size=2.1)


def TitleBlock(sh, x, y, w, h, lines):
    sh.Rect(x, y, w, h, "bx")
    sh.Text(x + 2, y + 4.6, lines[0], size=3.0, weight="bold")
    for i, s in enumerate(lines[1:]):
        sh.Text(x + 2, y + 8.4 + i * 2.75, s, size=2.0)


def BuildSchematic():
    sh = Sheet("RMR control panel wiring schematic")
    DrawFrame(sh, "RMR control panel: wiring schematic",
              "The layered E-stop panel of the 2026-10-06 panel reference, with the supplies of 2026-10-15. "
              "Planned wiring, not the machine as it is wired today.")

    # ------------------------------------------------ band 1: mains, PSU, K2 poles
    sh.Text(8, 21, "Mains and 24 V supply", size=2.4, weight="bold")
    # inlet
    sh.Rect(8, 24, 17, 20, "bx")
    sh.Lines(16.5, 29, ["Inlet", "110 VAC", "+ fuse", "(existing)"], size=1.9, anchor="middle")
    yL, yN, yPE = 27.0, 33.0, 41.0
    sh.Text(25.8, yL - 0.7, "L", size=1.7)
    sh.Text(25.8, yN - 0.7, "N", size=1.7)
    sh.Text(25.8, yPE - 0.7, "PE", size=1.7)
    # Q0 rear switch at x 31
    qx = 31.0
    sh.Wire([(25, yL), (qx, yL)], "ac")
    sh.Wire([(25, yN), (qx, yN)], "ac")
    ContactH(sh, qx, yL, "NO")
    ContactH(sh, qx, yN, "NO")
    sh.Wire([(qx + 0.9, yL + 1.6), (qx + 0.9, yN - 1.6)], "mech")
    sh.Text(qx + 0.9, 23.9, "Q0 rear", size=1.7, anchor="middle")
    sh.Text(qx + 0.9, 37.6, "service", size=1.7, anchor="middle")
    sh.Text(qx + 0.9, 39.6, "isolator", size=1.7, anchor="middle")
    # taps for rung A
    tL, tN = 38.0, 41.0
    k1x = 48.0
    sh.Wire([(qx + 1.8, yL), (k1x, yL)], "ac")
    sh.Wire([(qx + 1.8, yN), (k1x, yN)], "ac")
    sh.Dot(tL, yL, "ac")
    sh.Dot(tN, yN, "ac")
    sh.Wire([(tL, yL), (tL, yL - 3.2)], "ac")
    Tag(sh, tL, yL - 4.6, "L1", "ac", side="right")
    sh.Wire([(tN, yN), (tN, yN + 4.2)], "ac")
    Tag(sh, tN + 1.2, yN + 5.6, "N1", "ac", side="left")
    # K1 main poles
    ContactH(sh, k1x, yL, "NO")
    ContactH(sh, k1x, yN, "NO")
    sh.Wire([(k1x + 0.9, yL + 1.6), (k1x + 0.9, yN - 1.6)], "mech")
    sh.Text(k1x + 0.9, 23.9, "K1 1-2", size=1.7, anchor="middle")
    sh.Text(k1x + 0.9, 37.6, "K1 3-4", size=1.7, anchor="middle")
    sh.Text(k1x + 0.9, 39.6, "HC1-63", size=1.7, anchor="middle")
    psuX0, psuX1 = 57.0, 78.0
    sh.Wire([(k1x + 1.8, yL), (psuX0, yL)], "ac")
    sh.Wire([(k1x + 1.8, yN), (psuX0, yN)], "ac")
    # PSU
    sh.Rect(psuX0, 22, psuX1 - psuX0, 22, "bx")
    sh.Lines(67.5, 30.5, ["PSU", "24 V DC", "1200 W"], size=2.0, anchor="middle")
    sh.Text(psuX0 + 0.6, yL - 0.6, "L", size=1.5)
    sh.Text(psuX0 + 0.6, yN - 0.6, "N", size=1.5)
    sh.Text(psuX0 + 0.6, yPE - 0.6, "FG", size=1.5)
    sh.Text(psuX1 - 0.6, yL - 0.6, "V+", size=1.5, anchor="end")
    sh.Text(psuX1 - 3.4, 43.2, "V-", size=1.5, anchor="middle")
    # PE inlet -> tag, FG -> tag
    sh.Wire([(25, yPE), (28.5, yPE)], "pe")
    Tag(sh, 28.5, yPE, "PE", "pe")
    sh.Wire([(psuX0, yPE), (53.5, yPE)], "pe")
    Tag(sh, 53.5, yPE, "PE", "pe", side="left")

    # V+ node and K2 poles
    vpx = 96.0
    sh.Wire([(psuX1, yL), (vpx, yL)], "va")
    sh.Dot(vpx, yL, "va")
    sh.Text(82, yL - 1.2, "12 AWG", size=1.6)
    # FB1 bus
    fb1Y = 19.0
    sh.Wire([(vpx, yL), (vpx, fb1Y), (238, fb1Y)], "va")
    sh.Text(100, fb1Y - 1.0, "+24 V always on (while K1 is in), 12 AWG to FB1", size=1.7, fill=TolBlue)
    # K2 power poles in series
    sh.Wire([(vpx, yL), (vpx, 29.5)], "va")
    ContactV(sh, vpx, 29.5, "NO")
    sh.Wire([(vpx, 31.3), (vpx, 34.5)], "va")
    ContactV(sh, vpx, 34.5, "NO")
    sh.Text(vpx + 2.2, 31.0, "K2 1-2", size=1.7)
    sh.Text(vpx + 2.2, 36.0, "K2 3-4", size=1.7)
    sh.Text(vpx + 2.2, 38.2, "poles in series (DC)", size=1.6)
    sh.Text(vpx + 2.2, 40.2, "BMC7-25U", size=1.6)
    fb2Y = 84.0
    sh.Wire([(vpx, 36.3), (vpx, fb2Y)], "ve")
    sh.Text(vpx - 1.0, 70, "12 AWG", size=1.6, anchor="end", rot=0)

    # V- to S bar
    sY = 50.0
    sh.Wire([(psuX1 - 3.4, 44), (psuX1 - 3.4, 47.0), (106.5, 47.0), (106.5, sY - 2.0)], "zp")
    sh.Text(80, 46.2, "V-  12 AWG", size=1.6)

    # ------------------------------------------------ FB1 and its loads
    fb1Drops = [(118, "F1-1", ""), (142, "F1-2", "3 A"), (166, "F1-3", ""),
                (190, "F1-4", "3 A"), (210, "F1-5", "3 A"), (230, "F1-6", "")]
    sh.Text(104, 23.3, "FB1", size=2.4, weight="bold", fill=TolBlue)
    sh.Text(104, 25.6, "12-way", size=1.6)
    for x, name, amp in fb1Drops:
        sh.Dot(x, fb1Y, "va")
        if not amp:
            sh.Wire([(x, fb1Y), (x, 21.5)], "va")
            sh.Text(x, 24.2, name + " spare", size=1.7, anchor="middle")
            continue
        FuseV(sh, x, fb1Y, 26.0, "va")
        sh.Text(x + 1.6, 22.3, name, size=1.7)
        sh.Text(x + 1.6, 24.4, amp, size=1.7)
    # since 2026-10-15 one 5 V PSU feeds the Pi at the operator panel; the Mega runs on the Pi's USB
    # and the screen on the Pi, so F1-1 and F1-3 (the Mega buck and the screen supply) are spare
    bucks = [(142, "5 V PSU", "Pi at the panel", "5 V to Pi 5 (note 4)")]
    for x, l1, l2, outLabel in bucks:
        sh.Wire([(x, 26.0), (x, 28.0)], "va")
        sh.Rect(x - 8, 28.0, 16, 8.5, "bx")
        sh.Text(x, 31.4, l1, size=1.9, anchor="middle", weight="bold")
        sh.Text(x, 34.4, l2, size=1.7, anchor="middle")
        # IN- to S
        sh.Wire([(x - 5, 36.5), (x - 5, sY)], "zp")
        sh.Text(x - 4.4, 39.0, "IN-", size=1.5)
        # OUT+
        sh.Wire([(x + 5, 36.5), (x + 5, 41.4)], "lv")
        Tag(sh, x + 5, 43.0, outLabel, "lv", side="left" if x != 118 else "left", size=1.6)
    sh.Wire([(190, 26.0), (190, 28.6)], "va")
    Tag(sh, 186.0, 30.2, "F1-4", "va")
    sh.Text(184.5, 34.0, "to tower SSRs", size=1.6)
    sh.Wire([(210, 26.0), (210, 28.6)], "va")
    Tag(sh, 206.0, 30.2, "F1-5", "va")
    sh.Text(204.5, 34.0, "to E-stop latch", size=1.6)
    sh.Text(204.5, 36.0, "(rung B)", size=1.6)

    # S bar
    sh.Wire([(108.8, sY), (236, sY)], "zp")
    sh.Rect(104.2, sY - 2.0, 4.6, 4.0, "bx")
    sh.Text(106.5, sY + 0.75, "S", size=2.2, anchor="middle", weight="bold")
    sh.Text(170, sY - 1.0, "Star S at PSU V-: every 0 V return lands here on its own wire", size=1.7)
    for x in (137,):
        sh.Dot(x, sY)
    # servo PSU IN- tag stub and 0V-P drop and PE bond
    sh.Wire([(222, sY), (222, sY + 3.0)], "zp")
    Tag(sh, 222, sY + 4.6, "S", "zp", side="right", bold=True)
    sh.Text(226.5, sY + 5.4, "servo PSU IN-", size=1.6)
    sh.Dot(222, sY)
    # 0V-P drop from S to the 0V-P bus
    zpY = 92.0
    sh.Dot(110.5, sY)
    sh.Wire([(110.5, sY), (110.5, zpY)], "zp")
    sh.Text(112.0, 58.5, "0V-P bus, 12 AWG", size=1.6)
    # PE bond and PE bar
    peY = 70.0
    sh.Dot(150, sY)
    sh.Wire([(150, sY), (150, peY)], "pe")
    sh.Text(151.2, 58.5, "0 V to PE bond:", size=1.6)
    sh.Text(151.2, 60.6, "the only one", size=1.6)
    sh.Wire([(122, peY), (236, peY)], "pe")
    sh.Dot(150, peY, "pe")
    peItems = [(126, "inlet"), (136, "PSU FG"), (166, "chassis"), (178, "DIN rails"),
               (192, "frame"), (210, "motor shields,"), (229, "door plate")]
    for x, label in peItems:
        sh.Wire([(x, peY), (x, peY + 2.2)], "pe")
        sh.Dot(x, peY, "pe")
    sh.Text(126, peY + 4.5, "inlet earth", size=1.6, anchor="middle")
    sh.Text(136, peY + 6.6, "PSU FG", size=1.6, anchor="middle")
    sh.Text(166, peY + 4.5, "chassis stud", size=1.6, anchor="middle")
    sh.Text(178, peY + 6.6, "DIN rails", size=1.6, anchor="middle")
    sh.Text(192, peY + 4.5, "frame", size=1.6, anchor="middle")
    sh.Text(210, peY + 4.5, "motor shields", size=1.6, anchor="middle")
    sh.Text(210, peY + 6.6, "(driver end)", size=1.6, anchor="middle")
    sh.Text(229, peY + 4.5, "operator", size=1.6, anchor="middle")
    sh.Text(229, peY + 6.6, "plate", size=1.6, anchor="middle")
    sh.Text(122, peY - 1.0, "PE bar", size=1.8, weight="bold", fill=TolTeal)

    # ------------------------------------------------ rungs A and B
    sh.Text(8, 50.2, "Control rungs", size=2.4, weight="bold")
    # rung A
    ra = 56.0
    sh.Text(8, ra - 2.6, "A  110 VAC: master contactor K1", size=1.8, weight="bold")
    x = 10.0
    w = Tag(sh, 8, ra, "L1", "ac")
    sh.Wire([(8 + w, ra), (14, ra)], "ac")
    FuseH(sh, 14, 22, ra, "ac")
    sh.Text(18, ra + 3.4, "F0 1 A T", size=1.6, anchor="middle")
    sh.Text(18, ra + 5.3, "250 VAC", size=1.6, anchor="middle")
    sh.Wire([(22, ra), (30, ra)], "ac")
    ContactH(sh, 30, ra, "NO")
    sh.Wire([(30.9, ra - 2.4), (30.9, ra - 1.6)], "sym")
    sh.Wire([(29.5, ra - 2.4), (32.3, ra - 2.4)], "sym")
    sh.Text(30.9, ra + 3.4, "S1 knob", size=1.6, anchor="middle")
    sh.Text(30.9, ra + 5.3, "maintained", size=1.6, anchor="middle")
    sh.Wire([(31.8, ra), (52.6, ra)], "ac")
    sh.Dot(40, ra, "ac")
    Coil(sh, 55, ra, "K1")
    sh.Wire([(57.4, ra), (66, ra)], "ac")
    Tag(sh, 66, ra, "N1", "ac")
    sh.Text(55, ra - 3.0, "K1 coil 110 VAC", size=1.6, anchor="middle")
    sh.Wire([(40, ra), (40, ra + 6.5), (53.0, ra + 6.5)], "ac")
    sh.Circle(55, ra + 6.5, 2.0)
    sh.Text(55, ra + 7.2, "H1", size=1.6, anchor="middle", weight="bold")
    sh.Wire([(57.0, ra + 6.5), (63, ra + 6.5), (63, ra)], "ac")
    sh.Dot(63, ra, "ac")
    sh.Text(59, ra + 10.4, "H1 knob lamp, lit while K1 is in", size=1.6, anchor="middle")
    sh.Text(73.5, ra + 0.6, "rung wire rated", size=1.6)
    sh.Text(73.5, ra + 2.6, ">= 300 V", size=1.6)

    # rung B
    rb = 74.0
    sh.Text(8, rb - 5.0, "B  24 V: motor contactor K2, E-stop latch", size=1.8, weight="bold")
    w = Tag(sh, 8, rb, "F1-5", "va")
    sh.Wire([(8 + w, rb), (17, rb)], "va")
    ContactH(sh, 17, rb, "NC")
    sh.Text(17.9, rb - 2.3, "S2 E-stop NC1", size=1.5, anchor="middle")
    sh.Wire([(18.8, rb), (36, rb)], "ve")
    sh.Dot(27, rb, "ve")
    sh.Text(27, rb - 1.0, "X", size=1.7, anchor="middle", weight="bold")
    ContactH(sh, 36, rb, "NO")
    sh.Wire([(36.9, rb - 2.4), (36.9, rb - 1.6)], "sym")
    sh.Wire([(35.5, rb - 2.4), (38.3, rb - 2.4)], "sym")
    sh.Text(36.9, rb - 3.2, "S3 Reset (NO)", size=1.5, anchor="middle")
    sh.Wire([(37.8, rb), (52.6, rb)], "ve")
    sh.Dot(46, rb, "ve")
    sh.Text(46, rb - 1.0, "Y", size=1.7, anchor="middle", weight="bold")
    Coil(sh, 55, rb, "K2")
    sh.Wire([(57.4, rb), (64, rb), (64, rb + 2.6)], "zp")
    RailTag(sh, 64, rb + 2.6, "0V-P", "zp", size=1.5)
    sh.Text(55, rb - 3.0, "K2 coil 24 V", size=1.6, anchor="middle")
    # seal-in
    sh.Wire([(27, rb), (27, rb + 4.5), (36, rb + 4.5)], "ve")
    ContactH(sh, 36, rb + 4.5, "NO")
    sh.Wire([(37.8, rb + 4.5), (46, rb + 4.5), (46, rb)], "ve")
    sh.Text(38.6, rb + 3.9, "K2 5-6", size=1.4)
    sh.Text(38.6, rb + 7.0, "seal-in", size=1.4)
    sh.Text(68.0, rb - 1.4, "Reset pulls K2 in; 5-6 holds it;", size=1.5)
    sh.Text(68.0, rb + 0.5, "NC1 drops it. Releasing the", size=1.5)
    sh.Text(68.0, rb + 2.4, "mushroom restarts nothing.", size=1.5)
    sh.Text(68.0, rb + 4.3, "S1-S3 sit on the door plate.", size=1.5)

    # ------------------------------------------------ band 2: FB2, drives
    sh.Wire([(10, fb2Y), (346, fb2Y)], "ve")
    sh.Dot(vpx, fb2Y, "ve")
    sh.Text(114, fb2Y - 1.2, "FB2  12-way  +24 V cut by the E-stop (K2)", size=2.0, weight="bold",
            fill=TolMagenta, halo=True)
    sh.Wire([(10, zpY), (246, zpY)], "zp")
    sh.Dot(110.5, zpY)
    sh.Text(246.5, zpY + 0.6, "0V-P", size=1.7, weight="bold")
    zsY = 140.0
    sh.Wire([(8, zsY), (346, zsY)], "zs")
    sh.Text(281, zsY - 1.0, "0V-S signal bus", size=1.8, fill="#1a6f8f", weight="bold", halo=True,
            anchor="end")

    drivers = [(12, "X", "F2-1", "Gantry X"), (40, "Y1", "F2-2", "Gantry Y"),
               (68, "Y2", "F2-3", "follows Y"), (96, "Z", "F2-4", "Gantry Z"),
               (124, "A", "F2-5", "Filter feed (I)"), (152, "B", "F2-6", "Syringe ht (J)"),
               (180, "C", "F2-7", "Syringe (K)")]
    pins = DriverPins
    megaY0, megaY1 = 150.0, 160.0
    dTop, dBot = 106.0, 122.0
    for cx, ax, fz, desc in drivers:
        fx = cx + 3
        sh.Dot(fx, fb2Y, "ve")
        FuseV(sh, fx, fb2Y, 90.0, "ve")
        sh.Wire([(fx, 90.0), (fx, dTop)], "ve")
        sh.Text(fx + 1.5, 87.0, fz, size=1.6)
        sh.Text(fx + 1.5, 89.0, "5 A", size=1.6)
        gx = cx + 7
        sh.Wire([(gx, dTop), (gx, zpY)], "zp")
        sh.Dot(gx, zpY)
        mx = cx + 15.75
        for k, ox in enumerate((12.0, 14.5, 17.0, 19.5)):
            sh.Wire([(cx + ox, dTop), (cx + ox, 101.2)], "mo")
        sh.Wire([(cx + 12.0, 101.2), (cx + 19.5, 101.2)], "mo")
        sh.Wire([(mx, 101.2), (mx, 100.8)], "mo")
        Motor(sh, mx, 97.6, 3.2)
        sh.Rect(cx, dTop, 24, dBot - dTop, "bx")
        sh.Text(cx + 12, dTop + 6.2, ax, size=3.2, anchor="middle", weight="bold")
        sh.Text(cx + 12, dTop + 9.6, "TB6600", size=1.7, anchor="middle")
        sh.Text(cx + 12, dTop + 12.0, desc, size=1.6, anchor="middle")
        pp = pins[ax]
        for k, ox in enumerate((5.0, 10.0, 15.0)):
            sh.Wire([(cx + ox, dBot), (cx + ox, megaY0)], "sg")
            sh.Text(cx + ox, megaY0 + 2.6, pp[k], size=1.7, anchor="middle", weight="bold")
        sh.Wire([(cx + 20, dBot), (cx + 20, zsY)], "zs")
        sh.Dot(cx + 20, zsY, "zs")
    # pin key on the X driver
    cx = 12
    sh.Text(cx + 3, dTop - 0.6, "+V", size=1.3, anchor="middle")
    sh.Text(cx + 7, dTop - 0.6, "0V", size=1.3, anchor="middle")
    sh.Text(cx + 5, dBot + 1.9, "PUL+", size=1.3, anchor="middle")
    sh.Text(cx + 10, dBot + 1.9, "DIR+", size=1.3, anchor="middle")
    sh.Text(cx + 15, dBot + 1.9, "ENA+", size=1.3, anchor="middle")
    sh.Text(cx + 20, dBot + 1.9, "COM", size=1.3, anchor="middle")

    # ODrive column
    ox0 = 208.0
    fx = ox0 + 3
    sh.Dot(fx, fb2Y, "ve")
    FuseV(sh, fx, fb2Y, 90.0, "ve")
    sh.Wire([(fx, 90.0), (fx, dTop)], "ve")
    sh.Text(fx + 1.5, 87.0, "F2-8", size=1.6)
    sh.Text(fx + 1.5, 89.0, "10 A, 16 AWG", size=1.6)
    sh.Wire([(ox0 + 7, dTop), (ox0 + 7, zpY)], "zp")
    sh.Dot(ox0 + 7, zpY)
    for ox in (13.0, 16.0, 19.0):
        sh.Wire([(ox0 + ox, dTop), (ox0 + ox, 101.2)], "mo")
    sh.Wire([(ox0 + 13, 101.2), (ox0 + 19, 101.2)], "mo")
    sh.Wire([(ox0 + 16, 101.2), (ox0 + 16, 100.8)], "mo")
    Motor(sh, ox0 + 16, 97.6, 3.2)
    sh.Rect(ox0 + 25, 95.0, 9.0, 5.0, "bxl")
    sh.Text(ox0 + 29.5, 98.2, "AMT102", size=1.4, anchor="middle")
    sh.Wire([(ox0 + 29.5, 100.0), (ox0 + 29.5, dTop)], "sg")
    sh.Rect(ox0, dTop, 34, dBot - dTop, "bx")
    sh.Text(ox0 + 17, dTop + 5.0, "ODrive S1", size=2.4, anchor="middle", weight="bold")
    sh.Text(ox0 + 17, dTop + 8.0, "spin coater, D5312s", size=1.6, anchor="middle")
    sh.Text(ox0 + 17, dTop + 11.0, "J11, isolated UART", size=1.5, anchor="middle")
    # J11 lines
    jl = [(ox0 + 4, "J11-3 TX", "17", "sg"), (ox0 + 11, "J11-4 RX", "16", "sg")]
    for x, lab, mp, cls in jl:
        sh.Wire([(x, dBot), (x, megaY0)], cls)
        sh.Text(x, dBot + 1.9, lab, size=1.3, anchor="middle")
        sh.Text(x, megaY0 + 2.6, mp, size=1.7, anchor="middle", weight="bold")
    sh.Text(ox0 + 4, megaY0 + 4.6, "RX2", size=1.3, anchor="middle")
    sh.Text(ox0 + 11, megaY0 + 4.6, "TX2", size=1.3, anchor="middle")
    sh.Wire([(ox0 + 18, dBot), (ox0 + 18, zsY)], "zs")
    sh.Dot(ox0 + 18, zsY, "zs")
    sh.Text(ox0 + 18, dBot + 1.9, "GND", size=1.3, anchor="middle")
    sh.Wire([(ox0 + 26, dBot), (ox0 + 26, 131.0)], "lv", ' stroke-dasharray="1.1 .8"')
    sh.Text(ox0 + 26, dBot + 1.9, "5V", size=1.3, anchor="middle")
    sh.Text(ox0 + 26, 133.6, "J11 logic 5 V:", size=1.4, anchor="middle")
    sh.Text(ox0 + 26, 135.5, "which side? (note 3)", size=1.4, anchor="middle")

    # ------------------------------------------------ Mega
    sh.Rect(10, megaY0, 238, megaY1 - megaY0, "bx")
    sh.Text(129, megaY0 + 6.6, "Arduino Mega 2560 on a screw-terminal breakout   |   Marlin, "
            "BOARD_RAMPS_14_RMR (1025)   |   pins by board label", size=2.0, anchor="middle",
            weight="bold")

    # right edge exits: 5, 6, 4, 42
    exits = [(151.8, "5"), (153.8, "6"), (155.8, "4"), (157.8, "42")]
    for y, lab in exits:
        sh.Text(247.4, y + 0.55, lab, size=1.5, anchor="end", weight="bold")
    # servo PSU and servos
    f9 = 264.0
    sh.Dot(f9, fb2Y, "ve")
    FuseV(sh, f9, fb2Y, 90.0, "ve")
    sh.Text(f9 + 1.5, 87.0, "F2-9", size=1.6)
    sh.Text(f9 + 1.5, 89.0, "3 A", size=1.6)
    sh.Wire([(f9, 90.0), (f9, 94.0)], "ve")
    sh.Rect(256, 94.0, 16, 8.0, "bx")
    sh.Text(264, 97.4, "Servo PSU", size=1.8, anchor="middle", weight="bold")
    sh.Text(264, 100.4, "6 V (DC-DC)", size=1.5, anchor="middle")
    sh.Wire([(256, 98.0), (250.5, 98.0)], "zp")
    Tag(sh, 250.5, 98.0, "S", "zp", side="left", bold=True)
    sh.Text(253.2, 97.2, "IN-", size=1.2, anchor="middle")
    # servo 0 V (OUT-) and +6 V rails
    sh.Wire([(272, 96.5), (279, 96.5), (279, 122.0)], "zp")
    sh.Wire([(272, 100.0), (276, 100.0), (276, 119.0)], "lv")
    sh.Text(279.6, 95.8, "OUT-", size=1.3)
    sh.Text(279.6, 100.6, "+6 V", size=1.3)
    servos = [(105.0, "Gripper", "M280 P0", 252.0, 151.8), (117.0, "Lid", "M280 P1", 254.5, 153.8)]
    for sy, l1, l2, px, py in servos:
        sh.Rect(257, sy, 13, 8.0, "bx")
        sh.Text(263.5, sy + 3.3, l1 + " servo", size=1.5, anchor="middle", weight="bold")
        sh.Text(263.5, sy + 6.2, l2, size=1.5, anchor="middle")
        sh.Wire([(270, sy + 2.0), (276, sy + 2.0)], "lv")
        sh.Dot(276, sy + 2.0, "lv")
        sh.Wire([(270, sy + 5.0), (279, sy + 5.0)], "zp")
        sh.Dot(279, sy + 5.0)
        sh.Wire([(248, py), (px, py), (px, sy + 4.0), (257, sy + 4.0)], "sg")

    def SsrBlock(fx, fname, inX, inY, title):
        sh.Dot(fx, fb2Y, "ve")
        FuseV(sh, fx, fb2Y, 90.0, "ve")
        sh.Text(fx + 1.5, 87.0, fname, size=1.6)
        sh.Text(fx + 1.5, 89.0, "2 A", size=1.6)
        sh.Wire([(fx, 90.0), (fx, 94.0)], "ve")
        bx0 = fx - 5.5
        sh.Rect(bx0, 94.0, 15, 10.0, "bx")
        sh.Text(bx0 + 8.5, 98.0, title, size=1.7, anchor="middle", weight="bold")
        sh.Text(bx0 + 8.5, 101.0, "3-32 V in", size=1.3, anchor="middle")
        sh.Text(bx0 + 8.5, 102.9, "1.5 A DC out", size=1.3, anchor="middle")
        sh.Text(fx - 0.6, 95.8, "+", size=1.5, anchor="end")
        sh.Text(bx0 + 0.5, 97.3, "IN+", size=1.2)
        sh.Text(bx0 + 0.5, 101.5, "IN-", size=1.2)
        sh.Text(fx + 0.6, 105.9, "-", size=1.5)
        sh.Wire([(248, inY), (inX, inY), (inX, 96.8), (bx0, 96.8)], "sg")
        sh.Wire([(bx0, 101.0), (inX + 2.0, 101.0), (inX + 2.0, zsY)], "zs")
        sh.Dot(inX + 2.0, zsY, "zs")

    # SSR-UV: OUT- -> S4 lid switch -> UV array -> 0V-P
    ux = 292.0
    SsrBlock(ux, "F2-10", 283.5, 155.8, "SSR-UV")
    sh.Wire([(ux, 104.0), (ux, 107.5)], "ve")
    ContactV(sh, ux, 107.5, "NO")
    sh.Text(ux + 2.2, 108.4, "S4 lid switch,", size=1.4, weight="bold")
    sh.Text(ux + 2.2, 110.2, "closed = lid shut", size=1.4)
    sh.Wire([(ux, 109.3), (ux, 113.0)], "ve")
    sh.Rect(ux - 7, 113.0, 14, 7.5, "bx")
    sh.Text(ux, 116.3, "UV LED array", size=1.5, anchor="middle", weight="bold")
    sh.Text(ux, 118.9, "8 x (LED + 330 R)", size=1.3, anchor="middle")
    sh.Wire([(ux, 120.5), (ux, 123.0)], "zp")
    RailTag(sh, ux, 123.0, "0V-P", "zp", size=1.4)

    # SSR-valve: OUT- -> argon valve -> 0V-P, D1 across the coil
    vx = 322.0
    SsrBlock(vx, "F2-11", 311.5, 157.8, "SSR-valve")
    sh.Wire([(vx, 104.0), (vx, 113.0)], "ve")
    sh.Dot(vx, 110.0, "ve")
    sh.Rect(vx - 7, 113.0, 14, 7.5, "bx")
    sh.Text(vx, 116.3, "Argon valve", size=1.5, anchor="middle", weight="bold")
    sh.Text(vx, 118.9, "closes unpowered?", size=1.3, anchor="middle")
    sh.Wire([(vx, 110.0), (vx + 11.0, 110.0), (vx + 11.0, 111.0)], "sg")
    DiodeV(sh, vx + 11.0, 111.0, 122.5, cathodeTop=True)
    sh.Wire([(vx + 11.0, 122.5), (vx, 122.5)], "sg")
    sh.Dot(vx, 122.5)
    sh.Text(vx + 12.6, 115.6, "D1", size=1.4, weight="bold")
    sh.Text(vx + 12.6, 117.4, "1N4007", size=1.3)
    sh.Text(vx + 12.6, 119.2, "band to +", size=1.3)
    sh.Wire([(vx, 120.5), (vx, 125.0)], "zp")
    RailTag(sh, vx, 125.0, "0V-P", "zp", size=1.4)
    # F2-12 spare
    sh.Dot(344, fb2Y, "ve")
    sh.Wire([(344, fb2Y), (344, 86.5)], "ve")
    sh.Text(344, 89.2, "F2-12", size=1.5, anchor="middle")
    sh.Text(344, 91.0, "spare", size=1.5, anchor="middle")

    # ------------------------------------------------ band 3: Mega bottom edge
    zs2 = 198.0
    sh.Wire([(8, zsY), (8, zs2), (128, zs2)], "zs")
    sh.Text(10, zs2 + 2.6, "0V-S (same bus as above, joined at the left)", size=1.5, fill="#1a6f8f")
    where = {"X": "min", "Y": "min", "Z": "min", "A": "MAX end", "B": "min", "C": "open end"}
    ends = [(16 + 12 * i, pn, ax, where[ax]) for i, (ax, pn) in enumerate(EndstopPins)]
    sh.Text(10, 165.2, "Endstops: NO, COM to 0V-S", size=1.6, weight="bold", halo=True)
    for x, pin, ax, where in ends:
        sh.Text(x, megaY1 - 1.2, pin, size=1.7, anchor="middle", weight="bold")
        sh.Wire([(x, megaY1), (x, 176.0)], "sg")
        ContactV(sh, x, 176.0, "NO")
        sh.Wire([(x, 177.8), (x, zs2)], "zs")
        sh.Dot(x, zs2, "zs")
        sh.Text(x + 2.0, 174.4, ax, size=1.8, weight="bold")
        sh.Text(x + 2.0, 181.2, where, size=1.4)
    # Z cap
    sh.Dot(40, 169.0)
    sh.Wire([(40, 169.0), (46, 169.0), (46, 186.0)], "sg")
    CapV(sh, 46, 186.0, "sg")
    sh.Wire([(46, 187.0), (46, zs2)], "zs")
    sh.Dot(46, zs2, "zs")
    sh.Text(47.6, 189.6, "100 nF", size=1.4)
    # pin 39 S5
    x = 90
    sh.Text(x, megaY1 - 1.2, "39", size=1.7, anchor="middle", weight="bold")
    sh.Wire([(x, megaY1), (x, 176.0)], "sg")
    ContactV(sh, x, 176.0, "NO")
    sh.Wire([(x, 177.8), (x, zs2)], "zs")
    sh.Dot(x, zs2, "zs")
    sh.Text(x + 2.0, 174.4, "S5 lid", size=1.5, weight="bold")
    sh.Text(x + 2.0, 181.2, "closed =", size=1.4)
    sh.Text(x + 2.0, 183.0, "lid shut", size=1.4)
    # pin 43 sense
    x = 100
    sh.Text(x, megaY1 - 1.2, "43", size=1.7, anchor="middle", weight="bold")
    sh.Text(110, megaY1 - 1.2, "5V", size=1.7, anchor="middle", weight="bold")
    sh.Wire([(x, megaY1), (x, 178.0)], "sg")
    sh.Dot(x, 166.0)
    ResistorH(sh, x, 110, 166.0, "sg")
    sh.Wire([(110, 166.0), (110, megaY1)], "lv")
    sh.Text(105, 164.2, "1 k", size=1.4, anchor="middle")
    ContactV(sh, x, 178.0, "NO")
    sh.Wire([(x, 179.8), (x, zs2)], "zs")
    sh.Dot(x, zs2, "zs")
    sh.Text(x + 2.0, 177.6, "K2 7-8", size=1.5, weight="bold")
    sh.Text(x + 2.0, 181.6, "closed = motor", size=1.4)
    sh.Text(x + 2.0, 183.4, "power on", size=1.4)
    # GND one wire
    x = 122
    sh.Text(x, megaY1 - 1.2, "GND", size=1.7, anchor="middle", weight="bold")
    sh.Wire([(x, megaY1), (x, zs2)], "zs")
    sh.Dot(x, zs2, "zs")
    sh.Text(x + 1.2, 189.0, "the one wire", size=1.4)
    sh.Text(x + 1.2, 190.8, "0V-S to Mega", size=1.4)
    sh.Text(x + 1.2, 192.6, "GND", size=1.4)
    # Mega power input
    x = 134
    sh.Text(x, megaY1 - 1.2, "PWR", size=1.7, anchor="middle", weight="bold")
    sh.Text(x - 1.0, 164.8, "not used:", size=1.4)
    sh.Text(x - 1.0, 166.7, "USB from", size=1.4)
    sh.Text(x - 1.0, 168.6, "the Pi", size=1.4)
    # USB to Pi
    x = 144
    sh.Text(x, megaY1 - 1.2, "USB", size=1.7, anchor="middle", weight="bold")
    sh.Wire([(x, megaY1), (x, 186.0), (152, 186.0)], "sg")
    sh.Text(144.8, 184.8, "USB", size=1.3)

    # ------------------------------------------------ Pi 5 and tower
    pX0, pY0, pX1, pY1 = 152.0, 166.0, 178.0, 194.0
    sh.Rect(pX0, pY0, pX1 - pX0, pY1 - pY0, "bx")
    sh.Text(165, pY0 + 5.0, "Raspberry", size=1.9, anchor="middle", weight="bold")
    sh.Text(165, pY0 + 7.6, "Pi 5", size=1.9, anchor="middle", weight="bold")
    sh.Text(165, pY0 + 10.6, "rmr_bridge.py", size=1.4, anchor="middle")
    sh.Text(165, pY0 + 13.0, "GPIO = BCM", size=1.4, anchor="middle")
    sh.Wire([(156, pY0), (156, 163.0)], "lv")
    Tag(sh, 154.0, 162.6, "5 V PSU", "lv", side="right", size=1.4)
    # HDMI to screen
    sh.Wire([(174, pY0), (174, 163.4), (236, 163.4)], "sg")
    sh.Text(176, 162.6, "HDMI + USB touch", size=1.4)
    sh.Rect(236, 160.6, 14, 10.0, "bx")
    sh.Text(243, 164.4, "10 in", size=1.5, anchor="middle", weight="bold")
    sh.Text(243, 166.6, "touch", size=1.5, anchor="middle", weight="bold")
    sh.Text(243, 168.8, "screen", size=1.5, anchor="middle", weight="bold")
    sh.Wire([(243, 170.6), (243, 172.6)], "lv")
    Tag(sh, 243, 174.0, "from the Pi", "lv", side="left", size=1.3)
    # tower SSRs
    gp = [(170.0, "5", "red"), (174.0, "6", "amber"), (178.0, "13", "green"), (182.0, "26", "buzzer")]
    sh.Rect(190, 168.0, 14, 16.0, "bx")
    sh.Text(197, 186.8, "SSR x 4", size=1.5, anchor="middle", weight="bold")
    sh.Rect(214, 168.0, 12, 16.0, "bx")
    sh.Text(220, 175.4, "Status", size=1.5, anchor="middle", weight="bold")
    sh.Text(220, 177.6, "tower", size=1.5, anchor="middle", weight="bold")
    sh.Text(220, 179.8, "+ buzzer", size=1.3, anchor="middle")
    for y, g, col in gp:
        sh.Wire([(pX1, y), (190, y)], "sg")
        sh.Text(pX1 - 0.4, y + 0.5, g, size=1.4, anchor="end", weight="bold")
        sh.Text(184.0, y - 0.4, col, size=1.2, anchor="middle")
        sh.Wire([(204, y), (214, y)], "va")
    sh.Text(pX1 - 0.4, 168.6, "GPIO", size=1.2, anchor="end")
    # SSR IN- to Pi GND, OUT+ from F1-4
    sh.Wire([(197, 184.0), (197, 190.0)], "sg")
    sh.Text(198.0, 190.0, "IN- to Pi GND", size=1.2)
    sh.Wire([(200, 168.0), (200, 165.5), (207, 165.5)], "va")
    Tag(sh, 207, 165.5, "F1-4", "va", size=1.3)
    sh.Text(206.0, 189.0, "", size=1.2)
    sh.Wire([(226, 180.0), (229, 180.0), (229, 183.0)], "zp")
    RailTag(sh, 229, 183.0, "0V-P", "zp", size=1.3)
    sh.Text(226.6, 177.6, "COM", size=1.2)
    sh.Text(214.5, 191.0, "Tower common shown at 0 V:", size=1.3)
    sh.Text(214.5, 192.8, "check it (note 3)", size=1.3)
    # GPIO 20 E-stop NC2 with 1 k to 3V3, GPIO 22 button
    sh.Wire([(158, pY1), (158, 197.0)], "sg")
    sh.Dot(158, 197.0)
    ResistorH(sh, 158, 168, 197.0, "sg")
    sh.Wire([(168, 197.0), (168, pY1)], "lv")
    sh.Text(163, 195.4, "1 k", size=1.3, anchor="middle")
    sh.Wire([(158, 197.0), (158, 200.5)], "sg")
    ContactV(sh, 158, 200.5, "NC")
    sh.Wire([(158, 202.3), (158, 205.0), (174, 205.0), (174, pY1)], "sg")
    sh.Text(158, pY1 - 0.8, "20", size=1.4, anchor="middle", weight="bold")
    sh.Text(168, pY1 - 0.8, "3V3", size=1.4, anchor="middle", weight="bold")
    sh.Text(174, pY1 - 0.8, "GND", size=1.4, anchor="middle", weight="bold")
    sh.Text(156.2, 201.9, "S2 NC2", size=1.4, anchor="end", weight="bold")
    sh.Text(156.2, 203.7, "closed =", size=1.2, anchor="end")
    sh.Text(156.2, 205.3, "released", size=1.2, anchor="end")
    sh.Wire([(pX0, 191.0), (148, 191.0), (148, 196.0)], "sg")
    ContactV(sh, 148, 196.0, "NO")
    sh.Wire([(148, 197.8), (148, 205.0), (158, 205.0)], "sg")
    sh.Text(pX0 + 0.4, 190.6, "22", size=1.4, weight="bold")
    sh.Text(146.4, 196.6, "home", size=1.2, anchor="end")
    sh.Text(146.4, 198.2, "button", size=1.2, anchor="end")
    sh.Text(146.4, 199.8, "(optional)", size=1.2, anchor="end")
    sh.Text(178.8, 199.0, "rmr_io.json: estop pin 20, nc true,", size=1.3)
    sh.Text(178.8, 200.8, "cmd null (annunciate only);", size=1.3)
    sh.Text(178.8, 202.6, "tower 5/6/13/26 active high", size=1.3)

    # ------------------------------------------------ legend, notes, title block
    lx, ly = 244.0, 21.0
    LegendBlock(sh, lx, ly, 104.0)
    notes = [
        ("1", ["Source: control panel wiring reference of 2026-10-06 (stages 0 to 9). Mega pins",
               "checked against pins_RAMPS_14_RMR.h and Configuration_adv.h on main ad6c755",
               "(pin 43 MOTOR_POWER_SENSE on; pin 39 UV_LID_INTERLOCK off)."]),
        ("2", ["E-stop: NC1 drops K2, so FB2 loses every actuator (drivers, ODrive, servos,",
               "UV, valve). FB1 keeps Mega, Pi, screen and tower alive to report it."]),
        ("3", ["Read off the parts before wiring: tower common polarity, lid feed voltage,",
               "valve coil, servo 6 V rating, and which side powers ODrive J11 logic."]),
        ("4", ["5 V PSU (2026-10-15): it feeds the Pi 5 at the operator panel, which wants 5.1 V at",
               "5 A; check its rating and the drop along the cable. The Mega runs on the Pi's USB."]),
        ("5", ["Firmware (issue #131): setup(), kill() and a motor-power loss drive pins 4 and 42 to",
               "their OFF level. The bootloader's seconds before setup() are not covered."]),
    ]
    ny = 48.0
    sh.Text(lx, ny, "Notes", size=2.4, weight="bold")
    ny += 3.3
    for num, lines in notes:
        sh.Text(lx, ny, num, size=1.65, weight="bold")
        for s2 in lines:
            sh.Text(lx + 3.0, ny, s2, size=1.65)
            ny += 2.3
        ny += 0.5
    dn = ["Drive and wiring rules",
          "Every driver: PUL-, DIR- and ENA- jumpered at the driver (COM);",
          "one COM wire per driver to 0V-S. Driver top: +V, 0V, A+, A-, B+, B-.",
          "F2-1 to F2-7: 5 A on 18 AWG. Motor shields to PE at the driver end only.",
          "Mega pins are board labels (A0 = D54, A2 = D56, A8 = D62, A9 = D63).",
          "1 k pull-ups on pin 43 and GPIO 20: they read power contacts.",
          "Servo, lid and UV wires cross the hinge: stranded, service loop,",
          "strain relief at both ends."]
    sh.Text(258, 165.0, dn[0], size=2.0, weight="bold")
    for i, s2 in enumerate(dn[1:]):
        sh.Text(258, 168.0 + i * 2.3, s2, size=1.6)
    TitleBlock(sh, 256, 186, 92, 21.5, [
        "RMR control panel: wiring schematic",
        "Sheet 1. Legal 14 x 8.5 in, landscape. Print at 100 %.",
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-14, revised 2026-10-19.",
        "Status: design, not yet wired or tested on the machine.",
        "Sheets 2A and 2B show the same circuits on the two decks.",
    ])
    return sh


# ---------------------------------------------------------------- sheet 2: wiring on the two decks

# Sheet 2 draws sheet 1's circuits on the two decks of the box, one deck per page (2A lower, 2B upper),
# seen from above with the front at the left, so the left wall is at the top. Every rail, part, duct,
# cable slot, grommet and PE stud comes from the enclosure constants further down (DeckSolids(),
# CableSlots, CableEntries, PeStud and the rest), so the wiring follows the layout. Wires run in lanes:
# the ducts, and the free channels between rails. A wire leaves its terminal at right angles into the
# lane beside it, takes a track of that lane, and turns only where two lanes cross or meet at right
# angles. A wire that changes deck ends in its cable slot on both pages; SlotWires() lists each one
# once, and both pages draw and tabulate it from there. A lane is drawn as wide as its wires need:
# DeckSheet() widens each crowded duct or channel on paper and narrows the rest, so the parts keep
# their order and their places relative to each other but not their exact distances; sheet 3 gives
# those.
# The parts follow the owner's decisions of 2026-10-15: the Pi sits at the operator panel on the 5 V
# PSU, the Mega runs on the Pi's USB, the screen has no supply of its own, the tower runs on 24 V
# through SSRs in the box, and the ODrive sits in the spin coater's base. Sheet 1 carries the same.

WirePitch = 0.5                    # paper mm between two tracks of a lane
WireMargin = 0.45                  # paper mm from a lane's edge to its first track
WireGap = 0.8                      # paper mm between two runs on one track
TurnCost = 25.0                    # paper mm a turn costs when a path is chosen
DeckPaper = (20.0, 30.0, 228.0, 162.0)   # the plan's paper box: x, y, width, height


class DeckMap:
    """Deck (x, y) in mm to paper mm, seen from above with the front at the left: x runs right and
    y runs down, so the left wall is at the top. Each axis is piecewise linear; a band (lo, hi, k)
    is drawn k times denser than the rest of its axis. With no bands the map is a uniform scale."""

    def __init__(self, bandsX=(), bandsY=()):
        x0, y0, w, h = DeckPaper
        self.Ax = self.Axis(BoxD, w, bandsX, x0)
        self.Ay = self.Axis(BoxW, h, bandsY, y0)

    @staticmethod
    def Axis(span, width, bands, off):
        cuts = sorted(set([0.0, span] + [min(max(v, 0.0), span) for a, b, _ in bands for v in (a, b)]))
        dens = []
        for a, b in zip(cuts, cuts[1:]):
            ks = [k for lo, hi, k in bands if lo <= a + 1e-9 and b <= hi + 1e-9]
            dens.append((a, b, max(ks) if ks else 1.0))
        s = width / sum((b - a) * k for a, b, k in dens)
        pts = [(0.0, off)]
        for a, b, k in dens:
            pts.append((b, pts[-1][1] + (b - a) * k * s))
        return pts

    @staticmethod
    def At(pts, v):
        for (a, pa), (b, pb) in zip(pts, pts[1:]):
            if v <= b + 1e-9 or b == pts[-1][0]:
                return pa + (v - a) * (pb - pa) / (b - a)
        return pts[-1][1]

    def X(self, x):
        return self.At(self.Ax, x)

    def Y(self, y):
        return self.At(self.Ay, y)

    def R(self, box):
        x0, y0, x1, y1 = box
        return (self.X(x0), self.Y(y0), self.X(x1), self.Y(y1))


class Lane:
    """A routing lane on paper: a duct, or a free channel between parts. Its tracks run along its
    axis, 'x' (left to right on paper) or 'y' (top to bottom)."""

    def __init__(self, name, rect, axis, real):
        self.Name, self.Rect, self.Axis, self.Real = name, rect, axis, real
        x0, y0, x1, y1 = rect
        self.Across = (y0, y1) if axis == "x" else (x0, x1)
        self.Along = (x0, x1) if axis == "x" else (y0, y1)
        n = int((self.Across[1] - self.Across[0] - 2 * WireMargin) / WirePitch + 1e-9) + 1
        self.Cap = max(n, 1)
        self.At = [self.Across[0] + WireMargin + i * WirePitch for i in range(self.Cap)]
        self.Used = [[] for _ in range(self.Cap)]

    def Track(self, i):
        while i >= len(self.At):
            self.At.append(self.At[-1] + WirePitch)
            self.Used.append([])
        return self.At[i]


class DeckWiring:
    """One deck of sheet 2: its lanes, its parts and their terminals, its wires, and the router."""

    def __init__(self, sh, deck, dmap):
        self.Sh, self.Deck, self.M = sh, deck, dmap
        self.Lanes, self.Ends, self.Parts, self.Wires, self.Exits = {}, {}, {}, [], {}
        self.Dots, self.Drawn = [], []
        self.Mains = ()            # lanes inside the 110 VAC compartment
        self.Labels = {}           # terminal block: (slice labels, bridges), for sheet 2C

    # ---- geometry
    def AddLane(self, name, box, axis):
        self.Lanes[name] = Lane(name, self.M.R(box), axis, box)

    def Part(self, key, box, lines=(), size=1.5, rot=0, dashed=False, fill="#fff", at=None):
        """A part's footprint, with its name lines centred in it (or at=(fx, fy), fractions of its box)."""
        sh = self.Sh
        r = self.M.R(box)
        self.Parts[key] = r
        dash = ' stroke-dasharray="1.2 .7"' if dashed else ""
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="#000" stroke-width=".25"%s/>'
               % (Fmt(r[0]), Fmt(r[1]), Fmt(r[2] - r[0]), Fmt(r[3] - r[1]), fill, dash))
        if lines:
            fx, fy = at or (0.5, 0.5)
            cx, cy = r[0] + (r[2] - r[0]) * fx, r[1] + (r[3] - r[1]) * fy
            lead = size * 1.2
            for i, s2 in enumerate(lines):
                off = (i - (len(lines) - 1) / 2) * lead
                sz = size if i == 0 else size * 0.78
                if rot:
                    sh.Text(cx + off + sz * 0.35, cy, s2, size=sz, anchor="middle", rot=rot,
                            weight="bold" if i == 0 else "normal")
                else:
                    sh.Text(cx, cy + off + sz * 0.35, s2, size=sz, anchor="middle",
                            weight="bold" if i == 0 else "normal")
        return r

    def InLane(self, name, lane, x=None, y=None):
        """An end inside a lane: a cable slot, the shield clamp, or a grommet at the lane's end."""
        L = self.Lanes[lane]
        self.Ends[name] = ("i", self.M.X(x) if L.Axis == "x" else self.M.Y(y), lane)

    def Face(self, key, face, lane, names, labels=None, pad=0.1, size=1.0):
        """Terminals spread along one face ('x0', 'x1', 'y0' or 'y1' in deck terms) of part key,
        wired into lane; labels default to the names, and an empty label draws the terminal alone."""
        x0, y0, x1, y1 = self.Parts[key]
        lo, hi = (x0, x1) if face[0] == "y" else (y0, y1)
        n = len(names)
        labels = names if labels is None else labels
        for i, (nm, lab) in enumerate(zip(names, labels)):
            u = lo + (hi - lo) * (pad + (1 - 2 * pad) * (i + 0.5) / n)
            p = {"y0": (u, y0), "y1": (u, y1), "x0": (x0, u), "x1": (x1, u)}[face]
            self.Ends["%s.%s" % (key, nm)] = ("t", p[0], p[1], lane)
            self.TermMark(p, face, lab, size)

    def TermMark(self, p, face, lab, size=1.0):
        sh, s = self.Sh, 0.6
        x, y = p
        bx = {"y0": (x - s / 2, y), "y1": (x - s / 2, y - s), "x0": (x, y - s / 2), "x1": (x - s, y - s / 2)}[face]
        sh.Rect(bx[0], bx[1], s, s, "symf")
        if not lab:
            return
        if face == "y0":
            sh.Text(x, y + s + size * 0.9, lab, size=size, anchor="middle")
        elif face == "y1":
            sh.Text(x, y - s - size * 0.25, lab, size=size, anchor="middle")
        elif face == "x0":
            sh.Text(x + s + 0.3, y + size * 0.35, lab, size=size)
        else:
            sh.Text(x - s - 0.3, y + size * 0.35, lab, size=size, anchor="end")

    def Block(self, key, box, labels, laneA, laneB, bridges=(), title=None, size=1.0, note=None):
        """Feed-through terminals over box, slices along x: slice n has clamp KEY.na on the y0 face
        (into laneA) and KEY.nb on the y1 face (into laneB); bridges join slices (i, j)."""
        sh = self.Sh
        x0, y0, x1, y1 = self.Part(key, box)
        self.Labels[key] = (labels, list(bridges))
        n = len(labels)
        w = (x1 - x0) / n
        for i, lab in enumerate(labels):
            xc = x0 + w * (i + 0.5)
            if i:
                sh.Wire([(x0 + w * i, y0), (x0 + w * i, y1)], "sym")
            self.Ends["%s.%da" % (key, i + 1)] = ("t", xc, y0, laneA)
            self.Ends["%s.%db" % (key, i + 1)] = ("t", xc, y1, laneB)
            self.TermMark((xc, y0), "y0", "", size)
            self.TermMark((xc, y1), "y1", "", size)
            ym = (y0 + y1) / 2
            if len(lab) > 2:
                sh.Text(xc + size * 0.36, ym, lab, size=size, anchor="middle", weight="bold", rot=-90)
            else:
                sh.Text(xc, ym + size * 0.35, lab, size=size, anchor="middle", weight="bold")
            sh.Text(xc, y0 + 2.1, str(i + 1), size=0.8, anchor="middle", fill="#555")
        for i, j in bridges:
            xa, xb = x0 + w * (i + 0.5), x0 + w * (j + 0.5)
            yb = y1 - 2.2
            sh.Wire([(xa, yb), (xb, yb)], "sym")
            for k in range(i, j + 1):
                sh.Dot(x0 + w * (k + 0.5), yb, r=0.28)
        if title:
            sh.Text((x0 + x1) / 2, (y0 + y1) / 2 + (y1 - y0) * 0.33, title, size=1.25, anchor="middle",
                    weight="bold", halo=True)
        if note:
            sh.Text((x0 + x1) / 2, (y0 + y1) / 2 - (y1 - y0) * 0.27, note, size=0.95, anchor="middle", halo=True)

    # ---- wires
    def W(self, cls, a, b, via=None, weight=1, dash=False):
        self.Wires.append(dict(cls=cls, a=a, b=b, via=via, weight=weight, dash=dash))

    def Exit(self, name, lane, wall, u0, u1):
        """A grommet, gland or inlet in a wall, reached from lane: its ends spread over u0 to u1 (deck
        mm along the wall). wall is 'left', 'right', 'front' or 'back'."""
        self.Exits[name] = dict(lane=lane, wall=wall, u=(u0, u1), wires=[])

    def Out(self, cls, a, exitName, weight=1, dash=False):
        w = dict(cls=cls, a=a, b=None, via=None, weight=weight, dash=dash)
        self.Exits[exitName]["wires"].append(w)
        self.Wires.append(w)

    def Point(self, e):
        if e[0] == "t":
            return e[1], e[2]
        L = self.Lanes[e[2]]
        c = (L.Across[0] + L.Across[1]) / 2
        return (e[1], c) if L.Axis == "x" else (c, e[1])

    def PlaceExits(self):
        """Spread each exit's ends over its opening, in the order their wires arrive."""
        M = self.M
        for name, ex in self.Exits.items():
            wires, wall = ex["wires"], ex["wall"]
            alongX = wall in ("left", "right")
            wires.sort(key=lambda w: self.Point(self.Ends[w["a"]])[0 if alongX else 1])
            u0, u1 = ex["u"]
            p0, p1 = (M.X(u0), M.X(u1)) if alongX else (M.Y(u0), M.Y(u1))
            n = len(wires)
            # the stub from the wall must not run on the line of a terminal's stub or a slot end in the
            # same lane, or the two would read as joined: shift the whole spread off them
            near = [self.Point(e)[0 if alongX else 1] for e in self.Ends.values() if e[-1] == ex["lane"]]
            step = (p1 - p0) / n
            shift = min((k * WirePitch / 2 for k in range(-int(step / WirePitch), int(step / WirePitch) + 1)),
                        key=lambda s: (any(abs(p0 + step * (i + 0.5) + s - q) < WirePitch for i in range(n)
                                           for q in near), abs(s)))
            ex["pts"] = []
            for i, w in enumerate(wires):
                p = p0 + step * (i + 0.5) + shift
                pt = {"left": (p, M.Y(0.0)), "right": (p, M.Y(BoxW)), "front": (M.X(0.0), p),
                      "back": (M.X(BoxD), p)}[wall]
                key = "%s#%d" % (name, i)
                self.Ends[key] = ("t", pt[0], pt[1], ex["lane"])
                w["b"] = key
                ex["pts"].append((pt, w["cls"]))

    # ---- routing
    def Joint(self, a, b, tol=0.3):
        """Where lanes a and b cross or meet, or None: only lanes at right angles join."""
        A, B = self.Lanes[a], self.Lanes[b]
        if A.Axis == B.Axis:
            return None
        ax0, ay0, ax1, ay1 = A.Rect
        bx0, by0, bx1, by1 = B.Rect
        x0, x1 = max(ax0, bx0) - tol, min(ax1, bx1) + tol
        y0, y1 = max(ay0, by0) - tol, min(ay1, by1) + tol
        if x0 > x1 or y0 > y1:
            return None
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    def Path(self, la, pa, lb, pb):
        """The lanes from la to lb with the least length plus TurnCost per turn."""
        best = [None]

        def Go(path, cost, pt):
            cur = path[-1]
            if cur == lb:
                total = cost + abs(pt[0] - pb[0]) + abs(pt[1] - pb[1])
                if best[0] is None or total < best[0][0]:
                    best[0] = (total, list(path))
                return
            if len(path) > 8:
                return
            for n in self.Lanes:
                if n in path:
                    continue
                j = self.Joint(cur, n)
                if j is None:
                    continue
                c = cost + abs(pt[0] - j[0]) + abs(pt[1] - j[1]) + TurnCost
                if best[0] is not None and c >= best[0][0]:
                    continue
                path.append(n)
                Go(path, c, j)
                path.pop()

        Go([la], 0.0, pa)
        if best[0] is None:
            raise ValueError("%s deck: no path from lane %s to lane %s" % (self.Deck, la, lb))
        return best[0][1]

    @staticmethod
    def Free(ivs, lo, hi):
        return all(hi + WireGap < a or lo - WireGap > b for a, b in ivs)

    def Take(self, L, lo, hi, pref, weight):
        """The first free track (weight tracks side by side) in the preferred order; past the lane's
        capacity it adds tracks beyond its far edge, which DeckSheet() then widens the lane to hold."""
        n = L.Cap
        if pref == "lo":
            order = list(range(n))
        elif pref == "hi":
            order = list(range(n - 1, -1, -1))
        else:
            order = sorted(range(n), key=lambda i: abs(i - (n - 1) / 2))
        for i in order + list(range(n, n + 400)):
            ks = list(range(i, i + weight)) if (pref != "hi" or i >= n) else list(range(i - weight + 1, i + 1))
            if min(ks) < 0:
                continue
            for k in ks:
                L.Track(k)
            if all(self.Free(L.Used[k], lo, hi) for k in ks):
                for k in ks:
                    L.Used[k].append((lo, hi))
                return sum(L.At[k] for k in ks) / len(ks)
        raise RuntimeError("lane %s: no track" % L.Name)

    def Route(self):
        """Path and tracks for every wire. Returns {lane: (tracks it needs, tracks that fit)}."""
        self.PlaceExits()
        segs = {n: [] for n in self.Lanes}
        for w in self.Wires:
            ea, eb = self.Ends[w["a"]], self.Ends[w["b"]]
            w["path"] = w["via"] or self.Path(ea[-1], self.Point(ea), eb[-1], self.Point(eb))
            if w["path"][0] != ea[-1] or w["path"][-1] != eb[-1]:
                raise ValueError("%s to %s: via must start and end in the ends' lanes" % (w["a"], w["b"]))
            w["tracks"] = [None] * len(w["path"])
            for k, ln in enumerate(w["path"]):
                L = self.Lanes[ln]
                vals, sides = [], []
                for end in (0, 1):
                    if (k == 0) if end == 0 else (k == len(w["path"]) - 1):
                        e = ea if end == 0 else eb
                        if e[0] == "t":
                            along, across = (e[1], e[2]) if L.Axis == "x" else (e[2], e[1])
                            if not L.Along[0] - 1.0 <= along <= L.Along[1] + 1.0:
                                raise ValueError("%s deck: %s is off the end of lane %s"
                                                 % (self.Deck, w["a"] if end == 0 else w["b"], ln))
                            vals.append(along)
                            sides.append("lo" if across <= L.Across[0] + 1e-6 else
                                         "hi" if across >= L.Across[1] - 1e-6 else "mid")
                        else:
                            vals.append(e[1])
                            sides.append("mid")
                    else:
                        nb = self.Lanes[w["path"][k - 1] if end == 0 else w["path"][k + 1]]
                        if self.Joint(ln, nb.Name) is None:
                            raise ValueError("lanes %s and %s do not meet" % (ln, nb.Name))
                        vals += list(nb.Across)
                        mid = (L.Across[0] + L.Across[1]) / 2
                        sides.append("lo" if nb.Along[1] <= mid else "hi" if nb.Along[0] >= mid else "mid")
                pref = sides[0] if sides[0] == sides[1] else "mid"
                segs[ln].append((w, k, min(vals), max(vals), pref))
        for ln, lst in segs.items():
            L = self.Lanes[ln]
            lst.sort(key=lambda s: (s[0]["weight"] == 1, s[3] - s[2]))
            for w, k, lo, hi, pref in lst:
                w["tracks"][k] = self.Take(L, lo, hi, pref, w["weight"])
        return {n: (max([i + 1 for i, u in enumerate(L.Used) if u] or [0]), L.Cap) for n, L in self.Lanes.items()}

    def Draw(self):
        sh = self.Sh
        for w in sorted(self.Wires, key=lambda w: 0 if w["cls"] == "cb" else 1):
            ea, eb = self.Ends[w["a"]], self.Ends[w["b"]]
            t, path = w["tracks"], w["path"]
            pts = []
            L0 = self.Lanes[path[0]]
            if ea[0] == "t":
                pts.append((ea[1], ea[2]))
                pts.append((ea[1], t[0]) if L0.Axis == "x" else (t[0], ea[2]))
            else:
                pts.append((ea[1], t[0]) if L0.Axis == "x" else (t[0], ea[1]))
                self.Dots.append((pts[-1], w["cls"]))
            for k in range(1, len(path)):
                prev = self.Lanes[path[k - 1]]
                pts.append((t[k], t[k - 1]) if prev.Axis == "x" else (t[k - 1], t[k]))
            L1 = self.Lanes[path[-1]]
            if eb[0] == "t":
                pts.append((eb[1], t[-1]) if L1.Axis == "x" else (t[-1], eb[2]))
                pts.append((eb[1], eb[2]))
            else:
                pts.append((eb[1], t[-1]) if L1.Axis == "x" else (t[-1], eb[1]))
                self.Dots.append((pts[-1], w["cls"]))
            clean = [pts[0]]
            for q in pts[1:]:
                if abs(q[0] - clean[-1][0]) > 1e-6 or abs(q[1] - clean[-1][1]) > 1e-6:
                    clean.append(q)
            if len(clean) > 1:
                sh.Wire(clean, w["cls"], ' stroke-dasharray="1.1 .8"' if w["dash"] else "")
                self.Drawn.append((clean, w["cls"], w))
        for (x, y), cls in self.Dots:
            sh.Dot(x, y, cls, r=0.3)


# ---- what is on each deck

def DeckBoxes(deck):
    """{label: box} of the labelled parts on a deck; a repeated label gets ' 2', ' 3' after it."""
    out, seen = {}, {}
    for s in DeckSolids():
        if s["deck"] != deck or s["kind"] not in ("part", "clamp") or not s["label"]:
            continue
        lab = s["label"]
        seen[lab] = seen.get(lab, 0) + 1
        out[lab if seen[lab] == 1 else "%s %d" % (lab, seen[lab])] = s["box"]
    return out


def DuctBox(deck, start):
    return [box for d, box, _, label, _ in Ducts() if d == deck and label.startswith(start)][0]


def GroundBar(kind):
    """The ground bar's footprint on its plate's PE stud, its first screw on the stud. The bar is
    not chosen in size (OpenScrews()); this box only places it."""
    px, py = PeStud[kind]
    return (px - 6.0, py - 3.0, px + 6.0, py + 23.0) if kind == "base" else (px - 4.0, py - 6.0, px + 4.0, py + 24.0)


SsrNames = ["SSR-UV", "SSR-valve", "tower R", "tower A", "tower G", "buzzer"]
TowerSsr = ["tower R", "tower A", "tower G", "buzzer"]
PiTowerGpio = ["5", "6", "13", "26"]


def SlotWires():
    """[(slot, class, lower end, upper end, what)] for every conductor that changes deck, each once.
    An end in a slot or a grommet is named by it; the door cable passes slot 3 to the lower left
    grommet."""
    out = []
    for i, ax in enumerate(DriveAxes):
        out.append((1, "ve", "FB2.%d" % (i + 1), "%s.+V" % ax, "F2-%d to driver %s +V" % (i + 1, ax)))
    for ax in DriveAxes:
        out.append((1, "zp", "0V-P.%s" % ax, "%s.0V" % ax, "0V-P 1 to driver %s 0V" % ax))
    out += [(2, "ve", "FB2.10", "SSR-UV.OUT+", "F2-10 to SSR-UV +"),
            (2, "ve", "FB2.11", "SSR-valve.OUT+", "F2-11 to SSR-valve +"),
            (2, "va", "FB1.4", "tower R.OUT+", "F1-4 to the tower SSRs + (jumpered)"),
            (2, "zp", "0V-P 2.UV", "X6.2b", "0V-P 2 to X6 UV-"),
            (2, "zp", "0V-P 2.V", "X6.6b", "0V-P 2 to X6 V-"),
            (2, "zp", "0V-P 2.T", "X7.5b", "0V-P 2 to X7 C (tower common)"),
            (2, "lv", "servo PSU.OUT+", "X5.1b", "servo PSU +6 V to X5 6V"),
            (2, "zl", "servo PSU.OUT-", "X5.3b", "servo PSU 0 V to X5 0V"),
            (2, "pe", "bar.3", "bar.2", "lower ground bar to upper ground bar"),
            (3, "va", "FB1.5", "X2.1b", "F1-5 to X2 1 (E-stop latch)"),
            (3, "ve", "K2.5", "X2.3b", "K2 5 to X2 2b (seal-in, node X)"),
            (3, "ve", "K2.6", "X2.4b", "K2 6 to X2 3 (node Y)"),
            (3, "ve", "K2.A1", "X2.5b", "K2 A1 to X2 3b (coil, node Y)"),
            (3, "sg", "K2.7", "MEGA.43", "K2 7 to Mega 43 (motor power sense)"),
            (3, "zs", "K2.8", "0V-S.1a", "K2 8 to 0V-S"),
            (3, "va", "LL", "X2.1a", "door cable: X2 1 to S2 NC1, via the lower left grommet"),
            (3, "ve", "LL", "X2.2a", "door cable: NC1 and S3 (node X) to X2 2"),
            (3, "ve", "LL", "X2.4a", "door cable: S3 (node Y) to X2 3")]
    return out


def LowerWiring(d):
    B = DeckBoxes("lower")
    In, Out = Frame + RingClear, BoxD - Frame - RingClear
    low = DuctBox("lower", "duct 1/2 x 1 in: 24 V")
    mains = DuctBox("lower", "duct 1/2 x 1 in: mains")
    lo = LowerRails()
    r24, sp, k2, k1 = lo["24 V"], B["servo PSU"], B["K2"], B["K1"]
    bar = GroundBar("base")
    s1, s2, s3 = CableSlots
    llu = [u for _, u, _, k in CableEntries if k == "LL"][0]
    # lanes: the duct between the fuse rail and the 24 V row runs on (free) to the back ring; free
    # channels in front of the 24 V row, along its top, in the channel at its end, over the servo PSU,
    # and behind it round the base PE stud; the mains duct, and the strips each side of the 110 V rail
    d.AddLane("duct", (In, low[1], BoxD - Frame, low[3]), "x")
    d.AddLane("front", (In, low[3], r24["a0"], MainsZoneY), "y")
    d.AddLane("slot 3", (In, s3[1], r24["a0"], s3[3]), "x")
    d.AddLane("top", (In, k2[3], r24["a1"], MainsZoneY), "x")
    d.AddLane("channel", (r24["a1"], low[3], sp[0], MainsZoneY), "y")
    d.AddLane("over servo", (r24["a1"], sp[3], bar[0] - 2.0, MainsZoneY), "x")
    d.AddLane("behind servo", (sp[2], low[3], bar[0] - 2.0, MainsZoneY), "y")
    d.AddLane("slot 2", (sp[2], s2[1], bar[0] - 2.0, s2[3]), "x")
    d.AddLane("mains duct", (mains[0], sp[3], mains[2], mains[3]), "y")
    d.AddLane("mains front", (mains[2], PsuY0, Out, k1[1]), "x")
    d.AddLane("mains back", (mains[2], k1[3], Out, PsuY1), "x")
    d.AddLane("back", (Out, PsuY0, BoxD, PsuY1), "y")
    d.AddLane("LL", (llu - GrommetHole / 2, 0.0, llu + GrommetHole / 2, low[1]), "y")
    d.Mains = ("mains front", "mains back", "back")
    d.InLane("S1", "over servo", x=(s1[0] + s1[2]) / 2)
    d.InLane("S2", "slot 2", x=min((s2[0] + s2[2]) / 2, bar[0] - 6.0))
    d.InLane("S3", "slot 3", x=(s3[0] + s3[2]) / 2)
    d.InLane("LL", "LL", y=0.0)
    d.Exit("inlet", "back", "back", InletU - 9.0, InletU + 9.0)
    d.Exit("gland", "back", "back", DoorGland[0] - 6.0, DoorGland[0] + 6.0)

    # parts and terminals
    out12 = [str(i + 1) for i in range(12)]
    d.Part("FB2", B["FB2"], ["FB2  12-way", "+24 V cut by the E-stop (K2)"], size=1.7, at=(0.5, 0.42))
    d.Face("FB2", "y1", "duct", out12 + ["IN"], [""] * 12 + ["IN"])
    d.Part("FB1", B["FB1"], ["FB1  12-way", "+24 V always on"], size=1.7, at=(0.5, 0.42))
    d.Face("FB1", "y1", "duct", ["IN"] + out12, ["IN"] + [""] * 12)
    d.Part("K2", k2, ["K2", "BMC7-25U", "coil 24 V"], size=1.6)
    d.Face("K2", "y0", "duct", ["2", "4", "6", "8", "A2"])
    d.Face("K2", "y1", "top", ["1", "3", "5", "7", "A1"])
    d.Part("Star S", B["Star S"], ["Star S", "uxcell"], size=1.35, rot=-90)
    d.Face("Star S", "y0", "duct", ["0VP", "P5", "SP"], ["", "", ""])
    d.Face("Star S", "y1", "top", ["IN", "PE"], ["in", ""])
    d.Part("0V-P", B["0V-P"], ["0V-P 1", "linked to 0V-P 2"], size=1.35, rot=-90)
    d.Face("0V-P", "y0", "duct", ["IN", "K2", "LK"], ["in", "", ""])
    d.Face("0V-P", "y1", "top", DriveAxes, [""] * 7)
    d.Part("0V-P 2", B["0V-P 2"], ["0V-P 2"], size=1.35, rot=-90)
    d.Face("0V-P 2", "y0", "duct", ["IN", "OD"], ["in", ""])
    d.Face("0V-P 2", "y1", "top", ["UV", "V", "T"], [""] * 3)
    d.Part("servo PSU", sp, ["Servo PSU", "6 V, DC-DC"], size=1.5)
    d.Face("servo PSU", "y0", "duct", ["IN+", "IN-"], ["+24", "0V"])
    d.Face("servo PSU", "x1", "behind servo", ["OUT+", "OUT-"], ["+6V", "0V"])
    d.Part("5 V PSU", B["5 V PSU"], ["5 V PSU", "feeds the Pi", "at the panel"], size=1.5, at=(0.5, 0.6))
    d.Face("5 V PSU", "y0", "duct", ["IN+", "IN-", "OUT+", "OUT-"], ["+24", "0V", "+5V", "0V"])
    d.Part("PSU", B["24 V PSU"], ["24 V PSU 1200 W, lying flat", "terminals toward the mains duct,",
                                  "fan toward the right wall"], size=1.7, dashed=True)
    d.Face("PSU", "x1", "mains duct", ["V+a", "V+b", "V-a", "V-b", "FG", "N", "L"],
           ["+V", "+V", "-V", "-V", "FG", "N", "L"])
    d.Part("K1", k1, ["K1", "HC1-63", "coil 110 VAC"], size=1.5)
    d.Face("K1", "y0", "mains front", ["1", "3", "A2"])
    d.Face("K1", "y1", "mains back", ["2", "4", "A1"])
    d.Part("F0", B["F0"], ["F0", "1 A T"], size=1.3, dashed=True, rot=-90)
    d.Face("F0", "y0", "mains front", ["in"], [""])
    d.Face("F0", "y1", "mains back", ["out"], [""])
    d.Block("PE", B["PE"], ["PE", "PE", "PE", "PE"], "mains front", "mains back", title="PE")
    d.Block("X1", B["X1"], ["1", "2", "3"], "mains front", "mains back", title="X1", note="door 110 V")
    d.Block("X0", B["X0"], ["L", "L", "N", "N", "PE"], "mains front", "mains back", bridges=[(0, 1), (2, 3)],
            title="X0", note="mains in")
    d.Part("bar", bar, ["ground bar"], size=1.1, rot=-90, dashed=True)
    d.Face("bar", "x0", "behind servo", ["1", "2", "3"], ["", "", ""])

    # 110 VAC
    W = d.W
    W("ac", "X0.1a", "K1.1")
    W("ac", "X0.3a", "K1.3")
    W("ac", "X0.2a", "F0.in")
    W("ac", "F0.out", "X1.1b")
    W("ac", "X1.2b", "K1.A1")
    W("ac", "X0.4b", "X1.3b")
    W("ac", "X0.4a", "K1.A2")
    W("ac", "K1.2", "PSU.L")
    W("ac", "K1.4", "PSU.N")
    d.Out("ac", "X0.1b", "inlet")
    d.Out("ac", "X0.3b", "inlet")
    d.Out("pe", "X0.5b", "inlet")
    for i in range(3):
        d.Out("ac", "X1.%da" % (i + 1), "gland")
    d.Out("pe", "PE.3a", "gland")
    W("pe", "X0.5a", "PE.1a")
    W("pe", "PSU.FG", "PE.2b")
    W("pe", "PE.4a", "bar.1")
    W("pe", "Star S.PE", "bar.2")
    # 24 V, the E-stop contactor, the star and the 0 V buses
    W("va", "PSU.V+a", "FB1.IN")
    W("va", "PSU.V+b", "K2.1")
    W("va", "K2.2", "K2.3")
    W("ve", "K2.4", "FB2.IN")
    W("zp", "PSU.V-a", "Star S.IN")
    W("zp", "Star S.0VP", "0V-P.IN")
    W("zp", "0V-P.LK", "0V-P 2.IN")
    W("zp", "K2.A2", "0V-P.K2")
    W("va", "FB1.2", "5 V PSU.IN+")
    W("zp", "5 V PSU.IN-", "Star S.P5")
    W("ve", "FB2.9", "servo PSU.IN+")
    W("zp", "servo PSU.IN-", "Star S.SP")
    W("ve", "FB2.8", "LL")
    W("zp", "0V-P 2.OD", "LL")
    W("lv", "5 V PSU.OUT+", "LL")
    W("zl", "5 V PSU.OUT-", "LL")
    for slot, cls, a, b, _ in SlotWires():
        W(cls, a if a != "LL" else "S%d" % slot, "S%d" % slot if a != "LL" else "LL")
    return d


def UpperWiring(d):
    B = DeckBoxes("upper")
    In = Frame + RingClear
    fd, sd, md = UpRows["field duct"], UpRows["signal duct"], UpRows["motor duct"]
    up = UpperRails()
    clamp = ClampBox()
    back0, back1 = BackRunX - DuctWide / 2, BackRunX + DuctWide / 2
    feed = DuctBox("upper", "24 V feeds")
    ssrIn = DuctBox("upper", "SSR inputs")
    ssr = B["SSR-UV"]
    bar = GroundBar("upper")
    s1, s2, s3 = CableSlots
    u = dict((k, uu) for _, uu, _, k in CableEntries)
    # lanes: the ducts (the 24 V feed duct reaching down to slot 1, the motor duct in two parts either
    # side of the shield clamp, the back run reaching the left wall); free channels in front of the
    # logic rail (slot 3, the front grommet), along the left wall (field cables), behind the SSRs
    # (their outputs, slot 2), along the right wall, and behind the back run to the ground bar
    d.AddLane("front", (Frame + 1.0, 2.0, LogicRail0 - 0.5, sd[0]), "y")
    d.AddLane("left wall", (Frame + 1.0, 2.0, BoxD - Frame, FieldRail0 - 17.0), "x")
    d.AddLane("field duct", (LogicRail0 - 0.5, fd[0], back0, fd[1]), "x")
    d.AddLane("signal duct", (In, sd[0], up["drivers"]["a1"], sd[1]), "x")
    d.AddLane("SSR inputs", ssrIn, "y")
    d.AddLane("SSR outputs", (ssr[2], fd[1], back0, s2[3]), "y")
    d.AddLane("slot 2", (s2[0] - 2.0, s2[1], back0, s2[3]), "x")
    d.AddLane("feed duct", (feed[0], UpRows["drivers"][0], feed[2], md[0]), "y")
    d.AddLane("motor duct", (In, md[0], clamp[0], md[1]), "x")
    d.AddLane("motor duct 2", (clamp[2], md[0], back0, md[1]), "x")
    d.AddLane("back run", (back0, 0.0, back1, md[1]), "y")
    d.AddLane("to UR", (clamp[0] + 1.0, md[0], clamp[2] - 1.0, BoxW), "y")
    d.AddLane("right wall", (Frame + 1.0, md[1], back1, BoxW - 2.0), "x")
    d.AddLane("behind", (back1, In, bar[0] - 2.0, BoxW - 2.0), "y")
    d.InLane("S1", "feed duct", y=(s1[1] + s1[3]) / 2)
    d.InLane("S2", "slot 2", x=(s2[0] + s2[2]) / 2)
    d.InLane("S3", "front", y=(s3[1] + s3[3]) / 2)
    d.InLane("clamp", "motor duct", x=clamp[0])
    d.InLane("clamp out", "motor duct 2", x=clamp[2])
    d.InLane("clamp out UR", "to UR", y=(md[0] + md[1]) / 2)
    d.InLane("ULM", "back run", y=0.0)
    d.Exit("UL", "left wall", "left", u["UL"] - 21.0, u["UL"] + 21.0)
    d.Exit("UF", "front", "front", u["UF"] - 21.0, u["UF"] + 21.0)
    d.Exit("UR", "right wall", "right", u["UR"] - 21.0, u["UR"] + 21.0)

    # field rail
    blocks = [("X2", ["1", "2", "2b", "3", "3b", "4", "5"], [(1, 2), (3, 4)], "E-stop"),
              ("X4", ["3", "14", "40", "15", "23", "A9"] + ["C"] * 6, [(6, 11)], "endstops"),
              ("X5", ["6V", "6V", "0V", "0V", "P0", "P1"], [(0, 1), (2, 3)], "servos"),
              ("X6", ["UV+", "UV-", "S5", "S5c", "V+", "V-"], [], "lid, valve"),
              ("X7", ["R", "A", "G", "Bz", "C"], [], "tower"),
              ("X8", ["-", "-", "-", "-"], [], "spare")]
    for key, labels, bridges, note in blocks:
        d.Block(key, B[key], labels, "left wall", "field duct", bridges=bridges, title=key, note=note)
    # logic rail
    d.Part("MEGA", B["Mega 2560"], ["Arduino Mega 2560", "screw-terminal shield", "on a DIN carrier",
                                           "USB from the Pi"], size=1.6, at=(0.5, 0.47))
    top = [p for _, p in EndstopPins] + ["GND", "5", "6", "39", "43", "4", "42"]
    d.Face("MEGA", "y0", "field duct", top)
    d.Face("MEGA", "y1", "signal duct", ["g" + ax for ax in DriveAxes] + ["16", "17"],
           [""] * 7 + ["16 TX2", "17 RX2"], pad=0.04)
    for ax in DriveAxes:
        x, y = d.Ends["MEGA.g" + ax][1:3]
        d.Sh.Text(x + 0.4, y - 1.2, "%s: %s" % (ax, " ".join(DriverPins[ax])), size=0.95, anchor="start", rot=-90)
    d.Face("MEGA", "x0", "front", ["USB"])
    d.Block("0V-S", B["0V-S"], ["X", "Y1", "Y2", "Z", "A", "B", "C", "J", "lk"], "field duct", "signal duct",
            bridges=[(0, 8)], title="0V-S")
    d.Block("0V-S2", B["0V-S2"], ["1", "2", "3", "lk"], "field duct", "signal duct", bridges=[(0, 3)], title="0V-S2")
    # SSR rail
    for name in SsrNames:
        d.Part(name, B[name], [name], size=1.05, at=(0.5, 0.55))
        d.Face(name, "x0", "SSR inputs", ["IN+", "IN-"], ["+", "-"], size=0.8, pad=0.05)
        d.Face(name, "x1", "SSR outputs", ["OUT+", "OUT-"], ["+", "-"], size=0.8, pad=0.05)
    # drivers and the shield clamp
    for ax in DriveAxes:
        d.Part(ax, B[ax], [ax, "TB6600"], size=2.0)
        d.Face(ax, "y0", "signal duct", ["SIG", "COM"], ["sig", "com"])
        d.Face(ax, "y1", "motor duct", ["+V", "0V", "M"], ["+V", "0V", "M"])
    d.Part("clamp", clamp, ["shield clamp", "motor shields"], size=1.2, rot=-90, dashed=True)
    d.Face("clamp", "y1", "right wall", ["PE"], [""])
    d.Part("bar", bar, ["ground bar"], size=1.1, rot=-90, dashed=True)
    d.Face("bar", "x0", "behind", ["1", "2", "3"], ["", "", ""])

    W = d.W
    for i, ax in enumerate(DriveAxes):
        W("sgc", "MEGA.g" + ax, ax + ".SIG")
        W("zs", ax + ".COM", "0V-S.%db" % (i + 1))
        W("cb", ax + ".M", "clamp", weight=2)
    W("cb", "clamp out", "ULM", weight=3)
    d.Out("cb", "clamp out UR", "UR", weight=2)
    for i, (ax, pin) in enumerate(EndstopPins):
        W("sg", "MEGA." + pin, "X4.%db" % (i + 1))
    W("zs", "X4.7b", "0V-S.3a")
    W("zs", "MEGA.GND", "0V-S.2a")
    W("sg", "MEGA.5", "X5.5b")
    W("sg", "MEGA.6", "X5.6b")
    W("sg", "MEGA.39", "X6.3b")
    W("zs", "X6.4b", "0V-S2.3a")
    W("sg", "MEGA.4", "SSR-UV.IN+")
    W("sg", "MEGA.42", "SSR-valve.IN+")
    W("zs", "SSR-UV.IN-", "0V-S2.1b")
    W("zs", "SSR-valve.IN-", "0V-S2.2b")
    W("zs", "0V-S2.4a", "0V-S.9a")
    W("ve", "SSR-UV.OUT-", "X6.1b")
    W("ve", "SSR-valve.OUT-", "X6.5b")
    for i, name in enumerate(TowerSsr):
        W("va", name + ".OUT-", "X7.%db" % (i + 1))
    for a, b in zip(TowerSsr, TowerSsr[1:]):
        W("va", a + ".OUT+", b + ".OUT+")
        W("sg", a + ".IN-", b + ".IN-")
    # cables to the Pi and the ODrive at the operator panel and the spin coater, through the front
    d.Out("sgc", "MEGA.USB", "UF")
    d.Out("sg", "MEGA.17", "UF")
    d.Out("sg", "MEGA.16", "UF")
    d.Out("zs", "0V-S.8b", "UF")
    for name in TowerSsr:
        d.Out("sg", name + ".IN+", "UF")
    d.Out("sg", "tower R.IN-", "UF")
    # field cables
    fieldCls = {"X4": ["sg"] * 6 + ["zs"] * 6, "X5": ["lv", "lv", "zl", "zl", "sg", "sg"],
                "X6": ["ve", "zp", "sg", "zs", "ve", "zp"]}
    for key, cls in fieldCls.items():
        for i, c in enumerate(cls):
            d.Out(c, "%s.%da" % (key, i + 1), "UL")
    for i, c in enumerate(["va", "va", "va", "va", "zp"]):
        d.Out(c, "X7.%da" % (i + 1), "UR")
    W("pe", "clamp.PE", "bar.1")
    W("pe", "bar.3", "ULM")
    for slot, cls, a, b, _ in SlotWires():
        W(cls, "S%d" % slot, b)
    return d


# ---- the page

WireCss = (".ac{stroke-width:.4}.va,.ve{stroke-width:.32}.zp{stroke-width:.34}"
           ".zs,.pe{stroke-width:.28}.lv{stroke-width:.3}.zl{stroke-width:.24}"
           ".sg{stroke-width:.17}.sgc{stroke-width:.36}.cb{stroke-width:.75}")


def DeckFrame(d):
    """The deck's frame, plate or ring, rails, ducts, slots, PE stud, 110 VAC compartment, walls."""
    sh, M = d.Sh, d.M
    F = Frame

    def Rect(box, fill, stroke=0.25, cls=None):
        x0, y0, x1, y1 = M.R(box)
        if cls:
            sh.Rect(x0, y0, x1 - x0, y1 - y0, cls)
            return
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="#000" stroke-width="%s"/>'
               % (Fmt(x0), Fmt(y0), Fmt(x1 - x0), Fmt(y1 - y0), fill, Fmt(stroke)))

    Rect((0, 0, BoxD, BoxW), "#fff", 0.35)
    if d.Deck == "lower":
        for box in ((0, 0, BoxD, F), (0, BoxW - F, BoxD, BoxW), (0, F, F, BoxW - F), (BoxD - F, F, BoxD, BoxW - F)):
            Rect(box, ZoneFill["frame"], 0.15)
    else:
        x0, y0, x1, y1 = M.R((F, F, BoxD - F, BoxW - F))
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="#000" stroke-width=".2" '
               'stroke-dasharray="1.2 .7"/>' % (Fmt(x0), Fmt(y0), Fmt(x1 - x0), Fmt(y1 - y0)))
    for x, y in PostCentres:
        Rect((x - F / 2, y - F / 2, x + F / 2, y + F / 2), PostFill, 0.25)
    for s in DeckSolids():
        if s["deck"] == d.Deck and s["kind"] == "rail":
            Rect(s["box"], None, cls="rail")
    for s in DeckSolids():
        if s["deck"] == d.Deck and s["kind"] == "duct":
            Rect(s["box"], None, cls="duct")
    # cable slots: holes in the upper plate; on the lower deck they are overhead
    for i, (a0, b0, a1, b1) in enumerate(CableSlots):
        x0, y0, x1, y1 = M.R((a0, b0, a1, b1))
        r = min(x1 - x0, y1 - y0) / 2
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="none" stroke="%s" stroke-width=".35"%s/>'
               % (Fmt(x0), Fmt(y0), Fmt(x1 - x0), Fmt(y1 - y0), Fmt(r), TolOrange,
                  ' stroke-dasharray="1 .6"' if d.Deck == "lower" else ""))
        lx, ly = (x1 + 0.8, y0 + 1.6) if i != 2 else (x0 + 0.4, y1 + 1.8)
        sh.Text(lx, ly, "slot %d" % (i + 1), size=1.2, weight="bold", fill="#a0450f", halo=True)
    px, py = PeStud["base" if d.Deck == "lower" else "upper"]
    sh.Circle(M.X(px), M.Y(py), 0.9, "symf")
    sh.Text(M.X(px) + 1.2, M.Y(py) - 0.9, "PE stud", size=1.0, halo=True)
    if d.Deck == "lower":
        zx, zy = M.X(MainsZoneX), M.Y(MainsZoneY)
        sh.Wire([(zx, M.Y(BoxW - F)), (zx, zy), (M.X(BoxD - F), zy)], "ac", ' stroke-dasharray="2 1"')
        sh.Text(zx + 1.0, zy + 2.4, "110 VAC compartment: no wall (ADR-0013); mains parts 10 mm inside this line,"
                " low voltage outside it", size=1.15, fill=TolRed, weight="bold", halo=True)
    # walls
    x0, y0, x1, y1 = M.R((0, 0, BoxD, BoxW))
    sh.Text(x0 + 1.0, y0 - 1.2, "LEFT WALL", size=1.4, weight="bold", halo=True)
    sh.Text(x0 + 1.0, y1 + 2.6, "RIGHT WALL", size=1.4, weight="bold", halo=True)
    sh.Text(x0 - 1.2, (y0 + y1) / 2, "FRONT", size=1.4, anchor="middle", weight="bold", rot=-90)
    sh.Text(x1 + 2.4, (y0 + y1) / 2, "BACK", size=1.4, anchor="middle", weight="bold", rot=-90)


def DeckExits(d, notes):
    """The grommets, inlet and gland on the walls, with what leaves through each."""
    sh, M = d.Sh, d.M
    r = GrommetHole / 2
    marks = []
    for panel, u, what, key in CableEntries:
        wall, z0 = PanelWall[panel]
        if ("lower" if z0 == 0.0 else "upper") == d.Deck:
            marks.append((key, wall, u - r, u + r))
    if d.Deck == "lower":
        marks += [("inlet", "back", InletU - 12.0, InletU + 12.0),
                  ("gland", "back", DoorGland[0] - DoorGland[1] / 2, DoorGland[0] + DoorGland[1] / 2)]
    for key, wall, a, b in marks:
        if wall in ("left", "right"):
            y = M.Y(0.0) - 0.9 if wall == "left" else M.Y(BoxW)
            sh.FillRect(M.X(a), y, M.X(b) - M.X(a), 0.9, "#000")
        else:
            x = M.X(0.0) - 0.9 if wall == "front" else M.X(BoxD)
            sh.FillRect(x, M.Y(a), 0.9, M.Y(b) - M.Y(a), "#000")
        lines = notes[key]
        bold = ["bold"] + ["normal"] * (len(lines) - 1)
        if wall == "left":
            for i, s2 in enumerate(lines):
                sh.Text(M.X(b) + 1.0, M.Y(0.0) - 2.3 - (len(lines) - 1 - i) * 1.5, s2, size=1.15, weight=bold[i],
                        halo=True)
        elif wall == "right":
            for i, s2 in enumerate(lines):
                sh.Text(M.X(b) + 1.0, M.Y(BoxW) + 2.3 + i * 1.5, s2, size=1.15, weight=bold[i], halo=True)
        elif wall == "front":
            for i, s2 in enumerate(lines):
                sh.Text(M.X(0.0) - 2.6 - (len(lines) - 1 - i) * 1.5, (M.Y(a) + M.Y(b)) / 2, s2, size=1.15,
                        anchor="middle", rot=-90, weight=bold[i])
        else:
            for i, s2 in enumerate(lines):
                sh.Text(M.X(BoxD) + 2.0 + i * 1.5, (M.Y(a) + M.Y(b)) / 2, s2, size=1.1, anchor="middle", rot=-90,
                        weight=bold[i])


def WireLegend(sh, x, y, w):
    sh.Text(x, y, "Legend", size=2.0, weight="bold")
    items = [("ac", "110 VAC"), ("va", "+24 V always on (FB1)"), ("ve", "+24 V behind K2 (FB2)"),
             ("zp", "0 V power (0V-P, star S)"), ("zs", "0V-S signal 0 V"), ("pe", "PE"),
             ("lv", "+6 V servo, +5 V Pi"), ("zl", "their 0 V"), ("sg", "signal"),
             ("sgc", "multi-core signal cable"), ("cb", "motor cable")]
    col = w / 2
    for i, (cls, lab) in enumerate(items):
        cx, cy = x + (i % 2) * col, y + 3.2 + (i // 2) * 2.3
        sh.Wire([(cx, cy - 0.45), (cx + 5.0, cy - 0.45)], cls)
        sh.Text(cx + 6.0, cy, lab, size=1.3)
    cy = y + 3.2 + 6 * 2.3
    sh.Rect(x, cy - 1.4, 5.0, 1.8, "duct")
    sh.Text(x + 6.0, cy, "wire duct", size=1.3)
    sh.Rect(x + col, cy - 1.2, 5.0, 1.4, "rail")
    sh.Text(x + col + 6.0, cy, "DIN rail", size=1.3)
    cy += 2.3
    sh.Add('<rect x="%s" y="%s" width="5" height="1.8" rx=".9" fill="none" stroke="%s" stroke-width=".35"/>'
           % (Fmt(x), Fmt(cy - 1.4), TolOrange))
    sh.Text(x + 6.0, cy, "cable slot (dashed: overhead)", size=1.3)
    sh.Dot(x + col + 2.5, cy - 0.45, "zp", r=0.3)
    sh.Text(x + col + 6.0, cy, "wire ends in a slot", size=1.3)
    cy += 2.3
    sh.FillRect(x, cy - 1.0, 5.0, 0.9, "#000")
    sh.Text(x + 6.0, cy, "grommet, inlet or gland", size=1.3)
    sh.Rect(x + col, cy - 1.4, 5.0, 1.8, "bx")
    sh.Text(x + col + 6.0, cy, "part (dashed: size assumed)", size=1.3)
    return cy + 1.5


def SlotTable(sh, x, y):
    sh.Text(x, y, "Wires between the decks", size=2.0, weight="bold")
    y += 2.8
    cur = None
    for slot, cls, a, b, what in SlotWires():
        if slot != cur:
            cur = slot
            x0, y0, x1, y1 = CableSlots[slot - 1]
            sh.Text(x, y, "Slot %d (x %s-%s, y %s-%s)" % (slot, Mm(x0), Mm(x1), Mm(y0), Mm(y1)), size=1.3,
                    weight="bold")
            y += 1.8
        sh.Wire([(x + 0.4, y - 0.45), (x + 3.4, y - 0.45)], cls)
        sh.Text(x + 4.2, y, what, size=1.2)
        y += 1.55
    return y


def DeckSheet(deck):
    """Sheet 2A or 2B. Routes the deck, widens every lane its wires overflow, and routes again until
    every wire has a track inside its lane."""
    bands = {}
    for _ in range(12):
        bx = [(lo, hi, k) for ax, lo, hi, k in bands.values() if ax == "x"]
        by = [(lo, hi, k) for ax, lo, hi, k in bands.values() if ax == "y"]
        sh = Sheet("RMR control panel wiring, %s deck" % deck)
        sh.CssExtra = WireCss
        d = DeckWiring(sh, deck, DeckMap(bx, by))
        DeckFrame(d)
        (LowerWiring if deck == "lower" else UpperWiring)(d)
        use = d.Route()
        over = [n for n, (need, cap) in use.items() if need > cap]
        if not over:
            break
        for n in over:
            L = d.Lanes[n]
            need = 2 * WireMargin + (use[n][0] - 1) * WirePitch + 0.25
            have = L.Across[1] - L.Across[0]
            x0, y0, x1, y1 = L.Real
            band = ("y", y0, y1) if L.Axis == "x" else ("x", x0, x1)
            k = bands[n][3] if n in bands else 1.0
            bands[n] = band + (k * need / have * 1.04,)
    else:
        raise ValueError("%s deck: the lanes %s still overflow" % (deck, ", ".join(over)))
    MainsWireChecks(d)
    d.Draw()
    CrossChecks(d)
    return sh, d, use, bands


def CrossChecks(d):
    """Raise unless no two parts overlap on paper and no drawn wire passes through a part: a run may
    end on a part's face but not cross its inside. Motor cables pass the shield clamp, which holds
    their shields."""
    eps = 0.05

    def Inside(a, b):
        return a[0] < b[2] - eps and b[0] < a[2] - eps and a[1] < b[3] - eps and b[1] < a[3] - eps

    parts = list(d.Parts.items())
    for i, (ka, ra) in enumerate(parts):
        for kb, rb in parts[i + 1:]:
            if Inside(ra, rb):
                raise ValueError("%s deck: %s overlaps %s" % (d.Deck, ka, kb))
    segs = []
    for pts, cls, w in d.Drawn:
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            segs.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2), w))
    for pts, cls, w in d.Drawn:
        # no corner or end of one wire on another wire: that would read as a joint. Wires that meet at
        # a terminal are joined there anyway; wires that cross at right angles are not joined
        mine = set(e for e in (w["a"], w["b"]) if d.Ends[e][0] == "t")
        for x, y in pts:
            for x0, y0, x1, y1, v in segs:
                if v is not w and not mine & set((v["a"], v["b"])) and                         x0 - 1e-6 <= x <= x1 + 1e-6 and y0 - 1e-6 <= y <= y1 + 1e-6:
                    raise ValueError("%s deck: %s to %s touches %s to %s at (%.2f, %.2f)"
                                     % (d.Deck, w["a"], w["b"], v["a"], v["b"], x, y))
    for pts, cls, w in d.Drawn:
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            seg = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            for key, r in parts:
                if cls == "cb" and key == "clamp":
                    continue
                if (x1 == x2 and r[0] + eps < x1 < r[2] - eps and Inside((r[0], seg[1], r[2], seg[3]), r)) or                         (y1 == y2 and r[1] + eps < y1 < r[3] - eps and Inside((seg[0], r[1], seg[2], r[3]), r)):
                    raise ValueError("%s deck: a %s wire runs through %s" % (d.Deck, cls, key))


def MainsWireChecks(d):
    """Raise unless every 110 VAC wire stays in the compartment's lanes and the mains duct; the PSU's
    own DC leads keep to the mains duct; and no other wire but PE enters any of them (ADR-0013)."""
    inside = set(d.Mains) | ({"mains duct"} if d.Mains else set())
    for w in d.Wires:
        lanes = set(w["path"])
        dc = w["cls"] != "ac" and (w["a"].startswith("PSU.") or w["b"].startswith("PSU."))
        if w["cls"] == "ac" and not lanes <= inside:
            raise ValueError("110 VAC wire %s to %s leaves the compartment by %s" % (w["a"], w["b"], lanes - inside))
        if w["cls"] not in ("ac", "pe") and lanes & (set(d.Mains) if dc else inside):
            raise ValueError("low-voltage wire %s to %s runs in the 110 VAC compartment" % (w["a"], w["b"]))


ExitNotes = {
    "LL": ["Lower left grommet", "ODrive 24 V: F2-8 and 0V-P 2", "Pi 5 V: the 5 V PSU", "E-stop loop: the door cable from X2"],
    "inlet": ["IEC inlet with switch Q0", "L, N, PE"],
    "gland": ["M20 gland: door 110 V", "X1 1-3 and PE"],
    "UL": ["Upper left grommet: field cables", "X4 to the endstops, a pair each; X5 to the servos;",
           "X6 to the lid (S4 and UV array, S5) and the argon valve"],
    "ULM": ["Upper left grommet 2", "6 motor cables, gantry PE trunk"],
    "UF": ["Upper front grommet", "to the operator panel: Mega USB, Pi GPIO to the tower SSRs;",
           "to the spin coater base: J11 (ODrive UART)"],
    "UR": ["Upper right grommet", "X7 to the tower, 1 motor cable"],
}
FuseUse = {"FB2": ["X", "Y1", "Y2", "Z", "A", "B", "C", "ODrive", "servo", "UV", "valve", "spare"],
           "FB1": ["spare", "5 V PSU", "spare", "tower", "latch", "spare", "spare", "spare", "spare", "spare", "spare",
                   "spare"]}
FuseAmps = {"FB2": ["5", "5", "5", "5", "5", "5", "5", "10", "3", "2", "2", ""],
            "FB1": ["", "3", "", "3", "3", "", "", "", "", "", "", ""]}


def WireNotes(deck):
    common = [
        "Seen from above, front at the left, so the left wall is at the top. Each part sits where sheet 3",
        "puts it; ducts and channels are drawn wider than scale so that every wire shows: measure from sheet 3.",
        "Terminals are drawn on the face their wires leave from; read the real order off each part.",
        "Since 2026-10-15 the Pi sits at the operator panel on the 5 V PSU, the Mega runs on the Pi's USB and",
        "the screen has no supply of its own: F1-1, F1-3, X8 and X2 4-5 are spare (NC2 and the home button",
        "are wired at the panel). The ODrive sits in the spin coater's base.",
        "Gauges, copper only: mains, the PSU to FB1, K2 and S, K2 to FB2, S to 0V-P: 12 AWG. F2-1 to F2-7:",
        "18 AWG; F2-8: 16 AWG; the F0 rung: 300 V insulation; everything else: 20 AWG.",
        "PE home runs of the frame, the DIN rails and the TB6600 cases go to the ground bars (sheet 4).",
        "0 V meets PE only at star S, by its one wire to the lower ground bar.",
        "Open: tower common polarity, lid feed, valve coil, servo 6 V rating, J11 logic supply, and the",
        "5 V PSU's current for the Pi 5 (5.1 V, 5 A)."]
    if deck == "lower":
        return common + [
            "Mains duct: a separator between the 110 VAC wires and the PSU's DC and PE leads. Every 110 VAC",
            "terminal finger-safe or covered (ADR-0013). Fuses: F2-1 to F2-7 5 A, F2-8 10 A, F2-9 3 A,",
            "F2-10 and F2-11 2 A; F1-2, F1-4 and F1-5 3 A; F0 1 A T. The PSU's terminal order is assumed."]
    return common + [
        "Motor cables: shield to the clamp bar; six leave by the upper left grommet and one by the upper",
        "right one: pick which on the bench. Each TB6600: PUL-, DIR- and ENA- jumpered to COM at the driver.",
        "The tower cable leaves X7 by the upper right grommet, as sheet 3 has it, so it crosses the deck",
        "behind every rail; the upper left grommet, beside X7, would save most of that run.",
        "1 k from 5V to 43 and 100 nF from 40 to GND on the Mega's screw shield."]


def BuildDeckWiring(deck):
    """Sheet 2A (lower deck) or 2B (upper deck)."""
    sh, d, use, bands = DeckSheet(deck)
    lower = deck == "lower"
    DrawFrame(sh, "RMR control panel: %s deck wiring" % deck,
              ("Lower deck, on the base plate: 110 VAC and 24 V power. " if lower else
               "Upper deck, on the upper plate: drives, logic and field terminals. ") +
              "Sheet 1's circuits on the parts of sheet 3, every wire from terminal to terminal.")
    DeckExits(d, ExitNotes)
    if lower:
        for key in ("FB2", "FB1"):
            for i in range(12):
                x, y = d.Ends["%s.%d" % (key, i + 1)][1:3]
                amps = FuseAmps[key][i]
                lab = "F%s-%d  %s" % (key[2], i + 1, FuseUse[key][i]) + ("  %s A" % amps if amps else "")
                d.Sh.Text(x + 0.33, y - 1.2, lab, size=0.95, anchor="start", rot=-90,
                          fill="#555" if FuseUse[key][i] == "spare" else None)
    cx, cw = 256.0, 94.0
    y = WireLegend(sh, cx, 30.0, cw)
    y = SlotTable(sh, cx, y + 3.4)
    sh.Text(cx, y + 2.6, "Notes", size=2.0, weight="bold")
    for i, s2 in enumerate(WireNotes(deck)):
        sh.Text(cx, y + 5.4 + i * 1.75, s2, size=1.2)
    TitleBlock(sh, 256, 186, 92, 21.5, [
        "RMR control panel: %s deck wiring" % deck,
        "Sheet 2%s (2%s: %s deck). Legal 14 x 8.5 in, landscape, 100 %%." % (("A", "B", "upper") if lower else
                                                                            ("B", "A", "lower")),
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-19 (issue #164).",
        "Status: design, not yet built or tested.",
        "Circuits: sheet 1. Positions: sheet 3. Frame and PE: sheet 4.",
    ])
    return sh


# ---- sheet 2C: names and terminals

# What each name on sheets 1, 2A and 2B means and where it sits, then the terminal plan: what lands on
# every terminal block and bus, read from the same wire lists that draw sheets 2A and 2B (LowerWiring(),
# UpperWiring(), SlotWires()), so the plan cannot drift from the drawings. Only the field side of a
# terminal (what the cable meets outside the box) is written here by hand, in FieldUse.

NameParts = [
    ("Lower deck: 110 VAC and 24 V power", [
        ("Q0", "switch on the IEC inlet: isolates the mains", "back wall"),
        ("X0", "mains in: L, L, N, N, PE from the inlet", "110 V rail"),
        ("F0", "fuse holder, 1 A T: feeds the K1 rung", "110 V rail"),
        ("K1", "110 VAC contactor HC1-63: mains to the 24 V PSU, coil by S1", "110 V rail"),
        ("X1", "door 110 V: out to S1 and H1 on the panel", "110 V rail"),
        ("PE", "4 ground blocks: inlet PE, PSU FG, door plate, lower bar", "110 V rail"),
        ("PSU", "24 V 1200 W supply, lying flat, fan to the right wall", "110 VAC area"),
        ("FB1", "12-way fuse module: +24 V always on", "fuse rail"),
        ("FB2", "12-way fuse module: +24 V cut by the E-stop (behind K2)", "fuse rail"),
        ("K2", "24 V contactor BMC7-25U: 1-2 and 3-4 in series feed FB2, 5-6 seal in, 7-8 tell Mega pin 43 "
               "that motor power is on", "24 V rail"),
        ("star S", "the 0 V star at the PSU's -V; the only 0 V to PE bond", "24 V rail"),
        ("0V-P 1, 2", "0 V power buses, linked: drivers, ODrive, K2 coil, loads", "24 V rail"),
        ("servo PSU", "6 V DC-DC for the gripper and lid servos", "beside 24 V rail"),
        ("5 V PSU", "feeds the Pi at the operator panel", "24 V row, back"),
        ("ground bar", "lower PE bar on the base plate's PE stud", "behind servo PSU"),
    ]),
    ("Upper deck: drives, logic, field terminals", [
        ("X2", "E-stop latch: the door cable from S2 and S3", "field rail"),
        ("X4", "endstops: a signal and a common for each axis", "field rail"),
        ("X5", "servos: 6 V, 0 V and signal for the gripper and lid", "field rail"),
        ("X6", "lid (UV array, switch S5) and the argon valve", "field rail"),
        ("X7", "status tower: red, amber, green, buzzer, common", "field rail"),
        ("X8", "spare (was the screen supply and the home button)", "field rail"),
        ("Mega", "Arduino Mega 2560 on a screw shield; runs on the Pi's USB", "logic rail"),
        ("0V-S", "signal 0 V bus, 9 linked: driver COMs, Mega GND, endstops", "logic rail"),
        ("0V-S2", "second 0V-S group: SSR input returns, S5 return", "logic rail"),
        ("SSR-UV", "DC solid-state relay: Mega pin 4 switches the UV array", "SSR rail"),
        ("SSR-valve", "DC solid-state relay: Mega pin 42 switches the argon valve", "SSR rail"),
        ("tower R A G", "DC SSRs: Pi GPIO 5, 6, 13 switch the red, amber, green lamps", "SSR rail"),
        ("buzzer", "DC SSR: Pi GPIO 26 switches the tower's buzzer", "SSR rail"),
        ("X ... C", "TB6600 drivers: X, Y1, Y2 (follows Y), Z, A (filter feed), B (syringe height), "
                    "C (syringe)", "drivers rail"),
        ("shield clamp", "grips the motor cables' shields, bonded to PE", "past the drivers"),
        ("ground bar", "upper PE bar on the upper plate's PE stud", "behind back run"),
    ]),
    ("Outside the box (sheet 1)", [
        ("S1, H1", "panel knob that switches K1 on; H1 its lamp, lit while K1 is in", "operator panel"),
        ("S2", "E-stop mushroom: NC1 drops K2, NC2 tells the Pi (GPIO 20)", "operator panel"),
        ("S3", "Reset push button (NO): pulls K2 in after an E-stop", "operator panel"),
        ("S4", "lid switch in series with the UV array: closed = lid shut", "lid"),
        ("S5", "lid switch to Mega pin 39 (UV_LID_INTERLOCK, off for now)", "lid"),
        ("D1", "1N4007 across the argon valve's coil, band to +", "at the valve"),
        ("Pi", "Raspberry Pi 5 with the touch screen, runs rmr_bridge.py", "operator panel"),
        ("ODrive", "ODrive S1 spin coater drive; J11 is its UART", "spin coater base"),
        ("X, Y (nodes)", "E-stop latch nodes: X after NC1, Y after S3 (sheet 1, rung B)", ""),
    ]),
]

NameEntries = [
    ("UL", "upper left grommet: field cables X4, X5, X6"),
    ("ULM", "upper left grommet 2: 6 motor cables, gantry PE"),
    ("UF", "upper front grommet: Mega USB, J11, Pi GPIO"),
    ("UR", "upper right grommet: X7 tower, 1 motor cable"),
    ("LL", "lower left grommet: ODrive 24 V, Pi 5 V, door cable"),
    ("inlet", "IEC inlet with switch Q0, back panel"),
    ("gland", "M20 gland, back panel: door 110 V cable"),
    ("slot 1", "upper plate: driver +V and 0 V"),
    ("slot 2", "upper plate: SSR feeds, returns, servo 6 V, PE link"),
    ("slot 3", "upper plate: E-stop latch, pin 43, door cable"),
]

NameAbbrev = [
    ("PE", "protective earth"), ("FG", "the PSU's frame ground (earth) terminal"),
    ("NC, NO", "normally closed, normally open contact"), ("SSR", "solid-state relay"),
    ("COM", "common"), ("PUL, DIR, ENA", "a TB6600's step, direction, enable inputs"),
    ("F1-n, F2-n", "fuse n of FB1, of FB2"), ("0V-P, 0V-S", "0 V power, 0 V signal"),
    ("GPIO", "a Pi input/output pin (BCM numbers)"), ("J11", "the ODrive's isolated UART connector"),
    ("RX2, TX2", "the Mega's Serial2 pins (17, 16)"), ("USLKG 5", "DIN ground terminal block"),
    ("UK 2.5 B", "DIN feed-through terminal block"), ("TS35", "35 mm top-hat DIN rail"),
    ("SJOOW", "oil-resistant portable cord, 300 V"), ("AWG", "American wire gauge"),
]

# The field side of each terminal: what the cable meets outside the box, by (block, terminal).
FieldUse = {}
for _i, (_ax, _pin) in enumerate(EndstopPins):
    FieldUse[("X4", _i + 1)] = "endstop %s signal" % _ax
    FieldUse[("X4", _i + 7)] = "endstop %s common" % _ax
FieldUse.update({
    ("X5", 1): "gripper servo +6 V", ("X5", 2): "lid servo +6 V", ("X5", 3): "gripper servo 0 V",
    ("X5", 4): "lid servo 0 V", ("X5", 5): "gripper servo signal", ("X5", 6): "lid servo signal",
    ("X6", 1): "S4, then the UV array +", ("X6", 2): "UV array -", ("X6", 3): "lid switch S5",
    ("X6", 4): "S5's other side", ("X6", 5): "argon valve + (D1 across)", ("X6", 6): "argon valve -",
    ("X7", 1): "tower red", ("X7", 2): "tower amber", ("X7", 3): "tower green", ("X7", 4): "tower buzzer",
    ("X7", 5): "tower common",
    ("X2", 1): "+24 V to S2 NC1", ("X2", 2): "NC1 out, S3 in (node X)", ("X2", 4): "S3 out (node Y)",
    ("X2", 6): "spare: NC2 is wired at the panel", ("X2", 7): "spare",
    ("X0", 1): "L from the inlet", ("X0", 3): "N from the inlet", ("X0", 5): "PE from the inlet",
    ("X1", 1): "to S1", ("X1", 2): "from S1: K1 coil, H1", ("X1", 3): "N to H1",
    ("PE", 3): "door plate PE", ("0V-S", 8): "ODrive J11 GND", ("0V-P 2", "OD"): "ODrive DC-",
})


def NameEnd(name):
    """A wire end as the terminal plan writes it."""
    if name in ("S1", "S2", "S3"):
        return "slot " + name[1]
    if name == "LL":
        return "LL"
    if name == "ULM":
        return "ULM"
    if "#" in name:
        return name.split("#")[0]
    if "." not in name:
        return "shield clamp" if name.startswith("clamp") else name
    key, term = name.split(".", 1)
    if key == "MEGA":
        return "Mega " + ({"GND": "GND", "USB": "USB"}.get(term) or
                          (term[1:] + " signals" if term.startswith("g") else term))
    if key == "PSU":
        return "PSU " + {"V+a": "+V", "V+b": "+V", "V-a": "-V", "V-b": "-V"}.get(term, term)
    if key in DriveAxes:
        return "driver %s %s" % (key, term)
    if key in ("FB1", "FB2"):
        return "%s %s" % (key, term) if term == "IN" else "F%s-%s" % (key[2], term)
    for bus, text in (("0V-S2", "0V-S2"), ("0V-S", "0V-S"), ("0V-P 2", "0V-P 2"), ("0V-P", "0V-P 1"),
                      ("Star S", "star S"), ("bar", "ground bar"), ("clamp", "shield clamp")):
        if key == bus:
            return text
    if key in SsrNames:
        return "%s %s" % (key, term.replace("OUT", "out ").replace("IN", "in ").replace("+", "+").strip())
    if key[0] == "X" or key == "PE":
        return "%s %s" % (key, term.rstrip("ab"))
    return "%s %s" % (key, term)


def TerminalPlan(d):
    """{(part, terminal): [(where the other end goes, by)]} for one deck; by is the slot or the
    grommet a wire passes, or ''. A wire to a slot is followed to its end on the other deck."""
    slotUp = dict(((s, b), a) for s, _, a, b, _ in SlotWires())
    slotLo = dict(((s, a), b) for s, _, a, b, _ in SlotWires())
    out = {}
    for w in d.Wires:
        for here, there in ((w["a"], w["b"]), (w["b"], w["a"])):
            if here not in d.Ends or d.Ends[here][0] != "t" or "#" in here:
                continue
            key, term = here.split(".", 1)
            if there in ("S1", "S2", "S3"):
                s = int(there[1])
                far = slotUp.get((s, here)) if d.Deck == "upper" else slotLo.get((s, here))
                text, by = (NameEnd(far) if far != "LL" else "door cable, LL"), "slot %d" % s
            elif "#" in there or there in ("LL", "ULM"):
                text, by = None, NameEnd(there)
            else:
                text, by = NameEnd(there), ""
            out.setdefault((key, term), []).append((text, by))
    return out


def Wrap(s, width):
    return textwrap.wrap(s, width) or [""]


def BuildNomenclature():
    """Sheet 2C: names, the terminal plan, fuses, cable entries and abbreviations."""
    sh = Sheet("RMR control panel names and terminals")
    DrawFrame(sh, "RMR control panel: names and terminals",
              "Sheet 2C: what each name on sheets 1, 2A and 2B is and where it sits, and what lands on every "
              "terminal. The terminal plan is read from the wire lists that draw sheets 2A and 2B.")
    lead, size = 2.4, 1.8
    perChar = 0.53 * size              # average width of a character of Arial at this size, mm
    cols = [8.0, 95.0, 182.0, 268.0]       # four columns, each 84 mm wide

    class Cursor:
        col, y = 0, 22.0

    def Need(n):
        bottom = 207.0 if Cursor.col < 2 else 183.0       # columns 3 and 4 stop above the title block
        if Cursor.y + n * lead > bottom:
            Cursor.col += 1
            Cursor.y = 22.0
            if Cursor.col >= len(cols):
                raise ValueError("sheet 2C: the names run off the page")

    def Break():
        Cursor.col += 1
        Cursor.y = 22.0

    def Head(text, keep=0):
        """A heading, kept in one column with the keep rows that follow it."""
        Need(2 + keep)
        Cursor.y += 1.2 if Cursor.y > 22.0 else 0.0
        sh.Text(cols[Cursor.col], Cursor.y, text, size=2.3, weight="bold")
        Cursor.y += lead + 0.6

    def Row(cells, bold0=True, fill=None):
        """cells: [(dx, text, width)] in the current column, dx and width in mm; wraps each cell."""
        wrapped = [(dx, Wrap(t, max(4, int(wd / perChar)))) for dx, t, wd in cells]
        k = max(len(lines) for _, lines in wrapped)
        Need(k)
        x0 = cols[Cursor.col]
        for j, (dx, lines) in enumerate(wrapped):
            for i, s2 in enumerate(lines):
                TextFill(sh, x0 + dx, Cursor.y + i * lead, s2, size, fill or "#000",
                         weight="bold" if (j == 0 and bold0) else "normal")
        Cursor.y += k * lead

    for title, rows in NameParts:
        Head(title)
        for name, what, where in rows:
            Row([(0.0, name, 17.0), (18.0, what, 46.0), (65.0, where, 19.0)])
    lo, up = DeckSheet("lower")[1], DeckSheet("upper")[1]
    plans = {"lower": TerminalPlan(lo), "upper": TerminalPlan(up)}
    Head("Terminal plan", keep=12)
    Row([(0.0, "No.", 5.0), (5.0, "label", 7.0), (12.5, "in the box (by)", 38.0), (52.0, "field side (by)", 32.0)],
        fill="#555")
    blocks = [("upper", "X2"), ("upper", "X4"), ("upper", "X5"), ("upper", "X6"), ("upper", "X7"), ("upper", "X8"),
              ("upper", "0V-S"), ("upper", "0V-S2"), ("lower", "X0"), ("lower", "X1"), ("lower", "PE")]
    for deck, key in blocks:
        d = lo if deck == "lower" else up
        labels, bridges = d.Labels[key]
        Head("%s  (%s deck)" % (key, deck), keep=len(labels) + 2)
        for n, lab in enumerate(labels, 1):
            first = [i + 1 for i, j in bridges if i + 1 < n <= j + 1]
            inside, field, by = [], FieldUse.get((key, n), ""), set()
            for side in ("a", "b"):
                for text, via in plans[deck].get((key, "%d%s" % (n, side)), []):
                    if text is None:
                        by.add(via)
                    else:
                        inside.append(text + (" (%s)" % via if via else ""))
            if by:
                field = (field + " " if field else "") + "(%s)" % ", ".join(sorted(by))
            if not inside and first:
                inside = ["bridged to %d" % first[0]]
            Row([(0.0, str(n), 5.0), (5.0, lab, 7.0), (12.5, "; ".join(inside) or "-", 38.0),
                 (52.0, field or "-", 32.0)])
    Head("Buses on the lower deck")
    for key, title in (("Star S", "star S"), ("0V-P", "0V-P 1"), ("0V-P 2", "0V-P 2")):
        ends = []
        for (k, term), lst in sorted(plans["lower"].items()):
            if k == key:
                ends += [t + (" (%s)" % v if v else "") if t else "%s (%s)" % (FieldUse.get((k, term), "out"), v)
                         for t, v in lst]
        Row([(0.0, title, 11.0), (12.5, "; ".join(ends), 71.0)])
    Head("Fuses")
    for fb in ("FB1", "FB2"):
        uses = ["%s-%d %s%s" % ("F" + fb[2], i + 1, FuseUse[fb][i], (" (%s A)" % FuseAmps[fb][i]) if FuseAmps[fb][i] else "")
                for i in range(12)]
        Row([(0.0, fb, 6.0), (7.0, ", ".join(uses), 77.0)])
    Row([(0.0, "F0", 6.0), (7.0, "1 A T, 5 x 20 mm: the K1 rung (S1, K1 coil, H1)", 77.0)])
    Break()
    Head("Cable entries and slots")
    for name, what in NameEntries:
        Row([(0.0, name, 9.0), (10.0, what, 74.0)])
    Head("Abbreviations")
    for name, what in NameAbbrev:
        Row([(0.0, name, 18.0), (19.0, what, 65.0)])
    TitleBlock(sh, 256, 186, 92, 21.5, [
        "RMR control panel: names and terminals",
        "Sheet 2C (2A, 2B: the decks; 2D: the panel). Legal 14 x 8.5 in, 100 %.",
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-20 (issue #171).",
        "Status: design, not yet built or tested.",
        "Circuits: sheet 1. Positions: sheet 3. Wiring: sheets 2A, 2B.",
    ])
    return sh


# ---- sheet 2D: the operator panel

# A render of the operator panel as it might look, seen from the front: the 10 in touch screen with the
# Pi behind it, S1 (the power knob, its H1 lamp inside), S2 (the E-stop) and S3 (Reset), as ordered on
# 2026-09-14: a 22 mm latching rotary selector with a green 110 V lamp, a 2NC red mushroom, and a blue
# momentary button. The screen shows the Touch UI's Jog tab. Sizes are assumed (OpPanel): the screen is
# a generic 10.1 in HDMI module and the housing is not designed yet. Beside it, dashed and faint, a
# future button bank: rmr_bridge.py already maps physical buttons to G-code (pi-panel/rmr_io.example.json),
# but none is wired or bought.
OpScale = 1.5                                      # real mm per paper mm
OpPanel = (360.0, 220.0)                           # housing front, assumed
OpScreen = (15.0, 25.0, 257.0, 170.0)              # screen module: x, y, width, height, assumed (10.1 in)
OpActive = (17.5, 15.0, 222.0, 125.0)              # active area inside the module: dx, dy, width, height
OpFuture = [("HOME ALL", "22", "G28, then M118 RMR:HOMED_ALL", "#228833"),
            ("UV OFF", "23", "M42 P4 S0", "#555555"),
            ("VALVE SHUT", "24", "M42 P42 S0", "#555555")]
OpWiring = [
    ("S1 power knob", "NO, 110 V", "X1 1 in, X1 2 out", "110 V door cable (M20 gland)"),
    ("H1 lamp, in S1", "110 V", "X1 2 and X1 3 (N)", "110 V door cable"),
    ("panel PE", "", "PE 3", "110 V door cable"),
    ("S2 E-stop", "NC1", "X2 1 (+24 V), X2 2 (node X)", "E-stop loop (LL, slot 3)"),
    ("S2 E-stop", "NC2", "Pi GPIO 20 and GND, 1 k to 3V3", "at the panel"),
    ("S3 Reset", "NO", "X2 2 (node X) to X2 3 (node Y)", "E-stop loop (LL, slot 3)"),
    ("touch screen", "HDMI, USB", "Pi 5", "at the panel"),
    ("Pi 5", "5 V in", "5 V PSU (F1-2)", "5 V feed (LL)"),
    ("Pi 5", "USB", "Mega", "USB cable (UF)"),
    ("Pi 5", "GPIO 5, 6, 13, 26", "tower SSRs (GND to their inputs -)", "tower inputs (UF)"),
]
OpDefs = """<defs>
<linearGradient id="opHousing" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#E4E4E4"/><stop offset="1" stop-color="#B8B8B8"/></linearGradient>
<linearGradient id="opBezel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A3A3A"/><stop offset="1" stop-color="#161616"/></linearGradient>
<radialGradient id="opRed" cx=".38" cy=".35" r=".7"><stop offset="0" stop-color="#EE7766"/><stop offset=".55" stop-color="#CC3311"/><stop offset="1" stop-color="#7A1E0A"/></radialGradient>
<radialGradient id="opBlue" cx=".38" cy=".35" r=".7"><stop offset="0" stop-color="#88BBEE"/><stop offset=".6" stop-color="#4477AA"/><stop offset="1" stop-color="#22446A"/></radialGradient>
<radialGradient id="opGreen" cx=".4" cy=".35" r=".7"><stop offset="0" stop-color="#CCEEBB"/><stop offset=".55" stop-color="#228833"/><stop offset="1" stop-color="#11441A"/></radialGradient>
<radialGradient id="opGrey" cx=".38" cy=".35" r=".7"><stop offset="0" stop-color="#DDDDDD"/><stop offset=".6" stop-color="#777777"/><stop offset="1" stop-color="#333333"/></radialGradient>
<radialGradient id="opRing" cx=".5" cy=".5" r=".5"><stop offset=".7" stop-color="#F2F2F2"/><stop offset="1" stop-color="#8C8C8C"/></radialGradient>
</defs>"""


def TextFill(sh, x, y, s, size, fill, anchor="start", weight="normal"):
    """Text in a colour: an inline style, because the sheet's style sheet (text{fill:#000}) overrides a
    fill attribute, so Sheet.Text's fill= draws black."""
    attrs = 'x="%s" y="%s" font-size="%s" style="fill:%s"' % (Fmt(x), Fmt(y), Fmt(size), fill)
    if anchor != "start":
        attrs += ' text-anchor="%s"' % anchor
    if weight != "normal":
        attrs += ' font-weight="%s"' % weight
    sh.TextParts.append("<text %s>%s</text>" % (attrs, Esc(s)))


def BuildOperatorPanel():
    """Sheet 2D: the operator panel rendered from the front, its wiring, and the future button bank."""
    sh = Sheet("RMR operator panel")
    DrawFrame(sh, "RMR control panel: operator panel",
              "Sheet 2D: how the operator panel might look from the front, at 1:1.5 with assumed sizes, and what "
              "each control wires to. The dashed bank beside it is a future feature.")
    sh.Add(OpDefs)
    X0, Y0, S = 14.0, 27.0, OpScale

    def P(x, y):
        return X0 + x / S, Y0 + y / S

    def Rect(x, y, w, h, fill, stroke="#000", sw=0.3, rx=0.0, extra=""):
        px, py = P(x, y)
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" stroke="%s" stroke-width="%s"%s/>'
               % (Fmt(px), Fmt(py), Fmt(w / S), Fmt(h / S), Fmt(rx / S), fill, stroke, Fmt(sw), extra))

    def Disc(x, y, d, fill, stroke="#000", sw=0.25, extra=""):
        px, py = P(x, y)
        sh.Add('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="%s" stroke-width="%s"%s/>'
               % (Fmt(px), Fmt(py), Fmt(d / 2 / S), fill, stroke, Fmt(sw), extra))

    def Label(x, y, lines, size=1.6, fill="#000", bold0=True):
        px, py = P(x, y)
        for i, s2 in enumerate(lines):
            TextFill(sh, px, py + i * size * 1.25, s2, size if i == 0 else size * 0.85, fill, anchor="middle",
                     weight="bold" if (i == 0 and bold0) else "normal")

    def Plate(x, y, w, lines):
        Rect(x - w / 2, y, w, 9.5 + 4.5 * (len(lines) - 1), "#FFFFFF", sw=0.2, rx=1.5)
        Label(x, y + 6.0, lines, size=1.45)

    W, H = OpPanel
    # housing, screen module, active area
    Rect(0, 0, W, H, "url(#opHousing)", sw=0.4, rx=8.0)
    sx, sy, sw_, sh_ = OpScreen
    Rect(sx, sy, sw_, sh_, "url(#opBezel)", sw=0.3, rx=4.0)
    ax, ay, aw, ah = sx + OpActive[0], sy + OpActive[1], OpActive[2], OpActive[3]
    Rect(ax, ay, aw, ah, "#1E1E24", stroke="#000", sw=0.2)
    # the Touch UI's Jog tab, roughly as it draws in its tol-dark theme
    Rect(ax, ay, aw, 13.0, "#2B2B33", stroke="none", sw=0)
    Label(ax + 22.0, ay + 8.5, ["RMR Touch"], size=1.7, fill="#FFFFFF")
    Rect(ax + aw - 46.0, ay + 3.0, 42.0, 7.5, "#4477AA", stroke="none", sw=0, rx=2.0)
    Label(ax + aw - 25.0, ay + 8.2, ["Connected"], size=1.3, fill="#FFFFFF")
    Label(ax + aw - 92.0, ay + 8.5, ["X 385.00  Y 120.00  Z 10.00"], size=1.2, fill="#BBCCEE", bold0=False)
    tabs = ["Jog", "Recipe", "Log", "Spin", "Console", "Program", "Advanced"]
    tw = aw / len(tabs)
    for i, t in enumerate(tabs):
        Rect(ax + i * tw + 0.8, ay + 14.5, tw - 1.6, 9.0, "#4477AA" if i == 0 else "#33333C", stroke="none", sw=0, rx=1.5)
        Label(ax + (i + 0.5) * tw, ay + 20.6, [t], size=1.25, fill="#FFFFFF", bold0=i == 0)
    cx, cy, b = ax + 62.0, ay + 72.0, 22.0
    for dx, dy, arrow in ((0, -1, "Y+"), (0, 1, "Y-"), (-1, 0, "X-"), (1, 0, "X+")):
        Rect(cx + dx * (b + 3.0) - b / 2, cy + dy * (b + 3.0) - b / 2, b, b, "#4477AA", stroke="none", sw=0, rx=3.0)
        Label(cx + dx * (b + 3.0), cy + dy * (b + 3.0) + 2.5, [arrow], size=1.7, fill="#FFFFFF")
    Rect(cx - b / 2, cy - b / 2, b, b, "#228833", stroke="none", sw=0, rx=3.0)
    Label(cx, cy - 0.5, ["HOME", "ALL"], size=1.25, fill="#FFFFFF")
    zx = ax + 135.0
    for i, t in enumerate(("Z up", "Z down")):
        Rect(zx, ay + 38.0 + i * 31.0, 30.0, 26.0, "#4477AA", stroke="none", sw=0, rx=3.0)
        Label(zx + 15.0, ay + 53.5 + i * 31.0, [t], size=1.4, fill="#FFFFFF")
    for i, t in enumerate(("Step  1 mm", "Feed  3000 mm/min", "A  B  C axes")):
        Rect(ax + 172.0, ay + 38.0 + i * 21.0, 44.0, 16.0, "#33333C", stroke="none", sw=0, rx=2.0)
        Label(ax + 194.0, ay + 48.0 + i * 21.0, [t], size=1.2, fill="#DDDDDD", bold0=False)
    Label(sx + sw_ / 2, sy + sh_ + 9.0, ["10.1 in HDMI touch screen, Pi 5 behind it (Touch UI, Jog tab)"], size=1.5,
          bold0=False)

    # the controls column: E-stop on its yellow plate, Reset, the power knob with its lamp
    kx = 316.0
    Disc(kx, 52.0, 62.0, "#EEDD88", sw=0.3)
    Disc(kx, 52.0, 34.0, "url(#opRing)", sw=0.2)
    Disc(kx, 52.0, 42.0, "url(#opRed)", sw=0.35)
    Label(kx, 47.0, ["EMERGENCY"], size=1.15, fill="#FFFFFF")
    Label(kx, 58.5, ["STOP"], size=1.15, fill="#FFFFFF")
    Plate(kx, 86.0, 50.0, ["S2  E-STOP", "push to stop, twist to release"])
    Disc(kx, 124.0, 30.0, "url(#opRing)", sw=0.25)
    Disc(kx, 124.0, 22.0, "url(#opBlue)", sw=0.3)
    Plate(kx, 142.0, 50.0, ["S3  RESET", "starts the motors after an E-stop"])
    Disc(kx, 178.0, 30.0, "url(#opRing)", sw=0.25)
    Disc(kx, 178.0, 23.0, "url(#opGreen)", sw=0.3)
    Rect(kx - 3.0, 168.0, 6.0, 20.0, "#1C3A20", stroke="none", sw=0, rx=2.5, extra=' transform="rotate(45 %s %s)"'
         % tuple(Fmt(v) for v in P(kx, 178.0)))
    Label(kx - 20.0, 170.0, ["0"], size=1.4)
    Label(kx + 20.0, 170.0, ["I"], size=1.4)
    Plate(kx, 195.0, 50.0, ["S1  POWER, H1 lamp", "on: K1 in, lamp lit"])

    # the future button bank, dashed and faint, off to the right of the panel
    fx, fy, fw, fh = W + 30.0, 20.0, 82.0, 150.0
    Rect(fx, fy, fw, fh, "url(#opHousing)", stroke="#000", sw=0.35, rx=6.0,
         extra=' fill-opacity=".35" stroke-dasharray="1.6 1"')
    for i, (name, pin, cmd, color) in enumerate(OpFuture):
        y = fy + 28.0 + i * 44.0
        Disc(fx + fw / 2, y, 30.0, "url(#opRing)", sw=0.25, extra=' fill-opacity=".45" stroke-dasharray="1 .7"')
        Disc(fx + fw / 2, y, 22.0, color, sw=0.25, extra=' fill-opacity=".4" stroke-dasharray="1 .7"')
        Label(fx + fw / 2, y + 19.0, [name, "GPIO %s: %s" % (pin, cmd)], size=1.3, fill="#555555")
    Label(fx + fw / 2, fy - 4.0, ["FUTURE"], size=1.8, fill="#555555")
    lx, ly = P(W, H / 2)
    rx_, _ = P(fx, 0)
    sh.Wire([(lx + 0.6, ly), (rx_ - 0.6, ly)], "mech")
    px, py = P(fx, fy + fh + 8.0)
    for i, s2 in enumerate(["A physical alternative to the touch screen, for gloved or",
                            "dirty hands. rmr_bridge.py already maps buttons to G-code",
                            "(pi-panel/rmr_io.example.json); none is wired or bought.",
                            "The red and green 22 mm buttons on hand could serve."]):
        TextFill(sh, px, py + i * 2.0, s2, 1.35, "#555555")

    # what each control wires to
    tx, ty = 14.0, 182.0
    sh.Text(tx, ty, "Behind the panel", size=2.1, weight="bold")
    cols = (0.0, 30.0, 58.0, 118.0)
    for j, h in enumerate(("control", "contact", "lands on", "cable (by)")):
        TextFill(sh, tx + cols[j], ty + 3.4, h, 1.3, "#555555")
    for i, row in enumerate(OpWiring):
        for j, s2 in enumerate(row):
            sh.Text(tx + cols[j], ty + 6.2 + i * 2.15, s2, size=1.3, weight="bold" if j == 0 else "normal")
    TitleBlock(sh, 256, 186, 92, 21.5, [
        "RMR control panel: operator panel",
        "Sheet 2D (2A, 2B: the decks; 2C: names). Legal 14 x 8.5 in, 100 %.",
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-20 (issue #171).",
        "Status: concept; housing and sizes not designed yet.",
        "Circuits: sheet 1. Terminals: sheet 2C.",
    ])
    return sh


# ---------------------------------------------------------------- sheets 3 and 4: enclosure

# Envelope from the owner: 18 in deep x 13 in wide x 11 in tall. x = depth (front 0 -> back),
# y = width (left 0 -> right), z = height (floor 0 -> top). Millimetres.
# The 18 x 13 in footprint (457.2 x 330.2) was rounded down to whole millimetres for a cut-to-order
# rail; the rails are now cut in the shop, and 457 also leaves the 18 in sheet edge for the plates.
BoxD, BoxW, BoxH = 457.0, 330.0, 279.4
Frame = 20.0                       # 2020 extrusion on every edge
ZoneFill = {"110": "#FFAABB", "24": "#EEDD88", "drv": "#77AADD", "log": "#99DDFF",
            "fld": "#44BB99", "frame": "#DDDDDD"}   # Paul Tol "light" scheme
PostFill = "#BBBBBB"
LidFill = "#BBCC33"                # Tol light "pear": the lid ring lifts off
PlateFill = "#555555"              # aluminum plate seen edge-on
BracketFill = "#888888"

# Frame stack-up, shared by sheets 3 and 4 and the two plate DXFs. The frame is built like a
# platform-framed house, in two modules. Lower module: the base plate (under the whole frame;
# the box stands on it), the bottom ring and four lower posts. Upper module, built and wired on
# the bench: the mid ring (the platform), the upper plate on top of it, four upper posts
# standing on the plate, and the lid ring. It drops onto four M5 studs in the lower post tops,
# which pass through the mid ring and the plate into sockets in the upper posts and locate the
# two decks to each other.
# Materials (ADR-0009): both decks are 1/16 in 5052-H32, sheared and drilled in the shop through
# a template cut on the laser. The base plate is the floor of the 110 VAC compartment, and the
# upper plate is its ceiling, so neither is plastic. Only the side and top panels are acrylic:
# 1/8 in cast, McMaster 8560K259 (24 x 24 in, trimmed to 24 x 18), which McMaster lists with a
# thickness tolerance of -0.025 to +0.015 in (2.54 to 3.56 mm). The panel screw passes
# ScrewFits() at both ends of that range.
BasePlateT = 1.5875                # 1/16 in 5052-H32 aluminum
UpPlateT = 1.5875                  # the same sheet stock
PanelT = 3.175                     # 1/8 in cast acrylic side and top panels, nominal
# Every part stands on a 35 mm top-hat DIN rail screwed to its deck. EN 60715 makes that rail 7.5 or
# 15 mm tall; the rails on hand measure 7.5 (owner, 2026-10-17): five 18 in slotted aluminum rails
# from the 2026-09-14 order (B0BFFSMBC7, "7.5mm High"; issue #158). Parts without
# DIN feet (TB6600s, the PSUs, the Mega) sit on a printed clip that adds Clip over the rail's top
# face (the 2026-10-15 assumption; measure the first printed clip).
DinRailH = 7.5
Clip = 10.0
PartClear = 3.0                    # from the top of a part to the plate or ring over it
RingClear = 3.0                    # from a rail end or a part to the inside of the frame ring

# Part sizes in mm: (along its DIN rail, across it, listed height, sourced, mount). A sourced size
# is measured or read from a datasheet or a listing's dimension drawing (listings read 2026-10-17)
# and is drawn solid; an assumed size is drawn dashed. The parts are the ones the 2026-10-06 panel
# reference names as delivered. Mount: "rail" stands on the rail's top face, so MountedH() adds
# DinRailH (conservative for parts whose feet hook under the flanges); "clip" adds the rail and
# a printed clip; "incl" already includes the rail (Phoenix gives UK 2,5 heights on NS 35/7,5);
# "plate" stands on the deck itself.
PartSize = {
    "TB6600": (28.0, 96.0, 68.0, True, "clip"),  # measured 96 x 68 x 28
    "SSR": (6.1, 88.1, 70.9, True, "rail"),      # LClCTC SSR-41FDD on its 41F-1Z socket, B0D95FQVL6
                                                 # drawing: 0.24 x 3.47 x 2.79 in
    "K1": (36.1, 82.0, 65.0, True, "rail"),      # BAOMAIN HC1-63, B01J1RFZSY: 1.42 x 3.23 x 2.56 in
    "K2": (36.1, 85.1, 68.1, True, "rail"),      # BAOMAIN BMC7-25U, B0F9YJLLNB: 1.42 x 3.35 x 2.68 in
    "FB1": (153.0, 47.8, 43.2, True, "rail"),    # 12-way like FB2: the 2026-09-14 order brought two
                                                 # 12-position modules, not the 6-way (issue #158)
    "FB2": (153.0, 47.8, 43.2, True, "rail"),    # OONO 12-way, B08PT47SFD drawing
    "Bar": (20.0, 78.0, 53.0, True, "rail"),     # uxcell 1 in 9 out, B07XB8DY7Z: 78 x 53 x 20
    "Term": (6.2, 42.5, 42.0, True, "incl"),     # UK 2.5 B (GUETNEU kit B0GYRMR3W9); Phoenix UK 2,5 B
                                                 # per Conrad: 42.5 x 6.2 x 42
    "PETerm": (6.2, 42.5, 42.0, False, "incl"),  # Erayco USLKG5N ground block, B07M9LDK8F: 6.2 wide;
                                                 # depth and height assumed (issue #158)
    "Cover": (2.0, 42.5, 42.0, False, "incl"),   # end cover between terminal groups
    "Stop": (8.0, 42.5, 42.0, False, "incl"),    # end clamp
    "F0": (18.0, 80.0, 60.0, False, "rail"),     # Dinkle DK4-TF(5x20) fuse holder, B0F1DQLG89 (issue
                                                 # #158); not measured, so this assumed size stays
    "Mega": (99.0, 53.0, 35.0, False, "clip"),   # A000067 board, lying along its rail on a DIN carrier
                                                 # with the screw shield; the 35 is assumed
    "PSU24": (215.0, 115.0, 50.0, False, "clip"),  # 24 V 1200 W lying flat on a 215 x 115 face
                                                 # (ADR-0010); its size is assumed
    "PSU6": (58.0, 63.0, 23.0, True, "clip"),    # servo PSU 63 x 58 x 23, the 63 across its rail
    "PSU5": (76.0, 76.0, 32.0, True, "clip"),    # 5 V PSU 76 x 76 x 32
    "Clamp": (22.0, 124.0, 40.0, False, "plate"),  # motor cable shield clamp bar, assumed
}


def MountedH(key):
    """Height of a part above its deck, rail and clip included."""
    h, mount = PartSize[key][2], PartSize[key][4]
    return h + {"rail": DinRailH, "clip": DinRailH + Clip, "incl": 0.0, "plate": 0.0}[mount]


# Cable entries (owner, 2026-10-17): desk grommets in place of cable glands, large enough to pass a
# USB-B plug, with a slit rubber base: ZLTASYRY 4-pack (B0DYZP4256). Its listing, read on BomDate,
# gives a 2 in (50 mm) hole and 2.36 in overall; its drawing gives the sleeve 1.97 in across and
# the grommet 0.83 in tall with its flange, so about 16 mm of sleeve stands inside a 3 mm wall. A
# 3 mm wall grips the sleeve poorly: a ring cut from the acrylic offcut is pressed onto the sleeve
# behind the wall. Caliper one grommet before cutting; the hole and the ring bore follow it.
GrommetHole = 50.0
GrommetFlange = 2.36 * 25.4
GrommetSleeve = 1.97 * 25.4
RingOD, RingGrip = 64.0, 0.2       # ring bore = sleeve - RingGrip, a press fit: cut one ring first
GrommetsInPack = 4
HeadM5 = 8.7                       # M5 socket head across, as its pack lists it (ISO 4762 allows 8.72
                                   # knurled): each grommet flange clears the panel screws
HeadM5H = 5.0                      # and 5 tall (ISO 4762 k for M5), standing proud of what it holds
EntryEdge = 1.0                    # from a ring's edge to the rail behind the panel
RingName = "Grommet ring"
# One grommet per entry, halfway up its panel's window: (panel, u of the centre, what leaves there,
# the packing study's name for the exit). The owner chose the walls; the study (layout 3b, ADR-0010)
# moved each along its wall: upper left at the middle of the field rail and in the back corridor
# past its end, where the motor cables' back run ends (RunChecks); upper front on the Mega's centre
# line; upper right behind the shield clamp; lower left past the fuse rail's end, in front of the
# 5 V PSU (moved from 292 when FB1 became a 12-way and the fuse rail grew over it: issue #158).
CableEntries = [("Upper side, left", 182.0, "the field cables", "UL"),
                ("Upper side, left", 390.0, "most motor cables", "ULM"),
                ("Upper front", 110.0, "Mega USB, J11, Pi GPIO", "UF"),
                ("Upper side, right", 292.0, "one motor cable, the tower", "UR"),
                ("Lower side, left", 390.0, "ODrive 24 V feed, Pi 5 V feed, E-stop loop", "LL")]

# The lower bay, from the deck to the underside of the upper plate, is the larger of two needs: the
# tallest lower part plus PartClear, which with the PSU lying flat (ADR-0010) is K2's 78.6; and,
# when a lower wall has a cable entry, a window between the bottom ring and the mid ring that holds
# its grommet ring EntryEdge clear of both rails, 66 tall, so a 106 bay. At 78.6 that window is 38.6
# tall: no 50 mm grommet fits a lower wall, and the flat PSU's 50 mm fan face sits partly behind the
# rings. ADR-0011 records the change from ADR-0010's 78.6.
LowerKeys = ("K1", "K2", "FB1", "FB2", "Bar", "Term", "PETerm", "F0", "PSU24", "PSU6", "PSU5")
LowBayParts = max(MountedH(k) for k in LowerKeys) + PartClear
LowBayEntry = (RingOD + 2 * EntryEdge + 2 * Frame
               if any(p.startswith("Lower") for p, _, _, _ in CableEntries) else 0.0)
LowBay = max(LowBayParts, LowBayEntry)
DrvH = MountedH("TB6600")          # TB6600 standing on its 96 x 28 base, on rail and clip
LoDeck = BasePlateT                # lower deck floor: top of the base plate
UpPlate0 = LoDeck + LowBay         # underside of the upper plate = top of the mid ring
UpDeck = UpPlate0 + UpPlateT       # upper deck floor
MidF0 = UpPlate0 - Frame           # underside of the mid ring
TopIn = BoxH - Frame               # underside of the lid ring = upper post tops
LowPostL = MidF0 - LoDeck          # the lower posts set the mid ring height
UpPostL = TopIn - UpDeck
RingLong, RingShort = BoxD - 2 * Frame, BoxW - 2 * Frame
StudL, StudLow = 50.0, 12.0        # M5 x 50 rod (45 is not stocked); thread in a lower post top
StudSock = StudL - StudLow - Frame - UpPlateT  # what reaches into the upper post's socket
# Slots in the upper plate for the rail-leg screw of each upper-post bracket, on the ring
# centre line, 25 to 39 mm from the plate edge, so any 20 mm cast bracket lands in them.
BracketSlotA, BracketSlotB = 25.0, 39.0
# 2020 profile: European-standard 2020 with a 6 mm slot, the same slot as OpenBuilds V-slot
# (Rat Rig lists V-slot 2020 with a 6 mm slot, 6 mm deep), bought as 1000 mm sticks (IXGNIJ
# lists its 2020 series with a 6 mm slot and +/-0.5 mm cuts). The depth, lip, cavity and bore
# are assumed until the first stick is measured. The photo in CAD/ is not this profile: it
# measures a 5.2 to 5.3 mm slot and a 4.3 mm bore, which matches McMaster 5537T101 (5 mm slot,
# 6.3 deep, 4.3 bore), so it no longer sets any value here.
SlotOpen, SlotLip, SlotDepth, SlotCavity, BoreD = 6.0, 1.8, 6.0, 11.0, 4.2
# A screw into a slot T-nut must stop short of the slot floor and still catch three threads of
# the nut, which sits under the lip: SlotLip + 3 pitches <= tip past the rail face <=
# SlotDepth - 0.5. ScrewFits() checks every joint against that before anything is drawn.
WasherM5 = 1.0                     # DIN 125 flat washer thickness
BracketLegT = 3.5                  # cast 2020 corner bracket leg; assumed, measure the first one
BracketW = 17.0                    # across the bracket: the BoM's TOCLUX kit lists 17 x 20 mm
JointScrews = [
    # (joint, thread, length, stack under the head: plate, leg and washers)
    ("base plate to bottom ring, from below", "M4", 6, [BasePlateT]),
    ("upper plate to mid ring", "M4", 6, [UpPlateT]),
    ("upper-post bracket leg through the upper plate", "M4", 10, [BracketLegT, UpPlateT]),
    ("acrylic panel to the frame", "M5", 8, [PanelT]),
    ("aluminum back panel to the frame", "M5", 8, [WasherM5, BasePlateT]),
    # the gantry mount (GantryChecks): through a bracket leg and the panel into a lower post, and
    # through the other leg into a gantry member, each into an M5 roll-in T-nut
    ("mount bracket over the acrylic front panel", "M5", 12, [BracketLegT, PanelT]),
    ("mount bracket over the aluminum back panel", "M5", 10, [BracketLegT, BasePlateT]),
    ("mount bracket to a gantry member", "M5", 8, [BracketLegT]),
]
ThreadPitch = {"M4": 0.7, "M5": 0.8}


def ScrewFits():
    """[(joint, screw, tip past the rail face, threads caught in the T-nut)]; raises if any
    screw would bottom on the slot floor or catch fewer than three threads."""
    out = []
    for joint, thread, length, stack in JointScrews:
        tip = length - sum(stack)
        caught = (tip - SlotLip) / ThreadPitch[thread]
        if tip > SlotDepth - 0.5 or caught < 3.0:
            raise ValueError("%s: %s x %d leaves %.2f mm past the face (%.1f threads)"
                             % (joint, thread, length, tip, caught))
        out.append((joint, "%s x %d" % (thread, length), tip, caught))
    return out


# Screws through a deck plate into a nyloc nut under it (DIN rails, ducts, on either deck): each must
# carry the nut's full height and two threads past it. Under the base plate a tip must end 1 mm over
# the floor where the plate sags most. Under the upper plate the nut and tail hang into the lower bay,
# so they must end PartClear over whatever stands under the rail or duct they hold down (HangGaps).
# DIN 985 makes an M4 nyloc 5.0 mm tall (the TFC, McMaster and RS DIN 985 tables, read 2026-10-18). The
# DIN rail's and the duct's base thicknesses are assumed: measure one of each.
NylocH = {"M4": 5.0}
NylocAcross = 7 / math.cos(math.radians(30))   # M4 nyloc across corners, sharp: 7 across flats (DIN 985)
# The ground bars' screws take a plain nut from the M5 assortment (ISO 4032: 4.7 tall, 8 across flats)
# and an external tooth washer (DIN 6797 A, 0.6 thick; measure one) between bar and plate. The bar is
# not chosen, so sheet 4 gives their length from its foot (OpenScrews). The shield clamp's fasteners
# are taken as M4 into a nyloc, like a duct's.
PlainNutH = {"M5": 4.7}
HexNutAcross = {"M5": 8 / math.cos(math.radians(30))}
ToothWasherT = 0.6
DinRailBaseT = 1.0                 # TS35 x 7.5 steel rail base, assumed
DuctBaseT = 2.5                    # McMaster slotted duct base, assumed
FootH = 0.51 * 25.4                # the rubber feet: the base plate's underside stands this high
DeckPlateT = {"base": BasePlateT, "upper": UpPlateT}
ScrewEnd = 15.0                    # least distance from a rail or duct screw to either end of its run
MidBracket = 20.0                  # the mid ring's inside corner brackets in plan: a square this wide in
                                   # each corner, up to the plate (TOCLUX lists 17 x 20 mm; not measured)
ThroughScrews = [
    # (joint, thread, length, stack under the head over the plate, the DeckSolids kind it holds down)
    ("DIN rail to its plate", "M4", 12, [DinRailBaseT], "rail"),
    ("duct to its plate", "M4", 12, [DuctBaseT], "duct"),
]


def NutFits():
    """[(joint, screw, thread past the nut)]; raises if a screw leaves under two threads past its
    nyloc, if its tip under the base plate ends within 1 mm of the floor where that plate sags most
    (PlateSag), or if its nut and tail under the upper plate end within PartClear of what stands
    under them (HangGaps); OpenScrews checks the plate screws not chosen yet."""
    floor = FootH - PlateSag(E5052, Nu5052, BasePlateT) - 1.0
    out = []
    for joint, thread, length, stack, _ in ThroughScrews:
        tails = {p: length - sum(stack) - t for p, t in DeckPlateT.items()}
        past = min(tails.values()) - NylocH[thread]
        if past < 2 * ThreadPitch[thread]:
            raise ValueError("%s: %s x %d leaves %.1f mm past the nyloc" % (joint, thread, length, past))
        if tails["base"] > floor + 1e-6:
            raise ValueError("%s: %s x %d ends %.2f mm under the base plate, past the %.2f mm that the feet "
                             "leave over the floor less the plate's sag and 1 mm"
                             % (joint, thread, length, tails["base"], floor))
        out.append((joint, "%s x %d" % (thread, length), past))
    HangGaps()
    OpenScrews()
    return out


def UnderUpperPlate():
    """[(box, top, name)]: what stands under the upper plate, top as a height over the lower deck: the
    lower deck's solids, the mid ring and the ring's inside corner brackets (MidBracket)."""
    F = Frame
    under = [(s["box"], s["top"], "lower deck's " + (s["label"] or s["key"] or s["kind"]))
             for s in DeckSolids() if s["deck"] == "lower"]
    under += [(b, LowBay, "mid ring") for b in ((0, 0, BoxD, F), (0, BoxW - F, BoxD, BoxW), (0, 0, F, BoxW),
                                                (BoxD - F, 0, BoxD, BoxW))]
    under += [((x, y, x + MidBracket, y + MidBracket), LowBay, "mid ring's corner bracket")
              for x in (F, BoxD - F - MidBracket) for y in (F, BoxW - F - MidBracket)]
    return under


def TailRoom(fp):
    """(longest tail, name): how far a screw may reach under the upper plate over the plan footprint fp
    (x0, y0, x1, y1) of its nut, PartClear over the tallest thing under it with the plate sagged by
    PlateSag; name says what that is."""
    tops = [(top, name) for (c0, d0, c1, d1), top, name in UnderUpperPlate()
            if c0 < fp[2] and fp[0] < c1 and d0 < fp[3] and fp[1] < d1]
    top, name = max(tops, default=(0.0, "lower deck"))
    return LowBay - PlateSag(E5052, Nu5052, UpPlateT) - PartClear - top, name


def RunFootprint(s, r, onCentre):
    """Plan footprint of the nuts of screws along an upper run s (a DeckSolids dict) whose holes come from
    the final layout: anywhere along it at least ScrewEnd from either end, on its centre line (a DIN
    rail's slots) or across its base with an M4 head on the base, and the nut's half across corners r
    past that. Raises if the run is too short to take a screw ScrewEnd from both ends."""
    x0, y0, x1, y1 = s["box"]
    a0, b0, a1, b1 = (x0, y0, x1, y1) if s["alongX"] else (y0, x0, y1, x1)   # a along the run
    if a1 - a0 < 2 * ScrewEnd:
        raise ValueError("the upper deck's %s is %.1f mm long, too short for a screw %s mm from each end"
                         % (s["label"] or s["block"], a1 - a0, Mm(ScrewEnd)))
    b0, b1 = ((b0 + b1) / 2, (b0 + b1) / 2) if onCentre else (b0 + HeadM4 / 2, b1 - HeadM4 / 2)
    fp = (a0 + ScrewEnd - r, b0 - r, a1 - ScrewEnd + r, b1 + r)
    return fp if s["alongX"] else (fp[1], fp[0], fp[3], fp[2])


def HangGaps():
    """{joint: (gap, upper solid, name)} for each screw through the upper plate: the least height from
    the top of anything under the plate (UnderUpperPlate) to the tip of its tail, with the plate sagged
    by PlateSag, over every upper rail or duct it holds down (RunFootprint: on a rail's centre line,
    across a duct's base). Raises if a run is too short for its screws (RunFootprint) or a gap is under
    PartClear."""
    out = {}
    for joint, thread, length, stack, kind in ThroughScrews:
        tail = length - sum(stack) - UpPlateT
        for u in DeckSolids():
            if u["deck"] != "upper" or u["kind"] != kind:
                continue
            room, name = TailRoom(RunFootprint(u, NylocAcross / 2, kind == "rail"))
            if joint not in out or room + PartClear - tail < out[joint][0]:
                out[joint] = (room + PartClear - tail, u, name)
        if joint in out and out[joint][0] < PartClear - 1e-6:
            gap, u, name = out[joint]
            where = "%.1f mm over" % gap if gap >= 0 else "%.1f mm into" % -gap
            raise ValueError("%s: an %s x %d under the upper deck's %s ends %s the %s; PartClear is %s mm"
                             % (joint, thread, length, u["label"] or u["block"], where, name, Mm(PartClear)))
    return out


def OpenScrews():
    """[(screws, thread, plate, least tail, longest tail, what sets it)] for the plate screws whose
    hardware is not chosen: each ground bar's, at its plate's PE stud and, for the upper bars' other
    screws, anywhere over the lower deck off the mid ring and its brackets; and the shield clamp's,
    anywhere in its box. The least tail carries the nut and two threads past it; the longest ends 1 mm
    over the floor where the base plate sags most, or keeps TailRoom under the upper plate. Raises if no
    length fits."""
    floor = FootH - PlateSag(E5052, Nu5052, BasePlateT) - 1.0
    bar = PlainNutH["M5"] + 2 * ThreadPitch["M5"]
    px, py = PeStud["upper"]
    r = HexNutAcross["M5"] / 2
    c0, d0, c1, d1 = ClampBox()
    rc = NylocAcross / 2
    top, name = max((s["top"], "lower deck's " + (s["label"] or s["key"] or s["kind"]))
                    for s in DeckSolids() if s["deck"] == "lower")
    out = [("ground bar", "M5", "base", bar, floor, "floor"),
           ("ground bar", "M5", "upper", bar) + TailRoom((px - r, py - r, px + r, py + r)),
           ("other ground bar", "M5", "upper", bar,
            LowBay - PlateSag(E5052, Nu5052, UpPlateT) - PartClear - top, name),
           ("shield clamp", "M4", "upper", NylocH["M4"] + 2 * ThreadPitch["M4"])
           + TailRoom((c0 - rc, d0 - rc, c1 + rc, d1 + rc))]
    for what, thread, plate, least, room, name in out:
        if room < least - 1e-6:
            raise ValueError("%s screws through the %s plate: no %s fits; the nut and two threads need %.1f mm "
                             "under the plate, and the %s leaves %.1f" % (what, plate, thread, least, name, room))
    return out


# Plate stiffness. Timoshenko and Woinowsky-Krieger, Theory of Plates and Shells, Table 8: a
# simply supported rectangular plate under a uniform load q sags w_max = alpha q a^4 / D at the
# centre, a the shorter side, alpha by the side ratio b / a. The spans run between the ring's
# slot centre lines. 5052-H32: E 70.3 GPa, Poisson 0.33 (handbook values), in MPa below.
TimoshenkoAlpha = [(1.0, 0.00406), (1.1, 0.00485), (1.2, 0.00564), (1.3, 0.00638), (1.4, 0.00705),
                   (1.5, 0.00772), (1.6, 0.00830), (1.7, 0.00883), (1.8, 0.00931), (1.9, 0.00974),
                   (2.0, 0.01013)]
E5052, Nu5052 = 70300.0, 0.33
DeckLoadKg = 5.0                   # assumed for either deck


def PlateSag(eMpa, nu, t):
    """Centre sag in mm of a deck plate of thickness t on its ring under DeckLoadKg."""
    a, b = BoxW - Frame, BoxD - Frame
    r = b / a
    alpha = None
    for (r0, a0), (r1, a1) in zip(TimoshenkoAlpha, TimoshenkoAlpha[1:]):
        if r0 <= r <= r1:
            alpha = a0 + (a1 - a0) * (r - r0) / (r1 - r0)
            break
    q = DeckLoadKg * 9.81 / (a * b)              # N/mm2
    d = eMpa * t ** 3 / (12 * (1 - nu ** 2))     # N mm
    return alpha * q * a ** 4 / d
PostCentres = [(Frame / 2, Frame / 2), (Frame / 2, BoxW - Frame / 2),
               (BoxD - Frame / 2, Frame / 2), (BoxD - Frame / 2, BoxW - Frame / 2)]
# Layout 3b (ADR-0010): the packing study's arrangement, with the field rail shifted and two upper
# left grommets so that every cable group has a duct path. Upper deck rows across the width (y),
# from the left wall: the field rail, the logic rail (Mega and 0V-S) and the drivers, with an 18 mm
# channel between rows (the study's 9 mm wiring channel on each side) and a 1/2 in duct in each
# channel, then the motor duct RowGap behind the drivers. Slotted wire duct 1 in wide for the motor
# cables (McMaster 7578K14, 1 1/2 in tall), 1/2 in wide for the signal runs (7578K114, 1 in tall).
DuctWide, DuctNarrow, RowGap = 25.4, 12.7, 3.0
DuctTall = {DuctWide: 38.1, DuctNarrow: 25.4}
Chan = 18.0
DriveAxes = ["X", "Y1", "Y2", "Z", "A", "B", "C"]


def UpDeckRows():
    """{row: (y0, y1)} on the upper deck."""
    rows, y = {}, Frame + RingClear
    for name, w, after in [("terminals", PartSize["Term"][1], Chan), ("logic", PartSize["Mega"][1], Chan),
                           ("drivers", PartSize["TB6600"][1], RowGap), ("motor duct", DuctWide, 0.0)]:
        rows[name] = (y, y + w)
        y += w + after
    for duct, a, b in (("field duct", "terminals", "logic"), ("signal duct", "logic", "drivers")):
        c = (rows[a][1] + rows[b][0]) / 2
        rows[duct] = (c - DuctNarrow / 2, c + DuctNarrow / 2)
    return rows


UpRows = UpDeckRows()
DrvX = [Frame + RingClear + 5.0 + 34.0 * i for i in range(7)]   # TB6600 left edges along x, 28 wide
# What the study placed freely (tools/layout_study/layout3b_build.json); everything else follows
# from a neighbour, a channel or the ring, and StudyMatch() holds every block centre to that file.
FieldRail0 = 40.0                  # front end of the field terminal rail
LogicRail0 = 38.0                  # front end of the logic rail; the Mega's USB jack faces the front
R24Rail0 = 87.0                    # front end of the 24 V rail: K2, Star S, the 0V-P bars
PsuX0 = 46.5                       # front face of the 24 V PSU
# The mains strip along the right wall: the PSU lies flat with its fan face RingClear from the
# right ring, toward the vent in the lower right panel; the 110 V rail behind it ends at the back
# ring, where the inlet is. The 110 VAC compartment is a zone of the lower deck, not a box: it runs
# from a line MainsGap outside the mains parts (MainsZoneX, MainsZoneY) to the ring, with no wall on
# that line (the owner's decision of 2026-10-18, ADR-0013; ADR-0012's bent wall is rejected).
# RunChecks() keeps every mains part at least MainsGap inside the line, every low-voltage part and
# duct outside it, and every upper-plate cable slot off it, so nothing low-voltage on the lower deck
# stands within MainsGap of a mains part.
PsuY1 = BoxW - Frame - RingClear
PsuY0 = PsuY1 - PartSize["PSU24"][1]
MainsGap = 10.0                    # from a mains part to anything low-voltage on the lower deck
MainsZoneX, MainsZoneY = PsuX0 - MainsGap, PsuY0 - MainsGap
InletU = (PsuY0 + PsuY1) / 2       # the IEC inlet on the back panel, in line with the 110 V rail
BackRunX = [u for _, u, _, k in CableEntries if k == "ULM"][0]   # the motor cables' back run
# Cable passes through the upper plate (x0, y0, x1, y1), 13 wide with round ends, each beside the
# open end of its duct (a duct's base is solid) and over a free channel of the lower deck, and none
# over the 110 VAC compartment (RunChecks()): 1 rises between the drivers' rail end and the shield
# clamp to the 24 V duct, 2 behind the SSR rail, 3 in front of the Mega, beside X2 and K2.
CableSlots = [(267.5, 156.0, 280.5, 178.0), (290.0, 136.0, 350.0, 149.0), (23.0, 90.0, 36.0, 106.0)]
SlotUse = ["driver 24 V feeds, 0V-P returns", "SSR feeds and returns, servo 6 V",
           "X2, the E-stop latch, pin 43 sense"]
# PE studs: each plate carries its module's ground bar(s) on bare metal (BondPoints()). The base
# plate's stands outside the 110 VAC compartment, in front of the 5 V PSU; the upper plate's behind the
# motor cables' back run, clear of the mid ring's back right corner bracket under the plate, which
# its nut would meet at (425, 300) (OpenScrews, issue #154).
PeStud = {"base": (330.0, 150.0), "upper": (425.0, 280.0)}
HeadM4, HeadM4H = 7.0, 4.0         # M4 socket head across and tall, as the BoM's M4 x 12 pack lists them
                                   # (7.00, 3.91); ISO 4762 allows 7.22 across knurled, 4.0 tall
HoleRing, HoleM5 = 4.5, 5.5        # clearance: M4 into the ring T-nuts; M5 into posts, PE studs
Dia = "\u00d8"


def Mm(v):
    s = "%.1f" % v
    return s[:-2] if s.endswith(".0") else s


def RingHoles():
    """Plate screw holes on the slot centre lines of a ring: 5 per long rail, 3 per short."""
    xs = [Frame + RingLong * (i + 0.5) / 5 for i in range(5)]
    ys = [Frame + RingShort * (i + 0.5) / 3 for i in range(3)]
    c = Frame / 2
    return ([(x, c) for x in xs] + [(x, BoxW - c) for x in xs] + [(c, y) for y in ys]
            + [(BoxD - c, y) for y in ys])


def BracketSlots():
    """Upper-post bracket screw slots, HoleRing wide, along the ring rails beside each post."""
    a, b, c, h = BracketSlotA, BracketSlotB, Frame / 2, HoleRing / 2
    out = []
    for x0, x1 in ((a, b), (BoxD - b, BoxD - a)):
        for yc in (c, BoxW - c):
            out.append((x0, yc - h, x1, yc + h))
    for y0, y1 in ((a, b), (BoxW - b, BoxW - a)):
        for xc in (c, BoxD - c):
            out.append((xc - h, y0, xc + h, y1))
    return out


def PlateGeom(kind):
    """Deck plate seen from above: (outline points, holes [(x, y, dia)], slots [(x0, y0, x1, y1)]).
    Both plates are plain rectangles with a hole at each post: the base plate's take the feet
    screws into the lower posts, the upper plate's pass the locating studs."""
    outline = [(0.0, 0.0), (BoxD, 0.0), (BoxD, BoxW), (0.0, BoxW)]
    holes = [(x, y, HoleM5) for x, y in PostCentres]
    holes += [(x, y, HoleRing) for x, y in RingHoles()]
    if kind in PeStud:
        holes.append(PeStud[kind] + (HoleM5,))
    slots = [] if kind == "base" else list(CableSlots) + BracketSlots()
    return outline, holes, slots


def ObroundPts(x0, y0, x1, y1):
    """A slot with full-round ends as four (x, y, bulge) vertices, counter-clockwise; the
    bulge of 1 on a vertex makes the segment after it a half circle."""
    if x1 - x0 >= y1 - y0:
        r = (y1 - y0) / 2
        return [(x0 + r, y0, 0.0), (x1 - r, y0, 1.0), (x1 - r, y1, 0.0), (x0 + r, y1, 1.0)]
    r = (x1 - x0) / 2
    return [(x1, y0 + r, 0.0), (x1, y1 - r, 1.0), (x0, y1 - r, 0.0), (x0, y0 + r, 1.0)]


def DxfDoc(extent, contours):
    """ASCII DXF R12, millimetres, every entity on layer CUT; extent is the far corner (x, y).
    A contour is ("poly", [(x, y, bulge)]), a closed POLYLINE, or ("circle", x, y, dia)."""
    out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
           "9", "$INSUNITS", "70", "4",
           "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
           "9", "$EXTMAX", "10", "%.4f" % extent[0], "20", "%.4f" % extent[1], "30", "0.0",
           "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for c in contours:
        if c[0] == "poly":
            out.extend(["0", "POLYLINE", "8", "CUT", "66", "1", "10", "0.0", "20", "0.0", "30", "0.0",
                        "70", "1"])
            for x, y, bulge in c[1]:
                out.extend(["0", "VERTEX", "8", "CUT", "10", "%.4f" % x, "20", "%.4f" % y, "30", "0.0"])
                if bulge:
                    out.extend(["42", "%.4f" % bulge])
            out.extend(["0", "SEQEND", "8", "CUT"])
        else:
            _, x, y, d = c
            out.extend(["0", "CIRCLE", "8", "CUT", "10", "%.4f" % x, "20", "%.4f" % y, "30", "0.0",
                        "40", "%.4f" % (d / 2)])
    out.extend(["0", "ENDSEC", "0", "EOF"])
    return "\n".join(out) + "\n"


def DxfPlate(kind):
    """One deck plate as ASCII DXF R12: closed POLYLINEs (outline, slots) and CIRCLEs (holes)
    on layer CUT, millimetres, origin at the plate's front-left corner seen from above."""
    outline, holes, slots = PlateGeom(kind)
    return DxfDoc((BoxD, BoxW), [("poly", [(x, y, 0.0) for x, y in outline])]
                  + [("poly", ObroundPts(*s)) for s in slots]
                  + [("circle", x, y, d) for x, y, d in holes])


# ---------------------------------------------------------------- cut list, panels, PE bonding

StickL, Kerf, EndTrim = 1000.0, 3.0, 2.0   # 1000 mm sticks; saw kerf; one squaring cut per stick


def CutPieces():
    """(part, qty, length, ends) for every rail, cut in the shop from 1000 mm sticks."""
    return [("Lower post", len(PostCentres), LowPostL, "tap M5 both ends"),
            ("Upper post", len(PostCentres), UpPostL,
             "tap M5 top; drill %s5.5 x %d bottom" % (Dia, math.ceil(StudSock) + 2)),
            ("Bottom ring, long", 2, RingLong, "between the lower posts"),
            ("Ring rail, short", 6, RingShort, "bottom, mid and lid ring"),
            ("Mid and lid ring, long", 4, BoxD, "drill %s5.5 through, 10 from ends" % Dia)]


def NestSticks():
    """First-fit decreasing: a list of the lengths cut from each stick. Each piece costs its
    length plus one kerf, and each stick loses EndTrim to its squaring cut."""
    pieces = sorted((L for _, n, L, _ in CutPieces() for _ in range(n)), reverse=True)
    sticks = []
    for L in pieces:
        for s in sticks:
            if sum(p + Kerf for p in s) + L + Kerf <= StickL - EndTrim:
                s.append(L)
                break
        else:
            sticks.append([L])
    return sticks


LowerPanelH = LoDeck + LowPostL    # lower panels: from the floor to the lower post tops
UpperPanelH = BoxH - LowerPanelH   # upper panels: from the mid ring to the top of the lid ring


def EnclosurePanels():
    """(name, qty, width, height, material, screws each). Each panel lies flat on its own outside
    face of the frame, so the corners stay open by one panel thickness. The screws are M5 into
    T-nuts: lower panels into the lower posts (2 per post) and, on the sides, the bottom ring (the
    gantry member backs the front and back panels' bottom edge), upper panels into the upper posts
    (2 per post) and the mid ring. None goes into the lid ring, so the lid ring
    still lifts off alone with the top. Every mains part sits on metal: the lower back panel,
    which carries the inlet and Q0, is cut from the base plate's sheet. Each panel is its own part:
    vents and gland holes make the left and right, or front and back, panels differ."""
    return [("Lower side, left", 1, BoxD, LowerPanelH, "acrylic", 6),
            ("Lower side, right", 1, BoxD, LowerPanelH, "acrylic", 6),
            ("Lower front", 1, BoxW, LowerPanelH, "acrylic", 4),
            ("Lower back: inlet and Q0", 1, BoxW, LowerPanelH, "aluminum", 4),
            ("Upper side, left", 1, BoxD, UpperPanelH, "acrylic", 6),
            ("Upper side, right", 1, BoxD, UpperPanelH, "acrylic", 6),
            ("Upper front", 1, BoxW, UpperPanelH, "acrylic", 5),
            ("Upper back", 1, BoxW, UpperPanelH, "acrylic", 5),
            ("Top, on the lid ring", 1, BoxD, BoxW, "acrylic", 8)]


SheetW, SheetH = 609.6, 457.2      # 24 x 18 in: the acrylic and the aluminum sheets
NestGap = 4.0                      # between parts and from the sheet edge
# The owner's laser (2026-10-17): 813 x 457 mm. A 24 x 18 in sheet goes in with its 24 in side along
# the 813 mm axis; PanelNest() checks that every part also lies inside the cutting area.
LaserBed = (813.0, 457.0)
ShearGap = 1.0                     # the aluminum is sheared, not lasered: no kerf to leave


def NestPlan():
    """The 1/8 in acrylic panels on 24 x 18 in sheets, and the two deck plates (the lower back
    panel beside the base plate) on the aluminum sheets: {sheet: [(panel name, x, y, w, h)]}. Hand-placed; PanelNest()
    proves every placement fits and that each acrylic panel is placed as often as it is used.
    The grommet rings, one per cable entry, take the offcut of acrylic 2, two abreast beside the
    upper side panels."""
    g, a = NestGap, ShearGap
    return {
        "acrylic 1": [("Top, on the lid ring", g, g, BoxD, BoxW),
                      ("Lower side, left", g, 2 * g + BoxW, BoxD, LowerPanelH),
                      ("Lower front", 2 * g + BoxD, g, LowerPanelH, BoxW)],
        "acrylic 2": [("Upper side, left", g, g, BoxD, UpperPanelH),
                      ("Upper side, right", g, 2 * g + UpperPanelH, BoxD, UpperPanelH)]
                     + [(RingName, 2 * g + BoxD + (k % 2) * (RingOD + g), g + (k // 2) * (RingOD + g),
                         RingOD, RingOD) for k in range(len(CableEntries))],
        "acrylic 3": [("Upper front", g, g, UpperPanelH, BoxW),
                      ("Upper back", 2 * g + UpperPanelH, g, UpperPanelH, BoxW),
                      ("Lower side, right", g, 2 * g + BoxW, BoxD, LowerPanelH)],
        "aluminum 1": [("Base plate", a, a, BoxD, BoxW),
                       ("Lower back: inlet and Q0", 2 * a + BoxD, a, LowerPanelH, BoxW)],
        "aluminum 2": [("Upper plate", a, a, BoxD, BoxW)],
    }


def PanelNest():
    """Check NestPlan(); returns the number of acrylic sheets."""
    used = {}
    for sheet, parts in NestPlan().items():
        g = NestGap if sheet.startswith("acrylic") else ShearGap
        for i, (name, x, y, w, h) in enumerate(parts):
            if x < g - 1e-6 or y < g - 1e-6 or x + w > SheetW - g + 1e-6 or y + h > SheetH - g + 1e-6:
                raise ValueError("%s: %s runs off the sheet" % (sheet, name))
            if x + w > LaserBed[0] or y + h > LaserBed[1]:
                raise ValueError("%s: %s lies outside the laser bed" % (sheet, name))
            for name2, x2, y2, w2, h2 in parts[i + 1:]:
                if x < x2 + w2 + g - 1e-6 and x2 < x + w + g - 1e-6 and \
                        y < y2 + h2 + g - 1e-6 and y2 < y + h + g - 1e-6:
                    raise ValueError("%s: %s and %s overlap" % (sheet, name, name2))
            used[name] = used.get(name, 0) + 1
    for name, n, w, h, mat, _ in EnclosurePanels():
        if used.get(name, 0) != n:
            raise ValueError("%s placed %d times, needs %d" % (name, used.get(name, 0), n))
    return sum(1 for s in NestPlan() if s.startswith("acrylic"))


# ---------------------------------------------------------------- panel cut-outs and their DXFs

# Each panel is a part on its own (u, v) axes, millimetres from its corner. A wall panel has v up
# from its bottom edge and u along x (side panels: the front edge at u = 0) or along y (front and
# back panels: the left edge at u = 0); the top has u = x and v = y, like the deck plates. A cut
# panel is the same part seen from either face, so it is turned over to put its u = 0 edge where
# this says. (wall, z of the panel's bottom edge):
PanelWall = {"Lower side, left": ("left", 0.0), "Lower side, right": ("right", 0.0),
             "Lower front": ("front", 0.0), "Lower back: inlet and Q0": ("back", 0.0),
             "Upper side, left": ("left", LowerPanelH), "Upper side, right": ("right", LowerPanelH),
             "Upper front": ("front", LowerPanelH), "Upper back": ("back", LowerPanelH),
             "Top, on the lid ring": ("top", BoxH)}
BackPanel, TopPanel = "Lower back: inlet and Q0", "Top, on the lid ring"
PanelWeb = 2.0                     # least material between two cuts, or between a cut and an edge
PostScrewIn = Frame / 2            # post screws this far from each post end: level with the rings
# The four lid screws (M5 x 35 socket head; ISO 4762 gives an 8.5 mm head, 5 tall) stand on the
# lid ring under the top. The top clears each head and passes the 4 mm key to it.
LidAccess = 10.0
# Vent slots: 4 wide on an 8 mm pitch, so a 4 mm web, kept 4 in from what they serve. 4 mm is
# narrower than the 12 mm test finger of IEC 60529 code 2.
VentW, VentPitch, VentInset = 4.0, 8.0, 4.0
# The cable entries and their grommets are defined with the frame stack, which sizes the lower bay
# to the lower grommet (GrommetHole, RingOD, CableEntries).
# The 24 V PSU lies flat with its fan on the 215 x 50 face toward the right wall (ADR-0010), RingClear
# from the right ring, so the vent goes in the lower right side panel, the outer wall of the 110 VAC
# compartment: full-height slots from the PSU's front face along its length, as many as match the
# fan's area, pi d^2 / 4. Where along that face the fan sits is still to be read off the PSU.
PsuVentPanel, PsuVentSpan = "Lower side, right", (PsuX0, PsuX0 + PartSize["PSU24"][0])
# PLACEHOLDERS, for the owner to supply. Nothing is cut while one is None, and PanelOpen() lists it
# on sheet 4 and on the console.
PsuFanD = None                     # the PSU fan's diameter
# Cut-outs in the aluminum lower back panel: ((u, v) of the centre, ("rect", w, h) or ("round", d),
# [(du, dv, dia)] screw holes about the centre). The inlet mounts with two screws and carries a
# switch; if that switch is 2-pole it is Q0, which then needs no cut-out of its own.
MainsCuts = {"IEC inlet with switch": None}
Q0Cut = None                       # only if the inlet's switch is not 2-pole; the same form
# The back panel's own PE stud (BondPoints), inside the 110 VAC compartment's span of the back
# wall, from the compartment's edge to the right ring.
BackPeStud = (290.0, LoDeck + Frame + 12.0)
MainsSpan = (MainsZoneY, BoxW - Frame)
# The 110 VAC door cable (X1 to the S1 knob, the H1 lamp and the plate PE: sheets 1 and 2) leaves the
# compartment straight through the aluminum back panel, so it never crosses into the low-voltage side
# or shares a grommet with it: an M20 x 1.5 nylon cable gland (6 to 12 mm cable), halfway up the
# window (ADR-0013). (u of the centre, hole, across the locknut's corners, assumed.)
DoorGland = (205.0, 20.5, 30.0)
# The box in the gantry (issue #158, part A). The gantry is 2020 with a 6 mm slot (owner, 2026-10-19),
# so the kit's M5 roll-in T-nuts fit it. Its members run left to right against the box's front and back
# faces, in those faces' planes, and its lower members stand on the same rubber feet as the box, so
# their bottom faces are level with the base plate's underside, z = 0. The owner measured the gaps
# face to face on 2026-10-19: in front, lower member to middle member 230 and middle to top 130; at
# the back, center member to top 38; the front and back top members stand at the same height. The
# front middle member, which can move, goes up to GantryMidGap so the box lifts out (GantryChecks);
# the others stay where they were measured.
GantryMeasured = {"front lower to middle": 230.0, "front middle to top": 130.0, "back center to top": 38.0}
GantryMidGap = 315.0               # front, lower member's top face to the middle member's bottom face
GantryTopZ = Frame + GantryMeasured["front lower to middle"] + Frame + GantryMeasured["front middle to top"]
GantryMembers = [("front", "lower", 0.0), ("front", "middle", Frame + GantryMidGap),
                 ("front", "top", GantryTopZ), ("back", "lower", 0.0),
                 ("back", "center", GantryTopZ - GantryMeasured["back center to top"] - Frame),
                 ("back", "top", GantryTopZ)]
# Four spare cast corner brackets hold the box to the lower members, one at each lower post on the front
# and back faces. The vertical leg lies on the panel, held by that post's bottom panel screw, which moves
# up from PostScrewIn to clear the member; the horizontal leg rests on the member's top face, held by one
# M5 into a roll-in T-nut. The front and back panels lose their bottom ring screw: the member backs the
# panel's bottom edge. The joint only keeps the box in place; it is not structural. BracketHoleIn is a
# hole's distance from the bracket's inside corner, assumed until a bracket is measured.
BracketHoleIn = 10.0
GantryScrewV = Frame + BracketHoleIn
# The member's top face stands on the gantry's own feet, under another load, so its height against the
# box is not exact. The bracket's panel screw therefore passes the panel in a vertical slot MountSlotL
# long, which lets the bracket seat on the member +/- (MountSlotL - HoleM5) / 2 off its drawn height.
MountSlotL = 10.0
# A mains cut-out in the back panel (MainsCuts, Q0Cut) carries a flange outside, assumed this far past
# the cut-out on every side until the part is chosen.
CutFlange = 5.0
# To come out, the box lifts until its feet clear a lower member's top face, then slides forward under
# the front middle member. LiftMargin is the play wanted at each end of that lift.
LiftMargin = 5.0
# PLACEHOLDER, for the owner: the gantry's feet go on M5 screws into roll-in T-nuts in the lower
# members' bottom slots. The screw's length needs the stack under its head inside the foot (the depth of
# the foot's washer under its top face); None until a foot is measured.
GantryFootStack = None


def PanelSpec(name):
    """The EnclosurePanels() row of a panel."""
    for row in EnclosurePanels():
        if row[0] == name:
            return row
    raise KeyError(name)


def PanelWindow(name):
    """(u0, v0, u1, v1): the opening behind a panel, between the frame members it is screwed to."""
    wall, z0 = PanelWall[name]
    if wall == "top":
        return (Frame, Frame, BoxD - Frame, BoxW - Frame)
    span = BoxD if wall in ("left", "right") else BoxW
    if z0 == 0.0:
        return (Frame, LoDeck + Frame, span - Frame, LowerPanelH)
    return (Frame, UpDeck - z0, span - Frame, TopIn - z0)


def PanelScrews(name):
    """(u, v) of each M5 on the slot centre lines. A wall panel: two per post, PostScrewIn from
    the post ends, and one (upper front, upper back) or two (sides) at an even pitch into the bottom
    ring (lower panels) or the mid ring (upper panels). The lower front and back panels have no ring
    screw, and their bottom post screws sit at GantryScrewV, through the mount brackets. The top: three
    per long lid-ring rail between the lid screws, one per short rail."""
    wall, z0 = PanelWall[name]
    c = Frame / 2
    if wall == "top":
        xs = [c + (BoxD - Frame) * k / 4 for k in (1, 2, 3)]
        return ([(x, c) for x in xs] + [(x, BoxW - c) for x in xs]
                + [(c, BoxW / 2), (BoxD - c, BoxW / 2)])
    span = BoxD if wall in ("left", "right") else BoxW
    endWall = wall in ("front", "back")
    if z0 == 0.0:
        low = GantryScrewV if endWall else LoDeck + PostScrewIn
        posts, ring = (low, MidF0 - PostScrewIn), LoDeck + c
    else:
        posts, ring = (UpDeck + PostScrewIn - z0, TopIn - PostScrewIn - z0), MidF0 + c - z0
    n = 0 if endWall and z0 == 0.0 else 1 if endWall else 2
    us = [c + (span - Frame) * k / (n + 1) for k in range(1, n + 1)]
    return [(u, v) for u in (c, span - c) for v in posts] + [(u, ring) for u in us]


def TopVents():
    """Three slots over each TB6600, across its 96 mm depth: (u0, v0, u1, v1) on the top."""
    y0, y1 = UpRows["drivers"]
    out = []
    for x in DrvX:
        for k in (-1, 0, 1):
            uc = x + 14.0 + VentPitch * k
            out.append((uc - VentW / 2, y0 + VentInset, uc + VentW / 2, y1 - VentInset))
    return out


def PsuVent():
    """(panel, slots): full-height slots on PsuVentPanel, VentPitch apart from the PSU's front face,
    as many as match the fan's area. (None, []) while PsuFanD is open."""
    if PsuFanD is None:
        return None, []
    w0, w1, w2, w3 = PanelWindow(PsuVentPanel)
    v0, v1 = w1 + VentInset, w3 - VentInset
    each = VentW * (v1 - v0 - VentW) + math.pi * VentW ** 2 / 4
    n = math.ceil(math.pi * PsuFanD ** 2 / 4 / each)
    u0 = max(PsuVentSpan[0], w0 + VentInset)
    out = [(u0 + k * VentPitch, v0, u0 + k * VentPitch + VentW, v1) for k in range(n)]
    if out[-1][2] > min(PsuVentSpan[1], w2 - VentInset):
        raise ValueError("PSU vent: %d slots for a %s mm fan run past x %s"
                         % (n, Mm(PsuFanD), Mm(PsuVentSpan[1])))
    return PsuVentPanel, out


def GrommetAt():
    """[(panel, u, v, cables)]: each cable entry halfway up its panel's window."""
    out = []
    for panel, u, cables, _ in CableEntries:
        _, w1, _, w3 = PanelWindow(panel)
        out.append((panel, u, (w1 + w3) / 2, cables))
    return out


def MainsGeom():
    """(holes, cut-outs) of the IEC inlet, of Q0 if it has its own, and of the door cable gland, on
    the back panel."""
    holes, polys = [], []
    for cut in list(MainsCuts.values()) + [Q0Cut]:
        if cut is None:
            continue
        (uc, vc), shape, screws = cut
        if shape[0] == "rect":
            w, h = shape[1] / 2, shape[2] / 2
            polys.append([(uc - w, vc - h), (uc + w, vc - h), (uc + w, vc + h), (uc - w, vc + h)])
        else:
            holes.append((uc, vc, shape[1]))
        holes += [(uc + du, vc + dv, d) for du, dv, d in screws]
    _, w1, _, w3 = PanelWindow(BackPanel)
    holes.append((DoorGland[0], (w1 + w3) / 2, DoorGland[1]))
    return holes, polys


def PanelGeom(name):
    """A panel on its (u, v) axes, in the form of PlateGeom(): (outline, holes [(u, v, dia)],
    slots [(u0, v0, u1, v1)], cut-outs [[(u, v)]])."""
    _, _, w, h, _, _ = PanelSpec(name)
    outline = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    wall, z0 = PanelWall[name]
    holes, slots, polys = [], [], []
    for u, v in PanelScrews(name):
        if z0 == 0.0 and wall in ("front", "back") and abs(v - GantryScrewV) < 1e-6:
            slots.append((u - HoleM5 / 2, v - MountSlotL / 2, u + HoleM5 / 2, v + MountSlotL / 2))
        else:
            holes.append((u, v, HoleM5))
    if name == TopPanel:
        holes += [(x, y, LidAccess) for x, y in PostCentres]
        slots += TopVents()
    if name == BackPanel:
        holes.append(BackPeStud + (HoleM5,))
        mh, mp = MainsGeom()
        holes += mh
        polys += mp
    vName, vSlots = PsuVent()
    if vName == name:
        slots += vSlots
    holes += [(u, v, GrommetHole) for p, u, v, _ in GrommetAt() if p == name]
    return outline, holes, slots, polys


def PanelChecks():
    """Raise unless each panel has its screw count; every vent slot lies in its window; each
    grommet ring lies in its panel's window (EntryEdge clear of the rails), each flange clears the
    panel's screw heads, and one ring is nested per grommet; the mains cut-outs
    and the PE stud lie in the back panel's 110 VAC window; the templates fit. Returns the number
    of grommets."""
    for name, _, _, _, _, n in EnclosurePanels():
        if len(PanelScrews(name)) != n:
            raise ValueError("%s: %d screws drawn, %d listed" % (name, len(PanelScrews(name)), n))
    w0, w1, w2, w3 = PanelWindow(TopPanel)
    for u0, v0, u1, v1 in TopVents():
        if u0 < w0 + VentInset or v0 < w1 or u1 > w2 - VentInset or v1 > w3:
            raise ValueError("top vent at u %s runs over the lid ring" % Mm(u0))
    entries = GrommetAt()
    rings = sum(1 for parts in NestPlan().values() for p in parts if p[0] == RingName)
    if rings != len(entries):
        raise ValueError("%d grommet rings nested for %d entries" % (rings, len(entries)))
    for i, (panel, u, v, cables) in enumerate(entries):
        r = RingOD / 2 + EntryEdge - 1e-6
        w0, w1, w2, w3 = PanelWindow(panel)
        if u - r < w0 or v - r < w1 or u + r > w2 or v + r > w3:
            raise ValueError("%s: the grommet ring on %s runs over a rail" % (cables, panel))
        for su, sv in PanelScrews(panel):
            if math.hypot(su - u, sv - v) < (GrommetFlange + HeadM5) / 2 + EntryEdge:
                raise ValueError("%s: the grommet flange on %s meets a panel screw" % (cables, panel))
        for panel2, u2, v2, cables2 in entries[i + 1:]:
            if panel2 == panel and math.hypot(u2 - u, v2 - v) < RingOD + EntryEdge:
                raise ValueError("grommets for %s and %s on %s overlap" % (cables, cables2, panel))
    w0, w1, w2, w3 = PanelWindow(BackPanel)
    holes, polys = MainsGeom()
    for pts in polys + [[(u - d / 2, v - d / 2), (u + d / 2, v + d / 2)] for u, v, d in holes]:
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        if min(us) < max(w0, MainsSpan[0]) or max(us) > min(w2, MainsSpan[1]) or \
                min(vs) < w1 or max(vs) > w3:
            raise ValueError("a mains cut-out leaves the back panel's 110 VAC window")
    u, v = BackPeStud
    if not (max(w0, MainsSpan[0]) + HoleM5 / 2 <= u <= min(w2, MainsSpan[1]) - HoleM5 / 2
            and w1 + HoleM5 / 2 <= v <= w3 - HoleM5 / 2):
        raise ValueError("the back panel's PE stud is not in its 110 VAC window")
    gu, gv, r = DoorGland[0], (w1 + w3) / 2, DoorGland[2] / 2
    if gu - r < max(w0, MainsSpan[0]) or gu + r > min(w2, MainsSpan[1]) or gv - r < w1 or gv + r > w3 \
            or math.hypot(gu - u, gv - v) < r + HoleM5:
        raise ValueError("the door cable gland's locknut leaves the 110 VAC window or meets the PE stud")
    TemplateFits()
    return len(entries)


def PanelOpen():
    """The placeholders still open, each a cut that is not in the DXFs yet."""
    out = []
    if PsuFanD is None:
        out.append("PSU fan diameter: no PSU vent in the lower right side panel")
    out += ["%s: body cut-out and screw spacing" % k for k, cut in MainsCuts.items() if cut is None]
    return out


def MountBrackets():
    """[(wall, u)]: the four mount brackets, one at each lower post on the front and back faces,
    centred on the post's screw line."""
    return [(wall, u) for wall in ("front", "back") for u in (Frame / 2, BoxW - Frame / 2)]


def LowerPanelOf(wall):
    """The lower panel on the front or back wall."""
    return [n for n, (w, z0) in PanelWall.items() if w == wall and z0 == 0.0][0]


def FaceProtrusions(wall):
    """[(what, u0, u1, z0, z1)]: what stands proud of the front or back face, in box z: the panel
    screw heads, the grommet flanges, the back panel's door cable gland, PE stud and mains cut-outs
    (with CutFlange), a panel thicker than the face's lower panel, and the mount brackets."""
    out = []
    plane = BasePlateT if PanelSpec(LowerPanelOf(wall))[4] == "aluminum" else PanelT
    for name, (w, z0) in PanelWall.items():
        if w != wall:
            continue
        short = name.split(":")[0].lower()
        _, _, pw, ph, mat, _ = PanelSpec(name)
        if (BasePlateT if mat == "aluminum" else PanelT) > plane + 1e-6:
            out.append(("%s, proud of the lower panel's plane" % short, 0.0, pw, z0, z0 + ph))
        for u, v in PanelScrews(name):
            out.append(("%s screw at u %s" % (short, Mm(u)), u - HeadM5 / 2, u + HeadM5 / 2,
                        z0 + v - HeadM5 / 2, z0 + v + HeadM5 / 2))
        for p, u, v, cables in GrommetAt():
            if p == name:
                r = GrommetFlange / 2
                out.append(("grommet flange (%s)" % cables, u - r, u + r, z0 + v - r, z0 + v + r))
        if name == BackPanel:
            _, w1, _, w3 = PanelWindow(BackPanel)
            r, gv = DoorGland[2] / 2, (w1 + w3) / 2
            out.append(("door cable gland", DoorGland[0] - r, DoorGland[0] + r, gv - r, gv + r))
            u, v = BackPeStud
            out.append(("PE stud", u - HeadM5 / 2, u + HeadM5 / 2, v - HeadM5 / 2, v + HeadM5 / 2))
            for cutName, cut in list(MainsCuts.items()) + [("Q0", Q0Cut)]:
                if cut is None:
                    continue
                (uc, vc), shape = cut[0], cut[1]
                hw, hh = (shape[1] / 2, shape[2] / 2) if shape[0] == "rect" else (shape[1] / 2, shape[1] / 2)
                out.append(("%s and its flange" % cutName, uc - hw - CutFlange, uc + hw + CutFlange,
                            vc - hh - CutFlange, vc + hh + CutFlange))
    for w, u in MountBrackets():
        if w == wall:
            out.append(("mount bracket at u %s" % Mm(u), u - BracketW / 2, u + BracketW / 2, Frame, 2 * Frame))
    return out


def RectGap(a, b):
    """Least distance between two rectangles (u0, u1, z0, z1); 0 when they touch or overlap."""
    du = max(a[0] - b[1], b[0] - a[1], 0.0)
    dz = max(a[2] - b[3], b[2] - a[3], 0.0)
    return math.hypot(du, dz)


def GantryChecks():
    """Raise unless the box stands in the gantry and lifts out; return what sheet 5 prints.

    Standing: nothing proud of the front or back face meets a gantry member in that face's plane
    (resting on a member's top face is allowed, as the brackets do); each mount bracket lies on its
    post, off its panel's window, with the post's bottom screw through it, and clear of the gland, the
    PE stud and the grommets; the members on a face do not run into each other.
    Lifting out: the box rises until its feet clear a lower member's top face by LiftMargin. Raised that
    far, every protrusion stays LiftMargin under the next member up on its face, and the box's top,
    with the top panel's screw heads, passes LiftMargin or more under the front middle member on the
    way out forward. The room under the back center member is reported, not required.
    Also returns how far the two socket heads on a bracket overlap at BracketHoleIn (0 if they clear)
    and the gantry foot screw's length (None while GantryFootStack is open)."""
    lift = Frame + FootH + LiftMargin
    boxTop = BoxH + PanelT + HeadM5H
    z = {(w, n): z0 for w, n, z0 in GantryMembers}
    out = {"lift": lift, "box top": boxTop}
    for wall in ("front", "back"):
        members = sorted(z0 for (w, _), z0 in z.items() if w == wall)
        for a, b in zip(members, members[1:]):
            if b < a + Frame:
                raise ValueError("the %s gantry members at z %s and %s overlap" % (wall, Mm(a), Mm(b)))
        prot = FaceProtrusions(wall)
        for what, u0, u1, z0, z1 in prot:
            for (w, name), m in z.items():
                if w == wall and z0 < m + Frame - 1e-6 and z1 > m + 1e-6:
                    raise ValueError("%s on the %s face meets the %s member (z %s to %s)"
                                     % (what, wall, name, Mm(m), Mm(m + Frame)))
        top = max(p[4] for p in prot)
        nextUp = min(m for m in members if m > 0.0)
        room = nextUp - (top + lift)
        if room < LiftMargin:
            raise ValueError("lifted %s, the %s face's top protrusion (z %s) comes %s under the member at z %s"
                             % (Mm(round(lift, 1)), wall, Mm(round(top, 1)), Mm(round(room, 1)), Mm(nextUp)))
        out["%s room" % wall] = room
    fwd = z[("front", "middle")] - (boxTop + lift)
    if fwd < LiftMargin:
        raise ValueError("sliding out forward, the box's top (z %s, raised %s) passes %s under the front "
                         "middle member" % (Mm(round(boxTop, 1)), Mm(round(lift, 1)), Mm(round(fwd, 1))))
    out["forward"] = fwd
    out["back exit"] = z[("back", "center")] - (boxTop + lift)
    # The lift that works: the feet clear a lower member's top face, and the top passes under the front
    # middle member; LiftMargin is wanted at each end.
    out["lift band"] = (Frame + FootH, z[("front", "middle")] - boxTop)
    for wall in ("front", "back"):
        high = max(p[4] for p in FaceProtrusions(wall))
        if high > boxTop:
            raise ValueError("something on the %s face reaches z %s, over the box's top (%s), which the "
                             "forward pass is checked against" % (wall, Mm(round(high, 1)), Mm(round(boxTop, 1))))
    off = abs(BracketHoleIn - Frame / 2)
    if off > (SlotOpen - 5.0) / 2:
        raise ValueError("the mount bracket's member-side hole sits %s off the member's slot centre; an M5 "
                         "passes the %s slot opening only within %s" % (Mm(round(off, 2)), Mm(SlotOpen),
                                                                         Mm((SlotOpen - 5.0) / 2)))
    out["mid to top"] = z[("front", "top")] - z[("front", "middle")] - Frame
    for wall, u in MountBrackets():
        name = LowerPanelOf(wall)
        w0, _, w2, _ = PanelWindow(name)
        u0, u1 = u - BracketW / 2, u + BracketW / 2
        if not (u1 <= w0 or u0 >= w2) or u0 < 0.0 or u1 > BoxW:
            raise ValueError("the %s mount bracket at u %s leaves its post" % (wall, Mm(u)))
        if (u, GantryScrewV) not in PanelScrews(name):
            raise ValueError("no panel screw through the %s mount bracket at u %s" % (wall, Mm(u)))
        for what, a0, a1, b0, b1 in FaceProtrusions(wall):
            if what.startswith(("door cable gland", "PE stud", "grommet", "IEC", "Q0")) and \
                    RectGap((u0, u1, Frame, 2 * Frame), (a0, a1, b0, b1)) < EntryEdge:
                raise ValueError("the %s mount bracket at u %s meets the %s" % (wall, Mm(u), what))
    # The panel-side head stands on the vertical leg, BracketHoleIn up from the corner; the member-side
    # head on the horizontal leg, BracketHoleIn out from the panel face. Each reaches BracketLegT +
    # HeadM5H off its leg's rail and HeadM5 / 2 either side of its hole, so they meet in the corner
    # unless BracketHoleIn - HeadM5 / 2 >= BracketLegT + HeadM5H.
    out["head overlap"] = max(0.0, BracketLegT + HeadM5H - (BracketHoleIn - HeadM5 / 2))
    if GantryFootStack is None:
        out["foot screw"] = None
    else:
        lo, hi = SlotLip + 3 * ThreadPitch["M5"], SlotDepth - 0.5
        fit = [L for L in (8, 10, 12, 16, 20, 25) if lo <= L - GantryFootStack <= hi]
        if not fit:
            raise ValueError("no M5 length lands a gantry foot screw %s to %s past the slot face"
                             % (Mm(lo), Mm(hi)))
        out["foot screw"] = fit[0]
    return out


def GantryOpen():
    """What the gantry mount still waits on: listed on sheet 5 and on the console."""
    g, out = GantryChecks(), []
    if g["head overlap"] > 0:
        out.append("mount bracket holes: at %s from the corner the two socket heads overlap %s in the corner, "
                   "as in every frame bracket; measure a bracket" % (Mm(BracketHoleIn), "%.2f" % g["head overlap"]))
    if g["foot screw"] is None:
        out.append("gantry foot screw length: the depth of the foot's washer (GantryFootStack)")
    return out


def NestXform(name, x, y, w, h):
    """Map a panel's (u, v) to its place on a nest sheet; a part laid across turns 90 degrees
    counter-clockwise."""
    _, _, pw, ph, _, _ = PanelSpec(name)
    if abs(w - pw) < 1e-6 and abs(h - ph) < 1e-6:
        return lambda u, v: (x + u, y + v)
    if abs(w - ph) < 1e-6 and abs(h - pw) < 1e-6:
        return lambda u, v: (x + ph - v, y + u)
    raise ValueError("%s placed as %s x %s" % (name, Mm(w), Mm(h)))


def PanelContours(name, xf):
    """DxfDoc() contours of one panel through xf: every inner cut first, then the outline."""
    outline, holes, slots, polys = PanelGeom(name)
    out = [("circle",) + xf(u, v) + (d,) for u, v, d in holes]
    out += [("poly", [xf(u, v) + (b,) for u, v, b in ObroundPts(*s)]) for s in slots]
    out += [("poly", [xf(u, v) + (0.0,) for u, v in p]) for p in polys]
    out.append(("poly", [xf(u, v) + (0.0,) for u, v in outline]))
    return out


def RingContours(x, y):
    """A grommet ring in its RingOD square at (x, y): the bore, then the outline as two half-circle
    arcs, so it reads back as a part."""
    c, r = (x + RingOD / 2, y + RingOD / 2), RingOD / 2
    return [("circle", c[0], c[1], GrommetSleeve - RingGrip),
            ("poly", [(c[0] - r, c[1], 1.0), (c[0] + r, c[1], 1.0)])]


def PanelDxfFiles():
    """{file name: DXF}: one file per acrylic nest sheet, each part where NestPlan() puts it, origin
    at the sheet's corner; and the aluminum back panel alone, origin at its (u, v) corner, as the
    template it is drilled and nibbled through."""
    out = {}
    for sheet, parts in NestPlan().items():
        if sheet.startswith("acrylic"):
            contours = []
            for name, x, y, w, h in parts:
                if name == RingName:
                    contours += RingContours(x, y)
                else:
                    contours += PanelContours(name, NestXform(name, x, y, w, h))
            out["panels_%s.dxf" % sheet.replace(" ", "_")] = DxfDoc((SheetW, SheetH), contours)
    _, _, w, h, _, _ = PanelSpec(BackPanel)
    out["panel_lower_back_template.dxf"] = DxfDoc((w, h), PanelContours(BackPanel, lambda u, v: (u, v)))
    return out


def TemplateFits():
    """The spare acrylic sheet carries both templates: the upper plate along the 24 in side and the
    back panel turned beside it. Raises if they do not fit the sheet and the laser bed."""
    g = NestGap
    w, h = g + BoxD + g + LowerPanelH + g, g + BoxW + g
    if w > min(SheetW, LaserBed[0]) or h > min(SheetH, LaserBed[1]):
        raise ValueError("the two templates do not fit one sheet")


# Read-back. CheckWebs() parses a DXF as written, not the geometry that made it, and measures
# every web. A circle or an obround is a stadium (every point within r of a segment); an outline or
# a cut-out is a polygon, its arcs split into chords whose sag is added to the margin.

def ReadDxf(text):
    """(extent, contours) of an R12 DXF as DxfDoc() writes it: [("circle", x, y, r)] and
    [("poly", [(x, y, bulge)])]."""
    lines = text.split("\n")
    pairs = [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
    k = pairs.index(("9", "$EXTMAX"))
    extent = (float(pairs[k + 1][1]), float(pairs[k + 2][1]))
    i, out, cur = pairs.index(("2", "ENTITIES")) + 1, [], None
    while i < len(pairs):
        code, val = pairs[i]
        i += 1
        if code != "0":
            continue
        if val in ("CIRCLE", "VERTEX"):
            g = {}
            while pairs[i][0] != "0":
                g[pairs[i][0]] = float(pairs[i][1]) if pairs[i][0] in ("10", "20", "40", "42") else 0.0
                i += 1
            if val == "CIRCLE":
                out.append(("circle", g["10"], g["20"], g["40"]))
            else:
                cur.append((g["10"], g["20"], g.get("42", 0.0)))
        elif val == "POLYLINE":
            cur = []
        elif val == "SEQEND":
            out.append(("poly", cur))
        elif val == "ENDSEC":
            break
    return extent, out


def DxfShape(c):
    """("st", a, b, r, 0) for a circle or an obround, ("pg", pts, None, 0, sag) for any other
    closed polyline."""
    if c[0] == "circle":
        return ("st", (c[1], c[2]), (c[1], c[2]), c[3], 0.0)
    pts = c[1]
    if len(pts) == 4 and [round(b, 6) for _, _, b in pts] == [0.0, 1.0, 0.0, 1.0]:
        (x0, y0, _), (x1, y1, _), (x2, y2, _), (x3, y3, _) = pts
        return ("st", ((x3 + x0) / 2, (y3 + y0) / 2), ((x1 + x2) / 2, (y1 + y2) / 2),
                math.hypot(x2 - x1, y2 - y1) / 2, 0.0)
    poly, sag = [], 0.0
    for k, (x, y, b) in enumerate(pts):
        poly.append((x, y))
        if b:
            nx, ny, _ = pts[(k + 1) % len(pts)]
            half = math.hypot(nx - x, ny - y) / 2
            theta = 4 * math.atan(b)
            r = half * (b * b + 1) / (2 * abs(b))
            off = (r - abs(b) * half) * (1 if b > 0 else -1)
            ux, uy = (nx - x) / (2 * half), (ny - y) / (2 * half)
            cx, cy = (x + nx) / 2 - uy * off, (y + ny) / 2 + ux * off
            a0, n = math.atan2(y - cy, x - cx), max(8, int(abs(theta) / 0.05))
            poly += [(cx + r * math.cos(a0 + theta * j / n), cy + r * math.sin(a0 + theta * j / n))
                     for j in range(1, n)]
            sag = max(sag, r * (1 - math.cos(theta / (2 * n))))
    return ("pg", poly, None, 0.0, sag)


def PtSeg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def SegSeg(p, q, a, b):
    """Least distance between segments pq and ab; 0 when they cross."""
    def Turn(o, s, t):
        return (s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0])
    d1, d2, d3, d4 = Turn(a, b, p), Turn(a, b, q), Turn(p, q, a), Turn(p, q, b)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(PtSeg(p, a, b), PtSeg(q, a, b), PtSeg(a, p, q), PtSeg(b, p, q))


def Edges(s):
    if s[0] == "st":
        return [(s[1], s[2])]
    return list(zip(s[1], s[1][1:] + s[1][:1]))


def ShapeGap(s, t):
    """Material between two shapes, measured edge to edge."""
    d = min(SegSeg(p, q, a, b) for p, q in Edges(s) for a, b in Edges(t))
    return d - s[3] - t[3] - s[4] - t[4]


def Inside(pt, s):
    """pt inside shape s."""
    if s[0] == "st":
        return PtSeg(pt, s[1], s[2]) < s[3]
    x, y, inside = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in Edges(s):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def CheckWebs(text):
    """Read a panel DXF back: every part inside the extent and the laser bed, every cut inside one
    part, no cut inside another, and every web (cut to edge, cut to cut, part to part) at least
    PanelWeb. Returns (least web, where); raises otherwise."""
    extent, contours = ReadDxf(text)
    shapes = [DxfShape(c) for c in contours]
    pgs = [s for s in shapes if s[0] == "pg"]
    outlines = [s for s in pgs if not any(t is not s and Inside(s[1][0], t) for t in pgs)]
    for o in outlines:
        for x, y in o[1]:
            if not (-1e-6 <= x <= min(extent[0], LaserBed[0]) + 1e-6
                    and -1e-6 <= y <= min(extent[1], LaserBed[1]) + 1e-6):
                raise ValueError("a part runs off the sheet or the laser bed at (%.1f, %.1f)" % (x, y))
    cuts = {id(o): [] for o in outlines}
    for s in shapes:
        if any(s is o for o in outlines):
            continue
        ref = s[1] if s[0] == "st" else s[1][0]
        home = [o for o in outlines if Inside(ref, o)]
        if len(home) != 1:
            raise ValueError("cut at (%.1f, %.1f) is not inside one part" % ref)
        cuts[id(home[0])].append(s)
    least = [float("inf"), ""]

    def Web(d, s, what):
        if d < least[0]:
            ref = s[1] if s[0] == "st" else s[1][0]
            least[:] = [d, "%s at (%.1f, %.1f)" % (what, ref[0], ref[1])]

    for o in outlines:
        mine = cuts[id(o)]
        for i, s in enumerate(mine):
            Web(ShapeGap(s, o), s, "cut to edge")
            for t in mine[i + 1:]:
                for a, b in ((s, t), (t, s)):
                    if Inside(a[1] if a[0] == "st" else a[1][0], b):
                        raise ValueError("a cut lies inside another")
                Web(ShapeGap(s, t), s, "cut to cut")
    for i, o in enumerate(outlines):
        for p in outlines[i + 1:]:
            Web(ShapeGap(o, p), o, "part to part")
    if least[0] < PanelWeb - 1e-9:
        raise ValueError("web %.2f mm, under %s: %s" % (least[0], Mm(PanelWeb), least[1]))
    return least[0], least[1]


# PE bonding. Anodize insulates (and the cut ends of a rail meet anodized faces), so every rail
# is its own metal part. Each one gets a tapped M5 hole through its slot floor into the core and
# its own 12 AWG home run to the ground bar of its module: unbolting one part never opens
# another's bond, and each bond can be measured alone.
BarTerminals = 15                  # Siemens EC2GB152
JumperM = 0.5                      # average run: Manhattan from the part to its bar plus 150 mm,
                                   # with each module's bar(s) at its plate's PE stud


def BondPoints():
    """(module, part, count, landing) for every separate metal part of the box."""
    rails = {d: sum(1 for s in DeckSolids() if s["kind"] == "rail" and s["deck"] == d) for d in ("lower", "upper")}
    return [("lower", "lower post", 4, "tapped bond hole, ring lug"),
            ("lower", "bottom ring rail", 4, "tapped bond hole, ring lug"),
            ("lower", "DIN rail: fuses, 24 V, 110 V, three PSUs", rails["lower"], "its PE terminal"),
            ("lower", "aluminum lower back panel", 1, "M5 stud, ring lug"),
            ("lower", "PE bar on rail 1 (inlet PE, PSU FG)", 1, "bar to bar"),
            ("lower", "link to the upper module", 1, "unclamp to lift the module"),
            ("upper", "mid ring rail", 4, "tapped bond hole, ring lug"),
            ("upper", "upper post", 4, "tapped bond hole, ring lug"),
            ("upper", "lid ring rail", 4, "tapped bond hole, ring lug"),
            ("upper", "DIN rail: field, logic, SSRs, drivers", rails["upper"], "its PE terminal"),
            ("upper", "TB6600 case", 7, "ring lug and tooth washer under an ear screw"),
            ("upper", "motor shield clamp", 1, "ring lug"),
            ("upper", "link to the lower module", 1, "unclamp to lift the module"),
            ("upper", "trunk to the gantry bar", 1, "leaves with the motor cables")]


def BondSummary():
    """{module: (jumpers, bars)} and the total jumper count."""
    out = {}
    for module, _, n, _ in BondPoints():
        out[module] = out.get(module, 0) + n
    out = {m: (n, math.ceil(n / BarTerminals)) for m, n in out.items()}
    return out, sum(n for n, _ in out.values())


class View:
    """Orthographic view: real (a, b) mm to paper mm. a runs right, b runs up; with down, b runs
    down. A deck plan seen from above with the front at the left takes down: the generator's x and y
    are a left-handed set, so with y running up the left wall would land at the bottom and the plan
    would read as seen from below. Bottom is the real b of the view's lower edge on paper."""

    def __init__(self, sh, x0, y0, aSpan, bSpan, scale, down=False):
        self.Sh, self.X0, self.Y0, self.ASpan, self.BSpan, self.S = sh, x0, y0, aSpan, bSpan, scale
        self.Down = down
        self.Bottom = bSpan if down else 0.0

    def X(self, a):
        return self.X0 + a / self.S

    def Y(self, b):
        return self.Y0 + (b if self.Down else self.BSpan - b) / self.S

    def Top(self, b0, b1):
        """Paper y of the upper edge of the band from b0 to b1."""
        return min(self.Y(b0), self.Y(b1))

    def Box(self, a0, b0, a1, b1, fill="#fff", dashed=False, stroke=0.25, lines=(), size=1.4,
            bold=True, rot=0):
        sh = self.Sh
        x, y = self.X(a0), self.Top(b0, b1)
        w, h = (a1 - a0) / self.S, (b1 - b0) / self.S
        dash = ' stroke-dasharray="1.2 .7"' if dashed else ""
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="#000" stroke-width="%s"%s/>'
               % (Fmt(x), Fmt(y), Fmt(w), Fmt(h), fill, Fmt(stroke), dash))
        if lines:
            cx, cy = x + w / 2, y + h / 2
            lead = size * 1.18
            if rot:
                for i, s2 in enumerate(lines):
                    off = (i - (len(lines) - 1) / 2) * lead
                    sh.Text(cx + off + size * 0.35, cy, s2, size=size, anchor="middle", rot=rot,
                            weight="bold" if (bold and i == 0) else "normal")
            else:
                for i, s2 in enumerate(lines):
                    off = (i - (len(lines) - 1) / 2) * lead
                    sh.Text(cx, cy + off + size * 0.35, s2, size=size, anchor="middle",
                            weight="bold" if (bold and i == 0) else "normal")

    def Poly(self, pts, fill="#fff", stroke=0.3, dashed=False):
        """Closed polygon; a path, so the fill goes in style (the sheet CSS sets path fill none)."""
        dash = ' stroke-dasharray="1.2 .7"' if dashed else ""
        d = "M" + " L".join("%s %s" % (Fmt(self.X(a)), Fmt(self.Y(b))) for a, b in pts) + " Z"
        self.Sh.Add('<path d="%s" style="fill:%s" stroke="#000" stroke-width="%s"%s/>'
                    % (d, fill, Fmt(stroke), dash))

    def Hole(self, a, b, dia, fill="#fff", stroke=0.18):
        self.Sh.Add('<circle cx="%s" cy="%s" r="%s" fill="%s" stroke="#000" stroke-width="%s"/>'
                    % (Fmt(self.X(a)), Fmt(self.Y(b)), Fmt(dia / 2 / self.S), fill, Fmt(stroke)))

    def Obround(self, a0, b0, a1, b1, fill="#fff", stroke=0.25):
        """Slot with full-round ends, along a or along b, from the DXF's own vertices. They run
        counter-clockwise, which a view with b down draws clockwise, so its arcs sweep the other way."""
        rp = Fmt(min(a1 - a0, b1 - b0) / 2 / self.S)
        p = [(Fmt(self.X(a)), Fmt(self.Y(b))) for a, b, _ in ObroundPts(a0, b0, a1, b1)]
        sw = (1 if self.Down else 0,)
        d = ("M%s %s L%s %s A%s %s 0 0 %s %s %s L%s %s A%s %s 0 0 %s %s %s Z"
             % (p[0] + p[1] + (rp, rp) + sw + p[2] + p[3] + (rp, rp) + sw + p[0]))
        self.Sh.Add('<path d="%s" style="fill:%s" stroke="#000" stroke-width="%s"/>'
                    % (d, fill, Fmt(stroke)))

    def Line(self, pts, cls):
        self.Sh.Wire([(self.X(a), self.Y(b)) for a, b in pts], cls)

    def Title(self, s, sub=None):
        self.Sh.Text(self.X0, self.Y0 - 1.6, s, size=2.2, weight="bold")
        if sub:
            self.Sh.Text(self.X0 + self.ASpan / self.S, self.Y0 - 1.6, sub, size=1.4, anchor="end")

    def DimH(self, a0, a1, b, label, below=True, off=2.6):
        """Horizontal dimension line at real height b (paper offset outside the view)."""
        sh = self.Sh
        y = self.Y(b) + (off if below else -off)
        sh.Wire([(self.X(a0), y), (self.X(a1), y)], "sg")
        sh.Wire([(self.X(a0), y - 0.9), (self.X(a0), y + 0.9)], "sg")
        sh.Wire([(self.X(a1), y - 0.9), (self.X(a1), y + 0.9)], "sg")
        sh.Text((self.X(a0) + self.X(a1)) / 2, y - 0.5, label, size=1.35, anchor="middle", halo=True)

    def DimV(self, b0, b1, a, label, right=True, off=2.6):
        sh = self.Sh
        x = self.X(a) + (off if right else -off)
        sh.Wire([(x, self.Y(b0)), (x, self.Y(b1))], "sg")
        sh.Wire([(x - 0.9, self.Y(b0)), (x + 0.9, self.Y(b0))], "sg")
        sh.Wire([(x - 0.9, self.Y(b1)), (x + 0.9, self.Y(b1))], "sg")
        sh.Text(x + (0.6 if right else -0.6), (self.Y(b0) + self.Y(b1)) / 2, label, size=1.35,
                anchor="middle", rot=-90, halo=True)

    def OrdX(self, vals, b, size=1.1):
        """Ordinate values of a, ticked and written below the edge at real height b."""
        y = self.Y(b)
        for a in vals:
            x = self.X(a)
            self.Sh.Wire([(x, y + 0.5), (x, y + 1.6)], "sg")
            self.Sh.Text(x + size * 0.35, y + 1.9, Mm(a), size=size, anchor="end", rot=-90)

    def OrdY(self, vals, a, size=1.1):
        """Ordinate values of b, ticked and written left of the edge at real a."""
        x = self.X(a)
        for b in vals:
            y = self.Y(b)
            self.Sh.Wire([(x - 1.6, y), (x - 0.5, y)], "sg")
            self.Sh.Text(x - 1.9, y + size * 0.35, Mm(b), size=size, anchor="end")


def PlanFrame(v, deckLabel, upper=False):
    """The frame of a deck plan. Each wall is named in its own frame band, nearest the plate's
    edge; the right wall's band also carries the note on the ring, the left wall's the deck's name."""
    sh = v.Sh
    if upper:
        v.Poly(PlateGeom("upper")[0], fill="#fff", stroke=0.35)
        v.Box(Frame, Frame, BoxD - Frame, BoxW - Frame, fill="none", dashed=True, stroke=0.2)
        note = "upper posts stand on the plate; mid ring (dashed) under it"
    else:
        v.Box(0, 0, BoxD, BoxW, fill=ZoneFill["frame"], stroke=0.35)
        v.Box(Frame, Frame, BoxD - Frame, BoxW - Frame, fill="#fff", stroke=0.25)
        note = "bottom ring on the base plate"
    for x, y in PostCentres:
        v.Box(x - Frame / 2, y - Frame / 2, x + Frame / 2, y + Frame / 2, fill=PostFill, stroke=0.3)

    def Band(b, line):
        """Baseline of text line `line` (0 nearest the edge) in the band of the side wall at b."""
        edge = v.Y(b)
        return edge + 1.47 + 1.13 * line if edge < v.Y(BoxW - b) else edge - 0.6 - 1.45 * line
    sh.Text(v.X(BoxD / 2), Band(0.0, 0), "LEFT SIDE", size=1.2, anchor="middle", weight="bold")
    sh.Text(v.X(BoxD / 2), Band(BoxW, 0), "RIGHT SIDE", size=1.2, anchor="middle", weight="bold")
    sh.Text(v.X(BoxD / 2), Band(BoxW, 1), note, size=1.2, anchor="middle")
    sh.Text(v.X(Frame + 4), Band(0.0, 1), deckLabel, size=1.2, italic=True)
    # turned to read upward, a name stands left of its x: both sit 0.6 inside the plate's edge
    sh.Text(v.X(0) + 1.55, v.Y(BoxW / 2), "FRONT", size=1.3, anchor="middle", rot=-90, weight="bold")
    sh.Text(v.X(BoxD) - 0.6, v.Y(BoxW / 2), "BACK", size=1.3, anchor="middle", rot=-90, weight="bold")


def SectionFrame(v, span):
    """Frame members of an elevation with the near rails left off: far posts (lower and upper),
    far rails, near rails cut at the ends, the lid ring and both plates. span = BoxW or BoxD."""
    F = Frame
    for a0 in (0.0, span - F):
        v.Box(a0, LoDeck, a0 + F, MidF0, fill=PostFill, stroke=0.25)
        v.Box(a0, UpDeck, a0 + F, TopIn, fill=PostFill, stroke=0.25)
        v.Box(a0, LoDeck, a0 + F, LoDeck + F, fill=ZoneFill["frame"], stroke=0.25)
        v.Box(a0, MidF0, a0 + F, UpPlate0, fill=ZoneFill["frame"], stroke=0.25)
    v.Box(F, LoDeck, span - F, LoDeck + F, fill=ZoneFill["frame"], stroke=0.2)
    v.Box(F, MidF0, span - F, UpPlate0, fill=ZoneFill["frame"], stroke=0.2)
    v.Box(0, TopIn, span, BoxH, fill=LidFill, stroke=0.25)
    for a0 in (0.0, span - F):
        v.Box(a0, TopIn, a0 + F, BoxH, fill=LidFill, stroke=0.25)
    v.Box(0, 0, span, LoDeck, fill=PlateFill, stroke=0.1)
    v.Box(0, UpPlate0, span, UpDeck, fill=PlateFill, stroke=0.1)


# ---------------------------------------------------------------- sheet 3: parts at their real sizes

# PartSize and MountedH() sit with the frame stack, which takes the lower bay from them.

def RailRun(start, items):
    """Parts in a row along a DIN rail from `start`. An item is a gap in mm or (part key, label,
    count): count > 1 makes a group of terminals drawn as one block. Returns [(key, label, a0, a1)]
    and the end of the run."""
    out, a = [], start
    for it in items:
        if isinstance(it, (int, float)):
            a += it
            continue
        key, label, n = (it + (1,))[:3]
        out.append((key, label, a, a + n * PartSize[key][0]))
        a += n * PartSize[key][0]
    return out, a


def TerminalRun(start, groups, lead=()):
    """A terminal rail: the `lead` items (parts or gaps), an end clamp, groups of UK 2.5 B blocks
    with an end cover between, end clamp."""
    items = list(lead) + [("Stop", "")]
    for i, (label, n) in enumerate(groups):
        items += ([("Cover", "")] if i else []) + [("Term", label, n)]
    return RailRun(start, items + [("Stop", "")])


def DinRun(alongX, centre, runEnd, block, fill, ext=5.0):
    """A DIN rail with its parts, along x or along y, centred across at `centre`. The rail reaches
    ext past each end of the run (none under a PSU, which sits on its clip); block is the packing
    study's name for the group."""
    run, end = runEnd
    return dict(alongX=alongX, centre=centre, run=run, a0=run[0][2] - ext, a1=end + ext, block=block,
                fill=fill)


def UpperRails():
    """{rail: DinRun()} on the upper deck: the field, logic and drivers' rails along x, and the SSR
    rail along y, one channel past the logic rail's end."""
    def Row(r):
        return sum(UpRows[r]) / 2
    drv = []
    for i, ax in enumerate(DriveAxes):
        drv += ([6.0] if i else []) + [("TB6600", ax)]
    logic = DinRun(True, Row("logic"), TerminalRun(LogicRail0 + 5.0, [("0V-S", 9), ("0V-S2", 4)],
                                                   lead=[("Mega", "Mega 2560"), 4.0]),
                   "LOGIC", ZoneFill["fld"])
    ssr = [("SSR", s) for s in ("SSR-UV", "SSR-valve", "tower R", "tower A", "tower G", "buzzer")]
    return {
        "field": DinRun(True, Row("terminals"),
                        TerminalRun(FieldRail0 + 5.0, [("X2", 7), ("X4", 12), ("X5", 6), ("X6", 6),
                                                       ("X7", 5), ("X8", 4)]), "FIELD", ZoneFill["fld"]),
        "logic": logic,
        "SSR": DinRun(False, logic["a1"] + Chan + PartSize["SSR"][1] / 2,
                      RailRun(UpRows["logic"][0] + 5.0, ssr), "SSR", ZoneFill["log"]),
        "drivers": DinRun(True, Row("drivers"), RailRun(DrvX[0], drv), "DRV", ZoneFill["drv"]),
    }


def LowerRails():
    """{rail: DinRun()} on the lower deck, every rail along x: the fuse rail along the left wall,
    the 24 V rail one channel behind it with the servo PSU one channel past its end, the 5 V PSU in
    the same row against the back ring, past cable slot 2 and the base PE stud (the fuse rail, with FB1
    a 12-way, leaves no room for it at its end: issue #158), and the mains strip along the right wall:
    the 24 V PSU lying flat, then one channel behind it the 110 V rail, X0 at its back end by the
    inlet."""
    x0 = y0 = Frame + RingClear
    fuses = DinRun(True, y0 + PartSize["FB2"][1] / 2,
                   RailRun(x0 + 5.0, [("FB2", "FB2"), 6.0, ("FB1", "FB1")]), "RFB", ZoneFill["24"])
    yK = y0 + PartSize["FB2"][1] + Chan
    k2 = DinRun(True, yK + PartSize["K2"][1] / 2,
                RailRun(R24Rail0 + 5.0, [("K2", "K2"), 6.0, ("Bar", "Star S"), 6.0, ("Bar", "0V-P"), 4.0,
                                         ("Bar", "0V-P")]), "R24", ZoneFill["24"])
    mains = [("PETerm", "PE", PeBarTerms), 4.0, ("Term", "X1", 3), 4.0, ("K1", "K1"), 4.0, ("F0", "F0"), 4.0,
             ("Term", "X0", 5)]
    yM = (PsuY0 + PsuY1) / 2
    servo = DinRun(True, yK + PartSize["PSU6"][1] / 2,
                   RailRun(k2["a1"] + Chan, [("PSU6", "servo PSU")]), "PS6", ZoneFill["24"], 0.0)
    return {
        "fuses": fuses,
        "24 V": k2,
        "servo PSU": servo,
        "5 V PSU": DinRun(True, yK + PartSize["PSU5"][1] / 2,
                          RailRun(BoxD - Frame - RingClear - PartSize["PSU5"][0], [("PSU5", "5 V PSU")]),
                          "PS5", ZoneFill["24"], 0.0),
        "24 V PSU": DinRun(True, yM, RailRun(PsuX0, [("PSU24", "24 V PSU")]), "PSU", ZoneFill["110"], 0.0),
        "110 V": DinRun(True, yM, RailRun(BoxD - Frame - RingClear - 5.0 - RailRun(0.0, mains)[1], mains),
                        "R110", ZoneFill["110"]),
    }


def ClampBox():
    """The motor cable shield clamp bar: one channel past the drivers' rail, along the drivers and
    their motor duct."""
    x0, y0 = UpperRails()["drivers"]["a1"] + Chan, UpRows["drivers"][0]
    return (x0, y0, x0 + PartSize["Clamp"][0], y0 + PartSize["Clamp"][1])


def Ducts():
    """[(deck, (x0, y0, x1, y1), width, label, in the mains compartment)]: the slotted duct runs,
    which meet in tees. Upper deck: a narrow duct in each channel, one joining them between the logic
    rail's end and the SSRs, and one taking the driver 24 V from slot 1 to the motor duct; the motor
    duct behind the drivers to the shield clamp, on past it, and the back run, which carries the
    motor cables across the corridor behind every rail to the upper left grommet. Lower deck: one
    between the fuse rail and the 24 V rail, and one in the mains compartment between the PSU and
    the 110 V rail."""
    up, lo = UpperRails(), LowerRails()
    n, w = DuctNarrow / 2, DuctWide / 2
    fd, sd, md = UpRows["field duct"], UpRows["signal duct"], UpRows["motor duct"]
    drv0, drv1 = up["drivers"]["a0"], up["drivers"]["a1"]
    clamp = ClampBox()
    ssrX = (up["logic"]["a1"] + up["SSR"]["centre"] - PartSize["SSR"][1] / 2) / 2
    feedX = (drv1 + clamp[0]) / 2
    back0, back1 = BackRunX - w, BackRunX + w
    lowY = (lo["fuses"]["centre"] + PartSize["FB2"][1] / 2 + lo["24 V"]["centre"] - PartSize["K2"][1] / 2) / 2
    mainsX = (PsuX0 + PartSize["PSU24"][0] + lo["110 V"]["a0"]) / 2
    return [
        ("upper", (FieldRail0, fd[0], back0, fd[1]), DuctNarrow, "duct 1/2 x 1 in: field signals, SSR outputs",
         False),
        ("upper", (drv0, sd[0], drv1, sd[1]), DuctNarrow, "duct 1/2 x 1 in: driver signals", False),
        ("upper", (ssrX - n, fd[1], ssrX + n, sd[0]), DuctNarrow, "SSR inputs", False),
        ("upper", (feedX - n, CableSlots[0][3] + 2.0, feedX + n, md[0]), DuctNarrow, "24 V feeds", False),
        ("upper", (drv0, md[0], clamp[0], md[1]), DuctWide, "duct 1 x 1 1/2 in: motor cables, driver 24 V",
         False),
        ("upper", (clamp[2], md[0], back0, md[1]), DuctWide, "motor cables", False),
        ("upper", (back0, Frame + RingClear, back1, md[1]), DuctWide,
         "duct 1 x 1 1/2 in: back run, motor cables to the upper left grommet", False),
        ("lower", (Frame + RingClear, lowY - n, lo["fuses"]["a1"], lowY + n), DuctNarrow,
         "duct 1/2 x 1 in: 24 V feeds and 0V returns", False),
        ("lower", (mainsX - n, PsuY0, mainsX + n, PsuY1), DuctNarrow, "duct 1/2 x 1 in: mains", True),
    ]


RailPlanFill = "#EEEEEE"
KeyFill = {"Mega": ZoneFill["log"]}
MainsBlocks = ("PSU", "R110")


def DeckSolids():
    """Everything standing on the two decks, as boxes in deck coordinates seen from above:
    [dict(deck, kind, box (x0, y0, x1, y1), key, label, fill, block, mount, top, dashed, alongX,
    mains)]. kind is rail, part, duct or clamp; top is the height over the deck; block is the
    packing study's name for the group the box belongs to; mains marks the 110 VAC compartment."""
    out = []
    for deck, rails in (("upper", UpperRails()), ("lower", LowerRails())):
        for r in rails.values():
            c, ax, mains = r["centre"], r["alongX"], r["block"] in MainsBlocks

            def Box(a0, a1, half):
                return (a0, c - half, a1, c + half) if ax else (c - half, a0, c + half, a1)

            out.append(dict(deck=deck, kind="rail", box=Box(r["a0"], r["a1"], 17.5), key=None, label="",
                            fill=RailPlanFill, block=r["block"], mount="plate", top=DinRailH,
                            dashed=False, alongX=ax, mains=mains))
            for key, label, a0, a1 in r["run"]:
                out.append(dict(deck=deck, kind="part", box=Box(a0, a1, PartSize[key][1] / 2), key=key,
                                label=label, fill=KeyFill.get(key, r["fill"]), block=r["block"],
                                mount=PartSize[key][4], top=MountedH(key), dashed=not PartSize[key][3],
                                alongX=ax, mains=mains))
    for deck, box, w, label, mains in Ducts():
        out.append(dict(deck=deck, kind="duct", box=box, key=None, label=label, fill="#fff", block=None,
                        mount="plate", top=DuctTall[w], dashed=True,
                        alongX=box[2] - box[0] >= box[3] - box[1], mains=mains))
    out.append(dict(deck="upper", kind="clamp", box=ClampBox(), key="Clamp", label="shield clamp",
                    fill=ZoneFill["drv"], block="SHIELD", mount="plate", top=MountedH("Clamp"),
                    dashed=not PartSize["Clamp"][3], alongX=False, mains=False))
    return out


# The packing study (ADR-0010) scored layout 3b from block centres. StudyMatch() holds the drawing to
# that file, so moving a rail here without rescoring it fails loudly; StudyScore() rescores the
# layout as drawn with layout_study.Score(), which needs no solver.
StudyFile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layout_study", "layout3b_build.json")
HandWire = 57478                   # the 2026-10-17 hand layout, results_2026-10-17.json


def StudyBlocks():
    """{block: (cx, cy, rot)}: the drawn layout in the study's terms (layout_study.Blocks), each rail
    with its parts and the driver block with its motor duct; rot 1 where the study turned the block
    so that its length runs along y."""
    ext = {}
    for s in DeckSolids():
        if s["block"]:
            e = ext.setdefault(s["block"], list(s["box"]))
            e[:] = [min(e[0], s["box"][0]), min(e[1], s["box"][1]), max(e[2], s["box"][2]),
                    max(e[3], s["box"][3])]
    ext["DRV"][3] = UpRows["motor duct"][1]
    rot = {"SSR": 1, "PS6": 1, "SHIELD": 1}
    return {b: ((e[0] + e[2]) / 2, (e[1] + e[3]) / 2, rot.get(b, 0)) for b, e in ext.items()}


def StudyExits():
    """{exit: (x, y, deck)} of the cable entries and the inlet, in the form of layout_study.Exits."""
    at = {"left": lambda u: (u, 0.0), "right": lambda u: (u, BoxW), "front": lambda u: (0.0, u),
          "back": lambda u: (BoxD, u)}
    out = {}
    for panel, u, _, key in CableEntries:
        wall, z0 = PanelWall[panel]
        out[key] = at[wall](u) + ("lower" if z0 == 0.0 else "upper",)
    out["INLET"] = (BoxD, InletU, "lower")
    return out


def StudyMatch(tol=1.0):
    """Raise unless every block centre lies within tol of layout3b_build.json, turned as there, and
    every exit sits where the file puts it. Returns the file's expected wire length."""
    with open(StudyFile, encoding="utf-8") as f:
        study = json.load(f)
    drawn, exits = StudyBlocks(), StudyExits()
    if set(drawn) != set(study["place"]) or set(exits) != set(study["exits"]):
        raise ValueError("the drawn blocks or exits differ from %s" % os.path.basename(StudyFile))
    for b, (cx, cy, rot) in study["place"].items():
        x, y, r = drawn[b]
        if math.hypot(x - cx, y - cy) > tol or r != rot:
            raise ValueError("block %s is drawn at (%.1f, %.1f), the study has (%.1f, %.1f): rescore it "
                             "with layout_study.Score() and update the file" % (b, x, y, cx, cy))
    for e, (x, y, deck) in study["exits"].items():
        if math.hypot(exits[e][0] - x, exits[e][1] - y) > tol or exits[e][2] != deck:
            raise ValueError("exit %s is at (%.1f, %.1f), the study has (%.1f, %.1f)"
                             % (e, exits[e][0], exits[e][1], x, y))
    return study["expected_wire"]


def StudyScore():
    """(wire at the study's deck rise, wire at the drawn one), conductor-mm: layout_study.Score() on
    the drawn block centres and exits, with the motor cables on their own grommet (ULM)."""
    if os.path.dirname(StudyFile) not in sys.path:
        sys.path.insert(0, os.path.dirname(StudyFile))
    import layout_study
    nets = [(a, "ULM" if (a, b) == ("SHIELD", "UL") else b, n) for a, b, n in layout_study.Nets]
    args = dict(exits=StudyExits(), nets=nets)
    study = layout_study.Score("B", StudyBlocks(), **args)["wire"]
    return study, layout_study.Score("B", StudyBlocks(), rise=LowBay + UpPlateT, **args)["wire"]


def RunChecks():
    """Raise unless every solid stands inside the frame ring (RingClear clear) and under its bay
    (PartClear clear); nothing on a deck overlaps anything but its own rail, or a duct its tees;
    every plate slot lies over free lower deck, clear of everything on the upper plate and off the
    110 VAC compartment; each PE stud is clear of its deck's parts; the mains parts stand MainsGap inside
    the 110 VAC compartment's edge and the rest outside it; the motor grommet clears the field rail and
    the front one is on the Mega's line; and the drawing matches the study (StudyMatch()). Returns the length
    of each rail's run, end clamps included."""
    solids = DeckSolids()
    bays = {"upper": TopIn - UpDeck, "lower": UpPlate0 - LoDeck}
    lo, hx, hy = Frame + RingClear - 1e-6, BoxD - Frame - RingClear + 1e-6, BoxW - Frame - RingClear + 1e-6

    def Name(s):
        return "%s deck %s" % (s["deck"], s["label"] or s["key"] or s["kind"])

    def Hit(a, b):
        return a[0] < b[2] - 1e-6 and b[0] < a[2] - 1e-6 and a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6

    for s in solids:
        x0, y0, x1, y1 = s["box"]
        if x0 < lo or y0 < lo or x1 > hx or y1 > hy:
            raise ValueError("%s at x %.1f-%.1f, y %.1f-%.1f leaves the frame" % (Name(s), x0, x1, y0, y1))
        if s["top"] > bays[s["deck"]] - PartClear + 1e-6:
            raise ValueError("%s stands %.1f mm in a %.1f mm bay" % (Name(s), s["top"], bays[s["deck"]]))
    for i, s in enumerate(solids):
        for t in solids[i + 1:]:
            if s["deck"] != t["deck"] or not Hit(s["box"], t["box"]):
                continue
            if s["kind"] == t["kind"] == "duct" or ("rail" in (s["kind"], t["kind"]) and s["block"] == t["block"]):
                continue
            raise ValueError("%s overlaps %s" % (Name(s), Name(t)))
    for i, sl in enumerate(CableSlots):
        if sl[3] > MainsZoneY - 1e-6:
            raise ValueError("slot %d reaches over the 110 VAC compartment (y %s)" % (i + 1, Mm(MainsZoneY)))
        if sl[0] < Frame or sl[1] < Frame or sl[2] > BoxD - Frame or sl[3] > BoxW - Frame:
            raise ValueError("slot %d runs over the mid ring" % (i + 1))
        for s in solids:
            if (s["deck"] == "upper" or s["kind"] != "duct") and Hit(sl, s["box"]):
                raise ValueError("slot %d (%s) meets the %s" % (i + 1, SlotUse[i], Name(s)))
    for kind, (px, py) in PeStud.items():
        deck = "lower" if kind == "base" else "upper"
        for s in solids:
            x0, y0, x1, y1 = s["box"]
            if s["deck"] == deck and x0 - HoleM5 < px < x1 + HoleM5 and y0 - HoleM5 < py < y1 + HoleM5:
                raise ValueError("the %s PE stud at (%s, %s) is under the %s" % (kind, Mm(px), Mm(py), Name(s)))
    for s in solids:
        if s["deck"] == "lower":
            x0, y0, x1, y1 = s["box"]
            inside = x0 >= MainsZoneX + MainsGap - 1e-6 and y0 >= MainsZoneY + MainsGap - 1e-6
            outside = x1 <= MainsZoneX + 1e-6 or y1 <= MainsZoneY + 1e-6
            if not (inside if s["mains"] else outside):
                raise ValueError("%s is on the wrong side of the 110 VAC compartment's edge, or a mains "
                                 "part within %s mm of it" % (Name(s), Mm(MainsGap)))
    up = UpperRails()
    for _, u, _, key in CableEntries:
        if key == "ULM" and u - GrommetHole / 2 < up["field"]["a1"] + 5.0:
            raise ValueError("the motor grommet at x %s meets the field rail's end at x %s"
                             % (Mm(u), Mm(up["field"]["a1"])))
        if key == "UF" and abs(u - up["logic"]["centre"]) > 1e-6:
            raise ValueError("the front grommet is off the Mega's centre line")
        if key == "LL" and u - GrommetHole / 2 < LowerRails()["fuses"]["a1"] + 5.0:
            raise ValueError("the lower left grommet at x %s meets the fuse rail's end at x %s"
                             % (Mm(u), Mm(LowerRails()["fuses"]["a1"])))
    StudyMatch()
    return {name: r["run"][-1][3] - r["run"][0][2]
            for rails in (up, LowerRails()) for name, r in rails.items()}


DinRailStock, DinRailsOnHand = 18 * 25.4, 5   # the 18 in aluminum rails on hand (issue #158)
PeBarTerms = 4                     # USLKG blocks in the PE bar on the 110 V rail (sheet 2A)
# The aluminum rails are stiff enough once screwed down (issue #158): a TS35 x 7.5 rail of 1.0 mm sheet
# (roughly the EN 60715 outline: a 27 mm base, two 6.5 mm webs, two 4 mm lips) lies on its plate, so gravity
# only presses it down; the worst pull is a part hanging off it with the box on its side, taken as the
# 24 V PSU's assumed 3 kg at 3 g (88 N), at midspan between two screws 150 mm apart.
DinRailSection = [(27.0, 1.0, 0.5), (1.0, 6.5, 4.25), (1.0, 6.5, 4.25), (4.0, 1.0, 7.0), (4.0, 1.0, 7.0)]
EAluminum, ESteel = 69000.0, 200000.0   # MPa
RailPull, RailSpan = 3.0 * 9.81 * 3.0, 150.0


def DinRailBend(E):
    """Midspan deflection (mm) of a DIN rail between two screws under RailPull: F L^3 / (48 E I)."""
    area = sum(w * h for w, h, _ in DinRailSection)
    zc = sum(w * h * z for w, h, z in DinRailSection) / area
    i = sum(w * h ** 3 / 12 + w * h * (z - zc) ** 2 for w, h, z in DinRailSection)
    return RailPull * RailSpan ** 3 / (48 * E * i), i


def NestDinRails():
    """Every drawn DIN rail cut from the rails on hand, first fit decreasing with the 2020 cut list's
    kerf and squaring cut: a list of the lengths cut from each. Raises if they need more rails."""
    pieces = sorted(((s["box"][2] - s["box"][0]) if s["alongX"] else (s["box"][3] - s["box"][1])
                     for s in DeckSolids() if s["kind"] == "rail"), reverse=True)
    rails = []
    for L in pieces:
        for r in rails:
            if sum(p + Kerf for p in r) + L + Kerf <= DinRailStock - EndTrim:
                r.append(L)
                break
        else:
            rails.append([L])
    if len(rails) > DinRailsOnHand:
        raise ValueError("the DIN rails need %d rails of %s mm, %d on hand"
                         % (len(rails), Mm(DinRailStock), DinRailsOnHand))
    return rails


def PlanLabel(s):
    """(lines, text size, rotation) of a solid in a plan view."""
    key, label = s["key"], s["label"]
    if s["kind"] == "rail" or not label:
        return [], 1.1, 0
    if s["kind"] == "duct":
        return [label], 1.1, 0 if s["alongX"] else -90
    fixed = {"TB6600": ([label, "TB6600"], 1.2, 0),
             "Mega": (["Mega 2560", "99 x 53, along its rail", "+ screw shield"], 1.25, 0),
             "PSU24": (["PSU 24 V 1200 W, lying flat", "215 x 115 x 50 (assumed),",
                        "%s tall on clip and rail;" % Mm(MountedH("PSU24")), "fan face to the right wall"],
                       1.2, 0),
             "PSU6": (["Servo PSU", "6 V, 58 x 63"], 1.1, 0),
             "PSU5": (["5 V PSU", "76 x 76", "Pi at the panel"], 1.2, 0),
             "Clamp": (["shield clamp"], 1.1, -90)}
    if key in fixed:
        return fixed[key]
    narrow = s["alongX"] and s["box"][2] - s["box"][0] < 14
    return [label], 0.95 if key == "SSR" else 1.15, -90 if narrow else 0


def BuildPacking():
    sh = Sheet("RMR control panel packing study")
    DrawFrame(sh, "RMR control panel: packing study, 18 x 13 x 11 in",
              "Two decks in a 2020 frame, both on 1/16 in aluminum plates: lower deck for 110 VAC and "
              "24 V power, upper deck for drives and logic; acrylic walls. Scale 1:3.5 when printed at 100 %.")
    S = 3.5
    F = Frame
    lengths = RunChecks()
    solids = DeckSolids()
    upper = UpperRails()
    wireStudy, wireDrawn = StudyScore()
    room = TopIn - UpDeck - DrvH
    short = {"UL": "field", "ULM": "motors", "UF": "USB, J11, GPIO", "UR": "motor, tower", "LL": "ODrive, Pi, E-stop"}

    def Plan(v, deck):
        """Rails first, then ducts, parts and the clamp, each at its footprint."""
        for kind in ("rail", "duct", "part", "clamp"):
            for s in solids:
                if s["deck"] == deck and s["kind"] == kind:
                    lines, size, rot = PlanLabel(s)
                    v.Box(*s["box"], fill=s["fill"], dashed=s["dashed"], stroke=0.15 if kind == "rail" else 0.25,
                          lines=lines, size=size, rot=rot, bold=kind != "duct")

    def Entries(v, deck):
        """A bar at the wall for each grommet on this deck, named in the frame band beside it: past
        its back end, or before its front end where that would meet the wall's name."""
        r = GrommetHole / 2
        for panel, u, _, key in CableEntries:
            wall, z0 = PanelWall[panel]
            if ("lower" if z0 == 0.0 else "upper") != deck:
                continue
            if wall == "front":
                v.Box(-2.0, u - r, 0.0, u + r, fill="#000", stroke=0.1)
                sh.Text(v.X(F / 2) + 0.4, v.Y(u), short[key], size=1.0, anchor="middle", rot=-90, halo=True)
                continue
            b = 0.0 if wall == "left" else BoxW
            v.Box(u - r, b - 2.0 if wall == "left" else b, u + r, b if wall == "left" else b + 2.0,
                  fill="#000", stroke=0.1)
            a, width = u + r + 1.5, len(short[key]) * 0.55 * S   # the label's start and its length, real mm
            back = a + width < BoxD - F and (a > BoxD / 2 + 25 or a + width < BoxD / 2 - 25)
            sh.Text(v.X(a if back else u - r - 1.5), v.Y(F / 2 if wall == "left" else BoxW - F / 2) + 0.4,
                    short[key], size=1.0, anchor="start" if back else "end", halo=True)

    # ------------------------------------------------ upper deck plan
    up = View(sh, 10.0, 25.0, BoxD, BoxW, S, down=True)
    up.Title("A  Upper deck, seen from above", "1/16 in aluminum plate on the mid ring; parts at true size")
    PlanFrame(up, "upper plate 457 x 330, part of the upper module", upper=True)
    Plan(up, "upper")
    mega = [p for p in upper["logic"]["run"] if p[0] == "Mega"][0]
    yc = upper["logic"]["centre"]
    up.Box(mega[2] - 6.0, yc - 9.5, mega[2], yc + 9.5, fill=ZoneFill["log"], stroke=0.2)
    sh.Text(up.X(mega[2] - 7.0), up.Y(yc + 12) + 0.4, "USB", size=1.0, anchor="end")
    fx0, fx1 = upper["field"]["a0"], upper["field"]["a1"]
    sh.Text(up.X(fx1 + 3), up.Y(upper["field"]["centre"]) - 0.75, "field rail,", size=1.1)
    sh.Text(up.X(fx1 + 3), up.Y(upper["field"]["centre"]) + 0.85, "%d mm" % round(lengths["field"]),
            size=1.1)
    # in the open deck between slot 2 and the motor duct, past the shield clamp
    ax = (ClampBox()[2] + BackRunX - DuctWide / 2) / 2
    ay = (CableSlots[1][3] + UpRows["motor duct"][0]) / 2
    for i, s2 in enumerate(["ODrive: in the", "spincoater base", "", "Pi: at the", "operator panel"]):
        sh.Text(up.X(ax), up.Y(ay) + 1.6 * (i - 2) + 0.4, s2, size=1.1, anchor="middle", italic=True)
    for i, (a0, b0, a1, b1) in enumerate(CableSlots):
        up.Obround(a0, b0, a1, b1, stroke=0.35)
        sh.Text(up.X((a0 + a1) / 2), up.Y((b0 + b1) / 2) + 0.45, "slot %d" % (i + 1), size=1.05,
                anchor="middle", halo=True)
    Entries(up, "upper")
    up.DimH(0, BoxD, up.Bottom, "18 in (457 mm)")
    up.DimV(0, BoxW, BoxD, "13 in (330 mm)")

    # ------------------------------------------------ lower deck plan
    lo = View(sh, 150.0, 25.0, BoxD, BoxW, S, down=True)
    lo.Title("B  Lower deck, upper deck lifted off", "1/16 in aluminum base plate, bonded to PE")
    PlanFrame(lo, "parts inside the bottom ring, 417 x 290 mm")
    Plan(lo, "lower")
    # the 110 VAC compartment's edge: a line on the deck, no wall (ADR-0013)
    sh.Add('<path d="M%s %s L%s %s L%s %s" fill="none" stroke="%s" stroke-width=".6" '
           'stroke-dasharray="2.4 1.2"/>'
           % (Fmt(lo.X(BoxD - F)), Fmt(lo.Y(MainsZoneY)), Fmt(lo.X(MainsZoneX)), Fmt(lo.Y(MainsZoneY)),
              Fmt(lo.X(MainsZoneX)), Fmt(lo.Y(BoxW - F)), TolRed))
    gu = DoorGland[0]
    lo.Box(BoxD - F, gu - DoorGland[2] / 2, BoxD, gu + DoorGland[2] / 2, fill="#fff", stroke=0.3)
    sh.Text(lo.X(BoxD) + 1.5, lo.Y(gu) + 0.5, "door 110 V", size=1.1, rot=-90, anchor="middle")
    r110 = LowerRails()["110 V"]
    sh.Text(lo.X((r110["a0"] + BoxD - F) / 2), lo.Y((MainsZoneY + r110["centre"] - 41.0) / 2) + 0.5,
            "110 VAC compartment, no wall", size=1.3, anchor="middle", weight="bold", fill=TolRed)
    lo.Box(BoxD - F, InletU - 21, BoxD, InletU + 21, fill=ZoneFill["110"], stroke=0.35)
    sh.Text(lo.X(BoxD) + 1.5, lo.Y(InletU) + 0.5, "mains in", size=1.2, rot=-90, anchor="middle")
    lo.Box(PsuVentSpan[0], BoxW, PsuVentSpan[1], BoxW + 2.0, fill="#fff", dashed=True, stroke=0.2)
    sh.Text(lo.X(PsuVentSpan[0] + 30), lo.Y(BoxW - F / 2) + 0.4, "PSU vent (dashed)", size=1.0, halo=True)
    Entries(lo, "lower")

    # ------------------------------------------------ elevations
    RailFill, ClipFill = "#888888", "#FFFFFF"

    def Elevation(v, depth):
        """Every solid seen from the front (depth "x": a = y) or from the right wall (depth "y": a = x,
        so the front stays at the left, under the plan), painted farthest first: DIN rails dark,
        printed clips white and dashed."""
        if depth == "x":
            order = lambda t: -t["box"][0]       # the front face nearest
        else:
            order = lambda t: t["box"][3]        # the right wall's side nearest
        for s in sorted(solids, key=order):
            x0, y0, x1, y1 = s["box"]
            a0, a1 = (y0, y1) if depth == "x" else (x0, x1)
            base = LoDeck if s["deck"] == "lower" else UpDeck
            if s["kind"] == "rail":
                v.Box(a0, base, a1, base + DinRailH, fill=RailFill, stroke=0.12)
                continue
            z = base + (DinRailH if s["mount"] in ("rail", "clip") else 0.0)
            if s["mount"] == "clip":
                v.Box(a0, z, a1, z + Clip, fill=ClipFill, dashed=True, stroke=0.15)
                z += Clip
            v.Box(a0, z, a1, base + s["top"], fill=s["fill"], dashed=s["dashed"], stroke=0.2)

    def Tag(v, a, z, lines, size=1.1, rot=0):
        """A label over an elevation, in the middle of what shows of a part."""
        for i, s2 in enumerate(lines):
            off = (i - (len(lines) - 1) / 2) * size * 1.18
            if rot:
                sh.Text(v.X(a) + off + size * 0.35, v.Y(z), s2, size=size, anchor="middle", rot=rot, halo=True)
            else:
                sh.Text(v.X(a), v.Y(z) + off + size * 0.35, s2, size=size, anchor="middle", halo=True)

    def Mid(rail, key=None):
        """Centre of a rail's run, or of its parts whose key or label is `key`, along the rail."""
        p = [q for q in rail["run"] if key is None or key in q[:2]]
        return (p[0][2] + p[-1][3]) / 2

    lower = LowerRails()
    fr = View(sh, 10.0, 127.5, BoxW, BoxH, S)
    fr.Title("C  End view from the front", "front rails left off; heights, DIN rails dark grey")
    SectionFrame(fr, BoxW)
    Elevation(fr, "x")
    Tag(fr, lower["fuses"]["centre"], LoDeck + 31, ["FB1, FB2"])
    Tag(fr, lower["24 V"]["centre"], LoDeck + 45, ["K2", "24 V rail"])
    Tag(fr, lower["24 V PSU"]["centre"], LoDeck + 44, ["24 V PSU, flat", "fan face to the right"])
    Tag(fr, upper["field"]["centre"], UpDeck + 21, ["UK 2.5 B", "42 on rail"])
    Tag(fr, upper["logic"]["centre"], UpDeck + 34, ["Mega", "35 + 17.5"])
    Tag(fr, upper["SSR"]["a0"] / 2 + upper["SSR"]["a1"] / 2, UpDeck + 66, ["SSRs behind"], size=1.0)
    Tag(fr, upper["drivers"]["centre"], UpDeck + 50, ["TB6600s", "68 + clip 10 + rail 7.5"], size=1.15)
    Tag(fr, sum(UpRows["motor duct"]) / 2, UpDeck + 19, ["motor duct"], size=1.0, rot=-90)
    fr.DimV(LoDeck, UpPlate0, BoxW, "%s mm lower" % Mm(UpPlate0 - LoDeck))
    fr.DimV(UpDeck, TopIn, BoxW, "%s mm upper" % Mm(round(TopIn - UpDeck, 1)))
    sh.Text(fr.X(upper["drivers"]["centre"]), fr.Y(TopIn - 6) + 0.4,
            "%d mm over the drivers for the top-face wires" % round(room), size=1.15, anchor="middle")
    sh.Text(fr.X(56), fr.Y(MidF0 + F / 2) + 0.45, "mid ring", size=1.1, anchor="middle", halo=True)
    sh.Text(fr.X(BoxW / 2), fr.Y(TopIn + F / 2) + 0.45,
            "lid ring: off alone (4 screws) or with the upper module", size=1.15, anchor="middle",
            halo=True)
    sh.Text(fr.X(2), fr.Y(0) + 2.4, "LEFT", size=1.2, weight="bold")
    sh.Text(fr.X(BoxW / 2), fr.Y(0) + 2.4, "base plate under the frame", size=1.1, anchor="middle")
    sh.Text(fr.X(BoxW - 2), fr.Y(0) + 2.4, "RIGHT", size=1.2, weight="bold", anchor="end")

    # Seen from the right wall, projected from plan B above it: the 24 V PSU, the 110 V rail and the
    # motor duct stand nearest and hide the fuse modules, the field terminals and the Mega.
    sd = View(sh, 150.0, 127.5, BoxD, BoxH, S)
    sd.Title("D  Side view from the right", "right rails left off; nearer parts hide farther ones")
    SectionFrame(sd, BoxD)
    Elevation(sd, "y")
    mainsDuct = [s["box"] for s in solids if s["kind"] == "duct" and s["mains"]][0]
    clamp = ClampBox()
    Tag(sd, Mid(lower["24 V PSU"]), LoDeck + 42, ["24 V PSU, flat", "fan face this side"])
    Tag(sd, Mid(lower["24 V"], "K2"), LoDeck + 71.6, ["K2 behind"], size=1.0)
    Tag(sd, (mainsDuct[0] + mainsDuct[2]) / 2, LoDeck + 12.7, ["mains"], size=1.0, rot=-90)
    for label, z in (("PE", 30), ("X1", 30), ("K1", 60), ("F0", 55), ("X0", 30)):
        Tag(sd, Mid(lower["110 V"], label), LoDeck + z, [label])
    # the strips of the 5 V PSU and FB1 that show over the 42 mm terminal blocks
    Tag(sd, Mid(lower["110 V"], "X0"), LoDeck + 45.7, ["5 V PSU behind"], size=0.9)
    Tag(sd, (Mid(lower["110 V"], "PE") + Mid(lower["110 V"], "X1")) / 2, LoDeck + 46.3, ["FB1 behind"], size=0.9)
    Tag(sd, (upper["drivers"]["a0"] + clamp[0]) / 2, UpDeck + 19, ["motor duct"])
    Tag(sd, (clamp[0] + clamp[2]) / 2, UpDeck + 20, ["shield clamp"], size=1.0, rot=-90)
    for key, label, a0, a1 in upper["drivers"]["run"]:
        Tag(sd, (a0 + a1) / 2, UpDeck + 70, [label], size=1.4)
    Tag(sd, upper["SSR"]["centre"], UpDeck + 60, ["SSRs"])
    Tag(sd, BackRunX, UpDeck + 19, ["back run"], size=1.0, rot=-90)
    sd.DimV(0, BoxH, BoxD, "11 in (279 mm)")
    sh.Text(sd.X(2), sd.Y(0) + 2.4, "FRONT", size=1.2, weight="bold")
    sh.Text(sd.X(BoxD - 2), sd.Y(0) + 2.4, "BACK", size=1.2, weight="bold", anchor="end")

    # ------------------------------------------------ legend and notes
    cx = 291.0
    sh.Text(cx, 26.0, "Zones", size=2.2, weight="bold")
    zones = [(ZoneFill["110"], "110 VAC and the PSU"), (ZoneFill["24"], "24 V distribution and DC-DC"),
             (ZoneFill["drv"], "drives"), (ZoneFill["log"], "logic and SSRs"),
             (ZoneFill["fld"], "field terminals"), (ZoneFill["frame"], "2020 frame (posts darker)"),
             (LidFill, "lid ring, lifts off"), (PlateFill, "1/16 in aluminum plate, edge-on"),
             ("#888888", "DIN rail, 7.5 tall (elevations)")]
    for i, (fill, lab) in enumerate(zones):
        y = 29.5 + i * 3.0
        sh.Add('<rect x="%s" y="%s" width="5" height="2.2" fill="%s" stroke="#000" stroke-width=".2"/>'
               % (Fmt(cx), Fmt(y - 1.7), fill))
        sh.Text(cx + 6.4, y, lab, size=1.5)
    y = 29.5 + len(zones) * 3.0
    sh.Add('<rect x="%s" y="%s" width="5" height="2.2" fill="#fff" stroke="#000" stroke-width=".25"/>'
           % (Fmt(cx), Fmt(y - 1.7)))
    sh.Text(cx + 6.4, y, "solid outline: measured or datasheet", size=1.5)
    y += 3.0
    sh.Add('<rect x="%s" y="%s" width="5" height="2.2" fill="#fff" stroke="#000" stroke-width=".25" '
           'stroke-dasharray="1.2 .7"/>' % (Fmt(cx), Fmt(y - 1.7)))
    sh.Text(cx + 6.4, y, "dashed: size assumed, measure", size=1.5)
    at = {k: Mm(u) for _, u, _, k in CableEntries}
    if LowBayEntry > LowBayParts:
        bay = ["The lower left grommet sets the lower bay:",
               "its %s mm ring needs a %s mm window between" % (Mm(RingOD), Mm(LowBayEntry - 2 * F)),
               "the bottom and mid rings. K2 alone would set",
               "%s, which leaves %s (ADR-0011)." % (Mm(LowBayParts), Mm(LowBayParts - 2 * F))]
    else:
        bay = ["K2, the tallest lower part, sets the lower", "bay: %s + %s." % (Mm(MountedH("K2")), Mm(PartClear))]
    notes = [
        ("Mounting", [
            "Every part stands on a 7.5 mm DIN rail; parts",
            "without DIN feet add a printed clip, 10 mm.",
            "TB6600s stand on their 96 x 28 base, ears",
            "88 apart across the rail, fins vertical. The",
            "24 V PSU lies flat on a 215 x 115 face, its",
            "fan face %s mm from the right panel. The Mega" % Mm(BoxW - PsuY1),
            "lies along its rail, USB jack to the front",
            "grommet; the SSR sockets stand across their",
            "own short rail."]),
        ("Height budget (mm)", [
            "base plate %s, lower bay %s, upper plate %s,"
            % (Mm(BasePlateT), Mm(LowBay), Mm(UpPlateT)),
            "rail %s + clip 10 + drivers 68, wire room %s,"
            % (Mm(DinRailH), Mm(round(room, 1))),
            "lid ring 20 = 279.4."] + bay),
        ("Build and access", [
            "Two modules, like a platform-framed house.",
            "Lower: base plate, bottom ring and lower",
            "posts; stages 3 and 4 run on it alone.",
            "Upper: mid ring, upper plate, upper posts",
            "and lid ring, built and wired on the bench,",
            "then set on 4 studs in the lower posts that",
            "locate the decks. Inter-deck wires cross on",
            "pluggable terminals. Frame: sheet 4."]),
        ("Heat and cables", [
            "6 mm between drivers for air. The PSU fan",
            "blows into the vent in the lower right panel;",
            "its slots wait for the fan's size. Five 50 mm",
            "grommets: upper left at x %s (field) and" % at["UL"],
            "x %s (motors, at the back run's end), upper" % at["ULM"],
            "front (USB, J11, Pi GPIO), upper right (a",
            "motor, the tower), lower left (ODrive 24 V,",
            "Pi 5 V, E-stop). Mains in at the back wall in",
            "line with the 110 V rail; the 110 V door cable",
            "leaves beside it by an M20 gland; no wall",
            "around the mains parts (ADR-0013)."]),
        ("Sizes: along x across x high (mm)", [
            "TB6600 28 x 96 x 68, measured. From the",
            "listings: K1 HC1-63 36 x 82 x 65; K2 BMC7-25U",
            "36 x 85 x 68; FB1 and FB2 153 x 48 x 43;",
            "uxcell bar 20 x 78 x 53; SSR 6.1 x 88 x 71",
            "(41F-1Z socket); UK 2.5 B 6.2 x 42.5 x 42;",
            "5 V PSU 76 x 76 x 32; 6 V 63 x 58 x 23; Mega",
            "99 x 53 (A000067). Assumed (dashed): 24 V PSU",
            "215 x 115 x 50, F0, end clamps, PE blocks,",
            "shield clamp, Mega height. Heights add the rail."]),
        ("Layout 3b (ADR-0010)", [
            "From the CP-SAT packing study: %s" % "{:,}".format(wireDrawn),
            "conductor-mm as drawn (%s at the study's" % "{:,}".format(wireStudy),
            "%s bay), against %s for the hand layout." % (Mm(LowBayParts), "{:,}".format(HandWire)),
            "Each block centre is held to layout3b_build",
            ".json; no box overlaps another, and no plate",
            "slot lies over the mains (y %s and up)." % Mm(MainsZoneY)]),
    ]
    y += 4.6
    for head, lines in notes:
        sh.Text(cx, y, head, size=1.75, weight="bold")
        y += 2.4
        for s2 in lines:
            sh.Text(cx, y, s2, size=1.45)
            y += 1.95
        y += 1.1
    if y > 186.0:
        raise ValueError("sheet 3 notes run into the title block (y %.1f)" % y)
    TitleBlock(sh, 288, 186, 60, 21.5, [
        "Packing study",
        "Sheet 3. Legal, landscape, 100 %. Scale 1:3.5.",
        "Layout 3b (ADR-0010), 2026-10-17: the PSU",
        "flat, every part at its real size.",
        "Frame and plates: sheet 4. Measure dashed sizes.",
    ])
    return sh


# ---------------------------------------------------------------- sheet 4: frame and deck plates

def RailProfile():
    """Simplified 2020 outline in rail-local (u right, v down from the top face): four slots
    drawn from SlotOpen, SlotLip, SlotCavity and SlotDepth."""
    lo, hi = 10 - SlotOpen / 2, 10 + SlotOpen / 2
    c0, c1 = 10 - SlotCavity / 2, 10 + SlotCavity / 2
    web = 1.2                      # cavity floor stops short of the core corners: the webs
    k0, k1 = SlotDepth + web, 20 - SlotDepth - web
    top = [(0.0, 0.0), (lo, 0.0), (lo, SlotLip), (c0, SlotLip), (c0, 3.0), (k0, SlotDepth),
           (k1, SlotDepth), (c1, 3.0), (c1, SlotLip), (hi, SlotLip), (hi, 0.0)]
    pts = []
    for k in range(4):
        side = top
        for _ in range(k):
            side = [(20 - v, u) for u, v in side]
        pts += side
    return pts


def Bracket(v, a, b, da, db):
    """Corner bracket glyph: right angle at (a, b), legs 18 mm along da and db (+1 or -1)."""
    v.Poly([(a, b), (a + 18 * da, b), (a, b + 18 * db)], fill=BracketFill, stroke=0.2)


def ModuleBrace(sh, x, y0, y1, label):
    """Bracket left of an elevation that names the module between paper y0 (top) and y1."""
    sh.Wire([(x + 1.0, y0 + 0.3), (x, y0 + 0.3), (x, y1 - 0.3), (x + 1.0, y1 - 0.3)], "sg")
    sh.Text(x - 0.6, (y0 + y1) / 2, label, size=1.2, anchor="middle", rot=-90, weight="bold")


def FrameElevation(sh, v, span, fromFront):
    """The frame seen from the right side (span = BoxD, the front at the left, under the plates) or
    from the front (span = BoxW)."""
    F = Frame
    dash = ' stroke-dasharray="1 .6"'
    railLen = RingShort if fromFront else RingLong
    v.Box(0, 0, span, LoDeck, fill=PlateFill, stroke=0.1)
    for a0 in (0.0, span - F):
        v.Box(a0, LoDeck, a0 + F, MidF0, fill=PostFill, stroke=0.25)
        v.Box(a0, UpDeck, a0 + F, TopIn, fill=PostFill, stroke=0.25)
    v.Box(F, LoDeck, span - F, LoDeck + F, fill=ZoneFill["frame"], stroke=0.25,
          lines=["bottom ring %s" % Mm(railLen)], size=1.25, bold=False)
    v.Box(0, MidF0, span, UpPlate0, fill=ZoneFill["frame"], stroke=0.25)
    v.Box(0, UpPlate0, span, UpDeck, fill=PlateFill, stroke=0.1)
    v.Box(0, TopIn, span, BoxH, fill=LidFill, stroke=0.25)
    if fromFront:
        # the long rails of the mid and lid rings, end-on at the corners
        for a0 in (0.0, span - F):
            v.Box(a0, MidF0, a0 + F, UpPlate0, fill=ZoneFill["frame"], stroke=0.25)
            v.Box(a0, TopIn, a0 + F, BoxH, fill=LidFill, stroke=0.25)
    sh.Text(v.X(span / 2), v.Y(MidF0 + F / 2) + 0.45,
            "mid ring %s%s" % (Mm(railLen if fromFront else BoxD),
                               "" if fromFront else ": the upper module's platform"),
            size=1.25, anchor="middle")
    sh.Text(v.X(span / 2), v.Y(TopIn + F / 2) + 0.45,
            "lid ring %s%s" % (Mm(railLen if fromFront else BoxD),
                               "" if fromFront else ": off alone with 4 screws"),
            size=1.25, anchor="middle")
    for a0, da in ((F, 1), (span - F, -1)):
        Bracket(v, a0, LoDeck + F, da, 1)       # bottom ring to lower post
        Bracket(v, a0, MidF0, da, -1)           # lower post to mid ring: holds the modules
        Bracket(v, a0, UpDeck, da, 1)           # upper post, rail leg on the plate
    for a in (F / 2, span - F / 2):
        sh.Text(v.X(a) + 0.45, v.Y((LoDeck + MidF0) / 2), "lower post %s" % Mm(LowPostL),
                size=1.15, anchor="middle", rot=-90)
        sh.Text(v.X(a) + 0.45, v.Y((UpDeck + TopIn) / 2), "upper post %s" % Mm(UpPostL),
                size=1.15, anchor="middle", rot=-90)
        # locating stud: lower post top, through the mid ring and the plate, into the upper post
        v.Box(a - 2.5, MidF0 - StudLow, a + 2.5, UpDeck + StudSock, fill="#444444", stroke=0.1)
        # lid screw into the upper post top, foot screw into the lower post bottom
        v.Box(a - 4.25, BoxH, a + 4.25, BoxH + 5, fill="#fff", stroke=0.2)
        sh.Wire([(v.X(a), v.Y(BoxH)), (v.X(a), v.Y(BoxH - 35))], "sg", dash)
        v.Box(a - 10, -8, a + 10, 0, fill="#fff", dashed=True, stroke=0.2)
        sh.Wire([(v.X(a), v.Y(-8)), (v.X(a), v.Y(LoDeck + 12))], "sg", dash)
    ModuleBrace(sh, v.X0 - 3.2, v.Y(MidF0), v.Y(0), "LOWER MODULE")
    ModuleBrace(sh, v.X0 - 3.2, v.Y(BoxH), v.Y(MidF0), "UPPER MODULE")


def BuildFrame():
    sh = Sheet("RMR control panel frame and deck plates")
    DrawFrame(sh, "RMR control panel: frame and deck plates",
              "2020 frame %s x %s x %s mm (inside 18 x 13 x 11 in) in two modules, on two 1/16 in 5052 "
              % (Mm(BoxD), Mm(BoxW), Mm(BoxH)) +
              "deck plates, with 1/8 in acrylic walls. Views 1:5, detail E 2:1, printed at 100 %. Millimetres.")
    S = 5.0
    F = Frame

    # ------------------------------------------------ the two plates, from above
    for kind, x0, title, sub in [("base", 16.0, "A  Base plate, lower deck", "deck_base_plate.dxf"),
                                 ("upper", 130.0, "B  Upper plate", "deck_upper_plate.dxf")]:
        v = View(sh, x0, 30.0, BoxD, BoxW, S, down=True)
        v.Title(title, sub)
        outline, holes, slots = PlateGeom(kind)
        v.Poly(outline, fill="#EEEEEE", stroke=0.3)
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="#000" '
               'stroke-width=".18" stroke-dasharray="1 .6"/>'
               % (Fmt(v.X(F)), Fmt(v.Top(F, BoxW - F)), Fmt(RingLong / S), Fmt(RingShort / S)))
        for x, y in PostCentres:
            v.Box(x - F / 2, y - F / 2, x + F / 2, y + F / 2, fill="none", dashed=True, stroke=0.18)
        for s in slots:
            v.Obround(*s)
        for i, (a0, b0, a1, b1) in enumerate(CableSlots if kind == "upper" else []):
            sh.Text(v.X((a0 + a1) / 2), v.Top(b0, b1) - 0.6, str(i + 1), size=1.3, anchor="middle",
                    weight="bold")
        for x, y, d in holes:
            v.Hole(x, y, d)
        if kind in PeStud:
            px, py = PeStud[kind]
            sh.Text(v.X(px) - 1.2, v.Y(py) + 0.45, "PE", size=1.2, anchor="end", weight="bold")
        ty = 0.75 * BoxW               # clear of the cable slots and the PE studs
        sh.Text(v.X(BoxD / 2), v.Y(ty) - 1.0, "5052-H32, 1/16 in: sheared and drilled", size=1.6,
                anchor="middle", weight="bold")
        sh.Text(v.X(BoxD / 2), v.Y(ty) + 1.4,
                "seen from above, front on the left; the DXF (y up) shows it from below", size=1.3,
                anchor="middle")
        sh.Text(v.X(BoxD / 2), v.Y(ty) + 3.2, "dashed: %s" %
                ("posts and bottom ring on the plate" if kind == "base"
                 else "upper posts on the plate, mid ring under it"), size=1.3, anchor="middle")
        xs = sorted(set(round(x, 1) for x, _, _ in holes) | {0.0, BoxD})
        ys = sorted(set(round(y, 1) for _, y, _ in holes) | {0.0, BoxW})
        v.OrdX(xs, v.Bottom)
        v.OrdY(ys, 0)
        v.DimV(0, BoxW, BoxD, Mm(BoxW))
        nRing = len(RingHoles())
        tails = [length - sum(stack) - BasePlateT for _, _, length, stack, _ in ThroughScrews]
        floorGap = FootH - PlateSag(E5052, Nu5052, BasePlateT) - max(tails)
        hangGap = min((g for g, _, _ in HangGaps().values()), default=LowBay)
        openWin = OpenScrews()
        bars = [w for w in openWin if "ground bar" in w[0]]
        barLen = [math.ceil((ToothWasherT + max(BasePlateT, UpPlateT) + max(w[3] for w in bars)) * 10) / 10,
                  math.floor((ToothWasherT + min(BasePlateT, UpPlateT) + min(w[4] for w in bars)) * 10) / 10]
        clampW = [w for w in openWin if w[0] == "shield clamp"][0]
        clampLen = [math.ceil((UpPlateT + clampW[3]) * 10) / 10, math.floor((UpPlateT + clampW[4]) * 10) / 10]
        if kind == "base":
            px, py = PeStud[kind]
            sched = ["%d x %s%s: M5 into the lower posts, with the feet" % (len(PostCentres), Dia, Mm(HoleM5)),
                     "%d x %s%s: M4 x 6 into the bottom ring T-nuts, from below" % (nRing, Dia, Mm(HoleRing)),
                     "%s%s at (%s, %s): PE stud, first screw of the lower ground bar" % (Dia, Mm(HoleM5), Mm(px), Mm(py)),
                     "Drill through the acrylic template (sheet B's DXF plus this PE stud).",
                     "DIN rail and duct holes from the final layout: M4 x 12, nyloc nut below; the tails end %s mm "
                     "or more over the floor with the plate's sag (NutFits)" % Mm(math.floor(floorGap * 10) / 10),
                     "Ground bar screws, both plates: M5, plain nut below, tooth washer under the bar; the bar's foot "
                     "+ %s to + %s long (OpenScrews)" % (Mm(barLen[0]), Mm(barLen[1]))]
        else:
            px, py = PeStud[kind]
            sched = ["%d x %s%s: the locating studs. %d x %s%s: M4 x 6 into the mid ring T-nuts"
                     % (len(PostCentres), Dia, Mm(HoleM5), nRing, Dia, Mm(HoleRing)),
                     "%d slots %s wide, %s to %s from the edges: upper-post bracket screws, M4 x 10. PE stud at (%s, %s)"
                     % (len(BracketSlots()), Mm(HoleRing), Mm(BracketSlotA), Mm(BracketSlotB), Mm(px), Mm(py)),
                     "Template: cut this DXF from 1/8 in acrylic; drill, then nibble the slots to it.",
                     "DIN rail and duct holes from the final layout: M4 x 12, nyloc below, %s mm or more from each end"
                     % Mm(ScrewEnd),
                     "of the run; the tails end %s mm or more over what stands below (HangGaps)"
                     % Mm(math.floor(hangGap * 10) / 10),
                     "Shield clamp: M4 into a nyloc, the clamp's base + %s to + %s long; ground bar screws off the mid "
                     "ring and its corner brackets (OpenScrews)" % (Mm(clampLen[0]), Mm(clampLen[1])),
                     "Cable slots, round ends, edge trim:  " +
                     ";  ".join("%d: x %s-%s, y %s-%s" % (i + 1, Mm(a0), Mm(a1), Mm(b0), Mm(b1))
                                for i, (a0, b0, a1, b1) in enumerate(CableSlots)),
                     "  ".join("%d: %s." % (i + 1, u) for i, u in enumerate(SlotUse)) +
                     "  None over the 110 VAC compartment (y %s up)." % Mm(MainsZoneY)]
        sh.Lines(v.X(0), v.Y(v.Bottom) + 8.2, sched, size=1.3, lead=1.85)

    # ------------------------------------------------ the frame from the right and from the front
    sd = View(sh, 18.0, 133.0, BoxD, BoxH, S)
    sd.Title("C  Frame from the right side", "studs dark, screws dashed")
    FrameElevation(sh, sd, BoxD, False)
    sd.DimV(LoDeck, UpPlate0, 300, "%s lower bay" % Mm(UpPlate0 - LoDeck))
    sd.DimV(UpDeck, TopIn, 300, "%s upper bay" % Mm(TopIn - UpDeck))
    sh.Text(sd.X(BoxD / 2), sd.Y(0) + 2.2, "base plate; feet add their height", size=1.2,
            anchor="middle")
    xL = sd.X(BoxD) + 1.0
    sh.Text(xL + 0.6, sd.Y(BoxH) - 3.0, "z", size=1.3, weight="bold")
    for z, dy in [(0.0, 1.3), (LoDeck, -0.25), (LoDeck + F, 0.45), (MidF0, 0.45), (UpPlate0, 1.3),
                  (UpDeck, -0.25), (TopIn, 0.45), (BoxH, 0.45)]:
        sh.Wire([(xL, sd.Y(z)), (xL + 1.6, sd.Y(z))], "sg")
        sh.Text(xL + 2.0, sd.Y(z) + dy, Mm(z), size=1.15)
    sd.DimH(0, BoxD, 0, Mm(BoxD), off=6.2)

    fr = View(sh, 140.0, 133.0, BoxW, BoxH, S)
    fr.Title("D  Frame from the front")
    FrameElevation(sh, fr, BoxW, True)
    sh.Text(fr.X(BoxW / 2), fr.Y((LoDeck + MidF0) / 2), "lower bay", size=1.3, anchor="middle")
    sh.Text(fr.X(BoxW / 2), fr.Y((UpDeck + TopIn) / 2), "upper bay", size=1.3, anchor="middle")
    fr.DimV(0, BoxH, BoxW, "279.4 (11 in)")
    fr.DimH(0, BoxW, 0, Mm(BoxW), off=6.2)

    # ------------------------------------------------ detail E: a plate on a ring rail, 2:1
    fits = {j: (scr, tip) for j, scr, tip, _ in ScrewFits()}
    de = View(sh, 240.0, 33.0, 26.0, 27.0, 0.5)
    de.Title("E  Plate on a ring rail", "2:1")
    prof = [(u, 20 - w) for u, w in RailProfile()]
    de.Poly(prof, fill=ZoneFill["frame"], stroke=0.25)
    de.Hole(10, 10, BoreD)
    top = 20 + UpPlateT
    de.Box(0, 20, 26, top, fill="#999999", stroke=0.25)
    de.Box(6.0, 20 - SlotLip - 3.5, 14.0, 20 - SlotLip, fill="#666666", stroke=0.2)
    scr, tipLen = fits["upper plate to mid ring"]
    tip = 20 - tipLen
    de.Box(8.0, tip, 12.0, top, fill="#BBBBBB", stroke=0.2)
    de.Box(10 - HeadM4 / 2, top, 10 + HeadM4 / 2, top + HeadM4H, fill="#BBBBBB", stroke=0.25)
    de.DimH(10 - SlotOpen / 2, 10 + SlotOpen / 2, 0, "%s opening" % Mm(SlotOpen), off=2.4)
    de.DimV(20 - SlotDepth, 20, 20, "%s slot" % Mm(SlotDepth), off=2.0)
    de.DimV(tip, 20, 0, "%s tip" % Mm(tipLen), right=False, off=2.0)
    de.DimV(20, top, 26, Mm(UpPlateT), off=2.0)
    sh.Text(de.X(22), de.Y(20 + UpPlateT / 2) + 0.42, "plate", size=1.1, anchor="middle")
    sh.Text(de.X(14.6), de.Y(top + 1.1) + 0.45, "%s socket head" % scr, size=1.2)
    sh.Text(de.X(10), de.Y(20 - SlotLip - 1.75) + 0.4, "T-nut", size=1.0, anchor="middle", fill="#fff")
    sh.Text(de.X(13), de.Y(3.6), "2020, simplified", size=1.1, anchor="middle", halo=True)
    sh.Lines(de.X(0), de.Y(-1) + 5.6, [
        "Euro 2020, 6 mm slot. Depth %s, lip %s, bore %s:" % (Mm(SlotDepth), Mm(SlotLip), Mm(BoreD)),
        "assumed; measure the first stick.",
        "Base plate: the same joint upside down, from below."],
        size=1.2, lead=1.7)

    # ------------------------------------------------ notes beside the detail
    short = {"base plate to bottom ring, from below": "base plate",
             "upper plate to mid ring": "upper plate",
             "upper-post bracket leg through the upper plate": "bracket leg",
             "acrylic panel to the frame": "acrylic panel",
             "aluminum back panel to the frame": "back panel + washer",
             "mount bracket over the acrylic front panel": "mount, front panel",
             "mount bracket over the aluminum back panel": "mount, back panel",
             "mount bracket to a gantry member": "mount, gantry"}
    bond, _ = BondSummary()

    def Bars(n):
        return "%d bar%s" % (n, "" if n == 1 else "s")

    nx = 300.0
    notes = [
        ("Two modules", [
            "Like a platform-framed house. Lower module:",
            "base plate, bottom ring, 4 lower posts. Upper",
            "module, built and wired on the bench: mid ring",
            "(the platform), upper plate, 4 upper posts",
            "standing on the plate, lid ring. It drops onto",
            "4 M5 studs (%d long) in the lower post tops;" % round(StudL),
            "each passes the mid ring and the plate into a",
            "%s5.5 socket in its upper post, so the decks" % Dia,
            "line up within about 0.3 mm. 8 brackets from",
            "the lower posts to the mid ring hold it down."]),
        ("Joints", [
            "Corner brackets on the kit's M5 screws and",
            "sliding T-nuts, slid in before a joint closes:",
            "8 on the bottom ring, 8 lower posts to mid ring,",
            "4 in the mid ring, 8 upper posts (rail legs on",
            "the plate), 4 in the lid ring. Each plate,",
            "screwed every 97 mm or less, keeps its ring",
            "square: no diagonal braces."]),
        ("Screws, checked by ScrewFits()", [
            "Each stops 0.5 short of the slot floor and",
            "catches 3 or more threads of its spring T-nut:"] +
            ["%s: %s, tip %s" % (short[j], scr, Mm(t)) for j, (scr, t) in fits.items()] +
            ["Lid M5 x 35 needs 15 of end tap; feet M5 x 16."]),
        ("PE bonding", [
            "Anodize insulates: each rail is its own part.",
            "Drill %s4.2 through a slot floor into the bore," % Dia,
            "tap M5; M5 x 16 with a ring lug and a tooth",
            "washer. One 12 AWG home run per part to its",
            "module's bar: lower %d parts, %s; upper %d, %s."
            % (bond["lower"][0], Bars(bond["lower"][1]), bond["upper"][0], Bars(bond["upper"][1])),
            "DIN rails through their PE terminals, TB6600s",
            "under an ear screw. Measure each part to PE",
            "at 0.2 to 10 A (IEC 60204-1 18.2.2)."]),
        ("Stiffness", [
            "%d kg on a plate, simply supported on its ring" % round(DeckLoadKg),
            "(Timoshenko Table 8): %.1f mm for 1/16 in 5052." % PlateSag(E5052, Nu5052, BasePlateT)]),
    ]
    y = 30.0
    for head, lines in notes:
        sh.Text(nx, y, head, size=1.7, weight="bold")
        y += 2.3
        for s2 in lines:
            sh.Text(nx, y, s2, size=1.35)
            y += 1.8
        y += 1.0

    # ------------------------------------------------ cut list, plates and panels
    tx = 216.0

    def Table(y, widths, rows, size=1.3, lead=2.25):
        w = sum(widths)
        sh.Wire([(tx, y), (tx + w, y)], "zl")
        for i, row in enumerate(rows):
            cx = tx
            for wd, cell in zip(widths, row):
                sh.Text(cx + 0.7, y + lead - 0.6, cell, size=size, weight="bold" if i == 0 else "normal")
                cx += wd
            y += lead
            sh.Wire([(tx, y), (tx + w, y)], "zl" if i == 0 or i == len(rows) - 1 else "sg")
        return y

    pieces, sticks = CutPieces(), NestSticks()
    sh.Text(tx, 126.0, "Cut list: 2020, 6 mm slot, from 1000 mm sticks", size=1.7, weight="bold")
    y = Table(127.4, [27.0, 7.0, 11.0, 32.0], [["Part", "Qty", "Length", "Ends"]] +
              [[nm, str(n), Mm(L), ends] for nm, n, L, ends in pieces])
    plan = ["%d: %s" % (i + 1, " + ".join(Mm(L) for L in s)) for i, s in enumerate(sticks)]
    half = (len(plan) + 1) // 2
    sh.Lines(tx, y + 2.0, [
        "%d mm in %d pieces from %d sticks (kerf %s, one squaring cut each):"
        % (round(sum(n * L for _, n, L, _ in pieces)), sum(n for _, n, _, _ in pieces), len(sticks), Mm(Kerf)),
        "; ".join(plan[:half]) + ";",
        "; ".join(plan[half:]) + ".",
        "Cut equal parts against one stop: the plates set the squareness."],
        size=1.25, lead=1.75)
    y += 9.4
    nSheets = PanelNest()
    sheetOf = {name: sheet for sheet, parts in NestPlan().items() for name, _, _, _, _ in parts}
    sh.Text(tx, y + 2.0, "Plates and panels", size=1.7, weight="bold")
    rows = [["Part", "Nest sheet", "Size", "Material"]]
    rows += [[nm, sheetOf[nm], "%s x %s" % (Mm(BoxD), Mm(BoxW)), "5052, 1/16 in"]
             for nm in ("Base plate", "Upper plate")]
    rows += [[nm.split(":")[0], sheetOf[nm], "%s x %s" % (Mm(w), Mm(h)),
              "acrylic, 1/8 in" if mat == "acrylic" else "5052, 1/16 in"]
             for nm, n, w, h, mat, _ in EnclosurePanels()]
    rows.append(["%s x %d" % (RingName, len(CableEntries)), sheetOf[RingName],
                 "%s%s, bore %s" % (Dia, Mm(RingOD), Mm(GrommetSleeve - RingGrip)), "acrylic, 1/8 in"])
    y = Table(y + 3.4, [25.0, 14.0, 16.0, 20.0], rows, lead=2.0)
    nEntries = PanelChecks()
    web = min(CheckWebs(t)[0] for t in PanelDxfFiles().values())
    vents = TopVents()
    pending, hold = [], []
    if PsuFanD is None:
        pending.append("the PSU fan vent (its diameter)")
        hold.append("%s (%s)" % (PsuVentPanel.lower(), sheetOf[PsuVentPanel]))
    open_ = [k for k, cut in MainsCuts.items() if cut is None]
    if open_:
        pending += ["the %s cut-out" % k for k in open_]
        hold.append("the back panel template")
    walls = ["%s %s" % ("upper" if PanelWall[p][1] else "lower", PanelWall[p][0]) for p, _, _, _ in CableEntries]
    sides = ", ".join(("two " if walls.count(w) == 2 else "") + w
                      for i, w in enumerate(walls) if w not in walls[:i])
    text = (
        "Acrylic panels on %d sheets of 24 x 18 in, each inside the %s x %s laser bed: one DXF per "
        "sheet, panels_acrylic_1.dxf to _%d.dxf. The aluminum lower back panel carries the inlet and the door "
        "cable's M20 gland "
        "(every mains part sits on metal); drill and nibble it through "
        "panel_lower_back_template.dxf, cut from the spare sheet. Each part is drawn from outside: "
        "u along x (front at 0) or y (left at 0), v up; turn it over to match. Screws %s%s on the "
        "slot centre lines, %s from each post end, ring screws at an even pitch, except the lower front and "
        "back panels: their bottom post screws sit at %s in vertical slots, through the gantry mount "
        "brackets, and they have no ring screw (sheet 5); the top has 8 "
        "into the lid ring and %s%s over each lid screw. Vents: %d slots %s x %s on %s over the "
        "TB6600s. Cable entries: %d desk grommets in %s%s holes (%s), each held by a %s%s acrylic "
        "ring pressed onto its sleeve behind the wall; caliper one grommet before cutting. Q0 is "
        "the inlet's switch if that is 2-pole. Read back from the DXFs: least web %s mm (%s "
        "needed). Order list: bom_frame.csv."
        % (nSheets, Mm(LaserBed[0]), Mm(LaserBed[1]), nSheets, Dia, Mm(HoleM5), Mm(PostScrewIn),
           Mm(GantryScrewV), Dia, Mm(LidAccess), len(vents), Mm(VentW), Mm(vents[0][3] - vents[0][1]), Mm(VentPitch),
           nEntries, Dia, Mm(GrommetHole), sides, Dia, Mm(RingOD), Mm(web), Mm(PanelWeb)))
    if pending:
        text += (" NOT CUT YET, placeholders until the owner's data: %s. Hold the %s until then."
                 % (", ".join(pending), " and ".join(hold)))
    sh.Lines(tx, y + 2.0, textwrap.wrap(text, 118), size=1.2, lead=1.65)

    # ------------------------------------------------ assembly and title
    ax = 296.0
    sh.Text(ax, 126.0, "Assembly", size=1.7, weight="bold")
    steps = [
        ["Caliper a grommet and K2 before cutting:" if LowBayEntry > LowBayParts else
         "Measure K2 and the PSU before cutting:",
         "the %s sets the lower posts (%s). Measure"
         % ("lower grommet's ring" if LowBayEntry > LowBayParts else "tallest lower part", Mm(LowPostL)),
         "the first stick and a bracket leg, then rerun", "ScrewFits()."],
        ["Cut the list, equal parts against one stop.", "Tap and drill the ends; drill and tap one",
         "bond hole in every rail."],
        ["Lower module: feet and lower posts on the", "base plate, bottom ring on brackets, plate",
         "screws from below, studs in with threadlocker,", "ground bar on the PE stud."],
        ["Build the lower deck, every 110 VAC terminal", "finger-safe or covered (ADR-0013); bond and",
         "measure it."],
        ["Upper module, on the bench: mid ring on its", "corner brackets, upper plate on it, upper",
         "posts over the stud holes (a loose stud as a", "pin) with their brackets, then the lid ring.",
         "Ground bars on the upper PE stud; wire it."],
        ["Set it on the studs; 8 brackets to the lower", "posts; plug the inter-deck terminals; clamp",
         "the PE link; measure; panels last."]]
    y = 128.6
    for i, lines in enumerate(steps):
        sh.Text(ax, y, "%d" % (i + 1), size=1.3, weight="bold")
        sh.Lines(ax + 2.6, y, lines, size=1.3, lead=1.8)
        y += 1.8 * len(lines) + 0.5
    TitleBlock(sh, 288, 186, 60, 21.5, [
        "Frame and deck plates",
        "Sheet 4. Legal, landscape, 100 %.",
        "Views 1:5, detail E 2:1. Redrawn 2026-10-19.",
        "Two modules. Design, not yet built.",
        "DXFs: both deck plates, panel sheets, template.",
    ])
    return sh


FrameBrackets = 8 + 8 + 4 + 8 + 4  # bottom ring, lower posts to mid ring, mid ring, upper posts, lid ring


def BuildGantry():
    sh = Sheet("RMR control box in the gantry")
    g = GantryChecks()
    fits = {j: (scr, tip) for j, scr, tip, _ in ScrewFits()}
    F, S, t, tb = Frame, 5.0, BracketLegT, BasePlateT
    z = {(w, n): z0 for w, n, z0 in GantryMembers}
    zMid, zTop, zCtr = z[("front", "middle")], z[("front", "top")], z[("back", "center")]
    lift, boxTop = g["lift"], g["box top"]
    DrawFrame(sh, "RMR control box: mount in the gantry",
              "Four cast corner brackets hold the box to the gantry's lower members; it comes out by lifting %s "
              "and sliding forward under the front middle member. Views 1:5, detail C 1:1, printed at 100 %%. "
              "Millimetres; z up from the base plate's underside." % Mm(round(lift, 1)))
    span = zTop + F + 6.0
    panelFill, rubber = "#DDDDDD", "#555555"

    def Heads(v, a0, a1, zs):
        for zz in sorted(set(round(q, 2) for q in zs)):
            v.Box(min(a0, a1), zz - HeadM5 / 2, max(a0, a1), zz + HeadM5 / 2, fill="#BBBBBB", stroke=0.12)

    def BracketL(v, a, sgn):
        """The mount bracket seen from the side: inside corner at (a, F), horizontal leg outward (sgn)."""
        v.Poly([(a, F), (a + sgn * F, F), (a + sgn * F, F + t), (a + sgn * t, F + t), (a + sgn * t, 2 * F),
                (a, 2 * F)], fill=BracketFill, stroke=0.15)

    # ------------------------------------------------ A: from the right side, front on the left
    va = View(sh, 62.0, 30.0, BoxD, span, S)
    va.Title("A  Box in the gantry, from the right side", "front on the left")
    va.Line([(-90, -FootH), (BoxD + 90, -FootH)], "zl")
    sh.Text(va.X(BoxD + 88), va.Y(-FootH) + 2.0, "floor", size=1.2, anchor="end")
    va.Box(0, 0, BoxD, LoDeck, fill=PlateFill, stroke=0.1)
    va.Box(0, LoDeck, BoxD, MidF0, fill="#F6F6F6", stroke=0.2, lines=["lower module"], size=1.3)
    va.Box(0, MidF0, BoxD, UpPlate0, fill=ZoneFill["frame"], stroke=0.2)
    va.Box(0, UpPlate0, BoxD, UpDeck, fill=PlateFill, stroke=0.1)
    va.Box(0, UpDeck, BoxD, TopIn, fill="#F6F6F6", stroke=0.2, lines=["upper module"], size=1.3)
    va.Box(0, TopIn, BoxD, BoxH, fill=LidFill, stroke=0.2)
    va.Box(0, BoxH, BoxD, BoxH + PanelT, fill=panelFill, stroke=0.12)
    for x in sorted(set(round(u, 2) for u, _ in PanelScrews(TopPanel))):
        va.Box(x - HeadM5 / 2, BoxH + PanelT, x + HeadM5 / 2, boxTop, fill="#BBBBBB", stroke=0.12)
    va.Box(-PanelT, 0, 0, BoxH, fill=panelFill, stroke=0.15)
    va.Box(BoxD, 0, BoxD + tb, LowerPanelH, fill=PlateFill, stroke=0.12)
    va.Box(BoxD, LowerPanelH, BoxD + PanelT, BoxH, fill=panelFill, stroke=0.15)
    for x in (F / 2, BoxD - F / 2):
        va.Box(x - 10, -FootH, x + 10, 0, fill=rubber, stroke=0.12)
    for wall, x0, sgn in (("front", -PanelT, -1), ("back", BoxD + tb, 1)):
        upFace = -PanelT if wall == "front" else BoxD + PanelT
        zs = [z0 + v for name, (w, z0) in PanelWall.items() if w == wall for _, v in PanelScrews(name)]
        free = [q for q in zs if abs(q - GantryScrewV) > 1e-6]
        Heads(va, x0, x0 + sgn * HeadM5H, [q for q in free if q <= LowerPanelH])
        Heads(va, upFace, upFace + sgn * HeadM5H, [q for q in free if q > LowerPanelH])
        BracketL(va, x0, sgn)
        Heads(va, x0 + sgn * t, x0 + sgn * (t + HeadM5H), [GantryScrewV])
        xm = x0 + sgn * BracketHoleIn
        va.Box(xm - HeadM5 / 2, F + t, xm + HeadM5 / 2, F + t + HeadM5H, fill="#999999", stroke=0.12)
        for (w, name), m in sorted(z.items(), key=lambda kv: kv[1]):
            if w != wall:
                continue
            a0 = x0 if sgn > 0 else x0 - F
            va.Poly([(a0 + u, m + F - vv) for u, vv in RailProfile()], fill=ZoneFill["frame"], stroke=0.2)
            label = "%s %s, z %s to %s" % (wall, name, Mm(m), Mm(m + F))
            if (w, name) == ("front", "middle"):
                label += ": moved up %s" % Mm(round(m - (F + GantryMeasured["front lower to middle"]), 1))
            if sgn < 0:
                sh.Text(va.X(a0) - 1.0, va.Y(m + F / 2) + 0.45, label, size=1.2, anchor="end")
            else:
                sh.Text(va.X(a0 + F) + 1.0, va.Y(m + F / 2) + 0.45, label, size=1.2)
        a0 = x0 if sgn > 0 else x0 - F
        va.Box(a0, -FootH, a0 + F, 0, fill=rubber, stroke=0.12)
    # the way out: lifted, then forward
    va.Box(-PanelT, lift - FootH, BoxD + PanelT, boxTop + lift, fill="none", dashed=True, stroke=0.2)
    ya = TopIn - 25.0               # over the upper module's label
    va.Line([(BoxD * 0.6, ya), (-PanelT - F - 40, ya)], "sgc")
    va.Poly([(-PanelT - F - 46, ya), (-PanelT - F - 38, ya + 6), (-PanelT - F - 38, ya - 6)], fill="#000", stroke=0.1)
    sh.Text(va.X(BoxD * 0.3), va.Y(ya) - 1.0, "lifted %s (dashed), then out forward" % Mm(round(lift, 1)),
            size=1.3, anchor="middle", halo=True)
    xA = -PanelT - F
    va.DimV(F, zMid, xA, "%s (was %s)" % (Mm(GantryMidGap), Mm(GantryMeasured["front lower to middle"])),
            right=False, off=2.0)
    va.DimV(boxTop + lift, zMid, BoxD * 0.12, "%s clear" % Mm(round(g["forward"], 1)), off=0.0)
    va.DimV(zCtr + F, zTop, BoxD + tb + F, Mm(GantryMeasured["back center to top"]), off=2.0)
    va.DimV(-FootH, lift - FootH, BoxD * 0.5, "lift %s" % Mm(round(lift, 1)), off=0.0)
    xT = va.X(BoxD + tb + F) + 34.0
    sh.Text(xT + 0.6, va.Y(span) + 1.5, "z", size=1.3, weight="bold")
    for zz in sorted({0.0, F, BoxH, boxTop, zMid, zMid + F, zCtr, zCtr + F, zTop, zTop + F}):
        sh.Wire([(xT, va.Y(zz)), (xT + 1.6, va.Y(zz))], "sg")
        sh.Text(xT + 2.0, va.Y(zz) + 0.45, Mm(round(zz, 1)), size=1.1)

    # ------------------------------------------------ B: the front face
    vb = View(sh, 210.0, 30.0, BoxW, span, S)
    vb.Title("B  Front face, from the front", "the back brackets and screws match")
    vb.Line([(-25, -FootH), (BoxW + 25, -FootH)], "zl")
    for name in ("Lower front", "Upper front"):
        _, z0 = PanelWall[name]
        _, _, w, h, _, _ = PanelSpec(name)
        vb.Box(0, z0, w, z0 + h, fill="#EEEEEE", stroke=0.25)
        for p, u, v, _ in GrommetAt():
            if p == name:
                vb.Hole(u, z0 + v, GrommetFlange, fill="#888888")
        for u, v in PanelScrews(name):
            vb.Hole(u, z0 + v, HeadM5, fill="#BBBBBB")
    vb.Box(0, BoxH, BoxW, BoxH + PanelT, fill=panelFill, stroke=0.12)
    for u in (F / 2, BoxW - F / 2):
        vb.Box(u - HeadM5 / 2, BoxH + PanelT, u + HeadM5 / 2, boxTop, fill="#BBBBBB", stroke=0.12)
        vb.Box(u - 10, -FootH, u + 10, 0, fill=rubber, stroke=0.12)
    for (w, name), m in z.items():
        if w == "front":
            vb.Box(-25, m, BoxW + 25, m + F, fill=ZoneFill["frame"], stroke=0.2,
                   lines=["front %s member (2020), part shown" % name], size=1.2, bold=False)
    for wall, u in MountBrackets():
        if wall == "front":
            vb.Box(u - BracketW / 2, F, u + BracketW / 2, 2 * F, fill=BracketFill, stroke=0.15)
            vb.Hole(u, GantryScrewV, HeadM5, fill="#BBBBBB")
            vb.Box(u - HeadM5 / 2, F + t, u + HeadM5 / 2, F + t + HeadM5H, fill="#999999", stroke=0.12)
    vb.DimV(0, GantryScrewV, BoxW + 25, "%s" % Mm(GantryScrewV), off=1.6)
    sh.Lines(vb.X(0), vb.Y(-FootH) + 4.0, [
        "Lower front and back panels: the post screws at z %s pass the brackets; no bottom ring screw." % Mm(GantryScrewV),
        "Upper panels unchanged. The gantry feet stand under the lower members, %d in all." % GantryFeet],
        size=1.2, lead=1.7)

    # ------------------------------------------------ C: the front bracket, 1:1
    ox = PanelT + F + 7.0
    vc = View(sh, 289.0, 30.0, 60.0, 48.0, 1.0)
    vc.Title("C  Front mount bracket, 1:1", "section on a post")

    def A(a):
        return a + ox
    vc.Box(A(0), 0, A(29), LoDeck, fill=PlateFill, stroke=0.1)
    vc.Box(A(0), LoDeck, A(F), 46, fill=PostFill, stroke=0.2)
    vc.Box(A(F), LoDeck, A(29), LoDeck + F, fill=ZoneFill["frame"], stroke=0.2)
    vc.Box(A(-PanelT), 0, A(0), 46, fill=panelFill, stroke=0.2)
    vc.Poly([(A(-PanelT - F + u), F - vv) for u, vv in RailProfile()], fill=ZoneFill["frame"], stroke=0.2)
    vc.Poly([(A(-PanelT), F), (A(-PanelT - F), F), (A(-PanelT - F), F + t), (A(-PanelT - t), F + t),
             (A(-PanelT - t), 2 * F), (A(-PanelT), 2 * F)], fill=BracketFill, stroke=0.2)
    scrP, tipP = fits["mount bracket over the acrylic front panel"]
    scrM, tipM = fits["mount bracket to a gantry member"]
    vc.Box(A(SlotLip), GantryScrewV - 4, A(SlotLip + 3.5), GantryScrewV + 4, fill="#666666", stroke=0.15)
    vc.Box(A(-PanelT - t), GantryScrewV - 2.5, A(tipP), GantryScrewV + 2.5, fill="#BBBBBB", stroke=0.15)
    vc.Box(A(-PanelT - t - HeadM5H), GantryScrewV - HeadM5 / 2, A(-PanelT - t), GantryScrewV + HeadM5 / 2,
           fill="#BBBBBB", stroke=0.2)
    xm = -PanelT - BracketHoleIn
    vc.Box(A(xm - 4), F - SlotLip - 3.5, A(xm + 4), F - SlotLip, fill="#666666", stroke=0.15)
    vc.Box(A(xm - 2.5), F - tipM, A(xm + 2.5), F + t, fill="#BBBBBB", stroke=0.15)
    vc.Box(A(xm - HeadM5 / 2), F + t, A(xm + HeadM5 / 2), F + t + HeadM5H, fill="#BBBBBB", stroke=0.2)
    vc.Box(A(-PanelT - F), -FootH, A(-PanelT), 0, fill=rubber, stroke=0.12)
    vc.Box(A(F / 2 - 10), -FootH, A(F / 2 + 10), 0, fill=rubber, stroke=0.12)
    sh.Text(vc.X(A(-PanelT - F / 2)), vc.Y(F / 2) + 0.45, "gantry", size=1.1, anchor="middle", halo=True)
    sh.Text(vc.X(A(F / 2)), vc.Y(40) + 0.45, "post", size=1.1, anchor="middle", halo=True)
    sh.Text(vc.X(A(24.5)), vc.Y(LoDeck + F / 2) + 0.45, "ring", size=1.1, anchor="middle", halo=True)
    vc.DimV(F, GantryScrewV, A(-PanelT - F), "%s" % Mm(BracketHoleIn), right=False, off=1.6)
    vc.DimH(A(xm), A(-PanelT), 2 * F, Mm(BracketHoleIn), below=False, off=1.4)
    scrB, tipB = fits["mount bracket over the aluminum back panel"]
    sh.Lines(vc.X(0), vc.Y(-FootH) + 3.4, [
        "%s through leg and panel into the post's roll-in nut, tip %s;" % (scrP, Mm(round(tipP, 2))),
        "%s through the leg into the member's roll-in nut, tip %s." % (scrM, Mm(round(tipM, 2))),
        "Back: %s through leg and aluminum panel, tip %s." % (scrB, Mm(round(tipB, 2))),
        "Leg %s and holes %s from the corner: assumed, measure." % (Mm(BracketLegT), Mm(BracketHoleIn))],
        size=1.2, lead=1.65)

    # ------------------------------------------------ notes
    open_ = GantryOpen()
    notes = [
        ("The gantry (owner, 2026-10-19)", [
            "2020, 6 mm slot, so the kit's M5 roll-in T-nuts fit. The members run left to right in the",
            "planes of the box's front and back faces; the lower ones stand on the same rubber feet as the",
            "box (B08B87SRRG), their bottom faces level with the base plate's underside. Measured face to",
            "face: front, lower to middle %s and middle to top %s; back, center to top %s; front and back top"
            % (Mm(GantryMeasured["front lower to middle"]), Mm(GantryMeasured["front middle to top"]),
               Mm(GantryMeasured["back center to top"])),
            "at one height. The front middle member moves up to %s over the lower one, %s under the top one."
            % (Mm(GantryMidGap), Mm(round(g["mid to top"], 1)))]),
        ("Mount", [
            "%d spare cast corner brackets from the kit (40 bought, %d in the frame, 1 is the saw stop), one at"
            % (len(MountBrackets()), FrameBrackets),
            "each lower post, front and back: the vertical leg on the panel, held by the post's bottom panel",
            "screw at z %s in a %s x %s vertical slot, so the bracket seats on the member %s%s; the horizontal leg"
            % (Mm(GantryScrewV), Mm(HoleM5), Mm(MountSlotL), "\u00b1", Mm((MountSlotL - HoleM5) / 2)),
            "on the member's top face, one M5 into a roll-in T-nut. The front",
            "and back lower panels lose their bottom ring screw: the member backs their bottom edge. Not",
            "structural, and no bond: anodize insulates, so PE stays on the trunk to the gantry bar (ADR-0009)."]),
        ("Taking it out", [
            "Unplug the mains cord first. Free every cable that leaves the box: the door cable is wired to X1",
            "inside, through the M20 gland, so free it at the door (S1, H1); the field and motor cables, the Mega",
            "USB, and the PE trunk at the gantry bar. Take out the 4 member-side screws; the brackets stay on the",
            "box. Lift %s, so the feet clear a lower member by %s; any lift from %s to %s works."
            % (Mm(round(lift, 1)), Mm(LiftMargin), Mm(round(g["lift band"][0], 1)), Mm(round(g["lift band"][1], 1))),
            "Slide it out forward: its top (z %s with the top panel's screw heads) passes %s under the front"
            % (Mm(round(boxTop, 1)), Mm(round(g["forward"], 1))),
            "middle member. Out the back it would pass %s under the back center member, behind the mains."
            % Mm(round(g["back exit"], 1))]),
        ("Checked by GantryChecks()", [
            "Nothing proud of the front or back face (screw heads, grommet flanges, gland, PE stud, brackets)",
            "meets a member; lifted, each face keeps %s (front) and %s (back) under its next member up."
            % (Mm(round(g["front room"], 1)), Mm(round(g["back room"], 1))),
            "Brackets on the posts, off the panel windows, clear of the gland and the PE stud. ScrewFits()",
            "passes the three mount screws."]),
        ("Gantry feet", [
            "%d, on M5 screws into roll-in T-nuts in the lower members' bottom slots. The length lands the tip"
            % GantryFeet,
            "%s to %s past the slot face, so it needs the foot's stack under the head: %s."
            % (Mm(SlotLip + 3 * ThreadPitch["M5"]), Mm(SlotDepth - 0.5),
               "measure a foot" if g["foot screw"] is None else "M5 x %d" % g["foot screw"])]),
    ]
    if open_:
        notes.append(("OPEN", open_))
    y = 128.0
    for head, lines in notes:
        sh.Text(12.0, y, head, size=1.7, weight="bold")
        y += 2.3
        for s2 in lines:
            for piece in textwrap.wrap(s2, 150):
                sh.Text(12.0, y, piece, size=1.35)
                y += 1.8
        y += 1.0
    TitleBlock(sh, 288, 186, 60, 21.5, [
        "Box in the gantry",
        "Sheet 5. Legal, landscape, 100 %.",
        "Views 1:5, detail C 1:1. Drawn 2026-10-19.",
        "Issue #158, part A. Design, not yet built.",
        "Gantry heights: owner's tape, 2026-10-19.",
    ])
    return sh


# ---------------------------------------------------------------- bill of materials

# Sourcing (ADR-0009): Amazon for the rail, the hardware, the sheet stock and the PE parts;
# McMaster only for the slotted duct, which Amazon does not sell at these sizes for less (2 m of
# 1 x 1 1/2 in duct was $47.84 there on BomDate). Amazon prices, ASINs and pack contents were
# read on amazon.com on BomDate; the two duct prices are the McMaster reading of 2026-10-15,
# because its pages would not load on BomDate. Prices change: check them before ordering.
# Quantities come from the frame, panel and bonding constants above.
BomDate = "2026-10-17"
Amz, Mc = "Amazon", "McMaster"
# Purchase plan per line (issue #145), the CSV's Plan column; BomCsv sums the totals by it. Buy:
# order it; the gantry PE wire is bought with the box (owner, 2026-10-18, issue #149), and the bond
# survey only sets how much of it the gantry takes. LabFirst: the control box's screws, nuts and
# rod; take them from the lab's bins first and buy only what is missing. Optional: the cutting
# tools, since the shop's saw or Misumi cut to order would do instead. NotBought: every unpriced
# line.
Buy, LabFirst, Optional, NotBought = "buy", "lab stock first", "optional", "not bought"
RollM = 15.24                      # one 50 ft roll of wire
GantryFeet = 8                     # the owner's estimate for the gantry (2026-10-18, issue #158)
# The 12 AWG power runs of sheet 2, copper THHN/THWN-2, one 25 ft roll per colour (issue #158): the
# 12 AWG hookup wire of the 2026-09-14 order is copper-clad aluminum. Colours: US practice for the
# mains (white is the neutral); red and blue keep the 24 V pair apart from the black line conductor.
Thhn12 = [("black", "B0G13JNC44", 18.99, "mains L from the inlet through K1 to the PSU"),
          ("white", "B0G13KR5LS", 16.99, "mains N, the same path"),
          ("red", "B0G13QR6XF", 16.99, "+24 V: PSU V+ to K2 and FB1, K2 to FB2"),
          ("blue", "B0G13KQKBG", 18.99, "0 V power: PSU V- to Star S, Star S to the 0V-P bars")]
# Copper and aluminum resistivity at 20 C, ohm m: CCA conducts like a copper wire of area A x ratio.
RhoCu, RhoAl = 1.68e-8, 2.65e-8
# Cutting the 2020 sticks in house (issue #145): a 10 in miter saw whose maker lists aluminum, a blade
# made for thin aluminum, and an engineer's square to set the saw and check each end. From the
# Metabo HPT C10FCG2 owner's manual (p. 6 specifications; p. 7 "Applications: Wood and aluminum
# sash.") and the Amazon listings of the blade (Diablo D10100N) and the square (Kinex 4034-12-010),
# read on ToolDate, as were the M4 packs added with them, the socket head packs that replaced the
# button heads (issue #149) and the gantry PE wire.
ToolDate = "2026-10-18"
SawRpm, SawMaxKerf = 5000.0, 7 / 64 * 25.4    # C10FCG2: no-load speed; the widest kerf it takes
BladeMaxRpm, BladeKerf = 6000.0, 0.091 * 25.4  # D10100N: 10 in, 100 TCG teeth, 5/8 in arbor
SquareErr, SquareL = 0.015, 100.0              # Kinex 4034-12-010, DIN 875/1: 15 um over its 100 mm blade
EndSquare = 0.1                                # wanted: a cut end within 0.1 mm across the 20 mm face


def CutToolChecks():
    """Raise unless the blade is rated above the saw's speed, its kerf fits the saw and stays within
    the cut list's Kerf, and the square's error is under a tenth of the end tolerance. Returns (the
    end tolerance, the square's error) in degrees."""
    if BladeMaxRpm < SawRpm:
        raise ValueError("blade rated %d rpm on a %d rpm saw" % (BladeMaxRpm, SawRpm))
    if BladeKerf > SawMaxKerf or BladeKerf > Kerf:
        raise ValueError("blade kerf %.2f mm: the saw takes %.2f, the cut list allows %.2f"
                         % (BladeKerf, SawMaxKerf, Kerf))
    endDeg = math.degrees(math.atan(EndSquare / Frame))
    sqDeg = math.degrees(math.atan(SquareErr / SquareL))
    if sqDeg > endDeg / 10:
        raise ValueError("the square (%.3f deg) cannot set a %.2f deg end" % (sqDeg, endDeg))
    return endDeg, sqDeg


def Link(src, part):
    if src == Amz and part not in ("", "-"):
        return "https://www.amazon.com/dp/%s" % part
    if src == Mc:
        return "https://www.mcmaster.com/%s/" % part
    return ""


def BomRows():
    """(section, source, plan, item, part or ASIN, description, qty needed, order unit, units to
    order, price per unit or None, used for, notes)."""
    mounts = len(MountBrackets())
    brackets = FrameBrackets + mounts
    gantry = GantryChecks()
    ringScrews = len(RingHoles())  # per plate
    legs = len(BracketSlots())
    panelScrews = sum(n * k for _, n, _, _, _, k in EnclosurePanels())
    bonds, jumpers = BondSummary()
    railBonds = sum(n for _, _, n, land in BondPoints() if land.startswith("tapped"))
    lugs = sum(n for _, _, n, land in BondPoints() if "ring lug" in land)
    nBars = sum(b for _, b in bonds.values())
    sticks, pieces = NestSticks(), CutPieces()
    nPieces = sum(n for _, n, _, _ in pieces)
    nSheets = PanelNest()
    nEntries = PanelChecks()
    dinRails = [s for s in DeckSolids() if s["kind"] == "rail"]
    dinCuts = NestDinRails()
    dinLen = [max(s["box"][2] - s["box"][0], s["box"][3] - s["box"][1]) for s in dinRails]
    dinScrews = sum(max(2, 1 + math.ceil(L / 150.0)) for L in dinLen)   # one per 150 mm, 2 at least
    ductLen = {w: sum(max(b[2] - b[0], b[3] - b[1]) for _, b, wd, _, _ in Ducts() if wd == w)
               for w in (DuctNarrow, DuctWide)}
    trim = sum(2 * (max(s[2] - s[0], s[3] - s[1]) - min(s[2] - s[0], s[3] - s[1]))
               + math.pi * min(s[2] - s[0], s[3] - s[1]) for s in CableSlots)
    wireM = jumpers * JumperM
    boxRolls = math.ceil(wireM / RollM) - 1   # the wire on hand covers what is left
    narrowDuct, wideDuct = ductLen[DuctNarrow], ductLen[DuctWide]
    ductScrews = sum(max(2, 1 + math.ceil(max(b[2] - b[0], b[3] - b[1]) / 150.0)) for _, b, _, _, _ in Ducts())
    clipNames = {"TB6600": "TB6600", "Mega": "Mega carrier", "PSU24": "24 V PSU", "PSU6": "servo PSU",
                 "PSU5": "5 V PSU"}
    clips = {}
    for s in DeckSolids():
        if s["mount"] == "clip":
            clips[s["key"]] = clips.get(s["key"], 0) + 1
    endDeg, sqDeg = CutToolChecks()
    read = "Price read %s" % ToolDate
    peBlocks = len(dinRails) - 1 + PeBarTerms   # one per rail; the 110 V rail's is one of its PE bar's
    feet = len(PostCentres) + GantryFeet
    bendAl, railI = DinRailBend(EAluminum)
    ccaMm2 = 3.31 * RhoCu / RhoAl              # 12 AWG CCA as an equivalent copper area
    wire = [("Power wiring", Amz, Buy, "12 AWG stranded THHN, %s, 25 ft" % colour, part,
             "YDDECW THHN/THWN-2 12 AWG stranded copper, 600 V, 90 C, UL 83, nylon over PVC, 25 ft, %s" % colour,
             "the 12 AWG runs of sheet 2", "25 ft roll", 1, price, use,
             ("Copper only: the 2026-09-14 order's 12 AWG is copper-clad aluminum (Not in this BoM). 12 AWG "
              "copper is rated 30 A at 90 C (NEC Table 310.16). " if i == 0 else "") + read)
            for i, (colour, part, price, use) in enumerate(Thhn12)]
    return [
        # ---- frame
        ("Frame", Amz, Buy, "2020 rail, 6 mm slot, 1000 mm, silver, 10-pack", "B08PQPJYHX",
         "IXGNIJ 10 pcs 1000 mm T-slot 2020 European standard anodized rail, 6063-T5, cut +/-0.5 mm",
         "%d sticks" % len(sticks), "10-pack", 1, 74.99,
         "%d pieces, %d mm: the sheet 4 cut list" % (nPieces, round(sum(n * L for _, n, L, _ in pieces))),
         "%d sticks spare. 6 mm slot per the brand's comparison table; measure depth and lip on the first"
         % (10 - len(sticks))),
        ("Frame", Amz, Buy, "Corner bracket kit, 2020, 40 sets", "B0FK9W8KGW",
         "TOCLUX 40 cast corner brackets 17 x 20 mm, 80 M5 sliding T-nuts, 80 M5 socket cap screws, hex key",
         brackets, "kit of 40", 1, 24.99,
         "bottom 8, lower posts to mid ring 8, mid ring 4, upper posts 8, lid ring 4, gantry mount %d"
         % mounts,
         "Slide the kit's nuts in from the rail ends before each joint closes"),
        ("Frame", Amz, Buy, "Roll-in spring T-nut M5, 2020, 100", "B0DX7B5ZNN",
         "Yaocom 100 pcs 2020 series M5 half roll-in spring T-nuts",
         panelScrews + mounts + GantryFeet, "pack of 100", 1, 9.99,
         "panels %d, gantry mount %d, gantry feet %d (sheet 5)" % (panelScrews, mounts, GantryFeet),
         "Spring-leaf roll-in nut: drops in after assembly, so it also goes into the standing gantry. Ball-spring nuts were $8.89 for 25 (B082F9B1TZ)"),
        ("Frame", Amz, Buy, "Roll-in spring T-nut M4, 2020, 100", "B0FLP1BW2M",
         "Yaocom 100 pcs 2020 series M4 half roll-in spring T-nuts",
         2 * ringScrews + legs, "pack of 100", 1, 9.99,
         "plate screws %d, upper-post bracket legs %d" % (2 * ringScrews, legs), ""),
        ("Frame", Amz, LabFirst, "Socket head M5 x 8, 304, 100", "B0DF75LXL4",
         "Joamang 100 pcs M5-0.8 x 8 304 (A2-70) stainless socket head cap screws, fully threaded, head %s "
         "across, 5 tall" % Mm(HeadM5),
         panelScrews, "pack of 100", 1, 9.88,
         "panels %d, mount brackets to the gantry %d" % (panelScrews - mounts, mounts),
         "Back panel: add a flat washer. Acrylic panels: snug by hand. " + read),
        ("Frame", Amz, LabFirst, "Socket head M5 x 16, 304, 100", "B0GHN9C98P",
         "100 pcs M5-0.8 x 16 304 stainless socket head cap screws",
         len(PostCentres) + railBonds, "pack of 100", 1, 8.60,
         "feet %d, rail bond holes %d" % (len(PostCentres), railBonds), "Also the gantry bond holes"),
        ("Frame", Amz, LabFirst, "M5 socket head assortment, nuts and washers", "B0FGV561HZ",
         "Fgruh 272 pcs: 72 M5 socket cap screws 8 to 35 mm (9 per size), 40 nuts, 80 flat, 80 spring washers",
         "M5 x 35: %d; x 12: %d; x 10: %d; gantry feet: %d" % (len(PostCentres), mounts // 2, mounts // 2, GantryFeet),
         "kit", 1, 9.99,
         "lid ring to the upper posts, back panel washers and PE stud, ground bar screws (x 12) and nuts; the "
         "mount brackets' panel screws (x 12 front, x 10 back); the gantry feet (%s)"
         % ("length open: measure a foot" if gantry["foot screw"] is None else "x %d" % gantry["foot screw"]),
         "Black 12.9 alloy steel. The listing gives 8 to 35 mm, 9 per size: check it has 10 and 12, and buy a "
         "pack of one length if the ground bar screws and the gantry feet land on it together"),
        ("Frame", Amz, LabFirst, "Threaded rod M5 x 50, 304, 5-pack", "B0BLGQLPDF",
         "MECCANIXITY fully threaded rod M5 x 50, 304 stainless", len(PostCentres), "pack of 5", 1, 6.59,
         "locating studs, lower posts to upper posts", "Blue threadlocker into the lower posts"),
        ("Frame", Amz, LabFirst, "M4 socket head assortment, 304", "B0CLM7VMB8",
         "Sutemribor 385 pcs M4 x 5, 6, 8, 10, 12, 16, 20 304 stainless socket head cap screws with nuts, "
         "lock and flat washers",
         "x 10: %d" % legs, "kit", 1, 9.99, "upper-post bracket legs (x 10), and spare sizes",
         "Per-size counts are not listed on the page, so the DIN rail and duct screws have their own pack. "
         "No hex key in the kit. " + read),
        ("Frame", Amz, LabFirst, "Socket head M4 x 12, 304, 100", "B089M2LTHX",
         "iexcell 100 pcs M4-0.7 x 12 304 stainless socket head cap screws, head 7.00 across, 3.91 tall, "
         "3 mm hex key",
         dinScrews + ductScrews, "pack of 100", 1, 8.86,
         "DIN rails %d, duct %d (one per 150 mm of rail or duct, 2 at least), through the plate"
         % (dinScrews, ductScrews),
         "In a DIN rail the head stands %s mm over the plate, %s under the rail's top face: check that a "
         "part's foot clears one before fitting the rest. %s"
         % (Mm(DinRailBaseT + HeadM4H), Mm(DinRailH - DinRailBaseT - HeadM4H), read)),
        ("Frame", Amz, LabFirst, "Nylon insert lock nut M4, DIN 985, 304, 120", "B09PF5WCZL",
         "STORMCUBE 120 pcs M4-0.7 DIN 985 nylon insert lock nuts, 304 (A2-70)", dinScrews + ductScrews,
         "pack of 120", 1, 6.99, "under the plate, on each M4 x 12",
         "M4 x 12 leaves %s mm or more past the nut (NutFits). A nut from lab stock must keep NutFits "
         "passing: DIN 985 is %s mm tall, so if the lab's nuts are taller, set NylocH to their height and "
         "rerun NutFits. %s" % (Mm(round(min(p for _, _, p in NutFits()), 1)), Mm(NylocH["M4"]), read)),
        ("Frame", Amz, LabFirst, "Socket head M4 x 6, 304, 100", "B07CK187DR",
         "FULLERKREG 100 pcs M4-0.7 x 6 18-8 (304) stainless socket head cap screws, DIN 912, fully threaded",
         2 * ringScrews, "pack of 100", 1, 8.99, "both plates to their rings, %d each" % ringScrews,
         "Under the base plate the heads stand %s mm clear of the floor on the feet. %s"
         % (Mm(FootH - HeadM4H), read)),
        ("Frame", Amz, Buy, "Rubber feet 1 x 0.51 in, steel washer, 10-pack", "B08B87SRRG",
         "Round rubber bumper feet with built-in stainless washer, 0.51 in high, 1 in diameter",
         feet, "pack of 10", math.ceil(feet / 10), 9.99,
         "under the lower posts %d; under the gantry %d (the owner's estimate, issue #158), so both stand "
         "at the same height" % (len(PostCentres), GantryFeet),
         "They add 0.51 in below the 11 in envelope. Gantry feet: M5 into roll-in T-nuts in the lower "
         "members' bottom slots; the screw length waits on the foot (GantryFootStack, sheet 5)"),
        ("Frame", "on hand", NotBought, "Blue threadlocker", "-", "", 1, "-", 0, None,
         "studs into the lower posts", ""),
        # ---- plates and panels
        ("Plates and panels", Amz, Buy, "Aluminum 5052, 1/16 x 18 x 24 in", "B084KZ756P",
         "2TWENTYTWO STEEL DESIGNS 1/16 in 5052 aluminum plate, 18 x 24 in, laser-cut blank", 2, "each", 2,
         23.81, "base plate and lower back panel %s x %s; upper plate" % (Mm(BoxW), Mm(LowerPanelH)),
         "Shear in the shop; drill and nibble through an acrylic template cut on the laser"),
        ("Plates and panels", Amz, Buy, "Edge trim, 1/16 in U-channel, 10 ft", "B0CQLC4P4S",
         "Rubber U-channel edge trim, fits 0 to 5/64 in edges, 10 ft, black", "%d mm" % round(trim), "10 ft", 1,
         7.99, "the %d cable slots in the upper plate" % len(CableSlots), ""),
        ("Plates and panels", Mc, Buy, "Cast acrylic 1/8 x 24 x 24 in, clear", "8560K259",
         "Clear scratch- and UV-resistant cast acrylic sheet, 24 x 24 x 1/8 in", "%d sheets" % nSheets,
         "each", nSheets + 1, 39.04,
         "%d panels and %d grommet rings on %d sheets (sheet 4, NestPlan)"
         % (sum(n for _, n, _, _, m, _ in EnclosurePanels() if m == "acrylic"), nEntries, nSheets),
         "Trim each sheet to 24 x 18 in first: the nest is laid out on that size, and the %s mm bed "
         "takes no more than 18 in. The extra sheet: the drilling templates, the upper plate's (both "
         "plates) and the lower back panel's beside it. The 6 in offcuts are spare. McMaster price of "
         "2026-10-18; shipping extra. Ordered in place of the Amazon 4-pack of 18 x 24 in sheets "
         "(B0CZLDGK69, $49.99)" % Mm(LaserBed[1])),
        ("Plates and panels", Amz, Buy, "Acrylic bonding cement, 4 oz", "B0DS69HMN6",
         "Berkland acrylic bonding cement, 4 oz", 1, "each", 1, 19.99,
         "acrylic bonding (the owner's line)",
         "In the Amazon order since 2026-10-15, kept by the owner on 2026-10-18; price read from the cart "
         "that day"),
        ("Plates and panels", Amz, Buy, "Desk grommet 2 in (50 mm), 4-pack", "B0DYZP4256",
         "ZLTASYRY 4 desk grommets: 2 in (50 mm) hole, 2.36 in overall, ABS, removable cable cover, "
         "slit rubber base; a hole saw and 6 cable ties included", nEntries, "4-pack",
         math.ceil(nEntries / GrommetsInPack), 7.59,
         "cable entries: " + "; ".join(c for _, _, c, _ in CableEntries),
         "Owner's choice, in place of cable glands: passes a USB-B plug. Holes %s mm in the panel "
         "DXFs, each grommet held by a %s mm acrylic ring on its sleeve; caliper one first"
         % (Mm(GrommetHole), Mm(RingOD))),
        # ---- duct
        ("Cable duct", Mc, Buy, "Slotted wire duct 1/2 W x 1 H, gray", "7578K114",
         "Slotted wire duct with snap-on cover, 1 in high x 1/2 in wide, gray", "%d mm" % round(narrowDuct),
         "6 1/2 ft length", math.ceil(narrowDuct / (6.5 * 304.8)), 25.51,
         "upper signal, field, SSR and 24 V feed runs; both lower runs",
         "McMaster price of 2026-10-15; shipping extra"),
        ("Cable duct", Mc, Buy, "Slotted wire duct 1 W x 1 1/2 H", "7578K14",
         "Slotted wire duct with snap-on cover, 1 1/2 in high x 1 in wide", "%d mm" % round(wideDuct),
         "3 1/4 ft length", math.ceil(wideDuct / (3.25 * 304.8)), 23.74,
         "motor duct behind the drivers, past the clamp, and the back run to the upper left grommet",
         "McMaster price of 2026-10-15; gray or white"),
        # ---- PE bonding of the box
        ("PE bonding", Amz, Buy, "Ground bar kit, %d terminals" % BarTerminals, "B007ZZGSQI",
         "SIEMENS EC2GB152 ground bar kit: %d terminal positions and a ground lug" % BarTerminals,
         "lower %d, upper %d" % (bonds["lower"][1], bonds["upper"][1]), "each", nBars, 10.38,
         "on the plates' PE studs; home runs: lower %d, upper %d" % (bonds["lower"][0], bonds["upper"][0]),
         "None was on hand (issue #158); a spare uxcell 1-in 9-out block is no substitute: 9 ways, insulated "
         "from the plate, and the same body as the 0 V blocks. Never two parts per terminal. Its foot is not "
         "measured: sheet 4 gives the screw window from it. " + read),
        ("PE bonding", Amz, Buy, "12 AWG stranded green THHN, 50 ft", "B0DPK8KDLJ",
         "THHN wire 12 gauge 50 ft, stranded copper, green", "%.1f m" % wireM, "50 ft roll",
         boxRolls, 29.99,
         "%d jumpers at about %.1f m, both module links" % (jumpers, JumperM),
         "Start with the 12 AWG PE wire on hand; with one roll, it must cover the last %.1f m. 12 AWG is "
         "3.31 mm2, above the 2.5 mm2 floor of IEC 60364-5-54 543.1.3 for a separate PE conductor"
         % (wireM - boxRolls * RollM)),
        ("PE bonding", Amz, Buy, "Ring terminal 12-10 AWG, #10, heat shrink, 100", "B0DM8FW4LV",
         "12-10 AWG #10 stud heat-shrink ring terminals", lugs, "pack of 100", 1, 9.99,
         "the part end of each jumper; the bar end goes bare into its clamp", "Also the gantry jumpers"),
        ("PE bonding", Amz, Buy, "External tooth lock washers, 304, M2.5 to M12", "B0CP7YZ9JY",
         "500 pcs external tooth (star) lock washer assortment", lugs + 2 * nBars, "kit", 1, 9.99,
         "under each ring lug, under the bars on both plates",
         "Per-size counts are not listed; DIN 6797 A, taken as 0.6 thick for M5 (measure one: sheet 4's ground "
         "bar screw length counts it)"),
        ("PE bonding", Amz, Buy, "Ground terminal block USLKG 5, green-yellow, 20", "B07M9LDK8F",
         "Erayco USLKG5N DIN rail ground terminal blocks: 6.2 mm wide, 24 to 10 AWG (0.2 to 4 mm2), 600 V "
         "30 A, 20 pcs", peBlocks, "pack of 20", 1, 21.99,
         "one per DIN rail (%d), and %d more in the %d-way PE bar on the 110 V rail; each jumper lands bare"
         % (len(dinRails), PeBarTerms - 1, PeBarTerms),
         "In place of the terminal kits' 8 ground blocks, kept as spares: a 2.5 mm2 block takes 12 AWG (3.31 "
         "mm2) at its limit at best, this one mid-range. The rails are aluminum: meter each block to its rail. "
         + read),
        *wire,
        ("Power wiring", Amz, Buy, "DIN fuse holder 5 x 20 mm, 15-pack", "B0F1DQLG89",
         "Dinkle DK4-TF(5x20) DIN rail fuse holder, UL 300 V 16 A, 12 to 24 AWG, 15 pcs", 1, "pack of 15", 1,
         39.99, "F0, the 110 V control rung on the 110 V rail",
         "UL listed; the rest are spares. Not measured: F0 stays dashed on sheet 3. " + read),
        ("Power wiring", Amz, Buy, "Fuse 5 x 20 mm, 1 A time delay, ceramic, 5-pack", "B008R8XVHQ",
         "T1AH250V ceramic cartridge fuses, 5 x 20 mm, 5 pcs", 1, "pack of 5", 1, 10.99, "F0 (1 A T)",
         "High breaking capacity (H) on the mains side. The blade fuses on hand are 32 V automotive parts. "
         + read),
        ("Power wiring", Amz, Buy, "Cord 18/4 SJOOW, 300 V, 25 ft", "B0BKPRWN4N",
         "GEARit 18 AWG 4-conductor SJOOW portable cord, 300 V, stranded copper, 25 ft", 1, "25 ft", 1, 24.30,
         "the 110 V door cable: X1 1 to 3 and the plate PE, out through the M20 gland",
         "Caliper the jacket: the gland takes 6 to 12 mm. " + read),
        ("Wire marking", Amz, Buy, "Flexible ID tape 12 mm, TZe-FX231 type, 4-pack", "B0FJ25359S",
         "Greateam TZe-FX231 compatible flexible ID laminated tape, black on white, 12 mm x 8 m, 4 cassettes",
         "both ends of every wire and cable", "4-pack", 1, 16.29,
         "the owner's Brother PT-D220: wrap a cable, fold a flag on thin wire; names by function (X-PUL, F2-4)",
         "The listing names the PT-D220. At about 40 mm a flag, one 8 m cassette makes some 200. " + read),
        # ---- PE bonding of the gantry
        ("Gantry PE", Amz, Buy, "Ground bar kit, %d terminals" % BarTerminals, "B007ZZGSQI",
         "SIEMENS EC2GB152 ground bar kit: %d terminal positions and a ground lug" % BarTerminals, 1, "each", 1,
         10.38, "the gantry PE point, fed by the trunk from the upper bar",
         "Jumper count from a survey: measure every metal part to this bar; bond each that reads open. Over "
         "%d jumpers, add a bar. %s" % (BarTerminals - 1, read)),
        ("Gantry PE", Amz, Buy, "12 AWG stranded green THHN, 50 ft", "B0DPK8KDLJ",
         "THHN wire 12 gauge 50 ft, stranded copper, green", "the survey sets it", "50 ft roll", 1, 29.99,
         "trunk and stationary gantry parts",
         "Rail bond holes as in the box: M5 x 16, lug, tooth washer. With the box's roll this makes %.1f m; "
         "the box takes %.1f, which leaves %.1f for the gantry, more with the wire on hand. %s"
         % ((boxRolls + 1) * RollM, wireM, (boxRolls + 1) * RollM - wireM, read)),
        ("Gantry PE", Amz, Buy, "12 AWG silicone wire, green, 25 ft", "B06XDLS4TC",
         "BNTECHGO 12 gauge silicone wire, green, 25 ft, fine-stranded tinned copper", "the survey sets it",
         "25 ft roll", 1, 18.98, "carriages: one flexible jumper along each moving cable run",
         "V-wheels and belts isolate a carriage from its rail. " + read),
        ("Plates and panels", Amz, Buy, "Cable gland M20 x 1.5, 6-12 mm, 10-pack", "B0DJXC78WR",
         "SDTC Tech 10 nylon cord grips M20 x 1.5, IP68, locknut and gasket, 6 to 12 mm cable", 1, "10-pack", 1,
         7.99, "the 110 V door cable out of the back panel (X1 to S1, H1 and the plate PE)",
         "%s%s hole in the back panel template, inside the 110 VAC window. %s" % (Dia, Mm(DoorGland[1]), read)),
        ("Plates and panels", "printed", NotBought, "Printed DIN clips and carriers", "-",
         ", ".join("%s %d" % (clipNames[k], n) for k, n in clips.items()), sum(clips.values()), "-", 0, None,
         "the parts without DIN feet (PartSize mount clip), each %s mm over its rail" % Mm(Clip),
         "Printed in house like CAD/PSU DIN mount, which is for the PSU standing: the flat 24 V PSU's "
         "mount is not designed yet (ADR-0010)"),
        # ---- cutting the 2020 sticks
        ("Cutting tools", Amz, Optional, "Miter saw, 10 in, single bevel", "B0FBPB1MJ8",
         "Metabo HPT C10FCG2 10 in compound miter saw, 15 A, 5000 rpm, wood blade and vise included", 1, "each",
         1, 169.00, "the %d frame pieces of the sheet 4 cut list" % nPieces,
         "Its owner's manual lists wood and aluminum sash (p. 7) and takes a 10 in, 5/8 in arbor blade up to "
         "7/64 in kerf (p. 6). Bolt it to a level bench (p. 7: four 5/16 in bolts, not included) and clamp "
         "each piece in its vise. " + read),
        ("Cutting tools", Amz, Optional, "Saw blade, 10 in, 100 TCG, thin aluminum", "B0798GY3VQ",
         "Diablo D10100N: 10 in, 100 TCG teeth, 5/8 in arbor, .091 in kerf, .071 in plate, 6000 max rpm",
         1, "each", 1, 59.94, "in place of the saw's wood blade for every aluminum cut",
         "Rated %d rpm on the %d rpm saw; its %s mm kerf is within the saw's %s and the cut list's %s. %s"
         % (BladeMaxRpm, SawRpm, Mm(round(BladeKerf, 1)), Mm(round(SawMaxKerf, 1)), Mm(Kerf), read)),
        ("Cutting tools", Amz, Optional, "Engineer's try square, 4 in, DIN 875/1", "B079R9ZHRZ",
         "Kinex 4034-12-010, 100 x 70 mm with a base, square within 15 um, inspection certificate", 1, "each", 1,
         28.67, "set the blade square to the table and to the fence; check each cut end",
         "An end within %s mm across the 20 mm face is %.2f deg; the square is good to %.3f deg. %s"
         % (Mm(EndSquare), endDeg, sqDeg, read)),
        ("Cutting tools", "spare parts", NotBought, "Length stop", "-",
         "a spare stick clamped to the bench in line with the saw fence, shimmed to the table's height, with a "
         "spare corner bracket on a T-nut in its top slot as the stop", 1, "-", 0, None,
         "cut each set of equal pieces against one stop, up to %s mm" % Mm(max(L for _, _, L, _ in pieces)),
         "%d sticks and %d brackets are spare" % (10 - len(sticks), 40 - brackets)),
        ("Cutting tools", Amz, Optional, "Bar clamp, 12 in, 2-pack", "B001NP9S7M",
         "IRWIN QUICK-GRIP one-handed mini bar clamps, 12 in, 2-pack (1964745)", 2, "2-pack", 1, 19.87,
         "the stop stick to the bench", read),
        ("Cutting tools", Amz, Optional, "Deburring tool", "B01L2XR4P2",
         "AFA Tooling deburring tool, anodized aluminum handle, 11 M2 HSS blades", 1, "each", 1, 9.99,
         "every cut end, so it seats flat on its bracket and plate", read),
        ("Cutting tools", Amz, Optional, "Face shield, ANSI Z87.1", "B08P7MPWZ7",
         "NoCry face shield, clear anti-fog visor, adjustable headgear, ANSI Z87.1", 1, "each", 1, 32.37,
         "over safety glasses: the saw throws aluminum chips", "Safety glasses and hearing protection: on hand. "
         + read),
        # ---- tools and parts not in this BoM
        ("Tools", "on hand", NotBought, "M5 x 0.8 hand tap", "-", "", 1, "-", 0, None,
         "post ends and every bond hole", ""),
        ("Tools", "shop", NotBought, "Sheet shear, hand nibbler, files", "-", "", "", "-", 0, None,
         "shear the plates and the back panel from the 18 x 24 in sheets; nibble and file the plate slots and "
         "the inlet cut-out", "Check the shop has them before ordering the sheet"),
        ("Tools", "shop", NotBought, "4.2 mm and 7/32 in (5.56 mm) drills", "-", "", "", "-", 0, None,
         "bond holes (4.2, then tap M5); mid and lid rail holes and upper post sockets (5.56)", ""),
        ("Not in this BoM", "ordered 2026-09-14", NotBought, "Electrical parts", "-",
         "K1 and K2, two 12-way fuse modules (FB1, FB2), two terminal kits with 8 USLKG 2.5 ground blocks, five "
         "uxcell 1-in 9-out blocks (Star S and 0V-P use 3), SSRs, buttons, E-stop, tower with buzzer, 20 AWG "
         "wire, ferrules and crimper", "", "-", 0, None, "", ""),
        ("Not in this BoM", "on hand", NotBought, "Aluminum DIN rails, 18 in, slotted", "B0BFFSMBC7",
         "International Connector T&G 35 x 7.5 mm slotted aluminum, %d on hand (ordered 2026-09-14)"
         % DinRailsOnHand, len(dinCuts), "each", 0, None,
         "%d rail pieces, %d mm: %s" % (len(dinRails), round(sum(dinLen)),
                                       "; ".join(" + ".join(Mm(L) for L in r) for r in dinCuts)),
         "Cut with a hacksaw, first fit with a 3 mm kerf (NestDinRails). No steel rail needed: screwed down "
         "every %s mm, a pull of %d N between two screws bends the rail %.2f mm (I = %d mm4; steel %.2f)"
         % (Mm(RailSpan), round(RailPull), bendAl, round(railI), DinRailBend(ESteel)[0])),
        ("Not in this BoM", "on hand", NotBought, "Brother PT-D220 label maker", "-",
         "TZe tape up to 12 mm", "", "-", 0, None, "wire, terminal strip and device labels",
         "Standard TZe tape on the terminal kits' marker strips and on the devices"),
        ("Not in this BoM", "on hand", NotBought, "12 AWG copper-clad aluminum hookup wire", "-",
         "VIABRICO 600 ft, 6 colours, copper clad aluminium, low voltage (ordered 2026-09-14)", "", "-", 0, None,
         "nothing in the box",
         "Aluminum's resistivity is %.2f times copper's, so 12 AWG CCA conducts like %.1f mm2 of copper, about "
         "14 AWG; the 12 AWG power runs use the copper THHN above" % (RhoAl / RhoCu, ccaMm2)),
        ("Not in this BoM", "not chosen", NotBought, "Pluggable inter-deck terminals, USB isolator", "-",
         "", "", "-", 0, None, "", ""),
    ]


def BomCsv():
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["Section", "Source", "Plan", "Item", "Part or ASIN", "Description", "Qty needed",
                "Order unit", "Units to order", "Price per unit (USD, %s)" % BomDate, "Line total", "Used for",
                "Notes", "Link"])
    bySrc, byPlan, gantry = {}, {}, 0.0
    for sec, src, plan, item, part, desc, need, unit, units, price, use, note in BomRows():
        # The plan must agree with the price and the section, or the totals below mean nothing.
        want = ((NotBought,) if price is None else
                {"Cutting tools": (Optional,), "Gantry PE": (Buy,)}.get(sec, (Buy, LabFirst)))
        if plan not in want:
            raise ValueError("%s, %s: plan %r, expected %s" % (sec, item, plan, " or ".join(want)))
        line = units * price if (price is not None and units) else None
        if line:
            bySrc[src] = bySrc.get(src, 0.0) + line
            if sec == "Gantry PE":
                gantry += line
            else:
                byPlan[plan] = byPlan.get(plan, 0.0) + line
        w.writerow([sec, src, plan, item, part, desc, need, unit, units,
                    "" if price is None else "%.2f" % price, "" if line is None else "%.2f" % line,
                    use, note, Link(src, part)])

    def Total(label, usd, note=""):
        w.writerow(["", "", "", label, "", "", "", "", "", "", "%.2f" % usd, "", note, ""])

    box, lab = byPlan.get(Buy, 0.0) + byPlan.get(LabFirst, 0.0), byPlan.get(LabFirst, 0.0)
    for key in (Amz, Mc):
        Total("Total, %s" % key, bySrc.get(key, 0.0))
    Total("Total, control box", box)
    Total("Total, lab stock first (control box fasteners)", lab,
          "Take these from the lab's bins first; buy only what is missing")
    Total("Total, gantry PE", gantry, "Bought with the box; the survey sets how much of it the gantry takes")
    Total("New spend: control box and gantry PE, fasteners from lab stock, no cutting tools", box - lab + gantry,
          "New spend is what has to be bought new: the control box total less the lab-stock fasteners, "
          "plus the gantry PE. The optional cutting tools are not in it")
    Total("Total, cutting tools", byPlan.get(Optional, 0.0),
          "Optional: the alternatives are the shop's saw (no cost) or Misumi cut to order, which ADR-0009 "
          "priced at $146 against $75 for the sticks (+$71)")
    Total("Total, all priced lines", sum(bySrc.values()),
          "Amazon prices read on %s (the cutting tools, the M5 x 8 and M4 screw packs, the nut pack, the "
          "cable gland, the gantry PE wire, the acrylic cement and the issue #158 lines on %s), McMaster on "
          "2026-10-15 (the acrylic on 2026-10-18); shipping and tax extra"
          % (BomDate, ToolDate))
    return out.getvalue()


def Main():
    outDir = sys.argv[1] if len(sys.argv) > 1 else os.path.join("docs", "wiring")
    os.makedirs(outDir, exist_ok=True)
    sheets = [("wiring_schematic_legal.svg", BuildSchematic()),
              ("wiring_din_rails_lower_legal.svg", BuildDeckWiring("lower")),
              ("wiring_din_rails_upper_legal.svg", BuildDeckWiring("upper")),
              ("wiring_din_rails_names_legal.svg", BuildNomenclature()),
              ("wiring_din_rails_panel_legal.svg", BuildOperatorPanel()),
              ("packing_study_legal.svg", BuildPacking()),
              ("frame_plates_legal.svg", BuildFrame()),
              ("gantry_mount_legal.svg", BuildGantry())]
    for name, sh in sheets:
        path = os.path.join(outDir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sh.Svg())
        print("wrote", path)
    for kind in ("base", "upper"):
        path = os.path.join(outDir, "deck_%s_plate.dxf" % kind)
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(DxfPlate(kind))
        print("wrote", path)
    PanelChecks()
    for name, text in PanelDxfFiles().items():
        path = os.path.join(outDir, name)
        with open(path, "w", encoding="ascii", newline="\n") as f:
            f.write(text)
        with open(path, encoding="ascii") as f:
            web, where = CheckWebs(f.read())
        print("wrote %s: read back, least web %.2f mm, %s" % (path, web, where))
    for item in PanelOpen():
        print("OPEN, not cut yet:", item)
    for item in GantryOpen():
        print("OPEN, gantry mount:", item)
    path = os.path.join(outDir, "bom_frame.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(BomCsv())
    print("wrote", path)


if __name__ == "__main__":
    Main()
