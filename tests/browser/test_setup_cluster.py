"""The setup stage for a project that reads several works.

A cluster of related papers is one project with several sources (ROADMAP.md
10), and it is the case the panel was rebuilt for: an ask with four works
behind it. The rules it has to get right are not assertable against markup
(which ask is lit while you read its works, what the filters leave, whether
the maths in `conventions.md` rendered), so they need a browser.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[2]

CONFIG = (
    '[repo]\ncards_dir = "cards"\nprojects_dir = "projects"\n\n[cards]\ncontext_pages = 1\n'
)

# Two works to extract from and one to check against. The paper sets its own
# crop context, the book its own window: both are facts about a document, and
# a project reading two of them has two answers.
TOML = """title = "Probability, a cluster"
deck = "Prob"

[[sources]]
key = "book"
title = "Krause, lecture notes"
files = ["projects/cluster/book.tex"]
context_pages = 2

[[sources]]
key = "paper"
title = "Ermon, DPO"
files = ["projects/cluster/paper.tex"]
crop_context = 40

[[sources]]
key = "wiki"
title = "Wikipedia"
url = "https://en.wikipedia.org/"

[conventions]
layout = "denominator"
"""

TOPICS = """# What this deck is for

## conjugate priors

Which prior goes with which likelihood, and the update in closed form.

- the beta-binomial update
- the normal-normal update
- why conjugacy is a convenience and not a law

## preference optimisation

- the DPO objective
"""

# One unit per outline entry that has been proposed for, each naming the work
# it came out of. That naming is the whole of the ask-to-work relation.
UNITS = (
    {
        "id": "cluster:the-beta-binomial-update",
        "gist": "beta-binomial",
        "locator": {"document": "book"},
        "state": "new",
    },
    {
        "id": "cluster:the-normal-normal-update",
        "gist": "normal-normal",
        "locator": {"document": "book"},
        "state": "new",
        "refs": ["https://en.wikipedia.org/wiki/Conjugate_prior"],
    },
    {
        "id": "cluster:the-dpo-objective",
        "gist": "the DPO objective",
        "locator": {"document": "paper"},
        "state": "new",
    },
)

CONVENTIONS = """# What is ambient here

- Derivatives are **denominator** layout: $\\partial y/\\partial x$ is a
  column when $y$ is a scalar.
- A bare $p$ is a density, never a probability mass.
"""


def spare_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# A second project, so "a work this repo already reads" has something in it.
OTHER = """title = "Someone else's deck"

[[sources]]
key = "wiley"
title = "Wiley, the other book"
url = "https://example.com/wiley"
"""


def lay_out(repo: Path) -> None:
    (repo / "forge.toml").write_text(CONFIG, encoding="utf-8")
    other = repo / "projects" / "other"
    other.mkdir(parents=True, exist_ok=True)
    (other / "project.toml").write_text(OTHER, encoding="utf-8")
    folder = repo / "projects" / "cluster"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.toml").write_text(TOML, encoding="utf-8")
    (folder / "book.tex").write_text("the book\n", encoding="utf-8")
    (folder / "paper.tex").write_text("the paper\n", encoding="utf-8")
    (folder / "topics.md").write_text(TOPICS, encoding="utf-8")
    (folder / "conventions.md").write_text(CONVENTIONS, encoding="utf-8")
    (folder / "units.jsonl").write_text(
        "\n".join(json.dumps(u) for u in UNITS) + "\n", encoding="utf-8"
    )
    (repo / "cards" / "cluster").mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    repo = tmp_path_factory.mktemp("cluster")
    lay_out(repo)
    port = spare_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "--port", str(port), "--factory", "conftest:_app"],
        cwd=Path(__file__).parent,
        env={
            **os.environ,
            "FORGE_TEST_REPO": str(repo),
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONIOENCODING": "utf-8",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 40
    try:
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"{base}/api/counts", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            pytest.fail("the test server never came up")
        yield base, repo
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def live(served: tuple[str, Path]) -> str:
    base, repo = served
    lay_out(repo)
    return base


def setup(page, live):  # type: ignore[no-untyped-def]
    page.goto(f"{live}/setup?project=cluster")
    page.wait_for_selector("#topics")
    return page


def test_picking_an_ask_narrows_the_works_below_it(page, live) -> None:  # type: ignore[no-untyped-def]
    """The flow this panel exists for: an ask with several works behind it,
    and the list below cut down to them."""
    setup(page, live)
    assert page.locator("#source-list > li:visible").count() == 3

    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')

    # The book its units came out of, and the site one of them cites. Not the
    # paper: that belongs to the other ask.
    assert page.locator('#source-list > li[data-topics~="conjugate-priors"]').count() == 2
    assert page.locator("#source-list > li:visible").count() == 2
    assert page.locator('#source-list [data-pane="source:paper"]').is_visible() is False


def test_the_ask_stays_selected_while_you_read_its_works(page, live) -> None:  # type: ignore[no-untyped-def]
    """Clicking through them changes the right-hand panel and nothing else.
    Losing the ask would put the list back to all three every time."""
    setup(page, live)
    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')
    page.click('#source-list [data-pane="source:book"]')

    assert page.locator('[data-pane="source:book"].setup-pane').is_visible()
    assert "conjugate-priors" in page.url and "source:book" in page.url
    ask = page.locator('#setup-panel [data-pane="topic:conjugate-priors"]')
    assert "on" in (ask.get_attribute("class") or ""), "the ask is still lit"
    assert page.locator("#source-list > li:visible").count() == 2, "and still the filter"


def test_the_relation_reads_both_ways(page, live) -> None:  # type: ignore[no-untyped-def]
    """A chip on the ask goes to the work, and a chip on the work goes back."""
    setup(page, live)
    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')
    page.click('[data-pane="topic:conjugate-priors"].setup-pane .work-chip:has-text("Krause")')

    assert page.locator('[data-pane="source:book"].setup-pane').is_visible()

    page.click('[data-pane="source:book"].setup-pane .work-chip')
    assert page.locator('[data-pane="topic:conjugate-priors"].setup-pane').is_visible()


def test_the_works_filter_by_what_they_are(page, live) -> None:  # type: ignore[no-untyped-def]
    """Something units come out of, or something they are checked against."""
    setup(page, live)

    page.click('#source-filter [data-kind="reference"]')
    assert page.locator("#source-list > li:visible").count() == 1
    assert page.locator('#source-list [data-pane="source:wiki"]').is_visible()

    page.click('#source-filter [data-kind="authoritative"]')
    assert page.locator("#source-list > li:visible").count() == 2

    page.click('#source-filter [data-kind=""]')
    assert page.locator("#source-list > li:visible").count() == 3


def test_following_the_ask_can_be_turned_off(page, live) -> None:  # type: ignore[no-untyped-def]
    """It is a filter like the other one, and the two compose."""
    setup(page, live)
    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')
    assert page.locator("#source-list > li:visible").count() == 2

    page.click("#topic-sync")
    assert page.locator("#source-list > li:visible").count() == 3

    page.click('#source-filter [data-kind="reference"]')
    assert page.locator("#source-list > li:visible").count() == 1


def test_a_setting_a_work_declares_says_so(page, live) -> None:  # type: ignore[no-untyped-def]
    """How much page a crop carries is a fact about a document, and this
    project reads three. Each panel answers for its own."""
    setup(page, live)
    page.click('#source-list [data-pane="source:book"]')
    book = page.locator('[data-pane="source:book"].setup-pane').inner_text()
    assert "2 pages either side" in book, "the book asked for two"

    page.click('#source-list [data-pane="source:paper"]')
    paper = page.locator('[data-pane="source:paper"].setup-pane').inner_text()
    assert "40 points of page" in paper
    assert "1 page either side" in paper, "the paper inherits the repo's"


def test_the_ambient_file_is_rendered_and_not_quoted(page, live) -> None:  # type: ignore[no-untyped-def]
    """`conventions.md` is markdown with maths in it, and a wall of literal
    `-` and `$\\partial$` is the page saying it has not read the file."""
    setup(page, live)

    assert page.locator(".setup-prose li").count() == 2
    assert page.locator(".setup-prose strong").count() == 1
    assert page.locator(".setup-prose .katex").count() >= 2, "KaTeX ran over it"


def test_what_to_run_follows_what_is_selected(page, live) -> None:  # type: ignore[no-untyped-def]
    """An ask and a work want different passes, and the scope is the thing
    this screen can say that the triage rail cannot: triage does not know
    which ask you are working through."""
    setup(page, live)
    runs = page.locator("#setup-runs")
    assert "forge extract" in runs.inner_text()

    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')
    assert "/propose" in runs.inner_text()
    assert "conjugate priors" in runs.inner_text(), "the ask by name"

    page.click('#source-list [data-pane="source:wiki"]')
    assert "nothing to run" in runs.inner_text(), "a reference has no page to cut"


def test_the_commands_column_folds_away(page, live) -> None:  # type: ignore[no-untyped-def]
    """The one you stop needing: what to run next is a question you ask
    twice a session, and the other two are what you are reading."""
    setup(page, live)
    assert page.locator("#setup-runs").is_visible()

    page.click("#runs-fold")
    assert page.locator("#setup-runs").is_visible() is False
    assert page.locator("#runs-tab").is_visible()

    page.click("#runs-tab")
    assert page.locator("#setup-runs").is_visible()


def test_the_columns_drag(page, live) -> None:  # type: ignore[no-untyped-def]
    """Three columns and two handles, and neither handle moves the other's
    edge: the two left ones are widths and the panel takes the slack."""
    setup(page, live)
    panel = page.locator("#setup-panel")
    before = panel.bounding_box()

    handle = page.locator('[data-splitter="setupRuns"]')
    box = handle.bounding_box()
    page.mouse.move(box["x"] + 5, box["y"] + 200)
    page.mouse.down()
    page.mouse.move(box["x"] + 105, box["y"] + 200)
    page.mouse.up()

    after = panel.bounding_box()
    assert after["x"] > before["x"] + 50, "the commands column got wider"
    assert abs(after["width"] - before["width"]) < 2, "and the panel kept its own"


def test_a_count_carries_the_selection_into_triage(page, live) -> None:  # type: ignore[no-untyped-def]
    """The selection you made here is worth carrying. Re-making it over
    there by hand was the one thing this screen could not hand over."""
    setup(page, live)
    page.click('#setup-panel [data-pane="topic:conjugate-priors"]')
    page.click('[data-pane="topic:conjugate-priors"].setup-pane .count-chip')
    page.wait_for_selector("#filter-rail")

    assert "topic=conjugate-priors" in page.url
    assert page.locator('[data-id="cluster:the-beta-binomial-update"]').count() == 1
    assert page.locator('[data-id="cluster:the-dpo-objective"]').count() == 0
    # And the rail says where the deck came from, with the way out.
    assert "conjugate priors" in page.locator("#topics .pick-chip").inner_text()


def test_the_works_the_repo_knows_can_be_searched(page, live) -> None:  # type: ignore[no-untyped-def]
    """Past a handful the list is something to hunt through rather than
    read, which is the same reason the rail's tag box exists."""
    setup(page, live)
    page.click('#setup-panel [data-pane="add-source"]')
    rows = page.locator("#known-list > li")
    before = rows.count()

    page.fill("#known-search", "nothing-like-this")
    assert page.locator("#known-list > li:visible").count() == 0
    assert page.locator("#known-none").is_visible()

    page.fill("#known-search", "")
    assert page.locator("#known-list > li:visible").count() == before


def test_the_folded_column_leaves_its_way_back_at_the_top(page, live) -> None:  # type: ignore[no-untyped-def]
    """Beside the panel it opens, not floating at the middle of the window:
    a centred tab reads as a control belonging to nothing."""
    setup(page, live)
    page.click("#runs-fold")
    tab = page.locator("#runs-tab").bounding_box()
    panel = page.locator("#setup-panel").bounding_box()

    assert tab["y"] < panel["y"] + 80, "near the top of the column, not the window"
    assert tab["x"] < panel["x"] + 40, "against the edge it folded into"


def test_a_work_from_another_project_can_be_added(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """A paper can sit in two projects, cited by one and extracted from by
    another. Adding copies nothing: both read the same item."""
    _, repo = served
    setup(page, live)
    page.click('#setup-panel [data-pane="add-source"]')
    page.click('[data-add-source="wiley"]')
    page.wait_for_selector('#source-list [data-pane="source:wiley"]')

    text = (repo / "projects" / "cluster" / "project.toml").read_text(encoding="utf-8")
    assert 'key = "wiley"' in text
    assert "https://example.com/wiley" in text


def test_the_shelf_is_where_the_app_opens(page, live) -> None:  # type: ignore[no-untyped-def]
    """Landing on a deck meant landing on whichever project happened to be
    first, which is an answer to a question nobody asked."""
    page.goto(f"{live}/")
    page.wait_for_selector("#shelf-grid")

    assert "/projects" in page.url
    assert page.locator("#shelf-grid .gsource").count() == 2


def test_the_shelf_search_narrows_by_name(page, live) -> None:  # type: ignore[no-untyped-def]
    """A text match over what is already on screen: a round trip per
    keystroke is not what finding a name by typing three letters costs."""
    page.goto(f"{live}/projects")
    page.wait_for_selector("#shelf-grid")

    page.fill("#shelf-search", "clus")
    assert page.locator("#shelf-grid .gsource:visible").count() == 1

    page.fill("#shelf-search", "nothing-like-this")
    assert page.locator("#shelf-grid .gsource:visible").count() == 0
    assert page.locator("#shelf-none").is_visible()


def test_the_command_halves_fold(page, live) -> None:  # type: ignore[no-untyped-def]
    """Four commands you run and six you read is ten boxes in a column, and
    the one you want is under the other nine."""
    page.goto(f"{live}/projects")
    page.wait_for_selector("#shelf-grid")
    halves = page.locator(".runs-half")
    assert halves.count() == 2

    first = halves.nth(0)
    assert first.locator("li").first.is_visible()
    first.locator("summary").click()
    assert first.locator("li").first.is_visible() is False


def test_rejecting_a_proposal_from_its_panel(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The panel, its row in the list and the counts beside it all go, and
    they are drawn from the file that just changed. It used to call
    `.remove()` on a row that is not on this screen, which threw: the line
    went from the file and nothing moved until you reloaded by hand.
    """
    _, repo = served
    folder = repo / "projects" / "cpp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.toml").write_text('title = "C++"\n', encoding="utf-8")
    (folder / "references.md").write_text(
        "# References\n\n- [ ] cppreference (https://a.test/w/cpp/container)\n"
        "- [ ] Meyers, Effective STL, for the idioms\n",
        encoding="utf-8",
    )

    page.goto(f"{live}/setup?project=cpp")
    page.wait_for_selector("#setup")
    assert page.locator("#proposed-list li").count() == 2

    page.click('#proposed-list button[data-pane="proposed:1"]')
    page.click('section[data-pane="proposed:1"] [data-drop-reference]')
    page.wait_for_function(
        "() => document.querySelectorAll('#proposed-list li').length === 1"
    )

    left = (folder / "references.md").read_text(encoding="utf-8")
    assert "Meyers" not in left
    assert "cppreference" in left
    assert not page.complaints, page.complaints
