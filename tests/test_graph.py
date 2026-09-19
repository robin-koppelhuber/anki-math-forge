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
from anki_math_forge.app import create_app, project_graph
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
    project: str = "demo",
) -> Card:
    path = config.cards_dir / project / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = ""
    if requires:
        keys += "requires: [" + ", ".join(requires) + "]\n"
    if gist:
        keys += f"gist: {gist}\n"
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: {status}\n"
        f'unit: "{project}:2.4:61"\n{keys}---\n\n## front\n\n$a$\n\n## back\n\n$b$\n',
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
    there = write(config, "ccc333", project="paper")
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


def test_a_stale_arrangement_merges_rather_than_being_refused(tmp_path: Path) -> None:
    """The one write in this app with no staleness check, and the difference is
    what is being written.

    A card write rewrites a whole file, so a writer holding a stale copy
    destroys what it did not know about, and the precondition is all that
    stands between two tabs and a lost edit. This merges *per node*, so a stale
    writer cannot touch a key it never mentions.

    It was guarded. Measured in a browser with two tabs on one source: each
    drag landed and the next one from the other tab took a 409 and a full page
    reload, so two people arranging different halves ping-ponged and lost a
    drag each per turn -- to protect a merge that was already safe.
    """
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"aaa111": (1.0, 2.0)})
    assert graph_mod.move(path, {"bbb222": (3.0, 4.0)}) == {
        "aaa111": (1.0, 2.0),
        "bbb222": (3.0, 4.0),
    }, "the other tab's box is still there"


def test_the_guard_is_still_there_for_a_caller_that_wants_it(tmp_path: Path) -> None:
    """Kept rather than deleted. Nothing in the app passes it; a caller that
    read the whole file and rewrote it would need it."""
    path = tmp_path / "graph.json"
    graph_mod.save_positions(path, {"aaa111": (1.0, 2.0)})
    with pytest.raises(StaleFileError):
        graph_mod.move(path, {"aaa111": (9.0, 9.0)}, expect_mtime_ns=1)


# -- through the app --------------------------------------------------------


def test_the_payload_carries_every_field_the_canvas_reads(config: Config) -> None:
    """Renaming one of these in Python should fail here rather than blank the
    screen: the canvas has no markup, so nothing else would notice."""
    write(config, "aaa111", gist="the product of the eigenvalues")
    write(config, "bbb222", requires=["aaa111"])
    payload = project_graph(config, "demo")
    assert set(payload) >= {
        "project",
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
    assert project_graph(config, "demo")["hidden"] == 1
    assert project_graph(config, "demo", everything=True)["hidden"] == 0


def test_a_node_is_labelled_with_the_caption_the_review_view_shows(
    config: Config,
) -> None:
    """`card_gist`, so a card with no caption of its own is named by the unit
    it was written from, exactly as it is everywhere else."""
    write(config, "aaa111", gist="the adjugate in terms of the inverse")
    write(config, "bbb222", requires=["aaa111"])
    nodes = {n["id"]: n for n in project_graph(config, "demo")["nodes"]}
    assert nodes["aaa111"]["label"] == "the adjugate in terms of the inverse"
    assert nodes["aaa111"]["href"].endswith("#aaa111")


def test_the_api_serves_it(config: Config) -> None:
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    assert client.get("/graph?project=demo").status_code == 200
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
    path = graph_mod.positions_path(config.projects_dir, "demo")
    assert graph_mod.load_positions(path) == {"aaa111": (120.0, 240.0)}
    assert client.get("/api/graph/demo").json()["positions"] == {"aaa111": [120.0, 240.0]}


def two(config: Config) -> TestClient:
    """Two cards and a client, the fixture most of these start from."""
    write(config, "aaa111", gist="the product of the eigenvalues")
    write(config, "bbb222", gist="the determinant")
    return TestClient(create_app(config))


def test_two_tabs_can_arrange_the_same_source(config: Config) -> None:
    """Positions are merged per node, so a drag from a page that has not seen
    the other one's drag keeps both. This is the write that is deliberately
    unguarded; see `graph.move`."""
    write(config, "aaa111")
    write(config, "bbb222", requires=["aaa111"])
    client = TestClient(create_app(config))
    stale = client.get("/api/graph/demo").json()["mtime"]

    first = client.post(
        "/api/graph/demo/positions", json={"positions": {"aaa111": [1, 1]}, "mtime": stale}
    )
    assert first.status_code == 200
    # The same stale mtime the first write was made with, as a second tab would
    # still be holding.
    second = client.post(
        "/api/graph/demo/positions", json={"positions": {"bbb222": [2, 2]}, "mtime": stale}
    )
    assert second.status_code == 200
    assert second.json()["positions"] == {"aaa111": [1.0, 1.0], "bbb222": [2.0, 2.0]}


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

    assert client.get("/graph?project=demo").status_code == 404
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
    body = two(config).get("/graph?project=demo").text
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


def test_the_review_view_offers_the_canvas_wherever_it_could_be_used(
    config: Config,
) -> None:
    """Offered from any card of a source with more than one, not only from a
    card that already has a dependency.

    It used to need an existing edge, so that nothing pointed at an empty
    picture. That was right while the canvas could only be read. An arrow is
    drawn there now, so a source with no arrows is exactly when you want it --
    and under the old rule the canvas was unreachable from 90 of this deck's
    108 cards, and from a new source altogether.

    One card still offers nothing, because one card cannot depend on anything.
    """
    write(config, "aaa111")
    client = TestClient(create_app(config))
    assert "to-graph" not in client.get("/review?status=all").text

    write(config, "bbb222")
    body = client.get("/review?status=all").text
    assert "to-graph" in body, "two cards and no edges is the case that changed"
    assert "draw the dependencies" in body, "nothing to see yet, so do not promise it"

    model.load(write(config, "ccc333").path).save()  # type: ignore[union-attr]
    card = model.load(write(config, "ddd444").path)  # type: ignore[arg-type]
    card.frontmatter["requires"] = ["ccc333"]
    card.save()
    assert "see the whole graph" in client.get("/review?status=all").text


def test_there_is_a_way_off_the_canvas(config: Config) -> None:
    """The app puts navigation in the filter rail, and the graph view has no
    rail: measured on the real deck, the page carried no link to anywhere at
    all. With an empty canvas that is a dead end, since the only other way out
    is clicking a box."""
    body = two(config).get("/graph?project=demo").text
    assert "/review?project=demo" in body
