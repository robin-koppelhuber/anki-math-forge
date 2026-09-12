# Roadmap

The milestones in [proposal.md](proposal.md) §13 (M0–M6) are built. This is
what is left, and what we chose not to build and why.

Four parts. **The plan** is decided and in order. **Defects** are measured on
the Cookbook and still open. **Ideas** are recorded so they are not lost.
**Rejected** carries the reason, which is the part worth having later.

[PLAN.md](PLAN.md) is the planning round that produced the first part, closed
on 2026-09-11. It holds the questions and the answers; this file holds the
work.

---

# The plan

## 1. A second source, and why everything else waits

Every abstraction here has exactly one instance: one source, one deck, one
layout, one conventions file, one locator built around equation numbers.
`deck_for`, `layout_for` and `order_for` each resolve one value, so nothing
tests any of them. **A second source is not a feature, it is the evidence** that
any of this generalises, and it is worth more than every polish item combined.

The order, and the reason for it:

0. **The two names Anki already holds (§5)**, because they get cheaper to change
   the fewer notes exist, and §2 is about to create more.
1. **Zotero (§2)**, because a Zotero source arrives with geometry already
   attached and needs no segmenter at all. It exercises units, triage, cards
   and sync against a genuinely second source without touching extraction. The
   cheapest possible proof, and it is the reading workflow that already exists.
2. **The model extractor (§7)**, because it is the risky half, and Zotero buys
   time for it.
3. Everything else per-source (§3, §4) falls out of those two, and the
   source-facing half of the rename (§5b) rides along with publishing.

Publishing (§9) comes after. A README that says "two sources, one of them
prose" is a different document from one that says "one book".

## 2. Zotero as a source

Highlighting a passage while reading **is not the triage step**, and this
section used to claim it was: an imported unit arrived `queued`, with a human
decision supposedly already attached. Two things were wrong with that. Marking
says "this mattered while I was reading" and triage says "this is worth a card,
on its own, out of context" -- and the second is a judgement you can only make
once you see the mark beside its neighbours, which is exactly what the triage
view is for. It also removed the only gate between an import and a full card
queue: twenty units landed ready for `/extract-cards` with nobody having looked
at them. **Every unit arrives `new`, whichever door it came in by.** That it
lands on the existing state machine without bending it is still the test of
whether a feature belongs here -- and bending it was the tell.

**Some marks start a unit; the rest are context.** Which ones is yours to say,
in `[zotero] triggers`, because it is a fact about your colour scheme rather
than about this tool. Measured on the first real paper, the two are not close:

| colour | n | median words |
|---|---|---|
| green | 10 | 20 |
| note | 8 | 16 |
| magenta | 26 | 10 |
| orange | 14 | 4 |
| purple, blue | 44 | 2 |

A two-word term is not a card. It *is* worth reading next to the claim it
belongs to, so it travels with the unit as a `Mark`.

**Nothing here knows what a colour stands for, and nothing should.** The spread
above is evidence that a scheme *exists* and varies, not a model to build in:
across the two documents the same colour ran a median of twenty words in one
and two in another. An unmapped colour is reported rather than guessed at, the
rule `[anki.flags]` already follows. `[zotero.meanings]` resolves
`kind/colour`, then `kind`, then `colour` -- kind first because Zotero defines
the kinds and you define the colours, so a yellow sticky note reads as a note.

**A mark's meaning is resolved when it is displayed, never stored.** Freezing it
at import meant editing your scheme changed only the units imported since.

**Context is pages, not a curated set of marks.** An earlier version worked out
which marks were nearest in reading order and attached exactly those. That was
the tool deciding what is relevant, which belongs to whoever reads it. A unit
carries the marks on the pages around it (`NEIGHBOURHOOD`, one either side, so
an idea running over a page break survives), and a mark beside two units is no
problem: context is a view, not content.

**Triage wants one page; a pass that writes a card should ask for more.**
`forge context --pages N` widens the text it prints. There is no reason to
be stingy there, since the conditions an identity needs are printed around it,
as often on the previous page as on this one.

**A unit is named after the mark that triggered it.** Zotero's annotation key
is permanent, never reused, and never derived from a position, so marking up
more of a document renumbers nothing. That was the brittleness worth solving.
The document goes on the locator rather than into the name, so re-filing a unit
never renames it.

**Split and merge are the same operation: which marks make units.** This is what
makes the triage view able to disagree with the config without inventing
anything.

- **Split**: name one more colour, or promote a single mark. A second unit
  appears, called after *its* own mark, and the first is untouched. There is no
  id to mint, because the mark already has one.
- **Merge**: stop a mark making a unit. It stays, shown beside the unit that
  remains, and the redundant one goes `skipped`, which is already sticky and
  never re-offered.
- And a card's `unit:` already accepts a list, so two units that really are one
  idea end up on one card regardless.

The marks live on the unit as `marks`: kind, colour, covered text, your
comment, its own box, the source's reading-order key, whether it triggered, and
what you said the colour means. That is a property of a marked-up document, not
of Zotero, so nothing Zotero-shaped reaches the ledger.

**Python speaks it directly**, which reverses an earlier call in this plan. The
rule was "Python never talks to Zotero", aimed at vendor SDKs, credentials and
cloud APIs. Zotero's local API is none of those: plain HTTP on 127.0.0.1, no
key, read-only, and **exactly the shape of AnkiConnect**, which `anki.py`
already speaks natively. A `zotero.py` beside it is consistent with the code
that is already here, and it makes the import a plain CLI verb rather than a
skill. It costs the same precondition `sync` already has: Zotero running, with
its local API enabled, the way `sync` needs Anki running with AnkiConnect.

The MCP server stays useful, but not here: it is for asking about the library
in conversation while writing cards. It is not in the pipeline, so nothing in
`pyproject.toml` changes and no API key is needed to import anything.

**Store what Zotero stores**, field for field, and invent nothing: key, type,
colour, text, comment, page, tags, modified date, and the position if we can
get one (see below: today we cannot). Two traps worth naming once. Zotero's
rects are **bottom-left origin** and `locator.bbox` is top-left, so a
conversion bug there is silent and produces a plausible crop of the wrong
place. And a free-text note carries no document text at all, only your comment,
so for that type the comment *is* the content.

**The PDF and the text layer are cached locally**, pulled once rather than per
view, so crops render without an MCP round trip and card writing has the page
in context. This needs no new mechanism: `sources/<name>/.gitignore` already
ignores `*.pdf`, `*.tex` and `text.md`, and a paper source gets the same file.

**Meaning is configured on two axes, type and colour.** A block per annotation
type with colours inside it, repo-wide defaults under `[zotero]`, overridden
per source. `[anki.flags]` is the precedent for the shape; this needs one more
level than it does.

**Two ways to pull a document in:** a cite key you name, or a configured Zotero
tag on the item, which is how a query across the whole library works.

**Sync, and what happens when Zotero moves under us.** Zotero owns the
annotation's text and geometry; the ledger owns triage state and cards. A sync
fills empty fields and never overwrites `state`, `uids` or `notes`, exactly as
`upsert` already does for re-extraction. When an annotation changes or
disappears **after a card exists**, sync reports it and touches nothing; before
a card exists there is nothing to protect, so it just updates. The report lands
in the sync output *and* marks the unit, because a terminal line scrolls away.
Nothing is ever deleted on Zotero's say-so, for the same reason `sync` never
deletes from Anki.

**Image and area annotations are the existing unit model exactly**: a box, with
the crop authoritative and no text to trust. They need no new thinking, and
they are the first figures this tool has ever been able to hold (§11).

**Deck: one `Papers` deck, with `paper::<citekey>` as a tag.** Not a deck per
paper. The criterion, which is the same one that makes §3 use subdecks: a
subdeck is for a different new-card **rate**, a tag is for **filtering**, and
nobody wants to study Smith 2019 at a different rate from Jones 2021. Fifty
three-card decks is also fifty deck configurations to maintain.

**Each Zotero item is a first-level source**, not a document inside a
collection. The cost is a picker with fifty entries in it, so the source picker
must become searchable and tag-filterable **before** the first bulk import, not
after. An item is not one *document*, though: see below.

### Measured on the live library, 2026-09-11

Two items: `wegel...2025`, a preprint, and `wainwright...2019`, the book.

**An item is not a document.** Wegel holds a main PDF, an appendix PDF and an
HTML snapshot. Wainwright holds **fifteen chapter PDFs**, with annotations in
two of them. So `locator` needs the attachment key after all: it was dropped as
a field for zero instances, and the first two items produced two. Page 17 of
`1 - introduction` is not page 17 of `3 - concentration_of_measure`.

**Query annotations per attachment, not per item.** The item-level call
returned all 41 without saying which PDF each came from; per-attachment queries
gave 29 + 12 = 41, so the attribution is exact, just not from the obvious call.

**The MCP tools drop the geometry; Zotero does not.**
`zotero_get_annotations` renders markdown (type, key, colour, page, text,
comment) on both routes, with no rects. Zotero's own local API carries the
whole record:

```json
"annotationPosition": "{\"pageIndex\":7,\"rects\":[[360.03,626.68,524.41,640.31], ...]}",
"annotationSortIndex": "00007|000466|00201",
"parentItem": "ZIETASLD"
```

So **a Zotero unit is crop-backed like any other**, and invariant 7 holds
unchanged. There is no text-only degraded case to design for. Three
consequences:

- **`parentItem` on the annotation is the attachment key**, which settles the
  document attribution with no per-attachment queries at all.
- **`annotationSortIndex` is `page|offset|y`**, so reading order arrives for
  free and feeds `order = "printed"` without inventing anything.
- **A highlight can carry several rects** (one per line it spans), so a unit's
  bbox is their union. And the rects are bottom-left origin against our
  top-left, which is the silent conversion bug named above.

The file itself is at `<data dir>/storage/<attachment key>/<filename>`,
verified on disk, so `extract/render.py` crops it unchanged: it wants a path
and a bbox and does not care where either came from.

**The local API covers the whole feature**, verified endpoint by endpoint:
`?itemType=annotation` for the payload, `/items/<key>` for metadata,
`/items/<key>/children` for a book's chapter PDFs, `/items/<key>/fulltext` for
the text layer (`content`, `indexedPages`, `totalPages`), `?q=` for title
search, `?tag=` for a tagged pull. The `parentItem` query filter is ignored, so
the import scans annotations and buckets them client-side: 1206 annotations in
13 requests here, a few seconds.

Cite keys are the one thing that needs Better BibTeX rather than Zotero itself,
and they resolve locally once the API is on.

**Colours are hex** (`#2ea8e5`, `#f19837`, `#a28ae5`, `#e56eee`), from Zotero's
fixed palette of eight, so the mapping keys on hex with names as aliases.
**Types seen:** 96 highlight, 8 note, 1 image.

### What the two routes need before either is usable

- **The MetaMCP container is missing the `pdf` extra.** `zotero_get_page_layout`
  answers *"PDF layout detection requires PyMuPDF. Install it with: pip install
  zotero-mcp-server[pdf]"*, which also takes out `zotero_read_pdf_pages` and
  `zotero_get_pdf_outline`: the geometry tools, and the ones this needs. Fix is
  one line: `pip install --no-cache-dir "zotero-mcp-server[pdf]"`.
- **Zotero's local API is off.** `/api/users/0/items` answers
  `403 Local API is not enabled`, while `/connector/ping` answers 200, so Zotero
  is running and only the setting is missing (Settings > Advanced). Until then
  the local server starts happily and reads an empty library.
- **Tool names differ by route.** MetaMCP prefixes them
  (`zotero-mcp__zotero_get_annotations`); the local stdio server does not. This
  no longer touches the pipeline, but it bites anything written against the MCP.
- **Cite-key lookup needs the local route.** Both keys came back "No item found"
  through the web API, because Better BibTeX keys live in BBT's own database and
  not in Zotero's. Confirmed working locally once the API was enabled. Title
  search works either way.
- **The local API must be enabled** for any of this: without it the server
  starts and reads an empty library, which looks like an empty account rather
  than a missing setting.

**Prose cards are gated behind this.** A unit from free-form text must be
triggered by an annotation; nothing auto-generates units out of prose (§7). A
unit can still carry cards of both kinds, which needs no machinery at all: a
card is already not one-to-one with a unit, and `uids` is already a list.

## 3. Card `type`: `identity` and `intuition` (built)

A second value for `type`, for the free-form card that explains rather than
states. `verify` never applies to one. The card-writing skill branches on the
one key it already reads.

**A deck per type, as subdecks under a shared parent**, because here you *do*
want a different rate: five mechanical restatements a day is comfortable and
five pieces of intuition a day is not, and a per-deck new limit is the only
mechanism Anki offers for saying so. Studying the parent combines them again.

```toml
[sources.<name>.decks]
identity  = "Statistics::Wainwright::Statements"
intuition = "Statistics::Wainwright::Intuition"
```

**One axis, not two.** An earlier draft had a separate `kind` key next to
`type`; it is not needed, and two coarse keys meaning almost the same thing is
how a format rots. **Zotero's annotation type is a different thing entirely**:
unit metadata, recorded and filtered on, never chosen by us (§8).

**One note type, not two**, with unused fields left empty as `Uses` and `Proof`
already are and the template rendering them conditionally as it already does.
Which makes the note type's current name wrong, see §5.

Adding a type does not open the door to `type: proof`. That is a different
object and §15 says why.

Changing a deck does not move notes already in Anki, so a source's `type`
mapping wants deciding before its first sync. Free for a new source.

**Built:** the type, its section whitelist (no `verify`, no `conditions` on an
intuition), `verify` skipping one outright, the `type::` tag, and `[decks]` in
a source's own file. Adding the tag means the next sync updates all 108
existing notes, which is tags only and touches no scheduling.

**Still open:** nothing writes an `intuition` card yet. The card-writing skill
is about identities throughout, and teaching it the second kind is a change to
guidance rather than to code -- it belongs with the first prose source that has
marks worth explaining.

## 4. Per-source configuration (built)

`[sources.<name>]` has moved out of the root file and into the source's own
folder:
**one file per source, holding both the machine keys and the conventions
prose**, as TOML between `+++` fences with the prose below.

TOML rather than YAML frontmatter, which was the first attempt: every key up
there overrides one in `forge.toml`, so the two should be the same
language and a block should copy between them unchanged. TOML is also stricter,
and in YAML a tag or colour written `no`, `on` or `y` is silently a boolean.

Why: fifty papers each a first-level source (§2) makes a single root file
unreadable, and a source's conventions belong beside the source rather than
split across two files by kind. Defaults still cascade: repo-wide first, then
the source's own file.

Sources are discovered by directory, so the root file stops listing them.
Sources gain `tags`, which is what makes a fifty-entry picker usable.

CLAUDE.md's **Conventions** section described the old two-file split as a
deliberate decision. It was, and it stopped being true, so it was rewritten in
the same change rather than left to contradict the code. `conventions.md` is
still read where a repo has not moved.

**Still open here:** a source's `tags` are stored but nothing filters on them
yet, which §8 needs before the first bulk import puts fifty papers in the
picker.

## 5. The name, and decoupling from it

The project is **`anki-math-forge`**: `anki-forge` is taken. Renaming again is
likely enough that nothing machine-facing should be derived from the project
name at all.

**Hang the durable names on `forge`, not on the project name.** `forge` is the
stem that survived this rename and will probably survive the next, so the
command, the config file, the work directory and the tag prefix use it and stop
tracking the name:

| | now | after |
|---|---|---|
| distribution | `anki-forge` | `anki-math-forge` |
| import package | `anki_math_forge` | `anki_math_forge`, once, mechanically |
| command | `anki-forge` | `forge`, with the long name kept as an alias |
| config file | `forge.toml` | `forge.toml` |
| work dir | `.forge/` | unchanged |
| tag prefix | `forge` | unchanged |
| note type | `forge identity v1` | see below |

### 5a. The two strings Anki already holds. Do this first.

Three strings are written into the collection, on all 108 notes, and they get
more expensive to change with every sync: the note type name, the **card
template name** (which was derived from the note type name, so renaming one
orphaned the other), and `tag_prefix`. §2 is about to
add a second source, so this comes **before** it.

`tag_prefix` already survives the rename untouched. The card template becomes
a constant, `Card 1`, which is Anki's own default and tracks nothing; `sync`
renames a stray one in place, because this note type has exactly one and
pushing under a name it does not have would add a second card to every note.
The note type name needs more:
it is computed as `f"anki-forge identity v{version}"`, so it carries both the
project name and the word `identity`, which §3 makes wrong anyway when one note
type starts holding two card types.

Split it. `[anki] note_type_name` holds a stem that names the *content*, not
the tool, and `note_type_version` stays exactly as it is, because it is the
lever the field-migration errors already tell you to pull:

```toml
[anki]
note_type_name = "Math Card"       # -> "Math Card v1"
note_type_version = 1
```

Renaming a note type inside Anki keeps notes and history. The danger is the
tool quietly creating a *second* one when the configured name is not found, so
`sync` should recognise a previous-name note type carrying our fields and say
so, the way `PREVIOUS_FIELDS` already handles a field migration.

### 5b. The source-facing rename (done)

Done, and backwards compatible on purpose: a rename should not be something
you have to finish in one sitting.

| | now |
|---|---|
| distribution | `anki-math-forge` |
| import package | `anki_math_forge` |
| command | `forge`, with `anki-math-forge` kept as an alias |
| config file | `forge.toml`, and `anki-forge.toml` still read |
| work dir, tag prefix | `.forge`, `forge` -- unchanged, which was the point |

Two occurrences of the old name survive deliberately, and both are data rather
than branding: `notetype.PREVIOUS_NAMES`, which is a string in somebody's Anki
collection, and `config.LEGACY_CONFIG_NAMES`, which is a filename still read.
Sweeping either would break a real repo.

`sync --dry-run` after the rename reports 108 updates, and every one of them is
`+type::identity` from §3 -- the rename itself proposes no change at all. That
is what "nothing machine-facing derives from the project name" was for: the
note type is still `Math Card v1` and the tag prefix is still `forge`.

## 6. Crop context and the whole page (mostly built)

The cheapest useful thing on the list, and it improves the Cookbook too.

`TRIAGE_CONTEXT = 40.0` is a module constant in `extract/render.py` and the
crop endpoint already takes a `context` parameter. Forty points is right for a
one-line display equation and useless for a theorem with a three-sentence
preamble.

- **built:** per source (`crop_context`), with the default raised from 40 to
  90. Generous on purpose: a crop too tight to judge costs a review, one with
  too much around it costs nothing
- **built:** `context --pages N`, defaulting to one page either side rather
  than zero, and a per-document text layer so a source with fifteen chapter
  PDFs has one per chapter instead of an ambiguous `## page 7`
- **built:** every size on the chip, the one in force written out and the rest
  abbreviated -- `context 0 · 1 page either side · 3 · 10 · all` -- each one
  clickable, `c` walking them. A row of bare numbers is five things to decode.
  It also settles a real ambiguity: **the number is pages *either side***, so
  `3` hands over seven, and the chip, the tooltip and the guide all say so now
  rather than leaving it to be inferred
- **built:** how much context is a setting at three levels, most specific
  first: the **unit**, its **source**, the repo. The unit level is the one that
  earns its keep, because triage is where you can see that a theorem's
  hypotheses are two pages back and no per-source default knows that. `c`
  cycles this page / 1 / 3 / 10 / all, and the badge only appears once a unit
  asks for something other than the default
- **built:** `crop_width`, and a default that reads the geometry rather than a
  setting. A segmenter that found a display equation stopped where the equation
  stopped, so the box's left and right edges are an answer. A **mark's** box is
  the union of the lines a sentence happened to span, so its edges are wherever
  that sentence ran out mid-column -- and a sticky note's box is a 22pt pin in
  the margin, which with 90pt of context cropped to a sliver with every line
  cut mid-word. Marks get the full page width, everything else gets the box,
  and a source overrides either way. `box | page`, refused at load if it is
  neither, for the same reason `layout` is
- **built:** the marks painted back onto the crop in the colours the reader
  used, as real PDF annotations so the blend over text is the viewer's rather
  than one written by hand. The unit's own mark at full strength and its
  neighbours faded, because a page with six highlights on it has to say which
  one the card is about. Faded is **per kind**, not one number: a highlight is
  a band and reads as a tint at a third of the opacity, an underline is a
  hairline and disappears, an area selection is an outline whose interior
  belongs to the figure it points at, and a sticky note has no extent at all.
  Each mark's lines are drawn separately -- their union covers both lines end
  to end, including the half of each the reader left unmarked. About 65ms for
  28 marks on top of the 70ms the document open already costs
- **built:** a red box around the mark the unit *is*. Nothing else on a page
  is red -- the reader's own palette has no red in it -- and the muted orange
  it used to be read as one more highlight among them
- **built:** what the marks *say*, beside the crop -- the sentence each
  one covers and anything written beside it, the unit's own first. Deciding
  whether a marked claim is worth a card on its own is mostly a question about
  its neighbours, and reading them meant opening the PDF. A neighbour that is a
  unit in its own right is flagged and links to it
- **built:** the marks grouped by kind, collapsible, with the colour's meaning
  shown *once* on the other rail rather than on every row. Thirty marks meant
  thirty copies of one sentence; the swatch is the label, the group heading is
  the kind, and the legend is where a scheme belongs
- **built:** three views of the same geometry, cycled with `p` or the control
  in the corner of the picture: the crop, the whole page, and **every page,
  scrolling**. A crop answers "is this the right region"; sometimes the
  question is what the passage is actually *saying*, and that is three
  paragraphs up or on the page before. Still no pdf.js -- images the browser
  stacks and scrolls is the cheap half of a viewer and all that reading needs;
  pdf.js earns its place when you want to drag a box in the browser to make a
  unit. The page count opens the PDF, so it is fetched when the view is first
  opened rather than for every row of a 750-unit list, and the view lands on
  the unit's own page
- **left:** `+` and `-` in the triage view, to widen without a reload
- **built:** a whole-page toggle (`p`), rendering the page with the unit's own
  box drawn on it

No pdf.js. For the question actually being asked (what surrounds this, did the
segmenter cut it) a marked-up page beats a scrollable viewer, because box and
context arrive in one glance. pdf.js earns its place when you want to **drag a
box in the browser to make a unit**, which is a real future for prose sources
and the first thing a rendered image genuinely cannot do.

## 7. Reading pages with a model

The replacement for `extract/pdf.py` (§13), and the thing that makes a
non-Cookbook source possible. A model reads page images and reports
`(kind, label, page, bbox)` per statement, producing the transcription in the
same pass. Roughly 72 page reads for the Cookbook, and it generalises to
documents no heuristic can touch.

**The locator generalises.** `equation: int` becomes a label with a family:

```python
kind: str = ""     # "equation" | "theorem" | "lemma" | ...
label: str = ""    # "2.4", "61"
```

`pdf.py` keeps emitting `equation: int` exactly as it does and a shim maps it
across, so generalising the locator does not mean editing a frozen module.

There is no `document` field. An earlier draft added one as cheap insurance for
a collection abstraction; §2 made each paper a first-level source instead, so
it would be a field for zero instances.

**The contiguity oracle survives, and that is the good news.** `audit` checks
1..N with no gaps, which sounds like an equation-number trick. It is not:
theorems are numbered contiguously within a chapter, so the same oracle runs
per label family. That is the strongest evidence any of this generalises.

**Only mechanically identified things become units.** Named or numbered
statements: a theorem, a lemma, a definition, a display equation. Free prose is
never segmented, and a prose unit comes from a Zotero annotation instead (§2).
This is a deliberate scope cut and it removes the two hardest pieces of the
original plan: a prose segmenter, and the triage bottleneck that several
thousand paragraph-level candidates would have created.

**Judgement stays where it is.** Extraction produces units, never cards
(invariant 3). `classify` proposes skips and applies nothing; triage confirms.
No new stage, no new state machine.

What each source uses is configurable, so a book can stay on the heuristic.

## 7a. Extraction runs in subagents (noted, not scheduled)

`/transcribe` already dispatches one subagent per section, for a stated reason:
seven hundred crops would fill the main session's context and crowd out
everything else. The same is true of any pass that reads pages, and §7 is
exactly such a pass.

Worth making a rule rather than a habit, so a new extractor is not written as a
main-session loop and then retrofitted. Recorded as orthogonal to what the
extractor does.

**On sharing context between them, honestly:** there is no fork primitive. A
subagent starts with a fresh window, so "load once and fork" cannot be built
here. The two savings that are real are the ones `/transcribe` already uses:
give each agent a **disjoint slice** so no page is read twice, and have the
parent pass a short brief rather than each agent re-deriving the shared
setting. Anything past that would be inventing a mechanism the runtime does not
have.

## 8. Triage and review at scale (partly built)

- **Built: `source.toml` beside `conventions.md`.** They were one file, TOML
  fenced above prose, on the argument that a convention kept away from the keys
  it qualifies is the one nobody opens. What that produced was a file that is
  neither: no editor checks the TOML above the fence *and* renders the Markdown
  below it, so both halves lost the tooling they would have had apart. The
  fenced form is still read, and a folder with both lets the new file win.
  **No placeholder `conventions.md`** -- an empty one saying "nothing recorded
  yet" is indistinguishable from a real one to everything that reads it, and
  would silence the warning it should raise.
- **Built: `carded` and `draft` drawn as one moment.** They are not two steps:
  `/extract-cards` writes the card file and marks the unit in the same call,
  and there is no state where one has happened and the other has not. The
  diagram ran them as a long arrow from the top-right of one lane to the
  bottom-left of the other, which reads as a journey. It is a *split*, so the
  two boxes now sit one above the other, carry the same outline, and are tied
  by the only line in either diagram that is not a transition.
- **Built: the two assistive passes drawn alike.** `/transcribe` fills in what
  a unit says and `/augment` fills in what a card is missing; both are boxes
  hanging off the state they act on, in the same relative position one lane
  apart, because neither moves anything. `/augment` was not in the diagram at
  all, which made the card lane look like two keystrokes and a sync.
- **Built: a floor under the colour scheme.** `DEFAULT_MEANINGS` gives each of
  Zotero's five annotation kinds a reading, because that set is closed and the
  same in every library -- the tool can state it, and a *colour* is a scheme
  you invented and it cannot. So a mark always reads as something and a fresh
  repo is not a wall of squares with no captions. What you declare, repo-wide
  or per source, sits on top; the views carry the provenance, because a default
  says what the annotation *is* and a declaration says what you meant by it,
  and showing the first as the second hides a decision not taken. The scheme in
  force is what the filter offers, and the state diagram names the marks that
  make units instead of claiming `extract` did it. All of it is Zotero's: a
  segmented book has no marks, no scheme and none of this on screen.
- **Built: which of an item's PDFs to read** (`documents`, by title or key).
  A Zotero item routinely carries the paper twice -- a preprint and a version
  with the appendix -- and importing both doubled every mark against page
  numbers that do not correspond. Every attachment is now printed on every run,
  taken or not, because you cannot choose between things you have never been
  shown. Narrowing the list drops the units it orphans **only where nothing
  human has touched them**: a triaged unit is kept and counted, since deleting
  a decision to tidy up a config change is not a trade this tool gets to make.
  The stale text-layer cache goes with them, or `source-text` would hand a card
  writer a document this source has stopped reading.
- **Built: the marks filter is a picker, not a list.** Five annotation kinds
  times eight colours is forty rows, and as labelled lines that is the entire
  rail. One row per kind, one coloured square per colour -- which is also how
  the marks look on the page you made them on. **Only combinations you have
  declared a meaning for**: an undeclared colour is not a category yet, it is
  one you have not decided about, and offering it as a filter presents a
  decision you have not taken as one you have. The guide's legend still lists
  it, which is where that decision belongs.
- **Built: the header stopped repeating the rail.** `units` and `review` as
  bare words said where to go and nothing else; the rail carries both lanes as
  counts you can click, which says where the work *is* as well. What is left is
  the source picker -- no caret, since a caret promises a dropdown and what
  opens is the gallery -- and a gear beside it.
- **Built: the configuration is a panel, not a page.** It answers a question
  you have *while deciding something else* -- which layout did this card
  resolve to -- and a navigation away and back is a poor way to look something
  up. One renderer, over `/api/config`; the page it replaced is gone rather
  than kept as a second way to draw the same table.
- **Built: an open note holds an approved card in the draft pile.** `sync` has
  always refused an annotated card whatever its status, so it was never going
  to Anki -- but it sat in the approved pile looking like it was, and
  `approved 108` counted work that could not move. `Card.demotion` says why an
  approval is not holding (`edited` or `annotated`) and `effective_status`
  reads `draft` while it does. **The file is untouched**: `status: approved`
  stays, so resolving the note restores the approval with no re-review and no
  re-stamped hash -- which is the whole reason `## notes` sits outside
  `content_hash`. The card says so, because "draft" alone reads as work lost.
- **Built: annotating stays on the card.** It was treated as a decision --
  said, done, move on -- which is wrong twice over: a card often wants two
  notes, and the one just written scrolled off before it could be read back.
  The note also now *appears*: the panel was rendered once by the server and
  never rebuilt, so writing one looked like nothing had happened.
- **Built: the rail speaks about the work, not to the reader.** "needs you"
  became "action required", "you decide" became "a human decision". The
  distinction the labels are actually drawing is mechanical-versus-human, and
  addressing the reader was a roundabout way of saying it.
- **Built: the annotation panel, in one fixed place.** `@claude` and `@me`
  were scattered down the main column under everything else, and the `@claude`
  half was a *shut* `<details>` labelled "not for this decision" -- which is a
  poor way to present the one instruction `/extract-cards` ever receives. It is
  the brief now: first, open, with an `add` beside it and, when empty, a
  sentence saying what belongs there. The two sit in the lower pane of the
  triage column, above them the marks, the split draggable.
- **Built: answering an `@me` keeps the question.** The way out of a parked
  decision was to delete the line, which throws away both halves -- and the
  question is most of what made it worth recording. `yes`, `no` and free text
  all write the answer back *with* the question (`same as 2.4? - no`), and
  unaddressed, so it is a record rather than new work. `x` still deletes
  outright, which is right when the note was a reminder. **Yes/no alone would
  have been two ways to lose the reasoning**; the useful primitive is
  answer-and-settle, and the buttons are prefills for it.
- **Built: one job per rail.** The left one **acts** -- filters, and the
  commands that run on what they leave. The right one **tells you what you are
  looking at** and changes nothing. That is the whole layout rule, and it
  decides where anything new goes: what a colour *means* moved right, into a
  legend that also shows what you declared and have not used and -- more
  usefully -- what you have marked and never declared, which reaches a card
  writer as a coloured box with no caption. The filter rows kept the marks but
  are labelled by the colour you can see on the crop, because the same sentence
  in two places is one of them not being read.
- **Built: the header stopped being something to hide behind.** Both rails are
  `position: fixed` at a higher stacking order than an unpositioned header, so
  at `top: 0` the filter panel sat on top of the view links -- the one row that
  has to be reachable from anywhere. They now start at a measured `--header-h`,
  measured rather than assumed because the bar wraps to two rows on a narrow
  window, which is exactly when a hard-coded height is wrong.
- **Built: the left rail folds, and can be got back.** It had a keyboard
  toggle and no affordance at all. A fold arrow inside it and a tab that shows
  only when it is away -- the guide had already learnt this, and the tab's rule
  is written the positive way round, because with no stored preference
  *neither* state class is set and `:not(.filters-off)` hid the handle on a
  narrow window, where the rail starts folded and the handle is the only way in.
- **Built: filters gain the marks.** One row per `kind/colour` present in the
  source, labelled with what you said it means and swatched in Zotero's own
  palette, so the rail looks like the PDF rather than making you translate. A
  unit matches on *its own* mark, not the ones shown beside it: those belong to
  their own units, and matching on them would return every neighbour too.
  Nothing renders for a source with no marks, so the Cookbook's rail is
  unchanged. The earlier worry about five types times eight colours did not
  materialise -- a real source uses three.
- **Built: the source picker is a gallery, not a dropdown.** It started as a
  tag-grouped `<select>`, which answers "which one am I on" and nothing else.
  The question with a shelf of papers is *which one to work on next*, and that
  is a comparison: one card per source over the whole window, filterable by tag
  and by where the material came from, each carrying the counts for both halves
  of the pipeline. Units and cards both, because a source fully triaged with no
  cards written looks identical to an untouched one by unit count. Served from
  `/api/sources` on first open rather than rendered into every page, since it
  walks every ledger and every card. `g` opens it.
- **Built: switching source drops the filters that belonged to the old one.**
  A section number from one book means nothing in another, and the old handler
  carried it across -- landing you on an empty deck that read as a failed
  import.
- **Built: copyable commands**, per view and built from the active filter --
  the CLI form and the Claude slash command, each saying where it is pasted.
  Nothing is launched, which is the whole difference between a command you ran
  and one that ran itself. Quoted with double quotes throughout, since single
  quotes are a literal in PowerShell and the CLI's own examples use them.
- **Built: the commands are scoped, and pinned where they can be found.** They
  are the last thing in the rail, so with sixty-four sections above them they
  were four screens down the scroll; now they sit in a panel at the bottom of
  it. Renamed, too: "next on this" read as "the next item", which is what `j`
  does. The edge cases were the real work, and every one of them shipped
  broken: **no `--source`** on any generated command, so `/extract-cards` from
  a filtered view wrote stubs for every queued unit in the repo; **a section
  name with spaces in it** (a Zotero attachment is called `MOL appendix.pdf`)
  arrived as two arguments; **a value with a double quote in it** has no
  spelling that works in both `sh` and PowerShell, so the flag is dropped
  rather than mis-quoted -- a command that does too much is visible, one that
  does something else is not; and **`/transcribe` and `/classify` were offered
  for a marked-up source**, where there is no picture of an equation to read.
  The four slash commands gained the `--source` and `--section` contract to
  match, and `forge verify` gained `--source`, since the rail was generating a
  flag it did not have.
- **A progress strip that updates itself.** Everything worth showing is already
  on disk: transcription is `count(transcription == ok) / total`, triage is the
  state counts `pipeline_counts` already computes, cards are the status counts.
  Nothing visible in the ledger needs a job runner, and deriving it keeps
  invariant 2. What it cannot show is "a subagent is on §2.4, four minutes in";
  that would need an append-only `.forge/runs/*.jsonl` the CLI writes and the
  app tails, and it is only worth building if derived progress proves not to be
  enough.
- **Built: `/config`, and the settings that matter beside the deck.** The page
  lists every resolved value with its provenance and now puts the source in
  force first -- arriving from the rail is a question about *this* book. The
  rail itself carries a "this source" panel, because the answer is wanted
  mid-decision and not one navigation away: what the material is, which deck
  and layout a card from it resolves to, how wide its crops are cut, how much
  page a card writer gets, and whether anyone has written down what is ambient.
  Originally specified as:
- **A read-only `/config` page**, effective configuration per source with the
  provenance of each value. There is no way today to tell which layout a card
  resolved to, or whether that came from the source override or the default,
  without reading Python. Editing comes later and only where a mistake is cheap
  (flag meanings, `katex_base`, a source's title and citation); `layout`,
  `order`, `deck` and the note type stay in the file, because they change the
  meaning of existing content and the config is read at startup.
- **Keep the hand-written JS.** FastAPI plus Jinja2 is already the simple
  framework, and an auto-updating counts strip is about twenty lines of fetch
  and swap. Trigger for revisiting: if the same fetch-and-replace-a-fragment
  code gets written a third time, adopt htmx then. No SPA.

## 9. Publishing

- **The source-facing rename (§5b)**, so the name is right the first time a
  stranger reads it.
- **Built: `LICENSE`**, MIT. Its absence meant all rights reserved, so nobody
  could legally use it.
- **The AGPL footnote, stated once.** PyMuPDF is AGPL and it is an *optional*
  extra, which is exactly what makes an MIT core honest: the tool is MIT,
  `--extra pdf` pulls AGPL into your environment.
- **README**: a screenshot above the fold, what this is *not* (not a
  generate-my-cards tool), and first card in ten lines. Depth discoverable, not
  mandatory.
- **A committed folder of images and a demo recording**, referenced by the
  README, with a small helper script so regenerating is cheap. The FSM in the
  app stays generated from code. Committed images can go stale quietly and that
  is accepted.
- **Built: CI** running ruff, mypy and pytest on push and pull request, with
  `--extra pdf` and `npm ci` so the suite exercises the real KaTeX gate rather
  than its weaker fallback.
- **`.apkg` export** -- written, and the bug it hit was **ours**.
  `exportPackage` failed with `NOT NULL constraint failed: notes.sfld`. The
  first guess was the add-on's export path; bisecting a 108-card deck down to
  a single card said otherwise.

  `uid` is the note type's first field, and Anki keeps the sort field in a
  column that takes a number or text. **A uid shaped `4e6166` is a valid float
  literal** -- 4 x 10^6166 -- which overflows a double and lands as NULL. One
  such note takes the whole deck's export with it. Twelve of 108 uids parse as
  floats; two (`4e6166`, `77e454`) overflow. Exporting the other 106 succeeds
  and writes a 46 KB package, which is the proof.

  Two halves of a fix. `mint_uid` never produces one again, and `check` warns
  about the twelve already out there. The existing ones cannot be renamed --
  that would orphan the note already synced under the old uid -- so the
  collection side is one click: set the note type to sort by `Front` rather
  than `uid`. AnkiConnect has no action for it. The uid stays field 0, so
  duplicate detection and `sync` are untouched, and the browser starts sorting
  by the question.

  The other thing to check first: the Cookbook's front matter states **no
  licence at all** -- a disclaimer, an errata address and acknowledgements,
  nothing granting redistribution or derivative rights. Freely downloadable is
  not licensed. Worth two minutes on matrixcookbook.com before publishing a
  derived deck.
- **Fewer docs, not more polished ones.** The honest weakness is more prose
  than code; the fix is ordering and subtraction. No copyright section: the
  gitignore is the whole answer and does not need explaining.

**The claim, in mechanisms rather than adjectives.** "Specialised for maths"
and "human in the loop" are the real differentiators, and both are empty until
you say what makes them true:

- nothing reaches the deck unapproved, and editing an approved card un-approves
  it automatically, enforced by a hash rather than promised
- `verify` numerically checks that the identity on the card is true, with the
  layout declared per source so the check cannot silently run against the wrong
  one (§14 is a reason to fix its coverage before publishing)
- every card traces to a page and a bounding box
- a highlight in Zotero becomes a card with that provenance intact

"Complex sources" is the weakest of the three and mostly restates the second. A
second source replaces the adjective with "a prose statistics text and a
formula reference, same pipeline".

**Half of this does not run without Claude Code**, which is the flip side of
having no LLM code in the tool. The `.apkg` and the committed ledger are the
mitigation: they show the output without running the half a stranger cannot.
BYOK is the real fix and is not scheduled.

## 9a. Cookbook leakage, audited 2026-09-12

A whole-repo audit for facts about one book that had got into code claiming to
be general. Seven of the findings were live defects on the two Zotero sources,
not cosmetics, and the pattern in all of them is the same: a unit id was
assumed to be `<source>:<section>:<number>`, and a source was assumed to be one
PDF named in config.

**Fixed:**

- **`src::` tags named one note each.** `tags_for` took the first two segments
  of any unit id, so a marked-up source got `src::<source>::<annotation key>`
  -- defeating the only thing that tag exists for, and filling a collection
  with one tag per card. Now the section goes in only when the id has one.
- **`Card.section_name` returned an annotation key**, so the review view's
  section rail listed one section per card. Two segments means nothing to
  derive, and it says so.
- **`forge crops` produced nothing for a Zotero source, silently.** It read
  `source.pdf`; the app's crop route had already been generalised to
  `document_for(source, unit.locator.document)` and this verb had not. Both
  `/transcribe` and `/classify` drive off this manifest, so both reported
  nothing to do. Now 16 crops where there were 0.
- **Bare `forge extract` failed the whole run** over a source with no
  `tex`/`pdf` -- which every Zotero source legitimately is. Per-source guard;
  naming a source explicitly still raises.
- **`layout` defaulted to `denominator` repo-wide**, so a statistics paper that
  declared nothing was told it writes matrix calculus. That is the silent
  mixing CLAUDE.md names, arriving through the default rather than a mistake.
  The default is empty, `verify` now refuses a source that declares none
  rather than guessing, and the skill no longer mandates the clause.
- **The `intuition` type had no instructions anywhere.** `/augment` told a
  writer to add `## conditions` and `verify: true`, both of which `check`
  refuses on one. The skill now opens by naming both types.
- **The guard that should have caught all of this was too narrow.**
  `test_instructions.py` skipped `.claude/skills/**` and the app templates, and
  checked for source *numbers* but not source *conventions*. Widened on all
  three axes, and it immediately found three more: a Cookbook equation number
  in the skill, "UNIT -- an equation in the book" in the state diagram every
  user sees, and the guide teaching that a unit id is stable because of its
  equation number.
- **No test used a two-segment unit id.** That is precisely why the first two
  bugs shipped: `test_sync.py` asserted `src::demo::2.4` and passed. There is
  now a fixture for both shapes.

**Left, and why:** the `§` prefix on every section label (cosmetic, but it
reaches a card's `Source` field), `locator.equation` read directly in five
places instead of through `ref` (latent until something emits `kind`/`label`
with a number, then it silently disarms the contiguity oracle), chapter
splitting on `.` in the section rail, `front_char_cap` not being per-source,
and the "hand over the whole book" reasoning in `extract/__init__.py` -- which
was written about a 26k-token reference and now also applies to a 700-page
textbook.

`extract/pdf.py` is **not** on either list. Every heuristic in it is
Cookbook-specific and documented as such, with an ablation showing exactly
which signals carry it. That is honest specialisation behind a seam, and it is
what §13 is about.

---

---

# Defects the Cookbook taught us

## 10. Multi-line display equations get split

Found during the first §2.1 review. Equation 48 is a three-line display, and
`anchored_regions` grows a region only by *vertical overlap*: stacked lines do
not overlap, so it produced three units, two unnumbered fragments and one
carrying the number, each holding a third of the identity.

The audit does not catch it: the crops are adjacent, not overlapping, so
`crop-overlap` stays quiet and the numbering oracle is satisfied.

**Detectable signal:** an unnumbered unit sitting directly above a numbered one,
in the same horizontal band, with a gap smaller than a line height, is almost
certainly a continuation of it. That is an audit check (`fragment-suspected`)
before it is a segmentation fix.

**Also detectable mechanically.** `classify` flags unnumbered units whose text
contains no relation symbol, which is exactly what a continuation fragment
looks like. It caught the eq-48 middle line and 52 others without being told
about them, skipped with reason `no-relation`, so they are reviewable rather
than lost.

**Partly mitigated already.** The triage view renders each crop with 40pt of
surrounding page and the unit's own box drawn on it, so a split equation shows
its missing lines just outside the box and a merged one shows two numbers
inside it. §6 makes that margin adjustable, which helps here too.

### Measured, over the whole book (the `/classify` pass)

Six classifier agents read all 117 unnumbered units. Of the ~100 skips they
proposed, the large majority are this one defect. It is not a long tail, it is
concentrated:

| where | what |
|---|---|
| §8.2.4 quartic forms | **25 of §8.2's 36 units** are fragments, from **seven** identities of 2-5 lines each (the classify pass, seeing only unnumbered units, undercounted this as three) |
| §6.2 cubic forms | one equation into three units, another into two |
| §7.7–7.9 | Student-t / Wishart / inverse-Wishart densities, cut mid-formula |
| §2.8 | a four-crop chain, all of it equation 143 |
| §2.4, §2.5 | number on the *last* line, continuations orphaned above it |

The number attaches to whichever line carries it, so orphans appear **both**
above and below the numbered unit. Any fix must handle both directions.

**A merge signal that is free.** Every continuation line in §6.2 and §7.7–7.9
ends in a trailing binary operator (`×`, `+`). A line ending in an operator
cannot be the end of an equation. That is mechanical, needs no model, and would
merge most of these before a human ever sees them.

**The worst variant: a bbox that clips mid-glyph.** Unit `9.2:409` has a box
tight enough to shave the left stroke off `W_N`, so the crop reads `V_N`, a
different and perfectly legible symbol. Every other defect here announces
itself as *missing* something. This one does not: a transcriber reading only
the crop records a wrong symbol with full confidence, the KaTeX gate accepts
it, and the card is wrong forever. It was caught only because the agent
distrusted the shape and rendered a wider region to compare.

This is the strongest argument for the coverage oracle below, and for keeping
the crop visible next to the transcription: no check on the *text* can catch a
faithful transcription of a corrupted *picture*.

**A second, distinct failure: the bbox clips the relation.** §9.1.5 produced
~77pt-wide boxes that cut `C1 =` off the front and the trailing subscript off
the back. This is not line-splitting, it is a too-tight box on a short line,
and it is worse than a split because the crop still *looks* complete.

**One outright bug.** `matrix-cookbook:3.2:178` contains nothing but the number
`(178)`; the equation's content is in its unnumbered sibling `3.2:p20y147`. The
contiguity oracle is satisfied, since 178 exists, so nothing mechanical catches
an empty numbered unit. **A numbered unit whose crop holds no relation symbol
is an audit check worth adding**, the mirror of the `no-relation` rule already
used on unnumbered ones.

**Not everything unnumbered is a bug.** §11.1/§11.2 have a high unnumbered rate
because the book genuinely states long runs of unnumbered moment identities.
There the agent found only row-splitting of aligned blocks, where each row *is*
a complete identity: a consolidation question for the human, not a segmentation
defect.

### Worse than splitting: content dropped entirely (eq 27)

Found by the transcribe pass. Equation 27 is a three-line display. Two of its
lines survive, spread across `1.2:p7y169` and `1.2:27`. **The remaining line is
in no unit at all.** It was never extracted.

This is a different severity from everything above. A split equation is
annoying but recoverable, because every piece is on file and a human sees the
neighbours in the crop. A dropped line is *invisible*: the numbering oracle is
satisfied, no crop overlaps, and nothing in the units view hints that a third
of the identity is missing.

**It recurs, and by a second mechanism.** In §6.2 the unit `p36y310` has a bbox
whose *left edge* starts after the `=` sign, so the entire left-hand side
appears in no crop anywhere. Confirmed by rendering the full page width
straight from the PDF. So content is lost both vertically (a line between two
units) and horizontally (a bbox that begins mid-line). Two confirmed cases in
the first 355 units read.

**A third mechanism: multi-column layout.** The page-5 notation table is two
columns, symbol and description. Some units' bboxes cover only the description
column, so the symbol, the entire point of the row, is in no unit; others merge
two or three table rows into one. `anchored_regions` reasons about vertical
bands and has no notion of a column. It costs nothing here (all eight are
front-matter skips anyway), but the same heuristic runs over §5.1's
Condition/Solution table and §10.4's norm-relation table, which are real
content.

### The coverage oracle

Extraction knows every text block on the page. A block, or part of one, that
ends up inside no unit's bbox was dropped, and measuring that is cheap and
exact: a **coverage oracle** beside the contiguity one. Contiguity asks "is
every equation number present"; coverage asks "is every mark on the page inside
some unit". Neither the audit nor the KaTeX gate asks the second question.

**Narrowed, and demoted, by §7.** An earlier draft called this essential for
prose sources, on the grounds that prose has no numbering to lean on. That
argument died when prose stopped being segmented: most of a prose page is now
*meant* to be outside every box, and a literal coverage check would scream on
every page. What survives is the narrower question, "is every **named
statement** inside a unit", which is weaker and closer to contiguity. Still
worth building, especially before trusting the model extractor, since it is the
only thing that can say whether a new extractor is better or merely differently
wrong. No longer urgent.

### §12.1 (Appendix B) should probably not be extracted as units

The proofs appendix is not a list of identities, it is continuous multi-line
algebra. Reading all 35 of its units found the segmenter tearing fractions,
parentheses and summation limits across crop boundaries roughly every other
unit: 11 of 35 needed bracket-splitting or were pure debris (a stray `r=0`
summation limit; a duplicate top-sliver of the next crop; torn denominator
strokes).

The transcriptions are faithful, but they are *proof fragments*. The useful
content is the chain, not any single line. Two honest options: treat the whole
appendix as prose and skip it, or segment it by **proof block** rather than by
rendered line. Either way, do not author cards from 12.1 as currently
extracted. A scoping decision for the human, not something extraction should
decide.

## 11. Images and figures in PDFs

**The segmenter is blind to anything that is not a text block.** `page_blocks()`
skips every block whose `type != 0`, so embedded rasters are invisible, and
vector drawings (`page.get_drawings()`) are never consulted at all. Three
consequences, in increasing severity:

- **Figures are not units.** A diagram worth carding, a geometric picture of a
  projection, a plot of a matrix norm, cannot be triaged, because it never
  enters the ledger.
- **Equations set as images are silently lost.** In a scanned book, or one where
  a publisher rasterised the display math, extraction returns *nothing* and says
  so in no way at all.
- **Vector-drawn math is lost the same way**, and that includes fraction rules:
  TeX draws them as thin filled rectangles, which is a font-independent "there
  is math here" signal currently thrown away.

The Matrix Cookbook has **zero** image blocks and no heavy vector art, which is
why this has not bitten yet.

**Two of the three blockers have since dissolved.** Zotero's image and area
annotations (§2) are figure units already: a box, no text, crop authoritative.
And "a figure card needs a `type` beyond `identity`, which is a §14 non-goal"
stopped being a blocker when §3 added one. What is left is the segmenter work:
treat `type == 1` blocks as candidate units with a `kind` on the unit, and
cluster vector drawings into regions so a plot becomes one unit rather than
four hundred line segments. The model extractor (§7) gets most of this for
free, since a page image does not distinguish text from picture.

A cheap first step worth doing on its own: use fraction rules from the vector
layer as a math signal in `score_line`, which would make the fallback segmenter
far less dependent on Computer Modern font names.

## 12. The cross-check, and reconciling two extractions

Designed, not built. The principle that makes it legitimate: an LLM is not
mechanical, but **agreement between two independent extractors is**, and the
equation number is an exact join key.

- **Contiguity**: built (`forge audit`).
- **Transcription**: built (`/transcribe` plus the `transcriber` subagent). One
  extractor, not two, so it reconciles nothing yet.
- **Cross-extractor join**: a page-level pass that reads the *page* and reports
  the equations it finds, joined against the ledger on equation number. It must
  read the page, not our crops: fed our own crops it inherits our segmentation
  errors and cannot report them.
- **Round-trip render**: the strongest check, and the one that catches a *wrong*
  transcription rather than a missing equation. Render `tex_auto` with KaTeX,
  compare against the crop, store the agreement as a number. Without it, a
  transcription pass trades a detectable failure (a gap in the numbering) for
  an undetectable one (confident wrong LaTeX).

**§13 hands this one for free.** Keeping the heuristic as a second backend
means the Cookbook has two independent extractors reading it, which is exactly
what this section wanted and could not previously justify building. Their
disagreement is the signal, at no cost beyond running both.

## 13. `extract/pdf.py` is frozen, not deleted

**Status changed.** It was marked for deletion; it is now a frozen alternate
backend, selectable per source. The reason is that the general extractor (§7)
should not be the *only* thing that can read a PDF, and the seam is already one
function pinned by contract tests, so a second implementation behind it costs
almost nothing to keep.

Why it is not the default: the ablation is unambiguous.

| | equations found |
|---|---|
| as shipped | 571/571 |
| without math-font detection | 571/571 |
| without equation numbers | locators gone; 936 unverifiable regions |
| without either | **9** |

Two producer-specific signals carry everything: a right-margin `(61)` and
Computer Modern font names. It is a specialisation, and the Cookbook happens to
be exactly the specialisation.

**Frozen means frozen.** Do not fix its heuristics; bug reports against them
are closed as "use the model extractor for that source". When a shared type
changes under it, give it a shim rather than editing it: generalising `Locator`
(§7) leaves `pdf.py` emitting `equation: int` untouched and maps across.

**What it owes.** One function, `segment()`, returning units whose `locator`
carries `section`, `equation`, `page` and `bbox`, pinned by
`tests/test_extract_pdf.py` under *the deprecation contract*. Everything
valuable already lives elsewhere and is unaffected: `extract/render.py` (crops,
from `locator.bbox` alone), `audit.py` (the 1..N oracle, a property of the
*document*, so it scores any extractor), and `ledger.py` (stable ids from the
book's own numbering, which is why triage survives a change of extractor).

**Delete it** if it ever costs something real: a shared change it cannot absorb
behind a shim, or a second book where it is chosen and then found to mislead.

## 14. `verify` coverage

**Measured, not guessed: 42 of 108 cards verify.** The "exactly one card opts
in" this section used to say was years stale. 66 do not: 8 `definitional`
(nothing to derive), 57 `short`, 1 `long`.

**The contradiction is fixed.** `verify` is now in `UNHASHED_FRONTMATTER`, so
both halves of opting in are exempt rather than one. Re-stamping was proved
before it was done: all 108 approved cards matched their stored hash under the
old rule and none had drifted, so nothing was waved through. One line changed
per card, the hash itself. Coverage is **46 of 108** and rising without costing
a re-review.

What it used to be:
`## verify` the *section* is exempt from `content_hash`, for a reason the code
states plainly: it is a check on the author rather than card content, and
hashing it meant that fixing a test un-approved a card whose mathematics had
not changed. But `verify:` the *frontmatter flag* is **not** exempt. So turning
a test on does precisely what the exemption exists to prevent.

Four identities were opted in to demonstrate it: the norm gradient, the
derivative of an inverse and of a determinant with respect to a scalar, and
`d det(X^-1)/dX`. All four passed numerically on the first run, and all four
cards went `hash-stale` anyway. They are in now, and they do not.

Two of them differentiate with respect to a **scalar**, which `grad` does not
cover -- it walks the entries of a matrix. A central difference in one variable
is three lines, so the snippet does it rather than the helper growing a second
mode for two cards.

**Still open:** the gnarly identities (Woodbury, block inverses, anything with
three transposes) are where this earns its keep, and 62 cards still skip. Also
unchanged: `verify` casts to real, so a complex-valued identity cannot be
expressed at all.

**Measure it against `identity` cards only.** An `intuition` card (§3) has
nothing to check numerically, so counting it in the denominator would make
coverage look worse every time the deck got better.

**A known gap, unfixed:** `verify` casts to real (`np.asarray(..., dtype=float)`)
and so cannot express a complex-valued identity at all. §4.1 is where that
first bites.

---

# Ideas, not scheduled

## 15. A "daily proof" challenge

One theorem a day, presented as something to reconstruct rather than recall:
the fundamental theorem of algebra, Abel-Ruffini, irrationality of sqrt 2,
Cantor's diagonal argument, and their kin.

This is a **different object from an identity card**, which is why it does not
just become another `type`, and adding `intuition` (§3) does not change that.
An identity card asks for one answer and is graded in a second. A proof is a
structure: you either reconstruct the argument or you do not, the answer is a
paragraph, and grading it against a stored back is not what makes it useful.
Forcing it into the current card format would produce a front too broad to have
one answer, which the card-writing skill exists to prevent.

Two shapes worth considering, and they are not equivalent. **As Anki**, a
`proof` card type: front the statement, back the argument in named steps, and
the review is "did I get the shape". Cheap, reuses the whole pipeline, inherits
the wrong grading model. **As a standalone page**, one theorem a day with the
steps revealed on demand: escapes the recall-grading model entirely, but is a
second product with its own state.

Open questions before either is worth building. What is the source? The
Cookbook has no proofs, so this needs its own corpus and the extraction
pipeline may not apply at all. What is being reviewed: the statement, the key
idea, or the full argument? And is spaced repetition even the right schedule
for something you work through rather than recall?

## 16. A whole-deck view of the dependency graph

`requires` decides the order new cards are introduced in, and the review view
shows it one card at a time: what this card needs, what needs it, where it
lands in the study order. That answers the question you actually ask, which is
always about the card in front of you.

What it does not answer is the shape of the whole thing. Which cards are
foundations that many others rest on? Is there a cluster nothing points at? Did
a chapter's worth of dependencies never get recorded at all?

**Deferred because the graph is too sparse to be worth drawing.** Nine edges
across 108 cards renders as a hundred isolated dots and a few short chains,
taking a panel to say "almost nothing depends on anything". The per-card lines
carry more per pixel.

The data is already computed. `app.review_view` builds the forward edges from
`Card.requires` and the reverse edges by inversion, and `sync.effective_keys`
already walks the graph for priority inheritance, so a view would be rendering
work that exists rather than new machinery.

**Build it when the graph earns it.** A reasonable trigger is edge density:
once a meaningful fraction of cards carry a `requires`, or once a chain runs
more than three deep, the structure stops being legible one card at a time.

Two things to decide first. **What is a node**, a card or a concept that
several cards share? "The adjugate" is one idea carried by three of them, and a
concept graph would be smaller and more honest about the material. And **what
is it for**, reading the deck's structure or editing it? A read-only picture is
a weekend; draggable edges means writing frontmatter from the browser, which
invariant 2 allows but does not make free.

### 16a. Per source, on a canvas

Asked for 2026-09-12, and it sharpens both of the open questions above.

**Per source** is the scoping that makes the density argument go away. Nine
edges across 108 cards is a near-empty picture; nine edges across the thirty
cards of one paper is a readable one, and it is also the only scope where the
graph *means* anything — `requires` says "introduce that first", and cards from
two different books are not competing for a position in the same reading. The
rest of the app is already scoped this way, so the view inherits the source
selector rather than inventing a scope of its own.

**A canvas** rather than SVG answers the second question with "editing".
Dragging is the point: the layout a dependency graph wants is the one the
person who knows the material would draw, and neither dot-layout nor a force
simulation knows which two results belong side by side. That means node
positions have to be stored — and they are a fact about one source's graph, so
they belong in that source's folder rather than in `localStorage`, where they
would be invisible to everyone else and lost on a new machine. A
`sources/<name>/graph.json` of `{uid: [x, y]}`, written by the app and diffable
like everything else, satisfies invariant 2 without putting layout into card
frontmatter where it would be hashed.

Still gated on the same trigger: build it when the edges exist. A canvas of
thirty cards and no arrows is a worse answer than the per-card lines. What this
*does* change is the order — when it is built, it is per source and draggable
from the start, rather than a repo-wide read-only picture that then has to be
rewritten.

---

# Considered and rejected

**A database.** The files *are* the product: a card is a markdown file you can
read in a diff, the ledger is JSONL so a re-segmentation shows as reviewable
lines, and crops were removed from git for exactly this reason. A database is
either a second copy that drifts or a replacement that throws the property
away. What scale actually wants is an **index, not a store**: sqlite under
`.forge/`, gitignored, rebuilt when stale, deletable without consequence. Build
it when a units page render passes ~300 ms, which at 751 units and 108 cards is
several books away. Measure, do not guess.

**Triggering Claude from the website.** No supported way to push a prompt into
a running session; shelling out to `claude -p` is a separate headless run, and
a button that writes cards with nobody watching is what invariant 1 exists to
prevent. Superseded by copyable commands (§8), which keep a human at the point
of execution.

**A collection of documents inside one source, and `locator.document`.** §2
makes each paper a first-level source instead, so the field would exist for
zero instances. Revisit only if a source genuinely needs many documents.

**A subdeck per paper.** Fifty three-card decks and fifty deck configurations,
to express something a tag expresses better. Subdecks are for a different
new-card rate; tags are for filtering.

**Mermaid diagrams in the README.** Text that renders natively on GitHub and
cannot go stale, rejected in favour of committed images and a demo recording
(§9), on the grounds that more visualisations are coming and they will not all
be state machines.

**pdf.js in the triage view.** A whole-page render with the unit's box drawn on
it answers the same question in one glance and adds no dependency (§6).
Reconsider when you want to drag a box in the browser to create a unit.

**BYOK and LLM calls in the tool.** "No LLM API code in the Python" is why
there is no torch, no key handling, no cost model, no injection surface inside
the tool and no vendor in the dependency tree. That is a position, and it is
more interesting than the feature. If it ever happens it belongs in a separate
package implementing the same contracts the slash commands do. Recorded for
much later; it is also the real fix for "half of it needs Claude Code" (§9).

**A hosted live demo.** The app writes to the local filesystem, so a public
instance is either read-only (and therefore not the thing) or a vandalism
target, and it would need the source documents hosted. A recording gets the
same point across for an hour's work (§9).

**Docling** (and marker, MinerU). Measured on this book: 19.7 s/page against
0.18, five regions where we find twenty on the packed page, and no LaTeX
without a second model. Its real advantage is generality, and §7 gets that more
cheaply. It would earn its place on a **scanned** PDF with no text layer, which
is also case §11.

**Refreshing transcriptions on re-extract.** `upsert` used to treat
`tex_auto`/`transcription` as extraction output, so a single
`forge extract` silently wiped every transcription in the ledger. They are
work product now, like triage state: filled when empty, never overwritten. Two
regression tests hold the line, and §2's Zotero sync follows the same rule.

**Local math OCR** (pix2text). Removed. Transcription is `/transcribe`, a
Claude Code skill reading crops on the subscription, which keeps torch, CUDA,
Intel XPU builds and a 4 GB dependency tree out of the project entirely.

**Committing crops as PNGs.** Removed: 751 files, 7 MB, opaque diffs, stale
after every re-extract. The ledger stores `locator.bbox` and crops render from
the document on demand (~150 ms over HTTP). A re-segmentation is now a diff you
can read.

**Moving the model cache into the repo.** The shared HuggingFace cache is doing
its job; a per-project copy duplicates weights and drags them into whatever
backs up the project directory.
