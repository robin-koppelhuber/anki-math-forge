"""Ledger annotations: who a note is addressed to decides who may clear it."""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import config as config_mod
from anki_math_forge import extract
from anki_math_forge.ledger import Ledger, Locator, Unit


def test_resolve_notes_defaults_to_claude_only(repo: Path) -> None:
    """A `@me` decision parked beside a `@claude` request must survive the
    agent resolving its own note. The CLI never registered `--audience`, so
    the default reached `resolve_notes` as "" and cleared both."""
    from anki_math_forge import cli

    config = config_mod.load(repo)
    extract.run(config, "demo")
    led = Ledger.load(config.units_path("demo"))
    unit_id = led.units[0].id
    led.annotate(unit_id, "@claude a request")
    led.annotate(unit_id, "@me a decision only the human makes")
    led.save()

    cli.main(["--root", str(repo), "units", "--id", unit_id, "--resolve-notes"])

    notes = Ledger.load(config.units_path("demo")).get(unit_id).notes
    assert notes == ["@me a decision only the human makes"]


def test_resolve_notes_all_clears_everything(repo: Path) -> None:
    from anki_math_forge import cli

    config = config_mod.load(repo)
    extract.run(config, "demo")
    led = Ledger.load(config.units_path("demo"))
    unit_id = led.units[0].id
    led.annotate(unit_id, "@claude a request")
    led.annotate(unit_id, "@me a decision")
    led.save()

    cli.main(
        ["--root", str(repo), "units", "--id", unit_id, "--resolve-notes", "--audience", "all"]
    )

    assert Ledger.load(config.units_path("demo")).get(unit_id).notes == []


# -- the locator, generalised beyond equation numbers -----------------------


def test_the_cookbook_locator_is_unchanged() -> None:
    """751 units on disk record `equation`. Generalising the locator must not
    restate them, and must not read them differently."""
    loc = Locator(section="2.4", equation=61, page=12)
    assert loc.ref == ("equation", "61")
    assert loc.describe() == "§2.4, eq. 61, p. 12"


def test_ref_unifies_both_forms() -> None:
    """One reader for the frozen segmenter's output and the general form, so
    nothing downstream has to know which it is looking at."""
    assert Locator(equation=61).ref == ("equation", "61")
    assert Locator(kind="theorem", label="2.4").ref == ("theorem", "2.4")
    assert Locator().ref == ("", "")


def test_an_unnumbered_kind_says_nothing_in_a_citation() -> None:
    """A Zotero highlight is a "highlight" and nothing numbers it. The citation
    wants "p. 8", not "Highlight, p. 8"."""
    assert Locator(kind="theorem", label="2.4", page=17).describe() == "Theorem 2.4, p. 17"
    assert Locator(kind="highlight", page=8).describe() == "p. 8"


def test_document_round_trips_and_stays_out_of_the_way(tmp_path: Path) -> None:
    """A source can hold many documents; page 17 of one is not page 17 of
    another. An empty `document` is not written, so single-document sources
    keep the lines they have."""
    led = Ledger(path=tmp_path / "units.jsonl")
    led.units.append(Unit(id="papers:wegel:a1", locator=Locator(document="ZIETASLD", page=8)))
    led.units.append(Unit(id="demo:2.4:61", locator=Locator(equation=61)))
    led.save()

    back = Ledger.load(tmp_path / "units.jsonl")
    assert back.get("papers:wegel:a1").locator.document == "ZIETASLD"
    assert back.get("demo:2.4:61").locator.document == ""
    assert "document" not in led.path.read_text(encoding="utf-8").splitlines()[1]
