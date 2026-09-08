"""Ledger annotations: who a note is addressed to decides who may clear it."""

from __future__ import annotations

from pathlib import Path

from anki_forge import config as config_mod
from anki_forge import extract
from anki_forge.ledger import Ledger


def test_resolve_notes_defaults_to_claude_only(repo: Path) -> None:
    """A `@me` decision parked beside a `@claude` request must survive the
    agent resolving its own note. The CLI never registered `--audience`, so
    the default reached `resolve_notes` as "" and cleared both."""
    from anki_forge import cli

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
    from anki_forge import cli

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
