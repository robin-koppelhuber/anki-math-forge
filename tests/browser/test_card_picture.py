"""A card that carries a picture, in a real browser.

`tests/test_card_image.py` already pins the parts a string can answer: what
the reference parses to, what `check` refuses, what `sync` uploads, and that
the rendered markup carries an `<img class="card-image">`. None of that says
the picture arrives. There is no image file anywhere (invariant 3): the
reference names a unit and the crop is drawn from the source PDF per request,
so between the markup and a figure on screen sit a URL, an HTTP round trip and
a stylesheet. This file is the part only a browser can answer: the request the
browser actually makes, bytes that decode to an image, and a figure that does
not push the answer off the screen.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from anki_math_forge.extract.render import CARD_INSET
from conftest import build_pdf

ROOT = Path(__file__).resolve().parents[2]

# A PDF-backed source, which the shared fixture has none of. `[projects.demo]`
# there is a `.tex`, and a `.tex` has geometry for nothing.
CONFIG = (
    '[repo]\ncards_dir = "cards"\nprojects_dir = "projects"\n\n'
    "[cards]\n\n"
    '[projects.book]\ntitle = "A Book"\ncitation = "Book"\n'
    '\n[[projects.book.sources]]\nfiles = ["projects/book/book.pdf"]\n'
)

HEAD = (
    "---\nuid: {uid}\ntype: identity\nstatus: draft\n"
    'source: "A Book"\nunit: "{unit}"\ngist: {gist}\n---\n\n'
)


def lay_out(repo: Path) -> None:
    """Write the config, the PDF, the ledger and an empty deck."""
    (repo / "forge.toml").write_text(CONFIG, encoding="utf-8")
    source = repo / "projects" / "book"
    source.mkdir(parents=True, exist_ok=True)
    pdf = source / "book.pdf"
    if not pdf.exists():
        build_pdf(pdf)
    cards = repo / "cards" / "book"
    cards.mkdir(parents=True, exist_ok=True)
    for stale in cards.glob("*.md"):
        stale.unlink()
    if not (source / "units.jsonl").exists():
        _extract(repo)


def _extract(repo: Path) -> None:
    """`forge extract`, in-process, for units that carry real geometry."""
    from anki_math_forge import config as config_mod
    from anki_math_forge import extract

    extract.run(config_mod.load(repo), "book")


def a_unit(repo: Path) -> str:
    """The id of the first extracted unit, which has a page and a box."""
    line = (repo / "projects" / "book" / "units.jsonl").read_text(encoding="utf-8")
    return str(json.loads(line.splitlines()[0])["id"])


def a_card(repo: Path, uid: str, front: str, *, gist: str = "a card") -> str:
    """One draft card under the PDF-backed source. Returns its uid."""
    unit = a_unit(repo)
    (repo / "cards" / "book" / f"{uid}-x.md").write_text(
        HEAD.format(uid=uid, unit=unit, gist=gist)
        + f"## front\n\n{front}\n\n## back\n\n$\\det(AB)=\\det A\\det B$\n",
        encoding="utf-8",
    )
    return uid


def show(page, live: str, uid: str):  # type: ignore[no-untyped-def]
    """Open the deck on one card. The deck shows one at a time."""
    page.goto(f"{live}/review?project=book&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')
    return page.locator(f'[data-uid="{uid}"]')


def loaded(page, uid: str) -> None:  # type: ignore[no-untyped-def]
    """Wait for the browser to be done with the picture, one way or another."""
    page.wait_for_function(
        """uid => {
            const img = document.querySelector(`[data-uid="${uid}"] .card-image`);
            return img && img.complete;
        }""",
        arg=uid,
    )


# -- a server of this module's own ------------------------------------------
#
# The app reads `forge.toml` once, when the process starts, so a source added
# to the file afterwards is a source the running server has never heard of and
# every crop from it answers 409. A PDF-backed source therefore has to be on
# disk before uvicorn is launched, which the session fixture in `conftest.py`
# cannot do for us. `served` and `live` below override it for this module
# only; `browser` and `page` still come from there, which is where the console
# complaints are collected.


def spare_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    repo = tmp_path_factory.mktemp("pictures")
    lay_out(repo)

    port = spare_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--port", str(port), "--factory", "conftest:_app"],
        cwd=Path(__file__).parent,
        env={
            **os.environ,
            "FORGE_TEST_REPO": str(repo),
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONIOENCODING": "utf-8",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"{base}/api/counts", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            pytest.fail("the test server never came up")
        yield base, repo
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def live(served: tuple[str, Path]) -> str:
    base, repo = served
    lay_out(repo)
    return base


# -- what reaches the screen ------------------------------------------------


def test_the_reference_becomes_a_picture_and_not_a_line_of_markdown(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The reference is markdown in a file, and a card is reviewed on screen.
    Left unrendered it reads as a card whose answer is a broken link, and
    nothing about the card file would look wrong."""
    _, repo = served
    uid = a_card(repo, "c10a01", f"![the figure](unit:{a_unit(repo)})\n\nwhat is this")

    card = show(page, live, uid)

    assert card.locator("img.card-image").count() == 1
    body = card.locator(".card-body").inner_text()
    assert "![" not in body and "unit:" not in body, body


def test_the_browser_asks_for_the_picture_sync_will_upload(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """What you approve on screen has to be what Anki gets, and the two sides
    build their URLs in different places. `marks=false` is the one that bites:
    a unit that came from an image annotation has that annotation as its own
    boundary, so painting it back draws a coloured frame round the figure."""
    _, repo = served
    uid = a_card(repo, "c10a02", f"![the figure](unit:{a_unit(repo)})")
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if "/crop/" in r.url else None)

    card = show(page, live, uid)
    loaded(page, uid)

    # The aside asks for a crop of its own, framed for triage, off the same
    # unit. What is under test is the one the card body asked for.
    src = card.locator(".card-image").get_attribute("src")
    assert [url for url in asked if url.endswith(src)], (src, asked)
    assert "marks=false" in src
    assert f"context=-{CARD_INSET:g}" in src
    assert "width=" not in src, "the config decides that, the same way for both"


def test_the_picture_is_really_an_image(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """There is no image file to check: the crop is drawn from the PDF while
    the page is loading it. A 404, a 409 or a rendering that raised all look
    the same in the markup, and the browser is the only thing that will say
    whether what came back decodes."""
    _, repo = served
    uid = a_card(repo, "c10a03", f"![the figure](unit:{a_unit(repo)})")
    answers: dict[str, tuple[int, str]] = {}
    page.on(
        "response",
        lambda r: answers.__setitem__(r.url, (r.status, r.header_value("content-type") or ""))
        if "/crop/" in r.url
        else None,
    )

    card = show(page, live, uid)
    loaded(page, uid)

    picture = card.locator(".card-image")
    src = picture.get_attribute("src")
    answer = next(v for url, v in answers.items() if url.endswith(src))
    assert answer == (200, "image/png"), answer
    size = picture.evaluate("img => [img.naturalWidth, img.naturalHeight]")
    assert size[0] > 0 and size[1] > 0, size


def test_the_badge_is_on_the_card_that_has_one(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A label, not a filter: while you review a card it says that `sync` has
    a crop to render and upload before this one can go. On a card with no
    picture it would be a claim about work that does not exist."""
    _, repo = served
    with_picture = a_card(repo, "c10a04", f"![the figure](unit:{a_unit(repo)})")
    without = a_card(repo, "c10a05", "$\\operatorname{tr}(AB)$")

    assert show(page, live, with_picture).locator(".badge.image").count() == 1
    assert show(page, live, without).locator(".badge.image").count() == 0


def test_the_picture_leaves_room_for_the_answer(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A crop off a page is usually wider than it is tall and arrives at
    whatever size the renderer chose. Uncapped it filled the column and pushed
    the answer below the fold, so the card you approved was one you had to
    scroll to read. The stylesheet caps it; this is the cap doing its job in a
    browser, which is the only place a cap means anything."""
    _, repo = served
    uid = a_card(repo, "c10a06", f"![the figure](unit:{a_unit(repo)})\n\nwhat is this")

    card = show(page, live, uid)
    loaded(page, uid)

    image = card.locator(".card-image")
    picture = image.bounding_box()
    column = card.locator(".card-body").bounding_box()
    height = page.viewport_size["height"]
    # A floor as well as the bounds below, which a picture scaled to nothing
    # would satisfy every one of.
    assert picture["width"] > 200 and picture["height"] > 20, picture
    assert picture["x"] >= column["x"] - 1
    assert picture["x"] + picture["width"] <= column["x"] + column["width"] + 1
    # No sideways scroll anywhere on the page, the other way an oversized crop
    # shows up.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # The cap itself, resolved. This crop is wider than it is tall and would
    # fit whatever the rule said, and a figure that is taller than the pane is
    # the case the cap is there for.
    cap = image.evaluate("img => parseFloat(getComputedStyle(img).maxHeight)")
    assert cap <= 0.5 * height, cap
    answer = card.locator(".sec-back").bounding_box()
    assert answer["y"] + answer["height"] <= height, "the answer is below the fold"


def test_a_picture_that_cannot_be_drawn_leaves_the_page_readable(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """`check` refuses such a card, so it never reaches Anki, but it is a
    draft on screen for as long as it takes to fix, and that is exactly when
    you need to read it. A 404 on the crop is an image the browser could not
    load, not a page that stopped working."""
    _, repo = served
    uid = a_card(repo, "c10a07", "![the figure](unit:book:404:1)")

    card = show(page, live, uid)
    loaded(page, uid)

    assert [c for c in page.complaints if "pageerror" in c] == [], page.complaints
    assert card.locator("img.card-image").count() == 1
    assert "det" in card.locator(".sec-back").inner_text()
