---
description: Work the open @claude annotations
---

Resolve open annotations on cards and units.

1. Read the list:

   ```
   uv run anki-forge todo --json
   ```

2. For each item, do what it asks. The common ones:

   - *"this looks wrong"* — check the card against its source crop (the
     review view links to it; `units --id <unit> --json` gives the path) and
     fix it, or explain why it is right.
   - *"add a proof sketch"* — see the **card-writing** skill for when a proof
     earns its place.
   - *"split this into two cards"* — `anki-forge new` for the second, and
     add both uids to the unit's `uids`.
   - *"this duplicates 4b2e1c"* — compare, keep the better one, delete the
     other file. Say which you kept and why.

3. **Resolving means deleting the `@claude` line** from `## notes` and making
   the edit. Both, in the same pass. A note left behind keeps blocking sync.

   The edit changes `content_hash`, so an approved card drops back to `draft`
   and re-enters review automatically. That is the intended behaviour — do not
   re-approve anything yourself.

4. Confirm nothing is left dangling:

   ```
   uv run anki-forge check
   uv run anki-forge todo
   ```

For a **unit** annotation, act on it and then clear it:

```
uv run anki-forge units --id <unit-id> --resolve-notes
uv run anki-forge units --id <unit-id> --set-state queued     # or skipped --reason ...
```

That is the unit equivalent of deleting the `@claude` line from a card's
`## notes`; without it the annotation sits in `todo` for ever.

Report each annotation and what you did about it. If one is ambiguous, leave
it open and say so — guessing is worse than asking.

## Addressed annotations

`@claude ...` is a request for you: act on it, then delete the line (on a
card) or clear it with `--resolve-notes --audience claude` (on a unit).

`@me ...` is a decision only the human can make — a question parked where it
will be found again. **Report those; do not act on them and do not clear
them.** `anki-forge todo --json` carries an `audience` field for exactly this
split, and `anki-forge todo` marks them `(me)`.

Either kind blocks `sync`, because either kind means the thing is not
finished.
