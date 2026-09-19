"""`audit` -- mechanical confidence checks over an extracted ledger.

Extraction can fail silently. That is its worst property: 900 plausible
regions look exactly like 900 correct ones, and nobody discovers the
difference until a card is wrong months later.

Everything here is mechanical, and two of the checks need no ground truth at
all. The strongest one does have ground truth, for free: **a numbered
document must yield equations 1..N with no gaps.** That is a property of the
document, not of the extractor -- so it scores any extractor, including a
model-driven one.

Nothing here judges mathematics. It answers "is this index trustworthy", and
flags the units where the answer is no, so triage starts with the twenty
suspect ones rather than eyeballing seven hundred.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise

from .ledger import Ledger, Unit

# A crop this much wider or taller than its neighbours is worth a look.
OUTLIER_RATIO = 3.0


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    unit_id: str = ""

    def format(self) -> str:
        where = f"{self.unit_id}: " if self.unit_id else ""
        return f"{where}[{self.code}] {self.message}"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "unit": self.unit_id}


@dataclass
class Report:
    source: str
    total: int = 0
    numbered: int = 0
    expected: int = 0
    findings: list[Finding] = field(default_factory=list)
    flagged: set[str] = field(default_factory=set)

    @property
    def complete(self) -> bool:
        """True when the equation numbering has no gaps and no duplicates."""
        return self.expected > 0 and self.numbered == self.expected and not self.gaps

    @property
    def gaps(self) -> list[Finding]:
        return [f for f in self.findings if f.code in ("number-missing", "number-duplicate")]

    def summary(self) -> str:
        if self.expected:
            verdict = "complete" if self.complete else "INCOMPLETE"
            coverage = f"{self.numbered}/{self.expected} numbered equations ({verdict})"
        else:
            coverage = f"{self.numbered} numbered equations (no numbering to check against)"
        return (
            f"{self.source}: {self.total} units, {coverage}; "
            f"{len(self.flagged)} flagged, {len(self.findings)} findings"
        )


def audit(
    ledger: Ledger,
    source: str = "",
    makes_a_unit: Callable[[str, str], bool] | None = None,
) -> Report:
    """`makes_a_unit` is the source's `units_from` as a question, and it is
    optional because most callers are asking about a segmented book, where no
    colour scheme applies."""
    report = Report(source=source or (ledger.path.parent.name if ledger.path else ""))
    units = list(ledger)
    report.total = len(units)

    numbered = [u for u in units if u.locator.equation is not None]
    report.numbered = len(numbered)
    seen = [u.locator.equation for u in numbered if u.locator.equation is not None]
    report.expected = max(seen) if seen else 0

    _check_numbering(report, numbered, seen)
    _check_geometry(report, units)
    _check_transcription(report, units)
    if makes_a_unit is not None:
        _check_scheme(report, units, makes_a_unit)
    return report


def _check_scheme(
    report: Report, units: list[Unit], makes_a_unit: Callable[[str, str], bool]
) -> None:
    """Has `units_from` moved since the last import?

    Both directions are visible without Zotero, because the ledger records the
    marks it saw: the mark a unit came from is its first one, and everything
    marked nearby rides along on the unit as a neighbour. So a unit whose own
    mark no longer starts one is a leftover, and a *neighbour* whose colour now
    does start one is a unit the last import would have made had the scheme
    said so.

    It sees what the last import saw and no more. A colour you have started
    using on pages nowhere near an existing unit is invisible here, because
    nothing recorded it -- that is a question only Zotero can answer, and
    answering it is what re-running the import is for.
    """
    orphans: dict[str, int] = {}
    # By key, not by appearance: one mark rides along on every unit within a
    # few pages of it, so counting appearances would report the same mark
    # three times and call it three missing units.
    missed: dict[str, set[str]] = {}
    anchors = {u.marks[0].key for u in units if u.marks}
    for unit in units:
        for position, mark in enumerate(unit.marks):
            pair = f"{mark.kind}/{mark.colour}" if mark.colour else mark.kind
            if position == 0:
                if not makes_a_unit(mark.kind, mark.colour):
                    orphans[pair] = orphans.get(pair, 0) + 1
            elif makes_a_unit(mark.kind, mark.colour) and mark.key not in anchors:
                missed.setdefault(pair, set()).add(mark.key)
    for pair, count in sorted(orphans.items()):
        _flag(
            report,
            "scheme-orphan",
            f"{count} unit(s) came from {pair}, which `units_from` no longer names. "
            "Re-run the import: untouched ones are forgotten and anything you "
            "triaged is kept",
        )
    for pair, keys in sorted(missed.items()):
        _flag(
            report,
            "scheme-unimported",
            f"{len(keys)} mark(s) of {pair} are recorded but are not units, and "
            "`units_from` now names that pair. Re-run the import to make them",
        )


def _flag(report: Report, code: str, message: str, unit_id: str = "") -> None:
    report.findings.append(Finding(code, message, unit_id))
    if unit_id:
        report.flagged.add(unit_id)


def _check_numbering(report: Report, numbered: list[Unit], seen: list[int]) -> None:
    """The free oracle: 1..N, once each."""
    if not seen:
        return
    counts: dict[int, list[Unit]] = {}
    for unit in numbered:
        if unit.locator.equation is not None:
            counts.setdefault(unit.locator.equation, []).append(unit)

    missing = [n for n in range(1, report.expected + 1) if n not in counts]
    if missing:
        preview = ", ".join(str(n) for n in missing[:20])
        more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
        _flag(
            report,
            "number-missing",
            f"{len(missing)} equation numbers never appear: {preview}{more}",
        )
    for number, group in sorted(counts.items()):
        if len(group) > 1:
            for unit in group:
                _flag(
                    report,
                    "number-duplicate",
                    f"equation {number} was found {len(group)} times",
                    unit.id,
                )


def _check_geometry(report: Report, units: list[Unit]) -> None:
    """Overlapping crops, and crops far off the usual size."""
    by_page: dict[int, list[Unit]] = {}
    heights: list[float] = []
    for unit in units:
        if unit.locator.page is None or unit.locator.bbox is None:
            continue
        by_page.setdefault(unit.locator.page, []).append(unit)
        heights.append(unit.locator.bbox[3] - unit.locator.bbox[1])

    if heights:
        typical = sorted(heights)[len(heights) // 2]
        for unit in units:
            if unit.locator.bbox is None:
                continue
            height = unit.locator.bbox[3] - unit.locator.bbox[1]
            if typical and height > typical * OUTLIER_RATIO:
                _flag(
                    report,
                    "crop-oversized",
                    f"crop is {height / typical:.1f}x the typical height "
                    "-- it may hold more than one equation",
                    unit.id,
                )

    for page, group in sorted(by_page.items()):
        ordered = sorted(group, key=lambda u: (u.locator.bbox or [0, 0, 0, 0])[1])
        for first, second in pairwise(ordered):
            a, b = first.locator.bbox, second.locator.bbox
            if a is None or b is None:
                continue
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            if overlap > 1.0:
                _flag(
                    report,
                    "crop-overlap",
                    f"crop overlaps {second.id} by {overlap:.0f}pt on page {page}",
                    first.id,
                )


# A row separator eaten by a tool layer that collapses backslashes leaves a
# control space behind: `\\` becomes `\ `, which KaTeX accepts, so a
# two-row matrix silently becomes one. Look for that residue rather than for a
# missing separator -- a crop holding one row of a bigger matrix is legitimate
# and has no separator either. Five of the eight matrices in the first
# transcribe pass arrived corrupted this way; the check is the residue.
ROW_SEPARATOR = '\\\\'
ROW_ENVIRONMENTS = ("array", "matrix", "bmatrix", "pmatrix", "cases", "aligned")
# A lone control space -- one not part of a "\\" separator. `(?<!\\)`
# matters: without it every correct separator followed by a space matches.
LONE_CONTROL_SPACE = re.compile(r"(?<!\\)\\ ")


def _check_transcription(report: Report, units: list[Unit]) -> None:
    for unit in units:
        tex = unit.tex_auto or ""
        # Both conditions matter. A crop holding one row of a bigger matrix
        # has no separator and is fine; `\mathbf{A}\ n\times n` uses a control space and is
        # fine. Only the two together mean a matrix that lost every row it
        # had -- which is how all five real cases arrived. A *partial*
        # collapse (some separators surviving) slips through; catching that
        # needs the crop, not the text.
        if not tex or ROW_SEPARATOR in tex or not LONE_CONTROL_SPACE.search(tex):
            continue
        if any(f"begin{{{env}}}" in tex for env in ROW_ENVIRONMENTS):
            _flag(
                report,
                "transcription-rowsep",
                "multi-row environment whose row separator looks like it "
                "collapsed to a control space -- check it against the crop",
                unit.id,
            )
    failed = [u for u in units if u.transcription == "failed"]
    for unit in failed:
        _flag(report, "transcription-failed", "transcription did not parse under KaTeX", unit.id)
    # A unit with an annotation and no transcription is a *decision*, not a
    # gap: somebody read the crop and declined to guess at it. Counting those
    # as outstanding work sends the next pass back to re-guess exactly where
    # refusing was right.
    # A unit carrying marks already has its text: the reader highlighted a
    # passage and Zotero lifted it off the page. There is no equation to
    # transcribe, so asking `/transcribe` to read the crop would send it to
    # re-type prose that is already exact.
    untriaged = [
        u
        for u in units
        if u.transcription == "none" and u.state in ("new", "queued") and not u.marks
    ]
    missing = [u for u in untriaged if not u.notes]
    declined = len(untriaged) - len(missing)
    if missing:
        _flag(
            report,
            "transcription-missing",
            f"{len(missing)} untriaged units have no transcription -- run `/transcribe`",
        )
    if declined:
        _flag(
            report,
            "transcription-declined",
            f"{declined} units were read and deliberately left untranscribed "
            f"(fragments, prose, unreadable crops) -- see their annotations, "
            f"and do not re-run `/transcribe` over them",
        )
