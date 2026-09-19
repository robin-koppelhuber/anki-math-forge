"""A card that carries a picture.

The picture is a **unit**, not a file. Invariant 3: extraction produces
geometry, never image files, so a card names a unit and the crop is rendered
from the source document on the way to Anki. That keeps it reproducible, keeps
binaries out of git, and makes a re-segmentation fix every card that shows it.

Where the picture goes is the writer's call, so nothing here has an opinion
about which section it lands in -- only that every section which reaches Anki
can hold one, and that `## notes` and `## verify`, which do not, cannot.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anki_math_forge import check, model, sync
from anki_math_forge.app import create_app
from anki_math_forge.config import Config
from anki_math_forge.extract import run as extract_run
from anki_math_forge.ledger import Ledger
from conftest import FakeAnki

HEAD = """---
uid: {uid}
type: identity
status: {status}
source: "A Book"
unit: "{unit}"
tags: []
verify: false
---
"""


def write(
    config: Config,
    body: str,
    *,
    uid: str = "aa11bb",
    unit: str = "book:1:1",
    status: str = "draft",
    name: str = "picture.md",
) -> Path:
    path = config.cards_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEAD.format(uid=uid, status=status, unit=unit) + body, encoding="utf-8")
    return path


def a_unit(config: Config) -> str:
    """Extract the PDF source and hand back a unit that has geometry."""
    extract_run(config, "book")
    return next(iter(Ledger.load(config.units_path("book")))).id


# -- what the card says -----------------------------------------------------


def test_the_bare_form_means_the_unit_the_card_came_from() -> None:
    """Which the frontmatter already says. Repeating it in the body is a
    second copy to keep in step."""
    card = model.parse(HEAD.format(uid="aa11bb", status="draft", unit="book:2:7"))
    card.set_section("front", "what is this")
    card.set_section("back", "![the figure](unit)")

    found = card.images()

    assert [(i.unit, i.alt, i.section) for i in found] == [
        ("book:2:7", "the figure", "back")
    ]


def test_it_can_name_another_unit_and_be_anywhere_that_reaches_anki() -> None:
    """The writer decides where a picture belongs: a figure that *is* the
    answer goes in `## back`, one you are asked to read goes in `## front`,
    one supporting an explanation goes in `## prose`."""
    card = model.parse(HEAD.format(uid="aa11bb", status="draft", unit="book:2:7"))
    card.set_section("front", "![what is happening here](unit:book:9:1)")
    card.set_section("back", "the marginal")
    card.set_section("prose", "compare ![the prior](unit:book:8:4)")

    found = card.images()

    assert [i.unit for i in found] == ["book:9:1", "book:8:4"]
    assert [i.section for i in found] == ["front", "prose"]
    # The slot is what the media name is built from, so it counts across the
    # whole card and not within a section.
    assert [i.index for i in found] == [0, 1]


def test_a_picture_in_notes_or_verify_is_not_one() -> None:
    """Neither reaches Anki, so an image in either is one nobody sees."""
    card = model.parse(HEAD.format(uid="aa11bb", status="draft", unit="book:2:7"))
    card.set_section("front", "a")
    card.set_section("back", "b")
    card.set_section("notes", "@me maybe ![this](unit) belongs on the back")

    assert card.images() == []
    assert not card.has_image


def test_swapping_the_picture_un_approves_the_card() -> None:
    """It is content. `## front` and every other rendered section is inside
    `content_hash`, so this comes for free -- which is the reason the
    reference lives in the body rather than in the frontmatter."""
    card = model.parse(HEAD.format(uid="aa11bb", status="approved", unit="book:2:7"))
    card.set_section("front", "what is this")
    card.set_section("back", "![the figure](unit)")
    card.approve()

    card.set_section("back", "![the figure](unit:book:9:9)")

    assert card.effective_status == "draft"
    assert card.demotion == "edited"


# -- what `check` refuses ---------------------------------------------------


def codes(config: Config) -> set[str]:
    return {f.code for f in check.check_repo(config)[1]}


def test_a_picture_that_can_be_drawn_is_clean(pdf_source: Config) -> None:
    unit = a_unit(pdf_source)
    write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")

    assert not {c for c in codes(pdf_source) if c.startswith("image-")}


def test_a_unit_that_is_not_there_is_refused(pdf_source: Config) -> None:
    """Invariant 1 applied to media: a card whose picture cannot be rendered
    is refused rather than pushed to Anki as a broken image icon."""
    a_unit(pdf_source)
    write(pdf_source, "\n## front\n$a$\n\n## back\n![the figure](unit:book:404:1)\n")

    assert "image-unit-unknown" in codes(pdf_source)


def test_a_unit_with_no_geometry_is_refused(config: Config) -> None:
    """A `.tex` source has geometry for nothing, so there is no box to crop."""
    extract_run(config, "demo")
    unit = next(iter(Ledger.load(config.units_path("demo")))).id
    write(config, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")

    assert "image-no-geometry" in codes(config)


def test_a_missing_document_is_refused(pdf_source: Config) -> None:
    """The crop is rendered from the PDF at sync, so the PDF has to be here.
    It is the failure that arrives long after the card was written."""
    unit = a_unit(pdf_source)
    write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")
    (pdf_source.root / "sources" / "book" / "book.pdf").unlink()

    assert "image-document-missing" in codes(pdf_source)


def test_a_bare_reference_on_a_card_with_no_unit_is_refused(pdf_source: Config) -> None:
    a_unit(pdf_source)
    path = write(pdf_source, "\n## front\n$a$\n\n## back\n![the figure](unit)\n")
    path.write_text(
        path.read_text(encoding="utf-8").replace('unit: "book:1:1"\n', ""), encoding="utf-8"
    )

    assert "image-unresolved" in codes(pdf_source)


# -- what Anki is handed ----------------------------------------------------


def test_the_field_carries_an_img_naming_the_card_and_the_slot(pdf_source: Config) -> None:
    """One deterministic name per card and slot, so a re-sync overwrites the
    file it wrote last time instead of leaving an orphan behind."""
    unit = a_unit(pdf_source)
    card = model.load(
        write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")
    )

    fields = sync.fields_for(card, pdf_source)

    assert fields["Back"] == '<img src="forge-aa11bb-0.png" alt="the figure">'
    assert sync.media_name(card, card.images()[0]) == "forge-aa11bb-0.png"


def test_the_alt_text_is_escaped_and_the_reference_still_matched(
    pdf_source: Config,
) -> None:
    """`to_anki_html` escapes the prose it finds the reference in, so the
    rewrite has to look for the escaped spelling."""
    unit = a_unit(pdf_source)
    card = model.load(
        write(pdf_source, f"\n## front\n$a$\n\n## back\n![A < B & more](unit:{unit})\n")
    )

    back = sync.fields_for(card, pdf_source)["Back"]

    assert back.startswith("<img src=")
    assert "&lt;" in back and "&amp;" in back
    assert "![" not in back


def test_maths_beside_a_picture_still_becomes_mathjax(pdf_source: Config) -> None:
    unit = a_unit(pdf_source)
    card = model.load(
        write(pdf_source, f"\n## front\n$a$\n\n## back\n$X^2$ and ![it](unit:{unit})\n")
    )

    back = sync.fields_for(card, pdf_source)["Back"]

    assert "\\(X^2\\)" in back and "<img src=" in back


def test_sync_uploads_the_picture_before_the_note(pdf_source: Config) -> None:
    unit = a_unit(pdf_source)
    path = write(
        pdf_source,
        f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n",
        status="draft",
    )
    card = model.load(path)
    card.approve()
    card.save()
    client = FakeAnki()

    report = sync.run(pdf_source, client=client, dry_run=False)

    assert not check.errors(report.findings), report.findings
    assert "forge-aa11bb-0.png" in client.media
    assert client.calls.index("storeMediaFile") < client.calls.index("addNote")
    # A PNG, not a promise of one.
    from base64 import b64decode

    assert b64decode(client.media["forge-aa11bb-0.png"])[:4] == b"\x89PNG"


def test_a_rehearsal_writes_nothing_to_the_media_folder(pdf_source: Config) -> None:
    """`--dry-run` must not write a picture any more than it writes a note."""
    unit = a_unit(pdf_source)
    card = model.load(
        write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")
    )
    card.approve()
    card.save()
    client = FakeAnki()

    sync.run(pdf_source, client=client, dry_run=True)

    assert client.media == {}
    assert "storeMediaFile" not in client.calls


def test_a_drawn_box_is_cropped_to_itself(pdf_source: Config) -> None:
    """Invariant 8 widens a *mark's* crop to the page, because a highlight's
    edges are wherever a sentence started and stopped. A box somebody dragged
    around a figure means exactly what it says, and widening it would hand
    over the paragraph beside the figure too."""
    a_unit(pdf_source)
    path = pdf_source.units_path("book")
    with Ledger.edit(path) as ledger:
        unit = next(iter(ledger))
        unit.marks = [
            model_mark(unit.id, "image"),
        ]
    unit = Ledger.load(path).get(unit.id)
    assert unit.drawn_box and not unit.crops_to_page

    with Ledger.edit(path) as ledger:
        ledger.get(unit.id).marks = [model_mark(unit.id, "highlight")]
    widened = Ledger.load(path).get(unit.id)
    assert not widened.drawn_box and widened.crops_to_page


def model_mark(unit_id: str, kind: str, bbox=None, page=None):  # type: ignore[no-untyped-def]
    from anki_math_forge.ledger import Mark

    return Mark(key=unit_id.split(":")[-1], kind=kind, colour="yellow", bbox=bbox, page=page)


# -- what the app shows -----------------------------------------------------


def test_the_review_view_draws_the_picture(pdf_source: Config) -> None:
    """Rendered per request from the same geometry `sync` will use: what you
    approve on screen is what Anki gets."""
    unit = a_unit(pdf_source)
    write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")

    body = TestClient(create_app(pdf_source)).get("/review?source=book&status=draft").text

    assert 'class="card-image"' in body
    assert "/crop/book/" in body
    assert "![the figure]" not in body, "the reference itself should not be on screen"


def test_a_card_with_a_picture_says_so(pdf_source: Config) -> None:
    """A label, not a filter: it says what you are looking at while you look
    at it, and nobody works through the pile of cards that have one."""
    unit = a_unit(pdf_source)
    write(pdf_source, f"\n## front\n$a$\n\n## back\n![the figure](unit:{unit})\n")
    write(pdf_source, "\n## front\n$a$\n\n## back\n$b$\n", uid="bb22cc", name="plain.md")

    body = TestClient(create_app(pdf_source)).get("/review?source=book&status=draft").text

    assert body.count('class="badge image"') == 1


# -- the frame round the figure ---------------------------------------------


def test_the_card_picture_has_no_mark_painted_on_it(pdf_source: Config) -> None:
    """`regions_for` paints a unit's mark back onto its crop, and for an image
    mark that mark *is* the boundary: what gets drawn is a rectangle round the
    whole picture, in the colour you marked it with. Triage wants that, and it
    is the yellow border on a card."""
    from anki_math_forge.extract import render as render_mod

    a_unit(pdf_source)
    path = pdf_source.units_path("book")
    with Ledger.edit(path) as ledger:
        unit = next(iter(ledger))
        unit.marks = [model_mark(unit.id, "image", bbox=unit.locator.bbox, page=unit.locator.page)]
    unit = Ledger.load(path).get(unit.id)
    document = pdf_source.document_for("book", unit.locator.document)

    framed = render_mod.render_crop(
        document, *unit.crop_geometry(), width="box",
        regions=render_mod.regions_for(unit, unit.locator.page),
    )
    plain = render_mod.render_crop(
        document, *unit.crop_geometry(), width="box",
        context=-render_mod.CARD_INSET,
    )

    assert framed != plain
    assert render_mod.regions_for(unit, unit.locator.page), "triage does paint it"


def test_a_negative_context_pulls_the_crop_in(pdf_source: Config) -> None:
    """Which is how the stroke of a rectangle stored *inside* the PDF, by a
    reader whose annotations are written back to the file, is missed. Nothing
    here can switch that one off."""
    from anki_math_forge.extract import render as render_mod

    a_unit(pdf_source)
    unit = next(iter(Ledger.load(pdf_source.units_path("book"))))
    document = pdf_source.document_for("book", unit.locator.document)

    def size(context: float) -> tuple[int, int]:
        png = render_mod.render_crop(
            document, *unit.crop_geometry(), width="box", context=context
        )
        # PNG header: width and height as big-endian 32-bit ints at byte 16.
        return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")

    flush = size(0)
    inset = size(-render_mod.CARD_INSET)

    assert inset[0] < flush[0] and inset[1] < flush[1]
    # A trim, not a reframing: a few points at the render zoom.
    assert flush[0] - inset[0] <= 2 * render_mod.CARD_INSET * render_mod.RENDER_ZOOM + 2


def test_a_small_box_is_not_inset_to_nothing(pdf_source: Config) -> None:
    """A fixed inset on a box a few points across would leave no picture at
    all, and a card showing a 2px sliver is worse than one showing a border."""
    from anki_math_forge.extract import render as render_mod

    a_unit(pdf_source)
    unit = next(iter(Ledger.load(pdf_source.units_path("book"))))
    document = pdf_source.document_for("book", unit.locator.document)
    x0, y0 = unit.locator.bbox[0], unit.locator.bbox[1]
    tiny = [x0, y0, x0 + 6, y0 + 6]

    png = render_mod.render_crop(document, unit.locator.page, tiny, width="box", context=-20)

    width = int.from_bytes(png[16:20], "big")
    assert width > 0, "a box inset past itself renders nothing"


def test_the_app_asks_for_the_picture_sync_will_render(pdf_source: Config) -> None:
    """What you approve on screen has to be what Anki gets: same width rule,
    same inset, and the mark painted on neither."""
    from anki_math_forge.app import render_body
    from anki_math_forge.extract import render as render_mod

    unit = a_unit(pdf_source)

    tag = str(render_body(f"![the figure](unit:{unit})"))

    assert "marks=false" in tag
    assert f"context=-{render_mod.CARD_INSET:g}" in tag
    assert "width=" not in tag, "the config decides that, the same way for both"
