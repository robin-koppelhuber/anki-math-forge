"""The order new cards are introduced in: gradings, source order, `requires`."""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import check, model, sync
from anki_math_forge.config import Config


def card(
    config: Config,
    uid: str,
    *,
    unit: str = "demo:1.1:2",
    frequency: str = "core",
    derivation: str = "short",
    requires: list[str] | None = None,
    status: str = "draft",
) -> Path:
    path = config.cards_dir / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"uid: {uid}",
        "type: identity",
        f"status: {status}",
        'source: "somewhere"',
        f'unit: "{unit}"',
        f"frequency: {frequency}",
        f"derivation: {derivation}",
    ]
    if requires is not None:
        lines.append("requires: [" + ", ".join(requires) + "]")
    lines += ["tags: []", "verify: false", "---", "", "## front", "$X$", "", "## back", "$Y$", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def order(config: Config, positions: dict[str, int] | None = None) -> list[str]:
    cards = model.load_all(config.cards_dir)
    return [c.uid for c in sync.in_study_order(cards, positions)]


# -- the third key used to be a hash --------------------------------------


def test_within_a_grade_the_source_order_decides(config: Config) -> None:
    """It used to be `uid`, so inside a bucket the order was noise: eq. 108
    could be introduced seventeen cards before the eq. 99 it is built on."""
    card(config, "zzz999", unit="demo:1.1:2")
    card(config, "aaa111", unit="demo:1.1:3")
    positions = {"demo:1.1:2": 0, "demo:1.1:3": 1}

    assert order(config, positions) == ["zzz999", "aaa111"], "printed order, not hash order"


def test_grades_still_outrank_the_source_order(config: Config) -> None:
    card(config, "aaa111", unit="demo:1.1:2", frequency="rare")
    card(config, "zzz999", unit="demo:1.1:3", frequency="core")

    assert order(config, {"demo:1.1:2": 0, "demo:1.1:3": 1}) == ["zzz999", "aaa111"]


def test_source_positions_number_units_in_reading_order(config: Config) -> None:
    from anki_math_forge import extract

    extract.run(config, "demo")
    positions = sync.source_positions(config)
    ids = list(positions)
    assert ids == sorted(ids, key=lambda i: positions[i])
    assert len(set(positions.values())) == len(positions), "no two units share a position"


# -- requires -------------------------------------------------------------


def test_a_prerequisite_comes_first_however_it_is_graded(config: Config) -> None:
    card(config, "aaa111", frequency="core", requires=["zzz999"])
    card(config, "zzz999", frequency="rare")

    assert order(config) == ["zzz999", "aaa111"]


def test_the_prerequisite_is_pulled_forward_not_the_result_pushed_back(config: Config) -> None:
    """Respecting the dependency by demoting the core card would honour the
    graph and make the deck worse."""
    card(config, "aaa111", frequency="core", requires=["zzz999"])
    card(config, "zzz999", frequency="rare")
    for i, uid in enumerate(("bbb222", "ccc333", "ddd444")):
        card(config, uid, frequency="common", unit=f"demo:1.1:{i}")

    result = order(config)
    assert result[:2] == ["zzz999", "aaa111"], "the pair leads, the rare one first"


def test_a_chain_of_prerequisites_is_respected(config: Config) -> None:
    card(config, "aaa111", requires=["bbb222"])
    card(config, "bbb222", requires=["ccc333"], frequency="rare")
    card(config, "ccc333", frequency="rare", derivation="long")

    assert order(config) == ["ccc333", "bbb222", "aaa111"]


def test_an_unknown_prerequisite_does_not_strand_the_card(config: Config) -> None:
    """`sync` orders only what is approved, so a prerequisite still in draft
    must not remove everything built on it from the queue."""
    card(config, "aaa111", requires=["nosuch"])

    assert order(config) == ["aaa111"]


def test_a_cycle_still_places_every_card(config: Config) -> None:
    """`check` refuses one; the ordering must not drop cards on the floor."""
    card(config, "aaa111", requires=["bbb222"])
    card(config, "bbb222", requires=["aaa111"])

    assert sorted(order(config)) == ["aaa111", "bbb222"]


# -- requires is not card content -----------------------------------------


def test_requires_does_not_un_approve(config: Config) -> None:
    """A reviewer approving a card is not approving its position in the queue.
    Hashing it would re-review the deck on every refinement of the graph."""
    path = card(config, "aaa111")
    loaded = model.load(path)
    loaded.approve()
    loaded.save()
    before = loaded.content_hash()

    loaded.frontmatter["requires"] = ["bbb222"]

    assert loaded.content_hash() == before
    assert loaded.effective_status == "approved"


def test_requires_round_trips_through_the_file(config: Config) -> None:
    path = card(config, "aaa111", requires=["bbb222", "ccc333"])
    loaded = model.load(path)
    assert loaded.requires == ["bbb222", "ccc333"]
    loaded.save()
    assert model.load(path).requires == ["bbb222", "ccc333"], "survives a rewrite"
    assert model.parse(loaded.render()).render() == loaded.render(), "byte-stable"


# -- check ----------------------------------------------------------------


def findings(config: Config) -> dict[str, str]:
    return {f.code: f.message for f in check.check_deck(model.load_all(config.cards_dir), config)}


def test_an_unknown_prerequisite_is_an_error(config: Config) -> None:
    """The ordering ignores what it cannot resolve, so a typo would look like
    a graph that simply had no effect."""
    card(config, "aaa111", requires=["nosuch"])
    assert "requires-unknown" in findings(config)


def test_requiring_yourself_is_an_error(config: Config) -> None:
    card(config, "aaa111", requires=["aaa111"])
    assert "requires-self" in findings(config)


def test_a_cycle_is_an_error_naming_the_loop(config: Config) -> None:
    card(config, "aaa111", requires=["bbb222"])
    card(config, "bbb222", requires=["aaa111"])

    message = findings(config)["requires-cycle"]
    assert "aaa111" in message and "bbb222" in message


def test_an_unapproved_prerequisite_only_warns(config: Config) -> None:
    """Blocking would be wrong: it is a real state on the way to approving
    both, and sync introducing the card without its foundation is worth
    knowing rather than refusing."""
    path = card(config, "aaa111", requires=["bbb222"])
    approved = model.load(path)
    approved.approve()
    approved.save()
    card(config, "bbb222")

    found = [f for f in check.check_deck(model.load_all(config.cards_dir), config)]
    warned = [f for f in found if f.code == "requires-unapproved"]
    assert warned and warned[0].level == check.WARN
    assert not [f for f in found if f.code.startswith("requires-") and f.level == check.ERROR]


def test_a_source_whose_order_means_nothing_gets_no_positions(repo: Path) -> None:
    """Following a meaningless print order is worse than not following one:
    it looks deliberate."""
    from anki_math_forge import config as config_mod
    from anki_math_forge import extract

    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    # `[sources.demo]` already exists, so put the key inside it.
    toml = toml.replace("[sources.demo]", '[sources.demo]\norder = "none"', 1)
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    config = config_mod.load(repo)
    extract.run(config, "demo")

    assert sync.source_positions(config) == {}


def test_sources_are_numbered_in_the_order_the_config_lists_them(repo: Path) -> None:
    """Not alphabetically: which source leads is a decision you make by
    editing the config."""
    from anki_math_forge import config as config_mod
    from anki_math_forge import extract

    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    toml += '\n[sources.aaa]\ntitle = "A"\n'
    (repo / "forge.toml").write_text(toml, encoding="utf-8")
    config = config_mod.load(repo)
    extract.run(config, "demo")
    # `demo` is listed first in the base config, so it keeps the low numbers
    # even though "aaa" sorts before it.
    positions = sync.source_positions(config)
    assert positions and all(unit.startswith("demo:") for unit in positions)
    assert min(positions.values()) == 0
