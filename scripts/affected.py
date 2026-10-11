#!/usr/bin/env python
"""Run the tests an uncommitted change is likely to touch.

    uv run python scripts/affected.py          # run them
    uv run python scripts/affected.py --list   # say which, run nothing

Tests are picked by name. `inbox.py` has `tests/test_inbox*.py`, and a view's
script or template has the tests with the view's name in them, browser ones
included. A change to something every page uses, or to a file no test is named
for, runs all the tests that do not drive a browser.

This is a shortcut for the loop and not a gate. It cannot see a change in one
module that breaks another, so `uv run pytest` is what comes before a commit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = "src/anki_math_forge/"

#: Files every page, or every command, goes through.
SHARED = {"__init__", "base", "app", "theme", "model", "config", "cli"}


def select(changed: list[str], tests: Path = ROOT / "tests") -> tuple[list[str], bool]:
    """The test files to run, and whether to run everything but the browser."""
    chosen: set[str] = set()
    everything = False
    for name in changed:
        path = Path(name)
        if name.startswith("tests/"):
            if path.name == "conftest.py":
                everything = True
            elif path.suffix == ".py" and path.name.startswith("test_"):
                chosen.add(name)
        elif name.startswith(".claude/") or path.suffix == ".md":
            chosen.add("tests/test_style.py")
        elif name.startswith(SRC):
            stem = path.stem.lstrip("_")
            named = [] if stem in SHARED else sorted(tests.rglob(f"test_*{stem}*.py"))
            if named:
                chosen.update(p.relative_to(tests.parent).as_posix() for p in named)
            else:
                everything = True
    return sorted(chosen), everything


def commands(files: list[str], everything: bool) -> list[list[str]]:
    pytest = [sys.executable, "-m", "pytest"]
    if not everything:
        # Starting workers costs more than a couple of files take.
        return [[*pytest, *files, *(["-n0"] if len(files) <= 2 else [])]]
    workers = str(min(8, os.cpu_count() or 4))
    rest = [*pytest, "--ignore=tests/browser", "--dist", "load", "-n", workers]
    rest += ["--maxprocesses", workers]
    # `--ignore` would drop a browser file that was named, so it runs on its own.
    browser = [f for f in files if f.startswith("tests/browser/")]
    return [rest, *([[*pytest, *browser]] if browser else [])]


def changed_files() -> list[str]:
    """Everything uncommitted: edited, staged and new."""
    out: list[str] = []
    for args in (["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        done = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        )
        out.extend(done.stdout.split())
    return sorted(set(out))


def main() -> int:
    files, everything = select(changed_files())
    if not files and not everything:
        print("nothing changed that a test is named for")
        return 0
    if everything:
        named = sum(f.startswith("tests/browser/") for f in files)
        print("all but the browser's" + (f", and {named} browser files" if named else ""))
    else:
        print(" ".join(files))
    if "--list" in sys.argv:
        return 0
    status = 0
    for command in commands(files, everything):
        status = max(status, subprocess.run(command, cwd=ROOT).returncode)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
