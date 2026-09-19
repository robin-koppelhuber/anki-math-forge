"""The `verify` corruption suite: flip a transpose or a sign, assert rejection."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from anki_math_forge import model, verify
from anki_math_forge.config import Config
from anki_math_forge.model import Card, Section

# d/dX log|det X| = X^-T, on a *non-symmetric* X so the transpose is load-bearing.
LOGDET = """```python
X = invertible(4)
lhs = grad(lambda M: np.log(abs(np.linalg.det(M))), X)
rhs = np.linalg.inv(X).T
```"""

LOGDET_NO_TRANSPOSE = LOGDET.replace("np.linalg.inv(X).T", "np.linalg.inv(X)")

TRACE = """```python
A = randn(4, 4)
X = randn(4, 4)
lhs = grad(lambda M: np.trace(A @ M), X)
rhs = A.T
```"""

TRACE_WRONG_SIGN = TRACE.replace("rhs = A.T", "rhs = -A.T")

SHAPE_MISMATCH = """```python
lhs = randn(3, 3)
rhs = randn(4, 4)
```"""


def card(snippet: str, *, uid: str = "aa11bb", enabled: bool = True) -> Card:
    # `unit` names the source, and the source is where the layout lives now --
    # there is no repo-wide default any more, and `verify` refuses a card whose
    # source declares none rather than checking against a guess.
    return Card(
        frontmatter={
            "uid": uid,
            "type": "identity",
            "status": "draft",
            "verify": enabled,
            "unit": "demo:2.4:61",
        },
        sections=[
            Section("front", "$a$"),
            Section("back", "$b$"),
            Section("verify", snippet),
        ],
    )


def test_a_correct_identity_passes() -> None:
    result = verify.verify_card(card(LOGDET))
    assert result.status == verify.PASS, result.detail


def test_a_dropped_transpose_is_rejected() -> None:
    result = verify.verify_card(card(LOGDET_NO_TRANSPOSE))
    assert result.status == verify.FAIL
    assert "lhs - rhs" in result.detail


def test_a_flipped_sign_is_rejected() -> None:
    assert verify.verify_card(card(TRACE_WRONG_SIGN)).status == verify.FAIL
    assert verify.verify_card(card(TRACE)).status == verify.PASS


def test_a_shape_mismatch_is_rejected() -> None:
    result = verify.verify_card(card(SHAPE_MISMATCH))
    assert result.status == verify.FAIL
    assert "shape mismatch" in result.detail


def test_verification_is_off_by_default() -> None:
    assert verify.verify_card(card(LOGDET, enabled=False)).status == verify.SKIP


def test_an_empty_verify_section_is_an_error() -> None:
    assert verify.verify_card(card("")).status == verify.ERROR


def test_a_snippet_without_lhs_and_rhs_is_an_error() -> None:
    assert verify.verify_card(card("```python\nx = 1\n```")).status == verify.ERROR


def test_a_broken_snippet_reports_rather_than_raises() -> None:
    result = verify.verify_card(card("```python\nlhs = 1 +\n```"))
    assert result.status == verify.ERROR
    assert "syntax error" in result.detail


def test_a_snippet_that_throws_reports_rather_than_raises() -> None:
    result = verify.verify_card(card("```python\nlhs = np.linalg.inv(randn(3, 4))\nrhs = 1\n```"))
    assert result.status == verify.ERROR


def test_the_snippet_namespace_is_small() -> None:
    """Not a sandbox -- it is local repo code -- but not a kitchen sink either."""
    result = verify.verify_card(card("```python\nlhs = open('x')\nrhs = 1\n```"))
    assert result.status == verify.ERROR


def test_fences_are_optional() -> None:
    bare = "X = invertible(3)\nlhs = np.linalg.inv(X) @ X\nrhs = np.eye(3)"
    assert verify.verify_card(card(bare)).status == verify.PASS


def test_results_are_deterministic() -> None:
    first = verify.verify_card(card(LOGDET))
    second = verify.verify_card(card(LOGDET))
    assert first.worst == second.worst


def test_run_over_a_repo_skips_cards_that_did_not_opt_in(
    config: Config, repo: Path, card_path: Path
) -> None:
    card(LOGDET, uid="bb22cc").save(repo / "cards" / "bb22cc-logdet.md")
    results = verify.run(model.load_all(config.cards_dir), config)
    by_uid = {r.uid: r.status for r in results}
    assert by_uid["7f3a2b"] == verify.SKIP
    assert by_uid["bb22cc"] == verify.PASS


@pytest.mark.parametrize("trials", [1, 3])
def test_trial_count_is_honoured(trials: int) -> None:
    result = verify.verify_card(card(LOGDET), trials=trials)
    assert f"{trials} trials" in result.detail


def test_the_gradient_is_x_shaped_not_x_transpose_shaped() -> None:
    """Denominator layout, pinned to a rectangular case.

    CLAUDE.md claimed `d(scalar)/dX` has the shape of `X^T` while `grad()` has
    always produced the shape of `X`. On a square `X` the two are
    indistinguishable, which is why the contradiction sat in the contract
    until a card-writing pass hit eq. 55 with a rectangular `X`.
    """
    rng = np.random.default_rng(0)
    x = rng.normal(size=(5, 3))
    out = verify.grad(lambda m: float(np.log(np.linalg.det(m.T @ m))), x)
    assert out.shape == x.shape, "denominator layout: the gradient is shaped like X"
    assert out.shape != x.T.shape
    # and it is the Cookbook's eq. 55 value
    assert np.abs(out - 2 * np.linalg.pinv(x).T).max() < 1e-7


def test_verify_refuses_a_layout_its_gradient_cannot_compute(repo: Path) -> None:
    """`grad` computes denominator layout only. The two agree on every square
    matrix, so checking a numerator source against it would pass most cards and
    fail the rectangular ones for a reason nobody would guess."""
    from anki_math_forge import config as config_mod

    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    toml += '\n[projects.book]\ntitle = "A Book"\nlayout = "numerator"\n'
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    config = config_mod.load(repo)

    card = model.parse(
        "---\nuid: bbb222\ntype: identity\nstatus: draft\n"
        'unit: "book:1.1:1"\nverify: true\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n\n"
        "## verify\n```python\n"
        "X = spd(3)\n"
        "lhs = grad(lambda M: float(np.trace(M)), X)\n"
        "rhs = np.eye(3)\n"
        "```\n"
    )
    results = verify.run([card], config)
    assert [r.status for r in results] == [verify.SKIP]
    assert "numerator" in results[0].detail


def test_a_card_with_no_derivative_needs_no_declared_layout(repo: Path) -> None:
    """Requiring one of every card was the Cookbook generalised into a rule: a
    book of matrix derivatives, where the convention always decided the answer.
    An identity between two Gaussians has no layout to declare."""
    from anki_math_forge import config as config_mod

    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    toml += '\n[projects.paper]\ntitle = "A Paper"\n'
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    config = config_mod.load(repo)

    card = model.parse(
        "---\nuid: ccc333\ntype: identity\nstatus: draft\n"
        'unit: "paper:2.1:4"\nverify: true\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n\n"
        "## verify\n```python\n"
        "x = randn(4)\n"
        "lhs = float(np.sum(x**2))\n"
        "rhs = float(x @ x)\n"
        "```\n"
    )

    results = verify.run([card], config)

    assert [r.status for r in results] == [verify.PASS], results[0].detail


def test_the_layout_refusal_comes_from_the_helper_it_is_about() -> None:
    """Asking every card whether it takes a derivative was the same overfit
    one level up. Only `grad` has a layout, so only `grad` asks."""
    import numpy as np

    env = verify.namespace(np.random.default_rng(0), "numerator")
    with pytest.raises(verify.LayoutUndeclared, match="numerator"):
        env["grad"](lambda m: float(m.sum()), np.eye(2))

    undeclared = verify.namespace(np.random.default_rng(0), "")
    with pytest.raises(verify.LayoutUndeclared, match="declares no layout"):
        undeclared["grad"](lambda m: float(m.sum()), np.eye(2))

    fine = verify.namespace(np.random.default_rng(0), "denominator")
    assert fine["grad"](lambda m: float(m.sum()), np.eye(2)).shape == (2, 2)


def test_a_snippet_that_does_not_parse_is_reported_not_skipped(repo: Path) -> None:
    """A syntax error is more useful than a skip about a convention."""
    from anki_math_forge import config as config_mod

    config = config_mod.load(repo)
    card = model.parse(
        "---\nuid: ddd444\ntype: identity\nstatus: draft\n"
        'unit: "paper:2.1:5"\nverify: true\n---\n\n'
        "## front\n$a$\n\n## back\n$b$\n\n"
        "## verify\n```python\nlhs = grad(\n```\n"
    )

    results = verify.run([card], config)

    assert [r.status for r in results] == [verify.ERROR]
    assert "syntax error" in results[0].detail
