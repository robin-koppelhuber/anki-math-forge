---
description: Propose which units are not worth carding, by looking at the crops
argument-hint: [section|--all] [haiku|sonnet|opus]
---

Look at unit crops and **propose** which are not worth carding, so triage is
not fifty-seven presses of `s` before the first real decision.

**Run `/transcribe` first.** `classify` now reads a unit's transcription in
preference to the PDF text layer, because a transcription is what somebody saw
on the crop while the text layer is whatever pdfTeX happened to emit -- mangled
or absent for anything unusual. Classifying an untranscribed book still works;
it is just working from the worse of the two sources.

Arguments: `$ARGUMENTS` — `$1` a section (`2.8`) or `--all`; `$2` an optional
model override.

**Nothing here changes a unit's state.** Every finding is a suggestion the
human accepts (`a`) or throws away (`d`) in the triage view. That is the
contract, and it is not negotiable: this pass is a model looking at a picture,
and a guess that silently moved units would be indistinguishable from a bug.

## Steps

1. Run the mechanical pass first — it is free, instant, and its two rules are
   exact where they apply:

   ```
   uv run anki-forge classify
   ```

   It proposes `front-matter` and `no-relation` skips. It never touches a
   numbered equation, and it will not overwrite a suggestion that already
   exists.

2. See what it left unremarked:

   ```
   uv run anki-forge units --state new --json
   uv run anki-forge units --state new --suggested --json   # already proposed
   ```

3. Dispatch **classifier** subagents over the sections that still have
   unremarked units, in parallel, one per section. Crops go under the
   configured `work_dir` (`.forge/`) by default -- no `--out`, no temp
   directory to invent or forget to delete. Pass `model` only if `$2` was given.

4. Verify by counting rather than by reading summaries:

   ```
   uv run anki-forge units --state new --suggested --json
   uv run anki-forge units --state all --json    # states must be unchanged
   ```

   If any unit's *state* changed, something is wrong: this pass proposes only.

5. Report per section: how many proposed, under which reasons, and every
   pattern an agent noticed. A pattern — "all of §2.8 is rows of one big
   matrix" — is a segmentation finding worth more than the suggestions
   themselves, and belongs in ROADMAP.md rather than in thirty skips.

## Then

Review them yourself:

```
uv run anki-forge serve
```

The **suggested** chip filters to units with an open proposal. Each shows what
was proposed and why. `a` accepts, `d` dismisses, and pressing `q` or `s`
yourself clears it too — you overruled it.
