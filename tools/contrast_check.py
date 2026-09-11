#!/usr/bin/env python3
"""WCAG 2.1 contrast check for the RMR web UI colour themes.

Parses the theme token blocks straight out of the HTML (`:root { ... }` and every
`html[data-theme="..."] { ... }` block in the <style>), then checks each text / UI role
against every surface it is drawn on:

    text roles  (text, dim, green, yellow, red, blue, label ...)  need >= 4.5 : 1   (AA, normal text)
    UI roles    (borders of inputs / buttons, focus ring, bar fill) need >= 3.0 : 1  (AA, non-text)

Run from the repo root (no dependencies):

    python tools/contrast_check.py                      # both UIs, exit 1 on any failure
    python tools/contrast_check.py RMR_Touch.html -v    # one file, print every pair

Edit a theme in the HTML, re-run, and keep every line green before committing.
"""
import re
import sys

FILES = ['RMR_Controller.html', 'RMR_Touch.html']

# (foreground token, background token, minimum ratio, what it is)
PAIRS = [
    ('text', 'bg', 4.5, 'body text'),
    ('text', 'surface', 4.5, 'panel text'),
    ('text', 'surface2', 4.5, 'text on inputs / chips'),
    ('text', 'panel', 4.5, 'text on panels'),
    ('text-dim', 'bg', 4.5, 'dim text on bg'),
    ('text-dim', 'surface', 4.5, 'dim text on panel'),
    ('text-dim', 'surface2', 4.5, 'dim text on input'),
    ('text-dim', 'panel', 4.5, 'dim text on panel'),
    ('text-dim', 'console-bg', 4.5, 'console info line'),
    ('green', 'surface', 4.5, 'green text (ok / enabled)'),
    ('green', 'bg', 4.5, 'green text on bg'),
    ('green', 'panel', 4.5, 'RPM gauge value'),
    ('green', 'console-bg', 4.5, 'console RX line'),
    ('yellow', 'surface', 4.5, 'yellow text (warn / elapsed)'),
    ('yellow', 'bg', 4.5, 'yellow text on bg'),
    ('yellow', 'console-bg', 4.5, 'console TX line'),
    ('red', 'surface', 4.5, 'red text (error / stop)'),
    ('red', 'bg', 4.5, 'red text on bg'),
    ('red', 'console-bg', 4.5, 'console error line'),
    ('blue', 'surface', 4.5, 'blue text (values)'),
    ('blue', 'bg', 4.5, 'blue text on bg'),
    ('blue', 'panel', 4.5, 'dial degrees'),
    ('cyan', 'surface', 4.5, 'cyan text'),
    ('purple', 'surface', 4.5, 'purple text'),
    ('purple', 'surface2', 3.0, 'UV bar fill vs track (UI)'),
    ('label', 'surface', 4.5, 'field labels'),
    ('label', 'panel', 4.5, 'labels on panels'),
    ('on-accent', 'accent', 4.5, 'text on accent button'),
    ('on-danger', 'danger', 4.5, 'text on E-stop / stop'),
    ('on-green', 'green', 4.5, 'text on green button'),
    ('on-yellow', 'yellow', 4.5, 'text on yellow button'),
    ('on-red', 'red', 4.5, 'text on red button'),
    ('on-blue', 'blue', 4.5, 'text on blue button'),
    ('on-control', 'control', 4.5, 'text on control (Touch buttons / inputs)'),
    ('on-header', 'header', 4.5, 'header text / tabs'),
    ('header-accent', 'header', 4.5, 'header title accent'),
    ('border-strong', 'surface', 3.0, 'input / button border (UI)'),
    ('border-strong', 'surface2', 3.0, 'input border vs input (UI)'),
    ('accent', 'surface', 3.0, 'accent indicator (active tab / pill) (UI)'),
    ('focus', 'surface', 3.0, 'focus ring on panel (UI)'),
    ('focus', 'bg', 3.0, 'focus ring on bg (UI)'),
    ('focus', 'surface2', 3.0, 'focus ring on input (UI)'),
    ('focus-halo', 'focus', 3.0, 'focus ring vs its halo (two-tone ring, any background)'),
]


def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def parse_color(s):
    """#rgb / #rrggbb / rgb() / rgba() -> (r, g, b, a) in 0..255 / 0..1"""
    s = s.strip()
    m = re.fullmatch(r'#([0-9a-fA-F]{3})', s)
    if m:
        h = m.group(1)
        return tuple(int(ch * 2, 16) for ch in h) + (1.0,)
    m = re.fullmatch(r'#([0-9a-fA-F]{6})', s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)', s)
    if m:
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (r, g, b, a)
    raise ValueError('unsupported colour: %r' % s)


def luminance(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b)


def contrast(fg, bg):
    l1, l2 = luminance(parse_color(fg)), luminance(parse_color(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def themes_from_html(path):
    """{theme name: {token: value}} from the <style> block. ':root' is reported as 'default'."""
    with open(path, encoding='utf-8') as f:
        src = f.read()
    m = re.search(r'<style>(.*?)</style>', src, re.S)
    css = m.group(1) if m else src
    out = {}
    for sel, body in re.findall(r'(:root|html\[data-theme="[^"]+"\])\s*\{([^}]*)\}', css):
        name = 'default (:root)' if sel == ':root' else re.search(r'"([^"]+)"', sel).group(1)
        toks = dict(re.findall(r'--([a-z0-9-]+)\s*:\s*([^;]+);', body))
        if len(toks) < 5:
            continue          # e.g. the tiny :root { --touch-min } block
        out.setdefault(name, {}).update(toks)
    return out


def check_file(path, verbose=False):
    failures = 0
    themes = themes_from_html(path)
    if not themes:
        print('%s: no theme blocks found' % path)
        return 1
    print('== %s' % path)
    for name, t in themes.items():
        bad = []
        for fg, bg, need, what in PAIRS:
            if fg not in t or bg not in t:
                bad.append('  MISSING token for "%s" (%s / %s)' % (what, fg, bg))
                continue
            try:
                r = contrast(t[fg], t[bg])
            except ValueError as e:
                bad.append('  UNPARSEABLE %s: %s' % (what, e))
                continue
            ok = r >= need
            if verbose or not ok:
                print('   %s %-42s %-8s on %-8s = %5.2f (need %.1f)' % ('ok  ' if ok else 'FAIL', what, t[fg], t[bg], r, need))
            if not ok:
                bad.append(what)
        failures += len(bad)
        print('   theme %-16s %s' % (name, 'all %d pairs pass' % len(PAIRS) if not bad else '%d FAILURE(S)' % len(bad)))
    return failures


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    verbose = '-v' in sys.argv
    total = sum(check_file(p, verbose) for p in (args or FILES))
    print('\n%s' % ('ALL THEMES PASS' if total == 0 else '%d contrast failure(s)' % total))
    sys.exit(1 if total else 0)
