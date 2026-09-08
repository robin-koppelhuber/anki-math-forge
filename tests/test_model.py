"""The parser. Everything depends on the round trip being byte-stable."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from anki_forge import model
from anki_forge.model import Card, CardError, Section, StaleFileError


def test_round_trip_is_byte_stable(card_path: Path) -> None:
    original = card_path.read_text(encoding="utf-8")
    assert model.parse(original).render() == original


def test_round_trip_through_the_model_is_stable(card_path: Path) -> None:
    card = model.load(card_path)
    assert model.parse(card.render()).render() == card.render()


def test_parses_frontmatter_and_sections(card_path: Path) -> None:
    card = model.load(card_path)
    assert card.uid == "7f3a2b"
    assert card.type == "identity"
    assert card.status == "draft"
    assert card.unit == "demo:2.4:61"
    assert card.tags == ["matrix-calculus", "derivatives"]
    assert card.section_names() == ["front", "back", "conditions", "prose"]
    assert card.section("back") == r"$X^{-\top}$"


def test_missing_frontmatter_is_an_error() -> None:
    with pytest.raises(CardError, match="frontmatter"):
        model.parse("## front\n$x$\n")


def test_sections_are_canonically_ordered() -> None:
    card = Card(
        frontmatter={"uid": "abc123", "type": "identity"},
        sections=[Section("notes", "@claude hi"), Section("back", "$b$"), Section("front", "$f$")],
    )
    assert [s.name for s in card.canonical().sections] == ["front", "back", "notes"]


def test_unicode_and_colons_survive_the_round_trip() -> None:
    card = Card(
        frontmatter={"uid": "abc123", "source": "Matrix Cookbook §2.4, eq. 61", "tags": ["a", "b"]},
        sections=[Section("front", "$x$")],
    )
    reparsed = model.parse(card.render())
    assert reparsed.frontmatter["source"] == "Matrix Cookbook §2.4, eq. 61"
    assert reparsed.tags == ["a", "b"]
    assert reparsed.render() == card.render()


# -- hashing ---------------------------------------------------------------


def test_annotating_does_not_change_the_content_hash(card_path: Path) -> None:
    """Scribbling a note on a card is not an edit of the card (§8)."""
    card = model.load(card_path)
    before = card.content_hash()
    card.add_annotation("check the transpose")
    assert card.content_hash() == before


def test_editing_content_changes_the_hash(card_path: Path) -> None:
    card = model.load(card_path)
    before = card.content_hash()
    card.set_section("back", r"$X^{-1}$")
    assert card.content_hash() != before


def test_approve_stamps_a_matching_hash(card_path: Path) -> None:
    card = model.load(card_path)
    card.approve()
    assert card.status == "approved"
    assert card.hash_matches()


def test_approval_survives_a_save_and_reload(card_path: Path) -> None:
    card = model.load(card_path)
    card.approve()
    card.save()
    assert model.load(card_path).hash_matches()


# -- annotations -----------------------------------------------------------


def test_annotation_prefix_is_added_once() -> None:
    card = Card(frontmatter={"uid": "abc123"})
    card.add_annotation("fix the layout")
    card.add_annotation("@claude and the tags")
    assert card.annotations() == ["@claude fix the layout", "@claude and the tags"]
    assert card.section("notes") == "@claude fix the layout\n@claude and the tags"


def test_non_annotation_lines_are_not_open_requests() -> None:
    card = Card(frontmatter={"uid": "abc123"}, sections=[Section("notes", "just a thought")])
    assert card.annotations() == []


# -- writing ---------------------------------------------------------------


def test_stale_write_is_refused(card_path: Path) -> None:
    card = model.load(card_path)
    loaded_at = card.mtime_ns
    time.sleep(0.01)
    card_path.write_text(card_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(StaleFileError):
        card.save(expect_mtime_ns=loaded_at)


def test_write_succeeds_when_the_file_is_untouched(card_path: Path) -> None:
    card = model.load(card_path)
    card.add_annotation("looks fine")
    card.save(expect_mtime_ns=card.mtime_ns)
    assert "@claude looks fine" in card_path.read_text(encoding="utf-8")


def test_uids_are_deterministic_and_collision_free() -> None:
    assert model.mint_uid("demo:2.4:61") == model.mint_uid("demo:2.4:61")
    first = model.mint_uid("demo:2.4:61")
    assert model.mint_uid("demo:2.4:61", {first}) != first


def test_stub_is_minimal_but_complete() -> None:
    card = model.stub(uid="abc123", front="$a$", back="$b$", source="Demo", unit="demo:1:1")
    assert card.section_names() == ["front", "back"]
    assert card.status == "draft"
    assert model.parse(card.render()).render() == card.render()


def test_reordering_frontmatter_does_not_break_an_approval() -> None:
    """The digest is over content, not over the file's layout.

    It used to hash the rendered card, so it depended on FRONTMATTER_ORDER.
    Adding one optional field to that tuple invalidated every approval in the
    deck: the cards were untouched and `check` called them edited.
    """
    a = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity", "tags": ["x"], "frequency": "core"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    b = model.Card(
        frontmatter={"frequency": "core", "tags": ["x"], "type": "identity", "uid": "aa11bb"},
        sections=[model.Section("back", "$b$"), model.Section("front", "$a$")],
    )
    assert a.content_hash() == b.content_hash()


def test_changing_content_still_changes_the_hash() -> None:
    """Order-independence must not become blindness."""
    base = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    before = base.content_hash()

    edited = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$c$")],
    )
    assert edited.content_hash() != before

    tagged = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity", "frequency": "core"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    assert tagged.content_hash() != before, "adding a field is a real content change"


def test_status_and_notes_stay_out_of_the_hash() -> None:
    plain = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    approved = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity", "status": "approved",
                     "content_hash": "deadbeef"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$"),
                  model.Section("notes", "@me a thought")],
    )
    assert plain.content_hash() == approved.content_hash()


def test_editing_a_verify_block_does_not_unapprove() -> None:
    """`verify` is a check on the author, not content a reviewer saw.

    It never reaches Anki. Hashing it meant tightening a numerical test threw
    away an approval on a card whose mathematics had not moved.
    """
    def card(verify: str) -> model.Card:
        return model.Card(
            frontmatter={"uid": "aa11bb", "type": "identity"},
            sections=[
                model.Section("front", "$a$"),
                model.Section("back", "$b$"),
                model.Section("verify", verify),
            ],
        )

    assert card("lhs = 1\nrhs = 1").content_hash() == card("lhs = 2\nrhs = 2").content_hash()

    # but the claim itself still does
    changed = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$c$")],
    )
    assert changed.content_hash() != card("lhs = 1\nrhs = 1").content_hash()


def test_uses_is_a_recognised_section() -> None:
    """"Where does this actually turn up" is a different question from what the
    result means, so it gets its own short section rather than crowding prose."""
    assert "uses" in model.SECTION_ORDER
    assert model.SECTION_ORDER.index("uses") < model.SECTION_ORDER.index("proof")

    card = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity"},
        sections=[
            model.Section("back", "$b$"),
            model.Section("uses", "The normal equations."),
            model.Section("front", "$a$"),
        ],
    )
    # rendering puts sections in canonical order, so `uses` must have a place
    rendered = card.render()
    assert rendered.index("## front") < rendered.index("## back") < rendered.index("## uses")


def test_uses_reaches_anki_as_its_own_field() -> None:
    from anki_forge import notetype

    assert "Uses" in notetype.FIELDS
    assert "{{#Uses}}" in notetype.BACK_TEMPLATE
    assert "{{Uses}}" not in notetype.FRONT_TEMPLATE, "it is answer-side, not a prompt"


def test_add_annotation_keeps_an_existing_audience(card_path: Path) -> None:
    """`@me` is a decision parked for the human. Prefixing it with `@claude`
    would file it as the agent's work, which is the one mix-up the audience
    split exists to prevent."""
    card = model.load(card_path)
    card.add_annotation("@me a decision for the human")
    card.add_annotation("plain text gets the default")

    notes = card.annotations()
    assert notes[0] == "@me a decision for the human"
    assert notes[1] == "@claude plain text gets the default"
    assert [model.annotation_audience(n) for n in notes] == ["me", "claude"]


def test_resolve_annotation_deletes_the_line_and_leaves_the_prose(card_path: Path) -> None:
    """Resolving *is* deleting: a note still in the file still blocks sync, so
    anything short of a delete leaves the card exactly as stuck."""
    card = model.load(card_path)
    card.set_section("notes", "a plain note that is not addressed to anyone")
    card.add_annotation("@me a decision")
    card.add_annotation("work for the agent")

    removed = card.resolve_annotation(0)

    assert removed == "@me a decision"
    assert card.annotations() == ["@claude work for the agent"]
    assert "a plain note that is not addressed to anyone" in card.section("notes")


def test_resolving_does_not_un_approve(card_path: Path) -> None:
    """`## notes` is outside `content_hash`, so finishing with a note is not
    an edit to the card a reviewer looked at."""
    card = model.load(card_path)
    card.add_annotation("@me a decision")
    card.approve()
    before = card.content_hash()

    card.resolve_annotation(0)

    assert card.content_hash() == before
    assert card.effective_status == "approved"


def test_resolving_an_index_that_is_not_there_is_refused(card_path: Path) -> None:
    card = model.load(card_path)
    with pytest.raises(CardError):
        card.resolve_annotation(0)
