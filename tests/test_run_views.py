"""What a finished run says: a summary, a tone, and the blocks to look at.

The page draws blocks and knows nothing about commands, so what each
command's result means is decided here, once, and tested here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from anki_math_forge.app import create_app, run_views
from anki_math_forge.config import Config

KINDS = {"stats", "table", "lines", "data"}


def kinds(view: dict[str, Any]) -> list[str]:
    return [b["kind"] for b in view["blocks"]]


def titled(view: dict[str, Any], title: str) -> dict[str, Any]:
    return next(
        b for b in view["blocks"] if b["kind"] == "table" and b["title"].startswith(title)
    )


def test_check_says_errors_before_warnings() -> None:
    findings = [
        {"level": "warn", "code": "gist-long", "message": "long", "path": "cards/a/aa-x.md"},
        {"level": "error", "code": "latex-parse", "message": "bad", "path": "cards/a/bb-x.md"},
    ]

    view = run_views.describe("check", findings, ok=True)

    assert view["summary"] == "1 error, 1 warning"
    assert view["tone"] == "bad"
    assert kinds(view) == ["stats", "table", "table"]
    assert titled(view, "errors")["rows"][0]["card"] == "bb-x.md"


def test_a_clean_check_is_one_line() -> None:
    view = run_views.describe("check", [], ok=True)
    assert view == {"summary": "clean: no findings", "tone": "ok", "blocks": []}


def push_report(dry: bool, *actions: str) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": dry,
        "outcomes": [
            {"uid": f"{i:06x}", "action": a, "detail": "", "gist": "g"}
            for i, a in enumerate(actions)
        ],
        "findings": [],
    }


def test_a_dry_push_says_what_would_change() -> None:
    view = run_views.describe(
        "anki", push_report(True, "add", "add", "update", "unchanged", "skip"), ok=True
    )

    assert view["summary"] == "would push: 2 add, 1 update; 1 unchanged, 1 skip"
    assert view["tone"] == "warn", "a skip is worth a look"
    change, now = view["blocks"][0], view["blocks"][1]
    assert change["title"] == "would change"
    assert {i["label"]: i["value"] for i in change["items"]} == {"add": 2, "update": 1}
    assert now["title"] == "now", "the change, and the state after it"
    assert {i["label"]: i["value"] for i in now["items"]} == {
        "in Anki after": 4,
        "unchanged": 1,
        "not ready": 1,
    }
    assert len(titled(view, "would change")["rows"]) == 3


def test_a_push_with_nothing_to_do_says_so() -> None:
    view = run_views.describe("anki push", push_report(False, "unchanged"), ok=True)
    assert view["summary"] == "nothing to push; 1 unchanged"
    assert view["tone"] == "ok"


def test_a_push_refused_by_check_says_why() -> None:
    report = push_report(False)
    report["findings"] = [{"level": "error", "code": "uid-duplicate", "message": "x", "uid": "a"}]
    report["ok"] = False

    view = run_views.describe("anki push", report, ok=False)

    assert view["summary"] == "refused: 1 check error"
    assert view["tone"] == "bad"


def test_pull_says_what_it_took() -> None:
    view = run_views.describe(
        "anki pull",
        {"ok": True, "dry_run": False, "imported": [{"uid": "a", "kind": "field", "text": "t"}],
         "skipped": []},
        ok=True,
    )
    assert view["summary"] == "1 comment taken from Anki"


def test_audit_counts_findings_by_check() -> None:
    data = [
        {"source": "book", "total": 10, "numbered": 9, "expected": 9, "complete": True,
         "flagged": ["book:1"], "findings": [
             {"code": "fragment-suspected", "message": "m", "unit": "book:1"}]},
    ]
    view = run_views.describe("audit", data, ok=True)

    assert view["summary"] == "1 finding over 1 project"
    assert view["blocks"][0]["items"][0]["label"] == "fragment-suspected"


def test_verify_lists_only_what_failed() -> None:
    data = [
        {"uid": "a", "status": "pass", "detail": "", "worst": 0.0},
        {"uid": "b", "status": "fail", "detail": "off", "worst": 0.4},
        {"uid": "c", "status": "skip", "detail": "", "worst": 0.0},
    ]
    view = run_views.describe("verify", data, ok=True)

    assert view["summary"] == "1 pass, 1 fail, 0 error, 1 skip"
    assert [r["uid"] for r in titled(view, "failed")["rows"]] == ["b"]


@pytest.mark.parametrize(
    "verb,data",
    [
        ("units", [{"id": "p:1", "state": "new", "gist": "g"}]),
        ("units extract", [{"project": "p", "found": 3, "added": 1, "refreshed": 2,
                            "mode": "tex", "transcription": {"ok": 3}, "warnings": ["w"]}]),
        ("units classify", [{"source": "p", "considered": 4, "kept": 3, "dry_run": True,
                             "classified": [{"unit_id": "p:1", "reason": "r", "detail": "d"}]}]),
        ("sources", [{"title": "T", "project": "p", "authoritative": True, "document": True,
                      "url": "", "zotero": "", "files": ["a.pdf"]}]),
        ("zotero", [{"item": "K", "citation": "C", "title": "T", "source": ""}]),
        ("zotero import", [{"source": "p", "item": "K", "citation": "C", "documents": 1,
                            "attachments": [], "marks": 5, "units": ["p:1"], "unmapped": 0,
                            "skipped": 0}]),
        ("todo", [{"kind": "card", "ref": "a", "note": "n", "where": "w", "status": "draft",
                   "audience": "claude", "source": "p"}]),
        ("cards", [{"uid": "a", "status": "draft", "gist": "g"}]),
    ],
)
def test_every_runnable_command_gets_a_summary_and_known_blocks(verb: str, data: Any) -> None:
    view = run_views.describe(verb, data, ok=True)

    assert view["summary"] and view["tone"] in {"ok", "warn", "bad"}
    assert set(kinds(view)) <= KINDS
    assert "data" not in kinds(view), "a view of its own, not the generic table"


@pytest.mark.parametrize("data", [None, [], {}, {"weird": 1}, [1, 2], "text", [{"x": None}]])
@pytest.mark.parametrize("verb", [*sorted(run_views.VIEWS), "no-such-verb"])
def test_a_shape_nobody_expected_never_loses_the_result(verb: str, data: Any) -> None:
    """The view is a convenience over the output. If it trips, the output
    is still drawn, generically."""
    view = run_views.describe(verb, data, ok=True)
    assert view["summary"]
    assert set(kinds(view)) <= KINDS


def test_a_failure_with_nothing_printed_says_the_reason() -> None:
    view = run_views.describe("anki", None, ok=False, said="cannot reach AnkiConnect\nmore")
    assert view["summary"] == "cannot reach AnkiConnect"
    assert view["tone"] == "bad"


def test_plain_text_output_becomes_lines() -> None:
    view = run_views.describe("export", {"text": "wrote deck.apkg\n"}, ok=True)
    assert view["summary"] == "wrote deck.apkg"
    assert kinds(view) == ["lines"]


def test_the_verb_is_settled_by_the_words_typed() -> None:
    names = {"anki", "anki push", "units", "units extract"}
    assert run_views.verb_of(["anki", "push", "--json"], names) == "anki push"
    assert run_views.verb_of(["anki", "--json"], names) == "anki"
    assert run_views.verb_of(["units", "--state", "all"], names) == "units"


# -- through the server -------------------------------------------------------


def finished(at: TestClient, run_id: str) -> dict[str, Any]:
    import time

    for _ in range(400):
        run = at.get(f"/api/run/{run_id}").json()
        if run["done"]:
            return dict(run)
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_a_run_carries_its_summary_and_the_list_carries_no_output(
    config: Config, card_path: Path
) -> None:
    at = TestClient(create_app(config))
    started = at.post("/api/run", json={"run": "uv run forge check"}).json()

    run = finished(at, started["id"])
    listed = at.get("/api/runs").json()["runs"][0]

    assert run["verb"] == "check"
    assert run["summary"] and run["tone"]
    assert isinstance(run["blocks"], list)
    assert listed["summary"] == run["summary"]
    assert "data" not in listed and "blocks" not in listed, "fetched one run at a time"


def test_clearing_forgets_what_finished(config: Config, card_path: Path) -> None:
    at = TestClient(create_app(config))
    finished(at, at.post("/api/run", json={"run": "uv run forge check"}).json()["id"])

    assert at.delete("/api/runs").json() == {"forgotten": 1}
    assert at.get("/api/runs").json()["runs"] == []


def test_a_writer_says_the_change_and_the_state_after() -> None:
    """"3 new" alone does not say whether the source now has three units or
    three hundred."""
    view = run_views.describe(
        "zotero import",
        [{"source": "p", "item": "K", "citation": "C", "marks": 9, "units": ["p:1"],
          "added": 3, "refreshed": 6, "dropped": 0, "in_ledger": 52, "project_units": 140}],
        ok=True,
    )

    assert [b.get("title") for b in view["blocks"][:2]] == ["this run", "now"]
    now = {i["label"]: i["value"] for i in view["blocks"][1]["items"]}
    assert now == {"units from these items": 52, "in p": 140}
    assert view["summary"] == "3 new, 6 refreshed; 52 units from 1 item in the ledger"


def test_sources_update_reports_both_doors() -> None:
    view = run_views.describe(
        "sources update",
        {
            "zotero": [{"source": "p", "item": "K", "added": 1, "in_ledger": 5}],
            "extract": [{"project": "p", "found": 7, "added": 0, "refreshed": 7, "total": 7}],
            "said": [],
        },
        ok=True,
    )
    assert "1 new" in view["summary"] and "7 units in the ledger" in view["summary"]
