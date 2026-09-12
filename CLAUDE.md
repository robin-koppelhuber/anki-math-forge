# anki-math-forge

Turns mathematical source material into reviewed Anki cards.

Full reasoning behind every rule below: [docs/CONTRACT.md](docs/CONTRACT.md).
Design doc: [docs/DESIGN.md](docs/DESIGN.md) (cited as DESIGN.md in code
comments). What is left to build: [docs/ROADMAP.md](docs/ROADMAP.md).
How prose here is written, and what each object is called:
[docs/STYLE.md](docs/STYLE.md). Read it before writing docs, template text or
anything in `.claude/`.

## Invariants

Tests cite these by number. Each links to the reasoning.

1. **Nothing reaches Anki without human approval.** `sync` only touches
   `status: approved`. The one flow back out is `feedback`, which erases what
   it takes.
2. **Files are the source of truth.** The web app is a view over them. Anything
   it does is also doable by editing a file.
3. **Extraction produces units, never cards.** Geometry, never image files.
   Every unit arrives `new`, whichever door it came in by: a Zotero import is
   not triage.
4. **`tex_auto` is a hint.** The crop is authoritative. A transcription error
   must not become a card by inheritance.
5. **Editing an approved card un-approves it.** `content_hash` covers content
   and nothing else. Outside it: `status`, `content_hash`, `## notes`,
   `## verify`, `verify`, `requires`, `frequency`, `derivation`, `web`, `gist`.
   Nothing rewrites a file to enforce this; `Card.demotion` reports it, and
   fixing the cause restores the approval with no re-review.
6. **Card content guidelines live in the skill, not in code.** The Python never
   generates or rewrites card text.
7. **A crop is authoritative for what is printed and silent about the rest.**
   Whether an identity needs a condition is mathematics, and it belongs to
   whoever writes the card. Note in `## notes` any condition you add that the
   source does not state.
8. **A bounding box means what its origin means.** A segmenter's edges are an
   answer; a mark's left and right edges are wherever a sentence happened to
   start and stop, so those crops are cut to page width.
9. **A unit is a decision; a card is the content.** Triage answers "is this
   worth a card" and "roughly about what", and nothing else. Depth belongs at
   the card stage. You do not have to be able to transcribe a unit to triage
   it.

## Card format

One markdown file per card in [cards/](cards/), named
`<source>/<uid>-<slug>.md`. The folder is filing only: `unit:` records the
source and every loader `rglob`s.

Frontmatter: `uid` (6 hex), `type` (`identity | intuition`), `status`
(`draft | approved | rejected`), `content_hash` (set on approval), `source`,
`unit`, `tags`, `verify`, and optionally `frequency` (`core | common | rare`),
`derivation` (`definitional | short | long`), `web` and `gist` (a few words
naming the card, for a list or a graph node; never reaches Anki). An unrecognised
`frequency` or `derivation` is a `check` error.

Sections: `## front` and `## back` required; `conditions`, `prose`, `uses`,
`proof`, `verify`, `notes` optional. Math is `$...$` / `$$...$$`. `## notes`
and `## verify` never reach Anki.

`identity` states a fact and `verify` can check it numerically. `intuition`
explains one and has no `## verify` and no `## conditions`.

A card is not one-to-one with a unit: `uids` on the unit splits one, and
`unit:` accepts a list to merge several. `requires` lists uids that must be
introduced first, for a real dependency only.

## Conventions

**Conventions belong to a source, not to this file.** Which layout a
derivative uses, what a bare symbol means: each is a fact about one book. They
live in `sources/<name>/source.toml` (the `[conventions]` table, open to any
key) and `sources/<name>/conventions.md` (the prose a card writer must read).
`forge context <unit>` hands both over, along with whether web lookups are
allowed here.

There is deliberately no repo-wide counterpart. `[cards] layout` raises at
load.

## Commands

```
uv run forge extract [source]   # source -> units; never reads the maths
uv run forge zotero --list      # what Zotero has, and what is already a source
uv run forge zotero --tag anki  # what you marked up in Zotero -> units
uv run forge classify           # *propose* skips; applies nothing
uv run forge audit              # is the index trustworthy? 1..N, no gaps
uv run forge crops --section 2.4 --untranscribed --out DIR --json
uv run forge context <unit-id>  # the page it was printed on (--pages N for more,
                                #   counted *either side*: 3 hands over seven),
                                #   plus whether web lookups are allowed here
uv run forge units --id <id> --web yes|no|inherit   # grant or refuse them
uv run forge source-text <src>  # the book text, for card-writing context
uv run forge check              # lint (always; blocks sync)
uv run forge units --state queued --json
uv run forge units --ungisted   # no one-line subject yet; `/gist` fills them
uv run forge units --id <id> --gist 'Lemma 2'
uv run forge new --unit <id> --front '$...$' --back '$...$' --gist 'what it is'
uv run forge todo               # open @claude annotations
uv run forge serve              # units triage + card review
uv run forge sync --dry-run     # then without --dry-run
uv run forge feedback           # Anki review comments/flags -> @claude notes
uv run forge verify             # opt-in numeric check
```

Every verb that prints for a human takes `--json`. That is the interface to
read from, not the human output.

`uv run pytest` · `uv run ruff check .` · `uv run mypy`

## Frozen

`src/anki_math_forge/extract/pdf.py` is frozen
([ROADMAP](docs/ROADMAP.md) §9). It works, it is verified, and it is the only
PDF segmenter there is. It is frozen because every heuristic in it is
specialised to one book, so extending it means teaching that book's habits to
the next one.

Do not extend it and do not fix its heuristics. When a shared type changes
under it, give it a shim rather than editing it. `extract/render.py` (crops) is
deliberately separate and is not frozen.

## Working here

- Boring implementations. This has to stay legible in six months.
- Annotations are a scratchpad: lines in `## notes` starting `@claude` are open
  requests. Resolve one by deleting the line and making the edit. The edit
  changes `content_hash`, which drops the card back to `draft` automatically.
- When the design doc does not answer something, make a small call and note it
  in a comment. Do not block.
- `uv sync --extra pdf` for PDF work; `npm install` gives `check` the real
  KaTeX parser instead of the weaker structural fallback. `check` always says
  which one ran.
