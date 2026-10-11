"""A project's settings, edited from its panel on the setup stage.

Every write goes into the project's own `project.toml`, line by line so its
comments stay, and is checked by loading the config back (invariant 2: the
file is the setting, the page is a way to type it).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import projects
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError

OWN = """\
# What this project is for.
title = "Probability"
tags = ["stats"]

# Where the cards go.
[conventions]
layout = "denominator"

[[sources]]
key = "book"
title = "Krause, lecture notes"
url = "https://example.org/book"
"""


@pytest.fixture
def own(repo: Path) -> Config:
    folder = repo / "projects" / "prob"
    folder.mkdir(parents=True)
    (folder / "project.toml").write_text(OWN, encoding="utf-8")
    (folder / "topics.md").write_text("## conjugate priors\n\n- the update\n", encoding="utf-8")
    return config_mod.load(repo)


def text_of(config: Config) -> str:
    return (config.projects_dir / "prob" / "project.toml").read_text(encoding="utf-8")


def setting(client: TestClient, key: str, value: str) -> int:
    return client.post("/api/projects/prob/setting", json={"key": key, "value": value}).status_code


@pytest.fixture
def client(own: Config) -> TestClient:
    return TestClient(create_app(own))


def test_a_key_at_the_top_joins_the_others(own: Config) -> None:
    projects.set_setting(own, "prob", "deck", '"Prob::Main"')

    text = text_of(own)
    assert text.index('deck = "Prob::Main"') < text.index("[conventions]")
    assert text.index('tags = ["stats"]') < text.index('deck = "Prob::Main"')
    assert "# What this project is for." in text and "# Where the cards go." in text


def test_a_table_that_is_not_there_is_added(own: Config) -> None:
    projects.set_setting(own, "prob", "spaced tag", '"Prob::Spaced"', table="decks.by_tag")

    parsed = tomllib.loads(text_of(own))
    assert parsed["decks"]["by_tag"] == {"spaced tag": "Prob::Spaced"}
    assert parsed["conventions"] == {"layout": "denominator"}, "the other table is untouched"


def test_none_takes_the_key_out(own: Config) -> None:
    projects.set_setting(own, "prob", "tags", None)

    assert "tags" not in tomllib.loads(text_of(own))


@pytest.mark.parametrize(
    "key,value,check",
    [
        ("citation", "Krause 2025", lambda p: p.citation == "Krause 2025"),
        ("tags", "stats, ml ,", lambda p: p.tags == ("stats", "ml")),
        ("deck", "Prob::Main", lambda p: p.deck == "Prob::Main"),
        ("order", "none", lambda p: p.order == "none"),
        ("context", "web", lambda p: p.context == "web"),
        ("offer", "false", lambda p: p.offer is False),
        ("context_pages", "chapter", lambda p: p.context_pages == "chapter"),
        ("context_pages", "3", lambda p: p.context_pages == 3),
        ("front_char_cap", "240", lambda p: p.front_char_cap == 240),
        (
            "convention:notation",
            "bold vectors",
            lambda p: p.conventions["notation"] == "bold vectors",
        ),
        ("deck.tag:hard ones", "Prob::Hard", lambda p: p.tag_decks == {"hard ones": "Prob::Hard"}),
        (
            "deck.topic:conjugate-priors",
            "Prob::Conj",
            lambda p: p.topic_decks == {"conjugate-priors": "Prob::Conj"},
        ),
        ("deck.type:intuition", "Prob::Why", lambda p: p.decks == {"intuition": "Prob::Why"}),
    ],
)
def test_each_setting_lands_where_the_loader_reads_it(
    client: TestClient, own: Config, key: str, value: str, check: object
) -> None:
    assert setting(client, key, value) == 200

    spec = config_mod.load(own.root).projects["prob"]
    assert check(spec), text_of(own)  # type: ignore[operator]


def test_empty_inherits_again(client: TestClient, own: Config) -> None:
    setting(client, "front_char_cap", "240")
    setting(client, "front_char_cap", "")

    assert config_mod.load(own.root).projects["prob"].front_char_cap == 0
    assert "front_char_cap" not in text_of(own)


def test_the_new_context_key_replaces_the_old_one(client: TestClient, own: Config) -> None:
    """`web` is the older spelling of the same question, and two answers in
    one file disagree the moment one is taken out."""
    projects.set_setting(own, "prob", "web", "true")

    setting(client, "context", "none")

    parsed = tomllib.loads(text_of(own))
    assert parsed["context"] == "none" and "web" not in parsed


def test_a_flat_type_map_stays_flat(client: TestClient, own: Config) -> None:
    """An older file maps types under `[decks]` itself. A `[decks.by_type]`
    beside it would hide every line of the flat one."""
    projects.set_setting(own, "prob", "identity", '"Prob::Facts"', table="decks")

    setting(client, "deck.type:intuition", "Prob::Why")

    spec = config_mod.load(own.root).projects["prob"]
    assert spec.decks == {"identity": "Prob::Facts", "intuition": "Prob::Why"}


@pytest.mark.parametrize(
    "key,value",
    [("order", "sideways"), ("context", "everything"), ("front_char_cap", "-3"), ("nonsense", "x")],
)
def test_a_value_the_key_cannot_hold_is_refused(
    client: TestClient, own: Config, key: str, value: str
) -> None:
    before = text_of(own)

    assert setting(client, key, value) == 400
    assert text_of(own) == before


def test_what_the_loader_refuses_is_put_back(client: TestClient, own: Config) -> None:
    """`layout` is checked because something acts on it."""
    before = text_of(own)

    out = client.post(
        "/api/projects/prob/setting", json={"key": "convention:layout", "value": "sideways"}
    )

    assert out.status_code == 400 and "not saved" in out.json()["detail"]
    assert text_of(own) == before


def test_a_project_in_forge_toml_is_shown_not_edited(config: Config) -> None:
    client = TestClient(create_app(config))

    page = client.get("/setup?project=demo").text

    assert "/api/projects/demo/setting" not in page
    assert client.post(
        "/api/projects/demo/setting", json={"key": "deck", "value": "X"}
    ).status_code == 400


def test_the_page_offers_the_settings(client: TestClient) -> None:
    page = client.get("/setup?project=prob").text

    assert 'data-set-url="/api/projects/prob/setting"' in page
    for key in ("deck", "context", "context_pages", "front_char_cap", "citation", "tags",
                "deck.topic:conjugate-priors", "convention:layout"):
        assert f'data-set-key="{key}"' in page, key
    assert 'data-set-prefix="convention:"' in page and 'data-set-prefix="deck.tag:"' in page


def test_a_source_is_renamed_and_readdressed_from_its_panel(
    client: TestClient, own: Config
) -> None:
    url = "/api/sources/prob/book/setting"
    for key, value in (("title", "Krause and Hübotter"), ("url", "https://example.org/v2")):
        assert client.post(url, json={"key": key, "value": value}).status_code == 200

    (work,) = config_mod.load(own.root).projects["prob"].sources
    assert (work.title, work.url) == ("Krause and Hübotter", "https://example.org/v2")
    assert 'data-set-key="title"' in client.get("/setup?project=prob").text


def test_a_refused_key_says_so(own: Config) -> None:
    with pytest.raises(ConfigError):
        from anki_math_forge.app import project_setting

        project_setting("deck.type:essay", "X", "")
