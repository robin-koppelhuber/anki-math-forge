# The command names

**One word shows you something. Two words change something.**

Count the words before you press return. `forge units` prints the ledger;
`forge units set` writes to it. Nothing recorded moves under a one-word
command, so a name you half remember is safe to try.

The three that reach outside this repo live under `forge anki`, because the
word before the verb names the thing you cannot rebuild from the files here.

Each subcommand carries an `effect` in the parser (`reads`, `repo`, `anki`),
`forge --help` groups by it, the app's command registry derives `Offer.reads`
from it rather than restating it, and a test refuses a writing parser that is
reachable in one word. A rule
nothing checks closes again in three commits.

## Reads

| | |
|---|---|
| `forge check` | lint the card files |
| `forge audit` | is the ledger 1..N with no gaps |
| `forge verify` | the opt-in numeric check over identities |
| `forge todo` | open `@claude` and `@me` annotations |
| `forge units` | the ledger, filtered |
| `forge cards` | the cards, filtered |
| `forge sources` | every source, and which project reads it |
| `forge project` | the projects this repo holds |
| `forge topic` | what a project has been asked for |
| `forge remarks` | what the passes said about the tool |
| `forge zotero` | what Zotero holds, and what is already a source |
| `forge context <unit>` | the page a unit was printed on |
| `forge source-text` | the cached text layer |
| `forge crops` | render crops to a directory |
| `forge serve` | the app |

`crops` writes PNGs and is still a read, because what it writes is regenerable
bytes under a scratch directory, not recorded state. `serve` records nothing
itself; what it opens is the app, and the app writes.

## Writes, here

| | was |
|---|---|
| `forge units extract [project]` | `extract` |
| `forge units classify` | `classify` |
| `forge units add <slug> --project P` | `units --add` |
| `forge units set <id> --state\|--gist\|--tex\|--pages\|--web\|--reason` | `units --id --set-state` and friends |
| `forge units note <id> <text>` | `units --id --annotate` |
| `forge units clear-notes <id>` | `units --id --resolve-notes` |
| `forge units suggest <id> <state> <reason>` | `units --id --suggest` |
| `forge units accept <id>` · `forge units dismiss <id>` | `units --id --accept` / `--dismiss` |
| `forge zotero import [item]` | `zotero <item>` |
| `forge sources remove <key> --project P` | `sources --remove` |
| `forge sources update [--project P]` | new: the Zotero import and the segmenter in one run |
| `forge project new <name>` | `project <name>` |
| `forge project delete <name>` | `project <name> --delete` |
| `forge topic add <name> --project P` | `topic <name>` |
| `forge cards new --unit <id>` | `new` |
| `forge remarks add <text> --by <pass>` | new: a pass says what got in its way |

## Writes, outside

| | was |
|---|---|
| `forge anki` | `sync --dry-run`: what would be pushed, pushing nothing |
| `forge anki push` | `sync` |
| `forge anki pull` | `feedback`, which erases what it takes |
| `forge anki export` | `export` |

`forge anki` on its own is the dry run, so the plan is what you get by
typing the shortest thing. The one that writes is a word longer.

## The old spellings

Every one of them still runs, hidden from `--help`, and prints the new form
once on stderr. They are kept rather than dropped because they are written
into skills, notes and shell history that nobody is going to sweep.
