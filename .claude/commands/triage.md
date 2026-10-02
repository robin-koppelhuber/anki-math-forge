---
description: Work the open @claude annotations
argument-hint: [claude|me|cards|units|<status>|<state>|--project NAME]
---

Resolve open annotations on cards and units.

Arguments: `$ARGUMENTS` — optional, and any combination of these filters:

- **`claude`** or **`me`** — whose notes. `claude` is the work there is to do;
  `me` is a review of what is parked for the human, and changes nothing.
- **`cards`** or **`units`** — one side of the pipeline only.
- a card status (`draft`, `approved`, `rejected`) or a unit state (`new`,
  `queued`, `skipped`, `carded`) — only things at that stage.
- **`--project NAME`** — one book's notes. Worth reaching for whenever the repo
  has more than one: conventions are per source, so a list that hops between
  two books makes you reload the setting between every item.
- nothing — everything open.

**`/triage claude` is the common case**: every note you can actually act on,
and nothing else. Without it the list is mostly `@me` items you are only
allowed to report, and the work queues behind the reading.

The stage filter matters for a different reason. An annotation on an
`approved` card is blocking a sync *now*; one on a `new` unit is a note to
whoever cards it, some day. Working them in one undifferentiated list means
the urgent ones queue behind the speculative ones.

1. Pull anything waiting in Anki first, or the list is already stale --
   a comment typed during review is a `@claude` note only once it is
   imported:

   ```
   uv run forge anki pull
   ```

2. Read the list. `todo` filters on `--audience`, `--kind` and `--status`,
   which are the same three fields `--json` carries. Pass the filter to the
   command; do not match on the prose:

   ```
   uv run forge todo --audience claude --json
   uv run forge todo --audience claude --kind unit --status queued
   uv run forge todo --audience claude --project <name>
   ```

   Then say in your report how many you left untouched, so the rest are not
   silently forgotten.

3. For each item, do what it asks. The common ones:

   - *"this looks wrong"* — check the card against its source crop (the
     review view links to it; `units --id <unit> --json` gives the path) and
     fix it, or explain why it is right.
   - *"add a proof sketch"* — see the **card-writing** skill for when a proof
     earns its place.
   - *"split this into two cards"* — `forge cards new` for the second, and
     add both uids to the unit's `uids`.
   - *"this duplicates 4b2e1c"* — compare, keep the better one, delete the
     other file. Say which you kept and why.

4. **Resolving means settling the `@claude` line** in `## notes` and making
   the edit. Both, in the same pass. A line left addressed keeps blocking
   sync.

   **Replace it with what you did**, on the same line, unaddressed:

   ```
   resolved: <what was asked> — <what you did about it>
   ```

   **Replace the `@claude` line, and nothing else.** A card that has been
   round twice carries two `resolved:` lines, oldest first. They are a
   history of what was asked of this card and what came back, and a second
   round folded into the first loses that there were two. Rewrite an earlier
   line only when what it claims has stopped being true, which happens when a
   later round reverts it: then say so in the new line rather than quietly
   correcting the old one.

   `resolved:` is not an address, so the line is a record rather than work and
   does not hold the card out of sync. Keep the question in it: "fixed" is the
   thing nobody can act on six weeks later, and the person reading this will
   be trying to tell whether the point they made was taken. Say what changed,
   in the card's own terms, and say so plainly when the answer is that nothing
   needed changing: *"the sign was right; the condition it needs was missing
   and is now in `## conditions`"*, not *"checked"*.

   **One line, and read it back as a list entry before you keep it.** These
   stack up in `todo` and in the review rail, where each is one row among
   many and the reader is scanning for which point was taken. Two clauses
   carry that: what was asked, what changed. Around twenty words.

   The argument that got you there is not part of it. A counterexample, a
   numeric check, a page you chased down: those belong in the card, in
   `## prose` or `## conditions` where a reviewer meets them, or nowhere. A
   `resolved:` line that has to be unfolded to be read has taken the place of
   the list it sits in.

   | | |
   |---|---|
   | write | `resolved: asked what $H_\theta$ is — the Hessian in $\theta$, now glossed in ## prose` |
   | not | `resolved: asked what $H_\theta$ is — the Hessian in $\theta$, the matrix of second derivatives, which the book itself uses unglossed where it first appears and again in the Laplace approximation chapter, so ## prose now names it and draws out that the Fisher information is therefore the average curvature of the negative log-likelihood` |

   There is no notes archive to append to, and none to create. The
   `resolved:` line is the record. Most of `cards/` is not in git (see
   `.gitignore`), so for most cards the file is the only history there is,
   and a line you delete outright is gone.

   The edit changes `content_hash`, so an approved card drops back to `draft`
   and re-enters review automatically. That is the intended behaviour — do not
   re-approve anything yourself.

   If the card is already in Anki and the edit changed what it asks, set
   `relearn:` as the **card-writing** skill describes. A note that came from
   Anki review usually means the card is in Anki.

5. Confirm nothing is left dangling:

   ```
   uv run forge check
   uv run forge todo
   ```

For a **unit** annotation, act on it and then clear it:

```
uv run forge units clear-notes <unit-id>
uv run forge units set <unit-id> --state queued   # or --state skipped --reason ...
```

`clear-notes` clears `@claude` only, which is its default. `--audience all`
also deletes the `@me` decision parked on the same unit, so reach for it only
when that is what you mean.

That is the unit equivalent of deleting the `@claude` line from a card's
`## notes`; without it the annotation sits in `todo` for ever.

Report each annotation and what you did about it. If one is ambiguous, leave
it open and say so — guessing is worse than asking.

## Addressed annotations

`@claude ...` is a request for you: act on it, then delete the line (on a
card) or clear it with `units clear-notes <id> --audience claude` (on a
unit).

`@me ...` is a decision only the human can make — a question parked where it
will be found again. **Report those; do not act on them and do not clear
them.** `forge todo --json` carries an `audience` field for exactly this
split, and `forge todo` marks them `(me)`.

Either kind blocks `anki push`, because either kind means the thing is not
finished.
