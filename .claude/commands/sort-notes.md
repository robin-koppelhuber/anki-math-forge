---
description: Sort a pile of notes into a project, as new units and parked decisions
argument-hint: --project NAME <file, or the notes pasted after it>
---

Take notes written at a whole project and put each piece where it belongs.

Arguments: `$ARGUMENTS`

- **`--project NAME`**: which project. **Ask if it is not given.**
- **the notes**: a file path, or text pasted after the arguments. Anything:
  a list, a paragraph, half sentences, things you meant to look up.

## What this pass does, and what it does not

Each piece of the pile becomes one of three things:

- **a new unit**, when it is about something the project has no card or
  unit for;
- **an `@me` note on a card**, when it is about a card that exists;
- **an `@me` note on a unit**, when it is about a unit not yet carded.

It proposes and a human decides, like every other pass here. **It does not
edit a card's content, and it does not write cards.** A note saying a card
is wrong becomes a parked decision on that card, which you read in review
and turn into an `@claude` brief, an edit, or nothing. A mode that writes
the changes directly is not built.

## Steps

1. **Read the project.** `projects/<name>/conventions.md`,
   `projects/<name>/topics.md`, and what it already holds:

   ```
   uv run forge cards --project <name> --json
   uv run forge units --project <name> --state all --json
   ```

   A card is found by its `gist`, its front and its tags; read the file
   when the gist is not enough to tell.

2. **Split the pile into pieces, one idea each.** Keep the words they were
   written in: they are the evidence for whatever you do with them, and the
   person reading the result wants to recognise their own note.

3. **Place each piece.**

   - **About a card that exists**: append one line to the card's
     `## notes`, opening `@me`, quoting the note and naming what it would
     change: `@me your note: "the bound needs independence, not just
     zero mean"; the conditions say only zero mean`. Leave everything else
     in the file as it is. An `@me` line is outside `content_hash`, so the
     card keeps its approval; it is held out of `anki push` until the note
     is settled, which is the point.
   - **About a unit not yet carded**:

     ```
     uv run forge units note <unit-id> '<the note, and what it bears on>' --audience me
     ```

   - **About something new**: a unit, through the same door `/propose`
     uses, with the note itself as the sample:

     ```
     uv run forge units add '<a few words: the id comes from this>' --project <name> \
       --gist '<what a card from it would be about>' \
       --preview '<the note, in its own words>' --tag notes
     ```

     It arrives `new` and waits in triage like any other unit
     (invariant 3). Check the listing from step 1 first: a subject already
     there is a note on that unit, not a second unit.
   - **Not about the deck at all** (a reminder, a to-do, a thought about the
     tool): leave it out, and list it in the report.

   When one piece is about two cards, it is two notes. When you cannot tell
   which card a piece is about, put the `@me` note on the likeliest one and
   say in it which others it might mean.

4. **Report** a table: each piece, in a few words, and where it went (card
   by gist, unit by id, new unit by id, or left out and why). Then the
   counts. `uv run forge todo --audience me --project <name>` lists the
   notes this pass parked.

## What not to do

- **Do not resolve anything.** A note that says a card is wrong may be
  right or may be a misreading; the human decides, in review.
- **Do not use `@claude`.** That addresses the next pass, which would act
  on it without a human having read the note.
- **Do not rewrite the notes into card language.** Paraphrase loses the
  part the person meant, and the unit's sample is read again when the card
  is written.
