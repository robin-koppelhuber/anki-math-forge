"""Removing a project, and the two bugs that made one necessary.

A project is three things in three places: a folder under `projects/`, a
pile of cards under `cards/`, and a table in `forge.toml`. Deleting one of
them and not the others leaves a project that half exists, which is worse
than the one you meant to remove.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import model, projects
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError


def a_repo(tmp_path: Path, *, declared: bool = False) -> Config:
    """A repo with one project, declared in its own file or in `forge.toml`."""
    toml = '[repo]\nname = "x"\n\n# a comment that has to survive\n'
    if declared:
        toml += '[projects.book]\ntitle = "A Book"\ndeck = "D"\n\n'
        toml += '[[projects.book.sources]]\nurl = "https://x.test/"\n\n'
    toml += '[projects.other]\ntitle = "Another"\n'
    (tmp_path / "forge.toml").write_text(toml, encoding="utf-8")
    (tmp_path / "cards").mkdir()
    folder = tmp_path / "projects" / "book"
    folder.mkdir(parents=True)
    if not declared:
        (folder / "project.toml").write_text('title = "A Book"\n', encoding="utf-8")
    (folder / "units.jsonl").write_text(
        '{"id": "book:1:1", "state": "carded", "locator": {}}\n', encoding="utf-8"
    )
    return config_mod.load(tmp_path)


def a_card(config: Config, uid: str, *, unit: str, folder: str, status: str) -> Path:
    path = config.cards_dir / folder / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: {status}\n"
        f'source: "Somewhere"\nunit: "{unit}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$X$\n\n## back\n$Y$\n",
        encoding="utf-8",
    )
    return path


# -- what a delete takes ----------------------------------------------------


def test_it_takes_the_folder_the_cards_and_the_declaration(tmp_path: Path) -> None:
    config = a_repo(tmp_path, declared=True)
    a_card(config, "aaa111", unit="book:1:1", folder="book", status="draft")

    going = projects.remove(config, "book", force=True)

    assert not (tmp_path / "projects" / "book").exists()
    assert not (tmp_path / "cards" / "book").exists()
    assert going.units == 1 and going.cards == 1
    left = (tmp_path / "forge.toml").read_text(encoding="utf-8")
    assert "[projects.book]" not in left
    assert "[[projects.book.sources]]" not in left, "and the tables under it"
    assert "[projects.other]" in left, "and nothing else"
    assert "# a comment that has to survive" in left


def test_the_toml_keeps_its_comments(tmp_path: Path) -> None:
    """Line-wise, for the reason `scheme.py` gives: a round trip through a
    TOML writer returns a correct file with every comment gone, which is a
    worse file than the one you started with."""
    config = a_repo(tmp_path, declared=True)
    before = (tmp_path / "forge.toml").read_text(encoding="utf-8")

    projects.remove(config, "book")

    after = (tmp_path / "forge.toml").read_text(encoding="utf-8")
    assert "# a comment that has to survive" in after
    assert len(after) < len(before)
    # And it still parses, which is the thing a line-wise edit can get wrong.
    assert "book" not in config_mod.load(tmp_path).projects


def test_a_project_with_cards_is_refused_unless_forced(tmp_path: Path) -> None:
    """A project with no cards is a decision you can make again in one
    command. One with cards in it is review time, and a control that can
    destroy that on a mis-click is the wrong shape whatever it is labelled."""
    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="book:1:1", folder="book", status="approved")

    with pytest.raises(ConfigError) as caught:
        projects.remove(config, "book")

    assert "1 card" in str(caught.value)
    assert "approved" in str(caught.value), "and that it is already in Anki"
    assert (tmp_path / "projects" / "book").exists(), "nothing taken"

    projects.remove(config, "book", force=True)
    assert not (tmp_path / "projects" / "book").exists()


def test_units_alone_are_not_a_gate(tmp_path: Path) -> None:
    """They are derived from a document, and `extract` writes them again."""
    config = a_repo(tmp_path)

    going = projects.remove(config, "book")

    assert going.units == 1
    assert not (tmp_path / "projects" / "book").exists()


def test_a_dry_run_takes_nothing(tmp_path: Path) -> None:
    config = a_repo(tmp_path, declared=True)

    going = projects.removal(config, "book")

    assert going.folder is not None and going.declared
    assert (tmp_path / "projects" / "book").exists()
    assert "[projects.book]" in (tmp_path / "forge.toml").read_text(encoding="utf-8")


def test_deleting_something_that_is_not_there_says_so(tmp_path: Path) -> None:
    """Reported as success, "removed nothing" is how you find out a week
    later that you deleted the wrong one and never noticed."""
    config = a_repo(tmp_path)

    with pytest.raises(ConfigError, match="no project called"):
        projects.remove(config, "ghost")


def test_a_name_is_a_folder_and_never_a_path(tmp_path: Path) -> None:
    """This function ends in `rmtree`."""
    config = a_repo(tmp_path)

    for bad in ("", "..", "../..", "a/b", "..\\..", "."):
        with pytest.raises(ConfigError):
            projects.remove(config, bad)
    assert (tmp_path / "projects").is_dir()


def test_it_counts_what_anki_already_has(tmp_path: Path) -> None:
    """Nothing local records a note id, so an approved card that goes here
    leaves a note there. The number is the whole of what can be said."""
    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="book:1:1", folder="book", status="approved")
    a_card(config, "bbb222", unit="book:1:1", folder="book", status="draft")

    going = projects.removal(config, "book")

    assert going.cards == 2
    assert going.approved == 1


# -- from the app -----------------------------------------------------------


def test_the_app_removes_an_empty_project(tmp_path: Path) -> None:
    config = a_repo(tmp_path)
    client = TestClient(create_app(config))

    answer = client.delete("/api/projects/book")

    assert answer.status_code == 200
    assert answer.json()["project"] == "book"
    assert not (tmp_path / "projects" / "book").exists()


def test_the_app_never_forces(tmp_path: Path) -> None:
    """The override is a flag you type in a terminal. Thirty-nine cards is
    weeks of review, and the web has no second button for it."""
    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="book:1:1", folder="book", status="approved")
    client = TestClient(create_app(config))

    answer = client.delete("/api/projects/book")

    assert answer.status_code == 400
    assert "--force" in answer.json()["detail"]
    assert (tmp_path / "projects" / "book").exists()


def test_the_control_asks_you_to_type_the_name(tmp_path: Path) -> None:
    """The mistake worth making impossible is removing the wrong project
    because two of them start with the same word."""
    config = a_repo(tmp_path)
    page = TestClient(create_app(config)).get("/setup?project=book").text

    assert 'id="drop-project"' in page
    assert 'id="drop-name"' in page
    assert "disabled" in page[page.index('id="drop-project"') :][:900]


# -- the two bugs that sent us here -----------------------------------------


def test_a_name_that_is_mostly_punctuation_keeps_its_meaning(tmp_path: Path) -> None:
    """`c++` slugged to `c`, which is another language, and the project was
    silently created under that name."""
    assert model.slugify("c++") == "cpp"
    assert model.slugify("the C++ standard library") == "the-cpp-standard-library"
    assert model.slugify("C#") == "c-sharp"
    assert model.slugify("a+b") == "a-b", "a plus between two things is not a name"

    config = a_repo(tmp_path)
    made = projects.scaffold(config, "c++", deck="CS::cpp")

    assert made == "cpp"
    assert (tmp_path / "projects" / "cpp" / "project.toml").exists()
    assert 'title = "c++"' in (
        tmp_path / "projects" / "cpp" / "project.toml"
    ).read_text(encoding="utf-8"), "the folder is a slug, the title is what you typed"


def test_a_card_with_no_unit_does_not_haunt_every_project(tmp_path: Path) -> None:
    """It used to belong to all of them, so that it would be visible
    somewhere rather than lost. With one book that was right; with a shelf
    of projects it meant an unfiled card showed up in a project created a
    minute ago with nothing in it."""
    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="", folder="book", status="approved")
    projects.scaffold(config, "empty")
    client = TestClient(create_app(config_mod.load(tmp_path)))

    fresh = client.get("/review?project=empty&status=all").text
    home = client.get("/review?project=book&status=all").text

    assert "aaa111" not in fresh, "not in a project that has nothing in it"
    assert "aaa111" in home, "and still visible where it is filed"


def test_a_card_filed_nowhere_is_still_visible(tmp_path: Path) -> None:
    """The rule the old one was written for survives: a card directly in
    `cards/`, naming no unit, is filed nowhere and has to show up somewhere
    rather than be lost."""
    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="", folder=".", status="draft")
    client = TestClient(create_app(config))

    assert "aaa111" in client.get("/review?project=book&status=all").text


def test_check_says_which_card_is_unfiled(tmp_path: Path) -> None:
    """A warning, like `source-missing`: the card is fine, it just cannot
    say which project it belongs to, so it takes the repo's defaults."""
    from anki_math_forge import check

    config = a_repo(tmp_path)
    a_card(config, "aaa111", unit="", folder="book", status="draft")

    _, findings = check.check_repo(config)
    unfiled = [f for f in findings if f.code == "unit-missing"]

    assert len(unfiled) == 1
    assert unfiled[0].level == check.WARN
