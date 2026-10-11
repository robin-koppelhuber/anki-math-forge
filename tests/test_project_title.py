"""What a project is called on screen, and that renaming it is only that.

The folder name is in every unit id and never changes. The title is what the
picker, the shelf and the setup stage show, and it is yours to edit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import projects
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError

OWN = """\
# What this project is for.
title = "cpp"
tags = ["cpp"]

[[sources]]
title = "A Tour of C++"
url = "https://example.org/tour"
"""


@pytest.fixture
def own(repo: Path) -> Config:
    """A project with a `project.toml` of its own, a comment, and a source
    that has a `title` of its own under `[[sources]]`."""
    folder = repo / "projects" / "cpp"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text(OWN, encoding="utf-8")
    return config_mod.load(repo)


def test_a_rename_writes_the_title_and_nothing_else(own: Config) -> None:
    shown = projects.set_title(own, "cpp", "  A tour of   C++ ")

    text = (own.projects_dir / "cpp" / "project.toml").read_text(encoding="utf-8")
    assert shown == "A tour of C++", "the spacing a picker would show is tidied"
    assert 'title = "A tour of C++"' in text
    assert "# What this project is for." in text, "the comments stay"
    assert 'title = "A Tour of C++"' in text, "the source's own title is a different key"
    again = config_mod.load(own.root)
    assert again.projects["cpp"].title == "A tour of C++"
    assert [w.title for w in again.projects["cpp"].sources] == ["A Tour of C++"]


def test_a_project_with_no_title_gets_one(own: Config) -> None:
    path = own.projects_dir / "cpp" / "project.toml"
    path.write_text(OWN.replace('title = "cpp"\n', ""), encoding="utf-8")

    projects.set_title(own, "cpp", "C++")

    assert config_mod.load(own.root).projects["cpp"].title == "C++"


def test_a_zotero_project_keeps_its_deck(zotero_config: Config) -> None:
    """Its deck is named after its title unless it names one, so a rename
    would have moved every card. The deck it has is pinned instead."""
    before = zotero_config.deck_for("paper")

    projects.set_title(zotero_config, "paper", "Something else entirely")

    after = config_mod.load(zotero_config.root)
    assert after.projects["paper"].title == "Something else entirely"
    assert after.deck_for("paper") == before


def test_a_project_in_forge_toml_is_renamed_there(config: Config) -> None:
    with pytest.raises(ConfigError, match=r"forge.toml"):
        projects.set_title(config, "demo", "Something")


def test_an_empty_name_is_refused(own: Config) -> None:
    with pytest.raises(ConfigError):
        projects.set_title(own, "cpp", "   ")


def test_the_app_renames_and_shows_it(own: Config) -> None:
    client = TestClient(create_app(own))

    out = client.post("/api/projects/cpp/title", json={"title": "A tour of C++"})

    assert out.status_code == 200, out.text
    assert out.json()["title"] == "A tour of C++"
    page = client.get("/setup?project=cpp").text
    assert "A tour of C++" in page
    assert client.post("/api/projects/cpp/title", json={"title": ""}).status_code == 400


def test_the_bar_reads_project_then_what_to_do_with_it(own: Config) -> None:
    """The picker, by title, then setup, the commands and the graph."""
    projects.set_title(own, "cpp", "A tour of C++")
    page = TestClient(create_app(config_mod.load(own.root))).get("/units?project=cpp").text

    picker = page.index('id="project-pick"')
    assert "A tour of C++" in page[picker : page.index("</a>", picker)]
    setup = page.index('href="/setup', picker)
    runs = page.index("data-runs-open", picker)
    graph = page.index('href="/graph', picker)
    assert picker < setup < runs < graph


def test_the_bar_leads_back_to_triage_and_the_cards(own: Config) -> None:
    """The setup stage and the canvas have no rail with the lanes on it."""
    page = TestClient(create_app(own)).get("/setup?project=cpp").text

    bar = page[page.index('id="project-pick"') : page.index("data-runs-open")]
    assert 'aria-label="triage"' in bar and 'aria-label="cards"' in bar
