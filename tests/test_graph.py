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


def test_v1_writes_no_edges(config: Config) -> None:
    """Positions cost a drag if wrong. An edge is card content: writing one
    means putting `requires` into frontmatter, which `check` validates for
    cycles, self-reference and dangling uids -- so drawing an arrow in the
    browser needs the cycle check *before* the write, and an undo, and it is
    the next piece rather than this one."""
    routes = {r.path for r in create_app(config).routes}  # type: ignore[attr-defined]
    assert "/api/graph/{source}/positions" in routes
    assert not [r for r in routes if "edge" in r]


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
