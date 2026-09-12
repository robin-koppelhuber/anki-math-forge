# anki-math-forge

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
   on demand. **Every unit arrives `new`, whichever door it came in by.**
   Importing what someone marked in Zotero is not triage: marking says "this
   mattered while I was reading", and triage says "this is worth a card, on
   its own". Landing an import in `queued` answered the second question on the
   reader's behalf and removed the only gate before the card queue.
4. **`tex_auto` is a hint.** When writing a stub from a unit, the crop is
   authoritative. A transcription error must not become a card by inheritance.
5. **Editing an approved card un-approves it.** Enforced by `content_hash`,
   which covers the card's *content* and nothing else: `status`,
   `content_hash`, `## notes`, `## verify`, `verify`, `requires`, `frequency`,
   `derivation` and `web` are all outside it. Those last four are not claims
   the card makes — three decide *when* you meet it and one is a permission
   granted to whoever writes it — and approving a card is not approving its
   position in the queue. Nothing rewrites a file to enforce this: an approval
   that no longer holds is reported by `Card.demotion` and counts as a draft
   everywhere it matters, so resolving whatever broke it restores the approval
   with no re-review.
6. **Card content guidelines live in the skill, not in code.** The Python never
   generates or rewrites card text.
7. **A crop is authoritative for what is printed, and silent about the rest.**
   Conditions are usually printed around an identity, not inside it.
   `forge context <unit>` prints the page it came from — that is all it
   does. Whether the identity needs a condition is mathematics, and belongs to
   whoever writes the card: check it, prefer the source's wording where there
   is one, and note in `## notes` any condition you add that the source does
   not state.
8. **A bounding box means what its origin means.** A segmenter that found a
   display equation stopped where the equation stopped, so the box's edges are
   an answer. A *mark's* box is the union of the lines a sentence happened to
   span, so its left and right edges are wherever that sentence started and
   stopped mid-column and carry no information — those crops are cut to the
   full page width (`crop_width`). Marks are painted back onto the crop in the
   colours the reader used, the unit's own at full strength and its neighbours
   faded, because a page with six highlights on it has to say which one the
   card is about.
9. **A unit is a decision; a card is the content.** Two stages, two questions,
   and neither does the other's work.

   The **unit stage** answers exactly two things: *is this worth a card at
   all*, and *roughly what would the card be about*. That is the whole of
   triage. Everything on screen there serves those two questions — the crop,
   the sentence you marked, what you wrote beside it, the neighbouring marks,
   and a transcription where one happens to exist. An answer that needs more
   than "yes, and it is about X" is a brief (`@claude`), not a decision to
   postpone: `Q` queues and records one in the same keystroke.

   **`gist`** is the other half of that second question, answered in advance.
   `/gist` reads each crop and writes one line saying what a card from it would
   be about -- "Lemma 2", "why the bound needs independence". It is a *reading*
   and nothing downstream consumes it: `/extract-cards` still works from the
   crop, the page and the brief. Keeping it out of that path is the safety
   property -- a machine's guess written where the next pass reads instructions
   would be indistinguishable from yours one pass later. Its whole value is
   that disagreeing with it here costs one keystroke, where the same
   misunderstanding found after a card exists costs a rewrite.

   The **card stage** is where content is settled. `/extract-cards` and
   `/augment` pull whatever context the unit was granted — the page it was
   printed on, the pages either side, the source's conventions, web lookups
   where those were granted — and iterate until `check` passes and a human can
   approve it. Depth belongs here. It does not belong at triage, where it buys
   nothing and costs the throughput the stage exists for.

   The consequence worth stating: **you do not have to be able to transcribe a
   unit in order to triage it.** `tex_auto` exists to keep a *segmented*
   source legible enough to judge (DESIGN.md §4) — the same two questions, not
   a head start on the answer (invariant 4). A marked passage carries the
   sentence it covers and needs nothing more; a boxed figure carries neither
   text nor maths and is still obviously worth a card or obviously not. On a
   prose source the subject of a unit is what you highlighted and what you
   wrote about it, never a formula, which is why the triage view shows those
   and renders no transcription pane at all rather than an empty one.

## Card format

One markdown file per card in [cards/](cards/), named
`<source>/<uid>-<slug>.md`. The folder is **filing only**: `unit:` is the one
place a card's source is recorded, and every loader `rglob`s, so a card in the
wrong folder still loads and still syncs.
Frontmatter: `uid` (6 hex), `type` (`identity | intuition`), `status`
(`draft | approved | rejected`), `content_hash` (set on approval), `source`,
`unit`, `tags`, `verify`, and optionally `frequency`, `derivation` and `web`.

**A card is not one-to-one with a unit, in either direction.** One unit splits
into several cards (`uids` on the unit); several units merge into one card
(`unit` accepts a list, or a comma-separated string) — which is what a
multi-line display cut into pieces needs. `forge context <unit>` lists
every unit on the page in reading order, so the pieces are visible and
nameable; `new` takes `--unit` repeatedly and marks each one carded.

`requires` is a list of uids that must be introduced *before* this card, and
it decides the order `sync` adds new cards in. Only for a real dependency:
this card's proof or notation rests on that one. It is outside
`content_hash`, because approving a card is not approving its position in
the queue. Within the graph, order is `frequency`, then `derivation`, then
the order the source prints it in.

**`identity` states a fact; `intuition` explains one.** An identity has a
definite answer and `verify` can check it numerically. An intuition is what a
marked passage in a prose source becomes: why a bound is tight, what a term is
really measuring, which of two hypotheses is doing the work. It has no
`## verify` (there is nothing numeric to check) and no `## conditions` (a
hypothesis belongs to a statement; anything that needs one is an identity
wearing the wrong type). Both reach Anki as a `type::` tag, and a source may
send each to its own subdeck under `[decks]`, because five restatements a day
is comfortable and five pieces of intuition a day is not.

`frequency` (`core | common | rare`) is how often the identity turns up.
`derivation` (`definitional | short | long`) is what reconstructing it would
take — `definitional` for facts that are true by definition and have nothing
to derive. Both optional, both coarse on purpose, both reach Anki as
`freq::` / `derive::` tags. An unrecognised value is a `check` error, because
a typo would silently become its own tag and split the deck. Sections: `## front` and `## back` required; `conditions`, `prose`, `uses`,
`proof`, `verify`, `notes` optional. They read in that order on the card:
`prose` is one sentence and the only unlabelled block, so it sits directly
under the answer and everything after it is labelled. `content_hash` sorts
sections by name, so the reading order costs no approvals to change.

Math is written `$...$` / `$$...$$` and converted to MathJax delimiters on the
way into Anki. `## notes` and `## verify` never reach Anki.

## Conventions

**Conventions belong to a source, not to this file.** Which layout a
derivative uses, what the entries are, what a bare symbol means: each is a
fact about one book and one deck, not about this tool. Naming any of them here
would make this contract wrong the moment a second source arrives, and a card
writer told to read it as authoritative would be applying conventions that do
not hold for the page in front of them.

So they live with the source, in **`sources/<name>/`**: `source.toml` for the
keys the tool acts on, `conventions.md` for the prose a card writer has to
read. Two files, because they are two things -- a config and a document -- and
the fenced single file they replaced was neither: no editor checks the TOML
above the fence *and* renders the Markdown below it.

- **`source.toml`** is what a key can express, and it is what the tool acts
  on: `title`, `citation`, `pdf`/`tex`, `zotero`, `documents`, `deck`,
  `order`, `tags`, `crop_context`/`crop_width`, `context_pages`, `web`, a
  `[conventions]` table, and a source's own reading of its Zotero marks.
  `crop_width` outside `box | page` is refused at load, because an
  unrecognised value would read as "not box" and silently change every crop.
  `documents` names which of a Zotero item's PDFs to read, by title or
  key — an item routinely carries the paper and a preprint of the paper, and
  marks made in one are not marks in the other. `tags` are yours to invent:
  nothing writes one for you, because a label the tool made up means whatever
  the tool guessed and you would be filtering by it without having decided
  what it says.
- **`[conventions]`** is the keyed half of what is ambient here, and it is
  **open**: any key is accepted, and every one of them is handed to whoever
  writes a card, through `forge context`. What a source assumes is not a
  vocabulary this tool can enumerate — the next paper will take something for
  granted that neither of us has thought of — so the table carries what it is
  given rather than checking it against a list. **There is no repo-wide
  counterpart, deliberately**: a convention is a fact about one book, and
  defaulting one in `forge.toml` is how a statistics paper came to be told
  which matrix-derivative convention it writes. `[cards] layout` now raises at
  load rather than being quietly ignored.

  Exactly one entry is *acted* on rather than only shown, and the asymmetry is
  worth knowing: `layout`, one of `denominator | numerator`, because `verify`'s
  numerical gradient computes one of the two. A value outside them is refused
  at load — an unrecognised one would read as "not the one you meant" and
  silently change what every derivative on every card from that source means.
  **Which of the two a source uses is that source's business to declare**, and
  this file does not name a winner.
- **`web`** is whether whoever writes or augments a card from this source may
  look things up. Off repo-wide, and overridable per source, per unit (from
  triage, `w`) and per card. Off by default because the failure is invisible:
  a card should say what *this source* says, hypotheses and notation included,
  and the web's cleaner statement of the general theorem substituted for the
  printed one reads as a *better* card until the condition the paper had — and
  the general version has not — turns out to be the point. `forge context`
  resolves unit over source over repo and says the answer in words, so the
  pass reading it never has to work out whose setting won.
- **`conventions.md`** is what a key cannot express: the ambient mathematical
  setting, what is assumed constant, how a contested convention was settled.
  `forge context <unit>` prints it, so whoever writes or reviews a card sees
  the right one without knowing it exists. **There is no file until you write
  one** — nothing generates a placeholder, because a placeholder saying
  "nothing recorded yet" is indistinguishable from a real one to everything
  that reads it, and would silence the very warning it should raise. If a
  source has none, `context` says so: an absent convention is a card writer
  guessing.

TOML rather than YAML, because every key in `source.toml` overrides one in
`forge.toml` and a block copied between the two has to work unchanged. It is
also the stricter language: in YAML a tag or colour written `no`, `on` or `y`
is silently a boolean. A folder with neither `source.toml` nor the older
`source.md` is not a source: discovery does not guess.

`forge.toml` keeps what is genuinely repo-wide — `[cards] language`, the
note type, `[anki] deck` as a fallback, `[cards] web` as the floor under every
source's permission, `[zotero]` defaults — and a `[sources.<name>]` block there
still works for a repo that has not moved yet. Conventions are the one thing it
does **not** keep: see `[conventions]` above.

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
uv run forge new --unit <id> --front '$...$' --back '$...$'
uv run forge todo               # open @claude annotations
uv run forge serve              # units triage + card review
uv run forge sync --dry-run     # then without --dry-run
uv run forge feedback           # Anki review comments/flags -> @claude notes
uv run forge verify             # opt-in numeric check
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

## Frozen

`src/anki_math_forge/extract/pdf.py` is **frozen**, see [ROADMAP.md](ROADMAP.md)
§13. It works and it is verified, but it is a heuristic specialised to this one
book, so it is one selectable backend rather than the default. The default is a
model reading pages, checked by the same contiguity oracle.

Do not extend it; do not fix its heuristics. When a shared type changes under
it, give it a shim rather than editing it. `extract/render.py` (crops) is
deliberately separate and is not frozen.

## Working here

- Boring implementations. This has to stay legible in six months.
- Annotations are a scratchpad: lines in `## notes` starting `@claude` are open
  requests. Resolve one by deleting the line and making the edit — the edit
  changes `content_hash`, which drops the card back to `draft` automatically.
- When the design doc doesn't answer something, make a small call and note it
  in a comment. Don't block.
