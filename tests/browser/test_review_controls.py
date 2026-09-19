"""The controls down the side of a card, each followed through to the file.

Every one of them writes to `cards/<source>/*.md`, and the interesting part is
which of them may disturb an approval. A grading and the augmented flag sit
outside `content_hash` on purpose (invariant 5), so clicking one must leave an
approved card approved; a note is the opposite, and holds the card out of sync
until it is resolved. None of that is visible from the markup alone: the aside
is rendered once by the server and then rebuilt by `review.js` after every
write, so the two have to agree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


def a_card(repo: Path, uid: str, note: str = "") -> str:
    """One draft card of our own, with an optional annotation on it.

    Its own uid per test: the repo behind these tests is shared by the whole
    file, and the deck the fixture lays out is counted by other tests.
    """
    notes = f"\n## notes\n\n{note}\n" if note else ""
    (repo / "cards" / "demo" / f"{uid}-x.md").write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Demo"\nunit: "demo:1:1"\ngist: a card to drive the controls\n---\n\n'
        f"## front\n\n$a$\n\n## back\n\n$b$\n{notes}",
        encoding="utf-8",
    )
    return uid


def open_card(page, live, uid: str) -> None:  # type: ignore[no-untyped-def]
    """Land on one card, freshly rendered, whatever state it is now in.

    `status=all`, because half of these tests approve the card first and a
    draft filter would then be showing a deck it is no longer in.

    `reload` when we are already there: navigating to the URL in the bar is a
    hash navigation, which leaves the document exactly as the last write
    painted it. Reading that back would pass whether or not anything reached
    the file, which is the one thing these tests are for.
    """
    url = f"{live}/review?source=demo&status=all#{uid}"
    if page.url == url:
        page.reload()
    else:
        page.goto(url)
    page.wait_for_selector(f'[data-uid="{uid}"]:not([hidden])')


def read(repo: Path, uid: str) -> str:
    return (repo / "cards" / "demo" / f"{uid}-x.md").read_text(encoding="utf-8")


def chip_says(page, uid: str, selector: str, klass: str, on: bool) -> None:  # type: ignore[no-untyped-def]
    """Wait until a chip carries (or has dropped) a class.

    A write is a round trip: the file changes when the server answers and the
    chip changes when the browser handles that answer. Asserting the class off
    the back of the file asks whether the repaint has happened to run yet,
    which on a loaded machine it has not.
    """
    want = f'[data-uid="{uid}"] {selector}{"." + klass if on else ":not(." + klass + ")"}'
    page.wait_for_selector(want, timeout=5000)


def lands(page, repo: Path, uid: str, wants) -> str:  # type: ignore[no-untyped-def]
    """Poll the card file until `wants(text)` holds, then hand the text back.

    Every control here is a write, and a write is a round trip: the click
    returns immediately and the file changes when the server answers. Waiting a
    fixed time instead asks how loaded the machine is, which is a question with
    a different answer in a full run than in a single file.
    """
    for _ in range(40):
        try:
            text = read(repo, uid)
        except (PermissionError, OSError):
            # The card is written atomically, so a read can land inside the
            # rename. On Windows that raises rather than returning either
            # version of the file.
            text = ""
        if text and wants(text):
            return text
        page.wait_for_timeout(100)
    return read(repo, uid)


def frontmatter(repo: Path, uid: str) -> dict[str, str]:
    """The `---` block as raw strings. Quotes stripped, nothing else parsed:
    the point is what landed in the file, not what a loader makes of it."""
    lines = read(repo, uid).splitlines()
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields


def badge(page, uid: str) -> str:  # type: ignore[no-untyped-def]
    """What the card counts as, as the view says it. `text_content`, because
    the badge is uppercased in CSS and `inner_text` reports what is painted."""
    return page.locator(f'[data-uid="{uid}"] .badge').first.text_content().strip()


def chip(page, uid: str, selector: str):  # type: ignore[no-untyped-def]
    return page.locator(f'[data-uid="{uid}"] {selector}')


def rail(page) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """The two augmentation tallies in the left rail."""
    return {
        name: int(page.locator(f'[data-count="{name}"]').first.text_content().strip())
        for name in ("unaugmented", "augmented")
    }


def test_a_grading_click_leaves_an_approval_standing(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Approving a card is not approving its place in the queue.

    `frequency` is outside `content_hash` (invariant 5) so that it can be set
    during review, which is when you find out that a result is `common` rather
    than `core`. If the click demoted the card, the only way to grade an
    approved one would be to approve it twice.
    """
    _, repo = served
    uid = a_card(repo, "fee001")
    open_card(page, live, uid)
    page.keyboard.press("a")
    lands(page, repo, uid, lambda text: "status: approved" in text)

    stamped = frontmatter(repo, uid)
    assert stamped["status"] == "approved"
    assert stamped["content_hash"], "approving stamps the hash it was approved under"

    # Approving moves the deck on, so come back to the card before clicking.
    open_card(page, live, uid)
    page.locator(f'[data-uid="{uid}"] [data-grade="frequency"]').click()
    lands(page, repo, uid, lambda text: "frequency:" in text)

    graded = frontmatter(repo, uid)
    assert graded["frequency"] == "core"
    assert graded["status"] == "approved"
    # The digest, not merely the status: a grading that changed it would show
    # up later as `edited`, which would be a lie about what was touched.
    assert graded["content_hash"] == stamped["content_hash"]
    assert badge(page, uid) == "approved"


def test_the_augmented_chip_round_trips_into_the_rail(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """`augmented` is the one thing about a card that cannot be read off its
    content: the pass usually adds nothing, so a card it finished and a card it
    never saw are the same file. The chip is therefore the only record there
    is, and taking it off is how you ask for the pass again, which means the
    withdraw direction matters as much as the set one.
    """
    _, repo = served
    uid = a_card(repo, "fee002")
    open_card(page, live, uid)
    before = rail(page)
    assert chip(page, uid, "[data-card-augmented]").text_content().strip() == "not augmented"

    chip(page, uid, "[data-card-augmented]").click()
    lands(page, repo, uid, lambda text: "augmented: true" in text)
    assert frontmatter(repo, uid)["augmented"] == "true"

    # Reloaded rather than read off the page: the chip's write repaints the
    # card, and the rail beside it is only rebuilt by the server.
    open_card(page, live, uid)
    assert chip(page, uid, "[data-card-augmented]").text_content().strip() == "augmented"
    assert rail(page) == {
        "unaugmented": before["unaugmented"] - 1,
        "augmented": before["augmented"] + 1,
    }

    chip(page, uid, "[data-card-augmented]").click()
    lands(page, repo, uid, lambda text: "augmented:" not in text)
    assert "augmented" not in frontmatter(repo, uid), "withdrawn means the key goes"

    open_card(page, live, uid)
    assert chip(page, uid, "[data-card-augmented]").text_content().strip() == "not augmented"
    assert rail(page) == before


def test_the_web_chip_tells_a_refusal_from_no_answer(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Three states, not two. `web: false` on a card is a refusal that has to
    override a grant made source-wide, and no key at all is the absence of a
    decision here, which is what lets a grant made during triage carry through
    to the card written from the unit. Collapsing the two would make the
    refusal unsayable.
    """
    _, repo = served
    uid = a_card(repo, "fee003")
    open_card(page, live, uid)
    web = chip(page, uid, "[data-card-web]")

    web.click()
    lands(page, repo, uid, lambda text: "web: true" in text)
    assert frontmatter(repo, uid)["web"] == "true"

    web.click()
    lands(page, repo, uid, lambda text: "web: false" in text)
    assert frontmatter(repo, uid)["web"] == "false"
    # `own` is how the view says whose answer this is, and it is the only
    # thing separating a refusal from an inherited no on screen.
    chip_says(page, uid, "[data-card-web]", "own", True)

    web.click()
    lands(page, repo, uid, lambda text: "web:" not in text)
    assert "web" not in frontmatter(repo, uid)
    chip_says(page, uid, "[data-card-web]", "own", False)


def test_a_note_holds_an_approved_card_rather_than_withdrawing_it(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """An open note takes the card out of sync, and that is all it does.

    Nothing rewrites the file, so `status: approved` has to stay put while the
    view shows a draft: were the approval actually withdrawn, resolving the
    note would cost a re-review and a fresh hash for a question that turned out
    to be nothing. The banner exists because "draft" on its own reads as work
    lost.
    """
    _, repo = served
    uid = a_card(repo, "fee004")
    open_card(page, live, uid)
    page.keyboard.press("a")
    lands(page, repo, uid, lambda text: "status: approved" in text)
    assert frontmatter(repo, uid)["status"] == "approved"

    open_card(page, live, uid)
    page.keyboard.press("n")
    page.wait_for_selector("#prompt[open]")
    page.keyboard.type("is the transpose the right way round")
    page.keyboard.press("Enter")
    lands(page, repo, uid, lambda text: "right way round" in text)
    # The badge is painted from the same response that wrote the file, so it
    # is worth one more beat before reading it off the page.
    page.wait_for_selector(f'[data-uid="{uid}"] .held')

    assert badge(page, uid) == "draft"
    assert "back in the draft pile" in page.inner_text(f'[data-uid="{uid}"] .held')
    assert frontmatter(repo, uid)["status"] == "approved", "held, not withdrawn"

    page.locator(f'[data-uid="{uid}"] [data-resolve]').click()
    lands(page, repo, uid, lambda text: "right way round" not in text)
    page.wait_for_selector(f'[data-uid="{uid}"] .held', state="detached")

    assert badge(page, uid) == "approved"
    assert page.locator(f'[data-uid="{uid}"] .held').count() == 0
    card = read(repo, uid)
    assert "is the transpose" not in card, "resolving deletes the line"
    assert "status: approved" in card, "and the approval was never re-stamped"


def test_rewording_a_note_leaves_it_open(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Editing is the half of resolving that keeps the question alive.

    A reworded note is still a note, so the card stays held and the row stays
    on screen: an edit that quietly unblocked sync would push a card to Anki
    with its question unanswered. The row is also rebuilt by `review.js` after
    every write, so the buttons have to survive the next click anywhere on the
    card as well as this one.
    """
    _, repo = served
    uid = a_card(repo, "fee005", "@claude chekc the sign on the second term")
    open_card(page, live, uid)
    page.keyboard.press("a")
    lands(page, repo, uid, lambda text: "status: approved" in text)
    open_card(page, live, uid)

    page.locator(f'[data-uid="{uid}"] [data-edit-note]').click()
    page.wait_for_selector("#prompt[open]")
    page.fill("#prompt-input", "@claude check the sign on the second term")
    page.keyboard.press("Enter")
    card = lands(page, repo, uid, lambda text: "chekc" not in text)
    assert "@claude check the sign on the second term" in card
    assert "chekc" not in card, "the line was replaced, not added to"
    assert card.count("@claude") == 1, "and it kept its place rather than gaining one"

    assert badge(page, uid) == "draft"
    assert "back in the draft pile" in page.inner_text(f'[data-uid="{uid}"] .held')
    assert frontmatter(repo, uid)["status"] == "approved"

    # Any write that comes back with a card payload rebuilds the rows.
    page.locator(f'[data-uid="{uid}"] [data-grade="derivation"]').click()
    lands(page, repo, uid, lambda text: "derivation:" in text)
    assert page.locator(f'[data-uid="{uid}"] [data-edit-note]').count() == 1
    assert page.locator(f'[data-uid="{uid}"] [data-resolve]').count() == 1


def test_undo_after_a_resolve_puts_the_line_back(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """Resolving deletes, and for a note imported from Anki the file is the
    only copy: `feedback` erases the comment as it takes it. Without undo this
    is the one action in the app that destroys something outright, so the
    server sends the line back and `z` has to be able to write it again.
    """
    _, repo = served
    uid = a_card(repo, "fee006", "@me decide whether this is two cards")
    open_card(page, live, uid)

    page.locator(f'[data-uid="{uid}"] [data-resolve]').click()
    assert "@me" not in lands(page, repo, uid, lambda text: "@me" not in text)
    assert page.locator(f'[data-uid="{uid}"] .annotation').count() == 0

    page.keyboard.press("z")
    page.wait_for_timeout(1000)

    assert "@me decide whether this is two cards" in read(repo, uid)
    assert page.locator(f'[data-uid="{uid}"] .annotation').count() == 1
