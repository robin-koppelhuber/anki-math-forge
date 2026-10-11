"""The find palette, in review: one list for the graph's picker and for finding a card.

A browser test because what matters is what the list does as you type: it
narrows, Enter takes the first row, and a card that is not on the page opens.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="needs the `browser` extra")

from playwright.sync_api import Page, expect

CARD = ".item:not([hidden])"


def open_review(page: Page, live: str, query: str = "status=draft") -> None:
    page.goto(f"{live}/review?project=demo&{query}")
    page.wait_for_selector(f"{CARD} [data-panels]")


def test_slash_opens_it_and_typing_narrows_the_list(page: Page, live) -> None:
    open_review(page, live)
    page.keyboard.press("/")
    expect(page.locator("#finder")).to_be_visible()
    expect(page.locator("#finder-title")).to_have_text("find a card")
    page.wait_for_selector(".find-row")
    everything = page.locator(".find-row").count()

    page.fill("#finder-search", "adjugate")
    page.wait_for_function(
        "n => document.querySelectorAll('.find-row').length < n", arg=everything
    )
    assert page.locator(".find-row").count() >= 1
    assert not page.complaints, page.complaints


def test_enter_takes_the_first_row_and_jumps_to_it(page: Page, live) -> None:
    open_review(page, live)
    page.keyboard.press("/")
    page.fill("#finder-search", "inverse")
    page.wait_for_selector(".find-row")

    page.keyboard.press("Enter")

    expect(page.locator("#finder")).not_to_be_visible()
    assert "inverse" in page.inner_text(f"{CARD} .meta-head").lower() or page.url.endswith(
        page.eval_on_selector(CARD, "e => '#' + e.dataset.uid")
    )


def test_a_card_outside_the_filter_is_opened_by_its_link(page: Page, live) -> None:
    """The list is filtered to one card, and the palette searches the whole
    project: a row for a card not on the page opens by its link."""
    open_review(page, live, "status=all&q=trace")
    assert page.locator("article.item").count() == 1
    page.keyboard.press("/")
    page.fill("#finder-search", "inverse")
    page.wait_for_selector(".find-row")

    page.locator(".find-row").first.click()

    page.wait_for_selector(f"{CARD} [data-panels]")
    assert "q=trace" not in page.url and "#" in page.url, page.url
    assert page.locator("article.item").count() > 1
