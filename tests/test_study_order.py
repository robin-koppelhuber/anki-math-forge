"""`[cards] study_order`: the sort key as a declared, reorderable list.

The order Anki introduces new cards in used to be a hard-coded tuple, a
sentence in the guide and a paragraph in the config comments, and only the
tuple decided anything. These are the tests that the three cannot drift again,
and that reordering them from the canvas writes the file rather than a cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge import model, study, sync
from anki_math_forge.app import create_app
from anki_math_forge.config import Config, ConfigError
from test_order import card

# -- the declaration -------------------------------------------------------


def test_a_partial_order_is_completed_not_refused() -> None:
    """Naming two criteria is a statement about those two.

    The list grows, so a config written today has to keep working when a
    fourth criterion is added: the new one arrives as the least significant
    key rather than reshuffling a deck somebody is halfway through.
    """
    resolved = [c.name for c in study.resolve(["printed"])]

    assert resolved[0] == "printed"
    assert sorted(resolved) == sorted(study.DEFAULT)


def test_an_unknown_criterion_is_refused() -> None:
    """A typo reads exactly like the setting doing nothing."""
    with pytest.raises(study.StudyOrderError, match="hardness"):
        study.validate(["frequency", "hardness"])


def test_a_criterion_named_twice_is_refused() -> None:
    with pytest.raises(study.StudyOrderError, match="twice"):
        study.validate(["frequency", "frequency"])


def test_every_criterion_says_what_it_does() -> None:
    """The panel renders these, so an empty one is a blank row on screen."""
    for criterion in study.CRITERIA:
        assert criterion.label and criterion.sense and criterion.detail
        assert criterion.unset, f"{criterion.name} must name what an ungraded card is"


# -- what it changes -------------------------------------------------------


def test_reordering_the_criteria_reorders_the_deck(config: Config) -> None:
    """The whole point: easiest-first can outrank most-useful-first."""
    card(config, "aaa111", frequency="rare", derivation="definitional")
    card(config, "bbb222", frequency="core", derivation="long")
    cards = model.load_all(config.cards_dir)

    useful_first = [c.uid for c in sync.in_study_order(cards, {}, ("frequency", "derivation"))]
    easiest_first = [c.uid for c in sync.in_study_order(cards, {}, ("derivation", "frequency"))]

    assert useful_first == ["bbb222", "aaa111"]
    assert easiest_first == ["aaa111", "bbb222"]


def test_requires_still_outranks_every_criterion(config: Config) -> None:
    """It is not a tiebreak and cannot be ranked third, whatever the order."""
    card(config, "aaa111", frequency="core", derivation="definitional", requires=["bbb222"])
    card(config, "bbb222", frequency="rare", derivation="long")
    cards = model.load_all(config.cards_dir)

    for order in (("frequency", "derivation"), ("derivation", "frequency"), ("printed",)):
        uids = [c.uid for c in sync.in_study_order(cards, {}, order)]
        assert uids == ["bbb222", "aaa111"], f"{order} let a card precede its prerequisite"


def test_the_uid_still_settles_a_tie(config: Config) -> None:
    """Two machines must build the same deck out of the same files."""
    card(config, "bbb222", unit="demo:1.1:9")
    card(config, "aaa111", unit="demo:1.1:9")
    cards = model.load_all(config.cards_dir)

    assert [c.uid for c in sync.in_study_order(cards, {}, ("printed",))] == ["aaa111", "bbb222"]


def test_inherited_from_names_the_card_that_pulled_it_forward(config: Config) -> None:
    """"12 places earlier" with nothing named is not a fact you can act on."""
    card(config, "aaa111", frequency="core", derivation="definitional", requires=["bbb222"])
    card(config, "bbb222", frequency="rare", derivation="long")
    card(config, "ccc333", frequency="common", derivation="short")
    cards = model.load_all(config.cards_dir)

    owed = sync.inherited_from(cards, {})

    assert owed == {"bbb222": "aaa111"}, "only the promoted prerequisite, and who promoted it"


# -- the config ------------------------------------------------------------


def test_the_default_is_the_declared_order(config: Config) -> None:
    assert config.study_order == study.DEFAULT


def declare(repo: Path, body: str) -> None:
    """Put `body` inside the fixture's existing `[cards]` table.

    A second `[cards]` header is not valid TOML, so a test that appended one
    was checking the parser's error message rather than this setting.
    """
    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    (repo / "forge.toml").write_text(
        toml.replace("[cards]\n", f"[cards]\n{body}\n", 1), encoding="utf-8"
    )


def test_a_misspelled_criterion_fails_at_load(repo: Path) -> None:
    declare(repo, 'study_order = ["frequency", "hardness"]')

    with pytest.raises(ConfigError, match="hardness"):
        config_mod.load(repo)


def test_writing_it_keeps_every_other_byte(repo: Path) -> None:
    """A line edit, not a re-dump. This config is mostly commentary, and
    re-serialising it from `tomllib` would delete every word of that."""
    before = (repo / "forge.toml").read_text(encoding="utf-8")
    assert "# A convention belongs to the source" in before, "nothing to preserve"

    config_mod.save_study_order(repo, ["printed", "frequency", "derivation"])
    after = (repo / "forge.toml").read_text(encoding="utf-8")

    assert config_mod.load(repo).study_order == ("printed", "frequency", "derivation")
    for line in before.splitlines():
        if line.strip().startswith("#"):
            assert line in after, f"comment lost: {line}"


def test_writing_it_twice_leaves_one_line(repo: Path) -> None:
    config_mod.save_study_order(repo, ["printed"])
    config_mod.save_study_order(repo, ["derivation"])
    body = (repo / "forge.toml").read_text(encoding="utf-8")

    assert body.count("study_order =") == 1
    assert config_mod.load(repo).study_order[0] == "derivation"


def test_it_replaces_a_hand_written_multi_line_array(repo: Path) -> None:
    """Somebody may have typed it across three lines. Consuming only the first
    would leave a stray `]` behind and the file would stop parsing."""
    declare(repo, 'study_order = [\n  "printed",\n  "frequency",\n]')
    assert config_mod.load(repo).study_order[0] == "printed"

    config_mod.save_study_order(repo, ["derivation", "printed", "frequency"])

    assert config_mod.load(repo).study_order == ("derivation", "printed", "frequency")
    assert (repo / "forge.toml").read_text(encoding="utf-8").count("study_order") == 1


def test_it_creates_the_cards_table_when_there_is_none(tmp_path: Path) -> None:
    (tmp_path / "forge.toml").write_text('[repo]\ncards_dir = "cards"\n', encoding="utf-8")

    config_mod.save_study_order(tmp_path, ["printed"])

    assert config_mod.load(tmp_path).study_order[0] == "printed"


# -- the panel's API -------------------------------------------------------


@pytest.fixture
def client(config: Config) -> TestClient:
    return TestClient(create_app(config))


def test_the_canvas_carries_the_whole_order(config: Config, client: TestClient) -> None:
    """Every card in the source, not only the drawn ones.

    What the canvas leaves out is exactly the cards that depend on nothing.
    A panel that showed only what is drawn would be a second picture of the
    picture.
    """
    card(config, "aaa111", frequency="core", derivation="definitional", requires=["bbb222"])
    card(config, "bbb222", frequency="rare", derivation="long")
    card(config, "ccc333", frequency="common", derivation="short")

    payload = client.get("/api/graph/demo").json()
    order = payload["order"]

    assert [row["id"] for row in order["cards"]] == ["bbb222", "aaa111", "ccc333"]
    assert [c["name"] for c in order["criteria"]] == list(study.DEFAULT)
    # `ccc333` is on nobody's `requires`, so the canvas does not draw it.
    drawn = {row["id"]: row["drawn"] for row in order["cards"]}
    assert drawn == {"aaa111": True, "bbb222": True, "ccc333": False}


def test_a_row_says_what_requires_did_to_it(config: Config, client: TestClient) -> None:
    card(config, "aaa111", frequency="core", derivation="definitional", requires=["bbb222"])
    card(config, "bbb222", frequency="rare", derivation="long")

    rows = {r["id"]: r for r in client.get("/api/graph/demo").json()["order"]["cards"]}

    assert rows["bbb222"]["shift"] == 1, "the rule alone would have put it second"
    assert rows["bbb222"]["owes"] == "aaa111"
    assert rows["aaa111"]["shift"] == -1


def test_reordering_writes_the_file_and_takes_effect(config: Config, client: TestClient) -> None:
    """A control that needs a restart to do anything reads as a control that
    does not work, which is why the app re-reads this one setting."""
    card(config, "aaa111", frequency="rare", derivation="definitional")
    card(config, "bbb222", frequency="core", derivation="long")
    assert [r["id"] for r in client.get("/api/graph/demo").json()["order"]["cards"]] == [
        "bbb222",
        "aaa111",
    ]

    written = client.post("/api/study-order", json={"order": ["derivation", "frequency"]})

    assert written.status_code == 200
    assert written.json()["order"] == ["derivation", "frequency", "printed"]
    assert config_mod.load(config.root).study_order[0] == "derivation"
    after = client.get("/api/graph/demo").json()["order"]
    assert [r["id"] for r in after["cards"]] == ["aaa111", "bbb222"], "same process, new order"


def test_an_unknown_criterion_is_refused_by_the_endpoint(client: TestClient) -> None:
    refused = client.post("/api/study-order", json={"order": ["frequency", "hardness"]})

    assert refused.status_code == 400
    assert "hardness" in refused.json()["error"]


def test_the_canvas_being_off_takes_the_panel_with_it(repo: Path) -> None:
    """One guard on every door into the canvas, and this is one of its doors."""
    toml = (repo / "forge.toml").read_text(encoding="utf-8")
    (repo / "forge.toml").write_text(
        toml.replace("[app]\n", "[app]\ngraph = false\n", 1), encoding="utf-8"
    )
    off = TestClient(create_app(config_mod.load(repo)))

    assert off.post("/api/study-order", json={"order": ["printed"]}).status_code == 404
