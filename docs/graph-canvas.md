# The dependency canvas: a design to build from

Working notes for [ROADMAP.md](ROADMAP.md) §1, written before the code exists.
**Delete this file when it is built**, or fold what survives into comments at
the seams it describes.

The brief that shaped it: do not overfit to what the two current sources
happen to look like. The graph today is 9 `requires` edges across 108 cards
from one book. Everything below is chosen so that a different shape (a concept
graph, a second edge kind, 700 nodes, a source with no edges at all) costs a
function rather than a rewrite.

## What is allowed to change, and what is not

Three things will change, and the design pays for each:

1. **What a node is.** A card today. The roadmap flags "a concept several
   cards share" as open, and "the adjugate" is one idea carried by three
   cards.
2. **What an edge means.** `requires` today. Plausible later: two cards from
   one unit, two cards in one section, a second explicit frontmatter key.
3. **How many.** 108 nodes now. A fully carded 700-page book is a different
   picture.

Two things must not:

- **Files are the source of truth** (invariant 2). Positions are a file you
  can edit by hand and read in a diff.
- **The browser writes through the same guards as everything else**: the
  `mtime` precondition and `ledger.lock`, exactly as `_mutate_card` does.

## The seam

One generic payload, and one builder function per flavour of graph. The canvas
never learns what a card is.

```python
# src/anki_math_forge/graph.py  -- new module, no app or FastAPI imports

@dataclass(frozen=True)
class Node:
    id: str       # opaque and stable. A card node uses its uid
    label: str    # drawn in the box
    detail: str   # second line, and the tooltip
    kind: str     # "card" today; a styling hook, never branched on in Python
    state: str    # "approved" | "draft" | ...; another styling hook
    href: str     # where a click goes

@dataclass(frozen=True)
class Edge:
    src: str      # must be introduced BEFORE dst
    dst: str
    kind: str     # "requires" today

@dataclass(frozen=True)
class Graph:
    nodes: list[Node]
    edges: list[Edge]
```

```python
def card_graph(cards: list[Card], *, homes: dict[str, str]) -> Graph: ...
```

**Direction matters and is easy to get backwards.** `requires: [b]` on card `a`
means *b before a*, so the edge is `Edge(src=b, dst=a)`. Reading the canvas
left to right is then reading study order, which is what the key means. Write
the test for this first.

**The id is opaque.** Nothing may assume six hex digits. A concept node would
use `adjugate` or similar, and every layer below (layout, the position file,
the canvas, the API) keeps working because none of them parses an id.

A second flavour is a second builder plus `?graph=concepts` on the route. The
renderer, the layout and the position file are untouched. That is the whole
point of the shape; resist adding a registry or a plugin protocol for two
functions.

## Layout

`layered(graph) -> dict[str, tuple[float, float]]`, in the same module.

- **x is the layer**: the longest path from a node with no prerequisites. A
  dependency graph's meaning is "introduce this first", so the horizontal axis
  being "how early" is the honest reading and needs no explaining.
- **y is the order within the layer**, taken from `in_study_order` so it
  agrees with the queue you would actually meet.

Two properties the tests should hold, because both are what make a canvas
usable rather than annoying:

- **Deterministic.** Same cards in, same coordinates out. Opening the view
  twice must not shuffle it.
- **Stable.** Adding an unrelated card moves nothing that already had a
  position.

Cycles: `check` refuses one, but the app renders a repo that has not been
linted. Guard the longest-path walk the way `sync.effective_keys` guards its
own recursion, with a `walking` set, and stop rather than recurse forever.

**No force simulation, and no dot-style edge routing.** The roadmap rejected
both for the same reason: neither knows which two results belong side by side,
and that judgement is the only thing a person adds here. Straight lines, or a
shallow curve where two would overlap.

## The picture is the connected part, by default

This is the decision that makes the view worth opening at nine edges, and it
is the roadmap's own objection answered:

> Nine edges across 108 cards renders as a hundred isolated dots and a few
> short chains, taking a panel to say "almost nothing depends on anything".

So **default to the nodes that have at least one edge**, with a toggle for
everything. At 9 edges that is a readable dozen boxes instead of 99 dots and a
dozen boxes. On a source where most cards are linked the toggle stops
mattering, which is the right way round.

State the count that is hidden (`99 unlinked`), because a filtered view that
does not say it is filtered is the counts bug all over again.

## Positions on disk

`sources/<name>/graph.json`:

```json
{"version": 1, "positions": {"af5ca1": [120, 240], "ae6e48": [320, 240]}}
```

- Keyed by node id, so it serves any flavour. A card uid and a concept name
  cannot collide in practice, and if they ever could, that is when ids get
  prefixes and not before.
- The `version` wrapper costs one line and gives the next change somewhere to
  live.
- A node with no entry gets its position from `layered()`. Nothing is written
  until somebody drags something, so a fresh source has no file, and that is
  not an error.
- **It is in the source's folder, not `localStorage`**, so it is shared,
  diffable and survives a new machine. Not in card frontmatter, where it would
  be hashed and a drag would un-approve a card.

Add it to no `.gitignore`: this one is committed, unlike the crops.

## The API

```
GET  /api/graph/{source}            -> {nodes, edges, positions, mtime, hidden}
POST /api/graph/{source}/positions  <- {positions: {...}, mtime}
```

The POST follows `_mutate_card` exactly: read `mtime` from the body, take
`ledger.lock` on `graph.json`, write, return the new `mtime`. A stale write
gets the 409 with `{"stale": true}` that `app.js` already knows how to
surface.

Send only the nodes that moved, and merge server-side. A whole-map PUT loses a
concurrent drag in another tab for no gain.

Debounce on the client: write on `pointerup`, never on `pointermove`.

## Where it lives

A third view, `/graph`, not a dialog: it wants the whole window and its own
keys. It inherits the source picker from the header for free, which is the
scoping the roadmap asked for.

**Entry point is the card, not the header.** The header deliberately carries
no view links, and the moment you want the whole graph is when you are looking
at a card that has dependencies. Put the link in the review view's `requires` /
`required by` block: *see the whole graph →*. A source with no edges anywhere
never shows the link, so nothing offers an empty picture.

Pointer handling: copy the shape `app.js` already uses for the rail grips and
splitters (`pointerdown` + `setPointerCapture`, a module-level `drag` object,
`pointermove`, `pointerup`). Do not add a drag library.

## v1 stops before editing edges

Positions are a *view* preference and cost nothing if wrong. An edge is card
content: writing one means putting `requires` into frontmatter, which `check`
validates for cycles, self-reference and dangling uids.

So v1 is **drag to arrange, click to navigate, read-only edges**. Drawing an
edge in the browser is the next piece and it needs its own three things: the
cycle check *before* the write rather than after, the `mtime` guard, and an
undo, because a mis-dragged arrow is as easy to make as a mis-pressed key.

Do not build the endpoint before the feature. `Edge.kind` is the only
affordance v1 owes it.

## What a test can hold

The canvas has no markup, so the layout tests carry the weight:

- `card_graph` builds the edge in the right direction, and drops a `requires`
  naming a card that is not here (`check` reports that; the graph must not
  invent a node for it).
- `layered` is deterministic, is stable under an unrelated addition, and
  terminates on a cycle.
- Positions round-trip through `graph.json`, and a stale `mtime` is refused.
- The payload carries every field the canvas reads, so renaming one in Python
  fails a test rather than blanking the screen.

For the drawing itself, add a `graph` shot to `assets/make_assets.py`. It is
the only way anyone will notice the picture got worse.

## Not now, and the trigger for each

- **Quadtree hit-testing.** Linear hit-testing over 700 nodes on `pointermove`
  is microseconds. Revisit past a few thousand.
- **Zoom.** Pan is enough; the browser zooms. Revisit when a real source does
  not fit.
- **Concept nodes.** The second builder. Worth it when one idea is carried by
  enough cards that the card graph reads as duplication, which is the
  "adjugate" case and is not yet common.
- **Cross-source graphs.** `requires` may already name a card in another
  source and `review_view` links it with `homes`. The canvas should show such
  a node as present-but-elsewhere rather than pretend it does not exist, and
  that is the whole of the cross-source story for now.
