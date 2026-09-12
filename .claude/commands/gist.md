---
description: Say in one line what a card from each unit would be about
argument-hint: [--source NAME] [--section SECTION | --all]
---

Fill in the one-line subject for units that have none, by dispatching
**gist-writer** subagents.

Arguments: `$ARGUMENTS`

- **`--source NAME`** — which source. **Ask if it is not given and the repo
  has more than one.**
- **`--section SECTION`**, or **`--all`** for the whole source. Default: ask.

## Why

Triage answers two questions — is this worth a card at all, and roughly what
would the card be about (CLAUDE.md invariant 9). The crop answers the first.
Nothing answers the second, and a human cannot answer it 750 times by
squinting at pictures.

So this pass answers it in advance, in one line per unit, cheaply enough to
run over a whole book. **The value is that it is checkable before anything is
expensive.** A misunderstanding caught at triage costs one keystroke; the same
one caught after `/extract-cards` has written a card costs a rewrite, and
after approval it costs a re-review.

A gist **decides nothing**. Nothing downstream reads it: `/extract-cards`
still works from the crop, the page and the `@claude` brief. It is a window,
not a wire.

## Steps

1. See what needs doing:

   ```
   uv run forge units --source <name> --ungisted --json
   ```

2. Group by `locator.section`. A section of 30–40 units is one subagent; split
   anything much larger. A source with a handful of units needs no subagent at
   all — do it inline.

3. Dispatch one `gist-writer` per section, **in parallel** — several `Agent`
   calls in one message, each with its own temp directory:

   > Gist section <section> of <source>. Render with
   > `uv run --no-sync forge crops --source <source> --section <section> --ungisted --out <temp dir> --json`,
   > read each crop and the `marked`/`comment` fields, and record with
   > `uv run --no-sync forge units --id <id> --gist '<one line>'`.
   > Follow your instructions exactly: a subject, not a summary; no maths; say
   > so when you cannot read it; change no unit's state.

4. Verify mechanically rather than trusting the summaries:

   ```
   uv run forge units --source <name> --ungisted --json     # should be near empty
   uv run forge units --source <name> --state new           # gists print under each id
   ```

5. Report: how many per section, and **every gist that says the unit is
   unreadable, clipped or a fragment** — those are triage decisions made for
   free, and they are what the human should look at first.

## Model choice

`haiku` is the default, and this is the one pass where that is not a
compromise. The job is one short label from a picture that is already in front
of the model, there is no chain of reasoning to get wrong, and **being wrong
is cheap and visible by construction** — the human is looking at the same crop
when they read it. Reach for `sonnet` only if a section comes back with gists
that are obviously not about the right region.

Crops written under `--out` are **working files**. Delete them when the pass
is done.
