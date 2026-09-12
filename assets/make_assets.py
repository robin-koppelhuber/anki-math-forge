#!/usr/bin/env python
"""Regenerate the images the README points at.

    uv run python assets/make_assets.py            # all of them
    uv run python assets/make_assets.py triage     # just one

Run it after a UI change. The images are committed, so nothing checks that
they still match the app; this script is what makes bringing them back into
line cheap enough to bother with.

Two ways of taking a picture, because the subjects differ:

* The **state machine** is markup plus CSS with no data in it, so it renders
  straight from the app's own Jinja environment into a throwaway page. No
  server, no source, no ledger.
* The **screenshots** are of the running app against real content, so they
  start `forge serve` on a spare port and point a headless Chrome at it.

Chrome is looked up in the usual install locations; set CHROME to override.
The demo recording is not made here -- see README.md in this folder.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def find_chrome() -> str:
    override = os.environ.get("CHROME")
    if override:
        return override
    for name in ("google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    sys.exit("no Chrome found. Install it, or set CHROME to the binary.")


def shoot(url: str, out: Path, width: int, height: int, *, wait_ms: int = 4000) -> None:
    """One headless screenshot. `wait_ms` is virtual time, not wall clock."""
    subprocess.run(
        [
            find_chrome(),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}",
            f"--screenshot={out}",
            url,
        ],
        check=True,
        capture_output=True,
    )
    if not out.exists():
        sys.exit(f"Chrome wrote nothing for {url}")
    print(f"  {out.relative_to(ROOT)}  ({out.stat().st_size // 1024} KB)")


# -- the state machine, with no server involved -----------------------------

# The diagram is `.fsm` in the stylesheet and depends on no ancestor, so a bare
# page carrying the same stylesheet renders it exactly as the guide does. The
# width is fixed here rather than inherited from a rail, which is the one thing
# that differs: in the app it is whatever you dragged the guide to.
#
# The trailing script is how the page gets cropped to its content. Chrome's
# `--screenshot` captures the window, not the document, so a fixed height
# either clips the diagram or leaves a field of background under it. Measuring
# means one extra run: `--dump-dom` reads the height back out of the title,
# and the real screenshot uses it.
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="app.css">
<style>
  body {{ margin: 0; padding: 28px; background: var(--bg); }}
  .wrap {{ width: {width}px; margin: 0 auto; }}
</style>
</head><body><div class="wrap">{body}</div>
<script>document.title = "h" + Math.ceil(
  document.querySelector(".wrap").getBoundingClientRect().bottom + 28);</script>
</body></html>
"""


def render_states(out: Path, width: int) -> None:
    from jinja2 import Environment, FileSystemLoader

    from anki_math_forge.app import TEMPLATES, source_facts
    from anki_math_forge.config import load

    config = load(ROOT)
    source = next(iter(config.sources), "")
    facts = source_facts(config, source) if source else {"origin": "", "units_from": []}

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    body = env.get_template("_fsm.html").render(sf=facts)

    # Chrome needs the stylesheet on disk beside the page; a file:// URL will
    # not reach the running app's /static.
    scratch = HERE / ".scratch"
    scratch.mkdir(exist_ok=True)
    shutil.copy(TEMPLATES.parent / "static" / "app.css", scratch / "app.css")
    page = scratch / "states.html"
    page.write_text(PAGE.format(width=width, body=body), encoding="utf-8")

    window = width + 56
    shoot(page.as_uri(), out, window, measure(page.as_uri(), window), wait_ms=1500)
    shutil.rmtree(scratch, ignore_errors=True)


def measure(url: str, width: int) -> int:
    """The rendered height of a page that reports it in its own title."""
    dom = subprocess.run(
        [
            find_chrome(),
            "--headless=new",
            "--disable-gpu",
            f"--window-size={width},2000",
            "--virtual-time-budget=1500",
            "--dump-dom",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    match = re.search(r"<title>h(\d+)</title>", dom)
    return int(match.group(1)) if match else 1400


# -- the app, against real content ------------------------------------------


def spare_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(url: str, timeout: float = 40.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    sys.exit(f"{url} never came up")


class Serving:
    """`forge serve` on a spare port, stopped on the way out."""

    def __init__(self) -> None:
        self.port = spare_port()
        self.base = f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> Serving:
        self.proc = subprocess.Popen(
            ["uv", "run", "forge", "serve", "--port", str(self.port)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for(f"{self.base}/api/counts")
        return self

    def __exit__(self, *_: object) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# The README's screenshots want a source with something in every state, which
# is the Cookbook. Override with FORGE_ASSET_SOURCE if that stops being true.
SOURCE = os.environ.get("FORGE_ASSET_SOURCE", "matrix-cookbook")

SHOTS = {
    "triage": (f"/units?source={SOURCE}&state=queued", 1600, 1000),
    "review": (f"/review?source={SOURCE}&status=approved", 1600, 1000),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("only", nargs="*", help="triage, review, states; default all")
    ap.add_argument("--width", type=int, default=820, help="state diagram width")
    args = ap.parse_args()

    wanted = set(args.only) or {"triage", "review", "states"}
    unknown = wanted - set(SHOTS) - {"states"}
    if unknown:
        return sys.exit(f"no such asset: {', '.join(sorted(unknown))}")

    if "states" in wanted:
        print("state machine:")
        render_states(HERE / "states.png", args.width)

    live = wanted & set(SHOTS)
    if live:
        print("app screenshots:")
        with Serving() as server:
            for name in sorted(live):
                path, width, height = SHOTS[name]
                shoot(server.base + path, HERE / f"{name}.png", width, height)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
