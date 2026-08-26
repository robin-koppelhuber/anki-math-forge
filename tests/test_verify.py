"""The `verify` corruption suite: flip a transpose or a sign, assert rejection."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_forge import model, verify
from anki_forge.config import Config
from anki_forge.model import Card, Section

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
    return Card(
        frontmatter={"uid": uid, "type": "identity", "status": "draft", "verify": enabled},
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
