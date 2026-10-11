"""`scripts/affected.py`: which tests a change is likely to touch, by name."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("affected", HERE.parent / "scripts" / "affected.py")
assert spec and spec.loader
affected = importlib.util.module_from_spec(spec)
spec.loader.exec_module(affected)

SRC = affected.SRC


def test_a_module_runs_the_tests_named_for_it() -> None:
    files, everything = affected.select([f"{SRC}inbox.py"])

    assert "tests/test_inbox.py" in files and not everything


def test_a_views_script_runs_its_unit_and_browser_tests() -> None:
    files, everything = affected.select([f"{SRC}app/static/graph.js"])

    assert {"tests/test_graph.py", "tests/browser/test_graph.py"} <= set(files)
    assert not everything


def test_what_every_page_uses_runs_everything_but_the_browser() -> None:
    for name in ("app/__init__.py", "app/templates/base.html", "app/static/app.css", "model.py"):
        assert affected.select([f"{SRC}{name}"]) == ([], True), name


def test_a_file_no_test_is_named_for_is_not_skipped(tmp_path: Path) -> None:
    (tmp_path / "test_other.py").write_text("", encoding="utf-8")

    assert affected.select([f"{SRC}zzz.py"], tests=tmp_path) == ([], True)


def test_docs_and_a_changed_test_file_are_picked_up() -> None:
    files, everything = affected.select(
        ["docs/STYLE.md", ".claude/commands/gist.md", "tests/test_check.py"]
    )

    assert files == ["tests/test_check.py", "tests/test_style.py"] and not everything
    assert affected.select(["tests/conftest.py"]) == ([], True), "it reaches every test"


def test_a_named_browser_file_is_not_lost_to_the_ignore() -> None:
    first, second = affected.commands(["tests/browser/test_graph.py"], True)

    assert "--ignore=tests/browser" in first and "tests/browser/test_graph.py" not in first
    assert second[-1] == "tests/browser/test_graph.py"
    assert len(affected.commands(["tests/test_inbox.py"], False)) == 1
