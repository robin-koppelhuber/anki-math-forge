"""Actions: commands as forms, built from fields and never parsed from text."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.app import actions, create_app, runs
from anki_math_forge.config import Config

PROJECTS = ["book", "cpp"]


def finished(client: TestClient, run_id: str) -> dict[str, Any]:
    """Poll the way the page does, until the run is done.

    Kept here and not imported from `test_runner`: `tests/` is not a package,
    so a test module cannot import another one by name.
    """
    for _ in range(400):
        run = client.get(f"/api/run/{run_id}").json()
        if run["done"]:
            return dict(run)
        time.sleep(0.05)
    raise AssertionError("run never finished")


def argv(key: str, **values: object) -> list[str]:
    return actions.BY_KEY[key].argv(dict(values), PROJECTS)


def test_fields_become_flags_and_positionals() -> None:
    assert argv("anki-push", project="cpp", templates=True) == [
        "anki",
        "push",
        "--project",
        "cpp",
        "--templates",
    ]
    assert argv("units-extract", project="book", pages="10-40") == [
        "units",
        "extract",
        "book",
        "--pages",
        "10-40",
    ]
    assert argv("anki-push") == ["anki", "push"], "an empty project means every project"
    assert argv("anki-push", dry_run=True) == ["anki", "push", "--dry-run"]


def test_a_tag_action_starts_on_its_default() -> None:
    assert argv("zotero-tag") == ["zotero", "import", "--tag", "anki"]


@pytest.mark.parametrize(
    "key,values,why",
    [
        ("zotero-new", {}, "is needed"),
        ("zotero-new", {"item": "--tag"}, "may not start with '-'"),
        ("anki-push", {"project": "nope"}, "no project"),
        ("units-extract", {}, "is needed"),
    ],
)
def test_a_value_that_cannot_run_is_refused(key: str, values: dict[str, object], why: str) -> None:
    """Nothing typed into a field can become a flag."""
    with pytest.raises(actions.Invalid, match=why):
        actions.BY_KEY[key].argv(values, PROJECTS)


def test_every_action_names_a_command_the_parser_has() -> None:
    from anki_math_forge.app import command_effects

    effects = command_effects()
    for action in actions.ACTIONS:
        assert action.verb in effects, action.verb
        for field in action.fields:
            if field.flag:
                assert field.flag.startswith("--"), (action.key, field.name)


@pytest.mark.parametrize(
    "line,key,values",
    [
        # The rehearsal is the push with test ticked, not an action of its own.
        ("forge anki --project book", "anki-push", {"project": "book", "dry_run": True}),
        ("forge anki push --dry-run", "anki-push", {"dry_run": True}),
        ("forge zotero import --tag anki", "zotero-tag", {"tag": "anki"}),
        ("forge zotero import --project book", "zotero-project", {"project": "book"}),
        ("forge zotero import <citekey>", "zotero-new", {"item": ""}),
        ("forge units extract book", "units-extract", {"project": "book"}),
        ("forge anki push", "anki-push", {}),
    ],
)
def test_an_offered_line_opens_as_its_action(line: str, key: str, values: dict[str, str]) -> None:
    found = runs.action_of(line)
    assert found == (key, values)


def test_a_line_no_action_has_stays_a_line() -> None:
    assert runs.action_of("forge units --project book --state all") is None


def test_the_server_builds_runs_and_refuses(config: Config) -> None:
    client = TestClient(create_app(config))

    listed = client.get("/api/actions?project=demo").json()
    assert listed["project"] == "demo"
    assert {a["key"] for a in listed["actions"]} >= {"anki-push", "zotero-new", "check"}

    shown = client.post("/api/actions/audit/line", json={"values": {"project": "demo"}})
    assert shown.json() == {"line": "uv run forge audit --project demo", "effect": "reads"}

    # An unfilled form is a state, not a failure: it says what is missing.
    refused = client.post("/api/actions/zotero-new/line", json={"values": {}})
    assert refused.status_code == 200
    assert refused.json()["line"] == "" and "needed" in refused.json()["refused"]
    assert client.post("/api/actions/nope/line", json={"values": {}}).status_code == 404

    asked = client.post("/api/actions/units-classify/run", json={"values": {}})
    assert asked.status_code == 409, "a writer has to be confirmed"
    started = client.post("/api/actions/check/run", json={"values": {}})
    assert started.status_code == 200 and started.json()["verb"] == "check"
    # A run is a thread that swaps the process's `sys.stdout` while it works.
    # Left going, it swallows what the next test prints, and on a slower
    # machine than this one it was still going.
    finished(client, started.json()["id"])


# -- which project a Zotero item goes to -------------------------------------


def test_a_tagged_item_goes_to_the_project_that_already_reads_it(repo: Path) -> None:
    """`--tag anki` without `--project` filed every item under its cite key,
    making a second project for a book already imported into another."""
    folder = repo / "projects" / "cpp"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text(
        'title = "C++"\n\n[[sources]]\nzotero = "K123"\n', encoding="utf-8"
    )
    config = config_mod.load(repo)

    known = SimpleNamespace(key="K123", citation_key="stroustrupTour2022")
    unknown = SimpleNamespace(key="Z999", citation_key="newBook2024")

    assert cli._home_of(config, known) == "cpp"
    assert cli._home_of(config, unknown) == "newBook2024"


# -- the text layers a card writer reads ----------------------------------------


def test_source_text_prints_every_layer_a_project_has(
    config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """A project read from Zotero caches one file per document, and the
    command read only the single-file form."""
    folder = config.projects_dir / "demo"
    (folder / "text-AAA.md").write_text("## page 1\nfirst document", encoding="utf-8")
    (folder / "text-BBB.md").write_text("## page 1\nsecond document", encoding="utf-8")

    assert cli.main(["--root", str(config.root), "source-text", "demo"]) == 0
    out = capsys.readouterr().out
    assert "first document" in out and "second document" in out
    assert "# AAA" in out and "# BBB" in out


def test_a_project_web_key_is_honoured(repo: Path) -> None:
    folder = repo / "projects" / "open"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text('title = "Open"\nweb = true\n', encoding="utf-8")

    assert config_mod.load(repo).context_for("open") == "web"


def test_sources_update_re_reads_what_a_project_reads(
    config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    """The demo project reads a TeX file and no Zotero item, so the update
    is the segmenter, with the state after it."""
    import json

    code = cli.main(
        ["--root", str(config.root), "sources", "update", "--project", "demo", "--json"]
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["zotero"] == []
    assert out["extract"][0]["project"] == "demo"
    assert out["extract"][0]["total"] >= out["extract"][0]["added"] > 0
