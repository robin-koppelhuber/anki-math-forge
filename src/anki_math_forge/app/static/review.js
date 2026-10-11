/* Card review: a approve, r reject, e open in $EDITOR, n annotate.
   Approve writes `status` and `content_hash` back to the file. */

const deck = new Deck();
const activeStatus = new URLSearchParams(location.search).get("status") || "draft";

function refresh(item, card) {
  item.dataset.mtime = card.mtime;
  const badge = item.querySelector(".meta-head .badge");
  if (badge) {
    badge.textContent = card.status;
    badge.className = "badge state-" + card.status;
  }
  paintHeld(item, card);
  paintGrades(item, card);
  paintChanges(item, card);
  paintAnnotations(item, card);
  // `plain_notes`, not `notes`: the annotations render as their own rows
  // now, so repainting the whole section here printed each one twice.
  const notes = item.querySelector(".notes");
  if (card.plain_notes && notes) notes.textContent = card.plain_notes;
  else if (card.plain_notes) {
    const div = document.createElement("div");
    div.className = "notes";
    div.textContent = card.plain_notes;
    panelBody(item, "notes").appendChild(div);
  } else if (notes) {
    notes.remove();
  }
}

/* The body of one of a card's panels. */
function panelBody(item, key) {
  return item.querySelector(`[data-panel="${key}"] .panel-body`);
}

/* A panel's small label beside its title. */
function panelCount(item, key, text) {
  const label = item.querySelector(`[data-panel="${key}"] [data-panel-count]`);
  if (label) label.textContent = text;
}

/* What moved since the last decision, redrawn after every write: a grade
   click shows up in it at once, and after a decision the record has a new
   snapshot, so the list empties. One entry per look, newest first, each a
   note of its own. The history is redrawn on the next load. */
function paintChanges(item, card) {
  const panel = item.querySelector('[data-panel="changes"]');
  const body = panel && panel.querySelector(".panel-body");
  if (!body || !card.changes) return;
  const moved = card.changes.pending;
  const entries = card.changes.entries || [];
  const head = body.querySelector("[data-changes-head]");
  if (head) {
    head.textContent = `${moved ? "changed" : "unchanged"} since ${card.changes.after} ${card.changes.since}`;
  }
  panel.toggleAttribute("data-moved", Boolean(moved));
  panelCount(item, "changes", entries.length ? String(entries.length) : "");
  let list = body.querySelector("[data-change-pending]");
  if (!moved) {
    if (list) list.remove();
    return;
  }
  if (!list) {
    list = document.createElement("ol");
    list.className = "change-entries";
    list.dataset.changePending = "";
    if (head) head.after(list);
    else body.prepend(list);
  }
  const shown = (value) => (value === null || value === undefined ? "-" : String(value));
  const row = (kind, name, rest) => {
    const li = document.createElement("li");
    li.dataset.change = kind;
    if (name) {
      const code = document.createElement("code");
      code.textContent = name;
      li.append(code, " ");
    }
    li.append(rest);
    return li;
  };
  list.replaceChildren(
    ...(entries.length ? entries : [{ at: "", change: moved, from: card.changes.from || [] }]).map(
      (entry) => {
        const li = document.createElement("li");
        li.className = "change-entry";
        li.dataset.changeEntry = "";
        const title = document.createElement("p");
        title.className = "change-entry-head";
        title.textContent =
          (entry.at || "just now") + (entry.from && entry.from.length ? ` · from ${entry.from.join(", ")}` : "");
        const items = document.createElement("ul");
        items.className = "change-list";
        items.append(
          ...entry.change.resolved.map((line) => row("resolved", "", line)),
          ...entry.change.fields.map((f) =>
            row("field", f.key, `${shown(f.before)} → ${shown(f.after)}`),
          ),
          ...entry.change.sections.map((sec) => row("section", sec.name, sec.summary)),
        );
        li.append(title, items);
        return li;
      },
    ),
  );
  panel.dataset.default = "open";
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
    // Straight under the head: it says why the status there is not the
    // one the file declares.
    meta.insertBefore(banner, meta.querySelector(".meta-head").nextSibling);
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
  const list = item.querySelector(".annotations");
  panelCount(item, "notes", card.annotations.length ? String(card.annotations.length) : "");
  if (!list) return;
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
  relearn: ["slightly", "more", "reset", ""],
};

/* What a grading button says. `relearn` alone is a bare adverb, so it
   carries its name; the value itself is on `data-value`. */
function gradeLabel(key, value) {
  if (!value) return `no ${key}`;
  return key === "relearn" ? `relearn: ${value}` : value;
}

async function cycleGrade(item, key) {
  const steps = GRADES[key];
  const button = item.querySelector(`[data-grade="${key}"]`);
  const now = button.classList.contains("missing")
    ? ""
    : button.dataset.value || button.textContent.trim();
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
  [
    ["frequency", card.frequency],
    ["derivation", card.derivation],
    ["relearn", card.relearn],
  ].forEach(([key, value]) => {
    const button = item.querySelector(`[data-grade="${key}"]`);
    if (!button) return;
    button.textContent = gradeLabel(key, value);
    button.dataset.value = value || "";
    button.classList.toggle("missing", !value);
  });
  const done = item.querySelector("[data-card-augmented]");
  if (done) {
    done.textContent = card.augmented ? "augmented" : "not augmented";
    done.classList.toggle("on", Boolean(card.augmented));
  }
  // The fold's summary says the two gradings, so it says the new ones.
  panelCount(item, "details", `${card.frequency || "no frequency"} · ${card.derivation || "no derivation"}`);
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

/* How tall each box starts. The rest get four lines. */
const EDIT_ROWS = { front: 4, back: 6, proof: 8 };

/* A card's text, edited here rather than in $EDITOR. The server says which
   sections this card's type allows and what each holds now, so the save is
   checked against what was on disk when the dialog opened. A section the
   card does not have yet is a button under the fields rather than an empty
   box. `focus` is the section a pencil was clicked on. Success reloads onto
   the same card: the body is drawn by the server, crops and all, and
   redrawing it here would be a second renderer. */
async function editCard(focus) {
  const item = currentOf(deck);
  const dialog = document.querySelector("[data-card-edit-dialog]");
  const shape = document.querySelector("[data-card-edit-field]");
  if (!item || !dialog || !shape) return;
  const form = dialog.querySelector("[data-card-edit-form]");
  const response = await fetch(`/api/cards/${item.dataset.uid}/text`);
  if (!response.ok) {
    toast(`error ${response.status}`, "bad");
    return;
  }
  const text = await response.json();
  // A server started before the editor took every section sends two.
  const sections = text.sections || [
    { name: "front", body: text.front, required: true, allowed: true },
    { name: "back", body: text.back, required: true, allowed: true },
  ];
  form.reset();
  const fields = form.querySelector("[data-card-edit-fields]");
  const more = form.querySelector("[data-card-edit-more]");
  const add = form.querySelector("[data-card-edit-add]");
  fields.replaceChildren();
  add.replaceChildren();
  for (const section of sections) {
    const field = shape.content.firstElementChild.cloneNode(true);
    field.dataset.section = section.name;
    field.querySelector(".card-edit-preview").dataset.cardEditPreview = section.name;
    field.querySelector(".card-edit-name").textContent = section.name;
    field.querySelector(".card-edit-hint").textContent = section.required
      ? ""
      : section.allowed
        ? "optional; save it empty to remove it"
        : `a ${text.type} card has no ${section.name}: empty it`;
    const area = field.querySelector("textarea");
    area.name = section.name;
    area.value = section.body;
    area.defaultValue = section.body;
    area.rows = EDIT_ROWS[section.name] || 4;
    // `## verify` is code for the numeric check, not maths to render.
    if (section.name === "verify") field.classList.add("code");
    field.hidden = !section.body && !section.required && section.name !== focus;
    fields.appendChild(field);
    if (field.hidden) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "link-button";
      button.textContent = `+ ${section.name}`;
      button.addEventListener("click", () => {
        field.hidden = false;
        button.remove();
        more.hidden = !add.children.length;
        area.focus();
      });
      add.appendChild(button);
    }
  }
  more.hidden = !add.children.length;
  const gist = item.querySelector(".gist");
  form.querySelector("[data-card-edit-title]").textContent = gist
    ? gist.textContent.trim()
    : text.uid;
  previewCardEdit(form);
  form.dataset.uid = text.uid;
  form.dataset.mtime = text.mtime;
  dialog.showModal();
  const target = (focus && form.elements[focus]) || form.elements.front;
  target.focus();
  target.scrollIntoView({ block: "nearest" });
}

/* What the text renders as, under each box, so an unbalanced `$` shows
   before the save rather than in the next review. */
function previewCardEdit(form) {
  form.querySelectorAll(".card-edit-field").forEach((field) => {
    const box = field.querySelector(".card-edit-preview");
    if (field.hidden || field.classList.contains("code")) {
      box.textContent = "";
      return;
    }
    box.textContent = field.querySelector("textarea").value;
    renderMath(box);
  });
}

(function wireCardEdit() {
  const dialog = document.querySelector("[data-card-edit-dialog]");
  const form = dialog && dialog.querySelector("[data-card-edit-form]");
  if (!form) return;
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-edit-card]");
    if (button) editCard(button.dataset.editCard || "");
  });
  dialog.querySelector("[data-card-edit-cancel]").addEventListener("click", () =>
    dialog.close(),
  );
  form.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  let pending = 0;
  form.addEventListener("input", () => {
    clearTimeout(pending);
    pending = setTimeout(() => previewCardEdit(form), 150);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const uid = form.dataset.uid;
    // Only what you changed, so a section you did not touch is not
    // rewritten on its way through.
    const sections = {};
    form.querySelectorAll(".card-edit-field textarea").forEach((area) => {
      if (area.value !== area.defaultValue) sections[area.name] = area.value;
    });
    const note = form.elements.ask.checked ? form.elements.note.value : "";
    if (!Object.keys(sections).length && !note) {
      dialog.close();
      toast("nothing changed");
      return;
    }
    const body = { scope: viewScope(), mtime: form.dataset.mtime, sections, note };
    const response = await fetch(`/api/cards/${uid}/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (e) {
      payload = { error: response.statusText };
    }
    if (!response.ok) {
      // A 409 keeps what you typed: the file moved since the dialog opened,
      // and closing would throw the edit away.
      toast(payload.detail || payload.error || `error ${response.status}`, "bad");
      return;
    }
    dialog.close();
    location.hash = uid;
    location.reload();
  });
})();

/* Every key that writes waits for the one before it; moving and toggling do
   not. See `oneAtATime`. */
bindKeys({
  approve: () => oneAtATime(() => act("approve")),
  reject: () => oneAtATime(() => act("reject")),
  "back-to-draft": () => oneAtATime(() => act("unapprove")),
  undo: () => oneAtATime(undo),
  editor: openEditor,
  "edit-card": () => editCard(""),
  "note-claude": () => oneAtATime(() => annotate("claude")),
  "note-me": () => oneAtATime(() => annotate("me")),
  "resolve-note": () => oneAtATime(() => resolveAnnotation(0)),
  next: () => deck.nextPending(),
  prev: () => deck.prev(),
  "next-alt": () => deck.nextPending(),
  "prev-alt": () => deck.prev(),
  filters: toggleFilters,
  search: findCard,
  // The shelf is a page now, not a dialog over this one.
  projects: () => (location.href = "/projects"),
  guide: cycleGuide,
});

/* Resolving an annotation is deleting it. There is no reply and no done-flag:
   a note that is still in the file still blocks sync, so anything short of a
   delete would leave the card exactly as stuck as before.

   Which is why it goes on the undo stack. A note imported from Anki has no
   second copy anywhere: `anki pull` erases the comment as it takes it, so the
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

/* The aside's panels: fold one by clicking its title, move one by dragging
   its grip, or with Alt and the arrow keys from the title. Both are remembered
   in this browser, and for every card, so the layout you settle on is the one
   every card has. What the page guessed (`data-default`) applies to a panel
   you have not touched. Without storage the guess stands, and moving still
   works for the page. */
(function wirePanels() {
  const KEY = "forge.review.panels";
  let saved = { order: [], shut: {} };
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}");
    saved = { order: raw.order || [], shut: raw.shut || {} };
  } catch {
    /* storage refused or unreadable: the page's own order and defaults */
  }
  const store = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify(saved));
    } catch {
      /* remembered for this page only */
    }
  };
  const keysIn = (container) => [...container.children].map((p) => p.dataset.panel);

  function arrange(container) {
    const present = keysIn(container);
    const wanted = [
      ...saved.order.filter((k) => present.includes(k)),
      ...present.filter((k) => !saved.order.includes(k)),
    ];
    wanted.forEach((key) => container.appendChild(container.querySelector(`[data-panel="${key}"]`)));
  }

  function shut(panel) {
    const key = panel.dataset.panel;
    return key in saved.shut ? saved.shut[key] : panel.dataset.default !== "open";
  }

  function fold(panel) {
    const closed = shut(panel);
    panel.classList.toggle("folded", closed);
    const toggle = panel.querySelector(".panel-toggle");
    if (toggle) toggle.setAttribute("aria-expanded", String(!closed));
  }

  const all = () => document.querySelectorAll("[data-panels]");
  const settle = () => {
    all().forEach(arrange);
    document.querySelectorAll(".panel").forEach(fold);
  };
  settle();

  function remember(container) {
    saved.order = keysIn(container);
    store();
    all().forEach((other) => other !== container && arrange(other));
  }

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest(".panel-toggle");
    if (!toggle) return;
    const panel = toggle.closest(".panel");
    saved.shut[panel.dataset.panel] = !shut(panel);
    store();
    document
      .querySelectorAll(`.panel[data-panel="${panel.dataset.panel}"]`)
      .forEach(fold);
  });

  /* From the keyboard: Alt and Up or Down on a title moves its panel. */
  document.addEventListener("keydown", (event) => {
    const toggle = event.target.closest && event.target.closest(".panel-toggle");
    if (!toggle || !event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const panel = toggle.closest(".panel");
    const neighbour =
      event.key === "ArrowUp" ? panel.previousElementSibling : panel.nextElementSibling;
    if (!neighbour) return;
    if (event.key === "ArrowUp") panel.parentElement.insertBefore(panel, neighbour);
    else panel.parentElement.insertBefore(neighbour, panel);
    remember(panel.parentElement);
    toggle.focus();
  });

  /* By dragging the grip. The panel under the pointer decides: above its
     middle the dragged one goes before it, below, after. */
  let dragged = null;
  document.addEventListener("dragstart", (event) => {
    const grip = event.target.closest && event.target.closest(".panel-grip");
    if (!grip) return;
    dragged = grip.closest(".panel");
    dragged.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", dragged.dataset.panel);
  });
  document.addEventListener("dragover", (event) => {
    if (!dragged) return;
    const over = event.target.closest && event.target.closest(".panel");
    if (!over || over === dragged || over.parentElement !== dragged.parentElement) return;
    event.preventDefault();
    const box = over.getBoundingClientRect();
    const after = event.clientY > box.top + box.height / 2;
    over.parentElement.insertBefore(dragged, after ? over.nextSibling : over);
  });
  document.addEventListener("dragend", () => {
    if (!dragged) return;
    dragged.classList.remove("dragging");
    remember(dragged.parentElement);
    dragged = null;
  });
})();

/* Find a card: the shared palette over every card in the project, whatever
   the filters say. A card in this list is jumped to; one that is not is
   opened by its link, with the filters off. Shift+Enter keeps the query as a
   filter on the list instead. */
function findCard() {
  const project = document.getElementById("deck").dataset.project || "";
  const where = (query) =>
    `/api/cards/find?project=${encodeURIComponent(project)}&q=${encodeURIComponent(query)}`;
  finder.open({
    title: "find a card",
    placeholder: "text, gist, tag or uid",
    unnamed: "no gist yet",
    delay: 120,
    rows: async (query) => {
      const found = await (await fetch(where(query))).json();
      return {
        ...found,
        rows: found.rows.map((card) => ({
          name: card.gist,
          where: `${card.status} · ${card.uid}`,
          uid: card.uid,
          href: card.href,
        })),
      };
    },
    count: (rows, found) => `${found.matched} of ${found.total}`,
    foot: "enter jumps · shift+enter filters the list",
    pick: (row) => {
      finder.close();
      const at = deck.items.findIndex((item) => item.dataset.uid === row.uid);
      if (at < 0) {
        location.href = row.href;
        return;
      }
      deck.show(at);
      history.replaceState(null, "", `#${row.uid}`);
    },
    shiftEnter: (query) => {
      const url = new URL(location.href);
      if (query.trim()) url.searchParams.set("q", query.trim());
      else url.searchParams.delete("q");
      location.href = url.toString();
    },
  });
}
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-find]")) findCard();
});
