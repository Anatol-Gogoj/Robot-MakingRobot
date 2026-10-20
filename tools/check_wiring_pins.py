"""Check the Mega pins drawn in docs/wiring against the firmware headers.

Compares tools/draw_wiring.py's DriverPins, EndstopPins and OtherPins with
pins_RAMPS_14_RMR.h (which includes pins_RAMPS.h) and Configuration_adv.h, then
confirms each pin label appears on sheet 1 and each pin is a wired terminal of the
Mega on sheet 2B. Exits non-zero on any mismatch.

Usage: python tools/check_wiring_pins.py
"""

import os
import re
import sys

Here = os.path.dirname(os.path.abspath(__file__))
Root = os.path.dirname(Here)
sys.path.insert(0, Here)
import draw_wiring  # noqa: E402

MarlinDir = os.path.join(Root, "Marlin-2.1.2.7", "Marlin")
RmrPins = os.path.join(MarlinDir, "src", "pins", "ramps", "pins_RAMPS_14_RMR.h")
RampsPins = os.path.join(MarlinDir, "src", "pins", "ramps", "pins_RAMPS.h")
ConfigAdv = os.path.join(MarlinDir, "Configuration_adv.h")
DefineRe = re.compile(r"^\s*#define\s+(\w+)\s+(-?\d+)\b")


def Defines(path, firstWins, skipBlock=None):
    """Numeric #defines of a header; skipBlock names an #if ENABLED(...) block to ignore."""
    out = {}
    depth = 0
    skipping = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("#if"):
                depth += 1
                if skipBlock and skipBlock in s and not skipping:
                    skipping = depth
            elif s.startswith("#endif"):
                if skipping == depth:
                    skipping = 0
                depth -= 1
            if skipping:
                continue
            m = DefineRe.match(line)
            if m:
                if firstWins and m.group(1) in out:
                    continue
                out[m.group(1)] = int(m.group(2))
    return out


def BoardToDigital(label):
    return 54 + int(label[1:]) if label.startswith("A") else int(label)


def Main():
    ramps = Defines(RampsPins, firstWins=True, skipBlock="FOAMCUTTER_XYUV")
    rmr = Defines(RmrPins, firstWins=False)
    adv = Defines(ConfigAdv, firstWins=False)

    def Pin(name):
        return rmr[name] if name in rmr else ramps.get(name)

    marlinAxis = {"X": "X", "Y1": "Y", "Y2": "Y2", "Z": "Z", "A": "I", "B": "J", "C": "K"}
    endstopName = {"X": "X_MIN_PIN", "Y": "Y_MIN_PIN", "Z": "Z_STOP_PIN", "A": "I_MAX_PIN",
                   "B": "J_MIN_PIN", "C": "K_MIN_PIN"}
    otherName = {"servo gripper": ("SERVO0_PIN", rmr), "servo lid": ("SERVO1_PIN", rmr),
                 "UV SSR": ("UV_LAMP_PIN", adv), "lid switch S5": ("LID_SWITCH_PIN", adv),
                 "motor power sense": ("MOTOR_POWER_SENSE_PIN", adv)}
    fixed = {"valve SSR": 42, "ODrive TX2": 16, "ODrive RX2": 17}  # M42 P42; Serial2 on the Mega

    bad = 0
    rows = []
    for ax, labels in draw_wiring.DriverPins.items():
        for kind, label in zip(("STEP", "DIR", "ENABLE"), labels):
            name = "%s_%s_PIN" % (marlinAxis[ax], kind)
            rows.append((ax + " " + kind, label, name, Pin(name)))
    for ax, label in draw_wiring.EndstopPins:
        rows.append((ax + " endstop", label, endstopName[ax], Pin(endstopName[ax])))
    for what, label in draw_wiring.OtherPins.items():
        if what in otherName:
            name, table = otherName[what]
            rows.append((what, label, name, table.get(name)))
        else:
            rows.append((what, label, "(fixed)", fixed[what]))
    for what, label, name, fw in rows:
        ok = fw is not None and BoardToDigital(label) == fw
        bad += not ok
        print("%-4s %-22s drawn %-4s = D%-3d firmware %-22s %s"
              % ("ok" if ok else "FAIL", what, label, BoardToDigital(label), name, fw))

    svgDir = os.path.join(Root, "docs", "wiring")
    with open(os.path.join(svgDir, "wiring_schematic_legal.svg"), encoding="utf-8") as f:
        svg = f.read()
    labels = set(re.findall(r">([^<>]+)</text>", svg))
    words = set(w for s in labels for w in s.split())
    missing = [label for _, label, _, _ in rows if label not in words]
    bad += len(missing)
    print("wiring_schematic_legal.svg: %s" % ("every pin label present" if not missing
                                              else "MISSING " + ", ".join(missing)))
    # Sheet 2B: a word search would pass on terminal numbers and X4's labels, so ask the generator
    # for the Mega's own terminals instead: each pin must be one (a driver's three pins share the
    # terminal of its signal cable), and each terminal must carry a wire.
    d = draw_wiring.DeckSheet("upper")[1]
    wired = set(w[k] for w in d.Wires for k in ("a", "b"))
    have = {}
    for key in d.Ends:
        if key.startswith("MEGA.g"):
            for pin in draw_wiring.DriverPins[key[len("MEGA.g"):]]:
                have[pin] = key
        elif key.startswith("MEGA."):
            have[key[len("MEGA."):]] = key
    missing = [label for _, label, _, _ in rows if label not in have]
    unwired = sorted(set(k for k in have.values() if k not in wired))
    bad += len(missing) + len(unwired)
    print("sheet 2B, the Mega's terminals: %s" % ("every pin present and wired" if not missing and not unwired
                                                 else "MISSING %s, UNWIRED %s" % (missing, unwired)))
    print("PASS" if not bad else "FAIL: %d problem(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(Main())
