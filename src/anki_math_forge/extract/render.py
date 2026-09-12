"""Rendering crops from a source document.

Deliberately separate from segmentation. `pdf.py` is a heuristic with a
deprecation notice on it; this is not, because it works purely from geometry
the ledger already holds (`locator.page` and `locator.bbox`). Whatever ends up
producing that geometry -- the current heuristic, a layout model, or Claude
reading pages -- this module is unaffected.

Nothing here is written to the repo. Crops are rendered on demand: about 4ms
with the document already open, ~150ms per request over HTTP, which is what
lets the ledger store geometry instead of a directory of PNGs that go stale
the next time anything re-segments.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RENDER_ZOOM = 3.0
# Points of surrounding page shown around a crop. Forty was right for a
# one-line display equation and useless for a theorem with a three-sentence
# preamble, so it is a default rather than a constant: `[cards] crop_context`,
# and a source overrides it. Generous on purpose -- a crop too tight to judge
# costs a review, and a crop with too much around it costs nothing.
TRIAGE_CONTEXT = 90.0
OUTLINE_WIDTH = 3  # pixels
# Red, and nothing else on a page is. This box is the answer to the only
# question the crop is being read for -- *which* of the things on this page is
# the unit -- and the muted orange it used to be read as one more highlight
# among the reader's own colours, none of which is red.
OUTLINE_COLOUR = (208, 48, 40)
# Points of clearance between the box and the outline drawn round it, so it
# reads as *around* the mark rather than as part of it.
OUTLINE_MARGIN = 4.0

# How wide a crop is cut.
#
#   box  -- the unit's own bounding box, plus `context` on every side.
#   page -- the full width of the page, `context` still deciding the height.
#
# Which one is right is a fact about where the geometry came from. A display
# equation's box has meaningful left and right edges: the segmenter found the
# equation and stopped. A mark's box does not -- it is the union of the lines
# a sentence happened to span, so its edges are wherever that sentence started
# and stopped mid-column, and cutting there slices words in half and drops the
# rest of the paragraph that gives them their meaning.
WIDTHS = ("box", "page")


@dataclass(frozen=True)
class Region:
    """Somewhere on the page a reader marked, and how to draw it.

    Deliberately not a `Mark`: this module knows PDFs and geometry and nothing
    about where marks come from or what a colour means. Whoever holds the
    marks decides which ones are on this page and what colour they are; this
    puts paint on the page.

    `rects` are one box per line, top-left origin, not their union -- see
    `Mark.rects`. `faded` is a neighbouring mark: still on the page, drawn far
    enough back that the one this unit is *about* is unmistakable.
    """

    kind: str = "highlight"
    rects: tuple[tuple[float, ...], ...] = ()
    rgb: tuple[float, float, float] = (0.55, 0.55, 0.55)
    faded: bool = False


# What each kind of mark looks like, at full strength and faded.
#
# The fading is not one number, because what "less saturation" does to a mark
# depends on its shape. A highlight is a filled band: a third of the opacity
# still reads as a tint. An underline is a hairline, and at a third of the
# opacity it is gone -- so it fades much less and relies on being thin to stay
# quiet. An area selection is an outline around a figure, and *filling* it
# would hide the figure it is pointing at, so it stays an outline either way
# and loses its weight instead. A sticky note has no extent at all -- its box
# is where the pin sits -- so it keeps enough opacity to be findable.
OPACITY = {
    "highlight": (0.42, 0.13),
    "underline": (0.90, 0.45),
    "squiggly": (0.90, 0.45),
    "strikeout": (0.90, 0.45),
    "note": (0.85, 0.38),
    "image": (0.95, 0.40),
    "ink": (0.95, 0.40),
}
DEFAULT_OPACITY = (0.85, 0.35)
# Outlined kinds, the ones whose interior belongs to the page rather than to
# the mark.
OUTLINED = ("image", "ink", "note", "text")
# For a mark whose colour this project does not recognise. Drawn rather than
# dropped: "something is marked here" is most of what a crop has to say.
UNKNOWN_COLOUR = (0.55, 0.55, 0.55)
# ...except a sticky note, whose box is a pin in the margin covering nothing
# at all. An empty square there reads as "something is missing here"; a filled
# one reads as the pin it is.
FILLED = ("note",)


def regions_for(unit: Any, page: int) -> list[Region]:
    """The marks to paint on this page of a unit's crop.

    Here rather than in the app, because the app is not the only thing that
    renders a crop: `forge crops` writes them to disk for a reading pass, and
    two things called "the crop" that disagree about what is on it is exactly
    the drift this project cannot afford -- the whole review model rests on the
    crop being the authority.

    The unit's own mark at full strength and its neighbours faded, because a
    crop with six highlights on it has to say which one the card is about.
    Only marks recorded as being on **this** page: one from the page after,
    painted here, lands on unrelated text, so a mark imported before marks
    knew their page is skipped rather than guessed at. The first mark is the
    one the unit came from, so the locator's page is its page by construction,
    which is what lets an older ledger still draw the one that matters.
    """
    from ..zotero import colour_rgb

    out: list[Region] = []
    for index, mark in enumerate(unit.marks):
        where = mark.page if mark.page is not None else (unit.locator.page if not index else None)
        boxes = mark.rects or ([mark.bbox] if mark.bbox else [])
        if where != page or not boxes:
            continue
        out.append(
            Region(
                kind=mark.kind or "highlight",
                rects=tuple(tuple(float(v) for v in box) for box in boxes),
                # A colour this project has never seen still gets drawn, in
                # grey: "something is marked here" is most of the information.
                rgb=colour_rgb(mark.colour) or UNKNOWN_COLOUR,
                faded=bool(index),
            )
        )
    return out


class PdfUnavailable(RuntimeError):
    """PyMuPDF is not installed."""


def _fitz() -> Any:
    """PyMuPDF, under whichever name this install answers to.

    `pymupdf` is the current name and `fitz` the old one, which prints a
    deprecation line to stderr on every import. That is once per crop and once
    per page-height read, which is often enough to bury a message that matters.
    """
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        pass
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - exercised by hand
        raise PdfUnavailable("PDF extraction needs PyMuPDF: `uv sync --extra pdf`") from exc
    return fitz


class CropRenderer:
    """Renders unit crops straight from the source document.

    Cheap enough to use per request -- about 4ms including the page load --
    which is what lets the ledger hold geometry instead of a directory of
    PNGs. Holds the document open, so batch work over a whole book does
    not reopen it once per unit.
    """

    def __init__(self, pdf_path: Path, zoom: float = RENDER_ZOOM) -> None:
        self._fitz = _fitz()
        self._doc = self._fitz.open(str(pdf_path))
        self._matrix = self._fitz.Matrix(zoom, zoom)

    def render(
        self,
        page: int,
        bbox: Sequence[float],
        *,
        context: float = 0.0,
        outline: bool = False,
        width: str = "box",
        regions: Sequence[Region] = (),
    ) -> bytes:
        """PNG bytes for a 1-based page number and a top-left-origin bbox.

        `context` widens the view by that many points on every side and
        `outline` draws the unit's own box inside it. Together they make the
        two ways segmentation fails visible to whoever is looking: an equation
        split across units shows its missing lines just outside the box, and
        two equations merged into one show two numbers inside it. A bare crop
        cannot show either, because a bare crop *is* the mistake.

        `width="page"` keeps the full width of the page and lets `context`
        decide only the height -- see `WIDTHS`. `regions` are painted on
        first, which is what makes a highlight look on the crop the way it
        looked in the reader that recorded it.
        """
        if not 1 <= page <= self._doc.page_count:
            raise ValueError(f"page {page} is outside the document")
        if width not in WIDTHS:
            raise ValueError(f"unknown crop width {width!r}; expected one of {', '.join(WIDTHS)}")
        target = self._doc.load_page(page - 1)
        box = self._fitz.Rect(*bbox)
        # Rect + tuple is PyMuPDF's expand operator, not concatenation.
        clip = (box + (-context, -context, context, context)) & target.rect  # noqa: RUF005
        if width == "page":
            clip = self._fitz.Rect(target.rect.x0, clip.y0, target.rect.x1, clip.y1)
        drawn = self._draw_regions(target, regions)
        try:
            pixmap = target.get_pixmap(matrix=self._matrix, clip=clip)
        finally:
            # Removed whatever happens, because this renderer stays open
            # across a whole book: leaving them would stack one page's marks
            # onto every later crop of the same page, darker each time.
            for annot in reversed(drawn):
                target.delete_annot(annot)
        if outline and context > 0:
            # Rect + tuple expands; a little clearance so the outline reads as
            # being around the mark rather than as part of it.
            margin = (-OUTLINE_MARGIN, -OUTLINE_MARGIN, OUTLINE_MARGIN, OUTLINE_MARGIN)
            self._draw_outline(pixmap, (box + margin) & clip, clip)
        return bytes(pixmap.tobytes("png"))

    def _draw_regions(self, page: Any, regions: Sequence[Region]) -> list[Any]:
        """Paint the marks onto the page, as real PDF annotations.

        Annotations rather than pixels, because that is what they are: the
        viewer already knows how to blend a highlight over text so the words
        stay readable, and reimplementing that by hand over a pixmap gets the
        blend wrong in exactly the case that matters. They are added here and
        deleted by the caller; nothing is ever saved, so the file on disk is
        untouched.
        """
        drawn: list[Any] = []
        for region in regions:
            rects = [self._fitz.Rect(*r) for r in region.rects if len(r) == 4]
            rects = [r for r in rects if not (r.is_empty or r.is_infinite)]
            if not rects:
                continue
            full, faded = OPACITY.get(region.kind, DEFAULT_OPACITY)
            opacity = faded if region.faded else full
            if region.kind in OUTLINED:
                for rect in rects:
                    annot = page.add_rect_annot(rect)
                    if region.kind in FILLED:
                        annot.set_colors(stroke=region.rgb, fill=region.rgb)
                    else:
                        annot.set_colors(stroke=region.rgb)
                    annot.set_border(width=0.6 if region.faded else 1.6)
                    annot.set_opacity(opacity)
                    annot.update()
                    drawn.append(annot)
                continue
            adder = getattr(page, f"add_{region.kind}_annot", None) or page.add_highlight_annot
            annot = adder(rects)
            annot.set_colors(stroke=region.rgb)
            annot.set_opacity(opacity)
            annot.update()
            drawn.append(annot)
        return drawn

    def _draw_outline(self, pixmap: Any, box: Any, clip: Any) -> None:
        """Trace the unit's bounding box onto the rendered page fragment.

        A clipped pixmap carries the clip's own origin, so every coordinate
        here is offset by `pixmap.x`/`pixmap.y` -- without that `set_rect`
        silently does nothing and returns False.
        """
        zoom = self._matrix.a
        left = pixmap.x + max(0, round((box.x0 - clip.x0) * zoom))
        top = pixmap.y + max(0, round((box.y0 - clip.y0) * zoom))
        right = pixmap.x + min(pixmap.width, round((box.x1 - clip.x0) * zoom))
        bottom = pixmap.y + min(pixmap.height, round((box.y1 - clip.y0) * zoom))
        if right <= left or bottom <= top:
            return
        edges = [
            (left, top, right, top + OUTLINE_WIDTH),
            (left, bottom - OUTLINE_WIDTH, right, bottom),
            (left, top, left + OUTLINE_WIDTH, bottom),
            (right - OUTLINE_WIDTH, top, right, bottom),
        ]
        for edge in edges:
            pixmap.set_rect(self._fitz.IRect(*edge), OUTLINE_COLOUR)

    @property
    def page_count(self) -> int:
        return int(self._doc.page_count)

    def page(
        self,
        number: int,
        *,
        regions: Sequence[Region] = (),
        outline: Sequence[float] | None = None,
    ) -> bytes:
        """A whole page, marks painted on, optionally with a box drawn on it.

        For reading the document rather than judging a crop. A crop answers
        "is this the right region"; sometimes the question is "what is this
        passage actually about", and that is three paragraphs up the page --
        or the page before. This is the cheap half of a PDF viewer: images the
        browser can stack and scroll, no pdf.js, nothing interactive.
        """
        if not 1 <= number <= self._doc.page_count:
            raise ValueError(f"page {number} is outside the document")
        target = self._doc.load_page(number - 1)
        drawn = self._draw_regions(target, regions)
        try:
            pixmap = target.get_pixmap(matrix=self._matrix)
        finally:
            for annot in reversed(drawn):
                target.delete_annot(annot)
        if outline is not None:
            margin = (-OUTLINE_MARGIN, -OUTLINE_MARGIN, OUTLINE_MARGIN, OUTLINE_MARGIN)
            box = (self._fitz.Rect(*outline) + margin) & target.rect
            self._draw_outline(pixmap, box, target.rect)
        return bytes(pixmap.tobytes("png"))

    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> CropRenderer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


DOCUMENT_ZOOM = 2.0
"""Pages in the scrolling view are read, not inspected. At the crop's zoom a
single page is ~1785px and 150KB, and the view stacks dozens of them."""


def render_page(
    pdf_path: Path,
    number: int,
    *,
    regions: Sequence[Region] = (),
    outline: Sequence[float] | None = None,
    zoom: float = DOCUMENT_ZOOM,
) -> bytes:
    """One page, for the app's scrolling document view."""
    with CropRenderer(pdf_path, zoom=zoom) as renderer:
        return renderer.page(number, regions=regions, outline=outline)


def page_count(pdf_path: Path) -> int:
    with CropRenderer(pdf_path) as renderer:
        return renderer.page_count


def render_crop(
    pdf_path: Path,
    page: int,
    bbox: Sequence[float],
    *,
    context: float = 0.0,
    outline: bool = False,
    width: str = "box",
    regions: Sequence[Region] = (),
) -> bytes:
    """One-off crop, for the app's per-request rendering."""
    with CropRenderer(pdf_path) as renderer:
        return renderer.render(
            page, bbox, context=context, outline=outline, width=width, regions=regions
        )
