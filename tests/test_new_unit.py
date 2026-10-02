"""A unit typed in on the triage page (ROADMAP §19).

`forge units add` and the dialog write through one function, so they agree
about the id a subject takes and about what asking twice does. Invariant 3
holds whichever door a unit came in by: it arrives `new`, with no front and
no back.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import extract
from anki_math_forge.app import create_app
from anki_math_forge.cli import main
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger


@pytest.fixture
def client(config: Config) -> TestClient:
    extract.run(config, "demo")
    return TestClient(create_app(config))


def test_the_dialog_writes_a_new_unit(client: TestClient, config: Config) -> None:
    out = client.post(
        "/api/units/demo",
        json={
            "subject": "Cauchy Schwarz",
            "gist": "  the inequality,\n for vectors ",
            "preview": "|<x,y>| <= |x||y|",
            "tags": "inequality, linear-algebra",
            "refs": ["https://example.org/cs"],
        },
    )

    assert out.status_code == 200, out.text
    assert out.json()["created"] is True
    unit = Ledger.load(config.units_path("demo")).get("demo:cauchy-schwarz")
    assert unit is not None
    assert unit.state == "new", "invariant 3: every unit arrives new"
    assert unit.gist == "the inequality, for vectors", "one line"
    assert unit.tags == ["inequality", "linear-algebra"]
    assert unit.refs == ["https://example.org/cs"]


def test_asking_twice_leaves_the_first_alone(client: TestClient, config: Config) -> None:
    """It may have been triaged in between."""
    client.post("/api/units/demo", json={"subject": "Cauchy Schwarz"})
    with Ledger.edit(config.units_path("demo")) as led:
        led.set_state("demo:cauchy-schwarz", "queued")

    again = client.post("/api/units/demo", json={"subject": "cauchy schwarz", "gist": "x"})

    assert again.json()["created"] is False
    unit = Ledger.load(config.units_path("demo")).get("demo:cauchy-schwarz")
    assert unit is not None and unit.state == "queued" and unit.gist == ""


def test_the_command_and_the_dialog_take_the_same_id(
    client: TestClient, config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["--root", str(config.root), "units", "add", "Jensen's inequality",
          "--project", "demo"])
    capsys.readouterr()

    out = client.post("/api/units/demo", json={"subject": "Jensen's inequality"})

    assert out.json()["created"] is False, "the dialog found what the command wrote"


@pytest.mark.parametrize("subject", ["", "  ", "---"])
def test_a_subject_with_nothing_to_name_is_refused(client: TestClient, subject: str) -> None:
    out = client.post("/api/units/demo", json={"subject": subject})
    assert out.status_code == 400


def test_no_such_project(client: TestClient) -> None:
    assert client.post("/api/units/nope", json={"subject": "x"}).status_code == 404


def test_the_triage_page_carries_the_dialog_and_its_key(client: TestClient) -> None:
    page = client.get("/units?project=demo&state=all").text

    assert "data-new-unit-dialog" in page
    for name in ("subject", "gist", "preview", "tags", "refs"):
        assert f'name="{name}"' in page, name
    assert '"new-unit"' in page, "bound in the keymap the script reads"

