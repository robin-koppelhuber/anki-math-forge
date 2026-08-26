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
