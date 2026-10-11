"""What the passes say about the tool: one file, one command to add to it."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from anki_math_forge import remarks
from anki_math_forge.cli import main
from anki_math_forge.config import Config, ConfigError


def test_a_remark_is_appended_with_who_said_it(config: Config) -> None:
    assert remarks.add(config, "the brief was cut at 76 characters", by="card-writer") == 1
    assert remarks.add(config, "a rule that made a card worse", by="augmenter", project="demo") == 2

    first, second = remarks.remarks(config)
    assert (first.by, first.project, first.text) == (
        "card-writer", "", "the brief was cut at 76 characters"
    )
    assert (second.by, second.project) == ("augmenter", "demo")
    text = remarks.path_for(config).read_text(encoding="utf-8")
    assert text.startswith("# Remarks") and text.count("\n## ") == 2


def test_nothing_to_say_is_refused(config: Config) -> None:
    with pytest.raises(ConfigError):
        remarks.add(config, "   ", by="card-writer")


def test_the_command_says_and_lists(
    config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    root = ["--root", str(config.root)]
    assert main([*root, "remarks", "add", "context drops a note", "--by", "card-writer"]) == 0
    capsys.readouterr()

    assert main([*root, "remarks", "--json"]) == 0
    (row,) = json.loads(capsys.readouterr().out)
    assert row["by"] == "card-writer" and row["text"] == "context drops a note"

    assert main([*root, "remarks", "--by", "someone-else", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_one_word_reads_and_two_write() -> None:
    """The verb rule (docs/VERBS.md): `forge remarks` shows, `forge remarks
    add` changes a file."""
    from anki_math_forge.app import command_effects

    effects = command_effects()
    assert effects["remarks"] == "reads"
    assert effects["remarks add"] == "repo"


def test_the_file_sits_beside_the_projects(config: Config) -> None:
    """Not in `docs/`: a pass writes it while it works, and a file there turned
    up as a change to commit."""
    assert remarks.path_for(config) == config.projects_dir / "remarks.md"
    assert remarks.shown(config) == "projects/remarks.md"


def test_a_remark_is_never_a_change_to_commit() -> None:
    """The repo's own ignore rules cover it, which is why it lives there."""
    root = Path(__file__).resolve().parent.parent
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "projects/remarks.md"], cwd=root, check=False
    )
    assert ignored.returncode == 0
