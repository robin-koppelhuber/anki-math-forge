"""What to run next on exactly what is on screen.

The honest version of "trigger Claude from the website": the app writes the
command, you paste it where you can watch it. Nothing is launched, so nothing
writes cards with nobody looking.

Which makes the *arguments* the whole product. A command that silently acts on
a different population than the one you were looking at is worse than no
command at all, because you cannot see that it did.
"""

from __future__ import annotations

from typing import Any

from anki_math_forge.app import commands_for


def runs(view: str, filters: dict[str, object], counts: dict[str, int], **kw: Any) -> list[str]:
    return [c["run"] for c in commands_for(view, filters, counts, **kw)]


def test_it_offers_transcription_only_when_something_is_untranscribed() -> None:
    """On what the pass would work on, not on the triage state. `new` stood
    in for this, so a deck of sixteen new units that had all been read
    offered the pass anyway and running it reported nothing to do."""
    base = {"project": "book", "state": "new"}
    assert any("/transcribe" in r for r in runs("units", base, {"untranscribed": 12}))
    assert not any("/transcribe" in r for r in runs("units", base, {"untranscribed": 0}))
    assert not any(
        "/transcribe" in r for r in runs("units", base, {"new": 12, "untranscribed": 0})
    ), "sixteen units nobody has triaged, all of them already read"


def test_it_offers_card_writing_only_when_something_is_queued() -> None:
    base = {"project": "book", "state": "queued"}
    assert any("/extract-cards" in r for r in runs("units", base, {"queued": 3}))
    assert not any("/extract-cards" in r for r in runs("units", base, {"queued": 0}))


def test_it_offers_naming_the_units_before_writing_them_up() -> None:
    """`/gist` gives each queued unit a line saying what a card from it would
    be about. It is worth doing before the stubs exist, because it is what the
    list, the graph and every link to a card read as afterwards."""
    base = {"project": "book", "state": "queued"}
    out = runs("units", base, {"queued": 6, "ungisted": 6})
    assert any("/gist" in r for r in out)
    assert out.index(next(r for r in out if "/gist" in r)) < out.index(
        next(r for r in out if "/extract-cards" in r)
    ), "before the stubs, not after"

    named = runs("units", base, {"queued": 6, "ungisted": 0})
    assert not any("/gist" in r for r in named)


def test_the_way_back_from_anki_is_offered_without_a_count() -> None:
    """Nothing here can know you flagged a card in Anki last night: until
    `feedback` runs, that comment is not a note on anything and no list in
    this app is showing it. A row gated on a count would be a row you only
    see once it is too late to be told."""
    out = runs("review", {"project": "book"}, {"draft": 0, "approved": 0})
    assert any("forge feedback" in r for r in out)


def test_working_the_notes_stays_on_the_source_you_are_looking_at() -> None:
    """`todo` spans the repo, and conventions are per source: a list that hops
    between two books makes you reload the setting between every item."""
    out = runs("review", {"project": "book"}, {"annotated_claude_card": 3})
    triage = next(r for r in out if "/triage" in r)
    assert triage == '/triage claude --project "book"'


def test_every_command_names_the_source() -> None:
    """Three sources in a repo and none of these verbs defaults to one. A
    `/extract-cards` with no source writes stubs for every queued unit in the
    repo, which is not what the person filtering to one paper asked for."""
    counts = {"new": 2, "queued": 2, "ungisted": 2}
    for run in runs("units", {"project": "book", "state": "new"}, counts):
        assert '--project "book"' in run


def test_the_command_carries_the_section_you_filtered_to() -> None:
    """Otherwise it is a suggestion about a different population than the one
    on screen, which is worse than no suggestion."""
    filters = {"project": "book", "state": "new", "section": "2.4"}
    for run in runs("units", filters, {"new": 5}):
        assert '--section "2.4"' in run


def test_a_section_with_spaces_in_it_stays_one_argument() -> None:
    """A source that numbers nothing gets its sections from somewhere else --
    a Zotero attachment is called `MOL appendix.pdf` -- and an unquoted one
    would arrive as two arguments, the second of them a stray filename."""
    filters = {"project": "wegel", "state": "new", "section": "MOL appendix.pdf"}
    for run in runs("units", filters, {"new": 5}):
        assert '--section "MOL appendix.pdf"' in run


def test_a_value_that_cannot_be_quoted_drops_its_flag() -> None:
    """No spelling of an embedded double quote works in both `sh` and
    PowerShell: `""` escapes it in one and ends the string in the other. A
    command that does too much is visible; one that does something else is
    not."""
    filters = {"project": 'a "book"', "state": "new", "section": "2.4"}
    for run in runs("units", filters, {"new": 1}):
        assert "--project" not in run
        assert '--section "2.4"' in run, "the unaffected flag survives"


def test_quoting_is_powershell_safe() -> None:
    """Single quotes, which the CLI's own examples use, are a literal in
    PowerShell: the quote marks would be passed through as part of the value."""
    filters = {"project": "a book", "state": "new", "section": "2.4"}
    for run in runs("units", filters, {"new": 1}):
        assert "'" not in run


def test_a_marked_up_source_is_offered_neither_crop_pass() -> None:
    """Both read a picture of an equation. A highlight already carries the
    text it covers, so transcribing it is nothing; and `/classify` proposes
    skipping fragments and table rows, which is a judgement about a page of
    formulas, not about a paragraph somebody marked."""
    out = runs("units", {"project": "wegel", "state": "new"}, {"new": 16}, from_marks=True)
    assert not any("/transcribe" in r for r in out)
    assert not any("/classify" in r for r in out)


def test_a_marked_up_source_leaves_out_the_pass_without_explaining_itself() -> None:
    """A panel of commands is a list of what to do, not a list of what not
    to do. Two notes here said the transcription pass does not apply and how
    to transcribe one unit anyway; they were written when an absent pass
    left the panel empty, which it no longer does."""
    said = commands_for("units", {"project": "wegel"}, {"new": 16}, from_marks=True)

    assert said, "still something to run"
    assert not [c for c in said if c["kind"] == "note"]
    assert not any("/transcribe" in c["run"] for c in said)


def test_the_review_view_offers_review_things() -> None:
    out = runs("review", {"project": "book"}, {"draft": 4, "unaugmented": 4})
    assert any("/augment" in r for r in out)
    assert any("sync --dry-run" in r for r in out)
    assert not any("/transcribe" in r for r in out)


def test_augment_is_offered_on_what_is_left_not_on_every_draft() -> None:
    """A deck whose drafts have all had the pass does not want it again. A
    panel that goes on suggesting it is one you learn to ignore, and running
    it is a second opinion about cards nobody asked about twice."""
    done = runs("review", {"project": "book"}, {"draft": 4, "unaugmented": 0})
    assert not any("/augment" in r for r in done)

    left = runs("review", {"project": "book"}, {"draft": 4, "unaugmented": 1})
    assert any("/augment" in r for r in left)


def test_augment_is_not_offered_with_no_drafts() -> None:
    assert not any("/augment" in r for r in runs("review", {"project": "book"}, {"draft": 0}))


def test_open_requests_are_offered_only_when_there_are_some() -> None:
    """`/triage claude` on an empty queue is a round trip that reports nothing,
    and it was offered unconditionally."""
    quiet = runs("review", {"project": "book"}, {"draft": 1})
    assert not any("/triage" in r for r in quiet)
    busy = runs("review", {"project": "book"}, {"draft": 1, "annotated_claude_card": 3})
    assert any("/triage claude" in r for r in busy)


def test_every_view_offers_something() -> None:
    """With nothing to do the panel still has to explain itself rather than
    render as an empty box."""
    for view in ("units", "review"):
        assert commands_for(view, {"project": "book"}, {})


def test_every_command_says_where_it_is_pasted() -> None:
    """A slash command goes into Claude Code and a shell command does not, and
    pasting one into the other does nothing useful."""
    cases = (
        ("units", {"new": 1, "queued": 1}, {}),
        ("units", {"new": 1}, {"from_marks": True}),
        ("review", {"draft": 1, "approved": 2, "annotated_claude_card": 1}, {}),
    )
    for view, counts, kw in cases:
        for command in commands_for(view, {"project": "book"}, counts, **kw):
            assert command["kind"] in {"claude", "shell", "note"}
            if command["kind"] == "note":
                assert not command["run"], "a note is not copyable"
                continue
            assert command["run"].startswith("/") == (command["kind"] == "claude")


def test_every_command_says_what_it_does() -> None:
    """The label says which pass and how much is waiting -- `fill in 4 thin
    drafts` -- and never what the pass *is*. These are commands you run rarely
    enough to have forgotten between times, and the panel is the only place
    they are described anywhere near where you press them."""
    for view, counts in (
        ("units", {"new": 16, "queued": 4}),
        ("review", {"draft": 4, "approved": 9, "annotated_claude_card": 2}),
    ):
        for cmd in commands_for(view, {"project": "book"}, counts):
            if cmd["kind"] == "note":
                continue
            why = cmd.get("why", "")
            assert why, f"{cmd['run']} has no explainer"
            assert len(why.split()) >= 8, f"{cmd['run']}: {why!r} is not a sentence"
            assert why != cmd["label"], "an explainer that repeats the label explains nothing"
