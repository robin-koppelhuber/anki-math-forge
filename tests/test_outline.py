"""The document's own outline, and the windows it defines.

`section`, `chapter` and `part` are spans the book states. They used to be
read off the units' section labels, which in a book whose outline names
sections without numbers made every section a "chapter" and handed a unit
in the last marked one the remaining 378 pages.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import context, outline
from anki_math_forge.app import create_app
from anki_math_forge.config import Config
from anki_math_forge.ledger import Ledger, Locator, Unit

#: Krause and Hübotter's shape: chapter 1 at the top level with no part, then
#: two parts holding chapters, and back matter filed under the last part.
#: Ten front-matter pages, so PDF page 11 is printed page 1.
BOOK = [
    (1, "Fundamentals of Inference", 11),
    (2, "Probability", 12),
    (2, "Probabilistic Inference", 25),
    (2, "Outlook: Decision Theory", 39),
    (1, "I Probabilistic Machine Learning", 45),
    (2, "Linear Regression", 49),
    (3, "Weight-space View", 50),
    (3, "Non-linear Features", 55),
    (3, "Function-space View", 55),
    (2, "Filtering", 61),
    (3, "Kalman Filters", 64),
    (1, "II Sequential Decision-Making", 173),
    (2, "Active Learning", 177),
    (3, "Mutual Information", 178),
    (2, "Bibliography", 398),
]
PAGES = 427
LABELS = tuple(
    ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
    + [str(n) for n in range(1, PAGES - 9)]
)


@pytest.fixture
def book() -> outline.Outline:
    return outline.build(BOOK, PAGES, LABELS)


def kinds(found: outline.Outline) -> dict[str, str]:
    return {e.title: e.kind for e in found.entries}


def test_levels_are_named_by_shape_not_by_depth(book: outline.Outline) -> None:
    """Chapter 1 is at level 1 and every later chapter at level 2."""
    named = kinds(book)

    assert named["Fundamentals of Inference"] == "chapter"
    assert named["Linear Regression"] == "chapter"
    assert named["I Probabilistic Machine Learning"] == "part"
    assert named["Probability"] == named["Weight-space View"] == "section"
    assert named["Bibliography"] == "chapter", "a leaf under a part"


def test_each_word_is_the_span_the_book_states(book: outline.Outline) -> None:
    section = book.span(50, "section", "Weight-space View")
    chapter = book.span(50, "chapter")
    part = book.span(50, "part")

    assert section and (section.title, section.first, section.last) == ("Weight-space View", 50, 55)
    assert chapter and (chapter.title, chapter.first, chapter.last) == ("Linear Regression", 49, 60)
    assert part and (part.title, part.first, part.last) == (
        "I Probabilistic Machine Learning",
        45,
        172,
    )
    assert part.large and not chapter.large


def test_the_printed_numbers_come_with_the_span(book: outline.Outline) -> None:
    """PDF page 49 is printed page 39 in a book with ten front pages."""
    chapter = book.span(50, "chapter")

    assert chapter and chapter.printed == "pp. 39-50"


def test_a_chapter_outside_any_part_is_its_own_part(book: outline.Outline) -> None:
    part = book.span(13, "part")
    assert part and part.title == "Fundamentals of Inference"


def test_a_part_opening_page_is_not_the_whole_part(book: outline.Outline) -> None:
    """Page 47 is the part's own introduction, before its first chapter."""
    chapter = book.span(47, "chapter")

    assert chapter and (chapter.first, chapter.last) == (45, 48)


def test_a_shared_page_goes_to_the_section_the_unit_names(book: outline.Outline) -> None:
    """Two sections start on page 55. The unit's own label settles which."""
    named = book.span(55, "section", "Non-linear Features")
    unnamed = book.span(55, "section")

    assert named and named.title == "Non-linear Features"
    assert unnamed and unnamed.title == "Function-space View", "the last to start"


def test_front_matter_says_what_it_is(book: outline.Outline) -> None:
    span = book.span(5, "chapter")

    assert span and (span.first, span.last) == (1, 10)
    assert "before the outline" in span.title
    assert span.printed == "pp. i-x"


def test_a_book_of_numbered_chapters_reads_the_numbers() -> None:
    """`3 Filtering` is a chapter by its title, whatever sits under it."""
    found = outline.build(
        [(1, "Part One", 1), (2, "3 Filtering", 2), (3, "3.1 Kalman", 3), (2, "4 Smoothing", 9)],
        20,
    )

    assert kinds(found) == {
        "Part One": "part",
        "3 Filtering": "chapter",
        "3.1 Kalman": "section",
        "4 Smoothing": "chapter",
    }


def test_the_cookbook_shape_has_chapters_at_the_top() -> None:
    found = outline.build([(1, "Basics", 6), (2, "Trace", 6), (1, "Derivatives", 8)], 72)

    assert kinds(found) == {"Basics": "chapter", "Trace": "section", "Derivatives": "chapter"}
    chapter = found.span(7, "chapter")
    assert chapter and (chapter.first, chapter.last) == (6, 7)
    assert chapter.printed == "", "no labels: the PDF's own numbers are the answer"


# -- from a real PDF, through the window a card writer gets --------------------


fitz = pytest.importorskip("fitz", reason="needs the `pdf` extra: uv sync --extra pdf")


def outlined_pdf(path: Path) -> None:
    """Twenty pages, two front ones labelled in roman numerals, a part with
    two chapters, the second with two sections."""
    doc = fitz.open()
    for n in range(20):
        doc.new_page(width=300, height=400).insert_text((40, 60), f"page {n + 1}")
    doc.set_toc(
        [
            [1, "I The Part", 3],
            [2, "Opening", 4],
            [2, "Later", 9],
            [3, "First Section", 9],
            [3, "Second Section", 14],
        ]
    )
    doc.set_page_labels(
        [{"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
         {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1}]
    )
    doc.save(path)


@pytest.fixture
def outlined(repo: Path) -> Config:
    folder = repo / "projects" / "paper"
    folder.mkdir(parents=True)
    outlined_pdf(folder / "paper.pdf")
    (folder / "project.toml").write_text(
        'title = "Paper"\n\n[[sources]]\nfiles = ["projects/paper/paper.pdf"]\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)
    led = Ledger(config.units_path("paper"))
    led.units.append(Unit(id="paper:x:1", locator=Locator(section="First Section", page=10)))
    led.save()
    return config


def test_the_pdf_outline_and_labels_are_read(outlined: Config) -> None:
    found = outline.of_document(outlined, "paper")

    assert found is not None
    assert kinds(found)["Later"] == "chapter"
    assert found.label(3) == "1", "page 3 is printed page 1"


def test_the_window_comes_from_the_outline(outlined: Config) -> None:
    built = context.assemble(outlined, "paper:x:1", spread="chapter")

    assert built is not None
    assert built.pages == list(range(9, 21))
    assert built.span["source"] == "outline"
    assert built.span["title"] == "Later"
    assert built.window.startswith(
        'the chapter it was printed in, "Later" (pp. 7-18, PDF pages 9-20'
    )

    section = context.assemble(outlined, "paper:x:1", spread="section")
    assert section is not None and section.pages == list(range(9, 15))


def test_a_word_in_the_toml_is_read(outlined: Config, repo: Path) -> None:
    path = repo / "projects" / "paper" / "project.toml"
    for word in ("section", "chapter", "part"):
        path.write_text(
            f'title = "Paper"\ncontext_pages = "{word}"\n\n'
            '[[sources]]\nfiles = ["projects/paper/paper.pdf"]\n',
            encoding="utf-8",
        )
        assert config_mod.load(repo).context_pages_for("paper") == word


def test_the_panel_lists_the_chapters_and_offers_the_words(outlined: Config) -> None:
    client = TestClient(create_app(outlined))
    page = client.get("/setup?project=paper").text

    assert "data-outline" in page
    assert "Later" in page and "pp. 7-18" in page
    for word in ("section", "chapter", "part"):
        assert f'<option value="{word}"' in page, word

    answer = client.post(
        "/api/sources/paper/paper.pdf/setting", json={"key": "context_pages", "value": "part"}
    )
    assert answer.status_code == 200, answer.text
    assert config_mod.load(outlined.root).projects["paper"].sources[0].context_pages == "part"


def test_triage_says_what_the_size_comes_to(outlined: Config) -> None:
    client = TestClient(create_app(outlined))
    client.post("/api/units/paper/paper:x:1/context", json={"pages": "chapter"})

    page = client.get("/units?project=paper&state=all").text

    assert "data-context-span" in page
    assert "Later · pp. 7-18 · 12 pages" in page
