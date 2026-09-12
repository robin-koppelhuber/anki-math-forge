"""Triaging a prose source by what you meant, not by what state a unit is in.

"The claims first, the terms never" is the shape of the decision, and it is
invisible unless the rail is built from the marks themselves.

The rail is a *grid*, not a list. Five annotation kinds times eight colours is
forty labelled lines, which is the whole rail -- and the data is genuinely
two-dimensional, so any flat arrangement hides one axis. A column is a colour,
a row is a kind, a cell is one filter, and the empty cells carry as much as the
full ones: together they are the reader's scheme, drawn.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import config as config_mod
from anki_math_forge.app import mark_matrix, unit_mark
from anki_math_forge.config import Config
from anki_math_forge.ledger import Mark, Unit

MEANINGS = (
    "\n[zotero.meanings]\n"
    'green = "a claim worth a card"\n'
    'purple = "a term to know"\n'
    'note = "something I thought while reading"\n'
)


def declared(repo: Path, extra: str = MEANINGS) -> Config:
    path = repo / "forge.toml"
    path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return config_mod.load(repo)


def a_unit(uid: str, *marks: tuple[str, str]) -> Unit:
    return Unit(
        id=f"demo:{uid}",
        marks=[Mark(key=f"{uid}{i}", kind=k, colour=c) for i, (k, c) in enumerate(marks)],
    )


def cells(matrix: dict, kind: str) -> dict[str, dict]:
    row = next(r for r in matrix["rows"] if r["kind"] == kind)
    return {str(c["colour"]): c for c in row["cells"]}


def test_a_unit_is_matched_on_its_own_mark() -> None:
    """Not on the ones shown beside it: those belong to their own units, and
    matching on them would return every neighbour too."""
    unit = a_unit("a", ("highlight", "green"), ("highlight", "purple"))
    assert unit_mark(unit) == "highlight/green"


def test_a_unit_with_no_marks_matches_nothing() -> None:
    """Which is every unit the Cookbook has."""
    assert unit_mark(Unit(id="demo:2.4:61")) == ""


def test_a_colourless_kind_is_matched_on_the_kind_alone() -> None:
    assert unit_mark(a_unit("a", ("ink", ""))) == "ink"


def test_kinds_are_rows_and_colours_are_columns(repo: Path) -> None:
    """The compact shape, and the one that lets a colour be read across kinds."""
    units = [
        a_unit("a", ("highlight", "green")),
        a_unit("b", ("highlight", "green")),
        a_unit("c", ("highlight", "purple")),
        a_unit("d", ("note", "green")),
    ]
    matrix = mark_matrix(units, declared(repo), "demo")
    assert [r["kind"] for r in matrix["rows"]] == ["highlight", "note"], "commonest kind first"
    assert [c["colour"] for c in matrix["colours"]] == ["green", "purple"], "commonest first"
    assert cells(matrix, "highlight")["green"]["count"] == 2
    assert cells(matrix, "note")["green"]["count"] == 1


def test_every_row_spans_every_column(repo: Path) -> None:
    """A grid with ragged rows is not a grid. The cell for a combination you
    have never used is the informative one: it says this reader never wrote a
    purple note, which is a fact about how the document was read."""
    units = [a_unit("a", ("highlight", "purple")), a_unit("b", ("note", "green"))]
    matrix = mark_matrix(units, declared(repo), "demo")
    for row in matrix["rows"]:
        assert [c["colour"] for c in row["cells"]] == [c["colour"] for c in matrix["colours"]]
    assert cells(matrix, "note")["purple"]["count"] == 0
    assert cells(matrix, "note")["purple"]["key"] == "", "no filter to click"


def test_an_unused_cell_still_says_what_it_would_mean(repo: Path) -> None:
    """It is what the hover has to show, and it is also the moment you notice
    you have never used a combination you thought you had."""
    units = [a_unit("a", ("highlight", "purple")), a_unit("b", ("note", "green"))]
    empty = cells(mark_matrix(units, declared(repo), "demo"), "note")["purple"]
    assert empty["meaning"] == "something I thought while reading", "kind beats colour"


def test_a_cell_says_whether_you_decided_it_or_the_tool_did(repo: Path) -> None:
    """`DEFAULT_MEANINGS` is the floor -- a Zotero kind always reads as
    something, so a fresh repo is not a wall of squares with no captions. But a
    default says what the annotation *is* and a declaration says what you meant
    by it, and presenting the first as the second would hide a decision you
    have not taken."""
    units = [a_unit("a", ("highlight", "green")), a_unit("b", ("highlight", "orange"))]
    row = cells(mark_matrix(units, declared(repo), "demo"), "highlight")
    assert row["green"]["declared"]
    assert not row["orange"]["declared"]
    assert row["orange"]["meaning"], "still filterable, and still says something"


def test_a_kind_the_tool_knows_is_always_filterable(repo: Path) -> None:
    """Which kinds you can filter by is decided by the scheme in force, and the
    built-in defaults are part of it."""
    matrix = mark_matrix([a_unit("a", ("underline", "orange"))], declared(repo), "demo")
    assert [r["kind"] for r in matrix["rows"]] == ["underline"]
    assert not cells(matrix, "underline")["orange"]["declared"]


def test_a_kind_the_tool_does_not_know_is_not_invented(repo: Path) -> None:
    """The floor is Zotero's closed set of annotation kinds, not a guess."""
    assert mark_matrix([a_unit("a", ("doodle", "orange"))], declared(repo), "demo") == {}


def test_each_cell_carries_what_you_said_it_means(repo: Path) -> None:
    """It is the cell's whole label: the square is the thing you click, and the
    hover is what tells you what clicking it will leave."""
    matrix = mark_matrix([a_unit("a", ("highlight", "green"))], declared(repo), "demo")
    cell = cells(matrix, "highlight")["green"]
    assert cell["meaning"] == "a claim worth a card"
    assert cell["key"] == "highlight/green"


def test_a_source_with_no_marks_gets_no_rail(config: Config) -> None:
    """So the Cookbook's rail is exactly what it was."""
    assert mark_matrix([Unit(id="demo:2.4:61")], config, "demo") == {}
