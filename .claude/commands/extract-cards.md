---
description: Turn queued units into stub cards
---

Write stub cards for every queued unit. Stubs only — augmentation is `/augment`.

## Load the context first

A card is only as good as the context you had when you wrote it. Before
writing anything:

```
uv run anki-forge source-text matrix-cookbook
```

That is the whole book's text layer — about 26k tokens, so read all of it, not
a snippet. Two parts matter most:

- **Notation and Nomenclature** (near the front). It defines what `A⁺`,
  `A^{1/2}`, `(A)ᵢⱼ`, `Tr(A)` and the rest actually mean in this book. Without
  it you will guess at exactly the symbols that make a card wrong.
- **The section around each unit.** Equations 49–58 are all determinant
  derivatives; knowing that is what stops you writing ten near-duplicates.

The mathematics in that text layer is mangled — it is context for *deciding*,
never a transcription. The crop is the authority for what an equation says.

## Then work the queue

1. Read the work list:

   ```
   uv run anki-forge units --state queued --json
   ```

2. **Read each unit's `notes` and do what they say.** They are the instruction
   you were left at triage time — "two cards, one per layout convention", "the
   transcription is wrong, read the crop", "merge with eq 50". This is the
   greenlight gate: the human queued this unit *and told you how to card it*.

   When you have acted on them, clear them:

   ```
   uv run anki-forge units --id <unit-id> --resolve-notes
   ```

   If a note is ambiguous, **leave it open, skip that unit, and say why** in
   your report. Guessing is worse than asking.

3. Decide what card(s) the unit should produce. Use the **card-writing** skill
   for what makes a good front and back. Usually one card; occasionally zero
   (annotate the unit and move on) or two.

   The **crop is authoritative**. `tex_auto` is a transcription that may be
   wrong — where the two disagree, read the crop. If a unit's transcription is
   `failed` and you cannot read the crop, annotate rather than guess.

4. Write each stub. This writes the file and marks the unit `carded`:

   ```
   uv run anki-forge new --unit <unit-id> \
     --front '$\frac{\partial}{\partial X}\log\det X$' \
     --back '$X^{-\top}$' \
     --tag matrix-calculus --tag derivatives
   ```

5. Check the result:

   ```
   uv run anki-forge check
   ```

## Rules

`front` and `back` only at this stage. Every stub is `status: draft` and stays
that way — nothing here approves anything; that is the human at
`anki-forge serve`. Report how many stubs you wrote, and list every unit you
deliberately did not card, with the reason.
