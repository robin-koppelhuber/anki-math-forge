/* The setup stage: a list on the left, a panel on the right.

   Every panel is in the page already. This shows one and hides the rest,
   which is why the view still reads as a plain document with the script
   doing nothing.

   **Two selections, not one.** The ask you are working through and the panel
   you are reading are different things: an ask with four works behind it is
   the case the panel exists for, and clicking through them must not drop the
   ask. So the fragment carries both (`#topic:slug/source:key`) and the ask
   stays lit while the right-hand side changes.

   `post` comes from `app.js`, which loads first and is a classic script, so
   it is simply in scope -- the same way every other view script uses it. */
const panel = document.getElementById("setup-panel");
const detail = document.getElementById("setup-detail");

if (panel && detail) {
  /* The class, not the attribute. A chip inside a panel carries `data-pane`
     too, since that is how it selects, and a bare attribute selector made
     every one a pane to be hidden: "reads: X, Y" was an empty row. */
  const panes = [...detail.querySelectorAll(".setup-pane[data-pane]")];
  const buttons = [...panel.querySelectorAll("[data-pane]")];
  const names = new Set(panes.map((pane) => pane.dataset.pane));
  const sources = [...document.querySelectorAll("#source-list > li")];
  const filters = [...document.querySelectorAll("#source-filter [data-kind]")];
  const sync = document.getElementById("topic-sync");
  const nothing = document.getElementById("source-none");
  const shown = document.getElementById("source-count");
  const lists = [...document.querySelectorAll("[data-runs]")];
  const KIND = "anki-forge.setup.kind";
  const SYNC = "anki-forge.setup.sync";
  const RUNS = "anki-forge.setup.runs";

  function recall(key, fallback) {
    try {
      const saved = localStorage.getItem(key);
      return saved === null ? fallback : saved;
    } catch (err) {
      return fallback;
    }
  }

  function keep(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (err) {
      /* Private windows refuse storage. The filter works, it just forgets. */
    }
  }

  /* Which ask is selected, and what the right-hand side is showing. */
  let topic = "";
  let kind = recall(KIND, "");
  /* On by default: picking an ask in order to read its works is the flow
     this panel was asked for, and a filter you have to switch on every time
     is one you stop using. */
  let follow = recall(SYNC, "1") !== "0";

  /* `topic:a/source:b`, either half optional. The ask comes first because it
     is the wider selection: dropping the tail leaves a link to the ask. */
  function read(hash) {
    const parts = decodeURIComponent(hash.replace(/^#/, "")).split("/");
    const first = parts[0] || "";
    if (first.startsWith("topic:")) {
      return { topic: first.slice(6), pane: parts[1] || first };
    }
    return { topic: "", pane: first };
  }

  function write(push) {
    const url = new URL(location.href);
    const at = current();
    url.hash = at === "project" ? "" : at;
    if (push) history.pushState(null, "", url);
    else history.replaceState(null, "", url);
  }

  function current() {
    const pane = panes.find((p) => !p.hidden);
    const at = pane ? pane.dataset.pane : "project";
    if (topic && at !== `topic:${topic}`) return `topic:${topic}/${at}`;
    return at;
  }

  function show(name, { push = true } = {}) {
    const wanted = names.has(name) ? name : "project";
    if (wanted.startsWith("topic:")) topic = wanted.slice(6);
    /* The panes that belong to no ask clear it; a source does not, which is
       the whole point. */
    else if (!wanted.startsWith("source:")) topic = "";
    for (const pane of panes) pane.hidden = pane.dataset.pane !== wanted;
    for (const button of buttons) {
      button.classList.toggle(
        "on",
        button.dataset.pane === wanted || button.dataset.pane === `topic:${topic}`,
      );
    }
    /* What to run, for what is now selected. An ask and a work want
       different passes, and the column is only useful if it keeps up. */
    for (const list of lists) list.hidden = list.dataset.runs !== wanted;
    carryTopic(wanted);
    /* Back to the top: the panes are different lengths, and arriving at a
       short one scrolled halfway down reads as an empty panel. */
    detail.scrollTop = 0;
    paintSources();
    /* KaTeX over whatever just appeared. A pane is only rendered once:
       the flag is on the element, so switching back and forth does not
       re-parse a page of conventions every time. */
    const pane = panes.find((p) => !p.hidden);
    if (pane && !pane.dataset.rendered) {
      renderMath(pane);
      pane.dataset.rendered = "1";
    }
    write(push);
  }

  /* Reading a work while an ask is selected is two filters, not one, and
     the links in the panel are rendered with only their own half: the
     server does not know which ask you picked. Both filters compose over
     there, so this adds the missing one to every link that carries a scope.

     Only for a work's panel. An ask's own links already say the ask, and
     the project's mean the whole project on purpose. */
  function carryTopic(pane) {
    const showing = panes.find((p) => !p.hidden);
    if (!showing) return;
    const wanted = topic && pane.startsWith("source:") ? topic : "";
    for (const link of showing.querySelectorAll("[href]")) {
      const url = new URL(link.href, location.href);
      if (!url.searchParams.has("document") && !url.searchParams.has("topic")) continue;
      if (wanted) url.searchParams.set("topic", wanted);
      else if (pane.startsWith("source:")) url.searchParams.delete("topic");
      link.href = url.toString();
    }
  }

  /* The two filters over the works list: what a work is, and whether it has
     anything to do with the ask above. They compose, and the count in the
     heading says what is left. */
  function paintSources() {
    let count = 0;
    const following = follow && topic;
    for (const row of sources) {
      const mine = !following || (row.dataset.topics || "").split(" ").includes(topic);
      const right = !kind || row.dataset.kind === kind;
      row.hidden = !(mine && right);
      if (!row.hidden) count += 1;
    }
    if (shown) shown.textContent = count === sources.length ? sources.length : `${count}/${sources.length}`;
    if (nothing) {
      nothing.hidden = count > 0 || !sources.length;
      nothing.textContent = following
        ? "This topic has drawn on none of them yet."
        : "No source matches that.";
    }
    for (const button of filters) button.classList.toggle("on", button.dataset.kind === kind);
    if (sync) {
      sync.classList.toggle("on", Boolean(following));
      /* Off rather than hidden when no ask is selected: a control that
         disappears is one you have to rediscover, and this one says what it
         would do by sitting there greyed out. */
      sync.disabled = !topic;
    }
  }

  for (const button of buttons) {
    button.addEventListener("click", () => show(button.dataset.pane));
  }
  /* The chips inside a panel select too: "reads: X, Y" on an ask is the
     other way into the same works. */
  detail.addEventListener("click", (event) => {
    const chip = event.target.closest(".work-chip");
    if (chip) show(chip.dataset.pane);
  });
  for (const button of filters) {
    button.addEventListener("click", () => {
      kind = button.dataset.kind || "";
      keep(KIND, kind);
      paintSources();
    });
  }
  if (sync) {
    sync.addEventListener("click", () => {
      follow = !follow;
      keep(SYNC, follow ? "1" : "0");
      paintSources();
    });
  }
  /* The column you stop needing: what to run next is a question you ask
     twice a session, and the other two are what you are reading. */
  function foldRuns(away) {
    document.getElementById("setup").classList.toggle("runs-off", away);
    const tab = document.getElementById("runs-tab");
    if (tab) tab.hidden = !away;
    keep(RUNS, away ? "1" : "0");
  }

  const fold = document.getElementById("runs-fold");
  if (fold) fold.addEventListener("click", () => foldRuns(true));
  const tab = document.getElementById("runs-tab");
  if (tab) tab.addEventListener("click", () => foldRuns(false));
  if (recall(RUNS, "0") === "1") foldRuns(true);

  /* The picker, from the foot of the panel: starting another project is not
     something this one holds, so the list does not carry a row for it. */
  const toPicker = document.getElementById("project-pick-foot");
  if (toPicker) {
    toPicker.addEventListener("click", () => {
      const open = document.getElementById("project-pick");
      if (open) open.click();
    });
  }

  window.addEventListener("hashchange", () => {
    const at = read(location.hash);
    topic = at.topic;
    show(at.pane, { push: false });
  });
  const start = read(location.hash);
  topic = start.topic;
  show(start.pane || "project", { push: false });
}

/* The one write worth the name: recording a new ask.

   It appends a heading to `topics.md`, which is exactly what you would do in
   an editor, and the page reloads afterwards rather than patching itself:
   the outline it draws is a join between that file and the ledger, and
   re-deriving it in the browser would be a second implementation of the
   thing being shown. */
const form = document.getElementById("add-topic");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("topic-name").value.trim();
    if (!name) return;
    const ask = document.getElementById("topic-ask").value;
    const project = new URL(location.href).searchParams.get("project") || "";
    const answer = await post(`/api/topics/${encodeURIComponent(project)}`, { name, ask });
    /* Land on the topic just recorded rather than back where you started:
       the next thing you do with an ask is look at what it covers. */
    location.hash = answer && answer.slug ? `topic:${answer.slug}` : "";
    location.reload();
  });
}

/* Narrowing the list of works the repo knows. Past a handful it is
   something to hunt through rather than read, which is the same reason the
   rail's tag box exists. */
(function wireKnownSearch() {
  const search = document.getElementById("known-search");
  const list = document.getElementById("known-list");
  if (!search || !list) return;
  const empty = document.getElementById("known-none");
  search.addEventListener("input", () => {
    const wanted = search.value.trim().toLowerCase();
    let shown = 0;
    for (const row of list.children) {
      const hit = !wanted || (row.dataset.find || "").toLowerCase().includes(wanted);
      row.hidden = !hit;
      if (hit) shown += 1;
    }
    if (empty) empty.hidden = shown > 0;
  });
})();

/* Adding a work the repo already reads somewhere else. A `[[sources]]`
   table appended to this project's TOML, which is the edit you would make by
   hand, and nothing is copied: both projects read the same item. */
for (const button of document.querySelectorAll("[data-add-source]")) {
  button.addEventListener("click", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    /* Always as a reference: the item key and the files stay where they
       are, and deciding to segment a document is a command you type. */
    await post(`/api/sources/${encodeURIComponent(project)}`, {
      key: button.dataset.addSource,
    });
    /* Reloaded rather than patched: the counts, the filters and the panel it
       just gained are all derived from the file that changed. */
    location.hash = `source:${button.dataset.addSource}`;
    location.reload();
  });
}

/* Saving a work's marking scheme: what each mark means here, and which of
   them become units. A file edit, and the writer keeps every comment in the
   TOML it edits. */
for (const form of document.querySelectorAll("[data-scheme]")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const project = new URL(location.href).searchParams.get("project") || "";
    const meanings = {};
    const from = [];
    for (const row of form.querySelectorAll("tr[data-pair]")) {
      const pair = row.dataset.pair;
      const means = row.querySelector(".sc-means").value.trim();
      if (means) meanings[pair] = means;
      const unit = row.querySelector(".sc-unit");
      if (unit && unit.checked) from.push(pair);
    }
    const body = { meanings };
    /* Absent, not empty, for a work nothing is extracted from: a saved
       empty list is an answer nobody gave. */
    /* Only where there are marks to read. A work with no Zotero item behind
     it has no kinds and no colours, so the table has no column and an
     empty list would be an answer nobody gave. */
  if (form.dataset.marks === "1") body.units_from = from;
    await post(
      `/api/scheme/${encodeURIComponent(project)}/${encodeURIComponent(form.dataset.scheme)}`,
      body,
    );
    /* Reloaded: the mark grid in the rail, the legend on the other side and
       every count of "makes a unit" are derived from what just changed. */
    location.reload();
  });
}

/* Settling a shelf line. Dropping one is the same shape as resolving an
   annotation: the way to say you do not want a reference is to delete the
   line, and the app does by hand exactly what you would do in an editor.
   Keeping one takes the `[ ]` off, which is the other half of the same
   edit. */
for (const button of document.querySelectorAll("[data-drop-reference]")) {
  button.addEventListener("click", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    await post(`/api/references/${encodeURIComponent(project)}`, {
      line: button.dataset.dropReference,
    });
    /* Two places reject a line, and they cannot both just drop a row. On
       the project's shelf the button sits in one and taking it out is the
       whole change. On a proposal's own panel there is no row to take out:
       the panel, its entry in the list of sources and the counts beside it
       all have to go, and they are drawn from the file that just changed.

       This used to call `.remove()` on a `.shelf-line` that was not there,
       which threw, so the line went from the file and nothing moved on
       screen until you reloaded by hand. */
    const row = button.closest(".shelf-line");
    if (row) {
      row.remove();
      return;
    }
    location.hash = "project";
    location.reload();
  });
}

for (const button of document.querySelectorAll("[data-take-reference]")) {
  button.addEventListener("click", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    const answer = await post(`/api/references/${encodeURIComponent(project)}/accept`, {
      line: button.dataset.takeReference,
    });
    /* On the source it just became. Accepting writes a `[[sources]]` table,
       so the next thing you do is say what the thing is for, and that is
       its own panel. Reloaded rather than patched: the list, the counts and
       the panel are all drawn from the file that changed. */
    if (answer && answer.key) location.hash = `source:${answer.key}`;
    location.reload();
  });
}

/* Removing a project.

   The button stays disabled until the typed name matches. A project is a
   folder, a ledger and a pile of cards, and the mistake worth making
   impossible is deleting the wrong one because two of them start with the
   same word: typing the name is the one confirmation that cannot be clicked
   through by muscle memory.

   `DELETE`, not `post`: the shared helper sends a body and a scope, and
   this route takes neither. It refuses a project that holds cards and says
   so in the toast; the override is a flag you type in a terminal. */
(function wireDropProject() {
  const form = document.getElementById("drop-project");
  if (!form) return;
  const typed = document.getElementById("drop-name");
  const go = document.getElementById("drop-go");
  const wanted = form.dataset.project || "";
  /* Capitals are not the confirmation. The label is a small caps heading,
     so it showed `DOOMED` for a project called `doomed`, and typing back
     what it showed did not match. The label quotes the name verbatim now,
     and this forgives the case either way. */
  const matches = () => typed.value.trim().toLowerCase() === wanted.toLowerCase();

  typed.addEventListener("input", () => {
    go.disabled = !matches();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!matches()) return;
    go.disabled = true;
    const response = await fetch(`/api/projects/${encodeURIComponent(wanted)}`, {
      method: "DELETE",
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (e) {
      payload = {};
    }
    if (!response.ok) {
      toast(payload.detail || `error ${response.status}`, "bad");
      go.disabled = false;
      return;
    }
    /* To the shelf: the page you are on is about a project that no longer
       exists, and reloading it would land on whichever one resolves first. */
    location.href = "/projects";
  });
})();


/* What a work is for, in one line. Saved on its own rather than with the
   marking scheme below it: a scheme is a table you edit while looking at
   marks, and this is a sentence you write once when the source arrives. */
for (const form of document.querySelectorAll(".source-note")) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const project = new URL(location.href).searchParams.get("project") || "";
    const work = form.dataset.note;
    const value = form.querySelector("input").value;
    await post(
      `/api/sources/${encodeURIComponent(project)}/${encodeURIComponent(work)}/note`,
      { note: value },
    );
    toast("saved");
  });
}


/* A page to check cards against, typed in rather than proposed. The same
   writer as the accept button behind it, so both end as the same table,
   and the toast says when it widened a source you already read instead of
   adding one beside it. */
(function wireAddWeb() {
  const form = document.getElementById("add-web");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const project = new URL(location.href).searchParams.get("project") || "";
    const url = document.getElementById("web-url").value.trim();
    const title = document.getElementById("web-title").value.trim();
    if (!url && !title) return;
    const answer = await post(`/api/references/${encodeURIComponent(project)}/web`, {
      url,
      title,
      note: document.getElementById("web-note").value,
    });
    if (!answer || !answer.key) return;
    if (answer.merged) toast("added to a source you already read");
    location.hash = `source:${answer.key}`;
    location.reload();
  });
})();

/* Removing a source. Typed confirmation, like the project's, and for the
   same reason: the mistake worth making impossible is dropping the wrong
   one because two of them start with the same word. The server refuses
   while cards stand on it and says which command will do it anyway. */
for (const form of document.querySelectorAll("[data-drop-source]")) {
  const wanted = form.dataset.dropSource;
  const typed = form.querySelector("input");
  const go = form.querySelector("button");
  const matches = () => typed.value.trim().toLowerCase() === wanted.toLowerCase();

  typed.addEventListener("input", () => {
    go.disabled = !matches();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!matches()) return;
    go.disabled = true;
    const project = new URL(location.href).searchParams.get("project") || "";
    const response = await fetch(
      `/api/sources/${encodeURIComponent(project)}/${encodeURIComponent(wanted)}`,
      { method: "DELETE" },
    );
    let payload = {};
    try {
      payload = await response.json();
    } catch (e) {
      payload = {};
    }
    if (!response.ok) {
      toast(payload.detail || `error ${response.status}`, "bad");
      go.disabled = false;
      return;
    }
    /* Back to the project: the panel you are on is about a source that no
       longer exists. */
    location.hash = "project";
    location.reload();
  });
}


/* Whether units are extracted from a work. Reloaded rather than patched:
   the list beside it says `authoritative` or `reference`, the sentence at
   the head of the panel changes, and the panel gains or loses the passes
   that only apply to a document more units may come out of. The units it
   already holds do not move. */
for (const form of document.querySelectorAll("[data-extract]")) {
  const box = form.querySelector("input");
  box.addEventListener("change", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    const work = form.dataset.extract;
    const answer = await post(
      `/api/sources/${encodeURIComponent(project)}/${encodeURIComponent(work)}/extract`,
      { extract: box.checked },
    );
    if (!answer || !answer.ok) {
      box.checked = !box.checked;
      return;
    }
    location.hash = `source:${work}`;
    location.reload();
  });
}



/* Whether a reference is handed to a card writer. No reload: nothing else
   on the page reads it, unlike `extract`, which moves units. */
for (const form of document.querySelectorAll("[data-offer]")) {
  const box = form.querySelector("input");
  box.addEventListener("change", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    const work = form.dataset.offer;
    const answer = await post(
      `/api/sources/${encodeURIComponent(project)}/${encodeURIComponent(work)}/offer`,
      { offer: box.checked },
    );
    if (!answer || !answer.ok) {
      box.checked = !box.checked;
      return;
    }
    toast(box.checked ? "handed over with every unit" : "kept off the shelf");
  });
}


/* Which asks read a source. Written onto the *work*, because that is
   where the relation lives in the file (`topics` in its `[[sources]]`
   table), and read back as the union with what its units already say.

   The list holds the whole set, so a box only adds or removes its own
   slug and the others stay whatever they were. */
for (const list of document.querySelectorAll("[data-reads-for-topic]")) {
  const slug = list.dataset.readsForTopic;
  for (const box of list.querySelectorAll("[data-reads]")) {
    box.addEventListener("change", async () => {
      const project = new URL(location.href).searchParams.get("project") || "";
      const work = box.dataset.reads;
      /* Every ask this work serves, plus or minus this one. The write goes
         to the *work*: `topics` lives in its `[[sources]]` table, and the
         other asks it serves are not on this pane to be read off.

         Read off every box for this work rather than off this one. One
         pane per ask means one box per ask, each rendered with its own
         copy of the set, so ticking a work under two asks in a row posted
         the copy made before the first write and silently unsaid it. */
      const twins = [...document.querySelectorAll(`[data-reads="${CSS.escape(work)}"]`)];
      const current = new Set(
        twins.flatMap((t) => (t.dataset.topics || "").split(" ")).filter(Boolean),
      );
      if (box.checked) current.add(slug);
      else current.delete(slug);
      const answer = await post(
        `/api/sources/${encodeURIComponent(project)}/${encodeURIComponent(work)}/topics`,
        { topics: [...current] },
      );
      if (!answer || !answer.ok) {
        box.checked = !box.checked;
        return;
      }
      /* Reloaded, like the extract switch: the source pane's "used by"
         mirror, the works list beside it and every other pane's copy of
         this set are all derived from it, and patching three derived
         things by hand is how one of them goes stale. */
      toast(box.checked ? "used for this topic" : "no longer used for this topic");
      location.hash = `topic:${slug}`;
      location.reload();
    });
  }
}
