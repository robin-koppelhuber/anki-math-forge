"""Where things are on screen, and why.

Two rails with one job each: the left one **acts** -- filters, and the commands
that run on what they leave -- and the right one **tells you what you are
looking at**. When something on one of them explains rather than changes, it is
on the wrong side.

The assertions here are against the markup and the stylesheet rather than
against a rendered browser. That is weaker, but each one pins a bug that
actually shipped, and every one of them was invisible to every other test in
this suite: a panel can cover the navigation, or scroll four screens out of
reach, while every view still returns 200.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from anki_math_forge.app import create_app
from anki_math_forge.config import Config

APP = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app"
CSS = (APP / "static" / "app.css").read_text(encoding="utf-8")
JS = (APP / "static" / "app.js").read_text(encoding="utf-8")
FILTERS = (APP / "templates" / "_filters.html").read_text(encoding="utf-8")
GUIDE = (APP / "templates" / "_guide.html").read_text(encoding="utf-8")
BASE = (APP / "templates" / "base.html").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    """The body of the first rule for `selector`, so a test can ask what it
    sets without depending on the order of the declarations in it."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"no rule for {selector!r}"
    return match.group(1)


# -- the header is not something to hide behind ----------------------------


def test_the_rails_start_below_the_header() -> None:
    """Both are `position: fixed` at a higher stacking order than an
    unpositioned header, so at `top: 0` the filter panel sat on top of the
    view links -- the one row that has to be reachable from anywhere."""
    for selector in (".filter-rail", ".guide"):
        assert "top: var(--header-h" in rule(selector), selector


def test_the_header_outranks_both_rails() -> None:
    header = rule("header.bar")
    assert "position: sticky" in header
    z = int(re.search(r"z-index:\s*(\d+)", header).group(1))
    for selector in (".filter-rail", ".guide"):
        assert z > int(re.search(r"z-index:\s*(\d+)", rule(selector)).group(1)), selector


def test_the_header_height_is_measured_rather_than_assumed() -> None:
    """It wraps: on a narrow window it is two rows tall, which is exactly when
    a hard-coded height is wrong."""
    assert "--header-h" in JS
    assert "offsetHeight" in JS


# -- the left rail folds, and can be got back ------------------------------


def test_the_rail_has_both_a_fold_and_a_way_back() -> None:
    """The button inside the panel slides away with it, which is precisely
    when an affordance is essential. The guide learnt this already."""
    assert 'id="filters-fold"' in FILTERS
    assert 'id="filters-tab"' in BASE
    assert '"filters-fold"' in JS and '"filters-tab"' in JS


def test_the_handle_shows_exactly_when_the_rail_is_away() -> None:
    """Written the positive way round: with no stored preference *neither*
    state class is set, and `:not(.filters-off)` then hid the handle on a
    narrow window, where the rail starts folded and it is the only way in."""
    assert ".rail-tab.left { display: none; }" in CSS
    assert "body.filters-off .rail-tab.left { display: block; }" in CSS
    assert "body:not(.filters-on) .rail-tab.left { display: block; }" in CSS


# -- one job per side -------------------------------------------------------


def test_what_to_run_is_pinned_to_the_bottom_of_the_rail() -> None:
    """With sixty-four sections above it, the one panel that says what to do
    next was four screens down the scroll.

    Pinning it means being a sibling of the scrolling column rather than the
    last thing inside it, so the test is that the column has closed by the
    time the panel starts: `<div>` depth back to zero.
    """
    start = FILTERS.index('<div class="filter-rail-scroll"')
    segment = FILTERS[start : FILTERS.index('class="rail-actions"')]
    assert segment.count("<div") >= 1
    assert segment.count("<div") == segment.count("</div>"), "still inside the scroll column"
    assert "flex: 1" in rule(".filter-rail-scroll"), "the column takes the slack"
    assert "flex: none" in rule(".rail-actions"), "the panel keeps its height"


def test_the_actions_panel_says_what_it_is() -> None:
    """"Next on this" read as "the next item", which is what `j` does."""
    assert "copy a command" in FILTERS
    assert "next on this" not in FILTERS


def test_the_meaning_of_a_mark_is_on_the_information_side() -> None:
    """The left rail lists marks as something to click, labelled by the colour
    you can see on the crop. What one *means* is a fact about the material, so
    it belongs on the right -- and the same sentence in both places is one of
    them not being read."""
    assert "what the marks mean" in GUIDE
    assert "scheme-meaning" in GUIDE
    assert "scheme-meaning" not in FILTERS


def test_the_resolved_settings_are_reachable_without_leaving_the_view() -> None:
    """Which layout a card resolved to decides what every derivative on it
    means, and there was no way to see it but to read Python."""
    assert "source-facts" in GUIDE
    assert "data-settings" in GUIDE, "and the full table opens over the view, not away from it"


# -- the picker -------------------------------------------------------------


def test_the_picker_opens_the_gallery_rather_than_a_dropdown() -> None:
    assert 'id="gallery"' in BASE
    assert "<select" not in BASE, "a dropdown cannot compare fifty papers"
    assert "openGallery" in JS


def test_switching_source_drops_the_filters_that_belonged_to_the_old_one() -> None:
    """A section number from one book means nothing in another, and carrying
    it over lands you on an empty deck that looks like the import failed."""
    match = re.search(r"function sourceHref[\s\S]*?\n}", JS)
    assert match and 'searchParams.delete' in match.group(0)
    assert '"section"' in match.group(0) and '"mark"' in match.group(0)


def test_a_modal_over_the_deck_owns_the_keyboard() -> None:
    """`s` typed into the gallery's search box would otherwise skip whatever
    unit was behind it."""
    block = JS[JS.index("function bindKeys") : JS.index("function bindKeys") + 600]
    assert "galleryIsOpen()" in block


def test_both_panels_are_on_every_view(pdf_source: Config) -> None:
    """The picker and the settings are questions you have mid-decision, so
    they open over whatever you were doing rather than navigating away."""
    client = TestClient(create_app(pdf_source))
    for url in ("/units", "/review"):
        body = client.get(url).text
        assert 'id="gallery"' in body, url
        assert 'id="source-pick"' in body, url
        assert 'id="settings"' in body, url
        assert 'id="config-open"' in body, url


def test_the_header_does_not_repeat_the_rail(pdf_source: Config) -> None:
    """`units` and `review` as bare words said where to go and nothing else.
    The rail carries both lanes as counts you can click -- `new 16`,
    `approved 108` -- which says where the work *is* as well."""
    body = TestClient(create_app(pdf_source)).get("/units").text
    header = body[body.index("<header") : body.index("</header>")]
    assert ">units<" not in header and ">review<" not in header


# -- nothing slides under the footer ---------------------------------------


def test_the_rails_stop_above_the_sticky_footer() -> None:
    """The footer stacks over the rails, so a rail running to `bottom: 0` had
    its last panel -- the commands -- sliding beneath the shortcut row and out
    of reach."""
    for selector in (".filter-rail", ".guide"):
        assert "bottom: var(--footer-h" in rule(selector), selector
    assert "--footer-h" in JS, "measured, like the header"


# -- the guide's two panes --------------------------------------------------


def test_the_diagram_is_above_the_legend_and_the_split_drags() -> None:
    """They answer different questions and neither ratio is right for everyone:
    triaging a marked-up paper, the colours are most of what you need."""
    panes = GUIDE.index('class="guide-panes"')
    assert GUIDE.index("_fsm_mini.html") > panes
    assert GUIDE.index("_fsm_mini.html") < GUIDE.index('class="rail-card scheme"')
    assert 'data-splitter="guide"' in GUIDE
    assert "grid-template-rows" in rule(".guide-panes")


def test_a_vertical_split_reads_the_other_axis() -> None:
    """One drag helper for both, because two hand-rolled loops is how they end
    up behaving differently -- and only the axis actually differs."""
    assert 'axis: "y"' in JS
    assert "event.clientY" in JS


def test_a_dialog_keeps_the_browser_s_hidden_rule() -> None:
    """Setting `display` on a `<dialog>` overrides the UA's own
    `dialog:not([open]) { display: none }`, and the settings panel was painted
    over every page at all times. Any display we set must be on `[open]`."""
    on_the_dialog = re.compile(r"^(\.(?:gallery|settings)(?:\[open\])?)\s*\{([^}]*)\}", re.M)
    seen = 0
    for selector, body in on_the_dialog.findall(CSS):
        seen += 1
        if "display:" in body:
            assert "[open]" in selector, f"{selector} hides nothing when closed"
    assert seen, "the dialog rules moved; this test is watching nothing"


# -- the settings panel and the three views ---------------------------------


def test_the_settings_panel_shows_the_general_keys_and_this_source(
    pdf_source: Config,
) -> None:
    """The other fifty sources are a different question -- which book to work
    on -- and the gallery answers that one. Listing them here buried the two
    groups you opened the panel for."""
    client = TestClient(create_app(pdf_source))
    groups = [g["where"] for g in client.get("/api/config?source=book").json()["groups"]]
    assert groups[0] == "source: book"
    assert "repo" in groups and "anki" in groups
    assert not [g for g in groups if g.startswith("source: ") and g != "source: book"]


def test_the_picture_cycles_three_ways_and_says_so() -> None:
    """A key nobody can see is a feature nobody finds, and "what does this
    passage actually say" is a question you have while looking at the
    picture."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    assert "data-pdf-view" in units
    assert '["crop", "page", "document"]' in view_js
    assert "p: cyclePdfView," in view_js


def test_the_context_chip_shows_every_size_and_whose_it_is() -> None:
    """Hiding it until the unit had already overridden the source meant never
    seeing what you were overriding. A row of bare numbers is five things to
    decode, so the one in force is written out and the rest are abbreviated."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    chip = units[units.index("data-context-chip") - 600 : units.index("data-context-chip") + 600]
    assert "hidden" not in chip
    assert "this unit" in chip and "source" in chip
    assert "data-context-step" in chip, "every size is its own button"


def test_the_chip_says_what_a_page_count_actually_means() -> None:
    """`3` is three pages *either side* -- seven in all. Saying "3 pages" and
    handing over seven makes a card writer think they have the whole story."""
    from anki_math_forge.app import context_label

    assert context_label(3, chosen=True) == "3 pages either side"
    assert context_label(3) == "3"
    assert "either side" in (APP / "templates" / "units.html").read_text(encoding="utf-8")


def test_the_unit_s_own_mark_is_set_apart_from_its_neighbours() -> None:
    """It was a 6% tint and a line of small caps, which at a glance is the same
    as every other row; the decision in front of you is about this one."""
    own = rule(".mark.own")
    assert "border-left" in own and "margin-bottom" in own
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    assert 'class="mark own"' in units, "outside the grouping entirely"
    assert "mark-group" in units, "and the rest gather by kind"


# -- the annotation panel ---------------------------------------------------


def test_the_brief_for_the_card_writer_is_not_collapsed() -> None:
    """It used to be a shut `<details>` labelled "not for this decision",
    which is a poor way to present the one instruction `/extract-cards` gets."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    pane = units[units.index("notes-pane") :]
    assert "the brief for whoever writes the card" in pane
    assert "<details" not in pane, "the brief is open, and so is what you parked"


def test_the_two_audiences_have_one_fixed_place() -> None:
    """They were scattered down the main column under everything else; the
    panel is the same place on every unit, and it splits from the marks."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    assert 'data-splitter="beside"' in units
    assert '"beside"' in JS or "beside:" in JS, "and the split is remembered"
    assert units.index("marks-list") < units.index("notes-pane"), "marks above, notes below"


def test_answering_is_offered_only_for_what_you_parked() -> None:
    """`yes`/`no` on the brief would be answering on the card writer's behalf.
    The brief gets a delete and nothing else."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    at = units.index("note-list mine")
    mine = units[at : units.index("note-empty", at)]
    claude = units[units.index('note-list"') : at]
    assert 'data-answer="yes"' in mine and 'data-answer="no"' in mine
    assert 'data-answer="yes"' not in claude


def test_a_dialog_closes_when_you_click_away() -> None:
    """A modal that only closes on its own close button makes you hunt for
    the one pixel that dismisses it, which is the opposite of what a panel
    over your work should ask."""
    assert "getBoundingClientRect" in JS
    assert "dialog.close()" in JS


def test_adding_a_source_is_answered_where_you_would_ask() -> None:
    """The gallery is where you go when the one you want is not on the list."""
    assert "gallery-add" in BASE
    assert "forge zotero --list" in BASE


# -- things that should not scale for ever ---------------------------------


def test_the_compact_diagram_stops_growing_with_the_rail() -> None:
    """It tracked the rail exactly, so dragging the rail to half the window
    scaled a 220-unit viewBox to 900px -- a state machine at poster size, with
    the legend it shares the rail with pushed off the bottom."""
    assert "max-width" in rule(".at-a-glance .fsm svg")


def test_an_approval_held_by_a_note_says_it_is_not_withdrawn() -> None:
    """Saying "draft" alone reads as work lost: the file still says approved,
    and resolving the note restores it."""
    review = (APP / "templates" / "review.html").read_text(encoding="utf-8")
    assert "card.demotion" in review
    assert "not withdrawn" in review
    assert "function paintHeld" in (APP / "static" / "review.js").read_text(encoding="utf-8")


def test_the_rail_speaks_about_the_work_not_to_the_reader() -> None:
    """"needs you" and "you decide" address the reader; the rail is labelling
    states of the work."""
    for banned in ("needs you", "you decide", "yours to decide", "your judgement"):
        assert banned not in FILTERS, f"{banned!r} is still in the rail"
