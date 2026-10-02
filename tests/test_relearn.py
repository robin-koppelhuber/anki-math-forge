"""`relearn:`: how much of a changed card you have to learn again (ROADMAP §17).

Whoever changes a card you have already studied makes the call; `anki push`
carries it out in Anki once, and takes the key off the file so the next push
does not do it again. Outside `content_hash`, so none of that un-approves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import check, model, sync
from anki_math_forge.config import Config
from conftest import FakeAnki


def studied(config: Config, card_path: Path) -> FakeAnki:
    """The card approved, pushed, and reviewed at least once in Anki."""
    card = model.load(card_path)
    card.approve()
    card.save()
    anki = FakeAnki()
    sync.run(config, client=anki)
    for row in anki.cards.values():
        row["type"] = 2
    return anki


def ask(card_path: Path, how: str, *, edit: bool = True) -> None:
    """A changed card, re-approved, with the call made on it."""
    card = model.load(card_path)
    if edit:
        card.set_section("prose", "A new reading of it.")
    card.frontmatter["relearn"] = how
    card.approve()
    card.save()


@pytest.mark.parametrize(
    "how,done",
    [("slightly", "due 0"), ("more", "relearning"), ("reset", "forgotten")],
)
def test_each_answer_is_one_call_in_anki(
    config: Config, card_path: Path, how: str, done: str
) -> None:
    anki = studied(config, card_path)
    ask(card_path, how)

    report = sync.run(config, client=anki)

    assert [row.get("relearned") for row in anki.cards.values()] == [done]
    assert report.count("relearn") == 1
    assert "relearn" in report.summary()


def test_the_key_comes_off_once_anki_has_it(config: Config, card_path: Path) -> None:
    """Or every push would do it again."""
    anki = studied(config, card_path)
    ask(card_path, "more")
    sync.run(config, client=anki)
    for row in anki.cards.values():
        row.pop("relearned")

    again = sync.run(config, client=anki)

    card = model.load(card_path)
    assert "relearn" not in card.frontmatter
    assert card.effective_status == "approved", "taking it off is not an edit"
    assert again.count("relearn") == 0
    assert all("relearned" not in row for row in anki.cards.values())


def test_the_key_is_not_part_of_the_content(card_path: Path) -> None:
    """Setting it on an approved card does not take the approval back."""
    card = model.load(card_path)
    card.approve()
    card.save()

    ask(card_path, "slightly", edit=False)

    assert model.load(card_path).demotion == ""


def test_a_card_never_studied_has_nothing_to_relearn(config: Config, card_path: Path) -> None:
    card = model.load(card_path)
    card.approve()
    card.save()
    anki = FakeAnki()
    sync.run(config, client=anki)
    ask(card_path, "reset")

    report = sync.run(config, client=anki)

    assert all("relearned" not in row for row in anki.cards.values())
    assert "nothing to do" in next(o.detail for o in report.outcomes if o.action == "relearn")
    assert "relearn" not in model.load(card_path).frontmatter


def test_a_dry_run_says_what_it_would_do_and_keeps_the_key(
    config: Config, card_path: Path
) -> None:
    anki = studied(config, card_path)
    ask(card_path, "more")

    report = sync.run(config, client=anki, dry_run=True)

    assert any(o.action == "relearn" and "more" in o.detail for o in report.outcomes)
    assert all("relearned" not in row for row in anki.cards.values())
    assert model.load(card_path).relearn == "more"


def test_a_draft_is_not_relearned(config: Config, card_path: Path) -> None:
    """Only what reaches Anki. The call waits with the card for review."""
    anki = studied(config, card_path)
    card = model.load(card_path)
    card.set_section("prose", "Changed, not yet re-read.")
    card.frontmatter["relearn"] = "more"
    card.save()

    sync.run(config, client=anki)

    assert all("relearned" not in row for row in anki.cards.values())
    assert model.load(card_path).relearn == "more"


def test_an_unknown_answer_is_a_check_error(config: Config, card_path: Path) -> None:
    card = model.load(card_path)
    card.frontmatter["relearn"] = "a-lot"
    card.save()

    found = check.check_card(model.load(card_path), config)

    assert "relearn-unknown" in [f.code for f in found if f.level == check.ERROR]


def test_the_review_page_can_overrule_the_call(config: Config, card_path: Path) -> None:
    """The writer makes it; you may disagree while reading the card."""
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    client = TestClient(create_app(config))
    assert 'data-grade="relearn"' in client.get("/review").text

    mtime = str(card_path.stat().st_mtime_ns)
    out = client.post(
        "/api/cards/7f3a2b/grade", json={"key": "relearn", "value": "more", "mtime": mtime}
    )
    assert out.status_code == 200
    assert out.json()["card"]["relearn"] == "more"
    assert model.load(card_path).relearn == "more"

    refused = client.post(
        "/api/cards/7f3a2b/grade",
        json={"key": "relearn", "value": "a-lot", "mtime": out.json()["card"]["mtime"]},
    )
    assert refused.status_code == 400
