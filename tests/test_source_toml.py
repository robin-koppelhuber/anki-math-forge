"""`sources/<name>/source.toml`, and `conventions.md` beside it.

They were one file for a while: TOML between `+++` fences, then prose, on the
argument that a convention kept away from the keys it qualifies is the one
nobody opens. What that produced was a file that is neither -- no editor checks
the TOML above the fence *and* renders the Markdown below it, so both halves
lost the tooling they would have had apart. The keys are a config and the
conventions are a document; they are better off being those things.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import config as config_mod
from anki_math_forge.context import source_conventions


def a_repo(tmp_path: Path) -> Path:
    (tmp_path / "forge.toml").write_text("", encoding="utf-8")
    (tmp_path / "sources" / "book").mkdir(parents=True)
    return tmp_path


def test_a_source_is_plain_toml(tmp_path: Path) -> None:
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.toml").write_text(
        'title = "A Book"\ndeck = "Shelf"\n', encoding="utf-8"
    )
    config = config_mod.load(repo)
    assert config.source("book").title == "A Book"
    assert config.deck_for("book") == "Shelf"


def test_the_fenced_form_is_still_read(tmp_path: Path) -> None:
    """A repo should not have to migrate all at once."""
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.md").write_text(
        '+++\ntitle = "An Old Book"\n+++\n\n# An Old Book\n\nDenominator layout.\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)
    assert config.source("book").title == "An Old Book"
    assert "Denominator layout." in source_conventions(config, "book")


def test_where_a_folder_has_both_the_new_file_wins(tmp_path: Path) -> None:
    """The file you are being migrated *to* is the one that should decide."""
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.md").write_text(
        '+++\ntitle = "Old"\n+++\n', encoding="utf-8"
    )
    (repo / "sources" / "book" / "source.toml").write_text('title = "New"\n', encoding="utf-8")
    assert config_mod.load(repo).source("book").title == "New"


def test_conventions_are_their_own_markdown_file(tmp_path: Path) -> None:
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.toml").write_text('title = "A Book"\n', encoding="utf-8")
    (repo / "sources" / "book" / "conventions.md").write_text(
        "# A Book\n\nEverything is real unless a card says otherwise.\n", encoding="utf-8"
    )
    prose = source_conventions(config_mod.load(repo), "book")
    assert "Everything is real" in prose
    assert not prose.startswith("#"), "the title line is the file's, not a convention"


def test_a_source_with_no_conventions_has_no_file(tmp_path: Path) -> None:
    """An absent file is the honest state. A placeholder saying "nothing
    recorded yet" is indistinguishable from a real one to everything that reads
    it, and would silence the warning it should raise."""
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.toml").write_text('title = "A Book"\n', encoding="utf-8")
    assert source_conventions(config_mod.load(repo), "book") == ""


def test_a_folder_with_neither_is_not_a_source(tmp_path: Path) -> None:
    """Discovery is not a guess."""
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "notes.md").write_text("stray\n", encoding="utf-8")
    assert "book" not in config_mod.load(repo).sources


def test_broken_toml_is_refused_by_name(tmp_path: Path) -> None:
    repo = a_repo(tmp_path)
    (repo / "sources" / "book" / "source.toml").write_text("title = \n", encoding="utf-8")
    with pytest.raises(config_mod.ConfigError, match=r"source\.toml"):
        config_mod.load(repo)


def test_the_repo_s_own_sources_have_migrated() -> None:
    """The mechanism is only real if this repo uses it."""
    root = Path(__file__).resolve().parents[1]
    for folder in (root / "sources").iterdir():
        if not folder.is_dir() or not (folder / "units.jsonl").exists():
            continue
        assert (folder / "source.toml").exists(), f"{folder.name} still has only the old file"
        assert not (folder / "source.md").exists(), f"{folder.name} kept a stale source.md"
