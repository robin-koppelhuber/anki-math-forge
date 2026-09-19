"""The context chip on the triage view, from the click to the line on disk.

One of the sizes is the word `chapter` rather than a count, and everything
between the button and `units.jsonl` is a place that can quietly turn a word
into a number. The click handler did: `Number("chapter")` is NaN, a NaN posted
as JSON is `null`, and the server reads a missing size as "take the override
off", so picking `chapter` cleared the setting instead of storing it. Nothing
short of a real browser sees that, because every layer on its own is right.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The three units `conftest.lay_out` extracts from the demo document. Named
# here because the tests need two of them at once: one to set a size on, one to
# check nothing spilled onto.
FIRST = "demo:1:1"
SECOND = "demo:1.1:2"

# `CONTEXT_STEPS`, in the order the chip prints them and `c` walks them.
STEPS: tuple[int | str, ...] = (0, 1, 3, 10, "chapter", 999)

# No `context_pages` on the line means the unit has no opinion and takes the
# source's. The ledger leaves the key out rather than writing a null.
INHERIT = "inherit"

# What the chip says when a size is the one in force. Every other step is
# printed bare, which is what makes the row read as a sentence.
CHOSEN = {
    0: "this page only",
    1: "1 page either side",
    3: "3 pages either side",
    10: "10 pages either side",
    "chapter": "the chapter it is in",
    999: "the whole document",
}
BARE = {0: "0", 1: "1", 3: "3", 10: "10", "chapter": "chapter", 999: "all"}


def size_of(repo: Path, unit_id: str) -> int | str:
    """What `units.jsonl` says this unit's window is.

    Retried, because the ledger is written atomically: the server writes a
    temporary file and renames it over this one, and on Windows a read that
    lands in that instant gets a `PermissionError` rather than either version
    of the file. Polling a file somebody else is replacing is the one place
    that shows up, and it is the harness racing the server, not a fault in
    either.
    """
    ledger = repo / "projects" / "demo" / "units.jsonl"
    for attempt in range(10):
        try:
            text = ledger.read_text(encoding="utf-8")
            break
        except (PermissionError, OSError):
            if attempt == 9:
                raise
            time.sleep(0.05)
    for line in text.splitlines():
        row = json.loads(line)
        if row.get("id") == unit_id:
            return row.get("context_pages", INHERIT)
    raise AssertionError(f"no unit {unit_id!r} in the ledger")


def written(page, repo: Path, unit_id: str, want: int | str) -> int | str:  # type: ignore[no-untyped-def]
    """The size on disk once the write has had time to land.

    Polled rather than slept through, so a run costs one round trip per size
    instead of a fixed wait per size, and a failure reports the value that was
    actually there.
    """
    for _ in range(20):
        if size_of(repo, unit_id) == want:
            break
        page.wait_for_timeout(150)
    return size_of(repo, unit_id)


def settled(page, unit_id: str, want: int | str) -> None:  # type: ignore[no-untyped-def]
    """Wait until the chip itself says `want` is the size in force.

    The file is not enough. `c` picks the next step by reading which one is
    marked `on`, and that mark is painted from the server's answer, so a press
    that lands before the repaint cycles from the step *before* the one just
    written and the walk stands still.
    """
    page.wait_for_selector(
        f'[data-id="{unit_id}"] [data-context-step="{want}"].on', timeout=5000
    )


def open_triage(page, live: str, unit_id: str = FIRST) -> None:  # type: ignore[no-untyped-def]
    """The triage view with `unit_id` the one on screen.

    The deck shows one unit at a time and the keys act on that one, so which
    unit is current is part of the setup and not a detail.
    """
    page.goto(f"{live}/units#{unit_id}")
    page.wait_for_selector(f'[data-id="{unit_id}"]:not([hidden]) [data-context-chip]')


def pick(page, unit_id: str, step: int | str) -> None:  # type: ignore[no-untyped-def]
    """Click one size on one unit's chip."""
    page.click(f'[data-id="{unit_id}"] [data-context-step="{step}"]')


def chip_labels(page, unit_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    """The six buttons as they read right now, in order."""
    buttons = page.locator(f'[data-id="{unit_id}"] [data-context-step]')
    return [(buttons.nth(i).text_content() or "").strip() for i in range(buttons.count())]


def whose(page, unit_id: str) -> str:  # type: ignore[no-untyped-def]
    """`source` or `this unit`: who the size in force belongs to."""
    label = page.locator(f'[data-id="{unit_id}"] [data-context-chip] .chip-whose')
    return (label.text_content() or "").strip()


def test_clicking_a_size_writes_that_size(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Every step including `chapter`, because `chapter` is the one that used
    to arrive at the server as nothing at all and take the override off. A test
    over the numbers alone passes against the bug."""
    _, repo = served
    open_triage(page, live)

    for step in STEPS:
        pick(page, FIRST, step)
        assert written(page, repo, FIRST, step) == step, f"clicking {step!r}"


def test_the_c_key_walks_every_size(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The key is the other door to the same write, and it had the same bug to
    avoid: it too has to send the step verbatim rather than as a number. The
    chip starts on the source's size, so one press per step returns to it."""
    _, repo = served
    open_triage(page, live)
    assert size_of(repo, FIRST) == INHERIT, "the fixture's units carry no size"

    # From the source default of 1, so the walk is 3, 10, chapter, 999, 0 and
    # back to 1. Six presses, one full lap.
    expected = [3, 10, "chapter", 999, 0, 1]
    for step in expected:
        page.keyboard.press("c")
        assert written(page, repo, FIRST, step) == step, f"cycling to {step!r}"
        settled(page, FIRST, step)


def test_the_chip_repaints_from_what_the_server_sent(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The chip's job is to say which size is in force and whose it is, and the
    only thing that knows both is the file that was just written. Painting the
    click instead would leave a chip that agrees with the last button pressed
    rather than with the ledger."""
    _, repo = served
    open_triage(page, live)
    assert whose(page, FIRST) == "project"

    pick(page, FIRST, "chapter")
    assert written(page, repo, FIRST, "chapter") == "chapter"

    assert chip_labels(page, FIRST) == [
        BARE[0],
        BARE[1],
        BARE[3],
        BARE[10],
        CHOSEN["chapter"],
        BARE[999],
    ]
    assert whose(page, FIRST) == "this unit"

    # And the other direction: a second pick moves the written-out label, it
    # does not add one.
    pick(page, FIRST, 999)
    assert written(page, repo, FIRST, 999) == 999
    assert chip_labels(page, FIRST) == [
        BARE[0],
        BARE[1],
        BARE[3],
        BARE[10],
        BARE["chapter"],
        CHOSEN[999],
    ]


def test_undo_puts_the_previous_size_back(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A write that leaves the undo stack alone is worse than one that cannot
    be undone: `z` steps over it to an older action, which is very likely a
    different unit.

    The chip has to follow the file. It did not: `undo` repainted the state
    badge and nothing else, so the window went back on disk while the chip
    went on showing the size you had just undone.
    """
    _, repo = served
    open_triage(page, live)

    pick(page, FIRST, "chapter")
    assert written(page, repo, FIRST, "chapter") == "chapter"
    pick(page, FIRST, 999)
    assert written(page, repo, FIRST, 999) == 999

    page.keyboard.press("z")

    assert written(page, repo, FIRST, "chapter") == "chapter"
    settled(page, FIRST, "chapter")


def test_one_unit_at_a_time(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The size is a decision about this unit, taken while looking at it. The
    id travels in the URL of the write, so a chip that posted the deck's
    current unit rather than its own would be invisible until a reload."""
    _, repo = served
    open_triage(page, live, SECOND)

    pick(page, SECOND, 10)
    assert written(page, repo, SECOND, 10) == 10

    assert size_of(repo, FIRST) == INHERIT


def test_the_size_survives_a_reload(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The chip after a write is painted by the script and the chip after a
    load is painted by the template, and the two have to agree. They are
    separate renderers of the same payload, so only a reload shows the server
    reading back what the browser wrote."""
    _, repo = served
    open_triage(page, live, SECOND)

    pick(page, SECOND, "chapter")
    assert written(page, repo, SECOND, "chapter") == "chapter"

    open_triage(page, live, SECOND)

    assert chip_labels(page, SECOND)[4] == CHOSEN["chapter"]
    assert chip_labels(page, SECOND)[3] == BARE[10]
    assert whose(page, SECOND) == "this unit"
    assert whose(page, FIRST) == "project", "the neighbour still inherits"
