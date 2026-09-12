"""Showing a reader what they marked.

A crop used to be a rectangle of grey text with no indication of which part of
it the unit was about, and the sentence somebody wrote in the margin -- the
most useful thing on the page -- appeared nowhere in the app at all. Three
things fix that, and they are all in here: the marks are painted back onto the
crop in their own colours, the crop is cut wide enough to be readable, and what
each mark says is listed under it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge.app import (
    create_app,
    mark_payloads,
    scheme_rows,
    source_facts,
    source_origin,
)
from anki_math_forge.config import Config
from anki_math_forge.extract.render import regions_for
from anki_math_forge.ledger import Ledger, Locator, Mark, Unit

# Two marks on page 1 and one on page 2, which is the case that matters: a
# unit carries the marks from the pages *around* it.
HERE = Mark(
    key="AAA",
    kind="highlight",
    colour="green",
    text="a claim worth a card",
    page=1,
    bbox=[70, 300, 520, 330],
    rects=[[70, 300, 520, 315], [70, 315, 300, 330]],
)
BESIDE = Mark(
    key="BBB",
    kind="note",
    colour="yellow",
    comment="why is this tight?",
    page=1,
    bbox=[530, 300, 552, 322],
    rects=[[530, 300, 552, 322]],
)
OVERLEAF = Mark(
    key="CCC",
    kind="highlight",
    colour="purple",
    text="a term to know",
    page=2,
    bbox=[70, 100, 200, 115],
    rects=[[70, 100, 200, 115]],
)


def a_unit(source: str = "paper") -> Unit:
    return Unit(
        id=f"{source}:AAA",
        locator=Locator(section="PDF", kind="highlight", page=1, bbox=HERE.bbox),
        marks=[HERE, BESIDE, OVERLEAF],
    )


# -- what gets painted on the crop -----------------------------------------


def test_only_the_marks_on_this_page_are_drawn() -> None:
    """A mark from the next page painted onto this one lands on unrelated
    text, which is worse than not drawing it at all."""
    drawn = regions_for(a_unit(), page=1)
    assert len(drawn) == 2
    assert regions_for(a_unit(), page=2)[0].rgb == pytest.approx(
        (0xA2 / 255, 0x8A / 255, 0xE5 / 255)
    )


def test_the_unit_s_own_mark_is_the_only_one_at_full_strength() -> None:
    """Six highlights on a page and a uniform wash over them says nothing
    about which one the card is supposed to be about."""
    mine, beside = regions_for(a_unit(), page=1)
    assert not mine.faded
    assert beside.faded


def test_each_line_is_drawn_separately_not_their_union() -> None:
    """The union of a highlight running over a line break covers both lines
    end to end, including the part of each the reader left unmarked."""
    mine = regions_for(a_unit(), page=1)[0]
    assert len(mine.rects) == 2
    assert mine.rects != (tuple(HERE.bbox),)


def test_a_mark_imported_before_marks_knew_their_page_still_draws_its_own() -> None:
    """The first mark is the one the unit came from, so the locator's page is
    its page by construction. The neighbours are skipped rather than guessed
    at, and re-importing brings them back."""
    unit = a_unit()
    unit.marks = [Mark(key="AAA", kind="highlight", colour="green", bbox=[70, 300, 520, 330])]
    drawn = regions_for(unit, page=1)
    assert len(drawn) == 1
    assert drawn[0].rects == ((70.0, 300.0, 520.0, 330.0),), "falls back to the union"


def test_an_unknown_colour_is_drawn_grey_rather_than_dropped() -> None:
    """"Something is marked here" is most of what a crop has to say."""
    unit = a_unit()
    unit.marks = [Mark(key="AAA", kind="highlight", colour="chartreuse", page=1, bbox=[1, 2, 3, 4])]
    assert len(regions_for(unit, page=1)) == 1


# -- how wide the crop is cut ----------------------------------------------


def test_a_marked_unit_is_cut_to_the_page_width_by_default(config: Config) -> None:
    """A mark's box is the union of the lines a sentence spans, so its edges
    are wherever that sentence started and stopped mid-column. Cutting there
    slices words in half -- which is what a sticky note's 22pt box did."""
    assert config.crop_width_for("paper", from_a_mark=True) == "page"
    assert config.crop_width_for("paper", from_a_mark=False) == "box"


def test_a_source_that_says_otherwise_is_believed_both_ways(tmp_path: Path) -> None:
    (tmp_path / "sources" / "book").mkdir(parents=True)
    (tmp_path / "forge.toml").write_text("", encoding="utf-8")
    (tmp_path / "sources" / "book" / "source.md").write_text(
        '+++\ntitle = "Book"\ncrop_width = "page"\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(tmp_path)
    assert config.crop_width_for("book", from_a_mark=False) == "page"


def test_an_unrecognised_width_is_refused_at_load(tmp_path: Path) -> None:
    """Same reason `layout` is: it would fall through to whichever branch
    happens to be the `else`, and you would find out by wondering why half the
    crops look wrong."""
    (tmp_path / "sources" / "book").mkdir(parents=True)
    (tmp_path / "forge.toml").write_text("", encoding="utf-8")
    (tmp_path / "sources" / "book" / "source.md").write_text(
        '+++\ntitle = "Book"\ncrop_width = "wide"\n+++\n', encoding="utf-8"
    )
    with pytest.raises(config_mod.ConfigError, match="crop_width"):
        config_mod.load(tmp_path)


def test_the_crop_route_refuses_a_width_it_does_not_know(zotero_config: Config) -> None:
    ledger = Ledger(zotero_config.units_path("paper"), [a_unit()])
    ledger.save()
    client = TestClient(create_app(zotero_config))
    assert client.get("/crop/paper/paper:AAA.png?width=enormous").status_code == 400


# -- what the marks say -----------------------------------------------------


def test_the_text_and_the_comment_are_kept_apart(config: Config) -> None:
    """They are not the same claim: one is the document's words and one is the
    reader's."""
    rows = mark_payloads(a_unit(), config)
    assert rows[0]["text"] == "a claim worth a card"
    assert not rows[0]["comment"]
    assert rows[1]["comment"] == "why is this tight?"


def test_the_unit_s_own_mark_comes_first_and_says_so(config: Config) -> None:
    rows = mark_payloads(a_unit(), config)
    assert rows[0]["own"]
    assert not any(row["own"] for row in rows[1:])


def test_a_neighbour_that_is_itself_a_unit_is_flagged(config: Config) -> None:
    """It is something you will meet again rather than context for this one."""
    rows = mark_payloads(a_unit(), config, known={"paper:AAA", "paper:CCC"})
    by_key = {row["key"]: row for row in rows}
    assert by_key["CCC"]["unit"] == "paper:CCC"
    assert not by_key["BBB"]["unit"]


def test_the_meaning_is_resolved_now_rather_than_stored(config: Config) -> None:
    """Editing the scheme has to change every unit at once, not only the ones
    imported since -- which is why a mark records a colour and not a meaning."""
    rows = mark_payloads(a_unit(), config)
    assert all("meaning" in row for row in rows)


# -- the legend -------------------------------------------------------------


def test_the_legend_counts_each_mark_once(config: Config) -> None:
    """A mark appears in the neighbour list of every unit near it, and counting
    those reports the same highlight five times."""
    units = [a_unit(), a_unit()]
    counts = {row["key"]: row["count"] for row in scheme_rows(units, config, "paper")}
    assert counts.get("highlight/green") == 1, "nothing declared, so keyed in full"


def test_the_legend_shows_what_is_declared_but_unused(zotero_config: Config) -> None:
    """It is the scheme, not a tally. A colour you set aside for something and
    have not used yet is part of it."""
    keys = {row["key"] for row in scheme_rows([a_unit()], zotero_config, "paper")}
    assert "green" in keys, "declared, and nothing green is marked in this unit"


def test_there_is_no_legend_for_a_source_with_no_marks(zotero_config: Config) -> None:
    """`[zotero.meanings]` is repo-wide. Rendering it beside a book nobody has
    ever highlighted is the rail describing a different source -- a full colour
    legend with every count zero."""
    unit = a_unit()
    unit.marks = []
    assert scheme_rows([unit], zotero_config, "paper") == []


def test_the_legend_shows_what_is_used_but_undeclared(zotero_config: Config) -> None:
    """The row worth seeing: a mark whose meaning exists only in your head,
    which reaches a card writer as a coloured box with no caption."""
    unit = a_unit()
    unit.marks = [Mark(key="ZZZ", kind="highlight", colour="orange", page=1)]
    rows = {row["key"]: row for row in scheme_rows([unit], zotero_config, "paper")}
    assert rows["highlight/orange"]["count"] == 1
    assert not rows["highlight/orange"]["declared"]


def test_the_legend_says_which_marks_become_units(zotero_config: Config) -> None:
    rows = {row["key"]: row for row in scheme_rows([a_unit()], zotero_config, "paper")}
    assert rows["green"]["makes_a_unit"]
    assert not rows["purple"]["makes_a_unit"]


def test_the_legend_groups_the_way_the_config_resolves(zotero_config: Config) -> None:
    """A bare `note` entry collects every colour of sticky note, and seeing
    that is the point of showing it."""
    unit = a_unit()
    unit.marks = [
        Mark(key="N1", kind="note", colour="yellow", page=1),
        Mark(key="N2", kind="note", colour="red", page=1),
    ]
    rows = {row["key"]: row for row in scheme_rows([unit], zotero_config, "paper")}
    assert rows["note"]["count"] == 2


# -- where a source came from -----------------------------------------------


def test_a_zotero_source_is_distinguishable_from_a_local_pdf(zotero_config: Config) -> None:
    """They looked identical in every view, and they are not: it decides which
    passes make sense and where to go when a document is missing."""
    assert source_origin(zotero_config, "paper") == "zotero"


def test_the_source_facts_say_when_nothing_is_declared(zotero_config: Config) -> None:
    """An absent convention is a card writer guessing at what is ambient, and
    it was a blank where a value would be -- indistinguishable from a setting
    that happens to be empty."""
    facts = source_facts(zotero_config, "paper")
    assert facts["conventions"] is False
    assert facts["origin"] == "zotero"
    assert facts["crop_width"] == "box", "nothing said, and nothing asked about marks"
    assert facts["deck"] == zotero_config.deck, "inherited, and shown as the resolved value"


# -- the scheme has a floor -------------------------------------------------


def test_a_zotero_kind_always_reads_as_something(config: Config) -> None:
    """`DEFAULT_MEANINGS` is the closed set Zotero defines, so the tool can
    state it; a *colour* is a scheme you invented and it cannot. Without the
    floor a fresh repo is a wall of coloured squares with no captions."""
    scheme = config.zotero_for("nothing-declared-here")
    assert scheme.means("note", "yellow")
    assert scheme.reading("note", "yellow")[1] == "default"


def test_the_tool_invents_no_kind_it_does_not_know(config: Config) -> None:
    assert config.zotero_for("x").means("doodle", "chartreuse") == ""


def test_what_you_declare_sits_on_top(zotero_config: Config) -> None:
    scheme = zotero_config.zotero_for("paper")
    assert scheme.means("highlight", "green") == "a claim or result worth a card"
    assert scheme.reading("highlight", "green")[1] == "declared"


def test_the_legend_says_which_are_yours(zotero_config: Config) -> None:
    """A default says what the annotation *is*; a declaration says what you
    meant by it. Showing the first as the second hides a decision not taken."""
    unit = a_unit()
    unit.marks = [
        Mark(key="A", kind="highlight", colour="green", page=1),
        Mark(key="B", kind="underline", colour="orange", page=1),
    ]
    rows = {row["key"]: row for row in scheme_rows([unit], zotero_config, "paper")}
    assert rows["green"]["declared"]
    assert not rows["underline/orange"]["declared"], "its own row, at full specificity"
    assert rows["underline/orange"]["meaning"], "and it still reads as something"


def test_the_marks_scheme_is_zotero_only(config: Config) -> None:
    """A segmented book has no marks and no scheme, and a rail describing
    machinery that is not running is worse than an empty one."""
    assert source_facts(config, "demo")["units_from"] == []


# -- reading the document rather than judging a crop ------------------------


def a_ledger(config: Config, source: str = "paper") -> None:
    Ledger(config.units_path(source), [a_unit(source)]).save()


def test_the_document_view_says_how_long_it_is_and_where_you_are(
    zotero_config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked for only when the scrolling view is first opened, because it opens
    the PDF: a units page carrying this for every row would pay that cost 750
    times to answer a question nobody asked."""
    from anki_math_forge.extract import render as render_mod

    a_ledger(zotero_config)
    monkeypatch.setattr(render_mod, "page_count", lambda path: 58)
    monkeypatch.setattr(
        type(zotero_config), "document_for", lambda self, s, d="": Path(__file__)
    )
    payload = TestClient(create_app(zotero_config)).get("/api/document/paper/paper:AAA").json()
    assert payload == {"pages": 58, "page": 1}


def test_a_page_out_of_the_document_is_refused(zotero_config: Config) -> None:
    """Rather than a broken image, which reads as the PDF being missing."""
    a_ledger(zotero_config)
    client = TestClient(create_app(zotero_config))
    assert client.get("/page/paper/paper:AAA.png?n=999").status_code in (404, 409)


def test_the_page_number_is_a_query_not_a_path_segment(zotero_config: Config) -> None:
    """`{unit_id:path}` is greedy and would swallow a trailing segment, and a
    unit id already contains the colons that make it look like a path."""
    paths = {getattr(route, "path", "") for route in create_app(zotero_config).routes}
    assert "/page/{source}/{unit_id:path}.png" in paths
