"""Card files: parse, render, hash, write.

A card is one markdown file: YAML frontmatter plus `## section` bodies
(DESIGN.md §5). Parsing is round-trip stable -- `parse(render(card)) == card`
and, for a file already in canonical form, `render(parse(text)) == text`.
Everything else in this package leans on that, so keep it dull.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

# Frontmatter keys in the order they are written back out. Unknown keys keep
# their relative order and land after these.
# ASCII record separator: it cannot occur in card text, so joining on it
# cannot make two different cards hash the same.
HASH_SEPARATOR = chr(30)

FRONTMATTER_ORDER = (
    "uid",
    "type",
    "status",
    "content_hash",
    "source",
    "unit",
    "frequency",
    "derivation",
    "requires",
    "tags",
    "verify",
)

# Two optional judgements about a card, both coarse on purpose.
#
# `frequency` -- how often this identity actually turns up. It decides what is
# worth carding at all, and what deserves to come back often.
#
# `derivation` -- what it would take to reconstruct it. `definitional` is the
# one that matters: some facts are true by definition and have nothing to
# derive, so "how hard to derive" is the wrong question for them. They are
# recognised, not reconstructed, and that is a different kind of review.
#
# Three values each, and no numbers: a 1-10 scale here would be invented
# precision that no two sessions would apply the same way.
FREQUENCIES = ("core", "common", "rare")
DERIVATIONS = ("definitional", "short", "long")

# Canonical section order. Unknown sections keep file order and land after.
# Reading order on the card, and the order sections are written in a file.
# `prose` comes straight after the answer because it is one sentence and it
# interprets: the short thing first, then the longer ones. It is also the only
# unlabelled block, so putting it between two labelled ones left no way to see
# where `proof` ended and it began.
SECTION_ORDER = (
    "front",
    "back",
    "conditions",
    "prose",
    "uses",
    "proof",
    "verify",
    "notes",
)

# Sections allowed per `type` (DESIGN.md §7: "section whitelist for the
# declared type").
#
# `identity` states a mathematical fact: it has a definite answer, and `verify`
# can check it numerically.
#
# `intuition` explains one. It is what a marked passage in a prose source turns
# into -- why a bound is tight, what a term is really measuring, which of two
# conditions is doing the work. Two sections come off it. `verify` has nothing
# to run against an explanation, and `conditions` belongs to a statement rather
# than to a reading of one; anything that genuinely needs a hypothesis stated
# is an identity wearing the wrong type.
SECTIONS_BY_TYPE: dict[str, frozenset[str]] = {
    "identity": frozenset(SECTION_ORDER),
    "intuition": frozenset(SECTION_ORDER) - {"verify", "conditions"},
}

REQUIRED_SECTIONS = ("front", "back")

# `## notes` never syncs and never enters the content hash (DESIGN.md §8):
# annotating a card is not an edit of the card, but the fix that resolves the
# annotation is.
# `verify` is a check on the author, not card content: it never reaches Anki
# (see notetype.FIELDS) and no reviewer sees it. Hashing it meant that fixing
# a test un-approved a card whose mathematics had not changed. If the claim
# itself changes, `front` or `back` changes with it and the hash moves anyway.
UNHASHED_SECTIONS = frozenset({"notes", "verify"})
# `verify` joins them for the same reason `## verify` is unhashed: it says
# whether a numeric check runs, not what the card claims. It never reaches
# Anki and no reviewer sees it. Leaving it hashed meant turning a test *on*
# un-approved a card whose mathematics had not changed -- precisely what
# exempting the section was for, undone by the flag that enables it.
UNHASHED_FRONTMATTER = frozenset({"status", "content_hash", "requires", "verify"})

STATUSES = ("draft", "approved", "rejected")

# An annotation is an instruction for the next pass over this thing, and it
# is addressed. `@claude` is work for the model -- fix this, check that.
# `@me` is a decision only the human can make, parked where it will be found
# again. Both block sync, because both mean "this is not finished".
ANNOTATION_PREFIX = "@claude"
ANNOTATION_PREFIXES = ("@claude", "@me")


def annotation_audience(line: str) -> str:
    """`claude`, `me`, or "" if this line is not an annotation at all."""
    head = line.strip().lower()
    for prefix in ANNOTATION_PREFIXES:
        if head.startswith(prefix):
            return prefix[1:]
    return ""


UID_RE = re.compile(r"^[0-9a-f]{6}$")
_SECTION_RE = re.compile(r"^##[ \t]+([A-Za-z][A-Za-z0-9_-]*)[ \t]*$")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)(?:\n)---[ \t]*(?:\n|\Z)", re.DOTALL)


class CardError(Exception):
    """A card file could not be parsed."""


class StaleFileError(Exception):
    """The file changed on disk since it was loaded (DESIGN.md §6)."""


@dataclass
class Section:
    name: str
    body: str

    def canonical(self) -> Section:
        lines = [line.rstrip() for line in self.body.replace("\r\n", "\n").split("\n")]
        return Section(self.name, "\n".join(lines).strip("\n"))


@dataclass
class Card:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    preamble: str = ""
    path: Path | None = None
    mtime_ns: int | None = None

    # -- frontmatter accessors -------------------------------------------
    @property
    def uid(self) -> str:
        return str(self.frontmatter.get("uid", "") or "")

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type", "") or "")

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status", "draft") or "draft")

    @property
    def frequency(self) -> str:
        return str(self.frontmatter.get("frequency", "") or "")

    @property
    def derivation(self) -> str:
        return str(self.frontmatter.get("derivation", "") or "")

    @property
    def units(self) -> list[str]:
        """Every unit this card came from.

        A card is not one-to-one with a unit in either direction. One unit
        splits into several cards -- that already worked, because a unit
        carries a list of uids. Several units merge into one card, which is
        the common case for a multi-line display the segmenter cut into
        pieces, and that needs `unit` to accept a list.
        """
        raw = self.frontmatter.get("unit", "")
        if isinstance(raw, list):
            return [str(u).strip() for u in raw if str(u).strip()]
        return [u.strip() for u in str(raw or "").split(",") if u.strip()]

    @property
    def unit(self) -> str:
        """The first unit, for the things that need exactly one: the crop
        shown beside the card, and the `src::` tag."""
        units = self.units
        return units[0] if units else ""

    @property
    def source(self) -> str:
        return str(self.frontmatter.get("source", "") or "")

    @property
    def source_name(self) -> str:
        """The source *key*, read off the unit ids.

        `source` is the human citation ("Some Book, ss3.1, eq. 148"); this is
        the key that indexes `sources/` and `[sources.*]`, read off the unit
        id's first segment. Derived rather than stored, so it cannot drift from
        the unit the card actually came from. Empty when the card names no
        unit, which the app treats as "belongs to every source" rather than
        to none: a card with no home should be visible, not lost.
        """
        for unit in self.units:
            head = unit.split(":", 1)[0].strip()
            if head:
                return head
        return ""

    @property
    def section_name(self) -> str:
        """The source section, when the unit id encodes one.

        `<source>:<section>:<number>` is one shape a unit id takes, and it is
        the shape a segmenter working from a numbered book produces: `2.3` in
        `matrix-cookbook:2.3:66`. It is not the only shape. A unit imported
        from a marked-up PDF is `<source>:<annotation key>`, which has no
        section in it at all, and reading the middle segment there returned the
        annotation key -- so every card got its own "section", the review
        view's section rail listed one row per card, and the `src::` tag meant
        to suspend a batch wholesale named exactly one note.

        Derived rather than stored for the same reason as `source_name`: a card
        filed under a section it does not come from is a second truth waiting
        to disagree with the first. Two segments means there is nothing to
        derive, so it says so.
        """
        for unit in self.units:
            parts = unit.split(":")
            if len(parts) >= 3 and parts[1].strip():
                return parts[1].strip()
        return ""

    @property
    def requires(self) -> list[str]:
        """Cards that must be introduced before this one.

        The ordering respects this absolutely: a prerequisite outranks
        frequency, because meeting a result whose proof you cannot follow is
        worse than meeting a rare one early. Everything else is a tiebreak.

        Use it only for a real dependency -- this card's proof or notation
        rests on that one. Two cards on a theme are not a dependency, and a
        graph that says they are makes the order rigid for no gain.
        """
        raw = self.frontmatter.get("requires") or []
        if isinstance(raw, str):
            return [u.strip() for u in raw.split(",") if u.strip()]
        return [str(u).strip() for u in raw if str(u).strip()]

    @property
    def tags(self) -> list[str]:
        raw = self.frontmatter.get("tags") or []
        if isinstance(raw, str):
            return [t for t in raw.split() if t]
        return [str(t) for t in raw]

    @property
    def verify_enabled(self) -> bool:
        return bool(self.frontmatter.get("verify", False))

    @property
    def stored_hash(self) -> str:
        return str(self.frontmatter.get("content_hash", "") or "")

    # -- sections ---------------------------------------------------------
    def section(self, name: str) -> str | None:
        for sec in self.sections:
            if sec.name == name:
                return sec.body
        return None

    def section_names(self) -> list[str]:
        return [s.name for s in self.sections]

    def set_section(self, name: str, body: str) -> None:
        for sec in self.sections:
            if sec.name == name:
                sec.body = body
                return
        self.sections.append(Section(name, body))
        self.sections = _sorted_sections(self.sections)

    def remove_section(self, name: str) -> None:
        self.sections = [s for s in self.sections if s.name != name]

    # -- annotations (DESIGN.md §8) ---------------------------------------
    def annotations(self) -> list[str]:
        """Open `@claude ...` / `@me ...` lines from `## notes`, verbatim."""
        body = self.section("notes") or ""
        return [line.strip() for line in body.split(chr(10)) if annotation_audience(line)]

    def add_annotation(self, text: str) -> None:
        """Append an annotation, byte-identical to one typed by hand."""
        text = " ".join(text.split()).strip()
        if not text:
            return
        # Any known prefix, not just `@claude`. Guarding on one of the two
        # turned an `@me` note into `@claude @me ...`, which reads back as
        # audience `claude` -- a decision parked for the human, queued as work
        # for the agent, which is the one mix-up the split exists to prevent.
        if not annotation_audience(text):
            text = f"{ANNOTATION_PREFIX} {text}"
        body = self.section("notes")
        self.set_section("notes", f"{body}\n{text}" if body else text)

    def resolve_annotation(self, index: int) -> str:
        """Drop the `index`-th annotation from `## notes` and return it.

        Resolving a note *is* deleting it: there is no reply and no done-flag,
        because a note that is still there still blocks sync. Non-annotation
        lines in `## notes` are left where they are, so a resolve never
        touches the prose around it.
        """
        lines = (self.section("notes") or "").splitlines()
        marked = [i for i, line in enumerate(lines) if annotation_audience(line)]
        if not 0 <= index < len(marked):
            raise CardError(f"no annotation {index} on card {self.uid}")
        removed = lines.pop(marked[index])
        self.set_section("notes", "\n".join(lines).strip())
        return removed

    # -- hashing (DESIGN.md §3.5, §8) -------------------------------------
    def content_hash(self) -> str:
        """Hash of everything that is card content.

        Excludes `status`, `content_hash` itself and `## notes`, so approving a
        card or scribbling an annotation on it is not an edit -- but changing
        anything a reviewer looked at is.
        """
        # Hash the content, not the file. Rendering it would make the digest
        # depend on FRONTMATTER_ORDER, so adding an optional field to that
        # tuple silently invalidated every approval in the deck -- the card
        # was untouched and `check` reported it as edited. Sorted keys and an
        # explicit separator make the digest independent of how the file
        # happens to be laid out.
        parts = [
            f"{key}={self.frontmatter[key]!r}"
            for key in sorted(self.frontmatter)
            if key not in UNHASHED_FRONTMATTER
        ]
        parts += [
            f"##{s.name}\n{s.canonical().body}"
            for s in sorted(self.sections, key=lambda s: s.name)
            if s.name not in UNHASHED_SECTIONS
        ]
        digest = hashlib.sha256(HASH_SEPARATOR.join(parts).encode('utf-8')).hexdigest()
        return digest[:16]

    def hash_matches(self) -> bool:
        return bool(self.stored_hash) and self.stored_hash == self.content_hash()

    @property
    def effective_status(self) -> str:
        """`status`, except that an edited approval is really a draft again.

        DESIGN.md §8 promises that resolving an annotation "drops the card back
        to `draft` and re-enters review automatically". Nothing rewrites the
        file to make that true -- and it should not, silently -- so the rule
        lives here instead: a card whose content no longer matches the hash it
        was approved under counts as a draft everywhere it matters, which is
        what puts it back in the review queue.
        """
        if self.status == "approved" and not self.hash_matches():
            return "draft"
        return self.status

    def approve(self) -> None:
        self.frontmatter["status"] = "approved"
        self.frontmatter["content_hash"] = self.content_hash()

    def reject(self) -> None:
        self.frontmatter["status"] = "rejected"
        self.frontmatter.pop("content_hash", None)

    def unapprove(self) -> None:
        self.frontmatter["status"] = "draft"
        self.frontmatter.pop("content_hash", None)

    # -- serialisation ----------------------------------------------------
    def canonical(self) -> Card:
        return replace(
            self,
            frontmatter=_sorted_frontmatter(self.frontmatter),
            sections=[s.canonical() for s in _sorted_sections(self.sections)],
            preamble=self.preamble.strip("\n"),
        )

    def render(self) -> str:
        card = self.canonical()
        out = ["---\n"]
        for key, value in card.frontmatter.items():
            out.append(f"{key}: {_dump_scalar(value)}\n")
        out.append("---\n")
        if card.preamble:
            out.append("\n" + card.preamble + "\n")
        for sec in card.sections:
            out.append(f"\n## {sec.name}\n")
            if sec.body:
                out.append(sec.body + "\n")
        return "".join(out)

    def save(self, path: Path | None = None, *, expect_mtime_ns: int | None = None) -> Path:
        """Write canonically. With `expect_mtime_ns`, refuse a stale write."""
        target = path or self.path
        if target is None:
            raise CardError("card has no path to save to")
        if expect_mtime_ns is not None and target.exists():
            actual = target.stat().st_mtime_ns
            if actual != expect_mtime_ns:
                raise StaleFileError(
                    f"{target.name} changed on disk since it was loaded; reload and retry"
                )
        write_atomic(target, self.render())
        self.path = target
        self.mtime_ns = target.stat().st_mtime_ns
        return target


# -- parsing --------------------------------------------------------------


def parse(text: str, path: Path | None = None) -> Card:
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise CardError("missing YAML frontmatter (a card starts with a `---` block)")
    try:
        loaded = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CardError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CardError("frontmatter must be a mapping")

    body = text[match.end() :]
    preamble_lines: list[str] = []
    sections: list[Section] = []
    current: Section | None = None
    for line in body.split("\n"):
        header = _SECTION_RE.match(line)
        if header:
            current = Section(header.group(1).lower(), "")
            sections.append(current)
            continue
        if current is None:
            preamble_lines.append(line)
        else:
            current.body += line + "\n"

    return Card(
        frontmatter={str(k): v for k, v in loaded.items()},
        sections=[s.canonical() for s in sections],
        preamble="\n".join(preamble_lines).strip("\n"),
        path=path,
    )


def load(path: Path) -> Card:
    stat = path.stat()
    try:
        card = parse(path.read_text(encoding="utf-8"), path=path)
    except CardError as exc:
        raise CardError(f"{path}: {exc}") from exc
    card.mtime_ns = stat.st_mtime_ns
    return card


def load_all(cards_dir: Path) -> list[Card]:
    """Every card in the deck directory, sorted by uid then path."""
    if not cards_dir.exists():
        return []
    cards = [load(p) for p in sorted(cards_dir.rglob("*.md"))]
    return sorted(cards, key=lambda c: (c.uid, str(c.path)))


def find(cards_dir: Path, uid: str) -> Card | None:
    for card in load_all(cards_dir):
        if card.uid == uid:
            return card
    return None


# Windows refuses the rename while any other process holds the destination
# open, so this waits rather than failing. The budget is generous on purpose:
# waiting costs nothing, and the alternative is throwing away a write that has
# already been computed. One second was not enough under a loaded machine --
# twelve concurrent writers plus other work made the suite flake here.
REPLACE_ATTEMPTS = 100
REPLACE_POLL = 0.05


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` so a reader sees either the old file or the new.

    On Windows `os.replace` fails with PermissionError while *any* other
    process holds the destination open -- and the app re-reads the ledger on
    every request, so a reader can break a writer even when writers are
    serialised among themselves. Retry the rename rather than raise: the
    reader's handle is short-lived, and failing here would throw away work
    that has already been done.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_POLL)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# -- new cards ------------------------------------------------------------


def looks_numeric(uid: str) -> bool:
    """Would Anki read this uid as a number rather than as text?

    `uid` is the note type's first field, and Anki stores the sort field in a
    column that takes either. A six-hex uid shaped `4e6166` is a valid float
    literal -- 4 x 10^6166 -- which overflows a double, lands as NULL, and
    breaks `exportPackage` with a NOT NULL constraint on `notes.sfld`. Found
    by bisecting a 108-card deck down to one card.

    8.4% of the 6-hex space parses as a float; a handful of those overflow.
    Only the overflowing ones break an export, but a uid that sorts as a number
    is wrong in the browser too, so the test is the broader one: does it parse.
    The cheap half of the fix is never to mint another.
    """
    try:
        float(uid)
    except ValueError:
        return False
    return True


def mint_uid(seed: str, taken: set[str] | None = None) -> str:
    """Deterministic 6-hex uid from a seed, bumped on collision.

    Skips any uid Anki would read as a number; see `looks_numeric`.
    """
    taken = taken or set()
    for salt in range(1000):
        material = seed if salt == 0 else f"{seed}#{salt}"
        uid = hashlib.sha256(material.encode("utf-8")).hexdigest()[:6]
        if uid not in taken and not looks_numeric(uid):
            return uid
    raise CardError(f"could not mint a free uid for {seed!r}")


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit].strip("-") or "card"


def stub(
    *,
    uid: str,
    front: str,
    back: str,
    source: str,
    unit: str,
    card_type: str = "identity",
    tags: list[str] | None = None,
) -> Card:
    """A minimal valid card: `check` passes on it, it is just not good yet."""
    return Card(
        frontmatter={
            "uid": uid,
            "type": card_type,
            "status": "draft",
            "source": source,
            "unit": unit,
            "tags": tags or [],
            "verify": False,
        },
        sections=[Section("front", front.strip()), Section("back", back.strip())],
    )


# -- canonicalisation helpers ---------------------------------------------


def _sorted_frontmatter(fm: dict[str, Any]) -> dict[str, Any]:
    known = [k for k in FRONTMATTER_ORDER if k in fm]
    rest = [k for k in fm if k not in FRONTMATTER_ORDER]
    return {k: fm[k] for k in [*known, *rest]}


def _sorted_sections(sections: list[Section]) -> list[Section]:
    def key(item: tuple[int, Section]) -> tuple[int, int]:
        index, sec = item
        try:
            return (SECTION_ORDER.index(sec.name), index)
        except ValueError:
            return (len(SECTION_ORDER), index)

    return [sec for _, sec in sorted(enumerate(sections), key=key)]


_PLAIN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _.\-/()+^=]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_dump_scalar(v) for v in value) + "]"
    if isinstance(value, str):
        return _dump_str(value)
    # Anything exotic: let PyYAML decide, on one line.
    return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).strip()


def _dump_str(value: str) -> str:
    if (
        value
        and value.lower() not in _RESERVED
        and _PLAIN_RE.match(value)
        and not _looks_numeric(value)
        and value == value.strip()
    ):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
