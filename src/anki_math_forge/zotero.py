"""Zotero's local HTTP API, read-only.

The same shape as `anki.py`, and here for the same reason: a documented local
API on 127.0.0.1 with no credentials, which the tool speaks directly rather
than through anything else. It needs Zotero running with its local API enabled
(Settings > Advanced), exactly as `sync` needs Anki running with AnkiConnect.

Not the Zotero MCP server. That route cannot return annotation geometry, and
geometry is the whole point: without rects a highlight has no crop and an area
annotation has no content at all.

**Identity comes from the key; order comes from the sort index.** Every
annotation carries a permanent `key` that Zotero assigns and never reuses, and
a separate `annotationSortIndex` giving its place in reading order. Adding a
highlight in the middle of a document therefore renumbers nothing: ids are
stable under insertion, deletion and reordering, and only relative order moves.
Deriving a unit id from a position instead would break triage state and every
card pointing at it the first time a note was added mid-page.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://127.0.0.1:23119"
TIMEOUT = 30.0
PAGE_SIZE = 100

# Zotero's fixed highlight palette, so a config can be written in colours a
# human recognises rather than in hex nobody remembers.
COLOURS = {
    "#ffd400": "yellow",
    "#ff6666": "red",
    "#5fb236": "green",
    "#2ea8e5": "blue",
    "#a28ae5": "purple",
    "#e56eee": "magenta",
    "#f19837": "orange",
    "#aaaaaa": "grey",
}

# The way back, for anything that has to *draw* a mark rather than name it.
# The ledger stores the name, because a name is what a config maps and what a
# person reads; a renderer needs the paint.
HEX_BY_NAME = {name: code for code, name in COLOURS.items()}


def colour_rgb(colour: str) -> tuple[float, float, float] | None:
    """`"purple"` or `"#a28ae5"` to the 0..1 triple PDF drawing wants.

    Both spellings, because a mark records the name when it recognises one and
    falls back to the raw hex when it does not -- and a colour this project has
    never seen should still come out the colour it was.
    """
    code = HEX_BY_NAME.get(colour.strip().lower(), colour.strip().lower())
    if not code.startswith("#") or len(code) != 7:
        return None
    try:
        parts = (int(code[1:3], 16), int(code[3:5], 16), int(code[5:7], 16))
    except ValueError:
        return None
    return (parts[0] / 255, parts[1] / 255, parts[2] / 255)


class ZoteroError(Exception):
    """Zotero is not reachable, or said no."""


@dataclass
class Annotation:
    """One mark in a PDF, as Zotero records it.

    `rects` are Zotero's own: PDF user space, **bottom-left origin**, one box
    per line the mark spans. `bbox()` converts to the top-left origin the rest
    of this project uses, which needs the page height and so belongs to
    whoever has the document open.
    """

    key: str
    document: str  # the attachment it lives on, never the bibliographic item
    kind: str  # highlight | underline | note | image | ink
    colour: str = ""
    text: str = ""
    comment: str = ""
    page_index: int | None = None  # 0-based, as Zotero counts
    page_label: str = ""  # what is printed on the page, which may differ
    rects: list[list[float]] = field(default_factory=list)
    sort_index: str = ""
    tags: list[str] = field(default_factory=list)
    modified: str = ""

    @property
    def page(self) -> int | None:
        """1-based, the way `locator.page` counts and `render` loads."""
        return None if self.page_index is None else self.page_index + 1

    @property
    def colour_name(self) -> str:
        return COLOURS.get(self.colour.lower(), self.colour)

    @property
    def content(self) -> str:
        """What this annotation actually says.

        A highlight carries the text it covers. A note carries nothing from the
        page at all: its rect is where the pin sits, and the comment is the
        whole of it.
        """
        return self.comment if self.kind == "note" else self.text

    def bbox(self, page_height: float) -> list[float] | None:
        """The union of `rects`, flipped to top-left origin.

        The union rather than the first box: a highlight running over a line
        break is two rects, and the mark is both of them.
        """
        boxes = self.boxes(page_height)
        if not boxes:
            return None
        return [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]

    def boxes(self, page_height: float) -> list[list[float]]:
        """Every rect, flipped to top-left origin, kept apart.

        `bbox` unions these because a crop wants one rectangle. Drawing wants
        them separate: the union of a highlight that runs over a line break
        covers both lines end to end, including the part of each the reader
        left unmarked, so painting it would claim more than they marked.
        """
        return [[r[0], page_height - r[3], r[2], page_height - r[1]] for r in self.rects]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Annotation:
        position = data.get("annotationPosition") or "{}"
        if isinstance(position, str):
            try:
                position = json.loads(position)
            except json.JSONDecodeError:
                position = {}
        return cls(
            key=data["key"],
            document=data.get("parentItem", ""),
            kind=data.get("annotationType", ""),
            colour=data.get("annotationColor", ""),
            text=data.get("annotationText", "") or "",
            comment=data.get("annotationComment", "") or "",
            page_index=position.get("pageIndex"),
            page_label=str(data.get("annotationPageLabel", "") or ""),
            rects=[[float(v) for v in r] for r in position.get("rects", [])],
            sort_index=data.get("annotationSortIndex", ""),
            tags=[t["tag"] for t in data.get("tags", []) if "tag" in t],
            modified=data.get("dateModified", ""),
        )


@dataclass
class Attachment:
    key: str
    parent: str
    title: str = ""
    filename: str = ""
    content_type: str = ""

    @property
    def is_pdf(self) -> bool:
        return self.content_type == "application/pdf"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Attachment:
        return cls(
            key=data["key"],
            parent=data.get("parentItem", ""),
            title=data.get("title", ""),
            filename=data.get("filename", ""),
            content_type=data.get("contentType", ""),
        )


@dataclass
class Item:
    """A bibliographic item: the thing a source is made from."""

    key: str
    item_type: str = ""
    title: str = ""
    creators: list[str] = field(default_factory=list)
    date: str = ""
    citation_key: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        """`Wegel et al. 2025`, or the title when there are no authors."""
        year = self.date[:4] if self.date[:4].isdigit() else ""
        if not self.creators:
            return f"{self.title} {year}".strip()
        if len(self.creators) == 1:
            who = self.creators[0]
        elif len(self.creators) == 2:
            who = " and ".join(self.creators)
        else:
            who = f"{self.creators[0]} et al."
        return f"{who} {year}".strip()

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Item:
        creators = [
            c.get("lastName") or c.get("name", "")
            for c in data.get("creators", [])
            if c.get("creatorType") in ("author", "editor")
        ]
        # Better BibTeX's key. The local API hands it over as a field of its
        # own; `extra` is the fallback, for a library where it was pinned there
        # by hand instead.
        citation_key = str(data.get("citationKey", "") or "")
        if not citation_key:
            for line in (data.get("extra") or "").splitlines():
                if line.lower().startswith("citation key:"):
                    citation_key = line.split(":", 1)[1].strip()
        return cls(
            key=data["key"],
            item_type=data.get("itemType", ""),
            title=data.get("title", ""),
            creators=[c for c in creators if c],
            date=str(data.get("date", "") or ""),
            citation_key=citation_key,
            tags=[t["tag"] for t in data.get("tags", []) if "tag" in t],
        )


class Zotero:
    """Read-only client for the local API.

    Every method here is a GET. Nothing in this project writes to somebody's
    reference library, and the local API could not do it anyway: it is
    read-only by design, which is the reason to prefer it over the web API
    even where both would work.
    """

    def __init__(self, url: str = "", timeout: float = TIMEOUT) -> None:
        self.url = (url or os.environ.get("ZOTERO_API_URL") or DEFAULT_URL).rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        """The single seam: everything goes through here, tests replace it."""
        try:
            with urllib.request.urlopen(self.url + path, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read()[:200].decode(errors="replace").strip()
            if exc.code == 403:
                raise ZoteroError(
                    f"Zotero refused the request ({body}). Its local API is off: "
                    "turn it on under Settings > Advanced. Zotero itself is running, "
                    "or this would not have answered at all."
                ) from None
            raise ZoteroError(f"Zotero said {exc.code}: {body}") from None
        except urllib.error.URLError as exc:
            raise ZoteroError(
                f"cannot reach Zotero at {self.url}: {exc.reason}. It has to be "
                "running, with its local API enabled under Settings > Advanced."
            ) from None

    def _paged(self, path: str) -> list[dict[str, Any]]:
        """Walk a collection endpoint to the end.

        The API caps a page, and the annotation scan below is the one call that
        routinely exceeds it.
        """
        joiner = "&" if "?" in path else "?"
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            page = self._get(f"{path}{joiner}limit={PAGE_SIZE}&start={start}")
            if not page:
                return rows
            rows.extend(row["data"] for row in page if "data" in row)
            start += PAGE_SIZE

    # -- what is there ------------------------------------------------------

    def reachable(self) -> bool:
        try:
            self._get("/api/users/0/items/top?limit=1")
        except ZoteroError:
            return False
        return True

    def item(self, key: str) -> Item:
        return Item.from_json(self._get(f"/api/users/0/items/{key}")["data"])

    def tagged(self, tag: str) -> list[Item]:
        """Every top-level item carrying `tag`: the cross-library pull."""
        return [Item.from_json(row) for row in self._paged(f"/api/users/0/items?tag={tag}")]

    def search(self, query: str) -> list[Item]:
        """Items matching a title or creator.

        Attachments and notes are excluded: a search is looking for the thing
        on the shelf, not for the files hanging off it.
        """
        encoded = urllib.parse.quote(query)
        rows = self._paged(f"/api/users/0/items?q={encoded}&qmode=titleCreatorYear")
        return [
            Item.from_json(row)
            for row in rows
            if row.get("itemType") not in ("attachment", "note", "annotation")
        ]

    def attachments(self, key: str) -> list[Attachment]:
        """The item's PDFs, in the order Zotero returns them.

        An item is routinely several documents: a paper and its appendix, or a
        book as one PDF per chapter.
        """
        rows = self._paged(f"/api/users/0/items/{key}/children")
        return [
            Attachment.from_json(row)
            for row in rows
            if row.get("itemType") == "attachment" and row.get("contentType") == "application/pdf"
        ]

    def annotations(self, documents: set[str] | None = None) -> list[Annotation]:
        """Annotations, optionally only those on the given attachments.

        Scanned and filtered here rather than asked for by parent: the API
        accepts a `parentItem` query and then ignores it, returning the whole
        library, so filtering server-side would silently mean not filtering.
        """
        rows = self._paged("/api/users/0/items?itemType=annotation")
        found = [Annotation.from_json(row) for row in rows]
        if documents is None:
            return found
        return [a for a in found if a.document in documents]

    def fulltext(self, key: str) -> str:
        """An attachment's indexed text layer, or empty when Zotero has none."""
        try:
            return str(self._get(f"/api/users/0/items/{key}/fulltext").get("content", ""))
        except ZoteroError:
            return ""

    def storage_path(self, attachment: Attachment, data_dir: Path) -> Path:
        """Where the file actually is, so a crop can be rendered from it."""
        return data_dir / "storage" / attachment.key / attachment.filename
