# Roadmap

What is left, what the Cookbook taught us about its own extraction, and what
was rejected and why. The milestones in [DESIGN.md](DESIGN.md) §13 are built
and gone from this file; git history has them.

This file is about the tool. What is worth carding, and which sources to
import, is about one deck and lives in an untracked `ROADMAP.private.md`
beside it.

**The numbers are names, not an order.** Code cites them (`ROADMAP.md §1`,
`§9`), so a section keeps its number wherever it moves to and a new one takes
the next free number.

---

# What is left

## 1. The dependency canvas: what it does not do yet

Built, at `/graph`, per source, and `[app] graph = false` turns it off.
`graph.py` holds the graph and its layout with no app in it, `graph.js` draws
it, and `projects/<name>/graph.json` holds whatever you dragged.

- **A second edge kind.** `requires` is the only one, and `Edge.kind` is
  already carried through for the next. Nothing proposes a second: two cards
  from one unit and two cards in one section are not dependencies.
- **Concept nodes.** A node is a card, and "the adjugate" is one idea carried
  by three cards. It is a second builder beside `card_graph` and a
  `?graph=concepts` on the route, which is what that seam is for. Build it
  when one idea is carried by enough cards that the graph reads as
  duplication.
- **Zoom.** Pan is enough and the browser zooms. Revisit when a real source
  does not fit.
- **Quadtree hit-testing.** Linear over every node on `pointermove` is fine at
  700. Revisit past a few thousand.
- **Browser tests for the other two views.** `tests/browser/` covers the
  canvas, because a `<canvas>` and a pointer are what the rest of the suite
  cannot reach. The other two are markup and are covered as markup; the case
  for driving them anyway is the closed dialog that still painted over the
  canvas.

## 2. Two audit checks that would have caught dropped content

Small, mechanical, and they belong in `audit.py`, which is not frozen. The
evidence for both is in "What the Cookbook taught us".

- **`fragment-suspected`:** an unnumbered unit directly above or below a
  numbered one, in the same horizontal band, closer than a line height, is
  almost certainly a continuation of it. The contiguity oracle is satisfied
  either way, because the number exists.
- **A numbered unit whose crop holds no relation symbol.** The mirror of the
  `no-relation` rule `classify` already applies to unnumbered units. It would
  have caught `matrix-cookbook:3.2:178`, which holds nothing but `(178)`.

A third signal belongs to whatever segments next: **a line ending in a
trailing binary operator cannot be the end of an equation.** Every
continuation line in §6.2 and §7.7–7.9 ends in `×` or `+`.

## 3. Small and named

- **The `§` prefix on every section label.** Cosmetic, except that it reaches
  a card's `Source` field in Anki.
- **`front_char_cap` is not per-source.** 160 characters suits a formula
  reference and is tight for a statement from a paper.
- **Nothing writes an `intuition` card yet.** Teaching the card-writing skill
  the second kind is guidance, not code, and it belongs with the first prose
  source that has marks worth explaining.

## 11. Pulling context from Obsidian notes

`forge context <unit>` hands a card writer the page a unit was printed on and
the conventions the source declares. What it cannot hand over is the note you
already wrote about this material, which is where your notation, your worked
example and the thing that confused you the first time live.

The shape that fits: a vault path in the config, and `context` adding the
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

## 10. Projects, sources and topics

A deck you want on a subject where no single book is canonical. You say "I
want cards for how to use the standard containers", a pass proposes units,
you triage them the usual way, and the cards are written, reviewed and
iterated like every other card.

Only the first layer changes. `extract` and `zotero` are two frontends that
fill one ledger, and everything after the ledger already ignores which door a
unit came in by (invariant 3). This is a third frontend, plus generality in
the middle.

Worked through, it stops being one feature. It is four, and three of them
improve the sources that already exist:

1. sources become first-class inside a project, with their own settings, and
   a source may be a URL
2. topics: an optional grouping with an ask and an outline
3. a frontend that proposes units where there is no document
4. code on a card

**A frontend owes five things**, and nothing states this today:

- a stable id that survives a re-run
- a locator, as much of one as it can fill
- something scannable, so triage is not guesswork
- a subject and not a draft. A gist, a short preview, some references. The
  moment a frontend emits a front and a back, triage has become review
- `state: new`, and no opinion about anything after that

### The vocabulary, and a rename

Two things were called a source: the directory under `sources/`, and
the document a unit was printed in. They are now separate concepts and the
word has to go to one of them.

- **project**: what `sources/<name>/` was. One ledger, one deck, one
  `conventions.md`, one graph.
- **source**: one work inside it. A book, a paper, a URL. This is the
  meaning `Card.source` has always had, which is the evidence the word
  belongs here.
- **file**: a physical PDF under a source. A book delivered as fifteen
  chapter PDFs is one source with fifteen files.
- **topic**: optional, described below.

**The depth is fixed at project, source, file, and there are no parent
relations.** A source is one work, and a work's parts are its files. Nesting
beyond that is what the "split the project" rule below is for.

There is then no such thing as a custom project. There are projects, and
some have no authoritative source.

What gets renamed: `sources/`, `source.toml`, `SourceConfig`, `--source`,
`Unit.source`, the picker. In the same commit as the config split, since
that pass touches all of it, and by migrating rather than by keeping the old
spellings working (below).

What does not: **`Card.source`**, which is now exactly right. And **the
`src::` Anki tag**, though not for the reason I first gave. It could be
migrated, because `sync` diffs tags against the live note and adds and
removes them, so the next run would move every card over. It stays because
it is fine: the tag's job is filtering inside Anki, "src" still reads as
provenance, and renaming it breaks saved searches in a collection for no
gain in the repo.

### How big is a project

**A project's scope is the scope over which one `conventions.md` is true.**

CLAUDE.md refuses a repo-wide conventions table because a convention is a
fact about one book, and it names the failure it prevents: a statistics
paper told it writes matrix calculus in denominator layout. A project called
"probability theory" recreates that one level down. Two books that do not
share a notation leave no sentence in that file true, and every card writer
is handed something misleading.

Several authoritative sources in one project is fine and expected: a tight
cluster of papers is one subject and one notation. The signal is not
plurality, it is **two sources that disagree about their settings**. That is
also exactly when somebody would ask for a parent relation, so the ask is
the signal to split rather than to nest.

### Properties, not kinds

**No stage distinguishes source types. Every stage decides from properties
of the unit, the card, the source and the project in front of it.** That is
the whole design, and most of what would otherwise need arguing follows.

It is already the house style in one place: `from_marks` in the units view,
whose comment says it decides which passes are offered and that it is a
property of the units rather than a setting. Two invariants half say it too.
3 ends "whichever door it came in by", and 7 is careful to be authoritative
only "for what is printed". The rest is that applied everywhere instead of
twice.

Two sorts of property.

**What it has.** Derived, stored nowhere. Geometry, page text, an
authoritative source, references, marks, tags, a preview and its language.
`has_crop` and `from_marks` are the two that exist.

**What was decided.** A tri-state on the unit, falling back through the
chain. `web` and `context_pages` are both already this, and both put the
decision on the unit for the reason triage is where you can see it.

**The list is open.** The test for adding to it is whether some stage would
otherwise have to ask what kind of thing it is looking at. That test is what
keeps it from filling with settings nobody reads.

Today the screen is built from constants, and each of these becomes a read
of what the unit has:

- **the context chip.** `CONTEXT_STEPS` is a fixed tuple of page counts. A
  page-backed unit should offer pages and its chapter; a unit with
  references should offer this one or all of them. Same chip, same stored
  setting, a vocabulary that comes from the unit.
- **the commands panel.** `commands_for` takes one ad-hoc `from_marks` flag.
  Each row declares what it needs instead, and the panel shows the rows
  whose needs are met: no `/transcribe` where there is nothing to
  transcribe, no `/propose` where a source already answers what to cover.
- **the aside and the pdf view cycling** already read `has_crop`. The guide
  and `project_facts` should describe what is there rather than assume a
  document.
- **the rail.** The tag group appears when there are tags.

None of this is new behaviour for a book. It is the same screens deciding
from the unit instead of from a constant, which is also what keeps the two
kinds of deck from drifting into two front ends.

### What a unit stands on

**At most one authoritative source, and zero to many references.**

At most one, because two things that settle it can conflict with nothing to
break the tie. A card built from several units still has one authoritative
source each; merging is a card-level thing and does not need the unit to
hold two.

This lands on what exists. `locator.document` keeps its current meaning, the
authoritative file, and page and bbox keep resolving against it with no
migration. Which source that file belongs to is looked up rather than
stored, because file to source is many to one and declared. Plurality lives
in a new list beside it, so nothing existing becomes a list.

**So there is no `authority` setting.** A unit has an authoritative source
or it does not, and that is read off the links. Promoting a reference into
the authoritative slot is how you say "this one I did look up and it
settles it", which is more concrete than a tri-state and needs no
inheritance. `has_crop` stays separate and answers the other half: whether
that authoritative source has geometry you can check against at review.

Invariants 4 and 7 were always carrying this as an assumption. Naming it
lets them stand as written instead of growing an exception. What the two
cases cost is one paragraph at the end of this section rather than a rule
each.

### Topics

**A source answers "what does this say". A topic answers "what should we
cover".**

A topic is an ask in the words you used, an outline of what it means to
cover, any references particular to it, and a few defaults. It is what
supplies settings, context and provenance when no single source does.

**Zero by default, for every project.** A source with marks has already
answered the coverage question: the marks are the decision. Giving every
source a topic would put an empty outline on every book, which is a null
object and carries no information. **A topic exists if and only if somebody
wrote one**, and nothing auto-creates one for a source, a project or an
import.

Two shapes, both real:

- **standing alone**, where there is no definitive source and the topic is
  the only thing that can say what to cover
- **augmenting a source**, where a book is authoritative and you want a
  slice its own structure cannot express, with an outline of its own:
  "concentration inequalities", which crosses chapters and is not a section

Not required even in a sourceless project. Proposing into one with no topic
works; you get no outline, no recorded ask and no shared defaults, which is
why writing one is in practice the first thing you do there.

**Topics are not tags.** A tag like `invalidation` spans topics by design
and a topic does not. A topic is provenance and a tag is a property of the
content, so a unit has at most one topic and any number of tags, and they
want different controls: a picker and a search box.

**Topics do not duplicate sources**, because the two hold nearly disjoint
things. A source holds files, a marking scheme, crop settings, cached text
and a citation, all of it about reading a document. A topic holds an ask, an
outline and references, all of it about deciding what to cover. The overlap
is references, deck and a couple of permissions, which is a small shared
shape rather than a second system.

### The setup stage

Every project already has a pre-unit stage. It has no view and no name, so
it happens by editing TOML: which item, which files, which marks become
units, what the colours mean, which deck, what is ambient. That is not
triage and not review, and it is where a project with no book spends all of
its effort.

So it gets a view, for every project and not only for the new kind. A list
on the left of the sources and the topics, a panel on the right for whatever
is selected. The topic list is empty for most projects, and an empty list is
a true statement about them.

- **a source** shows its files, whether it is authoritative, which marks
  become units, what the colours mean, its citation, its deck
- **a topic** shows the ask, the outline with which entries have units, its
  references, its defaults
- **the project** shows the deck, the conventions, the permissions

Three things to hold to.

**It writes files and nothing else.** Everything it does is doable by
editing a file, per invariant 2. A form that starts owning its fields is the
failure here.

**Only decisions that change what the next pass does.** Deck, permissions,
marks, references, outline. Not `crop_width`, not `katex_base`, nothing that
is a fact about a machine. "Defaults etc." is unbounded and ends as forty
fields nobody reads.

**The outline is what makes it worth opening.** Configuration alone will rot
because you will edit the TOML instead. Build the topic half first; the
source half is mostly giving `project_facts` and the scheme legend room they
do not have in the rail.

### A topic, start to finish

Five steps. Two need Claude and three are file edits.

1. **Ask.** `forge topic --new "how to use the standard containers"` records
   the ask and nothing else.
2. **Sources, if you want them.** A pass appends what it found, as links
   with a line each on why. You add and delete.
3. **Approving is leaving them in.** No approved flag, the same way an
   annotation is resolved by deleting it. The list is what you left.
4. **Outline, then propose.** Below.
5. **The usual pipeline.** Units arrive `new`, and triage is triage.

**A topic has no state of its own.** Where it has got to is derivable, so it
is derived: no references means nobody has looked, no outline means nobody
has planned, no unit carrying the tag means nothing has been proposed. Same
call as `has_crop`, and it is what keeps this from adding a second state
machine beside the ledger's.

**The gate is that the steps are separate commands.** `classify` already
works this way: it proposes and applies nothing. Nothing mechanical enforces
the pause, and nothing should. The pause is that you run the next command.

#### Breadth, which is step 4

A single pass asked for forty proposals produces twelve and stops. It is
satisficing under length pressure, and nothing tells it that twelve is
short, because nothing knows what the subject contains.

- **Outline first, as its own pass.** One short line per thing to cover, no
  detail. Forty of those is cheap to generate, which is exactly why the
  failure does not happen there.
- **You edit the outline, not the units.** Deleting padding and adding the
  obvious gap costs three lines here and forty edits later. It is also a
  second look before anything enters the ledger.
- **Fan out the fill.** One subagent per chunk of the outline, which is what
  `/transcribe` already does per section and for the same reasons. A small
  list is easy to finish, so the pressure never builds.
- **Coverage becomes a diff.** Outline entries with no unit against them,
  printed by `forge`. Mechanical, counting rather than judging, and the same
  kind of question `audit`'s contiguity oracle asks about extraction. It
  also makes a second run resumable rather than a re-run.
- **Do not ask for a number.** "Produce forty" produces padding, and padding
  survives triage because none of it is clearly wrong. Twelve is sometimes
  the honest answer. An outline of sixty entries is the signal to split the
  topic.

None of it is enforced. A propose with no outline just proposes.

### What a project is on disk

A directory, a `project.toml`, and prose files beside it. No kind key: once
the config splits, a project with no authoritative source is one whose
sources declare no files, and that absence is the fact.

`project.toml` gains a table per source: its key or URL, its files, whether
it is authoritative, its marking scheme when it has one, its topics, its
deck. **Structured relations go here and not in prose**, because a relation
written in a prose file is the one that drifts.

`references.md` is the project's shelf of reference material, one entry each,
in prose, with no schema. A shelf to check against, not things to card.

`topics.md` holds the asks and the outlines, a heading each. One file rather
than a directory: there are ten of these, not a thousand.

`conventions.md` changes meaning in a project with no authoritative source.
For a book it describes what the source does. With no source it decides what
the deck does: which language version is ambient, how a snippet is written,
what is assumed. Write it before the first proposal, not after the first
batch reads inconsistent.

### Where a thing lives, and what may be overridden

The split already exists and is written down in `config.py`. Naming it
rather than inventing a new one:

- **TOML: what the tool acts on.** It resolves a path, runs an import,
  routes a deck, branches on it.
- **`[conventions]`, free-form keys: a short fact that reaches the writer
  verbatim.** Nothing branches on one except `layout`.
- **Markdown: prose the writer reads.**

The test for anything new is **does any Python branch on it.** Yes, TOML. No
and it is a sentence, markdown. No and it is a label, the conventions table.

A fourth case appears here and is worth naming: **markdown the tool counts
but does not interpret.** A topic's outline is read only to find its
entries, which is what `annotation_audience` already does with a prefix at
line start. Counting lines is not a schema.

That splits a topic across two files, the ask and the outline in markdown
and any defaults in TOML, joined by slug. Not novel: `project.toml` and
`conventions.md` are already one thing split by whether the tool acts on it,
and most topics will carry no TOML block at all.

**Everything is overridable except a short list**, and the list is short
because the test is narrow: **overriding is allowed unless it would make two
things in the same deck mean different things without saying so.**

- **Identity and derived facts** are not settings. You cannot override
  whether a unit has a crop; you change the thing.
- **Conventions.** Overriding `layout` on one unit puts two cards in one
  deck that read differently with nothing on either saying which. That is
  the silent mixing CLAUDE.md exists to prevent, so a convention is declared
  at the level it is true and does not cascade down.
- **Reading settings stop at the source.** A unit cannot have its own
  marking scheme; it was already imported by one.

Permissions, windows, decks and tags all pass the test, which is why they
are free. `layout` fails it.

### Units

Ids are slugs, `<project>:<slug>`, so a re-run adds only what is new.

**Units grow `tags`, which cards already have.** The first draft made the
topic the middle segment of the id, because a section is filtered everywhere
and it was free. Wrong shape: a section is where something sits in a
document. The topic is a field of its own, single-valued, and tags are the
many-valued thing beside it.

A unit has no `tex_auto`. It has a preview: for code, a snippet too small to
run, enough to see the point. Rather than a field beside `tex_auto`, this is
the moment to say what those three fields have always been, a machine's
reading of the unit and how far to trust it. `Unit.tex` is already the
accessor, so the seam exists. Generalise it to a preview with a language if
that stays cheap; otherwise a parallel field and two spellings of one idea.

### Cards

No new card type yet. `identity` and `intuition` carry definitions and
explanations, and the "here is code, is it right" card waits until there are
enough of them to know what it wants.

**Where a card goes** is a first-match chain, which is what `deck_for`
already is: the card's own tag, then its topic, then its source, then the
project's type map, then the project's deck. Topic above source, because a
topic says what the material is about and a source says where it was
printed, and a deck is something you study rather than somewhere you read.
Most links are unset in any given project, so the chain is long on paper and
short in practice.

A language version is a tag. `cpp20` is filterable in Anki, which is where
"drill only these" is decided. A card that departs from the ambient version
says so in `## conditions`, which renders with the front, so the question is
asked in the right setting.

**Routing needs `tags` out of the content hash.** As it stands, re-tagging
a card to move decks un-approves it for a change nobody reviewed, which is
invariant 5 firing on something it was not written for.

Exempting it is the consistent answer rather than a convenience, because the
inconsistency is already there: `frequency` and `derivation` are exempt
**and they become Anki tags**, `freq::core` and `derive::short`. So today
changing `freq::core` does not un-approve a card and changing
`tags: [core]` does, and they are the same kind of statement landing in the
same place. That is an accident of which field a value lives in, not a
policy.

The rule every existing exemption already implies: **the hash covers what a
reviewer read, and filing is not read.** `requires` says where a card sits
in the queue, `frequency` says when you meet it, a tag says where it is
filed, and approving a card is not approving its filing. The objection that
a subject tag is content does not survive the test: change
`matrix-calculus` to `linear-algebra` and the claim on the card is
identical. A tag that changes what the question means belongs in
`## conditions`, which renders with the front.

What it costs: `check` stops noticing a tag typo on an approved card. That
is already true of `frequency`, mitigated there by a vocabulary that free
tags do not have. The rest is already wired, since `sync` diffs tags against
the live note and `deck_drift` plus `--move-decks` move what the new deck
says.

### Filtering, which is the UI work

This matters more without a book. A book gives you sections, and a section
is a real division somebody made. A project gives you tags you invented,
there are more of them, and they are how you find anything.

The left rail does not scale to that. Every filter is a written-out row,
which is right for six and wrong for forty.

- a tag group with a search box: type to narrow, click to select, selected
  tags pin to the top, counts beside each, several at once
- one control, both views. Units carry tags now, so triage needs the same
  thing review does
- the topic is a separate single-select, beside the section tree rather than
  among the tags
- `frequency` and `derivation` become filters. They are chips on a card
  today and you cannot select by them
- the graph takes them too. It has no filters at all today, so this is the
  first one: a topic or a subject looked at alone, on the canvas as well as
  in the list

Nothing here is specific to a sourceless project. A book with four hundred
cards wants it too, and a tag filter carrying counts is the first thing
likely to make a page render slowly enough to want what "a database" below
describes, which is an index and not a store.

### Code on a card

The review view already handles fenced blocks: `render_body` splits on the
fences and emits `<pre>`, which KaTeX skips. Three gaps are left.

- `check` runs KaTeX over `## back`, so a fence has to be cut out first, the
  way `_prose_only` cuts out display math
- `section-wrapped` fires on anything multi-line, and code is meant to be
  multi-line
- `to_anki_html` turns newlines into `<br>`, so a fence has to become `<pre>`

Highlighting is not built into Anki. The add-ons bake Pygments HTML into the
field when you type it, which we do not need because we write the field. Run
Pygments at sync, the way a picture is rendered at sync: the card file keeps
plain code, the field gets classes, and the colours live in the note type
CSS so night mode works. No add-on for anyone you share the deck with.
MathJax skips `pre` and `code` by default, so the maths renderer leaves it
alone.

### Boundaries to fix while doing this

Not a rewrite. Six seams this leans on that are blurred today, each cheaper
to sharpen now than to work around twice.

**`ProjectConfig` holds two things.** Who a project is and where its deck
goes, and how to read its documents. The second half becomes a table per
source, and `document_for`, `crop_width_for`, `crop_context_for` and
`zotero_for` hang off it. That is what removes the need for a kind.

**Settings resolve by walking a chain, not a fixed ladder.** Unit, source,
project, repo today. Written as a walk, a parent relation or a topic layer
is one extra link and no caller changes. Written as four hardcoded lookups,
it is a rewrite each time.

**The frontend contract is written down and has one door.** In `ledger.py`'s
docstring, with `forge units --add` the only way in for a frontend that is
not a segmenter.

**The two views build their context by hand.** `/units` and `/review` each
compute `from_marks`, the filter dict and the counts inline, and they have
drifted once. One builder, which is also where the resolved properties land,
so a widget cannot read a different value than a pass.

**`check` says "skip these sections" in four places.** Fenced code makes it
five. One notion of which sections are linted as prose.

**`forge.toml` needs a pass, not a rename.** `[repo] projects_dir` becomes
`projects_dir`. `[zotero] units_from` and `[zotero.meanings]` are a marking
scheme, which is a property of a source rather than of a vendor, so the
data directory stays as a machine fact and the scheme becomes the last link
of a chain in a section not named after a company. And the
`Zotero::<title>` fallback inside `deck_for` is provenance picking a deck,
which belongs in the routing chain rather than as a branch in the middle of
it. Same code as the config split, so the same pass.

### Migrating rather than staying compatible

**No compatibility code for our own file formats.** There are two projects
with real content, the Cookbook and the Krause script, and everything else
is demo that never reached Anki. Carrying a fallback forever to avoid
editing two files is the worse trade.

So: no `projects/` falling back to `sources/`, no `--source` alias, no
list-of-strings form of the source table. A script moves the two projects
and the tests move with them.

**`LEGACY_UNHASHED_FRONTMATTER` goes with it.** It exists so that widening
the exemption does not invalidate a deck stamped under the old rule, and
the same migration re-stamps every approved card instead. That is honest
because nothing about those cards changed except the rule, it is one time
rather than permanent, and it clears the way for the `tags` exemption above
and for whatever the next one is.

**The line is at the collection.** Repo files get migrated; a live Anki
collection does not. Tags are safe because `sync` diffs them, so a renamed
tag would migrate itself. The note type is not: renaming it orphans every
note and its review history, which is what `PREVIOUS_NAMES` is for and it
stays.

One thing deliberately not migrated: `Locator.equation`. Its shim exists
because `extract/pdf.py` is frozen, not for compatibility, so rewriting 751
ledger lines to say `kind` and `label` would still leave the shim in place
on the write side. No new fact, so no change.

### What the website does, and what it does not

The setup stage is file edits: create a project, add a source, write a
topic, keep or drop a reference. Instant, local, no Claude, which is what
§12 is about, and the app already rewrites card markdown line by line to
resolve and edit annotations, so this is that machinery pointed at another
file.

The proposing passes stay copyable commands in the panel. That is what
"Triggering Claude from the website" settled and nothing here reopens it.
The division is clean enough to state: **the website edits files, Claude
Code does the thinking, and the commands panel is the handover.**

### Docs and pictures

The diagram in DESIGN.md §2 shows one door into the ledger and is already a
frontend behind, since `zotero` is not on it. It grows to three, which is
the picture worth having anyway.

- **CLAUDE.md**: the commands block, the vocabulary, and the conventions
  paragraph, which currently says "a source" where it now means a project.
- **DESIGN.md**: the §2 diagram, and §4's ledger paragraph.
- **README**: prose is yours. It is missing pictures on cards today, and
  this is a second gap, so both want the same pass.
- **assets**: `triage.png` changes with the chip and the commands panel, and
  the setup stage deserves a shot, which means `make_assets.py` needs a rule
  for picking a project the way it picks a marked-up one by a `demo` tag.
  `states.png` stands: the states do not change.

### Build order

1. Hand-write five units into a sourceless project's ledger and push them
   through to Anki. No new code. If the premise does not hold, it fails here
   and cheaply.
2. The config split, the rename and the `forge.toml` pass, the walk-up
   resolver, a source that is a URL, `forge units --add` with slug ids, unit
   tags, the preview and the reference list. One migration script moves the
   two real projects, exempts `tags` and re-stamps every approved card.
3. `forge context` for a unit with no page: the ask, the references, the
   conventions, the permissions. This one decides how good the cards are.
4. The setup stage, topics and outlines first.
5. Fenced code through `check` and `sync`, Pygments, a note type version
   bump.
6. The tag filter and the property filters, and the chip and the commands
   panel reading the unit. Then `/propose` and the outline pass.
7. Docs, README and assets, once the screens have stopped moving.
8. End to end tests over the whole of it, last: a project created, a topic
   written, units proposed, triaged, carded, checked and synced, with the
   browser driving the setup stage. Each step above carries its own unit
   tests as it lands; this is the pass that makes sure they compose.

### What no property settles

**Ask for less per topic.** "The standard containers" produces forty even,
shallow proposals that all survive triage because none is clearly wrong. A
topic you can enumerate does not: "the erase-remove idiom and what replaced
it", "when a `vector` invalidates". Breadth comes from many small topics.
Guidance for the skill, not a check, and that goes for every other worry on
this page: with no crop to check against, each one wants to become a `check`
rule and none of them is mechanical (invariant 6).

**A unit with no authoritative source costs something, and no rule recovers
it.** A book gives review a crop, and a wrong card is obvious in one glance.
Without one there are two weaker nets: the references keep a card from being
invented, and the loop catches the ones that are plausible and wrong, which
is the annotation, `/triage`, the settled note that keeps what you asked,
and `feedback` from Anki. Cost moves from triage to review, the opposite of
the Cookbook, and the pressure that comes with it is a bulk approve. There
is not one, and invariant 1 is the reason.

**Trigger:** none needed. The first sourceless project is the test.

## 12. Running a command from the website

The commands panel gives you a line to copy. Some of those commands need no
Claude and no watching: `zotero`, `sync`, `check`, and everything in §10 that
is a file edit. A button for them is not the thing "Triggering Claude from
the website" rejects, which is about pushing a prompt into a session. The
aim is that every command with no model behind it is reachable from the app.

Two kinds, and the easy kind is worth doing first. **A file edit** writes a
directory or rewrites a line and answers immediately: create a project, add
a source, write a topic, keep or drop a reference. The app already rewrites
card markdown line by line, so this is that machinery pointed at another
file, and it needs nothing new. **A long run** is `zotero`, `sync`,
`extract`. Those want a job to stream and cancel, which the app has none of.
Build that when a button is what you actually miss.

**Trigger:** the first project you create by hand while the app is open.

## 4. Publishing, what is left

**The demo recording.** `assets/make_assets.py` carries the shot list in its
docstring. Not scriptable: the interesting part is the pace of triage and no
script knows how long to pause.

**Half of this does not run without Claude Code**, the flip side of having no
LLM code in the tool. The committed ledger and the `.apkg` export are the
mitigation: they show the output without running the half a stranger cannot.

---

# Ideas, not scheduled

## 5. The model page extractor, and why it stopped being the plan

This was "the risky half" everything else was buying time for, and **the
argument for it has been overtaken by what got built.** The case was that
`extract/pdf.py` is specialised to one book (§9 measures how), so a second
source needs a general extractor reading page images and reporting
`(kind, label, page, bbox)`.

Two things happened. **Zotero brings its own geometry:** an annotation carries
rects, a page index and a sort index, so a marked-up source is crop-backed
with no segmenter at all. And **prose stopped being segmented:** a unit from
free-form text must be triggered by an annotation, which removed both a prose
segmenter and the triage bottleneck several thousand paragraph-level
candidates would have created.

What is left is narrow: a second formula-reference-shaped PDF that is not the
Cookbook and that you do not want to read through Zotero.

Three things constrain whatever is built. The locator generalises by shim:
`equation: int` becomes `kind` plus `label`, and `pdf.py` keeps emitting what
it emits, so generalising never means editing a frozen module. **The
contiguity oracle survives**, because theorems are numbered contiguously
within a chapter and the same 1..N check runs per label family. And judgement
stays put: extraction produces units, never cards.

**Trigger:** a source you want to card that is neither the Cookbook nor marked
up in Zotero.

## 6. Figures, and everything that is not a text block

`page_blocks()` skips every block whose `type != 0` and never consults
`page.get_drawings()`. So a diagram worth carding never enters the ledger,
equations set as images return nothing and say so in no way, and vector-drawn
math is lost the same way, fraction rules included, which TeX draws as thin
filled rectangles and which are a font-independent "there is math here"
signal. The Cookbook has neither, which is why this has never bitten.

**All three blockers dissolved for a marked-up source:** Zotero's image and
area annotations are figure units already, "a figure card needs a `type`
beyond `identity`" stopped being one when `intuition` landed, and a card can
now carry a picture (`![...](unit:<id>)`, rendered and uploaded by `sync`).
What is left is segmenter work -- finding a figure in a book nobody marked up
-- and the segmenter is frozen.

Worth doing alone if the fallback segmenter is ever touched: fraction rules
from the vector layer as a math signal in `score_line`, which would make it
far less dependent on Computer Modern font names.

## 7. The cross-check between two extractions

An LLM is not mechanical, but **agreement between two independent extractors
is**, and the equation number is an exact join key. Contiguity is built
(`forge audit`); transcription is built (`/transcribe`) but is one extractor,
so it reconciles nothing.

- **Cross-extractor join:** a pass that reads the *page* and reports the
  equations it finds, joined on equation number. It must read the page, not
  our crops: fed our own crops it inherits our segmentation errors.
- **Round-trip render:** the only check that catches a *wrong* transcription
  rather than a missing equation. Render `tex_auto` with KaTeX, compare
  against the crop, store the agreement as a number. Without it, transcription
  trades a detectable failure for an undetectable one.
- **The coverage oracle:** a text block inside no unit's bbox was dropped, and
  measuring that is cheap and exact. Narrowed by the decision not to segment
  prose, since most of a prose page is meant to be outside every box, so what
  survives is "is every *named statement* inside a unit".

**All of it needs §5.** A second extractor is the whole idea.

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

**BYOK and LLM calls in the tool.** "No LLM API code in the Python" is why
there is no torch, no key handling, no cost model, no injection surface and no
vendor in the dependency tree. That is a position, and it is more interesting
than the feature. If it happens it belongs in a separate package implementing
the same contracts the slash commands do.

**A hosted live demo.** The app writes to the local filesystem, so a public
instance is either read-only, and therefore not the thing, or a vandalism
target, and it would need the documents hosted.

**Docling** (and marker, MinerU). Measured on this book: 19.7 s/page against
0.18, five regions where we find twenty on the packed page, and no LaTeX
without a second model. Its advantage is generality, and §5 gets that more
cheaply. It would earn its place on a **scanned** PDF, which is also §6.

**Auto-generating units from free prose.** A prose unit must be triggered by a
Zotero annotation. This is what demoted §5.

**A placeholder `conventions.md`.** An empty one is indistinguishable from a
real one to everything that reads it, and would silence the warning it should
raise.

**An htmx or SPA rewrite.** FastAPI plus Jinja2 is already the simple
framework, and an auto-updating counts strip is twenty lines of fetch and
swap. Adopt htmx if that code gets written a third time.
