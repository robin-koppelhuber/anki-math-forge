"""A project with no book behind it, walked all the way to Anki.

The rest of the pipeline was built around a document: a segmenter finds
units, a crop settles what they say, a page of prose surrounds them. A
project on a subject has none of that, and the claim the whole of ROADMAP.md
10 rests on is that *only the first layer changes* -- that a unit proposed
rather than segmented goes through triage, carding, checking, approval and
sync exactly like any other.

This is that claim as a test. It is one long journey rather than many small
ones, because the hops are where it would break: a field the proposing door
writes and `context` does not read, a card with code that `check` refuses, a
deck routed off a tag that the content hash then un-approves.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import check, cli, model, sync
from anki_math_forge import config as config_mod
from anki_math_forge.context import assemble
from anki_math_forge.ledger import Ledger
from conftest import FakeAnki


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def a_project(repo: Path) -> None:
    """A project that declares no source at all: no pdf, no tex, no Zotero
    item. Under the old shape there was no way to say this."""
    folder = repo / "projects" / "cpp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.toml").write_text(
        'title = "Modern C++"\ncitation = "cppreference"\ndeck = "Cpp"\n',
        encoding="utf-8",
    )
    (folder / "references.md").write_text(
        "# References\n\n- cppreference, the container library overview.\n",
        encoding="utf-8",
    )
    (folder / "conventions.md").write_text(
        "# Conventions\n\nC++20 unless a card says otherwise.\n", encoding="utf-8"
    )


def test_a_proposed_subject_becomes_an_approved_note(repo: Path) -> None:
    a_project(repo)
    config = config_mod.load(repo)
    assert config.project("cpp").sources == (), "a project may read nothing"
    assert config.project("cpp").source() is None

    # -- propose: a subject, never a draft ---------------------------------
    assert (
        run(
            repo,
            "units",
            "--project",
            "cpp",
            "--add",
            "vector erase-remove",
            "--gist",
            "erase-remove on a vector",
            "--preview",
            "v.erase(std::remove(...), v.end());",
            "--lang",
            "cpp",
            "--ref",
            "https://en.cppreference.com/w/cpp/algorithm/remove",
            "--tag",
            "containers",
        )
        == 0
    )
    unit_id = "cpp:vector-erase-remove"
    unit = Ledger.load(config.units_path("cpp")).get(unit_id)
    assert unit is not None
    assert unit.state == "new", "every unit arrives new, whichever door it came in by"
    assert unit.uids == [], "and carries no card"

    # -- triage: the same keystroke as any other unit ----------------------
    assert run(repo, "units", "--id", unit_id, "--set-state", "queued") == 0
    assert Ledger.load(config.units_path("cpp")).get(unit_id).state == "queued"  # type: ignore[union-attr]

    # -- context: says there is no page, and hands over what there is ------
    handed = assemble(config, unit_id)
    assert handed is not None
    said = handed.format()
    assert handed.settled is False
    assert "no authoritative source" in said, "the writer is told what it does not have"
    assert "https://en.cppreference.com/w/cpp/algorithm/remove" in said
    assert "cppreference, the container library overview." in said, "the project's shelf"
    assert "C++20 unless a card says otherwise." in said, "and what is ambient here"
    assert "```cpp" in said, "the preview is fenced in its own language"

    # -- write: a card carrying code ---------------------------------------
    body = (
        "```cpp\n"
        "auto it = std::remove(v.begin(), v.end(), x);\n"
        "v.erase(it, v.end());\n"
        "```"
    )
    assert (
        run(
            repo,
            "new",
            "--unit",
            unit_id,
            "--front",
            "How do you erase every $x$ from a `std::vector`?",
            "--back",
            body,
            "--gist",
            "erase-remove on a vector",
            "--tag",
            "containers",
        )
        == 0
    )
    written = list(config.cards_dir.rglob("*.md"))
    assert len(written) == 1
    card = model.load(written[0])
    assert card.status == "draft", "nothing reaches Anki without a human (invariant 1)"

    # -- check: code is not maths ------------------------------------------
    findings = check.check_card(card, config)
    assert not [f for f in findings if f.level == "error"], [f.message for f in findings]
    assert "section-wrapped" not in {f.code for f in findings}

    # -- approve, and re-file it without losing the approval ---------------
    card.approve()
    card.save()
    assert model.load(card.path).effective_status == "approved"

    card = model.load(card.path)
    card.frontmatter["tags"] = ["containers", "idiom"]
    card.save()
    assert model.load(card.path).effective_status == "approved", (
        "filing is not what a reviewer read"
    )

    # -- sync: into the project's deck, with the code rendered -------------
    anki = FakeAnki()
    report = sync.run(config_mod.load(repo), client=anki, dry_run=False)
    assert not [o for o in report.outcomes if o.action == "error"], report.summary()

    note = next(iter(anki.notes.values()))
    assert note["deck"] == "Cpp"
    back = note["fields"]["Back"]
    assert '<pre class="code">' in back, "a fence is a block, not a paragraph of <br>"
    assert "<br>" not in back
    assert "\n" in back, "the newlines inside it are the readable part"
    assert "std" in back and "erase" in back, "and the code itself arrived"
    assert "containers" in note["tags"] and "idiom" in note["tags"]


def test_the_project_is_visible_in_the_app(repo: Path) -> None:
    """The views were written against a project with a document. One with
    none should list, count and open rather than 500."""
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "unique_ptr", "--gist", "owning a pointer")
    client = TestClient(create_app(config_mod.load(repo)))

    rows = client.get("/api/projects").json()["projects"]
    assert "cpp" in {row["name"] for row in rows}

    page = client.get("/units?project=cpp")
    assert page.status_code == 200
    assert "owning a pointer" in page.text
    assert "no crop geometry for this unit" in page.text, (
        "it says there is no picture rather than drawing a broken one"
    )


def test_triage_shows_the_sample_rather_than_nothing(repo: Path) -> None:
    """Every frontend owes something scannable, and a proposed unit has no
    crop and no transcription. Without the sample the view offered nothing to
    decide on, which is the one thing triage is for."""
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    a_project(repo)
    run(
        repo, "units", "--project", "cpp", "--add", "span", "--gist", "a view over a range",
        "--preview", "std::span<int> s{v};", "--lang", "cpp",
    )
    page = TestClient(create_app(config_mod.load(repo))).get("/units?project=cpp")

    assert '<pre class="code">' in page.text, "code is shown as code"
    assert "std::span" in page.text
    assert "$$std::span" not in page.text, "and never handed to KaTeX as a formula"


def test_nothing_about_this_needed_a_kind(repo: Path) -> None:
    """The rule the design rests on: no stage asks what sort of project it is
    looking at. There is no kind to ask about, so the only way a stage could
    branch on one is by inventing it."""
    a_project(repo)
    config = config_mod.load(repo)

    assert not hasattr(config.project("cpp"), "kind")
    # A project that reads nothing and one that reads a book differ only in
    # what they have, which is a question about the sources.
    assert config.project("cpp").sources == ()
    assert config.project("demo").sources != ()
