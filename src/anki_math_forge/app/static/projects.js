/* The shelf. Two things the server did not do: narrowing by name as you
   type, and the form that starts a project.

   The filters are links, like every other list in this app, so a narrowed
   shelf is something you can send. The search is not: it is a text match
   over what is already on screen, and a round trip per keystroke is not
   what finding a name by typing three letters should cost.

   `post` comes from `app.js`, which loads first and is a classic script. */
(function wireShelfSearch() {
  const search = document.getElementById("shelf-search");
  const grid = document.getElementById("shelf-grid");
  if (!search || !grid) return;
  const empty = document.getElementById("shelf-none");
  search.addEventListener("input", () => {
    const wanted = search.value.trim().toLowerCase();
    let shown = 0;
    for (const card of grid.children) {
      const hit = !wanted || (card.dataset.find || "").toLowerCase().includes(wanted);
      card.hidden = !hit;
      if (hit) shown += 1;
    }
    if (empty) empty.hidden = shown > 0;
  });
  search.focus();
})();
