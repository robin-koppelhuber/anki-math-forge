"""Pressing a run button, in a real browser.

The markup and the endpoint are covered elsewhere. What only a browser can
say is that the click reaches the server, the result reports in a
notification and the runs window and never under the row, and the page
keeps taking keystrokes while the command is still going.
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


def test_the_result_reports_bottom_right_and_never_under_the_row(
    page: Page, live
) -> None:
    """`forge anki` is the dry run, offered on the review rail. Anki is not
    running here, so it fails, and that is fine: what has to happen is a
    notification that says so, and nothing drawn into the list of commands."""
    page.goto(f"{live}/review?project=demo&status=all")

    button = page.locator('button.run[data-effect="reads"]').first
    button.scroll_into_view_if_needed()
    button.click()

    note = page.locator("[data-run-notices] .run-notice").first
    expect(note).to_be_visible()
    expect(note).not_to_have_attribute("data-state", "running", timeout=30_000)
    assert page.locator(".run-result").count() == 0, "nothing under the row"


def test_the_runs_window_lists_runs_and_shows_the_one_you_pick(
    page: Page, live
) -> None:
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator('button.run[data-effect="reads"]').first.click()
    note = page.locator("[data-run-notices] .run-notice").first
    expect(note).not_to_have_attribute("data-state", "running", timeout=30_000)

    note.locator(".run-notice-open").click()

    dialog = page.locator("[data-runs-dialog]")
    expect(dialog).to_be_visible()
    expect(dialog.locator("[data-run-row]").first).to_contain_text("anki")
    detail = dialog.locator("[data-run-detail]")
    expect(detail.locator(".run-summary")).not_to_be_empty()
    expect(detail.locator("[data-run-again]")).to_be_visible()

    # A filter that matches nothing says so rather than leaving a blank.
    dialog.locator("[data-runs-show=running]").click()
    expect(dialog.locator(".runs-none")).to_be_visible()
    dialog.locator("[data-runs-show=all]").click()
    expect(dialog.locator("[data-run-row]").first).to_be_visible()
    assert not page.complaints, page.complaints


def test_clearing_the_window_forgets_what_finished(page: Page, live) -> None:
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator('button.run[data-effect="reads"]').first.click()
    note = page.locator("[data-run-notices] .run-notice").first
    expect(note).not_to_have_attribute("data-state", "running", timeout=30_000)
    note.locator(".run-notice-open").click()

    page.locator("[data-runs-clear]").click()

    expect(page.locator("[data-runs-dialog] [data-run-row]")).to_have_count(0)


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
    assert page.locator("[data-run-notices] .run-notice").count() == 0, "nothing ran"


def test_a_writer_runs_once_you_say_yes(page: Page, live) -> None:
    """Anki is not running here, so the pull fails, and that is fine: what
    has to happen is that it ran, in the background, and came back to say
    how it went."""
    page.goto(f"{live}/review?project=demo&status=all")
    page.on("dialog", lambda dialog: dialog.accept())

    button = page.locator('button.run[data-effect="anki"]').first
    button.scroll_into_view_if_needed()
    button.click()

    note = page.locator("[data-run-notices] .run-notice").first
    expect(note).not_to_have_attribute("data-state", "running", timeout=30_000)
    expect(note.locator(".run-notice-said")).to_have_text(re.compile(r"\S"))


def test_the_builder_says_the_command_and_runs_it(page: Page, live) -> None:
    """Pick an action, read the command it comes to, run it here."""
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator("[data-runs-open]").click()
    dialog = page.locator("[data-runs-dialog]")
    expect(dialog).to_be_visible()

    dialog.locator("[data-builder-pick]").select_option("audit")
    line = dialog.locator("[data-builder-line]")
    expect(line).to_have_text('uv run forge audit --project demo')
    dialog.locator("[data-builder-form] select[name=project]").select_option("")
    expect(line).to_have_text("uv run forge audit")

    dialog.locator("[data-builder-go]").click()
    expect(dialog.locator("[data-run-row]").first).to_contain_text("audit", timeout=30_000)
    assert not page.complaints, page.complaints


def test_a_field_the_action_needs_stops_the_run(page: Page, live) -> None:
    page.goto(f"{live}/review?project=demo&status=all")
    page.locator("[data-runs-open]").click()
    dialog = page.locator("[data-runs-dialog]")
    dialog.locator("[data-builder-pick]").select_option("zotero-new")

    # Not filled in yet: a quiet prompt rather than an error, and no run.
    expect(dialog.locator("[data-builder-line]")).to_have_class(re.compile("missing"))
    expect(dialog.locator("[data-builder-line]")).to_contain_text("needed")
    expect(dialog.locator("[data-builder-go]")).to_be_disabled()


def test_a_quick_pick_opens_in_the_builder_filled_in(page: Page, live) -> None:
    page.goto(f"{live}/review?project=demo&status=all")
    tune = page.locator('[data-tune="anki-push"]').first
    tune.scroll_into_view_if_needed()
    tune.click()

    dialog = page.locator("[data-runs-dialog]")
    expect(dialog).to_be_visible()
    expect(dialog.locator("[data-builder-pick]")).to_have_value("anki-push")
    # The rehearsal opens as the push with test ticked, and a test runs on a click.
    expect(dialog.locator('[data-field="dry_run"] input')).to_be_checked()
    expect(dialog.locator("[data-builder-line]")).to_contain_text("anki push")
    expect(dialog.locator("[data-builder-line]")).to_contain_text("--dry-run")
    expect(dialog.locator("[data-builder-go]")).to_have_text("run")


def test_the_bar_reads_project_setup_runs_graph(page: Page, live) -> None:
    """The same items in the same order on every page: the project, then
    what you do with it."""
    page.goto(f"{live}/review?project=demo&status=all")
    at = [
        page.locator(selector).bounding_box()
        for selector in (
            "#project-pick",
            '#topbar a[aria-label="setup"]',
            "#topbar [data-runs-open]",
            '#topbar a[aria-label="graph"]',
        )
    ]
    assert all(at)
    xs = [box["x"] for box in at if box]
    assert xs == sorted(xs), xs
