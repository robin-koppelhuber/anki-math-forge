"""`classify` proposes; it never applies. And it reads the best source it has."""

from __future__ import annotations

from pathlib import Path

from anki_math_forge.classify import RELATION, classify
from anki_math_forge.ledger import Ledger, Locator, Unit


def test_relation_matches_both_alphabets() -> None:
    """The text layer speaks Unicode, a transcription speaks LaTeX."""
    for stated in ("a = b", "x ≤ y", r"x \leq y", r"A \succeq 0"):
        assert RELATION.search(stated), stated
    for not_stated in ("just some prose", r"\begin{bmatrix} a \\ b \end{bmatrix}"):
        assert not RELATION.search(not_stated), not_stated


def test_a_macro_boundary_is_required() -> None:
    r"""\infty is not a relation, and \int is not \in."""
    assert not RELATION.search(r"\infty")
    assert not RELATION.search(r"\int f")
    assert RELATION.search(r"x \in S")


def test_transcription_beats_the_text_layer(tmp_path: Path) -> None:
    """A transcribed identity must not be proposed for skipping.

    With no PDF the text layer is unavailable, so the transcription is the
    only thing that can save this unit from a false `no-relation` skip.
    """
    led = Ledger(tmp_path / "units.jsonl")
    led.units.append(
        Unit(id="s:eq:1", locator=Locator(page=9), tex_auto=r"A \succeq 0")
    )
    report = classify(led, None, "s", write=True)
    assert not report.classified, "a stated relation must not be skipped"
    assert led.units[0].suggestion is None
    assert led.units[0].state == "new", "classify applies nothing"
