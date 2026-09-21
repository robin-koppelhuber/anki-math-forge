"""Taking a source out of a project, and the rule about sites.

A source is a table, and what came out of it. Removing the table and
leaving the units behind gives you units whose work is gone: no crop to
render, no scheme to read, no settings to resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import projects
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError


def a_repo(tmp_path: Path, *, units: int = 0) -> Config:
    (tmp_path / "forge.toml").write_text('[repo]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "cards").mkdir()
    folder = tmp_path / "projects" / "cpp"
    folder.mkdir(parents=True)
    (folder / "book.pdf").write_bytes(b"%PDF-1.4\n")
    (folder / "project.toml").write_text(
        'title = "C++"\n\n'
        "# a comment about the book\n"
        '[[sources]]\nkey = "book"\nfiles = ["projects/cpp/book.pdf"]\n\n'
        '[[sources]]\nkey = "cppref"\ntitle = "cppreference"\n'
        'url = "https://en.cppreference.com/w/cpp/container"\n',
        encoding="utf-8",
    )
    if units:
        (folder / "units.jsonl").write_text(
            "".join(
                json.dumps(
                    {
                        "id": f"cpp:1:{n}",
                        "state": "new",
                        "locator": {"document": "book.pdf", "page": n},
                    }
                )
                + "\n"
                for n in range(1, units + 1)
            ),
            encoding="utf-8",
        )
    return config_mod.load(tmp_path)


def a_card(config: Config, uid: str, unit: str, status: str = "draft") -> None:
    path = config.cards_dir / "cpp" / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: {status}\n"
        f'source: "C++"\nunit: "{unit}"\ntags: []\nverify: false\n---\n\n'
        "## front\n$X$\n\n## back\n$Y$\n",
        encoding="utf-8",
    )


# -- removing one -----------------------------------------------------------


def test_removing_a_reference_drops_its_table_and_nothing_else(tmp_path: Path) -> None:
    config = a_repo(tmp_path, units=3)

    going = projects.remove_source(config, "cpp", "cppref")

    assert going.units == 0 and going.cards == 0
    after = config_mod.load(tmp_path).project("cpp")
    assert [w.key for w in after.sources] == ["book"]
    text = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "# a comment about the book" in text, "line-wise, like every other edit"
    assert len(config.units_path("cpp").read_text(encoding="utf-8").splitlines()) == 3


def test_a_work_takes_its_units_with_it(tmp_path: Path) -> None:
    """A unit whose work is gone has no crop to render and no settings to
    resolve, and `extract` writes them again from the document."""
    config = a_repo(tmp_path, units=3)

    going = projects.remove_source(config, "cpp", "book")

    assert going.units == 3
    assert going.authoritative
    assert config.units_path("cpp").read_text(encoding="utf-8").strip() == ""
    assert [w.key for w in config_mod.load(tmp_path).project("cpp").sources] == ["cppref"]


def test_cards_are_the_gate(tmp_path: Path) -> None:
    config = a_repo(tmp_path, units=2)
    a_card(config, "aaa111", "cpp:1:1", status="approved")

    with pytest.raises(ConfigError) as caught:
        projects.remove_source(config, "cpp", "book")

    assert "1 card" in str(caught.value) and "approved" in str(caught.value)
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 2, "nothing taken"

    projects.remove_source(config, "cpp", "book", force=True)
    assert [w.key for w in config_mod.load(tmp_path).project("cpp").sources] == ["cppref"]


def test_a_dry_run_takes_nothing(tmp_path: Path) -> None:
    config = a_repo(tmp_path, units=2)

    going = projects.source_removal(config, "cpp", "book")

    assert going.units == 2
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 2


def test_removing_something_it_does_not_read_says_so(tmp_path: Path) -> None:
    config = a_repo(tmp_path)

    with pytest.raises(ConfigError, match="does not read"):
        projects.remove_source(config, "cpp", "ghost")


def test_the_app_removes_a_reference_but_never_forces(tmp_path: Path) -> None:
    config = a_repo(tmp_path, units=1)
    a_card(config, "aaa111", "cpp:1:1")
    client = TestClient(create_app(config))

    assert client.delete("/api/sources/cpp/cppref").status_code == 200

    refused = client.delete("/api/sources/cpp/book")
    assert refused.status_code == 400
    assert "--force" in refused.json()["detail"]
    assert config_mod.load(tmp_path).project("cpp").source("book") is not None


def test_the_control_asks_you_to_type_the_key(tmp_path: Path) -> None:
    config = a_repo(tmp_path)
    page = TestClient(create_app(config)).get("/setup?project=cpp").text

    assert 'data-drop-source="cppref"' in page
    assert "remove this source" in page


# -- one source per site ----------------------------------------------------


def test_pages_of_one_site_are_one_source(tmp_path: Path) -> None:
    """Six rows for six pages of cppreference is six times the same source,
    and a card writer handed six of them learns nothing the first did not
    say. The note carries which part each was about."""
    config = a_repo(tmp_path)

    key, merged = projects.add_reference(
        config,
        "cpp",
        title="cppreference, the algorithms library",
        url="https://en.cppreference.com/w/cpp/algorithm",
        note="equal_range and lower_bound",
    )

    assert merged and key == "cppref"
    work = config_mod.load(tmp_path).project("cpp").source("cppref")
    assert work is not None
    assert work.url == "https://en.cppreference.com/w/cpp", "the deepest shared address"
    assert "algorithm: equal_range and lower_bound" in work.note
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 2, "no new row"


def test_two_documents_on_one_host_stay_two_sources(tmp_path: Path) -> None:
    """Two arXiv papers share `arxiv.org/abs` and are not one source.
    Merging on the host alone would make one entry out of two unrelated
    documents, which is worse than six entries for one manual."""
    config = a_repo(tmp_path)
    projects.add_reference(
        config, "cpp", title="DPO", url="https://arxiv.org/abs/2305.18290"
    )
    key, merged = projects.add_reference(
        config_mod.load(tmp_path),
        "cpp",
        title="UMAP",
        url="https://arxiv.org/abs/1802.03426",
    )

    assert not merged and key == "umap"
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 4


def test_a_page_is_never_folded_into_something_units_come_out_of(
    tmp_path: Path,
) -> None:
    """A page of a website is not part of a book somebody is segmenting,
    whatever the addresses have in common."""
    a_repo(tmp_path)
    (tmp_path / "projects" / "cpp" / "project.toml").write_text(
        'title = "C++"\n\n[[sources]]\nkey = "book"\n'
        'files = ["projects/cpp/book.pdf"]\nurl = "https://x.test/a/b/c"\n',
        encoding="utf-8",
    )

    key, merged = projects.add_reference(
        config_mod.load(tmp_path), "cpp", title="A page", url="https://x.test/a/b/d"
    )

    assert not merged and key == "a-page"


def test_the_widened_note_labels_both_halves(tmp_path: Path) -> None:
    """The old note described a page the address no longer names."""
    config = a_repo(tmp_path)
    projects.add_reference(
        config,
        "cpp",
        title="cppreference, hash",
        url="https://en.cppreference.com/w/cpp/utility/hash",
        note="what std::hash must do",
    )

    work = config_mod.load(tmp_path).project("cpp").source("cppref")
    assert work is not None
    assert work.url == "https://en.cppreference.com/w/cpp"
    assert work.note.startswith("container"), work.note
    assert "utility/hash: what std::hash must do" in work.note


def test_a_website_can_be_added_by_hand(tmp_path: Path) -> None:
    """The same three fields a proposal carries, typed in rather than
    suggested, so both end up as the same table."""
    config = a_repo(tmp_path)
    client = TestClient(create_app(config))

    answer = client.post(
        "/api/references/cpp/web",
        json={"url": "https://eel.is/c++draft", "note": "authoritative wording"},
    )

    assert answer.status_code == 200
    work = config_mod.load(tmp_path).project("cpp").source(answer.json()["key"])
    assert work is not None
    assert work.url == "https://eel.is/c++draft"
    assert work.title == "eel.is", "the host, when you did not name it"
    assert not work.authoritative


def test_adding_a_page_of_a_site_you_read_says_it_merged(tmp_path: Path) -> None:
    config = a_repo(tmp_path)
    client = TestClient(create_app(config))

    answer = client.post(
        "/api/references/cpp/web",
        json={"url": "https://en.cppreference.com/w/cpp/named_req", "note": "comparators"},
    )

    assert answer.json() == {"ok": True, "key": "cppref", "merged": True}


def test_two_asks_reading_one_site_are_two_sources(tmp_path: Path) -> None:
    """The part is what a card is checked against, not the domain. Widening
    them together would hand whoever writes about containers a note about
    threads."""
    config = a_repo(tmp_path)

    first, _ = projects.add_reference(
        config,
        "cpp",
        title="cppreference, containers",
        url="https://en.cppreference.com/w/cpp/container",
        note="the complexity tables",
        topic="containers",
    )
    second, merged = projects.add_reference(
        config_mod.load(tmp_path),
        "cpp",
        title="cppreference, threads",
        url="https://en.cppreference.com/w/cpp/thread",
        note="what a jthread joins",
        topic="concurrency",
    )

    assert not merged and second != first
    reads = config_mod.load(tmp_path).project("cpp")
    assert reads.source(first).url.endswith("/container")
    assert reads.source(second).url.endswith("/thread")
    assert reads.source(second).topics == ("concurrency",)


def test_two_pages_for_one_ask_are_still_one_source(tmp_path: Path) -> None:
    config = a_repo(tmp_path)
    projects.add_reference(
        config,
        "cpp",
        title="cppreference, containers",
        url="https://en.cppreference.com/w/cpp/container",
        note="the complexity tables",
        topic="containers",
    )
    key, merged = projects.add_reference(
        config_mod.load(tmp_path),
        "cpp",
        title="cppreference, algorithms",
        url="https://en.cppreference.com/w/cpp/algorithm",
        note="equal_range",
        topic="containers",
    )

    assert merged
    work = config_mod.load(tmp_path).project("cpp").source(key)
    assert work.url == "https://en.cppreference.com/w/cpp"
    assert work.topics == ("containers",)


def test_a_heading_says_which_ask_a_proposal_is_for(tmp_path: Path) -> None:
    """`##` in `references.md`, which is what anybody writing the file by
    hand would use."""
    from anki_math_forge.app import shelf_rows

    rows = shelf_rows(
        "## containers\n\n- [ ] cppreference (https://a.test/w/cpp/container)\n"
        "\n## concurrency\n\n- [ ] cppreference (https://a.test/w/cpp/thread)\n"
    )

    assert [row["topic"] for row in rows] == ["containers", "concurrency"]
    assert [row["slug"] for row in rows] == ["containers", "concurrency"]


def test_accepting_takes_the_ask_from_the_file(tmp_path: Path) -> None:
    """The browser knows which panel you clicked; the file knows what the
    pass was asked to cover, and that is the one that survives an edit."""
    a_repo(tmp_path)
    line = "- [ ] cppreference, threads (https://en.cppreference.com/w/cpp/thread)"
    (tmp_path / "projects" / "cpp" / "references.md").write_text(
        f"# References\n\n## Concurrency\n\n{line}\n", encoding="utf-8"
    )
    client = TestClient(create_app(config_mod.load(tmp_path)))

    answer = client.post("/api/references/cpp/accept", json={"line": line})

    key = answer.json()["key"]
    work = config_mod.load(tmp_path).project("cpp").source(key)
    assert work.topics == ("concurrency",), "slugged from the heading"
    # And it did not fold into the reference already there, which is for
    # no ask at all.
    assert work.url.endswith("/thread")


def test_the_app_adds_a_known_work_as_a_reference_only(tmp_path: Path) -> None:
    """The item key and the files are what make a work authoritative, and
    the app does not write those. Segmenting a document is a decision with
    crop settings and a marking scheme behind it."""
    a_repo(tmp_path)
    (tmp_path / "forge.toml").write_text(
        '[repo]\nname = "x"\n\n[projects.other]\ntitle = "Other"\n\n'
        '[[projects.other.sources]]\nkey = "paper"\nzotero = "ZOT1"\n'
        'title = "A paper"\nurl = "https://x.test/p"\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(config_mod.load(tmp_path)))

    answer = client.post("/api/sources/cpp", json={"key": "paper", "extract": True})

    assert answer.status_code == 200
    work = config_mod.load(tmp_path).project("cpp").source("paper")
    assert work is not None
    assert not work.authoritative, "even when asked for"
    assert not work.zotero_key and not work.files
    assert work.url == "https://x.test/p"


def test_the_pane_offers_no_way_to_extract(tmp_path: Path) -> None:
    config = a_repo(tmp_path)
    page = TestClient(create_app(config)).get("/setup?project=cpp").text

    assert "known-extract" not in page
    assert "extract from it" not in page


# -- an imported item is declared, marks or no marks ------------------------


def test_an_item_with_no_marks_is_still_declared(tmp_path: Path) -> None:
    """You have the book and have not marked it up yet. The import wrote
    the source only when it produced units, so importing a fresh book said
    what it found and wrote none of it down."""
    a_repo(tmp_path)

    written = projects.declare_zotero(
        config_mod.load(tmp_path),
        "cpp",
        key="STROUSTRUP1",
        title="A Tour of C++",
        citation="Stroustrup 2023",
    )

    assert written
    work = config_mod.load(tmp_path).project("cpp").source("STROUSTRUP1")
    assert work is not None
    assert work.authoritative, "an item key is what makes marks become units"
    assert work.title == "A Tour of C++"


def test_declaring_one_twice_writes_nothing(tmp_path: Path) -> None:
    """Re-running the import is safe, which is the whole shape of `zotero`."""
    a_repo(tmp_path)
    config = config_mod.load(tmp_path)
    projects.declare_zotero(config, "cpp", key="STROUSTRUP1", title="A Tour")

    assert not projects.declare_zotero(
        config_mod.load(tmp_path), "cpp", key="STROUSTRUP1", title="A Tour"
    )
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 3


def test_a_second_project_cannot_claim_the_same_item(tmp_path: Path) -> None:
    """One extraction per document: two is two ledgers of units and two
    notes per card in Anki."""
    a_repo(tmp_path)
    (tmp_path / "projects" / "other").mkdir()
    (tmp_path / "projects" / "other" / "project.toml").write_text(
        'title = "Other"\n\n[[sources]]\nzotero = "STROUSTRUP1"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="already extracts"):
        projects.declare_zotero(config_mod.load(tmp_path), "cpp", key="STROUSTRUP1")
