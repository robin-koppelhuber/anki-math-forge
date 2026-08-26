---
description: Fill in conditions, proof, prose and tags on stub cards
---

Add the optional sections to stubs that are still bare.

**This is not the command for working my annotations** — that is `/triage`.
And run this *before* approval: augmenting an approved card changes its
`content_hash`, which correctly drops it back to draft and means re-reviewing
it. Augment first, review once.

Load the book before you start, for the same reason `/extract-cards` does:

```
uv run anki-forge source-text matrix-cookbook
```

The notation section tells you what the symbols mean; the surrounding section
tells you which conditions are actually load-bearing.

1. Find them — cards with only `## front` and `## back`:

   ```
   uv run anki-forge check --json
   ```

   ...and read the card files under `cards/` directly. Work on
   `status: draft` cards only; never touch an approved one (editing it would
   silently reset it to draft, which is correct but rude to do in bulk).

2. For each, consult the **card-writing** skill and add what earns its place:

   - `## conditions` — when the identity is false without them. One line.
     Say the layout convention whenever the shape depends on it.
   - `## proof` — only when short and load-bearing (2–4 lines).
   - `## prose` — one sentence of intuition, or nothing.
   - `tags` — mechanical and reusable: topic, operation, structure.
   - `verify: true` plus a `## verify` snippet where a stray transpose or sign
     would survive proofreading.

3. Verify what opted in, then check:

   ```
   uv run anki-forge verify
   uv run anki-forge check
   ```

Do not rewrite `front` or `back` unless they are wrong — if they are, say so
in your report rather than quietly reshaping the card. Leave everything
`draft`; approval is a human at `anki-forge serve`.
