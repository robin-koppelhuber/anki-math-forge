"""Running a command from the website, in the background (ROADMAP.md §12).

**Only a command that shows you something.** The parser declares an
`effect` on every subcommand (docs/VERBS.md), and this refuses anything
that is not `reads`. That is the whole safety story and it is one rule
rather than a list kept by hand: a verb that starts writing tomorrow stops
being runnable here on the same commit, without anybody remembering to
come back.

**Always in the background.** `forge anki` is ten seconds on a deck of 150
cards, almost all of it waiting on AnkiConnect, and it grows with the
deck. A button that held the page for that is a button nobody presses
twice. So: start it, get an id back at once, and poll. The page stays
answering, which it does anyway because every endpoint in this app is
`def` and runs in a thread pool.

**A result, not a transcript.** These are wrappers around plain Python and
each already returns a structured object that `--json` prints. Rendering
that beats streaming a console: no transport, no buffering, no cancel
semantics, and the thing you wanted to read is a table rather than a log.

Nothing here is a model. A slash command stays copied, which is invariant
1's bargain: you paste it where you can watch it, so nothing writes cards
with nobody looking.
"""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

#: How many finished runs to remember. A run is read once, just after it
#: finishes, and the only reason to keep any is a page reloaded mid-run.
KEEP = 20


@dataclass
class Run:
    """One command, from the moment it was asked for."""

    id: str
    argv: list[str]
    started: float
    done: bool = False
    ok: bool = False
    seconds: float = 0.0
    #: What `--json` printed, parsed. `None` when the command printed
    #: nothing a machine could read, which is a result too.
    data: Any = None
    #: Anything on stderr, which is where every command puts the reason it
    #: could not do the thing: Anki closed, Zotero closed, no ledger yet.
    said: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run": "forge " + " ".join(self.argv),
            "done": self.done,
            "ok": self.ok,
            "seconds": round(self.seconds, 2),
            "data": self.data,
            "said": self.said,
        }


@dataclass
class Runner:
    """Every run this server has been asked for, newest last."""

    runs: dict[str, Run] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self, argv: list[str], root: Any) -> Run:
        run = Run(id=uuid.uuid4().hex[:12], argv=list(argv), started=time.monotonic())
        with self.lock:
            self.runs[run.id] = run
            # Oldest first, so the trim takes the ones nobody is watching.
            while len(self.runs) > KEEP:
                self.runs.pop(next(iter(self.runs)))
        threading.Thread(target=self._work, args=(run, root), daemon=True).start()
        return run

    def get(self, run_id: str) -> Run | None:
        with self.lock:
            return self.runs.get(run_id)

    def _work(self, run: Run, root: Any) -> None:
        """The command, in this process, with its output captured.

        In-process rather than a subprocess, for three reasons. The verbs
        already return objects that a subprocess would flatten to stdout
        and force us to re-parse. A second process reading the repo can
        break a writer on Windows, which is what `write_atomic`'s retry
        loop exists for. And a thread is the concurrency this app already
        has: every endpoint is `def`, so they all run in one.
        """
        from .. import cli

        out, err = io.StringIO(), io.StringIO()
        code = 1
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["--root", str(root), *run.argv])
        except SystemExit as exc:  # argparse, on a malformed argv
            code = int(exc.code or 0)
        except Exception as exc:  # pragma: no cover - reported, not raised
            err.write(f"{type(exc).__name__}: {exc}")
        printed = out.getvalue().strip()
        data: Any = None
        if printed:
            try:
                data = json.loads(printed)
            except json.JSONDecodeError:
                # Not every verb prints JSON for every shape of run. The
                # text is still the answer, so hand it over as one.
                data = {"text": printed}
        with self.lock:
            run.seconds = time.monotonic() - run.started
            run.ok = code == 0
            run.data = data
            run.said = err.getvalue().strip()
            run.done = True


class Refused(ValueError):
    """The command may not be run from here, and why."""


def argv_for(line: str, reads: set[str], known: set[str]) -> list[str]:
    """The argv inside an offered command line, if it may be run here.

    `reads` is every subcommand the parser declares as showing you
    something, and `known` is every subcommand there is. Both, because
    the arity has to be settled before the permission: with only the
    reading set, `forge anki push` fails to match as two words, falls
    back to its first word, finds `anki` among the reads and runs the
    push. The name is whatever the parser would resolve, and only then is
    it asked whether it may run.
    """
    words = shlex.split(line.replace("uv run ", "", 1))
    if not words or words[0] != "forge":
        raise Refused(f"not a forge command: {line!r}")
    rest = [w for w in words[1:] if w != "--json"]
    if not rest:
        raise Refused("no command named")
    two = " ".join(rest[:2])
    name = two if two in known else rest[0]
    if name not in reads:
        raise Refused(
            f"`forge {name}` is not a command this can run. Only the ones that"
            " show you something, which is what `forge --help` groups first"
        )
    # `--json` for everything: the panel renders a result rather than a
    # transcript, and every one of these has the flag.
    return [*rest, "--json"]
