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
from anki_math_forge.ledger import Ledger, Locator, Unit

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
    folder = repo / "sources" / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "Demo"\ncontext_pages = 4\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(repo)
    _seed(config)
    assert _span(config) == {f"body {n}" for n in range(16, 25)}


def test_the_unit_beats_its_source(repo: Path) -> None:
    folder = repo / "sources" / "demo"
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
