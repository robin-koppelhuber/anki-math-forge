"""The bugs four browser agents found, each pinned so it cannot come back.

Every one of these was invisible to the whole Python suite and took under a
minute to find with a pointer. They are grouped by what went wrong rather than
by view, because the shapes repeat: a handler reading state a key had already
cleared, a write with no precondition, a legend describing something the code
does not do.
"""

from __future__ import annotations

GRAPH = "/graph?source=demo"


def canvas(pg, live):  # type: ignore[no-untyped-def]
    pg.goto(live + GRAPH)
    pg.wait_for_function("typeof data !== 'undefined' && data !== null")
    pg.wait_for_timeout(200)
    return pg.evaluate(
        """() => data.nodes.map(n => {
      const b = canvas.getBoundingClientRect();
      const p = at(n.id);
      const to = (x, y) => ({x: b.left + pan.x + x * scale, y: b.top + pan.y + y * scale});
      return {
        id: n.id,
        centre: to(p.x + NODE_W / 2, p.y + NODE_H / 2),
        right: to(p.x + NODE_W, p.y + NODE_H / 2),
      };
    })"""
    )


# -- writes that went to the wrong file --------------------------------------


def test_undo_after_a_move_does_not_delete_an_arrow(page, live) -> None:  # type: ignore[no-untyped-def]
    """`undone` only ever held edge operations, so `z` after dragging a box
    popped the newest *arrow* instead: a keystroke meant to put a box back
    deleted a `requires` from a card file, possibly one you had not touched."""
    nodes = canvas(page, live)
    edges = page.evaluate("data.edges.length")
    assert edges, "the fixture has an arrow to lose"
    grab = nodes[0]["centre"]
    page.mouse.move(grab["x"], grab["y"])
    page.mouse.down()
    page.mouse.move(grab["x"] + 90, grab["y"] + 50, steps=6)
    page.mouse.up()
    page.wait_for_timeout(700)
    page.keyboard.press("z")
    page.wait_for_timeout(900)
    assert page.evaluate("data.edges.length") == edges


def test_escape_during_a_drag_puts_the_box_back(page, live) -> None:  # type: ignore[no-untyped-def]
    """The save read the *selection*, and Escape cleared the selection while
    the drag ran on: the box stayed drawn where it had been dragged, nothing
    was written, and the two only disagreed until the next reload."""
    nodes = canvas(page, live)
    grab = nodes[0]["centre"]
    page.mouse.move(grab["x"], grab["y"])
    page.mouse.down()
    page.mouse.move(grab["x"] + 140, grab["y"], steps=5)
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert page.evaluate("Object.keys(moved).length") == 0
    assert page.evaluate("Object.keys(data.positions || {}).length") == 0


def test_shift_clicking_a_selected_box_does_not_drag_the_others(page, live) -> None:  # type: ignore[no-untyped-def]
    """It removed the box under the pointer from the selection and then built
    the drag from what was left, so a shift-click that wandered four pixels
    rewrote every *other* selected card and left the one clicked where it was.
    There is no undo for an arrangement you did not make."""
    canvas(page, live)
    page.keyboard.press("f")  # every card, so there are several to catch
    page.wait_for_timeout(600)
    nodes = canvas(page, live)
    page.keyboard.press("A")
    page.wait_for_timeout(200)
    grab = nodes[0]["centre"]
    page.keyboard.down("Shift")
    page.mouse.move(grab["x"], grab["y"])
    page.mouse.down()
    page.mouse.move(grab["x"] + 60, grab["y"] + 40, steps=5)
    page.mouse.up()
    page.keyboard.up("Shift")
    page.wait_for_timeout(700)
    assert page.evaluate("Object.keys(data.positions || {}).length") == 0, (
        "a shift-click toggles a selection and writes nothing"
    )


def test_two_fast_presses_settle_the_unit_they_queued(page, live) -> None:  # type: ignore[no-untyped-def]
    """`settle` read `this.current`, which the second keypress had already
    advanced. Unit one was queued on disk and unit *two* was painted "no longer
    matches this filter" while still `new`, after which `nextPending` skipped
    it forever."""
    page.goto(live + "/units?state=new")
    page.wait_for_timeout(500)
    ids = page.eval_on_selector_all(".item", "e => e.map(x => x.dataset.id)")
    assert len(ids) > 1, "the fixture needs two units to confuse"
    page.keyboard.press("q")
    page.keyboard.press("q")
    page.wait_for_timeout(1200)
    settled = set(
        page.eval_on_selector_all(
            ".item", "e => e.filter(x => x.dataset.settled).map(x => x.dataset.id)"
        )
    )
    assert settled, "something was settled"
    # Whatever is marked settled on screen must really be queued on disk.
    states = page.evaluate(
        """async () => {
      const r = await fetch('/api/counts');
      return (await r.json()).pipeline;
    }"""
    )
    assert states["queued"] == len(settled), f"{states} vs settled={settled}"


def test_the_note_key_writes_the_audience_it_names(page, live) -> None:  # type: ignore[no-untyped-def]
    """`ask` selected its pre-fill, so the first keystroke replaced it. `N`
    pre-filled `@me ` and carried the audience nowhere else, so typing wiped it
    and `Ledger.annotate` filed the line as `@claude`: a decision parked for
    yourself became work queued for `/extract-cards`."""
    page.goto(live + "/units?state=new")
    page.wait_for_timeout(500)
    page.keyboard.press("N")
    page.wait_for_selector("#prompt[open]")
    page.keyboard.type("decide whether this is two cards")
    page.keyboard.press("Enter")
    # Writing a note reloads, onto the unit you were on. Wait for that to land
    # rather than reading the page it is replacing.
    page.wait_for_timeout(2500)
    body = page.content()
    assert "decide whether this is two cards" in body, "the note was written"
    assert "@me" in body, "and filed for you, not for claude" 


def test_an_untouched_prompt_writes_nothing(page, live) -> None:  # type: ignore[no-untyped-def]
    """Submitting the pre-fill unchanged wrote a bare `@claude` with nothing
    after it, which renders as a note row with no text."""
    page.goto(live + "/units?state=new")
    page.wait_for_timeout(500)
    page.evaluate("document.getElementById('toast').textContent = ''")
    page.keyboard.press("n")
    page.wait_for_selector("#prompt[open]")
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    assert "annotated" not in page.inner_text("#toast"), (
        "an empty answer used to write a bare `@claude` with nothing after it"
    )


# -- what the legend claims --------------------------------------------------


def test_a_dot_dropped_on_its_own_card_refuses(page, live) -> None:  # type: ignore[no-untyped-def]
    """`link.target` was nulled for a drop on the source node, so `whyNot`'s
    own wording never fired and the release read as a drop on empty space --
    which opened the card picker."""
    nodes = canvas(page, live)
    start, middle = nodes[0]["right"], nodes[0]["centre"]
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(middle["x"], middle["y"], steps=6)
    page.mouse.up()
    page.wait_for_timeout(400)
    assert not page.is_visible("#add-card")
    assert "itself" in page.inner_text("#toast")


def test_one_escape_closes_a_dialog_you_have_typed_in(page, live) -> None:  # type: ignore[no-untyped-def]
    """Chrome's `<input type="search">` eats the first Escape to clear itself,
    and every dialog here focuses its search box on open -- so the button
    saying "close (esc)" needed two presses."""
    canvas(page, live)
    page.keyboard.press("+")
    page.wait_for_timeout(250)
    page.fill("#add-search", "trace")
    page.wait_for_timeout(200)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.is_visible("#add-card")


def test_the_warning_colour_is_actually_read(page, live) -> None:  # type: ignore[no-untyped-def]
    """`palette()` never read `--warn`, and `ctx.strokeStyle = undefined` is a
    silent no-op: the one arrow the picture is meant to draw attention to kept
    whatever colour was set last."""
    canvas(page, live)
    assert page.evaluate("colours.warn")


def test_a_key_pressed_mid_gesture_waits(page, live) -> None:  # type: ignore[no-untyped-def]
    """`bindKeys` guarded on a modal being open and not on a gesture being
    live, so `+` during an arrow drag opened the picker *over* an arrow that
    then still landed underneath it."""
    nodes = canvas(page, live)
    start = nodes[0]["right"]
    page.mouse.move(start["x"], start["y"])
    page.mouse.down()
    page.mouse.move(start["x"] + 120, start["y"] + 80, steps=5)
    page.keyboard.press("+")
    page.wait_for_timeout(300)
    assert not page.is_visible("#add-card")
    page.keyboard.press("Escape")
    page.mouse.up()
    page.wait_for_timeout(300)
