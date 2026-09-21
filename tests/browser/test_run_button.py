"""Pressing a run button, in a real browser.

The markup and the endpoint are covered elsewhere. What only a browser can
say is that the click reaches the server, a result lands under the row, and
the page keeps taking keystrokes while the command is still going.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright", reason="needs the `browser` extra")

from playwright.sync_api import Page, expect


def test_a_read_runs_here_and_everything_else_is_still_copied(page: Page, live) -> None:
    """One control per row, which is why the button replaced the copy
    affordance rather than joining it: fourteen shell rows would have
    become twenty-eight controls on the heaviest panel in the app."""
    page.goto(f"{live}/units?project=demo&state=all")

    expect(page.locator("button.run[data-run]").first).to_be_attached()
    expect(page.locator("button.run[data-copy]").first).to_be_attached()
    assert page.locator("button.run[data-run][data-copy]").count() == 0


def test_a_writer_is_never_offered_as_runnable(page: Page, live) -> None:
    """Invariant 1's bargain, as markup: a command that changes something
    is copied and pasted where you can watch it."""
    page.goto(f"{live}/units?project=demo&state=all")

    for handle in page.locator("button.run[data-run]").all():
        line = handle.get_attribute("data-run") or ""
        for writer in ("units extract", "anki push", "anki pull", "zotero import"):
            assert writer not in line, line
    assert page.locator("button.run.claude[data-run]").count() == 0


def test_the_result_lands_under_the_row(page: Page, live) -> None:
    """`forge anki` is the dry run, offered on the review rail. Whether it
    reaches Anki is not the point here and Anki is not running: what the
    panel has to do is come back and say which it was."""
    page.goto(f"{live}/review?project=demo&status=all")

    button = page.locator("button.run[data-run]").first
    button.scroll_into_view_if_needed()
    button.click()

    expect(button.locator("xpath=following-sibling::div[@class='run-result']")).to_contain_text(
        re.compile("ok|failed"), timeout=30_000
    )


def test_the_page_answers_while_a_run_is_in_flight(page: Page, live) -> None:
    """The amendment, in a browser: the deck still takes a keystroke while
    a command is running."""
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator("button.run[data-run]").first.click()

    page.locator("body").press("j")

    expect(page.locator("#position")).to_contain_text("2 /")
