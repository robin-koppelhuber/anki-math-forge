"""`units --add`: the door for a frontend that is not a segmenter.

A project with no document cannot be segmented, so a pass proposes subjects
instead. What it owes is the frontend contract and nothing more (ROADMAP.md
10): a stable id, whatever locator it has, something scannable, and
`state: new`. What it must not do is write a card, because the line between
triage and review is that triage decides *whether* and review reads *what*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import cli
from anki_math_forge.ledger import Ledger


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def a_project(repo: Path, name: str = "cpp") -> Path:
    """A project with a deck and no document, which is the whole point."""
    folder = repo / "projects" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n', encoding="utf-8"
    )
    return folder


def test_a_proposal_lands_as_a_new_unit(repo: Path) -> None:
    folder = a_project(repo)
    assert not (folder / "units.jsonl").exists(), "the first proposal has no ledger to join"

    code = run(
        repo,
        "units",
        "--project",
        "cpp",
        "--add",
        "vector erase-remove",
        "--gist",
        "erase-remove on a vector",
        "--preview",
        "v.erase(std::remove(v.begin(), v.end(), x), v.end());",
        "--lang",
        "cpp",
        "--ref",
        "https://en.cppreference.com/w/cpp/algorithm/remove",
        "--tag",
        "containers",
    )

    assert code == 0
    unit = Ledger.load(folder / "units.jsonl").get("cpp:vector-erase-remove")
    assert unit is not None, "the slug is the id, so a re-run can find it again"
    assert unit.state == "new", "every unit arrives new, whichever door it came in by"
    assert unit.gist == "erase-remove on a vector"
    assert unit.tags == ["containers"]
    assert unit.refs == ["https://en.cppreference.com/w/cpp/algorithm/remove"]
    assert unit.scannable == ("v.erase(std::remove(v.begin(), v.end(), x), v.end());", "cpp")


def test_the_unit_carries_no_card(repo: Path) -> None:
    """A proposal is a subject, not a draft. The moment a frontend emits a
    front and a back, triage has become review and the unit stage has no job
    left, so there is nowhere here for one to be written."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "unique_ptr", "--gist", "owning a pointer")

    unit = Ledger.load(repo / "projects" / "cpp" / "units.jsonl").get("cpp:unique-ptr")
    assert unit is not None
    assert unit.uids == [], "no card until somebody queues it and writes one"
    assert not list((repo / "cards").rglob("*.md"))


def test_a_slug_already_there_is_left_alone(repo: Path) -> None:
    """Re-running a request adds only what is new. The unit may have been
    triaged since, and a proposal must not walk over a decision."""
    folder = a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "first")
    run(repo, "units", "--id", "cpp:vector-erase-remove", "--set-state", "queued")

    # Same subject, differently typed: the slug is what settles identity.
    code = run(
        repo, "units", "--project", "cpp", "--add", "Vector Erase-Remove!", "--gist", "second"
    )

    assert code == 0
    led = Ledger.load(folder / "units.jsonl")
    assert len(led) == 1, "one subject, one unit"
    unit = led.get("cpp:vector-erase-remove")
    assert unit is not None
    assert unit.gist == "first", "the proposal did not overwrite what was there"
    assert unit.state == "queued", "nor undo the triage decision"


def test_adding_without_a_project_is_a_misuse(repo: Path) -> None:
    a_project(repo)
    assert run(repo, "units", "--add", "vector erase-remove") == 2


def test_an_unknown_project_is_reported_not_guessed(repo: Path) -> None:
    """Discovery is not a guess. Creating the folder on the way past would
    make a typo into a project."""
    a_project(repo)
    assert run(repo, "units", "--project", "cpp-typo", "--add", "something") == 1
    assert not (repo / "projects" / "cpp-typo").exists()


@pytest.mark.parametrize("slug", ["", "   ", "!!!"])
def test_a_slug_that_says_nothing_is_refused(repo: Path, slug: str) -> None:
    a_project(repo)
    assert run(repo, "units", "--project", "cpp", "--add", slug) == 2


def test_a_project_with_a_document_can_be_proposed_into_too(repo: Path) -> None:
    """Nothing about this door is specific to a project with no document. A
    book you want one extra subject carded from takes the same call."""
    run(repo, "units", "--project", "demo", "--add", "a thought while reading", "--gist", "x")

    led = Ledger.load(repo / "projects" / "demo" / "units.jsonl")
    assert led.get("demo:a-thought-while-reading") is not None
