"""A unit id has more than one shape, and the tool must not assume otherwise.

    matrix-cookbook:2.3:66    a segmenter working from a numbered book
    wegel...:LDHUSBDM         a mark imported from a PDF somebody read

Every fixture in this suite used to be the first shape, which is how two bugs
reached a real collection: the `src::` tag meant to suspend a batch wholesale
named exactly one note, and the review view's section rail listed one section
per card. Both read the middle segment of an id that has no middle.
"""

from __future__ import annotations

from anki_math_forge import model, sync
from anki_math_forge.config import Config

MARKED = "wegelSampleComplexitySemisupervised2025:LDHUSBDM"
NUMBERED = "matrix-cookbook:2.3:66"


def a_card(unit: str) -> model.Card:
    return model.stub(uid="aaaaaa", front="$x$", back="$y$", source="A Source", unit=unit)


def test_a_marked_unit_has_no_section(config: Config) -> None:
    """Two segments means there is nothing to derive. Reading the middle one
    returned the annotation key, so every card got its own "section"."""
    assert a_card(MARKED).section_name == ""
    assert a_card(NUMBERED).section_name == "2.3"


def test_the_src_tag_names_a_batch_not_a_card(config: Config) -> None:
    """The only thing this tag is for is suspending a bad batch wholesale. One
    unique tag per card defeats that and fills the collection with them."""
    marked = [t for t in sync.tags_for(a_card(MARKED), config) if t.startswith("src::")]
    assert marked == ["src::wegelSampleComplexitySemisupervised2025"]

    numbered = [t for t in sync.tags_for(a_card(NUMBERED), config) if t.startswith("src::")]
    assert numbered == ["src::matrix-cookbook::2.3"], "a numbered source keeps its section"


def test_the_source_is_read_the_same_way_from_both(config: Config) -> None:
    """`project_name` is the first segment whatever follows it, and everything
    per-source resolves off that: deck, layout, conventions."""
    assert a_card(MARKED).project_name == "wegelSampleComplexitySemisupervised2025"
    assert a_card(NUMBERED).project_name == "matrix-cookbook"


def test_a_marked_card_still_syncs(config: Config) -> None:
    """The whole point: a card on a two-segment unit is an ordinary card."""
    card = a_card(MARKED)
    tags = sync.tags_for(card, config)
    assert config.tag_prefix in tags
    assert all(tag.strip() and " " not in tag for tag in tags)
