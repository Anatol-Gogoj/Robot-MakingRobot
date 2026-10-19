"""Draw the RMR control panel wiring diagrams as legal-size (14 x 8.5 in) SVG sheets.

Sheet 1: wiring schematic (every circuit on one page).
Sheet 2: the same circuits arranged on DIN rails, wired through ducts.
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
              "The layered E-stop panel as designed in the 2026-10-06 panel reference. "
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
    fb1Drops = [(118, "F1-1", "3 A"), (142, "F1-2", "3 A"), (166, "F1-3", "3 A"),
                (190, "F1-4", "3 A"), (210, "F1-5", "3 A"), (230, "F1-6", "")]
    sh.Text(104, 23.3, "FB1", size=2.4, weight="bold", fill=TolBlue)
    sh.Text(104, 25.6, "12-way", size=1.6)
    for x, name, amp in fb1Drops:
        sh.Dot(x, fb1Y, "va")
        if name == "F1-6":
            sh.Wire([(x, fb1Y), (x, 21.5)], "va")
            sh.Text(x, 24.2, "F1-6 spare", size=1.7, anchor="middle")
            continue
        FuseV(sh, x, fb1Y, 26.0, "va")
        sh.Text(x + 1.6, 22.3, name, size=1.7)
        sh.Text(x + 1.6, 24.4, amp, size=1.7)
    # bucks
    bucks = [(118, "Mega buck", "5 V out", "5 V to Mega (note 4)"),
             (142, "Pi 5 buck", "5.1 V 5 A", "5.1 V to Pi 5"),
             (166, "Screen", "supply", "to touchscreen")]
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
    for x in (113, 137, 161):
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
    sh.Wire([(x, megaY1), (x, 168.0)], "lv")
    Tag(sh, x, 169.6, "Mega buck 5 V", "lv", side="right", size=1.5)
    sh.Text(x, 174.4, "(note 4)", size=1.4)
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
    Tag(sh, 154.0, 162.6, "5.1 V Pi buck", "lv", side="right", size=1.4)
    # HDMI to screen
    sh.Wire([(174, pY0), (174, 163.4), (236, 163.4)], "sg")
    sh.Text(176, 162.6, "HDMI + USB touch", size=1.4)
    sh.Rect(236, 160.6, 14, 10.0, "bx")
    sh.Text(243, 164.4, "10 in", size=1.5, anchor="middle", weight="bold")
    sh.Text(243, 166.6, "touch", size=1.5, anchor="middle", weight="bold")
    sh.Text(243, 168.8, "screen", size=1.5, anchor="middle", weight="bold")
    sh.Wire([(243, 170.6), (243, 172.6)], "lv")
    Tag(sh, 243, 174.0, "screen supply", "lv", side="left", size=1.3)
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
        ("4", ["Mega buck: the Mega datasheet (A000067, 2.1) rates VIN at 7 to 12 V and gives no",
               "rating for feeding the 5 V pin. Pick the input, then set the buck output to suit."]),
        ("5", ["Firmware gap (stage 0): kill() and motor-power loss leave pins 4 and 42 as they",
               "were. With the UV behind K2, Reset relights the lamp until that is fixed."]),
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
        "Sheet 1 of 2. Legal 14 x 8.5 in, landscape. Print at 100 %.",
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-14.",
        "Status: design, not yet wired or tested on the machine.",
        "Sheet 2 shows the same circuits on DIN rails.",
    ])
    return sh


# ---------------------------------------------------------------- sheet 2: DIN rails

class Panel:
    """Devices on horizontal DIN rails. A wire leaves its terminal vertically into the duct
    beside the rail, runs horizontally on a track of that duct, and changes duct only in a
    side duct (lane) or through a gap between two devices on a rail."""

    Pitch = 0.56
    LanePitch = 0.5

    def __init__(self, sh):
        self.Sh = sh
        self.Ducts = {}     # name -> (y0, y1)
        self.Rows = {}      # name -> (bodyTop, bodyBot, ductAbove, ductBelow)
        self.Terms = {}     # key -> (x, y, duct, side)
        self.Reqs = []
        self.SideX = {}     # 'L' / 'R' -> (x0, x1)
        self.Tracks = {}
        self.Lanes = {"L": [], "R": []}

    def AddDuct(self, name, y0, y1):
        self.Ducts[name] = (y0, y1)
        n = int((y1 - y0 - 1.2) / self.Pitch) + 1
        self.Tracks[name] = [[] for _ in range(n)]

    def TrackY(self, duct, i):
        return self.Ducts[duct][0] + 0.6 + i * self.Pitch

    def LaneX(self, side, i):
        x0, x1 = self.SideX[side]
        return (x1 - 0.6 - i * self.LanePitch) if side == "L" else (x0 + 0.6 + i * self.LanePitch)

    def Device(self, row, key, x0, x1, title, sub=(), top=(), bot=(), titleSize=2.0):
        sh = self.Sh
        yT, yB, dA, dB = self.Rows[row]
        sh.Rect(x0, yT, x1 - x0, yB - yT, "bx")
        ty = (yT + yB) / 2 - len(sub) * 1.0 + 0.6
        sh.Text((x0 + x1) / 2, ty, title, size=titleSize, anchor="middle", weight="bold")
        for i, s2 in enumerate(sub):
            sh.Text((x0 + x1) / 2, ty + 2.2 + i * 1.8, s2, size=1.35, anchor="middle")
        for tkey, x, lab in top:
            sh.Rect(x - 0.45, yT, 0.9, 0.9, "symf")
            if lab:
                sh.Text(x, yT + 2.4, lab, size=1.1, anchor="middle")
            self.Terms["%s.%s" % (key, tkey)] = (x, yT, dA, "up")
        for tkey, x, lab in bot:
            sh.Rect(x - 0.45, yB - 0.9, 0.9, 0.9, "symf")
            if lab:
                sh.Text(x, yB - 1.4, lab, size=1.1, anchor="middle")
            self.Terms["%s.%s" % (key, tkey)] = (x, yB, dB, "down")

    def TermBlock(self, row, key, x0, labels, title, pitch=3.4, bridges=(), note=None):
        """Feed-through terminal block. Terminal n has a top clamp KEY.nt and a bottom
        clamp KEY.nb; bridges join terminals (i, j) with a comb across the slices."""
        sh = self.Sh
        yT, yB, dA, dB = self.Rows[row]
        n = len(labels)
        x1 = x0 + pitch * n
        sh.Rect(x0, yT, x1 - x0, yB - yT, "bx")
        for i, lab in enumerate(labels):
            xc = x0 + pitch * (i + 0.5)
            if i:
                sh.Wire([(x0 + pitch * i, yT), (x0 + pitch * i, yB)], "sym")
            if len(lab) > 2:
                sh.Text(xc + 0.45, (yT + yB) / 2 + 1.2, lab, size=1.2, anchor="middle", weight="bold",
                        rot=-90)
            else:
                sh.Text(xc, (yT + yB) / 2 + 1.6, lab, size=1.25, anchor="middle", weight="bold")
            self.Terms["%s.%dt" % (key, i + 1)] = (xc, yT, dA, "up")
            self.Terms["%s.%db" % (key, i + 1)] = (xc, yB, dB, "down")
            sh.Text(xc, yT + 1.9, str(i + 1), size=0.95, anchor="middle", fill="#555")
        for i, j in bridges:
            xa = x0 + pitch * (i + 0.5)
            xb = x0 + pitch * (j + 0.5)
            sh.Wire([(xa, yT + 3.2), (xb, yT + 3.2)], "sym")
            for k in range(i, j + 1):
                sh.Dot(x0 + pitch * (k + 0.5), yT + 3.2, r=0.35)
        sh.Text((x0 + x1) / 2, yT - 0.7, title, size=1.45, anchor="middle", weight="bold", halo=True)
        if note:
            sh.Text((x0 + x1) / 2, yB + 2.0, note, size=1.15, anchor="middle", halo=True)
        return x1

    def W(self, cls, a, b, via=None, dash=False):
        self.Reqs.append(dict(kind="wire", cls=cls, a=a, b=b, via=via, dash=dash))

    def Exit(self, cls, keys, side, lines, up=False):
        self.Reqs.append(dict(kind="exit", cls=cls, keys=keys, side=side, lines=lines, up=up))

    @staticmethod
    def _Free(ivs, lo, hi, gap=0.7):
        return all(hi + gap < a or lo - gap > b for a, b in ivs)

    def _TakeTrack(self, duct, lo, hi, pref):
        tr = self.Tracks[duct]
        n = len(tr)
        if pref == "top":
            order = list(range(n))
        elif pref == "bottom":
            order = list(range(n - 1, -1, -1))
        else:
            order = sorted(range(n), key=lambda i: abs(i - n // 2))
        for i in order:
            if self._Free(tr[i], lo, hi):
                tr[i].append((lo, hi))
                return i
        raise RuntimeError("duct %s is full for the span %.1f to %.1f" % (duct, lo, hi))

    def _TakeLane(self, side, lo, hi):
        lanes = self.Lanes[side]
        for i, ivs in enumerate(lanes):
            if self._Free(ivs, lo, hi, gap=0.5):
                ivs.append((lo, hi))
                return i
        lanes.append([(lo, hi)])
        return len(lanes) - 1

    @staticmethod
    def _Pref(side):
        # a terminal on the rail above the duct ('down' clamp) prefers the duct's top tracks
        return "top" if side == "down" else "bottom"

    def Route(self):
        sh = self.Sh
        for r in self.Reqs:
            if r["kind"] != "wire":
                continue
            r["A"] = self.Terms[r["a"]]
            r["B"] = self.Terms[r["b"]]
            if r["via"] in ("L", "R"):
                da, db = r["A"][2], r["B"][2]
                lo = min(self.Ducts[da][0], self.Ducts[db][0])
                hi = max(self.Ducts[da][1], self.Ducts[db][1])
                r["lane"] = self._TakeLane(r["via"], lo, hi)
        segs = []
        for r in self.Reqs:
            if r["kind"] == "wire":
                xa, ya, da, sa = r["A"]
                xb, yb, db, sb = r["B"]
                if r["via"] is None:
                    if da != db:
                        raise ValueError("%s to %s needs a via" % (r["a"], r["b"]))
                    pref = self._Pref(sa) if sa == sb else "mid"
                    segs.append((abs(xb - xa), r, "t", da, min(xa, xb), max(xa, xb), pref))
                else:
                    vx = self.LaneX(r["via"], r["lane"]) if r["via"] in ("L", "R") else r["via"]
                    r["vx"] = vx
                    segs.append((abs(vx - xa), r, "ta", da, min(xa, vx), max(xa, vx), self._Pref(sa)))
                    segs.append((abs(vx - xb), r, "tb", db, min(xb, vx), max(xb, vx), self._Pref(sb)))
            elif r["side"] in ("L", "R"):
                xs = [self.Terms[k][0] for k in r["keys"]]
                x, y, duct, side = self.Terms[r["keys"][0]]
                edge = 4.6 if r["side"] == "L" else PageW - 4.6
                r["edge"], r["duct"] = edge, duct
                lo, hi = min(xs + [edge]), max(xs + [edge])
                segs.append((-1000 + hi - lo, r, "te", duct, lo, hi, self._Pref(side)))
        # cables leaving the panel go first and keep a free track on each side
        segs.sort(key=lambda t: t[0])
        for _, r, slot, duct, lo, hi, pref in segs:
            i = self._TakeTrack(duct, lo, hi, pref)
            if slot == "te":
                for j in (i - 1, i + 1):
                    if 0 <= j < len(self.Tracks[duct]):
                        self.Tracks[duct][j].append((lo, hi))
            r[slot] = self.TrackY(duct, i)
        for r in self.Reqs:
            if r["kind"] == "wire":
                xa, ya, da, sa = r["A"]
                xb, yb, db, sb = r["B"]
                if r["via"] is None:
                    pts = [(xa, ya), (xa, r["t"]), (xb, r["t"]), (xb, yb)]
                else:
                    pts = [(xa, ya), (xa, r["ta"]), (r["vx"], r["ta"]), (r["vx"], r["tb"]),
                           (xb, r["tb"]), (xb, yb)]
                clean = [pts[0]]
                for q in pts[1:]:
                    if abs(q[0] - clean[-1][0]) > 1e-6 or abs(q[1] - clean[-1][1]) > 1e-6:
                        clean.append(q)
                sh.Wire(clean, r["cls"], ' stroke-dasharray="1.1 .8"' if r["dash"] else "")
            elif r["side"] in ("L", "R"):
                t = r["te"]
                xs = [self.Terms[k][0] for k in r["keys"]]
                for k in r["keys"]:
                    x, y = self.Terms[k][:2]
                    sh.Wire([(x, y), (x, t)], "sg")
                far = max(xs) if r["side"] == "L" else min(xs)
                sh.Wire([(far, t), (r["edge"], t)], r["cls"])
                for x in xs:
                    sh.Dot(x, t, r=0.35)
                # label runs along the outer edge of the side duct, rotated
                x0, x1 = self.SideX[r["side"]]
                n = len(r["lines"])
                for i, s2 in enumerate(r["lines"]):
                    lx = (x0 + 1.5 + i * 1.6) if r["side"] == "L" else (x1 - 0.6 - (n - 1 - i) * 1.6)
                    if r.get("up"):
                        sh.Text(lx, t - 1.2, s2, size=1.3, anchor="start", rot=-90, halo=True)
                    else:
                        sh.Text(lx, t + 1.2, s2, size=1.3, anchor="end", rot=-90, halo=True)
            else:
                xs = [self.Terms[k][0] for k in r["keys"]]
                y0 = self.Terms[r["keys"][0]][1]
                d0, d1 = self.Ducts["D5"]
                ty = d0 + 2.2
                for x in xs:
                    sh.Wire([(x, y0), (x, ty)], "sg")
                xm = (min(xs) + max(xs)) / 2
                if len(xs) > 1:
                    sh.Wire([(min(xs), ty), (max(xs), ty)], r["cls"])
                    for x in xs:
                        sh.Dot(x, ty, r=0.35)
                sh.Wire([(xm, ty), (xm, d1 + 1.6)], r["cls"])
                for i, s2 in enumerate(r["lines"]):
                    sh.Text(xm, d1 + 3.7 + i * 1.6, s2, size=1.3, anchor="middle")


def BuildPanel():
    sh = Sheet("RMR control panel DIN-rail layout")
    sh.CssExtra = (".ac{stroke-width:.4}.va,.ve{stroke-width:.34}.zp{stroke-width:.38}"
                   ".zs,.pe{stroke-width:.3}.lv{stroke-width:.3}.zl{stroke-width:.24}"
                   ".sg{stroke-width:.17}.sgc{stroke-width:.36}.cb{stroke-width:.7}")
    DrawFrame(sh, "RMR control panel: DIN-rail layout and wiring",
              "Sheet 1's circuits on five DIN rails with wire ducts between them. Every wire runs "
              "in a duct; the line shows its route and the terminal labels name both ends.")
    p = Panel(sh)
    p.SideX["L"] = (6.0, 16.0)
    p.SideX["R"] = (340.0, 350.0)
    rows = [("R1", 26.0, 40.5), ("R2", 56.5, 69.0), ("R3", 86.0, 104.0), ("R4", 121.0, 133.5),
            ("R5", 150.0, 161.5)]
    ducts = [("D0", 18.0, 25.0), ("D1", 41.5, 55.5), ("D2", 70.0, 85.0), ("D3", 105.0, 120.0),
             ("D4", 134.5, 149.0), ("D5", 162.5, 168.5)]
    for n, y0, y1 in ducts:
        p.AddDuct(n, y0, y1)
    for i, (n, yT, yB) in enumerate(rows):
        p.Rows[n] = (yT, yB, "D%d" % i, "D%d" % (i + 1))
    for n, y0, y1 in ducts:
        sh.Rect(17.0, y0, 322.5, y1 - y0, "duct")
    for side, (x0, x1) in p.SideX.items():
        sh.Rect(x0, 18.0, x1 - x0, 150.5, "duct")
    for i, (n, yT, yB) in enumerate(rows):
        yc = (yT + yB) / 2
        sh.Rect(17.0, yc - 3.0, 322.5, 6.0, "rail")
        sh.Circle(18.6, yc, 1.9, "symf")
        sh.Text(18.6, yc + 0.75, str(i + 1), size=2.1, anchor="middle", weight="bold")
    for d in ("D0", "D1"):
        y0, y1 = p.Ducts[d]
        sh.Wire([(236.0, y0), (236.0, y1)], "zl", ' stroke-dasharray="1 .6"')
    sh.Text(237.0, 17.2, "110 VAC compartment: separator in both ducts", size=1.3, weight="bold",
            fill=TolRed)

    # ------------------------------------------------ rail 1
    p.TermBlock("R1", "X2", 21.0, ["1", "2", "2b", "3", "3b", "4", "5"], "X2 door 24 V",
                pitch=3.1, bridges=[(1, 2), (3, 4)])
    p.Device("R1", "K2", 47.0, 67.0, "K2", sub=("BMC7-25U", "coil 24 V"),
             top=[("1", 49.5, "1"), ("3", 53.5, "3"), ("5", 57.5, "5"), ("7", 61.5, "7"),
                  ("A1", 65.0, "A1")],
             bot=[("2", 49.5, "2"), ("4", 53.5, "4"), ("6", 57.5, "6"), ("8", 61.5, "8"),
                  ("A2", 65.0, "A2")])
    p.Device("R1", "FB1", 73.0, 105.0, "FB1 12-way", sub=("always on",),
             bot=[("IN", 75.0, "IN")] + [("F%d" % (i + 1), 80.0 + i * 4.5, "F1-%d" % (i + 1))
                                         for i in range(6)])
    for key, x0, t1, t2 in [("MB", 110.0, "Mega buck", "5 V"), ("PB", 128.0, "Pi buck", "5.1 V 5 A"),
                            ("SB", 146.0, "Screen", "supply")]:
        p.Device("R1", key, x0, x0 + 14.0, t1, sub=(t2,), titleSize=1.5,
                 bot=[("IN+", x0 + 1.8, "+"), ("IN-", x0 + 5.2, "-"), ("OUT+", x0 + 8.6, "o+"),
                      ("OUT-", x0 + 12.0, "o-")])
    p.Device("R1", "PSU", 166.0, 232.0, "PSU 24 V 1200 W", sub=("DIN clips or panel screws",),
             bot=[("V+a", 169.0, "+V"), ("V+b", 173.0, "+V"), ("V-a", 179.0, "-V"),
                  ("FG", 205.0, "FG"), ("N", 218.0, "N"), ("L", 223.0, "L")])
    p.Device("R1", "K1", 240.0, 256.0, "K1", sub=("HC1-63", "coil 110 VAC"),
             top=[("1", 243.0, "1"), ("3", 248.0, "3"), ("A1", 253.0, "A1")],
             bot=[("2", 243.0, "2"), ("4", 248.0, "4"), ("A2", 253.0, "A2")])
    p.Device("R1", "F0", 260.5, 267.5, "F0", sub=("1 A T",), titleSize=1.6,
             top=[("out", 264.0, "")], bot=[("in", 264.0, "")])
    p.TermBlock("R1", "X1", 272.0, ["1", "2", "3"], "X1 door 110 V")
    p.TermBlock("R1", "X0", 286.0, ["L", "L", "N", "N", "PE"], "X0 mains in",
                bridges=[(0, 1), (2, 3)])
    p.Device("R1", "PE", 309.0, 337.0, "PE bar", sub=("on rail 1",),
             top=[("t1", 313.0, "")],
             bot=[("b1", 313.0, ""), ("b2", 317.0, ""), ("b3", 321.0, ""), ("b4", 325.0, "")])

    # ------------------------------------------------ rail 2
    p.Device("R2", "S", 21.0, 36.0, "Star S", sub=("dist. block",), titleSize=1.5,
             top=[("IN", 23.0, "in"), ("MB", 26.0, ""), ("PB", 29.0, ""), ("SB", 32.0, ""),
                  ("PE", 34.5, "")],
             bot=[("0VP", 23.0, ""), ("SP", 28.0, "")])
    zbot = [("IN", 43.0, "in")] + [("d%d" % (i + 1), 50.0 + i * 6.0, "") for i in range(8)] + \
           [("UV", 98.0, ""), ("V", 104.0, ""), ("T", 110.0, "")]
    p.Device("R2", "ZP", 40.0, 114.0, "0V-P power bus", sub=("two uxcell bars, linked",),
             top=[("K2", 45.0, "")], bot=zbot)
    p.Device("R2", "FB2", 120.0, 182.0, "FB2 12-way", sub=("E-stop side, behind K2",),
             top=[("IN", 122.0, "IN")],
             bot=[("F%d" % (i + 1), 124.0 + i * 5.0, "%d" % (i + 1)) for i in range(12)])
    p.Device("R2", "SP", 188.0, 203.0, "Servo PSU", sub=("6 V",), titleSize=1.5,
             bot=[("IN+", 189.8, "+"), ("IN-", 193.2, "-"), ("OUT+", 196.6, "o+"),
                  ("OUT-", 200.0, "o-")])
    sh.Text(270.0, 64.2, "spare rail", size=1.6, anchor="middle", italic=True)

    # ------------------------------------------------ rail 3
    drv = [("X", 50.0), ("Y1", 78.0), ("Y2", 106.0), ("Z", 134.0), ("A", 162.0), ("B", 190.0),
           ("C", 218.0)]
    for ax, x0 in drv:
        p.Device("R3", ax, x0, x0 + 24.0, ax, sub=("TB6600",), titleSize=2.6,
                 top=[("+V", x0 + 2.5, "+V"), ("0V", x0 + 6.0, "0V"), ("M", x0 + 16.0, "motor")],
                 bot=[("SIG", x0 + 10.0, "sig"), ("COM", x0 + 18.0, "com")])
    p.Device("R3", "OD", 248.0, 282.0, "ODrive S1", sub=("on a DIN carrier",), titleSize=2.0,
             top=[("DC+", 250.5, "+"), ("DC-", 254.0, "-"), ("PH", 264.0, "A B C"),
                  ("ENC", 275.0, "enc")],
             bot=[("TX", 252.0, "TX"), ("RX", 256.0, "RX"), ("GND", 260.0, "G"),
                  ("5V", 264.0, "5V")])
    p.Device("R3", "SC", 288.0, 322.0, "Shield clamp bar", sub=("motor cable shields",),
             titleSize=1.6, top=[("PE", 318.0, "PE")])

    # ------------------------------------------------ rail 4
    p.TermBlock("R4", "ZS", 19.5, ["X", "Y1", "Y2", "Z", "A", "B", "C", "J", "lk"], "0V-S bus",
                pitch=3.0, bridges=[(0, 8)])
    megaTop = [("PWR+", 51.0, "+"), ("PWR-", 54.0, "-")]
    groups = dict((ax, " ".join(DriverPins[ax])) for ax in DriverPins)
    for ax, x0 in drv:
        megaTop.append(("g" + ax, x0 + 10.0, ""))
    megaTop += [("17", 238.0, "17"), ("16", 242.0, "16")]
    megaBot = [("GND", 51.5, "G")] + \
              [(pn, 55.5 + i * 3.8, pn) for i, (ax, pn) in enumerate(EndstopPins)] + \
              [("5", 80.0, "5"), ("6", 84.0, "6"), ("USB", 124.0, "USB"), ("43", 160.0, "43"),
               ("5V", 164.0, "5V"), ("39", 236.0, "39"), ("4", 240.0, "4"), ("42", 244.0, "42")]
    p.Device("R4", "MEGA", 48.0, 247.0, "Arduino Mega 2560, screw-terminal breakout on a DIN carrier",
             titleSize=1.8, top=megaTop, bot=megaBot)
    for ax, x0 in drv:
        sh.Text(x0 + 10.0, 124.3, groups[ax], size=1.1, anchor="middle")
    sh.Text(148.0, 131.2, "1 k from 5V to 43 and 100 nF from 40 to GND, both on the breakout",
            size=1.2, anchor="middle")
    p.Device("R4", "SU", 251.0, 265.0, "SSR-UV", titleSize=1.5, sub=("DC SSR",),
             top=[("OUT+", 258.0, "+")],
             bot=[("OUT-", 253.0, "-"), ("IN+", 257.5, "i+"), ("IN-", 262.0, "i-")])
    p.Device("R4", "SV", 269.0, 283.0, "SSR-valve", titleSize=1.5, sub=("DC SSR",),
             top=[("OUT+", 276.0, "+")],
             bot=[("OUT-", 271.0, "-"), ("IN+", 275.5, "i+"), ("IN-", 280.0, "i-")])
    p.TermBlock("R4", "ZT", 288.0, ["1", "2", "3", "lk"], "0V-S, 2nd group", pitch=3.0,
                bridges=[(0, 3)])
    sh.Text(318.0, 128.8, "spare rail", size=1.6, anchor="middle", italic=True)

    # ------------------------------------------------ rail 5
    p.TermBlock("R5", "X4", 21.0, ["3", "14", "40", "15", "23", "A9", "C", "C", "C", "C", "C", "C"],
                "X4 endstops", pitch=3.2, bridges=[(6, 11)])
    p.TermBlock("R5", "X5", 63.0, ["6V", "6V", "0V", "0V", "P0", "P1"], "X5 servos",
                bridges=[(0, 1), (2, 3)])
    p.TermBlock("R5", "X8", 87.0, ["s+", "s-", "22", "G"], "X8 door")
    piTop = [("5V", 110.0, "5V"), ("GNDp", 113.0, "G"), ("USB", 117.0, "USB"), ("5", 122.0, "5"),
             ("6", 125.0, "6"), ("13", 128.0, "13"), ("26", 131.0, "26"), ("GND2", 134.0, "G"),
             ("20", 138.0, "20"), ("GND", 141.0, "G"), ("3V3", 144.0, "3V3"), ("22", 147.5, "22"),
             ("GND3", 150.5, "G")]
    p.Device("R5", "PI", 107.0, 153.0, "Raspberry Pi 5", sub=("DIN case, GPIO terminals",),
             titleSize=1.7, top=piTop, bot=[("HDMI", 130.0, "HDMI + USB")])
    sh.Text(141.5, 167.3, "1 k from 3V3 to 20 at the Pi", size=1.1, anchor="middle", halo=True)
    ts = [("IN%d" % (i + 1), 159.0 + i * 3.0, str(i + 1)) for i in range(4)] + \
         [("IN-", 171.0, "i-"), ("OUT+", 175.0, "o+")] + \
         [("O%d" % (i + 1), 178.5 + i * 3.0, str(i + 1)) for i in range(4)]
    p.Device("R5", "TS", 157.0, 190.0, "Tower SSR x 4", sub=("IN- and OUT+ jumpered",),
             titleSize=1.5, top=ts)
    p.TermBlock("R5", "X7", 194.0, ["R", "A", "G", "Bz", "C"], "X7 tower")
    sh.Text(202.5, 167.3, "C: tower common, 0 V assumed", size=1.1, anchor="middle", halo=True)
    p.TermBlock("R5", "X6", 250.0, ["UV+", "UV-", "S5", "S5c", "V+", "V-"], "X6 lid, valve")
    sh.Text(306.0, 156.8, "spare rail", size=1.6, anchor="middle", italic=True)

    W = p.W
    # ------------------------------------------------ 110 VAC
    W("ac", "X0.1t", "K1.1")
    W("ac", "X0.3t", "K1.3")
    W("ac", "X0.2b", "F0.in")
    W("ac", "F0.out", "X1.1t")
    W("ac", "X1.2t", "K1.A1")
    W("ac", "X0.4t", "X1.3t")
    W("ac", "X0.4b", "K1.A2")
    W("ac", "K1.2", "PSU.L")
    W("ac", "K1.4", "PSU.N")
    W("pe", "PSU.FG", "PE.b1")
    W("pe", "X0.5t", "PE.t1")
    p.Exit("cb", ["X0.1b", "X0.3b", "X0.5b"], "R", ["from rear switch Q0:", "L, N, PE"], up=True)
    p.Exit("cb", ["X1.1b", "X1.2b", "X1.3b", "PE.b2"], "R",
           ["to door plate: S1 knob,", "H1 lamp, plate PE"])
    # ------------------------------------------------ 24 V and the E-stop latch
    W("va", "PSU.V+a", "FB1.IN")
    W("va", "PSU.V+b", "K2.1", via=70.0)
    W("va", "K2.2", "K2.3", via=44.6)
    W("ve", "K2.4", "FB2.IN")
    W("zp", "PSU.V-a", "S.IN")
    W("va", "FB1.F1", "MB.IN+")
    W("va", "FB1.F2", "PB.IN+")
    W("va", "FB1.F3", "SB.IN+")
    W("zp", "MB.IN-", "S.MB")
    W("zp", "PB.IN-", "S.PB")
    W("zp", "SB.IN-", "S.SB")
    W("va", "FB1.F5", "X2.1b")
    W("va", "FB1.F4", "TS.OUT+", via="L")
    W("ve", "X2.3t", "K2.5")
    W("ve", "X2.4b", "K2.6")
    W("ve", "X2.5t", "K2.A1")
    W("zp", "K2.A2", "ZP.K2")
    W("sg", "K2.7", "MEGA.43", via="L")
    W("zs", "K2.8", "ZS.1b", via="L")
    W("sg", "X2.6b", "PI.20", via="L")
    W("sg", "X2.7b", "PI.GND", via="L")
    p.Exit("cb", ["X2.1t", "X2.2t", "X2.4t", "X2.6t", "X2.7t"], "L",
           ["to door plate: S2 E-stop", "NC1 + NC2, S3 Reset"])
    W("lv", "MB.OUT+", "MEGA.PWR+", via="L")
    W("zl", "MB.OUT-", "MEGA.PWR-", via="L")
    W("lv", "PB.OUT+", "PI.5V", via="L")
    W("zl", "PB.OUT-", "PI.GNDp", via="L")
    W("lv", "SB.OUT+", "X8.1t", via="L")
    W("zl", "SB.OUT-", "X8.2t", via="L")
    # ------------------------------------------------ rail 2 distribution
    W("zp", "S.0VP", "ZP.IN")
    W("pe", "S.PE", "PE.b3")
    W("zp", "SP.IN-", "S.SP")
    W("ve", "FB2.F9", "SP.IN+")
    W("lv", "SP.OUT+", "X5.1t", via="L")
    W("zl", "SP.OUT-", "X5.3t", via="L")
    for i, (ax, x0) in enumerate(drv):
        W("ve", "FB2.F%d" % (i + 1), ax + ".+V")
        W("zp", "ZP.d%d" % (i + 1), ax + ".0V")
    W("ve", "FB2.F8", "OD.DC+")
    W("zp", "ZP.d8", "OD.DC-")
    W("ve", "FB2.F10", "SU.OUT+", via="R")
    W("ve", "FB2.F11", "SV.OUT+", via="R")
    W("zp", "ZP.UV", "X6.2t", via="R")
    W("zp", "ZP.V", "X6.6t", via="R")
    W("zp", "ZP.T", "X7.5t", via="R")
    W("pe", "SC.PE", "PE.b4", via="R")
    p.Exit("cb", [ax + ".M" for ax, x0 in drv] + ["OD.PH", "OD.ENC"], "R",
           ["motor + encoder cables out,", "shields on the clamp bar"])
    # ------------------------------------------------ rail 3 to rail 4 signals
    for i, (ax, x0) in enumerate(drv):
        W("sgc", ax + ".SIG", "MEGA.g" + ax)
        W("zs", ax + ".COM", "ZS.%dt" % (i + 1))
    W("zs", "OD.GND", "ZS.8t")
    W("sg", "OD.TX", "MEGA.17")
    W("sg", "OD.RX", "MEGA.16")
    # ------------------------------------------------ rail 4 to rail 5
    W("zs", "MEGA.GND", "ZS.2b")
    for i, (ax, pn) in enumerate(EndstopPins):
        W("sg", "MEGA." + pn, "X4.%dt" % (i + 1))
    W("zs", "X4.7t", "ZS.3b")
    W("sg", "MEGA.5", "X5.5t")
    W("sg", "MEGA.6", "X5.6t")
    W("sg", "MEGA.4", "SU.IN+")
    W("sg", "MEGA.42", "SV.IN+")
    W("zs", "SU.IN-", "ZT.1b")
    W("zs", "SV.IN-", "ZT.2b")
    W("zs", "ZT.4t", "ZS.9t")
    W("sg", "MEGA.39", "X6.3t")
    W("zs", "X6.4t", "ZT.3b")
    W("sgc", "MEGA.USB", "PI.USB")
    W("ve", "SU.OUT-", "X6.1t")
    W("ve", "SV.OUT-", "X6.5t")
    for i, g in enumerate(["5", "6", "13", "26"]):
        W("sg", "PI." + g, "TS.IN%d" % (i + 1))
        W("va", "TS.O%d" % (i + 1), "X7.%dt" % (i + 1))
    W("sg", "TS.IN-", "PI.GND2")
    W("sg", "PI.22", "X8.3t")
    W("sg", "PI.GND3", "X8.4t")
    # field cables out of the bottom
    p.Exit("cb", ["X4.%db" % (i + 1) for i in range(12)], "B",
           ["to endstops X Y Z A B C,", "one twisted pair each"])
    p.Exit("cb", ["X5.%db" % (i + 1) for i in range(6)], "B", ["to gripper", "and lid servos"])
    p.Exit("cb", ["X8.%db" % (i + 1) for i in range(4)], "B", ["to screen power,", "home button"])
    p.Exit("cb", ["PI.HDMI"], "B", ["HDMI + USB", "to screen"])
    p.Exit("cb", ["X7.%db" % (i + 1) for i in range(5)], "B", ["to status", "tower"])
    p.Exit("cb", ["X6.%db" % (i + 1) for i in range(6)], "B",
           ["to lid (S4 + UV array, S5)", "and argon valve (D1 there)"])
    p.Route()
    # ODrive J11 logic supply: unresolved
    x, y = p.Terms["OD.5V"][:2]
    sh.Wire([(x, y), (x, y + 3.0)], "lv", ' stroke-dasharray="1.1 .8"')
    sh.Text(x + 0.8, y + 3.2, "J11 5 V: which side? (sheet 1 note 3)", size=1.2, halo=True)
    PanelFooter(sh)
    return sh


def PanelFooter(sh):
    y0 = 176.0
    # legend
    sh.Text(8, y0 + 1.0, "Legend", size=2.2, weight="bold")
    items = [("ac", "110 VAC"), ("va", "+24 V always on"), ("ve", "+24 V behind K2"),
             ("zp", "0 V power"), ("zs", "0V-S signal bus"), ("pe", "PE"),
             ("lv", "logic supply +"), ("zl", "logic supply 0 V"), ("sg", "signal"),
             ("sgc", "multi-core signal cable"), ("cb", "cable leaving the panel")]
    for i, (cls, lab) in enumerate(items):
        cx = 8 + (i % 3) * 37.0
        cy = y0 + 4.2 + (i // 3) * 2.6
        sh.Wire([(cx, cy - 0.5), (cx + 5.5, cy - 0.5)], cls)
        sh.Text(cx + 6.5, cy, lab, size=1.6)
    cy = y0 + 4.2 + 4 * 2.6
    sh.Rect(8, cy - 1.6, 5.5, 2.2, "duct")
    sh.Text(14.5, cy, "wire duct", size=1.6)
    sh.Rect(45, cy - 1.4, 5.5, 1.8, "rail")
    sh.Text(51.5, cy, "DIN rail (TS35)", size=1.6)
    sh.Rect(82, cy - 1.6, 1.0, 2.2, "bx")
    sh.Rect(83, cy - 1.6, 1.0, 2.2, "bx")
    sh.Wire([(82.5, cy - 0.5), (83.5, cy - 0.5)], "sym")
    sh.Text(85.2, cy, "terminal block, bridged", size=1.6)
    cy += 2.8
    sh.Text(8, cy, "Field cables: one twisted pair per endstop; motor cables shielded, shield to PE at the drive end.",
            size=1.45)
    # rails and notes
    nx = 122.0
    sh.Text(nx, y0 + 1.0, "Five rails, top to bottom", size=2.2, weight="bold")
    rl = ["1  X2, K2, FB1, Mega / Pi / screen bucks, PSU, K1, F0, X1, X0, PE bar",
          "2  Star S, 0V-P bus, FB2, servo PSU (spare length at the right)",
          "3  Drivers X Y1 Y2 Z A B C, ODrive S1, shield clamp bar",
          "4  0V-S bus, Mega breakout, SSR-UV, SSR-valve",
          "5  Field terminals X4 X5 X8 X7 X6, Pi 5, tower SSRs"]
    for i, s2 in enumerate(rl):
        sh.Text(nx, y0 + 4.0 + i * 2.25, s2, size=1.5)
    notes = ["Arrangement, not to scale; terminal positions are drawn where the routing is clearest.",
             "Land each wire on the terminal it is drawn to. Measure parts before cutting rail and duct.",
             "Gauges, copper only: mains L and N, PSU to FB1, K2, FB2 and S, S to 0V-P: 12 AWG.",
             "F2-1 to F2-7: 18 AWG. F2-8: 16. F0 rung: 300 V insulation. Everything else: 20 AWG.",
             "TB6600, ODrive, bucks, SSR modules, Mega and Pi need DIN clips or carriers.",
             "Bond every rail and the frame to PE (chassis stud); 0 V meets PE only at S.",
             "Open items and the firmware gap: sheet 1, notes 3 to 5."]
    for i, s2 in enumerate(notes):
        sh.Text(nx, y0 + 16.4 + i * 2.25, s2, size=1.5)
    TitleBlock(sh, 256, 186, 92, 21.5, [
        "RMR control panel: DIN-rail layout",
        "Sheet 2 of 2. Legal 14 x 8.5 in, landscape. Print at 100 %.",
        "Robot-MakingRobot, docs/wiring. Drawn 2026-10-14.",
        "Status: design, not yet built or tested.",
        "Circuits and part data: sheet 1.",
    ])


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
                ("Upper front", 110.0, "Mega USB, J11", "UF"),
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
    """Orthographic view: real (a, b) mm to paper mm. a runs right, b runs up."""

    def __init__(self, sh, x0, y0, aSpan, bSpan, scale):
        self.Sh, self.X0, self.Y0, self.ASpan, self.BSpan, self.S = sh, x0, y0, aSpan, bSpan, scale

    def X(self, a):
        return self.X0 + a / self.S

    def Y(self, b):
        return self.Y0 + (self.BSpan - b) / self.S

    def Box(self, a0, b0, a1, b1, fill="#fff", dashed=False, stroke=0.25, lines=(), size=1.4,
            bold=True, rot=0):
        sh = self.Sh
        x, y = self.X(a0), self.Y(b1)
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
        """Slot with full-round ends, along a or along b, from the DXF's own vertices."""
        rp = Fmt(min(a1 - a0, b1 - b0) / 2 / self.S)
        p = [(Fmt(self.X(a)), Fmt(self.Y(b))) for a, b, _ in ObroundPts(a0, b0, a1, b1)]
        d = ("M%s %s L%s %s A%s %s 0 0 0 %s %s L%s %s A%s %s 0 0 0 %s %s Z"
             % (p[0] + p[1] + (rp, rp) + p[2] + p[3] + (rp, rp) + p[0]))
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
    sh = v.Sh
    if upper:
        v.Poly(PlateGeom("upper")[0], fill="#fff", stroke=0.35)
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="#000" '
               'stroke-width=".2" stroke-dasharray="1.2 .7"/>'
               % (Fmt(v.X(Frame)), Fmt(v.Y(BoxW - Frame)), Fmt(RingLong / v.S),
                  Fmt(RingShort / v.S)))
        top = "upper posts stand on the plate; mid ring (dashed) under it"
    else:
        v.Box(0, 0, BoxD, BoxW, fill=ZoneFill["frame"], stroke=0.35)
        v.Box(Frame, Frame, BoxD - Frame, BoxW - Frame, fill="#fff", stroke=0.25)
        top = "bottom ring on the base plate"
    for x, y in PostCentres:
        v.Box(x - Frame / 2, y - Frame / 2, x + Frame / 2, y + Frame / 2, fill=PostFill, stroke=0.3)
    sh.Text(v.X(BoxD / 2), v.Y(BoxW) + 2.6, top, size=1.2, anchor="middle")
    sh.Text(v.X(2), v.Y(BoxW / 2), "FRONT", size=1.3, anchor="middle", rot=-90, weight="bold")
    sh.Text(v.X(BoxD - 2) + 0.9, v.Y(BoxW / 2), "BACK", size=1.3, anchor="middle", rot=-90,
            weight="bold")
    sh.Text(v.X(BoxD / 2), v.Y(2) + 0.5, "LEFT SIDE", size=1.2, anchor="middle", weight="bold")
    sh.Text(v.X(BoxD / 2), v.Y(BoxW - 2) + 0.9, "RIGHT SIDE", size=1.2, anchor="middle",
            weight="bold")
    sh.Text(v.X(Frame + 4), v.Y(Frame / 2 - 2), deckLabel, size=1.2, italic=True)


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
PeBarTerms = 4                     # USLKG blocks in the PE bar on the 110 V rail (sheet 2, rail 1)
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
    short = {"UL": "field", "ULM": "motors", "UF": "USB, J11", "UR": "motor, tower", "LL": "ODrive, Pi, E-stop"}

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
    up = View(sh, 10.0, 25.0, BoxD, BoxW, S)
    up.Title("A  Upper deck, seen from above", "1/16 in aluminum plate on the mid ring; parts at true size")
    PlanFrame(up, "upper plate 457 x 330, part of the upper module", upper=True)
    Plan(up, "upper")
    mega = [p for p in upper["logic"]["run"] if p[0] == "Mega"][0]
    yc = upper["logic"]["centre"]
    up.Box(mega[2] - 6.0, yc - 9.5, mega[2], yc + 9.5, fill=ZoneFill["log"], stroke=0.2)
    sh.Text(up.X(mega[2] - 7.0), up.Y(yc + 12) + 0.4, "USB", size=1.0, anchor="end")
    fx0, fx1 = upper["field"]["a0"], upper["field"]["a1"]
    sh.Text(up.X(fx1 + 3), up.Y(upper["field"]["centre"] + 4) + 0.4, "field rail,", size=1.1)
    sh.Text(up.X(fx1 + 3), up.Y(upper["field"]["centre"] + 4) + 2.0, "%d mm" % round(lengths["field"]),
            size=1.1)
    ax = (ClampBox()[2] + BackRunX - DuctWide / 2) / 2
    for i, s2 in enumerate(["ODrive: in the", "spincoater base", "", "Pi: at the", "operator panel"]):
        sh.Text(up.X(ax), up.Y(230) + 1.6 * i, s2, size=1.1, anchor="middle", italic=True)
    for i, (a0, b0, a1, b1) in enumerate(CableSlots):
        up.Obround(a0, b0, a1, b1, stroke=0.35)
        sh.Text(up.X((a0 + a1) / 2), up.Y((b0 + b1) / 2) + 0.45, "slot %d" % (i + 1), size=1.05,
                anchor="middle", halo=True)
    Entries(up, "upper")
    up.DimH(0, BoxD, 0, "18 in (457 mm)")
    up.DimV(0, BoxW, BoxD, "13 in (330 mm)")

    # ------------------------------------------------ lower deck plan
    lo = View(sh, 150.0, 25.0, BoxD, BoxW, S)
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
    sh.Text(lo.X(BoxD) + 0.8, lo.Y(gu) + 0.5, "door 110 V", size=1.1, rot=-90, anchor="middle")
    r110 = LowerRails()["110 V"]
    sh.Text(lo.X((r110["a0"] + BoxD - F) / 2), lo.Y((MainsZoneY + r110["centre"] - 41.0) / 2) + 0.5,
            "110 VAC compartment, no wall", size=1.3, anchor="middle", weight="bold", fill=TolRed)
    lo.Box(BoxD - F, InletU - 21, BoxD, InletU + 21, fill=ZoneFill["110"], stroke=0.35)
    sh.Text(lo.X(BoxD) + 0.8, lo.Y(InletU) + 0.5, "mains in", size=1.2, rot=-90, anchor="middle")
    lo.Box(PsuVentSpan[0], BoxW, PsuVentSpan[1], BoxW + 2.0, fill="#fff", dashed=True, stroke=0.2)
    sh.Text(lo.X(PsuVentSpan[0] + 30), lo.Y(BoxW - F / 2) + 0.4, "PSU vent (dashed)", size=1.0, halo=True)
    Entries(lo, "lower")

    # ------------------------------------------------ elevations
    RailFill, ClipFill = "#888888", "#FFFFFF"

    def Elevation(v, depth):
        """Every solid seen from the front (depth "x": a = y) or from the left (depth "y": a = x),
        painted farthest first: DIN rails dark, printed clips white and dashed."""
        k = 0 if depth == "x" else 1
        for s in sorted(solids, key=lambda t: -t["box"][k]):
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
        """Centre of a rail's run, or of its first part `key`, along the rail."""
        p = [q for q in rail["run"] if key is None or q[0] == key]
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

    sd = View(sh, 150.0, 127.5, BoxD, BoxH, S)
    sd.Title("D  Side view from the left", "left rails left off; nearer parts hide farther ones")
    SectionFrame(sd, BoxD)
    Elevation(sd, "y")
    Tag(sd, Mid(lower["fuses"], "FB2"), LoDeck + 31, ["FB2"])
    Tag(sd, Mid(lower["fuses"], "FB1"), LoDeck + 31, ["FB1"])
    Tag(sd, Mid(lower["5 V PSU"]), LoDeck + 35, ["5 V PSU"])
    Tag(sd, Mid(lower["24 V"], "K2"), LoDeck + 64, ["K2"])
    Tag(sd, (Mid(lower["24 V"], "K2") + PsuX0 + PartSize["PSU24"][0]) / 2 + 20, LoDeck + 60,
        ["24 V PSU behind"], size=1.0)
    Tag(sd, Mid(lower["110 V"], "K1"), LoDeck + 62, ["K1"])
    Tag(sd, Mid(upper["field"]), UpDeck + 21, ["field terminals, 42 on rail"])
    Tag(sd, Mid(upper["logic"], "Mega"), UpDeck + 47, ["Mega"], size=1.0)
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
            "front (USB, J11), upper right (a motor, the",
            "tower), lower left (ODrive 24 V, Pi 5 V,",
            "E-stop). Mains in at the back wall in line with",
            "the 110 V rail; the 110 V door cable leaves",
            "beside it by an M20 gland; no wall around",
            "the mains parts (ADR-0013)."]),
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
    """The frame seen from the left side (span = BoxD) or from the front (span = BoxW)."""
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
        v = View(sh, x0, 30.0, BoxD, BoxW, S)
        v.Title(title, sub)
        outline, holes, slots = PlateGeom(kind)
        v.Poly(outline, fill="#EEEEEE", stroke=0.3)
        sh.Add('<rect x="%s" y="%s" width="%s" height="%s" fill="none" stroke="#000" '
               'stroke-width=".18" stroke-dasharray="1 .6"/>'
               % (Fmt(v.X(F)), Fmt(v.Y(BoxW - F)), Fmt(RingLong / S), Fmt(RingShort / S)))
        for x, y in PostCentres:
            v.Box(x - F / 2, y - F / 2, x + F / 2, y + F / 2, fill="none", dashed=True, stroke=0.18)
        for s in slots:
            v.Obround(*s)
        for i, (a0, b0, a1, b1) in enumerate(CableSlots if kind == "upper" else []):
            sh.Text(v.X((a0 + a1) / 2), v.Y(b1) - 0.6, str(i + 1), size=1.3, anchor="middle",
                    weight="bold")
        for x, y, d in holes:
            v.Hole(x, y, d)
        if kind in PeStud:
            px, py = PeStud[kind]
            sh.Text(v.X(px) - 1.2, v.Y(py) + 0.45, "PE", size=1.2, anchor="end", weight="bold")
        ty = 0.75 * BoxW               # clear of the cable slots and the PE studs
        sh.Text(v.X(BoxD / 2), v.Y(ty) - 1.0, "5052-H32, 1/16 in: sheared and drilled", size=1.6,
                anchor="middle", weight="bold")
        sh.Text(v.X(BoxD / 2), v.Y(ty) + 1.4, "seen from above, front on the left",
                size=1.3, anchor="middle")
        sh.Text(v.X(BoxD / 2), v.Y(ty) + 3.2, "dashed: %s" %
                ("posts and bottom ring on the plate" if kind == "base"
                 else "upper posts on the plate, mid ring under it"), size=1.3, anchor="middle")
        xs = sorted(set(round(x, 1) for x, _, _ in holes) | {0.0, BoxD})
        ys = sorted(set(round(y, 1) for _, y, _ in holes) | {0.0, BoxW})
        v.OrdX(xs, 0)
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
        sh.Lines(v.X(0), v.Y(0) + 8.2, sched, size=1.3, lead=1.85)

    # ------------------------------------------------ the frame from the left and from the front
    sd = View(sh, 18.0, 133.0, BoxD, BoxH, S)
    sd.Title("C  Frame from the left side", "studs dark, screws dashed")
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

    # ------------------------------------------------ A: from the left side, front on the left
    va = View(sh, 62.0, 30.0, BoxD, span, S)
    va.Title("A  Box in the gantry, from the left side", "front on the left")
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
              ("wiring_din_rails_legal.svg", BuildPanel()),
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
