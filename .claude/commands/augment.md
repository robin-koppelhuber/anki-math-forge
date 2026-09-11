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
uv run forge context <unit-id>     # per card: the frame it was printed in
uv run forge source-text <source>   # the whole book, when you need it
```

`context` prints the page the equation was printed on. Read it — conditions
are usually printed around an identity, not inside it.

Then **check the mathematics yourself**. The page is evidence, not an oracle:
an identity can require a condition the source never bothered to state. If
the mathematics needs it, it belongs in `## conditions`; if you are adding
something the source does not say, say so in `## notes` so the disagreement
is visible.

1. Find them — cards with only `## front` and `## back`:

   ```
   uv run forge check --json
   ```

   ...and read the card files under `cards/` directly. Work on
   `status: draft` cards only; never touch an approved one (editing it would
   silently reset it to draft, which is correct but rude to do in bulk).

2. For each, consult the **card-writing** skill and add what earns its place:

   - `## conditions` — when the identity is false without them. One line.
     Say the layout convention whenever the shape depends on it. Prefer the
     source's own wording where it gives one; where it gives none and the
     mathematics still needs a condition, state it and note the addition.
   - `## proof` — only when short and load-bearing (2–4 lines).
   - `## prose` — one sentence of intuition, or nothing.
   - `## uses` — only where the answer alone leaves you asking *why would I
     ever need this*. One clause, the setting in plain words with its formal
     name in parentheses. Most cards should not have one.
   - `frequency` and `derivation` — **both, on every card.** `frequency` is
     `core | common | rare`, `derivation` is `definitional | short | long`.
     They are not decoration: `sync` introduces new cards in that order, most
     useful first and then easiest first, and a card missing either sorts to
     the back of the queue as unjudged. A stub left ungraded is a card you
     will meet last.
   - `requires` — uids this card's proof or notation rests on, if any.
     It decides the order the deck is introduced in and it outranks the
     gradings: without it a card can arrive before the result it is built
     from. Only real dependencies; two cards on a theme are not one.
   - `tags` — mechanical and reusable: topic, operation, structure.
   - `verify: true` plus a `## verify` snippet where a stray transpose or sign
     would survive proofreading.

3. Verify what opted in, then check:

   ```
   uv run forge verify
   uv run forge check
   ```

Do not rewrite `front` or `back` unless they are wrong — if they are, say so
in your report rather than quietly reshaping the card. Leave everything
`draft`; approval is a human at `forge serve`.
