# Roadmap

What is left to build, a short account of what is built, the evidence the
Cookbook's extraction left, and what was rejected and why.

This file is about the tool. What is worth carding, and which sources to
import, is about one deck and lives in an untracked `ROADMAP.private.md`
beside it.

**The numbers are names, not an order.** Code cites them (`ROADMAP.md §1`,
`§9`), so a section keeps its number wherever it moves to and a new one takes
the next free number.

**A built section is a summary.** The reasoning written while building it,
the alternatives and the bugs on the way, is in git: `git log -p --
docs/ROADMAP.md`. The milestones in [DESIGN.md](DESIGN.md) §13 are built and
gone from this file entirely.

---

# What is left

## 30. Running the passes with your own API key

**Next.** The passes (`/transcribe`, `/classify`, `/gist`, `/extract-cards`,
`/augment`, `/sort-notes`, `/triage`) run in Claude Code, where you watch
them. With an API key and credits they could also run from the website, in
the background, and be billed to the key. The reason to build it is cost and
reach, not a different way of writing cards.

**One runner, the same prompts.** The runner reads the agent and skill files
in `.claude/` verbatim and gives the model the same tools the slash commands
use: `forge context`, `forge cards new`, `forge units note`. It writes
drafts, notes and suggestions through those verbs, so everything it does is
a file edit you could have made, and nothing reaches Anki (invariants 1 and
2). It lives in its own package, so the core stays free of a vendor in its
dependencies, as the rejection asked.

**Invariant 6 is settled.** It means the guidelines stay in the skill and no
code writes or tidies card text itself, not that no process calls a model
([CONTRACT.md](CONTRACT.md) §6). The runner is on the right side of it as long
as it loads the skill unchanged and writes through the verbs. What is left to
change when it lands is [DESIGN.md](DESIGN.md) §2, which still says the Python
contains no LLM API code.

**Billing in the website.**
- Every call is one line in `.forge/usage.jsonl`: when, which pass, project,
  model, input, output and cached tokens, whether it was batched, and the
  cost from a price table in `forge.toml` (prices change, so they are config,
  not code).
- A usage page: spend by day, pass, project and model, and the number that
  matters, **cost per approved card**, since a pass that writes cards you
  reject is more expensive than its tokens say.
- A run says what it will cost before it starts ("about 40 units, 180k input
  tokens, about $2.10") and asks, like a write does. Budgets in `forge.toml`
  (per day, in total) stop a pass part way and say so.
- The key is read from an environment variable the config names. It is
  never written to a file.

**Batching and context, the bulk of the saving.**
- **Message batches** for what does not wait on you. Transcription,
  classification, gists, stubs and augmenting are independent per unit or
  card, so they go as one batch at about half the price, and the result is
  read when it lands. Passes that talk to you (`/triage`, `/sort-notes`) stay
  live.
- **Prompt caching.** Order a request so the part shared across a run comes
  first and the unit comes last: the skill, the project's conventions and
  the page window, then the unit. A section's units share a window, so group
  by section and the window is paid for once.
- **One window per section**, not one `forge context` per unit. Today each
  writer re-reads the same eleven thousand characters for every unit on a
  page.
- **A model per pass**, from the agent's own frontmatter: the small model for
  gists and classifying, the large one for card writing.
- A cheap first pass can decide whether an expensive one is worth running:
  skip units `/classify` already proposes to skip.

**Order of work.** The usage log and its page first, since they are useful
for the passes you already run if the runner writes them too. Then one pass
end to end (`/gist`, the smallest), then batching, then the writers.

## 27. Documents nobody marked up

The path for a PDF with no Zotero marks is deprecated as it stands, and it
needs a rework before a new source goes through it. Today that path is
`extract/pdf.py`, frozen (§9) and fitted to the Matrix Cookbook, with
`forge audit`, `/transcribe` and `units classify` checking its output after
the fact. Every project added since reads a source marked up in Zotero, or
has no document at all.

A source marked up in Zotero is not part of this. A mark is a unit
already, with its own geometry, and an image or area mark is a figure unit.

What the rework has to answer, collected from the sections it replaces:

- **Segmenting a book that is not the Cookbook.** A model reading page
  images and reporting `(kind, label, page, bbox)` was the plan once (§5,
  dropped). Whatever is built keeps three things: the locator generalises
  by a shim, so `pdf.py` is never edited; the 1..N contiguity check runs
  per label family; and extraction produces units, never cards.
- **Figures and anything that is not a text block.** `page_blocks()` skips
  every block whose `type != 0` and never reads `page.get_drawings()`. A
  diagram never enters the ledger, and an equation set as an image or drawn
  as vectors is lost without a word. TeX draws fraction rules as thin filled
  rectangles, which is a signal for maths that does not depend on font
  names.
- **A line ending in a binary operator cannot end an equation.** Every
  continuation line in the Cookbook's §6.2 and §7.7–7.9 ends in `×` or `+`.
- **Agreement between two extractions.** The equation number is an exact
  join key. A second pass that reads the *page*, never our crops, and is
  joined on it checks the first. A round trip, rendering `tex_auto` with
  KaTeX and comparing it with the crop, is the only check that catches a
  wrong transcription rather than a missing equation. A coverage check asks
  whether every named statement on a page is inside a unit.

## 35. Course material without Zotero

A course produces a dozen exercise sheets, quizzes and slides, each used
once. One Zotero item apiece buries the library, and none of them is a work
to cite. The deck still wants cards from them.

**Decided: marks in the PDF, made with the browser's own tools.** Firefox and
Chrome annotate a PDF and save a copy, so the app gets no annotation editor,
which would be rebuilding Zotero's reader. A Zotero item for the course with
the sheets as its attachments also works today, but it leaves the PDFs in a
synced library. It stays the fallback.

A source's parts are its files, and a mark's section is the PDF's outline or,
when it has none, the attachment's title, so each sheet is a row in the
section filter. A local file declared with `[[sources]] files = [...]` has no
door to units today: `extract/pdf.py` is fitted to one book and looks for
numbered equations (§27).

**Why it is small.** `Mark` is not Zotero-shaped, and `units_for` in
`extract/zotero.py` already turns a list of annotations and a scheme into
units. What is missing is a producer that reads a PDF's annotation layer into
the same objects.

**Spike first.** What each browser writes decides which of its tools are
supported, and nobody has checked. Annotate one page in each browser with a
highlight, a typed note and a drawn rectangle, save, and read what PyMuPDF
sees: subtype, colour, quad points, contents and name.

- Is a highlight a `Highlight` with quad points, or ink?
- Does a comment survive the save?
- Which colours exist, and do they map onto the scheme's names?
- Does a viewer keep annotation names when it saves again?

**What to build once the spike has answered.**

1. **The reader.** A new module under `extract/`, never `pdf.py`. The kind
   comes from the subtype, the colour is the nearest name in the scheme's
   palette, the covered text comes from the quad points through the page's
   text layer, and the comment from `/Contents`. The key is the annotation's
   `/NM` when it has one, otherwise page, box and kind, so reading a file
   again adds nothing twice and the rules for marks that vanished apply as
   they do for Zotero. The scheme, the page-width crop of invariant 8, the
   marks window and triage then work unchanged.
2. **A folder as a source.** `files` is an explicit list, so every new sheet
   is an edit to `project.toml`. A `folder` key, or globs in `files`, makes a
   new sheet a file dropped into the folder, and `forge sources update` picks
   it up. The file's name is its section.
3. **Freehand highlighting.** A stroke drawn over a line of text is ink, not
   a text selection. It should count as a highlight over the text under it.
   `Unit.drawn_box` assumes a rectangle dragged round a figure, and a stroke
   across one line is a thin strip.
4. **The round trip.** A browser saves a copy and writes nothing back to the
   project, so the folder is watched. A file that changed is offered for
   re-reading on the setup stage, the way the page already notices changed
   files. The app adds one link that opens the document in the browser's own
   viewer.

The scheme tables are called `zotero`. Local PDFs either reuse them or they
get a neutral name, which is a small decision to make with the reader.

**Not planned: drawing a box in the page.** The browsers' draw and rectangle
tools make the area mark, which is what it would have been.

**Open questions.**

- What a card from an exercise asks. The card-writing skill is written for
  identities. An exercise yields the method, or the one step that is not
  obvious, and the numbers are not worth a card. That is a paragraph in the
  course's `conventions.md` first, and in the skill once it holds across
  courses.
- Sheets with no solutions. The writer would have to solve the exercise. A
  step the source does not state belongs in `## notes`, as invariant 7 asks of
  an added condition.
- Dropping a course after the exam. `forge sources remove` refuses while
  cards stand on a source, and a picture card renders from its document, so
  the PDFs stay as long as the cards do.

## 31. A graph that separates what is not connected

`graph.py` places a node at its layer (the longest path from a card with no
prerequisites) and its row by study order, across **every** card at once.
Two components with nothing between them therefore share columns and
interleave, and a single stray `requires` joins two clusters into one tangle
with no way to see which edge did it.

Established ways, in the order to try them:
- **Lay out each connected component alone, then pack them.** The standard
  fix: Graphviz packs components, and ELK's `separateConnectedComponents` does
  the same. Each component gets the layered layout it already has, the
  component rectangles are packed side by side or in rows, largest first, and
  a gap between them says "these are separate".
- **A real layered layout inside each** (Sugiyama: rank, order to minimise
  crossings, then place) in place of "row by study order", which keeps the
  queue's order and ignores crossings. Dagre or ELK in the browser do this; the
  study order stays as the tie-break.
- **Bridges and articulation cards.** An edge whose removal splits a
  component, and a card whose removal does, are the "single links that mess
  things up". Find them with Tarjan's algorithm (linear), draw bridges
  differently, and list them: "this one `requires` joins 14 cards to 9".
- **Components as a first-class list.** A side panel of components with their
  sizes, click to focus one and fade the rest, and the isolated cards counted
  in a line rather than drawn as dots (the canvas already hides them by
  default).
- **Collapse.** A component (or a cluster by section) folded to one box that
  opens on click, for a deck with hundreds of cards.

Nothing dragged is touched: `graph.json` still outranks any computed
position, and a packed layout is the starting arrangement only.

## 14. A visual pass, and a theme you can swap

Work for the time between features: none of it changes what a command does.

**Built:** the colour seam. `static/theme.css` holds every colour and loads
before `app.css`, which holds none outside Zotero's palette, and
`tests/test_theme.py` keeps it that way. A control in the top bar cycles
system, light and dark, applied before the first paint.

**Left, the half that needs eyes:**

1. **One type scale, one spacing scale, one radius set.** Mechanical. The
   type scale and radii are measured; spacing is not a scale at all yet.
2. **Density per surface.** A rail, a card and a document are three
   densities, stated once rather than per rule.
3. **Borders.** Nearly everything is a 1px hairline, including things that
   would read better grouped by space.
4. **The empty states.** Each panel says "nothing yet" in its own voice.
5. **One design language for controls.** How an input, a choice, a switch
   and a button look, and how a value shows where it came from: set here,
   inherited, or a default nobody chose. The settings tables, the card
   editor, the command builder and the triage chips each answer it
   differently now.
6. **Clutter.** A line of standing prose earns its place when it says what
   the control cannot: what a command will do to your files, why a pass is
   missing.
7. **A narrow window.** Nothing overflows at 1024px, but both rails keep
   their remembered widths and leave the deck about 290px. Folding a rail by
   width has to survive the window growing again: remember a fold done by
   hand, treat a fold done by width as temporary. A decision, not a patch.
8. **A theme picker.** The seam makes a theme one file of the names
   `theme.css` declares. A picker would offer several, each such a file,
   and keep the choice the way the switch does.

## 16. Pictures that are not crops

A card gets a picture by naming a unit, and the crop is rendered from the
source document. That covers every picture a book already prints, and nothing
else. Three cards in the Krause deck describe in words a picture that would
say it faster: the Laplace density card, whose prose compares its tail to a
Gaussian's; the multivariate Gaussian density card, whose sublevel sets are
ellipsoids along the eigenvectors of $\boldsymbol{\Sigma}$; and the law of
total variance card, whose intuition is a picture of scores grouped by class.

Two routes, and they differ in what they give up. **Drawn here**, from TikZ or
an equivalent carried in the card file and compiled on the way to Anki. The
card keeps source rather than an image, which is the property the crop path
already has: re-rendering fixes every card that shows it, and nothing binary
enters `cards/`. The cost is a TeX toolchain wherever `anki push` runs.
**Fetched**, from a URL in the picture reference. Cheap, and it gives that
property up, because the far end can change or vanish and the licence belongs
to somebody else.

Three things to settle either way. Where a drawing lives, since a TikZ figure
is longer than any section a card carries now. Whether `check` can refuse a
picture it cannot draw, which it already does for a crop. And what
`anki push` uploads, because Anki's media folder is one flat namespace and a
generated picture needs the same `forge-<uid>-<n>` naming a crop gets.

**The drawn route is the one wanted.** The card writer writes the figure as
TikZ, or another text format a TeX toolchain compiles, the same way it
writes the card's LaTeX, and the figure is reviewed with the card. Finding
the figures a book prints, when nobody marked it up, is §27.

**Trigger:** a card whose `## prose` is describing a picture in words. The
three Krause cards above have met it already.

## 24. Decks for facts many sources restate

Probability and calculus facts recur across the books and papers here.
Later: a project per subject holding them, and a pass that moves cards in
and merges duplicates. Three facts to plan around. A merged card cites
several sources, which `unit:` already allows as a list. A uid is the
note's identity in Anki, so the surviving card should keep one of the
originals' uids to keep its review history. And `anki push` deletes
nothing, so the note a merge retires stays in Anki until removed there.

## 4. Publishing, what is left

**The demo recording.** `assets/make_assets.py` carries the shot list in its
docstring. It cannot be scripted, because the interesting part is the pace
of triage and no script knows how long to pause.

**Half of this does not run without Claude Code**, the flip side of having no
LLM code in the tool. The committed ledger and the `.apkg` export are the
mitigation: they show the output without running the half a stranger cannot.

## 11. Pulling context from Obsidian notes

**Blocked on the vault.** Nothing here can start until the Obsidian vault is
reachable through Nextcloud, and it is a large piece of work after that.

`forge context <unit>` hands a card writer the page a unit was printed on and
the conventions the source declares. What it cannot hand over is the note you
already wrote about this material, which is where your notation, your worked
example and the thing that confused you the first time live.

The shape that fits is a vault path in the config, with `context` adding the
notes that match the unit, by title, by tag, or by a link to a term the gist
names. Read-only, the way the Zotero client is. A third input beside the crop
and the conventions, not a replacement for either.

Two rules make it more than a file read:

- **A note of yours is not the source.** Invariant 7: a crop is authoritative
  for what is printed and silent about the rest, and a note is firmly in the
  rest. What a card takes from one belongs in `## notes`, the way a web
  lookup's contribution does.
- **It is a permission, not a default**, for the reason `web` is already per
  source and per unit: whose words may reach a card is a decision somebody
  makes.

Not to be confused with carding the vault itself. Notes as a *source* is a
much larger feature: files nobody segmented, with no page and no bbox, so
every assumption `locator` makes stops holding.

**Trigger:** the first card whose conventions you type out of a note instead
of reading off the page.

---

# Built

## 1. The dependency canvas

At `/graph`, per project; `[app] graph = false` turns it off. `graph.py`
builds and lays out the graph with no app in it, `graph.js` draws it, and
`projects/<name>/graph.json` keeps what you dragged. An arrow is a
`requires`, drawn by dragging between two cards. Ctrl and the wheel zoom
about the pointer. Nothing more is planned.

## 2. Two audit checks that would have caught dropped content

In `audit.py`, over units still waiting for a decision.
`fragment-suspected` is an unnumbered crop within a line of a numbered one in
the same column; `numbered-no-relation` is a numbered unit whose
transcription states no relation. Against the Cookbook ledger they flag 20
and 6.

## 3. Small and named

The `§` prefix on section labels stays: it is in `source:`, which is hashed.
`front_char_cap` may be set per project. The card-writing skill has a worked
`intuition` example.

## 10. Projects, sources and topics

A deck on a subject where no book is canonical, beside the decks that have
one. The vocabulary is in [STYLE.md](STYLE.md): a **project** is a folder
with one ledger, one deck, one `conventions.md` and one graph; a **source**
is one book, paper or website it reads, a `[[sources]]` table; a **topic**
is a heading in `topics.md` with an ask and an outline under it.

- **Three doors into one ledger.** `units extract` segments a document,
  `zotero import` reads marks, and `units add` (what `/propose` uses) makes
  a unit where there is nothing to segment. After the ledger nothing asks
  which door a unit came in by (invariant 3).
- **Properties, not kinds.** No stage branches on what kind of source it
  has. Each decides from what a unit, card or source *has* (a crop, marks,
  references) and from what was *decided*, a setting that falls back from
  the unit to the source, the project and the repo.
- **Where a thing lives.** TOML when Python branches on it; `[conventions]`
  for a short fact handed to a card writer verbatim, of which only `layout`
  is acted on; markdown for prose. Anything may be overridden lower down
  unless two cards in one deck would then mean different things without
  saying so: a convention is declared where it is true and does not
  cascade, and reading settings stop at the source.
- **Extracting is a permission.** A source is authoritative when units are
  extracted from it (the `extract` switch), and one project extracts from a
  given document. Adding a source another project reads takes it as a
  reference. An import declares the source it reads.
- **The setup stage** is where a project is set up: the project, its
  inbox, its topics and its sources, with what to run for each. The project
  picker is a page of its own. References a pass proposes wait in
  `references.md` until you take one, and one site is one source.
- **Taking things out.** `project delete` and `sources remove` refuse while
  cards stand on what they would remove, unless forced.
- **What no rule recovers.** A unit with no authoritative source has no crop
  to check a card against, so the cost moves from triage to review. There is
  no bulk approve, and invariant 1 is why. Ask for less per topic: a topic
  you can enumerate gives proposals worth triaging.

## 12. Running a command from the website

Every command with no model behind it runs from the page, in the
background (`app/jobs.py`). One that only reads runs on a click; one that
writes says what it changes and waits to be confirmed, and the server
refuses it unconfirmed. Which is which comes from the parser, so a row
cannot describe itself as safer than its command. A slash command is still
copied: a model in the loop is something you watch.

A finished run reports in a notification and in the runs window, as a
result rather than a transcript (`run_views.py`): counts for this run and
for now, tables of what moved. The window keeps a history and a builder
(`actions.py`): pick an action, fill its fields, read the command line, run
or copy it. The line is built from the fields and never parsed from text.
Each rail lists what to run next, headed by the command in a word or two
(`anki push test`, `/transcribe`), and opens any row in the builder.

Adding a source has three routes on the setup stage: a page typed in, a
source another project reads, and a Zotero item through the builder.
Cancel is left out on purpose: a half-pushed deck is worse than a finished
one.

## 13. Keeping the suite fast

Four workers by default, and the cap is the point: `-n auto` on sixteen
cores is sixteen Chromes. `--dist loadscope` keeps a browser module on one
worker, so its server starts once. No single test is slow. What costs time
is a broken page: every browser test on it waits out a 30s timeout, which
is why a test that the page loads without console errors is worth having on
every view that runs a script.

Measured on 20 cores: the 143 browser tests are 8% of the suite and about
half its time, and the others take 35 s on eight workers against 67 s on
four. `scripts/affected.py` runs the tests named for what changed, for the
loop, and the full run stays the gate before a commit. Pinning only the
browser modules to a worker (`--dist loadgroup`) hung once and was dropped.

## 15. One word reads, two words write

[VERBS.md](VERBS.md) is the table. `forge units` prints the ledger and
`forge units set` writes to it; `forge anki` is the dry run and
`forge anki push` the push. Each subcommand carries its `effect` in the
parser, and a test refuses a writer reachable in one word. Old spellings
still run, hidden from `--help`.

## 17. Letting an edit reset a card's schedule

`relearn: slightly | more | reset`, set by whoever changes a card already in
Anki: due today with its interval kept, back into relearning, or new again.
`anki push` does it once and takes the key off. Outside `content_hash`.

## 18. Editing a card in the page

`E`, the "edit card" button, or a pencil on a section opens the card's text
in a dialog at that section; `e` still opens the file in `$EDITOR`. Every
section the type allows except `## notes`, each with a KaTeX preview, and
only the sections you changed are sent. An optional note on the card,
prefilled "check my manual edit", is off by default. An edit to an approved
card un-approves it through the hash (invariant 5).

## 19. A unit from nothing, in the page

`+` in triage adds a unit through `ledger.add_unit`, the function
`forge units add` uses.

## 20. Handing a project a pile of notes

The project's inbox, on the setup stage: things you want in the deck
without knowing where. `/sort-notes` gives each waiting dump to the
`note-sorter` agent, which writes under the dump where each piece went. A
dump is placed one of three ways, chosen when you add it:

- **propose**, the default: `@me` notes on the cards a piece bears on, new
  units in triage;
- **modify existing cards** (` · write`): the cards are edited, with a `resolved: inbox
  <stamp>: ...` line saying what was asked and done, and anything new is
  queued and carded by the `card-writer` in the same run;
- **both** (` · both`, the two boxes ticked): edited where the change can be confirmed
  and the card still asks the same question, proposed otherwise.

Nothing a dump edits is pushed: an edit takes the approval back, and the
change record (§21) shows what moved and names the dump.

On the page the inbox is two collapsible lists, unsorted and sorted. A
sorted dump lists where each piece went, with a link to each card and unit,
and can be put back to unsorted. There is no third state.

## 21. What a pass changed, card by card

A local record per card in `.forge/changes/`, not in git: a snapshot when a
card is written, when the review page first draws it, and at each review
decision. The review page compares the file with the last snapshot and
shows what moved at the top of the card's aside: the keys, a line per
section, the `resolved:` lines added, and where it came from when something
says so (the page's editor, an inbox dump, a settled `@claude` note,
`/augment`). "changed since decided" in the review rail lists those cards.
`forge cards --changes` prints the same.

What moved is a list, one entry per look: each time the record looks at a card
and finds it changed (the review page drawing it, `forge cards --changes`, the
editor saving) the difference is filed as an entry with when and from where. Two
`@claude` passes with a look between them are two entries, each with the
`resolved:` lines it added; two with none between are one, because nothing sees
an agent's edit as it happens. A decision files the entries into that round of
the history and starts again. The newest settled line is shown open.

## 22. A deck per topic inside a project

`[decks.by_topic]` maps an ask to a deck. Most specific first: tag, topic,
type, then the project's deck.

## 23. The docs against the style guide

Done: every document checked against [STYLE.md](STYLE.md). The README's prose
is the author's (§4).

## 25. Windows the document's outline defines

`context_pages` takes `section`, `chapter` or `part` as well as a number,
read off the PDF's own outline (`outline.py`) and named by shape rather than
depth. Every place the size is chosen says the entry and its printed pages.

## 26. A project's name

A project is shown by its `title`, renamed on the setup stage; the folder
name stays, since it is in every unit id. A Zotero project's deck is pinned
on the first rename so its cards do not move. The setup stage is two
columns where there is room, and the top bar is the same on every page.

## 28. A project's settings in the page

The project pane edits what `project.toml` holds that needs no document to
be right: citation, labels, decks, what a card writer gets, the front cap,
the study order and `[conventions]`. A source's panel edits its name,
citation and address beside how it is read. Line by line into the file,
checked by loading the config back. A project declared in `forge.toml`, the
repo-wide settings and a source's files stay file edits.

## 29. The review panel and Anki disagree about newlines

`render_body` now applies the rule `to_anki_html` has: a newline outside maths
and outside fenced code is a `<br>`, and the blank line beside a fence is not.
Found on `a75c32`, whose back puts the gain and the update on separate lines.
It was right in Anki and run together in the page, so the card approved was
not the card read (invariant 1). `test_the_panel_breaks_lines_where_anki_does`
holds the two renderers to the same count of breaks.

## 32. The review page

The aside beside a card is a head (status, gist, uid, whether `check` is
clean) and panels: notes, what changed, what you wrote in Zotero, check, the
source crop, details. Each folds, moves by its grip or Alt and the arrow
keys, and is remembered in the browser for every card. The list is in
Anki's study order, the one the "order n/m" badge reports, so `j` walks the
queue; `j` and `k` both skip a card the filter no longer shows. `/` opens the
find palette (`finder.js`, shared with the graph's card picker): it narrows as
you type over every card in the project, Enter jumps to the first, and
Shift+Enter keeps the query as a filter on the list. Words may be anywhere on
a card: text, gist, tags, notes. A status or state row clears on a second click, and
no row means all of them.

## 33. What a card writer sees of your marks

`forge context` hands over this unit's own mark and then every mark inside the
same pages as the text it prints, any colour, each saying what became of the
unit it made (`skipped` is the reader's own "not a card"). The window decides:
a writer given a chapter gets the marks in the chapter. Every mark of a
document is cached at import beside its text (`marks-<document>.json`), so a
colour that makes no unit still counts; before a re-import the unit's own
neighbours stand in. A sticky note's comment is printed whole. The review page
shows your Zotero comments beside the card, read from the ledger.

## 34. Remarks

`projects/remarks.md` is where a pass says something about the tool or its
instructions rather than about a card: a brief that arrived cut off, a rule
that made a card worse. `forge remarks add` writes one, `forge remarks` lists
them, and each agent's instructions say when. Read it when planning, fold
what is worth keeping into this file and delete the rest. It sits beside the
projects and not in `docs/`, so what a pass writes never shows up as a change
to commit.

---

# Ideas, not scheduled

## 8. A "daily proof" challenge

One theorem a day, to reconstruct rather than recall. A **different object
from a card**, which is why it is not another `type`: a card asks for one
answer and is graded in a second, while a proof is a structure whose answer is
a paragraph, and grading that against a stored back is not what makes it
useful.

Two shapes. **As Anki**, a `proof` type: cheap, reuses the pipeline, inherits
the wrong grading model. **As a standalone page**: escapes that model, but is
a second product with its own state. Open first: what the source is, what is
being reviewed, and whether spaced repetition is the right schedule for
something you work through.

---

# What the Cookbook taught us

Measured evidence about the committed ledger, kept because it says which units
not to trust. Every fix would be a change to
[frozen](#9-extractpdfpy-is-frozen-not-deleted) code, so these are closed as
"use a different extractor for that source".

## Multi-line displays get split

`anchored_regions` grows a region only by vertical overlap, and stacked lines
do not overlap, so a three-line display becomes three units: two unnumbered
fragments and one carrying the number. The audit cannot see it: the crops are
adjacent rather than overlapping, so `crop-overlap` stays quiet, and the
numbering oracle is satisfied because the number exists.

Measured by the `/classify` pass over all 117 unnumbered units. Of the ~100
skips proposed, the large majority are this one defect, concentrated rather
than a long tail:

| where | what |
|---|---|
| §8.2.4 quartic forms | **25 of §8.2's 36 units** are fragments, from seven identities of 2–5 lines |
| §6.2 cubic forms | one equation into three units, another into two |
| §7.7–7.9 | Student-t / Wishart / inverse-Wishart densities, cut mid-formula |
| §2.8 | a four-crop chain, all of it equation 143 |
| §2.4, §2.5 | number on the *last* line, continuations orphaned above it |

Orphans appear both above and below the numbered unit, so any fix handles both
directions. Not everything unnumbered is a bug: §11.1 and §11.2 genuinely
state long runs of unnumbered moment identities.

**Partly mitigated.** The triage view draws each crop with `crop_context`
points of surrounding page and the unit's own box on it, so a split equation
shows its missing lines just outside the box.

## The three failures that do not announce themselves

**A bbox that clips mid-glyph.** Unit `9.2:409` has a box tight enough to
shave the left stroke off `W_N`, so the crop reads `V_N`: a different and
perfectly legible symbol. A transcriber reading only the crop records it with
full confidence, the KaTeX gate accepts it, and the card is wrong forever. No
check on the *text* can catch a faithful transcription of a corrupted
*picture*, which is why the crop stays beside the transcription.

**A bbox that clips the relation.** §9.1.5 produced ~77pt-wide boxes cutting
`C1 =` off the front and the trailing subscript off the back. Worse than a
split, because the crop still looks complete.

**Content in no unit at all.** Equation 27 is three lines; two survive across
`1.2:p7y169` and `1.2:27` and the third is nowhere. In §6.2, `p36y310` has a
bbox starting after the `=`, so the whole left-hand side is in no crop. And on
the page-5 notation table, a two-column layout, some bboxes cover only the
description column: `anchored_regions` reasons about vertical bands and has no
notion of a column.

**One outright bug.** `matrix-cookbook:3.2:178` holds nothing but the number
`(178)`; the content is in its unnumbered sibling `3.2:p20y147`.

## §12.1 (Appendix B) should probably not be units

The proofs appendix is continuous multi-line algebra rather than a list of
identities, and the segmenter tears fractions, parentheses and summation
limits across crop boundaries: 11 of its 35 units needed bracket-splitting or
were pure debris. The transcriptions are faithful, but they are proof
*fragments* and the content is the chain. Skip it as prose, or segment it by
proof block. Either way, do not author cards from §12.1 as extracted.

## 9. `extract/pdf.py` is frozen, not deleted

Not because something replaced it: because every heuristic in it is
specialised to one book, so extending it means teaching that book's habits to
the next one. How specialised, by ablation:

| | equations found |
|---|---|
| as shipped | 571/571 |
| without math-font detection | 571/571 |
| without equation numbers | locators gone; 936 unverifiable regions |
| without either | **9** |

Two producer-specific signals carry everything: a right-margin `(61)` and
Computer Modern font names.

**Frozen means frozen.** Do not fix its heuristics; when a shared type changes
under it, give it a shim. What it owes is one function, `segment()`, returning
units whose `locator` carries `section`, `equation`, `page` and `bbox`, pinned
by `tests/test_extract_pdf.py`. Everything valuable lives elsewhere and is
unaffected: `render.py` crops from `locator.bbox` alone, `audit.py`'s oracle is
a property of the *document* and scores any extractor, and `ledger.py`'s ids
come from the book's own numbering. **Delete it** if it ever costs something
real: a shared change it cannot absorb behind a shim, or a second book where
it is chosen and found to mislead.

The path it serves, a PDF nobody marked up, is deprecated as it stands and
waits for the rework in §27.

---

# Considered and rejected

The reason is the part worth having later.

**A database.** The files *are* the product: a card is a markdown file you can
read in a diff, and the ledger is JSONL so a re-segmentation shows as
reviewable lines. What scale wants is an **index, not a store**: sqlite under
`.forge/`, gitignored, rebuilt when stale. Build it when a units page render
passes ~300 ms, which at 751 units is several books away.

**Triggering Claude from the website.** No supported way to push a prompt into
a running session, and a button that writes cards with nobody watching is what
invariant 1 exists to prevent. Superseded by copyable commands.

**A collection of documents inside one source.** Each paper is a first-level
source instead, so `locator.document` would exist for zero instances.

**A subdeck per paper.** Fifty three-card decks and fifty deck configurations,
for something a tag expresses better. Subdecks are for a different new-card
rate.

**Mermaid diagrams in the README.** Rejected in favour of committed images and
a helper script: more visualisations are coming and they will not all be state
machines.

**pdf.js in the triage view.** A whole-page render with the unit's box drawn
on it answers the same question and adds no dependency. Reconsider when you
want to drag a box in the browser to create a unit.

**BYOK and LLM calls in the tool.** Was rejected here, and is §30 now: there
are credits to spend, which was the missing reason.

**A hosted live demo.** The app writes to the local filesystem, so a public
instance is either read-only, and therefore not the thing, or a vandalism
target, and it would need the documents hosted.

**Docling** (and marker, MinerU). Measured on this book: 19.7 s/page against
0.18, five regions where we find twenty on the packed page, and no LaTeX
without a second model. Its advantage is generality, which the rework in
§27 has to find more cheaply. It would earn its place on a **scanned** PDF,
which is also §27.

**Auto-generating units from free prose.** A prose unit must be triggered by a
Zotero annotation. This is what demoted §5.

**A model page extractor** (§5). A model reading page images and reporting
regions was the plan for every book after the Cookbook. Zotero marks carry
their own geometry and prose stopped being segmented, which left it one
case: a formula reference nobody marks up. That case is §27.

**A placeholder `conventions.md`.** An empty one is indistinguishable from a
real one to everything that reads it, and would silence the warning it should
raise.

**An htmx or SPA rewrite.** FastAPI plus Jinja2 is already the simple
framework, and an auto-updating counts strip is twenty lines of fetch and
swap. Adopt htmx if that code gets written a third time.
