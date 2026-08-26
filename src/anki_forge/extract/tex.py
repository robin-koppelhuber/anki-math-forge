"""Segment a LaTeX source into units (DESIGN.md §4).

When real source exists it is authoritative and nothing needs reading: the
locator falls out of the numbering, and `tex_source` is the transcription.

The parser is deliberately shallow -- it counts environments and section
headings, it does not understand TeX. That is enough for a document that
numbers its display equations, and it fails visibly rather than subtly if it
is not.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..ledger import Locator, Unit

# Environments whose contents are one or more numbered display equations.
NUMBERED_ENVS = ("equation", "align", "gather", "eqnarray", "multline", "flalign")
UNNUMBERED_ENVS = (*(f"{e}*" for e in NUMBERED_ENVS), "displaymath", "aligned", "split")

# Matched one environment at a time from its own `\begin`: a single regex over
# the whole document would swallow everything inside `\begin{document}` and
# never see the equations nested in it.
_BEGIN_RE = re.compile(r"\\begin\{(?P<env>[a-zA-Z]+\*?)\}")
_END_RE = re.compile(r"\\end\{(?P<env>[a-zA-Z]+\*?)\}")
_SECTION_RE = re.compile(
    r"\\(?P<level>chapter|section|subsection|subsubsection)\*?\s*\{(?P<title>[^}]*)\}"
)
_COMMENT_RE = re.compile(r"(?<!\\)%.*?$", re.MULTILINE)
_LEVELS = {"chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3}


@dataclass
class Heading:
    number: str
    title: str
    pos: int


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def headings(text: str) -> list[Heading]:
    """Section headings with LaTeX-style numbering (1, 1.2, 1.2.3)."""
    counters = [0, 0, 0, 0]
    found: list[Heading] = []
    for m in _SECTION_RE.finditer(text):
        level = _LEVELS[m.group("level")]
        counters[level] += 1
        for deeper in range(level + 1, len(counters)):
            counters[deeper] = 0
        parts = [counters[i] for i in range(level + 1)]
        # A document without \chapter should number its sections 1, 1.1 --
        # not 0.1, 0.1.1 -- so leading zero levels are dropped.
        while len(parts) > 1 and parts[0] == 0:
            parts.pop(0)
        number = ".".join(str(part) for part in parts)
        found.append(Heading(number, _clean(m.group("title")), m.start()))
    return found


def heading_at(found: list[Heading], pos: int) -> Heading | None:
    current: Heading | None = None
    for heading in found:
        if heading.pos <= pos:
            current = heading
        else:
            break
    return current


def environment_body(text: str, env: str, after_begin: int) -> tuple[str | None, int]:
    r"""Body of `\begin{env}` starting at `after_begin`, honouring nesting."""
    pattern = re.compile(r"\\(begin|end)\{" + re.escape(env) + r"\}")
    depth = 1
    for m in pattern.finditer(text, after_begin):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return text[after_begin : m.start()], m.end()
    return None, len(text)


def split_rows(body: str) -> list[str]:
    r"""Split an align/gather body on `\\` at brace *and* environment depth 0.

    A `cases` or `pmatrix` inside a row has its own `\\` separators; splitting
    on those would shred one equation into several.
    """
    rows: list[str] = []
    depth = 0
    env_depth = 0
    current: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and body[i : i + 2] == "\\\\" and depth == 0 and env_depth == 0:
            rows.append("".join(current))
            current = []
            i += 2
            continue
        if ch == "\\":
            nested = _BEGIN_RE.match(body, i) or _END_RE.match(body, i)
            if nested:
                env_depth += 1 if nested.re is _BEGIN_RE else -1
                current.append(body[i : nested.end()])
                i = nested.end()
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        current.append(ch)
        i += 1
    rows.append("".join(current))
    return [r for r in (row.strip() for row in rows) if r]


def context_before(text: str, pos: int, limit: int = 400) -> str:
    """The prose immediately before an equation, lightly de-TeXed."""
    window = text[max(0, pos - 1200) : pos]
    window = window.rsplit("\\end{", 1)[-1]
    paragraphs = [p for p in re.split(r"\n\s*\n", window) if p.strip()]
    tail = paragraphs[-1] if paragraphs else window
    return _clean(tail)[-limit:].strip()


def segment(text: str, source: str) -> list[Unit]:
    """Every numbered display equation in a LaTeX document, in order."""
    text = strip_comments(text)
    marks = headings(text)
    counter = 0
    units: list[Unit] = []
    used: set[str] = set()

    for match in _BEGIN_RE.finditer(text):
        env = match.group("env")
        base = env.rstrip("*")
        if base not in NUMBERED_ENVS:
            continue
        starred = env.endswith("*")
        body, _ = environment_body(text, env, match.end())
        if body is None:
            continue  # unterminated environment: report nothing rather than guess
        multi_row = base in {"align", "gather", "eqnarray", "flalign"}
        rows = split_rows(body) if multi_row else [body.strip()]
        heading = heading_at(marks, match.start())
        context = context_before(text, match.start())

        for row in rows:
            numbered = not starred and not re.search(r"\\(nonumber|notag)\b", row)
            if numbered:
                counter += 1
            tex = _clean_math(row, strip_alignment=multi_row)
            if not tex:
                continue
            section = heading.number if heading else ""
            equation = counter if numbered else None
            unit_id = _unique_id(source, section, equation, tex, used)
            units.append(
                Unit(
                    id=unit_id,
                    locator=Locator(section=section, equation=equation),
                    tex_source=tex,
                    transcription="ok",
                    context=context,
                    state="new",
                )
            )
    return units


def _unique_id(source: str, section: str, equation: int | None, tex: str, used: set[str]) -> str:
    """`source:section:number`, or a content hash when there is no number.

    An unnumbered display equation still deserves a unit, but its position in
    the document is not a stable handle -- inserting an equation above it would
    renumber it and orphan whatever triage state it had. Hashing its contents
    keeps the id stable for as long as the equation itself is.
    """
    if equation is None:
        digest = hashlib.sha256(tex.encode("utf-8")).hexdigest()[:6]
        stem = f"{source}:{section or 'eq'}:h{digest}"
    else:
        stem = f"{source}:{section or 'eq'}:{equation}"
    unit_id = stem
    bump = 1
    while unit_id in used:
        bump += 1
        unit_id = f"{stem}-{bump}"
    used.add(unit_id)
    return unit_id


def _clean_math(tex: str, *, strip_alignment: bool = False) -> str:
    tex = re.sub(r"\\(nonumber|notag)\b", "", tex)
    tex = re.sub(r"\\label\s*\{[^}]*\}", "", tex)
    if strip_alignment:
        # A row lifted out of `align` carries alignment markers that mean
        # nothing on their own -- and that KaTeX rejects outside an environment.
        tex = re.sub(r"(?<!\\)&", "", tex)
    tex = re.sub(r"[ \t]*\n[ \t]*", " ", tex)
    return " ".join(tex.split()).strip()


def _clean(text: str) -> str:
    text = re.sub(r"\\(label|index|cite|ref|eqref|footnote)\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\(emph|textbf|textit|texttt|mathrm)\s*\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\[a-zA-Z]+\s*", " ", text)
    text = text.replace("~", " ").replace("\\", "")
    text = re.sub(r"[{}$&]", "", text)
    return " ".join(text.split())
