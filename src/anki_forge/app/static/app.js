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
      this.position.textContent = `${this.index + 1} / ${this.items.length}`;
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

  prev() {
    this.show(this.index - 1);
  }

  /* Drop the current item from the working list -- used when an action moves
     it out of the active filter. The file is the truth; this is just the view
     keeping up until the next reload. */
  drop() {
    const item = this.current;
    if (!item) return;
    item.remove();
    this.items.splice(this.index, 1);
    if (!this.items.length) {
      const empty = document.getElementById("empty-filter");
      if (empty) empty.hidden = false;
      if (this.position) this.position.textContent = "0 / 0";
      return;
    }
    this.show(Math.min(this.index, this.items.length - 1));
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
