"""A real browser against a real server, for the one view tests cannot reach.

Everything else in this suite asserts against markup, a payload or a file. The
canvas has none of those: it is a `<canvas>` and a pointer, so "clicking a box
opens the card" is not a property of any string. These are the tests that need
a browser.

**Opt in**, because it starts a server and launches Chrome. `uv sync --extra
browser`, then `uv run pytest`; without the extra they skip with a line saying
so, and the rest of the suite is unaffected.

It drives the Chrome that is already installed (`channel="chrome"`) rather than
downloading one. `assets/make_assets.py` already assumes a local Chrome, so
this costs a Python package and nothing else.
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

ROOT = Path(__file__).resolve().parents[2]

pytest.importorskip(
    "playwright.sync_api",
    reason="needs the `browser` extra: uv sync --extra browser",
)


def spare_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# The deck every test starts from: one edge, `aaa111 -> bbb222`, and two cards
# with none so the picker has something in it.
#
# Graded, and deliberately not all the same way. The study-order panel is about
# which grading outranks which, and a deck where every card is `core` and
# `short` cannot show a reordering doing anything. `ddd444` carries no grading
# at all, which is the case the panel calls `ungraded`.
DECK = (
    ("aaa111", "the determinant of a 2 by 2 matrix", (), "rare", "definitional"),
    ("bbb222", "the inverse of a 2 by 2 matrix", ("aaa111",), "core", "long"),
    ("ccc333", "the trace as the sum of the diagonal", (), "common", "short"),
    ("ddd444", "the adjugate as the transposed cofactor matrix", (), "", ""),
)


DEMO_TEX = r"""
\documentclass{article}
\begin{document}
\section{Basics}
Prose about traces, and what a determinant is.
\begin{equation}
\operatorname{tr}(AB) = \operatorname{tr}(BA)
\end{equation}
\subsection{Derivatives}
The identity everyone forgets.
\begin{equation}
\frac{\partial}{\partial X}\log\det X = X^{-\top}
\end{equation}
\begin{equation}
\det(AB) = \det(A)\det(B)
\end{equation}
\end{document}
"""


# Rewritten on every reset, not only at startup: the study-order panel writes
# `[cards] study_order` into this file, so a test that reorders the criteria
# would otherwise hand the next test a deck in a different order.
CONFIG = (
    '[repo]\ncards_dir = "cards"\nprojects_dir = "projects"\n\n'
    "[cards]\n\n"
    '[projects.demo]\ntitle = "Demo"\ncitation = "Demo"\n'
    'tex = "projects/demo/demo.tex"\n'
)


def lay_out(repo: Path) -> None:
    """Write the config, the deck and the ledger, replacing what the last test
    left.

    Units as well as cards, because the triage view is half of what these
    tests drive and an empty ledger renders the "nothing here yet" page.
    """
    (repo / "forge.toml").write_text(CONFIG, encoding="utf-8")
    cards = repo / "cards" / "demo"
    cards.mkdir(parents=True, exist_ok=True)
    # Replacing what the last test left means *all* of it. Rewriting only the
    # cards this function knows about left any card a test had added standing,
    # and the next test counted it: one test adding a card to try something
    # became three failures somewhere else.
    for stale in cards.glob("*.md"):
        stale.unlink()
    (repo / "projects" / "demo").mkdir(parents=True, exist_ok=True)
    (repo / "projects" / "demo" / "demo.tex").write_text(DEMO_TEX, encoding="utf-8")
    (repo / "projects" / "demo" / "units.jsonl").unlink(missing_ok=True)
    (repo / "projects" / "demo" / "graph.json").unlink(missing_ok=True)
    for uid, gist, needs, frequency, derivation in DECK:
        graded = ""
        if frequency:
            graded += f"frequency: {frequency}\n"
        if derivation:
            graded += f"derivation: {derivation}\n"
        requires = f"requires: [{', '.join(needs)}]\n" if needs else ""
        (cards / f"{uid}-x.md").write_text(
            f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
            f'source: "Demo"\nunit: "demo:1:1"\ngist: {gist}\n{graded}{requires}---\n\n'
            "## front\n\n$a$\n\n## back\n\n$b$\n",
            encoding="utf-8",
        )
    _extract(repo)


def _extract(repo: Path) -> None:
    """`forge extract`, in-process. The ledger has to be there before the
    first request: the units view renders the empty page without one."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from anki_math_forge import config as config_mod
    from anki_math_forge import extract

    extract.run(config_mod.load(repo), "demo")


@pytest.fixture(scope="session")
def served(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    """One server for the whole session, over a throwaway repo.

    Its own repo, not this one: a browser test that drags arrows around would
    otherwise be writing `requires` into the real deck.

    The server is never restarted between tests, and does not need to be. The
    app re-reads from disk on every request and caches nothing (invariant 2),
    so rewriting the card files *is* resetting the fixture.
    """
    repo = tmp_path_factory.mktemp("served")
    lay_out(repo)

    port = spare_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--port",
            str(port),
            "--factory",
            "conftest:_app",
        ],
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


def _app():  # type: ignore[no-untyped-def]
    """Uvicorn's `--factory` target: the app over whatever repo was named."""
    from anki_math_forge import config as config_mod
    from anki_math_forge.app import create_app

    return create_app(config_mod.load(Path(os.environ["FORGE_TEST_REPO"])))


@pytest.fixture
def live(served: tuple[str, Path]) -> str:
    """The base URL, with the deck put back to what every test expects.

    Named rather than autouse: a test asking for `live` is asking for a server
    *and* a known deck, and a fixture that rewrites files should be something a
    test names out loud.
    """
    base, repo = served
    lay_out(repo)
    return base


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        # The installed Chrome, not a downloaded one.
        launched = play.chromium.launch(channel="chrome")
        yield launched
        launched.close()


@pytest.fixture
def page(browser, live):  # type: ignore[no-untyped-def]
    """A page, with whatever the console complained about collected on it.

    A canvas cannot show a broken script the way markup can: an uncaught error
    just stops the picture updating, and everything still looks like a page.
    """
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    pg.complaints = []
    pg.on("pageerror", lambda e: pg.complaints.append(f"pageerror: {e}"))
    pg.on(
        "console",
        lambda m: pg.complaints.append(f"console.error: {m.text}")
        if m.type == "error"
        else None,
    )
    yield pg
    pg.close()
