/* The find palette: a dialog with a search box over a list that narrows as you
   type. Enter takes the highlighted row (the first until you move), the arrows
   move it, a click takes any, Escape leaves.

   One component for every place a list has to be searched. The graph uses it
   to choose a card to put on the canvas, and the review page to jump to a
   card, and what each one does with a row is the only thing that differs, so
   that is all a caller supplies:

     finder.open({
       title, placeholder,
       rows(query)     the rows for what is typed: an array, or a promise of
                       `{rows, ...}`. A row is `{name, where}` and anything else
                       the caller wants back in `pick`.
       pick(row, ev)   what taking a row does. It closes the palette, or
                       `finder.refresh()`es it to stay open.
       count(rows, o)  the small line under the title.   (optional)
       empty(query,o)  what to say when nothing matches.  (optional)
       foot            a line of keys under the list.     (optional)
       delay           ms to wait after a keystroke, for rows that are fetched.
       shiftEnter(q)   Shift+Enter: what to do with the whole query. (optional)
       onClose()       (optional)
     })

   Markup is `_finder.html`. A newer keystroke owns the list: an answer to an
   older one that arrives late is dropped. */

const finder = (() => {
  const dialog = document.getElementById("finder");
  if (!dialog) return null;
  const search = document.getElementById("finder-search");
  const list = document.getElementById("finder-list");
  const empty = document.getElementById("finder-empty");
  const count = document.getElementById("finder-count");
  const foot = document.getElementById("finder-foot");
  let cfg = null;
  let rows = [];
  let seq = 0;
  let timer = 0;
  let active = 0;

  function mark() {
    [...list.children].forEach((el, i) => el.classList.toggle("active", i === active));
    const el = list.children[active];
    if (el) el.scrollIntoView({ block: "nearest" });
  }

  function paint(answer) {
    list.textContent = "";
    rows.slice(0, cfg.limit || 200).forEach((row, i) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "find-row";
      const name = document.createElement("span");
      name.className = `find-name${row.name ? "" : " unnamed"}`;
      name.textContent = row.name || cfg.unnamed || "no caption yet";
      const where = document.createElement("span");
      where.className = "find-where";
      where.textContent = row.where || "";
      el.append(name, where);
      el.addEventListener("click", (event) => cfg.pick(row, event));
      el.addEventListener("mouseenter", () => {
        active = i;
        mark();
      });
      list.appendChild(el);
    });
    active = Math.min(active, Math.max(rows.length - 1, 0));
    mark();
    empty.hidden = rows.length > 0;
    empty.textContent = cfg.empty ? cfg.empty(search.value, answer) : "no match";
    count.textContent = cfg.count ? cfg.count(rows, answer) : String(rows.length);
  }

  async function load() {
    if (!cfg) return;
    const mine = ++seq;
    const found = await cfg.rows(search.value);
    if (mine !== seq || !cfg) return; // a newer keystroke owns the list
    const answer = Array.isArray(found) ? { rows: found } : found;
    rows = answer.rows;
    active = 0;
    paint(answer);
  }

  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(load, (cfg && cfg.delay) || 0);
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const last = Math.min(rows.length, (cfg && cfg.limit) || 200) - 1;
      active = Math.max(0, Math.min(last, active + (event.key === "ArrowDown" ? 1 : -1)));
      mark();
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (event.shiftKey && cfg.shiftEnter) cfg.shiftEnter(search.value);
      else if (rows[active]) cfg.pick(rows[active], event);
    }
  });
  document.getElementById("finder-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    const done = cfg;
    cfg = null;
    seq += 1; // an answer still on its way has nowhere to land
    if (done && done.onClose) done.onClose();
  });

  return {
    isOpen: () => dialog.open,
    close: () => dialog.close(),
    /* The same list again, for what changed under it: a card was added, so it
       is no longer one to add. The query stays. */
    refresh: () => load(),
    /* Cleared every time it opens. It kept whatever you last typed, so
       reopening showed a list filtered by a word you had forgotten about and
       read as most of the deck having vanished. */
    open(config) {
      cfg = config;
      document.getElementById("finder-title").textContent = cfg.title;
      search.placeholder = cfg.placeholder || "";
      search.value = "";
      foot.textContent = cfg.foot || "";
      foot.hidden = !cfg.foot;
      rows = [];
      active = 0;
      if (!dialog.open) dialog.showModal();
      search.focus();
      return load();
    },
  };
})();
