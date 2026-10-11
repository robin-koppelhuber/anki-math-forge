# Commands

The website runs every `forge` command that has no model behind it. Its rail
lists the commands that apply to what is on screen, with a count of what is
waiting, and the runs window builds the rest and keeps their history. The keys
are in the guide on the website (`?`).

One word reads and two words write ([VERBS.md](VERBS.md)). Every `forge`
command that prints for a human takes `--json`, except `project new`,
`project delete`, `anki export` and `source-text`.

## Claude Code

The passes that need a model are slash commands, and the website gives the
line to paste for each one.

| Command | What it does |
|---|---|
| `/propose --project NAME '<subject>'` | A subject becomes units, where there is no document to segment. |
| `/sources --project NAME` | Proposes reference material to check a card against. Every line stays pending until you take it. |
| `/transcribe --project NAME` | Crops become LaTeX, through subagents. |
| `/classify --project NAME` | Proposes which units are not worth a card. Applies nothing. |
| `/gist --project NAME` | One line per unit on what its card would be about. |
| `/extract-cards --project NAME` | Queued units become draft cards. `--augment` runs `/augment` afterwards. |
| `/augment --project NAME` | Conditions, proof, prose and tags on drafts. Run it before approving. |
| `/triage claude [--project NAME]` | Works the open `@claude` annotations. |
| `/sort-notes --project NAME [--write \| --both] <notes>` | A pile of notes becomes new units and `@me` annotations on the cards and units they bear on. `--write` modifies existing cards instead and cards the new units. `--both` chooses for each piece. A card it edited returns to review. |

## forge

### Every session

| Command | What it does |
|---|---|
| `serve` | The website: project setup, triage, review and the dependency canvas. `--host`, `--port`. |
| `check` | Lint. An error blocks `anki push`. `--anki` also checks uids against the live collection. |
| `anki` | Says what `anki push` would do and pushes nothing. |
| `anki push` | Approved cards go to Anki, upserted by uid. `--project`, `--dry-run`, `--templates`, `--reposition`, `--move-decks`. |
| `anki pull` | Comments and flags from Anki become `@claude` annotations on the card, and are erased in Anki. `--dry-run`. |
| `todo` | The open `@claude` and `@me` annotations. |
| `remarks`, `remarks add` | What the passes said about the tool, kept in `projects/remarks.md`, and how a pass says one. |

### Once per project or source

| Command | What it does |
|---|---|
| `project new <name>` | Starts a project with no document. `--title`, `--deck`, `--citation`. `project delete <name>` removes it and its cards, with `--force` if it holds any. |
| `topic add '<subject>' --project NAME` | What you want cards for. `--ask` says what you want from it. |
| `units extract [project]` | A document becomes units. Never writes cards. `--pages`. |
| `zotero` | What Zotero holds, and what is already a source. `zotero import [item]` turns its marks into units. `--tag`, `--project`, `--dry-run`. |
| `sources` | Every source in the repo, and which project reads it. `sources update --project NAME` re-reads its Zotero items and its files. `sources remove KEY --project NAME` takes one out. `--force`, `--dry-run`. |
| `anki export [project]` | A deck as an `.apkg`. `--deck`, `--out`, and `--scheduling` to include review history. |
| `audit` | Whether the ledger can be trusted: 1..N, no gaps. |

### Called by the skills, or from a script

| Command | What it does |
|---|---|
| `units` | The ledger, filtered. `units set <id>` writes state, gist, annotations, transcription or web lookups. `units note <id> '<text>'` leaves an annotation. `units add SLUG` writes a unit where there was nothing to segment. |
| `cards` | The cards, filtered. `--changes` adds what moved on each one since you last approved or rejected it. |
| `cards new --unit <id>` | Scaffolds a draft card from a queued unit. Repeat `--unit` to build one card from several. |
| `context <unit-id>` | The page a unit was printed on, and the source's conventions. `--pages N` takes N pages either side, or `section`, `chapter` or `part` from the PDF's outline. |
| `source-text [project]` | The document's cached text layer. |
| `crops` | Renders unit crops to a directory. `--out`, `--untranscribed`, `--ungisted`. |
| `units classify` | Proposes skips and applies nothing. `--dry-run` records nothing either. |
| `verify` | An opt-in numeric check of identities. `--uid`, `--project`, `--trials`. |

## Anki and decks

- "cannot reach AnkiConnect" means Anki is closed.
- `anki push` does not push the card template. `anki push --templates` does.
- Changing a source's deck sends new notes there. `anki push` names the cards left behind, and `anki push --move-decks` moves them.
- `[decks]` in `project.toml` splits `identity` and `intuition` into subdecks, so each gets its own new-card limit. `[decks.by_tag]` and `[decks.by_topic]` route cards by tag, or by the ask in `topics.md` their units stand under. A tag wins over a topic, and a topic over a type.
- `relearn: slightly | more | reset` on a changed card tells the next `anki push` how much to reschedule it in Anki. The key comes off the file once it is done.
- Study order starts with `requires`, which always wins. The rest is `frequency`, then `derivation`, then printed order, and `study_order` in `forge.toml` reorders them. `anki push --reposition` moves cards you have not studied yet.
- In Anki, `E` writes the `Feedback` field and `Ctrl+1..7` sets a flag. `anki pull` brings both back.
