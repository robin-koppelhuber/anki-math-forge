"""The companion app is a view over files -- never a store (DESIGN.md §6)."""

from __future__ import annotations

import re
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
    from anki_forge.app import pipeline_counts

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
    from anki_forge.app import pipeline_counts

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
    from anki_forge import latex

    units.transcribe(units.units[0].id, r"X^{-\top}", latex.checker(()))
    body = client.get("/units?state=new").text
    assert "transcribed" in body


def test_units_view_has_a_section_filter_rail(config: Config, units: Ledger) -> None:
    """The filter rail is navigation, not decoration: 64 sections need it."""
    page = TestClient(create_app(config)).get("/units?state=all").text
    assert 'id="filter-rail"' in page
    assert "deck-column" in page


def test_section_tree_groups_by_chapter(config: Config) -> None:
    from anki_forge.app import section_tree
    from anki_forge.ledger import Ledger, Locator, Unit

    led = Ledger(config.sources_dir / "s" / "units.jsonl")
    led.units.extend(
        [
            Unit(id="s:eq:1", locator=Locator(section="2.1"), transcription="ok"),
            Unit(id="s:eq:2", locator=Locator(section="2.4"), state="skipped"),
            Unit(id="s:eq:3", locator=Locator(section="10.1")),
        ]
    )
    tree = {g["chapter"]: g for g in section_tree(led)}
    assert set(tree) == {"2", "10"}
    assert tree["2"]["total"] == 2
    assert tree["2"]["undecided"] == 1, "a skipped unit is decided"
    assert tree["10"]["sections"][0]["name"] == "10.1"


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

    They are addressed instructions, so the view says who each is for -- and
    Claude's are collapsed, because during triage they are provenance for
    card-writing rather than anything the human acts on.
    """
    led = Ledger.load(config.units_path("demo"))
    first = led.units[0].id
    led.annotate(first, "line 3 of 6, follows p67y189")
    led.annotate(first, "@me decide whether this is worth carding")
    led.save()

    page = TestClient(create_app(config)).get("/units?state=all").text
    assert "for you to decide" in page
    assert "note for Claude" in page or "notes for Claude" in page
    assert "decide whether this is worth carding" in page
    # Scope to the deck: the guide's diagram legitimately names `@claude`.
    deck = page.split('id="deck"')[1].split('id="empty-filter"')[0]
    assert "@claude" not in deck, "the prefix is redundant once the block is titled"


def test_note_prefix_stripping_survives_a_hand_edited_note() -> None:
    from anki_forge.app import _note_text

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
    from anki_forge.app import pipeline_counts

    counts = pipeline_counts(config)
    assert counts["queued"] == 1
    # the mini diagram renders it, and so does the filter rail's list
    assert f'>{counts["queued"]}</text>' in page
    assert f'queued<b>{counts["queued"]}</b>' in page


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

    static = _Path(__file__).resolve().parents[1] / "src" / "anki_forge" / "app" / "static"
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
        _Path(__file__).resolve().parents[1] / "src" / "anki_forge" / "app" / "static" / "app.css"
    ).read_text(encoding="utf-8")
    track = re.search(r"grid-template-columns: var\(--split, 1fr\) (\d+)px", css)
    assert track, "the split grid changed shape"
    width = int(track.group(1))
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

    static = _Path(__file__).resolve().parents[1] / "src" / "anki_forge" / "app" / "static"
    css = (static / "app.css").read_text(encoding="utf-8")
    floor = re.search(r"\.in-full \.fsm svg \{ min-width: (\d+)px", css)
    assert floor, "the diagram lost its minimum width"

    fsm = (
        _Path(__file__).resolve().parents[1]
        / "src" / "anki_forge" / "app" / "templates" / "_fsm.html"
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
        / "src" / "anki_forge" / "app" / "static" / "app.js"
    ).read_text(encoding="utf-8")
    assert '"anki-forge.rail-right"' in js
    assert '"anki-forge.rail-right-full"' in js
    assert "--rail-right-full" in js
