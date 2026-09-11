"""Concurrent writers must not lose each other's changes.

Six classifier agents running in parallel once destroyed 45 of 61 suggestions:
every write rewrites the whole ledger, so two processes that each load, change
one unit and save produce last-writer-wins, silently. `Ledger.edit` serialises
them. These tests fail loudly if that ever stops being true.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from anki_math_forge.ledger import Ledger, LockTimeout, Unit, lock

WRITERS = 12


def _make_ledger(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(Unit(id=f"src:eq:{i}").to_json(), ensure_ascii=False, sort_keys=True)
        for i in range(n)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _suggest(args: tuple[str, int]) -> None:
    """One process: propose a skip on exactly one unit."""
    raw, i = args
    with Ledger.edit(Path(raw)) as led:
        led.suggest(f"src:eq:{i}", "skipped", "fragment", f"detail {i}", by="test")


def test_parallel_writers_all_survive(tmp_path: Path) -> None:
    path = tmp_path / "units.jsonl"
    _make_ledger(path, WRITERS)

    with ProcessPoolExecutor(max_workers=WRITERS) as pool:
        list(pool.map(_suggest, [(str(path), i) for i in range(WRITERS)]))

    led = Ledger.load(path)
    assert len(led) == WRITERS
    missing = [u.id for u in led if u.suggestion is None]
    assert not missing, f"{len(missing)} of {WRITERS} writes were lost: {missing}"
    for i, unit in enumerate(led):
        assert unit.suggestion is not None
        assert unit.suggestion.detail == f"detail {i}"
        assert unit.state == "new", "a suggestion must not change state"


def test_lock_is_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "units.jsonl"
    _make_ledger(path, 1)
    with lock(path), pytest.raises(LockTimeout), lock(path, timeout=0.2):
        pass


def test_lock_is_released_on_error(tmp_path: Path) -> None:
    path = tmp_path / "units.jsonl"
    _make_ledger(path, 1)
    with pytest.raises(ValueError), lock(path):
        raise ValueError("boom")
    with lock(path, timeout=0.5):  # must not raise: the lock was released
        pass


def test_edit_does_not_save_a_failed_mutation(tmp_path: Path) -> None:
    path = tmp_path / "units.jsonl"
    _make_ledger(path, 1)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(KeyError), Ledger.edit(path) as led:
        led.suggest("src:eq:nope", "skipped", "fragment", "", by="test")
    assert path.read_text(encoding="utf-8") == before
    with lock(path, timeout=0.5):
        pass
