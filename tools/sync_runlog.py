#!/usr/bin/env python3
"""Keep the shared Run Log module identical in both browser UIs.

The module (a <style> + <script> block) lives between the markers
    <!-- RMR-RUNLOG:BEGIN -->  ...  <!-- RMR-RUNLOG:END -->
in RMR_Controller.html (the canonical copy) and RMR_Touch.html (an identical copy).

    python tools/sync_runlog.py            copy the Controller's block into the Touch page
    python tools/sync_runlog.py --check    exit 1 if the two copies differ (used by the tests)
    python tools/sync_runlog.py --from F   replace the Controller's block with the block in file F,
                                           then sync the Touch page (first insertion / bulk update)

A page that has no block yet gets it inserted just before its closing </body> tag.

Line endings: a page is written in the convention it already uses. On a Windows checkout
(core.autocrlf=true) both pages are CRLF on disk while the committed blobs are LF; the block
is converted to the target page's convention on the way in, and the files are read and
written with newline="" so nothing outside the block is touched. --check ignores CRLF/LF
differences: it is a content check, the same comparison git makes after normalising on commit.
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
    with p.open(encoding="utf-8", newline="") as f:  # newline="" keeps \r\n as \r\n
        return f.read()


def write(p: pathlib.Path, s: str) -> None:
    with p.open("w", encoding="utf-8", newline="") as f:  # no platform translation
        f.write(s)


def to_lf(s: str) -> str:
    return s.replace("\r\n", "\n")


def eol_of(html: str) -> str:
    """The line-ending convention a page uses: CRLF if most of its lines end that way, else LF."""
    crlf = html.count("\r\n")
    return "\r\n" if crlf > html.count("\n") - crlf else "\n"


def with_eol(s: str, eol: str) -> str:
    return to_lf(s).replace("\n", eol)


def line_count(block: str) -> int:
    return to_lf(block).count("\n") + 1


def extract(html: str, name: str):
    m = BLOCK_RE.search(html)
    if not m:
        return None
    if BLOCK_RE.search(html, m.end()):
        sys.exit(f"{name}: more than one RMR-RUNLOG block")
    return m.group(0)


def same(a, b) -> bool:
    """Two blocks are the same when their content is, line endings aside."""
    return a is not None and b is not None and to_lf(a) == to_lf(b)


def replace(html: str, block: str, name: str) -> str:
    """html with its block replaced by block (inserted before </body> if it has none),
    the block converted to html's own line-ending convention."""
    eol = eol_of(html)
    block = with_eol(block, eol)
    m = BLOCK_RE.search(html)
    if m:
        return html[: m.start()] + block + html[m.end():]
    i = html.rfind("</body>")
    if i < 0:
        sys.exit(f"{name}: no RMR-RUNLOG block and no </body> to insert before")
    return html[:i] + block + eol + html[i:]


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
        print(f"{CONTROLLER.name}: block written from {a.src} ({line_count(block)} lines)")

    block = extract(ctrl, CONTROLLER.name)
    if block is None:
        sys.exit(f"{CONTROLLER.name}: no RMR-RUNLOG block (the canonical copy)")
    tblock = extract(touch, TOUCH.name)

    if a.check:
        if same(tblock, block):
            print(f"OK: RMR-RUNLOG block identical in {CONTROLLER.name} and {TOUCH.name} ({line_count(block)} lines)")
            return 0
        print(f"DRIFT: the RMR-RUNLOG block in {TOUCH.name} differs from {CONTROLLER.name} — run python tools/sync_runlog.py")
        return 1

    if same(tblock, block):
        print(f"{TOUCH.name}: already in sync")
        return 0
    write(TOUCH, replace(touch, block, TOUCH.name))
    print(f"{TOUCH.name}: RMR-RUNLOG block {'updated' if tblock else 'inserted'} ({line_count(block)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
