"""Sync: approval gating, annotation gating, idempotency, field rendering."""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import check, model, notetype, sync
from anki_math_forge import config as config_mod
from anki_math_forge.config import Config
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
    assert set(fields) == set(notetype.FIELDS) - {"Feedback"}, (
        "`Feedback` is inbound only; sync writing it would wipe a comment "
        "typed between a review and the next `feedback` pull"
    )
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


def test_note_type_name_carries_no_project_name(config: Config) -> None:
    """The name is written into every note, so it must not track the tool's own
    name. Renaming the project is then a docs diff, not a migration."""
    assert config.note_type == "Math Card v1"
    assert not any(bit in config.note_type.lower() for bit in ("forge", "anki"))


def test_renamed_note_type_is_reported_not_recreated(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    """The name changed here and not in Anki. Creating the new note type would
    leave 108 notes on the old one: still in the collection, invisible to
    `sync`, and re-added as new. Refuse and say how to fix it."""
    approve(card_path)
    anki.models["anki-forge identity v1"] = list(notetype.FIELDS)

    report = sync.run(config, client=anki)

    assert not report.ok
    assert config.note_type not in anki.models, "must not create a second note type"
    assert len(anki.notes) == 0
    detail = " ".join(o.detail or "" for o in report.outcomes)
    assert "anki-forge identity v1" in detail
    assert "Rename it in Anki" in detail


def test_note_type_is_created_when_nothing_stale_is_there(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    approve(card_path)
    report = sync.run(config, client=anki)
    assert report.ok
    assert anki.models[config.note_type] == list(notetype.FIELDS)


def test_card_template_is_renamed_after_a_note_type_rename(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    """Anki renames a note type without renaming its template. Pushing under a
    name the note type does not have would add a *second* template, and a
    second card for every note."""
    approve(card_path)
    sync.run(config, client=anki)
    stale = "anki-forge identity v1 card"
    anki.templates[config.note_type] = {
        stale: anki.templates[config.note_type].pop(notetype.CARD_TEMPLATE)
    }

    report = sync.run(config, client=anki)

    assert report.ok
    assert list(anki.templates[config.note_type]) == [notetype.CARD_TEMPLATE], (
        "renamed in place, not added alongside"
    )
    assert any("renamed" in (o.detail or "") for o in report.outcomes)


def test_a_second_card_template_is_refused(
    config: Config, card_path: Path, anki: FakeAnki
) -> None:
    approve(card_path)
    sync.run(config, client=anki)
    live = anki.templates[config.note_type]
    live["anki-forge identity v1 card"] = live.pop(notetype.CARD_TEMPLATE)
    live["mine"] = {"Front": "hand-made", "Back": "hand-made"}

    report = sync.run(config, client=anki)

    assert not report.ok
    assert any("not guess which" in (o.detail or "") for o in report.outcomes)


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


def test_the_two_judgements_reach_anki_as_tags(config: Config) -> None:
    """Filterable in Anki, which is where the decision they inform is made."""
    card = model.Card(
        frontmatter={
            "uid": "aa11bb",
            "type": "identity",
            "status": "approved",
            "frequency": "core",
            "derivation": "definitional",
        },
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    tags = sync.tags_for(card, config)
    assert "freq::core" in tags
    assert "derive::definitional" in tags

    bare = model.Card(
        frontmatter={"uid": "cc22dd", "type": "identity", "status": "approved"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    assert not [t for t in sync.tags_for(bare, config) if t.startswith(("freq", "derive"))]


def test_conditions_are_shown_with_the_prompt() -> None:
    """A setting revealed after you answer is a verdict, not a condition.

    The front template used to be `{{Front}}` alone, so `X in R^{n x n}` --
    which says *which question is being asked* -- only appeared once the
    answer was already given. That made "could someone answer this front from
    the ambient conventions alone" a rule no card could satisfy.
    """
    from anki_math_forge import notetype

    assert "{{#Conditions}}" in notetype.FRONT_TEMPLATE, "the setting must be on the prompt"
    assert "{{Conditions}}" in notetype.FRONT_TEMPLATE
    # and not repeated on the back, which already renders {{FrontSide}}
    assert "{{FrontSide}}" in notetype.BACK_TEMPLATE
    assert "{{Conditions}}" not in notetype.BACK_TEMPLATE


# -- per-source decks ------------------------------------------------------


def min_card(config: Config, uid: str, unit: str) -> Path:
    path = config.cards_dir / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "somewhere"\nunit: "{unit}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$X$\n\n## back\n$Y$\n",
        encoding="utf-8",
    )
    return path


def with_book_deck(repo: Path, deck: str) -> Config:
    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    toml += f'\n[sources.book]\ntitle = "A Book"\ndeck = "{deck}"\n'
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    return config_mod.load(repo)


def test_each_source_syncs_to_its_own_deck(repo: Path) -> None:
    config = with_book_deck(repo, "Physics::Tensors")
    approve(min_card(config, "aaa111", "demo:1.1:2"))
    approve(min_card(config, "bbb222", "book:1.1:1"))

    fake = FakeAnki()
    sync.run(config, client=fake)

    filed = {n["fields"]["uid"]: n["deck"] for n in fake.notes.values()}
    assert filed == {"aaa111": config.deck, "bbb222": "Physics::Tensors"}


def test_sync_creates_every_deck_it_writes_to(repo: Path) -> None:
    config = with_book_deck(repo, "Physics::Tensors")
    approve(min_card(config, "bbb222", "book:1.1:1"))

    fake = FakeAnki()
    report = sync.run(config, client=fake)

    assert "Physics::Tensors" in fake.decks
    setup = [o.detail for o in report.outcomes if o.action == "setup"]
    assert any("Physics::Tensors" in (d or "") for d in setup)


# -- the order new cards are introduced in ---------------------------------


def graded(config: Config, uid: str, frequency: str, derivation: str) -> Path:
    path = min_card(config, uid, "demo:1.1:2")
    card = model.load(path)
    card.frontmatter["frequency"] = frequency
    card.frontmatter["derivation"] = derivation
    card.save()
    return path


def test_study_order_is_most_useful_first_then_easiest(config: Config) -> None:
    """Anki numbers a new card by when it arrives and introduces them in that
    order, so the order they are added in is the order they are studied."""
    graded(config, "aaa111", "rare", "definitional")
    graded(config, "bbb222", "core", "long")
    graded(config, "ccc333", "core", "definitional")
    graded(config, "ddd444", "common", "short")

    order = [c.uid for c in sync.in_study_order(model.load_all(config.cards_dir))]
    assert order == ["ccc333", "bbb222", "ddd444", "aaa111"]


def test_an_ungraded_card_sorts_last_in_its_group(config: Config) -> None:
    """Unannotated is unjudged, not easy."""
    graded(config, "aaa111", "core", "long")
    min_card(config, "bbb222", "demo:1.1:2")  # no frequency, no derivation

    order = [c.uid for c in sync.in_study_order(model.load_all(config.cards_dir))]
    assert order == ["aaa111", "bbb222"]


def test_cards_are_added_in_study_order(repo: Path, config: Config) -> None:
    approve(graded(config, "aaa111", "rare", "long"))
    approve(graded(config, "bbb222", "core", "definitional"))

    fake = FakeAnki()
    sync.run(config, client=fake)

    added = [n["fields"]["uid"] for n in fake.notes.values()]
    assert added == ["bbb222", "aaa111"], "insertion order is the study order"


def test_reposition_leaves_a_card_you_have_started_alone(config: Config) -> None:
    """Past the new queue `due` is a date, not a position. Rewriting it would
    move a real review by decades."""
    approve(graded(config, "aaa111", "rare", "long"))
    approve(graded(config, "bbb222", "core", "definitional"))
    fake = FakeAnki()
    sync.run(config, client=fake)

    for card in fake.cards.values():
        if card["uid"] == "bbb222":
            card["type"] = 2  # a review card
            card["due"] = 19_000

    report = sync.run(config, client=fake, reposition_new=True)

    assert fake.cards_by_uid("bbb222")["due"] == 19_000, "a studied card is untouched"
    assert any("already studied" in (o.detail or "") for o in report.outcomes)


def test_reposition_keeps_the_deck_where_it_sits(config: Config) -> None:
    """Positions start from where the deck already is, so it does not jump
    ahead of every other deck's new cards."""
    approve(graded(config, "aaa111", "rare", "long"))
    approve(graded(config, "bbb222", "core", "definitional"))
    fake = FakeAnki()
    sync.run(config, client=fake)
    for offset, card in enumerate(fake.cards.values()):
        card["due"] = 5000 + offset

    sync.run(config, client=fake, reposition_new=True)

    assert fake.cards_by_uid("bbb222")["due"] == 5000
    assert fake.cards_by_uid("aaa111")["due"] == 5001


def test_a_dry_run_repositions_nothing(config: Config) -> None:
    approve(graded(config, "aaa111", "rare", "long"))
    approve(graded(config, "bbb222", "core", "definitional"))
    fake = FakeAnki()
    sync.run(config, client=fake)
    before = {uid: fake.cards_by_uid(uid)["due"] for uid in ("aaa111", "bbb222")}

    report = sync.run(config, client=fake, reposition_new=True, dry_run=True)

    assert {uid: fake.cards_by_uid(uid)["due"] for uid in before} == before
    assert any("repositioned" in (o.detail or "") for o in report.outcomes)


# -- the card layout -------------------------------------------------------


def test_prose_comes_before_uses_and_proof_on_the_card(config: Config) -> None:
    """`prose` is one sentence and it is the only unlabelled block. Between two
    labelled ones there was no way to see where `proof` ended and it began."""
    back = notetype.spec(config.note_type)["cardTemplates"][0]["Back"]
    assert back.index("{{Prose}}") < back.index("{{Uses}}") < back.index("{{Proof}}")

    order = list(model.SECTION_ORDER)
    assert order.index("prose") < order.index("uses") < order.index("proof")


def test_reordering_sections_costs_no_approval(config: Config, card_path: Path) -> None:
    """`content_hash` sorts sections by name, so the reading order is free to
    change without re-reviewing the deck."""
    card = model.load(card_path)
    before = card.content_hash()
    card.sections = list(reversed(card.sections))
    assert card.content_hash() == before


def test_a_layout_change_is_reported_rather_than_pushed(config: Config, card_path: Path) -> None:
    """The template is yours to edit in Anki too, so a content sync must not
    quietly overwrite it. Saying nothing was the wrong other half: a layout
    change here simply never arrived."""
    approve(card_path)
    anki = FakeAnki()
    sync.run(config, client=anki)
    anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"] = "edited in Anki"

    report = sync.run(config, client=anki)

    assert anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"] == "edited in Anki"
    assert any("--templates" in (o.detail or "") for o in report.outcomes)


def test_templates_pushes_the_layout(config: Config, card_path: Path) -> None:
    approve(card_path)
    anki = FakeAnki()
    sync.run(config, client=anki)
    anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"] = "stale"

    sync.run(config, client=anki, templates=True)

    live = anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"]
    assert live.index("{{Prose}}") < live.index("{{Proof}}")
    assert anki.css[config.note_type] == notetype.CSS


def test_a_dry_run_pushes_no_template(config: Config, card_path: Path) -> None:
    approve(card_path)
    anki = FakeAnki()
    sync.run(config, client=anki)
    anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"] = "stale"

    sync.run(config, client=anki, templates=True, dry_run=True)

    assert anki.templates[config.note_type][notetype.CARD_TEMPLATE]["Back"] == "stale"


# -- which deck, and what happens when it changes ---------------------------


def zotero_source(repo: Path, key: str = "T7QDISXB", title: str = "A  Paper") -> Config:
    """A source with a Zotero key on it, which is what `forge zotero` writes."""
    folder = repo / "sources" / "paper"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.toml").write_text(
        f'title = "{title}"\ncitation = "Paper"\nzotero = "{key}"\n', encoding="utf-8"
    )
    return config_mod.load(repo)


def test_an_imported_source_lands_under_its_own_deck(repo: Path) -> None:
    """A shelf you are reading through is not the deck you have decided to
    keep, and one parent is what makes an import studiable or removable in one
    move. `::` is Anki's separator, so a title carrying one would nest a level
    nobody asked for, and a doubled space is a deck name you mistype once."""
    config = zotero_source(repo, title="A  Paper:: With Punctuation")

    assert config.deck_for("paper") == "Zotero::A Paper: With Punctuation"


def test_a_source_that_names_a_deck_keeps_it(repo: Path) -> None:
    """The default is a default. Naming one is how you say this book belongs
    beside what you already study rather than beside what you have imported."""
    folder = repo / "sources" / "paper"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.toml").write_text(
        'title = "A Paper"\ncitation = "Paper"\nzotero = "T7QDISXB"\n'
        'deck = "Mathe::Concentration"\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)

    assert config.deck_for("paper") == "Mathe::Concentration"


def test_a_source_that_did_not_come_from_zotero_is_untouched(config: Config) -> None:
    """Segmented from a file on disk, so there is nothing to file under an
    importer's name. It takes the repo default as it always has."""
    assert config.deck_for("demo") == config.deck


def test_a_new_card_goes_to_the_deck_the_source_asks_for(repo: Path) -> None:
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()

    sync.run(config, client=anki)

    assert next(iter(anki.notes.values()))["deck"] == "Zotero::A Paper"
    assert "Zotero::A Paper" in anki.decks


def test_a_deck_change_is_reported_rather_than_applied(repo: Path) -> None:
    """Anki settles a deck when the note is added and never again, so editing
    the setting moved nothing and the only symptom was one source spread over
    two decks, noticed weeks later."""
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()
    sync.run(config, client=anki)

    folder = repo / "sources" / "paper" / "source.toml"
    folder.write_text(
        folder.read_text(encoding="utf-8") + 'deck = "Mathe::Concentration"\n',
        encoding="utf-8",
    )
    report = sync.run(config_mod.load(repo), client=anki)

    said = [o for o in report.outcomes if o.uid == "aaa111"]
    assert any("Zotero::A Paper" in o.detail and "Mathe::Concentration" in o.detail
               for o in said), report.format()
    assert any("--move-decks" in o.detail for o in said)
    assert next(iter(anki.notes.values()))["deck"] == "Zotero::A Paper", "nothing moved"


def test_move_decks_files_them_under_the_new_name(repo: Path) -> None:
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()
    sync.run(config, client=anki)
    folder = repo / "sources" / "paper" / "source.toml"
    folder.write_text(
        folder.read_text(encoding="utf-8") + 'deck = "Mathe::Concentration"\n',
        encoding="utf-8",
    )

    report = sync.run(config_mod.load(repo), client=anki, move_decks=True)

    assert [o.action for o in report.outcomes if o.uid == "aaa111"] == ["unchanged", "move"]
    assert next(iter(anki.notes.values()))["deck"] == "Mathe::Concentration"


def test_the_summary_counts_what_moved(repo: Path) -> None:
    """Every other action is tallied, and a move was not: you ran the flag and
    the report said nothing about whether it had done anything.

    Only when something moved, though. A line reading "0 move" on every sync
    is a number nobody reads, which is how the one that is not zero is missed.
    """
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()
    first = sync.run(config, client=anki)
    assert "move" not in first.summary(), first.summary()

    folder = repo / "sources" / "paper" / "source.toml"
    folder.write_text(
        folder.read_text(encoding="utf-8") + 'deck = "Mathe::Concentration"\n',
        encoding="utf-8",
    )
    report = sync.run(config_mod.load(repo), client=anki, move_decks=True)

    assert "1 move" in report.summary(), report.summary()


def test_a_report_line_says_which_card_it_is_about(repo: Path) -> None:
    """A uid answers "which file". A report you read to decide whether
    something went wrong is asking "which card", and a column of six hex
    digits answers that only if you look every one of them up."""
    config = zotero_source(repo)
    path = min_card(config, "aaa111", "paper:1:1")
    card = model.load(path)
    card.frontmatter["gist"] = "the predictive posterior"
    card.save()
    approve(path)

    report = sync.run(config, client=FakeAnki())

    line = next(o.format() for o in report.outcomes if o.uid == "aaa111")
    assert "aaa111" in line and "the predictive posterior" in line


def test_a_card_with_no_gist_shows_its_uid_alone(repo: Path) -> None:
    """Honest rather than padded: a card nobody has named has only its uid,
    and seeing that is what sends you to `/gist`."""
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))

    report = sync.run(config, client=FakeAnki())

    line = next(o.format() for o in report.outcomes if o.uid == "aaa111")
    assert line.split() == ["add", "aaa111", "--", "->", "Zotero::A", "Paper"]


def test_a_rehearsal_moves_nothing(repo: Path) -> None:
    """`--dry-run` is a rehearsal whatever else is asked for."""
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()
    sync.run(config, client=anki)
    folder = repo / "sources" / "paper" / "source.toml"
    folder.write_text(
        folder.read_text(encoding="utf-8") + 'deck = "Mathe::Concentration"\n',
        encoding="utf-8",
    )

    sync.run(config_mod.load(repo), client=anki, dry_run=True, move_decks=True)

    assert "changeDeck" not in anki.calls
    assert next(iter(anki.notes.values()))["deck"] == "Zotero::A Paper"


def test_a_deck_that_still_agrees_says_nothing(repo: Path) -> None:
    """The report is for drift. A deck nobody changed is not news."""
    config = zotero_source(repo)
    approve(min_card(config, "aaa111", "paper:1:1"))
    anki = FakeAnki()
    sync.run(config, client=anki)

    report = sync.run(config, client=anki)

    assert not [o for o in report.outcomes if o.action == "move" or "asks for" in o.detail]
