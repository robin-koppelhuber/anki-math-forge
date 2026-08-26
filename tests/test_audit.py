"""The audit: mechanical confidence in an index, with no ground truth needed
beyond the document's own numbering."""

from __future__ import annotations

from pathlib import Path

from anki_forge import audit, extract
from anki_forge.config import Config
from anki_forge.ledger import Ledger, Locator, Unit


def ledger_of(tmp_path: Path, units: list[Unit]) -> Ledger:
    return Ledger(tmp_path / "units.jsonl", units)


def numbered(n: int, page: int = 1, top: float = 0.0, height: float = 12.0) -> Unit:
    return Unit(
        id=f"src:1:{n}",
        locator=Locator(section="1", equation=n, page=page, bbox=[100.0, top, 400.0, top + height]),
        transcription="ok",
        tex_auto="a = b",
    )


def test_a_complete_run_is_reported_complete(tmp_path: Path) -> None:
    led = ledger_of(tmp_path, [numbered(n, top=n * 20.0) for n in range(1, 6)])
    report = audit.audit(led, "src")
    assert report.complete
    assert report.numbered == report.expected == 5
    assert not report.gaps


def test_a_gap_in_the_numbering_is_caught(tmp_path: Path) -> None:
    """The free oracle: 1..N must be complete."""
    units = [numbered(n, top=n * 20.0) for n in (1, 2, 4, 5)]
    report = audit.audit(ledger_of(tmp_path, units), "src")
    assert not report.complete
    assert any(f.code == "number-missing" and "3" in f.message for f in report.findings)


def test_a_duplicated_equation_number_is_caught(tmp_path: Path) -> None:
    units = [numbered(1, top=20.0), numbered(2, top=40.0), numbered(2, top=60.0)]
    report = audit.audit(ledger_of(tmp_path, units), "src")
    assert not report.complete
    assert any(f.code == "number-duplicate" for f in report.findings)


def test_overlapping_crops_are_flagged(tmp_path: Path) -> None:
    """Two equations sharing a crop is the failure that reads as success."""
    units = [numbered(1, top=100.0, height=40.0), numbered(2, top=120.0, height=20.0)]
    report = audit.audit(ledger_of(tmp_path, units), "src")
    assert any(f.code == "crop-overlap" for f in report.findings)
    assert "src:1:1" in report.flagged


def test_an_oversized_crop_is_flagged(tmp_path: Path) -> None:
    units = [numbered(n, top=n * 40.0) for n in range(1, 6)]
    units.append(numbered(6, top=400.0, height=200.0))
    report = audit.audit(ledger_of(tmp_path, units), "src")
    assert any(f.code == "crop-oversized" for f in report.findings)


def test_a_failed_transcription_is_flagged(tmp_path: Path) -> None:
    unit = numbered(1, top=20.0)
    unit.transcription = "failed"
    report = audit.audit(ledger_of(tmp_path, [unit]), "src")
    assert any(f.code == "transcription-failed" for f in report.findings)


def test_untranscribed_units_are_reported_once(tmp_path: Path) -> None:
    units = [numbered(n, top=n * 20.0) for n in range(1, 4)]
    for unit in units:
        unit.transcription = "none"
    report = audit.audit(ledger_of(tmp_path, units), "src")
    codes = [f.code for f in report.findings]
    assert codes.count("transcription-missing") == 1


def test_an_unnumbered_document_has_no_oracle(tmp_path: Path) -> None:
    units = [Unit(id="src:eq:a", locator=Locator(page=1, bbox=[0.0, 0.0, 10.0, 10.0]))]
    report = audit.audit(ledger_of(tmp_path, units), "src")
    assert report.expected == 0
    assert not report.complete, "no numbering means nothing to prove completeness against"


def test_the_real_tex_source_audits_clean(config: Config) -> None:
    extract.run(config, "demo")
    report = audit.audit(Ledger.load(config.units_path("demo")), "demo")
    assert report.complete
    assert report.numbered == 4
