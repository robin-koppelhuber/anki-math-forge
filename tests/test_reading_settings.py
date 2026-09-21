"""What a project reads, and how much of it a card writer is handed.

Four settings that used to be one derived fact each: whether units come
out of a work, where its cached text lives, whether a reference reaches
the writer, and which ask reads it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import context, projects
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError
from anki_math_forge.extract import source_text_path


def a_repo(tmp_path: Path, sources: str = "", *, cards: str = "") -> Config:
    tmp_path.mkdir(parents=True, exist_ok=True)
    # A repo-wide scheme, so there is something to inherit and something
    # for the editor to offer before the first import.
    (tmp_path / "forge.toml").write_text(
        f'[repo]\nname = "x"\n\n[cards]\n{cards}\n\n'
        '[zotero]\nunits_from = ["highlight/green", "note/yellow"]\n\n'
        '[zotero.meanings]\n"highlight/green" = "a claim"\n'
        '"note/yellow" = "a thought"\n"highlight/purple" = "a term"\n',
        encoding="utf-8",
    )
    (tmp_path / "cards").mkdir()
    folder = tmp_path / "projects" / "cpp"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text(
        f'title = "C++"\n\n# a comment that survives\n{sources}', encoding="utf-8"
    )
    return config_mod.load(tmp_path)


MARKED = '[[sources]]\nzotero = "ZOT1"\ntitle = "A tour"\n'
SHELF = (
    '[[sources]]\nkey = "cppref"\ntitle = "cppreference"\n'
    'url = "https://en.cppreference.com/w/cpp"\nnote = "the tables"\n\n'
    '[[sources]]\nkey = "draft"\ntitle = "the working draft"\n'
    'url = "https://eel.is/c++draft"\nnote = "the wording"\n'
)


def units(config: Config, *rows: dict[str, object]) -> None:
    config.units_path("cpp").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _units(config: Config) -> list[object]:
    from anki_math_forge.ledger import Ledger

    return list(Ledger.load(config.units_path("cpp")))


def a_unit(uid: str, colour: str, *, state: str = "new") -> dict[str, object]:
    return {
        "id": f"cpp:{uid}",
        "state": state,
        "locator": {"document": "ATT1", "page": 1},
        "marks": [{"key": uid, "kind": "highlight", "colour": colour,
                   "bbox": [0, 0, 1, 1]}],
    }


# -- authoritative is a property you can set --------------------------------


def test_a_zotero_work_can_be_authoritative_nowhere(tmp_path: Path) -> None:
    """You own a marked-up paper, you want it cited and checked against,
    and you want none of its highlights in your ledger."""
    config = a_repo(tmp_path, MARKED + "extract = false\n")

    work = config.project("cpp").source("ZOT1")

    assert work is not None
    assert work.zotero_key == "ZOT1"
    assert not work.authoritative
    assert work in config.references_for("cpp"), "and it is on the shelf instead"


def test_turning_it_off_keeps_the_units_it_already_has(tmp_path: Path) -> None:
    """It says stop making units out of this, not that the ones you have
    are wrong: their document is still declared and their crops still
    render. Deleting them made the switch destroy work in one direction
    and do nothing in the other."""
    config = a_repo(tmp_path, MARKED)
    units(config, a_unit("a1", "green"), a_unit("b2", "green", state="queued"))
    client = TestClient(create_app(config))

    answer = client.post("/api/sources/cpp/ZOT1/extract", json={"extract": False})

    assert answer.json() == {"ok": True, "extract": False}
    left = config.units_path("cpp").read_text(encoding="utf-8")
    assert "cpp:a1" in left and "cpp:b2" in left
    assert not config_mod.load(tmp_path).project("cpp").source("ZOT1").authoritative


def test_the_switch_goes_both_ways(tmp_path: Path) -> None:
    """Off and on again leaves the ledger exactly as it was."""
    config = a_repo(tmp_path, MARKED)
    # Both a pair the scheme makes units out of, so the scheme rule has
    # nothing to say and the file should not be touched at all.
    units(config, a_unit("a1", "green"), a_unit("b2", "green", state="queued"))
    before = config.units_path("cpp").read_text(encoding="utf-8")
    client = TestClient(create_app(config))

    client.post("/api/sources/cpp/ZOT1/extract", json={"extract": False})
    client.post("/api/sources/cpp/ZOT1/extract", json={"extract": True})

    assert config.units_path("cpp").read_text(encoding="utf-8") == before
    assert config_mod.load(tmp_path).project("cpp").source("ZOT1").authoritative


def test_turning_it_back_on_is_one_click(tmp_path: Path) -> None:
    config = a_repo(tmp_path, MARKED + "extract = false\n")
    client = TestClient(create_app(config))

    assert client.post("/api/sources/cpp/ZOT1/extract", json={"extract": True}).status_code == 200

    reread = config_mod.load(tmp_path)
    assert reread.project("cpp").source("ZOT1").authoritative
    text = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "extract" not in text, "nobody said is the ordinary state"
    assert "# a comment that survives" in text


def test_a_reference_cannot_be_switched_on(tmp_path: Path) -> None:
    """There would be nothing to segment. The honest way to make something
    authoritative is to give it a document."""
    config = a_repo(tmp_path, SHELF)

    answer = TestClient(create_app(config)).post(
        "/api/sources/cpp/cppref/extract", json={"extract": True}
    )

    assert answer.status_code == 400
    assert "no document to segment" in answer.json()["detail"]


# -- the marking scheme reaches the ledger ---------------------------------


def test_unchecking_a_colour_forgets_its_untouched_units(tmp_path: Path) -> None:
    """They used to stay, as full units, in every count and every pass."""
    config = a_repo(tmp_path, MARKED)
    units(config, a_unit("a1", "green"), a_unit("b2", "purple"))
    client = TestClient(create_app(config))

    answer = client.post(
        "/api/scheme/cpp/ZOT1",
        json={"meanings": {}, "units_from": ["highlight/green"]},
    )

    assert answer.json()["dropped"] == 1
    left = config.units_path("cpp").read_text(encoding="utf-8")
    assert "cpp:a1" in left and "cpp:b2" not in left


# -- the text goes where the extraction is ----------------------------------


def test_the_cached_text_lives_with_the_project_that_extracts(tmp_path: Path) -> None:
    """A work is authoritative in at most one project, so its text has one
    home. Cached under whichever project ran the import, two projects
    citing one paper is two copies with nothing saying which is current."""
    a_repo(tmp_path, MARKED + 'attachments = ["ATT1"]\n')
    (tmp_path / "projects" / "other").mkdir()
    (tmp_path / "projects" / "other" / "project.toml").write_text(
        'title = "Other"\n\n[[sources]]\nzotero = "ZOT1"\nextract = false\n',
        encoding="utf-8",
    )
    config = config_mod.load(tmp_path)

    assert config.extracting("ATT1") == "cpp"
    for asked in ("cpp", "other"):
        assert source_text_path(config, asked, "ATT1").parent.name == "cpp"


def test_a_document_nobody_extracts_from_stays_where_it_was_asked(
    tmp_path: Path,
) -> None:
    config = a_repo(tmp_path, SHELF)

    assert config.extracting("ATT1") == ""
    assert source_text_path(config, "cpp", "ATT1").parent.name == "cpp"


# -- how much a writer is handed --------------------------------------------


def test_three_levels_not_two(tmp_path: Path) -> None:
    for word, expected in (("none", "none"), ("references", "references"), ("web", "web")):
        config = a_repo(tmp_path / word, SHELF, cards=f'context = "{word}"')
        assert config.context_for("cpp") == expected
        assert config.web_for("cpp") is (expected == "web")


def test_the_old_web_key_still_says_what_it_said(tmp_path: Path) -> None:
    """`web = true` is the web; `web = false` says no more than that the
    web is off, which is the middle setting and not the strict one."""
    assert a_repo(tmp_path / "a", cards="web = true").context_for("cpp") == "web"
    assert a_repo(tmp_path / "b", cards="web = false").context_for("cpp") == "references"
    assert a_repo(tmp_path / "c").context_for("cpp") == "references"


def test_a_unit_still_overrides_the_level(tmp_path: Path) -> None:
    """The per-unit grant is the exception the whole permission exists
    for: you grant it where you can see this one unit needs it."""
    config = a_repo(tmp_path, SHELF, cards='context = "references"')

    assert config.context_for("cpp", True) == "web"
    assert config.context_for("cpp", None) == "references"
    # And a refusal on a project that allows the web keeps the shelf.
    wider = a_repo(tmp_path / "w", SHELF, cards='context = "web"')
    assert wider.context_for("cpp", False) == "references"


def test_a_bad_level_is_refused_at_load(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not one of"):
        a_repo(tmp_path, cards='context = "everything"')


# -- which references reach the writer --------------------------------------


def test_a_reference_can_be_kept_off_the_shelf(tmp_path: Path) -> None:
    """Six places to look is a reading list nobody works through. Off, it
    stays declared, cited and findable."""
    config = a_repo(tmp_path, SHELF.replace('note = "the wording"', 'offer = false'))

    handed = config.references_for("cpp")

    assert [w.key for w in handed] == ["cppref"]
    assert "eel.is" not in context.shelf(config, "cpp")
    assert config.project("cpp").source("draft") is not None, "still declared"


def test_the_project_sets_the_default_and_a_source_overrides_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "forge.toml").write_text('[repo]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "cards").mkdir()
    (tmp_path / "projects" / "cpp").mkdir(parents=True)
    (tmp_path / "projects" / "cpp" / "project.toml").write_text(
        f'title = "C++"\noffer = false\n\n{SHELF}'.replace(
            'note = "the wording"', "offer = true"
        ),
        encoding="utf-8",
    )
    config = config_mod.load(tmp_path)

    assert [w.key for w in config.references_for("cpp")] == ["draft"]


def test_the_switch_writes_it_down(tmp_path: Path) -> None:
    config = a_repo(tmp_path, SHELF)

    answer = TestClient(create_app(config)).post(
        "/api/sources/cpp/draft/offer", json={"offer": False}
    )
    assert answer.status_code == 200

    reread = config_mod.load(tmp_path)
    assert [w.key for w in reread.references_for("cpp")] == ["cppref"]
    assert "# a comment that survives" in (
        tmp_path / "projects" / "cpp" / "project.toml"
    ).read_text(encoding="utf-8")


def test_the_writer_is_told_which_of_the_three_it_has(tmp_path: Path) -> None:
    config = a_repo(tmp_path, SHELF, cards='context = "none"')
    units(config, a_unit("a1", "green"))

    asked = context.assemble(config, "cpp:a1")

    assert asked.context == "none"
    text = asked.format()
    assert "No web access, and no shelf" in text
    assert "deliberately closed" in text


def test_the_usual_answer_tells_it_to_read_them(tmp_path: Path) -> None:
    config = a_repo(tmp_path, SHELF)
    units(config, a_unit("a1", "green"))

    text = context.assemble(config, "cpp:a1").format()

    assert "**Read the references**" in text
    assert "cppreference" in text and "eel.is" in text


# -- which ask reads which source -------------------------------------------


def test_a_source_can_say_which_ask_it_serves(tmp_path: Path) -> None:
    """The derivation answers for a book whose units are already here, and
    cannot answer for one you imported this morning."""
    a_repo(tmp_path, MARKED)
    (tmp_path / "projects" / "cpp" / "topics.md").write_text(
        "# What this deck is for\n\n## Containers\n\nthe containers\n", encoding="utf-8"
    )
    client = TestClient(create_app(config_mod.load(tmp_path)))

    answer = client.post("/api/sources/cpp/ZOT1/topics", json={"topics": ["containers"]})

    assert answer.json()["topics"] == ["containers"]
    work = config_mod.load(tmp_path).project("cpp").source("ZOT1")
    assert work.topics == ("containers",)

    # Edited on the ask's own panel, a box per source, and visible
    # without opening anything: it was behind a fold that read as a
    # heading with a stray zero beside it.
    page = client.get("/setup?project=cpp").text
    assert 'data-reads-for-topic="containers"' in page
    assert 'data-reads="ZOT1"' in page
    assert "details" not in page[page.index('data-reads-for-topic') - 400 :][:400]


def test_taking_one_off_leaves_the_others(tmp_path: Path) -> None:
    config = a_repo(tmp_path, MARKED + 'topics = ["containers", "algorithms"]\n')
    client = TestClient(create_app(config))

    client.post("/api/sources/cpp/ZOT1/topics", json={"topics": ["algorithms"]})

    work = config_mod.load(tmp_path).project("cpp").source("ZOT1")
    assert work.topics == ("algorithms",)


def test_an_empty_list_removes_the_key(tmp_path: Path) -> None:
    config = a_repo(tmp_path, MARKED + 'topics = ["containers"]\n')

    projects.scheme.set_list(config, "cpp", "ZOT1", "topics", [])

    text = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "topics" not in text


# -- an empty answer is an answer -------------------------------------------


def test_unchecking_every_pair_means_none_of_them(tmp_path: Path) -> None:
    """`units_from = []` read as "nobody said", so it inherited the repo
    scheme: the one action that says "stop making units out of this" was
    the one action with no effect."""
    config = a_repo(tmp_path, MARKED + "units_from = []\n")

    work = config.project("cpp").source("ZOT1")
    assert work.units_from == frozenset(), "an answer, not an absence"

    scheme = config.zotero_for("cpp", "ZOT1")
    assert not scheme.unit_pairs
    assert not scheme.makes_a_unit("highlight", "green")


def test_saying_nothing_still_inherits(tmp_path: Path) -> None:
    config = a_repo(tmp_path, MARKED)

    work = config.project("cpp").source("ZOT1")
    assert work.units_from is None
    assert config.zotero_for("cpp", "ZOT1").makes_a_unit("highlight", "green")


def test_the_editor_writes_the_empty_answer_and_the_units_go(tmp_path: Path) -> None:
    config = a_repo(tmp_path, MARKED)
    units(config, a_unit("a1", "green"), a_unit("b2", "yellow"))
    client = TestClient(create_app(config))

    answer = client.post("/api/scheme/cpp/ZOT1", json={"meanings": {}, "units_from": []})

    assert answer.json()["dropped"] == 2
    assert "units_from = []" in (
        tmp_path / "projects" / "cpp" / "project.toml"
    ).read_text(encoding="utf-8")
    assert not config.units_path("cpp").read_text(encoding="utf-8").strip()


def test_the_editor_offers_the_scheme_even_with_no_units(tmp_path: Path) -> None:
    """It was built from the marks in the ledger alone, so turning
    extraction off emptied the table: the units went, and the mapping read
    as deleted. The vocabulary is declared whether or not anything has been
    imported."""
    from anki_math_forge.app import scheme_editor

    config = a_repo(tmp_path, MARKED)
    work = config.project("cpp").source("ZOT1")

    rows = scheme_editor(config, "cpp", work, [])

    assert rows, "the scheme is there before the first import"
    pairs = {row["pair"] for row in rows}
    assert "highlight/green" in pairs and "note/yellow" in pairs
    assert all(row["count"] == 0 for row in rows)


def test_a_declared_meaning_survives_the_extract_switch(tmp_path: Path) -> None:
    """The mapping is a label on a mark and not a property of extraction."""
    config = a_repo(
        tmp_path,
        MARKED + '\n[sources.meanings]\n"highlight/green" = "a claim"\n',
    )
    client = TestClient(create_app(config))

    client.post("/api/sources/cpp/ZOT1/extract", json={"extract": False})
    client.post("/api/sources/cpp/ZOT1/extract", json={"extract": True})

    work = config_mod.load(tmp_path).project("cpp").source("ZOT1")
    assert dict(work.meanings) == {"highlight/green": "a claim"}


# -- the two readers of references.md --------------------------------------


def test_a_declared_source_is_not_a_shelf_line(tmp_path: Path) -> None:
    """`shelf()` composes what a card writer gets out of the declared
    sources and the prose. The setup page was reading that composed
    string, so every accepted reference came back as a line with an
    accept button on it, for something already accepted, and the buttons
    did nothing: the line is not in the file to drop, and accepting would
    write a second table."""
    a_repo(tmp_path, SHELF)
    (tmp_path / "projects" / "cpp" / "references.md").write_text(
        "# References\n\n- a note I keep on the shelf\n", encoding="utf-8"
    )
    page = TestClient(create_app(config_mod.load(tmp_path))).get(
        "/setup?project=cpp"
    ).text

    # Every line the page offers to settle. The declared sources were
    # in here, each with an accept button for something already
    # accepted.
    settled = re.findall(r'data-take-reference="([^"]*)"', page)
    assert settled == ["- a note I keep on the shelf"], settled
    assert page.count("shelf-line") == 1


def test_the_writer_still_gets_both_halves(tmp_path: Path) -> None:
    a_repo(tmp_path, SHELF)
    (tmp_path / "projects" / "cpp" / "references.md").write_text(
        "# References\n\nsomething I typed\n", encoding="utf-8"
    )
    reread = config_mod.load(tmp_path)

    assert "cppreference" in context.shelf(reread, "cpp")
    assert "something I typed" in context.shelf(reread, "cpp")
    assert "cppreference" not in context.references_prose(reread, "cpp")


# -- a unit still belongs to the work it came out of ------------------------


def test_a_unit_keeps_its_work_when_extraction_is_off(tmp_path: Path) -> None:
    """`extract` says whether to *make* units, not which work an existing
    one came out of. Asking only for an authoritative work left every unit
    belonging to nothing the moment the switch went off, so its crops, its
    scheme and its mark counts went with it."""
    config = a_repo(tmp_path, SHELF + MARKED + "extract = false\n")
    units(config, a_unit("a1", "green"), a_unit("b2", "green"))
    reread = config_mod.load(tmp_path)

    found = reread.project("cpp").source("ATT1")
    assert found is not None and found.zotero_key == "ZOT1"

    from anki_math_forge.app import scheme_editor

    rows = scheme_editor(reread, "cpp", found, list(_units(reread)))
    counts = {row["pair"]: row["count"] for row in rows}
    assert counts["highlight/green"] == 2


def test_two_documents_still_have_no_single_answer(tmp_path: Path) -> None:
    """The rule the fallback keeps: guessing between two books would read
    one book's scheme onto the other's crops."""
    config = a_repo(
        tmp_path,
        '[[sources]]\nzotero = "A"\n\n[[sources]]\nzotero = "B"\n',
    )

    assert config.project("cpp").source("UNKNOWN") is None


def test_a_work_with_no_units_says_so_once(tmp_path: Path) -> None:
    """Ten rows of zero read as ten failed lookups. The column is only
    drawn where there is something to count, and the reason is said
    once."""
    config = a_repo(tmp_path, MARKED)
    page = TestClient(create_app(config)).get("/setup?project=cpp").text

    assert "nothing to count" in page
    assert "sc-count" not in page, "no column of zeroes"


def test_a_zero_shows_beside_a_count(tmp_path: Path) -> None:
    """With a ledger to tally, a pair nobody used is a 0 and not a blank:
    blank read as a lookup that had failed."""
    config = a_repo(tmp_path, MARKED)
    units(config, a_unit("a1", "green"))
    page = TestClient(create_app(config_mod.load(tmp_path))).get(
        "/setup?project=cpp"
    ).text

    assert '<td class="sc-count">1</td>' in page
    assert '<td class="sc-count none">0</td>' in page


# -- a work that holds units and makes no more ------------------------------
#
# The state the switch made reachable. Everything below used to be
# unreachable, because turning it off deleted the units first.


def off_with_units(tmp_path: Path, extra: str = "") -> Config:
    """One marked-up work, switched off, holding two units and a card."""
    config = a_repo(tmp_path, MARKED + "extract = false\n" + extra)
    units(config, a_unit("a1", "green"), a_unit("b2", "green", state="queued"))
    return config


def test_the_panel_does_not_deny_the_units_it_is_counting(tmp_path: Path) -> None:
    """"Nothing is extracted from it" stood directly above a strip
    counting what was."""
    page = TestClient(create_app(off_with_units(tmp_path))).get(
        "/setup?project=cpp"
    ).text

    assert "Nothing new is extracted from this" in page
    assert "Reference material. Nothing is extracted from it" not in page


def test_the_passes_that_read_units_are_still_offered(tmp_path: Path) -> None:
    """The switch decides whether more units arrive. It does not decide
    whether the ones here want transcribing."""
    from anki_math_forge.app import runs

    at = runs.Ambient(
        project="cpp", authoritative=False, has_document=True,
        counts={"units": 2, "new": 1, "untranscribed": 2},
    )
    offered = [row["run"] for row in runs.propose("work", at)]

    assert any("/transcribe" in run for run in offered)
    assert any("/classify" in run for run in offered)
    assert not any("forge extract" in run for run in offered), "and no new ones"
    assert not any(
        "nothing to run: a reference" in row["label"] for row in runs.propose("work", at)
    )


def test_a_reference_with_no_units_still_says_there_is_nothing_to_run(
    tmp_path: Path,
) -> None:
    from anki_math_forge.app import runs

    rows = runs.propose(
        "work", runs.Ambient(project="cpp", authoritative=False, has_document=True)
    )

    assert any("nothing to run: a reference" in row["label"] for row in rows)


def test_the_project_still_says_what_it_is_made_of(tmp_path: Path) -> None:
    """`project_origin` read the switch and answered "nothing declared"
    for a project with a Zotero item and a full ledger."""
    from anki_math_forge.app import project_origin

    assert project_origin(off_with_units(tmp_path), "cpp") == "zotero"


def test_saving_a_caption_keeps_the_work_its_own_scheme(tmp_path: Path) -> None:
    """The column is drawn for every work with marks, so the save carries
    `units_from` and nothing has to guess at it."""
    config = off_with_units(tmp_path, 'units_from = ["highlight/purple"]\n')
    client = TestClient(create_app(config))

    answer = client.post(
        "/api/scheme/cpp/ZOT1",
        json={"meanings": {"highlight/purple": "a term"},
              "units_from": ["highlight/purple"]},
    )

    assert answer.json()["units_from"] == ["highlight/purple"]
    text = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert 'units_from = ["highlight/purple"]' in text


def test_a_save_that_says_nothing_about_units_leaves_the_key_alone(
    tmp_path: Path,
) -> None:
    """What `scheme.write` promises in its docstring, and did not do: it
    dropped the line first and re-appended it only when there was one."""
    from anki_math_forge import scheme

    config = off_with_units(tmp_path, 'units_from = ["highlight/purple"]\n')

    scheme.write(config, "cpp", "ZOT1", meanings={"highlight/purple": "x"},
                 units_from=None)

    text = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert 'units_from = ["highlight/purple"]' in text


def test_a_unit_is_not_handed_its_own_book_as_a_reference(tmp_path: Path) -> None:
    """A switched-off work is shelf material for every other card here and
    is the thing being read for its own."""
    config = off_with_units(tmp_path, "\n" + SHELF)

    printed = context.shelf(config, "cpp", printed_in="ZOT1")

    assert "A tour" not in printed
    assert "cppreference" in printed, "the real shelf is untouched"
    assert "A tour" in context.shelf(config, "cpp"), "and it is one, for other cards"


def test_the_segmenter_refuses_a_work_that_is_switched_off(tmp_path: Path) -> None:
    """Provenance answers for the units it made; permission does not."""
    from anki_math_forge import extract

    config = off_with_units(tmp_path)

    with pytest.raises(ConfigError, match="extraction off"):
        extract.run(config, "cpp")


def test_check_sees_two_ledgers_holding_one_work(tmp_path: Path) -> None:
    """The duplication the check exists to catch, with the switch off in
    one of the two."""
    from anki_math_forge import check

    config = off_with_units(tmp_path)
    other = tmp_path / "projects" / "dpo"
    other.mkdir(parents=True)
    (other / "project.toml").write_text(
        'title = "DPO"\n\n' + MARKED, encoding="utf-8"
    )
    config = config_mod.load(tmp_path)

    codes = [f.code for f in check.check_sources(config)]

    assert "source-extracted-twice" in codes


def test_the_import_says_in_json_that_it_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """`--json` is the interface this repo tells you to read from, so a
    refusal has to be in it and not only on stderr."""
    from types import SimpleNamespace

    from anki_math_forge.cli import _print_zotero, _zotero_row

    report = SimpleNamespace(
        documents=1, attachments=[], annotations=2, unmapped={}, skipped=[],
        text_chars=0, units=[SimpleNamespace(id="cpp:a1"), SimpleNamespace(id="cpp:b2")],
    )
    item = SimpleNamespace(key="ZOT1", citation="tour2023")

    row = _zotero_row("cpp", item, report, True)

    assert row["units"] == [], "nothing reached the ledger"
    assert row["would_make"] == ["cpp:a1", "cpp:b2"]
    assert "extraction is off" in row["refused"]
    assert "refused" not in _zotero_row("cpp", item, report, False)

    # And the printed line says one thing rather than both. It used to
    # read "2 units; 2 marks, none imported".
    _print_zotero("cpp", item, report, "none imported, extraction is off for this work",
                  refused=True)
    printed = capsys.readouterr().out
    assert "none imported, extraction is off for this work" in printed
    assert "2 units" not in printed


def test_the_sources_table_has_a_word_for_it(tmp_path: Path) -> None:
    """A book with extraction off printed as `reference`, in the same
    column as a URL somebody put on the shelf."""
    from anki_math_forge.app import every_work

    config = off_with_units(tmp_path, "\n" + SHELF)
    rows = {row["key"]: row for row in every_work(config)}

    assert rows["ZOT1"]["document"] and not rows["ZOT1"]["authoritative"]
    assert not rows["cppref"]["document"]


# -- what counts as "nobody said" -------------------------------------------


def test_a_zero_written_in_the_file_is_not_an_answer() -> None:
    """`settled` compared by identity, which reads as the careful choice and
    is the wrong one for a number: a `0` parsed out of TOML is a different
    object from the `0.0` the resolver calls empty. So `crop_context = 0` in
    `forge.toml`, which that file's own comment calls the default, resolved
    to a real zero and crops came out with none of the page around them."""
    from anki_math_forge.config import settled

    assert settled(0.0, 0.0, 90.0, empty=0.0) == 90.0
    assert settled(0, 0, 90.0, empty=0.0) == 90.0, "an int 0 from TOML, too"
    assert settled(40.0, 0.0, 90.0, empty=0.0) == 40.0, "and a real one still wins"
    assert settled(0.0, 25.0, 90.0, empty=0.0) == 25.0


def test_a_bool_is_never_read_as_a_number() -> None:
    """`False == 0` in Python and they mean different things here: one is an
    answer and the other is the absence of one."""
    from anki_math_forge.config import settled

    assert settled(False, True, empty=None) is False
    assert settled(None, False, empty=None) is False
    assert settled(False, 90.0, empty=0.0) is False


def test_the_page_window_keeps_its_own_empty() -> None:
    """Zero pages is an answer there: just this page, nothing either side."""
    from anki_math_forge.config import settled

    assert settled(-1, -1, 3, empty=-1) == 3
    assert settled(0, -1, 3, empty=-1) == 0
    assert settled("", "", "page", empty="") == "page"


def test_the_repo_default_reaches_the_crop(tmp_path: Path) -> None:
    """End to end, which is the thing that was wrong: `[cards] crop_context =
    0` is what the generated `forge.toml` carries."""
    (tmp_path / "forge.toml").write_text(
        '[repo]\nname = "x"\n\n[cards]\ncrop_context = 0\n', encoding="utf-8"
    )
    (tmp_path / "cards").mkdir()
    (tmp_path / "projects" / "cpp").mkdir(parents=True)
    (tmp_path / "projects" / "cpp" / "project.toml").write_text(
        'title = "C++"\n', encoding="utf-8"
    )

    from anki_math_forge.extract.render import TRIAGE_CONTEXT

    assert config_mod.load(tmp_path).crop_context_for("cpp") == TRIAGE_CONTEXT
