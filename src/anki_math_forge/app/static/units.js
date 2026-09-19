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
const undoStack = loadUndo("units");

/* One write at a time.

   Keys arrive faster than a round trip, and two in flight against one ledger
   is how `q` `q` settled the wrong unit and how `q` `z` either popped an empty
   stack -- the `q` had not recorded yet, and its toast overwrote the "nothing
   to undo" -- or posted the pre-`q` mtime and took a 409 and a forced reload.
   Neither is a race worth winning: a triage key is one keystroke and the
   answer is to make the second one wait. */
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

function recordUndo(item, result, what) {
  if (!result || !result.before) return;
  undoStack.push({ id: item.dataset.id, before: result.before, what });
  saveUndo("units", undoStack);
}

/* Reload, and land back on this unit. The deck is rebuilt from the file on
   every request, so the only thing carried across is which one you were
   reading -- through the hash, which `followHash` already knows how to use. */
function reloadHere(item) {
  /* The hash first, then a real reload.

     `location.replace(url)` with a URL that differs only in its fragment does
     not re-fetch the document -- it moves the fragment and fires `hashchange`.
     So the page did not reload at all: the note was on disk, the toast said so,
     and the panel still showed what it had before the write. `reload()` after
     setting the hash is a fetch, and `followHash` puts you back on the unit. */
  if (item) location.hash = item.dataset.id;
  location.reload();
}

function paintState(item, unit) {
  item.dataset.state = unit.state;
  const badge = item.querySelector(".badge");
  if (badge) {
    badge.textContent = unit.state;
    badge.className = "badge state-" + unit.state;
  }
}

/* The writes that leave a unit's state alone. Their undo has no state to
   report, so it says what it put back instead. */
const LEAVES_THE_STATE = new Set(["context size", "web lookups"]);

async function undo() {
  const step = undoStack.pop();
  saveUndo("units", undoStack);
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
    /* All three, because `restore` puts all three back: the snapshot carries
       the state, the brief, the window and the web grant, and a repaint that
       covers one of them leaves the other two showing what you just undid. */
    paintState(item, result.unit);
    paintContext(item, result.unit);
    paintWeb(item, result.unit);
    delete item.dataset.settled;
    const banner = item.querySelector(".settled");
    if (banner) banner.remove();
    /* The suggestion block is removed from the DOM when you accept or dismiss
       one, and the undo put it back in the *file* and not on the screen: the
       rail said two suggestions and the unit in front of you showed none.
       Reloading is the honest repaint -- the block carries the proposal, its
       reason and its buttons, and rebuilding that from the payload is a second
       renderer of the same thing. */
    if (result.unit.suggestion && !item.querySelector(".suggestion")) {
      reloadHere(item);
      return;
    }
    deck.show(deck.items.indexOf(item));
  }
  /* A state change is the only thing whose undo has a state to report. The
     window and the web grant leave the state where it was, and naming it
     there would print "back to new" about something that never moved. */
  toast(
    LEAVES_THE_STATE.has(step.what)
      ? `undone: ${step.what} is back where it was`
      : `undone: ${step.what} → back to ${result.unit.state}`,
  );
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
  toast(`${result.unit.id} → ${result.unit.state} · ${undoKeyName()} undoes`);
  if (activeState !== "all" && result.unit.state !== activeState) {
    deck.settle(result.unit.state, item);
  } else {
    deck.next();
  }
}

async function decideOnSuggestion(verb) {
  const item = currentOf(deck);
  if (!item) return;
  /* Both keys refuse the same way. `accept` was refused by the server, which
     `post` turns into a toast *and* a rethrow nobody caught -- so a routine
     miss on a key the footer invites you to press became an uncaught page
     error. `dismiss` was worse: it claimed success and pushed an undo step for
     a suggestion that was never there. */
  if (!item.querySelector(".suggestion")) {
    toast(`${item.dataset.id} has nothing suggested`);
    return;
  }
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
    toast(`${result.unit.id} → ${result.unit.state} (accepted) · ${undoKeyName()} undoes`);
    if (activeState !== "all" && result.unit.state !== activeState) {
      deck.settle(result.unit.state, item);
    } else {
      deck.next();
    }
  } else {
    toast("suggestion dismissed · ${undoKeyName()} undoes");
  }
}

async function noteOn(item, text) {
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/annotate`,
    { text, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  return result;
}

async function annotate(audience = "claude") {
  const item = currentOf(deck);
  if (!item) return;
  /* The prefix is added here rather than pre-filled into the box. It was the
     box's starting value, selected, so the first keystroke wiped it and `N`
     filed an unaddressed note -- which `Ledger.annotate` reads as `@claude`.
     `N` was indistinguishable from `n`. Asking for the text alone also means
     an empty answer stays empty rather than writing a bare `@claude` with
     nothing after it. */
  const mine = audience === "me";
  const said = await ask(
    mine ? "a decision to park for yourself" : "the brief for whoever writes the card",
  );
  if (!said) return;
  repaintNotes(item, (await noteOn(item, `${mine ? "@me" : "@claude"} ${said}`)).unit);
  toast(`annotated for ${mine ? "you" : "claude"}`);
}

/* Queue it, and say what the card is about, in one keystroke.

   The unit stage answers two questions -- is this worth a card, and roughly
   what would the card be about -- and only the first had a key. The second
   was a separate `n`, on a unit that had already scrolled past, which is why
   most units reach `/extract-cards` carrying nothing but a picture.

   Symmetric with `s`/`S`: the bare key is the common case and does not stop to
   ask, the shifted one records the sentence that makes the decision useful
   later. The note goes on *after* the state change, so a failure here leaves a
   queued unit with no brief rather than losing the queue -- and `n` fixes
   that, while nothing fixes a decision that never landed.

   Deliberately not `repaintNotes`: the unit has settled and is leaving the
   view, and that function reloads the page when the note count moves. */
async function queueWithABrief() {
  const item = currentOf(deck);
  if (!item) return;
  const text = await ask("what should the card be about?", "@claude ");
  if (text === null) return;
  await setState("queued");
  if (text.trim()) await noteOn(item, text);
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
    // and rebuilding one panel by hand is how the two drift, so reload --
    // *onto the unit you were on*. It used to come back at the top of the
    // deck, so writing a brief at unit forty cost you the scroll back.
    setTimeout(() => reloadHere(item), 400);
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
  /* The step verbatim, not a number: one of the sizes is the word `chapter`,
     and `Number("chapter")` is NaN, which the server would read as no size at
     all. The server parses it, because it is the same vocabulary the TOML
     files and `--pages` take. */
  return next ? setContext(item, next.dataset.contextStep) : undefined;
}

async function setContext(item, pages) {
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/context`,
    { pages, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  /* Recorded, like every other write. A key that changes a unit and leaves the
     undo stack alone is a key `z` silently steps over -- and it then acts on
     an older step, which is very likely a different unit. */
  recordUndo(item, result, "context size");
  item.dataset.contextPages = String(pages);
  paintContext(item, result.unit);
  toast(`card writers get ${contextLabel(pages)} · ${undoKeyName()} undoes`);
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
  if (pages === "chapter") return "the chapter it is in";
  const size = Number(pages);
  if (size === 0) return "this page only";
  if (size >= 100) return "the whole document";
  return `${size} page${size === 1 ? "" : "s"} either side — ${2 * size + 1} in all`;
}

/* Whether whoever writes this card may look things up on the web.

   Three states and not two. `inherit` is not the same as `no`: it is the
   absence of a decision here, and collapsing them would make a source-wide
   grant unrevokable for one unit and a source-wide refusal unliftable. `w`
   walks allowed -> no -> inherit, which is also the order you would reach for
   them in -- you grant it, you change your mind, you stop having an opinion. */
const WEB_STEPS = [true, false, null];

function cycleWeb() {
  const item = currentOf(deck);
  if (!item) return;
  const now = item.dataset.webOwn === "1" ? item.dataset.web === "1" : null;
  return setWeb(item, WEB_STEPS[(WEB_STEPS.indexOf(now) + 1) % WEB_STEPS.length]);
}

async function setWeb(item, web) {
  const result = await post(
    `/api/units/${encodeURIComponent(source)}/${item.dataset.id}/web`,
    { web, mtime: board.dataset.mtime },
  );
  board.dataset.mtime = result.mtime;
  recordUndo(item, result, "web lookups");
  paintWeb(item, result.unit);
  toast(
    `${
      result.unit.web
        ? "web research allowed for this unit"
        : result.unit.web_own
          ? "no lookups here, whatever the source says"
          : "no lookups: inherited from the source"
    } · ${undoKeyName()} undoes`,
  );
}

function paintWeb(item, unit) {
  const chip = item.querySelector("[data-web-chip]");
  if (!chip) return;
  item.dataset.web = unit.web ? "1" : "0";
  item.dataset.webOwn = unit.web_own ? "1" : "0";
  chip.classList.toggle("own", Boolean(unit.web_own));
  const whose = chip.querySelector(".chip-whose");
  if (whose) whose.textContent = unit.web_own ? "this unit" : "source";
  chip.querySelectorAll("[data-web-set]").forEach((button) => {
    button.classList.toggle("on", (button.dataset.webSet === "1") === Boolean(unit.web));
  });
}

/* Which of the neighbouring marks are worth reading right now.

   Independent of the left rail on purpose. That filter decides which *units*
   you meet; this one decides how much of the page around the unit in front of
   you is worth reading, and they pull in opposite directions -- narrowing the
   queue to green claims while also hiding every purple term beside them would
   remove exactly the context the decision needs.

   Remembered, because you triage one paper in one sitting and the colours that
   matter do not change between two units in a row. Per source, since a scheme
   is a fact about how one document was read. */
const MARK_FILTER_KEY = `anki-forge.marks.${source}`;

function hiddenColours() {
  try {
    return new Set(JSON.parse(localStorage.getItem(MARK_FILTER_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function rememberColours(hidden) {
  try {
    localStorage.setItem(MARK_FILTER_KEY, JSON.stringify(Array.from(hidden)));
  } catch {
    /* a private window still filters, it just forgets between loads */
  }
}

function paintMarkFilter(root = document) {
  const hidden = hiddenColours();
  // Per group, because the filter is per group: one row of colours for the
  // whole list could not say "the green highlights but not the green notes",
  // and it offered colours that were not in the group you were looking at.
  root.querySelectorAll(".mark-group").forEach((group) => {
    group.querySelectorAll("[data-mark-colour]").forEach((chip) => {
      const key = chip.dataset.markColour;
      if (key && key !== "*") chip.classList.toggle("on", !hidden.has(key));
    });
    const rows = Array.from(group.querySelectorAll("li[data-colour]"));
    rows.forEach((row) => {
      row.hidden = hidden.has(row.dataset.colour);
    });
    // A group whose rows are all filtered out still has to say so: an empty
    // `<details>` reads as "nothing of this kind here", which is a different
    // and false claim.
    const shown = rows.filter((row) => !row.hidden).length;
    group.classList.toggle("all-filtered", rows.length > 0 && shown === 0);
    const note = group.querySelector(".mg-shown");
    if (!note) return;
    note.hidden = shown === rows.length;
    note.textContent = shown ? `${shown} shown` : "all filtered out";
  });
}

document.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-mark-colour]");
  if (!chip) return;
  event.preventDefault();
  // `all` and `none` act on **this** group, which is the group the button is
  // in. Reaching across to the others would make two adjacent controls that
  // look identical do different amounts of work.
  const group = chip.closest(".mark-group");
  const every = Array.from(group.querySelectorAll("[data-mark-colour]"))
    .map((node) => node.dataset.markColour)
    .filter((colour) => colour && colour !== "*");
  const hidden = hiddenColours();
  if (chip.dataset.markColour === "*") every.forEach((key) => hidden.delete(key));
  else if (chip.dataset.markColour === "") every.forEach((key) => hidden.add(key));
  else if (hidden.has(chip.dataset.markColour)) hidden.delete(chip.dataset.markColour);
  else hidden.add(chip.dataset.markColour);
  rememberColours(hidden);
  paintMarkFilter();
});

paintMarkFilter();

/* Long marks fold to a few lines, with a way out.

   A highlight can run to a paragraph, and with the notes panel above them now,
   four of those push the brief off the screen -- which is the panel this
   column was rearranged to put first. Clamping in CSS and adding the button
   from here means it appears **only where the text actually overflows**: a
   fixed character count would put "more" after a sentence that was already
   complete, and truncate one that was not. */
const CLAMP_SLACK = 2; // px; sub-pixel line heights round the wrong way

function offerToExpand(root = document) {
  root.querySelectorAll(".clamp").forEach((node) => {
    if (node.dataset.clamped) return;
    node.dataset.clamped = "1";
    if (node.scrollHeight <= node.clientHeight + CLAMP_SLACK) {
      // It fits. Drop the clamp rather than leave a class that would start
      // truncating if the column were ever dragged narrower.
      node.classList.remove("clamp");
      return;
    }
    const more = el("button", "clamp-more", "more");
    more.type = "button";
    more.addEventListener("click", () => {
      more.textContent = node.classList.toggle("clamp") ? "more" : "less";
    });
    node.after(more);
  });
}

offerToExpand();

/* How much room the two panes actually have: from where the column starts to
   the top of the footer.

   The stylesheet can only guess at this -- `100vh` minus the two bars minus a
   number for the unit's head -- and the head is not a fixed height: a unit
   with a gist has an extra line, and the chips wrap on a narrow window. Guessed
   low the marks list stops short and leaves a band of nothing that reads as a
   footer; guessed high it runs underneath the real one. Measured, it is right
   on every unit.

   Set per item because only the visible one has a box to measure. */
function fitColumn(item) {
  const column = item && item.querySelector(".beside");
  if (!column) return;
  const footer = document.querySelector("footer");
  const floor = footer ? footer.getBoundingClientRect().top : window.innerHeight;
  const top = column.getBoundingClientRect().top;
  column.style.setProperty("--beside-max", `${Math.max(200, Math.round(floor - top - 8))}px`);
}

document.addEventListener("deck:shown", (event) => fitColumn(event.detail));
window.addEventListener("resize", () => fitColumn(currentOf(deck)));
fitColumn(currentOf(deck));

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
  document: "the whole document, scrolling",
};

/* A key that does nothing and says nothing reads as a broken keyboard, which
   is the sentence `currentOf` was written for. This source has no crops --
   a `tex` source has geometry for nothing -- so there is no picture to cycle. */
function cyclePdfView() {
  const item = currentOf(deck);
  if (!item) return;
  const now = item.dataset.pdfMode || "crop";
  showPdfView(item, PDF_VIEWS[(PDF_VIEWS.indexOf(now) + 1) % PDF_VIEWS.length]);
}

async function showPdfView(item, view) {
  const figure = item.querySelector(".crop");
  const img = item.querySelector("[data-crop]");
  if (!figure || !img) return;
  if (!item.dataset.cropSrc) item.dataset.cropSrc = img.getAttribute("src");
  /* `pdfMode`, not `pdfView`: the buttons are found by `[data-pdf-view]`, and
     writing that attribute onto the item made `closest` match the whole unit
     -- so clicking anywhere on the picture cycled the view. */
  item.dataset.pdfMode = view;
  item.classList.toggle("whole-page", view === "page");
  item.classList.toggle("whole-document", view === "document");
  item.querySelectorAll("[data-pdf-view]").forEach((button) => {
    button.classList.toggle("on", button.dataset.pdfView === view);
  });
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
  if (!showById(id)) toast(`${id} is not in this view. Try the state filter`);
}

window.addEventListener("hashchange", followHash);
followHash();

/* The context badge is a button. `c` does the same thing, and a number you
   are deciding about should be reachable with the pointer you are already
   using to read with. */
document.addEventListener("click", (event) => {
  const pick = event.target.closest("button[data-pdf-view]");
  if (pick) {
    event.preventDefault();
    const item = pick.closest(".item");
    if (item) showPdfView(item, pick.dataset.pdfView);
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
    /* Verbatim, like the key that cycles these: one of the sizes is the word
       `chapter`, `Number("chapter")` is NaN, and a NaN posted as JSON is
       `null` -- which the server reads as "no size given" and takes the
       override *off*. Clicking chapter cleared the setting instead. */
    if (item) setContext(item, step.dataset.contextStep);
    return;
  }
  const grant = event.target.closest("[data-web-set]");
  if (grant) {
    event.preventDefault();
    const item = grant.closest(".item");
    // Clicking the one already in force clears the override rather than
    // re-asserting it, the same way every other filter here toggles.
    const wanted = grant.dataset.webSet === "1";
    if (item) setWeb(item, grant.classList.contains("on") ? null : wanted);
    return;
  }
  const link = event.target.closest("[data-goto]");
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
  if (deck.items.some((item) => item.dataset.id === link.dataset.goto)) {
    event.preventDefault();
    location.hash = encodeURIComponent(link.dataset.goto);
  }
});

/* Every key that writes goes through `oneAtATime`; the ones that only move or
   toggle a panel do not. Guarding at the key rather than inside the write
   functions is deliberate: `Q` is a state change *and* a note, and a guard one
   level down would have the second half wait for the first forever. */
bindKeys({
  queue: () => oneAtATime(() => setState("queued")),
  "queue-with-brief": () => oneAtATime(queueWithABrief),
  /* No prompt. A skip is the commonest action in triage, and stopping to type
     a word turned one keystroke into a dialogue. `skip-with-reason` still
     asks, for the times the reason is worth recording. */
  skip: () => oneAtATime(() => setState("skipped")),
  "skip-with-reason": () =>
    oneAtATime(async () => {
      const reason = await ask("skip reason (optional)");
      if (reason === null) return;
      await setState("skipped", reason);
    }),
  "accept-suggestion": () => oneAtATime(() => decideOnSuggestion("accept")),
  "dismiss-suggestion": () => oneAtATime(() => decideOnSuggestion("dismiss")),
  "back-to-new": () => oneAtATime(() => setState("new")),
  undo: () => oneAtATime(undo),
  "note-claude": () => oneAtATime(() => annotate("claude")),
  "note-me": () => oneAtATime(() => annotate("me")),
  "context-size": () => oneAtATime(cycleContext),
  "web-lookups": () => oneAtATime(cycleWeb),
  "pdf-view": cyclePdfView,
  next: () => deck.nextPending(),
  prev: () => deck.prev(),
  "next-alt": () => deck.nextPending(),
  "prev-alt": () => deck.prev(),
  filters: toggleFilters,
  projects: openGallery,
  guide: cycleGuide,
});
