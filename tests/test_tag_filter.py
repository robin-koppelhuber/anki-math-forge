"""Filtering by tag and by grading, on both views.

A section is where something sits in a document; a tag is what it is about.
They answer different questions, and a project with no document has no
sections at all, so without this there is nothing to narrow a deck by
(ROADMAP.md 10).

Tags are offered from what is actually tagged. A list from anywhere else
would show tags nothing carries and hide the one you wrote a minute ago.

One control, one parameter, and several selections at once select the union:
three groups that each narrowed the last meant a second choice nearly always
emptied the deck.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.app import commands_for, create_app, pick_toggle, tag_rows


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def a_project(repo: Path) -> None:
    run(repo, "project", "cpp", "--title", "Modern C++", "--deck", "Cpp")


def propose(repo: Path, subject: str, *tags: str) -> None:
    args = ["units", "--project", "cpp", "--add", subject, "--gist", subject]
    for tag in tags:
        args += ["--tag", tag]
    run(repo, *args)


def client(repo: Path) -> TestClient:
    return TestClient(create_app(config_mod.load(repo)))


# -- the helper -------------------------------------------------------------


def test_the_most_used_tag_comes_first() -> None:
    """Alphabetical puts the tag you used twice above the one you used
    ninety times, and the order should not move as you click through."""
    rows = tag_rows([["a", "b"], ["b"], ["b", "c"], ["c"]], [])

    assert [row["name"] for row in rows] == ["b", "c", "a"]
    assert [row["count"] for row in rows] == [3, 2, 1]


def test_the_chosen_tag_survives_its_own_filter() -> None:
    """Filtering down to a tag can leave nothing else carrying it. Dropping
    it from the list then removes the only way back out."""
    rows = tag_rows([], ["containers"])

    assert [row["name"] for row in rows] == ["containers"]
    assert rows[0]["on"] is True


def test_a_selection_toggles_rather_than_replaces() -> None:
    """One parameter holds the lot, so adding a second filter has to keep the
    first: replacing it is what the three separate groups used to do."""
    assert pick_toggle("", "containers") == "containers"
    assert pick_toggle("containers", "frequency:core") == "containers,frequency:core"
    assert pick_toggle("containers,frequency:core", "containers") == "frequency:core"
    assert pick_toggle("containers", "containers") is None, "the last one off leaves no filter"


def test_a_tag_with_a_colon_in_it_is_still_a_tag() -> None:
    """Anki writes a hierarchy that way. Only the two closed vocabularies are
    claimed, and only for the values actually in them."""
    rows = tag_rows([["cpp::containers"]], ["cpp::containers"])

    assert rows[0]["on"] is True
    assert rows[0]["key"] == "cpp::containers"


# -- the views --------------------------------------------------------------


def test_units_can_be_narrowed_to_a_tag(repo: Path) -> None:
    a_project(repo)
    propose(repo, "vector erase", "containers")
    propose(repo, "sort stability", "algorithms")

    page = client(repo).get("/units?project=cpp&has=containers&state=new").text

    assert "vector erase" in page
    assert "sort stability" not in page


def test_two_tags_select_the_union(repo: Path) -> None:
    """Or, not and. Two groups that narrowed each other emptied the deck on
    the second click, which is not what anyone meant by picking two."""
    a_project(repo)
    propose(repo, "vector erase", "containers")
    propose(repo, "sort stability", "algorithms")
    propose(repo, "make_unique", "memory")

    page = client(repo).get("/units?project=cpp&has=containers,algorithms&state=new").text

    assert "vector erase" in page
    assert "sort stability" in page
    assert "make_unique" not in page


def test_the_rail_offers_what_is_actually_tagged(repo: Path) -> None:
    a_project(repo)
    propose(repo, "vector erase", "containers")
    propose(repo, "deque", "containers")
    propose(repo, "sort stability", "algorithms")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert 'data-pick="containers"' in page
    assert 'data-pick="algorithms"' in page
    assert 'data-pick="invalidation"' not in page, "nothing carries it, so it is not offered"


def test_a_tag_that_nothing_carries_leaves_the_group_out(repo: Path) -> None:
    a_project(repo)
    propose(repo, "vector erase")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert 'id="pick-list"' not in page, "an empty group is a heading over nothing"


def test_nothing_is_spelled_out_until_you_ask(repo: Path) -> None:
    """The list starts hidden behind the search box. Three groups spelling
    out their whole vocabulary were most of the rail's height, and the
    sections below them were off the bottom of the screen."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert 'id="pick-search"' in page, "the box is the control, at any number of tags"
    assert 'id="pick-list" hidden' in page


def test_a_grading_does_not_empty_the_units_lane(repo: Path) -> None:
    """A grading is a question a unit cannot answer, so it does not decide
    either way. The rail counts both lanes under the filters in force, and
    "0 new" because the review page is showing core cards is a lie about
    the other lane."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get(
        "/units?project=cpp&state=new&has=frequency:core&counts_scope=filtered"
    ).text

    assert "vector erase" in page


def test_a_unit_view_does_not_offer_a_grading(repo: Path) -> None:
    """Triage decides whether a unit is worth a card, and grading is a
    property of the card. A scale the stage cannot set is a row that would
    always select nothing."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert 'data-pick="frequency:core"' not in page


def a_card(repo: Path, uid: str, gist: str, *tags: str, freq: str = "", deriv: str = "") -> None:
    path = repo / "cards" / "demo" / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = ", ".join(f'"{t}"' for t in tags)
    graded = (f"frequency: {freq}\n" if freq else "") + (
        f"derivation: {deriv}\n" if deriv else ""
    )
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Demo"\nunit: "demo:1:1"\ngist: {gist}\ntags: [{listed}]\n{graded}---\n\n'
        "## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )


def test_cards_can_be_narrowed_too(repo: Path) -> None:
    """The same control on the review side: a card's tags are its own, and
    they are what a deck gets routed by."""
    a_card(repo, "aa11bb", "the trace of a product", "traces")
    a_card(repo, "cc22dd", "the determinant of a product", "determinants")

    page = client(repo).get("/review?project=demo&has=traces&status=draft")

    assert page.status_code == 200
    assert "the trace of a product" in page.text
    assert "the determinant of a product" not in page.text
    assert 'data-pick="traces"' in page.text


def test_what_is_on_shows_as_a_chip(repo: Path) -> None:
    """The list is hidden, so the chips are the only thing saying what the
    deck is narrowed to, and a filter you cannot see is one you cannot turn
    off."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get("/units?project=cpp&has=containers&state=new").text

    assert 'id="pick-chips"' in page
    assert "pick-chip" in page and ">containers</span>" in page
    assert "stop filtering by containers" in page, "and a link that drops it"


# -- the graded scales ------------------------------------------------------


def test_a_grading_can_be_selected_not_only_read(repo: Path) -> None:
    """They decide when Anki introduces a card, and they were chips you could
    read and not filters you could click."""
    a_card(repo, "aa11bb", "a core fact", freq="core")
    a_card(repo, "cc22dd", "a rare one", freq="rare")

    page = client(repo).get("/review?project=demo&status=draft&has=frequency:core").text

    assert "a core fact" in page
    assert "a rare one" not in page


def test_a_grading_and_a_tag_select_the_union(repo: Path) -> None:
    """One control over both, so "the core ones and anything tagged traces"
    is one view rather than two."""
    a_card(repo, "aa11bb", "a core fact", freq="core")
    a_card(repo, "cc22dd", "about traces", "traces")
    a_card(repo, "ee33ff", "neither of those")

    page = client(repo).get(
        "/review?project=demo&status=draft&has=frequency:core,traces"
    ).text

    assert "a core fact" in page
    assert "about traces" in page
    assert "neither of those" not in page


def test_a_grading_chip_says_which_scale_it_is_from(repo: Path) -> None:
    """`core` and `short` are unambiguous under a heading and not on a chip
    of their own, where a tag of the same name would read the same."""
    a_card(repo, "aa11bb", "a core fact", freq="core")

    page = client(repo).get("/review?project=demo&status=draft&has=frequency:core").text

    assert ">frequency: core</span>" in page


def test_ungraded_is_a_value_you_can_ask_for(repo: Path) -> None:
    """Asking what is not graded yet is the question you put most often
    while working a deck through, and a filter over the vocabulary alone
    cannot express it."""
    a_card(repo, "aa11bb", "a core fact", freq="core")
    a_card(repo, "cc22dd", "not judged yet")

    page = client(repo).get("/review?project=demo&status=draft&has=frequency:none").text

    assert "not judged yet" in page
    assert "a core fact" not in page


def test_the_whole_vocabulary_is_offered(repo: Path) -> None:
    """A row missing because nothing carries that value reads as "none of
    these are core" when it means "nothing is graded yet"."""
    a_card(repo, "aa11bb", "a core fact", freq="core")

    page = client(repo).get("/review?project=demo&status=draft").text

    for value in ("core", "common", "rare", "definitional", "short", "long", "ungraded"):
        assert f">{value}</span>" in page, value


# -- what the commands panel offers -----------------------------------------


def test_a_project_with_no_document_is_offered_propose(repo: Path) -> None:
    """The passes that read a crop have nothing to read here, and the pass
    that writes units has to be reachable from somewhere."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert "/propose --project" in page and "cpp" in page

    # The panel itself, not the page: the guide beside it explains the whole
    # pipeline and names `/transcribe` whether or not it applies here.
    runs = [row.get("run", "") for row in commands_for("units", {"project": "cpp"},
                                                       {"new": 1}, has_document=False)]
    assert any("/propose" in run for run in runs)
    assert not [run for run in runs if "/transcribe" in run], "nothing to transcribe"


def test_a_project_with_a_document_is_offered_the_crop_passes(repo: Path) -> None:
    """Keyed on what the project has, not on what kind it is."""
    runs = [row.get("run", "") for row in commands_for(
        "units", {"project": "demo"}, {"new": 1, "untranscribed": 1}, has_document=True)]

    assert not [run for run in runs if "/propose" in run]
    assert any("/transcribe" in run for run in runs)


def test_a_unit_with_no_page_is_not_offered_a_page_window(repo: Path) -> None:
    """Every size the chip offers counts pages either side of one. A unit
    that was proposed rather than printed has no page, so the control would
    be a row of numbers that change nothing."""
    a_project(repo)
    propose(repo, "vector erase", "containers")

    page = client(repo).get("/units?project=cpp&state=new").text

    assert "data-context-chip" not in page
    assert "data-web-chip" in page, "the permission still applies and still shows"
