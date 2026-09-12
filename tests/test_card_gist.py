"""A few words naming a card, for anywhere its LaTeX front is unreadable.

The unit stage answers "roughly what would the card be about" in one line.
Once the card existed nothing carried that answer forward, so a list of cards,
a `requires` link and a graph node each had a six-hex uid and a formula to
identify it by.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import check, extract, model
from anki_math_forge.app import card_gist, create_app
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger
from anki_math_forge.model import UNHASHED_FRONTMATTER


@pytest.fixture
def units(config: Config) -> Ledger:
    extract.run(config, "demo")
    return Ledger.load(config.units_path("demo"))


def write(config: Config, uid: str, unit: str, **front: object) -> Path:
    path = config.cards_dir / "demo" / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = "".join(f"{k}: {v}\n" for k, v in front.items())
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\nunit: {unit}\n{keys}---\n\n"
        "## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )
    return path


def test_a_caption_is_not_card_content(config: Config) -> None:
    """Unhashed, like `frequency` and `web`. A later pass improving the wording
    must not send an approved card back through review: nobody touched the
    mathematics, and the caption never reaches Anki or a reviewer."""
    assert "gist" in UNHASHED_FRONTMATTER
    card = model.load(write(config, "aaa111", "demo:2.4:61"))
    before = card.content_hash()
    card.frontmatter["gist"] = "the adjugate in terms of the inverse"
    assert card.content_hash() == before


def test_adding_the_exemption_moved_no_hash_that_existed(config: Config) -> None:
    """The exemption was safe to add precisely because no card carried the key.
    Widening `UNHASHED_FRONTMATTER` over a field cards *do* carry is the mass
    demotion invariant 5 exists to prevent, and it needs the legacy shim."""
    card = model.load(write(config, "bbb222", "demo:2.4:61"))
    assert card.gist == "", "a card with no caption has none, rather than a guess"
    assert card.content_hash() == card.content_hash(legacy=True)


def test_it_falls_back_to_the_unit_that_produced_the_card(
    config: Config, units: Ledger
) -> None:
    """A unit's gist already answers "what would a card from this be about",
    and this is that card. Inherited rather than copied in, so re-running
    `/gist` on the unit corrects every card written from it."""
    unit = next(iter(units))
    unit.gist = "what the unit says it is"
    units.save()

    card = model.load(write(config, "ccc333", unit.id))
    assert card_gist(card, config) == "what the unit says it is"

    card.frontmatter["gist"] = "what the card says it is"
    card.save()
    assert card_gist(model.load(card.path), config) == "what the card says it is", (
        "the card's own caption wins over the unit's"
    )


def test_no_caption_is_a_gap_rather_than_a_slug(config: Config, units: Ledger) -> None:
    """The filename slug is a transliteration of the LaTeX
    (`prod-i-lambda-i-where-lambda-i-text-eig`), which is the thing a caption
    is supposed to spare you. Better to show the gap."""
    card = model.load(write(config, "ddd444", next(iter(units)).id))
    assert card_gist(card, config) == ""


def test_a_caption_past_the_cap_is_a_warning_and_not_an_error(config: Config) -> None:
    """A long one still beats none, and no card should be blocked from syncing
    by its caption."""
    card = model.load(write(config, "eee555", "demo:2.4:61", gist="x " * 60))
    codes = {f.code: f.level for f in check.check_card(card, config)}
    assert codes.get("gist-too-long") == check.WARN


def test_the_review_view_shows_it(config: Config) -> None:
    write(config, "fff666", "demo:2.4:61", gist="the adjugate in terms of the inverse")
    body = TestClient(create_app(config)).get("/review?status=all").text
    assert "the adjugate in terms of the inverse" in body
