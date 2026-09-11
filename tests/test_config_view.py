"""What every setting resolved to, and where the value came from.

There was no way to tell which layout a card resolved to, or whether that came
from the source or the default, without reading Python. Read-only on purpose:
the config is read at startup, so editing here would take effect at some
unrelated later moment, and half these keys change the meaning of content that
already exists.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import config as config_mod
from anki_math_forge.app import effective_config
from anki_math_forge.config import Config


def rows_for(config: Config, where: str) -> dict[str, dict[str, object]]:
    return {str(r["key"]): r for r in effective_config(config) if r["where"] == where}


def write_source(repo: Path, name: str, frontmatter: str) -> None:
    folder = repo / "sources" / name
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        "+++\n" + frontmatter.strip() + "\n+++\n", encoding="utf-8"
    )


def test_it_says_which_value_won(repo: Path) -> None:
    write_source(repo, "book", 'title = "A Book"\ndeck = "Shelf"')
    rows = rows_for(config_mod.load(repo), "source: book")

    assert rows["deck"]["value"] == "Shelf"
    assert rows["deck"]["from"] == "sources/book/source.md"


def test_it_says_when_a_value_was_inherited(repo: Path) -> None:
    """The question the page exists to answer. A source that sets nothing still
    resolves to something, and which something is not guessable."""
    write_source(repo, "book", 'title = "A Book"')
    rows = rows_for(config_mod.load(repo), "source: book")

    assert rows["layout"]["from"] == "inherited"
    assert rows["layout"]["value"] == config_mod.load(repo).layout


def test_a_per_type_deck_is_listed_on_its_own_row(repo: Path) -> None:
    write_source(
        repo,
        "book",
        'title = "A Book"\n\n[decks]\nintuition = "Shelf::Intuition"',
    )
    rows = rows_for(config_mod.load(repo), "source: book")
    assert rows["deck [intuition]"]["value"] == "Shelf::Intuition"


def test_the_repo_group_carries_what_is_genuinely_repo_wide(config: Config) -> None:
    rows = rows_for(config, "anki")
    assert rows["note type"]["value"] == config.note_type
    assert rows["tag prefix"]["value"] == config.tag_prefix


def test_the_anki_url_says_the_environment_can_override_it(config: Config) -> None:
    """`ANKI_CONNECT_URL` wins over the file, which is invisible from the file
    alone and exactly the sort of thing this page is for."""
    assert "ANKI_CONNECT_URL" in str(rows_for(config, "anki")["url"]["from"])


def test_the_page_renders(config: Config) -> None:
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    response = TestClient(create_app(config)).get("/config")
    assert response.status_code == 200
    assert "effective configuration" in response.text
