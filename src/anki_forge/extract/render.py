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
from pathlib import Path
from typing import Any

RENDER_ZOOM = 3.0
TRIAGE_CONTEXT = 40.0  # points of surrounding page shown around a crop at triage
OUTLINE_WIDTH = 3  # pixels
OUTLINE_COLOUR = (210, 120, 90)


class PdfUnavailable(RuntimeError):
    """PyMuPDF is not installed."""


def _fitz() -> Any:
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
    ) -> bytes:
        """PNG bytes for a 1-based page number and a top-left-origin bbox.

        `context` widens the view by that many points on every side and
        `outline` draws the unit's own box inside it. Together they make the
        two ways segmentation fails visible to whoever is looking: an equation
        split across units shows its missing lines just outside the box, and
        two equations merged into one show two numbers inside it. A bare crop
        cannot show either, because a bare crop *is* the mistake.
        """
        if not 1 <= page <= self._doc.page_count:
            raise ValueError(f"page {page} is outside the document")
        target = self._doc.load_page(page - 1)
        box = self._fitz.Rect(*bbox)
        # Rect + tuple is PyMuPDF's expand operator, not concatenation.
        clip = (box + (-context, -context, context, context)) & target.rect  # noqa: RUF005
        pixmap = target.get_pixmap(matrix=self._matrix, clip=clip)
        if outline and context > 0:
            self._draw_outline(pixmap, box, clip)
        return bytes(pixmap.tobytes("png"))

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

    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> CropRenderer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def render_crop(
    pdf_path: Path,
    page: int,
    bbox: Sequence[float],
    *,
    context: float = 0.0,
    outline: bool = False,
) -> bytes:
    """One-off crop, for the app's per-request rendering."""
    with CropRenderer(pdf_path) as renderer:
        return renderer.render(page, bbox, context=context, outline=outline)
