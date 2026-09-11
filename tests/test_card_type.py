"""`identity` states a fact; `intuition` explains one.

The split exists because a prose source yields both, and they want different
new-card rates: five mechanical restatements a day is comfortable and five
pieces of intuition a day is not.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import check, model, sync, verify
from anki_math_forge import config as config_mod
from anki_math_forge.config import Config
from anki_math_forge.model import Card


def a_card(card_type: str, **sections: str) -> Card:
    body = {"front": "why is it tight?", "back": "because the bound is attained", **sections}
    return model.parse(
        "---\n"
        f"uid: abc123\ntype: {card_type}\nstatus: draft\nsource: A Book\nunit: book:1:1\n"
        "---\n\n" + "".join(f"## {name}\n{text}\n\n" for name, text in body.items())
    )


# -- what each type may hold ------------------------------------------------


def test_both_types_are_known(config: Config) -> None:
    for card_type in ("identity", "intuition"):
        findings = check.check_card(a_card(card_type), config)
        assert not [f for f in findings if f.code == "type-unknown"]


def test_an_unknown_type_is_still_refused(config: Config) -> None:
    """A typo would otherwise get its own section whitelist of nothing."""
    codes = {f.code for f in check.check_card(a_card("intution"), config)}
    assert "type-unknown" in codes


def test_intuition_has_no_verify_section(config: Config) -> None:
    """There is nothing numeric to check about an explanation."""
    findings = check.check_card(a_card("intuition", verify="x = 1"), config)
    assert any(f.code == "section-unknown" for f in findings)
    assert not [f for f in check.check_card(a_card("identity", verify="x = 1"), config)
                if f.code == "section-unknown"]


def test_intuition_has_no_conditions_section(config: Config) -> None:
    """A hypothesis belongs to a statement. Anything that genuinely needs one
    is an identity wearing the wrong type."""
    findings = check.check_card(a_card("intuition", conditions="$A$ invertible"), config)
    assert any(f.code == "section-unknown" for f in findings)


def test_prose_and_uses_are_kept(config: Config) -> None:
    """An explanation is mostly prose, so removing it would leave nothing."""
    findings = check.check_card(a_card("intuition", prose="It measures spread."), config)
    assert not [f for f in findings if f.code == "section-unknown"]


# -- verify never runs on one -----------------------------------------------


def test_verify_skips_an_intuition_card() -> None:
    """Counting them in the denominator would make coverage look worse every
    time the deck got better."""
    result = verify.verify_card(a_card("intuition"))
    assert result.status == verify.SKIP
    assert "intuition" in result.detail


# -- where each lands in Anki -----------------------------------------------


def test_a_source_may_send_each_type_to_its_own_deck(repo: Path) -> None:
    folder = repo / "sources" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "A Book"\ndeck = "Shelf"\n\n'
        '[decks]\nidentity = "Shelf::Statements"\nintuition = "Shelf::Intuition"\n+++\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)

    assert config.deck_for("book", "identity") == "Shelf::Statements"
    assert config.deck_for("book", "intuition") == "Shelf::Intuition"
    assert config.deck_for("book") == "Shelf", "the source's own deck when no type is named"


def test_a_source_without_a_mapping_sends_everything_to_one_deck(repo: Path) -> None:
    """Subdecks are for a different new-card rate. A source that does not want
    one should not be made to have two decks."""
    folder = repo / "sources" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        '+++\ntitle = "A Book"\ndeck = "Shelf"\n+++\n', encoding="utf-8"
    )
    config = config_mod.load(repo)

    assert config.deck_for("book", "identity") == "Shelf"
    assert config.deck_for("book", "intuition") == "Shelf"


def test_the_type_reaches_anki_as_a_tag(config: Config) -> None:
    """So a deck holding both can be drilled separately without splitting it."""
    assert "type::intuition" in sync.tags_for(a_card("intuition"), config)
    assert "type::identity" in sync.tags_for(a_card("identity"), config)
