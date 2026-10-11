"""`inbox.md`: what you know about a project's subject, waiting to be placed.

A fact you heard, a correction, a result met somewhere else: something that
belongs in this deck without your knowing where. The setup stage takes it
as typed and appends it here under a dated heading, and `/sort-notes` hands
each waiting dump to the `note-sorter` agent, which finds the card it fits
on or adds a unit for it (ROADMAP §20).

**Three ways to place a dump**, chosen when you add it and written on its
heading after the stamp:

- **propose**, the default, with no word. Each piece is parked where you
  decide it: an `@me` note on the card it bears on, or a new unit waiting
  in triage.
- **modify existing cards** (` · write`). The sorter edits the card itself,
  leaves an `@claude` brief on a unit not yet carded, and queues a new unit
  for `/sort-notes` to have carded.
- **both** (` · both`). Propose and modify at once: the sorter chooses,
  piece by piece, editing what it can confirm and what leaves a card
  asking the same question, and proposing the rest. On the page it is the two
  boxes ticked together, not a third option.

Whichever it is, nothing reaches Anki unreviewed. An edit changes
`content_hash`, so an approved card is a draft again until you approve it
(invariants 1 and 5). Every line the sorter leaves on a card names the dump
(`inbox <stamp>:`), which is how the review page says where an edit came
from (`changes.origins`).

**Nothing is deleted.** A dump is unsorted until the sorter marks it
`sorted` and writes under it where each piece went, the way a resolved
annotation keeps what was asked and what came of it. That list is the brief
you read on the setup stage, in two lists there: unsorted and sorted. A
dump can be put back to unsorted to be placed again. An older file may say
` · done`, which is read as `sorted`.

The shape, which is also what you would type:

    ## 2026-10-03 14:02 · write
    The bound in Hoeffding needs independence, not only zero mean.

    ## 2026-10-02 10:00 · sorted
    Jensen's inequality for conditional expectations.

    ### where it went
    - @me on card `4b2e1c` (Hoeffding's inequality): the conditions miss independence
    - new unit `stats:conditional-jensen`: Jensen for conditional expectations

Markdown, appended to and never rewritten wholesale, so it is a file you can
edit by hand as well (invariant 2).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import INBOX_FILE, Config, ConfigError
from .model import write_atomic

WAITING, SORTED = "waiting", "sorted"
STATES = (WAITING, SORTED)

#: What `sorted` was followed by, once. Still read, as `sorted`.
LEGACY = {"done": SORTED}

#: How a dump is placed. `propose` is the default and has no word on the
#: heading; the other two do.
PROPOSE, WRITE, BOTH = "propose", "write", "both"
MODES = (PROPOSE, WRITE, BOTH)

#: One dump: a level-two heading, then whatever was typed under it.
_HEADING = re.compile(r"^## (.+?)\s*$", re.M)
_BRIEF = re.compile(r"^### where it went\s*$", re.M)
#: A unit id or a card uid, in backticks, inside a brief line.
_UNIT = re.compile(r"`([\w.-]+:[^`\s]+)`")
_CARD = re.compile(r"`([0-9a-f]{6})`")


@dataclass(frozen=True)
class Dump:
    """One thing you added, and what became of it."""

    stamp: str
    state: str
    text: str
    mode: str = PROPOSE
    #: The sorter's list of where each piece went, one line each.
    brief: tuple[str, ...] = ()
    units: tuple[str, ...] = field(default_factory=tuple)
    cards: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "stamp": self.stamp,
            "state": self.state,
            "mode": self.mode,
            "text": self.text,
            "brief": list(self.brief),
            "units": list(self.units),
            "cards": list(self.cards),
        }


def path_for(config: Config, project: str) -> Path:
    return config.projects_dir / project / INBOX_FILE


def _heading(stamp: str, state: str, mode: str) -> str:
    parts = [stamp]
    if mode != PROPOSE:
        parts.append(mode)
    if state != WAITING:
        parts.append(state)
    return "## " + " · ".join(parts)


def _parse_heading(line: str) -> tuple[str, str, str]:
    """`2026-10-03 14:02 · write · sorted` -> stamp, state, mode."""
    stamp, *rest = (part.strip() for part in line.split("·"))
    # `decide` is what `both` was called first, and `done` what came after
    # `sorted`. Both are still read.
    words = [LEGACY.get(word, BOTH if word == "decide" else word) for word in rest]
    state = next((word for word in words if word in STATES), WAITING)
    mode = next((word for word in words if word in MODES), PROPOSE)
    return stamp, state, mode


def _checked(mode: str) -> str:
    mode = BOTH if mode == "decide" else mode
    if mode not in MODES:
        raise ConfigError(f"{mode!r} is not one of {', '.join(MODES)}")
    return mode


def add(config: Config, project: str, text: str, *, mode: str = PROPOSE) -> int:
    """Append one dump, to be placed the way `mode` says, and return how
    many are waiting."""
    mode = _checked(mode)
    body = text.strip()
    if not body:
        raise ConfigError("nothing to add")
    folder = config.projects_dir / project
    if not folder.is_dir():
        raise ConfigError(f"no project {project!r}")
    path = path_for(config, project)
    before = path.read_text(encoding="utf-8") if path.exists() else "# Inbox\n"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    taken = {d.stamp for d in dumps(config, project)}
    # Two dumps in one minute would share a heading, and the heading is how
    # a dump is addressed.
    n = 2
    unique = stamp
    while unique in taken:
        unique = f"{stamp} ({n})"
        n += 1
    heading = _heading(unique, WAITING, mode)
    write_atomic(path, before.rstrip("\n") + f"\n\n{heading}\n\n{body}\n")
    return waiting(config, project)


def dumps(config: Config, project: str) -> list[Dump]:
    """Every dump in the file, newest first."""
    path = path_for(config, project)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    heads = list(_HEADING.finditer(text))
    out: list[Dump] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stamp, state, mode = _parse_heading(head.group(1))
        body = text[head.end() : end]
        split = _BRIEF.search(body)
        said = body[: split.start()] if split else body
        brief_text = body[split.end() :] if split else ""
        brief = tuple(
            line.strip()[2:].strip()
            for line in brief_text.splitlines()
            if line.strip().startswith(("- ", "* "))
        )
        joined = " ".join(brief)
        out.append(
            Dump(
                stamp=stamp,
                state=state,
                mode=mode,
                text=said.strip(),
                brief=brief,
                units=tuple(dict.fromkeys(_UNIT.findall(joined))),
                cards=tuple(dict.fromkeys(_CARD.findall(joined))),
            )
        )
    return list(reversed(out))


def waiting(config: Config, project: str) -> int:
    """How many dumps nobody has sorted yet."""
    return sum(1 for d in dumps(config, project) if d.state == WAITING and d.text)


def mark(config: Config, project: str, stamp: str, state: str) -> None:
    """Set one dump's state, by its heading. The text, the brief and the
    way it is placed stay."""
    state = LEGACY.get(state, state)
    if state not in STATES:
        raise ConfigError(f"{state!r} is not one of {', '.join(STATES)}")
    _rehead(config, project, stamp, lambda _state, mode: (state, mode))


def set_mode(config: Config, project: str, stamp: str, mode: str) -> None:
    """Choose how a waiting dump is placed.

    Only while it waits. A sorted dump has been placed one way already, and
    its brief says how; to place it another way, put it back to waiting
    first.
    """
    mode = _checked(mode)

    def change(state: str, _mode: str) -> tuple[str, str]:
        if state != WAITING:
            raise ConfigError(
                f"the dump headed {stamp!r} is {state} already; put it back to waiting first"
            )
        return state, mode

    _rehead(config, project, stamp, change)


def _rehead(
    config: Config,
    project: str,
    stamp: str,
    change: Callable[[str, str], tuple[str, str]],
) -> None:
    """Rewrite one dump's heading, found by its stamp, through `change`."""
    path = path_for(config, project)
    if not path.exists():
        raise ConfigError(f"{project} has no inbox")
    text = path.read_text(encoding="utf-8")
    for head in _HEADING.finditer(text):
        found, state, mode = _parse_heading(head.group(1))
        if found != stamp:
            continue
        line = _heading(stamp, *change(state, mode))
        write_atomic(path, text[: head.start()] + line + text[head.end() :])
        return
    raise ConfigError(f"no dump headed {stamp!r} in {project}'s inbox")

