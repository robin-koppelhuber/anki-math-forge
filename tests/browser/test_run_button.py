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


def test_a_shell_command_runs_here_and_a_slash_command_is_copied(
    page: Page, live
) -> None:
    """One control per row, which is why the button replaced the copy
    affordance rather than joining it: fourteen shell rows would have
    become twenty-eight controls on the heaviest panel in the app."""
    page.goto(f"{live}/units?project=demo&state=all")

    expect(page.locator("button.run[data-run]").first).to_be_attached()
    expect(page.locator("button.run.claude[data-copy]").first).to_be_attached()
    assert page.locator("button.run[data-run][data-copy]").count() == 0


def test_a_slash_command_is_never_runnable(page: Page, live) -> None:
    """Invariant 1's bargain, as markup: a model in the loop is pasted
    where you can watch it."""
    page.goto(f"{live}/units?project=demo&state=all")

    assert page.locator("button.run.claude[data-run]").count() == 0


def test_every_writer_carries_what_it_changes(page: Page, live) -> None:
    """The page asks before running one of these, and it can only ask
    about what it was told."""
    page.goto(f"{live}/setup?project=demo")

    for handle in page.locator("button.run[data-run]").all():
        assert handle.get_attribute("data-effect") in ("reads", "repo", "anki")


def test_the_result_lands_under_the_row(page: Page, live) -> None:
    """`forge anki` is the dry run, offered on the review rail. Whether it
    reaches Anki is not the point here and Anki is not running: what the
    panel has to do is come back and say which it was."""
    page.goto(f"{live}/review?project=demo&status=all")

    button = page.locator('button.run[data-effect="reads"]').first
    button.scroll_into_view_if_needed()
    button.click()

    expect(button.locator("xpath=following-sibling::div[@class='run-result']")).to_contain_text(
        re.compile("ok|failed"), timeout=30_000
    )


def test_the_page_answers_while_a_run_is_in_flight(page: Page, live) -> None:
    """The amendment, in a browser: the deck still takes a keystroke while
    a command is running."""
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator('button.run[data-effect="reads"]').first.click()

    page.locator("body").press("j")

    expect(page.locator("#position")).to_contain_text("2 /")


def test_a_writer_asks_first_and_does_nothing_if_you_say_no(page: Page, live) -> None:
    """The dialog names what it changes. Dismissing it is the whole of
    saying no: nothing is posted, so nothing runs."""
    page.goto(f"{live}/review?project=demo&status=all")
    asked: list[str] = []

    def refuse(dialog) -> None:  # type: ignore[no-untyped-def]
        asked.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", refuse)
    button = page.locator('button.run[data-effect="anki"]').first
    button.scroll_into_view_if_needed()
    button.click()

    assert asked and "Anki collection" in asked[0], "it said what it would change"
    assert button.locator("xpath=following-sibling::div[@class='run-result']").count() == 0


def test_a_writer_runs_once_you_say_yes(page: Page, live) -> None:
    """Anki is not running here, so the pull fails, and that is fine: what
    has to happen is that it ran, in the background, and came back to say
    how it went."""
    page.goto(f"{live}/review?project=demo&status=all")
    page.on("dialog", lambda dialog: dialog.accept())

    button = page.locator('button.run[data-effect="anki"]').first
    button.scroll_into_view_if_needed()
    button.click()

    expect(button.locator("xpath=following-sibling::div[@class='run-result']")).to_contain_text(
        re.compile("ok|failed"), timeout=30_000
    )
