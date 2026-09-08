"""`verify` -- opt-in numeric check of an identity (DESIGN.md §7).

Sample random conforming matrices, evaluate both sides, assert agreement.
Default off; worth enabling on the gnarly ones -- Woodbury, block inverses --
where a stray transpose survives proofreading and then gets memorised
confidently.

A `## verify` section is a Python snippet that sets `lhs` and `rhs`:

    ```python
    X = spd(4)
    lhs = grad(lambda M: np.log(np.linalg.det(M)), X)
    rhs = np.linalg.inv(X).T
    ```

It runs once per trial with a fresh `rng`, so a lucky draw cannot hide a bug.
Gradients come from central differences (§15.4: numpy only, no torch/jax), so
tolerances are loose enough for numerical noise and tight enough to catch a
flipped sign or transpose.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from .config import Config
from .model import Card

TRIALS = 5
RTOL = 1e-4
ATOL = 1e-6
STEP = 1e-5

_FENCE_RE = re.compile(r"^\s*```(?:python|py)?\s*\n(?P<code>.*?)\n\s*```\s*$", re.DOTALL)

PASS, FAIL, SKIP, ERROR = "pass", "fail", "skip", "error"


@dataclass
class VerifyResult:
    uid: str
    status: str
    detail: str = ""
    worst: float = 0.0

    def format(self) -> str:
        suffix = f" -- {self.detail}" if self.detail else ""
        return f"{self.status:5} {self.uid}{suffix}"


def code_of(card: Card) -> str:
    """The executable body of `## verify`, fence stripped."""
    body = (card.section("verify") or "").strip()
    match = _FENCE_RE.match(body)
    return (match.group("code") if match else body).strip()


def grad(fn: Callable[[np.ndarray], float], x: np.ndarray, step: float = STEP) -> np.ndarray:
    """Central-difference gradient of a scalar function of a matrix.

    Denominator layout: the result has the shape of `x`, matching the cards.
    """
    x = np.asarray(x, dtype=float)
    out = np.zeros_like(x)
    it = np.nditer(x, flags=["multi_index"])
    while not it.finished:
        idx = it.multi_index
        original = x[idx]
        x[idx] = original + step
        plus = float(fn(x))
        x[idx] = original - step
        minus = float(fn(x))
        x[idx] = original
        out[idx] = (plus - minus) / (2 * step)
        it.iternext()
    return out


def namespace(rng: np.random.Generator) -> dict[str, Any]:
    """What a `## verify` snippet may use. Deliberately small."""

    def randn(*shape: int) -> np.ndarray:
        return rng.standard_normal(shape if shape else ())

    def spd(n: int, *, scale: float = 1.0) -> np.ndarray:
        """A well-conditioned symmetric positive definite matrix."""
        a = rng.standard_normal((n, n))
        return scale * (a @ a.T + n * np.eye(n))

    def sym(n: int) -> np.ndarray:
        a = rng.standard_normal((n, n))
        return (a + a.T) / 2

    def invertible(n: int) -> np.ndarray:
        while True:
            a = rng.standard_normal((n, n))
            if abs(np.linalg.det(a)) > 1e-3:
                return a

    def orth(n: int) -> np.ndarray:
        q, _ = np.linalg.qr(rng.standard_normal((n, n)))
        return q

    safe_builtins = {
        "abs": abs, "all": all, "any": any, "enumerate": enumerate, "float": float,
        "int": int, "len": len, "list": list, "max": max, "min": min, "range": range,
        "round": round, "sum": sum, "tuple": tuple, "zip": zip, "print": print,
    }  # fmt: skip

    return {
        "__builtins__": safe_builtins,
        "np": np,
        "rng": rng,
        "grad": grad,
        "randn": randn,
        "spd": spd,
        "sym": sym,
        "invertible": invertible,
        "orth": orth,
    }


def verify_card(card: Card, *, trials: int = TRIALS, seed: int = 0) -> VerifyResult:
    """Run a card's `## verify` snippet. Cards without one are skipped."""
    if not card.verify_enabled:
        return VerifyResult(card.uid, SKIP, "verify: false")
    code = code_of(card)
    if not code:
        return VerifyResult(card.uid, ERROR, "`verify: true` but `## verify` is empty")

    try:
        compiled = compile(code, f"<verify {card.uid}>", "exec")
    except SyntaxError as exc:
        return VerifyResult(card.uid, ERROR, f"syntax error: {exc.msg} (line {exc.lineno})")

    worst = 0.0
    for trial in range(trials):
        env = namespace(np.random.default_rng(seed + trial))
        try:
            exec(compiled, env)
        except Exception as exc:
            return VerifyResult(card.uid, ERROR, f"trial {trial}: {type(exc).__name__}: {exc}")

        if "lhs" not in env or "rhs" not in env:
            return VerifyResult(card.uid, ERROR, "snippet must set both `lhs` and `rhs`")
        lhs = np.asarray(env["lhs"], dtype=float)
        rhs = np.asarray(env["rhs"], dtype=float)
        if lhs.shape != rhs.shape:
            return VerifyResult(
                card.uid, FAIL, f"shape mismatch: lhs {lhs.shape} vs rhs {rhs.shape}"
            )
        diff = float(np.max(np.abs(lhs - rhs))) if lhs.size else 0.0
        scale = float(np.max(np.abs(rhs))) if rhs.size else 1.0
        worst = max(worst, diff)
        if not np.allclose(lhs, rhs, rtol=RTOL, atol=ATOL):
            return VerifyResult(
                card.uid,
                FAIL,
                f"trial {trial}: max |lhs - rhs| = {diff:.3g} (scale {scale:.3g})",
                worst,
            )

    return VerifyResult(card.uid, PASS, f"{trials} trials, max |lhs - rhs| = {worst:.2g}", worst)


def run(
    cards: list[Card],
    config: Config,
    *,
    trials: int = TRIALS,
    only: str | None = None,
) -> list[VerifyResult]:
    results = []
    for card in cards:
        if only and card.uid != only:
            continue
        # `grad` computes the denominator-layout gradient and nothing else. On
        # a square matrix the two conventions are indistinguishable, so a
        # numerator-layout source would pass most cards and fail the
        # rectangular ones for a reason nobody would guess. Say so instead.
        layout = config.layout_for(card.source_name)
        if layout and layout != "denominator":
            results.append(
                VerifyResult(
                    card.uid,
                    SKIP,
                    f"source uses {layout} layout; `grad` computes denominator layout only",
                )
            )
            continue
        results.append(verify_card(card, trials=trials))
    return results
