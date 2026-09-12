#!/usr/bin/env python
"""Regenerate the images the README points at.

    uv run python assets/make_assets.py            # all of them
    uv run python assets/make_assets.py triage     # just one

Run it after a visible change to the app. The images are committed, so nothing
checks that they still match; this script is what makes bringing them back into
line cheap enough to bother with.

What it writes, all at 2x device pixels so the text is sharp on a normal
display:

    triage.png   a queued unit from a segmented source: the crop with its box
                 drawn on the page, the transcription beside it, the brief
    zotero.png   a unit from a marked-up paper: the highlights painted back
                 onto the page, and what each one says beside it
    review.png   an approved card, with the notes that decided it
    states.png   the state machine, units above and cards below

Two ways of taking a picture, because the subjects differ. The **state
machine** is markup plus CSS with no data in it, so it renders straight from
the app's own Jinja environment into a throwaway page: no server, no source, no
ledger. The **screenshots** are of the running app against real content, so
they start `forge serve` on a spare port and point a headless Chrome at it.

Which source each screenshot uses is worked out from the config rather than
named here, so importing a different paper does not mean editing this file.
`triage` and `review` take the first segmented source. `zotero` takes the
first marked-up source that has **tagged itself `demo`** in its `source.toml`,
and takes none otherwise: that shot is a legible page of whatever you were
reading, and photographing the first Zotero source to hand would republish a
page of somebody's book. `FORGE_ASSET_SOURCE` and `FORGE_ASSET_ZOTERO`
override either. A shot with no source is skipped with a line saying so.

Crops render from the source document, which is gitignored, so the PDF has to
be present locally or the panes come out empty.

Chrome is looked up in the usual install locations; set CHROME to override.

## The demo recording is not made here

By hand, because the interesting part is the pace of triage and no script knows
how long to pause. Roughly 45 seconds:

1. `forge serve`, the units view, one source.
2. Triage six or seven units -- `q`, `q`, `s`, `Q` with a brief typed into the
   prompt. The point is that a decision costs one keystroke.
3. `f` for the rail, copy the `/extract-cards` line.
4. Cut to the review view with cards in it: `a` on one, then an edit in the
   editor, then back to show it has dropped to draft.

Export at 1600x1000 to match the screenshots, and save it as `demo.mp4`.
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
import urllib.parse
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

# Device pixels per CSS pixel. The window size below stays in CSS pixels, so
# raising this sharpens the text without reflowing anything. A 1x screenshot of
# a UI this dense reads as blurry the moment anyone opens it full width.
SCALE = 2

VIEW = (1600, 1000)


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


def chrome(*args: str) -> list[str]:
    return [find_chrome(), "--headless=new", "--disable-gpu", *args]


def shoot(url: str, out: Path, width: int, height: int, *, scale: int, wait_ms: int = 4000) -> None:
    """One headless screenshot. `wait_ms` is virtual time, not wall clock."""
    subprocess.run(
        chrome(
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale}",
            f"--virtual-time-budget={wait_ms}",
            f"--screenshot={out}",
            url,
        ),
        check=True,
        capture_output=True,
    )
    if not out.exists():
        sys.exit(f"Chrome wrote nothing for {url}")
    print(
        f"  {out.relative_to(ROOT)}  {width * scale}x{height * scale}, "
        f"{out.stat().st_size // 1024} KB"
    )


def measure(url: str, width: int) -> int:
    """The rendered height of a page that reports it in its own title.

    At scale 1 deliberately: the window size is in CSS pixels either way, so a
    scaled render here would measure the same number more slowly.
    """
    dom = subprocess.run(
        chrome(f"--window-size={width},2000", "--virtual-time-budget=1500", "--dump-dom", url),
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout
    match = re.search(r"<title>h(\d+)</title>", dom)
    return int(match.group(1)) if match else 1400


# -- the state machine, with no server involved -----------------------------

# The diagram is `.fsm` in the stylesheet and depends on no ancestor, so a bare
# page carrying the same stylesheet renders it exactly as the guide does. The
# width is fixed here rather than inherited from a rail, which is the one thing
# that differs: in the app it is whatever you dragged the guide to.
#
# The trailing script is how the page gets cropped to its content. Chrome's
# `--screenshot` captures the window, not the document, so a fixed height
# either clips the diagram or leaves a field of background under it.
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


def render_states(out: Path, width: int, scale: int) -> None:
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
    shoot(page.as_uri(), out, window, measure(page.as_uri(), window), scale=scale, wait_ms=1500)
    shutil.rmtree(scratch, ignore_errors=True)


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


# Which state to photograph, best first. `skipped` is last because a column of
# things you decided against is the least interesting picture of triage there
# is, and `carded` sits above it only because it at least shows a finished one.
TRIAGE_STATES = ("queued", "new", "carded", "skipped")

SHOTS = ("triage", "zotero", "review", "states")


def urls() -> dict[str, str]:
    """One URL per screenshot, resolved against whatever sources exist.

    Named sources would go stale the first time a paper is imported or
    dropped, and a screenshot of an empty deck is worse than none at all: it
    looks like the feature does not work.
    """
    from anki_math_forge.app import source_origin
    from anki_math_forge.config import load
    from anki_math_forge.ledger import open_ledgers

    config = load(ROOT)
    ledgers = open_ledgers(config.sources_dir)

    def candidates(marked_up: bool) -> list[str]:
        return [
            name
            for name in config.sources
            if (source_origin(config, name) == "zotero") is marked_up and ledgers.get(name)
        ]

    def tagged_demo(name: str) -> bool:
        spec = config.sources.get(name)
        return bool(spec and "demo" in spec.tags)

    def state_of(source: str) -> str:
        present = {u.state for u in ledgers.get(source, ())}
        return next((s for s in TRIAGE_STATES if s in present), "all")

    def units(source: str) -> str:
        return "/units?" + urllib.parse.urlencode(
            {"source": source, "state": state_of(source)}
        )

    out: dict[str, str] = {}
    segmented = os.environ.get("FORGE_ASSET_SOURCE", "") or next(iter(candidates(False)), "")
    if segmented:
        out["triage"] = units(segmented)
        # A repo that has approved nothing yet still gets a picture rather than
        # an empty column.
        approved = any(
            "status: approved" in c.read_text(encoding="utf-8")
            for c in (config.cards_dir / segmented).glob("*.md")
        )
        out["review"] = "/review?" + urllib.parse.urlencode(
            {"source": segmented, "status": "approved" if approved else "all"}
        )
    # The marked-up shot is opt-in, and that is the whole point of it. This
    # screenshot is a legible page of whatever you were reading, so taking it
    # of the first Zotero source to hand republishes a page of somebody's book
    # in the README -- the same thing the text layers were pulled out of git
    # for. A source says it is fine to photograph by tagging itself `demo`.
    marked = os.environ.get("FORGE_ASSET_ZOTERO", "") or next(
        (name for name in candidates(True) if tagged_demo(name)), ""
    )
    if marked:
        out["zotero"] = units(marked)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate the README's images.")
    ap.add_argument("only", nargs="*", help=f"{', '.join(SHOTS)}; default all")
    ap.add_argument("--width", type=int, default=820, help="state diagram width, CSS px")
    ap.add_argument("--scale", type=int, default=SCALE, help="device pixels per CSS pixel")
    args = ap.parse_args()

    wanted = set(args.only) or set(SHOTS)
    if unknown := wanted - set(SHOTS):
        sys.exit(f"no such asset: {', '.join(sorted(unknown))}")

    if "states" in wanted:
        print("state machine:")
        render_states(HERE / "states.png", args.width, args.scale)

    live = urls()
    why = {
        "zotero": "no marked-up source is tagged `demo` — skipped, so the README "
        "does not end up carrying a page of somebody's book",
    }
    for name in sorted((wanted - {"states"}) - set(live)):
        print(f"  {name}: {why.get(name, 'no source for it yet — skipped')}")

    if todo := sorted(wanted & set(live)):
        print("app screenshots:")
        with Serving() as server:
            for name in todo:
                shoot(server.base + live[name], HERE / f"{name}.png", *VIEW, scale=args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
