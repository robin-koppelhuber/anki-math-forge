---
description: Fill in conditions, proof, prose and tags on stub cards
argument-hint: [--project NAME]
---

Add the optional sections to stubs that are still bare.

Arguments: `$ARGUMENTS` — **`--project NAME`** narrows to one project's drafts.
Worth asking for when the repo has several: conventions are per source, and a
pass that hops between two books is one that has to reload the setting between
every card.

**`/triage` is still the command for working my annotations in general**:
it covers units, approved cards and `@me`, none of which this pass touches.
What this one does is answer the `@claude` notes on the drafts it is already
augmenting, because making the edit and leaving the line behind would block
the card's sync over a request that has been carried out.

Run this *before* approval: augmenting an approved card changes its
`content_hash`, which correctly drops it back to draft and means re-reviewing
it. Augment first, review once.

## Dispatch one augmenter per batch

Augmenting reads the page each card was printed on, the same eleven thousand
characters per card that `/extract-cards` pays, so a draft pile is as long as
a queue was. **One `augmenter` agent per batch, dispatched in parallel.**

1. Find the drafts this pass has not been over, without reading them into
   this session:

   ```
   grep -l "^status: draft" cards/<SOURCE>/*.md | xargs grep -L "^augmented: true"
   ```

   Then the ones somebody has asked about since, whatever their flag says:

   ```
   grep -l "^status: draft" cards/<SOURCE>/*.md | xargs grep -l "^@claude"
   ```

   Take the union. A note written on a card *after* the pass has been over it
   is a request for the pass to go again, which is exactly what withdrawing
   the flag would have said and is one fewer thing to remember. Answering it
   is part of augmenting: make the edit and delete the line, in the same pass.

   **A card is in by default.** The flag records that the pass has been
   over it, so a card that has never seen it carries nothing and is picked up
   without anybody marking it ready. Nothing needs greenlighting; the chip in
   the review view is for the other direction, saying "this one is done" or
   withdrawing that to ask again.

   The review rail counts the first set as **not augmented**, and a card
   carrying `augmented: true` has had the pass. **Running this twice over one
   source is a no-op the second time** unless a note asks otherwise, which is
   the point: nothing here is a second opinion about a card that already got
   one and that nobody has queried.

   A card that wants the pass again is one whose flag somebody withdrew, by
   clicking the chip in the review view or by deleting the line. That is an
   instruction rather than an accident, which is why it is a control and not
   just something an agent writes.

   Group them into batches of roughly twenty. Where the ids carry a section
   (`<source>:<section>:<n>` in each card's `unit:`), group by that instead:
   cards from one section share a page and a run of results on one theme, and
   an agent that sees them together writes fewer near-duplicate `## prose`
   lines than one that meets them scattered.

2. Dispatch one `augmenter` per batch, in parallel — several `Agent` calls in
   one message, each naming the card files it owns:

   > Augment these draft cards in `<SOURCE>`: `<paths>`. Follow your
   > instructions exactly — read the page each one came from, check the
   > mathematics yourself, add only what earns its place, and record as `@me`
   > any condition the source does not state. Drafts only; approve nothing.

   **A card belongs to exactly one agent.** Nothing serialises two writers of
   one card file the way the ledger lock serialises two writers of one unit,
   so overlapping batches are the one way this pass can lose work.

3. When they report back, verify mechanically rather than reading the
   summaries:

   ```
   uv run forge verify --project <PROJECT>
   uv run forge check
   ```

   Then count what is left: every card an agent touched should carry
   `augmented: true` now, so re-running the search from step 1 should return
   nothing. A card still in it is one an agent skipped without saying so.

4. Report: what was added per batch, every condition an agent added that the
   source does not state, every card left alone and why, and any card whose
   `front` or `back` an agent says is wrong.
