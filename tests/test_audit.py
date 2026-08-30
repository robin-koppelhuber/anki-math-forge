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


# -- the pre-classifier ----------------------------------------------------


def unnumbered(uid: str, page: int = 9) -> Unit:
    return Unit(id=uid, locator=Locator(section="1", page=page, bbox=[100.0, 10.0, 400.0, 30.0]))


def test_front_matter_is_suggested_not_applied(tmp_path: Path) -> None:
    """The whole point: a guess proposes, a human decides.

    Regression: this used to set the state itself, and 61 units the human had
    never triaged appeared as `skipped` with no explanation.
    """
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    report = classify.classify(led, None, "src")

    assert [c.reason for c in report.classified] == ["front-matter"]
    unit = led.get("src:eq:p2")
    assert unit.state == "new", "nothing may change state on its own"
    assert unit.suggestion is not None
    assert unit.suggestion.state == "skipped"
    assert unit.suggestion.by == "classify"
    assert unit.suggestion.detail, "a suggestion must carry its argument"


def test_accepting_a_suggestion_applies_it(tmp_path: Path) -> None:
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    classify.classify(led, None, "src")
    unit = led.accept("src:eq:p2")

    assert unit.state == "skipped"
    assert unit.reason == "front-matter"
    assert unit.suggestion is None, "an accepted suggestion is spent"


def test_dismissing_a_suggestion_leaves_the_unit_alone(tmp_path: Path) -> None:
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    classify.classify(led, None, "src")
    unit = led.dismiss("src:eq:p2")
    assert unit.state == "new"
    assert unit.suggestion is None


def test_deciding_yourself_overrules_a_suggestion(tmp_path: Path) -> None:
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    classify.classify(led, None, "src")
    led.set_state("src:eq:p2", "queued")

    unit = led.get("src:eq:p2")
    assert unit.state == "queued"
    assert unit.suggestion is None, "you overruled it; it should not linger"


def test_a_numbered_equation_is_never_classified(tmp_path: Path) -> None:
    """The book numbered it; no heuristic here overrules that."""
    from anki_forge import classify

    led = Ledger(tmp_path / "units.jsonl", [numbered(n, page=6, top=n * 20.0) for n in (1, 2)])
    report = classify.classify(led, None, "src")
    assert report.classified == []
    assert report.kept == 2


def test_a_triaged_unit_is_left_alone(tmp_path: Path) -> None:
    from anki_forge import classify

    unit = unnumbered("src:eq:p2", page=2)
    unit.state = "queued"
    led = Ledger(tmp_path / "units.jsonl", [unit, numbered(1, page=6, top=20.0)])
    classify.classify(led, None, "src")
    assert led.get("src:eq:p2").state == "queued"
    assert led.get("src:eq:p2").suggestion is None


def test_classify_does_not_churn_an_existing_suggestion(tmp_path: Path) -> None:
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    led.suggest("src:eq:p2", "queued", "mine", "a human said so", by="claude")
    classify.classify(led, None, "src")
    assert led.get("src:eq:p2").suggestion.by == "claude"


def test_dry_run_records_nothing(tmp_path: Path) -> None:
    from anki_forge import classify

    led = Ledger(
        tmp_path / "units.jsonl",
        [unnumbered("src:eq:p2", page=2), numbered(1, page=6, top=20.0)],
    )
    report = classify.classify(led, None, "src", write=False)
    assert report.classified
    assert led.get("src:eq:p2").suggestion is None


def test_a_suggestion_survives_the_ledger_round_trip(tmp_path: Path) -> None:
    led = Ledger(tmp_path / "units.jsonl", [unnumbered("src:eq:p2", page=2)])
    led.suggest("src:eq:p2", "skipped", "no-relation", "states no relation", by="claude")
    led.save()

    reloaded = Ledger.load(tmp_path / "units.jsonl").get("src:eq:p2")
    assert reloaded.suggestion.state == "skipped"
    assert reloaded.suggestion.by == "claude"


def test_matrix_without_row_separator_is_flagged(tmp_path: Path) -> None:
    """The failure this catches parses fine and means the wrong thing.

    A collapsed row separator turns a two-row matrix into one row. KaTeX
    accepts it, because `\ ` is a valid control space -- so the gate cannot
    be the check here.
    """
    led = Ledger(tmp_path / "units.jsonl")
    collapsed = Unit(id="s:eq:1", tex_auto=r"\begin{bmatrix} a & b \ c & d \end{bmatrix}")
    intact = Unit(id="s:eq:2", tex_auto=r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}")
    fragment = Unit(id="s:eq:4", tex_auto=r"\begin{bmatrix} a & b \end{bmatrix}")
    spaced = Unit(  # a legitimate control space, separators intact
        id="s:eq:5",
        tex_auto=r"\begin{array}{ll} \mathbf{A}\ n\times n & x \\ b & y \end{array}",
    )
    plain = Unit(id="s:eq:3", tex_auto="a = b")
    led.units.extend([collapsed, intact, fragment, spaced, plain])

    codes = [(f.code, f.unit_id) for f in audit.audit(led, "s").findings]
    assert ("transcription-rowsep", "s:eq:1") in codes
    # s:eq:4 is one row of a larger matrix, legitimately separator-free: a
    # check that flagged it would train the reader to ignore this finding.
    assert not [c for c in codes if c[0] == "transcription-rowsep" and c[1] != "s:eq:1"]


def test_a_deliberate_refusal_is_not_a_gap(tmp_path: Path) -> None:
    """Read-and-declined must not read as work outstanding.

    Otherwise the next pass is sent back over exactly the crops where
    refusing to guess was the right answer.
    """
    led = Ledger(tmp_path / "units.jsonl")
    unread = Unit(id="s:eq:1")
    declined = Unit(id="s:eq:2", notes=["@claude crop is cut off on the left"])
    led.units.extend([unread, declined])

    codes = {f.code: f.message for f in audit.audit(led, "s").findings}
    assert "1 untriaged units" in codes["transcription-missing"]
    assert "1 units were read" in codes["transcription-declined"]
