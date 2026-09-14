"""Zotero units, against payloads captured from a real library.

The fixtures in `tests/fixtures/zotero` are verbatim responses from Zotero's
local API, not hand-written shapes, so a change in what it returns shows up
here rather than in a card six weeks later.
"""

from __future__ import annotations

import json
from pathlib import Path

from anki_math_forge.config import ZoteroConfig
from anki_math_forge.extract.zotero import build, unit_id, units_for, write_source_stub
from anki_math_forge.ledger import Unit
from anki_math_forge.zotero import COLOURS, Annotation, Attachment, Item, Zotero

FIXTURES = Path(__file__).parent / "fixtures" / "zotero"


def load(name: str) -> list[dict] | dict:
    return json.loads(FIXTURES.joinpath(name).read_text(encoding="utf-8"))


def annotations() -> list[Annotation]:
    return [Annotation.from_json(row) for row in load("annotations.json")]


class FakeZotero(Zotero):
    """Replaces the one seam. Everything else is the real client."""

    def __init__(self, routes: dict[str, object]) -> None:
        super().__init__(url="http://test")
        self.routes = routes

    def _get(self, path: str):  # type: ignore[no-untyped-def]
        for prefix, payload in self.routes.items():
            if path.startswith(prefix):
                if "limit=" in path and "start=" in path:
                    start = int(path.split("start=")[1].split("&")[0])
                    rows = payload if isinstance(payload, list) else [payload]
                    return [{"data": r} for r in rows[start : start + 100]]
                return {"data": payload}
        return []


# -- what Zotero actually hands over ----------------------------------------


def test_a_multi_line_highlight_is_one_box() -> None:
    """A highlight running past a line break is two rects, and the mark is
    both of them."""
    a = next(x for x in annotations() if x.key == "PA9M3ZIA")
    assert len(a.rects) == 2
    bbox = a.bbox(841.89)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    assert (round(x0, 1), round(x1, 1)) == (70.9, 524.4), "spans both rects horizontally"
    assert y0 < y1, "top-left origin: the top edge comes first"


def test_coordinates_are_flipped_not_copied() -> None:
    """Zotero measures from the bottom of the page and we measure from the
    top. Copying the rect through would land a plausible crop on the wrong
    part of the page, which no later check would catch."""
    a = next(x for x in annotations() if x.key == "PA9M3ZIA")
    height = 841.89
    bbox = a.bbox(height)
    assert bbox is not None
    zotero_top = max(r[3] for r in a.rects)
    assert round(bbox[1], 2) == round(height - zotero_top, 2)


def test_a_note_says_what_the_reader_said() -> None:
    """A sticky note covers no text; its rect is where the pin sits and the
    comment is the whole of it."""
    note = next(x for x in annotations() if x.kind == "note")
    assert note.text == ""
    assert note.content == note.comment


def test_colours_are_named() -> None:
    a = next(x for x in annotations() if x.key == "PA9M3ZIA")
    assert a.colour == "#e56eee"
    assert a.colour_name == "magenta"


def test_page_is_one_based_like_every_other_page_here() -> None:
    a = next(x for x in annotations() if x.key == "PA9M3ZIA")
    assert a.page_index == 7
    assert a.page == 8, "`locator.page` and `render` both count from one"


# -- a unit is a mark you named, with the pages around it -------------------


def attachment() -> Attachment:
    return Attachment(key="ZIETASLD", parent="VFD2E2BR", title="PDF", filename="p.pdf")


def zcfg(*units_from: str, meanings: dict[str, str] | None = None) -> ZoteroConfig:
    return ZoteroConfig(
        data_dir=Path("/nowhere"),
        units_from=frozenset(units_from),
        meanings=meanings or {},
    )


def on_pdf() -> list[Annotation]:
    return [a for a in annotations() if a.document == "ZIETASLD"]


HEIGHTS = {p: 841.89 for p in range(1, 40)}


def test_only_the_colours_you_named_make_units() -> None:
    """The tool has no opinion about what a colour means. It reads the ones you
    declared and leaves the rest as context."""
    marks = on_pdf()
    kinds = {a.kind for a in marks}
    assert "note" in kinds and "highlight" in kinds

    units = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note"))

    assert len(units) == 1, "one note among them"
    assert units[0].id.endswith(units[0].marks[0].key), "named after its own mark"


def test_any_colour_can_be_the_one_that_counts() -> None:
    """Nothing privileges a particular colour. Declaring a different one moves
    which marks are units and changes nothing else."""
    marks = on_pdf()
    notes = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note"))
    magenta = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("magenta"))

    assert {u.id for u in notes} & {u.id for u in magenta} == set()
    assert notes and magenta


def test_nothing_declared_means_no_units() -> None:
    """Silence rather than a guess: if no colour is named, nothing is a card."""
    assert units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg()) == []


def test_the_unit_is_named_after_its_mark_not_its_place() -> None:
    """Zotero's key is permanent and never derived from a position, which is
    what makes marking up more of a document renumber nothing."""
    marks = on_pdf()
    before = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note"))
    extra = Annotation(
        key="NEWKEY00",
        document="ZIETASLD",
        kind="highlight",
        colour="#5fb236",
        page_index=7,
        rects=[[100.0, 500.0, 200.0, 515.0]],
        sort_index="00007|000100|00100",  # sorts first, mid-document
    )
    after = units_for("wegel", attachment(), [*marks, extra], HEIGHTS, zcfg("note"))

    assert [u.id for u in before] == [u.id for u in after], "no id moved"


def test_context_is_the_pages_around_it() -> None:
    """Not a curated set of marks. An idea runs across a page break, so the
    window is pages either side and the reader judges what is relevant."""
    near = Annotation(
        key="NEARBY01", document="ZIETASLD", kind="highlight", colour="#a28ae5",
        page_index=8, rects=[[10.0, 10.0, 20.0, 20.0]], sort_index="00008|000001|00001",
    )
    far = Annotation(
        key="FARAWAY1", document="ZIETASLD", kind="highlight", colour="#a28ae5",
        page_index=30, rects=[[10.0, 10.0, 20.0, 20.0]], sort_index="00030|000001|00001",
    )
    unit = units_for("wegel", attachment(), [*on_pdf(), near, far], HEIGHTS, zcfg("note"))[0]

    keys = {m.key for m in unit.marks}
    assert "NEARBY01" in keys, "the next page comes along"
    assert "FARAWAY1" not in keys, "a page twenty away does not"


def test_a_mark_can_sit_beside_two_units() -> None:
    """Context is a view, not content. Owning it exclusively would mean the
    tool deciding which unit a term belongs to."""
    marks = on_pdf()
    units = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note", "magenta"))
    assert len(units) > 1

    seen = [m.key for u in units for m in u.marks]
    assert len(seen) > len(set(seen)), "shared, not partitioned"


def test_the_window_is_adjustable() -> None:
    """Triage wants to stay readable; a pass that writes cards wants more."""
    far = Annotation(
        key="FARAWAY1", document="ZIETASLD", kind="highlight", colour="#a28ae5",
        page_index=10, rects=[[10.0, 10.0, 20.0, 20.0]], sort_index="00010|000001|00001",
    )
    rows = [*on_pdf(), far]
    tight = units_for("w", attachment(), rows, HEIGHTS, zcfg("note"), neighbourhood=1)[0]
    wide = units_for("w", attachment(), rows, HEIGHTS, zcfg("note"), neighbourhood=5)[0]

    assert "FARAWAY1" not in {m.key for m in tight.marks}
    assert "FARAWAY1" in {m.key for m in wide.marks}


def test_marks_are_in_reading_order() -> None:
    unit = units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg("note"))[0]
    rest = [m.order for m in unit.marks[1:]]
    assert rest == sorted(rest)


def test_naming_another_colour_splits_without_renaming_anything() -> None:
    """Split and merge are the same operation: which colours make units. Name
    one more and another unit appears, called after its own mark, with the
    first left exactly as it was."""
    marks = on_pdf()
    one = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note"))
    two = units_for("wegel", attachment(), marks, HEIGHTS, zcfg("note", "magenta"))

    assert len(two) > len(one)
    assert {u.id for u in one} <= {u.id for u in two}, "the first survives unchanged"


def test_the_unit_box_is_its_own_mark_not_the_whole_page() -> None:
    """What is around it is shown by rendering with context, not by widening
    the unit to cover things the card is not about."""
    unit = units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg("note"))[0]
    assert unit.locator.bbox == unit.marks[0].bbox


def test_a_marked_page_arrives_new() -> None:
    """Marking says "this mattered while I was reading"; triage says "this is
    worth a card on its own". They are different questions, and arriving
    `queued` answered the second one on the reader's behalf -- which let an
    import fill the card queue with no gate in between."""
    unit = units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg("note"))[0]
    assert unit.state == "new"


def test_the_document_is_on_the_locator_not_in_the_name() -> None:
    """An item is routinely several documents, and page 17 of a book's first
    chapter is not page 17 of its third. A unit that gets re-filed should not
    have to be renamed, so the document lives on the locator."""
    assert unit_id("wain", "LLWYVJPR") == "wain:LLWYVJPR"
    unit = units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg("note"))[0]
    assert unit.locator.document == "ZIETASLD"


def test_a_mark_records_zotero_not_your_scheme() -> None:
    """What a colour means is resolved wherever a mark is displayed, never
    frozen into the ledger. Editing your scheme has to change every unit at
    once, not only the ones imported since."""
    unit = units_for("wegel", attachment(), on_pdf(), HEIGHTS, zcfg("note"))[0]
    assert not hasattr(unit.marks[0], "meaning")
    assert {m.colour for m in unit.marks} <= set(COLOURS.values()) | {""}


def test_a_unit_with_no_marks_writes_no_marks_key() -> None:
    """The 751 Cookbook units must not grow a field they have no use for."""
    assert "marks" not in Unit(id="demo:2.4:61").to_json()


# -- the whole item ---------------------------------------------------------


def test_naming_no_colours_is_refused_loudly() -> None:
    """Importing everything, or nothing, silently would both be wrong."""
    report = build(FakeZotero({}), Item(key="X"), source="x", zotero=zcfg())
    assert not report.ok
    assert "units_from" in report.skipped[0]


def test_unmapped_colours_are_reported_not_guessed() -> None:
    """Same rule as an Anki flag with no meaning: a guess about your own scheme
    would be invisible by the time it reached a card."""
    client = FakeZotero(
        {
            "/api/users/0/items/VFD2E2BR/children": load("children-wegel.json"),
            "/api/users/0/items?itemType=annotation": load("annotations.json"),
        }
    )
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(client, item, source="wegel", zotero=zcfg("note", meanings={"note": "mine"}))
    assert any(name.startswith("highlight/") for name in report.unmapped)


def test_a_missing_pdf_is_reported_not_invented() -> None:
    """Without the file there is no page height, so there is no honest bbox.
    Guessing Letter or A4 would be right most of the time and silently wrong on
    the rest."""
    client = FakeZotero(
        {
            "/api/users/0/items/VFD2E2BR/children": load("children-wegel.json"),
            "/api/users/0/items?itemType=annotation": load("annotations.json"),
        }
    )
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(client, item, source="wegel", zotero=zcfg("note"))

    assert not report.ok
    assert report.units == []
    assert any("missing" in s for s in report.skipped)


def test_an_item_with_no_pdf_is_skipped_with_a_reason() -> None:
    client = FakeZotero({"/api/users/0/items/X/children": []})
    report = build(client, Item(key="X", title="A Web Page"), source="x", zotero=zcfg("note"))
    assert not report.ok
    assert "no PDF attachments" in report.skipped[0]


# -- the source file an import writes ---------------------------------------


def test_the_import_gives_a_new_source_its_own_file(tmp_path: Path) -> None:
    """Without one the units exist and the source does not: nothing can resolve
    its deck or its conventions."""
    path = tmp_path / "wegel" / "source.toml"
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]

    assert write_source_stub(path, item) is True
    text = path.read_text(encoding="utf-8")
    assert f'zotero = "{item.key}"' in text
    assert "+++" not in text, "plain TOML, not fenced frontmatter"


def test_the_import_writes_no_placeholder_conventions(tmp_path: Path) -> None:
    """An empty file saying "nothing recorded yet" is indistinguishable from a
    real one to everything that reads it, and `forge context` would stop
    telling a card writer that nobody has written down what is ambient here."""
    folder = tmp_path / "wegel"
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    write_source_stub(folder / "source.toml", item)
    assert not (folder / "conventions.md").exists()


def test_the_stub_never_overwrites(tmp_path: Path) -> None:
    """Everything in it is a starting point you will edit, and a re-import must
    not undo that."""
    path = tmp_path / "wegel" / "source.md"
    path.parent.mkdir(parents=True)
    path.write_text("+++\ntitle = \"Mine\"\n+++\n", encoding="utf-8")

    assert write_source_stub(path, Item(key="X", title="Theirs")) is False
    assert "Mine" in path.read_text(encoding="utf-8")


# -- which of an item's PDFs to read ----------------------------------------


def wegel_client() -> FakeZotero:
    return FakeZotero(
        {
            "/api/users/0/items/VFD2E2BR/children": load("children-wegel.json"),
            "/api/users/0/items?itemType=annotation": load("annotations.json"),
        }
    )


def test_every_pdf_on_the_item_is_reported_every_run() -> None:
    """You cannot choose between attachments you have never been shown. This
    item carries the paper twice -- `PDF` and `MOL_appendix.pdf` -- and reading
    both silently imported every mark against the wrong page numbers."""
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(wegel_client(), item, source="wegel", zotero=zcfg("note"))
    assert {title for _, title, _ in report.attachments} == {"PDF", "MOL_appendix.pdf"}
    assert all(taken for _, _, taken in report.attachments), "empty `documents` is all of them"


def test_documents_selects_by_title() -> None:
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(
        wegel_client(), item, source="wegel", zotero=zcfg("note"), documents=("PDF",)
    )
    taken = {title for _, title, keep in report.attachments if keep}
    assert taken == {"PDF"}
    assert report.excluded == {"VX8CZN3W"}


def test_documents_selects_by_key_too() -> None:
    """Both are things you can see: the title is what Zotero shows and the key
    is what the ledger records."""
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(
        wegel_client(), item, source="wegel", zotero=zcfg("note"), documents=("ZIETASLD",)
    )
    assert {title for _, title, keep in report.attachments if keep} == {"PDF"}


def test_naming_an_attachment_that_is_not_there_is_refused_loudly() -> None:
    """Silently importing nothing looks exactly like a document with no marks
    in it, which is a real state and not this one."""
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    report = build(
        wegel_client(), item, source="wegel", zotero=zcfg("note"), documents=("appendix",)
    )
    assert not report.ok
    assert "matches none of its attachments" in report.skipped[0]
    assert "MOL_appendix.pdf" in report.skipped[0], "and says what there was to choose from"


def test_the_stub_carries_your_tags_and_invents_none(tmp_path: Path) -> None:
    """A label the tool made up would mean whatever the tool guessed. A tag on
    the Zotero item is one you put there, so it comes across: `demo`, the one
    tag this repo reads, is then set where you would think to set it."""
    path = tmp_path / "wegel" / "source.md"
    item = Item.from_json(load("item-wegel.json"))  # type: ignore[arg-type]
    write_source_stub(path, item)
    text = path.read_text(encoding="utf-8")
    assert '"anki"' in text and '"Statistics - Machine Learning"' in text
    assert "documents = []" in text


def test_the_stub_has_no_tags_when_the_item_has_none(tmp_path: Path) -> None:
    path = tmp_path / "bare" / "source.toml"
    write_source_stub(path, Item(key="X", title="Bare"))
    assert "tags = []" in path.read_text(encoding="utf-8")
