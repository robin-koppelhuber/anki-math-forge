---
description: Read unit crops and record their LaTeX, via transcriber subagents
argument-hint: [--project NAME] [--section SECTION|--all] [haiku|sonnet|opus]
---

Fill in `tex_auto` for units that have a crop but no transcription, by
dispatching **transcriber** subagents. This runs *before* triage: you cannot
decide whether a unit is worth carding if all you can see is a picture
(DESIGN.md §4).

Arguments: `$ARGUMENTS`

- **`--project NAME`** — which source. **Ask if it is not given and the repo
  has more than one**: none of the commands below defaults to a source, so
  leaving it out silently means *every* source in the repo.
- **`--section SECTION`** — one section, as `locator.section` spells it, or
  `--all` for the whole source. Default: ask.
- a bare word — model override: `haiku`, `sonnet`, or `opus`. Default: the
  transcriber agent's own setting (`sonnet`).

Pass `--source` and `--section` straight through to every `forge` command
here; they are the same flags. The units view writes this line for you with
whatever you had filtered to, which is where the quoting comes from.

**Nothing to do here for a source whose units come from marks** (a document
someone highlighted in Zotero). A mark already carries the text it covers;
there is no picture of an equation to read. Say so and stop.

## Why a subagent

A crop is an image, and images are the most expensive thing this session can
read. A source of any size will crowd out everything else if the main agent
reads them all. Each subagent takes one section, keeps its images to itself,
and reports back a summary. Sections are independent, so dispatch them **in
parallel** — several `Agent` calls in one message.

## Steps

1. See what needs doing:

   ```
   uv run forge units --project <PROJECT> --state new --json
   uv run forge audit
   ```

   Units with `transcription: "none"` or `"failed"` need reading. Units with
   `tex_source` came from real LaTeX and need nothing. A unit carrying `marks`
   came from someone reading rather than from segmentation — leave it alone.

2. Work out the sections and their sizes:

   ```
   uv run forge units --project <PROJECT> --state all --json
   ```

   Group by `locator.section`. Aim at a few dozen units per subagent: enough
   that dispatch overhead is worth it, few enough that one agent's context
   holds the section. Split anything much larger; combine neighbouring small
   ones. A source that numbers no sections leaves `locator.section` empty —
   group by page instead.

3. Dispatch one `transcriber` subagent per section, in parallel, passing the
   section in the prompt and `model` only if `$2` was given:

   > Transcribe section `<SECTION>` of `<SOURCE>`. Render the crops with
   > `uv run forge crops --project <PROJECT> --section <SECTION> --untranscribed --json`,
   > read each one, and record it with
   > `uv run forge units --id <id> --tex-auto '<latex>'`.
   > Follow your instructions exactly: transcribe what is printed, annotate
   > anything unreadable or suspicious, never guess.

   Crops land under the configured `work_dir` (`.forge/crops/<section>/`),
   one directory per section, so parallel agents cannot collide and
   nothing needs cleaning up by hand. Scratch files go under
   `.forge/scratch/<section>/`.

4. When they report back, verify mechanically rather than trusting the
   summaries:

   ```
   uv run forge audit
   uv run forge units --project <PROJECT> --state new --json   # count "ok"
   ```

5. Report: how many transcribed per section, how many the KaTeX gate refused,
   every unit that got annotated, and anything an agent flagged as
   systematically wrong.

## Model choice

`sonnet` is the default because this is precision vision work over hundreds of
one-shot reads with no recovery, and a transcription that is plausible but
wrong is the failure that survives — it looks fine in the units view.
`haiku` is defensible for a re-run or a cheap first pass; `opus` for a section
that came back messy. The crop stays authoritative either way, which is what
keeps a bad transcription cheap: the units view shows crop and transcription
side by side, so the human sees the disagreement.

Crops are **working files** under `.forge/`, which is gitignored. The ledger
keeps geometry, not pictures, so the whole directory is safe to delete at any
time.

## Then

Run `/classify`. It reads the transcriptions this pass produced, which is a
better signal than the PDF text layer it falls back to.
