"""The card's aside as panels: folded, moved, remembered; and `k` on a filter.

A browser test because none of it is markup: whether a panel is folded is a
class a script puts on after reading storage, and a drag is a gesture.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="needs the `browser` extra")

from playwright.sync_api import Page, expect

CARD = ".item:not([hidden])"


def order(page: Page) -> list[str]:
    return page.eval_on_selector_all(
        f"{CARD} [data-panels] > .panel", "els => els.map(e => e.dataset.panel)"
    )


def open_review(page: Page, live: str, query: str = "status=all") -> None:
    page.goto(f"{live}/review?project=demo&{query}")
    page.wait_for_selector(f"{CARD} [data-panels]")


def test_a_panel_folds_and_stays_folded(page: Page, live) -> None:
    open_review(page, live)
    details = page.locator(f'{CARD} [data-panel="details"]')
    expect(details).to_have_class("panel folded")

    details.locator(".panel-toggle").click()
    expect(details).not_to_have_class("panel folded")
    page.reload()
    page.wait_for_selector(f"{CARD} [data-panels]")
    expect(page.locator(f'{CARD} [data-panel="details"]')).not_to_have_class("panel folded")

    page.locator(f'{CARD} [data-panel="notes"] .panel-toggle').click()
    page.reload()
    page.wait_for_selector(f"{CARD} [data-panels]")
    expect(page.locator(f'{CARD} [data-panel="notes"]')).to_have_class("panel folded")
    assert not page.complaints, page.complaints


def test_a_panel_moves_with_the_keyboard_and_stays_moved(page: Page, live) -> None:
    open_review(page, live)
    before = order(page)
    assert before[0] == "notes" and before[1] == "changes", before

    page.locator(f'{CARD} [data-panel="notes"] .panel-toggle').focus()
    page.keyboard.press("Alt+ArrowDown")
    assert order(page)[:2] == ["changes", "notes"]

    page.reload()
    page.wait_for_selector(f"{CARD} [data-panels]")
    assert order(page)[:2] == ["changes", "notes"], "remembered, and on every card"


def test_a_panel_moves_by_dragging_its_grip(page: Page, live) -> None:
    """The drag events are dispatched rather than made with the mouse: a real
    HTML5 drag is the one gesture Playwright's mouse cannot be trusted with,
    and what is under test is what the page does when they arrive."""
    open_review(page, live)
    first = order(page)[0]
    last = order(page)[-1]

    page.evaluate(
        """([card, first, last]) => {
          const root = document.querySelector(card);
          const grip = root.querySelector(`[data-panel="${first}"] .panel-grip`);
          const target = root.querySelector(`[data-panel="${last}"]`);
          const data = new DataTransfer();
          const fire = (el, type, y) =>
            el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true,
                                                   dataTransfer: data, clientY: y }));
          const box = target.getBoundingClientRect();
          fire(grip, "dragstart", box.top);
          fire(target, "dragover", box.bottom - 2);
          fire(target, "dragend", box.bottom - 2);
        }""",
        [CARD, first, last],
    )

    assert order(page)[-1] == first, order(page)
    page.reload()
    page.wait_for_selector(f"{CARD} [data-panels]")
    assert order(page)[-1] == first, "and it is remembered"


def test_k_does_not_walk_back_onto_a_card_the_filter_no_longer_shows(page: Page, live) -> None:
    """On the draft list `k` landed on cards approved a moment ago. Undo is the
    way back to one."""
    open_review(page, live, "status=draft")
    page.keyboard.press("a")
    page.wait_for_function("document.querySelector('#position').textContent.startsWith('2 /')")

    page.keyboard.press("k")

    expect(page.locator("#position")).to_contain_text("2 /")
    expect(page.locator(".toast, [data-toast]").last).to_contain_text("start of the list")
