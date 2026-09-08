# anki-forge

Turns mathematical source material into reviewed Anki cards. The working
example is [The Matrix Cookbook](sources/matrix-cookbook/).

Two rules explain most of the design:

1. **Nothing reaches Anki without human approval.** `sync` only touches cards
   you have marked `approved`.
2. **Files are the source of truth.** The web app is a view over them. Anything
   it does, you can do by editing a file.

## Install

```
uv sync --extra pdf     # --extra pdf pulls PyMuPDF (AGPL), needed to read PDFs
npm install             # optional: gives `check` the real KaTeX parser
```

Python 3.13+.

## The pipeline

```
extract  ->  units  ->  triage  ->  cards  ->  review  ->  sync
             (you)                  (Claude)   (you)
```

```
uv run anki-forge extract matrix-cookbook   # PDF -> units. Never reads the maths.
/transcribe                                 # crops -> tex_auto, via subagents
/classify                                   # propose which units aren't worth carding
uv run anki-forge serve                     # triage units, then review cards
/extract-cards                              # queued units -> stub cards
/augment                                    # fill in conditions, proof, prose
uv run anki-forge sync --dry-run            # then without --dry-run
```

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
uv run anki-forge sync --dry-run    # says exactly what it would add or update
uv run anki-forge sync
```

`sync` refuses to run at all while `check` reports an error, only ever touches
`status: approved` cards, and upserts by `uid`, so running it twice adds
nothing the second time. It never deletes: a card you un-approve is reported,
not removed, because your review history is not this tool's to throw away.

### Choosing the deck

**Per source**, so two books do not land in one pile. `[anki] deck` is the
default and each source may name its own; `::` makes subdecks:

```toml
[anki]
deck = "Mathematics"                    # the fallback

[sources.matrix-cookbook]
deck = "Mathematics::Matrix Calculus"
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

### Feeding an idea back from review

You are mid-review, you spot how a card should be better, and there is no
obvious way to say so. Two, both pulled in by one command:

```
uv run anki-forge feedback --dry-run   # what is waiting
uv run anki-forge feedback             # ...and pull it
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
order, introduces them in that order. `sync` adds in **study order**: most
useful first, then easiest first, so `frequency` runs core to rare and within
each frequency `derivation` runs definitional to long. A card with neither
annotation sorts last in its group, since unannotated is unjudged rather than
easy.

Cards already in Anki keep whatever position they were first given. To bring
them into line:

```
uv run anki-forge sync --dry-run --reposition    # says how many would move
uv run anki-forge sync --reposition
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
| [sources/](sources/) | the source documents, plus `units.jsonl` — the ledger |
| [cards/](cards/) | one markdown file per card, `<source>/<uid>-<slug>.md` |
| [src/anki_forge/](src/anki_forge/) | the tool |
| [anki-forge.toml](anki-forge.toml) | all configuration, one file |

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
