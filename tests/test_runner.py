"""Running a command from the website (ROADMAP.md §12).

Two rules, and the second is the amendment: only a command that shows you
something, and always in the background. The first is not a list kept here,
it is the `effect` the parser declares, so a verb that starts writing stops
being runnable from a button on the same commit.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.app import command_names, create_app, jobs, reading_verbs


def a_repo(repo: Path) -> Path:
    cli.main(["--root", str(repo), "project", "new", "demo", "--title", "Demo"])
    (repo / "projects" / "demo" / "units.jsonl").write_text(
        json.dumps({"id": "demo:one", "state": "new", "locator": {"document": "d.pdf"}}) + "\n",
        encoding="utf-8",
    )
    return repo


def client(repo: Path) -> TestClient:
    return TestClient(create_app(config_mod.load(repo)))


def finished(at: TestClient, run_id: str, seconds: float = 20.0) -> dict:
    """Poll the way the page does. Returns the run once it is done."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        got = at.get(f"/api/run/{run_id}").json()
        if got["done"]:
            return got
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never finished")


# -- only what shows you something ------------------------------------------


def test_the_allow_list_is_the_parser_not_a_list_kept_here() -> None:
    """Every name in it is declared `reads` by the parser, and the writers
    are not in it. An allow-list kept by hand is one that disagrees with
    the tool it is guarding."""
    reads = reading_verbs()

    assert "check" in reads and "audit" in reads and "units" in reads
    assert "anki" in reads, "the bare form is the dry run"
    for writer in ("units extract", "anki push", "anki pull", "zotero import"):
        assert writer not in reads, writer


@pytest.mark.parametrize(
    "line",
    [
        "uv run forge anki push",
        "uv run forge units extract demo",
        "uv run forge zotero import --tag anki",
        "uv run forge anki pull",
        "uv run forge cards new --unit demo:one --front a --back b",
    ],
)
def test_a_command_that_writes_is_refused(repo: Path, line: str) -> None:
    a_repo(repo)

    answer = client(repo).post("/api/run", json={"run": line})

    assert answer.status_code == 400
    assert "show you something" in answer.json()["detail"]


def test_something_that_is_not_a_forge_command_is_refused(repo: Path) -> None:
    a_repo(repo)

    answer = client(repo).post("/api/run", json={"run": "rm -rf /"})

    assert answer.status_code == 400


def test_a_quoted_project_name_survives_the_parse() -> None:
    """The offers quote the project, and a name with a space in it is the
    case a naive split gets wrong."""
    argv = jobs.argv_for('uv run forge audit --project "a book"', *command_names())

    assert argv == ["audit", "--project", "a book", "--json"]


# -- and always in the background -------------------------------------------


def test_it_answers_before_the_command_has_finished(repo: Path) -> None:
    a_repo(repo)
    at = client(repo)

    started = at.post("/api/run", json={"run": "uv run forge check"}).json()

    assert started["id"]
    assert started["done"] is False, "the page is not waiting for it"
    assert finished(at, started["id"])["ok"]


def test_the_result_is_what_the_command_returns_rather_than_a_transcript(
    repo: Path,
) -> None:
    """`--json` is added for us, so the panel renders a result."""
    a_repo(repo)
    at = client(repo)

    run = at.post("/api/run", json={"run": "uv run forge units --project demo"}).json()
    done = finished(at, run["id"])

    assert done["ok"]
    assert isinstance(done["data"], list)
    assert done["data"][0]["id"] == "demo:one"
    assert done["seconds"] >= 0


def test_a_command_that_fails_says_why_rather_than_vanishing(repo: Path) -> None:
    """Every one of these can fail for a reason outside the repo: Anki
    closed, Zotero closed, no ledger yet. The reason is on stderr."""
    a_repo(repo)
    at = client(repo)

    run = at.post("/api/run", json={"run": "uv run forge source-text nope"}).json()
    done = finished(at, run["id"])

    assert not done["ok"]
    assert done["said"], "the reason reaches the page"


def test_the_page_still_answers_while_a_run_is_in_flight(repo: Path) -> None:
    """The amendment. Every endpoint is `def`, so a run in a thread leaves
    the views alone; this is the test that says so out loud."""
    a_repo(repo)
    at = client(repo)

    run = at.post("/api/run", json={"run": "uv run forge check"}).json()
    page = at.get("/units?project=demo&state=all")

    assert page.status_code == 200
    assert finished(at, run["id"])["done"]


def test_a_run_outlives_the_page_that_asked_for_it(repo: Path) -> None:
    """One runner per server, not per page: a reload mid-run should find
    the result waiting rather than nothing."""
    a_repo(repo)
    at = client(repo)

    run = at.post("/api/run", json={"run": "uv run forge audit"}).json()
    finished(at, run["id"])

    again = at.get(f"/api/run/{run['id']}").json()
    assert again["done"] and again["id"] == run["id"]


def test_an_unknown_run_says_the_server_may_have_restarted(repo: Path) -> None:
    a_repo(repo)

    answer = client(repo).get("/api/run/beefbeefbeef")

    assert answer.status_code == 404
    assert "restarted" in answer.json()["detail"]


def test_old_runs_are_forgotten_rather_than_kept_for_ever(repo: Path) -> None:
    a_repo(repo)
    at = client(repo)

    ids = [
        at.post("/api/run", json={"run": "uv run forge audit"}).json()["id"]
        for _ in range(jobs.KEEP + 3)
    ]
    for run_id in ids[-3:]:
        finished(at, run_id)

    assert at.get(f"/api/run/{ids[0]}").status_code == 404
    assert at.get(f"/api/run/{ids[-1]}").status_code == 200


# -- every offer the app draws a button for actually runs -------------------


def test_every_read_only_offer_can_be_run(repo: Path) -> None:
    """The button is drawn from `Offer.reads`, and this is the check that
    the two agree: a row offered as runnable that the endpoint refuses is
    a button that fails at the moment somebody presses it."""
    from anki_math_forge.app import runs as runs_mod

    a_repo(repo)
    both = command_names()
    for offer in runs_mod.OFFERS:
        if offer.kind != "shell" or not offer.reads:
            continue
        at_ = runs_mod.Ambient(project="demo", zotero_key="K", state="all")
        line = offer.run if isinstance(offer.run, str) else offer.run(at_)
        jobs.argv_for(line, *both)  # raises Refused if it would not run
