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
    /* The same order the template renders: what people wrote, then what the
       linter made of it. A list inserted below the findings would put a note
       you just wrote underneath a machine's reading of the card it is about. */
    meta.insertBefore(
      list,
      item.querySelector(".notes, .checks-what, .findings, .checks-ok") ||
        item.querySelector("figure.crop"),
    );
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
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "edit-note";
    edit.dataset.editNote = String(index);
    edit.title = "edit this note, keeping it open";
    edit.textContent = "edit";
    const drop = document.createElement("button");
    drop.type = "button";
    drop.className = "resolve";
    drop.dataset.resolve = String(index);
    drop.title = "resolve: deletes the line, which is the only thing that unblocks sync. Undo puts it back";
    drop.textContent = "resolve";
    row.append(who, what, edit, drop);
    list.appendChild(row);
  });
}

/* Same contract as the units view: the server returns what it replaced, so
   `z` restores exactly that. Approving stamps `content_hash` and rejecting
   drops it, so a status-only undo would leave the card in a state it was
   never in. */
const undoStack = loadUndo("review");

/* One write at a time, as on the units view. Two quick clicks on a grading
   chip raced each other: the second posted the mtime the first had already
   moved, took a 409, and `post` reloaded the page out from under you. */
let busy = false;

async function oneAtATime(work) {
  if (busy) return;
  busy = true;
  try {
    await work();
  } finally {
    busy = false;
  }
}

async function undo() {
  const step = undoStack.pop();
  saveUndo("review", undoStack);
  if (!step) {
    toast("nothing to undo");
    return;
  }
  const item = deck.items.find((node) => node.dataset.uid === step.uid);
  let result;
  try {
    result = await post(`/api/cards/${step.uid}/restore`, {
      snapshot: step.before,
      mtime: step.mtime || (item ? item.dataset.mtime : ""),
    });
  } catch (e) {
    /* `post` has already toasted and, on a 409, scheduled the reload. Letting
       it through leaves an uncaught rejection in the console of a page that is
       behaving correctly, which is noise in the one place you look when
       something is actually wrong. */
    return;
  }
  repaintCounts(result.pipeline);
  if (item) {
    refresh(item, result.card);
    delete item.dataset.settled;
    const banner = item.querySelector(".settled");
    if (banner) banner.remove();
    deck.show(deck.items.indexOf(item));
  }
  /* A resolve does not change the status, so saying what it went back to
     would name a state that never moved. What came back is the note. */
  toast(
    step.what === "resolve"
      ? "undone: the note is back on the card"
      : `undone: ${step.what} → back to ${result.card.status}`,
  );
}

async function act(verb) {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/${verb}`, {
    mtime: item.dataset.mtime,
  });
  if (result.before) {
    /* The mtime this write produced, not the one on the element. Undo is the
       only write that can target a card the current filter does not list, and
       for that card `item` is null and the mtime went out empty -- which
       `_expected_mtime` reads as "no precondition", so `Card.save` skipped the
       staleness check. Approve a card, move to a filter that excludes it, let
       another tab reject it, press undo: the rejection was overwritten with no
       409 and no warning. It was the one unguarded write in the app. */
    undoStack.push({
      uid: item.dataset.uid,
      before: result.before,
      what: verb,
      mtime: result.card.mtime,
    });
    saveUndo("review", undoStack);
  }
  repaintCounts(result.pipeline);
  refresh(item, result.card);
  toast(`${result.card.uid} → ${result.card.status} · ${undoKeyName()} undoes`);
  if (activeStatus !== "all" && result.card.status !== activeStatus) {
    deck.settle(result.card.status, item);
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

/* Two states, and no inherit: a card has had the pass or it has not. */
async function toggleAugmented(item) {
  const button = item.querySelector("[data-card-augmented]");
  const result = await post(`/api/cards/${item.dataset.uid}/augmented`, {
    augmented: !button.classList.contains("on"),
    mtime: item.dataset.mtime,
  });
  /* The rail counts this one. "not augmented" is the row you work the augment
     queue through, so a chip that moves a card without moving the tally leaves
     the number wrong in exactly the view you clicked it from. */
  repaintCounts(result.pipeline);
  refresh(item, result.card);
  toast(
    result.card.augmented
      ? "marked augmented"
      : "withdrawn: `/augment` will pick this card up again",
  );
}

function paintGrades(item, card) {
  [["frequency", card.frequency], ["derivation", card.derivation]].forEach(([key, value]) => {
    const button = item.querySelector(`[data-grade="${key}"]`);
    if (!button) return;
    button.textContent = value || `no ${key}`;
    button.classList.toggle("missing", !value);
  });
  const done = item.querySelector("[data-card-augmented]");
  if (done) {
    done.textContent = card.augmented ? "augmented" : "not augmented";
    done.classList.toggle("on", Boolean(card.augmented));
  }
  const web = item.querySelector("[data-card-web]");
  if (!web) return;
  web.textContent = card.web ? "web: allowed" : "web: no";
  web.classList.toggle("on", Boolean(card.web));
  web.classList.toggle("own", Boolean(card.web_own));
}

document.addEventListener("click", (event) => {
  const grade = event.target.closest("[data-grade]");
  if (grade) {
    oneAtATime(() => cycleGrade(grade.closest(".item"), grade.dataset.grade)).catch(
      () => {},
    );
    return;
  }
  const web = event.target.closest("[data-card-web]");
  if (web) oneAtATime(() => cycleCardWeb(web.closest(".item"))).catch(() => {});
  const done = event.target.closest("[data-card-augmented]");
  if (done) oneAtATime(() => toggleAugmented(done.closest(".item"))).catch(() => {});
});

async function openEditor() {
  const item = currentOf(deck);
  if (!item) return;
  const result = await post(`/api/cards/${item.dataset.uid}/open`, {});
  toast("opened in " + result.opened);
}

/* Every key that writes waits for the one before it; moving and toggling do
   not. See `oneAtATime`. */
bindKeys({
  approve: () => oneAtATime(() => act("approve")),
  reject: () => oneAtATime(() => act("reject")),
  "back-to-draft": () => oneAtATime(() => act("unapprove")),
  undo: () => oneAtATime(undo),
  editor: openEditor,
  "note-claude": () => oneAtATime(() => annotate("claude")),
  "note-me": () => oneAtATime(() => annotate("me")),
  "resolve-note": () => oneAtATime(() => resolveAnnotation(0)),
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
   delete would leave the card exactly as stuck as before.

   Which is why it goes on the undo stack. A note imported from Anki has no
   second copy anywhere: `feedback` erases the comment as it takes it, so the
   line in `## notes` is the only one there is, and this was the one action in
   the app that destroyed something outright. The server sends the line back
   under `before`, and `restore` puts it where any annotation goes. */
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
  if (result.before && result.before.note) {
    undoStack.push({
      uid: item.dataset.uid,
      before: result.before,
      what: "resolve",
      mtime: result.card ? result.card.mtime : "",
    });
    saveUndo("review", undoStack);
  }
  repaintCounts(result.pipeline);
  if (result.card) refresh(item, result.card);
  toast(`resolved. The line is gone from ## notes · ${undoKeyName()} undoes`);
}

/* Rewording one, which is the other half of resolving one.

   The line keeps its place and stays open: this is for a typo, or for a
   request that came back misunderstood and wants saying again. It is not on
   the undo stack, because `restore` puts a note *back* and putting back what
   this replaced would leave the card carrying both. Undoing a wording is
   editing it again. */
async function editAnnotation(index) {
  const item = currentOf(deck);
  if (!item) return;
  const button = item.querySelector(`[data-edit-note="${index}"]`);
  const row = button && button.closest(".annotation");
  if (!row) return;
  const who = row.querySelector(".who");
  const what = row.querySelector(".what");
  /* The whole line, prefix and all. The audience is part of what you are
     editing: dropping the `@me` off the front sends the note to Claude,
     exactly as it would in the file. */
  const current = `${who ? who.textContent : "@claude"} ${what ? what.textContent : ""}`.trim();
  const text = await ask("edit this note", current);
  if (!text || text === current) return;
  const result = await post(`/api/cards/${item.dataset.uid}/edit-annotation`, {
    mtime: item.dataset.mtime,
    index,
    text,
  });
  repaintCounts(result.pipeline);
  refresh(item, result.card);
  toast("note reworded. Still open, so the card is still held out of sync");
}

document.addEventListener("click", (event) => {
  const edit = event.target.closest("[data-edit-note]");
  if (edit) {
    editAnnotation(Number(edit.dataset.editNote)).catch(() => {});
    return;
  }
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
  if (!uid) {
    /* Back out of a jump. An empty hash meant "nothing to do", so the back
       button left you on the card you had jumped *to* -- while the comment on
       `showByUid` promised it returned you to the one you came from. */
    if (cameFrom !== null) deck.show(cameFrom);
    cameFrom = null;
    return;
  }
  // Say so rather than doing nothing. A link that lands on a filter which
  // still excludes its target used to be indistinguishable from a dead one.
  if (!showByUid(uid)) toast(`${uid} is not in this view. Try the status filter`);
}

/* Where the deck was before a `#uid` jump, so the back button has somewhere
   to go. */
let cameFrom = null;

window.addEventListener("hashchange", followHash);
followHash();

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-goto]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
  const uid = link.dataset.goto;
  if (deck.items.some((item) => item.dataset.uid === uid)) {
    // Already here: move the cursor and leave the page alone.
    event.preventDefault();
    cameFrom = deck.index;
    if (location.hash === `#${uid}`) {
      /* Setting a hash to the value it already holds fires no `hashchange`,
         and `preventDefault` has already cancelled the href -- so a second
         click on the same link did nothing at all, silently. Jump directly. */
      showByUid(uid);
      return;
    }
    location.hash = uid;
  }
  // Otherwise the href does the work: it clears the filters that hide it.
});
