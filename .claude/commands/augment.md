---
description: Fill in conditions, proof, prose and tags on stub cards
argument-hint: [--source NAME]
---

Add the optional sections to stubs that are still bare.

Arguments: `$ARGUMENTS` — **`--source NAME`** narrows to one source's drafts.
Worth asking for when the repo has several: conventions are per source, and a
pass that hops between two books is one that has to reload the setting between
every card.

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

**Not by searching for it.** `context` ends with a section headed *looking
things up*, which says whether web research is permitted for that unit. It is
off unless somebody granted it. The card's own frontmatter may carry `web:`,
which overrides; the review view shows the resolved answer next to the
gradings. When it says no, a gap in the source is a `@me` note, not a search —
the web has a cleaner statement of nearly every result on these pages, and
substituting one produces a card that reads better than a correct one until
the hypothesis the paper had turns out to be the whole point. When it says
allowed, use it for what the source assumes and does not state, and say in
`## notes` what came from off the page.

1. Find them — cards with only `## front` and `## back`:

   ```
   uv run forge check --json
   ```

   ...and read the card files under `cards/` directly. Work on
   `status: draft` cards only; never touch an approved one (editing it would
   silently reset it to draft, which is correct but rude to do in bulk).

2. For each, consult the **card-writing** skill and add what earns its place.
   **Check `type:` first.** An `identity` takes everything below. An
   `intuition` explains rather than states: it has no `## conditions` and no
   `## verify` at all, and `check` refuses both. What it wants is a sharper
   `## front`, the explanation in `## back`, and `## uses` where the point is
   where this actually bites.


   - `## conditions` — when the identity is false without them. One line.
     Name the source's declared layout when the shape depends on it, and only
     then; a source that declares none gets no layout clause. Prefer the
     source's own wording where it gives one; where it gives none and the
     mathematics still needs a condition, state it and note the addition.
     **Not on an `intuition` card** — it has no `conditions` section.
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
   uv run forge verify --source <SOURCE>
   uv run forge check
   ```

Do not rewrite `front` or `back` unless they are wrong — if they are, say so
in your report rather than quietly reshaping the card. Leave everything
`draft`; approval is a human at `forge serve`.
