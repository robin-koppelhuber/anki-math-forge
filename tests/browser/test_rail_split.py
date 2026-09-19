"""Dragging the handle at the bottom of each rail.

Whether a grid row follows a pointer is not a property of any string: the
markup can be right, the stylesheet can be right, and the drag can still read
the wrong end of the box and move the panel the other way.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")


def height(page, selector: str) -> float:  # type: ignore[no-untyped-def]
    return page.locator(selector).bounding_box()["height"]


def drag(page, selector: str, dy: int) -> None:  # type: ignore[no-untyped-def]
    """Pointer-drag a handle by `dy`, the way a mouse does it.

    `pointerdown` and friends, not `mouse.move`: the handlers listen for
    pointer events and capture the pointer, and a synthetic mouse drag lands
    on neither.
    """
    box = page.locator(selector).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + dy, steps=8)
    page.mouse.up()


def test_the_commands_panel_follows_the_handle(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Up is bigger. The sized pane is the lower one, so a drag is measured up
    from the bottom of the rail. Read from the top instead, the panel would
    shrink when you pulled it open."""
    page.goto(f"{live}/units?state=all")
    page.wait_for_selector('[data-splitter="commands"]')
    before = height(page, ".rail-actions")

    drag(page, '[data-splitter="commands"]', -120)

    after = height(page, ".rail-actions")
    assert after > before + 40, f"{before} -> {after}"


def test_the_two_rails_drag_the_same_way(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Each rail has one handle between its two panes, and each gives the room
    to the pane the drag moves towards. Here that is the guide's upper pane,
    which is the one with a height on that side."""
    page.goto(f"{live}/units?state=all")
    page.wait_for_selector('[data-splitter="guide"]')
    before = height(page, ".guide-pane.top")

    # Up, not down: at rest the diagram is already as tall as its own content
    # and the handle is near the foot of the window, so growing it is the
    # direction there is no room to test in.
    drag(page, '[data-splitter="guide"]', -120)

    assert height(page, ".guide-pane.top") < before - 40


def test_both_handles_are_on_the_screen(page, live, served) -> None:
    """The guide's was not. `max-content` on its top track is not a cap, so at
    the rail's default width a 950px diagram in a 724px column pushed the
    handle 215px below the bottom of the window, so the one control that
    could have fixed the overflow was the one the overflow put out of reach."""
    page.goto(f"{live}/units?state=all")
    page.wait_for_selector('[data-splitter="guide"]')
    bottom = page.viewport_size["height"]

    for handle in ('[data-splitter="guide"]', '[data-splitter="commands"]'):
        box = page.locator(handle).bounding_box()
        assert 0 < box["y"] < bottom - box["height"], f"{handle} at {box['y']}"


def test_the_split_is_remembered(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Every view here is rendered by the server, so a split that did not
    survive a request would last until the next click."""
    page.goto(f"{live}/units?state=all")
    page.wait_for_selector('[data-splitter="commands"]')
    drag(page, '[data-splitter="commands"]', -100)
    dragged = height(page, ".rail-actions")

    page.goto(f"{live}/units?state=queued")
    page.wait_for_selector('[data-splitter="commands"]')

    assert abs(height(page, ".rail-actions") - dragged) < 12


def test_double_clicking_gives_the_room_back(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Back to no opinion at all: the panel is the height of its commands
    again, not some remembered number."""
    page.goto(f"{live}/units?state=all")
    page.wait_for_selector('[data-splitter="commands"]')
    resting = height(page, ".rail-actions")
    drag(page, '[data-splitter="commands"]', -120)
    assert height(page, ".rail-actions") > resting + 40

    page.dblclick('[data-splitter="commands"]')

    assert abs(height(page, ".rail-actions") - resting) < 12
