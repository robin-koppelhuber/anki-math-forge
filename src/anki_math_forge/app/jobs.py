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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import run_views

#: How many runs to remember. The runs window lists them, and a list of
#: the last fifty is a morning's work without being a log nobody reads.
KEEP = 50

#: A raw result bigger than this is not kept across a restart: one
#: `units --json` is the whole ledger. The rendered view is kept, which is
#: what the window shows first.
KEPT_DATA = 100_000


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
    #: The command by the words typed (`anki push`), which is what decides
    #: how its result is described.
    verb: str = ""
    #: `run_views.describe` over the result: a summary line, a tone and
    #: the blocks worth looking at. Set once, when the run finishes.
    view: dict[str, Any] | None = None

    def row(self) -> dict[str, Any]:
        """What a list of runs needs: no output, which can be the whole
        ledger and is read one run at a time."""
        view = self.view or {}
        from . import actions

        # The action this run is, with its fields, so the window opened on
        # it starts the builder on the same command rather than on whatever
        # action happens to come first.
        found = actions.match([a for a in self.argv if a != "--json"])
        return {
            "id": self.id,
            "action": found[0].key if found else "",
            "values": found[1] if found else {},
            "run": "forge " + " ".join(a for a in self.argv if a != "--json"),
            "verb": self.verb,
            "effect": self.effect,
            "at": round(self.at),
            "done": self.done,
            "ok": self.ok,
            "seconds": round(self.seconds, 2),
            "summary": view.get("summary", ""),
            "tone": view.get("tone", ""),
        }

    def payload(self) -> dict[str, Any]:
        view = self.view or {}
        return {
            **self.row(),
            "blocks": view.get("blocks", []),
            "data": self.data,
            "said": self.said,
        }


@dataclass
class Runner:
    """Every run this server has been asked for, newest last.

    With a `store`, the finished ones are written there after each run and
    read back when the server starts, so the history outlives a restart.
    Local and disposable, like the change records: losing the file loses
    the list and nothing else. A run still going when the server stopped
    is not in it; it never finished.
    """

    runs: dict[str, Run] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    store: Path | None = None

    def load(self) -> None:
        if self.store is None or not self.store.exists():
            return
        try:
            saved = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        with self.lock:
            for raw in saved if isinstance(saved, list) else ():
                try:
                    run = Run(**{**raw, "started": 0.0})
                except TypeError:
                    continue
                self.runs[run.id] = run

    def _save(self) -> None:
        """Every finished run, to the store. Called with the lock held."""
        if self.store is None:
            return
        kept = []
        for run in self.runs.values():
            if not run.done:
                continue
            raw = asdict(run)
            if len(json.dumps(raw.get("data"), default=str)) > KEPT_DATA:
                raw["data"] = None
            kept.append(raw)
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps(kept, default=str), encoding="utf-8")
        except OSError:
            return

    def start(
        self, argv: list[str], root: Any, effect: str = "reads", verb: str = ""
    ) -> Run:
        run = Run(
            id=uuid.uuid4().hex[:12],
            argv=list(argv),
            started=time.monotonic(),
            effect=effect,
            verb=verb or (argv[0] if argv else ""),
        )
        with self.lock:
            self.runs[run.id] = run
            # Oldest finished first, so the trim never takes a run that is
            # still going.
            while len(self.runs) > KEEP:
                oldest = next((k for k, r in self.runs.items() if r.done), None)
                if oldest is None:
                    break
                self.runs.pop(oldest)
        threading.Thread(target=self._work, args=(run, root), daemon=True).start()
        return run

    def get(self, run_id: str) -> Run | None:
        with self.lock:
            return self.runs.get(run_id)

    def forget_finished(self) -> int:
        """Drop every finished run, and say how many. Runs in flight stay:
        their result has nowhere else to land."""
        with self.lock:
            gone = [k for k, r in self.runs.items() if r.done]
            for key in gone:
                self.runs.pop(key)
            self._save()
        return len(gone)

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
        said = err.getvalue().strip()
        view = run_views.describe(run.verb, data, code == 0, said)
        with self.lock:
            run.seconds = time.monotonic() - run.started
            run.ok = code == 0
            run.data = data
            run.said = said
            run.view = view
            run.done = True
            self._save()


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
