---
description: Propose reference material for a project, as pending shelf lines
argument-hint: --project NAME [what the references should cover]
---

Propose places a card from this project can be **checked against**.

Arguments: `$ARGUMENTS`

- **`--project NAME`** — which project. **Ask if it is not given.**
- optionally, what to cover: a topic name, or a subject in your own words.
  Without it, cover what the project is for as a whole.

## Why this exists

A project with no book behind it has nothing authoritative. Its cards stand
on what a model remembers, and a card that is confidently wrong looks exactly
like one that is right. The shelf is what changes that: material a card
writer checks against before writing.

This pass proposes; it accepts nothing. Every line it writes is **pending**
until a human takes it, because which sources you trust is not a judgement
worth delegating, and an accepted list nobody read is worse than a short one
somebody did.

What happens to a line you write: it shows up under **sources** on the
setup stage, marked `proposed`. Taking it there writes a `[[sources]]`
table and the line leaves this file; rejecting deletes the line. The `##`
heading it sat under becomes the ask that source serves.

## What a good proposal is

- **Specific enough to open.** "cppreference, the container library
  overview" is a place to look. "the C++ documentation" is not.
- **Something you can check a claim against**: a reference, a standard, a
  well-known text, the library's own docs. Not a tutorial or a blog post,
  unless it is the canonical one and you say why.
- **Six or fewer.** A shelf nobody reads is the same as no shelf. Propose the
  ones you would actually open.
- **One line per site, per ask.** Three pages of cppreference are one
  reference read in three places, so propose it once, at the address they
  share, and say which parts matter in the "what it is for" half. Taking
  the line merges it anyway if you do not, but the line you wrote is what
  somebody reads before deciding.

  Two *different* asks reading two parts of one site are two lines, under
  their own headings. The part is what a card is checked against, not the
  domain, and a note about threads is no help to whoever is writing about
  containers.
- **Not a document to extract from.** Something worth segmenting is a
  `[[sources]]` table in `project.toml`, and that is a decision with crop
  settings and a marking scheme behind it. Say so in your summary and leave
  it to the human.

## Steps

1. **Read the project first**, the way `/propose` does:
   `projects/<name>/project.toml` for what it declares,
   `projects/<name>/conventions.md` for what is ambient,
   `projects/<name>/topics.md` for what it means to cover, and
   `projects/<name>/references.md` for what is already there.

2. **Check what the repo already reads**: `uv run forge sources --json`. A
   work another project already has is one to reuse rather than propose
   again, and the setup stage can add it in a click. Name it in your summary
   instead of writing a shelf line for it.

3. **Look them up** if the project allows it. `forge context <unit> --json`
   reports `web`; with no unit to hand, `[projects.<name>] web` in
   `forge.toml` is the same answer. **With lookups off, propose only what you
   can name without checking**, and say which ones you were unsure of.

4. **Append them** to `projects/<name>/references.md`, one per line, each
   with the checkbox that marks it pending. Three parts, in this order:
   **a name, the address in brackets, and what it is for**, because that is
   what accepting the line writes into the `[[sources]]` table.

   ```
   ## cpp std container

   - [ ] cppreference, the container library overview (https://en.cppreference.com/w/cpp/container), for the per-container complexity and iterator-invalidation tables
   - [ ] The C++ working draft, [container.requirements] (https://eel.is/c++draft/container.requirements), authoritative wherever cppreference paraphrases
   - [ ] Josuttis, The C++ Standard Library, 2nd edition
   ```

   **Under a `##` heading naming the ask**, spelled as it is in
   `topics.md`, when you are proposing for one. That heading is how the
   shelf knows which ask a line serves, and it is what keeps two asks
   reading one site as two sources. Reuse a heading that is already there
   rather than writing a second one for the same ask. Proposing for the
   project as a whole, leave them under no heading.

   The address is optional and the third line shows why: a book you own has
   a name and no URL. Everything before the address is the name, everything
   after it is what it is for, so do not put a URL in the middle of a title.

   Create the file with a `# References` heading if it is not there. **Never
   rewrite an existing line**, and never take a checkbox off: accepting is
   the human's move, on the setup stage or in the editor.

5. **Report**: how many you proposed, which you were unsure of and why,
   anything already in the repo that should be reused instead, and anything
   that looked worth extracting from rather than checking against. Say that
   they are waiting under **sources** on the setup stage, marked
   `proposed`, and that taking one there makes it a source with a panel of
   its own.
