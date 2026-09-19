"""How much of a document a card writer is handed.

Three levels, most specific first: the unit, its source, the repo. The unit
level exists because triage is where you can see that a theorem's hypotheses
are two pages back and the default window would cut them off.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import cli, context
from anki_math_forge import config as config_mod
from anki_math_forge.config import Config
from anki_math_forge.extract import source_text_path
from anki_math_forge.ledger import Ledger, Locator, Mark, Unit

PAGES = "".join(f"## page {n}\nbody {n}\n\n" for n in range(1, 41))


def _seed(config: Config, **unit_fields: object) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(
        Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=20), **unit_fields)
    )
    led.save()
    path = source_text_path(config, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGES, encoding="utf-8")


def _span(config: Config) -> set[str]:
    found = context.assemble(config, "demo:2.2:61")
    assert found is not None
    return {line for line in found.page_text.splitlines() if line.startswith("body ")}


def test_the_repo_default_is_one_page_either_side(config: Config) -> None:
    _seed(config)
    assert _span(config) == {"body 19", "body 20", "body 21"}


def test_a_unit_may_ask_for_more(config: Config) -> None:
    """Set during triage, when you can see the default window is too tight."""
    _seed(config, context_pages=3)
    assert _span(config) == {f"body {n}" for n in range(17, 24)}


def test_a_unit_may_ask_for_the_whole_document(config: Config) -> None:
    """A large number, rather than a sentinel nobody would remember. `_page`
    already skips pages that are not there."""
    _seed(config, context_pages=999)
    assert _span(config) == {f"body {n}" for n in range(1, 41)}


def test_a_unit_may_ask_for_less(config: Config) -> None:
    _seed(config, context_pages=0)
    assert _span(config) == {"body 20"}


def test_the_source_sets_it_when_the_unit_does_not(repo: Path) -> None:
    """How much a page carries is a fact about how the book is set."""
    folder = repo / "projects" / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "Demo"\ncontext_pages = 4\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(repo)
    _seed(config)
    assert _span(config) == {f"body {n}" for n in range(16, 25)}


def test_the_unit_beats_its_source(repo: Path) -> None:
    folder = repo / "projects" / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "Demo"\ncontext_pages = 4\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(repo)
    _seed(config, context_pages=0)
    assert _span(config) == {"body 20"}


def test_an_explicit_ask_beats_everything(config: Config) -> None:
    """`--pages` is the caller saying they know better, which they sometimes
    do: a one-off look at a wider span should not have to edit the ledger."""
    _seed(config, context_pages=0)
    found = context.assemble(config, "demo:2.2:61", spread=2)
    assert found is not None
    assert "body 18" in found.page_text


# -- setting it from the CLI, which is what triage will call ----------------


def test_the_cli_sets_and_clears_it(repo: Path, capsys: object) -> None:
    config = config_mod.load(repo)
    _seed(config)
    args = ["--root", str(repo), "units", "--id", "demo:2.2:61", "--context-pages"]

    cli.main([*args, "7"])
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").context_pages == 7

    cli.main([*args, "-1"])
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").context_pages is None


def test_it_is_not_written_when_inherited(config: Config) -> None:
    """751 Cookbook units must not grow a key they have no use for."""
    assert "context_pages" not in Unit(id="demo:2.4:61").to_json()
    assert Unit(id="demo:2.4:61", context_pages=3).to_json()["context_pages"] == 3


def test_it_survives_a_re_extraction(config: Config) -> None:
    """Human-owned, like `state`. Re-segmenting must not undo a judgement made
    while looking at the page."""
    _seed(config, context_pages=5)
    led = Ledger.load(config.units_path("demo"))
    led.upsert([Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=20))])
    led.save()

    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").context_pages == 5


# -- what the reader wrote about the mark -----------------------------------


def marked(comment: str, kind: str = "highlight") -> list[Mark]:
    return [Mark(key="61", kind=kind, colour="green", text="a passage", comment=comment)]


def test_a_comment_on_a_highlight_reaches_the_card_writer(config: Config) -> None:
    """`Mark.content` gives the comment only for a note, so a sentence typed
    onto a highlight reached the units view and stopped there. The one pass
    that most needs to know what you meant could not see it."""
    _seed(config, marks=marked("this is the version with the constant in front"))

    found = context.assemble(config, "demo:2.2:61")

    assert found is not None
    assert found.marks[0]["comment"] == "this is the version with the constant in front"
    assert "> this is the version with the constant in front" in found.format()


def test_a_note_does_not_repeat_itself(config: Config) -> None:
    """A note covers nothing on the page: its comment *is* its text, and
    printing it twice would read as two different things."""
    _seed(config, marks=marked("a thought", kind="note"))

    found = context.assemble(config, "demo:2.2:61")

    assert found is not None
    assert found.marks[0]["comment"] == ""


def test_a_mark_spanning_a_line_break_keeps_the_column(config: Config) -> None:
    _seed(config, marks=[Mark(key="61", kind="highlight", colour="green", text="two\nlines")])

    found = context.assemble(config, "demo:2.2:61")

    assert found is not None
    said = found.format()
    assert "two lines" in said
    assert "two" + chr(10) + "lines" not in said, "a newline would break the column under it"


def test_a_convention_comment_is_proposed_not_adopted(config: Config) -> None:
    """A convention decides how every later card here is read and nothing
    reviews it, so the pass may write it down for the human and no more."""
    _seed(config, marks=marked("convention: entries are real unless stated"))

    said = context.assemble(config, "demo:2.2:61").format()

    assert "## conventions this unit proposes" in said
    assert "- entries are real unless stated" in said
    assert "`@me` annotation" in said
    assert "Do not write them into `conventions.md`" in said


def test_a_comment_that_merely_starts_like_the_keyword_is_not_one(config: Config) -> None:
    _seed(config, marks=marked("conventional choice of sign here"))

    said = context.assemble(config, "demo:2.2:61").format()

    assert "## conventions this unit proposes" not in said
    assert "> conventional choice of sign here" in said, "still shown, as a comment"


def test_a_source_may_read_the_keyword_in_its_own_language(repo: Path) -> None:
    """The word is typed while reading, in whatever language you read in."""
    (repo / "projects" / "demo" / "project.toml").write_text(
        'title = "A Book"\nconvention_keyword = "Konvention"\n', encoding="utf-8"
    )
    config = config_mod.load(repo)

    scheme = config.zotero_for("demo")
    assert scheme.convention_in("Konvention: Eintraege sind reell") == "Eintraege sind reell"
    assert scheme.convention_in("convention: entries are real") == ""
    assert config.zotero.convention_in("convention: entries are real") == "entries are real"


# -- what triage asked for --------------------------------------------------


def test_the_unit_s_notes_reach_whoever_reads_the_context(config: Config) -> None:
    """The card writer sees them in its work list; the augmenter works from
    card files and this command, so a brief left at triage used to reach the
    first pass and vanish before the second."""
    _seed(config, notes=["@claude two cards, one per convention"])

    found = context.assemble(config, "demo:2.2:61")

    assert found is not None
    assert found.notes == ["@claude two cards, one per convention"]
    said = found.format()
    assert "## what triage asked for, on this unit" in said
    assert "two cards, one per convention" in said


def test_it_comes_before_the_source_it_is_about(config: Config) -> None:
    """It is the only part of this written *to* the reader, and it routinely
    says something the page cannot."""
    _seed(config, notes=["@claude the condition is two pages back"])

    said = context.assemble(config, "demo:2.2:61").format()

    assert said.index("what triage asked for") < said.index("the setting this source")


def test_a_unit_nobody_wrote_on_says_nothing(config: Config) -> None:
    _seed(config)

    said = context.assemble(config, "demo:2.2:61").format()

    assert "what triage asked for" not in said


# -- the chapter, which is not a number of pages ----------------------------


def _book(config: Config, **unit_fields: object) -> None:
    """A three-chapter book: 1 starts on page 5, 2 on page 12, 3 on page 30.

    Sections are the Cookbook's shape -- `2.3` is in chapter 2 -- and page 2
    carries a unit nothing filed under a section, which is what a segmenter
    leaves behind when a page has no heading above it.
    """
    led = Ledger(config.units_path("demo"))
    for section, page in (
        ("", 2),
        ("1.1", 5),
        ("1.2", 9),
        ("2.1", 12),
        ("2.3", 20),
        ("3.1", 30),
    ):
        led.units.append(
            Unit(
                id=f"demo:{section or 'front'}:{page}",
                locator=Locator(section=section, page=page),
            )
        )
    led.units.append(
        Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=20), **unit_fields)
    )
    led.save()
    path = source_text_path(config, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PAGES, encoding="utf-8")


def _chapter(config: Config, unit: str = "demo:2.2:61") -> context.UnitContext:
    found = context.assemble(config, unit, spread=config_mod.CHAPTER)
    assert found is not None
    return found


def test_the_chapter_runs_to_where_the_next_one_starts(config: Config) -> None:
    """Chapter 2 begins on page 12 and chapter 3 on page 30, so the window is
    12 to 29 -- including the pages at its end that hold no unit, which is the
    half a count of pages either side always misses."""
    _book(config)

    found = _chapter(config)

    assert found.pages == list(range(12, 30))
    assert found.window == 'the chapter it was printed in, "2" (pages 12 to 29)'


def test_the_last_chapter_runs_to_the_end_of_the_document(config: Config) -> None:
    _book(config)

    found = _chapter(config, "demo:3.1:30")

    assert found.pages == list(range(30, 41))


def test_a_unit_with_no_section_takes_the_chapter_it_is_printed_in(
    config: Config,
) -> None:
    """Asked by page, not by the unit's own section. Plenty of units have no
    section, and one printed in the middle of a chapter is in that chapter."""
    _book(config)
    led = Ledger.load(config.units_path("demo"))
    led.units.append(Unit(id="demo:none:14", locator=Locator(page=14)))
    led.save()

    assert _chapter(config, "demo:none:14").pages == list(range(12, 30))


def test_a_page_before_the_first_chapter_says_so(config: Config) -> None:
    """Front matter is not a chapter, and promising one would be a heading
    that lies about what is under it."""
    _book(config)

    found = _chapter(config, "demo:front:2")

    assert found.pages == list(range(1, 5))
    assert "before the first chapter" in found.window


def test_a_document_with_no_sections_hands_over_all_of_it(config: Config) -> None:
    """Nothing declared a table of contents, so the chapter is the document.
    The heading says which of the two happened."""
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:2.2:61", locator=Locator(page=20)))
    led.save()
    source_text_path(config, "demo").write_text(PAGES, encoding="utf-8")

    found = _chapter(config)

    assert found.pages == list(range(1, 41))
    assert "declares no chapters" in found.window


def test_the_window_names_itself_in_the_heading(config: Config) -> None:
    """A pass handed eighteen pages under a heading that says "page" has no
    way to tell how much it is holding."""
    _book(config)

    said = _chapter(config).format()

    assert '## the chapter it was printed in, "2" (pages 12 to 29)' in said


def test_the_chapter_stays_inside_one_document(config: Config) -> None:
    """Page 17 of the appendix is not page 17 of the paper."""
    _book(config)
    led = Ledger.load(config.units_path("demo"))
    led.units.append(
        Unit(id="demo:appendix:14", locator=Locator(section="A", document="appendix.pdf", page=14))
    )
    led.save()

    assert _chapter(config).pages == list(range(12, 30))


def test_the_unit_can_record_the_chapter_as_its_window(config: Config) -> None:
    """The point of the setting: widening your own call solves it for you,
    recording it solves it for everyone after you."""
    _book(config, context_pages=config_mod.CHAPTER)

    found = context.assemble(config, "demo:2.2:61")

    assert found is not None
    assert found.pages == list(range(12, 30))


def test_the_cli_writes_the_word_and_takes_it_off_again(repo: Path) -> None:
    config = config_mod.load(repo)
    _book(config)
    args = ["--root", str(repo), "units", "--id", "demo:2.2:61", "--context-pages"]

    cli.main([*args, "chapter"])
    stored = Ledger.load(config.units_path("demo")).get("demo:2.2:61")
    assert stored.context_pages == "chapter"
    assert stored.to_json()["context_pages"] == "chapter"

    cli.main([*args, "-1"])
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").context_pages is None


def test_a_source_and_the_repo_may_ask_for_it_too(repo: Path) -> None:
    """Same vocabulary at all three levels, so what you widen one call with is
    what you write down."""
    folder = repo / "projects" / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "Demo"\ncontext_pages = "chapter"\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(repo)
    _book(config)

    assert context.assemble(config, "demo:2.2:61").pages == list(range(12, 30))
    assert config.context_pages_for("demo") == "chapter"


def test_a_window_that_is_neither_is_refused(repo: Path) -> None:
    """Refused rather than guessed at: a value that fell through to the `else`
    would hand over one page and nobody would know why."""
    import pytest

    repo.joinpath("forge.toml").write_text(
        '[cards]\ncontext_pages = "the whole shelf"\n', encoding="utf-8"
    )
    with pytest.raises(config_mod.ConfigError):
        config_mod.load(repo)
