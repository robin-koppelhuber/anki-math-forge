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


def audit(ledger: Ledger, source: str = "") -> Report:
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
    return report


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


def _check_transcription(report: Report, units: list[Unit]) -> None:
    failed = [u for u in units if u.transcription == "failed"]
    for unit in failed:
        _flag(report, "transcription-failed", "transcription did not parse under KaTeX", unit.id)
    missing = [u for u in units if u.transcription == "none" and u.state in ("new", "queued")]
    if missing:
        _flag(
            report,
            "transcription-missing",
            f"{len(missing)} untriaged units have no transcription -- run `/transcribe`",
        )
