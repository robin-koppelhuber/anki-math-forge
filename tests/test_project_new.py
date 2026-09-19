"""`forge project`: starting one that reads nothing.

A project with a book behind it is created by importing the book, and
`forge zotero` writes its file. One on a subject has nothing to import, so
without this the only way to start is to write the TOML by hand and guess at
the key names.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from anki_math_forge import cli
from anki_math_forge import config as config_mod


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def test_it_writes_a_project_that_loads(repo: Path) -> None:
    assert run(repo, "project", "cpp", "--title", "Modern C++", "--deck", "Cpp") == 0

    path = repo / "projects" / "cpp" / "project.toml"
    assert path.exists()
    spec = config_mod.load(repo).project("cpp")
    assert spec.title == "Modern C++"
    assert spec.deck == "Cpp"


def test_it_declares_no_source_at_all(repo: Path) -> None:
    """The absence is the whole of what "no document" means: there is no kind
    key to set, and nothing asks what sort of project this is."""
    run(repo, "project", "cpp", "--title", "Modern C++")

    spec = config_mod.load(repo).project("cpp")
    assert spec.sources == ()
    assert spec.source() is None


def test_the_commented_example_is_valid_toml(repo: Path) -> None:
    """The file documents `[[sources]]` commented out. Uncommenting the
    documentation must not raise, which is the mistake the Zotero stub made
    once already."""
    run(repo, "project", "cpp")
    path = repo / "projects" / "cpp" / "project.toml"

    # Only the settings, not the prose around them: one of those sentences
    # names `[[sources]]` in passing and would uncomment into nonsense.
    setting = re.compile(r"^# (\[\[sources\]\]|[a-z_]+ = )")
    live = [
        line[2:]
        for line in path.read_text(encoding="utf-8").splitlines()
        if setting.match(line)
    ]
    parsed = tomllib.loads("\n".join(live))

    assert parsed["sources"][0]["url"].startswith("https://")


def test_it_never_overwrites(repo: Path) -> None:
    """Everything in it is a starting point you will edit."""
    run(repo, "project", "cpp", "--title", "Mine")
    path = repo / "projects" / "cpp" / "project.toml"
    path.write_text(path.read_text(encoding="utf-8") + '\norder = "none"\n', encoding="utf-8")

    assert run(repo, "project", "cpp", "--title", "Theirs") == 1
    assert "Mine" in path.read_text(encoding="utf-8")
    assert config_mod.load(repo).project("cpp").order == "none"


def test_the_title_defaults_to_the_name(repo: Path) -> None:
    run(repo, "project", "containers")

    assert config_mod.load(repo).project("containers").title == "containers"


def test_a_name_is_slugified_so_the_id_is_predictable(repo: Path) -> None:
    """The project name is the first segment of every unit id it holds."""
    assert run(repo, "project", "Modern C++") == 0

    assert (repo / "projects" / "modern-c").exists()


@pytest.mark.parametrize("name", ["", "   ", "!!!"])
def test_a_name_that_says_nothing_is_refused(repo: Path, name: str) -> None:
    assert run(repo, "project", name) == 2


def test_you_can_propose_into_it_immediately(repo: Path) -> None:
    """The line the command prints should work as printed."""
    run(repo, "project", "cpp", "--title", "Modern C++")

    assert run(repo, "units", "--project", "cpp", "--add", "spans", "--gist", "a view") == 0
