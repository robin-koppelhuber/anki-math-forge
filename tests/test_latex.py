"""LaTeX validation: both backends, and the math-span handling around them."""

from __future__ import annotations

import pytest

from anki_math_forge import latex

katex_available = latex._katex_js() is not None
needs_katex = pytest.mark.skipif(
    not katex_available, reason="no katex.min.js found (npm install katex)"
)

VALID = [
    r"\frac{\partial}{\partial X}\log\det X",
    r"X^{-\top}",
    r"\operatorname{tr}(AB) = \operatorname{tr}(BA)",
    r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
    r"\left( A + B \right)^{-1}",
    r"\sum_{i=1}^{n} \alpha_i x_i",
]

INVALID = [
    r"\frac{a}{b",
    r"\left( a + b",
    r"\begin{pmatrix} a & b",
    r"\bogusmacro{x}",
]


@pytest.mark.parametrize("tex", VALID)
def test_builtin_accepts_real_mathematics(tex: str) -> None:
    assert latex.BuiltinChecker().validate(tex) is None


@pytest.mark.parametrize("tex", INVALID)
def test_builtin_rejects_broken_mathematics(tex: str) -> None:
    assert latex.BuiltinChecker().validate(tex) is not None


def test_extra_macros_widen_the_builtin_allowlist() -> None:
    assert latex.BuiltinChecker().validate(r"\vecop{x}") is not None
    assert latex.BuiltinChecker(("vecop",)).validate(r"\vecop{x}") is None


@needs_katex
@pytest.mark.parametrize("tex", VALID)
def test_katex_accepts_real_mathematics(tex: str) -> None:
    checker = latex.checker(())
    assert checker.name == "katex"
    assert checker.validate(tex) is None
    assert checker.describe() == "katex", "a silent fallback would make this test a lie"


@needs_katex
@pytest.mark.parametrize("tex", INVALID)
def test_katex_rejects_broken_mathematics(tex: str) -> None:
    problem = latex.checker(()).validate(tex)
    assert problem is not None
    assert "KaTeX parse error" in problem


@needs_katex
def test_katex_is_stricter_than_the_builtin() -> None:
    """An alignment marker outside an environment: structurally fine, invalid."""
    assert latex.BuiltinChecker().validate("a & b") is None
    assert latex.checker(()).validate("a & b") is not None


@needs_katex
def test_priming_batches_the_work() -> None:
    checker = latex.checker(())
    assert isinstance(checker, latex.KatexChecker)
    checker.prime(VALID)
    assert all(tex in checker._cache for tex in VALID)


# -- math spans ------------------------------------------------------------


def test_display_and_inline_spans_are_distinguished() -> None:
    spans = latex.math_spans("inline $a$ and display $$b$$")
    assert [(s.tex, s.display) for s in spans] == [("a", False), ("b", True)]


def test_escaped_dollars_are_not_delimiters() -> None:
    assert latex.math_spans(r"costs \$5 and \$6") == []


def test_unbalanced_dollars_are_detected() -> None:
    assert latex.unbalanced_dollars("$a$ and $b")
    assert not latex.unbalanced_dollars("$a$ and $b$")
    assert not latex.unbalanced_dollars(r"\$5")


def test_rendered_length_counts_glyphs_not_markup() -> None:
    short = latex.rendered_length(r"$\frac{\partial}{\partial X}\log\det X$")
    long = latex.rendered_length("a sentence of ordinary prose that is quite a bit longer")
    assert short < long
