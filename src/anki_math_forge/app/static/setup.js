/* The setup stage. One write: recording a new ask.

   Everything else on this page is a view over files. This appends a heading
   to `topics.md`, which is exactly what you would do in an editor, and the
   page reloads afterwards rather than patching itself: the outline it draws
   is a join between that file and the ledger, and re-deriving it in the
   browser would be a second implementation of the thing being shown.

   `post` comes from `app.js`, which loads first and is a classic script, so
   it is simply in scope -- the same way every other view script uses it. */
const form = document.getElementById("add-topic");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("topic-name").value.trim();
    if (!name) return;
    const ask = document.getElementById("topic-ask").value;
    const project = new URL(location.href).searchParams.get("project") || "";
    await post(`/api/topics/${encodeURIComponent(project)}`, { name, ask });
    location.reload();
  });
}

/* Dropping a line from the shelf. Same shape as resolving an annotation:
   the way to say you do not want a reference is to delete the line, and the
   app does by hand exactly what you would do in an editor. */
for (const button of document.querySelectorAll("[data-drop-reference]")) {
  button.addEventListener("click", async () => {
    const project = new URL(location.href).searchParams.get("project") || "";
    await post(`/api/references/${encodeURIComponent(project)}`, {
      line: button.dataset.dropReference,
    });
    button.closest(".shelf-line").remove();
  });
}

/* Starting a project. The picker is filled from the config, which the app
   re-reads per request, so the new one is there the moment this returns. */
const startForm = document.getElementById("start-project");
if (startForm) {
  startForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("project-name").value.trim();
    if (!name) return;
    const answer = await post("/api/projects", {
      name,
      deck: document.getElementById("project-deck").value,
    });
    if (answer && answer.project) location.href = `/setup?project=${answer.project}`;
  });
}
