"""Notes dumped at a project, waiting for `/sort-notes` (ROADMAP §20).

Two ways to place one: proposed, the default, or by modifying the existing
cards (` · write` on its heading). The sorting is an agent's; what is tested here
is the file both modes are recorded in and the page that edits it.

The setup stage appends what you type to `projects/<name>/inbox.md`; the
command that sorts it is a slash command, offered once something waits.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import inbox
from anki_math_forge.app import create_app, runs
from anki_math_forge.config import Config, ConfigError


def test_a_note_is_appended_under_a_dated_heading(config: Config) -> None:
    assert inbox.add(config, "demo", "the bound needs independence") == 1
    assert inbox.add(config, "demo", "  a second thought  ") == 2

    text = inbox.path_for(config, "demo").read_text(encoding="utf-8")
    assert text.startswith("# Inbox")
    assert text.count("\n## ") == 2
    assert "the bound needs independence" in text and "a second thought\n" in text


def test_an_emptied_dump_is_not_counted(config: Config) -> None:
    """`/sort-notes` deletes a dump once it has placed it; a heading left
    with nothing under it is not waiting."""
    inbox.add(config, "demo", "one")
    path = inbox.path_for(config, "demo")
    path.write_text(path.read_text(encoding="utf-8").replace("one", ""), encoding="utf-8")

    assert inbox.waiting(config, "demo") == 0


@pytest.mark.parametrize("text", ["", "   "])
def test_nothing_is_refused(config: Config, text: str) -> None:
    with pytest.raises(ConfigError):
        inbox.add(config, "demo", text)


def test_the_page_adds_and_then_offers_the_command(config: Config) -> None:
    client = TestClient(create_app(config))
    page = client.get("/setup?project=demo").text
    assert 'data-pane="inbox"' in page and "data-inbox" in page
    assert 'data-copy="/sort-notes' not in page, "nothing to sort yet"

    answer = client.post("/api/projects/demo/inbox", json={"text": "check card 4b2e1c"})

    assert answer.json() == {"ok": True, "waiting": 1}
    page = client.get("/setup?project=demo").text
    assert 'data-copy="/sort-notes --project' in page
    assert "1 unsorted" in page


def test_the_offer_is_a_slash_command_and_only_when_something_waits() -> None:
    quiet = runs.propose("inbox", runs.Ambient(project="demo"))
    waiting = runs.propose("inbox", runs.Ambient(project="demo", inbox=3))

    assert not any("/sort-notes" in row["run"] for row in quiet)
    row = next(row for row in waiting if "/sort-notes" in row["run"])
    assert row["kind"] == "claude", "copied, never run from the page"
    assert row["label"] == "/sort-notes" and row["detail"] == "3 unsorted"


SORTED = """# Notes to sort

## 2026-10-02 10:00 · sorted

Jensen for conditional expectations.

### where it went
- new unit `demo:conditional-jensen`: Jensen, conditionally
- @me on card `4b2e1c` (Hoeffding): the conditions miss independence

## 2026-10-03 14:02

Something not yet sorted.
"""


def test_a_sorted_dump_keeps_its_text_and_says_where_it_went(config: Config) -> None:
    inbox.path_for(config, "demo").write_text(SORTED, encoding="utf-8")

    newest, older = inbox.dumps(config, "demo")

    assert (newest.state, newest.text) == ("waiting", "Something not yet sorted.")
    assert older.state == "sorted"
    assert older.text == "Jensen for conditional expectations."
    assert older.units == ("demo:conditional-jensen",)
    assert older.cards == ("4b2e1c",)
    assert inbox.waiting(config, "demo") == 1


def test_a_dump_is_unsorted_or_sorted_and_a_sorted_one_can_go_back(config: Config) -> None:
    """Two states and nothing else. An older file may say `done`, which is
    read as sorted; putting a dump back keeps its text and its brief."""
    old = SORTED.replace("· sorted", "· done")
    inbox.path_for(config, "demo").write_text(old, encoding="utf-8")
    assert inbox.dumps(config, "demo")[1].state == "sorted"
    client = TestClient(create_app(config))

    answer = client.post(
        "/api/projects/demo/inbox/state", json={"stamp": "2026-10-02 10:00", "state": "waiting"}
    )

    assert answer.status_code == 200
    text = inbox.path_for(config, "demo").read_text(encoding="utf-8")
    assert "## 2026-10-02 10:00\n" in text, "no state word on the heading: it waits"
    assert "Jensen for conditional expectations." in text, "nothing is deleted"
    assert inbox.waiting(config, "demo") == 2
    nope = {"stamp": "2026-10-02 10:00", "state": "nope"}
    bad = client.post("/api/projects/demo/inbox/state", json=nope)
    assert bad.status_code == 400


def test_two_dumps_in_one_minute_get_their_own_headings(config: Config) -> None:
    inbox.add(config, "demo", "one")
    inbox.add(config, "demo", "two")

    stamps = [d.stamp for d in inbox.dumps(config, "demo")]
    assert len(set(stamps)) == 2


def test_the_runs_button_is_there_before_anything_has_run(config: Config) -> None:
    """Hidden until the first run, it was a window nobody could find."""
    page = TestClient(create_app(config)).get("/units?project=demo&state=all").text

    button = page[page.index("data-runs-open") - 60 : page.index("data-runs-open") + 120]
    assert "hidden" not in button


WRITTEN = """# Inbox

## 2026-10-02 10:00 · write · sorted

Hoeffding needs independence.

### where it went
- edited card `4b2e1c` (Hoeffding): ## conditions now require independence
- new unit `demo:conditional-jensen`, queued for a card: Jensen → card `7d1e02`

## 2026-10-03 14:02 · write

Something to write in.
"""


def test_a_dump_says_how_it_is_placed(config: Config) -> None:
    inbox.add(config, "demo", "the bound needs independence", mode="write")
    inbox.add(config, "demo", "a vaguer thought")
    inbox.add(config, "demo", "you judge this one", mode="both")

    text = inbox.path_for(config, "demo").read_text(encoding="utf-8")
    both, vaguer, written = inbox.dumps(config, "demo")
    assert text.count(" · write") == 1 and text.count(" · both") == 1
    assert (written.mode, vaguer.mode, both.mode) == ("write", "propose", "both")
    assert inbox.waiting(config, "demo") == 3, "however it is placed, it waits the same"


def test_an_unknown_mode_is_refused(config: Config) -> None:
    with pytest.raises(ConfigError, match="propose"):
        inbox.add(config, "demo", "x", mode="yolo")


def test_the_mode_survives_the_state(config: Config) -> None:
    """Marking a dump that modifies cards keeps the word that says how it was
    placed: the brief under it reads differently, and so does the page."""
    inbox.path_for(config, "demo").write_text(WRITTEN, encoding="utf-8")

    inbox.mark(config, "demo", "2026-10-02 10:00", "waiting")
    inbox.mark(config, "demo", "2026-10-03 14:02", "sorted")

    text = inbox.path_for(config, "demo").read_text(encoding="utf-8")
    assert "## 2026-10-02 10:00 · write\n" in text
    assert "## 2026-10-03 14:02 · write · sorted" in text
    assert all(d.mode == "write" for d in inbox.dumps(config, "demo"))


def test_a_typed_heading_reads_in_either_order(config: Config) -> None:
    inbox.path_for(config, "demo").write_text(
        "# Inbox\n\n## 2026-10-02 10:00 · sorted · both\n\nby hand\n", encoding="utf-8"
    )

    (dump,) = inbox.dumps(config, "demo")

    assert (dump.stamp, dump.state, dump.mode) == ("2026-10-02 10:00", "sorted", "both")


def test_the_old_word_for_both_is_still_read(config: Config) -> None:
    """`both` was called `decide` first, and a heading typed then still works."""
    inbox.path_for(config, "demo").write_text(
        "# Inbox\n\n## 2026-10-02 10:00 · decide\n\nby hand\n", encoding="utf-8"
    )

    assert inbox.dumps(config, "demo")[0].mode == "both"


def test_only_a_waiting_dump_changes_how_it_is_placed(config: Config) -> None:
    inbox.path_for(config, "demo").write_text(WRITTEN, encoding="utf-8")

    inbox.set_mode(config, "demo", "2026-10-03 14:02", "both")

    waiting = inbox.dumps(config, "demo")[0]
    assert (waiting.stamp, waiting.mode) == ("2026-10-03 14:02", "both")
    with pytest.raises(ConfigError, match="waiting"):
        inbox.set_mode(config, "demo", "2026-10-02 10:00", "propose")


def test_the_page_offers_two_boxes_and_both_is_the_two_together(config: Config) -> None:
    """Not a third option: propose and modify existing cards, each a box, and
    both ticked is what the sorter chooses per piece."""
    client = TestClient(create_app(config))
    page = client.get("/setup?project=demo").text
    form = page[page.index("data-inbox") : page.index("</form>", page.index("data-inbox"))]
    box = {m: form[form.index(f'data-mode="{m}"') :][:60] for m in ("propose", "write")}
    assert "checked" in box["propose"], "proposing is the default"
    assert "checked" not in box["write"]
    assert "let it decide" not in page and 'value="both"' not in page, "no third choice"
    assert "modify existing cards" in form and "write in" not in page

    client.post("/api/projects/demo/inbox", json={"text": "write me in", "mode": "write"})
    page = client.get("/setup?project=demo").text
    assert "data-dump-mode" in page, "still boxes while it waits"

    stamp = inbox.dumps(config, "demo")[0].stamp
    answer = client.post("/api/projects/demo/inbox/mode", json={"stamp": stamp, "mode": "both"})
    assert answer.status_code == 200
    assert inbox.dumps(config, "demo")[0].mode == "both"
    page = client.get("/setup?project=demo").text
    waiting = page[page.index("data-dump-mode") :][:400]
    assert waiting.count("checked") == 2, "both boxes ticked"
    bad = client.post("/api/projects/demo/inbox/mode", json={"stamp": stamp, "mode": "nope"})
    assert bad.status_code == 400


def test_a_dump_leads_to_where_it_is_settled(config: Config) -> None:
    """An edit is settled under "changed since decided", whoever made it; a
    proposal is an open `@me` note."""
    inbox.path_for(config, "demo").write_text(WRITTEN, encoding="utf-8")

    page = TestClient(create_app(config)).get("/setup?project=demo").text

    assert "changed=yes" in page, "its edits are under changed since decided"
    assert "annotated=me" not in page, "a written-in dump proposes nothing"
    assert inbox.dumps(config, "demo")[1].cards == ("4b2e1c", "7d1e02")


def test_the_inbox_is_an_unsorted_list_and_a_sorted_one(config: Config) -> None:
    """Two collapsible lists and no `done`. Unsorted is where you work, so it
    starts open; sorted starts shut, with its count in the summary."""
    inbox.path_for(config, "demo").write_text(WRITTEN, encoding="utf-8")

    page = TestClient(create_app(config)).get("/setup?project=demo").text

    lists = dict(re.findall(r'<details class="dump-list" data-dumps="(\w+)"( open)?>', page))
    assert lists == {"unsorted": " open", "sorted": ""}
    assert re.search(r'unsorted <span class="dump-count">1<', page)
    assert re.search(r'sorted <span class="dump-count">1<', page)
    assert 'data-dump-state="done"' not in page and ">read again<" not in page
    sorted_list = page[page.index('data-dumps="sorted"') :]
    assert 'data-dump-state="waiting"' in sorted_list, "put back to sort again"
    assert 'data-dump-state="waiting"' not in page[: page.index('data-dumps="sorted"')]


def test_a_sorted_dump_lists_where_each_piece_went_with_links(config: Config) -> None:
    """A dump can touch forty cards, so the places are a collapsible list of
    links under it and not a row of chips."""
    inbox.path_for(config, "demo").write_text(WRITTEN, encoding="utf-8")

    page = TestClient(create_app(config)).get("/setup?project=demo").text

    went = page[page.index('<details class="dump-went">') :]
    assert "<summary>1 unit · 2 cards</summary>" in went
    assert "/review?project=demo&amp;status=all#4b2e1c" in went or "status=all#4b2e1c" in went
    assert "#7d1e02" in went and "#demo%3Aconditional-jensen" in went
    assert 'class="chip"' in went, "the filters for what it changed stay, once"


def test_a_brief_line_links_the_cards_and_units_it_names() -> None:
    from anki_math_forge.app import dump_line

    html = str(dump_line("edited card `4b2e1c` (Hoeffding); new unit `demo:a-b` & `code`", "demo"))

    assert '<a href="' in html and "#4b2e1c" in html and "#demo%3Aa-b" in html
    assert "<code>code</code>" in html and "<a" not in html.split("&amp;")[1], "only ids link"
