"""The whole pipeline, once, in order.

Every other file here tests one hop. This one walks a PDF all the way to an
approved note in Anki and back again, because the hops are where this tool
actually breaks: a field one stage writes and the next stage does not read, a
setting that survives its own test and is dropped by the stage after it, an
id that means one thing to the ledger and another to a card.

It is deliberately one long test per journey rather than many small ones. The
order *is* the subject, and a failure halfway is worth more than a green tick
on a stage that nothing reached.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anki_math_forge import check, cli, feedback, model, sync
from anki_math_forge import config as config_mod
from anki_math_forge.app import create_app
from anki_math_forge.config import CHAPTER, Config
from anki_math_forge.ledger import Ledger
from conftest import FakeAnki


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def only_unit(config: Config, source: str = "book") -> str:
    return next(iter(Ledger.load(config.units_path(source)))).id


# -- the journey a card actually makes --------------------------------------


def test_a_pdf_becomes_an_approved_note_and_a_comment_comes_back(
    pdf_source: Config,
) -> None:
    """Extract, triage, write, check, approve, sync, and the one flow back.

    The stages are separate commands on purpose (nothing is a pipeline you
    cannot stop halfway), which is exactly why they have to be tested joined
    up: each one reads what the last one wrote off disk, and nothing in a
    single-stage test says the two spellings agree.
    """
    repo = pdf_source.root

    # -- extract: geometry, never cards (invariant 3) ----------------------
    assert run(repo, "extract", "book") == 0
    ledger = Ledger.load(pdf_source.units_path("book"))
    assert len(list(ledger)) > 0
    assert all(u.state == "new" for u in ledger), "a unit arrives untriaged"
    assert not list(pdf_source.cards_dir.rglob("*.md")), "extraction writes no cards"

    unit_id = only_unit(pdf_source)

    # -- triage: a decision, and a brief for whoever writes the card -------
    assert run(repo, "units", "--id", unit_id, "--set-state", "queued") == 0
    assert run(repo, "units", "--id", unit_id, "--annotate", "state the condition") == 0
    assert run(repo, "units", "--id", unit_id, "--context-pages", "chapter") == 0
    assert run(repo, "units", "--id", unit_id, "--web", "yes") == 0

    queued = Ledger.load(pdf_source.units_path("book")).get(unit_id)
    assert queued.state == "queued"
    assert queued.context_pages == CHAPTER
    assert queued.web is True

    # -- context: what the writer is handed --------------------------------
    from anki_math_forge import context as context_mod

    handed = context_mod.assemble(pdf_source, unit_id)
    assert handed is not None
    said = handed.format()
    assert "state the condition" in said, "the brief reaches the next pass"
    assert "Web research is ALLOWED" in said, "and so does the permission"
    assert "chapter" in handed.window or "whole document" in handed.window

    # -- write: a draft, never an approval ---------------------------------
    assert (
        run(
            repo,
            "new",
            "--unit",
            unit_id,
            "--front",
            "$\\frac{d}{dX}\\log\\det X$",
            "--back",
            "$X^{-\\top}$",
            "--gist",
            "the log-det derivative",
        )
        == 0
    )
    written = list(pdf_source.cards_dir.rglob("*.md"))
    assert len(written) == 1
    card = model.load(written[0])
    assert card.status == "draft", "nothing reaches Anki without a human (invariant 1)"
    assert card.unit == unit_id

    # -- check: clean before anything is approved --------------------------
    _, findings = check.check_repo(pdf_source)
    assert not check.errors(findings), [f.format() for f in findings]

    # -- approve: through the app, because the app is a view over files ----
    client = TestClient(create_app(pdf_source))
    mtime = str(written[0].stat().st_mtime_ns)
    approved = client.post(f"/api/cards/{card.uid}/approve", json={"mtime": mtime})
    assert approved.status_code == 200
    on_disk = model.load(written[0])
    assert on_disk.status == "approved"
    assert on_disk.content_hash() == on_disk.frontmatter["content_hash"], (
        "approving stamps the hash of what was reviewed"
    )

    # -- sync: a rehearsal writes nothing ----------------------------------
    anki = FakeAnki()
    rehearsal = sync.run(pdf_source, client=anki, dry_run=True)
    assert not check.errors(rehearsal.findings), rehearsal.findings
    assert anki.notes == {}, "a dry run is a rehearsal"

    report = sync.run(pdf_source, client=anki, dry_run=False)
    assert not check.errors(report.findings), report.findings
    assert [o.action for o in report.outcomes if o.uid == card.uid] == ["add"]
    assert len(anki.notes) == 1
    note = next(iter(anki.notes.values()))
    assert note["fields"]["uid"] == card.uid
    assert "\\(X^{-\\top}\\)" in note["fields"]["Back"], "maths arrives as MathJax"

    # -- again: the same deck is a no-op -----------------------------------
    again = sync.run(pdf_source, client=anki, dry_run=False)
    assert [o.action for o in again.outcomes if o.uid == card.uid] == ["unchanged"]

    # -- feedback: the one flow back, and it erases what it takes ----------
    anki.set_feedback(card.uid, "the sign is wrong")
    imported = feedback.run(pdf_source, client=anki)
    assert [c.kind for c in imported.imported] == ["field"]
    back = model.load(written[0])
    assert back.annotations() == ["@claude the sign is wrong"]
    assert back.status == "approved", "the approval is held, not withdrawn"
    assert back.effective_status == "draft", "but it does not sync while a note is open"
    assert back.demotion == "annotated"

    # -- and an open note keeps it out of Anki -----------------------------
    # Skipped rather than reported as a finding: the card never reaches the
    # lint, because "not ready" here is mechanical and decided first.
    held = sync.run(pdf_source, client=anki, dry_run=True)
    said = [(o.action, o.detail) for o in held.outcomes if o.uid == card.uid]
    assert ("skip", "open @claude annotation") in said
    # And it says the note is already in Anki and no longer matches, which is
    # the half of the situation the card file cannot tell you.
    assert any("no longer approved" in detail for _, detail in said)

    # -- resolve: the edit is the resolution -------------------------------
    resolved = model.load(written[0])
    resolved.resolve_annotation(0)
    resolved.save()
    assert model.load(written[0]).effective_status == "approved", (
        "resolving restores the approval with no re-review"
    )
    after = sync.run(pdf_source, client=anki, dry_run=False)
    assert [o.action for o in after.outcomes if o.uid == card.uid] == ["unchanged"]


def test_a_figure_travels_the_same_road_and_arrives_as_a_picture(
    pdf_source: Config,
) -> None:
    """The same journey for a card whose answer is a figure.

    A picture is the one kind of content that is not in the card file: the
    card names a unit and the crop is rendered on the way out. So the
    stage-to-stage question is sharper here than anywhere else, and the answer
    has to be the same bytes in the browser and in Anki.
    """
    repo = pdf_source.root
    assert run(repo, "extract", "book") == 0
    unit_id = only_unit(pdf_source)
    assert run(repo, "units", "--id", unit_id, "--set-state", "queued") == 0

    card_path = pdf_source.cards_dir / "figure.md"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(
        "---\nuid: f19a3e\ntype: intuition\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: false\n---\n\n'
        "## front\nWhat does the figure on this page show?\n\n"
        "## back\n![the figure](unit)\n",
        encoding="utf-8",
    )

    # -- check has an opinion about a picture it cannot draw ---------------
    _, findings = check.check_repo(pdf_source)
    assert not [f for f in findings if f.code.startswith("image-")], (
        "the unit is here, it has geometry, and the document is on disk"
    )

    # -- the app shows what sync will upload -------------------------------
    body = TestClient(create_app(pdf_source)).get("/review?project=book&status=draft").text
    assert 'class="card-image"' in body
    assert "marks=false" in body, "no frame painted round the figure"
    assert 'class="badge image"' in body

    # -- sync renders the bytes and names them after the card --------------
    card = model.load(card_path)
    card.approve()
    card.save()
    anki = FakeAnki()
    report = sync.run(pdf_source, client=anki, dry_run=False)

    assert not check.errors(report.findings), report.findings
    assert "forge-f19a3e-0.png" in anki.media
    note = next(iter(anki.notes.values()))
    assert note["fields"]["Back"] == '<img src="forge-f19a3e-0.png" alt="the figure">'

    from base64 import b64decode

    assert b64decode(anki.media["forge-f19a3e-0.png"])[:4] == b"\x89PNG"


def test_a_broken_picture_stops_at_the_gate(pdf_source: Config) -> None:
    """Invariant 1 applied to media. The failure this pins is the slow one:
    the card was fine when it was approved, the document moved later, and
    without the gate Anki quietly shows a broken image on a card you trust."""
    repo = pdf_source.root
    assert run(repo, "extract", "book") == 0
    unit_id = only_unit(pdf_source)
    path = pdf_source.cards_dir / "figure.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: f19a3e\ntype: intuition\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: false\n---\n\n'
        "## front\nWhat does it show?\n\n## back\n![the figure](unit)\n",
        encoding="utf-8",
    )
    card = model.load(path)
    card.approve()
    card.save()

    (repo / "projects" / "book" / "book.pdf").unlink()

    anki = FakeAnki()
    report = sync.run(pdf_source, client=anki, dry_run=False)

    assert any(f.code == "image-document-missing" for f in report.findings)
    assert anki.notes == {}, "nothing was pushed"
    assert anki.media == {}, "and nothing was uploaded"


# -- the settings that have to survive the hops -----------------------------


def test_a_window_set_at_triage_is_the_window_the_writer_reads_in(
    pdf_source: Config,
) -> None:
    """`context_pages` is written by one command, stored by a second and read
    by a third. It has been three spellings of the same idea at once before."""
    repo = pdf_source.root
    run(repo, "extract", "book")
    unit_id = only_unit(pdf_source)

    for asked, expect in (("3", 3), ("chapter", CHAPTER), ("-1", None)):
        assert run(repo, "units", "--id", unit_id, "--context-pages", asked) == 0
        stored = Ledger.load(pdf_source.units_path("book")).get(unit_id)
        assert stored.context_pages == expect, asked
        # And the app agrees about what is in force, which is the third
        # reader of the same field. Through the units view rather than an API:
        # the chip is what a person actually reads the setting off.
        body = TestClient(create_app(pdf_source)).get("/units?project=book&state=all").text
        chip = body[body.index("data-context-chip") : body.index("data-web-chip")]
        whose = chip[chip.index('class="chip-whose"') :][:60]
        if expect == CHAPTER:
            assert "the chapter it is in" in chip
            assert "this unit" in whose
        elif expect == 3:
            assert "3 pages either side" in chip
            assert "this unit" in whose
        else:
            assert "project" in whose, "cleared, so the project decides again"


def test_a_re_extraction_does_not_undo_a_judgement(pdf_source: Config) -> None:
    """Re-segmenting is how a wrong box is fixed, and it must not cost the
    triage that was done while looking at it. `state`, the brief, the window
    and the web grant are all human-owned."""
    repo = pdf_source.root
    run(repo, "extract", "book")
    unit_id = only_unit(pdf_source)
    run(repo, "units", "--id", unit_id, "--set-state", "queued")
    run(repo, "units", "--id", unit_id, "--annotate", "two cards, one per case")
    run(repo, "units", "--id", unit_id, "--context-pages", "chapter")
    run(repo, "units", "--id", unit_id, "--web", "yes")

    assert run(repo, "extract", "book") == 0

    again = Ledger.load(pdf_source.units_path("book")).get(unit_id)
    assert again.state == "queued"
    assert again.notes == ["@claude two cards, one per case"]
    assert again.context_pages == CHAPTER
    assert again.web is True


def test_editing_an_approved_card_sends_it_back_and_fixing_it_restores_it(
    pdf_source: Config,
) -> None:
    """Invariant 5, over the whole road: the demotion is derived from the
    content, so nothing has to rewrite the file to enforce it and putting the
    content back is enough to get the approval back."""
    run(pdf_source.root, "extract", "book")
    unit_id = only_unit(pdf_source)
    path = pdf_source.cards_dir / "one.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: ab99cd\ntype: identity\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n",
        encoding="utf-8",
    )
    card = model.load(path)
    card.approve()
    card.save()
    assert model.load(path).effective_status == "approved"

    edited = model.load(path)
    edited.set_section("back", "$c$")
    edited.save()
    assert model.load(path).effective_status == "draft"
    assert model.load(path).demotion == "edited"

    back = model.load(path)
    back.set_section("back", "$b$")
    back.save()
    assert model.load(path).effective_status == "approved", "no re-approval needed"


def test_the_app_and_the_files_never_disagree(pdf_source: Config) -> None:
    """Invariant 2. The app caches nothing and re-reads per request, so a card
    changed in an editor is the card the next request serves."""
    run(pdf_source.root, "extract", "book")
    unit_id = only_unit(pdf_source)
    path = pdf_source.cards_dir / "one.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: ab99cd\ntype: identity\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(pdf_source))
    assert "ab99cd" in client.get("/review?project=book&status=draft").text

    edited = model.load(path)
    edited.set_section("prose", "written in an editor, not in the app")
    edited.save()

    assert "written in an editor" in client.get("/review?project=book&status=draft").text


def test_the_checks_a_deck_can_run_on_itself(pdf_source: Config) -> None:
    """`audit` and `verify` are the two commands that answer "is what I have
    right", and neither is on the road to Anki: nothing calls them for you, so
    they are exactly the ones that quietly stop working.

    Run over a deck the rest of this file builds rather than over a fixture
    made for them, which is the only way the answer means anything.
    """
    repo = pdf_source.root
    run(repo, "extract", "book")
    unit_id = only_unit(pdf_source)
    path = pdf_source.cards_dir / "verified.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: cc44dd\ntype: identity\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: true\n---\n\n'
        "## front\n$\\operatorname{tr}(AB)$\n\n"
        "## back\n$\\operatorname{tr}(BA)$\n\n"
        "## verify\n```python\n"
        "A = randn(4, 4)\n"
        "B = randn(4, 4)\n"
        "lhs = float(np.trace(A @ B))\n"
        "rhs = float(np.trace(B @ A))\n"
        "```\n",
        encoding="utf-8",
    )

    # -- the index is trustworthy ------------------------------------------
    assert run(repo, "audit", "--json") == 0

    # -- and the mathematics holds under random input ----------------------
    assert run(repo, "verify") == 0, "a true identity passes"

    # A card claiming something false has to fail, or the whole pass is
    # decoration: it caught three errors in the Cookbook by being able to.
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "rhs = float(np.trace(B @ A))",
            "rhs = float(np.trace(A) * np.trace(B))",
        ),
        encoding="utf-8",
    )
    assert run(repo, "verify") != 0, "and a false one fails"


def test_a_source_that_is_not_there_is_reported_not_guessed(pdf_source: Config) -> None:
    """Every verb takes a source name, and a typo in one is the cheapest
    mistake to make. It has to say so rather than acting on everything."""
    assert run(pdf_source.root, "extract", "nosuchbook") != 0


# -- the settings and records added this round ------------------------------


def test_an_imported_source_carries_its_own_deck_all_the_way(repo: Path) -> None:
    """A Zotero import lands under `Zotero::<title>`, and changing that later
    is reported rather than silently splitting the source across two decks.

    Every hop matters here: the key is written by the importer, read by the
    config, used by `sync` when the note is created, and compared against the
    collection on every sync after that.
    """
    folder = repo / "projects" / "paper"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("project.toml").write_text(
        'title = "A  Paper:: On Tails"\ncitation = "Paper"\nzotero = "T7QDISXB"\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)
    # `::` would nest a level nobody asked for; the double space is a name you
    # mistype once and then wonder about.
    assert config.deck_for("paper") == "Zotero::A Paper: On Tails"

    path = repo / "cards" / "aa11bb-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: aa11bb\ntype: identity\nstatus: draft\n"
        'source: "Paper"\nunit: "paper:1:1"\ngist: a tail bound\n'
        "tags: []\nverify: false\n---\n\n## front\n$a$\n\n## back\n$b$\n",
        encoding="utf-8",
    )
    card = model.load(path)
    card.approve()
    card.save()

    anki = FakeAnki()
    added = sync.run(config, client=anki, dry_run=False)

    assert next(iter(anki.notes.values()))["deck"] == "Zotero::A Paper: On Tails"
    # The report names the card rather than only its file.
    assert any("a tail bound" in o.format() for o in added.outcomes)

    # -- and when the deck changes under it --------------------------------
    toml = folder / "project.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8") + 'deck = "Mathe::Tails"\n', encoding="utf-8"
    )
    told = sync.run(config_mod.load(repo), client=anki, dry_run=False)

    assert any("--move-decks" in o.detail for o in told.outcomes)
    assert next(iter(anki.notes.values()))["deck"] == "Zotero::A Paper: On Tails"
    assert "move" not in told.summary(), "a report of nothing moved says nothing"

    moved = sync.run(config_mod.load(repo), client=anki, dry_run=False, move_decks=True)

    assert next(iter(anki.notes.values()))["deck"] == "Mathe::Tails"
    assert "1 move" in moved.summary()


def test_a_note_settled_by_a_pass_is_still_readable_afterwards(
    pdf_source: Config,
) -> None:
    """The record a resolved annotation leaves, from the file through the app.

    The point is the second half: it must not queue as work, must not hold the
    card out of sync, and must not be mistaken for the prose that invariant 7
    puts in the same section.
    """
    from anki_math_forge.app import _card_payload

    run(pdf_source.root, "extract", "book")
    unit_id = only_unit(pdf_source)
    path = pdf_source.cards_dir / "settled.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: cc55dd\ntype: identity\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n\n"
        "## notes\n\nThe source states this only for symmetric X.\n",
        encoding="utf-8",
    )

    # A human asks, a pass answers.
    card = model.load(path)
    card.add_annotation("@claude check the sign on the second term")
    card.save()
    assert model.load(path).annotations(), "open, and holding the card"

    answered = model.load(path)
    answered.resolve_annotation(0, "the sign was right; the condition it needs is stated")
    answered.approve()
    answered.save()

    settled = model.load(path)
    assert settled.annotations() == [], "nothing left queued as work"
    assert settled.effective_status == "approved", "and nothing holding it back"
    assert len(settled.resolved()) == 1

    # `sync` takes it, and the record reaches no field.
    anki = FakeAnki()
    report = sync.run(pdf_source, client=anki, dry_run=False)
    assert [o.action for o in report.outcomes if o.uid == "cc55dd"] == ["add"]
    fields = next(iter(anki.notes.values()))["fields"]
    assert not [v for v in fields.values() if "the sign was right" in v]

    # And the view keeps the three kinds of note apart.
    payload = _card_payload(settled, [], pdf_source)
    assert payload["plain_notes"] == "The source states this only for symmetric X."
    assert payload["annotations"] == []
    assert payload["resolved"] == [
        "check the sign on the second term \u2014 "
        "the sign was right; the condition it needs is stated"
    ]


def test_the_window_the_picture_and_the_record_coexist_on_one_card(
    pdf_source: Config,
) -> None:
    """Everything added this round on a single card, because each one writes
    to a different part of the same two files and the combination is what is
    never tested by a feature's own tests."""
    run(pdf_source.root, "extract", "book")
    unit_id = only_unit(pdf_source)
    run(pdf_source.root, "units", "--id", unit_id, "--context-pages", "chapter")

    path = pdf_source.cards_dir / "everything.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: ee77ff\ntype: intuition\nstatus: draft\n"
        f'source: "A Book"\nunit: "{unit_id}"\ngist: the figure and its caption\n'
        "tags: []\nverify: false\n---\n\n"
        "## front\n\nWhat does the figure show?\n\n"
        "## back\n\n![the figure](unit)\n\n"
        "## notes\n\n@claude is the crop the right one?\n",
        encoding="utf-8",
    )

    # The brief reaches the pass, in the window the unit asked for.
    from anki_math_forge import context as context_mod

    handed = context_mod.assemble(pdf_source, unit_id)
    assert handed is not None
    assert "chapter" in handed.window or "whole document" in handed.window

    # The picture is gated before it can reach Anki, and passes.
    _, findings = check.check_repo(pdf_source)
    assert not [f for f in findings if f.code.startswith("image-")]

    # The note holds the card, and settling it releases it.
    card = model.load(path)
    card.resolve_annotation(0, "yes, the box is the figure and its caption")
    card.approve()
    card.save()

    anki = FakeAnki()
    report = sync.run(pdf_source, client=anki, dry_run=False)

    assert not check.errors(report.findings), report.findings
    assert "forge-ee77ff-0.png" in anki.media
    note = next(iter(anki.notes.values()))
    assert note["fields"]["Back"] == '<img src="forge-ee77ff-0.png" alt="the figure">'
    assert any("the figure and its caption" in o.format() for o in report.outcomes), (
        "the report names the card, not only its file"
    )
