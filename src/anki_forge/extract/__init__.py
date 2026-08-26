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

from dataclasses import dataclass, field
from pathlib import Path

from .. import latex
from ..config import Config, ConfigError
from ..ledger import Ledger, Unit
from ..model import write_atomic
from . import pdf, render, tex, transcribe

__all__ = ["ExtractReport", "pdf", "render", "run", "tex", "transcribe"]


@dataclass
class ExtractReport:
    source: str
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
            f"{self.source}: {self.found} units found via {self.mode} "
            f"({self.added} new, {self.refreshed} refreshed); transcription: {counts or 'n/a'}"
        )


def run(
    config: Config,
    source_name: str,
    *,
    pages: range | None = None,
) -> ExtractReport:
    """Segment a configured source and merge the result into its ledger."""
    source = config.source(source_name)
    report = ExtractReport(source=source_name)
    checker = latex.checker(config.extra_macros)

    if source.tex and source.tex.exists():
        report.mode, report.path = "tex", source.tex
        units = tex.segment(source.tex.read_text(encoding="utf-8"), source_name)
        for unit in units:
            state, _ = transcribe.gate(unit.tex_source or "", checker)
            # Source LaTeX is authoritative even when KaTeX cannot render it
            # (a document macro, say) -- keep it, but say the render failed.
            unit.transcription = state if state != "none" else "none"
    elif source.pdf and source.pdf.exists():
        report.mode, report.path = "pdf", source.pdf
        units = pdf.segment(source.pdf, source_name, pages=pages)
        untranscribed = sum(1 for u in units if u.transcription == "none")
        if untranscribed:
            report.warnings.append(
                f"{untranscribed} units carry a crop but no transcription yet -- "
                "run `/transcribe` before triaging, or triage from the crops."
            )
    else:
        configured = source.tex or source.pdf
        raise ConfigError(
            f"source {source_name!r} has no readable input"
            + (f" (configured: {configured})" if configured else " (set `tex` or `pdf`)")
        )

    report.found = len(units)
    report.transcription = _tally(units)
    report.text_chars = cache_source_text(config, source_name)

    ledger_path = config.units_path(source_name)
    ledger = Ledger.load(ledger_path)
    report.added, report.refreshed = ledger.upsert(units)
    ledger.save()
    return report


def source_text_path(config: Config, source_name: str) -> Path:
    return config.sources_dir / source_name / "text.md"


def cache_source_text(config: Config, source_name: str) -> int:
    """Write the source's text layer next to its ledger, and return its size.

    This is what a card writer should have open. A 400-character snippet of
    surrounding prose is not enough to write a good card: the Cookbook's
    notation section defines what every symbol means, and the neighbouring
    equations are what stop you writing ten near-duplicates. The whole book is
    ~26k tokens, so the honest answer is to hand over all of it.
    """
    source = config.source(source_name)
    text = ""
    if source.tex and source.tex.exists():
        text = source.tex.read_text(encoding="utf-8")
    elif source.pdf and source.pdf.exists():
        text = _pdf_text(source.pdf)
    if not text.strip():
        return 0
    path = source_text_path(config, source_name)
    header = (
        f"<!-- {source.title}: text layer, cached by `anki-forge extract`.\n"
        "     Generated; do not edit. The mathematics here is mangled -- it is\n"
        "     context for writing cards, never a transcription. The crop is\n"
        "     the authority for what an equation says. -->\n\n"
    )
    write_atomic(path, header + text)
    return len(text)


def _pdf_text(pdf_path: Path) -> str:
    """Page-delimited text layer, so a citation can name a page."""
    fitz = render._fitz()
    document = fitz.open(str(pdf_path))
    try:
        pages = [
            f"\n\n## page {index + 1}\n\n" + document.load_page(index).get_text()
            for index in range(document.page_count)
        ]
    finally:
        document.close()
    return "".join(pages)


def _tally(units: list[Unit]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for unit in units:
        counts[unit.transcription] = counts.get(unit.transcription, 0) + 1
    return counts
