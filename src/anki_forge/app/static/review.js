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

async function act(verb) {
  const item = deck.current;
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/${verb}`, {
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  toast(`${result.card.uid} → ${result.card.status}`);
  if (activeStatus !== "all" && result.card.status !== activeStatus) deck.drop();
  else deck.next();
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
  a: () => act("approve"),
  r: () => act("reject"),
  e: openEditor,
  n: annotate,
  j: () => deck.next(),
  k: () => deck.prev(),
  ArrowDown: () => deck.next(),
  ArrowUp: () => deck.prev(),
});
