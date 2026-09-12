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
/* The dragged position lives here until `pointerup` posts it. Writing on every
   `pointermove` would be a file write per frame. */
let moved = {};

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

function drawEdge(edge) {
  const from = centre(edge.src);
  const to = onBorder(from, centre(edge.dst));
  const lit = hover && (edge.src === hover.id || edge.dst === hover.id);
  /* Muted rather than `--line`. The arrows are the content here, not a border
     between two things, and at `--line` on the dark ground they were a shade
     off the background: the first render read as a field of unconnected
     boxes. */
  ctx.strokeStyle = lit ? colours.accent : colours.muted;
  ctx.fillStyle = ctx.strokeStyle;
  ctx.lineWidth = lit ? 2 : 1.25;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();

  const angle = Math.atan2(to.y - from.y, to.x - from.x);
  const wing = 9;
  ctx.beginPath();
  ctx.moveTo(to.x, to.y);
  ctx.lineTo(to.x - wing * Math.cos(angle - 0.4), to.y - wing * Math.sin(angle - 0.4));
  ctx.lineTo(to.x - wing * Math.cos(angle + 0.4), to.y - wing * Math.sin(angle + 0.4));
  ctx.closePath();
  ctx.fill();
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
  const lit = hover && hover.id === node.id;

  ctx.save();
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
  ctx.restore();

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
  note.textContent = data.total
    ? `No card in ${data.source} needs another one yet. ` +
      "Add `requires: [<uid>]` to a card, or press a to see every card."
    : `No cards in ${data.source} yet.`;
}

async function load() {
  const source = stage.dataset.source;
  const query = everything ? "?all=1" : "";
  const response = await fetch(`/api/graph/${encodeURIComponent(source)}${query}`);
  if (!response.ok) {
    toast(`could not load the graph: ${response.status}`, "bad");
    return;
  }
  data = await response.json();
  moved = {};
  document.getElementById("graph-all").classList.toggle("on", everything);
  describe();
  recentre();
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
  if (await save({ [node.id]: null })) toast(`${node.id} back to its computed place`);
}

// -- pointer ---------------------------------------------------------------

if (canvas) {
  canvas.addEventListener("pointerdown", (event) => {
    if (!data) return;
    const p = pointer(event);
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
    if (!drag) {
      const p = pointer(event);
      const over = nodeAt(p.x, p.y);
      if (over === hover) return;
      hover = over;
      canvas.style.cursor = over ? "pointer" : "grab";
      /* The tooltip is the whole detail line: the label is cut to two lines in
         a 212px box, and the citation is what says which equation this is. */
      canvas.title = over
        ? [over.label || "no caption yet", over.detail, over.id].filter(Boolean).join(" — ")
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

  canvas.addEventListener("pointerup", () => {
    if (!drag) return;
    const { node, far } = drag;
    drag = null;
    if (node && !far) {
      if (node.href) location.href = node.href;
      return;
    }
    if (node && far) save({ [node.id]: moved[node.id] });
  });

  canvas.addEventListener("pointercancel", () => {
    drag = null;
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
  if (await save(back)) toast("every box back to its computed place");
});

bindKeys({
  a: () => document.getElementById("graph-all").click(),
  0: recentre,
  x: () => putBack(hover),
});

load();
