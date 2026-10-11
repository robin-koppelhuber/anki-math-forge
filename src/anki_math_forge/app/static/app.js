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
      toast("KaTeX did not load. The maths is raw LaTeX, not wrong", "bad");
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

/* Chrome's `<input type="search">` eats the first Escape to clear itself, so
   a dialog whose search box has focus -- which is every one of them, they all
   focus it on open -- took two presses to close while its button said
   "close (esc)". The box still clears; the dialog closes with it. */
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const box = event.target;
  if (!(box instanceof HTMLInputElement) || box.type !== "search") return;
  const dialog = box.closest("dialog");
  if (!dialog) return;
  event.preventDefault();
  box.value = "";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  dialog.close();
});

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

/* `value` is a starting point to edit, not a prefix to type after.

   It used to be selected on open, so the first character replaced it. That was
   harmless for an editable default and silently wrong for `N`, which pre-filled
   `@me ` and carried the audience nowhere else: typing wiped it, the note
   arrived unaddressed, and `Ledger.annotate` files an unaddressed line as
   `@claude`. `N` was indistinguishable from `n` unless you pressed End first.
   Callers that want a prefix now add it to the answer instead. */
function ask(label, value = "") {
  const dialog = document.getElementById("prompt");
  const input = document.getElementById("prompt-input");
  document.getElementById("prompt-label").textContent = label;
  input.value = value;
  dialog.showModal();
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => resolve(dialog.returnValue === "ok" ? input.value.trim() : null),
      { once: true },
    );
  });
}

/* Which project this view is showing. Sent with every write, because every
   write hands back the counts for the rail and those have to be about what is
   on screen -- unscoped, grading one card on a fifteen-unit paper made the
   rail jump to the whole repo's 127 carded and 108 approved. Resolved on the
   server and stamped onto the deck, so it is the real name and not whatever
   the query string omitted. */
function viewScope() {
  const deck = document.getElementById("deck");
  return (deck && deck.dataset.project) || "";
}

/* The unit a write is aimed at, if it is one: the id sits in the URL of
   every unit write, so this is found here once rather than passed in at
   every call site. */
function unitOf(url) {
  const match = /^\/api\/units\/[^/]+\/(.+)\/[a-z-]+$/.exec(url);
  if (!match) return null;
  return document.querySelector(`.unit.item[data-id="${CSS.escape(match[1])}"]`);
}

async function post(url, body) {
  /* The unit's own version, so the server refuses this only if *that*
     unit changed. Comparing the whole ledger's mtime made any background
     run, an extract over the rest of the book, cost you a reload on your
     next keystroke here. */
  const unit = unitOf(url);
  const version = unit ? unit.dataset.version : "";
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope: viewScope(),
      ...(version ? { version } : {}),
      ...(body || {}),
    }),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (e) {
    payload = { error: response.statusText };
  }
  if (response.status === 409) {
    toast(payload.error || "file changed on disk, reloading", "bad");
    setTimeout(() => location.reload(), 1400);
    throw new Error("stale");
  }
  if (!response.ok) {
    toast(payload.detail || payload.error || `error ${response.status}`, "bad");
    throw new Error(payload.detail || payload.error || response.statusText);
  }
  if (unit && payload.version) unit.dataset.version = payload.version;
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
    // Anything that has to measure the item it is looking at. Hidden items
    // have no box, so this cannot be done once for the whole deck.
    if (item) document.dispatchEvent(new CustomEvent("deck:shown", { detail: item }));
  }

  next() {
    if (this.index >= this.items.length - 1) {
      toast("end of the list");
      return;
    }
    this.show(this.index + 1);
  }

  /* Forward means "the next thing still needing a decision". Walking over
     settled items in either direction is only ever re-treading work, which
     reads as the navigation being stuck. */
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
    /* Repaint before bailing. Settling the last item left `4 / 4` on screen
       while three were still unsettled, because the only thing that writes the
       counter is `show`. */
    this.show(this.index);
    toast("end of the list");
  }

  /* Back means "the previous thing still needing a decision", like forward.
     Settled items stay in the list so that the file and the view agree until
     the next reload, but walking back onto a card the filter no longer
     matches is the filter leaking: on the draft list, `k` landed on cards you
     had just approved. Reaching one on purpose is what undo is for, which
     finds its item by id. */
  prev() {
    for (let i = this.index - 1; i >= 0; i -= 1) {
      if (!this.items[i].dataset.settled) {
        this.show(i);
        return;
      }
    }
    toast("start of the list");
  }

  /* Mark the current item as no longer matching the active filter, and move
     on. It stays in the list: removing it meant that a mis-pressed key left
     you with no way back to the thing you had just acted on, because `k`
     could not reach a node that no longer existed. The file is the truth;
     this is the view keeping up until the next reload. */
  /* `item` is passed in, not read off `this.current`.

     Every caller captures the item, awaits a write, and settles afterwards --
     and `this.current` has moved on if a second key was pressed during the
     round trip. Measured: two quick presses of `q` queued unit one on disk and
     painted "queued, no longer matches this filter" over unit *two*, which was
     still `new`. `nextPending` then skipped it forever and it dropped out of
     triage until a reload. */
  settle(label, item = this.current) {
    if (!item) return;
    item.dataset.settled = label || "done";
    let banner = item.querySelector(".settled");
    if (!banner) {
      banner = document.createElement("p");
      banner.className = "settled";
      item.prepend(banner);
    }
    banner.textContent =
      `${label} — no longer matches this filter. ${undoKeyName()} undoes it.`;
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
  if (!item) toast("nothing to act on: the filter is empty");
  return item;
}

/* Which key runs which action, from `app/keys.py` by way of the page.
   Empty if the server predates it, in which case nothing binds and the footer
   is empty too -- which is the honest pair, rather than a legend listing keys
   that do nothing. */
/* What to call the undo key in a message. It is configurable through
   `[app.keys]`, and seven toasts across three views said "z undoes" whatever
   it was actually bound to -- which is worse than saying nothing, because it
   names a key that does nothing. */
function undoKeyName() {
  return keymap().undo || "undo";
}

function keymap() {
  const tag = document.getElementById("keymap");
  try {
    return tag ? JSON.parse(tag.textContent) : {};
  } catch {
    return {};
  }
}

/* `handlers` is keyed by **action**, not by key.

   The letter is a setting and the action is the contract, so a view's script
   says what `approve` does and never mentions `a`. That is also what lets the
   legend and the bindings come from one declaration: they are two renderings
   of the same map rather than two lists someone has to keep equal. */
function bindKeys(handlers) {
  const map = keymap();
  const bound = {};
  Object.keys(handlers).forEach((action) => {
    const key = map[action];
    if (key) bound[key] = handlers[action];
  });
  document.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (document.getElementById("prompt").open) return;
    // A modal over the deck owns the keyboard: `s` in a search box would
    // otherwise skip whatever unit was behind it.
    if (aModalIsOpen()) return;
    const tag = document.activeElement && document.activeElement.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
    const handler = bound[event.key];
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

/* The commands panel, open or shut, remembered. Every view here is rendered
   by the server, so a panel folded on one click came back open on the next --
   which is the same tax as the rail itself, and it is pinned to the bottom of
   the rail taking a third of it. */
const COMMANDS_KEY = "anki-forge.commands";

(function rememberCommands() {
  const panel = document.getElementById("rail-actions");
  if (!panel) return;
  try {
    if (localStorage.getItem(COMMANDS_KEY) === "closed") panel.open = false;
  } catch {
    /* private window, or storage disabled: it opens, which is the default */
  }
  panel.addEventListener("toggle", () => {
    try {
      localStorage.setItem(COMMANDS_KEY, panel.open ? "open" : "closed");
    } catch {
      /* the fold still works for this page */
    }
  });
})();

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

/* The theme: what the system says, or pinned to one. The pinned value is
   applied by an inline script in `base.html` before anything paints; this
   only changes it. `theme.css` does the rest off `data-theme`, and the
   canvas, which draws with colours read once, listens for `forge:theme`. */
const THEME_KEY = "anki-forge.theme";
const THEMES = ["system", "light", "dark"];

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
  document.querySelectorAll("[data-theme-cycle]").forEach((button) => {
    button.dataset.themeNow = theme;
    button.title = "theme: " + (theme === "system" ? "follows the system" : theme);
  });
}

(function wireTheme() {
  let theme = document.documentElement.dataset.theme || "system";
  applyTheme(theme);
  document.querySelectorAll("[data-theme-cycle]").forEach((button) => {
    button.addEventListener("click", () => {
      theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
      forget(THEME_KEY, theme === "system" ? null : theme);
      applyTheme(theme);
      window.dispatchEvent(new CustomEvent("forge:theme", { detail: theme }));
      toast(button.title);
    });
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
    fallback: 320,
    axis: "y",
  },
  /* And the triage column's, between what the reader wrote on the page and
     what has been written about the unit since. Different questions, asked at
     different moments; stacked in one scroll the second was always below the
     fold. */
  /* The triage column's two panes. The notes are on top now -- the mark this
     unit came from is already on the crop beside it, outlined in red, so the
     best position was being spent on the one thing you cannot miss -- and the
     default leans to the marks below, which are the longer read. */
  beside: {
    key: "anki-forge.split.beside",
    left: "--split-beside",
    right: "--split-beside-bottom",
    fallback: 220,
    axis: "y",
  },
  /* The filter rail's, between the list and the commands pinned under it.
     `from: "bottom"` because the sized pane is the lower one here: the list
     takes the slack, so what a drag decides is how much room the panel gets,
     measured up from the bottom of the rail. The guide is the other way
     round, and the rails themselves already read left-to-right or
     right-to-left for the same reason. */
  commands: {
    key: "anki-forge.split.commands",
    left: "--split-commands",
    right: "--split-commands-top",
    fallback: 220,
    axis: "y",
    from: "bottom",
  },
  /* The setup stage's three columns. Widths rather than shares, because the
     three do not divide one box between them: the commands column and the
     list are each as wide as they need to be and the panel takes the slack,
     so a drag decides one edge and leaves the other where it was. Both
     measure from the left edge of the pane in front of the handle, which is
     the only thing the markup promises. */
  setupPanel: {
    key: "anki-forge.split.setup-panel",
    left: "--split-setup-panel",
    fallback: 288,
    axis: "x-px",
    min: 170,
    max: 640,
  },
  /* The shelf's rail: the filters, the form and the commands, beside the
     grid of projects. The top bar's first column follows it, so the two stay
     one frame. */
  shelfRail: {
    key: "anki-forge.split.shelf-rail",
    left: "--split-shelf-rail",
    fallback: 272,
    axis: "x-px",
    min: 180,
    max: 560,
  },
  /* The commands window: the history list's width, and how much of the
     right-hand side the builder takes above the run you picked. */
  runsSide: {
    key: "anki-forge.split.runs-side",
    left: "--split-runs-side",
    fallback: 300,
    axis: "x-px",
    min: 200,
    max: 640,
  },
  runsBuilder: {
    key: "anki-forge.split.runs-builder",
    left: "--split-runs-builder",
    right: "--split-runs-builder-bottom",
    fallback: 260,
    axis: "y",
  },
  /* The setup panel's two lists: what you asked for on top, what the project
     reads underneath. Which of the two is long depends entirely on the
     project (a book has one source and no asks, a deck with no book is all
     asks), so this is the one split with no sensible default share. */
  setup: {
    key: "anki-forge.split.setup",
    left: "--split-setup",
    right: "--split-setup-bottom",
    fallback: 260,
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

/* `null` means "forget it", which is not the same as storing a zero: the
   stylesheet's own default has to come back. */
function forget(key, value) {
  if (value === null) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* a private window resets for this page load and no longer */
    }
    return;
  }
  remember(key, value);
}

function remember(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    /* private window: the drag still applied for this session */
  }
}

/* `fallback` is returned for "nothing stored", and callers may pass `null` to
   tell the two apart -- a vertical split with no stored value must stay unset
   rather than take a number. */
function recall(key, fallback) {
  try {
    const saved = parseFloat(localStorage.getItem(key));
    return Number.isFinite(saved) ? saved : fallback;
  } catch {
    return fallback;
  }
}

/* A vertical split is a **height**, not a share.

   A share needs a box with a definite height to be a share *of*, and a box
   with a definite height is what left a band of nothing under a short column:
   the marks ran out and the pane kept the room anyway. As a length the
   stylesheet can wrap it in `fit-content` -- capped where you dragged it to,
   shrinking to its content when there is less -- and the column itself can be
   a `max-height`, so it ends where its content ends.

   Columns stay fractional: two of those plus a fixed gutter add up exactly,
   and lengths would need the gutter subtracted from one of them. */
function applyVerticalSplit(name, px) {
  const split = SPLITS[name];
  if (px === null) {
    // Back to the stylesheet's `max-content`: the pane is the height of what
    // is in it, which is the right answer until you have an opinion.
    document.documentElement.style.removeProperty(split.left);
    split.fraction = null;
    return 0;
  }
  const clamped = Math.min(2000, Math.max(40, px));
  document.documentElement.style.setProperty(split.left, `${clamped}px`);
  split.fraction = clamped;
  return clamped;
}

function applySplit(name, fraction) {
  const split = SPLITS[name];
  if (!split) return 0;
  if (split.axis === "y") return applyVerticalSplit(name, fraction);
  /* A width, for a row of three panes. One variable, clamped per split:
     a commands column below 150px is a column of ellipses, and one past
     560px is reading room spent on something you glance at. */
  if (split.axis === "x-px") {
    const wide = Math.min(split.max, Math.max(split.min, fraction));
    document.documentElement.style.setProperty(split.left, `${wide}px`);
    split.fraction = wide;
    return wide;
  }
  const clamped = Math.min(0.85, Math.max(0.15, fraction));
  document.documentElement.style.setProperty(split.left, `${clamped}fr`);
  document.documentElement.style.setProperty(split.right, `${1 - clamped}fr`);
  split.fraction = clamped;
  return clamped;
}

function applyRail(name, px) {
  const rail = RAILS[name];
  const clamped = Math.min(railBound(name, "max"), Math.max(railBound(name, "min"), px));
  document.documentElement.style.setProperty(rail.var, `${clamped}px`);
  return clamped;
}

(function enableDragging() {
  Object.keys(SPLITS).forEach((name) => {
    const split = SPLITS[name];
    /* A vertical split stays *unset* until you have actually moved it, so the
       stylesheet's `max-content` decides and the pane is the height of its
       own content. Writing a guessed default would park the divider wherever
       the guess landed -- which on a unit with no notes is a band of nothing
       above the marks, and on one with a long brief is a scrollbar you did not
       ask for. Columns have no such state: two of them always divide the full
       width, so a fraction is always meaningful. */
    const stored = recall(split.key, null);
    if (split.axis === "y" && stored === null) return;
    applySplit(name, stored === null ? split.fallback : stored);
  });
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
    const split = SPLITS[drag.name] || {};
    if (split.axis === "x-px") {
      // The pane this handle resizes is the one in front of it, and its own
      // left edge is where the width is measured from. That holds for both
      // handles in a row of three without either knowing about the other.
      const pane = drag.handle.previousElementSibling;
      if (pane) applySplit(drag.name, event.clientX - pane.getBoundingClientRect().left);
      return;
    }
    if (split.axis === "y") {
      // The pointer's offset into the box *is* the height of the sized pane,
      // measured from whichever end that pane is anchored to.
      applySplit(
        drag.name,
        split.from === "bottom" ? box.bottom - event.clientY : event.clientY - box.top,
      );
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
      if (split) remember(split.key, split.fraction);
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
      if (!split) return;
      // A vertical split resets to *no opinion* -- the pane goes back to the
      // height of its own content -- rather than to some remembered number,
      // because "however tall this is" is the state it starts in.
      const back = split.axis === "y" ? null : split.fallback;
      applySplit(splitter.dataset.splitter, back);
      forget(split.key, back);
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
/* One stack per view, not one for the app.

   It was a single key, so the two views shared a stack while pushing entries
   of different shapes: a unit step is `{id, before}` and a card step is
   `{uid, before}`. Triage three units, switch to the review view, press undo,
   and it popped a *unit* step, read `step.uid` off it as undefined, and posted
   to `/api/cards/undefined/restore`. Measured: a 400 either way, `unknown
   status ''` in one direction and `no unit 'None'` in the other -- and the
   step was popped and saved before the request went out, so each press
   destroyed one entry of the other view's history.

   Scoped by view, they cannot meet. The graph view keeps its own in memory:
   its undo is an inverse operation rather than a snapshot, so there is nothing
   to restore and nothing worth surviving a reload. */
const UNDO_KEY = "anki-forge.undo";

function undoKey(scope) {
  return `${UNDO_KEY}.${scope}`;
}

function loadUndo(scope) {
  try {
    const raw = sessionStorage.getItem(undoKey(scope));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveUndo(scope, stack) {
  try {
    sessionStorage.setItem(undoKey(scope), JSON.stringify(stack.slice(-50)));
  } catch {
    /* private window: undo still works within this page */
  }
}

/* One element, with a class and some text. Three views build lists of small
   nodes and `document.createElement` plus two assignments each is four lines
   where one says the same thing.

   `textContent`, never `innerHTML`: everything here is filled with a name or
   a citation out of a file, and one of those containing a `<` should show a
   `<` rather than open a tag. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* Starting a project, from the shelf. The list is filled from the config,
   which the app re-reads per request, so the new one is there the moment
   this returns, and the setup stage is where you go next: a project with no
   document is all pre-unit work. */
(function wireNewProject() {
  const form = document.getElementById("start-project");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("project-name").value.trim();
    if (!name) return;
    const answer = await post("/api/projects", {
      name,
      deck: document.getElementById("project-deck").value,
    });
    if (answer && answer.project) location.href = `/setup?project=${answer.project}`;
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

/* The multi-select filters: tags and gradings in the rail, tags on the
   shelf. Nothing is spelled out until you ask for it, because on a deck with
   forty tags the written-out list was most of the rail's height and the
   sections below it were off the bottom of the screen. The box opens the
   list, typing narrows it, and what is on shows as a chip underneath.

   Every option is a link the server built with the selection already toggled
   into it, so this only ever shows and hides. With it doing nothing the
   control is still a working list of filters, one click deeper. */
(function wirePickControls() {
  /* Every one on the page, by its own id. The rail has one and the shelf
     has another, and they are the same control over different
     vocabularies. */
  for (const box of document.querySelectorAll(".pick")) wireOnePick(box);
})();

function wireOnePick(box) {
  const id = box.id;
  const search = document.getElementById(`${id}-search`);
  const list = document.getElementById(`${id}-list`);
  if (!search || !list) return;
  const empty = document.getElementById(`${id}-none`);
  const rows = [...list.querySelectorAll("li[data-pick]")];
  const heads = [...list.querySelectorAll("li.pick-head")];
  /* Selecting reloads the page, which is how every other filter here works.
     Left to itself that shuts the list after each pick, and picking two is
     the case this control exists for, so a pick, and only a pick, asks the
     next page to open the list again. Read once and cleared, so it survives
     exactly one navigation: a flag that outlived the sequence left the list
     standing open over the sections for the rest of the session. Not the
     focus either, because with the caret in the box every single-key
     shortcut on the page types a letter instead. */
  const KEY = `pick-open.${id}`;
  let active = -1;

  const visible = () => rows.filter((row) => !row.hidden);

  function mark(index) {
    const shown = visible();
    for (const row of rows) row.classList.remove("here");
    active = shown.length ? Math.max(0, Math.min(index, shown.length - 1)) : -1;
    if (active < 0) return;
    shown[active].classList.add("here");
    shown[active].scrollIntoView({ block: "nearest" });
  }

  const hint = document.getElementById(`${id}-hint`);
  const counted = document.getElementById(`${id}-count`);

  function open(yes) {
    list.hidden = !yes;
    if (hint) hint.hidden = !yes;
    if (!yes) mark(-1);
  }

  function rememberOpen(yes) {
    try {
      if (yes) sessionStorage.setItem(KEY, "1");
      else sessionStorage.removeItem(KEY);
    } catch (err) {
      /* Private windows refuse storage. The control works, it just forgets. */
    }
  }

  function narrow() {
    const wanted = search.value.trim().toLowerCase();
    let shown = 0;
    for (const row of rows) {
      const hit = !wanted || (row.dataset.find || "").toLowerCase().includes(wanted);
      row.hidden = !hit;
      if (hit) shown += 1;
    }
    /* A heading over nothing reads as a group that is empty rather than as
       one filtered out. Each one owns the rows between it and the next, in
       document order, which is the only thing the markup promises. */
    for (const head of heads) {
      let any = false;
      for (let next = head.nextElementSibling; next; next = next.nextElementSibling) {
        if (next.classList.contains("pick-head")) break;
        if (next.dataset.pick && !next.hidden) any = true;
      }
      head.hidden = !any;
    }
    if (empty) empty.hidden = shown > 0;
    if (counted) counted.textContent = String(shown);
    /* What Enter would take. Typing three letters and pressing Enter is the
       whole point of a box over a list, and without a marked row it is a
       guess about which one you meant. */
    mark(0);
  }

  search.addEventListener("focus", () => open(true));
  search.addEventListener("click", () => open(true));
  search.addEventListener("input", () => {
    open(true);
    narrow();
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      search.value = "";
      narrow();
      open(false);
      search.blur();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      open(true);
      mark(active + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      mark(active - 1);
    } else if (event.key === "Enter") {
      const row = visible()[active];
      const link = row && row.querySelector("a");
      if (link) {
        event.preventDefault();
        link.click();
      }
    }
  });
  /* Clicking away closes it, the way the dialogs here do. The rail is narrow
     and the list is long, so leaving it open over the sections is the state
     you most want out of. */
  document.addEventListener("click", (event) => {
    if (event.target.closest(`#${id}-list a`)) rememberOpen(true);
    else if (!list.hidden && !event.target.closest(`#${id}`)) open(false);
  });
  let picked = false;
  try {
    picked = sessionStorage.getItem(KEY) === "1";
  } catch (err) {
    /* see above */
  }
  rememberOpen(false);
  if (picked) open(true);
}

/* The state machine, full width. It is static markup already on the page, so
   unlike the settings table there is nothing to fetch: the diagram is drawn at
   about 50rem and the guide rail stops at 38, which is the whole reason it is
   not simply in the rail. */
function openMachine() {
  const dialog = document.getElementById("machine");
  if (dialog) dialog.showModal();
}

/* The crop, full size. The image is already in the page and in the cache, so
   this sets a `src` it has and lets the browser do nothing. */
function openCrop(button) {
  const dialog = document.getElementById("crop-view");
  const image = document.getElementById("crop-view-image");
  const unit = document.getElementById("crop-unit");
  if (!dialog || !image) return;
  image.setAttribute("src", button.dataset.crop || "");
  image.setAttribute("alt", `source crop for ${button.dataset.unit || "this card"}`);
  if (unit) unit.textContent = button.dataset.unit || "";
  dialog.showModal();
}

(function wirePanels() {
  /* Guarded one at a time. Both dialogs come from the same block in
     `base.html`, but a missing element used to take the *other* one's wiring
     down with it, which is the kind of coupling that only shows up on the one
     page that lacks it. */
  const closes = {
    machine: "machine-close",
    "crop-view": "crop-close",
  };
  Object.entries(closes).forEach(([id, button]) => {
    const dialog = document.getElementById(id);
    const close = document.getElementById(button);
    if (dialog && close) close.addEventListener("click", () => dialog.close());
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-machine]")) openMachine();
    /* A value, not just the attribute. The units view marks its crop with a
       bare `data-crop` so a missing PDF can be caught by the error handler
       above, and matching that opened the dialog on an empty `src`. */
    const crop = event.target.closest("[data-crop]");
    if (crop && crop.dataset.crop) openCrop(crop);
  });
})();

/* Any open dialog owns the keyboard, not a named list of two of them.

   The list was `gallery` and `settings`, which is the rule stated as its
   instances: every dialog added since would have had to remember to join it,
   and the symptom is silent -- `s` typed into a search box also skips whatever
   was behind it. */
function aModalIsOpen() {
  return Array.from(document.querySelectorAll("dialog")).some((d) => d.open);
}

/* The mini diagram counts either the whole project or what the filters leave.
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

/* A control inside a heading acts; it does not also fold the heading.

   `<summary>` toggles its `<details>` on any click inside it, so the `add`
   button on a notes section opened the prompt *and* collapsed the section it
   was adding to, and the chapter tally -- which is a filter link -- would have
   navigated away while folding on the way out. Anything genuinely interactive
   in there keeps its own behaviour and suppresses the toggle; a click on the
   heading text still folds, which is what makes the heading a heading. */
document.addEventListener("click", (event) => {
  if (!event.target.closest("summary")) return;
  const link = event.target.closest("a[href]");
  if (link) {
    // Folding and following are both the *default action* of this one click,
    // so `preventDefault` cancels both. Suppress it and navigate by hand --
    // except on a modified click, where the browser is opening a tab and the
    // fold behind it does not matter.
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    window.location.href = link.href;
    return;
  }
  if (event.target.closest("button")) event.preventDefault();
});

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

/* Running one of the offered commands, here, in the background.

   Every command with no model behind it. What it does comes from the
   parser (`data-effect`), and one that writes is asked about first. The
   server asks the same question again: this dialog is a courtesy to
   whoever is looking, and a tab left open since before a rename is not.
   See ROADMAP.md §12 and src/anki_math_forge/app/jobs.py.

   The page keeps working while it runs, which is the whole point of the
   button. `forge anki push` is ten seconds against a deck of 150, and a
   control that froze the screen for that is one you press once. */
const RUN_WARNINGS = {
  repo: "changes files in this repo.",
  anki: "changes your Anki collection, which nothing here can undo.",
};

/* Start a command line, after asking where it writes. Answers the run as
   the server first reports it, or null if you said no. */
async function startRun(line, effect) {
  const warning = RUN_WARNINGS[effect];
  if (warning && !window.confirm(`${line}\n\n${warning} Run it?`)) return null;
  const run = await post("/api/run", { run: line, confirmed: Boolean(warning) });
  notifyRun(run);
  watchRunsNow();
  return run;
}

/* A run button. It says it is busy while its command runs and nothing
   else: the result goes to a notification and the runs window, never under
   the row, which is a list of commands and not a place to read output. */
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-run]");
  if (!button || button.dataset.busy) return;
  button.dataset.busy = "1";
  button.classList.add("running");
  try {
    const run = await startRun(button.dataset.run, button.dataset.effect);
    if (run) await untilDone(run.id);
  } catch (e) {
    /* `post` has already said why, in a toast. */
  } finally {
    button.classList.remove("running");
    delete button.dataset.busy;
  }
});

async function untilDone(id) {
  /* Its own poll rather than the four second counts tick: a run is
     usually over in well under a second, and waiting four to be told so
     reads as the button not having worked. */
  for (;;) {
    const response = await fetch(`/api/run/${id}`);
    if (!response.ok) throw new Error(`run ${id}: ${response.status}`);
    const run = await response.json();
    if (run.done) return run;
    await new Promise((wake) => setTimeout(wake, 300));
  }
}

/* -- the notification, bottom right ---------------------------------------
   One per run started from this page: "running", then the summary the
   server wrote for it. A run that went well leaves on its own; one that
   did not stays until you close it, because it is the one you need to
   read. Either opens the runs window at that run. */
const NOTE_LINGER_MS = 8000;

function notifyRun(run) {
  const stack = document.querySelector("[data-run-notices]");
  if (!stack) return;
  const note = el("div", "run-notice");
  note.dataset.runNote = run.id;
  note.dataset.state = "running";
  const what = el("code", "run-notice-what", run.run);
  const said = el("span", "run-notice-said", "running…");
  const open = el("button", "run-notice-open", "open");
  open.type = "button";
  open.addEventListener("click", () => openRuns(run.id));
  const close = el("button", "run-notice-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "dismiss");
  close.addEventListener("click", () => note.remove());
  note.append(what, said, open, close);
  stack.prepend(note);
  untilDone(run.id)
    .then((done) => {
      note.dataset.state = done.ok ? "ok" : "failed";
      note.dataset.tone = done.tone || (done.ok ? "ok" : "bad");
      said.textContent = done.summary || (done.ok ? "done" : "failed");
      if (done.ok && done.tone !== "bad") {
        setTimeout(() => {
          if (!note.matches(":hover")) note.remove();
          else note.addEventListener("mouseleave", () => note.remove(), { once: true });
        }, NOTE_LINGER_MS);
      }
    })
    .catch((e) => {
      note.dataset.state = "failed";
      said.textContent = String(e.message || e);
    });
}

/* -- the runs window ------------------------------------------------------
   A list on the left, newest first, with four filters, a text filter and a
   way to forget what has finished; the run you picked in the middle. The
   list is the light form of every run (`/api/runs`), and a run's output is
   fetched when you pick it, because one `units --state all` is the whole
   ledger. */
const runsState = { show: "all", search: "", picked: "", rows: [], shown: "" };
let watchRunsNow = () => {};

/* Open the window, on a run when `id` names one. However it opens, from the
   top bar, a notification or a quick pick, the builder above the history
   shows an action: it used to be filled only by the top bar's button, so a
   window opened from a notification had an empty list to pick from.
   `startOn` is the action a quick pick is about to show, which then fills
   it instead. */
function openRuns(id, startOn = "") {
  const dialog = document.querySelector("[data-runs-dialog]");
  if (!dialog) return;
  if (id) runsState.picked = id;
  if (!dialog.open) dialog.showModal();
  if (!builder.current && !startOn) {
    // Opened on a run: start on that run's own command, fields and all.
    const row = runsState.rows.find((r) => r.id === id);
    showAction(row && row.action ? row.action : "", row && row.action ? row.values : {});
  }
  watchRunsNow();
}

function runVisible(row) {
  if (runsState.show === "running" && row.done) return false;
  if (runsState.show === "failed" && (!row.done || (row.ok && row.tone !== "bad"))) return false;
  if (runsState.show === "writes" && row.effect === "reads") return false;
  const needle = runsState.search.trim().toLowerCase();
  return !needle || row.run.toLowerCase().includes(needle);
}

function runState(row) {
  if (!row.done) return "running";
  return row.ok ? "ok" : "failed";
}

function sideRow(row) {
  const item = el("li");
  item.dataset.runRow = row.id;
  item.dataset.state = runState(row);
  item.dataset.effect = row.effect;
  if (row.tone) item.dataset.tone = row.tone;
  if (row.id === runsState.picked) item.setAttribute("aria-current", "true");
  const pick = el("button", "runs-pick");
  pick.type = "button";
  const when = new Date(row.at * 1000);
  pick.append(
    el("span", "runs-when", when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })),
    el("code", "runs-what", row.run.replace(/^forge /, "")),
    el("span", "runs-said", row.done ? row.summary || (row.ok ? "done" : "failed") : "running…"),
  );
  pick.addEventListener("click", () => {
    runsState.picked = row.id;
    paintRunsList();
    showRun(row.id);
  });
  item.appendChild(pick);
  return item;
}

function paintRunsList() {
  const list = document.querySelector("[data-runs-list]");
  if (!list) return;
  const rows = runsState.rows.filter(runVisible);
  list.replaceChildren(...rows.map(sideRow));
  if (!rows.length) list.appendChild(el("li", "runs-none", "no runs match"));
}

async function showRun(id) {
  const box = document.querySelector("[data-runs-detail]");
  if (!box) return;
  if (!id) {
    box.replaceChildren(el("p", "runs-empty", "nothing run from the page yet"));
    runsState.shown = "";
    return;
  }
  let run;
  try {
    const response = await fetch(`/api/run/${id}`);
    if (!response.ok) throw new Error("this run is no longer remembered");
    run = await response.json();
  } catch (e) {
    box.replaceChildren(el("p", "runs-empty", String(e.message || e)));
    return;
  }
  if (runsState.picked !== id) return; // another pick landed first
  runsState.shown = `${id}:${run.done}`;
  box.replaceChildren(renderRunDetail(run));
}

function renderRunDetail(run) {
  const box = el("div", "run-detail");
  box.dataset.runDetail = run.id;
  box.dataset.state = runState(run);
  if (run.tone) box.dataset.tone = run.tone;

  const head = el("header", "run-detail-head");
  head.appendChild(el("code", "run-detail-what", run.run));
  const facts = [
    run.done ? (run.ok ? "finished" : "failed") : "running",
    new Date(run.at * 1000).toLocaleString(),
    run.done ? `${run.seconds}s` : "",
    run.effect === "reads" ? "reads" : run.effect === "anki" ? "writes to Anki" : "writes files",
  ];
  head.appendChild(el("p", "run-detail-facts", facts.filter(Boolean).join(" · ")));
  const again = el("button", "run-again", "run again");
  again.type = "button";
  again.dataset.runAgain = run.run;
  again.addEventListener("click", async () => {
    const started = await startRun(run.run, run.effect);
    if (started) {
      runsState.picked = started.id;
      watchRunsNow();
    }
  });
  const copy = el("button", "run-copy", "copy");
  copy.type = "button";
  copy.addEventListener("click", () => {
    navigator.clipboard.writeText(`uv run ${run.run}`).then(() => toast("copied"));
  });
  const actions = el("div", "run-detail-actions");
  actions.append(again, copy);
  head.appendChild(actions);
  box.appendChild(head);

  if (!run.done) {
    box.appendChild(el("p", "run-summary", "running…"));
    return box;
  }
  box.appendChild(el("p", "run-summary", run.summary || (run.ok ? "done" : "failed")));
  if (run.said) {
    const said = el("pre", "run-said");
    said.textContent = run.said;
    box.appendChild(said);
  }
  for (const block of run.blocks || []) {
    const drawn = renderBlock(block);
    if (drawn) box.appendChild(drawn);
  }
  if (run.data !== null && run.data !== undefined) {
    const raw = el("details", "run-raw");
    raw.appendChild(el("summary", "", "raw output"));
    const pre = el("pre");
    pre.textContent = JSON.stringify(run.data, null, 2);
    raw.appendChild(pre);
    box.appendChild(raw);
  }
  return box;
}

/* The four block kinds `run_views.py` writes. The page knows nothing about
   commands: what to show for `anki push` is decided in Python, once. */
function renderBlock(block) {
  const box = el("section", "run-block");
  box.dataset.block = block.kind;
  if (block.tone) box.dataset.tone = block.tone;
  if (block.title) box.appendChild(el("h3", "run-block-title", block.title));
  if (block.kind === "stats") {
    const row = el("div", "run-stats");
    for (const item of block.items || []) {
      const stat = el("div", "run-stat");
      if (item.tone) stat.dataset.tone = item.tone;
      stat.append(el("b", "", String(item.value)), el("span", "", item.label));
      row.appendChild(stat);
    }
    box.appendChild(row);
  } else if (block.kind === "table") {
    const grid = el("table", "run-table");
    const head = grid.createTHead().insertRow();
    for (const [, label] of block.columns) head.appendChild(el("th", "", label));
    const body = grid.createTBody();
    for (const row of block.rows || []) {
      const line = body.insertRow();
      for (const [key] of block.columns) line.insertCell().textContent = cell(row[key]);
    }
    box.appendChild(grid);
    if (block.more) box.appendChild(el("p", "run-more", `and ${block.more} more in the raw output`));
  } else if (block.kind === "lines") {
    box.appendChild(lines(block.items || []));
  } else {
    const drawn = table(block.data);
    if (drawn) box.appendChild(drawn);
  }
  return box;
}

(function watchRuns() {
  const open = document.querySelector("[data-runs-open]");
  const dialog = document.querySelector("[data-runs-dialog]");
  if (!open || !dialog) return;
  let signature = "";
  let timer = 0;

  async function refresh() {
    let answer;
    try {
      answer = await (await fetch("/api/runs")).json();
    } catch {
      return 5000;
    }
    runsState.rows = answer.runs;
    open.dataset.running = String(answer.running);
    open.querySelector("[data-runs-count]").textContent = answer.running
      ? `${answer.running} running`
      : "runs";
    if (dialog.open) {
      if (!runsState.picked && answer.runs.length) runsState.picked = answer.runs[0].id;
      const now = JSON.stringify(answer.runs.map((r) => [r.id, r.done, r.summary]));
      if (now !== signature) {
        signature = now;
        paintRunsList();
      }
      const picked = answer.runs.find((r) => r.id === runsState.picked);
      if (picked && runsState.shown !== `${picked.id}:${picked.done}`) showRun(picked.id);
      if (!picked && runsState.shown) showRun("");
    }
    return answer.running ? 800 : 5000;
  }

  async function loop() {
    clearTimeout(timer);
    const wait = document.visibilityState === "visible" ? await refresh() : 5000;
    timer = setTimeout(loop, wait);
  }
  watchRunsNow = () => {
    signature = "";
    loop();
  };

  open.addEventListener("click", () => openRuns(""));
  dialog.querySelector("[data-runs-close]").addEventListener("click", () => dialog.close());
  dialog.querySelectorAll("[data-runs-show]").forEach((button) =>
    button.addEventListener("click", () => {
      runsState.show = button.dataset.runsShow;
      dialog
        .querySelectorAll("[data-runs-show]")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      paintRunsList();
    }),
  );
  dialog.querySelector("[data-runs-search]").addEventListener("input", (event) => {
    runsState.search = event.target.value;
    paintRunsList();
  });
  dialog.querySelector("[data-runs-clear]").addEventListener("click", async () => {
    const response = await fetch("/api/runs", { method: "DELETE" });
    const answer = await response.json();
    toast(`forgot ${answer.forgotten} finished run${answer.forgotten === 1 ? "" : "s"}`);
    if (!runsState.rows.some((r) => r.id === runsState.picked && !r.done)) runsState.picked = "";
    watchRunsNow();
  });
  loop();
})();

/* -- the command builder ------------------------------------------------
   Pick an action, fill in its fields, read the command it comes to, run it
   or copy it. The fields are the server's (`/api/actions`), and so is the
   command line: the page never assembles one, so what you read is what
   runs. A quick pick on a rail opens here with its fields filled in. */
const GROUPS = { sources: "sources and units", anki: "Anki", checks: "checks", looking: "looking" };
const builder = { actions: [], projects: [], current: null, loaded: null, timer: 0 };

function pageProject() {
  return new URL(location.href).searchParams.get("project") || "";
}

async function loadActions() {
  if (builder.loaded) return builder.loaded;
  builder.loaded = fetch(`/api/actions?project=${encodeURIComponent(pageProject())}`)
    .then((r) => r.json())
    .then((answer) => {
      builder.actions = answer.actions;
      builder.projects = answer.projects;
      builder.project = answer.project;
      const pick = document.querySelector("[data-builder-pick]");
      if (!pick) return answer;
      pick.replaceChildren();
      for (const [group, label] of Object.entries(GROUPS)) {
        const set = el("optgroup");
        set.label = label;
        for (const action of answer.actions.filter((a) => a.group === group)) {
          const option = el(
            "option",
            "",
            action.variant ? `${action.label} · ${action.variant}` : action.label,
          );
          option.value = action.key;
          set.appendChild(option);
        }
        if (set.children.length) pick.appendChild(set);
      }
      return answer;
    });
  return builder.loaded;
}

/* Show an action's fields, filled from `values`, else from the page: a
   project field starts on the project you are looking at. */
async function showAction(key, values = {}) {
  await loadActions();
  const action = builder.actions.find((a) => a.key === key) || builder.actions[0];
  if (!action) return;
  builder.current = action;
  const pick = document.querySelector("[data-builder-pick]");
  const what = document.querySelector("[data-builder-what]");
  const form = document.querySelector("[data-builder-form]");
  if (pick) pick.value = action.key;
  if (what) what.textContent = action.what;
  form.replaceChildren();
  for (const field of action.fields) {
    const row = el("label", "builder-field");
    row.dataset.field = field.name;
    let input;
    if (field.kind === "flag") {
      input = el("input");
      input.type = "checkbox";
      input.checked = Boolean(values[field.name]);
      row.classList.add("flag");
      row.append(input, el("span", "", field.label));
      if (field.placeholder) row.title = field.placeholder;
    } else {
      row.appendChild(el("span", "builder-label", field.label));
      if (field.choices.length) {
        input = el("select");
        for (const [value, label] of field.choices) {
          const option = el("option", "", label);
          option.value = value;
          input.appendChild(option);
        }
        const start =
          field.name in values
            ? values[field.name]
            : field.kind === "project" && builder.project
              ? builder.project
              : field.choices[0][0];
        input.value = start;
      } else {
        input = el("input");
        input.type = "text";
        input.placeholder = field.placeholder || "";
        input.value = values[field.name] || "";
        if (field.kind === "number") input.inputMode = "numeric";
      }
      row.appendChild(input);
    }
    input.name = field.name;
    input.addEventListener("input", refreshLine);
    input.addEventListener("change", refreshLine);
    form.appendChild(row);
  }
  refreshLine();
}

function builderValues() {
  const values = {};
  const form = document.querySelector("[data-builder-form]");
  for (const input of form.querySelectorAll("[name]")) {
    values[input.name] = input.type === "checkbox" ? input.checked : input.value;
  }
  return values;
}

/* The command line, from the server, a moment after the last keystroke. A
   field the action cannot run with says why in the same place. */
function refreshLine() {
  clearTimeout(builder.timer);
  builder.timer = setTimeout(async () => {
    const shown = document.querySelector("[data-builder-line]");
    const go = document.querySelector("[data-builder-go]");
    if (!builder.current || !shown) return;
    const response = await fetch(`/api/actions/${builder.current.key}/line`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: builderValues() }),
    });
    const answer = await response.json();
    const ok = response.ok && !answer.refused;
    // A field nobody has filled in yet is a prompt, not a failure: quiet
    // until something typed is wrong.
    const missing = !ok && / is needed$/.test(answer.refused || "");
    shown.classList.toggle("refused", !ok && !missing);
    shown.classList.toggle("missing", missing);
    shown.textContent = ok ? answer.line : answer.refused || answer.detail || "cannot run this";
    builder.line = ok ? answer.line : "";
    builder.effect = ok ? answer.effect : "";
    if (go) {
      go.disabled = !ok;
      go.dataset.effect = builder.effect;
      go.textContent = builder.effect && builder.effect !== "reads" ? "run (writes)" : "run";
    }
  }, 120);
}

async function runBuilt() {
  if (!builder.current || !builder.line) return;
  const warning = RUN_WARNINGS[builder.effect];
  if (warning && !window.confirm(`${builder.line}\n\n${warning} Run it?`)) return;
  const run = await post(`/api/actions/${builder.current.key}/run`, {
    values: builderValues(),
    confirmed: Boolean(warning),
  });
  notifyRun(run);
  runsState.picked = run.id;
  watchRunsNow();
}

/* Open the window on an action, from a quick pick or from nowhere. */
async function openBuilder(key, values) {
  openRuns("", key || "first");
  await showAction(key, values || {});
}

(function wireBuilder() {
  const pick = document.querySelector("[data-builder-pick]");
  if (!pick) return;
  pick.addEventListener("change", () => showAction(pick.value));
  document.querySelector("[data-builder-go]").addEventListener("click", runBuilt);
  document.querySelector("[data-builder-copy]").addEventListener("click", () => {
    if (builder.line) navigator.clipboard.writeText(builder.line).then(() => toast("copied"));
  });
  document.querySelector("[data-builder-form]").addEventListener("submit", (event) => {
    event.preventDefault();
    runBuilt();
  });
  document.addEventListener("click", (event) => {
    const tune = event.target.closest("[data-tune]");
    if (!tune) return;
    let values = {};
    try {
      values = JSON.parse(tune.dataset.values || "{}");
    } catch {
      /* an unreadable prefill is an empty one */
    }
    openBuilder(tune.dataset.tune, values);
  });
})();

/* A result, not a transcript (ROADMAP.md §12): the generic renderer, for
   the `data` block and for a command `run_views.py` has no view for. A
   table where the shape is a list of flat records, and a line each
   otherwise. */
function table(data) {
  if (data === null || data === undefined) return null;
  if (Array.isArray(data)) {
    if (!data.length) {
      const none = document.createElement("p");
      none.className = "run-none";
      none.textContent = "nothing to report";
      return none;
    }
    if (typeof data[0] !== "object") return lines(data.map(String));
    /* The columns every row has, in the order the first one lists them.
       Not every key in the union: a row that carries one extra field
       would otherwise widen the table for all of them. */
    const keys = Object.keys(data[0]).filter((k) =>
      data.every((row) => row && typeof row === "object" && k in row),
    );
    const grid = document.createElement("table");
    grid.className = "run-table";
    const head = grid.insertRow();
    for (const key of keys) head.insertCell().textContent = key;
    for (const row of data.slice(0, 200)) {
      const line = grid.insertRow();
      for (const key of keys) line.insertCell().textContent = cell(row[key]);
    }
    if (data.length > 200) {
      const more = grid.insertRow().insertCell();
      more.colSpan = keys.length;
      more.textContent = `and ${data.length - 200} more`;
    }
    return grid;
  }
  if (typeof data === "object") {
    /* A report with a list in it: the list is the answer and the scalars
       beside it are the summary, so draw both rather than picking. */
    const box = document.createElement("div");
    const scalars = Object.entries(data).filter(([, v]) => !Array.isArray(v));
    if (scalars.length) {
      box.appendChild(lines(scalars.map(([k, v]) => `${k}: ${cell(v)}`)));
    }
    for (const [key, value] of Object.entries(data)) {
      if (!Array.isArray(value)) continue;
      const cap = document.createElement("p");
      cap.className = "run-cap";
      cap.textContent = key;
      box.appendChild(cap);
      const grid = table(value);
      if (grid) box.appendChild(grid);
    }
    return box;
  }
  return lines([String(data)]);
}

function cell(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function lines(texts) {
  const list = document.createElement("ul");
  list.className = "run-lines";
  for (const text of texts) {
    const item = document.createElement("li");
    item.textContent = text;
    list.appendChild(item);
  }
  return list;
}

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
  /* On every view, including the ones with no rail to paint. `paintCounts` and
     `paintFsm` are already no-ops when their elements are absent, so the only
     thing the old `#filter-rail` guard bought was silence on the graph view --
     which is the view most in need of both warnings below. It is the newest
     code in the app, so it is the likeliest to be running against a server
     that predates it, and a canvas cannot show a half-rendered panel the way
     a page of markup can: a drag would simply 404 with `error 404` in a
     toast. */
  let baseline = null;

  async function tick() {
    if (document.visibilityState !== "visible") return;
    const params = new URLSearchParams(location.search);
    /* The shelf is about every project, so it follows every project. With
       no scope the endpoint falls back to whichever one sorts first, and
       the page would offer a reload because *that* one changed. */
    if (document.body.dataset.view === "projects") {
      params.set("scope", "repo");
      params.delete("project");
    }
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

    /* The counts *and* when the files last moved. The counts alone missed
       every write that changes no number: a `units extract` over a book with
       nothing new in it, an import that found no marks, a card edited in
       an editor beside the browser. The page then learned about it from
       its own stale guard refusing the next keystroke, which is several
       seconds too late to be a warning. */
    const signature = JSON.stringify([payload.pipeline, payload.files ?? ""]);
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
  /* The template asked the server for a build stamp and got nothing, which
     only an old Python does. Checked once at load rather than on the poll,
     because a server that old does not report staleness either -- it predates
     the field the poll reads, which is exactly the restart where a warning
     would have helped most. */
  if (!document.body.dataset.app) setTimeout(showStale, 0);

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
