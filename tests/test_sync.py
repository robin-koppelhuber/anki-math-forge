"""Sync: approval gating, annotation gating, idempotency, field rendering."""

from __future__ import annotations

from pathlib import Path

from anki_forge import check, model, notetype, sync
from anki_forge.config import Config
from conftest import FakeAnki


def approve(path: Path) -> model.Card:
    card = model.load(path)
    card.approve()
    card.save()
    return card


# -- rendering (DESIGN.md §9) ----------------------------------------------


def test_dollar_math_becomes_mathjax() -> None:
    assert sync.to_anki_html("$X^{-\\top}$") == "\\(X^{-\\top}\\)"
    assert sync.to_anki_html("$$A B$$") == "\\[A B\\]"


def test_html_is_escaped_inside_and_outside_math() -> None:
    rendered = sync.to_anki_html("a < b and $x < y$ & more")
    assert "&lt;" in rendered
    assert "\\(x &lt; y\\)" in rendered
    assert "<script" not in rendered


def test_newlines_break_only_outside_math() -> None:
    rendered = sync.to_anki_html("line one\nline two $a\nb$")
    assert "line one<br>line two" in rendered
    assert "\\(a b\\)" in rendered  # the formula stays one text node


def test_notes_and_verify_never_reach_a_field(config: Config, card_path: Path) -> None:
    card = model.load(card_path)
    card.add_annotation("do not ship this")
    card.set_section("verify", "lhs = 1\nrhs = 1")
    fields = sync.fields_for(card, config)
    assert set(fields) == set(notetype.FIELDS)
    assert "do not ship" not in "".join(fields.values())
    assert "lhs" not in "".join(fields.values())


def test_tags_carry_a_source_marker(config: Config, card_path: Path) -> None:
    tags = sync.tags_for(model.load(card_path), config)
    assert "forge" in tags
    assert "src::demo::2.4" in tags
    assert "matrix-calculus" in tags


# -- gating ----------------------------------------------------------------


def test_a_draft_is_not_synced(config: Config, card_path: Path, anki: FakeAnki) -> None:
    report = sync.run(config, client=anki)
    assert report.count("add") == 0
    assert any(o.detail == "status is draft" for o in report.outcomes)
    assert anki.notes == {}


def test_an_open_annotation_blocks_sync(config: Config, card_path: Path, anki: FakeAnki) -> None:
    """Refused regardless of status -- "not ready" is mechanical (§8)."""
    card = approve(card_path)
    card.add_annotation("check the transpose against §2.4")
    card.save()

    report = sync.run(config, client=anki)
    assert anki.notes == {}
    assert any("annotation" in o.detail for o in report.outcomes)


def test_a_card_edited_after_approval_is_not_synced(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    """The un-approval rule (§3.5): editing an approved card un-approves it."""
    approve(card_path)
    text = card_path.read_text(encoding="utf-8").replace(r"$X^{-\top}$", r"$X^{-1}$")
    card_path.write_text(text, encoding="utf-8")

    report = sync.run(config, client=anki)
    assert anki.notes == {}, "an edited approval must not reach Anki"
    assert any("edited since" in o.detail for o in report.outcomes)
    # ...and `check` still reports the file itself as inconsistent
    assert any(f.code == "hash-stale" for f in check.check_repo(config)[1])


# -- upsert ----------------------------------------------------------------


def test_approved_cards_are_added(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    report = sync.run(config, client=anki)
    assert report.ok
    assert report.count("add") == 1
    assert report.count("setup") == 2  # the deck and the note type
    (note,) = anki.notes.values()
    assert note["model"] == config.note_type
    assert note["deck"] == config.deck
    assert note["fields"]["uid"] == "7f3a2b"
    assert "\\(" in note["fields"]["Front"]


def test_sync_is_idempotent(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    sync.run(config, client=anki)
    before = {k: dict(v) for k, v in anki.notes.items()}

    second = sync.run(config, client=anki)
    assert len(anki.notes) == 1
    assert anki.notes == before
    assert second.count("unchanged") == 1
    assert second.count("add") == 0


def test_an_edit_updates_the_existing_note(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    sync.run(config, client=anki)
    (note_id,) = anki.notes

    card = model.load(card_path)
    card.set_section("prose", "A brand new explanation.")
    card.approve()
    card.save()

    report = sync.run(config, client=anki)
    assert list(anki.notes) == [note_id], "upsert by uid, never a second note"
    assert report.count("update") == 1
    assert "brand new" in anki.notes[note_id]["fields"]["Prose"]


def test_dry_run_touches_nothing(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    report = sync.run(config, client=anki, dry_run=True)
    assert report.ok
    assert anki.notes == {}
    assert anki.decks == ["Default"]
    assert report.summary().startswith("would sync")


def test_a_card_pulled_back_to_draft_is_reported_not_deleted(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    approve(card_path)
    sync.run(config, client=anki)

    card = model.load(card_path)
    card.unapprove()
    card.save()

    report = sync.run(config, client=anki)
    assert len(anki.notes) == 1, "sync never deletes: review history is not ours to drop"
    assert any("no longer approved" in o.detail for o in report.outcomes)


def test_note_type_field_drift_is_refused(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    anki.models[config.note_type] = ["uid", "Front"]  # someone edited it in Anki
    report = sync.run(config, client=anki)
    assert not report.ok
    assert len(anki.notes) == 0
    assert any("Bump `note_type_version`" in o.detail for o in report.outcomes)


def test_tags_are_reconciled_on_update(config: Config, card_path: Path, anki: FakeAnki) -> None:
    approve(card_path)
    sync.run(config, client=anki)
    (note_id,) = anki.notes

    card = model.load(card_path)
    card.frontmatter["tags"] = ["matrix-calculus", "determinant"]
    card.approve()
    card.save()

    sync.run(config, client=anki)
    tags = anki.notes[note_id]["tags"]
    assert "determinant" in tags
    assert "derivatives" not in tags
