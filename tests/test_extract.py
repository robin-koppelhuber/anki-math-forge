"""Extraction and the ledger: segmentation, idempotency, transcription gating."""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import extract, latex
from anki_math_forge.config import Config
from anki_math_forge.extract import tex, transcribe
from anki_math_forge.ledger import Ledger

# -- tex segmentation ------------------------------------------------------


def test_numbered_equations_become_units(config: Config) -> None:
    report = extract.run(config, "demo")
    assert report.mode == "tex"
    units = Ledger.load(config.units_path("demo")).units
    assert [u.locator.equation for u in units if u.locator.equation] == [1, 2, 3, 4]
    assert units[1].locator.section == "1.1"
    assert units[1].tex_source == r"\frac{\partial}{\partial X}\log\det X = X^{-\top}"
    assert all(u.state == "new" for u in units)


def test_align_rows_are_numbered_separately(config: Config) -> None:
    extract.run(config, "demo")
    units = Ledger.load(config.units_path("demo")).units
    assert units[2].tex_source.endswith(r"= A^\top")
    assert units[3].tex_source.endswith(r"= (A + A^\top) X")


def test_unnumbered_equations_get_a_content_based_id(config: Config) -> None:
    """No number means no stable position -- hash the contents instead."""
    extract.run(config, "demo")
    units = Ledger.load(config.units_path("demo")).units
    unnumbered = [u for u in units if u.locator.equation is None]
    assert len(unnumbered) == 1
    assert unnumbered[0].id.split(":")[-1].startswith("h")

    extract.run(config, "demo")
    again = Ledger.load(config.units_path("demo")).units
    assert [u.id for u in again] == [u.id for u in units]


def test_alignment_markers_do_not_leak_into_a_row(config: Config) -> None:
    extract.run(config, "demo")
    units = Ledger.load(config.units_path("demo")).units
    assert "&" not in (units[2].tex_source or "")
    assert all(u.transcription == "ok" for u in units)


def test_context_comes_from_the_preceding_paragraph(config: Config) -> None:
    extract.run(config, "demo")
    unit = Ledger.load(config.units_path("demo")).units[1]
    assert "determinant identity" in unit.context
    assert "%" not in unit.context  # comments are stripped


def test_ids_are_source_section_equation(config: Config) -> None:
    extract.run(config, "demo")
    ids = [u.id for u in Ledger.load(config.units_path("demo")).units]
    assert ids[1] == "demo:1.1:2"


def test_extraction_never_writes_cards(config: Config) -> None:
    extract.run(config, "demo")
    assert list(config.cards_dir.glob("*.md")) == []


def test_split_rows_ignores_separators_inside_a_nested_environment() -> None:
    rows = tex.split_rows(r"a = \begin{cases} 1 \\ 2 \end{cases} \\ b = c")
    assert len(rows) == 2
    assert rows[1] == "b = c"


# -- ledger idempotency (DESIGN.md §12) ------------------------------------


def test_rerunning_extract_adds_nothing_and_preserves_state(config: Config) -> None:
    first = extract.run(config, "demo")
    path = config.units_path("demo")

    ledger = Ledger.load(path)
    ledger.set_state("demo:1.1:2", "queued")
    ledger.set_state("demo:1:1", "skipped", reason="trivial")
    ledger.mark_carded("demo:1.1:3", ["abc123"])
    ledger.save()

    second = extract.run(config, "demo")
    assert second.added == 0
    assert second.found == first.found

    after = Ledger.load(path)
    assert len(after) == first.found
    assert len({u.id for u in after}) == len(after)
    assert after.get("demo:1.1:2").state == "queued"
    assert after.get("demo:1:1").state == "skipped"
    assert after.get("demo:1:1").reason == "trivial"
    assert after.get("demo:1.1:3").state == "carded"
    assert after.get("demo:1.1:3").uids == ["abc123"]


def test_a_skip_is_sticky(config: Config) -> None:
    extract.run(config, "demo")
    path = config.units_path("demo")
    ledger = Ledger.load(path)
    ledger.set_state("demo:1:1", "skipped", reason="trivial")
    ledger.save()

    extract.run(config, "demo")
    assert Ledger.load(path).get("demo:1:1").state == "skipped"
    assert Ledger.load(path).select(state="new") != []


def test_new_source_material_is_added_on_rerun(config: Config, repo: Path) -> None:
    extract.run(config, "demo")
    source = repo / "projects" / "demo" / "demo.tex"
    text = source.read_text(encoding="utf-8").replace(
        r"\end{document}",
        "\\begin{equation}\nA^{-1}A = I\n\\end{equation}\n\\end{document}",
    )
    source.write_text(text, encoding="utf-8")

    report = extract.run(config, "demo")
    assert report.added == 1
    assert len(Ledger.load(config.units_path("demo"))) == 6


def test_ledger_round_trips_through_jsonl(config: Config) -> None:
    extract.run(config, "demo")
    path = config.units_path("demo")
    before = path.read_text(encoding="utf-8")
    Ledger.load(path).save()
    assert path.read_text(encoding="utf-8") == before


# -- transcription gating (DESIGN.md §4) -----------------------------------


def test_parseable_ocr_output_is_kept() -> None:
    state, value = transcribe.gate(r"$$X^{-\top}$$", latex.checker(()))
    assert (state, value) == ("ok", r"X^{-\top}")


def test_unparseable_ocr_output_stores_nothing() -> None:
    state, value = transcribe.gate(r"\frac{a}{b", latex.checker(()))
    assert state == "failed"
    assert value == "", "garbage must not be stored: the crop is the authority"


def test_empty_ocr_output_is_none() -> None:
    assert transcribe.gate("   ", latex.checker(())) == ("none", "")


def test_normalise_strips_delimiters_and_tags() -> None:
    assert transcribe.normalise(r"\[ x = y \tag{3} \]") == "x = y"


def test_a_transcription_is_only_stored_once_it_parses() -> None:
    """The gate is the whole mechanical contribution here (§4)."""
    assert transcribe.gate(r"X^{-	op}", latex.checker(()))[0] == "ok"
    assert transcribe.gate(r"\frac{a}{b", latex.checker(()))[0] == "failed"


def test_rerunning_extract_never_destroys_a_transcription(config: Config) -> None:
    """Re-extract fixes geometry; it must not undo what `/transcribe` read.

    Regression: `tex_auto` and `transcription` used to be refreshed along with
    the locator, so a single `forge extract` silently wiped every
    transcription in the ledger.
    """
    extract.run(config, "demo")
    path = config.units_path("demo")
    ledger = Ledger.load(path)
    unit_id = ledger.units[0].id
    ledger.transcribe(unit_id, r"X^{-\top}", latex.checker(()))

    extract.run(config, "demo")

    after = Ledger.load(path).get(unit_id)
    assert after.tex_auto == r"X^{-\top}"
    assert after.transcription == "ok"


def test_rerunning_extract_still_refreshes_geometry(config: Config) -> None:
    """The other half of the contract: a re-segment must move the box."""
    extract.run(config, "demo")
    path = config.units_path("demo")
    ledger = Ledger.load(path)
    unit = ledger.units[0]
    unit.locator.section = "wrong"
    unit.context = "stale"
    ledger.save()

    extract.run(config, "demo")
    after = Ledger.load(path).get(unit.id)
    assert after.locator.section != "wrong"
    assert after.context != "stale"
