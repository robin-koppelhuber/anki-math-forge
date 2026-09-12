---
description: Turn queued units into stub cards
argument-hint: [--source NAME] [--section SECTION]
---

Write stub cards for every queued unit. Stubs only — augmentation is `/augment`.

Arguments: `$ARGUMENTS`

- **`--source NAME`** — which source. **Ask if it is not given and the repo
  has more than one.** Nothing here defaults to a source, so leaving it out
  writes cards for every queued unit in the repo — including books you were
  not looking at.
- **`--section SECTION`** — narrow to one section, as `locator.section`
  spells it. Optional; without it, the whole source's queue.

Pass both straight through to the `forge` commands below. The units view
writes this line for you from whatever you had filtered to.

## Load the context first

A card is only as good as the context you had when you wrote it. Before
writing anything:

```
uv run forge source-text <source>
```

That is the source's whole text layer. Read it rather than a snippet if it
fits; where it does not, read these two parts, which are the ones that matter:

- **The front matter**, before the numbered body starts. This is where a
  source defines its symbols, and it is the one place that says what its
  notation means. Skipping it means guessing at exactly the symbols that make
  a card wrong. (`forge context <unit>` gives you the page a unit came
  from; the front matter you have to go and read.)
- **The neighbourhood of each unit.** A run of results on one theme is the
  usual shape of a reference work, and knowing you are inside one is what
  stops you writing ten near-duplicate cards.

The mathematics in that text layer is mangled — it is context for *deciding*,
never a transcription. The crop is the authority for what a unit says.

## Then work the queue

1. Read the work list:

   ```
   uv run forge units --source <SOURCE> --state queued --json
   ```

2. **Read each unit's `notes` and do what they say.** They are the instruction
   you were left at triage time — "two cards, one per layout convention", "the
   transcription is wrong, read the crop", "merge with the unit above". This is
   greenlight gate: the human queued this unit *and told you how to card it*.

   Annotations are **addressed**. `@claude ...` is work for you. `@me ...` is a
   decision the human parked for themselves — read it for context, **never act
   on it, and never clear it**.

   When you have acted on the ones addressed to you, clear only those:

   ```
   uv run forge units --id <unit-id> --resolve-notes --audience claude
   ```

   `--audience claude` is the default; `--audience all` also deletes the
   `@me` decision parked on the same unit, so reach for it only when that is
   what you mean.

   If a note is ambiguous, **leave it open, skip that unit, and say why** in
   your report. Guessing is worse than asking.

3. **Read the page, then check the mathematics yourself.**

   ```
   uv run forge context <unit-id>
   ```

   That prints the page the equation was printed on, prose and all. Conditions
   are usually printed *around* an identity rather than inside it, so the crop
   cannot carry them and the page usually can.

   Then do the part no tool does: **work out whether the identity is actually
   true as stated.** A derivative of an inverse needs the matrix to be
   invertible whether or not the page says so. A trace identity may need the
   product to be square. If the mathematics requires a condition, it goes in
   `## conditions` — the page not mentioning it is not evidence that it does
   not hold.

   Two directions to be wrong in, and they are not symmetric. Omitting a real
   condition makes a card that teaches something false. Adding one the source
   does not have makes a card that disagrees with the book you are learning.
   When the source states a condition, use its wording. When you believe one
   is needed and the source is silent, state it and say so in `## notes`.

   If you cannot settle it, **leave the card in draft and say why in
   `## notes`**.

3. **Decide the boundary before the content.** `context` lists every unit on
   the page in reading order. A display equation the segmenter cut into three
   is three units and one identity — card it whole:

   ```
   uv run forge new --unit <a> --unit <b> --unit <c> --front '...' --back '...'
   ```

   All three are marked carded and point at the same card. The reverse also
   happens: one unit stating two independent facts is two cards, each citing
   that unit.

   Neither is the common case. Most units are one card. Merge when the pieces
   are meaningless apart, split when a single card would have two answers.

3. Decide what card(s) the unit should produce. Use the **card-writing** skill
   for what makes a good front and back. Usually one card; occasionally zero
   (annotate the unit and move on) or two.

   The **crop is authoritative**. `tex_auto` is a transcription that may be
   wrong — where the two disagree, read the crop. If a unit's transcription is
   `failed` and you cannot read the crop, annotate rather than guess.

4. Write each stub. This writes the file and marks the unit `carded`:

   ```
   uv run forge new --unit <unit-id> \
     --front '$\frac{\partial}{\partial X}\log\det X$' \
     --back '$X^{-\top}$' \
     --tag matrix-calculus --tag derivatives
   ```

5. Check the result:

   ```
   uv run forge check
   ```

## Rules

`front` and `back` only at this stage. Every stub is `status: draft` and stays
that way — nothing here approves anything; that is the human at
`forge serve`. Report how many stubs you wrote, and list every unit you
deliberately did not card, with the reason.
