"""What changed on a card since you last decided on it (ROADMAP §21).

A card is changed by several hands: `/augment`, `/triage` working a note,
the editor on the review page, `$EDITOR`. When it comes back for review the
question is what is different, and the file alone cannot say.

**Local and disposable.** One JSON file per card under the work dir
(`.forge/changes/<uid>.json`), which is not in git. Deleting it loses the
history and nothing else: no card, no decision and no command reads it.

A snapshot is taken when a card is written by `cards new` and each time you
decide on it in review (approve, reject, back to draft). The review page
compares the file with the last snapshot, so it sees every edit made since,
whoever made it and however. Each decision files the difference it was made
over into the history.
"""

from __future__ import annotations

import difflib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .model import Card, is_resolved, resolved_body, write_atomic

#: The decision itself and its stamp. A record of what changed under a
#: decision should not list the decision as one of the changes.
UNTRACKED = frozenset({"status", "content_hash"})

#: Enough to answer "what happened to this card lately". Older rounds are
#: dropped first.
KEPT = 20

#: A one-line summary is one line in an aside 240px wide.
WIDTH = 60


@dataclass
class Change:
    """The difference between two snapshots of one card."""

    #: `(key, before, after)` for each frontmatter key that moved.
    fields: list[tuple[str, Any, Any]] = field(default_factory=list)
    #: `(section, one line)` for each section whose text moved.
    sections: list[tuple[str, str]] = field(default_factory=list)
    #: `resolved:` lines added since: what whoever changed it said they did.
    resolved: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.fields or self.sections or self.resolved)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fields": [{"key": k, "before": b, "after": a} for k, b, a in self.fields],
            "sections": [{"name": n, "summary": s} for n, s in self.sections],
            "resolved": list(self.resolved),
        }


def snapshot(card: Card) -> dict[str, Any]:
    """What a later diff compares against, as plain JSON."""
    raw = {
        "frontmatter": {k: v for k, v in card.frontmatter.items() if k not in UNTRACKED},
        "sections": {s.name: s.body.strip() for s in card.sections},
    }
    # Through JSON and back, so a date or a set in the frontmatter compares
    # equal to what was stored rather than to its own Python object.
    return dict(json.loads(json.dumps(raw, default=str, ensure_ascii=False)))


def diff(before: dict[str, Any], after: dict[str, Any]) -> Change:
    change = Change()
    old_fm, new_fm = before.get("frontmatter", {}), after.get("frontmatter", {})
    for key in sorted(set(old_fm) | set(new_fm)):
        if old_fm.get(key) != new_fm.get(key):
            change.fields.append((key, old_fm.get(key), new_fm.get(key)))

    old_sec, new_sec = before.get("sections", {}), after.get("sections", {})
    names = list(new_sec) + [name for name in old_sec if name not in new_sec]
    for name in names:
        was, now = old_sec.get(name, ""), new_sec.get(name, "")
        if was == now:
            continue
        if name == "notes":
            # Open annotations are on screen already. What is worth having
            # here is what got settled, in the words it was settled in.
            seen = {line.strip() for line in was.splitlines()}
            change.resolved += [
                resolved_body(line)
                for line in now.splitlines()
                if is_resolved(line) and line.strip() not in seen
            ]
            continue
        change.sections.append((name, one_line(was, now)))
    return change


def one_line(was: str, now: str) -> str:
    """The first place two texts differ, in a line, and how many more."""
    if not was:
        return f'added "{_clip(now)}"'
    if not now:
        return "removed"
    old, new = was.split(), now.split()
    edits = [
        op
        for op in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes()
        if op[0] != "equal"
    ]
    if not edits:
        # Only the spacing moved.
        return "whitespace"
    _, i1, i2, j1, j2 = edits[0]
    took, gave = " ".join(old[i1:i2]), " ".join(new[j1:j2])
    if took and gave:
        text = f'"{_clip(took)}" -> "{_clip(gave)}"'
    elif gave:
        text = f'added "{_clip(gave)}"'
    else:
        text = f'cut "{_clip(took)}"'
    more = len(edits) - 1
    return text + (f" (+{more} more)" if more else "")


def _clip(text: str, width: int = WIDTH // 2) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


# -- the record ---------------------------------------------------------------


def _path(config: Config, uid: str) -> Path:
    return config.work_dir / "changes" / f"{uid}.json"


def load(config: Config, uid: str) -> dict[str, Any] | None:
    path = _path(config, uid)
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def record(config: Config, card: Card, decision: str) -> None:
    """Take a snapshot, filing what changed since the last one.

    Never fails the write it follows: this is a convenience kept beside the
    card, and a review decision that errored because a cache could not be
    written would be the tail wagging the dog.
    """
    if not card.uid:
        return
    try:
        rec = load(config, card.uid) or {}
        now = snapshot(card)
        at = time.strftime("%Y-%m-%d %H:%M")
        history: list[dict[str, Any]] = list(rec.get("history", []))
        entry: dict[str, Any] = {"at": at, "decision": decision}
        if rec.get("seen") is not None:
            entry["since"] = rec.get("at", "")
            entry["after"] = rec.get("decision", "")
            entry["change"] = diff(rec["seen"], now).as_dict()
        history.append(entry)
        rec = {"seen": now, "at": at, "decision": decision, "history": history[-KEPT:]}
        path = _path(config, card.uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, json.dumps(rec, indent=1, ensure_ascii=False))
    except OSError:
        return


def view(config: Config, card: Card) -> dict[str, Any] | None:
    """What the review page and `forge cards --changes` show: what moved
    since the last snapshot, and the rounds before it, newest first. `None`
    for a card with no record yet."""
    rec = load(config, card.uid)
    if rec is None or rec.get("seen") is None:
        return None
    pending = diff(rec["seen"], snapshot(card))
    return {
        "since": rec.get("at", ""),
        "after": rec.get("decision", ""),
        "pending": pending.as_dict() if pending else None,
        "history": list(reversed(rec.get("history", []))),
    }
