"""What changed on a card since you last decided on it (ROADMAP §21).

Local and disposable: under the work dir, read by nothing that decides
anything. These check that it sees an edit whoever made it, that a review
decision is where it takes its snapshot, and that losing it costs nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import changes, model
from anki_math_forge.app import create_app
from anki_math_forge.cli import main
from anki_math_forge.config import Config


@pytest.fixture
def client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def mtime(path: Path) -> str:
    return str(path.stat().st_mtime_ns)


def by_hand(card_path: Path, **sections: str) -> None:
    """An edit no forge command made: an agent's Edit, or `$EDITOR`."""
    card = model.load(card_path)
    for name, body in sections.items():
        card.set_section(name, body)
    card.save()


def test_a_card_with_no_record_shows_none(config: Config, card_path: Path) -> None:
    assert changes.view(config, model.load(card_path)) is None


def test_a_decision_takes_the_snapshot(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    seen = changes.view(config, model.load(card_path))
    assert seen is not None
    assert seen["after"] == "approved"
    assert seen["pending"] is None, "nothing moved since"
    assert (config.work_dir / "changes" / "7f3a2b.json").exists()


def test_an_edit_by_anyone_shows_as_pending(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    card = model.load(card_path)
    card.frontmatter["frequency"] = "core"
    card.frontmatter["relearn"] = "more"
    card.set_section("back", "$X^{-\\top}$, for invertible $X$")
    card.add_annotation("@claude was the transpose right")
    card.resolve_annotation(0, "the transpose was right; the condition is now stated")
    card.save()

    pending = changes.view(config, model.load(card_path))["pending"]  # type: ignore[index]

    assert {f["key"] for f in pending["fields"]} == {"frequency", "relearn"}
    assert [s["name"] for s in pending["sections"]] == ["back"]
    assert "invertible" in pending["sections"][0]["summary"]
    assert pending["resolved"] and "condition is now stated" in pending["resolved"][0]


def test_the_status_is_not_listed_as_a_change(
    client: TestClient, config: Config, card_path: Path
) -> None:
    """The decision is the record's subject, not one of its rows."""
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    client.post("/api/cards/7f3a2b/unapprove", json={"mtime": mtime(card_path)})

    rec = changes.load(config, "7f3a2b")
    assert rec is not None
    last = rec["history"][-1]
    assert last["decision"] == "back to draft"
    assert last["change"]["fields"] == []


def test_the_next_decision_files_the_round(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    by_hand(card_path, prose="Why it holds.")
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    seen = changes.view(config, model.load(card_path))
    assert seen is not None and seen["pending"] is None
    newest = seen["history"][0]
    assert newest["decision"] == "approved"
    assert [s["name"] for s in newest["change"]["sections"]] == ["prose"]


def test_a_new_card_starts_its_record(config: Config, capsys: pytest.CaptureFixture[str]) -> None:
    """So the first review shows what the passes after `cards new` did."""
    from anki_math_forge import extract

    extract.run(config, "demo")
    main(["--root", str(config.root), "units", "set", "demo:1.1:2", "--state", "queued"])
    capsys.readouterr()
    main(["--root", str(config.root), "cards", "new", "--unit", "demo:1.1:2",
          "--front", "$a$", "--back", "$b$", "--json"])
    uid = json.loads(capsys.readouterr().out)["uid"]

    rec = changes.load(config, uid)
    assert rec is not None and rec["decision"] == "written"


def test_the_command_shows_it(
    client: TestClient, config: Config, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    by_hand(card_path, back="$Y$")
    capsys.readouterr()

    main(["--root", str(config.root), "cards", "--changes", "--json"])
    out = json.loads(capsys.readouterr().out)

    assert out[0]["changes"]["pending"]["sections"][0]["name"] == "back"

    main(["--root", str(config.root), "cards", "--changes"])
    assert "since approved" in capsys.readouterr().out


def test_the_review_page_shows_what_moved(
    client: TestClient, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    by_hand(card_path, back="$Y$")

    page = client.get("/review?status=all").text

    assert "data-changes open" in page
    assert 'data-change="section"' in page


def test_a_lost_record_costs_nothing(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    (config.work_dir / "changes" / "7f3a2b.json").write_text("{not json", encoding="utf-8")

    assert changes.view(config, model.load(card_path)) is None
    out = client.post("/api/cards/7f3a2b/unapprove", json={"mtime": mtime(card_path)})
    assert out.status_code == 200


@pytest.mark.parametrize(
    "was,now,says",
    [
        ("", "new text", 'added "new text"'),
        ("old", "", "removed"),
        ("a b c", "a x c", '"b" -> "x"'),
        ("a b c d e", "a x c y e", '"b" -> "x" (+1 more)'),
        ("a  b", "a b", "whitespace"),
    ],
)
def test_one_line(was: str, now: str, says: str) -> None:
    assert changes.one_line(was, now) == says


def test_the_review_page_draws_the_rounds_before(
    client: TestClient, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    card = model.load(card_path)
    card.frontmatter["frequency"] = "rare"
    card.set_section("prose", "Why it holds.")
    card.save()
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    page = client.get("/review?status=all")

    assert page.status_code == 200
    assert "data-change-history" in page.text
    assert "approved: frequency, prose" in page.text
