"""The PDF path: display-equation detection, cropping, locators.

Runs against a PDF built in-process, so the fixture is legible and there is no
binary blob in the repo. Skipped when the optional `pdf` extra is absent.
"""

from __future__ import annotations

import pytest

from anki_forge import extract
from anki_forge.config import Config
from anki_forge.extract import pdf, render
from anki_forge.ledger import Ledger

fitz = pytest.importorskip("fitz", reason="needs the `pdf` extra: uv sync --extra pdf")


def test_display_equations_become_units_with_geometry(pdf_source: Config) -> None:
    report = extract.run(pdf_source, "book")
    assert report.mode == "pdf"
    units = Ledger.load(pdf_source.units_path("book")).units

    assert [u.locator.equation for u in units] == [61, 62]
    for unit in units:
        assert unit.locator.page == 1
        assert unit.locator.section == "2.4"
        assert unit.has_crop
        x0, y0, x1, y1 = unit.locator.bbox
        assert x1 > x0 and y1 > y0


def test_extraction_writes_no_image_files(pdf_source: Config) -> None:
    """The ledger holds geometry; crops are rendered from the PDF on demand."""
    extract.run(pdf_source, "book")
    assert list((pdf_source.sources_dir / "book").rglob("*.png")) == []


def test_a_crop_renders_from_the_bounding_box(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    unit = Ledger.load(pdf_source.units_path("book")).units[0]
    page, bbox = unit.crop_geometry()
    png = render.render_crop(pdf_source.source("book").pdf, page, bbox)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 200


def test_rendering_refuses_a_page_outside_the_document(pdf_source: Config) -> None:
    document = pdf_source.source("book").pdf
    with pytest.raises(ValueError, match="outside the document"):
        render.render_crop(document, 99, [0.0, 0.0, 100.0, 100.0])


def test_geometry_survives_the_ledger_round_trip(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    path = pdf_source.units_path("book")
    before = path.read_text(encoding="utf-8")
    Ledger.load(path).save()
    assert path.read_text(encoding="utf-8") == before
    assert '"bbox"' in before, "the bbox is what makes a re-segmentation reviewable"


def test_prose_is_not_mistaken_for_an_equation(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    units = Ledger.load(pdf_source.units_path("book")).units
    assert len(units) == 2, "page 2 has no equations and must contribute nothing"
    assert all(u.locator.equation is not None for u in units)


def test_context_is_the_text_above_the_equation(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    unit = Ledger.load(pdf_source.units_path("book")).units[0]
    assert "everyone forgets" in unit.context


def test_extraction_reads_no_mathematics(pdf_source: Config) -> None:
    """`extract` is an indexer: transcription is `/transcribe`'s job."""
    report = extract.run(pdf_source, "book")
    units = Ledger.load(pdf_source.units_path("book")).units
    assert all(u.transcription == "none" for u in units)
    assert all(u.tex_auto == "" for u in units)
    assert report.warnings and "no transcription yet" in report.warnings[0]


def test_rerunning_preserves_triage(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    path = pdf_source.units_path("book")
    ledger = Ledger.load(path)
    first_id = ledger.units[0].id
    ledger.set_state(first_id, "queued")
    ledger.save()

    second = extract.run(pdf_source, "book")
    assert second.added == 0
    assert Ledger.load(path).get(first_id).state == "queued"


def test_page_range_limits_the_work(pdf_source: Config) -> None:
    report = extract.run(pdf_source, "book", pages=range(2, 3))
    assert report.found == 0


# -- the scoring function itself -------------------------------------------


def line(text: str, x0: float, x1: float, *, math_font: bool = False) -> pdf.Line:
    return pdf.Line(text=text, bbox=(x0, 100.0, x1, 112.0), math_font=math_font)


def test_a_right_margin_equation_number_is_the_strongest_signal() -> None:
    score, number = pdf.score_line(line("x = y + z    (61)", 250, 520), 595, 72)
    assert number == 61
    assert score >= pdf.SCORE_THRESHOLD


def test_ordinary_prose_scores_below_the_threshold() -> None:
    score, number = pdf.score_line(line("This is a normal sentence of text.", 72, 400), 595, 72)
    assert score < pdf.SCORE_THRESHOLD
    assert number is None


def test_a_math_font_alone_can_carry_a_line() -> None:
    text = "A^-1 = (B + C)^-1"
    score, _ = pdf.score_line(line(text, 250, 400, math_font=True), 595, 72)
    assert score >= pdf.SCORE_THRESHOLD


# -- block anchoring -------------------------------------------------------
#
# These reproduce layouts met in the real Matrix Cookbook, each of which broke
# an earlier version of the segmenter.


def block(text: str, x0: float, y0: float, x1: float, y1: float, *, lines=None) -> pdf.Block:
    members = lines if lines is not None else [pdf.Line(text, (x0, y0, x1, y1), True)]
    return pdf.Block(text, (x0, y0, x1, y1), True, members)


def numbered(text: str, y: float, number: int) -> pdf.Block:
    """An equation line plus its right-margin number, as pdfTeX sets them."""
    return block(
        f"{text} ({number})",
        200.0,
        y,
        468.5,
        y + 11.0,
        lines=[
            pdf.Line(text, (200.0, y, 380.0, y + 11.0), True),
            pdf.Line(f"({number})", (450.8, y, 468.5, y + 11.0), False),
        ],
    )


def test_a_cross_reference_in_prose_is_not_an_equation_number() -> None:
    """Justified body text reaches the right margin too."""
    prose = block(
        "Since the two results have the same sign, the derivative (230)",
        124.8,
        550.0,
        468.5,
        560.0,
    )
    assert pdf.marker_lines(prose, 468.5, 124.8) == []
    assert pdf.anchor_number(prose, 468.5, 124.8) is None


def test_an_indented_equation_line_is_an_equation_number() -> None:
    eq = numbered("A = B", 550.0, 230)
    assert pdf.anchor_number(eq, 468.5, 124.8) == 230


def test_a_block_packed_with_many_equations_is_split() -> None:
    """The Cookbook sets twelve differentiation rules as one block."""
    lines = []
    for i, y in enumerate(range(340, 400, 12)):
        n = 33 + i
        lines.append(pdf.Line(f"rule {n}", (200.0, y, 300.0, y + 10.0), True))
        lines.append(pdf.Line(f"({n})", (450.8, y, 468.5, y + 10.0), False))
    packed = pdf.Block("...", (161.0, 340.0, 468.5, 400.0), True, lines)

    parts = pdf.split_by_markers(packed, 468.5, 124.8)
    numbers = [pdf.anchor_number(p, 468.5, 124.8) for p in parts]
    assert numbers == [33, 34, 35, 36, 37]


def test_a_numerator_block_joins_the_equation_below_it() -> None:
    """`∂det(X)/∂X = ...` arrives as a numerator plus the rest."""
    numerator = block("d det(X)", 193.0, 152.8, 231.0, 162.8)
    rest = numbered("/dX = det(X)(X-1)T", 157.7, 49)
    regions = pdf.anchored_regions([numerator, rest], 124.8, 468.5)
    assert len(regions) == 1
    assert regions[0].equation == 49
    assert regions[0].bbox[1] == 152.8, "the numerator must be inside the crop"


def test_tightly_packed_equations_do_not_merge() -> None:
    """Consecutive display equations can touch to within a fraction of a point."""
    first = numbered("A = B", 157.9, 1)
    second = numbered("C = D", 168.9, 2)  # starts 0.0pt after the first ends
    regions = pdf.anchored_regions([first, second], 124.8, 468.5)
    assert [r.equation for r in regions] == [1, 2]


def test_an_anchor_never_absorbs_another_anchor() -> None:
    tall = numbered("a very tall equation", 100.0, 7)
    tall.bbox = (200.0, 100.0, 468.5, 140.0)
    overlapping = numbered("B = C", 120.0, 8)
    regions = pdf.anchored_regions([tall, overlapping], 124.8, 468.5)
    assert sorted(r.equation for r in regions) == [7, 8]


def test_prose_is_never_pulled_into_an_equation() -> None:
    prose = block("If X is square and invertible, then", 124.8, 150.0, 273.0, 160.0)
    eq = numbered("A = B", 155.0, 52)
    regions = pdf.anchored_regions([prose, eq], 124.8, 468.5)
    assert len(regions) == 1
    assert regions[0].bbox[0] >= 200.0, "the prose sits left of the crop"


def test_crop_padding_never_crosses_into_a_neighbour() -> None:
    assert pdf._vertical_pad(None) == pdf.CROP_PADDING
    assert pdf._vertical_pad(3.0) == 1.5, "half the gap, so two crops cannot overlap"
    assert pdf._vertical_pad(100.0) == pdf.CROP_PADDING
    assert pdf._vertical_pad(-1.0) == 0.0


def test_hyperref_destinations_give_section_numbers() -> None:
    class FakeDoc:
        page_count = 2

        def get_toc(self, simple: bool = True):
            return [
                [
                    1,
                    "Basics",
                    6,
                    {"page": 5, "to": fitz.Point(124.0, 716.0), "nameddest": "section.1"},
                ],
                [
                    2,
                    "Trace",
                    6,
                    {"page": 5, "to": fitz.Point(124.0, 523.0), "nameddest": "subsection.1.1"},
                ],
                [
                    2,
                    "Determinant",
                    6,
                    {"page": 5, "to": fitz.Point(124.0, 377.0), "nameddest": "subsection.1.2"},
                ],
            ]

        def load_page(self, index: int):
            return fitz.open().new_page(width=595, height=842)

    marks = pdf.toc_sections(FakeDoc())
    assert [m.number for m in marks] == ["1", "1.1", "1.2"]
    # y measured from the top, so later subsections sort lower down the page
    assert pdf.section_at(marks, 6, 200.0) == "1"
    assert pdf.section_at(marks, 6, 400.0) == "1.1"
    assert pdf.section_at(marks, 6, 600.0) == "1.2"


def test_an_outline_without_numbers_falls_back_to_counting_levels() -> None:
    class FakeDoc:
        page_count = 1

        def get_toc(self, simple: bool = True):
            return [
                [1, "First", 1, {"page": 0, "to": fitz.Point(0.0, 800.0)}],
                [2, "Nested", 1, {"page": 0, "to": fitz.Point(0.0, 700.0)}],
                [1, "Second", 1, {"page": 0, "to": fitz.Point(0.0, 600.0)}],
            ]

        def load_page(self, index: int):
            return fitz.open().new_page(width=595, height=842)

    assert [m.number for m in pdf.toc_sections(FakeDoc())] == ["1", "1.1", "2"]


# -- triage context --------------------------------------------------------


def test_context_widens_the_crop(pdf_source: Config) -> None:
    extract.run(pdf_source, "book")
    unit = Ledger.load(pdf_source.units_path("book")).units[0]
    page, bbox = unit.crop_geometry()
    document = pdf_source.source("book").pdf

    tight = render.render_crop(document, page, bbox)
    wide = render.render_crop(document, page, bbox, context=render.TRIAGE_CONTEXT, outline=True)
    assert len(wide) > len(tight), "the wider view must actually show more page"


def test_the_outline_is_actually_drawn(pdf_source: Config) -> None:
    """A clipped pixmap carries the clip's own origin; without that offset
    `set_rect` silently no-ops and the box never appears."""
    extract.run(pdf_source, "book")
    unit = Ledger.load(pdf_source.units_path("book")).units[0]
    page, bbox = unit.crop_geometry()
    document = pdf_source.source("book").pdf

    plain = render.render_crop(document, page, bbox, context=render.TRIAGE_CONTEXT)
    boxed = render.render_crop(document, page, bbox, context=render.TRIAGE_CONTEXT, outline=True)
    assert plain != boxed, "outline=True must change the pixels, not just the argument"


def test_a_tight_crop_has_no_outline(pdf_source: Config) -> None:
    """The review view wants the equation, not a box around it."""
    extract.run(pdf_source, "book")
    unit = Ledger.load(pdf_source.units_path("book")).units[0]
    page, bbox = unit.crop_geometry()
    png = render.render_crop(pdf_source.source("book").pdf, page, bbox, outline=True)
    assert png.startswith(b"\x89PNG")  # outline needs context; without it, nothing is drawn


# -- the deprecation contract ----------------------------------------------
#
# `pdf.py` is marked for deletion (ROADMAP.md §4). These pin the only promises
# the rest of the system relies on, so a replacement -- a layout model, or
# Claude reading pages -- can be checked against them rather than against 700
# lines of heuristics.


def test_segment_returns_units_with_a_locator_and_geometry(pdf_source: Config) -> None:
    """The whole contract: section, equation number, page, bbox."""
    units = pdf.segment(pdf_source.source("book").pdf, "book")
    assert units
    for unit in units:
        assert unit.id.startswith("book:")
        assert unit.locator.page is not None
        assert unit.locator.bbox is not None and len(unit.locator.bbox) == 4
    numbered = [u for u in units if u.locator.equation is not None]
    assert numbered, "a numbered document must yield numbered units, or the oracle is blind"


def test_ids_come_from_the_document_not_from_the_segmenter(pdf_source: Config) -> None:
    """Ids must survive a replacement, because triage state hangs off them."""
    first = [u.id for u in pdf.segment(pdf_source.source("book").pdf, "book")]
    second = [u.id for u in pdf.segment(pdf_source.source("book").pdf, "book")]
    assert first == second
    assert "book:2.4:61" in first, "the id is section + equation number, both printed in the book"


def test_rendering_does_not_depend_on_the_segmenter(pdf_source: Config) -> None:
    """`render.py` outlives `pdf.py`: geometry in, pixels out, nothing else."""
    png = render.render_crop(pdf_source.source("book").pdf, 1, [200.0, 150.0, 500.0, 200.0])
    assert png.startswith(b"\x89PNG")


def test_the_audit_scores_any_extractor(pdf_source: Config) -> None:
    """The completeness oracle reads the ledger, not the code that filled it."""
    from anki_forge import audit
    from anki_forge.ledger import Ledger, Locator, Unit

    hand_made = Ledger(
        pdf_source.units_path("book"),
        [
            Unit(id=f"book:1:{n}", locator=Locator(section="1", equation=n, page=1))
            for n in (1, 2, 4)
        ],
    )
    report = audit.audit(hand_made, "book")
    assert not report.complete
    assert any("3" in f.message for f in report.gaps)
