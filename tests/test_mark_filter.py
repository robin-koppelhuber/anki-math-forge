"""Triaging a prose source by what you meant, not by what state a unit is in.

"The claims first, the terms never" is the shape of the decision, and it is
invisible unless the rail is built from the marks themselves.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import config as config_mod
from anki_math_forge.app import mark_rows, unit_mark
from anki_math_forge.config import Config
from anki_math_forge.ledger import Mark, Unit


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


def test_rows_are_counted_and_ordered_by_weight(config: Config) -> None:
    units = [
        a_unit("a", ("highlight", "green")),
        a_unit("b", ("highlight", "green")),
        a_unit("c", ("note", "yellow")),
        Unit(id="demo:plain"),
    ]
    rows = mark_rows(units, config, "demo")

    assert [(r["key"], r["count"]) for r in rows] == [
        ("highlight/green", 2),
        ("note/yellow", 1),
    ], "commonest first, and a unit with no marks is in no row"


def test_rows_carry_what_you_said_it_means(repo: Path) -> None:
    """The rail should read "a claim worth a card", not "highlight/green"."""
    path = repo / "forge.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + '\n[zotero.meanings]\ngreen = "a claim worth a card"\n',
        encoding="utf-8",
    )
    rows = mark_rows([a_unit("a", ("highlight", "green"))], config_mod.load(repo), "demo")
    assert rows[0]["meaning"] == "a claim worth a card"


def test_a_source_with_no_marks_gets_no_rail(config: Config) -> None:
    """So the Cookbook's rail is exactly what it was."""
    assert mark_rows([Unit(id="demo:2.4:61")], config, "demo") == []
