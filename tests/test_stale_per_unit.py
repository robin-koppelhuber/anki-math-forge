"""The stale guard asks about one unit, not the whole ledger.

It compared the mtime of `units.jsonl`, so a background run that touched
any unit refused the next decision on whichever one you were looking at
and reloaded the page. With commands running from the page in the
background, that is the ordinary case rather than a rare one.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import extract
from anki_math_forge.app import create_app, unit_version
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger

THIS, OTHER = "demo:1.1:2", "demo:1:1"


@pytest.fixture
def ledger(config: Config) -> Path:
    extract.run(config, "demo")
    return config.units_path("demo")


def drawn(client: TestClient, unit_id: str) -> tuple[str, str]:
    """`(version, mtime)` as the triage page renders them."""
    page = client.get("/units?project=demo&state=all").text
    version = re.search(
        rf'data-id="{re.escape(unit_id)}"[^>]*?data-version="([0-9a-f]+)"', page, re.S
    )
    mtime = re.search(r'id="deck"[^>]*data-mtime="(\d+)"', page)
    assert version and mtime, "the page carries both"
    return version.group(1), mtime.group(1)


def somebody_else_queues(path: Path, unit_id: str) -> None:
    time.sleep(0.01)
    led = Ledger.load(path)
    led.set_state(unit_id, "queued")
    led.save()


def test_a_write_to_another_unit_does_not_stop_this_one(
    config: Config, ledger: Path
) -> None:
    client = TestClient(create_app(config))
    version, mtime = drawn(client, THIS)

    somebody_else_queues(ledger, OTHER)
    answer = client.post(
        f"/api/units/demo/{THIS}/state",
        json={"state": "queued", "version": version, "mtime": mtime},
    )

    assert answer.status_code == 200
    assert Ledger.load(ledger).get(THIS).state == "queued"
    assert Ledger.load(ledger).get(OTHER).state == "queued", "and theirs stands"


def test_a_write_to_this_unit_still_stops_it(config: Config, ledger: Path) -> None:
    client = TestClient(create_app(config))
    version, mtime = drawn(client, THIS)

    somebody_else_queues(ledger, THIS)
    answer = client.post(
        f"/api/units/demo/{THIS}/state",
        json={"state": "skipped", "version": version, "mtime": mtime},
    )

    assert answer.status_code == 409
    assert answer.json()["stale"] is True
    assert Ledger.load(ledger).get(THIS).state == "queued", "theirs was kept"


def test_the_answer_carries_the_unit_s_new_version(config: Config, ledger: Path) -> None:
    """So the next keystroke on the same unit is checked against what this
    one just wrote, not against what the page first drew."""
    client = TestClient(create_app(config))
    version, _ = drawn(client, THIS)

    answer = client.post(
        f"/api/units/demo/{THIS}/state", json={"state": "queued", "version": version}
    ).json()

    assert answer["version"] == unit_version(Ledger.load(ledger).get(THIS))
    assert answer["version"] != version


def test_a_page_that_sends_no_version_keeps_the_old_guard(
    config: Config, ledger: Path
) -> None:
    client = TestClient(create_app(config))
    _, mtime = drawn(client, THIS)

    somebody_else_queues(ledger, OTHER)
    answer = client.post(
        f"/api/units/demo/{THIS}/state", json={"state": "queued", "mtime": mtime}
    )

    assert answer.status_code == 409


def test_an_annotation_is_checked_against_its_own_unit(
    config: Config, ledger: Path
) -> None:
    client = TestClient(create_app(config))
    version, mtime = drawn(client, THIS)

    somebody_else_queues(ledger, OTHER)
    answer = client.post(
        f"/api/units/demo/{THIS}/annotate",
        json={"text": "@claude look", "version": version, "mtime": mtime},
    )

    assert answer.status_code == 200
