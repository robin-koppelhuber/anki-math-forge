"""The companion app is a view over files -- never a store (DESIGN.md §6)."""

from __future__ import annotations

import dataclasses
import re
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import extract, model
from anki_math_forge.app import create_app
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger


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
    body = client.get("/review").text
    assert "no cards here yet" in body
    assert "/extract-cards" in body, "say what would produce one"


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


# -- reading the files once per change, not once per click ------------------


def test_the_cached_loader_agrees_with_check_repo(config: Config, card_path: Path) -> None:
    """`_parse_deck` is `check_repo` with a per-file parse cache in front. The
    two must not disagree about what the deck contains, and the only guard
    against this drifting into a second loader is asking them."""
    from anki_math_forge import check
    from anki_math_forge.app import _parse_deck

    mine, my_findings = _parse_deck(config)
    theirs, their_findings = check.check_repo(config)

    assert [c.uid for c in mine] == [c.uid for c in theirs]
    assert [(f.code, f.level) for f in my_findings] == [
        (f.code, f.level) for f in their_findings
    ]


def test_a_write_is_seen_without_anyone_invalidating_anything(
    client: TestClient, config: Config, card_path: Path
) -> None:
    """The cache key is the files themselves, which is what keeps this a view
    over them (invariant 2). A write from anywhere -- this app, an editor, a
    subagent running `forge new` in another terminal -- moves an mtime and
    misses. Nothing is invalidated by hand, so nothing can forget to."""
    assert client.get("/api/counts").json()["pipeline"]["draft"] == 1

    # Not through the app: straight to disk, the way another process would.
    card = model.load(card_path)
    card.frontmatter["status"] = "approved"
    card.frontmatter["content_hash"] = card.content_hash()
    card.save()

    counts = client.get("/api/counts").json()["pipeline"]
    assert counts["approved"] == 1 and counts["draft"] == 0


def test_a_rendered_page_is_not_re_rendered_to_be_looked_at_twice(
    pdf_client: TestClient, pdf_units: Config
) -> None:
    """These were `Cache-Control: no-store`, which is the strongest thing you
    can say and says the wrong thing: a crop is derived, not secret. Forbidding
    the browser to keep it meant every crop/page/doc toggle re-rendered from
    the PDF -- measured at 103 ms for a full page, for a picture it had just
    been shown."""
    unit = next(iter(Ledger.load(pdf_units.units_path("book"))))
    url = f"/crop/book/{unit.id}.png"

    first = pdf_client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-cache", "store it, but ask first"
    etag = first.headers["etag"]

    again = pdf_client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert not again.content


def test_the_tag_moves_when_the_geometry_does(
    pdf_client: TestClient, pdf_units: Config
) -> None:
    """A stale picture must not be reachable. The tag covers the document's
    mtime and the ledger's, because that is where geometry and marks live."""
    path = pdf_units.units_path("book")
    unit = next(iter(Ledger.load(path)))
    url = f"/crop/book/{unit.id}.png"
    before = pdf_client.get(url).headers["etag"]

    with Ledger.edit(path) as ledger:
        target = ledger.get(unit.id)
        assert target is not None and target.locator.bbox is not None
        target.locator.bbox = [x + 3 for x in target.locator.bbox]

    assert pdf_client.get(url).headers["etag"] != before
    assert pdf_client.get(url, headers={"If-None-Match": before}).status_code == 200


# -- the two gradings, set from where you learn them ------------------------


def test_a_grading_can_be_set_from_the_review_view(
    client: TestClient, card_path: Path
) -> None:
    """You learn that a result is `common` rather than `core` by meeting it,
    which is to say during review. Until now the only way to record that was to
    open the file, which is why so many cards carry neither."""
    response = client.post(
        "/api/cards/7f3a2b/grade",
        json={"key": "frequency", "value": "common", "mtime": mtime(card_path)},
    )
    assert response.status_code == 200
    assert response.json()["card"]["frequency"] == "common"
    assert model.load(card_path).frequency == "common"


def test_a_grading_can_be_taken_off_again(client: TestClient, card_path: Path) -> None:
    """The cycle passes through unset, so a grading given by a mis-click comes
    off by carrying on clicking rather than by reaching for an editor."""
    client.post(
        "/api/cards/7f3a2b/grade",
        json={"key": "derivation", "value": "short", "mtime": mtime(card_path)},
    )
    client.post(
        "/api/cards/7f3a2b/grade",
        json={"key": "derivation", "value": "", "mtime": mtime(card_path)},
    )
    assert "derivation" not in model.load(card_path).frontmatter


def test_setting_a_grading_does_not_un_approve_the_card(
    client: TestClient, card_path: Path
) -> None:
    """`requires`'s argument, which CLAUDE.md states: approving a card is not
    approving its position in the queue. Both gradings decide *when* you meet
    it and neither changes a word a reviewer read."""
    client.post("/api/cards/7f3a2b/approve", json={"mtime": mtime(card_path)})
    client.post(
        "/api/cards/7f3a2b/grade",
        json={"key": "frequency", "value": "rare", "mtime": mtime(card_path)},
    )
    card = model.load(card_path)
    assert card.status == "approved"
    assert card.hash_matches()
    assert card.effective_status == "approved"


def test_a_value_outside_the_scale_is_refused(client: TestClient, card_path: Path) -> None:
    """`check` errors on an unrecognised grading because a typo would silently
    become its own `freq::` tag and split the deck. The endpoint must not be
    the way one gets in."""
    for body in (
        {"key": "frequency", "value": "often"},
        {"key": "tags", "value": "anything"},
    ):
        response = client.post(
            "/api/cards/7f3a2b/grade", json={**body, "mtime": mtime(card_path)}
        )
        assert response.status_code == 400, body


# -- looking things up ------------------------------------------------------


def test_a_unit_can_be_granted_web_access(
    client: TestClient, config: Config, units: Ledger
) -> None:
    path = config.units_path("demo")
    response = client.post("/api/units/demo/demo:1:1/web", json={"web": True, "mtime": mtime(path)})
    assert response.status_code == 200
    assert response.json()["unit"]["web"] is True
    assert response.json()["unit"]["web_own"] is True
    assert Ledger.load(path).get("demo:1:1").web is True


def test_clearing_the_grant_is_not_the_same_as_refusing_it(
    client: TestClient, config: Config, units: Ledger
) -> None:
    """`None` is the absence of a decision on this unit, and it is what lets a
    source-wide setting apply. Collapsing it into `false` would make a
    source-wide grant unrevokable and a source-wide refusal unliftable."""
    path = config.units_path("demo")
    client.post("/api/units/demo/demo:1:1/web", json={"web": False, "mtime": mtime(path)})
    assert Ledger.load(path).get("demo:1:1").web is False

    client.post("/api/units/demo/demo:1:1/web", json={"web": None, "mtime": mtime(path)})
    assert Ledger.load(path).get("demo:1:1").web is None


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


# -- the pipeline strip ----------------------------------------------------


def test_pipeline_counts_span_units_and_cards(
    config: Config, units: Ledger, card_path: Path
) -> None:
    """Units and cards are separate objects with separate gates; the strip is
    the only place that shape is visible, so it must count both."""
    from anki_math_forge.app import pipeline_counts

    units.set_state(units.units[0].id, "queued")
    units.set_state(units.units[1].id, "skipped", reason="trivial")
    units.save()

    counts = pipeline_counts(config)
    assert counts["queued"] == 1
    assert counts["skipped"] == 1
    assert counts["new"] == len(units.units) - 2
    assert counts["draft"] == 1, "the one card on disk is a draft"
    assert counts["approved"] == 0


def test_an_edited_approval_counts_as_draft_in_the_strip(
    config: Config, units: Ledger, card_path: Path
) -> None:
    from anki_math_forge.app import pipeline_counts

    card = model.load(card_path)
    card.approve()
    card.save()
    assert pipeline_counts(config)["approved"] == 1

    card = model.load(card_path)
    card.set_section("back", r"$X^{-1}$")
    card.save()
    counts = pipeline_counts(config)
    assert counts["approved"] == 0
    assert counts["draft"] == 1, "an edited approval is back in the review queue"


def test_the_filter_rail_carries_the_counts_on_both_views(
    client: TestClient, units: Ledger
) -> None:
    """One navigation surface, not a top strip plus a differently-shaped list.

    The strip this replaced also had to be kept in step with the rail by
    hand, and had drifted: it showed no annotation counts and rendered a
    pseudo-element into its own label.
    """
    for url in ("/units", "/review"):
        page = client.get(url).text
        assert 'id="filter-rail"' in page, url
        assert 'class="filter-list flow"' in page, url
        assert "queued" in page and "approved" in page, url
    assert 'class="pipeline"' not in client.get("/units").text


def test_the_section_dropdown_says_what_is_transcribed(
    client: TestClient, config: Config, units: Ledger
) -> None:
    """So you can pick a section that is ready, rather than discovering it."""
    from anki_math_forge import latex

    units.transcribe(units.units[0].id, r"X^{-\top}", latex.checker(()))
    body = client.get("/units?state=new").text
    assert "transcribed" in body


def test_units_view_has_a_section_filter_rail(config: Config, units: Ledger) -> None:
    """The filter rail is navigation, not decoration: 64 sections need it."""
    page = TestClient(create_app(config)).get("/units?state=all").text
    assert 'id="filter-rail"' in page
    assert "deck-column" in page


def demo_units() -> list[Any]:
    from anki_math_forge.ledger import Locator, Unit

    return [
        Unit(id="s:eq:1", locator=Locator(section="2.1"), transcription="ok"),
        Unit(id="s:eq:2", locator=Locator(section="2.4"), state="skipped"),
        Unit(id="s:eq:3", locator=Locator(section="10.1")),
    ]


def rows_for(shown: set[str]) -> dict[str, Any]:
    from anki_math_forge.app import UNIT_STATES, section_rows

    tree = section_rows(
        demo_units(),
        shown,
        lambda u: u.locator.section,
        lambda u: u.state,
        lambda u: u.id,
        UNIT_STATES,
    )
    return {g["chapter"]: g for g in tree}


def test_section_rows_group_by_chapter(config: Config) -> None:
    tree = rows_for({"s:eq:1", "s:eq:2", "s:eq:3"})
    assert set(tree) == {"2", "10"}
    assert tree["2"]["total"] == 2
    assert tree["10"]["sections"][0]["name"] == "10.1"


def test_the_section_count_is_what_clicking_would_show(config: Config) -> None:
    """It used to count one hard-coded state, so once nothing was `new` every
    row read `0/x` for ever. It has to move with the other filters."""
    assert rows_for({"s:eq:1", "s:eq:2", "s:eq:3"})["2"]["matching"] == 2
    assert rows_for({"s:eq:2"})["2"]["matching"] == 1, "the filter narrowed it"
    assert rows_for(set())["2"]["matching"] == 0
    assert rows_for(set())["2"]["total"] == 2, "the total does not move"


def test_section_rows_carry_the_whole_state_split(config: Config) -> None:
    """One ratio cannot say where a section stands across four states."""
    tree = rows_for(set())
    by_name = {r["name"]: r for g in tree.values() for r in g["sections"]}
    assert by_name["2.1"]["states"] == {"new": 1, "queued": 0, "carded": 0, "skipped": 0}
    assert by_name["2.4"]["states"]["skipped"] == 1
    # ...and as bar widths, so it can be read without hovering
    assert by_name["2.4"]["bar"] == [{"state": "skipped", "n": 1, "pct": 100.0}]
    assert sum(part["pct"] for part in by_name["2.1"]["bar"]) == 100.0


def test_absent_suggestion_is_explained_not_silent(config: Config, units: Ledger) -> None:
    """No suggestion is a result, not a gap.

    A numbered equation is off limits to the classifier by contract, so most
    units will never carry a suggestion. Showing nothing made that look like a
    broken feature.
    """
    page = TestClient(create_app(config)).get("/units?state=new").text
    assert "no suggestion" in page


def test_notes_are_titled_and_split_by_audience(config: Config, units: Ledger) -> None:
    """Untitled `@claude ...` lines under a crop read as stray text.

    They are addressed instructions, so the view says who each is for. The
    `@claude` half used to be a shut `<details>` labelled "not for this
    decision", which is a poor way to present the one thing you can say to
    whoever writes the card -- it is the brief, and it is open.
    """
    led = Ledger.load(config.units_path("demo"))
    first = led.units[0].id
    led.annotate(first, "line 3 of 6, follows p67y189")
    led.annotate(first, "@me decide whether this is worth carding")
    led.save()

    page = TestClient(create_app(config)).get("/units?state=all").text
    deck = page.split('id="deck"')[1].split('id="empty-filter"')[0]
    assert "the brief for whoever writes the card" in deck
    assert "parked for a decision" in deck
    assert "decide whether this is worth carding" in deck
    assert "line 3 of 6" in deck
    pane = deck.split("notes-pane")[1]
    # It folds -- either section can run long -- but it must not *start*
    # folded: shut by default is the half of the old `<details>` that actually
    # hid the one instruction `/extract-cards` gets.
    assert pane.count('<details class="note-section" open>') == 2


def test_an_answered_note_keeps_the_question(config: Config, units: Ledger) -> None:
    """Deleting the line throws away both halves, and the question is most of
    what made the decision worth recording. Unaddressed, so it is a record
    rather than new work."""
    led = Ledger.load(config.units_path("demo"))
    first = led.units[0].id
    led.annotate(first, "@me same as 2.4?")
    led.save()

    client = TestClient(create_app(config))
    client.post(f"/api/units/demo/{first}/answer", json={"index": 0, "answer": "no"})

    notes = Ledger.load(config.units_path("demo")).get(first).notes
    assert notes == ["same as 2.4? — no"]


def test_an_empty_answer_just_deletes(config: Config, units: Ledger) -> None:
    """Right when the note was a reminder rather than a question."""
    led = Ledger.load(config.units_path("demo"))
    first = led.units[0].id
    led.annotate(first, "@me look at this again")
    led.save()

    client = TestClient(create_app(config))
    client.post(f"/api/units/demo/{first}/answer", json={"index": 0, "answer": ""})
    assert Ledger.load(config.units_path("demo")).get(first).notes == []


def test_note_prefix_stripping_survives_a_hand_edited_note() -> None:
    from anki_math_forge.app import _note_text

    assert _note_text("@claude fix it") == "fix it"
    assert _note_text("@me mine") == "mine"
    assert _note_text("no prefix at all") == "no prefix at all"


def test_an_action_reports_what_it_replaced(config: Config, units: Ledger) -> None:
    """Undo needs the prior state from the server, not the browser's guess."""
    led = Ledger.load(config.units_path("demo"))
    unit = led.units[0]
    led.suggest(unit.id, "skipped", "no-relation", "no relation symbol", by="classify")
    led.save()

    client = TestClient(create_app(config))
    path = config.units_path("demo")
    result = client.post(
        f"/api/units/demo/{unit.id}/state",
        json={"state": "queued", "mtime": str(path.stat().st_mtime_ns)},
    ).json()
    assert result["unit"]["state"] == "queued"
    assert result["before"]["state"] == "new"
    assert result["before"]["suggestion"]["reason"] == "no-relation"


def test_undo_restores_the_suggestion_the_action_cleared(
    config: Config, units: Ledger
) -> None:
    """`set_state` clears a suggestion, so undo must put it back.

    Restoring only the state would silently discard the proposal -- an undo
    that loses work of its own is worse than no undo.
    """
    led = Ledger.load(config.units_path("demo"))
    unit = led.units[0]
    led.suggest(unit.id, "skipped", "no-relation", "no relation symbol", by="classify")
    led.save()

    client = TestClient(create_app(config))
    path = config.units_path("demo")
    acted = client.post(
        f"/api/units/demo/{unit.id}/state",
        json={"state": "queued", "mtime": str(path.stat().st_mtime_ns)},
    ).json()
    assert Ledger.load(path).get(unit.id).suggestion is None

    undone = client.post(
        f"/api/units/demo/{unit.id}/restore",
        json={"snapshot": acted["before"], "mtime": str(path.stat().st_mtime_ns)},
    ).json()
    assert undone["unit"]["state"] == "new"

    back = Ledger.load(path).get(unit.id)
    assert back.state == "new"
    assert back.suggestion is not None
    assert back.suggestion.reason == "no-relation"
    assert back.suggestion.by == "classify"


def test_undo_after_accepting_a_suggestion(config: Config, units: Ledger) -> None:
    led = Ledger.load(config.units_path("demo"))
    unit = led.units[0]
    led.suggest(unit.id, "skipped", "front-matter", "before the first equation", by="classify")
    led.save()

    client = TestClient(create_app(config))
    path = config.units_path("demo")
    acted = client.post(
        f"/api/units/demo/{unit.id}/accept",
        json={"mtime": str(path.stat().st_mtime_ns)},
    ).json()
    assert acted["unit"]["state"] == "skipped"

    client.post(
        f"/api/units/demo/{unit.id}/restore",
        json={"snapshot": acted["before"], "mtime": str(path.stat().st_mtime_ns)},
    )
    back = Ledger.load(path).get(unit.id)
    assert back.state == "new"
    assert back.suggestion is not None, "accepting consumed the suggestion; undo restores it"


def test_undo_restores_the_content_hash_not_just_the_status(
    config: Config, tmp_path: Path
) -> None:
    """Approving stamps `content_hash`; rejecting drops it.

    Restoring the status alone would leave an approved card with no hash --
    a state it was never in, and one that reads as "edited since approval".
    """
    card = model.Card(
        frontmatter={"uid": "abc123", "type": "identity", "status": "draft"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    path = config.cards_dir / "abc123-x.md"
    card.save(path)
    client = TestClient(create_app(config))

    approved = client.post(
        "/api/cards/abc123/approve", json={"mtime": str(path.stat().st_mtime_ns)}
    ).json()
    assert approved["card"]["status"] == "approved"
    assert approved["before"]["status"] == "draft"
    assert model.load(path).frontmatter.get("content_hash")

    client.post(
        "/api/cards/abc123/restore",
        json={"snapshot": approved["before"], "mtime": str(path.stat().st_mtime_ns)},
    )
    back = model.load(path)
    assert back.status == "draft"
    assert "content_hash" not in back.frontmatter


def test_the_guide_offers_both_depths(client: TestClient, units: Ledger) -> None:
    """Counts at normal width, the whole explanation when expanded.

    Both are always in the markup; CSS chooses between them, so cycling size
    costs no request and the counts cannot go stale against the filters.
    """
    for url in ("/units", "/review"):
        page = client.get(url).text
        assert 'id="guide"' in page, url
        assert 'class="at-a-glance"' in page, url
        assert 'class="in-full"' in page, url


def test_the_compact_diagram_uses_the_same_counts_as_the_filters(
    client: TestClient, config: Config, units: Ledger
) -> None:
    """Two places showing a number is two places to disagree, unless it is
    literally the same number."""
    led = Ledger.load(config.units_path("demo"))
    led.set_state(led.units[0].id, "queued")
    led.save()

    page = client.get("/units").text
    from anki_math_forge.app import pipeline_counts

    counts = pipeline_counts(config)
    assert counts["queued"] == 1
    n = counts["queued"]
    # The rail and the diagram carry the same number under different tags:
    # the rail is always the whole source, the diagram follows `counts_scope`,
    # so one repaint must not be able to overwrite the other.
    assert re.search(rf'data-count="queued"[^>]*>{n}<', page), "the rail lost the count"
    assert re.search(rf'data-fsm-count="queued"[^>]*>{n}<', page), "the diagram lost it"
    assert page.count('data-count="queued"') == 1, "one owner per tag"

    # ...and with a scope of `filtered` they are allowed to differ, because
    # they are then answering different questions.
    scoped = client.get("/units?state=queued&counts_scope=filtered&section=1.1").text
    assert re.search(r'data-count="new"[^>]*>[1-9]', scoped), "the rail still counts everything"
    assert re.search(r'data-fsm-count="new"[^>]*>0<', scoped), "the diagram counts the filter"


def test_the_guide_has_a_handle_that_survives_being_hidden(
    client: TestClient, units: Ledger
) -> None:
    """The button inside the panel slides away with it.

    Hiding the guide then left no way to bring it back, which is the one
    state where an affordance is essential.
    """
    page = client.get("/units").text
    assert 'id="guide-tab"' in page
    assert 'id="guide-cycle"' in page


def test_the_crop_and_transcription_can_be_resized(client: TestClient, units: Ledger) -> None:
    page = client.get("/units").text
    assert "data-splitter" in page, "the split between crop and transcription is draggable"


def test_the_guide_size_classes_match_the_stylesheet(client: TestClient, units: Ledger) -> None:
    """The size names are a contract between app.js and app.css.

    Renaming the panel once left the script emitting `guide-normal` while the
    stylesheet still expected `guide-counts` -- the guide simply stopped
    responding, with nothing to show for it.
    """
    from pathlib import Path as _Path

    static = _Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
    js = (static / "app.js").read_text(encoding="utf-8")
    css = (static / "app.css").read_text(encoding="utf-8")

    sizes = re.search(r"const GUIDE_SIZES = \[([^\]]*)\]", js)
    assert sizes, "GUIDE_SIZES moved or was renamed"
    names = re.findall(r'"([a-z]+)"', sizes.group(1))
    assert names, "no size names parsed"
    for name in names:
        assert f"body.guide-{name}" in css, f"app.js emits guide-{name}, app.css never styles it"


def test_both_rails_can_be_dragged(client: TestClient, units: Ledger) -> None:
    page = client.get("/units").text
    assert 'data-rail="left"' in page
    assert 'data-rail="right"' in page


def test_the_splitter_track_is_wide_enough_to_grab(client: TestClient) -> None:
    """It was 6px of track carrying a 0.6rem margin, so its box collapsed.

    The handle was in the markup and impossible to hit -- the kind of fault
    that reads as "the feature does not exist".
    """
    from pathlib import Path as _Path

    css = (
        _Path(__file__).resolve().parents[1]
        / "src"
        / "anki_math_forge"
        / "app"
        / "static"
        / "app.css"
    ).read_text(encoding="utf-8")
    tracks = re.findall(r"grid-template-columns: var\(--split-[\w-]+[^)]*\) (\d+)px", css)
    assert len(tracks) >= 2, "expected a draggable split in both the units and review views"
    for width in (int(w) for w in tracks):
        assert width >= 12, f"a {width}px handle is too thin to grab"

    rule = re.search(r"\.splitter \{([^}]*)\}", css)
    assert rule and "margin: 0;" in rule.group(1), (
        "a horizontal margin inside the track collapses the handle again"
    )


def test_the_full_diagram_keeps_a_legible_minimum_width() -> None:
    """It has a 960-unit viewBox and 10.5px labels.

    Squeezed into a 15rem rail those land near 7px -- present, not readable.
    So it stops shrinking and the panel scrolls; drag the rail wider and the
    scrolling stops.
    """
    from pathlib import Path as _Path

    static = _Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
    css = (static / "app.css").read_text(encoding="utf-8")
    floor = re.search(r"\.in-full \.fsm svg \{ min-width: (\d+)px", css)
    assert floor, "the diagram lost its minimum width"

    fsm = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "templates" / "_fsm.html"
    ).read_text(encoding="utf-8")
    view = re.search(r'viewBox="0 0 (\d+) (\d+)"', fsm)
    assert view, "the diagram lost its viewBox"
    width, smallest = int(view.group(1)), 10.5
    scale = int(floor.group(1)) / width
    assert smallest * scale >= 6.5, (
        f"at {floor.group(1)}px the smallest label renders at {smallest * scale:.1f}px"
    )


def test_the_guide_remembers_its_two_widths_separately() -> None:
    """One number for both sizes meant resizing one silently resized the other."""
    from pathlib import Path as _Path

    js = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "static" / "app.js"
    ).read_text(encoding="utf-8")
    assert '"anki-forge.rail-right"' in js
    assert '"anki-forge.rail-right-full"' in js
    assert "--rail-right-full" in js


def test_katex_is_served_locally_when_installed(config: Config, units: Ledger) -> None:
    """The CDN default fails silently: `renderMathInElement` is undefined,
    nothing throws, and every card shows raw `$...$` as though its LaTeX were
    wrong. `npm install katex` is already required for `check`, so use it."""
    dist = config.root / "node_modules" / "katex" / "dist" / "contrib"
    dist.mkdir(parents=True)
    (dist.parent / "katex.min.js").write_text("//", encoding="utf-8")
    (dist / "auto-render.min.js").write_text("//", encoding="utf-8")

    auto = dataclasses.replace(config, katex_base="")  # "" means decide at startup
    client = TestClient(create_app(auto))
    page = client.get("/units").text
    assert "/katex/katex.min.js" in page
    assert client.get("/katex/katex.min.js").status_code == 200
    assert client.get("/katex/contrib/auto-render.min.js").status_code == 200


def test_the_cdn_is_the_fallback_when_katex_is_not_installed(
    config: Config, units: Ledger
) -> None:
    auto = dataclasses.replace(config, katex_base="")
    page = TestClient(create_app(auto)).get("/units").text
    assert "cdn.jsdelivr.net" in page, "no local copy, so fall back rather than break"


def test_a_configured_katex_base_still_wins(config: Config, units: Ledger) -> None:
    page = TestClient(
        create_app(dataclasses.replace(config, katex_base="https://example.test/katex"))
    ).get("/units").text
    assert "https://example.test/katex/katex.min.js" in page


def test_the_template_never_renders_an_empty_katex_base(config: Config, units: Ledger) -> None:
    """Templates reload per request; Python does not reload until a restart.

    That mismatch shipped a broken page: the new template asked for a global
    the old process had never set, so every asset URL came out as
    `/katex.min.css` and KaTeX silently failed to load. The template carries
    its own fallbacks so it renders something usable against either.
    """
    import re
    from pathlib import Path as _Path

    base = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "templates" / "base.html"
    ).read_text(encoding="utf-8")
    assert 'default("", true)' in base, "the global must have a fallback"
    assert "cdn.jsdelivr.net" in base, "and a last-resort URL"

    page = TestClient(create_app(config)).get("/units").text
    for ref in re.findall(r'(?:href|src)="([^"]*katex[^"]*)"', page):
        assert not ref.startswith("/katex.min"), f"empty base rendered: {ref}"
        assert ref.startswith(("http", "/katex/", "/static/")), ref


def test_hidden_beats_every_display_rule() -> None:
    """`item.hidden = true` is how the deck shows one thing at a time.

    A class rule that sets `display` outranks the browser's own
    `[hidden] { display: none }`. `.card.item { display: grid }` did exactly
    that, so every card was on screen at once and only the first had been
    through KaTeX -- which read as "only the first card renders".
    """
    import re
    from pathlib import Path as _Path

    css = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "static" / "app.css"
    ).read_text(encoding="utf-8")
    # Comments quote the rule they explain; searching them finds the wrong one.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rule = re.search(r"\[hidden\]\s*\{([^}]*)\}", css)
    assert rule, "nothing makes [hidden] authoritative"
    assert "display: none" in rule.group(1)
    assert "!important" in rule.group(1), "without it any class rule still wins"


def test_an_approved_card_can_be_sent_back_to_draft(config: Config) -> None:
    """Changing your mind is not an edit.

    Editing an approved card un-approves it as a side effect, but reaching for
    the editor to make a token change would be a worse way to say so.
    """
    card = model.Card(
        frontmatter={"uid": "abc123", "type": "identity", "status": "draft"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    path = config.cards_dir / "abc123-x.md"
    card.save(path)
    client = TestClient(create_app(config))

    client.post("/api/cards/abc123/approve", json={"mtime": str(path.stat().st_mtime_ns)})
    assert model.load(path).status == "approved"
    assert model.load(path).frontmatter.get("content_hash")

    result = client.post(
        "/api/cards/abc123/unapprove", json={"mtime": str(path.stat().st_mtime_ns)}
    ).json()
    assert result["card"]["status"] == "draft"
    back = model.load(path)
    assert back.status == "draft"
    assert "content_hash" not in back.frontmatter, "an unapproved card must not sync"


def test_both_middle_splits_are_draggable(config: Config, units: Ledger) -> None:
    """The units view splits crop from transcription, the review view splits
    the card from its metadata. Both ratios are per-viewer, not per-stylesheet."""
    model.Card(
        frontmatter={"uid": "abc123", "type": "identity", "status": "draft"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    ).save(config.cards_dir / "abc123-x.md")

    client = TestClient(create_app(config))
    assert 'data-splitter="units"' in client.get("/units").text
    assert 'data-splitter="card"' in client.get("/review").text


def test_each_split_remembers_its_own_width() -> None:
    """One stored number for both meant dragging one silently resized the other."""
    from pathlib import Path as _Path

    js = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "static" / "app.js"
    ).read_text(encoding="utf-8")
    assert '"anki-forge.split.units"' in js
    assert '"anki-forge.split.card"' in js


def test_every_bound_key_is_in_the_footer() -> None:
    """The footer is the only place the keys are advertised.

    `u` (send an approved card back to draft) was bound and unlisted, so it
    existed only for whoever read the source. A keymap and a legend maintained
    by hand drift; this notices.
    """
    import re
    from pathlib import Path as _Path

    app = _Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app"
    for view in ("units", "review"):
        js = (app / "static" / f"{view}.js").read_text(encoding="utf-8")
        block = js[js.index("bindKeys({") :]
        bound = {k for k in re.findall(r'^\s{2}"?([A-Za-z?])"?:', block, re.M)}

        html = (app / "templates" / f"{view}.html").read_text(encoding="utf-8")
        start = html.index("{% block keys %}")
        keys = html[start : html.index("{% endblock %}", start)]
        listed = {k for entry in re.findall(r"<b>([^<]+)</b>", keys) for k in entry.split("/")}

        assert bound <= listed, f"{view}: bound but not in the footer: {sorted(bound - listed)}"


def test_every_mutation_returns_fresh_counts(config: Config, units: Ledger) -> None:
    """The filter rail is what you navigate by; a stale count misdirects.

    Both the rail and the guide's diagram render `pipeline`, so a decision
    that changed a state used to leave every number on screen wrong until a
    page load.
    """
    led = Ledger.load(config.units_path("demo"))
    unit = led.units[0]
    client = TestClient(create_app(config))
    path = config.units_path("demo")

    before = client.get("/api/counts").json()["pipeline"]
    result = client.post(
        f"/api/units/demo/{unit.id}/state",
        json={"state": "queued", "mtime": str(path.stat().st_mtime_ns)},
    ).json()

    assert "pipeline" in result, "a mutation must hand back the counts it changed"
    assert result["pipeline"]["queued"] == before["queued"] + 1
    assert result["pipeline"]["new"] == before["new"] - 1


def test_the_counts_have_somewhere_to_be_painted() -> None:
    """`data-count` is the contract between the templates and app.js."""
    import re
    from pathlib import Path as _Path

    app = _Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app"
    js = (app / "static" / "app.js").read_text(encoding="utf-8")
    assert "[data-count]" in js, "nothing repaints the rail"
    assert "[data-fsm-count]" in js, "nothing repaints the diagram"

    states = {"new", "queued", "carded", "skipped", "draft", "approved"}
    rail = (app / "templates" / "_filters.html").read_text(encoding="utf-8")
    diagram = (app / "templates" / "_fsm_mini.html").read_text(encoding="utf-8")
    assert states <= set(re.findall(r'data-count="(\w+)"', rail))
    assert states <= set(re.findall(r'data-fsm-count="(\w+)"', diagram))


def test_undo_survives_a_page_load() -> None:
    """Clicking a rail link is a navigation.

    An in-page stack died on that click -- so a mis-pressed key became
    permanent the moment you changed filter, which is when you would go
    looking for undo.
    """
    from pathlib import Path as _Path

    js = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_math_forge" / "app" / "static" / "app.js"
    ).read_text(encoding="utf-8")
    assert "sessionStorage" in js
    assert "anki-forge.undo" in js
    for view in ("units", "review"):
        src = (
            _Path(__file__).resolve().parents[1]
            / "src" / "anki_math_forge" / "app" / "static" / f"{view}.js"
        ).read_text(encoding="utf-8")
        assert "loadUndo()" in src, f"{view} does not restore the stack"
        assert "saveUndo(undoStack)" in src, f"{view} does not persist it"


def test_the_review_view_matches_the_anki_prompt(config: Config) -> None:
    """What you approve should be what you review.

    `conditions` belongs above the answer rule, as it does in the note type;
    otherwise the web view and Anki disagree about what the question was.
    """
    import re

    model.Card(
        frontmatter={"uid": "abc123", "type": "identity", "status": "draft"},
        sections=[
            model.Section("front", "$a$"),
            model.Section("back", "$b$"),
            model.Section("conditions", "$X$ square."),
        ],
    ).save(config.cards_dir / "abc123-x.md")

    page = TestClient(create_app(config)).get("/review").text
    article = re.search(r'<article class="card item".*?</article>', page, re.S).group(0)
    found = re.findall(r'sec sec-(\w+)|(<hr class="answer-rule">)', article)
    order = [m or "RULE" for m, _ in found]
    assert order.index("conditions") < order.index("RULE"), "conditions must precede the answer"
    assert order.index("RULE") < order.index("back")


def test_code_fences_render_as_code_not_as_backticks() -> None:
    """A `## verify` block is Python between triple backticks.

    Rendered as text it showed the fences literally and KaTeX tried to read
    the maths-like parts of the code. `<pre>` is right here for exactly the
    reason it was wrong for notes: KaTeX skips it.
    """
    from anki_math_forge.app import render_body

    out = str(render_body("before\n```python\nlhs = a < b\n```\nafter"))
    assert "```" not in out
    assert "<pre class='code'>" in out
    assert "a &lt; b" in out, "code must still be escaped"
    assert out.startswith("before")


def test_the_filter_returns_markup_not_a_string(config: Config) -> None:
    """A plain str would be escaped again by Jinja and shown as tags."""
    from markupsafe import Markup

    from anki_math_forge.app import render_body

    assert isinstance(render_body("```\nx = 1\n```"), Markup)

    model.Card(
        frontmatter={"uid": "abc123", "type": "identity", "status": "draft"},
        sections=[
            model.Section("front", "$a$"),
            model.Section("back", "$b$"),
            model.Section("verify", "```python\nlhs = 1\nrhs = 1\n```"),
        ],
    ).save(config.cards_dir / "abc123-x.md")
    page = TestClient(create_app(config)).get("/review").text
    assert "&lt;pre" not in page
    assert "<pre class='code'>" in page


def test_the_guide_lists_every_bound_key() -> None:
    """The guide is where a key is explained, the footer only names it.

    Six keys were bound and absent from the guide -- including `?`, which
    opens the guide. Two hand-maintained lists against one keymap drift.
    """
    import re
    from pathlib import Path as _Path

    app = _Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app"
    guide = (app / "templates" / "_guide.html").read_text(encoding="utf-8")
    units_part, review_part = guide.split("{% else %}", 1)

    for view, part in (("units", units_part), ("review", review_part)):
        js = (app / "static" / f"{view}.js").read_text(encoding="utf-8")
        block = js[js.index("bindKeys({") :]
        bound = set(re.findall(r'^\s{2}"?([A-Za-z?])"?:', block, re.M))
        listed: set[str] = set()
        for dt in re.findall(r"<dt>(.*?)</dt>", part, re.S):
            listed |= set(re.findall(r"<b>([A-Za-z?])</b>", dt))
        assert bound <= listed, f"{view}: bound but unexplained: {sorted(bound - listed)}"


# -- the source picker -----------------------------------------------------


def write_card(config: Config, uid: str, unit: str) -> Path:
    """A minimal valid card belonging to whichever source `unit` names."""
    path = config.cards_dir / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"uid: {uid}\n"
        "type: identity\n"
        "status: draft\n"
        'source: "somewhere"\n'
        f'unit: "{unit}"\n'
        "tags: []\n"
        "verify: false\n"
        "---\n\n"
        "## front\n$X$\n\n## back\n$Y$\n",
        encoding="utf-8",
    )
    return path


def test_source_picker_is_on_both_views(client: TestClient, card_path: Path) -> None:
    """It renders for a single source too. Its absence was what made the units
    view look like it was showing every book at once."""
    for url in ("/units", "/review"):
        body = client.get(url).text
        assert 'id="source-pick"' in body, url
        assert "demo" in body, url
        assert 'id="gallery"' in body, url


def test_the_gallery_lists_every_configured_source(pdf_source: Config) -> None:
    """The picker is a gallery now, filled from the API: a dropdown answers
    "which one am I on" and nothing else, and the question with a shelf of
    papers is which to work on next."""
    rows = TestClient(create_app(pdf_source)).get("/api/sources").json()
    assert [row["name"] for row in rows["sources"]] == ["demo", "book"]


def test_the_gallery_counts_both_halves_of_the_pipeline(pdf_source: Config) -> None:
    """Which source to work on next is a comparison, and a name cannot make
    it. Units and cards both, because a source can be fully triaged and have
    no cards written, which looks identical to an untouched one by unit count."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "book:1.1:1")
    rows = TestClient(create_app(pdf_source)).get("/api/sources").json()
    by_name = {row["name"]: row for row in rows["sources"]}
    assert by_name["demo"]["counts"]["draft"] == 1
    assert by_name["book"]["counts"]["draft"] == 1
    assert rows["cards"] == 2
    assert rows["totals"]["draft"] == 2


def test_the_gallery_says_where_each_source_came_from(pdf_source: Config) -> None:
    """A paper imported from Zotero and a PDF sitting in the repo looked
    identical in every view, and they are not: it decides which passes make
    sense and where to go when a document is missing."""
    rows = TestClient(create_app(pdf_source)).get("/api/sources").json()
    by_name = {row["name"]: row for row in rows["sources"]}
    assert by_name["book"]["origin"] == "pdf"
    assert "pdf" in rows["origins"]


def test_review_scopes_to_the_selected_source(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "book:1.1:1")
    client = TestClient(create_app(pdf_source))

    only_demo = client.get("/review?source=demo").text
    assert "aaa111" in only_demo
    assert "bbb222" not in only_demo

    only_book = client.get("/review?source=book").text
    assert "bbb222" in only_book
    assert "aaa111" not in only_book


def test_a_card_naming_no_unit_shows_under_every_source(pdf_source: Config) -> None:
    """Misfiled, not homeless. A view that hides it is worse than one that
    shows it twice, because nothing else would ever surface it."""
    write_card(pdf_source, "ccc333", "")
    client = TestClient(create_app(pdf_source))
    assert "ccc333" in client.get("/review?source=demo").text
    assert "ccc333" in client.get("/review?source=book").text


def test_unknown_source_falls_back_rather_than_emptying(
    client: TestClient, card_path: Path
) -> None:
    """A stale link should land somewhere real."""
    response = client.get("/review?source=no-such-book")
    assert response.status_code == 200
    assert "7f3a2b" in response.text


def test_pipeline_counts_scope_to_one_source(pdf_source: Config) -> None:
    from anki_math_forge.app import pipeline_counts

    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "book:1.1:1")
    assert pipeline_counts(pdf_source)["draft"] == 2
    assert pipeline_counts(pdf_source, "demo")["draft"] == 1
    assert pipeline_counts(pdf_source, "book")["draft"] == 1


def test_crossing_between_the_two_lanes_carries_the_source(pdf_source: Config) -> None:
    """Switching view must not silently switch book.

    The header used to carry `units` / `review` links for this. It no longer
    does -- the rail's own state rows cross between the lanes, and they say
    where the work *is* as well as where to go -- so the guarantee moved to
    them.
    """
    write_card(pdf_source, "bbb222", "book:1.1:1")
    body = TestClient(create_app(pdf_source)).get("/review?source=book").text
    assert "/units?source=book" in body, "the unit counts lead back to the same book"
    assert "/review?source=book" in body


def test_rail_card_links_carry_the_source(pdf_source: Config) -> None:
    write_card(pdf_source, "bbb222", "book:1.1:1")
    body = TestClient(create_app(pdf_source)).get("/review?source=book").text
    # `&` is escaped in an href now that the URL comes through a variable.
    assert "/review?source=book&amp;status=draft" in body


def test_source_name_comes_off_the_unit_id() -> None:
    card = model.Card(
        frontmatter={"uid": "a1b2c3", "unit": ["matrix-cookbook:3.1:148", "other:1:1"]},
        sections=[],
    )
    assert card.source_name == "matrix-cookbook"
    assert model.Card(frontmatter={"uid": "a1b2c3"}, sections=[]).source_name == ""


def test_api_counts_take_a_source(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "book:1.1:1")
    client = TestClient(create_app(pdf_source))
    assert client.get("/api/counts?source=demo").json()["pipeline"]["draft"] == 1
    assert client.get("/api/counts?source=book").json()["pipeline"]["draft"] == 1


def test_the_default_source_is_the_first_in_the_toml(pdf_source: Config) -> None:
    """Not alphabetical: which book you land on is a decision you make by
    editing the config, not a consequence of its name."""
    from anki_math_forge.app import resolve_source, source_names

    assert source_names(pdf_source) == ["demo", "book"]
    assert resolve_source(pdf_source, "") == "demo"


# -- annotations: filtering, and the only way to finish with one ----------


def annotate(config: Config, uid: str, unit: str, note: str) -> None:
    path = write_card(config, uid, unit)
    card = model.load(path)
    card.add_annotation(note)
    card.save()


def test_review_filters_by_annotation_audience(pdf_source: Config) -> None:
    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision for the human")
    annotate(pdf_source, "bbb222", "demo:2.4:61", "work for the agent")
    write_card(pdf_source, "ccc333", "demo:2.4:61")
    client = TestClient(create_app(pdf_source))

    mine = client.get("/review?status=draft&annotated=me").text
    assert "aaa111" in mine and "bbb222" not in mine and "ccc333" not in mine

    theirs = client.get("/review?status=draft&annotated=claude").text
    assert "bbb222" in theirs and "aaa111" not in theirs

    both = client.get("/review?status=draft&annotated=any").text
    assert "aaa111" in both and "bbb222" in both and "ccc333" not in both


def test_annotating_an_approved_card_returns_it_to_the_draft_pile(
    pdf_source: Config,
) -> None:
    """`sync` has always refused an annotated card whatever its status, so it
    was never going to Anki -- but it sat in the approved pile looking like it
    was, and `approved 108` counted work that could not move.

    The file is untouched: `status: approved` stays, so resolving the note
    restores the approval with no re-review and no re-stamped hash. That is the
    whole reason `## notes` sits outside `content_hash`.
    """
    annotate(pdf_source, "bbb222", "demo:2.4:61", "@me on an approved card")
    path = next(pdf_source.cards_dir.rglob("bbb222-*.md"))
    card = model.load(path)
    card.approve()
    card.save()

    held = model.load(path)
    assert held.status == "approved", "the file still says so"
    assert held.effective_status == "draft"
    assert held.demotion == "annotated"

    client = TestClient(create_app(pdf_source))
    assert "bbb222" not in client.get("/review?status=approved").text
    assert "bbb222" in client.get("/review?status=draft").text


def test_a_resolved_note_restores_the_approval_by_itself(pdf_source: Config) -> None:
    """No re-review, no re-stamped hash: the approval was never withdrawn."""
    annotate(pdf_source, "bbb222", "demo:2.4:61", "@me a question")
    path = next(pdf_source.cards_dir.rglob("bbb222-*.md"))
    card = model.load(path)
    card.approve()
    card.save()
    assert model.load(path).effective_status == "draft"

    TestClient(create_app(pdf_source)).post("/api/cards/bbb222/resolve", json={"index": 0})
    assert model.load(path).effective_status == "approved"


def test_the_annotation_filter_keeps_the_stage_filter(pdf_source: Config) -> None:
    """"@me on drafts" is one click from "draft", not a view of its own."""
    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me on a draft")
    write_card(pdf_source, "ccc333", "demo:2.4:61")
    client = TestClient(create_app(pdf_source))

    drafts = client.get("/review?status=draft&annotated=me").text
    assert "aaa111" in drafts and "ccc333" not in drafts


def test_counts_split_annotations_by_audience(pdf_source: Config) -> None:
    from anki_math_forge.app import pipeline_counts

    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision")
    annotate(pdf_source, "bbb222", "demo:2.4:61", "work for the agent")
    counts = pipeline_counts(pdf_source)
    assert counts["annotated"] == 2
    assert counts["annotated_me"] == 1
    assert counts["annotated_claude"] == 1


def test_resolve_route_removes_one_annotation(pdf_source: Config) -> None:
    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision")
    path = next(pdf_source.cards_dir.rglob("aaa111-*.md"))
    client = TestClient(create_app(pdf_source))

    response = client.post(
        "/api/cards/aaa111/resolve", json={"mtime": mtime(path), "index": 0}
    )

    assert response.status_code == 200
    assert model.load(path).annotations() == []
    assert response.json()["pipeline"]["annotated_me"] == 0


def test_resolve_refuses_a_stale_write(pdf_source: Config) -> None:
    """The app is a view over files, so a note added in an editor meanwhile
    must not be clobbered by a resolve aimed at the old list."""
    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision")
    client = TestClient(create_app(pdf_source))

    response = client.post("/api/cards/aaa111/resolve", json={"mtime": "1", "index": 0})

    assert response.status_code == 409


def test_units_filter_by_annotation_audience(pdf_client: TestClient, pdf_units: Config) -> None:
    from anki_math_forge.ledger import Ledger

    path = pdf_units.units_path("book")
    with Ledger.edit(path) as led:
        first = led.units[0].id
        led.annotate(first, "@me a decision on a unit")

    mine = pdf_client.get("/units?source=book&state=all&annotated=me").text
    assert first in mine
    theirs = pdf_client.get("/units?source=book&state=all&annotated=claude").text
    assert first not in theirs


def test_a_filter_matching_nothing_is_not_an_empty_repo(pdf_source: Config) -> None:
    """`empty.html` says "no cards here yet" and tells you to go extract some.
    With cards on disk and a filter that matches none of them, that is a lie,
    and the way out (drop the filter) is not the thing it suggests."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    client = TestClient(create_app(pdf_source))

    for url in (
        "/review?status=rejected",
        "/review?status=draft&annotated=claude",
        "/review?source=book",
    ):
        body = client.get(url).text
        assert "no cards here yet" not in body, url
        assert "nothing here with this filter" in body, url


def test_empty_html_still_shows_when_the_repo_has_no_cards(client: TestClient) -> None:
    body = client.get("/review").text
    assert "no cards here yet" in body
    assert "/extract-cards" in body


# -- the filter rail: every toggle has a way back out ---------------------


def action_rows(body: str) -> dict[str, tuple[bool, str]]:
    """The `action required` rows, as {label: (active, href)}."""
    block = re.search(r"<summary>action required</summary>(.*?)</details>", body, re.S).group(1)
    rows = {}
    for li in re.findall(r"<li>(.*?)</li>", block, re.S):
        href = re.search(r'href="([^"]+)"', li).group(1).replace("&amp;", "&")
        label = re.sub(r"<[^>]+>", "", li).replace("&times;", "").split()[0]
        rows[label] = ('class="on"' in li, href)
    return rows


def test_an_active_filter_links_to_clearing_itself(client: TestClient, units: Ledger) -> None:
    """It was one-way: once on, the only way off was editing the URL."""
    rows = action_rows(client.get("/units?state=all&suggested=1").text)
    active, href = rows["suggested"]
    assert active
    assert "suggested=1" not in href, "an active filter must link to its own removal"

    assert not action_rows(client.get("/units?state=all").text)["suggested"][0]


def test_clearing_one_filter_keeps_the_others(client: TestClient, units: Ledger) -> None:
    """Turning `@me` off should not quietly take `suggested` with it."""
    rows = action_rows(client.get("/units?state=all&suggested=1&annotated=me").text)

    assert rows["@me"][0] and rows["suggested"][0]
    assert "annotated=me" not in rows["@me"][1]
    assert "suggested=1" in rows["@me"][1], "the other filter survives"
    assert "annotated=me" in rows["suggested"][1], "and the same in reverse"


def test_me_and_claude_replace_each_other(client: TestClient, units: Ledger) -> None:
    """`annotated` holds one value, so they are alternatives, not a pair."""
    rows = action_rows(client.get("/units?state=all&annotated=me").text)
    assert rows["@claude"][1].endswith("annotated=claude")
    assert "annotated=me" not in rows["@claude"][1]


def test_the_annotation_count_matches_the_view_it_links_to(pdf_source: Config) -> None:
    """The repo-wide total read "@me 42" on the review page and then showed no
    cards, because all 42 were on units."""
    from anki_math_forge.ledger import Ledger as L

    write_card(pdf_source, "aaa111", "demo:2.4:61")
    card = model.load(next(pdf_source.cards_dir.rglob("aaa111-*.md")))
    card.add_annotation("@me a decision on a card")
    card.save()
    extract.run(pdf_source, "book")
    with L.edit(pdf_source.units_path("book")) as led:
        annotated_units = [u.id for u in led.units[:2]]
        for unit_id in annotated_units:
            led.annotate(unit_id, "@me a decision on a unit")

    client = TestClient(create_app(pdf_source))
    assert action_rows(client.get("/review?status=draft").text)["@me"][1]
    card_count = re.search(
        r'data-count="annotated_me_card">(\d+)<',
        client.get("/review?status=draft").text,
    )
    unit_count = re.search(
        r'data-count="annotated_me_unit">(\d+)<',
        client.get("/units?source=book&state=all").text,
    )
    assert card_count.group(1) == "1"
    assert unit_count.group(1) == str(len(annotated_units))


# -- sections on both views, and filters that compose ---------------------


def test_card_section_comes_off_the_unit_id() -> None:
    card = model.Card(frontmatter={"uid": "a1b2c3", "unit": "matrix-cookbook:2.3:66"}, sections=[])
    assert card.section_name == "2.3"
    assert model.Card(frontmatter={"uid": "a1b2c3"}, sections=[]).section_name == ""


def test_review_filters_by_section(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "demo:1.1:2")
    client = TestClient(create_app(pdf_source))

    only = client.get("/review?status=draft&section=2.4").text
    assert "aaa111" in only and "bbb222" not in only


def test_filter_url_changes_one_key_and_keeps_the_rest() -> None:
    """Every rail link used to assemble its own query string, and each forgot
    a different parameter."""
    from anki_math_forge.app import filter_url

    current = {"source": "mc", "status": "draft", "section": "2.4", "annotated": "me"}
    assert filter_url("/review", current, status="approved") == (
        "/review?source=mc&status=approved&section=2.4&annotated=me"
    )
    assert filter_url("/review", current, annotated=None) == (
        "/review?source=mc&status=draft&section=2.4"
    )
    assert filter_url("/review", {}) == "/review"


def test_picking_a_section_keeps_the_annotation_filter(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    card = model.load(next(pdf_source.cards_dir.rglob("aaa111-*.md")))
    card.add_annotation("@me a decision")
    card.save()
    body = TestClient(create_app(pdf_source)).get("/review?status=draft&annotated=me").text

    section_links = re.findall(r'href="(/review\?[^"]*section=2\.4[^"]*)"', body)
    assert section_links, "the review rail should offer sections"
    assert all("annotated=me" in href for href in section_links)


def test_the_section_row_clears_itself(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    body = TestClient(create_app(pdf_source)).get("/review?status=draft&section=2.4").text
    # From the sections heading to the end of the rail. Not to a fixed number
    # of `</details>`: the chapter level only exists where a source has one,
    # and this fixture's sections are each alone in theirs -- which is the
    # flat shape a paper gets.
    block = body[body.index("<summary>sections</summary>") : body.index("</aside>")]
    active = re.search(r'<a class="on"[^>]*href="([^"]+)"', block)
    assert active and "section=2.4" not in active.group(1).replace("&amp;", "&")


def test_a_chapter_level_appears_only_where_there_is_one(config: Config) -> None:
    """`2.4` -> chapter `2` is the Cookbook's numbering, and splitting on `.`
    gave a paper imported from Zotero -- whose sections are attachment titles
    like `1 - introduction`, or simply `PDF` -- one chapter per section, each
    folded into a `<details>` of one. That is an extra click on every row and,
    for a single-attachment paper, one shut fold labelled `PDF`."""
    from anki_math_forge.app import section_rows

    def tree(*names: str) -> list[dict[str, Any]]:
        return section_rows(
            list(names), set(names), lambda s: s, lambda s: "new", lambda s: s, ("new",)
        )

    cookbook = tree("2.1", "2.4", "3.1")
    assert [g["chapter"] for g in cookbook] == ["2", "3"], "a real chapter groups"

    paper = tree("1 - introduction", "2- tail_bounds")
    assert [g["chapter"] for g in paper] == [""], "one section each: no level"
    assert len(paper[0]["sections"]) == 2

    one_file = tree("PDF")
    assert [g["chapter"] for g in one_file] == [""]
    assert [r["name"] for r in one_file[0]["sections"]] == ["PDF"]


# -- what the compact diagram counts --------------------------------------


def test_counts_scope_narrows_the_diagram_only(pdf_source: Config) -> None:
    """The rail's rows are links, so a row that says 3 and then shows 40 is
    worse than one that says 40. The diagram answers a different question."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "demo:1.1:2")
    client = TestClient(create_app(pdf_source))

    whole = client.get("/review?status=draft&section=2.4").text
    scoped = client.get("/review?status=draft&section=2.4&counts_scope=filtered").text

    assert re.search(r'data-count="draft"[^>]*>2<', whole), "rail counts every card"
    assert re.search(r'data-fsm-count="draft"[^>]*>2<', whole), "diagram defaults to all"
    assert re.search(r'data-count="draft"[^>]*>2<', scoped), "the rail does not narrow"
    assert re.search(r'data-fsm-count="draft"[^>]*>1<', scoped), "the diagram does"


def test_api_counts_answers_for_the_active_filters(pdf_source: Config) -> None:
    """A mutation response cannot know the query, so filtered mode asks."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    write_card(pdf_source, "bbb222", "demo:1.1:2")
    client = TestClient(create_app(pdf_source))

    plain = client.get("/api/counts").json()
    assert plain["pipeline"]["draft"] == 2
    assert plain["fsm"] == plain["pipeline"], "no scope means no narrowing"

    scoped = client.get("/api/counts?counts_scope=filtered&section=2.4").json()
    assert scoped["pipeline"]["draft"] == 2
    assert scoped["fsm"]["draft"] == 1


def test_the_scope_toggle_offers_both_ways(pdf_source: Config) -> None:
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    client = TestClient(create_app(pdf_source))
    for url, active in (("/review?status=draft", "all"),
                        ("/review?status=draft&counts_scope=filtered", "filtered")):
        block = re.search(r'<p class="counts-scope">(.*?)</p>', client.get(url).text, re.S).group(1)
        on = re.search(r'<a class="on"[^>]*>(\w+)</a>', block)
        assert on and on.group(1) == active, url


def test_filtering_to_cards_with_no_annotation(pdf_source: Config) -> None:
    """Without this an annotated draft sat in the review queue for ever, and
    the only way to stop meeting it was to reject it -- which claims the card
    should never exist and is not what anyone meant."""
    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision")
    write_card(pdf_source, "bbb222", "demo:2.4:61")
    client = TestClient(create_app(pdf_source))

    clear = client.get("/review?status=draft&annotated=none").text
    assert "bbb222" in clear and "aaa111" not in clear

    rows = action_rows(client.get("/review?status=draft").text)
    assert rows["no"][1].endswith("annotated=none"), "offered when it is off"
    assert not action_rows(clear)["no"][1].endswith("annotated=none"), "clears when on"


def test_the_no_notes_count_is_the_complement(pdf_source: Config) -> None:
    from anki_math_forge.app import pipeline_counts

    annotate(pdf_source, "aaa111", "demo:2.4:61", "@me a decision")
    write_card(pdf_source, "bbb222", "demo:2.4:61")
    counts = pipeline_counts(pdf_source)

    assert counts["unannotated_card"] == 1
    assert counts["annotated_me_card"] == 1


def test_enter_in_the_prompt_means_ok_not_cancel(client: TestClient, card_path: Path) -> None:
    """In a `method="dialog"` form, Enter activates the *first submit button*
    in tree order. With `cancel` first, every annotation typed and submitted
    with Enter was discarded in silence: the dialog returned "cancel", `ask()`
    resolved null, and the caller returned without a word. Four cards lost
    their notes that way."""
    body = client.get("/review").text
    actions = re.search(r'<div class="prompt-actions">(.*?)</div>', body, re.S).group(1)
    buttons = re.findall(r"<button([^>]*)>", actions)

    submits = [b for b in buttons if 'type="button"' not in b]
    assert submits, "the dialog needs a submit button or Enter does nothing"
    assert 'value="ok"' in submits[0], "the first submit button is what Enter presses"

    js = (Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
          / "app.js").read_text(encoding="utf-8")
    assert "prompt-cancel" in js, "a non-submit cancel has to be closed by hand"


def test_annotating_stays_on_the_card() -> None:
    """It was treated as a decision -- "said, done, move on" -- which is wrong
    twice over: a card often wants two notes, and the one just written scrolled
    off before it could be read back."""
    app = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
    js = (app / "review.js").read_text(encoding="utf-8")
    body = js[js.index("async function annotate") : js.index("async function openEditor")]
    assert "deck.nextPending()" not in body and "deck.settle" not in body


def test_a_new_note_appears_without_a_reload() -> None:
    """The panel was rendered once by the server and never rebuilt, so writing
    a note looked like nothing had happened."""
    app = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
    review = (app / "review.js").read_text(encoding="utf-8")
    assert "function paintAnnotations" in review
    assert "paintAnnotations(item, card)" in review, "on every refresh, not only on add"
    units = (app / "units.js").read_text(encoding="utf-8")
    assert "repaintNotes(item, result.unit)" in units


def place_of(body: str, uid: str) -> str:
    block = re.search(rf'data-uid="{uid}".*?<div class="place">(.*?)</div>', body, re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", block.group(1)).split()) if block else ""


def test_a_card_shows_where_it_sits_and_what_put_it_there(pdf_source: Config) -> None:
    """`frequency`, `derivation` and `requires` all decide when Anki
    introduces a card, and none of them was visible while reviewing."""
    path = write_card(pdf_source, "aaa111", "demo:2.4:61")
    card = model.load(path)
    card.frontmatter["frequency"] = "core"
    card.frontmatter["derivation"] = "short"
    card.save()

    place = place_of(TestClient(create_app(pdf_source)).get("/review?status=draft").text, "aaa111")
    assert "order 1/1" in place
    assert "core" in place and "short" in place


def test_the_card_names_what_needs_it_not_only_what_it_needs(pdf_source: Config) -> None:
    """The reverse edge is the half no file can give you: a card records what
    it requires, never what requires it."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    dependent = model.load(write_card(pdf_source, "bbb222", "demo:2.4:61"))
    dependent.frontmatter["requires"] = ["aaa111"]
    dependent.save()

    body = TestClient(create_app(pdf_source)).get("/review?status=draft").text
    assert "needs aaa111" in place_of(body, "bbb222")
    assert "needed by bbb222" in place_of(body, "aaa111")


def test_an_ungraded_card_says_so(pdf_source: Config) -> None:
    """It sorts last as unjudged, which is worth seeing rather than guessing."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    place = place_of(TestClient(create_app(pdf_source)).get("/review?status=draft").text, "aaa111")
    assert "no frequency" in place and "no derivation" in place


def test_the_guide_states_the_sort_key(client: TestClient, card_path: Path) -> None:
    body = client.get("/review").text
    key = re.search(r'<p class="order-key".*?</p>', body, re.S)
    assert key, "the rule that decides what you meet next should be stated somewhere"
    text = " ".join(re.sub(r"<[^>]+>", " ", key.group(0)).split())
    for part in ("frequency", "derivation", "source order", "requires"):
        assert part in text


def test_a_dependency_is_a_link_you_can_follow(pdf_source: Config) -> None:
    """Both directions. The href drops the filters that could hide the target,
    so following one always lands somewhere rather than on an empty deck."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    dependent = model.load(write_card(pdf_source, "bbb222", "demo:2.4:61"))
    dependent.frontmatter["requires"] = ["aaa111"]
    dependent.save()

    body = TestClient(create_app(pdf_source)).get("/review?status=draft&annotated=none").text
    links = dict(re.findall(r'<a class="goto" data-goto="(\w+)" href="([^"]+)"', body))

    assert set(links) == {"aaa111", "bbb222"}, "needs and needed-by are both links"
    for href in links.values():
        target = href.replace("&amp;", "&")
        assert "status=all" in target, "a status filter must not hide the target"
        assert "annotated=" not in target, "nor an annotation filter"
        assert target.endswith("#" + target.split("#")[-1])


def test_following_a_dependency_stays_on_the_page_when_it_can() -> None:
    """The target is usually already in the deck, hidden behind the card you
    are looking at, so jumping to it should not cost a page load. The hash
    carries it either way, which is what makes the back button work."""
    js = (Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
          / "review.js").read_text(encoding="utf-8")
    assert "data-goto" in js
    assert "preventDefault" in js, "no reload when the card is already here"
    assert "hashchange" in js, "and a full navigation lands via the hash"


def test_a_dependency_links_to_its_own_source_not_the_current_one(pdf_source: Config) -> None:
    """`check` validates `requires` against the whole repo, not one book, so a
    cross-source dependency is legal. Linking it with the current source would
    land on a card that is not there, and the hash lookup would find nothing
    and say nothing."""
    write_card(pdf_source, "aaa111", "book:1.1:1")
    dependent = model.load(write_card(pdf_source, "bbb222", "demo:2.4:61"))
    dependent.frontmatter["requires"] = ["aaa111"]
    dependent.save()

    body = TestClient(create_app(pdf_source)).get("/review?status=draft&source=demo").text
    href = dict(re.findall(r'data-goto="(\w+)" href="([^"]+)"', body))["aaa111"]

    assert "source=book" in href.replace("&amp;", "&"), "the target's source, not the page's"


def test_a_requires_naming_no_card_is_not_offered_as_a_link(pdf_source: Config) -> None:
    """`check` errors on it. The UI should not also invite a click."""
    card = model.load(write_card(pdf_source, "aaa111", "demo:2.4:61"))
    card.frontmatter["requires"] = ["nosuch"]
    card.save()

    body = TestClient(create_app(pdf_source)).get("/review?status=draft").text
    assert 'data-goto="nosuch"' not in body
    assert '<code class="dead"' in body


def test_the_order_badge_is_labelled(pdf_source: Config) -> None:
    """The header already shows a bare `N / M` for the filtered list. Two
    unlabelled counters on one screen compete, and they count different
    things: this one does not move when you filter."""
    write_card(pdf_source, "aaa111", "demo:2.4:61")
    body = TestClient(create_app(pdf_source)).get("/review?status=draft").text
    assert re.search(r'<span class="pos"[^>]*>order \d+/\d+</span>', body)


def test_a_hash_that_names_a_hidden_card_says_so() -> None:
    js = (Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
          / "review.js").read_text(encoding="utf-8")
    body = js[js.index("function followHash"):js.index("window.addEventListener")]
    assert "toast" in body, "a miss must not be silent"


def test_the_dependency_list_survives_a_stale_server(config: Config, card_path: Path) -> None:
    """Templates are re-read per request; Python is only loaded at startup. A
    template that assumed the new payload rendered every dependency as a blank
    while the running server still returned plain strings. `base.html` states
    this rule; this pins it for the block that broke it."""
    from fastapi.templating import Jinja2Templates

    from anki_math_forge.app import TEMPLATES

    env = Jinja2Templates(directory=str(TEMPLATES)).env
    source = (TEMPLATES / "review.html").read_text(encoding="utf-8")
    block = re.search(r"needs \{% for dep in card\.requires %\}(.*?)\{% endfor %\}", source, re.S)
    assert block, "the dependency loop moved"

    # The fragment uses `loop.last`, so give it a loop.
    template = env.from_string("{% for dep in deps %}" + block.group(1) + "{% endfor %}")

    stale = template.render(deps=["5658ad"])
    assert "5658ad" in stale, "an old payload of plain strings still shows the uid"

    fresh = template.render(deps=[{"uid": "5658ad", "known": True, "href": "/review#5658ad"}])
    assert 'data-goto="5658ad"' in fresh and "/review#5658ad" in fresh
