"""A document's own table of contents, and the page windows it defines.

`context_pages` may be a number of pages either side, or a word: `section`,
`chapter` or `part`. A word used to be worked out from the units' section
labels, which is right for a book whose labels are numbered (`2.4` is in
chapter 2) and wrong for one whose outline names sections without numbers:
in Krause and Hübotter's book every section became its own "chapter", and a
unit in the last marked section was handed the remaining 378 pages.

The PDF knows better. Its outline has levels, and this module reads them.

**Levels are named by shape, not by depth.** That book puts chapter 1 at the
top level and every later chapter under a part, so "level 2 is a chapter" is
wrong for one and right for the rest. A part is an entry whose children are
mostly containers themselves, or whose title says so (`I Probabilistic
Machine Learning`, `Part II`); a chapter is any other entry with no part
above it saying otherwise; everything under a chapter is a section. A title
that starts with a bare number (`3 Filtering`) is a chapter whatever its
shape.

**Pages are PDF pages**, counted from 1, which is what the ledger and the
cached text layer use. What the book prints on them can differ (that book
has ten front-matter pages, so PDF page 50 is printed page 40), so a span
also carries the printed labels, which are what a person checks against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import CHAPTER, PART, SECTION, Config

#: A window this many pages or longer is said to be large. A chapter of a
#: textbook is twenty to forty; past that a card writer is handed a book.
LARGE = 40

_PART = re.compile(r"^(?:part\s+\S+|[IVXLC]+)(?:[\s.:]|$)", re.I)
_ROMAN = re.compile(r"^[IVXLC]+(?:[\s.:]|$)")
_CHAPTER = re.compile(r"^(?:chapter\s+\S+|\d+\.?)(?:\s|$)", re.I)


@dataclass(frozen=True)
class Entry:
    """One line of the outline: where it starts, where it ends, what it is."""

    level: int
    title: str
    page: int
    kind: str = SECTION
    end: int = 0
    #: The page its first child starts on, or 0. The pages before that are
    #: the entry's own: a chapter's opening page before its first section.
    first_child: int = 0


@dataclass(frozen=True)
class Span:
    """A window the outline defines: which entry, and its pages."""

    word: str
    title: str
    first: int
    last: int
    printed: str = ""

    @property
    def count(self) -> int:
        return self.last - self.first + 1

    @property
    def large(self) -> bool:
        return self.count >= LARGE

    def as_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "title": self.title,
            "first": self.first,
            "last": self.last,
            "count": self.count,
            "printed": self.printed,
            "large": self.large,
        }


@dataclass(frozen=True)
class Outline:
    entries: tuple[Entry, ...]
    pages: int
    #: The printed label of each page, `""` where the PDF declares none.
    labels: tuple[str, ...] = field(default_factory=tuple)

    def label(self, page: int) -> str:
        if 1 <= page <= len(self.labels) and self.labels[page - 1]:
            return self.labels[page - 1]
        return ""

    def printed(self, first: int, last: int) -> str:
        """`pp. 39-50` as printed, or `""` when the PDF prints no labels or
        they are the PDF's own numbers."""
        a, b = self.label(first), self.label(last)
        if not a or not b or (a == str(first) and b == str(last)):
            return ""
        return f"p. {a}" if first == last else f"pp. {a}-{b}"

    def chain(self, page: int, hint: str = "") -> list[Entry]:
        """The entries a page is in, outermost first.

        Two sections can share a page, one ending and the next starting on
        it. The unit's own section label settles which, where it names
        one of them; otherwise the later one, the last to have started.
        """
        wanted = _norm(hint)
        by_level: dict[int, list[Entry]] = {}
        for entry in self.entries:
            if entry.page <= page <= entry.end:
                by_level.setdefault(entry.level, []).append(entry)
        kept: list[Entry] = []
        for level in sorted(by_level):
            # Only what sits inside the entry already chosen above it.
            options = [
                e for e in by_level[level] if not kept or kept[-1].page <= e.page <= kept[-1].end
            ]
            if not options:
                continue
            named = [e for e in options if wanted and _norm(e.title) == wanted]
            if named:
                kept.append(named[0])
                continue
            # The last to have started, and of two starting on one page, the
            # later in the outline.
            latest = max(e.page for e in options)
            kept.append([e for e in options if e.page == latest][-1])
        return kept

    def span(self, page: int, word: str, hint: str = "") -> Span | None:
        """The `section`, `chapter` or `part` a page is in."""
        chain = self.chain(page, hint)
        if not chain:
            first = min((e.page for e in self.entries), default=0)
            if first > 1 and page < first:
                return self._span(word, "the pages before the outline starts", 1, first - 1)
            return None
        part = next((e for e in chain if e.kind == PART), None)
        chapter = next((e for e in chain if e.kind == CHAPTER), None)
        section = next((e for e in chain if e.kind == SECTION), None)
        if word == PART:
            whole = part or chapter or chain[0]
            return self._span(word, whole.title, whole.page, whole.end)
        if word == CHAPTER:
            if chapter is not None:
                return self._span(word, chapter.title, chapter.page, chapter.end)
            # On a part's own opening pages, before its first chapter: those
            # pages, not the whole part.
            return self._own(word, chain[-1], page)
        if section is not None:
            return self._span(word, section.title, section.page, section.end)
        # In a chapter's opening pages, before its first section.
        return self._own(word, chapter or chain[-1], page)

    def _own(self, word: str, entry: Entry, page: int) -> Span:
        last = entry.first_child - 1 if entry.first_child > entry.page else entry.end
        return self._span(word, entry.title, entry.page, max(last, page))

    def _span(self, word: str, title: str, first: int, last: int) -> Span:
        return Span(word, title, first, last, self.printed(first, last))

    def chapters(self) -> list[tuple[Entry | None, Entry]]:
        """Every chapter, with the part it sits in, in reading order."""
        out: list[tuple[Entry | None, Entry]] = []
        part: Entry | None = None
        for entry in self.entries:
            if entry.kind == PART:
                part = entry
            elif entry.kind == CHAPTER:
                inside = part if part is not None and part.page <= entry.page <= part.end else None
                out.append((inside, entry))
        return out


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def build(toc: list[tuple[int, str, int]], pages: int, labels: tuple[str, ...] = ()) -> Outline:
    """An outline from `(level, title, page)` rows, as PDFs store them."""
    rows = [(int(level), " ".join(str(title).split()), int(page)) for level, title, page in toc]
    rows = [row for row in rows if row[2] >= 1 and row[1]]
    children: dict[int, list[int]] = {}
    parent: dict[int, int] = {}
    stack: list[int] = []
    for index, (level, _, _) in enumerate(rows):
        while stack and rows[stack[-1]][0] >= level:
            stack.pop()
        if stack:
            parent[index] = stack[-1]
            children.setdefault(stack[-1], []).append(index)
        stack.append(index)

    kinds: dict[int, str] = {}
    for index, (_, title, _) in enumerate(rows):
        above = kinds.get(parent[index], "") if index in parent else ""
        kids = children.get(index, [])
        if above in (CHAPTER, SECTION):
            kind = SECTION
        elif _PART.match(title) and (_ROMAN.match(title) or title.lower().startswith("part")):
            kind = PART
        elif _CHAPTER.match(title) or above == PART:
            kind = CHAPTER
        elif kids and 2 * sum(1 for k in kids if children.get(k)) >= len(kids):
            kind = PART
        else:
            kind = CHAPTER
        kinds[index] = kind

    entries: list[Entry] = []
    for index, (level, title, page) in enumerate(rows):
        later = next((j for j in range(index + 1, len(rows)) if rows[j][0] <= level), None)
        if later is None:
            end = pages
        elif kinds[later] in (PART, CHAPTER):
            # A chapter starts on a fresh page, so the one before it is the
            # last of this entry.
            end = rows[later][2] - 1
        else:
            # A section can start halfway down the page this one ends on.
            end = rows[later][2]
        kids = children.get(index, [])
        entries.append(
            Entry(
                level=level,
                title=title,
                page=page,
                kind=kinds[index],
                end=max(end, page),
                first_child=rows[kids[0]][2] if kids else 0,
            )
        )
    return Outline(tuple(entries), pages, tuple(labels))


@lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int) -> Outline | None:
    from .extract.render import PdfUnavailable, _fitz

    try:
        fitz = _fitz()
    except PdfUnavailable:
        return None
    try:
        doc = fitz.open(path)
    except Exception:
        # An unreadable PDF has no outline, which is an answer, not a crash.
        return None
    try:
        toc = [(row[0], row[1], row[2]) for row in doc.get_toc(simple=True)]
        if not toc:
            return None
        labels = tuple(str(doc[i].get_label() or "") for i in range(doc.page_count))
        return build(toc, doc.page_count, labels)
    finally:
        doc.close()


def read(path: Path) -> Outline | None:
    """The outline of a PDF, or `None` where it has none or cannot be read.
    Kept per file and modification time, so a page of fifty units asks the
    PDF once."""
    if path.suffix.lower() != ".pdf" or not path.exists():
        return None
    return _read(str(path), path.stat().st_mtime_ns)


def of_document(config: Config, project: str, document: str = "") -> Outline | None:
    path = config.document_for(project, document)
    return read(path) if path is not None else None
