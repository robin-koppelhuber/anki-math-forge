"""The two coarsest filters in the rail: which source, and which ask.

They answer different questions and combine differently. Sources take the
**union**, because a cluster of related papers is read as one deck. Asks
take the **intersection**, because an ask states what the deck should
contain and two of them ask what is under both.

Both views carry both, and `/api/counts` answers for the same query string:
the mini diagram is repainted from it seconds after the page settles, so a
filter the endpoint does not read shows up as the numbers moving on their
own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.app import create_app

TWO_ASKS = """# What this deck is for

## containers

choosing between them, not the full API

- vector erase-remove
- shared entry

## algorithms

what they assume of a range

- shared entry
- lower bound
"""


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def client(repo: Path) -> TestClient:
    return TestClient(create_app(config_mod.load(repo)))


def a_repo(
    repo: Path,
    *,
    sources: str = "",
    outline: str = TWO_ASKS,
    units: list[dict[str, object]] | None = None,
) -> Path:
    run(repo, "project", "cpp", "--title", "Modern C++", "--deck", "Cpp")
    folder = repo / "projects" / "cpp"
    if outline:
        (folder / "topics.md").write_text(outline, encoding="utf-8")
    if sources:
        with (folder / "project.toml").open("a", encoding="utf-8") as out:
            out.write("\n" + sources)
    if units is not None:
        (folder / "units.jsonl").write_text(
            "".join(json.dumps(u) + "\n" for u in units), encoding="utf-8"
        )
    return folder


def a_unit(slug: str, document: str = "b.pdf") -> dict[str, object]:
    return {
        "id": f"cpp:{slug}",
        "state": "new",
        "locator": {"document": document, "page": 1},
    }


TWO_BOOKS = (
    '[[sources]]\nkey = "book"\nfiles = ["b.pdf"]\ntitle = "A tour"\n\n'
    '[[sources]]\nkey = "other"\nfiles = ["o.pdf"]\ntitle = "The other one"\n'
)


def shown(page: str) -> list[str]:
    return sorted(set(re.findall(r'class="unit item" data-id="([^"]+)"', page)))


def rows_of(page: str, group: str) -> list[tuple[str, str]]:
    """Every row of one pick control, as (key, count)."""
    block = re.search(rf'<div class="pick" id="{group}">(.*?)</div>', page, re.S)
    if block is None:
        return []
    return re.findall(r'data-pick="([^"]+)".*?<b>(\d+)</b>', block.group(1), re.S)


# -- sources take the union -------------------------------------------------


def test_two_sources_show_everything_either_holds(repo: Path) -> None:
    folder = a_repo(
        repo,
        sources=TWO_BOOKS,
        units=[a_unit("one", "b.pdf"), a_unit("two", "o.pdf")],
    )
    (folder / "b.pdf").write_bytes(b"%PDF-1.4\n")
    (folder / "o.pdf").write_bytes(b"%PDF-1.4\n")
    at = client(repo)

    both = at.get("/units?project=cpp&state=all&document=book,other").text

    assert shown(both) == ["cpp:one", "cpp:two"]
    assert shown(at.get("/units?project=cpp&state=all&document=book").text) == ["cpp:one"]
    assert ">or<" in both, "and the word between the chips says so"


def test_one_source_is_the_project_and_needs_no_group(repo: Path) -> None:
    """A row that selects what is already on screen is not a filter."""
    folder = a_repo(
        repo,
        sources='[[sources]]\nkey = "book"\nfiles = ["b.pdf"]\n',
        units=[a_unit("one")],
    )
    (folder / "b.pdf").write_bytes(b"%PDF-1.4\n")

    page = client(repo).get("/units?project=cpp&state=all").text

    assert ">sources<" not in page


# -- asks take the intersection ---------------------------------------------


def test_two_asks_leave_what_is_under_both(repo: Path) -> None:
    a_repo(
        repo,
        units=[a_unit("vector-erase-remove"), a_unit("shared-entry"), a_unit("lower-bound")],
    )
    at = client(repo)

    one = at.get("/units?project=cpp&state=all&topic=containers").text
    both = at.get("/units?project=cpp&state=all&topic=containers,algorithms").text

    assert shown(one) == ["cpp:shared-entry", "cpp:vector-erase-remove"]
    assert shown(both) == ["cpp:shared-entry"], "the entry both outlines list"
    assert ">and<" in both, "and the word between the chips says so"


def test_an_ask_with_no_outline_says_so_before_you_click(repo: Path) -> None:
    """It selects nothing, which is honest and useless. The row carries the
    reason, because a 0 has two causes and only one of them is fixable."""
    a_repo(repo, outline="# what for\n\n## containers\n\nan ask and no list\n",
           units=[a_unit("something")])

    page = client(repo).get("/units?project=cpp&state=all").text

    assert rows_of(page, "topics") == [("containers", "0")]
    assert "no outline yet, so no unit joins to it" in page


def test_two_headings_that_slugify_alike_are_one_filter(repo: Path) -> None:
    """`slugify` lowercases and cuts at forty characters, so two headings can
    land on one slug. Stopping at the first made the second row an alias."""
    a_repo(
        repo,
        outline="# what for\n\n## Containers\n\n- alpha\n\n## containers\n\n- beta\n",
        units=[a_unit("alpha"), a_unit("beta")],
    )

    page = client(repo).get("/units?project=cpp&state=all&topic=containers").text

    assert shown(page) == ["cpp:alpha", "cpp:beta"], "both outlines, one slug"


# -- the rail adds up to the deck -------------------------------------------


def test_a_document_no_source_claims_still_gets_a_row(repo: Path) -> None:
    """A Zotero unit names the attachment; a work declares the item. With two
    works holding a document nothing matches the two up, and the rows read
    zero over a deck that was full."""
    a_repo(
        repo,
        sources=(
            '[[sources]]\nzotero = "ITEMA"\ntitle = "Paper A"\n\n'
            '[[sources]]\nzotero = "ITEMB"\ntitle = "Paper B"\n'
        ),
        units=[a_unit("a1", "ATTA"), a_unit("a2", "ATTA"), a_unit("b1", "ATTB")],
    )
    at = client(repo)

    page = at.get("/units?project=cpp&state=all").text
    rows = rows_of(page, "sources")

    assert sum(int(n) for _, n in rows) == 3, "every unit on screen is in a row"
    assert ("ATTA", "2") in rows
    assert shown(at.get("/units?project=cpp&state=all&document=ATTA").text) == [
        "cpp:a1",
        "cpp:a2",
    ]


def test_naming_the_attachments_gives_the_rows_their_titles(repo: Path) -> None:
    a_repo(
        repo,
        sources=(
            '[[sources]]\nzotero = "ITEMA"\ntitle = "Paper A"\nattachments = ["ATTA"]\n\n'
            '[[sources]]\nzotero = "ITEMB"\ntitle = "Paper B"\nattachments = ["ATTB"]\n'
        ),
        units=[a_unit("a1", "ATTA"), a_unit("b1", "ATTB")],
    )

    page = client(repo).get("/units?project=cpp&state=all").text

    assert rows_of(page, "sources") == [("ITEMA", "1"), ("ITEMB", "1")]


def test_a_filter_with_no_row_left_can_still_be_taken_off(repo: Path) -> None:
    """Hiding the group hid the way out: an empty deck and nothing on screen
    saying why."""
    a_repo(repo, outline="", units=[a_unit("one")])

    page = client(repo).get("/units?project=cpp&state=all&topic=gone").text

    assert ">topics<" in page
    assert "pick-chip f-topic" in page


# -- a card is not one unit -------------------------------------------------


def a_card(repo: Path, uid: str, units: str) -> None:
    folder = repo / "cards" / "cpp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}-x.md").write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Modern C++"\nunit: {units}\n---\n\n## front\n\n$a$\n\n## back\n\n$b$\n',
        encoding="utf-8",
    )


def test_a_card_merged_from_two_units_is_under_both_asks(repo: Path) -> None:
    """`unit:` takes a list, which is how a display equation the segmenter cut
    in three becomes one card. Read off the first alone, the card vanished
    from the second ask while its own unit still showed there."""
    a_repo(repo, units=[a_unit("vector-erase-remove"), a_unit("lower-bound")])
    a_card(repo, "aa11bb", '["cpp:vector-erase-remove", "cpp:lower-bound"]')
    at = client(repo)

    def cards(url: str) -> list[str]:
        return sorted(set(re.findall(r'class="card item" data-uid="([^"]+)"', at.get(url).text)))

    assert cards("/review?project=cpp&status=all&topic=containers") == ["aa11bb"]
    assert cards("/review?project=cpp&status=all&topic=algorithms") == ["aa11bb"]


# -- the counts endpoint answers the same question --------------------------


def test_the_poll_reads_the_same_filters_the_page_drew(repo: Path) -> None:
    """The diagram is repainted from `/api/counts` a few seconds after the
    page settles, so a filter it does not read showed as the numbers moving
    on their own."""
    a_repo(
        repo,
        units=[a_unit("vector-erase-remove"), a_unit("shared-entry"), a_unit("lower-bound")],
    )
    at = client(repo)

    def polled(query: str) -> int:
        got = at.get(f"/api/counts?project=cpp&counts_scope=filtered&state=all{query}")
        return int(got.json()["fsm"]["new"])

    assert polled("") == 3
    assert polled("&topic=containers") == 2
    assert polled("&topic=containers,algorithms") == 1


# -- and the deck you land on is the one in the URL -------------------------


def test_no_project_named_lands_on_one_with_units_and_says_so(repo: Path) -> None:
    """A zero-byte `units.jsonl` is a file that is present, so the guard that
    steps past an empty project stepped onto it. The script polls with
    `location.search`, so the URL has to carry where it landed."""
    a_repo(repo, outline="", units=[])
    run(repo, "project", "later", "--title", "Later", "--deck", "Later")
    (repo / "projects" / "later" / "units.jsonl").write_text(
        json.dumps({"id": "later:one", "state": "new", "locator": {"document": "x.pdf"}}) + "\n",
        encoding="utf-8",
    )

    landed = client(repo).get("/units?state=all")

    assert "project=later" in str(landed.url)
    assert shown(landed.text) == ["later:one"]


def test_an_empty_ledger_does_not_blame_a_filter(repo: Path) -> None:
    a_repo(repo, outline="", units=[])

    page = client(repo).get("/units?project=cpp&state=all").text

    assert "no units in cpp yet." in page
    assert "nothing here with this filter." not in page
