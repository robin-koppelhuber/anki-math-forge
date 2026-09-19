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
    folder = repo / "projects" / name
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("source.md").write_text(
        "+++\n" + frontmatter.strip() + "\n+++\n", encoding="utf-8"
    )


def test_it_says_which_value_won(repo: Path) -> None:
    write_source(repo, "book", 'title = "A Book"\ndeck = "Shelf"')
    rows = rows_for(config_mod.load(repo), "source: book")

    assert rows["deck"]["value"] == "Shelf"
    assert rows["deck"]["from"] == "projects/book/project.toml"


def test_it_says_when_a_value_was_inherited(repo: Path) -> None:
    """The question the page exists to answer. A source that sets nothing still
    resolves to something, and which something is not guessable."""
    write_source(repo, "book", 'title = "A Book"')
    rows = rows_for(config_mod.load(repo), "source: book")

    assert rows["context_pages"]["from"] == "inherited"
    assert rows["context_pages"]["value"] == config_mod.load(repo).context_pages


def test_a_convention_is_listed_whether_or_not_anything_acts_on_it(repo: Path) -> None:
    """`[conventions]` is open: what is ambient in a source is not a vocabulary
    this tool can enumerate, and the next paper will assume something neither
    of us has thought of. `verify` acts on `layout` alone; the rest still have
    to reach whoever writes a card, and this table is where they are visible.
    """
    write_source(
        repo,
        "book",
        'title = "A Book"\n\n[conventions]\nlayout = "numerator"\nindices = "1-based"',
    )
    rows = rows_for(config_mod.load(repo), "source: book")

    assert rows["conventions.layout"]["value"] == "numerator"
    assert rows["conventions.indices"]["value"] == "1-based"


def test_there_is_no_repo_wide_convention_to_inherit(repo: Path) -> None:
    """A convention is a fact about one book. Defaulting one repo-wide is how a
    statistics paper came to be told it writes matrix calculus in denominator
    layout -- the silent mixing CLAUDE.md names, arriving through a default
    rather than through a mistake."""
    write_source(repo, "book", 'title = "A Book"')
    rows = rows_for(config_mod.load(repo), "source: book")

    assert not [key for key in rows if key.startswith("conventions.")]
    assert config_mod.load(repo).layout_for("book") == ""


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


def test_it_is_served_as_a_panel_not_a_page(config: Config) -> None:
    """It answers a question you have *while deciding something else* -- which
    layout did this card resolve to -- so it opens over the view you were on.
    A navigation away and back is a poor way to look something up."""
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    payload = TestClient(create_app(config)).get("/api/config").json()
    assert payload["groups"], "every resolved setting, grouped by where it applies"
    assert {"where", "rows", "focused"} <= set(payload["groups"][0])


def test_the_source_in_force_comes_first(pdf_source: Config) -> None:
    """With fifty of them, landing at the top of an alphabetical list and
    scrolling is not an answer."""
    from fastapi.testclient import TestClient

    from anki_math_forge.app import create_app

    client = TestClient(create_app(pdf_source))
    payload = client.get("/api/config?source=book").json()
    assert payload["groups"][0]["where"] == "source: book"
    assert payload["groups"][0]["focused"]
