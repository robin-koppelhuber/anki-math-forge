"""The keyboard dialogs: a new unit in triage, front and back in review,
and the theme switch in the top bar.

Each is a key, a form and a write, and the endpoint tests cover the write.
What only a browser shows is whether the key opens the form, whether the
form submits from the keyboard, and whether the page lands somewhere useful.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")


def test_plus_opens_a_unit_and_enter_files_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    _, repo = served
    page.goto(f"{live}/units?project=demo&state=all")
    page.wait_for_selector(".unit.item:not([hidden])")

    page.keyboard.press("+")
    page.wait_for_selector("[data-new-unit-dialog][open]")
    page.keyboard.type("Hadamard inequality")
    page.keyboard.press("Tab")
    page.keyboard.type("the determinant bound")
    page.keyboard.press("Enter")

    page.wait_for_url("**/units?project=demo&state=new#demo%3Ahadamard-inequality")
    ledger = (repo / "projects" / "demo" / "units.jsonl").read_text(encoding="utf-8")
    added = [json.loads(line) for line in ledger.splitlines() if "hadamard" in line]
    assert len(added) == 1 and added[0]["gist"] == "the determinant bound"
    assert not page.complaints, page.complaints


def test_shift_e_edits_the_card_and_lands_back_on_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    _, repo = served
    page.goto(f"{live}/review?project=demo&status=draft#ccc333")
    page.wait_for_selector('[data-uid="ccc333"]:not([hidden])')

    page.keyboard.press("Shift+E")
    page.wait_for_selector("[data-card-edit-dialog][open]")
    assert page.input_value("[data-card-edit-form] [name=front]") == "$a$"
    page.fill("[data-card-edit-form] [name=back]", "$b + c$")
    page.check("[data-card-edit-form] [name=ask]")
    page.keyboard.press("Control+Enter")

    page.wait_for_selector('[data-uid="ccc333"]:not([hidden])')
    page.wait_for_function("!document.querySelector('[data-card-edit-dialog]').open")
    card = (repo / "cards" / "demo" / "ccc333-x.md").read_text(encoding="utf-8")
    assert "$b + c$" in card
    assert "@claude check my manual edit" in card
    assert not page.complaints, page.complaints


def test_the_note_is_off_unless_ticked(page, live, served) -> None:  # type: ignore[no-untyped-def]
    _, repo = served
    page.goto(f"{live}/review?project=demo&status=draft#ccc333")
    page.wait_for_selector('[data-uid="ccc333"]:not([hidden])')

    page.keyboard.press("Shift+E")
    page.wait_for_selector("[data-card-edit-dialog][open]")
    page.fill("[data-card-edit-form] [name=back]", "$d$")
    page.click("[data-card-edit-form] button[value=ok]")
    page.wait_for_function("!document.querySelector('[data-card-edit-dialog]').open")

    card = (repo / "cards" / "demo" / "ccc333-x.md").read_text(encoding="utf-8")
    assert "$d$" in card and "@claude" not in card


def test_the_theme_switch_cycles_and_is_remembered(page, live) -> None:  # type: ignore[no-untyped-def]
    page.goto(f"{live}/review?project=demo")
    root = "document.documentElement.dataset.theme || 'system'"
    assert page.evaluate(root) == "system"

    page.click("[data-theme-cycle]")
    assert page.evaluate(root) == "light"
    page.click("[data-theme-cycle]")
    assert page.evaluate(root) == "dark"

    page.reload()
    assert page.evaluate(root) == "dark", "restored before the page paints"
    page.click("[data-theme-cycle]")
    assert page.evaluate(root) == "system"
    page.reload()
    assert page.evaluate(root) == "system"
