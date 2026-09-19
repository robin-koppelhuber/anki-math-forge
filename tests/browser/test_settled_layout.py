"""What the deck looks like once the last card leaves the filter.

A card that no longer matches stays in the deck rather than vanishing, so a
mis-pressed key can be walked back. It gets a banner saying so, prepended to
the card. The card is a three-column grid whose children are placed by order,
so prepending a fourth child shifted every one of them: the body landed in the
18px splitter column and rendered as a ribbon of single letters, and the aside
fell off the end of the grid entirely.

Invisible to every markup test, because the markup was right.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


def a_draft(repo: Path, uid: str) -> str:
    """One draft of our own, so approving it empties the `draft` filter."""
    (repo / "cards" / "demo" / f"{uid}-x.md").write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Demo"\nunit: "demo:1:1"\ngist: the last draft\n---\n\n'
        "## front\n\nWhat is the trace of a product?\n\n"
        "## back\n\n$\\operatorname{tr}(AB) = \\operatorname{tr}(BA)$\n\n"
        "## prose\n\nA sentence long enough that a column eighteen pixels wide "
        "would wrap it to one letter a line, which is what the bug looked "
        "like.\n",
        encoding="utf-8",
    )
    return uid


def box(page, selector: str):  # type: ignore[no-untyped-def]
    found = page.locator(selector)
    assert found.count() == 1, f"{selector}: {found.count()} matches"
    return found.bounding_box()


def test_approving_the_last_card_leaves_the_layout_alone(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The banner goes above the card, not into the column the body was in."""
    _, repo = served
    uid = a_draft(repo, "fee101")
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')
    before = box(page, f'[data-uid="{uid}"] .card-body')

    page.keyboard.press("a")
    page.wait_for_selector(f'[data-uid="{uid}"] .settled')

    after = box(page, f'[data-uid="{uid}"] .card-body')
    assert after["width"] > before["width"] * 0.9, (
        f"the body collapsed from {before['width']} to {after['width']}"
    )
    # The aside is the child that used to fall off the end of the grid.
    aside = box(page, f'[data-uid="{uid}"] aside.meta')
    assert aside["width"] > 100
    assert aside["x"] + aside["width"] <= page.viewport_size["width"] + 1


def test_the_banner_sits_above_the_card_and_spans_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """It is about the whole card, so it reads across the whole card rather
    than as a caption on one column of it."""
    _, repo = served
    uid = a_draft(repo, "fee102")
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    page.keyboard.press("a")
    page.wait_for_selector(f'[data-uid="{uid}"] .settled')

    banner = box(page, f'[data-uid="{uid}"] .settled')
    body = box(page, f'[data-uid="{uid}"] .card-body')
    aside = box(page, f'[data-uid="{uid}"] aside.meta')
    assert banner["y"] + banner["height"] <= body["y"] + 1, "above the body"
    assert banner["width"] > body["width"], "and wider than the body alone"
    assert banner["x"] + banner["width"] >= aside["x"], "reaching across the aside"


def test_the_card_is_still_readable_after_it_settles(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The point of keeping it in the deck is being able to look at it, and
    `z` undoes from here. A ribbon of single letters is not a card you can
    check before deciding whether to undo."""
    _, repo = served
    uid = a_draft(repo, "fee103")
    page.goto(f"{live}/review?project=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    page.keyboard.press("a")
    page.wait_for_selector(f'[data-uid="{uid}"] .settled')

    prose = box(page, f'[data-uid="{uid}"] .sec-prose')
    # One letter a line is about 10px of text in a column of 18. Anything that
    # can hold the sentence is many times that.
    assert prose["width"] > 200, f"prose column is {prose['width']}px wide"
