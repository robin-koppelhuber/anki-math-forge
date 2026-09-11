"""`feedback`: the one read from Anki, and why it erases what it takes."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import config as config_mod
from anki_math_forge import feedback, model, notetype, sync
from anki_math_forge.config import Config
from conftest import FakeAnki


def approve(path: Path) -> model.Card:
    card = model.load(path)
    card.approve()
    card.save()
    return card


def card_file(config: Config, uid: str, unit: str = "demo:1.1:2") -> Path:
    path = config.cards_dir / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "somewhere"\nunit: "{unit}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$X$\n\n## back\n$Y$\n",
        encoding="utf-8",
    )
    return path


def synced(config: Config, *uids: str) -> FakeAnki:
    for uid in uids:
        approve(card_file(config, uid))
    anki = FakeAnki()
    sync.run(config, client=anki)
    return anki


def with_flags(repo: Path, **flags: str) -> Config:
    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    toml += "\n[anki.flags]\n" + "".join(f'{k.lstrip("f")} = "{v}"\n' for k, v in flags.items())
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    return config_mod.load(repo)


# -- the field ------------------------------------------------------------


def test_a_comment_becomes_a_claude_annotation(config: Config) -> None:
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "the transpose on the back looks wrong")

    report = feedback.run(config, client=anki)

    card = model.find(config.cards_dir, "aaa111")
    assert card.annotations() == ["@claude the transpose on the back looks wrong"]
    assert [c.kind for c in report.imported] == ["field"]


def test_the_comment_is_erased_from_anki(config: Config) -> None:
    """Without this every run re-imports it, and a note resolved through
    `/triage` comes back from the dead on the next pull."""
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "needs a proof")
    feedback.run(config, client=anki)

    assert anki.get_feedback("aaa111") == ""

    card = model.find(config.cards_dir, "aaa111")
    card.resolve_annotation(0)
    card.save()
    feedback.run(config, client=anki)
    assert model.find(config.cards_dir, "aaa111").annotations() == []


def test_editor_html_becomes_one_line_of_text(config: Config) -> None:
    """`## notes` is line-based: a wrapped note would read back as a second,
    unaddressed annotation."""
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "first line<br>second &amp; third<div>fourth</div>")

    feedback.run(config, client=anki)

    assert model.find(config.cards_dir, "aaa111").annotations() == [
        "@claude first line second & third fourth"
    ]


def test_sync_never_writes_the_feedback_field(config: Config) -> None:
    """It is inbound only. A sync between typing and pulling must not wipe it."""
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "do not lose me")

    sync.run(config, client=anki)

    assert anki.get_feedback("aaa111") == "do not lose me"


# -- flags ----------------------------------------------------------------


def test_a_flag_becomes_an_annotation_naming_what_you_meant(repo: Path) -> None:
    config = with_flags(repo, f1="wrong: the maths does not check out")
    anki = synced(config, "aaa111")
    anki.set_flag("aaa111", 1)

    feedback.run(config, client=anki)

    assert model.find(config.cards_dir, "aaa111").annotations() == [
        "@claude flagged 1: wrong: the maths does not check out"
    ]
    assert anki.cards_by_uid("aaa111")["flags"] == 0, "cleared, or it returns for ever"


def test_a_flag_with_no_configured_meaning_is_reported_not_guessed(repo: Path) -> None:
    config = with_flags(repo, f1="wrong")
    anki = synced(config, "aaa111")
    anki.set_flag("aaa111", 5)

    report = feedback.run(config, client=anki)

    assert report.imported == []
    assert any("no meaning" in reason for _, reason in report.skipped)
    assert anki.cards_by_uid("aaa111")["flags"] == 5, "left set, so nothing is lost"


def test_an_unrecognised_flag_number_is_refused_at_load(repo: Path) -> None:
    with pytest.raises(config_mod.ConfigError, match="1 to 7"):
        with_flags(repo, f9="nonsense")


# -- what it refuses to do ------------------------------------------------


def test_a_comment_with_no_card_file_is_left_where_it_is(config: Config) -> None:
    """Clearing the only copy of a comment would destroy it."""
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "keep me")
    model.find(config.cards_dir, "aaa111").path.unlink()

    report = feedback.run(config, client=anki)

    assert report.imported == []
    assert anki.get_feedback("aaa111") == "keep me"
    assert any("no card file" in reason for _, reason in report.skipped)


def test_a_dry_run_changes_nothing_at_either_end(config: Config) -> None:
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "a thought")

    report = feedback.run(config, client=anki, dry_run=True)

    assert len(report.imported) == 1
    assert anki.get_feedback("aaa111") == "a thought"
    assert model.find(config.cards_dir, "aaa111").annotations() == []


# -- the migration that must not orphan review history --------------------


def test_a_missing_field_is_added_to_the_live_note_type(config: Config) -> None:
    """Bumping the version instead renames the note type, and `sync` finds
    notes by that name -- so every note would be orphaned with its whole
    review history and re-added as new."""
    anki = synced(config, "aaa111")
    (note_id,) = anki.notes
    anki.models[config.note_type] = [f for f in notetype.FIELDS if f != "Feedback"]

    report = sync.run(config, client=anki)

    assert anki.models[config.note_type] == notetype.FIELDS
    assert list(anki.notes) == [note_id], "the note survives, history and all"
    assert any("Feedback" in (o.detail or "") for o in report.outcomes)


def test_a_renamed_or_removed_field_is_still_refused(config: Config) -> None:
    anki = synced(config, "aaa111")
    anki.models[config.note_type] = ["uid", "Recto", "Verso"]

    report = sync.run(config, client=anki)

    assert any(o.action == "error" for o in report.outcomes)
    assert any("note_type_version" in (o.detail or "") for o in report.outcomes)


def test_the_field_is_on_no_template(config: Config) -> None:
    """If it rendered, it would show up mid-review, which defeats the point."""
    spec = notetype.spec(config.note_type)
    rendered = "".join(
        side for template in spec["cardTemplates"] for side in template.values()
    )
    assert "Feedback" in notetype.FIELDS
    assert "{{Feedback}}" not in rendered


def test_anki_error_while_clearing_is_reported_not_swallowed(config: Config) -> None:
    anki = synced(config, "aaa111")
    anki.set_feedback("aaa111", "a thought")
    anki.fail_on = "updateNoteFields"

    report = feedback.run(config, client=anki)

    assert report.imported == []
    assert not report.ok
    assert model.find(config.cards_dir, "aaa111").annotations(), "recorded before clearing"
