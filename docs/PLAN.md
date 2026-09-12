# Planning round, 2026-09-11 (closed)

One brainstorm, three clusters: prose-heavy sources and Zotero, more control in
the web app, publishing as open source.

**This round is settled.** [ROADMAP.md](ROADMAP.md) is the live document and
holds what to do. This file is the record of how it was decided: the question,
the answer, and what the answer was taken to mean. Kept because the reasoning
behind a rejection is worth more later than the rejection.

---

## The short version

**A (prose sources, Zotero, papers) is the valuable cluster**, and not mainly
for the features. Every abstraction here has exactly one instance: one source,
one deck, one layout, one conventions file, one locator built around equation
numbers. None of it is tested. A second source is what proves which of them are
real.

**B (control surface) is mostly answered by what exists.** Progress is already
in the ledger. A database would be a second copy of the truth. Config in the
browser is the one idea to shrink rather than build.

**C (open source) is cheap and goes second**, because a README that says "two
sources, one of them prose" is a different document from one that says "one
book".

---

# Round 1

## A1. Split a deck into "statements" and "intuition"

**Yes, and most of it exists.** Decks are per source and `::` already makes
subdecks. The only gap: the deck is picked per source, and this needs it per
card. **Subdecks, not tags**, because what you want is a different new-card
rate for the two. Five restatements a day is fine, five pieces of intuition a
day is not, and a per-deck limit is the only way Anki lets you say that.

Catch: changing a deck does not move notes already in Anki. Pick before a
source's first sync.

**Answer:**
```
OK, let's settle one subdecks since we may also want a different card type
from statements which e.g. is a bit more free form etc.
```

## A2. More page context around a crop, and maybe a PDF viewer

**Yes, do it first.** `TRIAGE_CONTEXT = 40.0` is a constant and the crop
endpoint already takes a `context` parameter. Make it per source, add `+`/`-`
in triage. **Not pdf.js yet**: a "show the whole page" toggle with the unit's
box drawn on it gets most of the value with no dependency. pdf.js earns its
place when you want to drag a box in the browser to make a unit.

**Answer:**
```
OK, no pdf.js, implement your first suggestion
```

## A3. Extract by convention, not by equation number

Generalise the locator from `equation: int` to a label with a family. The
contiguity oracle survives: theorems are numbered contiguously per chapter. The
coverage oracle was argued as essential, because prose has no numbering to lean
on. Judgement stays in `classify` and triage, never in extraction.

**Answer:**
```
I don't understand what you mean by the contiguity oracle and coverage oracle;
justify them in simple language; Let's introduce a mechanical vs. prose split
for the cards as suggested in the initial prompt. Each mechanicaly identified
thing in the text (e.g. a lemma) becomes a unit. Let's not auto-generate units
from free form prose yet. Let's lock this behind the Zotero integration: each
unit from a free-form text must be triggered by a zotero annotation. This
doesn't automaticaly mean that no mechanical unit can gain an intuition
companion and the other way around later.
```

**The two oracles, plainly.** *Contiguity* (built, this is `audit`): the book
numbers its equations 1 to 571, so if the numbers we found are exactly 1 to 571
with nothing missing and nothing twice, we lost no equation. No human, no
mathematics. It works because the book tells us how many things there should
be. *Coverage* (not built): contiguity only proves we found every **numbered**
thing, not that each unit holds the **whole** equation. Equation 27 is three
lines; we have two, and the third is in no unit anywhere, and contiguity was
satisfied because 27 existed. Coverage takes every piece of text on the page
and checks it lands inside some unit's box.

**Understood as:** only mechanically identified things become units. Free prose
is never segmented; a prose unit must come from a Zotero annotation. A unit can
carry cards of both kinds, which needs no machinery: a card is already not
one-to-one with a unit and `uids` is already a list.

This **weakens my own argument for coverage** and I am recording that rather
than quietly keeping it. If most of a prose page is meant to be outside every
box, a naive coverage check screams on every page. It narrows to "is every
named statement inside a unit", which is weaker and closer to contiguity. Still
worth building, no longer urgent.

## A4. Zotero annotations as a source

Highlighting while you read **is the triage step**, done earlier by someone
paying attention, so an imported annotation arrives `queued` rather than `new`.
**Python must not talk to Zotero**: a `/zotero-import` skill uses the MCP and
writes units through the CLI, so no MCP in `pyproject.toml` and no credentials
in the tool.

**Answer:**
```
I already have this MCP server set up: https://pypi.org/project/zotero-mcp-server/;
I suggest the following flow: I tell you in natural language or via a cite-key
that I want to create cards from a zotero document. You use the MCP server to
pull the full text as well as annotations and store them in a simple but
reliable and usefull format to you (don't over engineer; how does Zotero do
it?); Then I can spin up our website and triage the annotation, i.e. which ones
get queued.
A few things to note:
- There should be a "sync" step that uses Zotero as source of truth and pulls
  the latest documents and annotations via the MCP
- Which annotation means what should be configurable
- Note that there exist "full text marking", "underlining" as well as "free
  text notes" and "image boxing" as "annotation types" in Zotero (don't know
  how they are formaly called). All of them should be mappable and our website
  should be able to filter for which we are currently triaging
- There should be a "Zotero default" for these settings and a possibility to
  overwritte per source
- I could also add a tag to an entire Zotero source if I want it to be pulled
  here
- Things from Zotero should by default land in a "Paper" deck if not further
  specified (or in a subdeck); Not sure yet whether to make a new sub-deck for
  each paper, but I'm leaning towards it
```

## A5. A deck for papers

`source` currently means five things at once: one document, one deck, one
conventions file, one ledger, one dropdown entry. Either each paper is a
source, or a source holds many documents.

**Answer:**
```
I think it's not too important for later steps where a source "initialy came
from"; Either as a full pdf put in the repo by hand or via Zotero. Both should
be "first level sources". We could "tag" the sources to make them easier to
filter later. For the "bloated .toml" point: What about having default settings
and the possibility to overwritte them with a source specific toml which also
lives in the source folder. This document should then also bundle all
conventions of the source for extraction etc.; single "source specific config
source of thruth" beyond the standart config
```

**Understood as:** each paper is a first-level source. No collection
abstraction, and **`locator.document` is dropped** since there is now no case
for it. Per-source config moves into the source's own folder, holding both the
machine keys and the conventions prose, with repo-wide defaults cascading.

## B1. Triggering Claude from the website

There is no supported way to push a prompt into a running Claude Code session
from outside. Shelling out to `claude -p` works but is a separate headless run,
and a button that writes cards unwatched is what invariant 1 exists to prevent.

**Answer:**
```
OK, let's not add this functionality for now. But maybe give dynamicaly
generated copyable commands different "actions" on our website, e.g. we have a
source collected and a filter active, make the command copyable for how to move
these cards to the next step
```

## B2. Progress bars

Most progress is already on disk, so nothing visible in the ledger needs a job
runner. A counts strip reading what the FSM panel reads, no new state.

**Answer:**
```
Progress bar only is a good idea, but make sure it updates automaticaly
```

## B3. The toml config in the browser

Config is read at startup and half these keys change the meaning of existing
content, so a text box over them with a restart in between is a trap. What is
missing is seeing, not editing.

**Answer:**
```
Let's start with viewing only for now
```

## B4. sqlite or a real database

The files are the product. What scale wants is an index under `.forge/`, not a
store. Measure first: build it when a units page passes about 300 ms.

**Answer:**
```
Implement yours
```
```
yes, measure and maybe build an index to speed things up later
```

## B5. A web framework

FastAPI plus Jinja2 is already the simple framework. The question is the
frontend: about 25 kB of hand-written JS, fine for lists and keyboard
navigation, less fine once live progress and config forms arrive.

**Answer:**
```
Keep the current setup if you deem it suffices
```

**Understood as:** keeping it. It suffices for what is actually planned: an
auto-updating counts strip is about twenty lines of fetch and swap, and the
graph view is deferred. Trigger for revisiting, in the style of B4: if the same
fetch-and-replace-a-fragment code gets written a third time, adopt htmx then.

## C1. Polish, and the licensing question

No `LICENSE` exists, which means all rights reserved. PyMuPDF is AGPL and
optional, which is what makes an MIT core honest. The repo stores geometry
rather than documents, so it redistributes nothing.

**Answer:**
```
Aggree. You may update the Readme etc. for now, but I will rewritte by hand to
give it a human tone etc. later
```

## C2. Export the flow diagram

Mermaid renders natively on GitHub and stays in sync by being text.

**Answer:**
```
No, svg or png would be nice. You may put the current thing in for now, but
with the heavy updates upcoming I will probably want to create more
visualizations in the future
```

## C3. Screenshots and a live demo

A recording beats a paragraph. A live demo writes to the filesystem, needs the
PDF hosted, and is a stateful service to babysit so a visitor can click twice.

**Answer:**
```
Agree
```

## C4. Ship a finished `.apkg`

The pipeline's output, openable in thirty seconds with nothing installed, and a
golden fixture you can regenerate and diff.

**Answer:**
```
Let's just add the feature to save the .apg and have the matrixCookbook one as
an example since the lincense of this one is nice
```

**Two facts checked, both against this.** AnkiConnect's `exportPackage` could
not be verified (Anki was not running). And the Cookbook's front matter states
**no licence at all**: a disclaimer, an errata address, acknowledgements, and
nothing granting redistribution or derivative rights. Freely downloadable is
not the same as licensed. Worth two minutes on matrixcookbook.com before a
derived deck is published.

## C5. LLM calls in the code, with BYOK

"No LLM API code in the Python" is why there is no torch, no key handling, no
cost model, no injection surface inside the tool. That is a position, and it is
more interesting than the feature.

**Answer:**
```
Put in the backlog for way later; but this might be a nice thing to have if
people are not exactly using my exact claude setup
```

## C6. Is this a good portfolio project? Critically.

Strong: software you actually use, built on invariants with teeth, with
rejected options recorded *with numbers*. Weak, worst first: one instance of
every abstraction; more prose than code; half of it does not run without Claude
Code; the tests are invisible.

**Answer:**
```
We just need to be honest about what this is and what it is not and "de-AI" the
docs etc.; You may still write them, but I will polish them for the human touch
later; I think it's fair for the code to be LLM generated
```

## C7. The USP

Mechanisms rather than adjectives: nothing reaches the deck unapproved and
editing un-approves automatically; `verify` numerically checks the identity;
every card traces to a page and a box.

**Answer:**
```
Also the Zotero integration now is a USP
```

---

# Round 2: the critical review

## 2. "Zotero as source of truth" versus invariant 2

**You:** do the notification thing

**Understood as:** Zotero owns the annotation's text and geometry, the ledger
owns triage state and cards. A sync fills empty fields and never overwrites
`state`, `uids` or `notes`, which is what `upsert` already does for
re-extraction. When an annotation changes or disappears **after a card exists**,
sync reports it and touches nothing. Before a card exists there is nothing to
protect, so it just updates. The report goes to the sync output *and* marks the
unit, because a terminal line scrolls away.

## 3. Storing paper full text

**You:** Stop worrying about copy-right; I already have the papers in MY Zotero
and all of them are public; I want them as fulltext here so you can do the
"snapshots" from them to show on the website instead of an MCP call each time

**Understood as:** the PDF and the text layer are pulled once and cached in the
source folder, so crops render locally and card writing has context without an
MCP call per view. This needs no new mechanism:
`sources/matrix-cookbook/.gitignore` already ignores `*.pdf`, `*.tex` and
`text.md`, and papers get the same file. A clone still carries no documents.
The copyright argument comes out of the public docs entirely; the gitignore
keeps doing its job without being talked about.

## 5. A subdeck per paper

**You:** agreed

**Understood as:** one `Papers` deck with a `paper::<citekey>` tag. The
criterion that makes A1 subdecks and this one tags: subdecks are for a
different new-card **rate**, tags are for **filtering**.

## 6. Fifty sources and fifty decks

**You:** Agreed

**Understood as:** the source picker becomes searchable and tag-filterable
before the first bulk import, not after.

## 7. Three names for one axis

**You:** agreed, but the annotation type comes from Zotero, not for us to
choose; I just want the unit triage (and maybe later stages) to be filterable
for the annotation type; note that there are many compared for the filters we
already have

**Understood as, corrected:** these are two axes and I had conflated them.

- **Card `type`**, ours: `identity` and `intuition`. No `kind` key. The deck
  mapping keys off `type`.
- **Annotation type**, Zotero's: highlight, underline, note, image, ink. Unit
  metadata, recorded and filtered on, never chosen by us.

The filter strip needs work before this lands. Existing filters are small
closed sets (four states, three statuses) drawn as toggle rows; five annotation
types times eight colours does not fit that shape. **Left as a design call
rather than decided:** whether to filter on the raw type and colour, or on the
meaning they map to. Meanings are what you think in but they change when the
config changes; the raw pair is stable. Taking it as: show the meaning, filter
on both.

## 8. The extractor

**You:** go for the most flexible / general option; you may leave the other
option as a configurable option per source, but only if it doesn't add too much
tech dept to maintain

**Understood as:** the model reading pages is the extractor. `pdf.py` is kept
as a per-source backend, **frozen and unmaintained**: do not fix its
heuristics. Debt is low because the seam is already one function with contract
tests.

One near-term cost, because it contradicts a rule already in writing:
generalising `Locator` means touching `pdf.py`, which ROADMAP said never to
extend. The way out is a shim. `pdf.py` keeps emitting `equation: int` exactly
as it does, and an adapter maps it to `kind="equation", label="61"`.

## 9. Copyable commands

**You:** Good to consider this. I was also thinking the claude commands actualy

**Understood as:** the website offers both, built from the active filter: the
CLI command, and the Claude slash command to paste into a session where you can
watch it. That is the honest version of "trigger Claude from the website".
Slash commands are not shell, so the PowerShell quoting problem applies only to
the CLI half.

## 10. Diagrams

**You:** Yeah, you may make a small helper script to render them, but in the
end there will just be some folder with the images and demo video that is then
imported by the readme. The FSM on the website stays dynamic / from code of
course

**Understood as:** a committed folder of images plus the demo video, referenced
by the README, with a small helper script so regenerating is cheap. No mermaid.
The live FSM stays generated from code. Accepting that committed images can go
stale quietly, since nobody will be checking.

## The rename

**You:** Note that we at some point have to rename the project, so don't put
the name everywhere

**Understood as:** the name is a variable. Two strings are already written into
the Anki collection and are the only expensive part of a rename:

| | where | cost later |
|---|---|---|
| `forge identity v1` | the note type, on all 108 notes | renaming in Anki keeps history, but the tool must not silently create a second note type when the configured name is missing |
| `forge` | `tag_prefix`, on every synced note | sync can retag, but stale tags linger until it does |
| package, CLI, `forge.toml`, `.forge/`, docs | source only | cheap, any time |

Both Anki-facing names are config values, so they get neutral values **now**,
while there are 108 notes, and the eventual rename never touches Anki.
`identity` in the note type name is wrong anyway once the type split lands.
Docs say "the tool" in prose, keeping the literal name to install lines and
command invocations.

**Settled: `anki-math-forge`**, because `anki-forge` is taken. `Anki-Math-Studio`
was declined: "Studio" promises an IDE and this is a CLI plus a review view.
Invented names (`Cardwright`) were declined too, and rightly: the brief is a
plain clean tool, not a product with branding.

Since a further rename is plausible, nothing machine-facing derives from the
project name any more. `forge` is the stem that survived this rename, so the
command, config file, work directory and tag prefix hang off that instead.
ROADMAP §5 carries the table and splits the work: the two strings already in
the Anki collection go first, before §2 syncs more notes, and the source-facing
rename rides along with publishing.
