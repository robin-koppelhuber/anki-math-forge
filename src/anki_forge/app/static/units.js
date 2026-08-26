/* Units triage: q queue, s skip (with a one-word reason), n annotate.
   Designed for flipping through a hundred units in a few minutes. */

const deck = new Deck();
const board = document.getElementById("deck");
const source = board ? board.dataset.source : "";
const activeState = new URLSearchParams(location.search).get("state") || "new";

async function setState(state, reason) {
  const item = deck.current;
  if (!item) return;
  const body = { state, reason: reason || "", mtime: board.dataset.mtime };
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/state`,
    body,
  );
  board.dataset.mtime = result.mtime;
  item.dataset.state = result.unit.state;
  const badge = item.querySelector(".badge");
  if (badge) {
    badge.textContent = result.unit.state;
    badge.className = "badge state-" + result.unit.state;
  }
  toast(`${result.unit.id} → ${result.unit.state}`);
  if (activeState !== "all" && result.unit.state !== activeState) deck.drop();
  else deck.next();
}

async function annotate() {
  const item = deck.current;
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
  q: () => setState("queued"),
  s: async () => {
    const reason = await ask("skip reason (one word)");
    if (reason === null) return;
    setState("skipped", reason);
  },
  u: () => setState("new"),
  n: annotate,
  j: () => deck.next(),
  k: () => deck.prev(),
  ArrowDown: () => deck.next(),
  ArrowUp: () => deck.prev(),
});
