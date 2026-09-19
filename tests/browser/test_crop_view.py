"""Opening the source crop.

A crop cut to page width is unreadable in a 240px aside, which is every crop
from a marked-up source: invariant 8 cuts those to the page, because a mark's
left and right edges are wherever a sentence happened to start and stop. The
picture being *there* and not readable is the thing this fixes, and whether a
click opens a dialog is exactly what markup tests cannot say.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


def a_crop(repo: Path) -> str:
    """Give the demo source one unit with geometry, and a card that names it.

    The deck this fixture lays out comes from a `.tex` source, which has no
    geometry for anything, so nothing in it has a crop to open. The image
    itself 404s here (there is no PDF behind it) and that is fine: what is
    under test is the control and the dialog, not the renderer, which
    `test_app.py` covers against a real document.
    """
    unit = {
        "id": "demo:9:1",
        "locator": {"section": "9", "equation": 1, "page": 1, "bbox": [10, 10, 200, 60]},
        "state": "carded",
    }
    ledger = repo / "projects" / "demo" / "units.jsonl"
    with ledger.open("a", encoding="utf-8") as out:
        out.write(json.dumps(unit) + "\n")
    card = repo / "cards" / "demo" / "zzcrop-x.md"
    card.write_text(
        "---\nuid: zzcrop\ntype: identity\nstatus: draft\n"
        'source: "Demo"\nunit: "demo:9:1"\ngist: a card with a crop\n---\n\n'
        "## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )
    return "zzcrop"


def test_clicking_the_crop_opens_it_full_size(page, live, served) -> None:  # type: ignore[no-untyped-def]
    _, repo = served
    uid = a_crop(repo)
    # The deck shows one card at a time, and the fragment is how a link
    # from elsewhere lands on a particular one.
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    opener = page.locator(f'[data-uid="{uid}"] .crop-open')
    assert opener.count() == 1, "the thumbnail should be the control"
    assert not page.locator("#crop-view").evaluate("d => d.open")

    opener.click()

    dialog = page.locator("#crop-view")
    assert dialog.evaluate("d => d.open"), "clicking the crop opens the dialog"
    assert "demo:9:1" in page.locator("#crop-unit").inner_text()
    assert "/crop/demo/" in page.locator("#crop-view-image").get_attribute("src")


def test_what_opens_is_the_picture_already_on_screen(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The aside shows the crop triage showed, so the dialog is the same image
    at full size rather than a second framing of the same unit. One URL means
    opening it is a cache hit: the picture is there before the dialog has
    finished growing, and there is no 4ms render on a click."""
    _, repo = served
    uid = a_crop(repo)
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')
    opener = page.locator(f'[data-uid="{uid}"] .crop-open')
    thumbnail = opener.locator("img").get_attribute("src")

    opener.click()

    opened = page.locator("#crop-view-image").get_attribute("src")
    assert opened == thumbnail
    # And it is the triage framing, not the bare box.
    assert "context=" in opened and "outline=1" in opened


def test_it_opens_on_an_approved_card_too(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The crop is evidence for "is this card right", which is a question you
    ask hardest about the ones you already approved."""
    _, repo = served
    uid = a_crop(repo)
    card = repo / "cards" / "demo" / f"{uid}-x.md"
    card.write_text(
        card.read_text(encoding="utf-8").replace("status: draft", "status: approved"),
        encoding="utf-8",
    )
    page.goto(f"{live}/review?project=demo&status=all#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    page.locator(f'[data-uid="{uid}"] .crop-open').click()

    assert page.locator("#crop-view").evaluate("d => d.open")
    # The image itself answers 409 here: crops are rendered from the source
    # document on demand and this fixture has none. What must be silent is the
    # script, because a handler that throws is the way this control fails
    # without looking broken.
    assert [c for c in page.complaints if "pageerror" in c] == [], page.complaints


def test_escape_closes_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """It is a dialog, so the browser already does this. The test is that
    nothing on the page has taken the key away from it: any open dialog owns
    the keyboard here, and `esc` used to reach the deck underneath."""
    _, repo = served
    uid = a_crop(repo)
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')
    page.locator(f'[data-uid="{uid}"] .crop-open').click()

    page.keyboard.press("Escape")

    assert not page.locator("#crop-view").evaluate("d => d.open")
