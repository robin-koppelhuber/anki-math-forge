# anki-math-forge

[![checks](https://github.com/robin-koppelhuber/anki-math-forge/actions/workflows/checks.yml/badge.svg)](https://github.com/robin-koppelhuber/anki-math-forge/actions/workflows/checks.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](pyproject.toml)
[![anki 26.8.1](https://img.shields.io/badge/anki-26.8.1-blue.svg)](https://apps.ankiweb.net/)
[![zotero 9.0.6](https://img.shields.io/badge/zotero-9.0.6-blue.svg)](https://www.zotero.org/)


Turn math-heavy texts into Anki cards with a human in the loop.

1. Import standalone PDFs or entries from your Zotero collection.
2. Decide which parts of the text are worth putting into a card.
3. Generate cards and iterate until they are perfect.

## Features
- Local website to build cards and iterate together with AI.
- Import standalone PDFs or entries from your Zotero collection.
- Use Zotero annotations as the starting point for your cards, and map
  annotation types to different meanings for the agent.
- Augment equations with proof outlines, intuition and use cases.
- Optimized study order: let AI classify the usefulness, hardness and dependency between cards and explore them in a graph view, for the optimal initial study order in Anki.
- Sync cards to Anki and update safely if something changes.
- Write card feedback directly in Anki, sync it back into the website and improve your cards.
- Supported models: currently only works with a Claude Code subscription, no
  API key needed. The website gives you Claude skill commands to run instead
  of triggering API calls from code.


## Quickstart

```
git clone https://github.com/robin-koppelhuber/anki-math-forge
cd anki-math-forge
uv sync --extra pdf      # PyMuPDF (AGPL), needed to read PDFs
npm install              # optional: gives `check` the real KaTeX parser
```

```toml
# sources/<name>/source.toml, for a PDF source
title = "The Matrix Cookbook"
citation = "Matrix Cookbook"
pdf = "sources/<name>/the-file.pdf"
deck = "Mathematics::Matrix Calculus"   # optional; falls back to [anki] deck
```

For a Zotero source instead: run Zotero (version 7+) with its local API enabled
(*Settings > Advanced*), tag the item `anki`, and skip the `source.toml`.

```
uv run forge extract <name>            # or: uv run forge zotero --tag anki
uv run forge serve                     # http://127.0.0.1:8000, press ? for the guide
```

Anki, once:

1. Install AnkiConnect: *Tools > Add-ons > Get Add-ons*, code `2055492159`,
   restart Anki.
2. Leave Anki running while you sync. `sync` talks to
   `http://127.0.0.1:8765`; `ANKI_CONNECT_URL` or `[anki] url` changes it.
3. The deck and the note type are created on the first sync.

## Workflow
Creating cards is a two stage process
1. Create and select **Units**: These are candidate parts of a page in a source for becoming a card. They are cheap to create and change
2. Create and refine **Cards**: Once you've selected which units should become cards, a thourough agent can create a card draft for you to iterate on
```
extract  ->  units  ->  triage  ->  cards  ->  review  ->  sync
             (you)                  (Claude)   (you)
```

```
# route 1: a PDF
uv run forge extract <source>         # PDF -> units. Never reads the maths
/transcribe --source <source>         # crops -> LaTeX, via subagents
/classify --source <source>           # propose skips; applies nothing

# route 2: a marked-up paper in Zotero (needs Zotero running, local API on)
uv run forge zotero --list            # what Zotero has, and what is already a source
uv run forge zotero --tag anki        # every item tagged `anki` -> units

# both routes
uv run forge serve                    # triage units, then review cards
/extract-cards --source <source>      # queued units -> draft cards
/augment --source <source>            # conditions, proof, prose, tags
uv run forge sync --dry-run           # then without --dry-run
```



![the state machine](assets/states.png)

![triage](assets/triage.png)

![review](assets/review.png)

![the dependency canvas](assets/graph.png)

## Commands

Every session:

| `forge` | |
|---|---|
| `serve` | the web app: triage, review, dependency canvas |
| `check` | lint; blocks sync on error |
| `sync` | approved cards -> Anki, upsert by uid. `--dry-run`, `--templates`, `--reposition` |
| `feedback` | Anki comments and flags -> `@claude` notes |
| `todo` | open `@claude` annotations |

Once per source:

| `forge` | |
|---|---|
| `extract [source]` | PDF -> units; never writes cards |
| `zotero [item]` | Zotero marks -> units. `--list`, `--tag`, `--dry-run` |
| `export [source]` | a deck as `.apkg`; `--scheduling` includes review history |
| `audit` | is the ledger trustworthy: 1..N, no gaps |

In the order the pipeline runs them:

| Claude Code | |
|---|---|
| `/transcribe --source NAME` | crops -> LaTeX, via subagents |
| `/classify --source NAME` | propose which units are not worth a card |
| `/gist --source NAME` | one line per unit on what its card would be about |
| `/extract-cards --source NAME` | queued units -> draft cards |
| `/augment --source NAME` | conditions, proof, prose, tags on drafts. Run before approving |
| `/triage claude` | work the open `@claude` annotations |

Mostly called by the skills, or from a script:

| `forge` | |
|---|---|
| `units` | view or change the ledger: state, gist, notes, transcription |
| `context <unit-id>` | the page a unit was printed on, plus the source's conventions |
| `source-text <source>` | the document's cached text layer |
| `crops` | render unit crops to a directory |
| `classify` | propose skips; applies nothing |
| `new` | scaffold a draft card from a queued unit |
| `verify` | opt-in numeric check of identities |

| Keys | units | review | graph |
|---|---|---|---|
| decide | `q` queue, `Q` queue + brief, `s` skip, `S` skip + reason, `a` accept a suggestion, `d` dismiss it | `a` approve, `r` reject | `+` add a card, `Delete` remove selection, `Enter` open card |
| repair | `u` back to new, `z` undo, `n` note for claude, `N` note for me, `c` context size, `w` web lookups, `p` crop/page/doc | `u` back to draft, `z` undo, `e` `$EDITOR`, `n`, `N`, `x` resolve first note | `z` undo, `x` put boxes back, `A` select all |
| move | `j` `k` next/prev, `f` filters, `g` sources, `?` guide | same | `.` `,` zoom, `0` fit, `g` sources |

> [claude] `[app.keys]` in `forge.toml` remaps any key by action name.

## Debugging
- "cannot reach AnkiConnect" means Anki is closed.
- `sync` does not push the card template; `sync --templates` does.
- Changing a source's deck sends new notes there, does not move old ones.
- `[decks]` in `source.toml` splits `identity` and `intuition` into subdecks, so each gets its own new-card limit.
- Study order: `frequency`, then `derivation`, then printed order;
 `requires` overrides. `sync --reposition` moves cards you have not
 studied yet.
- Feedback: `E` in Anki writes the `Feedback` field, `Ctrl+1..4` sets a flag.

## Contributing & License
Happy for any contributions, open a PR.

License: MIT. `--extra pdf` pulls PyMuPDF, which is AGPL.
