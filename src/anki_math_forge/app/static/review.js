/* Card review: a approve, r reject, e open in $EDITOR, n annotate.
   Approve writes `status` and `content_hash` back to the file. */

const deck = new Deck();
const activeStatus = new URLSearchParams(location.search).get("status") || "draft";
const activeAnnotated = new URLSearchParams(location.search).get("annotated") || "";

function refresh(item, card) {
  item.dataset.mtime = card.mtime;
  const badge = item.querySelector(".badge");
  if (badge) {
    badge.textContent = card.status;
    badge.className = "badge state-" + card.status;
  }
  // `plain_notes`, not `notes`: the annotations render as their own rows
  // now, so repainting the whole section here printed each one twice.
  const notes = item.querySelector(".notes");
  if (card.plain_notes && notes) notes.textContent = card.plain_notes;
  else if (card.plain_notes) {
    const div = document.createElement("div");
    div.className = "notes";
    div.textContent = card.plain_notes;
    item.querySelector(".meta").appendChild(div);
  } else if (notes) {
    notes.remove();
  }
}

/* Same contract as the units view: the server returns what it replaced, so
   `z` restores exactly that. Approving stamps `content_hash` and rejecting
   drops it, so a status-only undo would leave the card in a state it was
   never in. */
const undoStack = loadUndo();

async function undo() {
  const step = undoStack.pop();
  saveUndo(undoStack);
  if (!step) {
    toast("nothing to undo");
    return;
  }
  const item = deck.items.find((node) => node.dataset.uid === step.uid);
  const result = await post(`/api/cards/${step.uid}/restore`, {
    snapshot: step.before,
    mtime: item ? item.dataset.mtime : "",
  });
  repaintCounts(result.pipeline);
  if (item) {
    refresh(item, result.card);
    delete item.dataset.settled;
    const banner = item.querySelector(".settled");
    if (banner) banner.remove();
    deck.show(deck.items.indexOf(item));
  }
  toast(`undone: ${step.what} → back to ${result.card.status}`);
}

async function act(verb) {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/${verb}`, {
    mtime: item.dataset.mtime,
  });
  if (result.before) {
    undoStack.push({ uid: item.dataset.uid, before: result.before, what: verb });
    saveUndo(undoStack);
  }
  repaintCounts(result.pipeline);
  refresh(item, result.card);
  toast(`${result.card.uid} → ${result.card.status} · z undoes`);
  if (activeStatus !== "all" && result.card.status !== activeStatus) {
    deck.settle(result.card.status);
  } else {
    deck.next();
  }
}

async function annotate() {
  const item = currentOf(deck);
  if (!item) return;
  const text = await ask("annotation for " + item.dataset.uid, "@claude ");
  if (!text) return;
  const result = await post(`/api/cards/${item.dataset.uid}/annotate`, {
    text,
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  repaintCounts(result.pipeline);
  // Annotating *is* a decision: you have said your piece and you are done
  // with the card. Leaving the cursor put meant reaching for `j` every time,
  // which is the one thing every other action here does for you.
  if (activeAnnotated === "none") {
    deck.settle("annotated");
  } else {
    deck.nextPending();
  }
  toast("annotated — sync refuses it until resolved · k goes back");
}

async function openEditor() {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/open`, {});
  toast("opened in " + result.opened);
}

bindKeys({
  "?": cycleGuide,
  f: toggleFilters,
  g: openGallery,
  z: undo,
  a: () => act("approve"),
  u: () => act("unapprove"),
  r: () => act("reject"),
  e: openEditor,
  n: annotate,
  x: () => resolveAnnotation(0),
  j: () => deck.nextPending(),
  k: () => deck.prev(),
  ArrowDown: () => deck.nextPending(),
  ArrowUp: () => deck.prev(),
});

/* Resolving an annotation is deleting it. There is no reply and no done-flag:
   a note that is still in the file still blocks sync, so anything short of a
   delete would leave the card exactly as stuck as before. */
async function resolveAnnotation(index) {
  const item = currentOf(deck);
  if (!item) return;
  const rows = item.querySelectorAll("[data-resolve]");
  if (!rows.length) {
    toast("no annotations on this card");
    return;
  }
  const result = await post(`/api/cards/${item.dataset.uid}/resolve`, {
    mtime: item.dataset.mtime,
    index,
  });
  item.dataset.mtime = result.card ? result.card.mtime : item.dataset.mtime;
  repaintCounts(result.pipeline);
  const row = rows[index];
  if (row) row.closest(".annotation").remove();
  toast("resolved — the line is gone from ## notes");
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-resolve]");
  if (!button) return;
  resolveAnnotation(Number(button.dataset.resolve)).catch(() => {});
});


/* Following a dependency. The card is usually already in the deck on screen,
   just hidden behind the one you are looking at, so jumping to it should not
   cost a page load. The hash is what carries it either way: setting it makes
   a history entry, so the back button returns you to the card you came from,
   and a full navigation lands on `#uid` and is picked up by the same handler. */
function showByUid(uid) {
  const index = deck.items.findIndex((item) => item.dataset.uid === uid);
  if (index < 0) return false;
  deck.show(index);
  return true;
}

function followHash() {
  const uid = location.hash.replace(/^#/, "");
  if (!uid) return;
  // Say so rather than doing nothing. A link that lands on a filter which
  // still excludes its target used to be indistinguishable from a dead one.
  if (!showByUid(uid)) toast(`${uid} is not in this view — try the status filter`);
}

window.addEventListener("hashchange", followHash);
followHash();

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-goto]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
  const uid = link.dataset.goto;
  if (deck.items.some((item) => item.dataset.uid === uid)) {
    // Already here: move the cursor and leave the page alone.
    event.preventDefault();
    location.hash = uid;
  }
  // Otherwise the href does the work: it clears the filters that hide it.
});
