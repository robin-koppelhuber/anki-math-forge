"""Gating a first-pass math transcription (DESIGN.md §4).

You need to see the actual mathematics to decide whether a unit is worth
carding, so units carry a transcription alongside their crop. That
transcription is written by the `/transcribe` Claude Code skill reading the
crops -- there is no local vision model here, and no LLM API code either (§2).
This module is the mechanical half: the gate every transcription passes
through on its way into the ledger.

`tex_auto` is a **preview, not content.** It exists so you can triage. The
units view shows the crop and the rendered transcription side by side
precisely so a bad transcription is obvious, and when writing a card the crop
is authoritative.

The confidence check is mechanical: does the output parse under KaTeX strict
mode? If not, the unit is marked `transcription: "failed"` and shows the crop
only -- storing garbage would be worse than storing nothing.
"""

from __future__ import annotations

import re

from .. import latex

_WRAPPERS = re.compile(r"^\s*(\$\$?|\\\[|\\\(|\\begin\{(?:equation|displaymath)\*?\})\s*")
_WRAPPERS_END = re.compile(r"\s*(\$\$?|\\\]|\\\)|\\end\{(?:equation|displaymath)\*?\})\s*$")


def normalise(tex: str) -> str:
    """Strip the delimiters a transcriber likes to add; we store bare math."""
    tex = tex.strip()
    previous = None
    while previous != tex:
        previous = tex
        tex = _WRAPPERS.sub("", tex)
        tex = _WRAPPERS_END.sub("", tex)
    tex = re.sub(r"\\(tag|label)\s*\{[^}]*\}", "", tex)
    return " ".join(tex.split()).strip()


def gate(tex: str, checker: latex.LatexChecker | None = None) -> tuple[str, str]:
    """Return `(transcription_state, tex)`.

    `("ok", tex)` when it parses, `("failed", "")` when it does not, and
    `("none", "")` when there was nothing to transcribe. A failed
    transcription stores no LaTeX at all -- the crop is the authority anyway.
    """
    tex = normalise(tex)
    if not tex:
        return "none", ""
    checker = checker or latex.checker()
    if checker.validate(tex) is not None:
        return "failed", ""
    return "ok", tex
