"""A source describes itself, in its own folder.

This suite covers the **older** fenced form, `projects/<name>/source.md`: TOML
between `+++` fences for the keys, prose below for the conventions. It is still
read, because a repo should not have to migrate all at once -- and everything
asserted here about inheritance, precedence and refusal is the same machinery
`project.toml` uses, so it is worth keeping exercised through both doors.
`test_source_toml.py` covers the current form.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import config as config_mod


def write_source(repo: Path, name: str, frontmatter: str, prose: str = "") -> None:
    folder = repo / "projects" / name
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

    assert "book" in config.projects
    assert config.project("book").title == "A Book"
    assert config.deck_for("book") == "Shelf::A Book"
    assert config.project("book").tags == ("paper",)


def test_a_folder_without_a_source_file_is_not_a_source(repo: Path) -> None:
    """Discovery does not guess: a stray directory is not a book."""
    (repo / "projects" / "scratch").mkdir(parents=True, exist_ok=True)
    assert "scratch" not in config_mod.load(repo).projects


def test_the_folder_wins_over_the_root_file(repo: Path) -> None:
    """Both are read, so a repo migrates one source at a time. The file sitting
    next to the document is the one that is right."""
    add_toml(repo, '[projects.book]\ntitle = "Stale"\ndeck = "Old"\norder = "none"\n')
    write_source(repo, "book", 'title = "Current"\ndeck = "New"')

    config = config_mod.load(repo)
    assert config.project("book").title == "Current"
    assert config.deck_for("book") == "New"
    assert config.project("book").order == "none", "keys it does not restate are kept"


def test_a_block_copies_between_the_two_files_unchanged(repo: Path) -> None:
    """The whole argument for TOML over YAML frontmatter: the same text means
    the same thing in the root file and in a source's own."""
    block = (
        'units_from = ["highlight/green"]\n\n'
        '[meanings]\n"highlight/green" = "a claim"\n'
    )
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
    assert config_mod.load(repo).project("book").tags == ("no", "on", "y")


def test_a_source_file_without_frontmatter_is_refused(repo: Path) -> None:
    folder = repo / "projects" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text("# just prose\n", encoding="utf-8")
    with pytest.raises(config_mod.ConfigError, match="no frontmatter"):
        config_mod.load(repo)


def test_an_unclosed_frontmatter_block_is_refused(repo: Path) -> None:
    folder = repo / "projects" / "book"
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

# Both keys name a mark the same way, by kind and colour together: which
# marks become units is a different question from what they mean, but it is
# a question about the same marks.
REPO_ZOTERO = (
    '[zotero]\nunits_from = ["highlight/green"]\n\n'
    '[zotero.meanings]\n"highlight/green" = "a claim"\n'
)


def test_zotero_settings_fall_back_to_the_repo(repo: Path) -> None:
    add_toml(repo, REPO_ZOTERO)
    write_source(repo, "book", 'title = "A Book"')

    zotero = config_mod.load(repo).zotero_for("book")
    assert zotero.units_from == frozenset({"highlight/green"})
    assert zotero.means("highlight", "green") == "a claim"


def test_a_source_may_read_its_colours_differently(repo: Path) -> None:
    """A scheme drifts between a book read last year and a paper read last
    week, and a scheme that is wrong is worse than none."""
    add_toml(repo, REPO_ZOTERO)
    write_source(
        repo,
        "book",
        'title = "A Book"\nunits_from = ["highlight/magenta"]\n\n'
        '[meanings]\n"highlight/magenta" = "a result"',
    )

    config = config_mod.load(repo)
    mine = config.zotero_for("book")
    assert mine.units_from == frozenset({"highlight/magenta"})
    assert mine.means("highlight", "magenta") == "a result"
    assert mine.reading("highlight", "green")[1] == "default", "replaced, not merged"
    assert config.zotero.units_from == frozenset(
        {"highlight/green"}
    ), "the repo default is untouched"


def test_only_the_pair_decides_a_meaning() -> None:
    """It used to fall back `kind/colour` -> `kind` -> `colour`, which is two
    problems wearing one rule.

    A bare `highlight` shadowed every colour under it, so writing down what a
    highlight generally is quietly undid the scheme built out of colours. And a
    bare `yellow` claimed yellow means one thing however it was drawn -- which
    is exactly the distinction a second annotation kind exists to draw, and the
    reader who made both marks meant them differently.

    What is left under the pairs is `DEFAULT_MEANINGS`, keyed by kind, and that
    one is a fact about the kind rather than a reading of it: it says what
    Zotero's annotation *is*, not what you used it for.
    """
    zotero = config_mod.ZoteroConfig(
        data_dir=Path("/nowhere"), meanings={"note/yellow": "my own thought"}
    )
    assert zotero.reading("note", "yellow") == ("my own thought", "declared")
    assert zotero.reading("note", "blue") == (
        "something you wrote in the margin",
        "default",
    ), "a declared yellow note says nothing about a blue one"
    assert zotero.reading("highlight", "yellow") == (
        "a passage you marked",
        "default",
    ), "nor about a yellow highlight"


def test_half_a_mark_is_refused_rather_than_read_loosely(repo: Path) -> None:
    """Reading it loosely would put the old shadowing back, invisibly. The
    error names the pair to write instead."""
    add_toml(repo, '[zotero]\n\n[zotero.meanings]\ngreen = "a claim"\n')
    with pytest.raises(config_mod.ConfigError, match="highlight/green"):
        config_mod.load(repo)


def test_half_a_mark_is_refused_in_units_from_too(repo: Path) -> None:
    """The two keys name the same thing, so they take the same name. A bare
    `green` could only mean "green, however it was drawn", which is the
    distinction a second annotation kind exists to draw."""
    add_toml(repo, '[zotero]\nunits_from = ["green"]\n')
    with pytest.raises(config_mod.ConfigError, match="highlight/green"):
        config_mod.load(repo)


def test_a_bare_kind_is_refused_in_units_from(repo: Path) -> None:
    """`note` covered every colour of note, which is the shadowing the
    meanings table already refuses."""
    add_toml(repo, '[zotero]\nunits_from = ["note"]\n')
    with pytest.raises(config_mod.ConfigError, match="note/green"):
        config_mod.load(repo)


def test_a_source_naming_half_a_mark_is_refused(repo: Path) -> None:
    add_toml(repo, REPO_ZOTERO)
    write_source(repo, "book", 'title = "A Book"\nunits_from = ["magenta"]')
    with pytest.raises(config_mod.ConfigError, match=r"projects\.book"):
        config_mod.load(repo)


def test_the_pair_that_makes_a_unit_is_the_pair_that_carries_a_meaning() -> None:
    """One name, looked up one way. Two spellings is how a mark that starts a
    unit ends up with no declared meaning and nothing saying why."""
    zotero = config_mod.ZoteroConfig(
        data_dir=Path("/nowhere"),
        units_from=frozenset({"highlight/green"}),
        meanings={"highlight/green": "a claim"},
    )
    assert zotero.makes_a_unit("highlight", "green")
    assert not zotero.makes_a_unit("underline", "green"), "a different mark"
    assert not zotero.makes_a_unit("highlight", "blue")
    assert zotero.means("highlight", "green") == "a claim"


def test_declared_takes_every_pair_the_meanings_name(repo: Path) -> None:
    """For a document you mark sparingly, where writing a colour down at all
    means you expect a card out of it."""
    add_toml(
        repo,
        '[zotero]\nunits_from = "declared"\n\n'
        '[zotero.meanings]\n"highlight/green" = "a claim"\n"note/yellow" = "a thought"\n',
    )
    zotero = config_mod.load(repo).zotero

    assert zotero.unit_pairs == frozenset({"highlight/green", "note/yellow"})
    assert zotero.makes_a_unit("note", "yellow")
    assert not zotero.makes_a_unit("highlight", "magenta"), "no meaning, no unit"


def test_declared_follows_the_meanings_actually_in_force(repo: Path) -> None:
    """The marker is kept rather than expanded at load, so a source that reads
    its own colours and inherits the marker reads its own scheme."""
    add_toml(
        repo,
        '[zotero]\nunits_from = "declared"\n\n'
        '[zotero.meanings]\n"highlight/green" = "a claim"\n',
    )
    write_source(
        repo,
        "book",
        'title = "A Book"\n\n[meanings]\n"highlight/magenta" = "a result"',
    )

    mine = config_mod.load(repo).zotero_for("book")
    assert mine.unit_pairs == frozenset({"highlight/magenta"})
    assert not mine.makes_a_unit("highlight", "green"), "the shelf's scheme is replaced"


def test_a_source_may_opt_in_where_the_repo_lists_pairs(repo: Path) -> None:
    add_toml(repo, REPO_ZOTERO)
    write_source(
        repo,
        "book",
        'title = "A Book"\nunits_from = "declared"\n\n'
        '[meanings]\n"highlight/magenta" = "a result"\n"note/yellow" = "a thought"',
    )

    config = config_mod.load(repo)
    assert config.zotero_for("book").unit_pairs == frozenset(
        {"highlight/magenta", "note/yellow"}
    )
    assert config.zotero.unit_pairs == frozenset({"highlight/green"}), "not the default"


def test_declared_is_the_only_word_the_key_takes(repo: Path) -> None:
    add_toml(repo, '[zotero]\nunits_from = "everything"\n')
    with pytest.raises(config_mod.ConfigError, match="declared"):
        config_mod.load(repo)


def test_declaring_nothing_makes_no_units(repo: Path) -> None:
    """The same empty answer an empty list gives, and the importer reports it
    rather than importing a paper with nothing in it."""
    add_toml(repo, '[zotero]\nunits_from = "declared"\n')
    assert config_mod.load(repo).zotero.unit_pairs == frozenset()


def test_a_kind_with_nothing_to_colour_is_the_pair() -> None:
    """`ink` has no colour to pair with, so the kind *is* the whole of it.
    Demanding `ink/red` would be demanding a mark nobody can make."""
    zotero = config_mod.ZoteroConfig(
        data_dir=Path("/nowhere"), meanings={"ink": "something I drew"}
    )
    assert zotero.means("ink", "") == "something I drew"


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

    folder = repo / "projects" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("conventions.md").write_text("# Old\n\nStill read.\n", encoding="utf-8")
    assert "Still read." in source_conventions(config_mod.load(repo), "book")
