"""Front and back, edited on the review page (ROADMAP §18).

The editor is a way to write the file and nothing more (invariant 2). It
does not enforce invariant 5: changing what a reviewer read changes
`content_hash`, and that alone takes an approval back.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import model
from anki_math_forge.app import create_app
from anki_math_forge.config import Config


@pytest.fixture
def client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def opened(client: TestClient) -> dict[str, str]:
    out = client.get("/api/cards/7f3a2b/text")
    assert out.status_code == 200
    return dict(out.json())


def test_the_editor_starts_from_the_file(client: TestClient, card_path: Path) -> None:
    text = opened(client)
    card = model.load(card_path)

    assert text["front"] == card.section("front")
    assert text["back"] == card.section("back")
    assert text["mtime"] == str(card_path.stat().st_mtime_ns)


def test_saving_writes_both_sides(client: TestClient, card_path: Path) -> None:
    text = opened(client)
    out = client.post(
        "/api/cards/7f3a2b/text",
        json={"mtime": text["mtime"], "front": "$\\log|X|$", "back": "$X^{-T}$"},
    )

    assert out.status_code == 200, out.text
    card = model.load(card_path)
    assert card.section("front") == "$\\log|X|$"
    assert card.section("back") == "$X^{-T}$"
    assert card.annotations() == [], "no note unless asked for"


def test_an_edit_takes_an_approval_back(client: TestClient, card_path: Path) -> None:
    """Invariant 5, by the hash and nothing else: the file still says
    approved, and the card counts as a draft."""
    card = model.load(card_path)
    card.approve()
    card.save()
    text = opened(client)

    client.post(
        "/api/cards/7f3a2b/text",
        json={"mtime": text["mtime"], "front": text["front"] + " ", "back": "$Y$"},
    )

    card = model.load(card_path)
    assert card.status == "approved"
    assert card.demotion == "edited"
    assert card.effective_status == "draft"


def test_the_note_goes_on_in_the_same_write(client: TestClient, card_path: Path) -> None:
    text = opened(client)
    client.post(
        "/api/cards/7f3a2b/text",
        json={
            "mtime": text["mtime"],
            "front": text["front"],
            "back": "$Y$",
            "note": "check my manual edit",
        },
    )

    assert model.load(card_path).annotations() == ["@claude check my manual edit"]


def test_a_note_for_me_stays_mine(client: TestClient, card_path: Path) -> None:
    text = opened(client)
    client.post(
        "/api/cards/7f3a2b/text",
        json={"mtime": text["mtime"], "front": text["front"], "back": "$Y$",
              "note": "@me is this the right sign"},
    )

    assert model.load(card_path).annotations() == ["@me is this the right sign"]


def test_a_file_that_moved_since_the_editor_opened_is_not_overwritten(
    client: TestClient, card_path: Path
) -> None:
    text = opened(client)
    time.sleep(0.01)
    card_path.write_text(
        card_path.read_text(encoding="utf-8").replace("## back", "## back\n<!-- -->"),
        encoding="utf-8",
    )

    out = client.post(
        "/api/cards/7f3a2b/text",
        json={"mtime": text["mtime"], "front": "$A$", "back": "$B$"},
    )

    assert out.status_code == 409
    assert model.load(card_path).section("front") != "$A$"


@pytest.mark.parametrize("front,back", [("", "$Y$"), ("$X$", "  ")])
def test_an_empty_side_is_refused(
    client: TestClient, card_path: Path, front: str, back: str
) -> None:
    text = opened(client)
    out = client.post(
        "/api/cards/7f3a2b/text", json={"mtime": text["mtime"], "front": front, "back": back}
    )
    assert out.status_code == 400


def test_the_review_page_carries_the_editor_and_its_key(
    client: TestClient, card_path: Path
) -> None:
    page = client.get("/review").text

    assert "data-card-edit-dialog" in page
    for name in ("front", "back", "ask", "note"):
        assert f'name="{name}"' in page, name
    assert 'value="check my manual edit"' in page, "the default words"
    assert '"edit-card"' in page
