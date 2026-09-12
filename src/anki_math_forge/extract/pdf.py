"""Segment a PDF into units by heuristic. **Frozen -- see ROADMAP.md §9.**

This works, and it is verified: 571/571 numbered equations on The Matrix
Cookbook, 98.8% of them in a crop holding exactly one equation. It is also a
specialisation rather than a solution, and an ablation says so plainly:

    as shipped                    571/571 equations
    without math-font detection   571/571
    without equation numbers      locators gone; 936 unverifiable regions
    without either                9

Two producer-specific signals carry the whole thing -- a right-margin `(61)`
and Computer Modern font names. A book that does not number its equations, a
Word-produced PDF, anything set in STIX or Times math, and this degrades to
plausible-looking noise with no way to tell.

**Do not extend it.** When a source defeats it, the replacement is not more
heuristics: let a model read the pages and report `(equation number, page,
bbox)`, then check that with the same contiguity oracle in `audit.py`. The
ledger does not care who fills it, as long as the ids stay stable -- and they
come from the document's own numbering, not from anything in here.

**What must survive without it**, and does not live here:

* `render.py` -- crops, which work from `locator.bbox` alone;
* `audit.py` -- the 1..N oracle, which scores *any* extractor;
* `ledger.py` -- stable ids and triage state, the actual valuable thing.

It is **kept**, not deleted: one selectable backend per source, behind the
same one-function seam. Frozen means frozen. When a shared type changes
under it, give it a shim rather than editing it.

The only contract this module owes the rest of the system is `segment()`
returning units whose `locator` carries a section, an equation number and a
bounding box. Anything that honours that can replace it wholesale.

---

Detection is a small scoring function over text lines rather than a model:

    +3  a right-margin equation number `(61)`
    +2  spans in a math font (Computer Modern math, or similar)
    +1  the line is indented and roughly centred
    +1  high symbol density

Three points is a display equation. The weights live here in one place because
they are the thing you would tune -- if you were going to, which you are not.

Requires the `pdf` extra (`uv sync --extra pdf`), which pulls PyMuPDF.
Note: PyMuPDF is AGPL-licensed -- fine for a private repo, worth knowing.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..ledger import Locator, Unit
from .render import PdfUnavailable, _fitz

__all__ = ["PdfUnavailable", "segment"]

SCORE_THRESHOLD = 3
CROP_PADDING = 6.0
HEADER_MARGIN = 110.0  # running heads live above this
FOOTER_MARGIN = 55.0  # folios below this
MARGIN_SLACK = 2.0  # how far right of the text margin still counts as flush
RIGHT_MARGIN_SLACK = 6.0
MIN_UNNUMBERED_WIDTH = 30.0  # narrower than this is a fragment, not an equation

_EQ_NUMBER_RE = re.compile(r"\(\s*(\d{1,4})\s*\)\s*$")
_EQ_ONLY_RE = re.compile(r"^\(\s*\d{1,4}\s*\)$")
_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(\S.*)$")
_MATH_FONT_RE = re.compile(r"(CMMI|CMSY|CMEX|MathItalic|Math|Symbol|Italic)", re.IGNORECASE)
_SYMBOLS = set("=+-*/^_<>|∂∑∫√≈≠≤≥x÷±∇⊗⊕αβγδεθλμσφψωΓΔΛΣΦΨΩ()[]{}")


@dataclass
class Line:
    text: str
    bbox: tuple[float, float, float, float]
    math_font: bool

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass
class Block:
    """A text block as the PDF's own layout reports it.

    pdfTeX emits a display equation as one or two blocks, which is a far
    better starting point than a stream of lines: `∂det(X)/∂X = ...` arrives
    as a small numerator block overlapping a block that carries the rest of
    the equation and its number.
    """

    text: str
    bbox: tuple[float, float, float, float]
    math: bool
    lines: list[Line] = field(default_factory=list)


@dataclass
class Region:
    bbox: tuple[float, float, float, float]
    equation: int | None
    text: str = ""

    @classmethod
    def of(
        cls, boxes: list[tuple[float, float, float, float]], equation: int | None, text: str
    ) -> Region:
        return cls(
            (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ),
            equation,
            text,
        )


def page_lines(page: Any) -> list[Line]:
    lines: list[Line] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            math_font = any(_MATH_FONT_RE.search(str(span.get("font", ""))) for span in spans)
            lines.append(Line(text=text, bbox=tuple(line["bbox"]), math_font=math_font))
    lines.sort(key=lambda line: (round(line.bbox[1], 1), line.bbox[0]))
    return lines


def score_line(line: Line, page_width: float, body_left: float) -> tuple[int, int | None]:
    """How much this line looks like a display equation, and its number."""
    score = 0
    number: int | None = None

    match = _EQ_NUMBER_RE.search(line.text)
    if match and line.bbox[2] > page_width * 0.78:
        score += 3
        number = int(match.group(1))

    if line.math_font:
        score += 2

    indented = line.bbox[0] > body_left + page_width * 0.06
    centre = (line.bbox[0] + line.bbox[2]) / 2
    centred = abs(centre - page_width / 2) < page_width * 0.18
    if indented and centred:
        score += 1

    body = _EQ_NUMBER_RE.sub("", line.text)
    if body:
        density = sum(1 for ch in body if ch in _SYMBOLS) / len(body)
        if density > 0.18:
            score += 1

    return score, number


def group_regions(lines: list[Line], page_width: float, body_left: float) -> list[Region]:
    """Fallback grouping: consecutive equation-ish lines become one region.

    Used only for documents that do not number their equations, where there
    is no anchor to build a region around.
    """
    regions: list[Region] = []
    current: list[Line] = []
    number: int | None = None

    def flush() -> None:
        nonlocal current, number
        if current:
            regions.append(
                Region.of(
                    [line.bbox for line in current],
                    number,
                    " ".join(line.text for line in current),
                )
            )
        current, number = [], None

    for line in lines:
        score, line_number = score_line(line, page_width, body_left)
        if score >= SCORE_THRESHOLD:
            gap = line.bbox[1] - current[-1].bbox[3] if current else 0.0
            if current and gap >= max(current[-1].height, 4.0):
                flush()
            current.append(line)
            number = line_number if line_number is not None else number
        else:
            flush()
    flush()
    return regions


# -- block-anchored grouping (the primary strategy) ------------------------


def page_blocks(page: Any) -> list[Block]:
    """Text blocks on a page, minus the running head and the folio."""
    height = page.rect.height
    blocks: list[Block] = []
    for raw in page.get_text("dict").get("blocks", []):
        if raw.get("type") != 0:
            continue
        lines = raw.get("lines", [])
        text = " ".join(
            "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            for line in lines
        ).strip()
        if not text:
            continue
        x0, y0, x1, y1 = raw["bbox"]
        if y1 < HEADER_MARGIN or y0 > height - FOOTER_MARGIN:
            continue
        fonts = " ".join(
            str(span.get("font", "")) for line in lines for span in line.get("spans", [])
        )
        members = [
            Line(
                text="".join(s.get("text", "") for s in line.get("spans", [])).strip(),
                bbox=tuple(line["bbox"]),
                math_font=any(
                    _MATH_FONT_RE.search(str(s.get("font", ""))) for s in line.get("spans", [])
                ),
            )
            for line in lines
            if "".join(s.get("text", "") for s in line.get("spans", [])).strip()
        ]
        blocks.append(Block(text, (x0, y0, x1, y1), bool(_MATH_FONT_RE.search(fonts)), members))
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return blocks


def document_margins(doc: Any, sample: int = 40) -> tuple[float, float]:
    """The text column's left and right edges, measured over the document.

    Per page these are unreliable -- on a page that is mostly equations the
    commonest line start is an equation indent, not the margin. Over the whole
    document the prose wins, and the margins are a constant of the layout.
    """
    lefts: Counter[int] = Counter()
    rights: Counter[int] = Counter()
    width = 0.0
    pages = range(min(doc.page_count, sample))
    for index in pages:
        page = doc.load_page(index)
        width = max(width, float(page.rect.width))
        for block in page_blocks(page):
            lefts[round(block.bbox[0])] += 1
            rights[round(block.bbox[2])] += 1
    body_left = float(lefts.most_common(1)[0][0]) if lefts else 0.0
    modal_right = float(rights.most_common(1)[0][0]) if rights else 0.0
    # The floor matters for documents whose commonest block end is ragged
    # prose rather than a right-aligned equation-number column.
    return body_left, max(modal_right, width * 0.72)


def anchor_number(block: Block, right_margin: float, body_left: float = 0.0) -> int | None:
    """The equation number this block carries, if any.

    Read off the block's own lines rather than its concatenated text: when a
    block holds the end of one equation and the start of the next, the number
    is not at the end of the text and an end-anchored match would miss it.
    """
    markers = marker_lines(block, right_margin, body_left)
    if markers:
        match = _EQ_NUMBER_RE.search(markers[-1].text)
        if match:
            return int(match.group(1))
    if not block.lines:  # synthesised blocks keep only their text
        match = _EQ_NUMBER_RE.search(block.text)
        if match and block.bbox[2] >= right_margin - RIGHT_MARGIN_SLACK:
            return int(match.group(1))
    return None


def _overlaps(a: Sequence[float], b: Sequence[float]) -> bool:
    """True when two boxes genuinely share vertical extent.

    Strictly greater than zero: consecutive display equations in a dense list
    can touch to within a fraction of a point, and any slack here chains them
    into one enormous region.
    """
    return min(a[3], b[3]) - max(a[1], b[1]) > 0.0


def marker_lines(block: Block, right_margin: float, body_left: float) -> list[Line]:
    """The lines in a block that carry an equation number.

    Reaching the right margin is not enough on its own: justified body text
    reaches it too, and a sentence ending "...the derivative (230)" would then
    conjure a second copy of equation 230 out of a cross-reference. So a
    marker is either a line that is *only* the number -- how LaTeX sets it --
    or a line that ends with one and is indented clear of the text margin.
    """
    out: list[Line] = []
    for line in block.lines:
        if not _EQ_NUMBER_RE.search(line.text):
            continue
        if line.bbox[2] < right_margin - RIGHT_MARGIN_SLACK:
            continue
        if _EQ_ONLY_RE.match(line.text.strip()) or line.bbox[0] > body_left + MARGIN_SLACK:
            out.append(line)
    return out


def split_by_markers(block: Block, right_margin: float, body_left: float) -> list[Block]:
    """Re-cut a block around the equation numbers inside it.

    PyMuPDF's blocks are close to equations but not equal to them. Two ways
    they go wrong, both fixed here by working one level down, on lines:

    * a tightly set list of rules -- the Cookbook's twelve differentiation
      identities -- arrives as a *single* block with twelve numbers in it, so
      eleven equations would silently vanish;
    * the tail of one equation and the head of the next share a block, which
      leaves the number stranded mid-block where an end-anchored match cannot
      see it, and drags a neighbour into the crop.

    Each marker line seeds a group that grows by vertical overlap. Lines that
    reach no marker come back as their own block rather than being forced into
    the nearest one.
    """
    markers = marker_lines(block, right_margin, body_left)
    if not markers:
        return [block]

    groups: list[list[Line]] = [[m] for m in markers]
    spans = [list(m.bbox) for m in markers]
    remaining = [line for line in block.lines if line not in markers]

    growing = True
    while growing:
        growing = False
        for line in list(remaining):
            overlaps = [
                (
                    min(line.bbox[3], s[3]) - max(line.bbox[1], s[1]),
                    -abs(_centre(line.bbox) - _centre(s)),
                    i,
                )
                for i, s in enumerate(spans)
            ]
            depth, _, index = max(overlaps)
            if depth <= 0.0:
                continue
            groups[index].append(line)
            spans[index][1] = min(spans[index][1], line.bbox[1])
            spans[index][3] = max(spans[index][3], line.bbox[3])
            remaining.remove(line)
            growing = True

    out = [_block_of(group) for group in groups]
    out.extend(_block_of(cluster) for cluster in _cluster_lines(remaining))
    return out


def _block_of(lines: list[Line]) -> Block:
    ordered = sorted(lines, key=lambda line: line.bbox[0])
    boxes = [line.bbox for line in ordered]
    return Block(
        text=" ".join(line.text for line in ordered),
        bbox=(
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ),
        math=any(line.math_font for line in ordered),
        lines=ordered,
    )


def _cluster_lines(lines: list[Line]) -> list[list[Line]]:
    clusters: list[list[Line]] = []
    for line in sorted(lines, key=lambda line: line.bbox[1]):
        if clusters and _overlaps(
            (0.0, min(x.bbox[1] for x in clusters[-1]), 0.0, max(x.bbox[3] for x in clusters[-1])),
            line.bbox,
        ):
            clusters[-1].append(line)
        else:
            clusters.append([line])
    return clusters


def _centre(bbox: Sequence[float]) -> float:
    return (bbox[1] + bbox[3]) / 2


def _cluster(blocks: list[Block]) -> list[list[Block]]:
    """Group blocks that vertically overlap, transitively."""
    clusters: list[list[Block]] = []
    for block in sorted(blocks, key=lambda b: b.bbox[1]):
        if clusters and _overlaps(_bounds(clusters[-1]), block.bbox):
            clusters[-1].append(block)
        else:
            clusters.append([block])
    return clusters


def _bounds(blocks: list[Block]) -> tuple[float, float, float, float]:
    boxes = [b.bbox for b in blocks]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def anchored_regions(blocks: list[Block], body_left: float, right_margin: float) -> list[Region]:
    """One region per numbered equation, plus leftover display math.

    Each equation-number block anchors a region, which then grows to include
    any block it vertically overlaps -- the numerator sitting above the rule,
    a sum's limits, an over-brace. Anchors never absorb each other, so a list
    of tightly packed equations stays a list.
    """
    blocks = [sub for block in blocks for sub in split_by_markers(block, right_margin, body_left)]
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    anchors = [
        (i, n) for i, b in enumerate(blocks) if (n := anchor_number(b, right_margin, body_left))
    ]
    anchor_ix = {i for i, _ in anchors}
    claimed: set[int] = set()
    regions: list[Region] = []

    for i, number in anchors:
        group = [i]
        claimed.add(i)
        span = list(blocks[i].bbox)
        growing = True
        while growing:
            growing = False
            for j, block in enumerate(blocks):
                if j in claimed or j in anchor_ix:
                    continue
                # Blocks flush against the text margin are prose or headings;
                # display math is always indented from it.
                if block.bbox[0] <= body_left + MARGIN_SLACK:
                    continue
                if _overlaps(tuple(span), block.bbox):
                    group.append(j)
                    claimed.add(j)
                    span[1] = min(span[1], block.bbox[1])
                    span[3] = max(span[3], block.bbox[3])
                    growing = True
        ordered = sorted(group)
        regions.append(
            Region.of(
                [blocks[j].bbox for j in ordered],
                number,
                " ".join(blocks[j].text for j in ordered),
            )
        )

    # Display math with no number of its own still deserves a unit -- but as
    # whole equations, not as the dozen fragments a big fraction breaks into,
    # so cluster what is left before emitting it.
    leftover = [
        block
        for j, block in enumerate(blocks)
        if j not in claimed and block.math and block.bbox[0] > body_left + MARGIN_SLACK
    ]
    for cluster in _cluster(leftover):
        bbox = _bounds(cluster)
        text = " ".join(b.text for b in sorted(cluster, key=lambda b: b.bbox[0]))
        if bbox[2] - bbox[0] < MIN_UNNUMBERED_WIDTH or len(text.strip()) < 3:
            continue  # a stray delimiter glyph, not an equation
        regions.append(Region(bbox, None, text))

    regions.sort(key=lambda r: r.bbox[1])
    return regions


@dataclass(frozen=True)
class SectionMark:
    """Where a numbered section starts, as a (page, y-from-top) position."""

    page: int  # 1-based
    y: float
    number: str


def toc_sections(doc: Any) -> list[SectionMark]:
    """Section starts from PDF bookmarks, in reading order.

    Three ways to get a number out of an outline entry, best first:

    1. hyperref's named destination -- `subsection.2.4` *is* the number, and
       any LaTeX document with hyperref has them;
    2. a number leading the title, for outlines written by hand;
    3. counting outline levels, which is right whenever the document numbers
       its sections in the usual way and nothing was skipped.

    Marks carry a position, not just a page: this book starts three
    subsections on one page, so page granularity would misfile equations.
    """
    try:
        toc = doc.get_toc(simple=False)
    except Exception:
        return []

    marks: list[SectionMark] = []
    counters: list[int] = []
    for entry in toc:
        level, title, page = int(entry[0]), str(entry[1]), int(entry[2])
        target = entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {}

        counters = counters[:level] + [0] * max(0, level - len(counters))
        counters[level - 1] += 1

        number = _number_from_dest(target.get("nameddest"))
        if number is None:
            heading = _HEADING_RE.match(title.strip())
            number = heading.group(1) if heading else ".".join(str(c) for c in counters)

        dest_page = int(target.get("page", page - 1)) + 1
        point = target.get("to")
        height = float(doc.load_page(dest_page - 1).rect.height) if dest_page >= 1 else 0.0
        y = height - float(point.y) if point is not None else 0.0
        marks.append(SectionMark(dest_page, y, number))

    marks.sort(key=lambda m: (m.page, m.y))
    return marks


_DEST_RE = re.compile(r"^(?:sub)*section\.([0-9]+(?:\.[0-9]+)*)$")


def _number_from_dest(nameddest: object) -> str | None:
    match = _DEST_RE.match(str(nameddest or ""))
    return match.group(1) if match else None


def section_at(marks: list[SectionMark], page: int, y: float) -> str:
    """The section a point on a page falls in."""
    current = ""
    for mark in marks:
        if (mark.page, mark.y) <= (page, y):
            current = mark.number
        else:
            break
    return current


def heading_on_page(lines: list[Line]) -> str | None:
    """Fallback for PDFs with no usable outline: a numbered heading line."""
    for line in lines:
        match = _HEADING_RE.match(line.text.strip())
        if match and len(match.group(1)) <= 8:
            return match.group(1)
    return None


def context_for(region: Region, blocks: list[Block], body_left: float, limit: int = 400) -> str:
    """The prose above an equation region.

    Only blocks flush against the text margin -- the surrounding sentences,
    not whatever equation happens to sit above this one. Display math is
    always indented clear of the margin, which is the same test
    `anchored_regions` uses to keep prose *out* of a crop; using it here keeps
    the two consistent.

    Without the filter this returns the mangled text layer of neighbouring
    equations, which is worse than returning nothing: it looks like context.
    """
    top = region.bbox[1]
    before = [b.text for b in blocks if b.bbox[3] <= top and b.bbox[0] <= body_left + MARGIN_SLACK]
    return " ".join(" ".join(before).split())[-limit:].strip()


def segment(
    pdf_path: Path,
    source: str,
    *,
    pages: range | None = None,
) -> list[Unit]:
    """Locate every display equation in the PDF and return units for them.

    Returns geometry, not pictures. The crop is still the authority a human
    decides from, but it is rendered from this bounding box on demand -- so a
    change in segmentation is a diff you can read, and the repo does not
    accumulate a thousand PNGs that go stale the next time you re-extract.
    """
    fitz = _fitz()
    doc = fitz.open(str(pdf_path))
    marks = toc_sections(doc)
    body_left, right_margin = document_margins(doc)
    units: list[Unit] = []
    used: set[str] = set()
    fallback_section = ""

    try:
        for index in range(doc.page_count):
            page_number = index + 1
            if pages is not None and page_number not in pages:
                continue
            page = doc.load_page(index)
            blocks = page_blocks(page)
            if not blocks:
                continue
            width = page.rect.width
            if not marks:
                fallback_section = heading_on_page(page_lines(page)) or fallback_section

            regions = anchored_regions(blocks, body_left, right_margin)
            if not any(r.equation for r in regions):
                # No numbered equations here: fall back to scoring lines.
                regions = group_regions(page_lines(page), width, body_left)

            for position, region in enumerate(regions):
                x0, y0, x1, y1 = region.bbox
                section = section_at(marks, page_number, y0) if marks else fallback_section
                above = regions[position - 1].bbox[3] if position else None
                below = regions[position + 1].bbox[1] if position + 1 < len(regions) else None
                bbox = [
                    max(0.0, x0 - CROP_PADDING),
                    max(0.0, y0 - _vertical_pad(y0 - above if above is not None else None)),
                    min(width, x1 + CROP_PADDING),
                    min(
                        page.rect.height,
                        y1 + _vertical_pad(below - y1 if below is not None else None),
                    ),
                ]
                units.append(
                    Unit(
                        id=_unique_id(source, section, region.equation, page_number, y0, used),
                        locator=Locator(
                            section=section,
                            equation=region.equation,
                            page=page_number,
                            bbox=[round(v, 1) for v in bbox],
                        ),
                        context=context_for(region, blocks, body_left),
                        state="new",
                    )
                )
    finally:
        doc.close()
    return units


def _vertical_pad(gap: float | None) -> float:
    """Padding above or below a crop, never crossing into the neighbour.

    Display equations in a dense list sit two or three points apart, so a
    fixed margin would put a slice of the equation above and below into every
    crop -- and the crop is the artefact a human decides from.
    """
    if gap is None:
        return CROP_PADDING
    return max(0.0, min(CROP_PADDING, gap / 2))


def _unique_id(
    source: str, section: str, equation: int | None, page: int, y: float, used: set[str]
) -> str:
    """`source:section:number`, or page-and-position when there is no number.

    Position rather than a running index: a sequence number would shift every
    id below it the moment detection picks up one more region on the page,
    orphaning triage state that was attached to the old ids.
    """
    tail = str(equation) if equation is not None else f"p{page}y{int(y)}"
    stem = f"{source}:{section or 'eq'}:{tail}"
    unit_id = stem
    bump = 1
    while unit_id in used:
        bump += 1
        unit_id = f"{stem}-{bump}"
    used.add(unit_id)
    return unit_id
