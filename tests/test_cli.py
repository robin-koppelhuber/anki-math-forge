"""The command line: exit codes, and the `--json` shapes Claude Code reads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from anki_math_forge import cli, model, sync
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger, Locator, Unit
from conftest import FakeAnki


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def out(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def drain(capsys: pytest.CaptureFixture[str]) -> None:
    """Forget output from set-up commands so `out()` sees only what matters."""
    capsys.readouterr()


# -- check -----------------------------------------------------------------


def test_check_passes_on_a_good_card(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "check") == 0
    assert "0 errors" in out(capsys)


def test_check_fails_on_a_broken_card(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "cards" / "bad.md").write_text(
        "---\nuid: nope\n---\n\n## front\n$a$\n", encoding="utf-8"
    )
    assert run(repo, "check") == 1


def test_check_json_is_machine_readable(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "check", "--json")
    assert json.loads(out(capsys)) == []


# -- extract and units -----------------------------------------------------


def test_extract_then_units(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo, "extract") == 0
    assert "units found via tex" in out(capsys)

    assert run(repo, "units", "--state", "new", "--json") == 0
    units = json.loads(out(capsys))
    assert len(units) == 5
    assert units[0]["source"] == "demo"
    assert units[0]["citation"].startswith("Demo")


def test_units_state_change_round_trips(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    assert run(repo, "units", "--id", "demo:1.1:2", "--set-state", "queued") == 0
    assert Ledger.load(config.units_path("demo")).get("demo:1.1:2").state == "queued"

    drain(capsys)
    run(repo, "units", "--state", "queued", "--json")
    assert [u["id"] for u in json.loads(out(capsys))] == ["demo:1.1:2"]


def test_units_rejects_an_unknown_id(repo: Path) -> None:
    run(repo, "extract")
    assert run(repo, "units", "--id", "demo:9:9", "--set-state", "queued") == 1


# -- new -------------------------------------------------------------------


def test_new_writes_a_stub_and_cards_the_unit(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1.1:2", "--set-state", "queued")
    drain(capsys)
    assert (
        run(
            repo,
            "new",
            "--unit",
            "demo:1.1:2",
            "--front",
            r"$\frac{\partial}{\partial X}\log\det X$",
            "--back",
            r"$X^{-\top}$",
            "--tag",
            "matrix-calculus",
            "--json",
        )
        == 0
    )
    payload = json.loads(out(capsys))
    assert payload["findings"] == []

    card = model.load(repo / payload["path"])
    assert card.status == "draft"
    assert card.unit == "demo:1.1:2"
    assert card.source == "Demo §1.1, eq. 2"
    assert card.tags == ["matrix-calculus"]

    unit = Ledger.load(config.units_path("demo")).get("demo:1.1:2")
    assert unit.state == "carded"
    assert unit.uids == [card.uid]


def test_new_files_the_card_under_its_source(repo: Path, config: Config) -> None:
    """One folder per source, so a second book does not land in the same
    thousand-file directory. Filing only: `unit:` is still what says where a
    card came from, and every loader rglobs, so a misfiled card still loads."""
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1.1:2", "--set-state", "queued")
    run(repo, "new", "--unit", "demo:1.1:2", "--front", "$a$", "--back", "$b$")

    written = list(config.cards_dir.rglob("*.md"))
    assert len(written) == 1
    assert written[0].parent.name == "demo"
    assert model.load_all(config.cards_dir)[0].source_name == "demo"


def test_new_without_a_unit_stays_at_the_top(repo: Path, config: Config) -> None:
    """No unit means no source to file it under. It must not vanish."""
    run(repo, "new", "--front", "$a$", "--back", "$b$")
    written = list(config.cards_dir.rglob("*.md"))
    assert len(written) == 1
    assert written[0].parent == config.cards_dir
    assert len(model.load_all(config.cards_dir)) == 1


def test_new_refuses_an_unknown_unit(repo: Path) -> None:
    run(repo, "extract")
    assert run(repo, "new", "--unit", "demo:9:9", "--front", "$a$", "--back", "$b$") == 1


def test_new_reports_a_malformed_stub(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(repo, "new", "--front", r"$\frac{a}{b$", "--back", "$c$") == 1
    assert "latex-parse" in out(capsys)


# -- todo ------------------------------------------------------------------


def test_todo_lists_open_annotations(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card = model.load(card_path)
    card.add_annotation("check the transpose")
    card.save()

    run(repo, "todo", "--json")
    items = json.loads(out(capsys))
    assert items[0]["kind"] == "card"
    assert items[0]["ref"] == "7f3a2b"
    assert "transpose" in items[0]["note"]


def test_todo_includes_units(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    ledger = Ledger.load(config.units_path("demo"))
    ledger.annotate("demo:1:1", "worth carding?")
    ledger.save()

    drain(capsys)
    run(repo, "todo", "--json")
    assert [i["kind"] for i in json.loads(out(capsys))] == ["unit"]


def test_todo_is_quiet_when_there_is_nothing(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "todo") == 0
    assert "no open annotations" in out(capsys)


# -- sync and verify -------------------------------------------------------


def test_sync_dry_run_reports_without_writing(
    repo: Path, card_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeAnki()
    monkeypatch.setattr(sync, "AnkiConnect", lambda *a, **k: fake)

    card = model.load(card_path)
    card.approve()
    card.save()

    assert run(repo, "sync", "--dry-run") == 0
    assert "would sync" in out(capsys)
    assert fake.notes == {}


def test_sync_refuses_a_card_with_an_open_annotation(
    repo: Path, card_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeAnki()
    monkeypatch.setattr(sync, "AnkiConnect", lambda *a, **k: fake)

    card = model.load(card_path)
    card.approve()
    card.add_annotation("not ready")
    card.save()

    run(repo, "sync")
    assert fake.notes == {}
    assert "open @claude annotation" in out(capsys)


def test_verify_reports_skips(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, "verify") == 0
    assert "1 skip" in out(capsys)


# -- transcription, note resolution, context -------------------------------


def test_a_transcription_is_gated_before_it_is_stored(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    drain(capsys)
    assert run(repo, "units", "--id", "demo:1:1", "--tex-auto", r"X^{-\top}") == 0
    assert "ok" in out(capsys)
    assert Ledger.load(config.units_path("demo")).get("demo:1:1").tex_auto == r"X^{-\top}"


def test_garbage_is_refused_and_nothing_is_stored(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    before = Ledger.load(config.units_path("demo")).get("demo:1:1").tex_auto
    drain(capsys)
    run(repo, "units", "--id", "demo:1:1", "--tex-auto", r"\frac{a}{b")
    assert "failed" in out(capsys)
    assert Ledger.load(config.units_path("demo")).get("demo:1:1").tex_auto == before


def test_unit_annotations_can_be_resolved(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without this a Gate 1 annotation would sit in `todo` for ever."""
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1:1", "--annotate", "two cards please")
    assert Ledger.load(config.units_path("demo")).get("demo:1:1").notes

    drain(capsys)
    assert run(repo, "units", "--id", "demo:1:1", "--resolve-notes") == 0
    assert "1 annotation(s) resolved" in out(capsys)
    assert Ledger.load(config.units_path("demo")).get("demo:1:1").notes == []
    drain(capsys)
    run(repo, "todo")
    assert "no open annotations" in out(capsys)


def test_audit_reports_the_numbering_oracle(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(repo, "extract")
    drain(capsys)
    assert run(repo, "audit") == 0
    assert "4/4 numbered equations (complete)" in out(capsys)


def test_source_text_is_cached_for_card_writing(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    drain(capsys)
    assert run(repo, "source-text", "demo") == 0
    text = out(capsys)
    assert "determinant identity everyone forgets" in text
    assert "context for writing cards, never a transcription" in text


def test_flagged_filters_to_the_suspect_units(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    drain(capsys)
    run(repo, "units", "--state", "all", "--flagged", "--json")
    # the tex source is clean, so nothing should be suspect
    assert json.loads(out(capsys)) == []


def test_crops_renders_working_files_with_a_manifest(
    repo: Path, pdf_source: Config, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """`crops` is how a transcriber subagent gets PNGs to read."""
    run(repo, "extract")
    drain(capsys)
    out = tmp_path / "crops"
    assert run(repo, "crops", "--source", "book", "--out", str(out), "--json") == 0

    manifest = json.loads(capsys.readouterr().out)
    assert len(manifest) == 2
    for entry in manifest:
        assert Path(entry["file"]).read_bytes().startswith(b"\x89PNG")
        assert entry["unit"].startswith("book:")
        assert entry["page"] == 1


def test_crops_can_select_only_what_still_needs_reading(
    repo: Path,
    pdf_source: Config,
    config: Config,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    run(repo, "extract")
    units = Ledger.load(pdf_source.units_path("book")).units
    run(repo, "units", "--id", units[0].id, "--tex-auto", "a = b")
    drain(capsys)

    run(repo, "crops", "--source", "book", "--untranscribed", "--out", str(tmp_path), "--json")
    remaining = json.loads(capsys.readouterr().out)
    assert [e["unit"] for e in remaining] == [units[1].id]


# -- suggestions -----------------------------------------------------------


def test_a_suggestion_is_recorded_but_not_applied(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    drain(capsys)
    assert (
        run(
            repo,
            "units",
            "--id",
            "demo:1:1",
            "--suggest",
            "skipped",
            "fragment",
            "--detail",
            "the equation continues above this box",
            "--by",
            "claude",
        )
        == 0
    )
    assert "not applied" in out(capsys)

    unit = Ledger.load(config.units_path("demo")).get("demo:1:1")
    assert unit.state == "new", "a suggestion must never move a unit on its own"
    assert unit.suggestion.reason == "fragment"
    assert unit.suggestion.by == "claude"


def test_accept_applies_a_suggestion(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1:1", "--suggest", "skipped", "fragment")
    drain(capsys)
    assert run(repo, "units", "--id", "demo:1:1", "--accept") == 0

    unit = Ledger.load(config.units_path("demo")).get("demo:1:1")
    assert unit.state == "skipped"
    assert unit.reason == "fragment"
    assert unit.suggestion is None


def test_dismiss_discards_a_suggestion(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1:1", "--suggest", "skipped", "fragment")
    drain(capsys)
    assert run(repo, "units", "--id", "demo:1:1", "--dismiss") == 0

    unit = Ledger.load(config.units_path("demo")).get("demo:1:1")
    assert unit.state == "new"
    assert unit.suggestion is None


def test_suggested_filters_to_open_proposals(
    repo: Path, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    run(repo, "extract")
    run(repo, "units", "--id", "demo:1:1", "--suggest", "skipped", "fragment")
    drain(capsys)
    run(repo, "units", "--state", "all", "--suggested", "--json")
    assert [r["id"] for r in json.loads(out(capsys))] == ["demo:1:1"]


def test_resolving_one_audience_leaves_the_other(tmp_path: Path) -> None:
    """Claude clearing its own request must not delete a decision parked for me.

    Both live in the same `notes` list, so a resolve that took everything
    would throw away the human's note without ever saying so.
    """
    led = Ledger(tmp_path / "units.jsonl")
    led.units.append(Unit(id="s:eq:1"))
    led.annotate("s:eq:1", "fix the transcription")           # defaults to @claude
    led.annotate("s:eq:1", "@me decide whether this is worth carding")
    assert len(led.units[0].notes) == 2

    cleared = led.resolve_notes("s:eq:1", "claude")
    assert cleared == 1
    assert led.units[0].notes == ["@me decide whether this is worth carding"]

    assert led.resolve_notes("s:eq:1") == 1
    assert led.units[0].notes == []


def test_one_card_can_be_built_from_several_units(tmp_path: Path, config: Config) -> None:
    """A multi-line display is several units and one identity.

    Splitting already worked -- a unit carries a list of uids. Merging needed
    `unit` to accept more than one, or the pieces of a torn equation could
    only ever become separate cards.
    """
    led = Ledger(config.units_path("demo"))
    led.units.extend(
        [
            Unit(id="demo:2.5:p13y636", locator=Locator(section="2.5", page=13)),
            Unit(id="demo:2.5:123", locator=Locator(section="2.5", equation=123, page=13)),
        ]
    )
    led.save()

    args = argparse.Namespace(
        unit=["demo:2.5:p13y636", "demo:2.5:123"],
        front="$a$",
        back="$b$",
        type="identity",
        tag=[],
        source="",
        gist="",
        json=False,
    )
    assert cli.cmd_new(args, config) == cli.OK

    card = next(iter(model.load_all(config.cards_dir)))
    assert card.units == ["demo:2.5:p13y636", "demo:2.5:123"]
    assert card.unit == "demo:2.5:p13y636", "one unit for the crop and the src:: tag"

    after = Ledger.load(config.units_path("demo"))
    for unit_id in card.units:
        unit = after.get(unit_id)
        assert unit is not None
        assert unit.state == "carded", f"{unit_id} was left untouched"
        assert unit.uids == [card.uid]


def test_todo_filters_on_audience(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The audience split decides whether a note is work or a report, so it is
    a flag rather than something the caller matches on the prose."""
    card = model.load(card_path)
    card.add_annotation("check the transpose")
    card.add_annotation("@me a decision for the human")
    card.save()
    drain(capsys)

    run(repo, "todo", "--audience", "claude")
    claude = out(capsys)
    assert "check the transpose" in claude
    assert "a decision for the human" not in claude

    run(repo, "todo", "--audience", "me")
    mine = out(capsys)
    assert "a decision for the human" in mine
    assert "check the transpose" not in mine


def test_todo_says_when_a_filter_emptied_the_list(
    repo: Path, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """"no open annotations" would otherwise read as "you are done"."""
    card = model.load(card_path)
    card.add_annotation("@me a decision for the human")
    card.save()
    drain(capsys)

    run(repo, "todo", "--audience", "claude")
    assert "matching that filter" in out(capsys)
    run(repo, "todo")
    assert "matching that filter" not in out(capsys)
