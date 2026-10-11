---
description: Turn queued units into stub cards
argument-hint: [--project NAME] [--section SECTION] [--augment]
---

Write stub cards for every queued unit. Stubs only — augmentation is `/augment`.

Arguments: `$ARGUMENTS`

- **`--project NAME`** — which project. **Ask if it is not given and the repo
  has more than one.** Nothing here defaults to a source, so leaving it out
  writes cards for every queued unit in the repo — including books you were
  not looking at.
- **`--section SECTION`** — narrow to one section, as `locator.section`
  spells it. Optional; without it, the whole project's queue.
- **`--augment`** — once the stubs are written and checked, run the
  `/augment` pass in the same run (step 5): over the new stubs and over
  every older draft in the same scope that `/augment` would pick up. With
  an empty queue it only augments. Without it this stops at stubs, which is
  the default because a stub is cheap to look over: one you would reject
  costs no second reading of its page.

Pass both straight through to the `forge` commands below. The units view
writes this line for you from whatever you had filtered to.

## Dispatch one writer per section

Writing a card reads the page the unit was printed on: one `forge context`
block is about eleven thousand characters, so a queue of five hundred units is
more context than any one session has. The answer is `/transcribe`'s: **one
`card-writer` agent per section, dispatched in parallel**, each with a slice
nothing else touches.

1. See what is waiting, and group it:

   ```
   uv run --no-sync forge units --project <PROJECT> --state queued --json
   ```

   Group by `locator.section`. Aim at a few dozen units per agent: enough that
   dispatch overhead is worth it, few enough that one agent's context holds the
   section and the book's front matter beside it. Split anything much larger;
   combine neighbouring small ones. A source whose ids carry no section leaves
   `locator.section` empty, so group by page instead.

2. Dispatch one `card-writer` per section, in parallel — several `Agent` calls
   in one message:

   > Write stub cards for every queued unit in section `<SECTION>` of
   > `<SOURCE>`. Your work list is
   > `uv run --no-sync forge units --project <PROJECT> --section <SECTION> --state queued --json`.
   > Read each unit's `@claude` notes and do what they say: that is the brief
   > you were left at triage. Follow your instructions exactly — check the
   > mathematics yourself, write stubs only, approve nothing, and propose a
   > skip rather than taking one.

   **A section is the unit of work because it is the unit of collision.** Two
   agents pointed at one queue would card the same unit twice; two agents on
   different sections cannot, and the writes themselves are already safe,
   since `forge cards new` marks the unit inside `Ledger.edit` and that
   takes the ledger's lock.

3. When they report back, verify mechanically rather than reading the
   summaries:

   ```
   uv run --no-sync forge check
   uv run --no-sync forge units --project <PROJECT> --state queued --json   # what is left
   ```

   A section that comes back with units still queued and no reason given is a
   section to re-dispatch, not to accept.

4. Report: how many cards per section, every unit deliberately not carded with
   its reason, and anything an agent flagged as systematically wrong — a
   mangled text layer, a run of fragments, a notation the front matter never
   defines.

5. **With `--augment`**, augment every draft in scope that the pass has not
   been over, the stubs this run wrote and any older ones alike, plus any
   draft with an open `@claude` note. The scope is the stub writing's: the
   project, and the section when one was given.

   ```
   uv run --no-sync forge cards --project <PROJECT> [--section <SECTION>] --status draft --json
   ```

   Take the cards with `"augmented": false` or `"open_claude"` above zero.
   Then follow `.claude/commands/augment.md` from its step 1's batching on,
   with this list in place of its search: one `augmenter` per batch of about
   twenty, grouped by section, each card in exactly one batch, then its
   verification and its report. A card the writers flagged as wrong is left
   out and named.

## Rules

A stub at this stage: `front`, `back` and a `gist`, plus a condition only where
the card is false without it. With `--augment`, step 5 adds the rest. Every stub is `status: draft` and stays that way
— nothing here approves anything; that is the human at `forge serve`. Report
how many stubs you wrote, and list every unit you deliberately did not card,
with the reason.
