"""What to run next on exactly what is on screen.

The honest version of "trigger Claude from the website": the app writes the
command, you paste it where you can watch it. Nothing is launched, so nothing
writes cards with nobody looking.
"""

from __future__ import annotations

from anki_math_forge.app import commands_for


def runs(view: str, filters: dict[str, object], counts: dict[str, int]) -> list[str]:
    return [c["run"] for c in commands_for(view, filters, counts)]


def test_it_offers_transcription_only_when_something_is_untriaged() -> None:
    base = {"source": "book", "state": "new"}
    assert any("/transcribe" in r for r in runs("units", base, {"new": 12}))
    assert not any("/transcribe" in r for r in runs("units", base, {"new": 0}))


def test_it_offers_card_writing_only_when_something_is_queued() -> None:
    base = {"source": "book", "state": "queued"}
    assert any("/extract-cards" in r for r in runs("units", base, {"queued": 3}))
    assert not any("/extract-cards" in r for r in runs("units", base, {"queued": 0}))


def test_the_command_carries_the_section_you_filtered_to() -> None:
    """Otherwise it is a suggestion about a different population than the one
    on screen, which is worse than no suggestion."""
    filters = {"source": "book", "state": "new", "section": "2.4"}
    assert "/transcribe 2.4" in runs("units", filters, {"new": 5})
    assert any('--section "2.4"' in r for r in runs("units", filters, {"new": 5}))


def test_quoting_is_powershell_safe() -> None:
    """Single quotes, which the CLI's own examples use, are a literal in
    PowerShell: the quote marks would be passed through as part of the value."""
    filters = {"source": "a book", "state": "new", "section": "2.4"}
    for run in runs("units", filters, {"new": 1}):
        assert "'" not in run


def test_the_review_view_offers_review_things() -> None:
    out = runs("review", {"source": "book"}, {"draft": 4})
    assert any("/augment" in r for r in out)
    assert any("sync --dry-run" in r for r in out)
    assert not any("/transcribe" in r for r in out)


def test_augment_is_not_offered_with_no_drafts() -> None:
    assert not any("/augment" in r for r in runs("review", {"source": "book"}, {"draft": 0}))


def test_every_command_says_where_it_is_pasted() -> None:
    """A slash command goes into Claude Code and a shell command does not, and
    pasting one into the other does nothing useful."""
    for view, counts in (("units", {"new": 1, "queued": 1}), ("review", {"draft": 1})):
        for command in commands_for(view, {"source": "book"}, counts):
            assert command["kind"] in {"claude", "shell"}
            assert command["run"].startswith("/") == (command["kind"] == "claude")
