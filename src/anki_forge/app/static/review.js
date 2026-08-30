/* Card review: a approve, r reject, e open in $EDITOR, n annotate.
   Approve writes `status` and `content_hash` back to the file. */

const deck = new Deck();
const activeStatus = new URLSearchParams(location.search).get("status") || "draft";

function refresh(item, card) {
  item.dataset.mtime = card.mtime;
  const badge = item.querySelector(".badge");
  if (badge) {
    badge.textContent = card.status;
    badge.className = "badge state-" + card.status;
  }
  const notes = item.querySelector(".notes");
  if (card.notes && notes) notes.textContent = card.notes;
  else if (card.notes) {
    const pre = document.createElement("pre");
    pre.className = "notes";
    pre.textContent = card.notes;
    item.querySelector(".meta").appendChild(pre);
  }
}

/* Same contract as the units view: the server returns what it replaced, so
   `z` restores exactly that. Approving stamps `content_hash` and rejecting
   drops it, so a status-only undo would leave the card in a state it was
   never in. */
const undoStack = [];

async function undo() {
  const step = undoStack.pop();
  if (!step) {
    toast("nothing to undo");
    return;
  }
  const item = deck.items.find((node) => node.dataset.uid === step.uid);
  const result = await post(`/api/cards/${step.uid}/restore`, {
    snapshot: step.before,
    mtime: item ? item.dataset.mtime : "",
  });
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
  const item = deck.current;
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/${verb}`, {
    mtime: item.dataset.mtime,
  });
  if (result.before) undoStack.push({ uid: item.dataset.uid, before: result.before, what: verb });
  refresh(item, result.card);
  toast(`${result.card.uid} → ${result.card.status} · z undoes`);
  if (activeStatus !== "all" && result.card.status !== activeStatus) {
    deck.settle(result.card.status);
  } else {
    deck.next();
  }
}

async function annotate() {
  const item = deck.current;
  if (!item) return;
  const text = await ask("annotation for " + item.dataset.uid, "@claude ");
  if (!text) return;
  const result = await post(`/api/cards/${item.dataset.uid}/annotate`, {
    text,
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  toast("annotated — sync will refuse this card until it is resolved");
}

async function openEditor() {
  const item = deck.current;
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/open`, {});
  toast("opened in " + result.opened);
}

bindKeys({
  "?": cycleGuide,
  f: toggleFilters,
  z: undo,
  a: () => act("approve"),
  r: () => act("reject"),
  e: openEditor,
  n: annotate,
  j: () => deck.nextPending(),
  k: () => deck.prev(),
  ArrowDown: () => deck.nextPending(),
  ArrowUp: () => deck.prev(),
});
