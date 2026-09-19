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
   uv run forge feedback
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
   - *"split this into two cards"* — `forge new` for the second, and
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

   `resolved:` is not an address, so the line is a record rather than work and
   does not hold the card out of sync. Keep the question in it: "fixed" is the
   thing nobody can act on six weeks later, and the person reading this will
   be trying to tell whether the point they made was taken. Say what changed,
   in the card's own terms, and say so plainly when the answer is that nothing
   needed changing: *"the sign was right; the condition it needs was missing
   and is now in `## conditions`"*, not *"checked"*.

   There is no notes archive to append to, and none to create. Deleting a
   note used to be unrecoverable, which is the whole reason one existed;
   `cards/` is tracked now, so a card's own history holds every line it has
   ever carried. For any other source an archive would be gitignored
   alongside the ledger it was archiving, which is no protection at all.

   The edit changes `content_hash`, so an approved card drops back to `draft`
   and re-enters review automatically. That is the intended behaviour — do not
   re-approve anything yourself.

5. Confirm nothing is left dangling:

   ```
   uv run forge check
   uv run forge todo
   ```

For a **unit** annotation, act on it and then clear it:

```
uv run forge units --id <unit-id> --resolve-notes
uv run forge units --id <unit-id> --set-state queued     # or skipped --reason ...
```

`--resolve-notes` clears `@claude` only, which is its default. `--audience all`
also deletes the `@me` decision parked on the same unit, so reach for it only
when that is what you mean.

That is the unit equivalent of deleting the `@claude` line from a card's
`## notes`; without it the annotation sits in `todo` for ever.

Report each annotation and what you did about it. If one is ambiguous, leave
it open and say so — guessing is worse than asking.

## Addressed annotations

`@claude ...` is a request for you: act on it, then delete the line (on a
card) or clear it with `--resolve-notes --audience claude` (on a unit).

`@me ...` is a decision only the human can make — a question parked where it
will be found again. **Report those; do not act on them and do not clear
them.** `forge todo --json` carries an `audience` field for exactly this
split, and `forge todo` marks them `(me)`.

Either kind blocks `sync`, because either kind means the thing is not
finished.
