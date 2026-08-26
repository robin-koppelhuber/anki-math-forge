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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

# Frontmatter keys in the order they are written back out. Unknown keys keep
# their relative order and land after these.
FRONTMATTER_ORDER = (
    "uid",
    "type",
    "status",
    "content_hash",
    "source",
    "unit",
    "tags",
    "verify",
)

# Canonical section order. Unknown sections keep file order and land after.
SECTION_ORDER = ("front", "back", "conditions", "proof", "prose", "verify", "notes")

# Sections allowed per `type` (DESIGN.md §7: "section whitelist for the
# declared type"). MVP ships `identity` only (§5).
SECTIONS_BY_TYPE: dict[str, frozenset[str]] = {
    "identity": frozenset(SECTION_ORDER),
}

REQUIRED_SECTIONS = ("front", "back")

# `## notes` never syncs and never enters the content hash (DESIGN.md §8):
# annotating a card is not an edit of the card, but the fix that resolves the
# annotation is.
UNHASHED_SECTIONS = frozenset({"notes"})
UNHASHED_FRONTMATTER = frozenset({"status", "content_hash"})

STATUSES = ("draft", "approved", "rejected")

ANNOTATION_PREFIX = "@claude"
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
    def unit(self) -> str:
        return str(self.frontmatter.get("unit", "") or "")

    @property
    def source(self) -> str:
        return str(self.frontmatter.get("source", "") or "")

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
        """Open `@claude ...` lines from `## notes`, verbatim."""
        body = self.section("notes") or ""
        return [
            line.strip()
            for line in body.split("\n")
            if line.strip().lower().startswith(ANNOTATION_PREFIX)
        ]

    def add_annotation(self, text: str) -> None:
        """Append an annotation, byte-identical to one typed by hand."""
        text = " ".join(text.split()).strip()
        if not text:
            return
        if not text.lower().startswith(ANNOTATION_PREFIX):
            text = f"{ANNOTATION_PREFIX} {text}"
        body = self.section("notes")
        self.set_section("notes", f"{body}\n{text}" if body else text)

    # -- hashing (DESIGN.md §3.5, §8) -------------------------------------
    def content_hash(self) -> str:
        """Hash of everything that is card content.

        Excludes `status`, `content_hash` itself and `## notes`, so approving a
        card or scribbling an annotation on it is not an edit -- but changing
        anything a reviewer looked at is.
        """
        payload = Card(
            frontmatter={
                k: v for k, v in self.frontmatter.items() if k not in UNHASHED_FRONTMATTER
            },
            sections=[s.canonical() for s in self.sections if s.name not in UNHASHED_SECTIONS],
        )
        digest = hashlib.sha256(payload.render().encode("utf-8")).hexdigest()
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


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# -- new cards ------------------------------------------------------------


def mint_uid(seed: str, taken: set[str] | None = None) -> str:
    """Deterministic 6-hex uid from a seed, bumped on collision."""
    taken = taken or set()
    for salt in range(1000):
        material = seed if salt == 0 else f"{seed}#{salt}"
        uid = hashlib.sha256(material.encode("utf-8")).hexdigest()[:6]
        if uid not in taken:
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
