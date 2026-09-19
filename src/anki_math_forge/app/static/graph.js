/* The dependency canvas: one project's `requires`, drawn and arranged by hand.

   Everything on screen comes from `/api/graph/<project>`. The server decides
   what is drawn and where it starts; this file draws it, moves boxes, and
   posts the ones that moved. It knows nothing about cards -- a node is an id,
   a label and a link -- so a second kind of graph is a second builder in
   Python and nothing here changes.

   Straight lines and no force simulation, deliberately. Neither a spring
   layout nor dot's edge routing knows which two results belong side by side,
   and that judgement is the only thing a person adds to this picture. The
   computed layout is a starting point; `graph.json` is the answer. */

/* Wide enough for two lines of a caption at the 60-character cap `check`
   warns past, so the common case is drawn whole rather than ellipsised. */
const NODE_W = 240;
const NODE_H = 60;
const NODE_R = 8;
/* A click that wandered a few pixels is still a click. Without the slop,
   opening a card by clicking it depended on holding the mouse perfectly
   still. */
const CLICK_SLOP = 4;
const MARGIN = 48;
/* The connector dots. Drawn small and grabbed generously: the dot is the
   affordance and the ring around it is the target. */
const PORT_R = 5;
const PORT_GRAB = 13;
/* How near the pointer has to be to an arrow to be pointing at it. */
const EDGE_GRAB = 8;

const stage = document.getElementById("graph-stage");
const canvas = document.getElementById("graph-canvas");
const note = document.getElementById("graph-note");
const counts = document.getElementById("graph-counts");
const ctx = canvas && canvas.getContext("2d");

let data = null;
let everything = false;
/* The view transform: where the origin of the picture sits on screen, and how
   big. Every coordinate crosses it exactly once, through `toScreen` and
   `toWorld`, because a canvas with two places that convert is a canvas where
   hit-testing and drawing disagree by a scale factor. */
let pan = { x: MARGIN, y: MARGIN };
let scale = 1;
/* A box drags smaller than this and the labels stop being labels; bigger and
   four cards fill the window. */
const ZOOM = { min: 0.25, max: 2.5, step: 1.15 };
/* `0` may go below the interactive floor. A hundred cards in one chain is
   wider than 0.25 fits, and a "fit on screen" that leaves most of the graph
   off the left edge is the one gesture that has to work when you are lost. */
const FIT_MIN = 0.06;
let marquee = null;
let drag = null;
let hover = null;
let hoverPort = null;
/* The arrow being drawn, from `pointerdown` on a port until it is dropped. */
let link = null;
/* The arrow under the pointer, and the one clicked. Selecting before deleting,
   rather than deleting whatever is hovered: an arrow is a line a few pixels
   wide and a key that removes one on hover is a key that removes the wrong
   one. */
let hoverEdge = null;
/* The dragged position lives here until `pointerup` posts it. Writing on every
   `pointermove` would be a file write per frame. */
let moved = {};
/* Inverse operations, newest last: `{dependent, add|remove}` for an arrow,
   `{positions}` for an arrangement.

   Moves have to be on here too. They were not, and `z` after moving a box
   popped the newest *edge* op instead -- so a keystroke that should have put a
   box back deleted a `requires` from a card file, silently, possibly from a
   card you had not touched. An edge undo is "remove what you added", which
   needs nothing remembered; a move undo is the positions from before it. */
const undone = [];

function palette() {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(name).trim();
  return {
    ink: read("--ink"),
    muted: read("--muted"),
    line: read("--line"),
    accent: read("--accent"),
    panel: read("--panel"),
    bad: read("--bad"),
    /* Missing, and `ctx.strokeStyle = undefined` is a silent no-op: the one
       arrow the picture is supposed to draw attention to -- an approved card
       resting on a draft one -- kept whatever colour was set last, which on
       the dark ground made it the least visible line on screen. */
    warn: read("--warn"),
  };
}

let colours = palette();
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    colours = palette();
    draw();
  });
}

/* Where a node sits: what somebody dragged it to, else where the layout put
   it. Two maps rather than one, so putting a box back is deleting an entry
   rather than remembering a number. */
function at(id) {
  const here = moved[id] || (data.positions || {})[id] || (data.layout || {})[id];
  return here ? { x: here[0], y: here[1] } : { x: 0, y: 0 };
}

function centre(id) {
  const p = at(id);
  return { x: p.x + NODE_W / 2, y: p.y + NODE_H / 2 };
}

function nodeAt(x, y) {
  /* Last drawn is on top, so search backwards. Linear over every node: at a
     few hundred boxes this is microseconds, and a quadtree is worth its own
     bugs only past a few thousand. */
  for (let i = data.nodes.length - 1; i >= 0; i--) {
    const p = at(data.nodes[i].id);
    if (x >= p.x && x <= p.x + NODE_W && y >= p.y && y <= p.y + NODE_H) return data.nodes[i];
  }
  return null;
}

function pointer(event) {
  const box = canvas.getBoundingClientRect();
  return toWorld(event.clientX - box.left, event.clientY - box.top);
}

function toWorld(x, y) {
  return { x: (x - pan.x) / scale, y: (y - pan.y) / scale };
}

/* Zoom about a fixed point: the thing under the pointer stays under the
   pointer. Zooming about the origin instead sends whatever you were looking at
   off the edge, which is the version that feels broken. */
function zoomTo(next, atX, atY) {
  const clamped = Math.min(ZOOM.max, Math.max(ZOOM.min, next));
  if (clamped === scale) return;
  const box = canvas.getBoundingClientRect();
  const sx = atX === undefined ? box.width / 2 : atX;
  const sy = atY === undefined ? box.height / 2 : atY;
  const before = toWorld(sx, sy);
  scale = clamped;
  pan = { x: sx - before.x * scale, y: sy - before.y * scale };
  draw();
}

function zoomBy(factor) {
  zoomTo(scale * factor);
}

// -- the connectors --------------------------------------------------------

/* Two dots per box, and which one you grab says which card is the dependent
   before anything is sent.

   The right dot is "is needed by": the box you started from is the
   prerequisite, and whatever you drop on needs it. The left dot is "needs":
   the box you started from is the one that needs whatever you drop on. Both
   produce the same arrow, from prerequisite to dependent, so there is no way
   to author one backwards by dragging from the wrong end -- which is the
   thing that would otherwise be easy, because `requires` is written on the
   card that does the needing and the arrow points the other way. */
function port(id, side) {
  const p = at(id);
  return { x: side === "left" ? p.x : p.x + NODE_W, y: p.y + NODE_H / 2 };
}

function portAt(x, y) {
  for (let i = data.nodes.length - 1; i >= 0; i--) {
    for (const side of ["left", "right"]) {
      const spot = port(data.nodes[i].id, side);
      if (Math.hypot(x - spot.x, y - spot.y) <= PORT_GRAB / scale) {
        return { node: data.nodes[i], side };
      }
    }
  }
  return null;
}

/* Which card ends up with the `requires` line, and which one it names. */
function ends(from, side, target) {
  return side === "right"
    ? { dependent: target.id, prereq: from.id }
    : { dependent: from.id, prereq: target.id };
}

function leadsTo(start, goal) {
  const ahead = {};
  data.edges.forEach((e) => (ahead[e.src] = ahead[e.src] || []).push(e.dst));
  const queue = [start];
  const seen = new Set([start]);
  while (queue.length) {
    for (const next of ahead[queue.shift()] || []) {
      if (next === goal) return true;
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }
  return false;
}

/* Why this arrow cannot be drawn, or the empty string.

   Answered while dragging rather than on the drop. Being allowed to release an
   arrow and *then* told it would make a cycle is a worse feature than not
   being able to release it there: the refusal arrives after you have committed
   to the gesture, and it tells you nothing about where to put it instead. The
   server checks all of this again, because the browser is one way in. */
function whyNot(prereq, dependent) {
  if (prereq === dependent) return "a card cannot need itself";
  if (data.edges.some((e) => e.src === prereq && e.dst === dependent)) {
    return "that arrow is already there";
  }
  if (leadsTo(dependent, prereq)) return "that would make a cycle";
  return "";
}

/* Along the curve, not along the straight line between its ends: an arrow that
   bows out is grabbed where it is drawn, not where it would have been. */
function nearEdge(x, y) {
  for (const edge of data.edges) {
    const points = along(port(edge.src, "right"), port(edge.dst, "left"));
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1];
      const b = points[i];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = dx * dx + dy * dy;
      const u = len ? Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / len)) : 0;
      if (Math.hypot(x - (a.x + u * dx), y - (a.y + u * dy)) <= EDGE_GRAB / scale) return edge;
    }
  }
  return null;
}

function labelOf(id) {
  const node = (data.nodes || []).find((n) => n.id === id);
  return (node && node.label) || id;
}

// -- drawing ---------------------------------------------------------------

function boxPath(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* An arrow runs dot to dot: out of the prerequisite's right port and into the
   dependent's left port, which are the two things you dragged between.

   Centre to centre, clipped at the border, was the first version and it is what
   made the picture read as clunky: the line met the box wherever the geometry
   happened to put it, so the arrow you had just drawn between two dots arrived
   somewhere else, and two arrows into one card entered at two different places.

   A curve rather than a straight line, because the ports face outwards. The
   handles are horizontal, so every arrow leaves to the right and enters from
   the left even when the dependent has been dragged to the left of what it
   needs -- which is the case a straight line cuts back through both boxes. */
function bend(from, to) {
  const reach = Math.max(45, Math.abs(to.x - from.x) * 0.4);
  return [
    { x: from.x + reach, y: from.y },
    { x: to.x - reach, y: to.y },
  ];
}

function curve(from, to) {
  const [c1, c2] = bend(from, to);
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, to.x, to.y);
  ctx.stroke();
}

/* Where the curve is going as it arrives, so the head points along it rather
   than along the straight line between the two ends. */
function arrowhead(from, to) {
  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const wing = 9;
  ctx.beginPath();
  ctx.moveTo(to.x, to.y);
  ctx.lineTo(to.x - wing * Math.cos(angle - 0.4), to.y - wing * Math.sin(angle - 0.4));
  ctx.lineTo(to.x - wing * Math.cos(angle + 0.4), to.y - wing * Math.sin(angle + 0.4));
  ctx.closePath();
  ctx.fill();
}

function headOfCurve(from, to) {
  const [, c2] = bend(from, to);
  arrowhead(c2, to);
}

/* The curve as points, for hit-testing and nothing else. Twenty segments is
   under a pixel of error at the sizes this draws at, and the alternative is
   solving a cubic for the nearest point. */
function along(from, to, steps = 20) {
  const [c1, c2] = bend(from, to);
  const out = [];
  for (let i = 0; i <= steps; i++) {
    const u = i / steps;
    const v = 1 - u;
    out.push({
      x: v ** 3 * from.x + 3 * v * v * u * c1.x + 3 * v * u * u * c2.x + u ** 3 * to.x,
      y: v ** 3 * from.y + 3 * v * v * u * c1.y + 3 * v * u * u * c2.y + u ** 3 * to.y,
    });
  }
  return out;
}

function stateOf(id) {
  const node = (data.nodes || []).find((n) => n.id === id);
  return node ? node.state : "";
}

function drawEdge(edge) {
  const from = port(edge.src, "right");
  const at_ = port(edge.dst, "left");
  /* Stop just short of the dot. Ending on its centre buries the head inside a
     circle filled with the panel colour, which reads as an arrow that fades
     out rather than one that arrives. The curve enters horizontally, so
     backing off along x is backing off along the curve. */
  const to = { x: at_.x - (PORT_R + 2), y: at_.y };
  const lit = hover && (edge.src === hover.id || edge.dst === hover.id);
  const on = picked.edge && picked.edge.src === edge.src && picked.edge.dst === edge.dst;
  /* An approved card whose prerequisite is not approved. `sync` would
     introduce it without its foundation, and `check` says so as
     `requires-unapproved` -- after the fact, in a list you read later. The
     arrow itself is where that belongs, because the arrow is the thing that
     made it true. */
  const unbuilt =
    stateOf(edge.dst) === "approved" && stateOf(edge.src) !== "approved";
  /* Muted rather than `--line`. The arrows are the content here, not a border
     between two things, and at `--line` on the dark ground they were a shade
     off the background: the first render read as a field of unconnected
     boxes. */
  ctx.save();
  ctx.strokeStyle =
    on || edge === hoverEdge ? colours.accent : unbuilt ? colours.warn : colours.muted;
  ctx.fillStyle = ctx.strokeStyle;
  ctx.lineWidth = on ? 3 : lit || edge === hoverEdge ? 2 : 1.25;
  if (unbuilt && !on) ctx.setLineDash([7, 4]);
  curve(from, to);
  ctx.setLineDash([]);
  headOfCurve(from, to);
  ctx.restore();
}

/* The arrow being dragged, and whether it may land where it is pointing. */
function drawPending() {
  const spot = port(link.node.id, link.side);
  /* Onto the target's *opposite* port, so the shape you are dragging is the
     shape you will get. */
  const end = link.target
    ? port(link.target.id, link.side === "right" ? "left" : "right")
    : link.to;
  ctx.save();
  ctx.strokeStyle = link.why ? colours.bad : colours.accent;
  ctx.fillStyle = ctx.strokeStyle;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  /* The head is on the end that will carry it once this lands, which for a
     left-port drag is the box you started from. Drawn now rather than on
     release, so the direction is settled before you commit to it. */
  if (link.side === "right") {
    curve(spot, end);
    ctx.setLineDash([]);
    headOfCurve(spot, end);
  } else {
    curve(end, spot);
    ctx.setLineDash([]);
    headOfCurve(end, spot);
  }
  ctx.restore();
}

/* On every box, always, rather than on the one under the pointer.

   `drag a dot to connect two cards` is an instruction about something you
   cannot see if the dots appear only on hover: you would have to already know
   they were there to find out they were there. Quiet until pointed at, so
   thirty-six of them do not compete with the arrows. */
function drawPorts(node) {
  const near = hover && hover.id === node.id;
  ["left", "right"].forEach((side) => {
    const spot = port(node.id, side);
    const grabbed = hoverPort && hoverPort.node.id === node.id && hoverPort.side === side;
    ctx.save();
    if (!near && !grabbed && !link) ctx.globalAlpha = 0.55;
    ctx.beginPath();
    ctx.arc(spot.x, spot.y, grabbed ? PORT_R + 2 : PORT_R, 0, Math.PI * 2);
    ctx.fillStyle = grabbed ? colours.accent : colours.panel;
    ctx.strokeStyle = grabbed || near ? colours.accent : colours.muted;
    ctx.lineWidth = 1.5;
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  });
}

function fit(text, width) {
  if (ctx.measureText(text).width <= width) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(cut + "…").width > width) cut = cut.slice(0, -1);
  return cut + "…";
}

function wrap(text, width, lines) {
  const words = text.split(/\s+/).filter(Boolean);
  const out = [];
  let line = "";
  for (let i = 0; i < words.length; i++) {
    const next = line ? `${line} ${words[i]}` : words[i];
    if (ctx.measureText(next).width <= width || !line) {
      line = next;
      continue;
    }
    if (out.length === lines - 1) {
      /* The last line the box has room for, and there is more text. What is
         left goes on it and gets cut with an ellipsis.

         Dropping the remainder instead was worse than it sounds: a caption cut
         at a word boundary reads as a finished phrase that means something
         else. `the condition number as a ratio of singular values` came out as
         `the condition number as a ratio of`, and nothing on screen said a
         word was missing. */
      return [...out, fit(`${line} ${words.slice(i).join(" ")}`, width)];
    }
    out.push(line);
    line = words[i];
  }
  if (line) out.push(line);
  /* A single word wider than the box never overflows, it gets cut. `fit`
     returns a line that already fits unchanged, so this costs nothing. */
  return out.map((each) => fit(each, width));
}

/* The border says the state and the word repeats it, so only the word that is
   an exception is allowed to be loud. A deck is mostly approved, and a draft
   sitting in the middle of a chain -- a foundation nobody has reviewed -- is
   the thing worth spotting from across the canvas. */
const STATE_COLOUR = {
  approved: "accent",
  rejected: "muted",
};
const STATE_INK = {
  draft: "ink",
  rejected: "bad",
};

function drawNode(node) {
  const p = at(node.id);
  const edge = colours[STATE_COLOUR[node.state] || "line"];
  const chosen = isPicked(node.id);
  const lit =
    (hover && hover.id === node.id) ||
    (link && link.target === node) ||
    spotlight === node.id;

  ctx.save();
  /* While an arrow is being dragged, a box it cannot land on is dimmed. The
     picture answers "where may this go" continuously, instead of letting you
     aim at something that will be refused. */
  if (link && node !== link.node) {
    const { prereq, dependent } = ends(link.node, link.side, node);
    if (whyNot(prereq, dependent)) ctx.globalAlpha = 0.3;
  }
  boxPath(p.x, p.y, NODE_W, NODE_H, NODE_R);
  ctx.fillStyle = colours.panel;
  ctx.fill();
  ctx.strokeStyle = chosen || lit ? colours.accent : edge;
  ctx.lineWidth = chosen ? 3 : lit ? 2 : 1.25;
  /* A card from another project is a real node: `requires` may cross them, and
     hiding the target would draw a card whose foundation is elsewhere as a
     foundation itself. Dashed, because it is not yours to arrange here. */
  if (node.kind === "elsewhere") ctx.setLineDash([5, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  const pad = 11;
  const width = NODE_W - pad * 2;
  ctx.textBaseline = "top";

  if (node.label) {
    ctx.font = "600 13px -apple-system, 'Segoe UI', system-ui, sans-serif";
    ctx.fillStyle = colours.ink;
    wrap(node.label, width, 2).forEach((line, i) => {
      ctx.fillText(line, p.x + pad, p.y + 9 + i * 16);
    });
  } else {
    /* Nobody has named this card. Show the gap: the filename slug is a
       transliteration of the LaTeX, so a caption made from it would be the
       thing a caption exists to spare you. An empty box is also what tells
       you which cards to name. */
    ctx.font = "italic 13px -apple-system, 'Segoe UI', system-ui, sans-serif";
    ctx.fillStyle = colours.muted;
    ctx.fillText("no caption yet", p.x + pad, p.y + 9);
  }

  ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
  ctx.fillStyle = colours.muted;
  ctx.fillText(fit(node.id, width - 60), p.x + pad, p.y + NODE_H - 19);

  ctx.font = "11px -apple-system, 'Segoe UI', system-ui, sans-serif";
  ctx.textAlign = "right";
  ctx.fillStyle = colours[STATE_INK[node.state] || "muted"];
  ctx.fillText(node.state, p.x + NODE_W - pad, p.y + NODE_H - 19);
  ctx.textAlign = "left";
  drawPorts(node);
  ctx.restore();
}

function draw() {
  markSelected();
  if (!data) return;
  const dpr = window.devicePixelRatio || 1;
  const box = stage.getBoundingClientRect();
  canvas.width = Math.round(box.width * dpr);
  canvas.height = Math.round(box.height * dpr);
  canvas.style.width = `${box.width}px`;
  canvas.style.height = `${box.height}px`;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, box.width, box.height);
  ctx.translate(pan.x, pan.y);
  ctx.scale(scale, scale);
  data.edges.forEach(drawEdge);
  data.nodes.forEach(drawNode);
  if (link) drawPending();
  if (marquee) drawMarquee();
}

/* The selection box. Drawn in world coordinates like everything else, so its
   line stays one screen pixel whatever the zoom. */
function drawMarquee() {
  const x = Math.min(marquee.from.x, marquee.to.x);
  const y = Math.min(marquee.from.y, marquee.to.y);
  const w = Math.abs(marquee.to.x - marquee.from.x);
  const h = Math.abs(marquee.to.y - marquee.from.y);
  ctx.save();
  ctx.fillStyle = colours.accent;
  ctx.globalAlpha = 0.12;
  ctx.fillRect(x, y, w, h);
  ctx.globalAlpha = 1;
  ctx.strokeStyle = colours.accent;
  ctx.lineWidth = 1 / scale;
  ctx.setLineDash([5 / scale, 4 / scale]);
  ctx.strokeRect(x, y, w, h);
  ctx.restore();
}

function inMarquee() {
  const x1 = Math.min(marquee.from.x, marquee.to.x);
  const y1 = Math.min(marquee.from.y, marquee.to.y);
  const x2 = Math.max(marquee.from.x, marquee.to.x);
  const y2 = Math.max(marquee.from.y, marquee.to.y);
  /* Touched, not enclosed. Requiring a box to be wholly inside means a careful
     drag that clips one corner silently leaves that card out, and you find out
     when you move the rest without it. */
  return data.nodes.filter((n) => {
    const p = at(n.id);
    return p.x <= x2 && p.x + NODE_W >= x1 && p.y <= y2 && p.y + NODE_H >= y1;
  });
}

/* The whole picture on screen at once: scaled down if it does not fit, never
   scaled up past life size. `0` does this, and it is the way back from any
   pan or zoom that lost the graph. */
function recentre() {
  if (!data || !data.nodes.length) return;
  const spots = data.nodes.map((n) => at(n.id));
  const x1 = Math.min(...spots.map((p) => p.x));
  const y1 = Math.min(...spots.map((p) => p.y));
  const x2 = Math.max(...spots.map((p) => p.x)) + NODE_W;
  const y2 = Math.max(...spots.map((p) => p.y)) + NODE_H;
  /* The stage, not the canvas. A `<canvas>` with no width attribute measures
     300 by 150 until `draw` sizes it, and `recentre` runs first on load: the
     whole graph came up clamped to the minimum zoom in the top-left corner,
     laid out for a box a fifth of the window. The stage is a styled div and
     has its real size from the stylesheet before any script runs. */
  const box = stage.getBoundingClientRect();
  const room = Math.min(
    (box.width - MARGIN * 2) / Math.max(1, x2 - x1),
    (box.height - MARGIN * 2) / Math.max(1, y2 - y1),
  );
  scale = Math.min(1, Math.max(FIT_MIN, room));
  pan = {
    x: (box.width - (x2 - x1) * scale) / 2 - x1 * scale,
    y: (box.height - (y2 - y1) * scale) / 2 - y1 * scale,
  };
  draw();
}

// -- loading and saving ----------------------------------------------------

function describe() {
  const drawn = `${data.shown} of ${data.total} ${data.total === 1 ? "card" : "cards"}`;
  const arrows = `${data.edges.length} ${data.edges.length === 1 ? "arrow" : "arrows"}`;
  /* Say what is not on screen. A filtered view that does not report its filter
     reads as the whole picture -- and "almost nothing depends on anything" is
     a real answer that should not be mistaken for an empty feature. */
  const hidden = data.hidden ? ` · ${data.hidden} unlinked, hidden` : "";
  counts.textContent = `${drawn} · ${arrows}${hidden}`;

  note.hidden = data.nodes.length > 0;
  if (data.nodes.length) return;
  /* The empty state has to name the way out of it, and the way out is now on
     this page: add two cards and drag between their dots. It used to say
     "add `requires: [<uid>]` to a card", which was the only way when nothing
     here could write one. */
  /* The keys are configurable, so the one sentence that teaches this view
     reads them rather than naming the defaults it was written against. */
  const keys = keymap();
  note.textContent = data.total
    ? `No card in ${data.project} needs another one yet. ` +
      `Press ${keys["add-card"] || "+"} to put a card on the canvas, then drag ` +
      "from a dot on its edge to another card to say which comes first."
    : `No cards in ${data.project} yet. Card some units first.`;
}

async function load({ recentre: centre = true } = {}) {
  const project = stage.dataset.project;
  const query = everything ? "?all=1" : "";
  const response = await fetch(`/api/graph/${encodeURIComponent(project)}${query}`);
  if (!response.ok) {
    toast(`could not load the graph: ${response.status}`, "bad");
    return;
  }
  data = await response.json();
  moved = {};
  /* An edge write refetches, and jumping the view back to the top-left after
     every arrow would undo the panning you did to reach the two boxes. */
  picked = { nodes: picked.nodes.filter((id) => data.nodes.some((n) => n.id === id)), edge: null };
  hoverEdge = null;
  document.getElementById("graph-all").classList.toggle("on", everything);
  document.getElementById("graph-linked").classList.toggle("on", !everything);
  describe();
  /* The panel is a second reading of the same payload, so it is repainted
     from the same place rather than by each caller that happens to reload. */
  paintOrder();
  if (centre) recentre();
  else draw();
}

async function save(positions) {
  try {
    const payload = await post(`/api/graph/${encodeURIComponent(stage.dataset.project)}/positions`, {
      positions,
      mtime: data.mtime,
    });
    data.positions = payload.positions;
    data.mtime = payload.mtime;
    moved = {};
    draw();
    return true;
  } catch (e) {
    /* `post` has already said what happened, and reloads on a stale write. */
    return false;
  }
}

async function putBack(node) {
  if (!node) {
    toast("point at a card, or select one");
    return;
  }
  /* For a box that has an arrow, this is "go back to where the layout puts
     you". For one that has none, its position is the only reason it is drawn
     at all, so forgetting it takes it off the canvas. Same rule, two visible
     consequences, and the message says which one happened. */
  const leaves = !data.edges.some((e) => e.src === node.id || e.dst === node.id);
  if (!(await save({ [node.id]: null }))) return;
  toast(
    leaves
      ? `${labelOf(node.id)} taken off the canvas`
      : `${node.id} back to its computed place`,
  );
  if (leaves) await load({ recentre: false });
}

// -- edges -----------------------------------------------------------------

/* Writing an edge writes `requires` into the dependent card's frontmatter.

   `requires` sits outside `content_hash` under both the current rule and the
   legacy one, so linking two approved cards demotes neither. That is what
   makes this safe to do by dragging: the order the deck is introduced in is a
   judgement about the deck, not a change to any card's content. */
async function write(dependent, body, said) {
  try {
    await post(`/api/cards/${encodeURIComponent(dependent)}/requires`, {
      ...body,
      mtime: (data.mtimes || {})[dependent] || "",
    });
  } catch (e) {
    return false; /* `post` has already said what happened */
  }
  await load({ recentre: false });
  toast(said);
  return true;
}

async function connect(dependent, prereq) {
  if (await write(dependent, { add: prereq }, `${labelOf(dependent)} needs ${labelOf(prereq)} · ${undoKeyName()} undoes`)) {
    undone.push({ dependent, remove: prereq });
  }
}

async function disconnect(edge) {
  if (!edge) return;
  const said = `${labelOf(edge.dst)} no longer needs ${labelOf(edge.src)} · ${undoKeyName()} undoes`;
  if (await write(edge.dst, { remove: edge.src }, said)) {
    undone.push({ dependent: edge.dst, add: edge.src });
    picked = { nodes: [], edge: null };
  }
}

async function undo() {
  const step = undone.pop();
  if (!step) {
    toast("nothing to undo");
    return;
  }
  if (step.positions) {
    if (await save(step.positions)) {
      await load({ recentre: false });
      const moved = Object.keys(step.positions).length;
      toast(`undone: ${moved} ${moved === 1 ? "box" : "boxes"} back`);
    }
    return;
  }
  const { dependent, ...op } = step;
  await write(dependent, op, `undone: ${labelOf(dependent)}`);
}

// -- putting a card on the canvas -------------------------------------------

/* A card with no `requires` either way is not drawn, which is what keeps the
   picture worth opening. You cannot connect what is not there, so this is how
   one gets on: give it a position, which is the same thing a drag writes, and
   `connected(keep)` on the server then keeps drawing it.

   Chosen by caption. A list of ninety rows reading `af5ca1`, `ae6e48` is not
   something anyone picks from. */
const picker = {
  open: false,
  query: "",
  /* Set when the picker was opened by dropping an arrow on empty space:
     `{from, side, at}`. Whatever gets picked lands at `at` and is connected to
     `from` in the same step, which is the gesture finishing rather than being
     thrown away. */
  connect: null,
};

function pickerRows() {
  const q = picker.query.trim().toLowerCase();
  return (data.absent || []).filter(
    (node) =>
      !q ||
      node.label.toLowerCase().includes(q) ||
      node.id.includes(q) ||
      node.detail.toLowerCase().includes(q),
  );
}

function paintPicker() {
  const list = document.getElementById("add-list");
  const empty = document.getElementById("add-empty");
  list.textContent = "";
  const rows = pickerRows();
  rows.slice(0, 200).forEach((node, i) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = `add-row${i === 0 ? " first" : ""}`;
    const name = document.createElement("span");
    name.className = `add-name${node.label ? "" : " unnamed"}`;
    name.textContent = node.label || "no caption yet";
    const where = document.createElement("span");
    where.className = "add-where";
    where.textContent = node.detail || node.id;
    row.append(name, where);
    row.addEventListener("click", () => addToCanvas(node));
    list.appendChild(row);
  });
  empty.hidden = rows.length > 0;
  empty.textContent = (data.absent || []).length
    ? "nothing matches that."
    : "every card in this project is already on the canvas.";
  const left = (data.absent || []).length;
  document.getElementById("add-count").textContent = picker.connect
    ? `connect ${labelOf(picker.connect.from.id)} to one of ${left}`
    : `${left} not on the canvas`;
}

/* Dropped where you are looking, not at the origin: the canvas pans, and a
   card added off-screen reads as an add that did nothing. Successive ones step
   down and right so they do not land on each other. */
let dropped = 0;

function landingSpot() {
  if (picker.connect) {
    /* Under the arrow that was dropped, offset so the box is not centred on
       the pointer and half on top of the port it came from. */
    const side = picker.connect.side === "right" ? 0 : -NODE_W;
    return [
      Math.round(picker.connect.at.x + side),
      Math.round(picker.connect.at.y - NODE_H / 2),
    ];
  }
  const box = stage.getBoundingClientRect();
  const step = dropped++ * 28;
  const middle = toWorld(box.width / 2, box.height / 2);
  return [
    Math.round(middle.x - NODE_W / 2 + step),
    Math.round(middle.y - NODE_H / 2 + step),
  ];
}

async function addToCanvas(node) {
  const joining = picker.connect;
  if (!(await save({ [node.id]: landingSpot() }))) return;
  if (joining) {
    /* Close first: the arrow appears behind the panel otherwise, and the
       gesture is finished either way. */
    togglePicker(false);
    const { prereq, dependent } = ends(joining.from, joining.side, node);
    await load({ recentre: false });
    await connect(dependent, prereq);
    return;
  }
  await load({ recentre: false });
  paintPicker();
  toast(`${node.label || node.id} added · drag a dot to connect it`);
}

function openPicker(connect = null) {
  picker.connect = connect;
  togglePicker(true);
}

function togglePicker(open) {
  const dialog = document.getElementById("add-card");
  if (!dialog) return;
  picker.open = open === undefined ? !dialog.open : open;
  const search = document.getElementById("add-search");
  if (picker.open) {
    dropped = 0;
    /* Cleared every time it opens. It kept whatever you last typed, so
       reopening showed a list filtered by a word you had forgotten about and
       read as most of the deck having vanished. */
    picker.query = "";
    search.value = "";
    paintPicker();
    if (!dialog.open) dialog.showModal();
    search.focus();
  } else {
    picker.connect = null;
    dialog.close();
  }
}

// -- selection --------------------------------------------------------------

/* What is picked: any number of boxes, or one arrow, never both. They are
   different kinds of thing to act on -- an arrow comes out of a card file, a
   box comes off the canvas -- and a Delete that had to choose between them
   would be guessing. */
let picked = { nodes: [], edge: null };

function isPicked(id) {
  return picked.nodes.includes(id);
}

function pickNodes(ids, add = false) {
  picked = { nodes: add ? [...new Set([...picked.nodes, ...ids])] : [...ids], edge: null };
}

function pickedBoxes() {
  return data.nodes.filter((n) => isPicked(n.id));
}

// -- pointer ---------------------------------------------------------------

/* Space turns a left-drag back into a pan, which is the one gesture the
   marquee took over. Middle-drag does it too, for a mouse with a wheel. */
let spaceHeld = false;
document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || aModalIsOpen()) return;
  spaceHeld = true;
  if (canvas) canvas.style.cursor = "grab";
});
document.addEventListener("keyup", (event) => {
  if (event.code === "Space") spaceHeld = false;
});

if (canvas) {
  canvas.addEventListener("pointerdown", (event) => {
    if (!data) return;
    const p = pointer(event);
    /* A port before the box it sits on. The dots overhang the border, so the
       box would otherwise swallow half of every grab. */
    const grabbed = portAt(p.x, p.y);
    if (grabbed) {
      link = {
        node: grabbed.node,
        side: grabbed.side,
        to: p,
        target: null,
        why: "",
        grabX: event.clientX,
        grabY: event.clientY,
        far: false,
      };
      canvas.setPointerCapture(event.pointerId);
      draw();
      return;
    }
    const node = nodeAt(p.x, p.y);
    if (node) {
      /* Grabbing a box that is not in the selection picks it, so a drag moves
         what you grabbed rather than the leftovers of an earlier one. Grabbing
         one that *is* in the selection keeps the whole selection, which is how
         six boxes move together. */
      if (event.shiftKey) {
        /* Toggle and stop. It used to fall through into the drag, which built
           `drag.from` from the selection *after* removing the box under the
           pointer: a shift-click that wandered four pixels rewrote the
           positions of every other selected card and left the one you clicked
           where it was. There is no undo for an arrangement you did not make.
           */
        const rest = picked.nodes.filter((id) => id !== node.id);
        pickNodes(isPicked(node.id) ? rest : [node.id], !isPicked(node.id));
        canvas.setPointerCapture(event.pointerId);
        draw();
        return;
      }
      if (!isPicked(node.id)) pickNodes([node.id]);
      drag = {
        kind: "boxes",
        from: Object.fromEntries(pickedBoxes().map((n) => [n.id, at(n.id)])),
        grabX: event.clientX,
        grabY: event.clientY,
        far: false,
      };
      canvas.setPointerCapture(event.pointerId);
      draw();
      return;
    }
    const panning = spaceHeld || event.button === 1;
    drag = {
      kind: panning ? "pan" : "marquee",
      grabX: event.clientX,
      grabY: event.clientY,
      pan: { ...pan },
      shift: event.shiftKey,
      far: false,
    };
    if (!panning) marquee = { from: p, to: p };
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (!data) return;
    const p = pointer(event);
    if (link) {
      link.to = p;
      if (
        Math.abs(event.clientX - link.grabX) > CLICK_SLOP ||
        Math.abs(event.clientY - link.grabY) > CLICK_SLOP
      ) {
        /* A click on a dot that never moved is a mis-click, not an attempt to
           connect to nothing. Only a real drag offers the picker. */
        link.far = true;
      }
      const over = nodeAt(p.x, p.y);
      link.target = over && over !== link.node ? over : null;
      if (link.target) {
        const { prereq, dependent } = ends(link.node, link.side, link.target);
        link.why = whyNot(prereq, dependent);
      } else {
        /* Over its own box is a refusal `whyNot` already has the words for.
           Nulling the target lost it, and the release then read as a drop on
           empty space and opened the card picker. */
        link.why = over === link.node ? "a card cannot need itself" : "";
      }
      canvas.title = link.why || "";
      draw();
      return;
    }
    if (!drag) {
      const overPort = portAt(p.x, p.y);
      const over = overPort ? overPort.node : nodeAt(p.x, p.y);
      const overEdge = over ? null : nearEdge(p.x, p.y);
      const same =
        over === hover &&
        overEdge === hoverEdge &&
        (overPort ? hoverPort && hoverPort.side === overPort.side : !hoverPort);
      if (same) return;
      hover = over;
      hoverPort = overPort;
      hoverEdge = overEdge;
      canvas.style.cursor = spaceHeld
        ? "grab"
        : overPort
          ? "crosshair"
          : over || overEdge
            ? "pointer"
            : "default";
      canvas.title = overPort
        ? overPort.side === "right"
          ? "drag to a card that needs this one"
          : "drag to a card this one needs"
        : over
          ? [over.label || "no caption yet", over.detail, over.id].filter(Boolean).join(" \u2014 ")
          : overEdge
            ? `${labelOf(overEdge.dst)} needs ${labelOf(overEdge.src)} \u2014 click to select`
            : "";
      draw();
      return;
    }
    const dx = event.clientX - drag.grabX;
    const dy = event.clientY - drag.grabY;
    if (Math.abs(dx) > CLICK_SLOP || Math.abs(dy) > CLICK_SLOP) drag.far = true;
    if (drag.kind === "boxes") {
      /* Screen pixels divided by the zoom, so a box keeps up with the pointer
         rather than lagging behind it at anything but life size. */
      Object.entries(drag.from).forEach(([id, spot]) => {
        moved[id] = [spot.x + dx / scale, spot.y + dy / scale];
      });
    } else if (drag.kind === "pan") {
      pan = { x: drag.pan.x + dx, y: drag.pan.y + dy };
    } else if (marquee) {
      marquee.to = p;
    }
    draw();
  });

  canvas.addEventListener("pointerup", (event) => {
    if (link) {
      const pending = link;
      link = null;
      canvas.title = "";
      draw();
      if (pending.target && !pending.why) {
        const { prereq, dependent } = ends(pending.node, pending.side, pending.target);
        connect(dependent, prereq);
      } else if (pending.why) {
        toast(pending.why, "bad");
      } else if (pending.far && !(data.absent || []).length) {
        /* Nothing to offer. In `every card` mode `absent` is empty by
           construction, so the fallback was always a dead end: a panel saying
           "connect this to one of 0". */
        toast("every card is already on the canvas");
      } else if (pending.far) {
        /* Let go over nothing, having actually dragged somewhere. The card you
           meant is very likely one of the ones not drawn -- that is the whole
           reason the picker exists -- so offer it rather than throwing the
           gesture away. Whatever is chosen lands where the arrow was dropped
           and is connected in the same step. */
        openPicker({ from: pending.node, side: pending.side, at: pending.to });
      }
      return;
    }
    if (!drag) return;
    const finished = drag;
    drag = null;

    if (finished.kind === "marquee") {
      const caught = marquee ? inMarquee() : [];
      marquee = null;
      if (finished.far) {
        pickNodes(
          caught.map((n) => n.id),
          finished.shift,
        );
        if (caught.length) toast(`${caught.length} selected`);
      } else {
        /* A click on nothing: take the arrow under it, or let the selection
           go. */
        const p = pointer(event);
        const edge = nearEdge(p.x, p.y);
        picked = edge
          ? { nodes: [], edge: { src: edge.src, dst: edge.dst } }
          : { nodes: [], edge: null };
      }
      draw();
      return;
    }
    if (finished.kind === "pan") return;
    if (finished.far) {
      /* Keyed off what the drag started with, not off `picked`. A key pressed
         mid-drag -- Escape, Delete -- clears the selection while the drag runs
         on, and the save then found nothing to write: the box stayed drawn
         where you had dragged it and went back on the next reload, with
         nothing on screen saying so. */
      const places = Object.fromEntries(
        Object.keys(finished.from)
          .filter((id) => moved[id])
          .map((id) => [id, moved[id]]),
      );
      if (Object.keys(places).length) {
        undone.push({
          positions: Object.fromEntries(
            Object.keys(places).map((id) => [id, (data.positions || {})[id] || null]),
          ),
        });
        save(places);
      }
    }
    draw();
  });

  /* Open what is under the pointer. Safe on `dblclick` now that the first
     click only selects: the two gestures no longer fight, which is why
     putting a box back had to be a key before. */
  canvas.addEventListener("dblclick", (event) => {
    if (!data) return;
    const node = nodeAt(pointer(event).x, pointer(event).y);
    if (node && node.href) location.href = node.href;
  });

  /* Plain wheel pans, ctrl or meta zooms. That is what a trackpad already
     sends -- a pinch arrives as a wheel event with `ctrlKey` set -- so pinch
     to zoom and two-finger scroll to pan both work with no setting. */
  canvas.addEventListener(
    "wheel",
    (event) => {
      if (!data) return;
      event.preventDefault();
      const box = canvas.getBoundingClientRect();
      if (event.ctrlKey || event.metaKey) {
        zoomTo(
          scale * Math.pow(ZOOM.step, -event.deltaY / 60),
          event.clientX - box.left,
          event.clientY - box.top,
        );
        return;
      }
      pan = { x: pan.x - event.deltaX, y: pan.y - event.deltaY };
      draw();
    },
    { passive: false },
  );

  canvas.addEventListener("pointercancel", () => {
    drag = null;
    link = null;
    marquee = null;
    moved = {};
    draw();
  });
}

window.addEventListener("resize", draw);

/* Two buttons, one state. Clicking the option already in force does nothing
   rather than toggling off it: a segment where pressing the lit half flips you
   to the other is a segment you cannot press to confirm where you are. */
function showDrawn(all) {
  if (all === everything) return;
  everything = all;
  load();
}

document.getElementById("graph-all").addEventListener("click", () => showDrawn(true));
document.getElementById("graph-linked").addEventListener("click", () => showDrawn(false));

document.getElementById("graph-reset").addEventListener("click", async () => {
  if (!data) return;
  const back = {};
  data.nodes.forEach((node) => {
    back[node.id] = null;
  });
  if (await save(back)) {
    toast("every box back to its computed place");
    await load({ recentre: false });
  }
});

document.getElementById("graph-add").addEventListener("click", () => openPicker());
document.getElementById("add-close").addEventListener("click", () => togglePicker(false));
document.getElementById("add-search").addEventListener("input", (event) => {
  picker.query = event.target.value;
  paintPicker();
});

/* Type a word, press Enter, take the first match. The list is sorted by
   nothing in particular, so this is only worth having because the search is
   over captions: two or three words usually leave one row. */
document.getElementById("add-search").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const first = document.querySelector(".add-row");
  if (first) first.click();
});

/* Escape closes the picker, cancels an arrow being drawn, and lets a selection
   go, in that order -- innermost first, which is what the key means. */
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (picker.open) return; /* the dialog closes itself, and `close` tidies up */
  if (drag && drag.kind === "boxes") {
    /* Put them back where the drag started. Clearing the selection and leaving
       the drag running is what left a box drawn somewhere it had not been
       saved to. */
    Object.entries(drag.from).forEach(([id, spot]) => delete moved[id]);
    drag = null;
    draw();
    return;
  }
  if (link) {
    link = null;
    canvas.title = "";
    draw();
  } else if (picked.nodes.length || picked.edge) {
    picked = { nodes: [], edge: null };
    draw();
  }
});

document.getElementById("add-card").addEventListener("close", () => {
  picker.open = false;
  picker.connect = null;
});

/* Delete acts on the selection, whichever kind it is: an arrow goes out of the
   card file, a card comes off the canvas. A card that has an arrow cannot come
   off, because an arrow is why it is drawn -- so that says so rather than
   doing nothing. */
async function removeSelected() {
  if (picked.edge) {
    await disconnect(picked.edge);
    return;
  }
  const boxes = pickedBoxes();
  if (!boxes.length) {
    toast("nothing selected. Drag a box round some cards, or click an arrow");
    return;
  }
  /* One write for the lot, and the ones that cannot come off reported once
     rather than as a toast each. */
  const stuck = boxes.filter((n) =>
    data.edges.some((e) => e.src === n.id || e.dst === n.id),
  );
  const free = boxes.filter((n) => !stuck.includes(n));
  if (free.length) {
    picked = { nodes: [], edge: null };
    if (await save(Object.fromEntries(free.map((n) => [n.id, null])))) {
      await load({ recentre: false });
    }
  }
  if (stuck.length) {
    toast(
      `${stuck.length} of those ${stuck.length === 1 ? "has an arrow" : "have arrows"}. ` +
        "Remove the arrow first",
      "bad",
    );
  } else if (free.length) {
    toast(`${free.length} taken off the canvas`);
  }
}

/* A key pressed with a drag or an arrow in flight. `bindKeys` guards on a
   modal being open and nothing guarded on a gesture being live, so `+`
   mid-drag opened the picker *over* an arrow that then still landed under it,
   and `A` changed the selection an in-flight drag was reading. */
/* The whole selection, as `remove-selected` does. Acting on one box out of
   six is the kind of asymmetry you only find by pressing it. */
async function forgetPositions() {
  const boxes = hover ? [hover] : pickedBoxes();
  if (!boxes.length) {
    toast("point at a card, or select some");
    return;
  }
  if (await save(Object.fromEntries(boxes.map((n) => [n.id, null])))) {
    await load({ recentre: false });
    toast(
      boxes.length === 1
        ? `${labelOf(boxes[0].id)} back to its computed place`
        : `${boxes.length} boxes back to their computed places`,
    );
  }
}

function openSelected() {
  const node = hover || pickedBoxes()[0];
  if (node && node.href) location.href = node.href;
  else toast("no card selected");
}

function selectAll() {
  pickNodes(data.nodes.map((n) => n.id));
  toast(`${picked.nodes.length} selected`);
  draw();
}

// -- the study order --------------------------------------------------------

/* The queue this picture is half of.

   `requires` is drawn on the canvas and it is one of two things deciding what
   Anki hands you next; the other is a sort key a few values long, and until
   now it was stated in a template and acted on in Python and visible in
   neither. A card could say "order 4 of 108" and nothing could say why, or
   what the deck would look like if easiest-first outranked most-useful-first.

   So this panel: the rule as rows you can drag into a different sequence, and
   under it the order it produces over every card in the project. Not only the
   drawn ones: what the canvas leaves out is exactly the cards that depend on
   nothing, and those are in the queue like any other. */

const rail = document.getElementById("order-rail");
const RAIL_KEPT = "forge:graph:study-order";

/* A box lit from the panel rather than by the pointer. Separate from `hover`
   on purpose: `hover` is what `x` and Enter act on, and pointing at a row in a
   list is not pointing at a box on the canvas. */
let spotlight = null;
/* What `markSelected` last painted, so `draw` can skip the DOM work on the
   hundred rows it is not changing. `draw` runs on every pointermove. */
let markedAs = null;

function railIsOpen() {
  return Boolean(rail) && !rail.hidden;
}

/* `remember` is off for a panel opened by a URL: arriving somewhere by a link
   somebody sent you is not a decision about how the view should open
   tomorrow. */
function toggleOrder(open, { remember = true } = {}) {
  if (!rail) return;
  const next = open === undefined ? rail.hidden : open;
  /* What the stage loses or gains, split between the two sides, so the middle
     of the picture stays in the middle. Opening a panel that shoved the graph
     sideways would mean re-finding whatever you were looking at. */
  const before = stage.getBoundingClientRect().width;
  rail.hidden = !next;
  document.body.classList.toggle("with-order-rail", next);
  const chip = document.getElementById("graph-order");
  chip.classList.toggle("on", next);
  chip.setAttribute("aria-expanded", next ? "true" : "false");
  /* Hidden while the panel is open: it is the way *back* to it, and a tab
     sitting on the seam between the canvas and the open panel is a control
     pointing at what is already in front of you. */
  document.getElementById("order-tab").hidden = next;
  try {
    if (remember) localStorage.setItem(RAIL_KEPT, next ? "1" : "");
  } catch (e) {
    /* A private window refuses storage. The panel still opens. */
  }
  pan.x += (stage.getBoundingClientRect().width - before) / 2;
  if (next) paintOrder();
  else spotlight = null;
  draw();
}

function orderData() {
  return (data && data.order) || { criteria: [], cards: [], names: [] };
}

function paintOrder() {
  if (!railIsOpen() || !data) return;
  paintCriteria();
  paintOrderCards();
}

// -- the rule ---------------------------------------------------------------

function paintCriteria() {
  const list = document.getElementById("order-criteria");
  list.textContent = "";
  orderData().criteria.forEach((criterion, i) => {
    const row = document.createElement("li");
    row.className = "criterion";
    row.dataset.name = criterion.name;
    row.tabIndex = 0;
    row.title = "drag, or press the up and down arrows, to change what outranks what";

    const grip = document.createElement("span");
    grip.className = "grip";
    grip.setAttribute("aria-hidden", "true");
    grip.textContent = "⠿";

    const rank = document.createElement("span");
    rank.className = "rank";
    rank.textContent = String(i + 1);

    const body = document.createElement("div");
    const name = document.createElement("b");
    name.textContent = criterion.label;
    const sense = document.createElement("span");
    sense.className = "sense";
    sense.textContent = criterion.sense;
    const detail = document.createElement("p");
    detail.className = "detail";
    detail.textContent = criterion.detail;
    body.append(name, sense, detail);

    row.append(grip, rank, body);
    row.addEventListener("pointerdown", (event) => startRuleDrag(event, row));
    row.addEventListener("keydown", (event) => nudgeRule(event, row));
    list.appendChild(row);
  });
}

function ruleNames() {
  return Array.from(document.querySelectorAll("#order-criteria .criterion")).map(
    (row) => row.dataset.name,
  );
}

/* Reorder by moving the row in the DOM as the pointer passes each neighbour's
   midpoint, rather than by animating a floating copy. Three rows, and the list
   under the pointer is the answer being previewed. */
let ruleDrag = null;

function startRuleDrag(event, row) {
  if (event.button !== 0) return;
  event.preventDefault();
  ruleDrag = { row, was: ruleNames() };
  row.classList.add("dragging");
  row.setPointerCapture(event.pointerId);
}

function slotFor(list, y) {
  const others = Array.from(list.querySelectorAll(".criterion:not(.dragging)"));
  let best = null;
  let nearest = Number.NEGATIVE_INFINITY;
  others.forEach((other) => {
    const box = other.getBoundingClientRect();
    const above = y - box.top - box.height / 2;
    if (above < 0 && above > nearest) {
      nearest = above;
      best = other;
    }
  });
  return best;
}

document.addEventListener("pointermove", (event) => {
  if (!ruleDrag) return;
  const list = document.getElementById("order-criteria");
  const before = slotFor(list, event.clientY);
  if (before) list.insertBefore(ruleDrag.row, before);
  else list.appendChild(ruleDrag.row);
  renumberRules();
});

document.addEventListener("pointerup", () => {
  if (!ruleDrag) return;
  const { row, was } = ruleDrag;
  ruleDrag = null;
  row.classList.remove("dragging");
  const now = ruleNames();
  if (now.join() !== was.join()) saveRule(now);
});

function renumberRules() {
  document.querySelectorAll("#order-criteria .criterion").forEach((row, i) => {
    row.querySelector(".rank").textContent = String(i + 1);
  });
}

/* The same reorder from the keyboard. A drag is the gesture this was asked
   for, and a control that only answers to a drag is one somebody cannot use. */
function nudgeRule(event, row) {
  const step = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0;
  if (!step) return;
  event.preventDefault();
  const list = row.parentElement;
  const rows = Array.from(list.children);
  const to = rows.indexOf(row) + step;
  if (to < 0 || to >= rows.length) return;
  const was = ruleNames();
  if (step < 0) list.insertBefore(row, rows[to]);
  else list.insertBefore(rows[to], row);
  renumberRules();
  row.focus();
  saveRule(ruleNames(), was);
}

async function saveRule(names, was) {
  const said = document.getElementById("order-saved");
  try {
    const payload = await post("/api/study-order", { order: names });
    said.hidden = false;
    said.textContent = `${payload.sentence} · written to ${payload.path}`;
    /* Refetch rather than re-sort here. The criteria also decide the y order
       inside a layer of the layout, so the picture moves too, and computing
       that in two places is how the two come to disagree. */
    await load({ recentre: false });
    toast(`study order: ${names.join(", then ")}`);
  } catch (e) {
    /* `post` has already said what happened. Put the rows back where they
       were, so the panel is not showing an order the file does not have. */
    if (was) paintCriteria();
    else paintOrder();
  }
}

// -- the order it produces --------------------------------------------------

function gradeRow(row) {
  const chips = document.createElement("span");
  chips.className = "grades";
  orderData().criteria.forEach((criterion) => {
    const value = row.values[criterion.name];
    const chip = document.createElement("span");
    chip.className = `grade${value ? "" : " none"}`;
    chip.title = value
      ? `${criterion.label}: ${value}`
      : `${criterion.label}: ${criterion.unset}. It sorts last within its group`;
    /* The printed position is a number and reads as one; a grading is a word.
       Both are the value of one criterion, so both are one chip. */
    chip.textContent = value
      ? criterion.name === "printed"
        ? `#${value}`
        : value
      : criterion.unset;
    chips.appendChild(chip);
  });
  return chips;
}

/* What `requires` did to this card's place, in words. The number alone is not
   actionable: the question it raises is "should it have been?", and the answer
   is the card at the other end of the arrow. */
function shiftNote(row) {
  if (!row.shift) return null;
  const places = Math.abs(row.shift);
  const word = `${places} ${places === 1 ? "place" : "places"}`;
  const note = document.createElement("span");
  note.className = `shift ${row.shift > 0 ? "up" : "down"}`;
  /* A word rather than an arrow glyph. `↑27` beside `#173` read as the number
     127: a thin arrow at 10px is not a symbol, it is a stroke. */
  note.textContent = `${places} ${row.shift > 0 ? "earlier" : "later"}`;
  note.title =
    row.shift > 0
      ? row.owes
        ? `${word} earlier than the rule alone: ${row.owes_label || row.owes} needs it, ` +
          "and a prerequisite is at least as important as the thing that needs it"
        : `${word} earlier than the rule alone, because something needs it`
      : `${word} later than the rule alone: cards were pulled in front of it by ` +
        "what depends on them";
  return note;
}

function paintOrderCards() {
  const list = document.getElementById("order-cards");
  const empty = document.getElementById("order-empty");
  const sub = document.getElementById("order-sub");
  const rows = orderData().cards;
  list.textContent = "";
  empty.hidden = rows.length > 0;
  empty.textContent = "No cards in this project yet.";
  const drawn = rows.filter((r) => r.drawn).length;
  sub.textContent = rows.length
    ? `${rows.length} ${rows.length === 1 ? "card" : "cards"} · ${drawn} on the canvas`
    : "";

  rows.forEach((row) => {
    const item = document.createElement("li");
    item.className = `order-card${row.drawn ? "" : " off"}`;
    item.dataset.id = row.id;

    const place = document.createElement("span");
    place.className = "place";
    place.textContent = String(row.place);

    const body = document.createElement("button");
    body.type = "button";
    body.className = "order-open";
    body.title = row.drawn
      ? "find it on the canvas"
      : "not on the canvas: click to put it there";
    const name = document.createElement("span");
    name.className = `order-name${row.label ? "" : " unnamed"}`;
    name.textContent = row.label || "no caption yet";
    const line = document.createElement("span");
    line.className = "order-meta";
    line.append(gradeRow(row));
    const moved = shiftNote(row);
    if (moved) line.append(moved);
    body.append(name, line);
    body.addEventListener("click", () => reachCard(row));
    body.addEventListener("pointerenter", () => {
      spotlight = row.id;
      draw();
    });
    body.addEventListener("pointerleave", () => {
      spotlight = null;
      draw();
    });

    const open = document.createElement("a");
    open.className = "order-review";
    open.href = row.href;
    open.textContent = "→";
    open.title = "open the card for review";

    item.append(place, body, open);
    list.appendChild(item);
  });
  markedAs = null;
  markSelected();
}

/* Selection, one way and the other. Clicking a row finds the box; selecting a
   box marks the row, because the panel is only worth having open if it says
   where the thing in front of you sits. */
function markSelected() {
  if (!railIsOpen()) return;
  const now = picked.nodes.join();
  if (now === markedAs) return;
  markedAs = now;
  document.querySelectorAll("#order-cards .order-card").forEach((item) => {
    const on = isPicked(item.dataset.id);
    item.classList.toggle("on", on);
    if (on) item.scrollIntoView({ block: "nearest" });
  });
}

async function reachCard(row) {
  /* A card the canvas is not drawing has no box to find, and the reason it is
     not drawn is that nothing depends on it. Putting it there is the step you
     were about to take anyway, and `x` takes it back off. */
  if (!row.drawn) {
    await addToCanvas({ id: row.id, label: row.label, detail: "" });
    return;
  }
  pickNodes([row.id]);
  const spot = at(row.id);
  const box = stage.getBoundingClientRect();
  pan = {
    x: box.width / 2 - (spot.x + NODE_W / 2) * scale,
    y: box.height / 2 - (spot.y + NODE_H / 2) * scale,
  };
  draw();
}

document.getElementById("graph-order").addEventListener("click", () => toggleOrder());
document.getElementById("order-close").addEventListener("click", () => toggleOrder(false));
document.getElementById("order-tab").addEventListener("click", () => toggleOrder(true));

function mid(handler) {
  return () => {
    if (link || drag) {
      toast("finish the drag first");
      return;
    }
    handler();
  };
}

bindKeys({
  "every-card": mid(() => showDrawn(!everything)),
  "add-card": mid(() => openPicker()),
  "study-order": () => toggleOrder(),
  recentre,
  "forget-position": forgetPositions,
  undo,
  "remove-selected": removeSelected,
  "remove-selected-alt": removeSelected,
  "open-card": openSelected,
  "zoom-in": () => zoomBy(ZOOM.step),
  "zoom-out": () => zoomBy(1 / ZOOM.step),
  "select-all": mid(selectAll),
  /* The one shared key this view can honour beyond undo. `filters` here is
     the only filter the canvas has, and `guide` has no guide to open. */
  projects: openGallery,
});

/* Reopened where you left it, unless the link says otherwise.

   `?order=1` opens it and `?order=0` shuts it, which makes the panel part of
   what a URL can say: a link to "this project, with its queue" is a different
   thing to send somebody than a link to the picture. It is also the only way
   to photograph it, since `assets/make_assets.py` points a fresh browser at a
   URL and a fresh browser has no stored preference.

   The link does not overwrite the preference. Arriving somewhere by a link
   somebody sent you is not a decision about how you want the view to open
   tomorrow. */
const asked = new URLSearchParams(location.search).get("order");
if (asked !== null) {
  toggleOrder(asked !== "0", { remember: false });
} else {
  try {
    if (localStorage.getItem(RAIL_KEPT)) toggleOrder(true);
  } catch (e) {
    /* No storage: it starts closed, which is the default anyway. */
  }
}

load();
