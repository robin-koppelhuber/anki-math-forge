"""A proposed source, accepted, is a source.

The flow the setup stage owes: a pass proposes, you accept or reject, and
what you accepted has a panel where you say how to read it. Before this,
accepting took the checkbox off a line of prose and nothing else happened,
so a pass could propose six sources and the sources list stayed empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import context, projects, scheme
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError

LINE = (
    "- [ ] cppreference, the containers library overview"
    " (https://en.cppreference.com/w/cpp/container),"
    " for the per-container complexity and iterator-invalidation tables"
)


def a_project(tmp_path: Path, *lines: str) -> Config:
    (tmp_path / "forge.toml").write_text('[repo]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "cards").mkdir()
    folder = tmp_path / "projects" / "cpp"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text(
        'title = "The C++ standard library"\n\n# a comment that survives\n',
        encoding="utf-8",
    )
    if lines:
        body = "\n".join(lines)
        (folder / "references.md").write_text(
            f"# References\n\nthe prose above the list\n\n{body}\n", encoding="utf-8"
        )
    return config_mod.load(tmp_path)


# -- reading a proposal -----------------------------------------------------


def test_a_proposal_is_read_as_a_name_an_address_and_a_purpose() -> None:
    """The three parts the `[[sources]]` table wants. Split on the address,
    because it is the only part with a syntax."""
    title, url, note = projects.parse_proposal(LINE)

    assert title == "cppreference, the containers library overview"
    assert url == "https://en.cppreference.com/w/cpp/container"
    assert note == "for the per-container complexity and iterator-invalidation tables"


def test_a_book_has_the_same_three_parts_with_no_address() -> None:
    """`, for ` ends the name where an address would. A guess about prose
    rather than a syntax, so it takes the *last* one: a title can have one
    in it and the purpose is always at the end."""
    title, url, note = projects.parse_proposal(
        "- [ ] Josuttis, The C++ Standard Library, 2nd edition,"
        " for worked container usage"
    )

    assert title == "Josuttis, The C++ Standard Library, 2nd edition"
    assert not url
    assert note == "worked container usage"

    # Nothing to split on: all name, which is what a bare title is.
    bare, _, nothing = projects.parse_proposal("- [ ] Meyers, Effective STL")
    assert bare == "Meyers, Effective STL" and not nothing

    # And a title that carries one keeps it, because the split is the last.
    named, _, why = projects.parse_proposal(
        "- [ ] A Course in Combinatorics, for Beginners, for the counting chapter"
    )
    assert named == "A Course in Combinatorics, for Beginners"
    assert why == "the counting chapter"


# -- accepting one ----------------------------------------------------------


def test_accepting_writes_a_source_and_clears_the_line(tmp_path: Path) -> None:
    config = a_project(tmp_path, LINE, "- [ ] Josuttis, The C++ Standard Library")

    key = projects.accept_proposal(config, "cpp", LINE)

    work = config_mod.load(tmp_path).project("cpp").source(key)
    assert work is not None
    assert work.title == "cppreference, the containers library overview"
    assert work.url == "https://en.cppreference.com/w/cpp/container"
    assert work.note.startswith("for the per-container")
    assert not work.authoritative, "no files and no item key"

    shelf = (tmp_path / "projects" / "cpp" / "references.md").read_text(encoding="utf-8")
    assert "cppreference" not in shelf, "it lives in the table now"
    assert "Josuttis" in shelf, "and the other proposal is untouched"
    assert "the prose above the list" in shelf


def test_the_toml_keeps_its_comments(tmp_path: Path) -> None:
    config = a_project(tmp_path, LINE)

    projects.accept_proposal(config, "cpp", LINE)

    written = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "# a comment that survives" in written


def test_a_key_is_cut_at_a_word(tmp_path: Path) -> None:
    """It goes in a table, in a unit id and on a command line.
    `cppreference-the-containers-libr` is a word you have to check against
    the file every time."""
    config = a_project(tmp_path, LINE)

    key = projects.accept_proposal(config, "cpp", LINE)

    assert key == "cppreference-the-containers-library"
    assert not key.endswith("-")


def test_two_proposals_that_slug_the_same_get_two_keys(tmp_path: Path) -> None:
    first = "- [ ] cppreference (https://a.test/1)"
    second = "- [ ] cppreference (https://b.test/2)"
    config = a_project(tmp_path, first, second)

    projects.accept_proposal(config, "cpp", first)
    key = projects.accept_proposal(config_mod.load(tmp_path), "cpp", second)

    assert key == "cppreference-2"
    assert len(config_mod.load(tmp_path).project("cpp").sources) == 2


def test_a_quote_in_a_proposal_is_escaped_not_refused(tmp_path: Path) -> None:
    """A title is prose somebody wrote, and prose has quotes in it. It has
    to survive the round trip through TOML, or the file will not load."""
    line = '- [ ] The so-called "small string" optimisation (https://x.test/s)'
    config = a_project(tmp_path, line)

    projects.accept_proposal(config, "cpp", line)

    work = config_mod.load(tmp_path).project("cpp").sources[0]
    assert work.title == 'The so-called "small string" optimisation'


def test_rejecting_deletes_the_line(tmp_path: Path) -> None:
    config = a_project(tmp_path, LINE)

    assert projects.drop_proposal(config, "cpp", LINE)

    shelf = (tmp_path / "projects" / "cpp" / "references.md").read_text(encoding="utf-8")
    assert "cppreference" not in shelf
    assert not config_mod.load(tmp_path).project("cpp").sources, "and nothing written"


def test_a_project_configured_in_forge_toml_says_where_to_edit(tmp_path: Path) -> None:
    (tmp_path / "forge.toml").write_text(
        '[repo]\nname = "x"\n\n[projects.cpp]\ntitle = "C++"\n', encoding="utf-8"
    )
    (tmp_path / "cards").mkdir()
    (tmp_path / "projects" / "cpp").mkdir(parents=True)
    (tmp_path / "projects" / "cpp" / "references.md").write_text(
        f"# References\n\n{LINE}\n", encoding="utf-8"
    )
    config = config_mod.load(tmp_path)

    with pytest.raises(ConfigError, match=r"forge\.toml"):
        projects.accept_proposal(config, "cpp", LINE)


# -- the panel --------------------------------------------------------------


def test_proposals_are_listed_among_the_sources(tmp_path: Path) -> None:
    """Where somebody looks for a source. They were under the shelf on the
    project's own panel, so a pass proposed six and they read as having
    gone nowhere."""
    config = a_project(tmp_path, LINE)
    page = TestClient(create_app(config)).get("/setup?project=cpp").text

    # The left-hand list only: the panels below render every proposal too.
    listed = page[page.index('id="source-list"') : page.index('+ add a source')]
    assert 'data-pane="proposed:0"' in listed
    assert "cppreference, the containers library overview" in listed


def test_the_panel_says_what_accepting_would_write(tmp_path: Path) -> None:
    config = a_project(tmp_path, LINE)
    page = TestClient(create_app(config)).get("/setup?project=cpp").text

    pane = page[page.index('<section class="setup-pane" data-pane="proposed:0"') :]
    pane = pane[: pane.index("</section>")]
    assert "https://en.cppreference.com/w/cpp/container" in pane
    assert "for the per-container complexity" in pane
    assert "data-take-reference" in pane and "data-drop-reference" in pane


def test_accepting_from_the_app_names_the_source_it_made(tmp_path: Path) -> None:
    """The page lands on that panel, so the next thing you do is say what
    the source is for."""
    config = a_project(tmp_path, LINE)

    answer = TestClient(create_app(config)).post(
        "/api/references/cpp/accept", json={"line": LINE}
    )

    assert answer.status_code == 200
    assert answer.json()["key"] == "cppreference-the-containers-library"


# -- what it is for ---------------------------------------------------------


def test_the_note_is_editable_on_the_source(tmp_path: Path) -> None:
    config = a_project(tmp_path, LINE)
    key = projects.accept_proposal(config, "cpp", LINE)
    client = TestClient(create_app(config_mod.load(tmp_path)))

    answer = client.post(
        f"/api/sources/cpp/{key}/note", json={"note": "start here for complexity"}
    )

    assert answer.status_code == 200
    work = config_mod.load(tmp_path).project("cpp").source(key)
    assert work is not None and work.note == "start here for complexity"
    written = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "# a comment that survives" in written, "line-wise, like the scheme"


def test_an_empty_note_removes_the_key(tmp_path: Path) -> None:
    """A `note = ""` in the table is a caption somebody wrote and deleted,
    which reads as a considered blank."""
    config = a_project(tmp_path, LINE)
    key = projects.accept_proposal(config, "cpp", LINE)

    scheme.set_key(config_mod.load(tmp_path), "cpp", key, "note", "")

    written = (tmp_path / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert "note =" not in written
    assert config_mod.load(tmp_path).project("cpp").source(key) is not None


def test_a_card_writer_is_handed_the_accepted_sources(tmp_path: Path) -> None:
    """The whole reason the note is worth typing. A reference that reaches
    nobody is a line in a config file."""
    config = a_project(tmp_path, LINE, "- something I typed myself")
    projects.accept_proposal(config, "cpp", LINE)

    shelf = context.shelf(config_mod.load(tmp_path), "cpp")

    assert "cppreference, the containers library overview" in shelf
    assert "https://en.cppreference.com/w/cpp/container" in shelf
    assert "for the per-container complexity" in shelf
    assert "something I typed myself" in shelf, "and the prose half as well"


def test_an_authoritative_work_is_not_on_the_shelf(tmp_path: Path) -> None:
    """A crop settles what the card says. It reaches the writer as the
    unit's own source, not as something to check against."""
    a_project(tmp_path)
    (tmp_path / "projects" / "cpp" / "project.toml").write_text(
        'title = "C++"\n\n[[sources]]\nkey = "book"\nfiles = ["projects/cpp/b.pdf"]\n',
        encoding="utf-8",
    )
    (tmp_path / "projects" / "cpp" / "b.pdf").write_bytes(b"%PDF-1.4\n")

    assert "book" not in context.shelf(config_mod.load(tmp_path), "cpp")
