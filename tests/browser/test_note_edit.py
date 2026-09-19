"""Rewording a note on a card.

The row it lives in is built twice -- once by the server, once by `review.js`
after any write -- and a control missing from the second copy disappears the
moment you touch the card, which is the sort of thing only a browser notices.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


def with_a_note(repo: Path, text: str = "@claude chekc the sign") -> str:
    """One card carrying one annotation."""
    card = repo / "cards" / "demo" / "zznote-x.md"
    card.write_text(
        "---\nuid: zznote\ntype: identity\nstatus: draft\n"
        'source: "Demo"\nunit: "demo:1:1"\ngist: a card with a note\n---\n\n'
        f"## front\n\n$a$\n\n## back\n\n$b$\n\n## notes\n\n{text}\n",
        encoding="utf-8",
    )
    return "zznote"


def test_editing_a_note_rewrites_the_line_and_keeps_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    _, repo = served
    uid = with_a_note(repo)
    page.goto(f"{live}/review?source=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    page.locator(f'[data-uid="{uid}"] [data-edit-note]').click()
    page.wait_for_selector("#prompt[open]")
    # The pre-fill is the whole line, prefix and all, and the caret is at the
    # end of it -- so this is the correction typed over the top of it.
    page.fill("#prompt-input", "@claude check the sign")
    page.keyboard.press("Enter")
    # The row is rebuilt from the response, so waiting for the file alone
    # reads whatever the previous render left on screen.
    page.wait_for_selector(
        f'[data-uid="{uid}"] .annotation .what:text-is("check the sign")'
    )

    card = (repo / "cards" / "demo" / "zznote-x.md").read_text(encoding="utf-8")
    assert "@claude check the sign" in card
    assert "chekc" not in card, "the line was replaced, not added to"
    # The row itself, not the whole card: the findings banner beside it still
    # quotes the old wording until the next request rebuilds it.
    assert page.inner_text(f'[data-uid="{uid}"] .annotation .what') == "check the sign"


def test_the_edit_button_survives_a_repaint(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """`review.js` rebuilds the annotation rows after every write. A button
    the template has and the script does not vanishes on the first click you
    make anywhere else on the card."""
    _, repo = served
    uid = with_a_note(repo, "@me decide whether this is two cards")
    page.goto(f"{live}/review?source=demo&status=draft#{uid}")
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')

    # Any write that comes back with a card payload repaints the rows.
    page.locator(f'[data-uid="{uid}"] [data-grade="frequency"]').first.click()
    # The grading lands in the frontmatter; the rows are rebuilt in the same
    # breath, and it is the rows this test is about.
    page.wait_for_function(
        "uid => !document.querySelector(`[data-uid=\"${uid}\"] [data-grade=\"frequency\"]`)"
        ".classList.contains('missing')",
        arg=uid,
    )

    assert page.locator(f'[data-uid="{uid}"] [data-edit-note]').count() == 1
    assert page.locator(f'[data-uid="{uid}"] [data-resolve]').count() == 1
