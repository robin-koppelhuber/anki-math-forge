# anki-math-forge

[![checks](https://github.com/robin-koppelhuber/anki-math-forge/actions/workflows/checks.yml/badge.svg)](https://github.com/robin-koppelhuber/anki-math-forge/actions/workflows/checks.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)

Turns mathematical source material into reviewed Anki cards: a formula
reference like [The Matrix Cookbook](sources/matrix-cookbook/), a statistics
text, or a paper you marked up in Zotero.

Two rules explain most of the design:

1. **Nothing reaches Anki without human approval.** `sync` only touches cards
   you have marked `approved`, and editing an approved card un-approves it
   automatically, enforced by a hash rather than promised.
2. **Files are the source of truth.** The web app is a view over them. Anything
   it does, you can do by editing a file.

### What this is not

**Not a generate-my-cards tool.** It will not write a deck for you and it
refuses to put anything in front of you that you have not read. What it does is
make the reading fast: every card traces to a page and a bounding box, the crop
is rendered beside the text so a bad transcription is visible rather than
inherited, and `verify` can check numerically that the identity on the card is
actually true.

The Python contains **no LLM API code at all** — no keys, no cost model, no
vendor in the dependency tree. The passes that read pages are Claude Code
skills in [.claude/](.claude/), which you run and watch.

## Install

```
uv sync --extra pdf     # --extra pdf pulls PyMuPDF (AGPL), needed to read PDFs
npm install             # optional: gives `check` the real KaTeX parser
```

Python 3.13+. The tool is MIT; `--extra pdf` is what pulls AGPL code into your
environment, which is a choice you make rather than a licence you inherit.

## First card in ten lines

```
uv run forge extract matrix-cookbook   # PDF -> units. Never reads the maths.
uv run forge serve                     # q to queue one, in the browser
/extract-cards                              # queued units -> a stub card
uv run forge serve                     # a to approve it, in the browser
uv run forge sync --dry-run            # then without --dry-run
```

Everything below is detail.

## The pipeline

```
extract  ->  units  ->  triage  ->  cards  ->  review  ->  sync
             (you)                  (Claude)   (you)
```

```
uv run forge extract matrix-cookbook   # PDF -> units. Never reads the maths.
uv run forge zotero --list             # what Zotero has, and what is already here
uv run forge zotero --tag anki         # or: what you marked up in Zotero -> units
/transcribe --source <name>                 # crops -> tex_auto, via subagents
/classify --source <name>                   # propose which units aren't worth carding
uv run forge serve                     # triage units, then review cards
/extract-cards --source <name>              # queued units -> stub cards
/augment --source <name>                    # fill in conditions, proof, prose
uv run forge sync --dry-run            # then without --dry-run
```

Every unit arrives `new` and nothing leaves it without you, whichever door it
came in by. Marking a paper up while reading says "this mattered"; triage says
"this is worth a card, on its own" -- a different question, and the only gate
between an import and a full card queue.

The triage view writes these command lines for you, scoped to whatever you had
filtered to: press `f` for the rail, and copy from the panel at the bottom of
it. Nothing is launched from the browser.

The slash commands are Claude Code skills in [.claude/](.claude/) — the Python
contains no LLM API code at all. `serve` runs at http://127.0.0.1:8000; press
`?` there for the state machine.

Every verb that prints for a human also takes `--json`.

## Sync to Anki

Three things, once:

1. **Install the AnkiConnect add-on.** In Anki: *Tools > Add-ons > Get
   Add-ons*, code `2055492159`, then restart Anki.
2. **Leave Anki running.** `sync` talks to `http://127.0.0.1:8765`; a closed
   Anki is the whole of "cannot reach AnkiConnect".
3. **Nothing else.** The deck and the note type are created on the first sync
   if they are missing. Set `ANKI_CONNECT_URL` to override the address.

```
uv run forge sync --dry-run    # says exactly what it would add or update
uv run forge sync
```

`sync` refuses to run at all while `check` reports an error, only ever touches
`status: approved` cards, and upserts by `uid`, so running it twice adds
nothing the second time. It never deletes: a card you un-approve is reported,
not removed, because your review history is not this tool's to throw away.

### The note type's name

`[anki] note_type_name` sets it, and nothing derives it from this project's
name. The name is written into every note you own, so it has to survive the
tool being renamed.

```toml
[anki]
note_type_name = "Math Card"    # -> "Math Card v1"
note_type_version = 1
```

Change the stem and `sync` will **refuse** rather than create a second note
type: it finds the old one still in your collection, and creating a new one
would leave every existing note on the old type, invisible to `sync` and
re-added as new. Renaming it in Anki (*Tools > Manage Note Types > Rename*)
keeps every note and its review history.

### Changing the card layout

`sync` does not push the card template: it is yours to edit in Anki too, and a
content sync silently overwriting it would be a bad trade. It does say when the
live layout has drifted from `notetype.py`, and `--templates` pushes it.

```
uv run forge sync --templates
```

### Two kinds of card

`identity` states a fact, `intuition` explains one. An identity has a definite
answer and `verify` can check it; an intuition is what a passage you marked in
a prose source becomes. Both reach Anki as a `type::` tag, and a source can
send each to its own subdeck:

```toml
# sources/<name>/source.md
+++
deck = "Statistics::Wainwright"

[decks]
identity  = "Statistics::Wainwright::Statements"
intuition = "Statistics::Wainwright::Intuition"
+++
```

Subdecks rather than tags here because the point is a different **new-card
rate**: five mechanical restatements a day is comfortable and five pieces of
intuition a day is not, and a per-deck limit is the only way Anki lets you say
that. Studying the parent still sees both.

### Choosing the deck

**Per source**, so two books do not land in one pile. `[anki] deck` is the
default and each source may name its own; `::` makes subdecks:

```toml
[anki]
deck = "Mathematics"                    # the fallback
```

```toml
# sources/matrix-cookbook/source.md
+++
deck = "Mathematics::Matrix Calculus"
+++
```

Anki creates the whole chain, so these cards land in *Matrix Calculus* nested
under *Mathematics*, and a second source with no `deck` of its own goes to
*Mathematics*. A card is filed by the source its `unit:` names.

Change a deck and the next sync writes *new* notes there; it does not move the
ones already filed, since moving somebody's cards between decks is a
scheduling decision, not a lint fix. Move those in Anki.

Every synced note also carries `[anki] tag_prefix` plus the card's own tags
and its `freq::` / `derive::` annotations, so you can build filtered decks
without splitting the deck itself.

### Taking the deck out again

```
uv run forge export matrix-cookbook --out cookbook.apkg
```

Your review history is left out unless you ask for it: a deck you hand to
somebody else should arrive unstudied, and your intervals say more about you
than about the cards.

**One thing to set first, once.** Anki keeps a note's sort field in a column
that takes a number or text, and the sort field is `uid`. A uid shaped
`4e6166` is a valid float literal — 4 × 10^6166 — which overflows a double and
lands as NULL, and a single such note takes the whole deck's export down with
`NOT NULL constraint failed: notes.sfld`.

In Anki: *Tools > Manage Note Types > Fields > `Front` > "Sort by this field in
the browser"*. The uid stays the first field, so duplicate detection and `sync`
are unaffected, and the browser starts sorting by the question, which is what
you wanted anyway. AnkiConnect cannot set this, so it is a one-time click.

`check` warns about any uid with this shape, and new ones never have it.

### Feeding an idea back from review

You are mid-review, you spot how a card should be better, and there is no
obvious way to say so. Two, both pulled in by one command:

```
uv run forge feedback --dry-run   # what is waiting
uv run forge feedback             # ...and pull it
```

**A comment**, when you have the words. Press `E` in Anki and type into the
**Feedback** field. It is on the note type but on no template, so it never
appears during review and always appears in the editor.

**A flag**, when you do not. `Ctrl+1`-`4`, one keystroke, and it works on a
phone. What each colour means is yours to set:

```toml
[anki.flags]
1 = "wrong: the maths does not check out"
2 = "unclear: I could not tell what was being asked"
```

A flag with no entry here is reported rather than guessed at, and left set so
nothing is lost.

Either becomes a `@claude` line in the card's `## notes`, which is where
`/triage claude` looks. Fixing it changes `content_hash`, so the card drops to
draft and comes back through review before it reaches Anki again.

**`feedback` erases what it takes.** That is not tidiness: without it every
run would re-import the same comment, and a note you had already resolved
would come back from the dead on the next pull. It is also the only reason
this does not break rule 2 above -- Anki is a transient inbox for that text,
never a source of truth, and `sync` never writes the field back.

### The order new cards are introduced in

Anki numbers a new card by when it arrives and, with the default new-card
order, introduces them in that order. `sync` adds in **study order**, on
three keys and a graph:

1. `frequency`, core to rare.
2. `derivation`, definitional to long.
3. **the order the source prints it in.** A text that builds up introduces
   things in a usable order, and following it costs nothing. This key used to
   be the uid, a hash, so the order inside a large group was noise and a
   result could arrive well before what it is built from. Whether a source's
   order means anything is a fact about that source: set
   `order = "none"` in the source's own file for a table with no meaningful order, and
   its cards fall back to an arbitrary but stable tiebreak instead of a
   misleading one.
4. **`requires`**, a list of uids in a card's frontmatter, which overrides all
   of the above. Only for a real dependency: this card's proof or notation
   rests on that one. Two cards on a theme are not a dependency.

A card with no `frequency` or `derivation` sorts last in its group, since
unannotated is unjudged rather than easy.

`requires` **pulls the prerequisite forward** rather than pushing the result
back. Demoting a `core` card to sit behind the `rare` one it needs would
honour the graph and make the deck worse, so a prerequisite inherits the
priority of the most important card that needs it.

It is outside `content_hash`: approving a card is not approving its position
in the queue, and hashing it would re-review the whole deck every time the
graph was refined. `check` refuses a cycle, a self-reference, or a uid naming
no card -- the ordering ignores what it cannot resolve, so a typo would
otherwise look like a graph that quietly had no effect.

Cards already in Anki keep whatever position they were first given. To bring
them into line:

```
uv run forge sync --dry-run --reposition    # says how many would move
uv run forge sync --reposition
```

Only cards you have never studied are moved. Past the new queue a card's
position field means a date, so anything you have started is left where it is
and reported. Positions count up from where the deck already sits, so it keeps
its place relative to every other deck's new cards.

This assumes the deck's new-card order is the default (by position). If you
set it to random in Anki's deck options, Anki wins.

## Layout

| | |
|---|---|
| [sources/](sources/) | one folder per source: its `source.md`, the document, and `units.jsonl` — the ledger |
| [cards/](cards/) | one markdown file per card, `<source>/<uid>-<slug>.md` |
| [src/anki_math_forge/](src/anki_math_forge/) | the tool |
| [forge.toml](forge.toml) | all configuration, one file |

A **source** describes itself in `sources/<name>/source.md`: TOML between `+++`
fences for the keys the tool acts on, prose below for the conventions a card
writer needs. A folder without one is not a source.

A **unit** is a located region of the source (page, bbox, section, equation
number) — geometry, never an image file. Crops render from the PDF on demand.
A **card** is a markdown file with `## front` and `## back`; editing an
approved one un-approves it, because `content_hash` stops matching.

## Development

```
uv run pytest
uv run ruff check .
uv run mypy
```

## Further reading

- [CLAUDE.md](CLAUDE.md) — the invariants, the card format, the conventions
- [proposal.md](proposal.md) — the design doc
- [ROADMAP.md](ROADMAP.md) — what is missing, and what was rejected
- [PLAN.md](PLAN.md) — one planning round, closed: the questions and the answers
