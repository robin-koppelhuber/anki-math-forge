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

async function annotate() {
  const item = currentOf(deck);
  if (!item) return;
  const text = await ask("annotation for " + item.dataset.id, "@claude ");
  if (!text) return;
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/annotate`,
    { text, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  toast("annotated");
}

/* How much of the document a card writer gets for this unit.

   Triage is the moment you can see it: the theorem is on this page and its
   hypotheses are two pages back, and no per-source default knows that. `c`
   cycles a few sizes rather than asking for a number, because the decision is
   "a bit more" or "all of it", not a measurement. */
const CONTEXT_STEPS = [0, 1, 3, 10, 999];

async function cycleContext() {
  const item = currentOf(deck);
  if (!item) return;
  const now = Number(item.dataset.contextPages || 1);
  const next =
    CONTEXT_STEPS.find((n) => n > now) ?? CONTEXT_STEPS[0];
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/context`,
    { pages: next, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  item.dataset.contextPages = String(next);
  const badge = item.querySelector("[data-context-badge]");
  if (badge) badge.textContent = contextLabel(next);
  toast(`card writers get ${contextLabel(next)}`);
}

function contextLabel(pages) {
  if (pages === 0) return "this page only";
  if (pages >= 100) return "the whole document";
  return `${pages} page${pages === 1 ? "" : "s"} either side`;
}

/* The whole page, with the unit's own box drawn on it.

   The two ways segmentation fails are only visible against the surroundings:
   an equation split across units shows its missing lines outside the box, and
   two merged into one show two numbers inside it. A wide margin usually
   suffices; when it does not, this is the rest of the page. No pdf.js needed
   -- the renderer already clips to the page, so asking for more than a page
   gives exactly a page. */
const WHOLE_PAGE = 9999;

function togglePage() {
  const item = currentOf(deck);
  if (!item) return;
  const img = item.querySelector("[data-crop]");
  if (!img) return;
  const whole = item.dataset.wholePage === "1";
  if (!item.dataset.cropSrc) item.dataset.cropSrc = img.getAttribute("src");
  img.setAttribute(
    "src",
    whole
      ? item.dataset.cropSrc
      : item.dataset.cropSrc.split("?")[0] + `?context=${WHOLE_PAGE}&outline=1`,
  );
  item.dataset.wholePage = whole ? "0" : "1";
  item.classList.toggle("whole-page", !whole);
  toast(whole ? "back to the crop" : "the whole page, box drawn on it");
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

document.addEventListener("click", (event) => {
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
  p: togglePage,
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
  n: annotate,
  j: () => deck.nextPending(),
  k: () => deck.prev(),
  ArrowDown: () => deck.nextPending(),
  ArrowUp: () => deck.prev(),
});
