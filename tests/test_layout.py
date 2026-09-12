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
    assert "sl-meaning" in GUIDE
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
    assert GUIDE.index("_fsm_mini.html") < GUIDE.index("scheme scheme-whole")
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


def test_clicking_the_picture_does_not_change_the_view() -> None:
    """It did, and it was not a design. `item.dataset.pdfView` wrote the same
    attribute the buttons are found by, so `closest("[data-pdf-view]")` matched
    the whole unit: leaning in to read a highlight jumped you to the scrolling
    document. The state and the control must not share an attribute name.
    """
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    assert "item.dataset.pdfView" not in view_js, "the state cannot use the control's name"
    assert "item.dataset.pdfMode" in view_js
    assert 'closest("button[data-pdf-view]")' in view_js, "scoped to the button"


def test_each_view_of_the_picture_is_reachable_in_one_click() -> None:
    """A cycling label is a poor pointer control: reaching the third state
    means pressing the thing twice and watching what happens, and there is
    nowhere to read what the third state even is. `p` still walks them."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    assert "('crop', 'crop'), ('page', 'page'), ('document', 'doc')" in units, "one button each"
    assert 'data-pdf-view="{{ view }}"' in units, "and each one names the view it shows"
    assert "data-pdf-view-label" not in units, "no cycling label left"
    # The three names live in two places -- the template's buttons and the
    # keyboard cycle -- and they have to agree, or `p` walks to a state no
    # button can reach.
    assert '["crop", "page", "document"]' in view_js


def test_a_neighbours_filter_is_not_the_rails_filter() -> None:
    """Two filters over marks, pulling in opposite directions. The rail decides
    which *units* you meet; this one decides how much of the page around the
    one in front of you is worth reading. Tying them would mean narrowing the
    queue to green claims also hid every purple term beside them -- which is
    exactly the context the decision needs."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    assert "data-mark-filter" in units and "data-mark-colour" in units
    assert 'data-mark-colour="*"' in units and 'data-mark-colour=""' in units, "all and none"
    # Client-side and per viewer: it changes nothing on disk and travels with
    # no query parameter, so it cannot reach the rail's filter by accident.
    assert "filter_url" not in units[units.index("data-mark-filter") :]
    assert "anki-forge.marks." in view_js, "remembered per source"


def test_a_group_filtered_empty_says_so_rather_than_vanishing() -> None:
    """An empty `<details>` reads as "nothing of this kind here", which is a
    different and false claim."""
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    assert "all-filtered" in view_js
    assert "all filtered out" in view_js
    assert "opacity" in rule(".mark-group.all-filtered"), "dimmed, not removed"


def test_the_permission_to_look_things_up_is_visible_on_the_unit() -> None:
    """Off on every unit in the repo by default, so it has to be quiet when it
    says nothing -- and loud when it does. It is the one setting here that
    changes what may reach a card from somewhere other than the page."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    chip = units[units.index("data-web-chip") - 500 : units.index("data-web-chip") + 500]
    assert 'data-web-set="1"' in chip and 'data-web-set="0"' in chip
    assert "this unit" in chip and "source" in chip, "whose answer it is"
    assert "--warn" in rule(".badge.web-chip.own"), "not the accent the others use"


def test_each_stage_says_what_it_decides() -> None:
    """A unit is a decision; a card is the content (CLAUDE.md invariant 9).
    Both views now say which of the two they are, at the top of the guide,
    because everything below only makes sense in that light -- and because
    depth applied at triage buys nothing and costs the throughput the stage
    exists for."""
    units_part, review_part = GUIDE.split("{% else %}", 1)
    for part in (units_part, review_part):
        assert "what this stage decides" in part
    assert "worth a card at all" in units_part
    assert "do not have to\n        be able to transcribe" in units_part.replace("<b>", "")
    assert "already settled" in review_part, "the card stage does not re-triage"


def test_queueing_can_record_what_the_card_is_about() -> None:
    """The second half of what triage decides, and it only had a key by
    accident: a separate `n`, on a unit that had usually scrolled past. Which
    is why most units reach `/extract-cards` carrying nothing but a picture.

    Symmetric with `s`/`S` -- bare key does not stop to ask, shifted one
    records the sentence that makes the decision useful later."""
    view_js = (APP / "static" / "units.js").read_text(encoding="utf-8")
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    assert "Q: queueWithABrief," in view_js
    assert "<b>Q</b> queue + brief" in units, "and the footer names it"
    # The state change first: a failure writing the note leaves a queued unit
    # with no brief, which `n` fixes -- nothing fixes a decision that never
    # landed.
    body = view_js[view_js.index("async function queueWithABrief") :][:700]
    assert body.index('setState("queued")') < body.index("noteOn(item, text)")


def test_a_marked_unit_is_not_asked_for_a_transcription() -> None:
    """You do not have to be able to transcribe a unit to triage it. A marked
    passage carries the sentence it covers and nothing will ever read a picture
    of it, so the pane is absent rather than empty -- and the badge says what
    the unit *is* instead of accusing it of missing something it cannot have."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    assert "{% set reads = unit.tex or not unit.marks %}" in units
    assert "marked while reading" in units


def test_the_control_stays_on_the_picture_in_every_view() -> None:
    """It did not: the document view set `.crop` to `position: static`, which
    also stops it being a containing block, so the absolutely-positioned
    crop/page/doc control escaped to the nearest positioned ancestor and left
    the viewport. You could reach the document view and then had no way back.

    And `.crop` must not carry a `position: relative` of its own -- an
    identical selector later in the file wins over the `sticky` above, which
    quietly un-stuck the crop that triage reads the marks against."""
    assert "position: relative" in rule(".unit.whole-document .crop")
    assert "position: static" not in rule(".unit.whole-document .crop")
    # Anchored at the line start, so the nested and media-query forms do not
    # count. There must be exactly one top-level `.crop` rule: a second one
    # wins on order at equal specificity, however far away it was written.
    bare = re.findall(r"(?m)^\.crop\s*\{([^}]*)\}", CSS)
    assert len(bare) == 1, "a second `.crop` rule silently overrides the first"
    assert "position: sticky" in bare[0]


def test_the_app_says_when_its_own_code_is_stale() -> None:
    """Jinja re-reads a template every request and Python is imported once, so
    editing both and not restarting leaves new markup on old code: every new
    panel renders empty and every new endpoint 404s. Three features were
    reported as never built on one afternoon for exactly this reason, and
    nothing in the app could say so."""
    assert "code_is_newer_than_this_process" in (APP / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "showStale" in JS and "stale-code" in JS
    # No reload button: reloading fixes nothing here, and one that looked like
    # it might would send you round the same loop.
    start = JS.index("function showStale")
    stale = JS[start : JS.index("function showReload", start)]
    assert "location.reload" not in stale
    assert "Restart" in stale


def test_the_legend_groups_by_meaning_rather_than_by_key() -> None:
    """Eight colours times six kinds is forty-eight combinations in a 240px
    rail -- but nobody has forty-eight meanings, and `kind` beats `colour` in
    the config's own lookup, so one `note = "..."` already covers every colour
    of sticky note. Listing those separately prints one sentence eight times
    and calls it detail."""
    assert "scheme_legend" in (APP / "__init__.py").read_text(encoding="utf-8")
    assert "sl-mark" in GUIDE, "every mark for a meaning on one line"
    # The colour leads: you arrive holding one, so it is the lookup key. The
    # meaning used to lead, with the colour name on a second line.
    assert GUIDE.index("sl-label") < GUIDE.index("sl-meaning")


def test_the_whole_legend_folds_as_one() -> None:
    """A meaning is an arbitrary sentence and a source may declare forty of
    them, so half a 240px rail can end up spent on something you read twice.
    Splitting it into three folds by what each row *does* answered that but
    made the panel three decisions deep for a reference.

    One fold, open by default -- a legend nobody found is not a legend -- and
    the rows ordered by what the scheme does, so the marks that become units
    (the ones you meet in the queue) are the first thing under the heading."""
    assert "scheme scheme-whole" in GUIDE
    assert "<summary><h3>what the marks mean</h3>" in GUIDE
    assert "open>" in GUIDE[GUIDE.index("scheme scheme-whole") : ][:80]
    # And one entry cannot take the rail hostage however long it is written.
    assert "line-clamp" in rule(".sl-meaning")


def test_a_legend_row_is_a_kind_and_a_colour() -> None:
    """A row labelled just `green` claimed a green highlight and a green
    underline are one thing. They are two marks the reader made deliberately
    differently, and the pair is what decides the meaning."""
    from anki_math_forge.config import ZoteroConfig

    scheme = ZoteroConfig(data_dir=Path("/nowhere"), meanings={"note/yellow": "mine"})
    assert scheme.reading("note", "yellow")[1] == "declared"
    assert scheme.reading("note", "blue")[1] == "default", "no borrowing across colours"
    assert scheme.reading("highlight", "yellow")[1] == "default", "nor across kinds"


def test_the_gist_is_labelled_as_a_reading(zotero_config: Config) -> None:
    """A machine's guess presented as the answer is the one way this feature
    could do harm. The label is load-bearing, not decoration."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    block = units[units.index('class="gist"') - 200 : units.index('class="gist"') + 500]
    assert "reads as" in block, "not 'is about' -- it is somebody's reading"
    assert "/gist" in block, "and it says who read it"
    assert "decides nothing" in block, "and that nothing downstream acts on it"
    assert "cursor: help" in rule(".gist-what")


def test_a_grading_is_something_you_can_click() -> None:
    """Both decide the order Anki introduces new cards in, and the only way to
    set either used to be opening the file -- which is why so many cards carry
    neither. You learn that a result is `common` rather than `core` by meeting
    it, which is to say during review."""
    review = (APP / "templates" / "review.html").read_text(encoding="utf-8")
    review_js = (APP / "static" / "review.js").read_text(encoding="utf-8")
    assert 'data-grade="frequency"' in review and 'data-grade="derivation"' in review
    assert "cursor: pointer" in rule(".place .grade")
    # Through unset, so a grading given by a mis-click comes off by carrying on
    # clicking rather than by reaching for an editor.
    assert '"rare", ""]' in review_js and '"long", ""]' in review_js


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


def test_the_brief_for_the_card_writer_starts_open() -> None:
    """It may fold -- either section can run long on a unit you have been round
    a few times -- but it must not *start* folded. It once was a shut
    `<details>` labelled "not for this decision", which is a poor way to
    present the one instruction `/extract-cards` gets, and shut by default is
    the half of that which actually hid it."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    pane = units[units.index("notes-pane") :]
    assert "the brief for whoever writes the card" in pane
    folds = re.findall(r'<details class="note-section"([^>]*)>', pane)
    assert len(folds) == 2, "both sections fold"
    assert all("open" in attrs for attrs in folds), "and both start open"


def test_the_two_audiences_have_one_fixed_place() -> None:
    """They were scattered down the main column under everything else; the
    panel is the same place on every unit, and it splits from the marks.

    Notes **above** the marks: the mark this unit came from is already on the
    crop beside them, at full strength with a red outline round it, so the top
    of this column was being spent on the one thing you cannot miss. What
    belongs there is where the work is."""
    units = (APP / "templates" / "units.html").read_text(encoding="utf-8")
    assert 'data-splitter="beside"' in units
    assert '"beside"' in JS or "beside:" in JS, "and the split is remembered"
    assert units.index("notes-pane") < units.index("marks-list"), "notes above, marks below"


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


def test_a_control_in_a_heading_acts_without_folding_it() -> None:
    """`<summary>` toggles its `<details>` on any click inside it, so the `add`
    button on a notes section opened the prompt *and* collapsed the section it
    was adding to, and the chapter tally -- a filter link -- would navigate
    away while folding on the way out.

    A link needs both halves separated by hand: folding and following are the
    same click's default action, so `preventDefault` alone would cancel the
    navigation too."""
    block = JS[JS.index("A control inside a heading acts") :][:1200]
    assert 'closest("a[href]")' in block
    assert "window.location.href" in block, "suppress the fold, follow by hand"
    assert "event.metaKey" in block, "and leave a modified click to the browser"


def test_the_neighbour_chips_do_not_shout() -> None:
    """Green is the app's "you decided this" colour and it is already doing
    that job on the rail's grid, where a selection changes which units you
    meet. These chips change nothing on disk and nothing about the queue --
    they are a reading aid for the list beside them -- and six green rectangles
    beside a crop full of colours was the loudest thing on the panel for the
    least important reason.

    Equal padding all round, because a chip is a swatch *and* a count and the
    padding has to sit outside both or the box reads as lopsided."""
    on = rule(".mf-chip.on")
    assert "var(--line)" in on and "--accent" not in on
    padding = re.search(r"padding:\s*([^;]+);", rule(".mf-chip, .mf-all")).group(1)
    assert len(padding.split()) == 1, f"padding {padding!r} is not equal on all sides"
