"""Triaging a prose source by what you meant, not by what state a unit is in.

"The claims first, the terms never" is the shape of the decision, and it is
invisible unless the rail is built from the marks themselves.

The rail is a *picker*, not a list. Five annotation kinds times eight colours
is forty rows, and as labelled lines that is the whole rail; one row per kind
and a coloured square per colour is a handful of rows, and it is also how the
marks look on the page you made them on.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import config as config_mod
from anki_math_forge.app import mark_picker, unit_mark
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


def test_colours_are_grouped_under_their_kind(repo: Path) -> None:
    """The compact shape: `highlight` once, with a square per colour."""
    units = [
        a_unit("a", ("highlight", "green")),
        a_unit("b", ("highlight", "green")),
        a_unit("c", ("highlight", "purple")),
        a_unit("d", ("note", "green")),
    ]
    groups = mark_picker(units, declared(repo), "demo")
    assert [g["kind"] for g in groups] == ["highlight", "note"], "commonest kind first"
    assert [(c["colour"], c["count"]) for c in groups[0]["colours"]] == [
        ("green", 2),
        ("purple", 1),
    ], "commonest colour first within the kind"


def test_a_chip_says_whether_you_decided_it_or_the_tool_did(repo: Path) -> None:
    """`DEFAULT_MEANINGS` is the floor -- a Zotero kind always reads as
    something, so a fresh repo is not a wall of squares with no captions. But a
    default says what the annotation *is* and a declaration says what you meant
    by it, and presenting the first as the second would hide a decision you
    have not taken."""
    units = [a_unit("a", ("highlight", "green")), a_unit("b", ("highlight", "orange"))]
    chips = {c["colour"]: c for c in mark_picker(units, declared(repo), "demo")[0]["colours"]}
    assert chips["green"]["declared"]
    assert not chips["orange"]["declared"]
    assert chips["orange"]["meaning"], "still filterable, and still says something"


def test_a_kind_the_tool_knows_is_always_filterable(repo: Path) -> None:
    """Which kinds you can filter by is decided by the scheme in force, and the
    built-in defaults are part of it."""
    units = [a_unit("a", ("underline", "orange"))]
    groups = mark_picker(units, declared(repo), "demo")
    assert [g["kind"] for g in groups] == ["underline"]
    assert not groups[0]["colours"][0]["declared"]


def test_a_kind_the_tool_does_not_know_is_not_invented(repo: Path) -> None:
    """The floor is Zotero's closed set of annotation kinds, not a guess."""
    assert mark_picker([a_unit("a", ("doodle", "orange"))], declared(repo), "demo") == []


def test_each_chip_carries_what_you_said_it_means(repo: Path) -> None:
    """It is the chip's label -- the square is the thing you click, and the
    sentence is what tells you what clicking it will leave."""
    groups = mark_picker([a_unit("a", ("highlight", "green"))], declared(repo), "demo")
    assert groups[0]["colours"][0]["meaning"] == "a claim worth a card"
    assert groups[0]["colours"][0]["key"] == "highlight/green"


def test_a_source_with_no_marks_gets_no_rail(config: Config) -> None:
    """So the Cookbook's rail is exactly what it was."""
    assert mark_picker([Unit(id="demo:2.4:61")], config, "demo") == []
