# anki-forge

Turns mathematical source material into reviewed Anki cards. Design doc:
[proposal.md](proposal.md) (referred to as DESIGN.md in code comments).

## Invariants

1. **Nothing reaches Anki without human approval.** `sync` only touches
   `status: approved`. Traffic is one-way with one exception: `feedback`
   reads review comments and flags back out, writes them into `## notes` as
   `@claude` lines, and erases them from Anki in the same pass — so Anki is
   an inbox for that text, never a source of truth.
2. **Files are the source of truth.** The web app is a view over them, never a
   store. Anything it does is also doable by editing a file.
3. **Extraction produces units, never cards.** If `extract` is tempted to write
   a `front`, it is overstepping. It produces *geometry*, never image files:
   each unit carries `locator.bbox` and crops render from the source document
   on demand.
4. **`tex_auto` is a hint.** When writing a stub from a unit, the crop is
   authoritative. A transcription error must not become a card by inheritance.
5. **Editing an approved card un-approves it.** Enforced by `content_hash`,
   which covers everything except `status`, `content_hash` and `## notes`.
6. **Card content guidelines live in the skill, not in code.** The Python never
   generates or rewrites card text.
7. **A crop is authoritative for what is printed, and silent about the rest.**
   Conditions are usually printed around an identity, not inside it.
   `anki-forge context <unit>` prints the page it came from — that is all it
   does. Whether the identity needs a condition is mathematics, and belongs to
   whoever writes the card: check it, prefer the source's wording where there
   is one, and note in `## notes` any condition you add that the source does
   not state.

## Card format

One markdown file per card in [cards/](cards/), named
`<source>/<uid>-<slug>.md`. The folder is **filing only**: `unit:` is the one
place a card's source is recorded, and every loader `rglob`s, so a card in the
wrong folder still loads and still syncs.
Frontmatter: `uid` (6 hex), `type` (`identity` only for now), `status`
(`draft | approved | rejected`), `content_hash` (set on approval), `source`,
`unit`, `tags`, `verify`, and optionally `frequency` and `derivation`.

**A card is not one-to-one with a unit, in either direction.** One unit splits
into several cards (`uids` on the unit); several units merge into one card
(`unit` accepts a list, or a comma-separated string) — which is what a
multi-line display cut into pieces needs. `anki-forge context <unit>` lists
every unit on the page in reading order, so the pieces are visible and
nameable; `new` takes `--unit` repeatedly and marks each one carded.

`frequency` (`core | common | rare`) is how often the identity turns up.
`derivation` (`definitional | short | long`) is what reconstructing it would
take — `definitional` for facts that are true by definition and have nothing
to derive. Both optional, both coarse on purpose, both reach Anki as
`freq::` / `derive::` tags. An unrecognised value is a `check` error, because
a typo would silently become its own tag and split the deck. Sections: `## front` and `## back` required;
`conditions`, `proof`, `prose`, `verify`, `notes` optional.

Math is written `$...$` / `$$...$$` and converted to MathJax delimiters on the
way into Anki. `## notes` and `## verify` never reach Anki.

## Conventions

**Conventions belong to a source, not to this file.** Which layout a
derivative uses, what the entries are, what a bare symbol means: each is a
fact about one book and one deck, not about this tool. Naming any of them here
would make this contract wrong the moment a second source arrives, and a card
writer told to read it as authoritative would be applying conventions that do
not hold for the page in front of them.

So they live in two places, by kind:

- **`anki-forge.toml`** for what a key can express, and **under
  `[sources.<name>]` when it is a fact about one book**: `layout` and `deck`
  both live there, with `[cards] layout` and `[anki] deck` as the repo-wide
  fallback. `[cards] language` and the note type are genuinely repo-wide and
  stay put. A `layout` outside `denominator | numerator` is refused at load,
  because an unrecognised one would read as "not denominator" and silently
  change what every card from that source means.
- **`sources/<name>/conventions.md`** for what it cannot: the ambient
  mathematical setting, what is assumed constant, how a contested convention
  was settled. `anki-forge context <unit>` prints it, so whoever writes or
  reviews a card sees the right one without knowing it exists. If a source has
  no such file, `context` says so — an absent convention is a card writer
  guessing.

What is true of the *tool* stays here:

- **`verify` backend:** numpy plus central-difference numerical gradients. No
  torch, no jax.
- **Mixing conventions silently is the failure that quietly poisons a deck.**
  Whatever a source declares, a card that could be read either way says so in
  `## conditions`. `verify` refuses a source whose layout its gradient does
  not compute rather than checking against the wrong one: the two agree on
  every square matrix, so the mismatch would pass review and first bite on a
  rectangular one.

## Commands

```
uv run anki-forge extract [source]   # source -> units; never reads the maths
uv run anki-forge classify           # *propose* skips; applies nothing
uv run anki-forge audit              # is the index trustworthy? 1..N, no gaps
uv run anki-forge crops --section 2.4 --untranscribed --out DIR --json
uv run anki-forge context <unit-id>  # the page an equation was printed on
uv run anki-forge source-text <src>  # the book text, for card-writing context
uv run anki-forge check              # lint (always; blocks sync)
uv run anki-forge units --state queued --json
uv run anki-forge new --unit <id> --front '$...$' --back '$...$'
uv run anki-forge todo               # open @claude annotations
uv run anki-forge serve              # units triage + card review
uv run anki-forge sync --dry-run     # then without --dry-run
uv run anki-forge feedback           # Anki review comments/flags -> @claude notes
uv run anki-forge verify             # opt-in numeric check
```

Every verb that prints for a human takes `--json` for a machine. That is the
interface to read from, not the human output.

`uv run pytest` · `uv run ruff check .` · `uv run mypy`

## Setup notes

- `uv sync` for the core; `--extra pdf` for PDF segmentation (PyMuPDF, AGPL).
  There is no OCR extra and no torch: transcription is `/transcribe`, a Claude
  Code skill reading crops.
- `npm install katex` gives `check` the **exact** KaTeX strict-mode parser.
  Without it there is a structural fallback that is strictly weaker —
  `check` always says which one ran, so "it passed" is never ambiguous.
- The app loads KaTeX from a CDN by default. For offline use, copy
  `node_modules/katex/dist` somewhere served and point `[app] katex_base` at it.

## Deprecated

`src/anki_forge/extract/pdf.py` is **marked for deletion** — see
[ROADMAP.md](ROADMAP.md) §4. It works and it is verified, but it is a
heuristic specialised to this one book. Do not extend it; do not fix its
heuristics. Its replacement is a model reading pages, checked by the same
contiguity oracle. `extract/render.py` (crops) is deliberately separate and
is *not* deprecated.

## Working here

- Boring implementations. This has to stay legible in six months.
- Annotations are a scratchpad: lines in `## notes` starting `@claude` are open
  requests. Resolve one by deleting the line and making the edit — the edit
  changes `content_hash`, which drops the card back to `draft` automatically.
- When the design doc doesn't answer something, make a small call and note it
  in a comment. Don't block.
