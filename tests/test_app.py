"""The companion app is a view over files -- never a store (DESIGN.md §6)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_forge import extract, model
from anki_forge.app import create_app
from anki_forge.config import Config
from anki_forge.ledger import Ledger


@pytest.fixture
def client(config: Config) -> TestClient:
    return TestClient(create_app(config))


@pytest.fixture
def units(config: Config) -> Ledger:
    extract.run(config, "demo")
    return Ledger.load(config.units_path("demo"))


@pytest.fixture
def pdf_units(pdf_source: Config) -> Config:
    """A PDF-backed source, so crops have geometry to render from."""
    extract.run(pdf_source, "book")
    return pdf_source


@pytest.fixture
def pdf_client(pdf_units: Config) -> TestClient:
    return TestClient(create_app(pdf_units))


def mtime(path: Path) -> str:
    return str(path.stat().st_mtime_ns)


# -- views -----------------------------------------------------------------


def test_review_shows_a_card(client: TestClient, card_path: Path) -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert "7f3a2b" in response.text
    assert r"\log \det X" in response.text


def test_review_without_cards_says_so(client: TestClient) -> None:
    assert "no cards yet" in client.get("/review").text


def test_units_view_shows_the_transcription(client: TestClient, units: Ledger) -> None:
    response = client.get("/units?state=new")
    assert response.status_code == 200
    assert "demo:1.1:2" in response.text
    assert "X^{-\\top}" in response.text


def test_units_view_filters_by_state(client: TestClient, config: Config, units: Ledger) -> None:
    units.set_state("demo:1.1:2", "queued")
    units.save()
    assert "demo:1.1:2" not in client.get("/units?state=new").text
    assert "demo:1.1:2" in client.get("/units?state=queued").text


# -- triage writes ---------------------------------------------------------


def test_queueing_a_unit_writes_the_ledger(
    client: TestClient, config: Config, units: Ledger
) -> None:
    path = config.units_path("demo")
    response = client.post(
        "/api/units/demo/demo:1.1:2/state", json={"state": "queued", "mtime": mtime(path)}
    )
    assert response.status_code == 200
    assert response.json()["unit"]["state"] == "queued"
    assert Ledger.load(path).get("demo:1.1:2").state == "queued"


def test_skipping_records_the_reason(client: TestClient, config: Config, units: Ledger) -> None:
    path = config.units_path("demo")
    client.post(
        "/api/units/demo/demo:1:1/state",
        json={"state": "skipped", "reason": "trivial", "mtime": mtime(path)},
    )
    unit = Ledger.load(path).get("demo:1:1")
    assert (unit.state, unit.reason) == ("skipped", "trivial")


def test_an_unknown_state_is_refused(client: TestClient, config: Config, units: Ledger) -> None:
    path = config.units_path("demo")
    response = client.post(
        "/api/units/demo/demo:1:1/state", json={"state": "lovely", "mtime": mtime(path)}
    )
    assert response.status_code == 400


def test_a_stale_ledger_write_is_refused(client: TestClient, config: Config, units: Ledger) -> None:
    path = config.units_path("demo")
    stale = mtime(path)
    time.sleep(0.01)
    ledger = Ledger.load(path)
    ledger.set_state("demo:1:1", "queued")
    ledger.save()  # an editor, or another tab, got there first

    response = client.post(
        "/api/units/demo/demo:1.1:2/state", json={"state": "queued", "mtime": stale}
    )
    assert response.status_code == 409
    assert response.json()["stale"] is True
    assert Ledger.load(path).get("demo:1.1:2").state == "new"


# -- review writes ---------------------------------------------------------


def test_approving_writes_status_and_hash(client: TestClient, card_path: Path) -> None:
    response = client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    assert response.status_code == 200
    card = model.load(card_path)
    assert card.status == "approved"
    assert card.hash_matches()


def test_rejecting_clears_the_hash(client: TestClient, card_path: Path) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    client.post("/api/cards/7f3a2b/reject", json={"mtime": mtime(card_path)})
    card = model.load(card_path)
    assert card.status == "rejected"
    assert card.stored_hash == ""


def test_a_stale_card_write_is_refused(client: TestClient, card_path: Path) -> None:
    stale = mtime(card_path)
    time.sleep(0.01)
    card_path.write_text(card_path.read_text(encoding="utf-8"), encoding="utf-8")

    response = client.post("/api/cards/7f3a2b/approve", json={"mtime": stale})
    assert response.status_code == 409
    assert model.load(card_path).status == "draft"


def test_an_unknown_card_is_a_404(client: TestClient, card_path: Path) -> None:
    assert client.post("/api/cards/ffffff/approve", json={}).status_code == 404


# -- annotations (DESIGN.md §6, §8) ----------------------------------------


def test_a_browser_annotation_is_byte_identical_to_a_hand_written_one(
    client: TestClient, card_path: Path, tmp_path: Path
) -> None:
    """The app is one entry point, not the entry point."""
    by_hand = model.load(card_path)
    by_hand.add_annotation("check the transpose against §2.4")
    expected = by_hand.render()

    client.post(
        "/api/cards/7f3a2b/annotate",
        json={"text": "check the transpose against §2.4", "mtime": mtime(card_path)},
    )
    assert card_path.read_text(encoding="utf-8") == expected


def test_an_annotation_does_not_unapprove_the_card(client: TestClient, card_path: Path) -> None:
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    client.post(
        "/api/cards/7f3a2b/annotate", json={"text": "one thought", "mtime": mtime(card_path)}
    )
    card = model.load(card_path)
    assert card.status == "approved"
    assert card.hash_matches(), "annotating is not editing (§8)"


def test_an_empty_annotation_is_refused(client: TestClient, card_path: Path) -> None:
    response = client.post(
        "/api/cards/7f3a2b/annotate", json={"text": "  ", "mtime": mtime(card_path)}
    )
    assert response.status_code == 400


def test_unit_annotations_land_in_the_ledger(
    client: TestClient, config: Config, units: Ledger
) -> None:
    path = config.units_path("demo")
    client.post(
        "/api/units/demo/demo:1:1/annotate",
        json={"text": "is this worth a card?", "mtime": mtime(path)},
    )
    assert Ledger.load(path).get("demo:1:1").notes == ["@claude is this worth a card?"]


# -- statelessness ---------------------------------------------------------


def test_the_app_re_reads_from_disk_on_every_request(client: TestClient, card_path: Path) -> None:
    assert "brand new prose" not in client.get("/review").text
    card = model.load(card_path)
    card.set_section("prose", "brand new prose")
    card.save()
    assert "brand new prose" in client.get("/review").text


def test_check_findings_are_shown_next_to_the_card(client: TestClient, card_path: Path) -> None:
    card = model.load(card_path)
    card.add_annotation("needs a proof")
    card.save()
    assert "annotation-open" in client.get("/review").text


# -- crops are rendered, not stored ----------------------------------------


def test_the_crop_route_renders_from_the_source_document(
    pdf_client: TestClient, pdf_units: Config
) -> None:
    unit = Ledger.load(pdf_units.units_path("book")).units[0]
    response = pdf_client.get(f"/crop/book/{unit.id}.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_the_units_view_points_at_the_crop_route(pdf_client: TestClient, pdf_units: Config) -> None:
    body = pdf_client.get("/units?source=book&state=new").text
    assert "/crop/book/" in body
    assert "/sources/" not in body, "nothing is served off disk any more"


def test_a_missing_source_document_is_explained_not_a_broken_image(
    pdf_client: TestClient, pdf_units: Config
) -> None:
    unit = Ledger.load(pdf_units.units_path("book")).units[0]
    pdf_units.source("book").pdf.unlink()
    response = pdf_client.get(f"/crop/book/{unit.id}.png")
    assert response.status_code == 409
    assert "rendered from it on demand" in response.text


def test_an_unknown_unit_crop_is_a_404(pdf_client: TestClient, pdf_units: Config) -> None:
    assert pdf_client.get("/crop/book/book:9:9.png").status_code == 404


def test_a_tex_unit_has_no_crop(client: TestClient, units: Ledger) -> None:
    """Units from LaTeX source carry no page geometry, and say so."""
    unit = units.units[0]
    assert not unit.has_crop
    assert client.get(f"/crop/demo/{unit.id}.png").status_code == 404
