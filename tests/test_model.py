"""The parser. Everything depends on the round trip being byte-stable."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from anki_math_forge import model
from anki_math_forge.model import Card, CardError, Section, StaleFileError


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


def test_turning_verify_on_does_not_un_approve(card_path: Path) -> None:
    """Both halves of opting in, or neither.

    The `## verify` section was exempt because hashing it meant that fixing a
    test un-approved a card whose mathematics had not changed. The `verify:`
    flag was not, so turning a test *on* did exactly that -- demonstrated on
    four identities that passed numerically and went `hash-stale` anyway.
    """
    card = model.load(card_path)
    before = card.content_hash()

    card.frontmatter["verify"] = True
    card.set_section("verify", "```python\nlhs = 1\nrhs = 1\n```")

    assert card.content_hash() == before, "a numeric check is not a claim on the card"


def test_changing_what_the_card_claims_still_does(card_path: Path) -> None:
    """The exemption is narrow: only whether a check runs, never what it says
    about the mathematics."""
    card = model.load(card_path)
    before = card.content_hash()
    card.frontmatter["type"] = "intuition"
    assert card.content_hash() != before


def test_a_grading_is_not_a_claim_the_card_makes(card_path: Path) -> None:
    """`frequency` and `derivation` decide *when you meet* a card, not what it
    says. They join `requires` on its own argument, which CLAUDE.md states:
    approving a card is not approving its position in the queue.

    You also learn one by meeting the card, months later -- so hashing them
    meant that deciding a result was `common` rather than `core` un-approved
    something nobody had touched.
    """
    card = model.load(card_path)
    before = card.content_hash()
    card.frontmatter["frequency"] = "rare"
    card.frontmatter["derivation"] = "short"
    assert card.content_hash() == before


def test_a_grading_carries_the_approval_with_it(card_path: Path) -> None:
    """Including on a card stamped under the older rule, whose digest covers
    the very key being changed. Without the re-stamp, the first click on any
    card approved before the exemption widened would report it as edited --
    which is a lie: nobody edited the mathematics."""
    card = model.load(card_path)
    card.approve()
    card.frontmatter["content_hash"] = card.content_hash(legacy=True)

    card.set_grade("frequency", "rare")

    assert card.status == "approved"
    assert card.hash_matches(), "a grading is not an edit"
    assert card.effective_status == "approved"


def test_a_grading_does_not_launder_a_real_edit(card_path: Path) -> None:
    """The re-stamp happens only when the approval was holding to begin with.
    A card whose content had already drifted stays drifted: re-stamping that
    one would push an unreviewed edit to Anki under an old approval."""
    card = model.load(card_path)
    card.approve()
    card.set_section("back", "$something else entirely$")

    card.set_grade("frequency", "rare")

    assert not card.hash_matches()
    assert card.effective_status == "draft"


def test_the_older_digest_is_still_accepted(card_path: Path) -> None:
    """Widening the exemption changed what `content_hash` computes, and a whole
    deck was stamped under the old rule. Recomputing alone would have reported
    108 untouched cards as edited on the strength of a code change."""
    card = model.load(card_path)
    card.frontmatter["frequency"] = "core"
    card.frontmatter["status"] = "approved"
    card.frontmatter["content_hash"] = card.content_hash(legacy=True)

    assert card.hash_matches()
    assert card.effective_status == "approved"


def test_the_older_digest_does_not_forgive_an_edit(card_path: Path) -> None:
    """The fallback is weaker in one direction only. Change the mathematics and
    both digests move, so a legacy stamp rescues nothing it should not."""
    card = model.load(card_path)
    card.frontmatter["status"] = "approved"
    card.frontmatter["content_hash"] = card.content_hash(legacy=True)
    card.set_section("front", "$a different question$")

    assert not card.hash_matches()


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
        frontmatter={"uid": "aa11bb", "type": "identity", "tags": ["traces"]},
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
    from anki_math_forge import notetype

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


def test_a_prefix_has_to_end_where_it_ends(card_path: Path) -> None:
    """`@metric space` opens like `@me` and is not a note addressed to anyone,
    which a bare `startswith` could not tell."""
    assert model.annotation_audience("@metric space bound is wrong") == ""
    assert model.annotation_audience("@me, on reflection") == "me"
    assert model.annotation_audience("@claude: check the sign") == "claude"

    card = model.load(card_path)
    card.add_annotation("@metric space bound is wrong")
    assert card.annotations() == ["@claude @metric space bound is wrong"]


def test_annotation_line_is_what_gets_written_and_is_idempotent(card_path: Path) -> None:
    """`feedback` builds the line to compare against `annotations()` and then
    hands the same line back to `add_annotation`."""
    once = model.annotation_line("  two   spaces  ")
    assert once == "@claude two spaces"
    assert model.annotation_line(once) == once
    assert model.annotation_line("   ") == ""

    card = model.load(card_path)
    card.add_annotation(once)
    assert card.annotations() == [once]


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


def test_edit_annotation_rewrites_the_line_where_it_stands(card_path: Path) -> None:
    """Editing, not resolving. The note keeps its place and stays open, and
    the prose around it is left alone."""
    card = model.load(card_path)
    card.set_section("notes", "a plain note that is not addressed to anyone")
    card.add_annotation("@me a decison")
    card.add_annotation("work for the agent")

    written = card.edit_annotation(0, "@me a decision")

    assert written == "@me a decision"
    assert card.annotations() == ["@me a decision", "@claude work for the agent"]
    assert "a plain note that is not addressed to anyone" in card.section("notes")


def test_an_edit_may_move_a_note_to_the_other_audience(card_path: Path) -> None:
    """The prefix is part of the line, so dropping it sends the note to
    Claude exactly as editing the file would."""
    card = model.load(card_path)
    card.add_annotation("@me is this the right layout?")

    card.edit_annotation(0, "is this the right layout?")

    assert card.annotations() == ["@claude is this the right layout?"]


def test_an_edited_note_still_holds_the_card(card_path: Path) -> None:
    """Rewording is not answering: the one thing that unblocks sync is the
    line being gone."""
    card = model.load(card_path)
    card.add_annotation("@me a decision")
    card.approve()
    before = card.content_hash()

    card.edit_annotation(0, "@me a decision, by Friday")

    assert card.content_hash() == before, "`## notes` is outside the hash"
    assert card.effective_status == "draft"
    assert card.demotion == "annotated"


def test_editing_an_index_or_an_empty_line_is_refused(card_path: Path) -> None:
    """Emptying the box is not how a note is deleted: resolve is, and resolve
    hands the line back for undo where this would not."""
    card = model.load(card_path)
    with pytest.raises(CardError):
        card.edit_annotation(0, "still nothing there")

    card.add_annotation("@me a decision")
    with pytest.raises(CardError):
        card.edit_annotation(0, "   ")
    assert card.annotations() == ["@me a decision"]


# -- the one state that is not readable off the content ---------------------


def test_augmented_is_outside_the_content_hash(card_path: Path) -> None:
    """The pass's right answer is usually to add nothing, so hashing its
    receipt would un-approve every card it decided to leave alone."""
    card = model.load(card_path)
    card.approve()
    card.save()

    again = model.load(card_path)
    again.set_grade("augmented", True)
    again.save()

    settled = model.load(card_path)
    assert settled.augmented is True
    assert settled.effective_status == "approved", "recording the pass is not an edit"


def test_withdrawing_it_is_how_you_ask_again(card_path: Path) -> None:
    card = model.load(card_path)
    card.set_grade("augmented", True)
    card.set_grade("augmented", "")
    card.save()

    assert model.load(card_path).augmented is False
    assert "augmented" not in model.load(card_path).frontmatter, "removed, not false"


def test_a_card_says_nothing_about_it_by_default(card_path: Path) -> None:
    assert model.load(card_path).augmented is False


# -- what a settled annotation leaves behind --------------------------------


def test_a_reply_keeps_the_question_it_answered(card_path: Path) -> None:
    """Deleting the line threw away both halves, and the question is most of
    what makes the answer worth having: "fixed" tells you nothing six weeks
    later about whether the point you made was taken."""
    card = model.load(card_path)
    card.add_annotation("@claude check the sign on the second term")

    card.resolve_annotation(0, "the sign was right; the condition it needs is now stated")

    assert card.annotations() == []
    assert card.resolved() == [
        "resolved: check the sign on the second term \u2014 "
        "the sign was right; the condition it needs is now stated"
    ]


def test_a_record_is_not_an_annotation(card_path: Path) -> None:
    """The whole reason a settled note can stay on the card: it carries no
    address, so nothing reads it as work and it does not hold the card back.
    `sync` refuses an annotated card whatever its status."""
    card = model.load(card_path)
    card.add_annotation("@claude too thin")
    card.resolve_annotation(0, "added the derivation in ## proof")

    assert card.annotations() == []
    assert model.annotation_audience(card.resolved()[0]) == ""


def test_a_record_does_not_withdraw_an_approval(card_path: Path) -> None:
    """`## notes` is outside `content_hash`, so settling a note restores the
    approval rather than costing a re-review. That is the same rule resolving
    already relied on, and it has to survive the line staying."""
    card = model.load(card_path)
    card.add_annotation("@claude check the sign")
    card.approve()
    before = card.content_hash()

    card.resolve_annotation(0, "the sign was right")

    assert card.content_hash() == before
    assert card.effective_status == "approved"
    assert card.demotion == ""


def test_no_reply_still_deletes_outright(card_path: Path) -> None:
    """Right when the note was a reminder rather than a request. A record of
    "remember to look at this" and nothing else is noise on the card."""
    card = model.load(card_path)
    card.add_annotation("@claude have another look")

    card.resolve_annotation(0)

    assert card.annotations() == [] and card.resolved() == []


def test_the_record_keeps_the_line_s_place(card_path: Path) -> None:
    """Settled in order, so reading down the list is reading the history of
    the card rather than a pile in the order somebody happened to answer."""
    card = model.load(card_path)
    card.add_annotation("@claude first")
    card.add_annotation("@claude second")

    card.resolve_annotation(0, "did the first")

    notes = (card.section("notes") or "").splitlines()
    assert notes[0].startswith("resolved: first")
    assert notes[1] == "@claude second"


def test_prose_in_notes_is_left_alone(card_path: Path) -> None:
    """Invariant 7 puts real content in `## notes`: any condition added that
    the source does not state. Settling a note must not disturb it."""
    card = model.load(card_path)
    card.set_section("notes", "The source states this only for symmetric X.")
    card.add_annotation("@claude check the sign")

    card.resolve_annotation(0, "right as written")

    assert "The source states this only for symmetric X." in (card.section("notes") or "")
