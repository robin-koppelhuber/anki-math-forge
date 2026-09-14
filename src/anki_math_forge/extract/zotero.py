"""Zotero annotations into units.

**What each mark means is yours to declare, and the tool has no opinion.**
`[zotero] units_from` names the colours and kinds worth a card of their own;
`[zotero.meanings]` says what any of them mean, and a source can read its own
scheme differently. Nothing here knows what a colour stands for, and nothing
should: a scheme is a fact about how one person read one document. What is
measurable is only that a scheme exists, and that it varies. Across the first
two real documents the same colour ran a median of twenty words in one and two
in another, which is an argument for declaring it rather than guessing it.

**A unit is named after the mark it came from.** Zotero's annotation key is
permanent: assigned once, never reused, never derived from a position. So
marking up more of a document renumbers nothing.

**Context is pages, not a curated set of marks.** An earlier version worked out
which marks were nearest in reading order and attached those. That was the tool
deciding what is relevant, which belongs to whoever reads it. A unit carries
the marks on the pages around it; a mark appearing beside two units is not a
problem, because context is a view and not content.

**Units arrive `new`, like every other unit.** They used to arrive `queued`, on
the argument that marking the document up *was* the triage step. It is not the
same step: marking says "this mattered while I was reading", and triage says
"this is worth a card, on its own, out of context" -- which is a judgement you
can only make once you see the mark next to its neighbours, which is what this
view is for. Skipping it also skipped the one gate that stops an import from
silently filling the card queue.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import zotero as api
from ..config import ZoteroConfig
from ..ledger import Locator, Mark, Unit

# How many pages either side of a unit come with it. One catches an idea that
# runs over a page break, which is the case a same-page window cuts through.
# Passes that write cards ask for more; triage wants to stay readable.
NEIGHBOURHOOD = 1


@dataclass
class ImportReport:
    item: str = ""
    documents: int = 0
    annotations: int = 0
    units: list[Unit] = field(default_factory=list)
    unmapped: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    text_chars: int = 0
    # Every PDF on the item, as `(key, title, taken)`. Printed on every run,
    # because you cannot choose between two attachments you have never been
    # shown -- and an item routinely carries a paper and a preprint of it.
    attachments: list[tuple[str, str, bool]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.skipped

    @property
    def excluded(self) -> set[str]:
        """Attachment keys `documents` left out. Units already imported from
        one of these are stale: they describe a document this source no longer
        reads."""
        return {key for key, _, taken in self.attachments if not taken}


def wanted(attachment: api.Attachment, documents: tuple[str, ...]) -> bool:
    """Is this attachment one the source asked for?

    By title or by key, because both are things you can see: the title is what
    Zotero shows you and the key is what the ledger records. Empty means all of
    them, which is right until an item carries the paper and its appendix as
    two PDFs and every mark gets imported twice.
    """
    return not documents or attachment.title in documents or attachment.key in documents


def outline(pdf: Path) -> list[tuple[int, str]]:
    """`(first page, title)` for each section the document declares, in order.

    A paper's own table of contents, which most PDFs built from LaTeX carry as
    bookmarks. Without it every mark in a paper landed in one section named
    after the *attachment* -- "PDF" -- so the section rail offered a single row
    that filtered nothing, and a card's `Source` field cited the filename where
    it should have cited a section.

    Titles as the document wrote them, and no numbering invented on top: this
    one names its sections "Introduction" and "Multi-objective learning", and
    turning those into "1" and "2.3" would be asserting a numbering the paper
    does not print. Order is the document's, which is why this returns a list.

    Empty for a PDF with no bookmarks -- a scan, or a chapter exported on its
    own -- and the caller falls back to the attachment title, which for a book
    split into one file per chapter is exactly right.
    """
    from .render import _fitz

    doc = _fitz().open(str(pdf))
    try:
        found = [
            (int(page), " ".join(str(title).split()))
            for _level, title, page in doc.get_toc()
            if int(page) > 0 and str(title).strip()
        ]
    except Exception:
        # A malformed outline is not a reason to refuse the import; the
        # attachment title is a workable fallback and the marks are the point.
        return []
    finally:
        doc.close()
    return sorted(found, key=lambda entry: entry[0])


def section_at(toc: list[tuple[int, str]], page: int) -> str:
    """The last section to have started at or before this page."""
    name = ""
    for starts, title in toc:
        if starts > page:
            break
        name = title
    return name


def page_heights(pdf: Path) -> dict[int, float]:
    """Every page's height, which is what turns Zotero's coordinates into ours.

    Zotero measures from the bottom of the page and this project measures from
    the top, so the flip needs a height and the height has to come from the
    document. Guessing Letter or A4 would be right most of the time and
    silently wrong on the rest, which is the worst available failure.
    """
    from .render import _fitz

    doc = _fitz().open(str(pdf))
    try:
        return {n + 1: float(doc.load_page(n).rect.height) for n in range(doc.page_count)}
    finally:
        doc.close()


def unit_id(source: str, key: str) -> str:
    """`<source>:<annotation key>`.

    Zotero's key, not a position and not a page: the one identifier that
    survives a mark being inserted, deleted or moved. The document is on the
    locator rather than in the name, because a unit that gets re-filed should
    not have to be renamed.
    """
    return f"{source}:{key}"


def to_mark(annotation: api.Annotation, height: float | None) -> Mark:
    return Mark(
        key=annotation.key,
        kind=annotation.kind,
        colour=annotation.colour_name,
        text=annotation.text,
        comment=annotation.comment,
        bbox=annotation.bbox(height) if height is not None else None,
        order=annotation.sort_index,
        page=annotation.page,
        # Kept alongside the union, because the two answer different
        # questions: the union is what to crop to, the rects are where the
        # reader's pen actually went.
        rects=annotation.boxes(height) if height is not None else None,
    )


def units_for(
    source: str,
    attachment: api.Attachment,
    annotations: list[api.Annotation],
    heights: dict[int, float],
    zotero: ZoteroConfig,
    *,
    section: str = "",
    toc: list[tuple[int, str]] | None = None,
    neighbourhood: int = NEIGHBOURHOOD,
) -> list[Unit]:
    """One unit per mark you declared worth a card, with its pages around it."""
    ordered = sorted(
        (a for a in annotations if a.page),
        key=lambda a: (a.sort_index, a.key),
    )
    marks = [to_mark(a, heights.get(a.page or 0)) for a in ordered]
    pages = [a.page or 0 for a in ordered]

    units = []
    for index, annotation in enumerate(ordered):
        if not zotero.makes_a_unit(annotation.kind, annotation.colour_name):
            continue
        mine, here = marks[index], pages[index]
        near = [
            mark
            for page, mark in zip(pages, marks, strict=True)
            if abs(page - here) <= neighbourhood and mark.key != mine.key
        ]
        units.append(
            Unit(
                id=unit_id(source, mine.key),
                locator=Locator(
                    # The document's own section, where it declares one. The
                    # attachment title is the fallback and not the answer: it
                    # is the name of a *file*, so every mark in a paper landed
                    # in one section called "PDF".
                    section=section_at(toc or [], here) or section or attachment.title,
                    kind=annotation.kind,
                    document=attachment.key,
                    page=here,
                    # The mark's own box. What is around it is shown by
                    # rendering with context, not by widening the unit to
                    # cover things the card is not about.
                    bbox=mine.bbox,
                ),
                # Its own mark first, then everything marked nearby, in reading
                # order.
                marks=[mine, *near],
            )
        )
    return units


def write_source_stub(path: Path, item: api.Item, *, tags: tuple[str, ...] = ()) -> bool:
    """Give a freshly imported source its `source.toml`, if it has none.

    Without one the units exist and the source does not: `config.source()` has
    never heard of it, so nothing can resolve its deck or its conventions. The
    import is the only moment that knows the title and the citation, so it is
    the right moment to write them down.

    **No `conventions.md`.** An empty placeholder saying "nothing recorded yet"
    is indistinguishable from a real one to everything that reads it, and
    `forge context` would stop telling a card writer that nobody has written
    down what is ambient here. An absent file is the honest state.

    Never overwrites. Everything in here is a starting point you will edit, and
    a re-import must not undo that.
    """
    if path.exists():
        return False
    # The item's own tags, and nothing this tool made up. The difference is the
    # whole rule: a label invented here would mean whatever the tool guessed it
    # means, while a tag on a Zotero item is one you put there and already
    # know the meaning of. They are also the labels you would narrow a shelf of
    # fifty papers by, which is what `tags` is for -- and `demo`, the one tag
    # this repo reads, is then set the way you would expect to set it.
    quoted = [f'"{t}"' for t in tags or tuple(item.tags)]
    lines = [
        f'title = "{item.title}"',
        f'citation = "{item.citation}"',
        f"tags = [{', '.join(quoted)}]",
        "",
        "# Which Zotero item this came from. The units carry attachment keys,",
        "# and this is what they hang off.",
        f'zotero = "{item.key}"',
        "",
        "# Which of its attachments to read, by title or by key. Empty means",
        "# all of them; name them when the item carries more than one PDF of",
        "# the same thing, since marks made in one are not marks in the other.",
        "documents = []",
        "",
        "# What your marks mean here, when this document is not read the way",
        "# the rest of the shelf is. Anything you set replaces the repo-wide",
        "# scheme for this source; leave it out to inherit.",
        "# [meanings]",
        '# green = "a claim or result worth a card"',
        "",
        "# Conventions -- the ambient setting a card writer has to know -- go",
        "# in `conventions.md` beside this file. There is none until you write",
        "# one, and `forge context` says so rather than pretending.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def build(
    client: api.Zotero,
    item: api.Item,
    *,
    source: str,
    zotero: ZoteroConfig,
    documents: tuple[str, ...] = (),
    text_for: Callable[[str, Path], int] | None = None,
) -> ImportReport:
    """Every unit-making mark on every PDF of one Zotero item.

    `documents` names the attachments to read, by title or key; empty is all of
    them. `text_for` caches a document's text layer and returns its size.
    Passed in rather than done here, so this stays a function of Zotero and a
    config and nothing else has to exist for a test to call it.
    """
    report = ImportReport(item=item.key)
    if not zotero.units_from:
        report.skipped.append(
            "`[zotero] units_from` is empty, so nothing you marked would become a "
            "unit. Name the colours or kinds that mean 'this is worth a card'."
        )
        return report

    every = client.attachments(item.key)
    if not every:
        report.skipped.append(f"{item.citation}: no PDF attachments")
        return report
    attachments = [a for a in every if wanted(a, documents)]
    report.attachments = [(a.key, a.title, wanted(a, documents)) for a in every]
    if not attachments:
        names = ", ".join(sorted(a.title for a in every)) or "(untitled)"
        report.skipped.append(
            f"{item.citation}: `documents` matches none of its attachments ({names})"
        )
        return report

    annotations = client.annotations({a.key for a in attachments})
    report.annotations = len(annotations)
    for annotation in annotations:
        # Undeclared, not meaningless. `DEFAULT_MEANINGS` gives every Zotero
        # kind a reading, so "has no meaning" stopped being a question anyone
        # can ask; what is worth reporting is the colour you have not decided
        # about, which is a decision outstanding rather than a gap.
        if zotero.reading(annotation.kind, annotation.colour_name)[1] != "declared":
            name = f"{annotation.kind}/{annotation.colour_name}"
            report.unmapped[name] = report.unmapped.get(name, 0) + 1

    by_document: dict[str, list[api.Annotation]] = {}
    for annotation in annotations:
        by_document.setdefault(annotation.document, []).append(annotation)

    for attachment in attachments:
        mine = by_document.get(attachment.key, [])
        if not mine:
            continue  # nothing marked here; not a unit, and not a complaint
        pdf = client.storage_path(attachment, zotero.data_dir)
        if not pdf.exists():
            report.skipped.append(
                f"{attachment.title}: {pdf} is missing, so its marks have no geometry"
            )
            continue
        report.documents += 1
        # The whole document's text, page by page, next to the ledger. A card
        # is easier to write and quicker to review when whoever wrote it could
        # see the paragraph that states the conditions, and that paragraph is
        # as often on the page before as on this one.
        if text_for is not None:
            report.text_chars += text_for(attachment.key, pdf)
        report.units.extend(
            units_for(
                source,
                attachment,
                mine,
                page_heights(pdf),
                zotero,
                section=attachment.title,
                toc=outline(pdf),
            )
        )
    return report
