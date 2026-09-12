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
  paintHeld(item, card);
  paintGrades(item, card);
  paintAnnotations(item, card);
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

/* An approval that is not holding. Saying "draft" alone reads as work lost:
   the file still says `approved` and resolving the note restores it, so the
   card has to show both halves. */
function paintHeld(item, card) {
  const meta = item.querySelector(".meta");
  let banner = item.querySelector(".held");
  if (!card.demotion) {
    if (banner) banner.remove();
    return;
  }
  if (!banner) {
    banner = document.createElement("p");
    banner.className = "held";
    meta.insertBefore(banner, item.querySelector(".findings, .checks-ok"));
  }
  banner.textContent =
    card.demotion === "annotated"
      ? "back in the draft pile while a note is open. Nothing about the card changed and the approval is not withdrawn: resolve the note and it is approved again."
      : "back in the draft pile because it was edited after approval. Re-read it and approve again.";
}

/* The note that was just written has to appear. It did not: the panel was
   rendered once by the server and never rebuilt, so writing one looked like
   nothing had happened -- and the only way to see it was a reload. */
function paintAnnotations(item, card) {
  if (!card.annotations) return;
  let list = item.querySelector(".annotations");
  if (!card.annotations.length) {
    if (list) list.remove();
    return;
  }
  if (!list) {
    list = document.createElement("ul");
    list.className = "annotations";
    const meta = item.querySelector(".meta");
    meta.insertBefore(list, item.querySelector(".notes") || item.querySelector("figure.crop"));
  }
  list.textContent = "";
  card.annotations.forEach((note, index) => {
    const row = document.createElement("li");
    row.className = "annotation " + note.audience;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = "@" + note.audience;
    const what = document.createElement("span");
    what.className = "what";
    what.textContent = note.text;
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "resolve";
    drop.dataset.resolve = String(index);
    drop.title = "resolve: deletes the line, which is the only thing that unblocks sync";
    drop.textContent = "resolve";
    row.append(who, what, drop);
    list.appendChild(row);
  });
}

/* Same contract as the units view: the server returns what it replaced, so
   `z` restores exactly that. Approving stamps `content_hash` and rejecting
   drops it, so a status-only undo would leave the card in a state it was
   never in. */
const undoStack = loadUndo("review");

async function undo() {
  const step = undoStack.pop();
  saveUndo("review", undoStack);
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
    saveUndo("review", undoStack);
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

async function annotate(audience = "claude") {
  const item = currentOf(deck);
  if (!item) return;
  const text = await ask(
    audience === "me" ? "a decision to park" : "a request for Claude",
    audience === "me" ? "@me " : "@claude ",
  );
  if (!text) return;
  const result = await post(`/api/cards/${item.dataset.uid}/annotate`, {
    text,
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  repaintCounts(result.pipeline);
  // The cursor stays. Annotating was treated as a decision -- "said, done,
  // move on" -- which is wrong twice over: a card often wants two notes, and
  // the note that was just written scrolled off before it could be read back.
  toast("annotated. Held out of sync until it is resolved");
}

/* The two gradings, cycled in place.

   They decide the order Anki introduces new cards in, and until now the only
   way to set either was to open the file -- which is why so many cards carry
   neither. You learn that a result is `common` rather than `core` by meeting
   it, which is to say during review, which is here.

   The cycle passes through unset deliberately. A grading given by a mis-click
   should be removable by carrying on clicking, not by reaching for an editor.

   Neither is inside `content_hash`, so none of this un-approves a card: the
   argument is `requires`'s, spelled out in CLAUDE.md -- approving a card is
   not approving its position in the queue. */
const GRADES = {
  frequency: ["core", "common", "rare", ""],
  derivation: ["definitional", "short", "long", ""],
};

async function cycleGrade(item, key) {
  const steps = GRADES[key];
  const button = item.querySelector(`[data-grade="${key}"]`);
  const now = button.classList.contains("missing") ? "" : button.textContent.trim();
  const value = steps[(steps.indexOf(now) + 1) % steps.length];
  const result = await post(`/api/cards/${item.dataset.uid}/grade`, {
    key,
    value,
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  repaintCounts(result.pipeline);
  toast(value ? `${key}: ${value}` : `${key} cleared`);
}

/* Whether whoever augments this card may look things up. Three states, not
   two: `inherit` is the absence of a decision here, and it is what lets a
   grant made during triage carry through to the card written from it. */
const CARD_WEB = [true, false, null];

async function cycleCardWeb(item) {
  const button = item.querySelector("[data-card-web]");
  const now = button.classList.contains("own") ? button.classList.contains("on") : null;
  const web = CARD_WEB[(CARD_WEB.indexOf(now) + 1) % CARD_WEB.length];
  const result = await post(`/api/cards/${item.dataset.uid}/web`, {
    web,
    mtime: item.dataset.mtime,
  });
  refresh(item, result.card);
  toast(
    result.card.web
      ? "web lookups allowed for this card"
      : "no lookups: the card says what the source says",
  );
}

function paintGrades(item, card) {
  [["frequency", card.frequency], ["derivation", card.derivation]].forEach(([key, value]) => {
    const button = item.querySelector(`[data-grade="${key}"]`);
    if (!button) return;
    button.textContent = value || `no ${key}`;
    button.classList.toggle("missing", !value);
  });
  const web = item.querySelector("[data-card-web]");
  if (!web) return;
  web.textContent = card.web ? "web: allowed" : "web: no";
  web.classList.toggle("on", Boolean(card.web));
  web.classList.toggle("own", Boolean(card.web_own));
}

document.addEventListener("click", (event) => {
  const grade = event.target.closest("[data-grade]");
  if (grade) {
    cycleGrade(grade.closest(".item"), grade.dataset.grade).catch(() => {});
    return;
  }
  const web = event.target.closest("[data-card-web]");
  if (web) cycleCardWeb(web.closest(".item")).catch(() => {});
});

async function openEditor() {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/open`, {});
  toast("opened in " + result.opened);
}

bindKeys({
  approve: () => act("approve"),
  reject: () => act("reject"),
  "back-to-draft": () => act("unapprove"),
  undo,
  editor: openEditor,
  "note-claude": () => annotate("claude"),
  "note-me": () => annotate("me"),
  "resolve-note": () => resolveAnnotation(0),
  next: () => deck.nextPending(),
  prev: () => deck.prev(),
  "next-alt": () => deck.nextPending(),
  "prev-alt": () => deck.prev(),
  filters: toggleFilters,
  sources: openGallery,
  guide: cycleGuide,
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
  if (result.card) refresh(item, result.card);
  toast("resolved. The line is gone from ## notes");
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
  if (!showByUid(uid)) toast(`${uid} is not in this view. Try the status filter`);
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
