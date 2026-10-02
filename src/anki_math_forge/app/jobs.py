"""Running a command from the website, in the background (ROADMAP.md §12).

**Every command with no model behind it**, which is what §12 set out to
reach. The parser declares an `effect` on each one (docs/VERBS.md) and
that decides how it is offered, not whether: a `reads` runs on a click,
and a `repo` or an `anki` says what it will change and waits to be told
again. The declaration is the whole safety story and it is one rule
rather than a list kept by hand, so a verb that starts writing tomorrow
starts asking first on the same commit, without anybody remembering to
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
    #: What it changes, so a list of runs can say which ones wrote.
    effect: str = "reads"
    #: Wall-clock start, for a list a person reads. `started` is monotonic
    #: and only good for measuring.
    at: float = field(default_factory=time.time)
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
            "run": "forge " + " ".join(a for a in self.argv if a != "--json"),
            "effect": self.effect,
            "at": round(self.at),
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

    def start(self, argv: list[str], root: Any, effect: str = "reads") -> Run:
        run = Run(
            id=uuid.uuid4().hex[:12],
            argv=list(argv),
            started=time.monotonic(),
            effect=effect,
        )
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

    def listed(self) -> list[Run]:
        """Every run this server remembers, newest first.

        So a result outlives the page that asked for it: start a push,
        go and triage something else, and the answer is still there to
        read when it lands.
        """
        with self.lock:
            return list(reversed(self.runs.values()))

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


def argv_for(line: str, effects: dict[str, str]) -> tuple[list[str], str]:
    """`(argv, effect)` for an offered command line, or a refusal.

    `effects` maps every subcommand, by the words you type, to what it
    does: `reads`, `repo` or `anki`. The whole map rather than the
    reading half of it, because arity has to be settled before
    permission: knowing only the reads, `forge anki push` fails to match
    as two words, falls back to its first word, finds `anki` among them
    and runs the push. The name is whatever the parser would resolve, and
    only then is it asked what it does.

    Nothing is refused for writing. What writes needs saying out loud
    first, which is the caller's job and not this one's; what is refused
    here is a command the parser does not have.
    """
    words = shlex.split(line.replace("uv run ", "", 1))
    if not words or words[0] != "forge":
        raise Refused(f"not a forge command: {line!r}")
    rest = [w for w in words[1:] if w != "--json"]
    if not rest:
        raise Refused("no command named")
    two = " ".join(rest[:2])
    name = two if two in effects else rest[0]
    if name not in effects:
        raise Refused(f"`forge {name}` is not a command")
    # `--json` for everything: the panel renders a result rather than a
    # transcript, and every one of these has the flag.
    return [*rest, "--json"], effects[name]


#: What to say before running one, by effect. A confirmation is only worth
#: having while it says something the label does not, so each names what
#: this particular command puts at risk rather than asking "are you sure".
WARNINGS = {
    "repo": "changes files in this repo. Run it?",
    "anki": "changes your Anki collection, which nothing here can undo. Run it?",
}
