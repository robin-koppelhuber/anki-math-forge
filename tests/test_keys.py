"""Shortcuts: declared once, configurable, and the same in all three places.

The keys used to be written down three times per view -- bound in the view's
JavaScript, listed in its footer legend, and explained in the guide -- with two
regex tests holding them together, neither of which covered the graph view.
`app/keys.py` is the declaration now, and these are the properties that keeps.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import config as config_mod
from anki_math_forge.app import create_app
from anki_math_forge.app import keys as keymod
from anki_math_forge.config import Config

APP = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app"


def deck(config: Config) -> Config:
    """A repo with a card in it, so the views render themselves rather than
    the "nothing here yet" page -- which deliberately shows a three-key legend
    now, because three keys are what it binds."""
    path = config.cards_dir / "demo" / "aaa111-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: aaa111\ntype: identity\nstatus: draft\n"
        'unit: "demo:2.4:61"\n---\n\n## front\n\n$a$\n\n## back\n\n$b$\n',
        encoding="utf-8",
    )
    return config



def test_a_key_means_one_thing_across_the_views_that_have_it() -> None:
    """The rule the defaults are chosen by, and worth more than any individual
    mnemonic: a key that approves here and shows everything there is a key you
    have to stop and think about.

    Measured before `keys.py`: the canvas bound `a` to *every card* against `a`
    for approve and accept, and `n` to *add a card* against `n` for the
    `@claude` note.
    """
    where: dict[str, set[str]] = {}
    for view in keymod.VIEWS:
        for entry in keymod.resolve(view, {}):
            where.setdefault(entry.key, set()).add(view)
    shared = {key for key, views in where.items() if len(views) > 1}
    assert shared - set(keymod.SHARED) == set(), (
        "a key in two views with nothing written down saying they are the same "
        f"thing: {sorted(shared - set(keymod.SHARED))}"
    )
    assert set(keymod.SHARED) - shared == set(), (
        f"declared as shared but is not: {sorted(set(keymod.SHARED) - shared)}"
    )


def test_every_declared_key_is_in_the_legend_or_is_a_second_key() -> None:
    """An entry with no label binds and stays out of the footer row, which is
    only for `Backspace` beside `Delete` and the arrows beside `j`/`k`."""
    for view in keymod.VIEWS:
        unlabelled = [k.action for k in keymod.resolve(view, {}) if not k.label]
        assert all(a.endswith("-alt") for a in unlabelled), (
            f"{view}: unlabelled and not an alias: {unlabelled}"
        )


def test_the_footer_and_the_bindings_are_one_list(config: Config) -> None:
    """The property the whole module exists for. Not "they agree" -- they
    cannot disagree, because the page renders both from `resolve`."""
    import json

    body = TestClient(create_app(deck(config))).get("/review").text
    footer = body[body.index('<footer class="bar keys">') : body.index("</footer>")]
    listed = set(re.findall(r"<b>([^<]+)</b>", footer))
    # Parsed rather than pattern-matched, because the failure this guards is
    # the payload not being parseable: Jinja autoescaped it once, `JSON.parse`
    # threw, and every key in the app silently stopped binding.
    start = body.index('type="application/json">') + len('type="application/json">')
    shipped = set(json.loads(body[start : body.index("</script>", start)]).values())
    for entry in keymod.resolve("review", {}):
        assert entry.key in shipped, f"{entry.action} not shipped to the browser"
        if entry.label:
            assert entry.key in listed, f"{entry.action} not in the footer"


@pytest.mark.parametrize("view", keymod.VIEWS)
def test_the_script_binds_by_action_and_never_names_a_key(view: str) -> None:
    """The letter is a setting; the action is the contract. A script that
    mentions `a` is a script `[app.keys]` cannot reach."""
    js = (APP / "static" / f"{view}.js").read_text(encoding="utf-8")
    block = js[js.index("bindKeys({") : js.index("});", js.index("bindKeys({"))]
    handled = set(re.findall(r'^\s{2}"?([a-z][a-z-]*)"?[,:]', block, re.M))
    declared = {k.action for k in keymod.BY_VIEW[view]}
    assert handled == declared, (
        f"{view}: declared with no handler {sorted(declared - handled)}, "
        f"handled but undeclared {sorted(handled - declared)}"
    )


# -- configuring one --------------------------------------------------------


def with_keys(repo: Path, table: str) -> None:
    """Append `[app.keys]`, which is where a TOML sub-table has to go.

    Written just after the `[app]` header instead, it swallows every bare key
    below it: `katex_base` became an entry in the keymap and the load failed
    with `no such action: katex_base`. Correct of it, and the reason
    `forge.toml` shows the table at the end of the section.
    """
    path = repo / "forge.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n[app.keys]\n{table}\n", encoding="utf-8"
    )


def test_a_remapped_key_moves_the_binding_and_the_legend_together(
    config: Config,
) -> None:
    moved = dataclasses.replace(deck(config), keys={"approve": "y"})
    body = TestClient(create_app(moved)).get("/review").text
    assert "<b>y</b> approve" in body
    assert '"approve": "y"' in body
    assert "<b>a</b> approve" not in body


def test_a_remapped_key_reaches_the_guide_too(config: Config) -> None:
    """The guide is where a key is explained. Left hard-coded it would teach
    the default to somebody who had configured something else."""
    from anki_math_forge import extract

    extract.run(config, "demo")
    moved = dataclasses.replace(config, keys={"queue": "1"})
    body = TestClient(create_app(moved)).get("/units").text
    explained = body[body.index("what each key does") :]
    assert "<b>1</b>" in explained
    assert "<b>q</b> queue" not in body


def test_an_override_naming_no_action_is_refused_at_load() -> None:
    """The symptom of a typo is that the shortcut does not change, which is
    indistinguishable from the feature not working. So it is an error, like an
    unknown `layout`, rather than a key that is quietly ignored."""
    with pytest.raises(keymod.KeyError_) as caught:
        keymod.validate({"aprove": "y"})
    assert "no such action" in str(caught.value)
    assert "approve" in str(caught.value), "and it lists the ones that exist"


def test_two_actions_on_one_key_in_one_view_are_refused() -> None:
    """One of the two would never run, and which one depends on dict order."""
    with pytest.raises(keymod.KeyError_) as caught:
        keymod.validate({"approve": "r"})
    assert "bound to both" in str(caught.value)


def test_the_same_key_in_two_views_is_fine() -> None:
    """Each view binds its own map, so there is no collision to have. `q`
    queues a unit and is free on the review view."""
    keymod.validate({"editor": "q"})


def test_an_empty_key_is_refused() -> None:
    with pytest.raises(keymod.KeyError_):
        keymod.validate({"approve": ""})


def test_it_is_read_from_the_file(repo: Path) -> None:
    with_keys(repo, 'approve = "y"')
    assert config_mod.load(repo).keys == {"approve": "y"}


def test_a_bad_table_stops_the_load_rather_than_the_first_request(repo: Path) -> None:
    with_keys(repo, 'nope = "y"')
    with pytest.raises(keymod.KeyError_):
        config_mod.load(repo)


# -- undo is per view -------------------------------------------------------


def test_each_view_keeps_its_own_undo_stack() -> None:
    """They shared one `sessionStorage` key while pushing entries of different
    shapes: a unit step is `{id, before}`, a card step is `{uid, before}`.

    Triage three units, switch to the review view, press undo: it popped a
    *unit* step, read `step.uid` off it as undefined, and posted to
    `/api/cards/undefined/restore`. A 400 either way, and the step was popped
    and saved before the request went out, so each press destroyed one entry of
    the other view's history.
    """
    app_js = (APP / "static" / "app.js").read_text(encoding="utf-8")
    assert "function undoKey(scope)" in app_js
    for view, shape in (("units", "id"), ("review", "uid")):
        js = (APP / "static" / f"{view}.js").read_text(encoding="utf-8")
        assert f'loadUndo("{view}")' in js
        assert f'saveUndo("{view}"' in js
        assert f"step.{shape}" in js, "and the two shapes really do differ"


def test_the_nothing_here_yet_page_binds_the_keys_it_lists(config: Config) -> None:
    """It extends the same base as the other views, so it renders the same
    header, rails and footer -- but it overrode no `scripts` block, so
    `bindKeys` was never called and not one of the fifteen keys its footer
    listed did anything. The first screen anybody sees was the one that lied
    about how to drive it.

    Three now, on both sides: `EMPTY_VIEW_KEYS` narrows the legend and
    `empty.js` binds the same three, so neither can advertise what the other
    does not do.
    """
    from anki_math_forge.app import EMPTY_VIEW_KEYS

    body = TestClient(create_app(config)).get("/review").text
    assert "no cards here yet" in body, "the fixture repo has no cards"
    assert '/static/empty.js' in body, "the page loads something that binds"

    footer = body[body.index('<footer class="bar keys">') : body.index("</footer>")]
    listed = set(re.findall(r"<b>([^<]+)</b>", footer))
    expected = {
        entry.key
        for entry in keymod.resolve("review", {})
        if entry.action in EMPTY_VIEW_KEYS
    }
    assert listed == expected, f"listed {sorted(listed)}, binds {sorted(expected)}"

    js = (APP / "static" / "empty.js").read_text(encoding="utf-8")
    block = js[js.index("bindKeys({") : js.index("});", js.index("bindKeys({"))]
    handled = set(re.findall(r"^\s{2}([a-z][a-z-]*):", block, re.M))
    assert handled == set(EMPTY_VIEW_KEYS), f"binds {sorted(handled)}"
