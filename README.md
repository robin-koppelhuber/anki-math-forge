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

## Layout

| | |
|---|---|
| [sources/](sources/) | the source documents, plus `units.jsonl` — the ledger |
| [cards/](cards/) | one markdown file per card, `<uid>-<slug>.md` |
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
