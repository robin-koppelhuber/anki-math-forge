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


PAGES = (
    "## page 9\nprevious-page-marker\n\n"
    "## page 10\nLet A be invertible.\ndaX-1b dX (61)\n\n"
    "## page 11\nnext-page-marker\n"
)


def _one_unit(config: Config) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(
        Unit(
            id="demo:2.2:61",
            locator=Locator(section="2.2", equation=61, page=10),
            tex_auto="x = y",
        )
    )
    led.save()
    _source(config, PAGES)


def test_it_returns_the_page_and_its_neighbours(config: Config) -> None:
    """The default is generous on purpose. A card is easier to write and
    quicker to review when whoever wrote it could see the paragraph that states
    the conditions, and that paragraph is as often on the page before."""
    _one_unit(config)

    found = context.assemble(config, "demo:2.2:61")
    assert found is not None
    assert "Let A be invertible." in found.page_text
    assert "previous-page-marker" in found.page_text
    assert "next-page-marker" in found.page_text
    assert found.transcription == "x = y"


def test_one_page_only_when_asked_for_one(config: Config) -> None:
    """Triage is deciding whether a region is worth carding at all, and a wall
    of text makes that harder rather than easier."""
    _one_unit(config)

    found = context.assemble(config, "demo:2.2:61", spread=0)
    assert found is not None
    assert "Let A be invertible." in found.page_text
    assert "previous-page-marker" not in found.page_text
    assert "next-page-marker" not in found.page_text


def test_more_pages_when_asked_for_more(config: Config) -> None:
    """A pass that writes the card should ask for as much as is reasonable."""
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=10)))
    led.save()
    _source(config, "".join(f"## page {n}\nbody {n}\n\n" for n in range(1, 21)))

    wide = context.assemble(config, "demo:2.2:61", spread=5)
    assert wide is not None
    assert "body 5" in wide.page_text and "body 15" in wide.page_text
    assert "body 4" not in wide.page_text


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


def test_conventions_come_from_the_source(config: Config) -> None:
    """Per source, not per project.

    "Denominator layout" and "entries are real" are facts about one book. In
    the project's own contract they would be wrong the moment a second source
    arrived, and a card writer would be reading conventions that do not apply
    to the page in front of them.
    """
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:1:1", locator=Locator(section="1", page=1)))
    led.save()
    _source(config, "## page 1\nsomething\n")

    path = config.sources_dir / "demo" / "conventions.md"
    path.write_text("# Conventions\n\n- entries are quaternions\n", encoding="utf-8")

    found = context.assemble(config, "demo:1:1")
    assert found is not None
    assert "quaternions" in found.conventions
    assert "quaternions" in found.format()


def test_a_source_with_no_conventions_says_so(config: Config) -> None:
    """Silence would read as "there are none", which is never why they are absent."""
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:1:1", locator=Locator(section="1", page=1)))
    led.save()
    _source(config, "## page 1\nsomething\n")

    found = context.assemble(config, "demo:1:1")
    assert found is not None
    assert found.conventions == ""
    assert "none recorded" in found.format(), "an absent convention is a writer guessing"
