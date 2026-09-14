#!/usr/bin/env python3
"""Keep the shared Run Log module identical in both browser UIs.

The module (a <style> + <script> block) lives between the markers
    <!-- RMR-RUNLOG:BEGIN -->  ...  <!-- RMR-RUNLOG:END -->
in RMR_Controller.html (the canonical copy) and RMR_Touch.html (a byte-identical copy).

    python tools/sync_runlog.py            copy the Controller's block into the Touch page
    python tools/sync_runlog.py --check    exit 1 if the two copies differ (used by the tests)
    python tools/sync_runlog.py --from F   replace the Controller's block with the block in file F,
                                           then sync the Touch page (first insertion / bulk update)

A page that has no block yet gets it inserted just before its closing </body> tag.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTROLLER = ROOT / "RMR_Controller.html"
TOUCH = ROOT / "RMR_Touch.html"
BEGIN = "<!-- RMR-RUNLOG:BEGIN -->"
END = "<!-- RMR-RUNLOG:END -->"
BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: pathlib.Path, s: str) -> None:
    p.write_text(s, encoding="utf-8", newline="\n")


def extract(html: str, name: str):
    m = BLOCK_RE.search(html)
    if not m:
        return None
    if BLOCK_RE.search(html, m.end()):
        sys.exit(f"{name}: more than one RMR-RUNLOG block")
    return m.group(0)


def replace(html: str, block: str, name: str) -> str:
    m = BLOCK_RE.search(html)
    if m:
        return html[: m.start()] + block + html[m.end():]
    i = html.rfind("</body>")
    if i < 0:
        sys.exit(f"{name}: no RMR-RUNLOG block and no </body> to insert before")
    return html[:i] + block + "\n" + html[i:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    ap.add_argument("--from", dest="src", help="file whose RMR-RUNLOG block replaces the Controller's")
    a = ap.parse_args()

    ctrl, touch = read(CONTROLLER), read(TOUCH)
    if a.src:
        block = extract(read(pathlib.Path(a.src)), a.src)
        if block is None:
            sys.exit(f"{a.src}: no RMR-RUNLOG block")
        ctrl = replace(ctrl, block, CONTROLLER.name)
        write(CONTROLLER, ctrl)
        print(f"{CONTROLLER.name}: block written from {a.src} ({block.count(chr(10)) + 1} lines)")

    block = extract(ctrl, CONTROLLER.name)
    if block is None:
        sys.exit(f"{CONTROLLER.name}: no RMR-RUNLOG block (the canonical copy)")
    tblock = extract(touch, TOUCH.name)

    if a.check:
        if tblock == block:
            print(f"OK: RMR-RUNLOG block identical in {CONTROLLER.name} and {TOUCH.name} ({block.count(chr(10)) + 1} lines)")
            return 0
        print(f"DRIFT: the RMR-RUNLOG block in {TOUCH.name} differs from {CONTROLLER.name} — run python tools/sync_runlog.py")
        return 1

    if tblock == block:
        print(f"{TOUCH.name}: already in sync")
        return 0
    write(TOUCH, replace(touch, block, TOUCH.name))
    print(f"{TOUCH.name}: RMR-RUNLOG block {'updated' if tblock else 'inserted'} ({block.count(chr(10)) + 1} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
