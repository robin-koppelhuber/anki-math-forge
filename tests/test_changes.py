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


def test_a_decision_takes_the_snapshot(client: TestClient, config: Config, card_path: Path) -> None:
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
    main(
        [
            "--root",
            str(config.root),
            "cards",
            "new",
            "--unit",
            "demo:1.1:2",
            "--front",
            "$a$",
            "--back",
            "$b$",
            "--json",
        ]
    )
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


def test_the_review_page_shows_what_moved(client: TestClient, card_path: Path) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    by_hand(card_path, back="$Y$")

    page = client.get("/review?status=all").text

    panel = page[page.index('data-panel="changes"') :][:200]
    assert 'data-default="open"' in panel and "data-moved" in panel
    assert 'data-change="section"' in page


def test_a_lost_record_costs_nothing(client: TestClient, config: Config, card_path: Path) -> None:
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


def test_the_review_page_draws_the_rounds_before(client: TestClient, card_path: Path) -> None:
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


def test_the_first_view_starts_the_record(
    client: TestClient, config: Config, card_path: Path
) -> None:
    """A card approved before the record existed had nothing to compare an
    edit against. Seeing it once in review is enough to start one."""
    assert changes.load(config, "7f3a2b") is None

    client.get("/review?status=all")
    by_hand(card_path, back="$Y$")
    page = client.get("/review?status=all").text

    assert changes.load(config, "7f3a2b")["history"][0]["decision"] == "first seen"  # type: ignore[index]
    assert 'data-change="section"' in page, "the edit after it shows"


def changed_row(page: str) -> str:
    """The rail row for the cards that moved, from its link to its count."""
    at = page.index('data-filter="changed"')
    return page[at : page.index("</li>", at)]


def test_the_rail_lists_the_cards_that_moved(client: TestClient, card_path: Path) -> None:
    """One click from "something changed" to the cards it changed: a pass
    edited a few of fifty, and finding them by paging is the thing to spare."""
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    still = client.get("/review?status=all&changed=yes").text
    assert '<article class="card item" data-uid="7f3a2b"' not in still
    assert "<b>0</b>" in changed_row(still), "on, it stays to be switched off"
    assert 'data-filter="changed"' not in client.get("/review?status=all").text, (
        "off and empty, there is no row"
    )

    by_hand(card_path, back="$Y$")
    moved = client.get("/review?status=all&changed=yes").text

    assert '<article class="card item" data-uid="7f3a2b"' in moved
    assert "<b>1</b>" in changed_row(moved)
    assert "data-moved" in moved, "and its panel says what moved, open"


# -- where a change came from -------------------------------------------------


def test_an_edit_in_the_page_says_so(client: TestClient, config: Config, card_path: Path) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    out = client.post(
        "/api/cards/7f3a2b/text",
        json={"mtime": mtime(card_path), "sections": {"back": "$Y$"}},
    )

    assert out.status_code == 200, out.text
    assert out.json()["card"]["changes"]["from"] == ["edited in the page"]
    page = client.get("/review?status=all").text
    assert "from edited in the page" in page

    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    seen = changes.view(config, model.load(card_path))
    assert seen is not None and seen["from"] == [], "a decision settles it"
    assert seen["history"][0]["from"] == ["edited in the page"], "and the round keeps it"


@pytest.mark.parametrize(
    "line,origin",
    [
        ('resolved: inbox 2026-10-03 14:02: "needs independence" — added to ## conditions',
         "inbox dump 2026-10-03 14:02"),
        ("resolved: asked what H is — glossed in ## prose", "a settled @claude note"),
    ],
)
def test_a_resolved_line_names_its_asker(
    client: TestClient, config: Config, card_path: Path, line: str, origin: str
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    card = model.load(card_path)
    card.set_section("prose", "Now with more.")
    card.set_section("notes", line)
    card.save()

    seen = changes.view(config, model.load(card_path))

    assert seen is not None and seen["from"] == [origin]


def test_the_augment_pass_is_named_by_its_flag(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    card = model.load(card_path)
    card.frontmatter["augmented"] = True
    card.set_section("proof", "By the chain rule.")
    card.save()

    seen = changes.view(config, model.load(card_path))

    assert seen is not None and "/augment" in seen["from"]


def test_an_edit_nothing_names_is_not_guessed(
    client: TestClient, config: Config, card_path: Path
) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    by_hand(card_path, back="$Y$")

    seen = changes.view(config, model.load(card_path))

    assert seen is not None and seen["pending"] and seen["from"] == []


def test_listing_the_changes_starts_a_record(
    config: Config, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What `/sort-notes` runs before it edits: a card with no record gets
    one, so the edit after it is a change the review page shows."""
    assert changes.load(config, "7f3a2b") is None

    main(["--root", str(config.root), "cards", "--changes", "--json"])
    capsys.readouterr()
    by_hand(card_path, back="$Y$")

    seen = changes.view(config, model.load(card_path))
    assert seen is not None and seen["pending"], "the edit shows"


def test_the_card_list_says_what_augment_selects_on(
    config: Config, card_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`/extract-cards --augment` picks its drafts from this: the ones the
    pass has not been over, and the ones somebody has asked about since."""
    card = model.load(card_path)
    card.add_annotation("@claude prove this one")
    card.add_annotation("@me is the sign right")
    card.save()

    main(["--root", str(config.root), "cards", "--status", "draft", "--json"])
    (row,) = json.loads(capsys.readouterr().out)

    assert row["augmented"] is False
    assert row["open_claude"] == 1, "an @me note is not a request for the pass"


def test_each_look_that_finds_a_change_is_an_entry_of_its_own(
    client: TestClient, config: Config, card_path: Path
) -> None:
    """Two passes with a look between them are two notes, each carrying the
    `resolved:` line it added, and a decision files them into its round."""
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})

    card = model.load(card_path)
    card.set_section("notes", "resolved: asked about the sign: it was right")
    card.set_section("prose", "The sign is fixed by the layout.")
    card.save()
    changes.ensure(config, model.load(card_path))  # the review page drawing it

    card = model.load(card_path)
    earlier = card.section("notes") or ""
    card.set_section("notes", earlier + "\nresolved: asked for a proof: added")
    card.set_section("proof", "By the chain rule.")
    card.save()

    seen = changes.view(config, model.load(card_path))
    assert seen is not None
    newest, older = seen["entries"][0], seen["entries"][1]
    assert newest["change"]["resolved"] == ["asked for a proof: added"], "the live look"
    assert older["change"]["resolved"] == ["asked about the sign: it was right"]
    assert older["at"] and not newest["at"], "one is filed, the other is not yet"
    assert [s["name"] for s in older["change"]["sections"]] == ["prose"]

    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    after = changes.view(config, model.load(card_path))
    assert after is not None and after["entries"] == [] and after["pending"] is None
    round_ = after["history"][0]
    assert len(round_["notes"]) == 2, "the round keeps both"
