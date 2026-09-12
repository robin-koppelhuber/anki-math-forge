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


def test_a_caption_does_not_demote_a_card_stamped_under_the_old_rule(
    config: Config,
) -> None:
    """The case the fixture above cannot see, and the one the whole deck is in.

    Every approval in this repo predates the `frequency`/`derivation`/`web`
    exemption, so its stored hash is the *legacy* digest and the current one
    does not match it. A card whose two digests coincide -- a freshly written
    one, with none of those keys -- proves nothing about that.

    Measured before this was fixed: `af5ca1`, approved and matching, went to
    `draft` the moment it was given a caption. `/augment` writing one per card
    would have demoted all 108 in a single pass.
    """
    card = model.load(
        write(config, "ccc111", "demo:2.4:61", frequency="core", derivation="short")
    )
    card.frontmatter["content_hash"] = card.content_hash(legacy=True)
    card.frontmatter["status"] = "approved"
    card.save()

    stamped = model.load(card.path)
    assert stamped.content_hash() != stamped.frontmatter["content_hash"], (
        "this fixture is only meaningful while the two digests differ"
    )
    assert stamped.hash_matches() and stamped.effective_status == "approved"

    stamped.frontmatter["gist"] = "the determinant as a product of eigenvalues"
    stamped.save()

    after = model.load(card.path)
    assert after.hash_matches(), "a caption broke a legacy-stamped approval"
    assert after.effective_status == "approved"


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


def test_the_stub_carries_it_rather_than_being_patched_afterwards(
    config: Config, units: Ledger
) -> None:
    """`forge new` takes it, because whoever runs that has just decided what
    the card is and every later pass reads it back off the LaTeX."""
    import argparse

    from anki_math_forge import cli

    unit = next(iter(units))
    args = argparse.Namespace(
        unit=[unit.id],
        front="$a$",
        back="$b$",
        type="identity",
        tag=[],
        source="",
        gist="derivative of log det",
        json=False,
    )
    assert cli.cmd_new(args, config) == cli.OK
    written = [c for c in model.load_all(config.cards_dir) if c.gist]
    assert [c.gist for c in written] == ["derivative of log det"]


def test_an_unnamed_stub_carries_no_empty_key(config: Config, units: Ledger) -> None:
    """`gist: ''` in a file reads as a considered blank rather than as a card
    nobody has named yet, and `/augment` would have no way to tell."""
    card = model.stub(uid="a1b2c3", front="$a$", back="$b$", source="", unit="")
    assert "gist" not in card.frontmatter


def test_a_dependency_link_says_what_it_is(config: Config) -> None:
    """`needs af5ca1, ae6e48` names two cards and says nothing about which
    two, which is the one thing you want while deciding whether the edge is
    real."""
    write(config, "aaa999", "demo:2.4:61", gist="the product of the eigenvalues")
    dependent = model.load(write(config, "bbb999", "demo:2.4:61"))
    dependent.frontmatter["requires"] = ["aaa999"]
    dependent.save()

    body = TestClient(create_app(config)).get("/review?status=all").text
    assert "the product of the eigenvalues" in body
    assert 'class="dep-gist"' in body


def test_it_never_reaches_anki(config: Config) -> None:
    """A caption is not content. `sync` builds the note's fields from the
    sections, and a field nobody reviews has no business in the collection."""
    from anki_math_forge import notetype

    assert "gist" not in [f.lower() for f in notetype.FIELDS]
