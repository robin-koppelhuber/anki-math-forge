/* Shared machinery for both views: one item at a time, keyboard-first.
   The app is a view over files -- nothing here caches anything, and every
   write round-trips to the server, which re-reads from disk. */

const KATEX_DELIMS = [
  { left: "$$", right: "$$", display: true },
  { left: "$", right: "$", display: false },
  { left: "\\[", right: "\\]", display: true },
  { left: "\\(", right: "\\)", display: false },
];

function renderMath(root) {
  if (typeof renderMathInElement !== "function") return;
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
    if (!this.items.length) return;
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
    if (item) item.scrollIntoView({ block: "nearest" });
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

function bindKeys(handlers) {
  document.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (document.getElementById("prompt").open) return;
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
const SPLIT_KEY = "anki-forge.split";

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

function applySplit(fraction) {
  const clamped = Math.min(0.85, Math.max(0.15, fraction));
  document.documentElement.style.setProperty("--split", `${clamped}fr`);
  document.documentElement.style.setProperty("--split-right", `${1 - clamped}fr`);
  return clamped;
}

function applyRail(name, px) {
  const rail = RAILS[name];
  const clamped = Math.min(railBound(name, "max"), Math.max(railBound(name, "min"), px));
  document.documentElement.style.setProperty(rail.var, `${clamped}px`);
  return clamped;
}

(function enableDragging() {
  applySplit(recall(SPLIT_KEY, 0.5));
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
      : { kind: "split", box: splitter.parentElement, handle };
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
    if (box.width) applySplit((event.clientX - box.left) / box.width);
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
      remember(SPLIT_KEY, read("--split"));
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
    if (event.target.closest("[data-splitter]")) {
      applySplit(0.5);
      remember(SPLIT_KEY, 0.5);
    }
  });
})();
