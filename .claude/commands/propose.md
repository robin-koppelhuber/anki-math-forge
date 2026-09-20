---
description: Propose units for a subject, where there is no document to segment
argument-hint: --project NAME "what you want cards for"
---

Turn a subject into **units**, for a project with no book behind it.

Arguments: `$ARGUMENTS`

- **`--project NAME`** — which project. **Ask if it is not given.** Start one
  with `forge project <name> --title '...' --deck '...'`.
- **the subject**, in your own words: "how to use the standard containers",
  "when a `vector` invalidates its iterators".

## Why this exists

`extract` and `zotero` find units inside a document. A project on a subject
has no document, so nothing can be segmented and there is nothing to triage.
This pass writes the units instead.

It is a **frontend**, and it owes exactly what the other two owe (ROADMAP.md
10): a stable id, whatever locator it has, something scannable, and
`state: new`. **It does not write cards.** The moment a proposal carries a
front and a back, triage has become review and the unit stage has no job
left. A proposal is a subject, not a draft.

## Steps

1. **Read the project first.** `forge context` needs a unit, so read the
   files directly: `projects/<name>/conventions.md` for what is ambient
   here, and `references.md` for the shelf. If `conventions.md` is missing,
   **stop and ask.** With no book to read it off, that file decides what the
   deck does rather than describing it, and proposing forty units before it
   exists means forty units written against nothing.

2. **Outline what the subject contains, before proposing anything.** One
   short line each, no detail, in `projects/<name>/topics.md` under a
   heading naming the subject. If the ask is not recorded there yet,
   `forge topic --project <name> '<subject>' --ask '<what you want>'`
   writes the heading; the entries you add by editing the file.

   This step is the whole defence against stopping halfway. A single pass
   asked for forty proposals writes twelve and stops, because it is
   satisficing under length pressure and nothing tells it that twelve is
   short. Forty one-line entries is cheap, so the failure does not happen
   here.

   **Do not aim for a number.** "Produce forty" produces padding, and
   padding survives triage because none of it is clearly wrong. Twelve is
   sometimes the honest answer. An outline of sixty says the subject is too
   big and wants splitting.

3. **Stop and show the outline.** The human edits it: deleting padding and
   adding the obvious gap costs three lines here and forty edits later. Wait
   for them.

4. **Fill it in, one `forge units --add` per entry:**

   ```
   forge units --project <name> --add '<a few words: the id comes from this>' \
     --gist '<what a card from it would be about>' \
     --preview '<a sample too small to run, enough to see the point>' \
     --lang cpp \
     --ref '<the page you read>' --tag '<subject>'
   ```

   Over a long outline, **dispatch subagents a chunk at a time**, the way
   `/transcribe` does per section. A short list is easy to finish, so the
   pressure that made step 2 necessary never builds.

   The slug is the id, so re-running adds only what is new and a subject
   already there is left alone. That is what makes this safe to run twice.

5. **Report** how many were proposed, which outline entries have no unit
   yet, and anything you could not find a reference for. `/setup` in the app
   shows the same thing as a count and a list, so the human can see what is
   still open without re-reading the file.

## What goes in each field

**`--gist`** is what a card from this would be about, in a few words. It is a
reading and not an instruction: nothing downstream consumes it, so it can be
wrong at the cost of a second look.

**`--preview`** is the smallest thing that shows what is meant. For code, a
snippet too small to run. It is a hint under the same rule `tex_auto`
follows: whoever writes the card reads the references, not this.

**`--ref`** is where you actually read it. Cite the page you used, not the
one you would have used. With no authoritative source, these references are
the only thing keeping a card off the model's memory alone, and
`forge context` hands them to the writer under a heading saying they are
checked against rather than copied from.

**`--tag`** is what the unit is about, and tags cross each other:
`invalidation` covers units under several subjects. Yours to invent.

## What not to do

- **Do not write cards.** Not even good ones. `/extract-cards` does that,
  after a human has queued the unit.
- **Do not invent a reference.** A unit with no `--ref` is honest; one
  citing a page you did not open is worse than none.
- **Do not propose what the project already has.** Check
  `forge units --project <name> --state all --json` first.
- **Do not write `conventions.md` yourself.** Same rule as a convention
  proposed by a mark: record it as an `@me` note and let the human decide.
  A convention governs every card written here afterwards and nothing
  reviews it.
