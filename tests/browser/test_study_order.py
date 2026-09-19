"""The study-order panel, driven in a real browser.

Its two halves are exactly the two things the rest of the suite cannot check.
The rule is reordered by dragging, and a drag is a sequence of pointer events
against a live layout. The order under it is rendered from the payload the
canvas already fetched, so "the panel agrees with the picture" is a claim about
two renderings of one response rather than about any string.
"""

from __future__ import annotations

import json

GRAPH = "/graph?project=demo"


def open_panel(pg, live):  # type: ignore[no-untyped-def]
    pg.goto(live + GRAPH)
    pg.wait_for_function("typeof data !== 'undefined' && data !== null")
    pg.wait_for_timeout(200)
    if pg.evaluate("document.getElementById('order-rail').hidden"):
        pg.click("#graph-order")
    pg.wait_for_selector("#order-cards .order-card")
    pg.wait_for_timeout(150)


def rule(pg):  # type: ignore[no-untyped-def]
    return pg.eval_on_selector_all(
        "#order-criteria .criterion", "rows => rows.map(r => r.dataset.name)"
    )


def queue(pg):  # type: ignore[no-untyped-def]
    return pg.eval_on_selector_all(
        "#order-cards .order-card", "rows => rows.map(r => r.dataset.id)"
    )


def declared(repo):  # type: ignore[no-untyped-def]
    """What `forge.toml` says, which is the only record of this setting."""
    body = (repo / "forge.toml").read_text(encoding="utf-8")
    for line in body.splitlines():
        if line.strip().startswith("study_order"):
            return json.loads(line.split("=", 1)[1].strip())
    return None


def test_the_panel_opens_without_the_console_complaining(page, live) -> None:  # type: ignore[no-untyped-def]
    open_panel(page, live)
    assert page.complaints == []


def test_it_lists_every_card_not_only_the_drawn_ones(page, live) -> None:  # type: ignore[no-untyped-def]
    """The gap the panel exists to close. The canvas draws what depends on
    something, which here is two of the four cards."""
    open_panel(page, live)

    assert len(queue(page)) == 4
    assert page.evaluate("data.nodes.length") == 2
    off = page.eval_on_selector_all(".order-card.off", "rows => rows.map(r => r.dataset.id)")
    assert sorted(off) == ["ccc333", "ddd444"]


def test_the_queue_is_the_study_order(page, live) -> None:  # type: ignore[no-untyped-def]
    """`bbb222` is core and `aaa111` is rare, but `bbb222` needs `aaa111`, so
    the prerequisite is pulled in front of the card that made it important."""
    open_panel(page, live)

    assert queue(page) == ["aaa111", "bbb222", "ccc333", "ddd444"]
    assert page.inner_text("#order-cards .order-card:first-child .shift").endswith("earlier")


def test_an_ungraded_card_says_so(page, live) -> None:  # type: ignore[no-untyped-def]
    """It sorts last within its group, which is a fact worth seeing rather
    than an empty cell."""
    open_panel(page, live)
    chips = page.eval_on_selector_all(
        "#order-cards .order-card:last-child .grade", "c => c.map(x => x.textContent)"
    )

    assert chips[:2] == ["ungraded", "ungraded"]


def test_dragging_a_rule_reorders_the_deck_and_writes_the_file(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The whole feature: drag `derivation` above `frequency` and the queue
    under it changes, because the file changed and the server re-read it."""
    _, repo = served
    open_panel(page, live)
    assert rule(page) == ["frequency", "derivation", "printed"]

    rows = page.query_selector_all("#order-criteria .criterion")
    first = rows[0].bounding_box()
    second = rows[1].bounding_box()
    page.mouse.move(second["x"] + 20, second["y"] + second["height"] / 2)
    page.mouse.down()
    # Past the midpoint of the row above, which is what moves it.
    page.mouse.move(first["x"] + 20, first["y"] + 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(900)

    assert rule(page) == ["derivation", "frequency", "printed"]
    assert declared(repo) == ["derivation", "frequency", "printed"]
    assert page.complaints == []


def test_the_rule_can_be_reordered_from_the_keyboard(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A control that only answers to a drag is one somebody cannot use."""
    _, repo = served
    open_panel(page, live)

    page.focus("#order-criteria .criterion:nth-child(3)")
    page.keyboard.press("ArrowUp")
    page.wait_for_timeout(900)

    assert rule(page) == ["frequency", "printed", "derivation"]
    assert declared(repo) == ["frequency", "printed", "derivation"]


def test_reordering_moves_the_picture_too(page, live) -> None:  # type: ignore[no-untyped-def]
    """The criteria also decide the order within a layer of the layout, so the
    canvas is refetched rather than the panel re-sorted on its own."""
    open_panel(page, live)
    before = page.evaluate("JSON.stringify(data.order.names)")

    page.focus("#order-criteria .criterion:nth-child(2)")
    page.keyboard.press("ArrowUp")
    page.wait_for_timeout(900)

    assert page.evaluate("JSON.stringify(data.order.names)") != before
    assert page.evaluate("data.nodes.length") == 2, "the picture came back with it"


def test_clicking_a_drawn_row_finds_it_on_the_canvas(page, live) -> None:  # type: ignore[no-untyped-def]
    open_panel(page, live)

    page.click("#order-cards .order-card[data-id='bbb222'] .order-open")
    page.wait_for_timeout(250)

    assert page.evaluate("picked.nodes") == ["bbb222"]
    middle = page.evaluate(
        """() => {
      const b = stage.getBoundingClientRect();
      const p = at("bbb222");
      return Math.abs(pan.x + (p.x + NODE_W / 2) * scale - b.width / 2);
    }"""
    )
    assert middle < 2, "the box it found should be in the middle of what is left"


def test_clicking_an_undrawn_row_puts_it_on_the_canvas(page, live) -> None:  # type: ignore[no-untyped-def]
    """The row is dim because nothing depends on the card, and clicking it is
    the step you were about to take: it is on the canvas to be connected."""
    open_panel(page, live)
    assert page.evaluate("data.nodes.length") == 2

    page.click("#order-cards .order-card[data-id='ccc333'] .order-open")
    page.wait_for_timeout(700)

    assert page.evaluate("data.nodes.map(n => n.id)").count("ccc333") == 1
    assert page.eval_on_selector(
        "#order-cards .order-card[data-id='ccc333']",
        "row => !row.classList.contains('off')",
    )


def test_the_panel_survives_being_closed_and_reopened(page, live) -> None:  # type: ignore[no-untyped-def]
    """It is remembered, so it is on again after a navigation. A panel that
    closed itself every time you moved would be one you stop opening."""
    open_panel(page, live)
    page.click("#order-close")
    page.wait_for_timeout(150)
    assert page.evaluate("document.getElementById('order-rail').hidden")

    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(300)
    assert page.evaluate("document.getElementById('order-rail').hidden"), "stayed closed"

    page.click("#graph-order")
    page.wait_for_timeout(200)
    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.getElementById('order-rail').hidden"), "stayed open"

    page.click("#order-close")


def test_the_canvas_keeps_its_width_for_the_panel(page, live) -> None:  # type: ignore[no-untyped-def]
    """The stage gives up the room rather than being covered: the picture and
    the order it produces are meant to be read against each other."""
    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(200)
    wide = page.evaluate("stage.getBoundingClientRect().width")

    page.click("#graph-order")
    page.wait_for_timeout(250)
    narrow = page.evaluate("stage.getBoundingClientRect().width")

    assert narrow < wide - 100
    assert page.evaluate("canvas.getBoundingClientRect().width") == narrow, "canvas resized"
    page.click("#order-close")


def test_the_edge_tab_is_the_way_back_to_the_panel(page, live) -> None:  # type: ignore[no-untyped-def]
    """Closing it put the only way back on the far side of the window: the
    gesture that shut the panel is on the right and the chip is on the left."""
    open_panel(page, live)
    assert page.evaluate("document.getElementById('order-tab').hidden"), "hidden while open"

    page.click("#order-close")
    page.wait_for_timeout(200)
    assert not page.evaluate("document.getElementById('order-tab').hidden")

    page.click("#order-tab")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.getElementById('order-rail').hidden")
    assert page.evaluate("document.getElementById('order-tab').hidden")
    page.click("#order-close")


def test_the_drawn_segment_names_both_sides(page, live) -> None:  # type: ignore[no-untyped-def]
    """`every card` as a lone pill never said what its alternative was, so off
    it left you to infer from the counts line what you were being shown."""
    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(200)

    lit = ".tool-group .ctx-step.on"
    assert page.inner_text(lit) == "linked"

    page.click("#graph-all")
    page.wait_for_timeout(600)
    assert page.inner_text(lit) == "every card"
    assert page.evaluate("data.nodes.length") == 4

    # Pressing the half already in force is not a toggle back off it.
    page.click("#graph-all")
    page.wait_for_timeout(400)
    assert page.inner_text(lit) == "every card"
    page.click("#graph-linked")
    page.wait_for_timeout(600)
    assert page.evaluate("data.nodes.length") == 2


def test_a_link_can_open_the_panel_without_changing_the_preference(page, live) -> None:  # type: ignore[no-untyped-def]
    """`?order=1` makes the panel part of what a URL can say, which is what
    lets `make_assets.py` photograph it. Arriving by somebody's link is not a
    decision about how the view should open tomorrow, so it is not stored."""
    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(200)
    if not page.evaluate("document.getElementById('order-rail').hidden"):
        page.click("#order-close")
        page.wait_for_timeout(150)

    page.goto(live + GRAPH + "&order=1")
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.getElementById('order-rail').hidden")
    assert page.evaluate("document.getElementById('order-tab').hidden")

    page.goto(live + GRAPH)
    page.wait_for_function("typeof data !== 'undefined' && data !== null")
    page.wait_for_timeout(300)
    assert page.evaluate("document.getElementById('order-rail').hidden"), "not remembered"
