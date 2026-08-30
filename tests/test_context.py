"""`context` hands over the page an equation was printed on. That is all.

The conditions an identity needs are usually printed around it rather than in
it, so the page goes over whole. Which sentence bears on which equation, and
whether the identity needs something the page never states, is mathematics --
judged by whoever writes the card, not by anything here.
"""

from __future__ import annotations

from anki_forge import context
from anki_forge.config import Config
from anki_forge.extract import source_text_path
from anki_forge.ledger import Ledger, Locator, Unit


def _source(config: Config, text: str) -> None:
    path = source_text_path(config, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_it_returns_the_units_own_page(config: Config) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(
        Unit(
            id="demo:2.2:61",
            locator=Locator(section="2.2", equation=61, page=10),
            tex_auto="x = y",
        )
    )
    led.save()
    _source(
        config,
        "## page 9\nprevious-page-marker\n\n"
        "## page 10\nLet A be invertible.\ndaX-1b dX (61)\n\n"
        "## page 11\nnext-page-marker\n",
    )

    found = context.assemble(config, "demo:2.2:61")
    assert found is not None
    assert "Let A be invertible." in found.page_text
    assert "previous-page-marker" not in found.page_text
    assert "next-page-marker" not in found.page_text
    assert found.transcription == "x = y"


def test_a_missing_text_layer_is_not_an_error(config: Config) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:1:1", locator=Locator(section="1", page=1)))
    led.save()
    found = context.assemble(config, "demo:1:1")
    assert found is not None
    assert found.page_text == ""
    assert "no text layer" in found.format()


def test_an_unknown_unit_returns_nothing(config: Config) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:1:1", locator=Locator(section="1", page=1)))
    led.save()
    assert context.assemble(config, "demo:1:nope") is None
    assert context.assemble(config, "nosuchsource:1:1") is None


def test_no_vocabulary_is_baked_in() -> None:
    """No list of English mathematical adjectives, and no guessing.

    An earlier version matched words like "invertible" and pointed at the
    match. On the first real unit it pointed at a sentence governing a
    different equation further down the page.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "src" / "anki_forge" / "context.py"
    ).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]
    for word in ("symmetric", "hermitian", "positive definite", "full rank"):
        assert word not in body.lower(), f"{word!r} is back in the code"
