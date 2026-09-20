"""Triage for a project with no document, in a real browser.

The views were written against a deck with a book behind it, and the unit
tests can only say that a string reached the page. What they cannot see is
the layout: a pane sized for a crop that now holds nothing, a chip removed
from a row that was counting on it, a code block running off its column.
That is what this is for, and it is the same reason the settled-card banner
needed a browser to notice it had taken the body's grid column.
"""

from __future__ import annotations

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

# A project that declares no source at all. The shared fixture has none: its
# `demo` reads a `.tex`, which is still a document.
CONFIG = (
    '[repo]\ncards_dir = "cards"\nprojects_dir = "projects"\n\n'
    "[cards]\n\n"
    '[projects.cpp]\ntitle = "Modern C++"\ncitation = "cppreference"\ndeck = "Cpp"\n'
)

UNITS = (
    ("cpp:vector-erase-remove", "erase-remove on a vector", "containers",
     "auto it = std::remove(v.begin(), v.end(), x);\nv.erase(it, v.end());"),
    ("cpp:span-is-a-view", "a span owns nothing", "views", "std::span<int> s{v};"),
    ("cpp:deque-invalidation", "what a deque invalidates", "containers", ""),
)


def spare_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def lay_out(repo: Path) -> None:
    """The config, the shelf, and a ledger of proposed units."""
    (repo / "forge.toml").write_text(CONFIG, encoding="utf-8")
    folder = repo / "projects" / "cpp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "references.md").write_text(
        "# References\n\n- cppreference, the container library overview.\n",
        encoding="utf-8",
    )
    lines = []
    for unit_id, gist, tag, preview in UNITS:
        row = {
            "id": unit_id,
            "gist": gist,
            "state": "new",
            "tags": [tag],
            "refs": ["https://en.cppreference.com/w/cpp/container"],
        }
        if preview:
            row["preview"] = preview
            row["lang"] = "cpp"
        lines.append(row)
    import json

    (folder / "units.jsonl").write_text(
        "\n".join(json.dumps(row) for row in lines) + "\n", encoding="utf-8"
    )
    (repo / "cards" / "cpp").mkdir(parents=True, exist_ok=True)


# A server of this module's own: the app reads `forge.toml` once, at start,
# so a project added afterwards is one it has never heard of.
@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    repo = tmp_path_factory.mktemp("project")
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


def triage(page, live):  # type: ignore[no-untyped-def]
    page.goto(f"{live}/units?project=cpp&state=new")
    page.wait_for_selector('[data-id="cpp:vector-erase-remove"]')
    return page


# -- what reaches the screen ------------------------------------------------


def test_the_sample_is_shown_as_code_and_stays_in_its_column(page, live) -> None:  # type: ignore[no-untyped-def]
    """A snippet handed to KaTeX renders as a broken formula, and one in a
    `<pre>` that is not scrollable pushes the column wider than the pane."""
    triage(page, live)

    block = page.locator('[data-id="cpp:vector-erase-remove"] pre.code')
    assert block.count() == 1
    assert "std::remove" in block.inner_text()

    pane = page.locator('[data-id="cpp:vector-erase-remove"] .transcription')
    assert block.bounding_box()["width"] <= pane.bounding_box()["width"] + 1


def test_a_unit_with_nothing_to_read_says_so(page, live) -> None:  # type: ignore[no-untyped-def]
    """No crop and no sample. The pane used to promise a crop to read."""
    triage(page, live)

    said = page.locator('[data-id="cpp:deque-invalidation"] .transcription').inner_text()
    assert "nothing to read here" in said
    assert "read the crop" not in said, "there is no crop to read"


def test_no_context_chip_where_there_are_no_pages(page, live) -> None:  # type: ignore[no-untyped-def]
    """Every size it offers counts pages either side of one."""
    triage(page, live)

    unit = page.locator('[data-id="cpp:vector-erase-remove"]')
    assert unit.locator("[data-context-chip]").count() == 0
    assert unit.locator("[data-web-chip]").count() == 1, "the permission still applies"


def test_the_tag_filter_narrows_the_deck(page, live) -> None:  # type: ignore[no-untyped-def]
    triage(page, live)

    page.click('#tag-list [data-tag="views"] a')
    page.wait_for_selector('[data-id="cpp:span-is-a-view"]')

    assert page.locator('[data-id="cpp:vector-erase-remove"]').count() == 0
    assert "all tags" in page.locator("#filter-rail").inner_text()


def test_triage_still_queues_a_unit(page, live, served) -> None:  # type: ignore[no-untyped-def]
    """The whole claim: only the first layer changed. The keystroke that
    queues a unit from a book queues one nobody printed."""
    _, repo = served
    triage(page, live)

    page.locator('[data-id="cpp:vector-erase-remove"]').click()
    page.keyboard.press("q")
    page.wait_for_function(
        "() => !document.querySelector('[data-id=\"cpp:vector-erase-remove\"]')"
        " || document.querySelector('[data-id=\"cpp:vector-erase-remove\"]')"
        ".dataset.state === 'queued'"
    )

    ledger = (repo / "projects" / "cpp" / "units.jsonl").read_text(encoding="utf-8")
    assert '"state": "queued"' in ledger
