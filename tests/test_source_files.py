"""A source describes itself, in its own folder.

`sources/<name>/source.md`: TOML between `+++` fences for the keys the tool
acts on, prose below for the conventions a card writer needs. TOML because
every key up there overrides one in `forge.toml`, and a block you copy
between the two files has to work unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import config as config_mod


def write_source(repo: Path, name: str, frontmatter: str, prose: str = "") -> None:
    folder = repo / "sources" / name
    folder.mkdir(parents=True, exist_ok=True)
    body = "+++\n" + frontmatter.strip() + "\n+++\n\n" + prose
    folder.joinpath("source.md").write_text(body, encoding="utf-8")


def add_toml(repo: Path, block: str) -> None:
    path = repo / "forge.toml"
    path.write_text(path.read_text(encoding="utf-8") + "\n" + block, encoding="utf-8")


# -- discovery --------------------------------------------------------------


def test_a_source_is_discovered_from_its_folder(repo: Path) -> None:
    """No listing in the root file. Fifty papers there would be unreadable, and
    a source that has to be registered twice is one that gets forgotten once."""
    write_source(repo, "book", 'title = "A Book"\ndeck = "Shelf::A Book"\ntags = ["paper"]')
    config = config_mod.load(repo)

    assert "book" in config.sources
    assert config.source("book").title == "A Book"
    assert config.deck_for("book") == "Shelf::A Book"
    assert config.source("book").tags == ("paper",)


def test_a_folder_without_a_source_file_is_not_a_source(repo: Path) -> None:
    """Discovery does not guess: a stray directory is not a book."""
    (repo / "sources" / "scratch").mkdir(parents=True, exist_ok=True)
    assert "scratch" not in config_mod.load(repo).sources


def test_the_folder_wins_over_the_root_file(repo: Path) -> None:
    """Both are read, so a repo migrates one source at a time. The file sitting
    next to the document is the one that is right."""
    add_toml(repo, '[sources.book]\ntitle = "Stale"\ndeck = "Old"\norder = "none"\n')
    write_source(repo, "book", 'title = "Current"\ndeck = "New"')

    config = config_mod.load(repo)
    assert config.source("book").title == "Current"
    assert config.deck_for("book") == "New"
    assert config.source("book").order == "none", "keys it does not restate are kept"


def test_a_block_copies_between_the_two_files_unchanged(repo: Path) -> None:
    """The whole argument for TOML over YAML frontmatter: the same text means
    the same thing in the root file and in a source's own."""
    block = 'units_from = ["green"]\n\n[meanings]\ngreen = "a claim"\n'
    add_toml(repo, "[zotero]\n" + block.replace("[meanings]", "[zotero.meanings]"))
    write_source(repo, "book", 'title = "A Book"\n' + block)

    config = config_mod.load(repo)
    assert config.zotero_for("book").units_from == config.zotero.units_from
    assert config.zotero_for("book").means("highlight", "green") == "a claim"


# -- what a bad one does ----------------------------------------------------


def test_frontmatter_that_is_not_toml_is_refused_at_load(repo: Path) -> None:
    write_source(repo, "book", 'title = "unclosed')
    with pytest.raises(config_mod.ConfigError, match="not valid TOML"):
        config_mod.load(repo)


def test_a_tag_named_no_stays_a_string(repo: Path) -> None:
    """The other reason this is TOML. YAML reads `no`, `on` and `y` as
    booleans, so a tag or colour spelled that way would silently stop being
    either one."""
    write_source(repo, "book", 'title = "A Book"\ntags = ["no", "on", "y"]')
    assert config_mod.load(repo).source("book").tags == ("no", "on", "y")


def test_a_source_file_without_frontmatter_is_refused(repo: Path) -> None:
    folder = repo / "sources" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text("# just prose\n", encoding="utf-8")
    with pytest.raises(config_mod.ConfigError, match="no frontmatter"):
        config_mod.load(repo)


def test_an_unclosed_frontmatter_block_is_refused(repo: Path) -> None:
    folder = repo / "sources" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text('+++\ntitle = "A Book"\n', encoding="utf-8")
    with pytest.raises(config_mod.ConfigError, match="never closed"):
        config_mod.load(repo)


def test_a_layout_typo_is_still_refused_from_a_source_file(repo: Path) -> None:
    """The check that matters most has to survive the move: an unrecognised
    layout reads as "not denominator" and silently changes what every card from
    that source means."""
    write_source(repo, "book", 'title = "A Book"\nlayout = "sideways"')
    with pytest.raises(config_mod.ConfigError):
        config_mod.load(repo)


# -- a source reads its own marks -------------------------------------------

REPO_ZOTERO = '[zotero]\nunits_from = ["green"]\n\n[zotero.meanings]\ngreen = "a claim"\n'


def test_zotero_settings_fall_back_to_the_repo(repo: Path) -> None:
    add_toml(repo, REPO_ZOTERO)
    write_source(repo, "book", 'title = "A Book"')

    zotero = config_mod.load(repo).zotero_for("book")
    assert zotero.units_from == frozenset({"green"})
    assert zotero.means("highlight", "green") == "a claim"


def test_a_source_may_read_its_colours_differently(repo: Path) -> None:
    """A scheme drifts between a book read last year and a paper read last
    week, and a scheme that is wrong is worse than none."""
    add_toml(repo, REPO_ZOTERO)
    write_source(
        repo,
        "book",
        'title = "A Book"\nunits_from = ["magenta"]\n\n[meanings]\nmagenta = "a result"',
    )

    config = config_mod.load(repo)
    mine = config.zotero_for("book")
    assert mine.units_from == frozenset({"magenta"})
    assert mine.means("highlight", "magenta") == "a result"
    assert mine.means("highlight", "green") == "", "replaced, not merged"
    assert config.zotero.units_from == frozenset({"green"}), "the repo default is untouched"


def test_the_more_specific_meaning_wins() -> None:
    zotero = config_mod.ZoteroConfig(
        data_dir=Path("/nowhere"),
        meanings={"note/yellow": "my own thought", "yellow": "a citation", "note": "a note"},
    )
    assert zotero.means("note", "yellow") == "my own thought", "kind/colour is most specific"
    assert zotero.means("note", "blue") == "a note", "then the kind"
    assert zotero.means("highlight", "yellow") == "a citation", "then the colour"


# -- and the prose half reaches a card writer -------------------------------


def test_context_reads_the_prose_under_the_frontmatter(repo: Path) -> None:
    """`forge context` prints it, so whoever writes a card sees the right
    conventions without having to know the file exists."""
    from anki_math_forge.context import source_conventions

    write_source(repo, "book", 'title = "A Book"', "# A Book\n\nEntries are real.\n")
    config = config_mod.load(repo)

    prose = source_conventions(config, "book")
    assert "Entries are real." in prose
    assert "title" not in prose, "the frontmatter is for the tool, not the writer"


def test_conventions_still_read_from_the_older_file(repo: Path) -> None:
    """A repo that has not migrated keeps working."""
    from anki_math_forge.context import source_conventions

    folder = repo / "sources" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("conventions.md").write_text("# Old\n\nStill read.\n", encoding="utf-8")
    assert "Still read." in source_conventions(config_mod.load(repo), "book")
