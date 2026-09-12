/* The dependency canvas: one source's `requires`, drawn and arranged by hand.

   Everything on screen comes from `/api/graph/<source>`. The server decides
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
let pan = { x: MARGIN, y: MARGIN };
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
let selected = null;
/* The dragged position lives here until `pointerup` posts it. Writing on every
   `pointermove` would be a file write per frame. */
let moved = {};
/* Inverse operations, newest last. An edge undo is "remove what you added",
   which is exact and needs nothing remembered about the file; the app's own
   undo stack restores a *status* snapshot and has nothing to say here. */
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
  return { x: event.clientX - box.left - pan.x, y: event.clientY - box.top - pan.y };
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
      if (Math.hypot(x - spot.x, y - spot.y) <= PORT_GRAB) {
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

function nearEdge(x, y) {
  for (const edge of data.edges) {
    const a = centre(edge.src);
    const b = centre(edge.dst);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = dx * dx + dy * dy;
    const t = len ? Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / len)) : 0;
    if (Math.hypot(x - (a.x + t * dx), y - (a.y + t * dy)) <= EDGE_GRAB) return edge;
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

/* Where the line from `from` to `to` leaves `to`'s box. Drawn centre to centre
   the arrowheads land under the boxes and the direction -- the one thing the
   picture is for -- is invisible. */
function onBorder(from, to) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (!dx && !dy) return to;
  const half = { x: NODE_W / 2 + 6, y: NODE_H / 2 + 6 };
  const scale = Math.min(
    dx ? half.x / Math.abs(dx) : Infinity,
    dy ? half.y / Math.abs(dy) : Infinity,
  );
  return { x: to.x - dx * scale, y: to.y - dy * scale };
}

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

function stateOf(id) {
  const node = (data.nodes || []).find((n) => n.id === id);
  return node ? node.state : "";
}

function drawEdge(edge) {
  const from = centre(edge.src);
  const to = onBorder(from, centre(edge.dst));
  const lit = hover && (edge.src === hover.id || edge.dst === hover.id);
  const on = selected && selected.src === edge.src && selected.dst === edge.dst;
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
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();
  ctx.setLineDash([]);
  arrowhead(from, to);
  ctx.restore();
}

/* The arrow being dragged, and whether it may land where it is pointing. */
function drawPending() {
  const spot = port(link.node.id, link.side);
  const tip = link.target ? centre(link.target.id) : link.to;
  const end = link.target ? onBorder(spot, tip) : tip;
  ctx.save();
  ctx.strokeStyle = link.why ? colours.bad : colours.accent;
  ctx.fillStyle = ctx.strokeStyle;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(spot.x, spot.y);
  ctx.lineTo(end.x, end.y);
  ctx.stroke();
  ctx.setLineDash([]);
  /* The head is on the end that will carry it once this lands, which for a
     left-port drag is the box you started from. Drawn now rather than on
     release, so the direction is settled before you commit to it. */
  if (link.side === "right") arrowhead(spot, end);
  else arrowhead(end, spot);
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
  const lit = (hover && hover.id === node.id) || (link && link.target === node);

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
  ctx.strokeStyle = lit ? colours.accent : edge;
  ctx.lineWidth = lit ? 2 : 1.25;
  /* A card from another source is a real node: `requires` may cross them, and
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
  data.edges.forEach(drawEdge);
  data.nodes.forEach(drawNode);
  if (link) drawPending();
}

/* Put the whole picture on screen, top-left, rather than wherever the last pan
   left it. Also what `0` does. */
function recentre() {
  if (!data || !data.nodes.length) return;
  const xs = data.nodes.map((n) => at(n.id).x);
  const ys = data.nodes.map((n) => at(n.id).y);
  pan = { x: MARGIN - Math.min(...xs), y: MARGIN - Math.min(...ys) };
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
  note.textContent = data.total
    ? `No card in ${data.source} needs another one yet. ` +
      "Press n to put a card on the canvas, then drag from a dot on its edge " +
      "to another card to say which comes first."
    : `No cards in ${data.source} yet. Card some units first.`;
}

async function load({ recentre: centre = true } = {}) {
  const source = stage.dataset.source;
  const query = everything ? "?all=1" : "";
  const response = await fetch(`/api/graph/${encodeURIComponent(source)}${query}`);
  if (!response.ok) {
    toast(`could not load the graph: ${response.status}`, "bad");
    return;
  }
  data = await response.json();
  moved = {};
  /* An edge write refetches, and jumping the view back to the top-left after
     every arrow would undo the panning you did to reach the two boxes. */
  selected = null;
  hoverEdge = null;
  document.getElementById("graph-all").classList.toggle("on", everything);
  describe();
  if (centre) recentre();
  else draw();
}

async function save(positions) {
  try {
    const payload = await post(`/api/graph/${encodeURIComponent(stage.dataset.source)}/positions`, {
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
  if (!node) return;
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
  if (await write(dependent, { add: prereq }, `${labelOf(dependent)} needs ${labelOf(prereq)} · z undoes`)) {
    undone.push({ dependent, remove: prereq });
  }
}

async function disconnect(edge) {
  if (!edge) return;
  const said = `${labelOf(edge.dst)} no longer needs ${labelOf(edge.src)} · z undoes`;
  if (await write(edge.dst, { remove: edge.src }, said)) {
    undone.push({ dependent: edge.dst, add: edge.src });
    selected = null;
  }
}

async function undo() {
  const step = undone.pop();
  if (!step) {
    toast("nothing to undo");
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
  rows.slice(0, 200).forEach((node) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "add-row";
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
    : "every card in this source is already on the canvas.";
  document.getElementById("add-count").textContent =
    `${(data.absent || []).length} not on the canvas`;
}

/* Dropped where you are looking, not at the origin: the canvas pans, and a
   card added off-screen reads as an add that did nothing. Successive ones step
   down and right so they do not land on each other. */
let dropped = 0;

async function addToCanvas(node) {
  const box = stage.getBoundingClientRect();
  const step = dropped++ * 28;
  const spot = [
    Math.round(-pan.x + box.width / 2 - NODE_W / 2 + step),
    Math.round(-pan.y + box.height / 2 - NODE_H / 2 + step),
  ];
  if (!(await save({ [node.id]: spot }))) return;
  await load({ recentre: false });
  paintPicker();
  toast(`${node.label || node.id} added · drag a dot to connect it`);
}

function togglePicker(open) {
  const dialog = document.getElementById("add-card");
  if (!dialog) return;
  picker.open = open === undefined ? !dialog.open : open;
  if (picker.open) {
    dropped = 0;
    paintPicker();
    dialog.showModal();
    document.getElementById("add-search").focus();
  } else {
    dialog.close();
  }
}

// -- pointer ---------------------------------------------------------------

if (canvas) {
  canvas.addEventListener("pointerdown", (event) => {
    if (!data) return;
    const p = pointer(event);
    /* A port before the box it sits on. The dots overhang the border, so the
       box would otherwise swallow half of every grab. */
    const grabbed = portAt(p.x, p.y);
    if (grabbed) {
      link = { node: grabbed.node, side: grabbed.side, to: p, target: null, why: "" };
      canvas.setPointerCapture(event.pointerId);
      draw();
      return;
    }
    const node = nodeAt(p.x, p.y);
    drag = {
      node,
      from: node ? at(node.id) : null,
      grabX: event.clientX,
      grabY: event.clientY,
      pan: { ...pan },
      far: false,
    };
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (!data) return;
    const p = pointer(event);
    if (link) {
      link.to = p;
      const over = nodeAt(p.x, p.y);
      link.target = over && over !== link.node ? over : null;
      if (link.target) {
        const { prereq, dependent } = ends(link.node, link.side, link.target);
        link.why = whyNot(prereq, dependent);
      } else {
        link.why = "";
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
      canvas.style.cursor = overPort ? "crosshair" : over || overEdge ? "pointer" : "grab";
      canvas.title = overPort
        ? overPort.side === "right"
          ? "drag to a card that needs this one"
          : "drag to a card this one needs"
        : over
          ? [over.label || "no caption yet", over.detail, over.id].filter(Boolean).join(" — ")
          : overEdge
            ? `${labelOf(overEdge.dst)} needs ${labelOf(overEdge.src)} — click to select`
            : "";
      draw();
      return;
    }
    const dx = event.clientX - drag.grabX;
    const dy = event.clientY - drag.grabY;
    if (Math.abs(dx) > CLICK_SLOP || Math.abs(dy) > CLICK_SLOP) drag.far = true;
    if (drag.node) moved[drag.node.id] = [drag.from.x + dx, drag.from.y + dy];
    else pan = { x: drag.pan.x + dx, y: drag.pan.y + dy };
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
      }
      return;
    }
    if (!drag) return;
    const { node, far } = drag;
    drag = null;
    if (node && !far) {
      if (node.href) location.href = node.href;
      return;
    }
    if (node && far) {
      save({ [node.id]: moved[node.id] });
      return;
    }
    /* A click on nothing. Either an arrow was under it, or the selection is
       being let go. */
    if (!far) {
      const p = pointer(event);
      selected = nearEdge(p.x, p.y);
      draw();
    }
  });

  canvas.addEventListener("pointercancel", () => {
    drag = null;
    link = null;
    moved = {};
    draw();
  });
}

window.addEventListener("resize", draw);

document.getElementById("graph-all").addEventListener("click", () => {
  everything = !everything;
  load();
});

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

document.getElementById("graph-add").addEventListener("click", () => togglePicker(true));
document.getElementById("add-close").addEventListener("click", () => togglePicker(false));
document.getElementById("add-search").addEventListener("input", (event) => {
  picker.query = event.target.value;
  paintPicker();
});

/* Escape closes the picker, cancels an arrow being drawn, and lets a selected
   one go, in that order -- innermost first, which is what the key means. */
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (picker.open) return; /* the dialog closes itself */
  if (link) {
    link = null;
    canvas.title = "";
    draw();
  } else if (selected) {
    selected = null;
    draw();
  }
});

document.getElementById("add-card").addEventListener("close", () => {
  picker.open = false;
});

bindKeys({
  a: () => document.getElementById("graph-all").click(),
  0: recentre,
  x: () => putBack(hover),
  n: () => togglePicker(true),
  z: undo,
  Delete: () => disconnect(selected),
  Backspace: () => disconnect(selected),
  /* The one shared key this view can honour. `f` and `?` toggle the filter
     rail and the guide, and this view has neither; `g` opens the source
     picker, whose button is in the header here like everywhere else, and
     leaving it unbound made the same button answer to the mouse on three
     views and to the keyboard on two. */
  g: openGallery,
});

load();
