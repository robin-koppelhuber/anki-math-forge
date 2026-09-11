"""Per-source overrides: which deck a book files into, which layout it uses."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_forge import config as config_mod


def two_source_repo(repo: Path, **book: str) -> config_mod.Config:
    """`demo` inherits the repo defaults; `book` overrides whatever is given."""
    toml = (repo / "anki-forge.toml").read_text(encoding="utf-8")
    toml += '\n[sources.book]\ntitle = "A Book"\n'
    for key, value in book.items():
        toml += f'{key} = "{value}"\n'
    (repo / "anki-forge.toml").write_text(toml, encoding="utf-8")
    return config_mod.load(repo)


def test_deck_falls_back_to_the_repo_default(repo: Path) -> None:
    config = two_source_repo(repo)
    assert config.deck_for("book") == config.deck
    assert config.deck_for("demo") == config.deck
    assert config.deck_for("") == config.deck, "a card naming no source still lands somewhere"


def test_a_source_may_name_its_own_deck(repo: Path) -> None:
    config = two_source_repo(repo, deck="Physics::Tensors")
    assert config.deck_for("book") == "Physics::Tensors"
    assert config.deck_for("demo") == config.deck, "the override is not repo-wide"


def test_a_source_may_name_its_own_layout(repo: Path) -> None:
    config = two_source_repo(repo, layout="numerator")
    assert config.layout_for("book") == "numerator"
    assert config.layout_for("demo") == "denominator"


def test_an_unrecognised_layout_is_refused_at_load(repo: Path) -> None:
    """It would otherwise read as "not denominator" and silently change what
    every card from that source means."""
    with pytest.raises(config_mod.ConfigError, match="denominator"):
        two_source_repo(repo, layout="denomenator")


def test_source_order_defaults_to_printed(repo: Path) -> None:
    assert two_source_repo(repo).source("book").order == "printed"


def test_a_source_can_say_its_printed_order_means_nothing(repo: Path) -> None:
    """An alphabetical table or a paper whose results precede their lemmas
    should not have its print order followed as if it were a syllabus."""
    assert two_source_repo(repo, order="none").source("book").order == "none"


def test_an_unrecognised_order_is_refused_at_load(repo: Path) -> None:
    with pytest.raises(config_mod.ConfigError, match="printed"):
        two_source_repo(repo, order="alphabetical")
