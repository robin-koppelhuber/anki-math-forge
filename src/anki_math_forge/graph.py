"""The dependency graph as data, and where its layout is kept (ROADMAP.md §1).

`requires` decides the order Anki introduces new cards in, and the review view
shows one card's share of it: what this card needs, what needs it, where it
lands. The shape of the whole thing -- which results everything rests on,
whether a chapter recorded any dependencies at all -- is not a question about
one card, so it gets a view of its own.

Nothing here imports the app. A `Node` carries a label, a state and a link and
knows nothing about what produced it, so a second flavour of graph is a second
builder function and the layout, the position file and the canvas are
untouched. `card_graph` is the only one so far.

**An id is opaque.** Nothing below parses one, so a concept node calling itself
`adjugate` costs nothing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .ledger import lock
from .model import Card, StaleFileError, write_atomic

# CSS pixels between layers and between rows within one. Only a starting
# arrangement: the point of the canvas is that you drag it into the shape the
# material has, and `graph.json` then outranks everything here.
# `Node` boxes draw 240 by 60, so these are the box plus the gap. A column of
# 280 left forty pixels between one box and the next, which is a seam rather
# than a gap: two captions ran together and the arrows between them had nowhere
# to bend. Wide enough that an arrow's curve is visible as a curve.
COLUMN = 380.0
ROW = 128.0

POSITIONS_FILE = "graph.json"
POSITIONS_VERSION = 1


@dataclass(frozen=True)
class Node:
    """One box on the canvas."""

    id: str
    #: Drawn in the box. Empty for a card nobody has named, and the canvas
    #: shows the gap rather than inventing one: the filename slug is a
    #: transliteration of the LaTeX, which is the thing a caption spares you.
    label: str = ""
    #: Second line, and the tooltip.
    detail: str = ""
    #: A styling hook, never branched on in Python.
    kind: str = "card"
    state: str = ""
    href: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "detail": self.detail,
            "kind": self.kind,
            "state": self.state,
            "href": self.href,
        }


@dataclass(frozen=True)
class Edge:
    """`src` must be introduced before `dst`."""

    src: str
    dst: str
    kind: str = "requires"

    def as_dict(self) -> dict[str, str]:
        return {"src": self.src, "dst": self.dst, "kind": self.kind}


@dataclass(frozen=True)
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def connected(self, keep: Iterable[str] = ()) -> Graph:
        """The same graph with the nodes no edge touches left out.

        What makes the view worth opening while the edges are few. Nine edges
        across 108 cards draws as ninety-nine isolated dots and a dozen boxes,
        which takes a whole window to say that almost nothing depends on
        anything. On a source where most cards are linked this drops nothing,
        which is the right way round.

        `keep` is how a card with no edges gets onto the canvas anyway, and it
        is the ids that have a position in `graph.json`. Somebody put that node
        somewhere, which is the only statement of intent available, and it says
        *keep showing me this*. Adding a card to the canvas is then giving it a
        position and removing it is forgetting one, both of which the file and
        the API already do. The alternative was a second list of pinned ids,
        which is a new piece of state saying the same thing.

        The caller states the count it hid. A filtered view that does not say
        it is filtered reads as the whole picture.
        """
        shown = {e.src for e in self.edges} | {e.dst for e in self.edges} | set(keep)
        return Graph([n for n in self.nodes if n.id in shown], list(self.edges))

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "nodes": [n.as_dict() for n in self.nodes],
            "edges": [e.as_dict() for e in self.edges],
        }


def card_graph(
    cards: Iterable[Card],
    *,
    label: Callable[[Card], str] | None = None,
    href: Callable[[Card], str] | None = None,
    here: str = "",
) -> Graph:
    """The cards, and the `requires` between them.

    **The direction is the one the key means, and it is easy to get backwards.**
    `requires: [b]` on card `a` says *b before a*, so the edge runs from `b` to
    `a`. Reading the canvas left to right is then reading study order.

    A `requires` naming a card that is not in `cards` is dropped rather than
    drawn to an invented node. `check` reports a dangling uid, and a box on the
    canvas for something that does not exist would be the graph disagreeing
    with the lint about what the deck contains.

    `here` is the source being drawn. A card from another one is a real node
    with `kind="elsewhere"`, because `requires` may cross sources and hiding
    the target would show the dependent as a foundation it is not.
    """
    naming = label or (lambda card: card.gist)
    linking = href or (lambda card: "")
    cards = list(cards)
    nodes = [
        Node(
            id=card.uid,
            label=naming(card),
            detail=card.source or card.unit,
            kind="card" if not here or card.project_name == here else "elsewhere",
            state=card.effective_status,
            href=linking(card),
        )
        for card in cards
    ]
    known = {node.id for node in nodes}
    edges = [
        Edge(src=need, dst=card.uid)
        for card in cards
        for need in card.requires
        if need in known and need != card.uid
    ]
    return Graph(nodes, edges)


def route(edges: Iterable[Edge], start: str, goal: str) -> list[str]:
    """A path from `start` to `goal` following edges forwards, or an empty list.

    What the cycle guard is made of. Adding `requires: [p]` to card `d` draws
    the edge `p -> d`, and that closes a loop exactly when `d` already leads to
    `p`. Asking beforehand is the whole point: `check` reports a cycle after
    the fact, and a card file written into a state the lint refuses is a worse
    answer than a refusal at the moment of the drag.

    The path comes back rather than a boolean so the refusal can name the loop.
    Being told "that would make a cycle" without being told which one leaves
    you to find it by hand in a graph you were drawing because you could not
    see it.
    """
    ahead: dict[str, list[str]] = {}
    for edge in edges:
        ahead.setdefault(edge.src, []).append(edge.dst)
    trails = [[start]]
    seen = {start}
    while trails:
        trail = trails.pop(0)
        for nxt in ahead.get(trail[-1], []):
            if nxt == goal:
                return [*trail, nxt]
            if nxt not in seen:
                seen.add(nxt)
                trails.append([*trail, nxt])
    return []


def layered(graph: Graph, order: Sequence[str] = ()) -> dict[str, tuple[float, float]]:
    """A starting position for every node, before anyone has dragged anything.

    **x is the layer**: the longest path from a node with no prerequisites. The
    meaning of the graph is "introduce this first", so the horizontal axis
    being "how early" needs no explaining.

    **y is the order within the layer**, taken from `order` -- the study order
    of the source -- so a column agrees with the queue you would actually meet.
    A node `order` does not mention sorts to the end by id.

    Deterministic: the same cards give the same coordinates, so opening the
    view twice does not shuffle it. Adding a card that touches no edge moves
    nothing, which is the case that comes up, since such a card is not drawn at
    all by default. A new node *inside* an occupied layer does push the ones
    below it down, and that is the arrangement being right rather than drifting:
    it has taken its place in the reading. Nothing dragged is affected either
    way -- `graph.json` outranks this.
    """
    needs: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.src in needs and edge.dst in needs and edge.src != edge.dst:
            needs[edge.dst].append(edge.src)

    depth: dict[str, int] = {}
    walking: set[str] = set()

    def resolve(node_id: str) -> int:
        if node_id in depth:
            return depth[node_id]
        if node_id in walking:
            # A cycle. `check` refuses one, but the app renders a repo nobody
            # has linted, and a canvas that hangs the server is a worse answer
            # than a canvas drawn slightly wrong. Same guard as
            # `sync.effective_keys`.
            return 0
        walking.add(node_id)
        deep = max((resolve(p) + 1 for p in needs[node_id]), default=0)
        walking.discard(node_id)
        depth[node_id] = deep
        return deep

    rank = {node_id: i for i, node_id in enumerate(order)}
    last = len(rank)
    columns: dict[int, list[str]] = {}
    for node in graph.nodes:
        columns.setdefault(resolve(node.id), []).append(node.id)

    out: dict[str, tuple[float, float]] = {}
    for layer, ids in columns.items():
        # The id is the tiebreak, not the input order, so two runs over the
        # same deck read the same even if the loader walked the files in a
        # different order.
        ids.sort(key=lambda node_id: (rank.get(node_id, last), node_id))
        for row, node_id in enumerate(ids):
            out[node_id] = (layer * COLUMN, row * ROW)
    return out


# -- where an arrangement is kept -------------------------------------------


def positions_path(projects_dir: Path, source: str) -> Path:
    """`projects/<name>/graph.json`.

    In the source's folder rather than in `localStorage`, so an arrangement is
    shared, diffable and survives a new machine. Not in card frontmatter, where
    it would be hashed and dragging a box would un-approve a card.

    Keyed by node id, so the file serves any flavour of graph. A card uid and a
    concept name cannot collide in practice, and the day they could is the day
    ids get prefixes.
    """
    return projects_dir / source / POSITIONS_FILE


def load_positions(path: Path) -> dict[str, tuple[float, float]]:
    """What has been dragged. A source nobody has arranged has no file, and
    that is not an error: every node falls back to `layered`."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: not readable as JSON: {exc}") from exc
    out: dict[str, tuple[float, float]] = {}
    for node_id, pair in (raw.get("positions") or {}).items():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            out[str(node_id)] = (float(pair[0]), float(pair[1]))
    return out


def save_positions(path: Path, positions: dict[str, tuple[float, float]]) -> None:
    """One node per line, so a diff reads as the boxes that moved.

    Coordinates are whole pixels. A drag lands on a fraction and nobody
    arranging a graph by hand means the half-pixel, so keeping it would put
    noise in every diff.
    """
    rows = ",\n".join(
        f'    "{node_id}": [{round(x)}, {round(y)}]'
        for node_id, (x, y) in sorted(positions.items())
    )
    inner = f"\n{rows}\n  " if rows else ""
    write_atomic(
        path,
        f'{{\n  "version": {POSITIONS_VERSION},\n  "positions": {{{inner}}}\n}}\n',
    )


def move(
    path: Path,
    moved: dict[str, tuple[float, float] | None],
    *,
    expect_mtime_ns: int | None = None,
) -> dict[str, tuple[float, float]]:
    """Merge the nodes that moved into the file, and hand back the whole map.

    Only what moved, merged here, rather than the browser posting the whole
    arrangement: a whole-map write loses a concurrent drag in another tab and
    buys nothing.

    A node mapped to `None` loses its entry and goes back to wherever `layered`
    puts it. That is what putting a box back means, and recording the computed
    coordinate instead would freeze today's arrangement into the file and stop
    it ever being recomputed.

    **There is deliberately no `mtime` precondition**, unlike every other write
    in this app, and the difference is what is being written. A card write
    rewrites a whole file, so a writer working from a stale copy destroys
    whatever it did not know about; the precondition is the only thing standing
    between two tabs and a lost edit. This merges *per node*, so a stale writer
    cannot destroy a key it never mentions.

    It was guarded, on the reasoning that a reader with a stale picture should
    be told. Measured with two tabs on one source: each arrangement drag landed
    and the next one from the other tab took a 409 and a full page reload, so
    two people arranging different halves of a graph ping-ponged, losing one
    drag each per turn -- to protect a merge that was already safe. The merge
    is the guarantee here. `expect_mtime_ns` is kept for a caller that wants
    the check, and nothing in the app passes it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock(path):
        actual = path.stat().st_mtime_ns if path.exists() else 0
        if expect_mtime_ns is not None and actual != expect_mtime_ns:
            raise StaleFileError(
                f"{path.name} changed on disk since it was loaded; reload and retry"
            )
        positions = load_positions(path)
        for node_id, at in moved.items():
            if at is None:
                positions.pop(node_id, None)
            else:
                positions[node_id] = at
        save_positions(path, positions)
    return positions
