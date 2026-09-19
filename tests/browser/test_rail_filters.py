"""The left filter rail, and the commands panel pinned under it.

A rail row is a claim about a population: "seven cards have an open request",
and clicking it gives you those seven. Nothing outside a browser can check
that claim, because the count comes from `pipeline_counts` and the deck comes
from the view's own filtering, and the two are separate pieces of code that
only ever meet on screen. A markup test sees a number beside a link and a link
beside a number, and agrees with itself.

The commands panel is the same shape of problem. What it offers is scoped to
the source and section on screen, so its text is only right relative to
whatever the rail is filtered to at that moment, and the one thing it must
never do is run anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

UNITS = "/units?source=demo&state=all"
REVIEW = "/review?source=demo&status=all"

# Every state, not the default lane. The properties counts are taken over the
# whole source, so on a view filtered to `new` units or `draft` cards a row
# would promise more than the deck below it can hold, and the promise is what
# these tests are about.

CLAUDE_NOTE = "@claude check the sign on this one"
ME_NOTE = "@me decide whether this wants splitting"

RAIL = "#filter-rail"
# The mark an active row carries. Named rather than pasted in: the character
# is a multiplication sign, which is not the letter it looks like.
CLEAR_MARK = "\N{MULTIPLICATION SIGN}"
PROPERTIES = (
    f'{RAIL} details.filter-group:has(> summary:text-is("properties"))'
    " > ul.filter-list > li > a"
)


def properties(pg):  # type: ignore[no-untyped-def]
    return pg.locator(PROPERTIES)


def labels(pg) -> list[str]:  # type: ignore[no-untyped-def]
    """The row names, with the clear mark an active row carries taken off."""
    return [
        text.replace(CLEAR_MARK, "").strip()
        for text in properties(pg).locator("span").all_inner_texts()
    ]


def row_named(pg, label: str):  # type: ignore[no-untyped-def]
    return properties(pg).nth(labels(pg).index(label))


def promised(row) -> int:  # type: ignore[no-untyped-def]
    return int(row.locator("b").inner_text().strip())


def deck(pg) -> int:  # type: ignore[no-untyped-def]
    """How many units or cards the server put on the page.

    Both views render the whole filtered deck and reveal one item at a time,
    so the articles are the deck whether or not they are `hidden`.
    """
    return pg.locator("#deck > article").count()


def settled(pg) -> None:  # type: ignore[no-untyped-def]
    pg.wait_for_selector(PROPERTIES)


def annotate(pg, live: str, unit_id: str, text: str) -> None:
    """One annotation on one unit, through the endpoint the app itself uses.

    The ledger is rewritten by the `live` fixture before every test, so this
    has to be redone per test rather than once for the file.
    """
    reply = pg.request.post(f"{live}/api/units/demo/{unit_id}/annotate", data={"text": text})
    assert reply.ok, reply.text()


def write_card(repo: Path, uid: str, *, note: str = "", augmented: bool = False) -> None:
    """One extra draft beyond the fixture's deck, named so nothing collides."""
    flag = "augmented: true\n" if augmented else ""
    notes = f"\n## notes\n\n{note}\n" if note else ""
    (repo / "cards" / "demo" / f"{uid}-x.md").write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Demo"\nunit: "demo:1:1"\ngist: a card for the rail\n{flag}---\n\n'
        f"## front\n\n$a$\n\n## back\n\n$b$\n{notes}",
        encoding="utf-8",
    )


def a_deck_with_something_in_every_row(repo: Path) -> None:
    """Cards that make each properties row a number rather than a zero.

    A row that counts nothing filters to nothing, and a test where both sides
    are zero passes whatever the filter does.
    """
    write_card(repo, "zzcla1", note=CLAUDE_NOTE)
    write_card(repo, "zzmee1", note=ME_NOTE)
    write_card(repo, "zzaug1", augmented=True)


def pick_section(pg, name: str) -> None:
    """Click the section row called `name`, opening its chapter on the way.

    The demo source is one chapter holding two sections, so the rows start
    inside a shut `<details>`. Its tally is a filter link, which both opens the
    fold and narrows to the chapter, and the section click then replaces that
    with the section itself.
    """
    folded = pg.locator(f"{RAIL} details.filter-chapter:not([open]) > summary .chapter-pick")
    if folded.count():
        folded.first.click()
        settled(pg)
    row = pg.locator(f"{RAIL} .filter-list.sections > li > a").filter(
        has=pg.locator(f'.sec-name:text-is("§{name}")')
    )
    row.click()
    settled(pg)


def test_each_units_row_shows_as_many_units_as_it_counted(page, live) -> None:  # type: ignore[no-untyped-def]
    """The rail's whole contract. The count comes from the pipeline totals and
    the deck comes from the view's own filtering, so a row can be off by
    exactly the population the two disagree about and still look right."""
    annotate(page, live, "demo:1:1", CLAUDE_NOTE)
    annotate(page, live, "demo:1.1:2", ME_NOTE)
    page.goto(live + UNITS)
    settled(page)
    kept: list[tuple[str, int]] = []

    for index in range(properties(page).count()):
        page.goto(live + UNITS)
        settled(page)
        row = properties(page).nth(index)
        name, said = labels(page)[index], promised(row)
        row.click()
        settled(page)
        assert deck(page) == said, f"{name} counted {said}, showed {deck(page)}"
        kept.append((name, said))

    assert sum(said for _, said in kept) > 0, f"nothing to filter: {kept}"


def test_each_cards_row_shows_as_many_cards_as_it_counted(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The same contract on the other view, where the rows are different ones
    and the counts come from the card half of the pipeline."""
    _, repo = served
    a_deck_with_something_in_every_row(repo)
    page.goto(live + REVIEW)
    settled(page)
    kept: list[tuple[str, int]] = []

    for index in range(properties(page).count()):
        page.goto(live + REVIEW)
        settled(page)
        row = properties(page).nth(index)
        name, said = labels(page)[index], promised(row)
        row.click()
        settled(page)
        assert deck(page) == said, f"{name} counted {said}, showed {deck(page)}"
        kept.append((name, said))

    assert all(said for _, said in kept), f"a row counted nothing: {kept}"


def test_an_active_row_offers_the_way_out(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A filter you cannot see is on is a deck that looks empty for no reason.
    The row marks itself and takes the filter off again when clicked, so the
    exit is visible rather than merely reachable through the back button."""
    _, repo = served
    a_deck_with_something_in_every_row(repo)
    page.goto(live + REVIEW)
    settled(page)
    everything = deck(page)

    row_named(page, "@claude").click()
    settled(page)
    row = row_named(page, "@claude")
    assert "on" in (row.get_attribute("class") or "")
    assert row.locator(".clear-mark").count() == 1
    assert deck(page) < everything

    row.click()
    settled(page)

    assert "on" not in (row_named(page, "@claude").get_attribute("class") or "")
    assert deck(page) == everything


def test_the_rows_are_in_the_order_the_work_goes_in(page, live) -> None:  # type: ignore[no-untyped-def]
    """Each view leads with what is specific to it and ends with the three
    annotation rows, which mean the same thing on both sides. `ungraded` was
    taken off on purpose: a rail row is a population you work through, and
    nobody works through the cards that have no grading yet."""
    page.goto(live + UNITS)
    settled(page)

    assert labels(page) == ["suggested", "transcribed", "no notes", "@claude", "@me"]
    assert "ungraded" not in page.inner_text(RAIL)

    page.goto(live + REVIEW)
    settled(page)

    assert labels(page) == ["not augmented", "augmented", "no notes", "@claude", "@me"]
    assert "ungraded" not in page.inner_text(RAIL)


def test_a_section_and_an_annotation_filter_intersect(page, live) -> None:  # type: ignore[no-untyped-def]
    """Every link is built by `filter_url` from the filters already in force,
    so picking a section must narrow the annotation filter rather than replace
    it. Hand-written query strings each dropped a different parameter."""
    annotate(page, live, "demo:1:1", CLAUDE_NOTE)
    annotate(page, live, "demo:1.1:2", CLAUDE_NOTE)
    page.goto(live + UNITS)
    settled(page)

    row_named(page, "@claude").click()
    settled(page)
    assert deck(page) == 2

    # The section rows count what clicking one would give under the filters
    # already on, so this number is a promise made while `@claude` is active.
    row = page.locator(f"{RAIL} .filter-list.sections > li > a").filter(
        has=page.locator('.sec-name:text-is("§1.1")')
    )
    pick_section(page, "1.1")

    assert deck(page) == 1
    assert "on" in (row_named(page, "@claude").get_attribute("class") or ""), (
        "the section link dropped the annotation filter"
    )
    assert row.locator("b").inner_text() == "1/2"


def test_a_command_carries_what_is_on_screen(page, live) -> None:  # type: ignore[no-untyped-def]
    """The panel is worth having only because the scope is already filled in.
    A command that says `--all` while you are looking at one section is a
    command that does something other than what you asked for."""
    page.goto(live + UNITS)
    settled(page)
    pick_section(page, "1.1")

    runs = page.locator("#rail-actions .run code").all_inner_texts()

    assert runs, "the panel offered nothing to copy"
    assert all('--source "demo"' in run for run in runs), runs
    assert all('--section "1.1"' in run for run in runs), runs


def test_clicking_a_command_copies_it_and_stays_put(page, live) -> None:  # type: ignore[no-untyped-def]
    """Copied, never launched: you paste it where you can watch it, so nothing
    writes cards with nobody looking. A button that navigated, or that only
    looked like it had copied, would break that quietly."""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live)
    page.goto(live + UNITS)
    settled(page)
    button = page.locator("#rail-actions .run").first
    wanted = button.get_attribute("data-copy")
    where = page.url

    button.click()

    page.wait_for_selector("#rail-actions .run.copied")
    assert page.evaluate("navigator.clipboard.readText()") == wanted
    assert page.url == where, "the command ran or navigated instead of copying"


def test_the_fold_is_remembered(page, live) -> None:  # type: ignore[no-untyped-def]
    """Every view here is rendered by the server, so a panel folded on one
    click came back open on the next, and it takes the foot of a rail you are
    scrolling."""
    page.goto(live + UNITS)
    settled(page)
    panel = page.locator("#rail-actions")
    assert panel.get_attribute("open") is not None, "it starts open"

    page.locator("#rail-actions > summary").click()
    page.wait_for_timeout(100)
    assert panel.get_attribute("open") is None

    page.goto(live + REVIEW)
    settled(page)

    assert page.locator("#rail-actions").get_attribute("open") is None
    # Put it back: the preference lives in `localStorage`, which outlives this
    # test wherever the browser context does.
    page.evaluate("localStorage.removeItem('anki-forge.commands')")
