/* Shared machinery for both views: one item at a time, keyboard-first.
   The app is a view over files -- nothing here caches anything, and every
   write round-trips to the server, which re-reads from disk. */

const KATEX_DELIMS = [
  { left: "$$", right: "$$", display: true },
  { left: "$", right: "$", display: false },
  { left: "\\[", right: "\\]", display: true },
  { left: "\\(", right: "\\)", display: false },
];

/* If KaTeX never loaded, every card shows raw `$...$` and looks like the
   LaTeX is wrong. Returning quietly made a loading failure indistinguishable
   from a transcription failure, which is the worst thing this view could get
   wrong -- so say so, once. */
let katexWarned = false;

function renderMath(root) {
  if (typeof renderMathInElement !== "function") {
    if (!katexWarned) {
      katexWarned = true;
      toast("KaTeX did not load — maths is showing as raw LaTeX, not wrong", "bad");
    }
    return;
  }
  renderMathInElement(root, { delimiters: KATEX_DELIMS, throwOnError: false });
}

function toast(message, kind = "") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast " + kind;
  el.hidden = false;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => (el.hidden = true), 2600);
}

/* Cancel is not a submit button (see base.html), so it needs closing by
   hand. Bound once, not per call. */
document.addEventListener("DOMContentLoaded", () => {
  const cancel = document.getElementById("prompt-cancel");
  if (cancel) {
    cancel.addEventListener("click", () =>
      document.getElementById("prompt").close("cancel"),
    );
  }
});

function ask(label, value = "") {
  const dialog = document.getElementById("prompt");
  const input = document.getElementById("prompt-input");
  document.getElementById("prompt-label").textContent = label;
  input.value = value;
  dialog.showModal();
  input.focus();
  input.select();
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "ok" ? input.value.trim() : null),
      { once: true },
    );
  });
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (e) {
    payload = { error: response.statusText };
  }
  if (response.status === 409) {
    toast(payload.error || "file changed on disk — reloading", "bad");
    setTimeout(() => location.reload(), 1400);
    throw new Error("stale");
  }
  if (!response.ok) {
    toast(payload.detail || payload.error || `error ${response.status}`, "bad");
    throw new Error(payload.detail || payload.error || response.statusText);
  }
  return payload;
}

class Deck {
  constructor() {
    this.items = Array.from(document.querySelectorAll(".item"));
    this.index = 0;
    this.position = document.getElementById("position");
    if (!this.items.length) {
      const empty = document.getElementById("empty-filter");
      if (empty) empty.hidden = false;
    }
    this.show(0);
  }

  get current() {
    return this.items[this.index] || null;
  }

  show(index) {
    if (!this.items.length) {
      // Say "0 / 0" rather than leaving the last count on screen. An empty
      // list is a real state, not a failure to paint.
      if (this.position) this.position.textContent = "0 / 0";
      return;
    }
    this.index = Math.max(0, Math.min(index, this.items.length - 1));
    this.items.forEach((item, i) => (item.hidden = i !== this.index));
    const item = this.current;
    if (item && !item.dataset.rendered) {
      renderMath(item);
      item.dataset.rendered = "1";
    }
    if (this.position) {
      const pending = this.remaining;
      const total = this.items.length;
      this.position.textContent =
        pending === total
          ? `${this.index + 1} / ${total}`
          : `${this.index + 1} / ${total} · ${pending} left`;
    }
    // `start`, not `nearest`. A unit that is taller than the window -- a
    // page-wide crop with thirty marks listed under it -- is scrolled by
    // `nearest` so that its *bottom* comes into view, which lands you in the
    // middle of a card you have not read yet. `scroll-margin-top` keeps the
    // sticky header from covering the line you land on.
    //
    // Not on the first paint, though: the page is already at the top and
    // scrolling it anywhere else is the browser moving under you before you
    // have touched anything.
    if (item && this.painted) item.scrollIntoView({ block: "start" });
    this.painted = true;
  }

  next() {
    if (this.index >= this.items.length - 1) {
      toast("end of the list");
      return;
    }
    this.show(this.index + 1);
  }

  /* Forward means "the next thing still needing a decision". Walking back
     over settled items is deliberate -- that is how you reach something you
     just acted on -- but walking *forward* over them is only ever re-treading
     work, which reads as the navigation being stuck. */
  nextPending() {
    for (let i = this.index + 1; i < this.items.length; i += 1) {
      if (!this.items[i].dataset.settled) {
        this.show(i);
        return;
      }
    }
    if (this.index < this.items.length - 1) {
      this.show(this.index + 1); // nothing pending ahead: still let it move
      return;
    }
    toast("end of the list");
  }

  prev() {
    this.show(this.index - 1);
  }

  /* Mark the current item as no longer matching the active filter, and move
     on. It stays in the list: removing it meant that a mis-pressed key left
     you with no way back to the thing you had just acted on, because `k`
     could not reach a node that no longer existed. The file is the truth;
     this is the view keeping up until the next reload. */
  settle(label) {
    const item = this.current;
    if (!item) return;
    item.dataset.settled = label || "done";
    let banner = item.querySelector(".settled");
    if (!banner) {
      banner = document.createElement("p");
      banner.className = "settled";
      item.prepend(banner);
    }
    banner.textContent = `${label} — no longer matches this filter. z undoes it.`;
    this.nextPending();
  }

  get remaining() {
    return this.items.filter((item) => !item.dataset.settled).length;
  }
}

/* Every action needs something to act on. Returning silently made an empty
   filter look like a broken keyboard, so say which it is. */
function currentOf(deck) {
  const item = deck.current;
  if (!item) toast("nothing here to act on — the filter is empty");
  return item;
}

function bindKeys(handlers) {
  document.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (document.getElementById("prompt").open) return;
    // A modal over the deck owns the keyboard: `s` in the gallery's search box
    // would otherwise skip whatever unit was behind it.
    if (galleryIsOpen()) return;
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
    const handler = handlers[event.key];
    if (!handler) return;
    event.preventDefault();
    handler();
  });
}

/* Crops are rendered from the source document on request, so a missing PDF
   should read as an explanation rather than a broken-image icon. */
document.addEventListener(
  "error",
  (event) => {
    const img = event.target;
    if (!(img instanceof HTMLImageElement) || !img.hasAttribute("data-crop")) return;
    img.hidden = true;
    const note = img.parentElement && img.parentElement.querySelector(".crop-missing");
    if (note) note.hidden = false;
  },
  true,
);

/* Both rails are fixed panels that start *under* the header. They used to
   start at y=0 with a higher stacking order, which put the filter panel on top
   of the view links -- the one row that has to be reachable from everywhere.

   Measured rather than assumed, because the header wraps: at a narrow window
   it is two rows tall, which is exactly when a hard-coded height is wrong. */
(function trackBarHeights() {
  const bars = [
    ["--header-h", document.getElementById("topbar")],
    // The footer is sticky at the bottom and stacks above the rails, so a rail
    // running to `bottom: 0` had its last panel -- the commands -- sliding
    // underneath the shortcut row and out of reach.
    ["--footer-h", document.querySelector("footer.bar")],
  ].filter(([, el]) => el);
  const set = () =>
    bars.forEach(([name, el]) =>
      document.documentElement.style.setProperty(name, `${el.offsetHeight}px`),
    );
  set();
  if (window.ResizeObserver) {
    const watch = new ResizeObserver(set);
    bars.forEach(([, el]) => watch.observe(el));
  } else {
    window.addEventListener("resize", set);
  }
})();

/* The filter-rail. Its state persists: a triage session is long, and being asked
   to re-open the same panel every reload is its own small tax. */
const FILTERS_KEY = "anki-forge.filters";

function applyFilters(open) {
  document.body.classList.toggle("filters-off", !open);
  document.body.classList.toggle("filters-on", open);
}

function toggleFilters() {
  const open = document.body.classList.contains("filters-off");
  applyFilters(open);
  try {
    localStorage.setItem(FILTERS_KEY, open ? "open" : "closed");
  } catch {
    /* private window, or storage disabled: the toggle still works this session */
  }
}

try {
  if (localStorage.getItem(FILTERS_KEY) === "closed") applyFilters(false);
} catch {
  /* no stored preference is the same as the default */
}

/* Two buttons, one job. The fold arrow lives inside the rail and goes away
   with it; the tab stays on screen, which is the only state where an
   affordance is essential. `f` still does it from the keyboard. */
["filters-fold", "filters-tab"].forEach((id) => {
  const button = document.getElementById(id);
  if (button) button.addEventListener("click", toggleFilters);
});

/* The guide cycles through three sizes rather than toggling two, because
   the question it answers changes: mid-session you want the counts, and only
   occasionally the whole explanation. Remembered, since which size suits you
   depends on how well you know the tool, not on which page you are on. */
const GUIDE_KEY = "anki-forge.guide";
/* The class names are the contract with the stylesheet, so they are written
   out rather than built by concatenation -- a rename of one half otherwise
   leaves the two silently disagreeing. */
const GUIDE_SIZES = ["counts", "full", "off"];
const GUIDE_LABEL = {
  counts: "guide: counts",
  full: "guide: everything",
  off: "guide hidden",
};

function applyGuide(size) {
  GUIDE_SIZES.forEach((name) =>
    document.body.classList.toggle("guide-" + name, name === size),
  );
}

function cycleGuide() {
  const current = GUIDE_SIZES.find((name) =>
    document.body.classList.contains("guide-" + name),
  );
  const next = GUIDE_SIZES[(GUIDE_SIZES.indexOf(current) + 1) % GUIDE_SIZES.length];
  applyGuide(next);
  toast(GUIDE_LABEL[next]);
  try {
    localStorage.setItem(GUIDE_KEY, next);
  } catch {
    /* private window: the cycle still works for this session */
  }
}

(function restoreGuide() {
  let size = "counts";
  try {
    const stored = localStorage.getItem(GUIDE_KEY);
    if (GUIDE_SIZES.includes(stored)) size = stored;
  } catch {
    /* no stored preference is the same as the default */
  }
  applyGuide(size);
  ["guide-cycle", "guide-tab"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.addEventListener("click", cycleGuide);
  });
})();

/* Two things drag: the rails, and the split between a crop and its
   transcription. Both are per-viewer preferences rather than layout
   decisions -- which side wants the room changes crop by crop, and how much
   rail you want depends on your screen -- so both are remembered.
   One pointer-drag helper serves both, because two hand-rolled drag loops is
   how they end up behaving differently. */
/* Two things split down the middle, and neither ratio is a decision the
   stylesheet can make once: a dense matrix wants the crop wide, a long
   identity wants the text wide, and how much room the metadata deserves
   changes with how much of it there is. Named, so each remembers its own. */
const SPLITS = {
  units: {
    key: "anki-forge.split.units",
    left: "--split-units",
    right: "--split-units-right",
    fallback: 0.5,
  },
  card: {
    key: "anki-forge.split.card",
    left: "--split-card",
    right: "--split-card-right",
    fallback: 0.72,
  },
  /* The guide's two panes split *vertically*: the diagram is glanced at and
     the legend is read, and which deserves the room changes with the work. */
  guide: {
    key: "anki-forge.split.guide",
    left: "--split-guide",
    right: "--split-guide-bottom",
    fallback: 0.55,
    axis: "y",
  },
  /* And the triage column's, between what the reader wrote on the page and
     what has been written about the unit since. Different questions, asked at
     different moments; stacked in one scroll the second was always below the
     fold. */
  beside: {
    key: "anki-forge.split.beside",
    left: "--split-beside",
    right: "--split-beside-bottom",
    fallback: 0.6,
    axis: "y",
  },
};

/* The right rail has two widths, because it has two jobs. At `counts` it is a
   narrow column of numbers; at `full` it holds a 960-unit-wide state machine.
   Remembering one number for both meant dragging one silently resized the
   other, and loading the page pulled the expanded width down to the collapsed
   default. */
const RAILS = {
  left: { var: "--rail-left-size", key: "anki-forge.rail-left", fallback: 240 },
  right: { var: "--rail-right-size", key: "anki-forge.rail-right", fallback: 240 },
  rightFull: { var: "--rail-right-full", key: "anki-forge.rail-right-full", fallback: 620 },
};
/* Per side, because they hold different things. The filter rail is a list and
   stops being useful much past a few hundred pixels; the guide has a diagram
   that at 640px renders its 10.5px labels at about 7px -- legible only in the
   sense that the pixels are there. */
const RAIL_LIMITS = {
  left: { min: 150, max: () => Math.min(640, window.innerWidth * 0.6) },
  right: { min: 180, max: () => Math.min(1400, window.innerWidth * 0.9) },
  rightFull: { min: 320, max: () => Math.min(1400, window.innerWidth * 0.9) },
};

/* Which of the right rail's two widths a drag is currently adjusting. */
function railName(side) {
  if (side !== "right") return side;
  return document.body.classList.contains("guide-full") ? "rightFull" : "right";
}

function railBound(name, which) {
  const bound = RAIL_LIMITS[name][which];
  return typeof bound === "function" ? bound() : bound;
}

function remember(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    /* private window: the drag still applied for this session */
  }
}

function recall(key, fallback) {
  try {
    const saved = parseFloat(localStorage.getItem(key));
    return Number.isFinite(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

function applySplit(name, fraction) {
  const split = SPLITS[name];
  if (!split) return 0;
  const clamped = Math.min(0.85, Math.max(0.15, fraction));
  document.documentElement.style.setProperty(split.left, `${clamped}fr`);
  document.documentElement.style.setProperty(split.right, `${1 - clamped}fr`);
  return clamped;
}

function applyRail(name, px) {
  const rail = RAILS[name];
  const clamped = Math.min(railBound(name, "max"), Math.max(railBound(name, "min"), px));
  document.documentElement.style.setProperty(rail.var, `${clamped}px`);
  return clamped;
}

(function enableDragging() {
  Object.keys(SPLITS).forEach((name) =>
    applySplit(name, recall(SPLITS[name].key, SPLITS[name].fallback)),
  );
  Object.keys(RAILS).forEach((name) =>
    applyRail(name, recall(RAILS[name].key, RAILS[name].fallback)),
  );

  let drag = null;

  document.addEventListener("pointerdown", (event) => {
    const grip = event.target.closest("[data-rail]");
    const splitter = event.target.closest("[data-splitter]");
    if (!grip && !splitter) return;
    const handle = grip || splitter;
    drag = grip
      ? { kind: "rail", side: grip.dataset.rail, handle }
      : { kind: "split", name: splitter.dataset.splitter, box: splitter.parentElement, handle };
    handle.classList.add("dragging");
    handle.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  document.addEventListener("pointermove", (event) => {
    if (!drag) return;
    if (drag.kind === "rail") {
      applyRail(
        railName(drag.side),
        drag.side === "left" ? event.clientX : window.innerWidth - event.clientX,
      );
      return;
    }
    const box = drag.box.getBoundingClientRect();
    // A vertical split reads the same way down the other axis. One helper for
    // both, because two hand-rolled drag loops is how they end up behaving
    // differently -- and only the axis actually differs.
    if ((SPLITS[drag.name] || {}).axis === "y") {
      if (box.height) applySplit(drag.name, (event.clientY - box.top) / box.height);
      return;
    }
    if (box.width) applySplit(drag.name, (event.clientX - box.left) / box.width);
  });

  document.addEventListener("pointerup", () => {
    if (!drag) return;
    drag.handle.classList.remove("dragging");
    const read = (name) =>
      parseFloat(document.documentElement.style.getPropertyValue(name));
    if (drag.kind === "rail") {
      const rail = RAILS[railName(drag.side)];
      remember(rail.key, read(rail.var));
    } else {
      const split = SPLITS[drag.name];
      if (split) remember(split.key, read(split.left));
    }
    drag = null;
  });

  document.addEventListener("dblclick", (event) => {
    const grip = event.target.closest("[data-rail]");
    if (grip) {
      const rail = RAILS[railName(grip.dataset.rail)];
      applyRail(railName(grip.dataset.rail), rail.fallback);
      remember(rail.key, rail.fallback);
      return;
    }
    const splitter = event.target.closest("[data-splitter]");
    if (splitter) {
      const split = SPLITS[splitter.dataset.splitter];
      if (split) {
        applySplit(splitter.dataset.splitter, split.fallback);
        remember(split.key, split.fallback);
      }
    }
  });
})();

/* Keep the filter rail and the guide's diagram in step with what you just
   decided. Both render the same `pipeline` counts, so a decision that changed
   a state used to leave every number on screen stale until a page load -- and
   the rail is what you navigate by. Every mutating route returns the fresh
   counts; this paints them. */
function paintCounts(pipeline) {
  if (!pipeline) return;
  document.querySelectorAll("[data-count]").forEach((el) => {
    const value = pipeline[el.dataset.count];
    if (value !== undefined) el.textContent = value;
  });
}

/* The undo stack outlives a page load. Clicking a rail link is a navigation,
   which used to throw the stack away -- so a mis-pressed key became permanent
   the moment you changed filter, which is exactly when you would go looking
   for it. Session storage, so it dies with the tab and never with a click. */
const UNDO_KEY = "anki-forge.undo";

function loadUndo() {
  try {
    const raw = sessionStorage.getItem(UNDO_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveUndo(stack) {
  try {
    sessionStorage.setItem(UNDO_KEY, JSON.stringify(stack.slice(-50)));
  } catch {
    /* private window: undo still works within this page */
  }
}

/* The source gallery.

   A dropdown answers "which one am I on" and nothing else. With a shelf of
   papers the question is which one to work on next, and that is a comparison:
   how far along each is, where it came from, what it is about. So this is the
   window rather than a list, and it carries the counts.

   Loaded once per page, on first open, because it walks every ledger and
   every card. */
const gallery = {
  data: null,
  tag: "",
  origin: "",
  query: "",
};

const ORIGIN_LABEL = {
  zotero: "from Zotero",
  pdf: "a PDF here",
  tex: "LaTeX source",
};
const UNIT_LANE = ["new", "queued", "carded", "skipped"];
const CARD_LANE = ["draft", "approved", "rejected"];

function sourceHref(name) {
  /* Keep the view and the state you were on; drop the filters that belong to
     the source you are leaving. A section number from one book means nothing
     in another, and carrying it over lands you on an empty deck that looks
     like the import failed. */
  const url = new URL(location.href);
  ["section", "mark"].forEach((key) => url.searchParams.delete(key));
  url.searchParams.set("source", name);
  url.hash = "";
  return url.toString();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function countBar(counts, lane) {
  const total = lane.reduce((sum, state) => sum + (counts[state] || 0), 0);
  const bar = el("span", "gsource-bar");
  if (!total) return bar;
  lane.forEach((state) => {
    const n = counts[state] || 0;
    if (!n) return;
    const seg = el("i", `seg state-${state}`);
    seg.style.width = `${(100 * n) / total}%`;
    seg.title = `${n} ${state}`;
    bar.appendChild(seg);
  });
  return bar;
}

function countRow(counts, lane) {
  const row = el("span", "gsource-counts");
  lane.forEach((state) => {
    const n = counts[state] || 0;
    const cell = el("i", n ? `on state-${state}` : "");
    cell.appendChild(el("b", "", String(n)));
    cell.appendChild(document.createTextNode(` ${state}`));
    row.appendChild(cell);
  });
  return row;
}

function sourceCard(row, current) {
  const card = el("a", "gsource" + (row.name === current ? " current" : ""));
  card.href = sourceHref(row.name);
  const head = el("span", "gsource-head");
  head.appendChild(el("span", "gsource-name", row.name));
  if (row.origin) {
    head.appendChild(el("span", `gsource-origin o-${row.origin}`, ORIGIN_LABEL[row.origin] || row.origin));
  } else {
    head.appendChild(el("span", "gsource-origin warn", "no source.md"));
  }
  card.appendChild(head);
  card.appendChild(el("span", "gsource-title", row.title));
  if (row.tags.length) {
    const tags = el("span", "gsource-tags");
    row.tags.forEach((tag) => tags.appendChild(el("i", "", tag)));
    card.appendChild(tags);
  }
  card.appendChild(el("span", "gsource-lane", `units · ${row.units}`));
  card.appendChild(countBar(row.counts, UNIT_LANE));
  card.appendChild(countRow(row.counts, UNIT_LANE));
  card.appendChild(el("span", "gsource-lane", `cards · ${row.cards}`));
  card.appendChild(countBar(row.counts, CARD_LANE));
  card.appendChild(countRow(row.counts, CARD_LANE));
  return card;
}

function chip(label, active, onPick) {
  const button = el("button", "chip" + (active ? " on" : ""), label);
  button.type = "button";
  button.addEventListener("click", onPick);
  return button;
}

function paintGallery() {
  const data = gallery.data;
  if (!data) return;
  const current = new URL(location.href).searchParams.get("source") || "";
  const chips = document.getElementById("gallery-chips");
  chips.textContent = "";
  const pick = (key) => (value) => () => {
    gallery[key] = gallery[key] === value ? "" : value;
    paintGallery();
  };
  const byTag = pick("tag");
  const byOrigin = pick("origin");
  if (data.tags.length) {
    chips.appendChild(el("span", "chip-label", "tag"));
    data.tags.forEach((tag) => chips.appendChild(chip(tag, gallery.tag === tag, byTag(tag))));
  }
  if (data.origins.length > 1) {
    chips.appendChild(el("span", "chip-label", "from"));
    data.origins.forEach((origin) =>
      chips.appendChild(
        chip(ORIGIN_LABEL[origin] || origin, gallery.origin === origin, byOrigin(origin)),
      ),
    );
  }

  const needle = gallery.query.trim().toLowerCase();
  const shown = data.sources.filter((row) => {
    if (gallery.tag && !row.tags.includes(gallery.tag)) return false;
    if (gallery.origin && row.origin !== gallery.origin) return false;
    if (!needle) return true;
    return `${row.name} ${row.title} ${row.citation}`.toLowerCase().includes(needle);
  });

  const grid = document.getElementById("gallery-grid");
  grid.textContent = "";
  shown.forEach((row) => grid.appendChild(sourceCard(row, current)));
  document.getElementById("gallery-empty").hidden = shown.length > 0;

  const t = data.totals;
  document.getElementById("gallery-totals").textContent =
    `${shown.length} of ${data.sources.length} sources · ` +
    `${data.units} units (${t.new} new, ${t.queued} queued) · ` +
    `${data.cards} cards (${t.draft} draft, ${t.approved} approved)`;
}

async function openGallery() {
  const dialog = document.getElementById("gallery");
  if (!dialog) return;
  dialog.showModal();
  if (!gallery.data) {
    try {
      const response = await fetch("/api/sources");
      gallery.data = await response.json();
    } catch {
      document.getElementById("gallery-totals").textContent = "could not read the sources";
      return;
    }
  }
  paintGallery();
  document.getElementById("gallery-search").focus();
}

(function wireGallery() {
  const dialog = document.getElementById("gallery");
  if (!dialog) return;
  const open = document.getElementById("source-pick");
  if (open) open.addEventListener("click", openGallery);
  document.getElementById("gallery-close").addEventListener("click", () => dialog.close());
  const search = document.getElementById("gallery-search");
  search.addEventListener("input", () => {
    gallery.query = search.value;
    paintGallery();
  });
})();

/* Clicking away closes. A modal that only closes on its own × makes you hunt
   for the one pixel that dismisses it, which is the opposite of what a panel
   over your work should ask.

   The test is the click landing outside the dialog's *box*: a `<dialog>` fills
   the viewport as far as the event target is concerned -- the backdrop is part
   of it -- so `event.target === dialog` alone would also fire for a click on a
   padding edge inside it. */
document.addEventListener("click", (event) => {
  const dialog = event.target.closest("dialog");
  if (!dialog || !dialog.open) return;
  const box = dialog.getBoundingClientRect();
  const outside =
    event.clientX < box.left ||
    event.clientX > box.right ||
    event.clientY < box.top ||
    event.clientY > box.bottom;
  // A keyboard-driven activation reports (0, 0); it is not a click on the
  // backdrop and closing on it would dismiss the panel as it opened.
  if (outside && (event.clientX || event.clientY)) dialog.close();
});

/* The effective configuration, over whatever you were doing. It answers a
   question you have *mid-decision* -- which layout did this card resolve to --
   and a navigation away and back is a poor way to look something up. Read-only
   for the reason the panel says: the config is read at startup, and half these
   keys change what existing content means. */
async function openSettings() {
  const dialog = document.getElementById("settings");
  if (!dialog) return;
  dialog.showModal();
  const body = document.getElementById("settings-body");
  body.textContent = "reading…";
  const source = new URL(location.href).searchParams.get("source") || "";
  let data;
  try {
    const response = await fetch(`/api/config?source=${encodeURIComponent(source)}`);
    data = await response.json();
  } catch {
    body.textContent = "could not read the configuration";
    return;
  }
  body.textContent = "";
  data.groups.forEach((group) => {
    const section = el("section", "config-group" + (group.focused ? " focus" : ""));
    section.appendChild(el("h2", "", group.where));
    const table = el("table", "config-table");
    const tbody = document.createElement("tbody");
    group.rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.appendChild(el("th", "", row.key));
      const value = document.createElement("td");
      // An empty value is an answer -- a source that declares no layout gets
      // no layout -- but a blank cell reads as a rendering failure, so say it.
      const text = String(row.value);
      value.appendChild(text ? el("code", "", text) : el("span", "muted", "unset"));
      tr.appendChild(value);
      tr.appendChild(el("td", "origin" + (row.from === "inherited" ? " inherited" : ""), row.from));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    section.appendChild(table);
    body.appendChild(section);
  });
}

(function wireSettings() {
  const dialog = document.getElementById("settings");
  if (!dialog) return;
  document.getElementById("settings-close").addEventListener("click", () => dialog.close());
  document.addEventListener("click", (event) => {
    if (event.target.closest("#config-open, [data-settings]")) openSettings();
  });
})();

/* Any modal over the deck owns the keyboard: `s` typed into the gallery's
   search box would otherwise skip whatever unit was behind it. */
function galleryIsOpen() {
  return ["gallery", "settings"].some((id) => {
    const dialog = document.getElementById(id);
    return Boolean(dialog && dialog.open);
  });
}

/* The mini diagram counts either the whole source or what the filters leave.
   It has its own attribute because the rail shows the unfiltered numbers on
   the same page, and one repaint would otherwise overwrite the other. */
function paintFsm(counts) {
  if (!counts) return;
  document.querySelectorAll("[data-fsm-count]").forEach((el) => {
    const value = counts[el.dataset.fsmCount];
    if (value !== undefined) el.textContent = value;
  });
}

/* In `filtered` mode the new counts depend on the query, which a mutation
   response cannot know, so ask for them. In `all` mode the response already
   carries them. */
async function repaintCounts(pipeline) {
  paintCounts(pipeline);
  const params = new URLSearchParams(location.search);
  if (params.get("counts_scope") !== "filtered") {
    paintFsm(pipeline);
    return;
  }
  try {
    const response = await fetch(`/api/counts?${params.toString()}`);
    const payload = await response.json();
    paintCounts(payload.pipeline);
    paintFsm(payload.fsm);
  } catch {
    /* the numbers go stale until the next load; nothing else breaks */
  }
}

/* Copy a suggested command. Nothing is launched from here on purpose: you
   paste it where you can watch it, which is the whole difference between a
   command you ran and one that ran itself. */
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  const text = button.dataset.copy;
  try {
    await navigator.clipboard.writeText(text);
    button.classList.add("copied");
    setTimeout(() => button.classList.remove("copied"), 1200);
  } catch {
    /* Clipboard needs a secure context, and 127.0.0.1 counts -- but a
       hostname alias does not. Select it instead so ctrl+c still works. */
    const code = button.querySelector("code");
    if (!code) return;
    const range = document.createRange();
    range.selectNodeContents(code);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
});

/* Counts that follow work happening elsewhere.

   Everything worth showing is already on disk: a `/transcribe` pass writes the
   ledger and a `/extract-cards` pass writes card files, so the numbers can be
   derived rather than reported. No job runner, no progress protocol, and it
   works whether the pass was started from a terminal, a subagent or by hand.

   The deck on screen deliberately does not reshuffle underneath you -- being
   moved to a different card mid-decision is worse than a stale list -- so when
   the numbers move, the header offers a reload and leaves the choice alone. */
const COUNT_POLL_MS = 4000;

(function followTheFiles() {
  const rail = document.getElementById("filter-rail");
  if (!rail) return;
  let baseline = null;

  async function tick() {
    if (document.visibilityState !== "visible") return;
    const params = new URLSearchParams(location.search);
    let payload;
    try {
      const response = await fetch(`/api/counts?${params.toString()}`);
      payload = await response.json();
    } catch {
      return; /* the numbers go stale until the next load; nothing else breaks */
    }
    paintCounts(payload.pipeline);
    paintFsm(params.get("counts_scope") === "filtered" ? payload.fsm : payload.pipeline);
    if (payload.stale) showStale();

    const signature = JSON.stringify(payload.pipeline);
    if (baseline === null) baseline = signature;
    else if (signature !== baseline) showReload();
  }

  /* The Python on disk is newer than the process serving this page.

     Templates are re-read per request and Python is imported once, so editing
     both and not restarting leaves new markup running against old code. Every
     new template block guarded by `{% if thing is defined %}` renders nothing
     and every new endpoint 404s -- so a feature that exists and works reads,
     on screen, as a feature that was never built.

     Louder than the reload hint beside it, and it does not offer a button:
     reloading fixes nothing here, and a button that looked like it might
     would send you round the same loop. Only a restart moves this. */
  function showStale() {
    if (document.getElementById("stale-code")) return;
    const bar = document.createElement("div");
    bar.id = "stale-code";
    bar.className = "stale-code";
    bar.innerHTML =
      "<b>this server is older than the code</b> — templates reload per request, " +
      "Python does not, so new panels render empty and new buttons return 404. " +
      "Restart <code>forge serve</code>.";
    document.body.appendChild(bar);
  }

  function showReload() {
    if (document.getElementById("reload-hint")) return;
    const hint = document.createElement("button");
    hint.id = "reload-hint";
    hint.type = "button";
    hint.className = "reload-hint";
    hint.textContent = "files changed — reload";
    hint.title = "something wrote to the ledger or the cards while this page was open";
    hint.addEventListener("click", () => location.reload());
    document.querySelector("header")?.appendChild(hint);
  }

  setInterval(tick, COUNT_POLL_MS);
  document.addEventListener("visibilitychange", tick);
  tick();
})();
