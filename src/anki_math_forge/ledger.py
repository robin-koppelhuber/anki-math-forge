"""The units ledger: `units.jsonl`, one unit per line (DESIGN.md §4).

A unit is one equation, its context, a stable locator, and a best-effort
transcription. `state` tracks human triage:

    new -> queued -> carded
        \\-> skipped   (sticky: never re-offered)

`extract` is re-runnable: `upsert` preserves the state of everything already
in the file and only adds genuinely new ids, so working through a book is an
incrementally resumable queue rather than a one-shot dump.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .model import ANNOTATION_PREFIX, annotation_audience, write_atomic

STATES = ("new", "queued", "skipped", "carded")

# Fields extraction owns: refreshed on re-extract, because re-segmenting is
# exactly how you fix a wrong bounding box. Everything else -- state, reason,
# uids, notes -- belongs to the human and survives untouched.
EXTRACTED_FIELDS = ("locator", "context")

# Transcriptions are *not* extraction output any more: `/transcribe` reads the
# crops and writes them. Re-extracting must never destroy that work, so these
# are only ever filled in when they are empty, never overwritten.
TRANSCRIPTION_FIELDS = ("tex_source", "tex_auto", "transcription")


@dataclass
class Locator:
    """Where a unit is: in the document, and on the page.

    `bbox` is the segmenter's actual output, in PDF points, top-left origin.
    Keeping it -- rather than only a rendered crop of it -- is what makes a
    re-segmentation show up as a reviewable diff instead of an opaque pile of
    changed PNGs, and it is what the crop is rendered from on demand.
    """

    section: str = ""
    # The Cookbook's own key, and the only thing `extract/pdf.py` emits. Kept
    # rather than migrated: that module is frozen (§13), and rewriting 751
    # ledger lines to say `kind: equation` would be churn for no new fact.
    # `ref` below reads it and the general form the same way.
    equation: int | None = None
    # The general form, for sources that number something other than equations.
    # `kind` is the family a contiguity check runs over ("equation",
    # "theorem", "lemma"); `label` is the number within it ("2.4", "61").
    kind: str = ""
    label: str = ""
    # Which file inside the source, when a source has more than one. Empty
    # means the only one. A Zotero item is routinely many documents: a paper
    # plus its appendix, or a book as fifteen chapter PDFs, and page 17 of one
    # is not page 17 of another.
    document: str = ""
    page: int | None = None
    bbox: list[float] | None = None

    @property
    def ref(self) -> tuple[str, str]:
        """`(kind, label)`, however this unit happens to record it.

        The shim between the frozen segmenter and everything after it: one
        place reads `equation`, and nothing else has to know it exists.
        """
        if self.label or self.kind:
            # A kind with no label is normal: a Zotero highlight is a
            # "highlight" and nothing numbers it.
            return self.kind or "equation", self.label
        if self.equation is not None:
            return "equation", str(self.equation)
        return "", ""

    def describe(self) -> str:
        """A human reading of where this is, for a citation line."""
        bits = []
        if self.section:
            bits.append(f"§{self.section}")
        kind, label = self.ref
        if label:
            # An unnumbered kind contributes nothing to a citation: "p. 8" is
            # what you want, not "Highlight, p. 8".
            bits.append(f"eq. {label}" if kind == "equation" else f"{kind.capitalize()} {label}")
        if self.page is not None:
            bits.append(f"p. {self.page}")
        return ", ".join(bits)


@dataclass
class Mark:
    """One human mark inside a unit: a highlight, an underline, a sticky note.

    A unit is a *region*, and a region can carry several marks that belong
    together. Zotero is where these come from today, but nothing here is
    Zotero-shaped: a mark is a kind, a colour, what it covers and what the
    reader said about it, which is what a PDF annotation layer is anywhere.
    It is called a mark and not an annotation because this project already
    uses that word for the `@claude` lines in a card's `## notes`.

    The first mark on a unit is the one the unit came from -- its key is the
    unit's id -- and the rest are what you marked around it.

    What a kind or a colour *means* is deliberately not here. It lives in the
    config and is resolved when something displays a mark, so that editing your
    scheme changes every unit at once instead of only the ones imported since.

    `key` is the source's own permanent id for the mark, never a position.
    Marks are what *changes* inside a unit as you keep reading, so deriving
    anything durable from their order would renumber the world every time a
    sentence got highlighted.
    """

    key: str = ""
    kind: str = ""  # highlight | underline | note | image | ink
    colour: str = ""  # the name, not the hex: "purple"
    text: str = ""  # what it covers on the page
    comment: str = ""  # what the reader wrote about it
    bbox: list[float] | None = None  # top-left origin, like every other bbox
    order: str = ""  # the source's own reading-order key

    @property
    def content(self) -> str:
        """A note covers nothing; its comment is the whole of it."""
        return self.comment if self.kind == "note" else self.text


@dataclass
class Suggestion:
    """A proposed triage decision, and who proposed it.

    A suggestion is *not* a decision. Nothing acts on it until a human accepts
    it, because the thing making it -- a regex over a mangled text layer, or a
    model looking at a picture -- is guessing, and a guess that silently
    changes state is indistinguishable from a bug to whoever meets it later.
    """

    state: str = ""  # the state being proposed, e.g. "skipped"
    reason: str = ""  # short, machine-ish: "no-relation"
    detail: str = ""  # the argument, for a human deciding
    by: str = ""  # what proposed it: "classify" | "claude" | ...


@dataclass
class Unit:
    id: str
    locator: Locator = field(default_factory=Locator)
    tex_auto: str = ""
    tex_source: str | None = None
    transcription: str = "none"  # ok | failed | none
    context: str = ""
    state: str = "new"
    reason: str = ""  # why it was skipped
    uids: list[str] = field(default_factory=list)  # cards produced from it
    notes: list[str] = field(default_factory=list)  # @claude annotations
    marks: list[Mark] = field(default_factory=list)  # what a reader marked here
    # Pages either side of this one that a card writer should be handed. `None`
    # inherits the source's setting, which inherits the repo's. Set during
    # triage, where you can see that a theorem's hypotheses are two pages back
    # and the default window would cut them off. Human-owned: extraction never
    # touches it, so it survives a re-segmentation like `state` does.
    context_pages: int | None = None
    suggestion: Suggestion | None = None  # proposed, never applied

    @property
    def source(self) -> str:
        return self.id.split(":", 1)[0]

    @property
    def tex(self) -> str:
        """The transcription to show: source LaTeX if we have it, else the
        one `/transcribe` read off the crop."""
        return self.tex_source or self.tex_auto

    @property
    def has_crop(self) -> bool:
        """True when this unit can be rendered from its source document."""
        return self.crop_geometry() is not None

    def crop_geometry(self) -> tuple[int, list[float]] | None:
        """`(page, bbox)` when this unit has page geometry, else None."""
        if self.locator.page is None or self.locator.bbox is None:
            return None
        return self.locator.page, self.locator.bbox

    @property
    def authoritative(self) -> bool:
        """True when the transcription came from real LaTeX source, not OCR."""
        return bool(self.tex_source)

    def citation(self, title: str) -> str:
        label = self.locator.describe()
        return f"{title} {label}" if label else title

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["locator"] = {k: v for k, v in data["locator"].items() if v not in ("", None)}
        # Same treatment as the locator: a mark with no comment should not
        # write `"comment": ""` on every line of the ledger.
        marks = [{k: v for k, v in m.items() if v not in ("", None)} for m in data.get("marks", [])]
        if marks:
            data["marks"] = marks
        else:
            data.pop("marks", None)
        if data.get("suggestion") is None:
            data.pop("suggestion", None)
        if data.get("context_pages") is None:
            data.pop("context_pages", None)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Unit:
        raw_locator = data.get("locator") or {}
        known = {f for f in cls.__dataclass_fields__ if f != "locator"}
        fields = Locator.__dataclass_fields__
        raw_suggestion = data.get("suggestion") or None
        suggestion = (
            Suggestion(
                **{k: v for k, v in raw_suggestion.items() if k in Suggestion.__dataclass_fields__}
            )
            if isinstance(raw_suggestion, dict)
            else None
        )
        mark_fields = Mark.__dataclass_fields__
        marks = [
            Mark(**{k: v for k, v in row.items() if k in mark_fields})
            for row in data.get("marks") or []
            if isinstance(row, dict)
        ]
        rest = {k: v for k, v in data.items() if k in known and k not in ("suggestion", "marks")}
        return cls(
            locator=Locator(**{k: v for k, v in raw_locator.items() if k in fields}),
            suggestion=suggestion,
            marks=marks,
            **rest,
        )


class Ledger:
    """A units.jsonl file. Insertion order is document order; keep it."""

    def __init__(self, path: Path, units: list[Unit] | None = None) -> None:
        self.path = path
        self.units: list[Unit] = units or []

    # -- io ---------------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> Ledger:
        units: list[Unit] = []
        if path.exists():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    units.append(Unit.from_json(json.loads(line)))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{path}:{lineno}: bad unit record: {exc}") from exc
        return cls(path, units)

    def save(self) -> None:
        lines = [json.dumps(u.to_json(), ensure_ascii=False, sort_keys=True) for u in self.units]
        write_atomic(self.path, "\n".join(lines) + ("\n" if lines else ""))

    @classmethod
    @contextmanager
    def edit(cls, path: Path) -> Iterator[Ledger]:
        """Load, mutate, save -- with nobody else in the file meanwhile.

        Every write rewrites the whole ledger, so two processes that each
        load, change one unit and save produce last-writer-wins: the earlier
        change vanishes with no error anywhere. That is not hypothetical --
        six classifier agents running in parallel destroyed 45 of 61
        suggestions this way. Anything that mutates a ledger goes through
        here; `load` alone is for readers.
        """
        with lock(path):
            led = cls.load(path)
            yield led
            led.save()

    # -- access -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.units)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.units)

    def get(self, unit_id: str) -> Unit | None:
        return next((u for u in self.units if u.id == unit_id), None)

    def select(self, state: str | None = None, section: str | None = None) -> list[Unit]:
        units = self.units
        if state and state != "all":
            units = [u for u in units if u.state == state]
        if section:
            units = [u for u in units if u.locator.section == section]
        return list(units)

    def counts(self) -> dict[str, int]:
        return {state: sum(1 for u in self.units if u.state == state) for state in STATES}

    def sections(self) -> list[str]:
        seen = {u.locator.section for u in self.units if u.locator.section}
        return sorted(seen, key=_section_key)

    # -- mutation ---------------------------------------------------------
    def upsert(self, incoming: list[Unit]) -> tuple[int, int]:
        """Merge freshly extracted units. Returns (added, refreshed).

        Existing units keep their state, skip reason, uids and notes. Only the
        extraction-owned fields are refreshed, and only for units still `new`
        -- once you have triaged something, re-extracting must not move the
        ground under it.
        """
        by_id = {u.id: u for u in self.units}
        added = refreshed = 0
        for unit in incoming:
            existing = by_id.get(unit.id)
            if existing is None:
                self.units.append(unit)
                by_id[unit.id] = unit
                added += 1
                continue
            if existing.state == "new":
                for name in EXTRACTED_FIELDS:
                    setattr(existing, name, getattr(unit, name))
                if existing.transcription == "none":
                    # Nothing has read this one yet, so adopt whatever the
                    # segmenter came with (the tex path transcribes as it
                    # goes). A unit that *has* been read keeps what it says.
                    for name in TRANSCRIPTION_FIELDS:
                        setattr(existing, name, getattr(unit, name))
                refreshed += 1
        return added, refreshed

    def suggest(self, unit_id: str, state: str, reason: str, detail: str, by: str) -> Unit:
        """Record a proposed decision. Changes no state."""
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; expected one of {', '.join(STATES)}")
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        unit.suggestion = Suggestion(state=state, reason=reason, detail=detail, by=by)
        return unit

    def accept(self, unit_id: str) -> Unit:
        """Act on a suggestion, and clear it."""
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        if unit.suggestion is None or not unit.suggestion.state:
            raise ValueError(f"{unit_id} has nothing suggested")
        proposed = unit.suggestion
        self.set_state(unit_id, proposed.state, reason=proposed.reason)
        unit.suggestion = None
        return unit

    def dismiss(self, unit_id: str) -> Unit:
        """Reject a suggestion, leaving the unit as it was."""
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        unit.suggestion = None
        return unit

    def set_state(self, unit_id: str, state: str, *, reason: str = "") -> Unit:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; expected one of {', '.join(STATES)}")
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        unit.state = state
        if state == "skipped" or reason:
            unit.reason = reason
        # Deciding for yourself overrules anything that was proposed.
        unit.suggestion = None
        return unit

    def restore(self, unit_id: str, snapshot: dict[str, Any]) -> Unit:
        """Put a unit back exactly as it was, for undo.

        `set_state` is not an undo: it clears any suggestion and cannot tell
        you what the reason used to be. Mis-pressing `q` on a unit that was
        `skipped` with a proposal on it has to restore all three, or undo
        quietly loses work of its own.
        """
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        state = str(snapshot.get("state", unit.state))
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}; expected one of {', '.join(STATES)}")
        unit.state = state
        unit.reason = str(snapshot.get("reason", ""))
        proposed = snapshot.get("suggestion")
        unit.suggestion = Suggestion(**proposed) if proposed else None
        return unit

    def snapshot(self, unit_id: str) -> dict[str, Any]:
        """What `restore` needs to undo whatever happens next."""
        unit = self.get(unit_id)
        if unit is None:
            return {}
        return {
            "state": unit.state,
            "reason": unit.reason,
            "suggestion": asdict(unit.suggestion) if unit.suggestion else None,
        }

    def mark_carded(self, unit_id: str, uids: list[str]) -> Unit:
        unit = self.set_state(unit_id, "carded")
        for uid in uids:
            if uid not in unit.uids:
                unit.uids.append(uid)
        return unit

    def transcribe(self, unit_id: str, tex: str, checker: Any = None) -> tuple[str, str]:
        """Record a transcription for a unit, gated through KaTeX (§4)."""
        from .extract.transcribe import gate

        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        unit.transcription, unit.tex_auto = gate(tex, checker)
        self.save()
        return unit.transcription, unit.tex_auto

    def resolve_notes(self, unit_id: str, audience: str = "") -> int:
        """Clear a unit's annotations once they have been acted on.

        Card annotations resolve by deleting the line from `## notes`; without
        this, a unit annotation would have no way out and would sit in `todo`
        for ever.

        `audience` limits it to one side's notes. That matters: Claude
        resolving its own request must not delete a `@me` decision parked on
        the same unit, which clearing everything would do silently.
        """
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        before = len(unit.notes)
        if audience:
            unit.notes = [n for n in unit.notes if annotation_audience(n) != audience]
        else:
            unit.notes = []
        cleared = before - len(unit.notes)
        self.save()
        return cleared

    def annotate(self, unit_id: str, text: str) -> Unit:
        """Record an instruction for the next pass over this unit.

        Addressed: `@claude` is work for the model, `@me` is a decision only
        the human can make. An unaddressed note is assumed to be for Claude,
        which is what `n` in the triage view has always meant.
        """
        text = " ".join(text.split())
        if not annotation_audience(text):
            text = f"{ANNOTATION_PREFIX} {text}"
        unit = self.get(unit_id)
        if unit is None:
            raise KeyError(f"no unit {unit_id!r} in {self.path}")
        unit.notes.append(text)
        return unit


def _section_key(section: str) -> tuple[float, ...]:
    try:
        return tuple(float(part) for part in section.split("."))
    except ValueError:
        return (float("inf"),)



# -- the write lock -------------------------------------------------------
#
# A lock *file* rather than an OS advisory lock: it is the one mechanism that
# behaves the same on Windows and POSIX, and it is visible in a directory
# listing when something goes wrong.

LOCK_TIMEOUT = 30.0   # give up rather than hang a batch of agents forever
LOCK_STALE = 120.0    # a lock older than this belonged to a process that died
LOCK_POLL = 0.05


class LockTimeout(RuntimeError):
    """Somebody held the ledger lock for longer than LOCK_TIMEOUT."""


@contextmanager
def lock(path: Path, timeout: float = LOCK_TIMEOUT) -> Iterator[None]:
    """Hold an exclusive lock on `path` for the body of the `with`.

    `os.open(..., O_CREAT | O_EXCL)` is atomic on every platform we care
    about: exactly one process creates the file, everyone else gets EEXIST
    and waits.
    """
    lockfile = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            # A holder that died leaves the file behind. Break it, but only
            # once it is old enough that no live writer could still own it.
            try:
                age = time.time() - lockfile.stat().st_mtime
            except FileNotFoundError:
                continue  # released while we looked; go round again
            if age > LOCK_STALE:
                lockfile.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise LockTimeout(
                    f"{lockfile} held for over {timeout:g}s -- another "
                    f"forge is writing, or a stale lock needs deleting"
                ) from None
            time.sleep(LOCK_POLL)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lockfile.unlink(missing_ok=True)

def open_ledgers(sources_dir: Path) -> dict[str, Ledger]:
    """Every units.jsonl under the sources directory, keyed by source name."""
    ledgers: dict[str, Ledger] = {}
    if not sources_dir.exists():
        return ledgers
    for path in sorted(sources_dir.glob("*/units.jsonl")):
        ledgers[path.parent.name] = Ledger.load(path)
    return ledgers
