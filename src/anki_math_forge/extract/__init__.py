"""`extract` -- source material in, units out (DESIGN.md §4).

Extraction produces **units, never cards**. If something in here is tempted to
write a `front`, it is overstepping: a unit is one equation, its context, a
stable locator and a best-effort transcription, and that is all.

Two paths:

* **LaTeX source**, if it exists -- authoritative, and the locator falls out
  of the numbering.
* **PDF** -- locate each display equation and record where it is, so the crop
  can be rendered from the document on demand.

Neither path reads the mathematics. `tex_auto` is filled afterwards by the
`/transcribe` skill; extraction is an *indexer*, and its job is a stable,
complete, resumable list of work items. Re-running is safe: the ledger keeps
every state you have already set and only genuinely new units are added.

Extraction also caches the source's text layer next to the ledger, because a
card is only as good as the context the writer had -- the whole Cookbook is
about 26k tokens, so there is no reason to write cards off 400-character
snippets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import latex
from ..config import Config, ConfigError
from ..ledger import Ledger, Unit
from ..model import write_atomic
from . import pdf, render, tex, transcribe

__all__ = [
    "ExtractReport",
    "TextQuality",
    "pdf",
    "render",
    "run",
    "source_text_quality",
    "tex",
    "text_quality",
    "transcribe",
]


@dataclass
class ExtractReport:
    project: str
    path: Path | None = None
    mode: str = ""  # tex | pdf
    found: int = 0
    added: int = 0
    refreshed: int = 0
    transcription: dict[str, int] = field(default_factory=dict)
    text_chars: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        counts = ", ".join(f"{n} {state}" for state, n in sorted(self.transcription.items()))
        return (
            f"{self.project}: {self.found} units found via {self.mode} "
            f"({self.added} new, {self.refreshed} refreshed); transcription: {counts or 'n/a'}"
        )


def run(
    config: Config,
    project_name: str,
    *,
    pages: range | None = None,
) -> ExtractReport:
    """Segment a configured source and merge the result into its ledger."""
    source = config.project(project_name)
    report = ExtractReport(project=project_name)
    checker = latex.checker(config.extra_macros)

    if source.tex and source.tex.exists():
        report.mode, report.path = "tex", source.tex
        units = tex.segment(source.tex.read_text(encoding="utf-8"), project_name)
        for unit in units:
            state, _ = transcribe.gate(unit.tex_source or "", checker)
            # Source LaTeX is authoritative even when KaTeX cannot render it
            # (a document macro, say) -- keep it, but say the render failed.
            unit.transcription = state if state != "none" else "none"
    elif source.pdf and source.pdf.exists():
        report.mode, report.path = "pdf", source.pdf
        units = pdf.segment(source.pdf, project_name, pages=pages)
        untranscribed = sum(1 for u in units if u.transcription == "none")
        if untranscribed:
            report.warnings.append(
                f"{untranscribed} units carry a crop but no transcription yet -- "
                "run `/transcribe` before triaging, or triage from the crops."
            )
    else:
        configured = source.tex or source.pdf
        raise ConfigError(
            f"source {project_name!r} has no readable input"
            + (f" (configured: {configured})" if configured else " (set `tex` or `pdf`)")
        )

    report.found = len(units)
    report.transcription = _tally(units)
    report.text_chars = cache_source_text(config, project_name)

    ledger_path = config.units_path(project_name)
    with Ledger.edit(ledger_path) as ledger:
        report.added, report.refreshed = ledger.upsert(units)
    return report


# -- is the text layer worth reading? ---------------------------------------

# Measured across the four layers in this repo, which are all healthy: letters
# are 57--75% of the characters, and the Matrix Cookbook is the low end because
# it is dense mathematics and half its tokens are single symbols. So these sit
# well below anything a real book produces, and what they catch is the other
# thing entirely -- a scan with no text layer, or one whose font encoding never
# resolved.
BLANK_PAGE = 40  # characters; below this a page has nothing on it
POOR_BLANK = 0.25  # proportion of blank pages that means "this is a scan"
POOR_LETTERS = 0.35  # proportion of characters that are letters
POOR_DAMAGED = 0.001  # proportion that are U+FFFD


@dataclass(frozen=True)
class TextQuality:
    """What a source's cached text layer looks like, mechanically.

    A PDF's text layer is the *prose* a card writer is handed: the paragraph
    that states the conditions, the notation section, the sentence before the
    equation. The mathematics in it is mangled by design and that is fine --
    the crop is authoritative (invariant 4) and every file says so in its own
    header.

    What is **not** fine is a layer that is missing or garbled, because then
    the context is noise and nothing says so. A scanned book has no text layer
    at all; one with a broken font encoding produces pages of replacement
    characters or of single letters spaced out. Both read, to whoever is
    writing the card, as "this source just does not say much", which is the
    wrong conclusion to draw silently.

    Mechanical on purpose, like every other check here: it counts characters.
    It cannot tell a bad transcription from a terse one, and does not try.
    """

    verdict: str  # "ok" | "poor" | "missing"
    pages: int
    blank_pages: int
    letters: float
    damaged: float
    reasons: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.verdict == "ok"

    def describe(self) -> str:
        if self.verdict == "missing":
            return "no text layer at all: this is a scan, or the PDF is not here"
        if self.usable:
            return f"{self.pages} pages of text"
        return "; ".join(self.reasons)

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "pages": self.pages,
            "blank_pages": self.blank_pages,
            "letters": round(self.letters, 3),
            "damaged": round(self.damaged, 4),
            "reasons": list(self.reasons),
        }


def text_quality(text: str) -> TextQuality:
    """Read a cached text layer and say whether it is worth handing over."""
    body = text.split("-->", 1)[-1] if text.lstrip().startswith("<!--") else text
    if not body.strip():
        return TextQuality("missing", 0, 0, 0.0, 0.0, ("nothing was extracted",))

    pages = re.split(r"^## page \d+", body, flags=re.M)[1:] or [body]
    blank = sum(1 for page in pages if len(page.strip()) < BLANK_PAGE)
    letters = sum(character.isalpha() for character in body) / len(body)
    damaged = body.count("�") / len(body)

    reasons: list[str] = []
    if blank / len(pages) > POOR_BLANK:
        reasons.append(f"{blank} of {len(pages)} pages have no text on them")
    if letters < POOR_LETTERS:
        reasons.append(f"only {letters:.0%} of it is letters")
    if damaged > POOR_DAMAGED:
        reasons.append(f"{damaged:.1%} of it is replacement characters")
    return TextQuality(
        "poor" if reasons else "ok",
        len(pages),
        blank,
        letters,
        damaged,
        tuple(reasons),
    )


def source_text_quality(config: Config, project_name: str, document: str = "") -> TextQuality:
    path = source_text_path(config, project_name, document)
    if not path.exists():
        return TextQuality("missing", 0, 0, 0.0, 0.0, ("no text layer has been cached",))
    return text_quality(path.read_text(encoding="utf-8", errors="replace"))


def source_text_path(config: Config, project_name: str, document: str = "") -> Path:
    """Where a source's text layer is cached.

    Per document, because `## page 7` means nothing across fifteen
    chapter PDFs. A single-document source keeps the plain name it had.
    """
    folder = config.projects_dir / project_name
    return folder / (f"text-{document}.md" if document else "text.md")


def cache_source_text(config: Config, project_name: str) -> int:
    """Write the source's text layer next to its ledger, and return its size.

    This is what a card writer should have open. A 400-character snippet of
    surrounding prose is not enough to write a good card: the Cookbook's
    notation section defines what every symbol means, and the neighbouring
    equations are what stop you writing ten near-duplicates. The whole book is
    ~26k tokens, so the honest answer is to hand over all of it.
    """
    source = config.project(project_name)
    text = ""
    if source.tex and source.tex.exists():
        text = source.tex.read_text(encoding="utf-8")
    elif source.pdf and source.pdf.exists():
        text = _pdf_text(source.pdf)
    if not text.strip():
        return 0
    path = source_text_path(config, project_name)
    header = (
        f"<!-- {source.title}: text layer, cached by `forge extract`.\n"
        "     Generated; do not edit. The mathematics here is mangled -- it is\n"
        "     context for writing cards, never a transcription. The crop is\n"
        "     the authority for what an equation says. -->\n\n"
    )
    write_atomic(path, header + text)
    return len(text)


def cache_document_text(config: Config, project_name: str, document: str, pdf: Path) -> int:
    """The same thing, for one attachment of a multi-document source.

    Handing over the whole document is the point: a card is easier to write and
    quicker to review when whoever wrote it could see the paragraph that states
    the conditions, and that paragraph is as often on the previous page.
    """
    text = _pdf_text(pdf)
    if not text.strip():
        return 0
    header = (
        f"<!-- {project_name}/{document}: text layer, cached by `forge zotero`.\n"
        "     Generated; do not edit. -->\n\n"
    )
    write_atomic(source_text_path(config, project_name, document), header + text)
    return len(text)


def _pdf_text(pdf_path: Path) -> str:
    """Page-delimited text layer, so a citation can name a page."""
    fitz = render._fitz()
    document = fitz.open(str(pdf_path))
    try:
        pages = [
            f"\n\n## page {index + 1}\n\n" + _printable(document.load_page(index).get_text())
            for index in range(document.page_count)
        ]
    finally:
        document.close()
    return "".join(pages)


def _printable(text: str) -> str:
    """Drop control characters, keeping tab, newline and carriage return.

    A PDF with glyphs its font never mapped extracts them as codepoints 0-31:
    one paper here produced NUL, backspace, formfeed and a dozen others. They
    are not text, they make the cache read as a binary file to `grep`, and a
    card writer reading the page has to see past them.
    """
    return "".join(c for c in text if c >= " " or c in "\t\n\r")


def _tally(units: list[Unit]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for unit in units:
        counts[unit.transcription] = counts.get(unit.transcription, 0) + 1
    return counts
