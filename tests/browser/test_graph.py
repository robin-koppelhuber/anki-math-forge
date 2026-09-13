"""The canvas, driven by a pointer in a real browser.

Every other test in this suite asserts against markup, a payload or a file.
None of those can say what a click does to a `<canvas>`, and that is where this
view's bugs were: a close button that set `open = false` while the panel stayed
painted, an arrow drawn to the wrong place, a selection whose `kind` was
overwritten by a spread. Each was invisible to the whole suite and obvious in
the first thirty seconds of driving the page.

Opt in with `uv sync --extra browser`; the fixtures are in `conftest.py`
beside this file, so the whole directory skips without it.
"""

from __future__ import annotations

import pytest

GRAPH = "/graph?source=demo"


def boxes(pg):  # type: ignore[no-untyped-def]
    """Screen coordinates of every node's centre and its two ports."""
    return pg.evaluate(
        """() => data.nodes.map(n => {
      const b = canvas.getBoundingClientRect();
      const p = at(n.id);
      const to = (x, y) => ({x: b.left + pan.x + x, y: b.top + pan.y + y});
      return {
        id: n.id,
        centre: to(p.x + NODE_W / 2, p.y + NODE_H / 2),
        left: to(p.x, p.y + NODE_H / 2),
        right: to(p.x + NODE_W, p.y + NODE_H / 2),
      };
    })"""
    )


def open_graph(pg, live):  # type: ignore[no-untyped-def]
    pg.goto(live + GRAPH)
    pg.wait_for_function("typeof data !== 'undefined' && data !== null")
    pg.wait_for_timeout(200)
    return boxes(pg)


def test_the_page_loads_without_the_console_complaining(page, live) -> None:  # type: ignore[no-untyped-def]
    open_graph(page, live)
    assert page.complaints == []


def test_a_click_selects_and_does_not_navigate(page, live) -> None:  # type: ignore[no-untyped-def]
    """Opening a card on a single click made the gesture that picks something
    out of the picture the same gesture that leaves it."""
    nodes = open_graph(page, live)
    page.mouse.click(nodes[0]["centre"]["x"], nodes[0]["centre"]["y"])
    page.wait_for_timeout(150)
    assert page.evaluate("selected") == {"kind": "node", "id": nodes[0]["id"]}
    assert "/graph" in page.url


def test_a_double_click_opens_the_card(page, live) -> None:  # type: ignore[no-untyped-def]
    nodes = open_graph(page, live)
    with page.expect_navigation():
        page.mouse.dblclick(nodes[0]["centre"]["x"], nodes[0]["centre"]["y"])
    assert "/review" in page.url and nodes[0]["id"] in page.url


def test_dragging_dot_to_dot_writes_the_dependency(page, live) -> None:  # type: ignore[no-untyped-def]
    open_graph(page, live)
    # Every card, so there are two on screen that are not already linked. The
    # default picture is only the connected part, and connecting those two
    # again is correctly refused as a duplicate.
    page.keyboard.press("f")
    page.wait_for_timeout(700)
    nodes = boxes(page)
    before = page.evaluate("data.edges.length")
    free = page.evaluate(
        """() => data.nodes
             .filter(n => !data.edges.some(e => e.src === n.id || e.dst === n.id))
             .map(n => n.id)"""
    )
    assert len(free) >= 2, "the fixture should have two unlinked cards"
    src = next(n for n in nodes if n["id"] == free[0])
    dst = next(n for n in nodes if n["id"] == free[1])
    page.mouse.move(src["right"]["x"], src["right"]["y"])
    page.mouse.down()
    page.mouse.move(dst["centre"]["x"], dst["centre"]["y"], steps=8)
    page.mouse.up()
    page.wait_for_timeout(900)
    assert page.evaluate("data.edges.length") == before + 1
    assert page.evaluate(
        "([a, b]) => data.edges.some(e => e.src === a && e.dst === b)",
        [src["id"], dst["id"]],
    )


def test_an_arrow_runs_from_one_dot_to_the_other(page, live) -> None:  # type: ignore[no-untyped-def]
    """Not centre to centre clipped at the border, which is what made the view
    read as clunky: the arrow you had just dragged between two dots arrived
    somewhere else on the box, and two arrows into one card entered at two
    different places."""
    open_graph(page, live)
    ends = page.evaluate(
        """() => {
      const e = data.edges[0];
      const from = port(e.src, 'right');
      const to = port(e.dst, 'left');
      return {from, to, srcRight: port(e.src, 'right'), dstLeft: port(e.dst, 'left')};
    }"""
    )
    assert ends["from"] == ends["srcRight"]
    assert ends["to"] == ends["dstLeft"]


def test_a_selected_arrow_can_be_deleted(page, live) -> None:  # type: ignore[no-untyped-def]
    """`selected` carried `kind: "requires"` for a while -- an `Edge` has its
    own `kind`, and `{kind: "edge", ...edge}` put it back -- so every test of
    `selected.kind === "edge"` was false and Delete quietly did nothing."""
    open_graph(page, live)
    spot = page.evaluate(
        """() => {
      const e = data.edges[0];
      const m = along(port(e.src, 'right'), port(e.dst, 'left'))[10];
      const b = canvas.getBoundingClientRect();
      return {x: b.left + pan.x + m.x, y: b.top + pan.y + m.y};
    }"""
    )
    page.mouse.click(spot["x"], spot["y"])
    page.wait_for_timeout(150)
    assert page.evaluate("selected && selected.kind") == "edge"
    page.keyboard.press("Delete")
    page.wait_for_timeout(900)
    assert page.evaluate("data.edges.length") == 0


def test_deleting_a_card_that_has_an_arrow_says_why(page, live) -> None:  # type: ignore[no-untyped-def]
    """An arrow is why it is drawn, so taking it off the canvas would put it
    straight back. Better to say so than to do nothing."""
    nodes = open_graph(page, live)
    linked = page.evaluate("data.edges[0].dst")
    box = next(n for n in nodes if n["id"] == linked)
    page.mouse.click(box["centre"]["x"], box["centre"]["y"])
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)
    assert "arrow" in page.inner_text("#toast")


# -- the picker -------------------------------------------------------------


def test_the_close_button_closes_it(page, live) -> None:  # type: ignore[no-untyped-def]
    """It set `open` to false and the panel stayed on screen, over the canvas,
    with the keyboard still going to it: `.gallery.adder { display: flex }`
    outranks the browser's own `dialog:not([open]) { display: none }`.

    Only a real browser shows that. The markup was right and the JavaScript ran.
    """
    open_graph(page, live)
    page.keyboard.press("+")
    page.wait_for_timeout(200)
    assert page.is_visible("#add-card")
    page.click("#add-close")
    page.wait_for_timeout(200)
    assert page.eval_on_selector("#add-card", "d => d.open") is False
    assert not page.is_visible("#add-card")


def test_escape_closes_it_too(page, live) -> None:  # type: ignore[no-untyped-def]
    open_graph(page, live)
    page.keyboard.press("+")
    page.wait_for_timeout(200)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    assert not page.is_visible("#add-card")


def test_the_search_is_empty_every_time_it_opens(page, live) -> None:  # type: ignore[no-untyped-def]
    """It kept whatever you last typed, so reopening showed a list filtered by
    a word you had forgotten about, which reads as most of the deck having
    vanished."""
    open_graph(page, live)
    page.keyboard.press("+")
    page.wait_for_timeout(200)
    everything = page.eval_on_selector_all(".add-row", "e => e.length")
    page.fill("#add-search", "adjugate")
    page.wait_for_timeout(200)
    assert page.eval_on_selector_all(".add-row", "e => e.length") < everything
    page.click("#add-close")
    page.wait_for_timeout(200)
    page.keyboard.press("+")
    page.wait_for_timeout(200)
    assert page.input_value("#add-search") == ""
    assert page.eval_on_selector_all(".add-row", "e => e.length") == everything


def test_the_keyboard_comes_back_after_the_picker_closes(page, live) -> None:  # type: ignore[no-untyped-def]
    """A dialog owns the keyboard while it is open. One that closed without
    unpainting owned it forever, which is how `f`, `0` and `g` all appeared to
    be dead keys."""
    open_graph(page, live)
    page.keyboard.press("+")
    page.wait_for_timeout(200)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    before = page.inner_text("#graph-counts")
    page.keyboard.press("f")
    page.wait_for_timeout(700)
    assert page.inner_text("#graph-counts") != before


def test_dropping_an_arrow_on_nothing_offers_the_cards_not_drawn(page, live) -> None:  # type: ignore[no-untyped-def]
    """The card you meant is very likely one of the ones not on the canvas --
    that is what the picker is for -- so the gesture finishes rather than being
    thrown away."""
    nodes = open_graph(page, live)
    src = nodes[0]
    page.mouse.move(src["right"]["x"], src["right"]["y"])
    page.mouse.down()
    page.mouse.move(src["right"]["x"] + 180, src["right"]["y"] + 240, steps=6)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert page.is_visible("#add-card")
    assert "connect" in page.inner_text("#add-count")


def test_picking_one_there_adds_it_and_draws_the_arrow(page, live) -> None:  # type: ignore[no-untyped-def]
    nodes = open_graph(page, live)
    src = next(n for n in nodes if n["id"] == page.evaluate("data.edges[0].src"))
    before = page.evaluate("data.edges.length")
    page.mouse.move(src["right"]["x"], src["right"]["y"])
    page.mouse.down()
    page.mouse.move(src["right"]["x"] + 180, src["right"]["y"] + 240, steps=6)
    page.mouse.up()
    page.wait_for_timeout(400)
    page.click(".add-row")
    page.wait_for_timeout(1200)
    assert not page.is_visible("#add-card")
    assert page.evaluate("data.edges.length") == before + 1


def test_a_click_on_a_dot_that_never_moved_opens_nothing(page, live) -> None:  # type: ignore[no-untyped-def]
    """A mis-click on a dot is not an attempt to connect to nothing."""
    nodes = open_graph(page, live)
    page.mouse.click(nodes[0]["right"]["x"], nodes[0]["right"]["y"])
    page.wait_for_timeout(300)
    assert not page.is_visible("#add-card")


# -- the way in and out -----------------------------------------------------


@pytest.mark.parametrize("view", ["/units", "/review"])
def test_every_view_has_a_button_to_the_canvas(page, live, view: str) -> None:  # type: ignore[no-untyped-def]
    page.goto(live + view)
    page.wait_for_timeout(300)
    assert page.is_visible('#topbar a[aria-label="graph"]')
    with page.expect_navigation():
        page.click('#topbar a[aria-label="graph"]')
    assert "/graph" in page.url


def test_the_canvas_has_a_button_back(page, live) -> None:  # type: ignore[no-untyped-def]
    open_graph(page, live)
    with page.expect_navigation():
        page.click('#topbar a[aria-label="review"]')
    assert "/review" in page.url
