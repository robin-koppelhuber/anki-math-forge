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

bindKeys({
  "?": cycleGuide,
  f: toggleFilters,
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
