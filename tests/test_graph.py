"""The dependency canvas: the graph, its layout, and where an arrangement is
kept (ROADMAP.md §1).

The canvas is drawn on a `<canvas>` and has no markup, so nothing here can
assert what it looks like. What these tests hold is everything the drawing
reads: the direction of an edge, which nodes are on screen, where each one
starts, and that a written arrangement survives a round trip and refuses a
stale write. A renamed field in the payload fails a test here rather than
blanking the screen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import graph as graph_mod
from anki_math_forge import model
from anki_math_forge.app import create_app, source_graph
from anki_math_forge.config import Config
from anki_math_forge.graph import Edge, Graph, Node, card_graph, layered
from anki_math_forge.model import Card, StaleFileError


def write(
    config: Config,
    uid: str,
    *,
    requires: list[str] | None = None,
    gist: str = "",
    status: str = "draft",
    source: str = "demo",
) -> Card:
    path = config.cards_dir / source / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = ""
    if requires:
        keys += "requires: [" + ", ".join(requires) + "]\n"
    if gist:
        keys += f"gist: {gist}\n"
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: {status}\n"
        f'unit: "{source}:2.4:61"\n{keys}---\n\n## front\n\n$a$\n\n## back\n\n$b$\n',
        encoding="utf-8",
    )
    return model.load(path)


# -- the graph --------------------------------------------------------------


def test_an_edge_runs_from_the_prerequisite_to_the_card_that_needs_it(
    config: Config,
) -> None:
    """The direction the key means, and the one that is easy to get backwards.

    `requires: [b]` on `a` says *b before a*. Drawn the other way the canvas
    reads right to left and every foundation looks like a conclusion.
    """
    base = write(config, "aaa111")
    built = write(config, "bbb222", requires=["aaa111"])
    graph = card_graph([base, built])
    assert graph.edges == [Edge(src="aaa111", dst="bbb222", kind="requires")]


def test_a_requires_naming_no_card_here_draws_no_node(config: Config) -> None:
    """`check` reports a dangling uid. A box on the canvas for something that
    does not exist would be the picture disagreeing with the lint about what
    the deck contains."""
    graph = card_graph([write(config, "aaa111", requires=["ffffff"])])
    assert [n.id for n in graph.nodes] == ["aaa111"]
    assert graph.edges == []


def test_a_card_naming_itself_is_not_an_edge(config: Config) -> None:
    """A self-loop draws an arrow from a box to itself and puts the node in its
    own layer forever. `check` reports it as `requires-self`."""
    assert card_graph([write(config, "aaa111", requires=["aaa111"])]).edges == []


def test_a_node_nobody_named_carries_no_label(config: Config) -> None:
    """Empty rather than a name built from the filename slug, which is a
    transliteration of the LaTeX and so the thing a caption spares you. The
    canvas shows the gap, which is also what says which cards to name."""
    graph = card_graph([write(config, "aaa111"), write(config, "bbb222", gist="the adjugate")])
    assert {n.id: n.label for n in graph.nodes} == {"aaa111": "", "bbb222": "the adjugate"}


def test_a_card_from_another_source_is_present_but_marked(config: Config) -> None:
    """`requires` may cross sources. Leaving the target out would draw a card
    whose foundation is elsewhere as a foundation itself, which is the one
    thing the picture is read for."""
    here = write(config, "aaa111", requires=["ccc333"])
    there = write(config, "ccc333", source="paper")
    kinds = {n.id: n.kind for n in card_graph([here, there], here="demo").nodes}
    assert kinds == {"aaa111": "card", "ccc333": "elsewhere"}


def test_the_default_picture_is_the_part_that_has_edges(config: Config) -> None:
    """What makes the view worth opening while the edges are few. Nine edges
    across 108 cards draws as ninety-nine isolated dots, which takes a whole
    window to say that almost nothing depends on anything."""
    cards = [
        write(config, "aaa111"),
        write(config, "bbb222", requires=["aaa111"]),
        write(config, "ccc333"),
    ]
    assert {n.id for n in card_graph(cards).connected().nodes} == {"aaa111", "bbb222"}


# -- the layout -------------------------------------------------------------


def chain(n: int) -> Graph:
    nodes = [Node(id=f"n{i}") for i in range(n)]
    edges = [Edge(src=f"n{i}", dst=f"n{i + 1}") for i in range(n - 1)]
    return Graph(nodes, edges)


def test_x_is_how_early_the_card_is_introduced() -> None:
    """The graph means "introduce this first", so the horizontal axis being
    "how early" is the reading that needs no explaining."""
    at = layered(chain(3))
    assert [at["n0"][0], at["n1"][0], at["n2"][0]] == [0.0, graph_mod.COLUMN, 2 * graph_mod.COLUMN]


def test_a_layer_is_the_longest_path_not_the_shortest() -> None:
    """`c` needs both `a` and `b`, and `b` needs `a`. Placed by the shortest
    path `c` would sit beside `b`, with an arrow from `a` jumping over it."""
    graph = Graph(
        [Node(id="a"), Node(id="b"), Node(id="c")],
        [Edge("a", "b"), Edge("a", "c"), Edge("b", "c")],
    )
    at = layered(graph)
    assert at["c"][0] == 2 * graph_mod.COLUMN


def test_the_order_within_a_layer_follows_the_study_order() -> None:
    """So a column agrees with the queue you would actually meet, rather than
    with the order the loader happened to walk the files in."""
    graph = Graph([Node(id="a"), Node(id="b"), Node(id="c")], [])
    assert [layered(graph, ["c", "a", "b"])[k][1] for k in ("c", "a", "b")] == [
        0.0,
        graph_mod.ROW,
        2 * graph_mod.ROW,
    ]


def test_it_is_deterministic() -> None:
    """Opening the view twice must not shuffle it. The id is the tiebreak
    rather than the input order, so two runs over the same deck agree even if
    the nodes arrived in a different sequence."""
    graph = Graph([Node(id="a"), Node(id="b"), Node(id="c")], [Edge("a", "b")])
    shuffled = Graph(list(reversed(graph.nodes)), list(graph.edges))
    assert layered(graph) == layered(shuffled)


def test_an_unconnected_card_moves_nothing_that_is_drawn() -> None:
    """The stability that matters, because it is the case that comes up: a
    card with no dependencies is added far more often than one with them, and
    in the default picture it is not drawn at all."""
    before = layered(chain(3).connected())
    grown = chain(3)
    grown.nodes.append(Node(id="loner"))
    assert layered(grown.connected()) == before


def test_a_cycle_terminates_rather_than_recursing_forever() -> None:
    """`check` refuses a cycle, but the app renders a repo nobody has linted,
    and a canvas that hangs the server is a worse answer than one drawn
    slightly wrong."""
    graph = Graph([Node(id="a"), Node(id="b")], [Edge("a", "b"), Edge("b", "a")])
    assert set(layered(graph)) == {"a", "b"}


# -- the arrangement on disk ------------------------------------------------


def test_positions_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"af5ca1": (120.0, 240.0)})
    assert graph_mod.load_positions(path) == {"af5ca1": (120.0, 240.0)}


def test_a_source_nobody_arranged_has_no_file(tmp_path: Path) -> None:
    """Nothing is written until somebody drags something, so a fresh source
    having no `graph.json` is the normal state and not an error."""
    assert graph_mod.load_positions(tmp_path / "graph.json") == {}


def test_the_file_is_one_node_per_line(tmp_path: Path) -> None:
    """It is committed, so a diff has to read as the boxes that moved. It also
    carries a version, which costs one line and gives the next change somewhere
    to live."""
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"bbb222": (10.0, 20.4), "aaa111": (0.0, 0.0)})
    text = path.read_text(encoding="utf-8")
    assert '"version": 1' in text
    assert '"aaa111": [0, 0],\n    "bbb222": [10, 20]' in text, text


def test_only_what_moved_is_written(tmp_path: Path) -> None:
    """A whole-map write loses a concurrent drag in another tab and buys
    nothing."""
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"aaa111": (1.0, 2.0), "bbb222": (3.0, 4.0)})
    after = graph_mod.move(path, {"bbb222": (30.0, 40.0)})
    assert after == {"aaa111": (1.0, 2.0), "bbb222": (30.0, 40.0)}


def test_putting_a_box_back_deletes_its_entry(tmp_path: Path) -> None:
    """Rather than recording where the layout currently puts it, which would
    freeze today's arrangement into the file and stop it being recomputed."""
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"aaa111": (1.0, 2.0)})
    assert graph_mod.move(path, {"aaa111": None}) == {}


def test_a_stale_write_is_refused(tmp_path: Path) -> None:
    """The same guard every other write in the app has: an editor open beside
    the browser is normal here, and silent clobbering is worse than a retry."""
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"aaa111": (1.0, 2.0)})
    with pytest.raises(StaleFileError):
        graph_mod.move(path, {"aaa111": (9.0, 9.0)}, expect_mtime_ns=1)


def test_expecting_no_file_is_a_precondition_rather_than_the_lack_of_one(
    tmp_path: Path,
) -> None:
    """Zero is what a reader is told when the source has no arrangement yet. A
    file that has appeared since belongs to somebody else's drag, and this
    reader's whole picture of where the boxes are is empty.

    Measured before this was fixed, against the real deck: a browser that
    loaded an unarranged source and posted twice had its second write accepted,
    because "0" read as no precondition at all.
    """
    path = tmp_path / "graph.json"
    assert graph_mod.move(path, {"aaa111": (1.0, 2.0)}, expect_mtime_ns=0)
    with pytest.raises(StaleFileError):
        graph_mod.move(path, {"bbb222": (3.0, 4.0)}, expect_mtime_ns=0)


# -- through the app --------------------------------------------------------


def test_the_payload_carries_every_field_the_canvas_reads(config: Config) -> None:
    """Renaming one of these in Python should fail here rather than blank the
    screen: the canvas has no markup, so nothing else would notice."""
    write(config, "aaa111", gist="the product of the eigenvalues")
    write(config, "bbb222", requires=["aaa111"])
    payload = source_graph(config, "demo")
    assert set(payload) >= {
        "source",
        "nodes",
        "edges",
        "layout",
        "positions",
        "mtime",
        "shown",
        "hidden",
        "total",
    }
    assert set(payload["nodes"][0]) == {"id", "label", "detail", "kind", "state", "href"}
    assert set(payload["edges"][0]) == {"src", "dst", "kind"}
    assert set(payload["layout"]) == {"aaa111", "bbb222"}


def test_the_view_says_what_it_left_out(config: Config) -> None:
    """A filtered view that does not report its filter reads as the whole
    picture, and "almost nothing depends on anything" is a real answer that
    should not be mistaken for an empty feature."""
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    write(config, "ccc333")
    assert source_graph(config, "demo")["hidden"] == 1
    assert source_graph(config, "demo", everything=True)["hidden"] == 0


def test_a_node_is_labelled_with_the_caption_the_review_view_shows(
    config: Config,
) -> None:
    """`card_gist`, so a card with no caption of its own is named by the unit
    it was written from, exactly as it is everywhere else."""
    write(config, "aaa111", gist="the adjugate in terms of the inverse")
    write(config, "bbb222", requires=["aaa111"])
    nodes = {n["id"]: n for n in source_graph(config, "demo")["nodes"]}
    assert nodes["aaa111"]["label"] == "the adjugate in terms of the inverse"
    assert nodes["aaa111"]["href"].endswith("#aaa111")


def test_the_api_serves_it(config: Config) -> None:
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    assert client.get("/graph?source=demo").status_code == 200
    assert len(client.get("/api/graph/demo").json()["edges"]) == 1


def test_dragging_a_box_writes_the_file_and_nothing_else(config: Config) -> None:
    """Invariant 2: the browser is one way in, not the way in. What a drag
    writes is a file you can read in a diff and edit by hand."""
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    before = client.get("/api/graph/demo").json()

    response = client.post(
        "/api/graph/demo/positions",
        json={"positions": {"aaa111": [120, 240]}, "mtime": before["mtime"]},
    )
    assert response.status_code == 200
    assert response.json()["positions"] == {"aaa111": [120.0, 240.0]}
    path = graph_mod.positions_path(config.sources_dir, "demo")
    assert graph_mod.load_positions(path) == {"aaa111": (120.0, 240.0)}
    assert client.get("/api/graph/demo").json()["positions"] == {"aaa111": [120.0, 240.0]}


def test_a_drag_against_a_changed_file_is_refused(config: Config) -> None:
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    graph_mod.save_positions(
        graph_mod.positions_path(config.sources_dir, "demo"), {"bbb222": (1.0, 1.0)}
    )
    response = client.post(
        "/api/graph/demo/positions",
        json={"positions": {"aaa111": [1, 1]}, "mtime": "1"},
    )
    assert response.status_code == 409
    assert response.json()["stale"] is True


def test_a_drag_that_thought_the_source_was_unarranged_is_refused(
    config: Config,
) -> None:
    """The route reads "0" as *expect no file*, unlike `_expected_mtime`, which
    reads it as no precondition. That is right for a card, which exists by the
    time anything writes to it, and wrong here: a source with no arrangement is
    the ordinary starting state, and it is exactly when two tabs both think
    they are the first to drag something."""
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    first = client.post(
        "/api/graph/demo/positions", json={"positions": {"aaa111": [1, 1]}, "mtime": "0"}
    )
    assert first.status_code == 200
    second = client.post(
        "/api/graph/demo/positions", json={"positions": {"aaa111": [9, 9]}, "mtime": "0"}
    )
    assert second.status_code == 409


def test_no_position_reaches_a_card_file(config: Config) -> None:
    """Positions are a view preference. In frontmatter they would be hashed,
    and dragging a box would un-approve a card."""
    card = write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    assert card.path is not None
    before = card.path.read_text(encoding="utf-8")
    client.post(
        "/api/graph/demo/positions",
        json={"positions": {"aaa111": [120, 240]}, "mtime": "0"},
    )
    assert card.path.read_text(encoding="utf-8") == before


# -- drawing an edge --------------------------------------------------------


def two(config: Config) -> TestClient:
    write(config, "aaa111", gist="the product of the eigenvalues")
    write(config, "bbb222", gist="the determinant")
    return TestClient(create_app(config))


def needs(config: Config, uid: str) -> list[str]:
    card = next(c for c in model.load_all(config.cards_dir) if c.uid == uid)
    return card.requires


def test_an_arrow_writes_requires_on_the_card_that_needs_the_other(
    config: Config,
) -> None:
    """The direction, once more, at the layer that writes a file. `requires`
    lives on the dependent and the arrow points at it, so the two read
    opposite ways and this is where that gets mixed up."""
    client = two(config)
    assert client.post("/api/cards/bbb222/requires", json={"add": "aaa111"}).status_code == 200
    assert needs(config, "bbb222") == ["aaa111"]
    assert needs(config, "aaa111") == []

    edges = client.get("/api/graph/demo").json()["edges"]
    assert edges == [{"src": "aaa111", "dst": "bbb222", "kind": "requires"}]


def test_linking_two_approved_cards_demotes_neither(config: Config) -> None:
    """The fact the whole feature rests on: `requires` is outside
    `content_hash` under the current rule *and* the legacy one, so an arrow
    drawn between two approved cards is not an edit to either.

    Stamped the way the deck is stamped, with the legacy digest, because a
    fresh card's two digests coincide and would prove nothing.
    """
    for uid in ("aaa111", "bbb222"):
        card = model.load(
            write(config, uid, status="draft", gist="x").path  # type: ignore[arg-type]
        )
        card.frontmatter["frequency"] = "core"
        card.frontmatter["content_hash"] = card.content_hash(legacy=True)
        card.frontmatter["status"] = "approved"
        card.save()

    client = TestClient(create_app(config))
    payload = client.post("/api/cards/bbb222/requires", json={"add": "aaa111"}).json()
    assert payload["card"]["status"] == "approved"
    after = [c for c in model.load_all(config.cards_dir) if c.uid in ("aaa111", "bbb222")]
    assert all(c.hash_matches() and c.effective_status == "approved" for c in after)


def test_a_cycle_is_refused_before_the_write_and_names_the_loop(
    config: Config,
) -> None:
    """`check` reports a cycle after the fact. A card file written into a state
    the lint refuses is a worse answer than a refusal at the drag, and being
    told "that would make a cycle" without being told which one leaves you
    hunting through the graph you opened because you could not see it."""
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    response = client.post("/api/cards/aaa111/requires", json={"add": "bbb222"})
    assert response.status_code == 400
    assert "cycle" in response.json()["detail"]
    assert "aaa111 needs bbb222 needs aaa111" in response.json()["detail"]
    assert needs(config, "aaa111") == [], "nothing was written"


def test_a_longer_cycle_is_refused_too(config: Config) -> None:
    client = two(config)
    write(config, "ccc333")
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    client.post("/api/cards/ccc333/requires", json={"add": "bbb222"})
    response = client.post("/api/cards/aaa111/requires", json={"add": "ccc333"})
    assert response.status_code == 400
    assert "aaa111 needs ccc333 needs bbb222 needs aaa111" in response.json()["detail"]


def test_a_card_cannot_be_made_to_need_itself(config: Config) -> None:
    client = two(config)
    assert client.post("/api/cards/aaa111/requires", json={"add": "aaa111"}).status_code == 400


def test_an_edge_to_a_card_that_is_not_here_is_refused(config: Config) -> None:
    """`check` calls this `requires-unknown`: the ordering ignores what it
    cannot resolve, so a typo would quietly do nothing."""
    client = two(config)
    assert client.post("/api/cards/aaa111/requires", json={"add": "ffffff"}).status_code == 400


def test_drawing_the_same_arrow_twice_writes_one(config: Config) -> None:
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    assert needs(config, "bbb222") == ["aaa111"]


def test_removing_the_last_one_takes_the_key_off(config: Config) -> None:
    """Rather than leaving `requires: []`, which reads as a considered empty
    list instead of a card with no dependencies."""
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    client.post("/api/cards/bbb222/requires", json={"remove": "aaa111"})
    card = next(c for c in model.load_all(config.cards_dir) if c.uid == "bbb222")
    assert "requires" not in card.frontmatter


def test_an_edge_write_against_a_changed_card_is_refused(config: Config) -> None:
    """The same guard every other card write has."""
    client = two(config)
    response = client.post(
        "/api/cards/bbb222/requires", json={"add": "aaa111", "mtime": "1"}
    )
    assert response.status_code == 409
    assert response.json()["stale"] is True


def test_it_takes_exactly_one_of_add_or_remove(config: Config) -> None:
    client = two(config)
    assert client.post("/api/cards/bbb222/requires", json={}).status_code == 400
    assert (
        client.post(
            "/api/cards/bbb222/requires", json={"add": "aaa111", "remove": "aaa111"}
        ).status_code
        == 400
    )


# -- putting a card on the canvas -------------------------------------------


def test_a_card_with_no_edges_is_drawn_once_it_has_a_position(config: Config) -> None:
    """How an unconnected card gets onto the canvas so it can be connected.
    Its position is the only statement of intent available, and it says keep
    showing me this -- so adding one is a write the file and the API already
    do, rather than a second list of pinned ids saying the same thing."""
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    write(config, "ccc333", gist="the trace")
    assert "ccc333" not in {n["id"] for n in client.get("/api/graph/demo").json()["nodes"]}

    now = client.get("/api/graph/demo").json()
    client.post(
        "/api/graph/demo/positions",
        json={"positions": {"ccc333": [400, 400]}, "mtime": now["mtime"]},
    )
    assert "ccc333" in {n["id"] for n in client.get("/api/graph/demo").json()["nodes"]}


def test_forgetting_its_position_takes_it_off_again(config: Config) -> None:
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    write(config, "ccc333")
    client.post(
        "/api/graph/demo/positions", json={"positions": {"ccc333": [400, 400]}, "mtime": "0"}
    )
    now = client.get("/api/graph/demo").json()["mtime"]
    client.post("/api/graph/demo/positions", json={"positions": {"ccc333": None}, "mtime": now})
    assert "ccc333" not in {n["id"] for n in client.get("/api/graph/demo").json()["nodes"]}


def test_a_connected_card_stays_drawn_when_its_position_is_forgotten(
    config: Config,
) -> None:
    """Same write, two consequences, and this is the one that must not become
    "the box vanished": forgetting where a connected box was put sends it back
    to the computed place, it does not take it off the canvas."""
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    client.post(
        "/api/graph/demo/positions", json={"positions": {"aaa111": [9, 9]}, "mtime": "0"}
    )
    now = client.get("/api/graph/demo").json()["mtime"]
    client.post("/api/graph/demo/positions", json={"positions": {"aaa111": None}, "mtime": now})
    assert "aaa111" in {n["id"] for n in client.get("/api/graph/demo").json()["nodes"]}


def test_the_picker_is_offered_what_is_not_drawn(config: Config) -> None:
    client = two(config)
    client.post("/api/cards/bbb222/requires", json={"add": "aaa111"})
    write(config, "ccc333", gist="the trace")
    absent = client.get("/api/graph/demo").json()["absent"]
    assert [n["id"] for n in absent] == ["ccc333"]
    assert absent[0]["label"] == "the trace", "picked by caption, not by uid"


# -- the opt-out ------------------------------------------------------------


def test_the_canvas_can_be_turned_off(repo: Path) -> None:
    """`[app] graph = false`. It changes what the app shows and nothing about
    what any file means: `requires` still decides the study order."""
    import anki_math_forge.config as config_mod

    (repo / "forge.toml").write_text(
        (repo / "forge.toml").read_text(encoding="utf-8").replace(
            "[app]", "[app]\ngraph = false", 1
        ),
        encoding="utf-8",
    )
    off = config_mod.load(repo)
    assert off.graph is False
    client = two(off)
    client_on = TestClient(create_app(config_mod.load(repo)))

    assert client.get("/graph?source=demo").status_code == 404
    assert client.get("/api/graph/demo").status_code == 404
    assert client_on.post("/api/cards/bbb222/requires", json={"add": "aaa111"}).status_code == 404
    assert "to-graph" not in client.get("/review?status=all").text


def test_it_is_on_by_default(config: Config) -> None:
    """A deck with no `requires` anywhere never offers the link, so having it
    enabled costs nothing to somebody who does not want it."""
    assert config.graph is True


def test_the_page_carries_every_element_the_canvas_reaches_for(config: Config) -> None:
    """A canvas has no markup, so a renamed id is not a broken layout, it is a
    null dereference at load and a blank window with nothing in the page to
    say why. These are every id `graph.js` looks up at the top level."""
    body = two(config).get("/graph?source=demo").text
    for element in (
        "graph-stage",
        "graph-canvas",
        "graph-note",
        "graph-counts",
        "graph-all",
        "graph-add",
        "graph-reset",
        "add-card",
        "add-list",
        "add-empty",
        "add-count",
        "add-search",
        "add-close",
    ):
        assert f'id="{element}"' in body, f"graph.js reaches for #{element}"


def test_the_review_view_offers_the_canvas_only_where_there_is_one(
    config: Config,
) -> None:
    """A source where nothing needs anything never shows the link, so nothing
    points at an empty picture."""
    write(config, "aaa111")
    client = TestClient(create_app(config))
    assert "to-graph" not in client.get("/review?status=all").text

    write(config, "bbb222", requires=["aaa111"])
    assert "to-graph" in client.get("/review?status=all").text
