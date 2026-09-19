"""Whether whoever writes a card may look things up on the web.

Off everywhere unless granted, and the default is the point. A card is supposed
to say what *this source* says -- hypotheses and notation included -- and the
web has a cleaner statement of nearly every result on these pages. One of those
substituted for the printed one produces a card that reads *better* than a
correct one, right up until the condition the paper had and the general version
does not turns out to be what the card was for. That failure is invisible at
review time, which is why the permission is a decision somebody takes rather
than a default somebody inherits.

Four levels, most specific first: the card, its unit, the source, the repo.
Same shape as `context_pages`, and for the same reason -- triage is where you
can see that *this* unit cites a result the paper never states.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import cli, context, model
from anki_math_forge import config as config_mod
from anki_math_forge.config import Config, ConfigError
from anki_math_forge.extract import source_text_path
from anki_math_forge.ledger import Ledger, Locator, Unit


def _seed(config: Config, **unit_fields: object) -> None:
    led = Ledger(config.units_path("demo"))
    led.units.append(
        Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=1), **unit_fields)
    )
    led.save()
    path = source_text_path(config, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("## page 1\nbody\n", encoding="utf-8")


def _with_cards_key(repo: Path, line: str) -> Config:
    """Add a key to the fixture's existing `[cards]` table.

    Appending a second `[cards]` header is a TOML error, not an override, so
    the key has to go inside the block that is already there.
    """
    path = repo / "forge.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("[cards]\n", f"[cards]\n{line}\n", 1), encoding="utf-8")
    return config_mod.load(repo)


def _asked(config: Config) -> context.UnitContext:
    found = context.assemble(config, "demo:2.2:61")
    assert found is not None
    return found


def test_the_repo_default_is_no(config: Config) -> None:
    _seed(config)
    assert config.web is False
    assert _asked(config).web is False


def test_a_unit_may_be_granted_it(config: Config) -> None:
    """The level that matters: you grant it looking at the one unit that needs
    it, not across a book you have not finished reading."""
    _seed(config, web=True)
    asked = _asked(config)
    assert asked.web is True
    assert asked.web_from == "unit"


def test_a_unit_may_refuse_what_the_source_allows(config: Config, repo: Path) -> None:
    """Three states, not two. `False` on a unit is a refusal, and it has to
    outrank a source-wide grant or the grant would be unrevokable."""
    wider = _with_cards_key(repo, "web = true")
    _seed(wider, web=False)
    assert wider.web_for("demo") is True
    assert _asked(wider).web is False


def test_inheriting_is_not_the_same_as_refusing(config: Config, repo: Path) -> None:
    """`None` is the absence of a decision here. Collapsing it into `no` would
    make a source-wide refusal impossible to lift for one unit and a
    source-wide grant impossible to revoke."""
    _seed(config, web=None)
    assert _asked(config).web_from == "repo"


def test_it_is_not_written_when_inherited(config: Config) -> None:
    """A 751-unit ledger of `"web": null` is a wall of lines all saying that
    nobody has said anything."""
    _seed(config)
    assert '"web"' not in config.units_path("demo").read_text(encoding="utf-8")


def test_it_survives_a_re_extraction(config: Config) -> None:
    """Human-owned, like `state` and `context_pages`. Re-segmenting must not
    quietly revoke a permission somebody granted."""
    _seed(config, web=True)
    led = Ledger.load(config.units_path("demo"))
    led.upsert([Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=1))])
    led.save()
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").web is True


def test_the_answer_is_spelled_out_for_whoever_writes_the_card(config: Config) -> None:
    """In both directions. An absent line would read as "nobody thought about
    it", and the whole value of the permission is that somebody did."""
    _seed(config)
    assert "No web access" in _asked(config).format()

    _seed(config, web=True)
    granted = _asked(config).format()
    assert "ALLOWED" in granted
    assert "`## notes`" in granted, "and say what came from off the page"


def test_the_cli_grants_and_revokes(repo: Path, capsys: object) -> None:
    config = config_mod.load(repo)
    _seed(config)
    args = ["--root", str(repo), "units", "--id", "demo:2.2:61", "--web"]

    cli.main([*args, "yes"])
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").web is True

    cli.main([*args, "inherit"])
    assert Ledger.load(config.units_path("demo")).get("demo:2.2:61").web is None
    assert "inherited" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_a_card_inherits_the_grant_made_to_its_unit(config: Config) -> None:
    """A grant made during triage that evaporated the moment a stub existed
    would be useless exactly where it was aimed: the pass that writes the card
    is the one it was granted for."""
    from anki_math_forge.app import _card_web

    _seed(config, web=True)
    card = model.Card(frontmatter={"uid": "aa11bb", "unit": "demo:2.2:61"}, sections=[])
    assert _card_web(card, config) is True


def test_a_card_may_refuse_what_its_unit_was_granted(config: Config) -> None:
    from anki_math_forge.app import _card_web

    _seed(config, web=True)
    card = model.Card(
        frontmatter={"uid": "aa11bb", "unit": "demo:2.2:61", "web": False}, sections=[]
    )
    assert _card_web(card, config) is False


def test_granting_it_does_not_un_approve_a_card(card_path: Path) -> None:
    """It is a permission granted to whoever writes the card, not a claim the
    card makes. `web` is outside `content_hash` for the same reason `requires`
    is: approving a card is not approving everything recorded beside it."""
    card = model.load(card_path)
    card.approve()

    card.set_grade("web", True)

    assert card.hash_matches()
    assert card.effective_status == "approved"


# -- the source's conventions, which is where `layout` went ------------------


def test_a_repo_wide_layout_is_refused_rather_than_ignored(repo: Path) -> None:
    """It was the repo-wide default for a matrix-calculus convention, which is
    a claim about every book in the deck including the ones nobody has read
    yet. Ignoring a value left there would leave `verify` checking against a
    guess while the file said otherwise -- the exact failure the key exists to
    prevent, arriving through silence instead."""
    with pytest.raises(ConfigError, match="no longer read"):
        _with_cards_key(repo, 'layout = "denominator"')


def test_a_source_declares_its_own_conventions(repo: Path) -> None:
    folder = repo / "projects" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("project.toml").write_text(
        'title = "A Book"\n\n[conventions]\nlayout = "numerator"\nentries = "complex"\n',
        encoding="utf-8",
    )
    config = config_mod.load(repo)

    assert config.layout_for("book") == "numerator"
    assert config.conventions_for("book")["entries"] == "complex"


def test_an_unrecognised_layout_is_still_refused(repo: Path) -> None:
    """The one convention anything acts on. An unrecognised value would read as
    "not denominator" and silently change what every derivative means."""
    folder = repo / "projects" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("project.toml").write_text(
        'title = "A Book"\n\n[conventions]\nlayout = "sideways"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="sideways"):
        config_mod.load(repo)


def test_the_older_top_level_layout_is_still_read(repo: Path) -> None:
    """A repo should not have to migrate in the same sitting as the tool."""
    folder = repo / "projects" / "book"
    folder.mkdir(parents=True, exist_ok=True)
    folder.joinpath("project.toml").write_text(
        'title = "A Book"\nlayout = "numerator"\n', encoding="utf-8"
    )
    assert config_mod.load(repo).layout_for("book") == "numerator"


def test_a_convention_nothing_acts_on_still_reaches_a_card_writer(config: Config) -> None:
    """`[conventions]` is open because what a source assumes is not a
    vocabulary this tool can enumerate. A key it has never heard of is still a
    fact somebody needs, so it is printed rather than dropped."""
    _seed(config)
    assert config.conventions_for("demo")["layout"] == "denominator"

    printed = _asked(config).format()
    assert "and what it declares as keys" in printed
    assert "layout" in printed
