"""`classify` -- *propose* skipping the units that were never going to be cards.

Segmentation is deliberately generous: it would rather hand you a notation
table row than miss an identity. The cost lands on whoever triages, who should
not have to press `s` fifty-seven times before reaching a real decision.

**Nothing here changes state.** It writes a `suggestion` onto the unit, which
sits there until a human accepts or overrides it in the triage view. That is
the whole design: these rules are a regex over a mangled text layer, and a
guess that silently moves units is indistinguishable from a bug to whoever
meets it later. An earlier version of this module did apply its decisions, and
the result was 61 units the human had never triaged appearing as `skipped`.

The rules deliberately cannot touch a numbered equation: the book numbering
something is the document asserting it is a result, and no heuristic here gets
to overrule that.

These two rules are also *this document's* rules. They lean on a text layer
existing and on relation symbols surviving it, which is a property of pdfTeX
output, not of PDFs. `/classify` -- a model looking at the crops -- generalises
where this does not, and writes suggestions through the same mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .extract import render
from .ledger import Ledger, Unit

# A display equation states a relation. Something with no relation symbol in
# it is a fragment of one, a heading, or prose that scored too highly.
#
# Two alphabets, because there are two sources. The PDF text layer carries
# real Unicode symbols; a transcription writes LaTeX, where the same relations
# are macros. Miss the macros and every transcribed identity using `\leq`
# would be proposed for skipping -- a false skip on a real result, which is
# the expensive direction to be wrong in.
RELATION = re.compile(
    "[=<>≤≥≈≡∝≠]"
    r"|\\(?:leq|geq|neq|approx|equiv|propto|sim|simeq|cong"
    "|subset|subseteq|supset|supseteq|in|ni|succ|succeq|prec|preceq"
    "|ll|gg|doteq|triangleq)"
    "(?![a-zA-Z])"  # a macro name ends here: \in must not match \infty
)

REASONS = {
    "front-matter": "before the document's first numbered equation",
    "no-relation": "unnumbered and states no relation -- a fragment, heading, or prose",
}


@dataclass
class Classification:
    unit_id: str
    reason: str
    detail: str = ""


@dataclass
class Report:
    source: str
    considered: int = 0
    classified: list[Classification] = field(default_factory=list)
    kept: int = 0

    def by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.classified:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts

    def summary(self) -> str:
        detail = ", ".join(f"{n} {reason}" for reason, n in sorted(self.by_reason().items()))
        return (
            f"{self.source}: {len(self.classified)} of {self.considered} untriaged units "
            f"*suggested* for skipping ({detail or 'none'}); {self.kept} unremarked. "
            "Nothing changed -- accept or override each in the triage view."
        )


def first_numbered_page(units: list[Unit]) -> int | None:
    """Where the body starts. Everything before it is front matter."""
    pages = [
        u.locator.page
        for u in units
        if u.locator.equation is not None and u.locator.page is not None
    ]
    return min(pages) if pages else None


def classify(
    ledger: Ledger,
    document: Path | None,
    source: str = "",
    *,
    write: bool = True,
) -> Report:
    """Propose skipping obviously non-cardable units. Applies nothing."""
    units = list(ledger)
    report = Report(source=source or (ledger.path.parent.name if ledger.path else ""))
    body_starts = first_numbered_page(units)

    renderer = None
    if document is not None and document.exists():
        renderer = render.CropRenderer(document)
    try:
        for unit in units:
            if unit.state != "new":
                continue  # a decision has already been made about this one
            if unit.suggestion is not None:
                continue  # already proposed; do not churn it
            report.considered += 1
            if unit.locator.equation is not None:
                report.kept += 1
                continue

            reason = _reason_to_skip(unit, body_starts, renderer)
            if reason is None:
                report.kept += 1
                continue
            report.classified.append(Classification(unit.id, reason, REASONS[reason]))
            if write:
                ledger.suggest(unit.id, "skipped", reason, REASONS[reason], by="classify")
    finally:
        if renderer is not None:
            renderer.close()

    if write and report.classified:
        ledger.save()
    return report


def _reason_to_skip(unit: Unit, body_starts: int | None, renderer: object) -> str | None:
    page = unit.locator.page
    if body_starts is not None and page is not None and page < body_starts:
        return "front-matter"

    text = _text_of(unit, renderer)
    if text is not None and not RELATION.search(text):
        return "no-relation"
    return None


def _text_of(unit: Unit, renderer: object) -> str | None:
    """What this unit says, best source first.

    A transcription beats the PDF text layer outright: somebody -- or some
    model -- looked at the crop and wrote down what is actually printed,
    whereas the text layer is whatever pdfTeX happened to emit and is mangled
    or absent for anything unusual. So prefer `tex_auto`/`tex_source` when a
    transcription exists, which is why `/transcribe` runs before `/classify`.

    Falls back to the text layer, from which only relation symbols are read,
    and those survive it intact even when the structure around them does not.
    """
    transcription = unit.tex_source or unit.tex_auto
    if transcription:
        return transcription

    geometry = unit.crop_geometry()
    if geometry is None or renderer is None:
        return None
    page, bbox = geometry
    document = getattr(renderer, "_doc", None)
    fitz = getattr(renderer, "_fitz", None)
    if document is None or fitz is None or not 1 <= page <= document.page_count:
        return None
    return str(document.load_page(page - 1).get_textbox(fitz.Rect(*bbox)))
