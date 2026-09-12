"""One line per unit saying what a card from it would be about.

Triage answers two questions -- is this worth a card at all, and roughly what
would the card be about (CLAUDE.md invariant 9). The crop answers the first.
Nothing answered the second, and a human cannot answer it 750 times by
squinting at pictures, so `/gist` answers it in advance and cheaply.

The whole value is the asymmetry: disagreeing with a gist at triage costs one
keystroke, and the same misunderstanding found after `/extract-cards` has
written a card costs a rewrite. Which is also why it has to be *visibly* a
reading rather than a fact.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.app import _unit_payload
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger, Locator, Unit


def _seed(config: Config, *units: Unit) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.extend(units)
    led.save()


def a_unit(uid: str, **fields: object) -> Unit:
    return Unit(id=f"demo:{uid}", locator=Locator(section="2.2", page=1), **fields)


def test_a_unit_starts_without_one(config: Config) -> None:
    assert Unit(id="demo:2.4:61").gist == ""


def test_it_is_not_written_when_empty(config: Config) -> None:
    """751 Cookbook units must not each grow a `"gist": ""`."""
    assert "gist" not in Unit(id="demo:2.4:61").to_json()
    assert Unit(id="demo:2.4:61", gist="Lemma 2").to_json()["gist"] == "Lemma 2"


def test_it_survives_a_re_extraction(config: Config) -> None:
    """Not an extraction-owned field. Re-segmenting must not throw away a pass
    that has already run over the book."""
    _seed(config, a_unit("a", gist="inverse of a product"))
    led = Ledger.load(config.units_path("demo"))
    led.upsert([a_unit("a")])
    led.save()
    assert Ledger.load(config.units_path("demo")).get("demo:a").gist == "inverse of a product"


def test_the_cli_sets_and_clears_it(repo: Path, capsys: object) -> None:
    config = config_mod.load(repo)
    _seed(config, a_unit("a"))
    args = ["--root", str(repo), "units", "--id", "demo:a", "--gist"]

    cli.main([*args, "why the bound needs independence"])
    assert Ledger.load(config.units_path("demo")).get("demo:a").gist == (
        "why the bound needs independence"
    )

    cli.main([*args, ""])
    assert Ledger.load(config.units_path("demo")).get("demo:a").gist == ""


def test_it_is_collapsed_to_one_line(repo: Path) -> None:
    """A gist that runs to a paragraph is a card being written at the wrong
    stage, and it would not fit the one place it is shown."""
    config = config_mod.load(repo)
    _seed(config, a_unit("a"))
    cli.main(["--root", str(repo), "units", "--id", "demo:a", "--gist", "  two\n lines  "])
    assert Ledger.load(config.units_path("demo")).get("demo:a").gist == "two lines"


def test_the_pass_can_find_what_it_has_left(repo: Path, capsys: object) -> None:
    config = config_mod.load(repo)
    _seed(config, a_unit("a", gist="done"), a_unit("b"))

    cli.main(["--root", str(repo), "units", "--ungisted", "--json"])
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "demo:b" in out
    assert "demo:a" not in out


def test_the_crop_manifest_carries_what_the_pass_needs(repo: Path) -> None:
    """The mark's own sentence, and nothing else. On a prose source the subject
    of a unit *is* the marked sentence, so asking a model to re-derive it from
    a picture of itself is wasted work and a worse answer. Deliberately not the
    neighbours: a gist is supposed to be cheap."""
    import inspect

    from anki_math_forge.cli import cmd_crops

    source = inspect.getsource(cmd_crops)
    assert '"marked": unit.marks[0].text if unit.marks else ""' in source
    assert '"comment": unit.marks[0].comment if unit.marks else ""' in source
    assert "neighbours" in source, "and a comment saying why they are not here"


def test_it_reaches_the_triage_view(config: Config) -> None:
    payload = _unit_payload(a_unit("a", gist="Lemma 2"), config)
    assert payload["gist"] == "Lemma 2"


def test_nothing_downstream_consumes_it() -> None:
    """The safety property, and the reason it is a separate field rather than a
    line in the brief.

    `/extract-cards` reads the crop, the page and the `@claude` brief. A
    machine's reading written into that channel would come back one pass later
    as the human's instruction, with nothing to tell the two apart -- and the
    pass would then be taking dictation from its own earlier guess.
    """
    from anki_math_forge import check, context, sync

    # `context` builds what a card writer reads and `sync` builds what reaches
    # Anki. A gist in either becomes an instruction or becomes content, which
    # is the whole failure this field is shaped to avoid.
    for module in (context, sync):
        assert ".gist" not in Path(module.__file__).read_text(encoding="utf-8"), (
            f"{module.__name__} reads the gist; it is a window, not a wire"
        )

    # `check` is the exception, and a narrow one: it may measure the caption's
    # length, because linting a field is not consuming it. It may not let the
    # caption decide anything else, so there is exactly one mention and it is
    # the length rule.
    source = Path(check.__file__).read_text(encoding="utf-8")
    reads = [line.strip() for line in source.splitlines() if ".gist" in line]
    assert reads, "the length rule went away"
    for line in reads:
        assert "len(card.gist)" in line, (
            f"check reads the caption's content, not only its length: {line}"
        )
