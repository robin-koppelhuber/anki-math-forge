# anki-forge

Turns mathematical source material into reviewed Anki cards. Design doc:
[proposal.md](proposal.md) (referred to as DESIGN.md in code comments).

## Invariants

1. **Nothing reaches Anki without human approval.** `sync` only touches
   `status: approved`.
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

## Card format

One markdown file per card in [cards/](cards/), named `<uid>-<slug>.md`.
Frontmatter: `uid` (6 hex), `type` (`identity` only for now), `status`
(`draft | approved | rejected`), `content_hash` (set on approval), `source`,
`unit`, `tags`, `verify`. Sections: `## front` and `## back` required;
`conditions`, `proof`, `prose`, `verify`, `notes` optional.

Math is written `$...$` / `$$...$$` and converted to MathJax delimiters on the
way into Anki. `## notes` and `## verify` never reach Anki.

## Conventions (DESIGN.md §15, decided)

- **Language:** English, including prose sections.
- **Layout:** **denominator layout** throughout. `∂(scalar)/∂X` has the shape
  of `Xᵀ`; `∂y/∂x` for vectors has shape `(dim x, dim y)`. Every card that
  could be read either way says so in `## conditions`. Mixing conventions is
  the failure that quietly poisons a deck — do not do it silently.
- **Deck:** `Mathematics::Matrix Calculus`, note type `anki-forge identity v1`.
- **`verify` backend:** numpy plus central-difference numerical gradients. No
  torch, no jax.
- **Cookbook source form:** PDF. No LaTeX source is published, so the
  crop is the artefact. See [sources/matrix-cookbook/README.md](sources/matrix-cookbook/README.md)
  for what extraction gets, and for the one known error in the book (eq 28).

## Commands

```
uv run anki-forge extract [source]   # source -> units; never reads the maths
uv run anki-forge audit              # is the index trustworthy? 1..N, no gaps
uv run anki-forge crops --section 2.4 --untranscribed --out DIR --json
uv run anki-forge source-text <src>  # the book text, for card-writing context
uv run anki-forge check              # lint (always; blocks sync)
uv run anki-forge units --state queued --json
uv run anki-forge new --unit <id> --front '$...$' --back '$...$'
uv run anki-forge todo               # open @claude annotations
uv run anki-forge serve              # units triage + card review
uv run anki-forge sync --dry-run     # then without --dry-run
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
