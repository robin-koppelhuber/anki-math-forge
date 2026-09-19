---
description: Propose which units are not worth carding, by looking at the crops
argument-hint: [--project NAME] [--section SECTION|--all] [haiku|sonnet|opus]
---

Look at unit crops and **propose** which are not worth carding, so triage is
not fifty-seven presses of `s` before the first real decision.

**Run `/transcribe` first.** `classify` now reads a unit's transcription in
preference to the PDF text layer, because a transcription is what somebody saw
on the crop, while the text layer is whatever the document's producer happened
to emit -- mangled or absent for anything unusual, and missing entirely from a
scanned source. Classifying an untranscribed book still works;
it is just working from the worse of the two sources.

Arguments: `$ARGUMENTS` — `--project NAME` which project (**ask if it is not
given and the repo has more than one**: nothing below defaults to a source, so
leaving it out means every source in the repo); `--section SECTION` or `--all`;
a bare word as a model override. Pass `--source` and `--section` through to
every `forge` command here.

**Nothing to classify for a source whose units come from marks.** The two
rules below are about a page of formulas -- a fragment of a display equation, a
row of a notation table -- and a paragraph somebody highlighted is neither.
Say so and stop.

**Nothing here changes a unit's state.** Every finding is a suggestion the
human accepts (`a`) or throws away (`d`) in the triage view. That is the
contract, and it is not negotiable: this pass is a model looking at a picture,
and a guess that silently moved units would be indistinguishable from a bug.

## Steps

1. Run the mechanical pass first — it is free, instant, and its two rules are
   exact where they apply:

   ```
   uv run forge classify --project <PROJECT>
   ```

   It proposes `front-matter` and `no-relation` skips. It never touches a
   numbered equation, and it will not overwrite a suggestion that already
   exists.

2. See what it left unremarked:

   ```
   uv run forge units --project <PROJECT> --state new --json
   uv run forge units --project <PROJECT> --state new --suggested --json
   ```

3. Dispatch **classifier** subagents over the sections that still have
   unremarked units, in parallel, one per section. Crops go under the
   configured `work_dir` (`.forge/`) by default -- no `--out`, no temp
   directory to invent or forget to delete. Pass `model` only if `$2` was given.

4. Verify by counting rather than by reading summaries:

   ```
   uv run forge units --project <PROJECT> --state new --suggested --json
   uv run forge units --project <PROJECT> --state all --json   # states unchanged
   ```

   If any unit's *state* changed, something is wrong: this pass proposes only.

5. Report per section: how many proposed, under which reasons, and every
   pattern an agent noticed. A pattern — "every unit in this section is one
   row of a single larger structure" — is a segmentation finding worth more
   than the suggestions themselves, and belongs in ROADMAP.md rather than in
   thirty skips.

## Then

Review them yourself:

```
uv run forge serve
```

The **suggested** chip filters to units with an open proposal. Each shows what
was proposed and why. `a` accepts, `d` dismisses, and pressing `q` or `s`
yourself clears it too — you overruled it.
