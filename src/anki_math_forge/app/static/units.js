/* Units triage: q queue, s skip, S skip-with-reason, n annotate, f filters,
   z undo.
   Designed for flipping through a hundred units in a few minutes. */

const deck = new Deck();
const board = document.getElementById("deck");
const source = board ? board.dataset.source : "";
const activeState = new URLSearchParams(location.search).get("state") || "new";

/* Every action is undoable. The server hands back what the unit looked like
   before it acted, so `z` restores exactly that -- state, reason and any
   suggestion -- rather than guessing. A mis-pressed key costs one keystroke,
   which is the point of a keyboard-driven triage view. */
const undoStack = loadUndo();

function recordUndo(item, result, what) {
  if (!result || !result.before) return;
  undoStack.push({ id: item.dataset.id, before: result.before, what });
  saveUndo(undoStack);
}

function paintState(item, unit) {
  item.dataset.state = unit.state;
  const badge = item.querySelector(".badge");
  if (badge) {
    badge.textContent = unit.state;
    badge.className = "badge state-" + unit.state;
  }
}

async function undo() {
  const step = undoStack.pop();
  saveUndo(undoStack);
  if (!step) {
    toast("nothing to undo");
    return;
  }
  const item = deck.items.find((node) => node.dataset.id === step.id);
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${step.id}/restore`,
    { snapshot: step.before, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  repaintCounts(result.pipeline);
  if (item) {
    paintState(item, result.unit);
    delete item.dataset.settled;
    const banner = item.querySelector(".settled");
    if (banner) banner.remove();
    deck.show(deck.items.indexOf(item));
  }
  toast(`undone: ${step.what} → back to ${result.unit.state}`);
}

async function setState(state, reason) {
  const item = currentOf(deck);
  if (!item) return;
  const body = { state, reason: reason || "", mtime: board.dataset.mtime };
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/state`,
    body,
  );
  board.dataset.mtime = result.mtime;
  repaintCounts(result.pipeline);
  recordUndo(item, result, state);
  paintState(item, result.unit);
  toast(`${result.unit.id} → ${result.unit.state} · z undoes`);
  if (activeState !== "all" && result.unit.state !== activeState) {
    deck.settle(result.unit.state);
  } else {
    deck.next();
  }
}

async function decideOnSuggestion(verb) {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/${verb}`,
    { mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  repaintCounts(result.pipeline);
  recordUndo(item, result, verb === "accept" ? "accept" : "dismiss");
  const note = item.querySelector(".suggestion");
  if (note) note.remove();
  if (verb === "accept") {
    paintState(item, result.unit);
    toast(`${result.unit.id} → ${result.unit.state} (accepted) · z undoes`);
    if (activeState !== "all" && result.unit.state !== activeState) {
      deck.settle(result.unit.state);
    } else {
      deck.next();
    }
  } else {
    toast("suggestion dismissed · z undoes");
  }
}

async function annotate(audience = "claude") {
  const item = currentOf(deck);
  if (!item) return;
  const prefix = audience === "me" ? "@me " : "@claude ";
  const text = await ask(
    audience === "me"
      ? "a decision to park for yourself"
      : "the brief for whoever writes the card",
    prefix,
  );
  if (!text) return;
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/annotate`,
    { text, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  repaintNotes(item, result.unit);
  toast("annotated");
}

/* Answering keeps the question. Deleting the line throws away both halves, and
   the question is most of what made the decision worth recording -- `same as
   2.4?` resolved with `no` is worth reading in six weeks; a blank is not.

   `yes` and `no` are prefills for the same flow rather than a separate one:
   the useful primitive is "answer and settle", and two buttons that only ever
   delete would be two ways to lose the reasoning. */
async function answerNote(item, index, reply) {
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/answer`,
    { index, answer: reply, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  repaintNotes(item, result.unit);
  toast(reply ? `answered: ${reply}` : "note deleted");
}

/* Repainted from the file rather than from the DOM: the indices shift when a
   line is removed, and a stale one answers the wrong question. */
function repaintNotes(item, unit) {
  const pane = item.querySelector(".notes-pane");
  if (!pane || !unit.annotations) return;
  ["claude", "me"].forEach((audience) => {
    const list = pane.querySelector(audience === "me" ? ".note-list.mine" : ".note-list");
    if (!list) return;
    const keep = unit.annotations.filter((n) =>
      audience === "me" ? n.audience === "me" : n.audience !== "me",
    );
    Array.from(list.children).forEach((row, at) => {
      const note = keep[at];
      if (!note) {
        row.remove();
        return;
      }
      row.dataset.noteIndex = String(note.index);
      const text = row.querySelector(".note-text");
      if (text) text.textContent = note.text;
    });
  });
  if (unit.annotations.length !== item.querySelectorAll("[data-note-index]").length) {
    // A note was added, or the split no longer matches. The file is the truth
    // and rebuilding one panel by hand is how the two drift, so reload.
    setTimeout(() => location.reload(), 400);
  }
}

/* How much of the document a card writer gets for this unit.

   Triage is the moment you can see it: the theorem is on this page and its
   hypotheses are two pages back, and no per-source default knows that. `c`
   cycles a few sizes rather than asking for a number, because the decision is
   "a bit more" or "all of it", not a measurement. */
function cycleContext() {
  const item = currentOf(deck);
  if (!item) return;
  const steps = Array.from(item.querySelectorAll("[data-context-step]"));
  const at = steps.findIndex((b) => b.classList.contains("on"));
  const next = steps[(at + 1) % steps.length];
  if (next) setContext(item, Number(next.dataset.contextStep));
}

async function setContext(item, pages) {
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/context`,
    { pages, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  item.dataset.contextPages = String(pages);
  paintContext(item, result.unit);
  toast(`card writers get ${contextLabel(pages)}`);
}

/* Repaint from what the server sent back rather than from what was clicked.
   The chip's whole job is to say which size is in force and whose setting it
   is, and the only place that knows both is the file it just wrote. */
function paintContext(item, unit) {
  const chip = item.querySelector("[data-context-chip]");
  if (!chip || !unit.context_steps) return;
  chip.classList.toggle("own", Boolean(unit.context_own));
  const whose = chip.querySelector(".chip-whose");
  if (whose) whose.textContent = unit.context_own ? "this unit" : "source";
  unit.context_steps.forEach((step) => {
    const button = chip.querySelector(`[data-context-step="${step.pages}"]`);
    if (!button) return;
    button.textContent = step.label;
    button.classList.toggle("on", Boolean(step.on));
  });
}

function contextLabel(pages) {
  if (pages === 0) return "this page only";
  if (pages >= 100) return "the whole document";
  return `${pages} page${pages === 1 ? "" : "s"} either side — ${2 * pages + 1} in all`;
}

/* Three ways to look at the same geometry, cycled with `p`.

   crop     -- the box and a margin. Is this the right region?
   page     -- the whole page it sits on. The two ways segmentation fails are
               only visible against the surroundings: an equation split across
               units shows its missing lines outside the box, and two merged
               into one show two numbers inside it.
   document -- every page, scrolling. Sometimes the question is not about the
               region at all but about what the passage is *saying*, and the
               answer is three paragraphs up, or on the page before.

   Still no pdf.js. The document view is images the browser stacks and scrolls,
   which is the cheap half of a viewer and all that reading needs; pdf.js earns
   its place when you want to drag a box in the browser to make a unit. */
const WHOLE_PAGE = 9999;
const PDF_VIEWS = ["crop", "page", "document"];
const PDF_VIEW_SAID = {
  crop: "the crop",
  page: "the whole page, box drawn on it",
  document: "the whole document — scroll it",
};

function cyclePdfView() {
  const item = currentOf(deck);
  if (!item) return;
  const now = item.dataset.pdfView || "crop";
  showPdfView(item, PDF_VIEWS[(PDF_VIEWS.indexOf(now) + 1) % PDF_VIEWS.length]);
}

async function showPdfView(item, view) {
  const figure = item.querySelector(".crop");
  const img = item.querySelector("[data-crop]");
  if (!figure || !img) return;
  if (!item.dataset.cropSrc) item.dataset.cropSrc = img.getAttribute("src");
  item.dataset.pdfView = view;
  item.classList.toggle("whole-page", view === "page");
  item.classList.toggle("whole-document", view === "document");
  const label = item.querySelector("[data-pdf-view-label]");
  if (label) label.textContent = view;
  toast(PDF_VIEW_SAID[view]);

  if (view === "document") {
    img.hidden = true;
    await buildDocument(item, figure);
    return;
  }
  img.hidden = false;
  const box = figure.querySelector(".doc-scroll");
  if (box) box.hidden = true;
  img.setAttribute(
    "src",
    view === "page"
      ? item.dataset.cropSrc.split("?")[0] + `?context=${WHOLE_PAGE}&outline=1`
      : item.dataset.cropSrc,
  );
}

/* Built once per unit, on first use. The page count needs the PDF opened, so
   asking for it up front would pay that cost for every row in a 750-unit list
   to answer a question nobody asked. */
async function buildDocument(item, figure) {
  const existing = figure.querySelector(".doc-scroll");
  if (existing) {
    existing.hidden = false;
    return;
  }
  const id = item.dataset.id;
  const at = (path) => `${path}/${encodeURIComponent(source)}/${encodeURIComponent(id)}`;
  let info;
  try {
    info = await (await fetch(at("/api/document"))).json();
  } catch {
    toast("could not read the document", "bad");
    return;
  }
  if (!info || !info.pages) {
    toast(info && info.detail ? info.detail : "no document to scroll", "bad");
    return;
  }
  const box = el("div", "doc-scroll");
  for (let n = 1; n <= info.pages; n += 1) {
    const wrap = el("div", "doc-page" + (n === info.page ? " here" : ""));
    const page = document.createElement("img");
    // The page you land on, and its neighbours, are wanted immediately; the
    // other fifty-five are wanted only if you scroll to them.
    page.loading = Math.abs(n - info.page) <= 1 ? "eager" : "lazy";
    page.alt = `page ${n}`;
    page.src = `${at("/page")}.png?n=${n}`;
    wrap.appendChild(page);
    wrap.appendChild(el("span", "doc-page-no", `p${n}`));
    box.appendChild(wrap);
  }
  figure.appendChild(box);
  // Land on the unit's own page rather than at the front of the paper. Only
  // the container scrolls: `scrollIntoView` would move the whole page too.
  const here = box.querySelector(".doc-page.here");
  if (here) box.scrollTop = here.offsetTop;
}

/* Jumping to a neighbouring mark that is a unit in its own right. It is
   usually already in the deck on screen, just hidden behind the one you are
   looking at, so this should not cost a page load. Same shape as the review
   view's dependency links, for the same reason. */
function showById(id) {
  const index = deck.items.findIndex((item) => item.dataset.id === id);
  if (index < 0) return false;
  deck.show(index);
  return true;
}

function followHash() {
  const id = decodeURIComponent(location.hash.replace(/^#/, ""));
  if (!id) return;
  // Say so rather than doing nothing: a link that lands on a filter which
  // still excludes its target is otherwise indistinguishable from a dead one.
  if (!showById(id)) toast(`${id} is not in this view — try the state filter`);
}

window.addEventListener("hashchange", followHash);
followHash();

/* The context badge is a button. `c` does the same thing, and a number you
   are deciding about should be reachable with the pointer you are already
   using to read with. */
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-pdf-view]")) {
    event.preventDefault();
    cyclePdfView();
    return;
  }
  const add = event.target.closest("[data-annotate]");
  if (add) {
    event.preventDefault();
    annotate(add.dataset.annotate);
    return;
  }
  const answer = event.target.closest("[data-answer]");
  if (answer) {
    event.preventDefault();
    const row = answer.closest("[data-note-index]");
    const item = answer.closest(".item");
    if (!row || !item) return;
    const index = Number(row.dataset.noteIndex);
    if (answer.dataset.answer === "?") {
      ask("your answer", "").then((text) => {
        if (text) answerNote(item, index, text);
      });
      return;
    }
    answerNote(item, index, answer.dataset.answer);
    return;
  }
  const step = event.target.closest("[data-context-step]");
  if (step) {
    event.preventDefault();
    const item = step.closest(".item");
    if (item) setContext(item, Number(step.dataset.contextStep));
    return;
  }
  const link = event.target.closest("[data-goto]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
  if (deck.items.some((item) => item.dataset.id === link.dataset.goto)) {
    event.preventDefault();
    location.hash = encodeURIComponent(link.dataset.goto);
  }
});

bindKeys({
  "?": cycleGuide,
  c: cycleContext,
  p: cyclePdfView,
  f: toggleFilters,
  g: openGallery,
  z: undo,
  q: () => setState("queued"),
  /* No prompt. A skip is the commonest action in triage, and stopping to type
     a word turned one keystroke into a dialogue. `S` still asks, for the times
     the reason is worth recording. */
  s: () => setState("skipped"),
  S: async () => {
    const reason = await ask("skip reason (optional)");
    if (reason === null) return;
    setState("skipped", reason);
  },
  u: () => setState("new"),
  a: () => decideOnSuggestion("accept"),
  d: () => decideOnSuggestion("dismiss"),
  n: () => annotate("claude"),
  N: () => annotate("me"),
  j: () => deck.nextPending(),
  k: () => deck.prev(),
  ArrowDown: () => deck.nextPending(),
  ArrowUp: () => deck.prev(),
});
