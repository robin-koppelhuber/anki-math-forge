r"""LaTeX validation and the little bit of math-string handling we need.

`check` has to answer one mechanical question -- *does this parse under KaTeX
in strict mode?* -- with no network and no guarantee that node is installed.
So there are two backends:

* **katex** -- real `katex.renderToString(..., {strict: true})` via node, used
  when a `katex.min.js` can be found (env `ANKI_FORGE_KATEX_JS`,
  `vendor/katex/katex.min.js`, or `node_modules/katex/dist/katex.min.js`).
* **builtin** -- a structural validator: balanced braces, matched
  `\left`/`\right`, matched environments, and control sequences drawn from an
  allowlist. Strictly weaker, but mechanical and dependency-free, which is
  what §4 of the design asks of a confidence check.

`checker()` picks the strongest available. The backend in use is reported, so
"it passed" is never ambiguous about which check ran.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------------------
# Math spans
# --------------------------------------------------------------------------

# $$...$$ first, then $...$; \$ is a literal dollar and never opens a span.
_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.DOTALL)


@dataclass(frozen=True)
class MathSpan:
    tex: str
    display: bool
    start: int
    end: int


def math_spans(text: str) -> list[MathSpan]:
    """Every `$...$` / `$$...$$` span in a section body."""
    spans: list[MathSpan] = []
    for m in _MATH_RE.finditer(text):
        display = m.group(1) is not None
        spans.append(
            MathSpan(
                tex=(m.group(1) if display else m.group(2)) or "",
                display=display,
                start=m.start(),
                end=m.end(),
            )
        )
    return spans


def unbalanced_dollars(text: str) -> bool:
    """True when `$` delimiters do not pair up."""
    stripped = _MATH_RE.sub("", text)
    return bool(re.search(r"(?<!\\)\$", stripped))


_COMMAND_RE = re.compile(r"\\([a-zA-Z]+|.)")


def rendered_length(text: str) -> int:
    r"""Approximate on-screen length of a section body.

    Markup is not what a reader sees, so `\\frac{a}{b}` counts as a handful of
    glyphs rather than twelve characters. Deliberately crude -- it only has to
    make the `front` character cap (§7) mean roughly what it says.
    """
    stripped = _MATH_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    stripped = _COMMAND_RE.sub("x", stripped)
    stripped = re.sub(r"[{}&]", "", stripped)
    return len(" ".join(stripped.split()))


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LatexError:
    tex: str
    message: str


class LatexChecker:
    """Base class; `validate` returns None when the expression is fine."""

    name = "none"

    def validate(self, tex: str) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError

    def validate_text(self, text: str) -> list[LatexError]:
        """Validate every math span in a section body."""
        errors: list[LatexError] = []
        for span in math_spans(text):
            problem = self.validate(span.tex)
            if problem:
                errors.append(LatexError(span.tex.strip(), problem))
        return errors

    def describe(self) -> str:
        """Which check actually ran. Never let "it passed" be ambiguous."""
        return self.name

    def prime(self, expressions: list[str]) -> None:
        """Optional hint: these will be validated shortly. Free for the
        builtin checker; saves a process per section for the katex one."""


# -- builtin ---------------------------------------------------------------

_ENV_ALLOWED = frozenset(
    {
        "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix",
        "smallmatrix", "array", "cases", "rcases", "aligned", "alignedat",
        "gathered", "split", "equation", "align", "gather", "darray",
        "dcases", "subarray",
    }
)  # fmt: skip

_MACRO_ALLOWED = frozenset(
    {
        # structure
        "frac", "dfrac", "tfrac", "cfrac", "binom", "dbinom", "tbinom", "sqrt",
        "left", "right", "middle", "big", "Big", "bigg", "Bigg", "bigl", "bigr",
        "Bigl", "Bigr", "biggl", "biggr", "Biggl", "Biggr", "begin", "end",
        "text", "textrm", "textbf", "textit", "textsf", "texttt", "mathrm",
        "mathbf", "mathit", "mathsf", "mathtt", "mathcal", "mathbb", "mathfrak",
        "mathscr", "boldsymbol", "bm", "operatorname", "limits", "nolimits",
        "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle",
        "substack", "overset", "underset", "stackrel", "atop", "over",
        # spacing and punctuation
        "quad", "qquad", ",", ";", ":", "!", " ", "\\", "&", "%", "$", "#", "_",
        "{", "}", "|", "hspace", "kern", "phantom", "hphantom", "vphantom",
        "notag", "nonumber", "label", "tag",
        # relations and operators
        "cdot", "cdots", "ldots", "dots", "dotsc", "vdots", "ddots", "times",
        "div", "pm", "mp", "ast", "star", "circ", "bullet", "oplus", "ominus",
        "otimes", "oslash", "odot", "wedge", "vee", "cap", "cup", "setminus",
        "leq", "le", "geq", "ge", "neq", "ne", "equiv", "sim", "simeq",
        "approx", "cong", "propto", "ll", "gg", "subset", "subseteq", "supset",
        "supseteq", "in", "notin", "ni", "perp", "parallel", "mid", "nmid",
        "to", "mapsto", "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
        "leftrightarrow", "Leftrightarrow", "implies", "iff", "longrightarrow",
        "hookrightarrow", "succ", "prec", "succeq", "preceq", "triangleq",
        "doteq", "asymp", "models", "vdash", "colon",
        # big operators
        "sum", "prod", "coprod", "int", "iint", "iiint", "oint", "bigcup",
        "bigcap", "bigoplus", "bigotimes", "bigwedge", "bigvee", "bigsqcup",
        "lim", "limsup", "liminf", "max", "min", "sup", "inf", "arg", "argmax",
        "argmin", "det", "dim", "ker", "deg", "gcd", "exp", "log", "ln", "lg",
        "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
        "sinh", "cosh", "tanh", "coth", "Pr", "mod", "bmod", "pmod", "tr",
        # decorations
        "hat", "widehat", "bar", "overline", "underline", "tilde", "widetilde",
        "vec", "dot", "ddot", "check", "breve", "acute", "grave", "mathring",
        "overbrace", "underbrace", "overrightarrow", "overleftarrow",
        "boxed", "cancel", "not", "prime", "top", "bot", "dagger", "ddagger",
        "angle", "measuredangle",
        # delimiters
        "langle", "rangle", "lvert", "rvert", "lVert", "rVert", "lfloor",
        "rfloor", "lceil", "rceil", "vert", "Vert", "backslash",
        # symbols
        "infty", "partial", "nabla", "emptyset", "varnothing", "forall",
        "exists", "nexists", "neg", "lnot", "land", "lor", "aleph", "hbar",
        "ell", "Re", "Im", "wp", "imath", "jmath", "surd", "flat", "sharp",
        "natural", "clubsuit", "diamondsuit", "heartsuit", "spadesuit",
        "square", "blacksquare", "triangle", "cdotp", "ldotp",
        "mathbin", "mathrel", "mathop", "mathopen", "mathclose", "mathpunct",
        "mathord", "mathinner", "space", "thinspace", "negthinspace", "enspace",
        "color", "textcolor", "colorbox", "fcolorbox",
        # greek
        "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta",
        "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu",
        "xi", "pi", "varpi", "rho", "varrho", "sigma", "varsigma", "tau",
        "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta",
        "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi",
        "Omega",
    }
)  # fmt: skip

_BEGIN_END_RE = re.compile(r"\\(begin|end)\s*\{([^}]*)\}")


class BuiltinChecker(LatexChecker):
    name = "builtin"

    def __init__(self, extra_macros: tuple[str, ...] = ()) -> None:
        self.allowed = _MACRO_ALLOWED | {m.lstrip("\\") for m in extra_macros}

    def validate(self, tex: str) -> str | None:
        if not tex.strip():
            return "empty math span"
        for check in (self._braces, self._environments, self._left_right, self._macros):
            problem = check(tex)
            if problem:
                return problem
        return None

    def _braces(self, tex: str) -> str | None:
        depth = 0
        i = 0
        while i < len(tex):
            ch = tex[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return "unbalanced braces: a `}` closes nothing"
            i += 1
        if depth:
            return f"unbalanced braces: {depth} unclosed `{{`"
        return None

    def _environments(self, tex: str) -> str | None:
        stack: list[str] = []
        for m in _BEGIN_END_RE.finditer(tex):
            kind, env = m.group(1), m.group(2).strip().rstrip("*")
            if env not in _ENV_ALLOWED:
                return f"unknown environment `{env}`"
            if kind == "begin":
                stack.append(env)
            elif not stack:
                return f"`\\end{{{env}}}` without a matching `\\begin`"
            elif stack.pop() != env:
                return f"`\\end{{{env}}}` does not match the open environment"
        if stack:
            return f"`\\begin{{{stack[-1]}}}` is never closed"
        return None

    def _left_right(self, tex: str) -> str | None:
        depth = 0
        for m in re.finditer(r"\\(left|right)\b", tex):
            if m.group(1) == "left":
                depth += 1
            else:
                depth -= 1
                if depth < 0:
                    return "`\\right` without a matching `\\left`"
        if depth:
            return "`\\left` without a matching `\\right`"
        return None

    def _macros(self, tex: str) -> str | None:
        for m in _COMMAND_RE.finditer(tex):
            name = m.group(1)
            if name.isalpha() and name not in self.allowed:
                return (
                    f"unknown macro `\\{name}` "
                    "(add it to `[check] extra_macros`, or install node + katex "
                    "for exact checking)"
                )
        return None


# -- katex via node --------------------------------------------------------

# The path arrives by environment variable: with `node -e`, argv does not have
# a script slot, so positional arguments land at an index that is easy to get
# wrong and fails silently into the fallback checker.
_NODE_SCRIPT = r"""
const katex = require(process.env.ANKI_FORGE_KATEX_JS);
let raw = "";
process.stdin.on("data", (d) => (raw += d));
process.stdin.on("end", () => {
  const out = JSON.parse(raw).map((tex) => {
    try {
      katex.renderToString(tex, { strict: true, throwOnError: true, displayMode: false });
      return null;
    } catch (e) {
      return String(e.message || e);
    }
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def _katex_js() -> Path | None:
    candidates = [
        os.environ.get("ANKI_FORGE_KATEX_JS"),
        "vendor/katex/katex.min.js",
        "node_modules/katex/dist/katex.min.js",
        "node_modules/katex/katex.min.js",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path.resolve()
    return None


class KatexChecker(LatexChecker):
    """Exact check: KaTeX itself, strict mode, one node process per batch."""

    name = "katex"

    def __init__(self, node: str, katex_js: Path, fallback: LatexChecker) -> None:
        self.node = node
        self.katex_js = katex_js
        self.fallback = fallback
        self.degraded = ""
        # Every distinct expression costs a node process unless it is batched,
        # so results are remembered and `prime` fills the cache in one go.
        self._cache: dict[str, str | None] = {}

    def validate(self, tex: str) -> str | None:
        return self.validate_many([tex])[0]

    def prime(self, expressions: list[str]) -> None:
        self.validate_many(expressions)

    def validate_many(self, expressions: list[str]) -> list[str | None]:
        pending = [tex for tex in dict.fromkeys(expressions) if tex not in self._cache]
        if pending:
            for tex, problem in zip(pending, self._run(pending), strict=True):
                self._cache[tex] = problem
        return [self._cache[tex] for tex in expressions]

    def _run(self, expressions: list[str]) -> list[str | None]:
        if not expressions:
            return []
        env = {**os.environ, "ANKI_FORGE_KATEX_JS": str(self.katex_js)}
        try:
            proc = subprocess.run(
                [self.node, "-e", _NODE_SCRIPT],
                input=json.dumps(expressions),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip().splitlines()[-1][:120])
            result = json.loads(proc.stdout)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            # node blew up. Fall back rather than block a check run -- but
            # remember why, so `check` can say which check actually ran.
            self.degraded = str(exc) or type(exc).__name__
            return [self.fallback.validate(tex) for tex in expressions]
        self.degraded = ""
        return [None if item is None else str(item) for item in result]

    def describe(self) -> str:
        if self.degraded:
            return f"builtin (katex unavailable: {self.degraded})"
        return self.name

    def validate_text(self, text: str) -> list[LatexError]:
        spans = math_spans(text)
        results = self.validate_many([s.tex for s in spans])
        return [
            LatexError(span.tex.strip(), problem)
            for span, problem in zip(spans, results, strict=True)
            if problem
        ]


@lru_cache(maxsize=8)
def checker(extra_macros: tuple[str, ...] = ()) -> LatexChecker:
    """The strongest checker available in this environment."""
    builtin = BuiltinChecker(extra_macros)
    node = shutil.which("node")
    katex_js = _katex_js()
    if node and katex_js:
        return KatexChecker(node, katex_js, builtin)
    return builtin
