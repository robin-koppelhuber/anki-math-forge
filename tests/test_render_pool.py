"""Documents stay open between renders.

Opening the file is the whole cost of a crop: about 4ms off an open
document, and 1.2 *seconds* on a 16MB, 312-page book. Every render used to
pay it, so a triage deck of fifty units opened one PDF fifty times and the
crops arrived over a minute, while the same book's full-page view, which is
one request, came up at once.
"""

from __future__ import annotations

import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from anki_math_forge.extract import render as render_mod

fitz = pytest.importorskip("fitz", reason="needs the `pdf` extra: uv sync --extra pdf")

BOX = (72.0, 90.0, 400.0, 150.0)


@pytest.fixture(autouse=True)
def _clean_pool() -> None:
    render_mod.forget_documents()


def a_pdf(path: Path, pages: int = 2, text: str = "a line of it") -> Path:
    doc = fitz.open()
    for n in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), f"{text} {n}", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every path `CropRenderer` opens, in order."""
    seen: list[str] = []
    real = render_mod.CropRenderer.__init__

    def counted(self: object, pdf_path: Path, zoom: float = render_mod.RENDER_ZOOM) -> None:
        seen.append(str(pdf_path))
        real(self, pdf_path, zoom)  # type: ignore[arg-type]

    monkeypatch.setattr(render_mod.CropRenderer, "__init__", counted)
    return seen


def test_a_deck_of_crops_opens_the_document_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = a_pdf(tmp_path / "book.pdf", pages=4)
    seen = opens(monkeypatch)

    for page in (1, 2, 3, 4, 1, 2):
        render_mod.render_crop(book, page, BOX, context=20.0)

    assert seen == [str(book)], "six crops, one open"


def test_the_page_view_and_the_crops_share_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Different zooms, so they are two entries rather than one, and each is
    opened once. A page is read and a crop is inspected, which is why the
    zooms differ in the first place."""
    book = a_pdf(tmp_path / "book.pdf")
    seen = opens(monkeypatch)

    render_mod.render_crop(book, 1, BOX)
    render_mod.render_page(book, 1)
    render_mod.render_crop(book, 2, BOX)
    render_mod.render_page(book, 2)

    assert seen == [str(book), str(book)], "one per zoom, not one per render"


def test_rewriting_the_file_is_read_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise re-exporting a PDF serves crops of the old one until the app
    is restarted."""
    book = a_pdf(tmp_path / "book.pdf", pages=2)
    longer = a_pdf(tmp_path / "longer.pdf", pages=5)

    assert render_mod.page_count(book) == 2
    seen = opens(monkeypatch)
    shutil.copy(longer, book)

    assert render_mod.page_count(book) == 5
    assert seen == [str(book)], "and only because the file moved"


def test_a_pooled_document_is_not_closed_under_a_reader(tmp_path: Path) -> None:
    """A pooled renderer is dropped, never closed: whoever is rendering holds
    a reference. Closing it to save a file handle would pull the document out
    from under a thread mid-render."""
    kept = a_pdf(tmp_path / "kept.pdf")
    with render_mod.borrow(kept) as renderer:
        # Push it out of the pool from underneath, the way a long run over
        # many documents would.
        for n in range(render_mod.POOL_SIZE + 2):
            render_mod.page_count(a_pdf(tmp_path / f"other{n}.pdf"))
        assert renderer.page_count == 2, "still usable"


def test_more_documents_than_the_pool_holds_still_render(tmp_path: Path) -> None:
    books = [a_pdf(tmp_path / f"b{n}.pdf", pages=n + 1) for n in range(render_mod.POOL_SIZE + 3)]

    assert [render_mod.page_count(b) for b in books] == list(range(1, len(books) + 1))


def test_eight_threads_on_one_document(tmp_path: Path) -> None:
    """The app answers from a thread pool and a PyMuPDF document is not safe
    to use from two threads at once, so one document renders one at a time."""
    book = a_pdf(tmp_path / "book.pdf", pages=3)

    def one(n: int) -> int:
        return len(render_mod.render_crop(book, (n % 3) + 1, BOX, context=10.0))

    with ThreadPoolExecutor(max_workers=8) as pool:
        sizes = list(pool.map(one, range(24)))

    assert all(size > 0 for size in sizes)
    assert len(sizes) == 24


def test_two_threads_opening_the_same_document_agree(tmp_path: Path) -> None:
    """Both may open it; one entry wins and the other is dropped. What must
    not happen is two entries for one key, which would double the memory and
    lose the locking that makes the first point true."""
    book = a_pdf(tmp_path / "book.pdf")
    ready = threading.Barrier(4)

    def one(_: int) -> int:
        ready.wait()
        return render_mod.page_count(book)

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(one, range(4))) == [2, 2, 2, 2]

    assert len(render_mod._POOL) == 1


def test_a_document_that_is_gone_still_raises_its_own_error(tmp_path: Path) -> None:
    with pytest.raises(Exception, match=r"(?i)no such file|cannot open|not found"):
        render_mod.page_count(tmp_path / "nothing.pdf")
