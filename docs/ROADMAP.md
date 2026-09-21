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

**Done.** The DESIGN.md §2 diagram shows all three doors into the ledger and
the verb table names `zotero` and `sources`; §6 describes the shelf and the
setup stage beside the three deck views; CLAUDE.md carries `forge sources`
and says a convention belongs to a project.

**Left:**

- **README**: prose is yours. It is missing pictures on cards today, and
  this is a second gap, so both want the same pass.
- **assets**: `triage.png` and `review.png` were retaken part way through
  the setup work, so they show the commands panel before it was split into
  action and info and before a command stopped breaking mid-token. Retake
  both. The setup stage deserves a shot of its own, which means
  `make_assets.py` needs a rule for picking a project the way it picks a
  marked-up one by a `demo` tag. `states.png` stands: the states do not
  change.

### Build order

**Built.** The eight steps below are done, and what each one settled is kept
because the reasoning is the part worth having later.

1. A project with no source walks from `units --add` to a note in Anki,
   covered by `tests/test_end_to_end_project.py`. The premise held: only the
   first layer changed.
2. The config split, the rename, the `forge.toml` pass, `units --add` with
   slug ids, unit tags, the preview, the reference list, the migration and
   the `tags` exemption. Settings resolve through one walk outwards
   (`config.settled`) rather than a ladder written out at each call site, so
   a parent relation or a layer for topics is one more argument and not four
   edits.
3. `forge context` says plainly when nothing settles a card, and hands over
   the unit's references, the project's shelf and the ask where the page
   would be.
4. The setup stage, at `/setup`: what a project reads, what you asked for,
   and which outline entries still have no unit. That last is the only thing
   on it you cannot read off a file, and it is where a pass that stopped
   halfway stops looking like a subject that was smaller than you thought.
   One write, recording an ask, which is a heading appended to `topics.md`.
   A list and a panel: asks on top, sources underneath, a handle between
   them, and whichever you pick opens on the right. Every panel is rendered
   and the script shows one, so the page is still a plain document without
   it, and the fragment says which panel, so it is a link you can send. The
   page drops both rails, which were a triage filter and a guide to triage
   beside the one screen that is all controls, and it takes the whole window:
   a centred column with the page showing round it read as a dialog somebody
   had forgotten to close.

   **An ask stays selected while you read its works.** One with four behind
   it is the case the panel is for, so picking an ask narrows the list below
   to the works it drew on and stays lit itself. That relation is derived,
   not declared: a unit records the document it was printed in and the
   references it stands on, and an outline entry joins to its units by slug,
   so it is a walk over what the ask produced. A third list in a file would
   be a fourth thing to keep in step, and it would go stale the first time a
   pass proposed a unit against a work nobody had written down. `units --add`
   takes `--document` for the same reason: a proposal from a cluster has to
   be able to say which paper.

   The works list also filters by what a work *is*, which is a property and
   not a kind key: `authoritative` is "there is something here to segment",
   and it is already derived.

   **A source's panel is where the per-work settings live**, each saying
   whether the work set it or inherited it. See "what belongs to a work"
   below.

   Three columns, every ratio draggable: what to run next, what the project
   holds, and whichever one you picked. The commands column folds away,
   because what to run is a question you ask twice a session and the other
   two are what you are reading. It is scoped to the *selection*, which is
   the thing this screen can say and the triage rail cannot: triage has no
   idea which ask you are working through.

   Each panel counts what it is holding, in both halves of the pipeline, and
   every count is a link that lands on the triage or review view already
   narrowed to that ask or that work (`?topic=` and `?document=`, resolved
   through the unit a card was written from). The rail over there says where
   the deck came from and offers the way out. Carrying the selection is the
   point: re-making it by hand was the one thing this screen could not hand
   over.

   `approved` doubles as "what sync would push". Nothing local records a note
   id, so whether a card is *in* Anki is a question only the dry run can
   answer, and a panel does not make network calls to draw a number.

   Starting another project moved to the picker. It is not something this
   project holds, so it was never a row in this project's lists.

   **Which work a unit belongs to is asked, never matched.** A Zotero work
   declares the *item* key while its units carry *attachment* keys, and
   empty `attachments` means all of them, so a hand-rolled `document in
   (key, *attachments)` matched nothing: the Krause book's panel counted
   zero units for a work with fifty-six, and offered it the transcription
   pass it had already ruled out for marked-up sources. `ProjectConfig.source`
   is the one definition of that mapping and everything goes through it. A
   work with no `key` and no `zotero` is named after the file it reads, for
   the same reason: a work nothing can refer to cannot be filtered to,
   counted, or copied into another project.

   **Narrow first, then the repo.** You are looking at one project, so the
   command about that project comes before the one about everything:
   `sync --project` above `sync`, `zotero --project` above `zotero --tag
   anki`. Both flags are new. Scoping a sync is safe because nothing there
   deletes, and its lint stays repo-wide because a duplicate uid is a
   repo-wide fact.

   **A pass is offered only where it applies.** `extract` segments a
   document in the repo, so a work that arrived from Zotero is offered
   `zotero` instead: a command that does nothing is worse than no command.
   A marked-up work is offered no transcription pass, which the triage rail
   had known for a while and the setup column had not.

   The rail gained the filter that matched: **works**, where a project reads
   more than one, and above the properties, because project, work, section,
   unit is the order the material nests in. A section says where in the
   book; this says which book. Several at once select the union, like the
   tags, because a cluster of papers is read as one deck. One work is the
   project, so the group is absent there rather than offering a row that
   selects what is already on screen. The section group goes the same way
   when nothing has a section: every unit in one bucket called "no section"
   is a control that selects the whole deck. The bucket stays wherever there
   are real sections beside it, because that is where the units the
   segmenter could not place go.

   **Two works can disagree about a colour.** A marking scheme belongs to a
   document, and a project reading two books marked up in different years
   has two readings of `highlight/green`. Everything that explains a mark
   resolves per work now: the panel beside a crop reads that unit's work's
   scheme, and the guide's legend groups by *reading* rather than by pair, so
   a disagreement lands as two rows and each says which works it speaks for.
   Where they agree, which is nearly always, the rows merge and the legend is
   the one it always was. The guide's `units_from` row goes quiet with more
   than one work, the same way the crop rows do.
5. Fenced code through `check` and `sync`, highlighted by Pygments at sync
   as an optional extra. No note type version bump: the CSS changed, so the
   first sync wants `--templates`, and a new model name would orphan every
   note on the old one.
6. Both lists and the canvas filter by tag, `frequency` and `derivation`
   are selectable and not only readable, and the commands panel offers the
   passes a project can actually run. The context chip is absent where there
   are no pages. The three groups are **one** control: a search box that
   lists nothing until you ask, narrows as you type, and shows what is on as
   chips under it. One comma-separated parameter carries the lot, which is
   what makes several at once mean **or**: separate parameters can only
   narrow each other, and a second choice nearly always emptied the deck.
   Selected filters do not pin to the top of the list as this page first
   proposed: the chips say what is on, and a list that rearranges itself
   under the pointer is worse than one that does not.
7. Docs: the DESIGN diagram shows three doors rather than one, CLAUDE.md and
   CONTRACT.md carry the vocabulary, and the assets are re-rendered. **The
   README's prose is still the author's to write.** Pictures on cards and
   code on cards both work; the README does not yet say a card can carry
   either, and it says nothing about a deck with no book behind it.
8. End to end over both halves: `tests/test_end_to_end_project.py` for the
   pipeline and `tests/browser/test_project_view.py` for the screens.

### The shelf is a page

`/projects`, and the app opens on it. Landing on a deck meant landing on
whichever project happened to be first, which is an answer to a question
nobody asked; what you do first is choose what to work on.

It was a dialog over whatever you were reading. A dialog with a left rail in
it is a page that has not admitted it yet, and as a page it can be filtered
by a link, which is how every other list here works. The rail holds the tag
filter, the form that starts a project with no document, and the repo-wide
commands; the middle keeps the free-text search, centred over the grid it
narrows.

**No project is in force here.** This is the one screen that is not about
one, so it carries none of the row that is: no project name, no setup link,
no canvas, no settings panel. Each of those needs a project, and the page
answered "which one" with whichever sorted first, then offered its setup
stage. The search sits in the bar instead, in a cell the width of the rail
so the two line up, which is also why the page needs no heading: the bar
says where you are. The counts poll behind the reload hint asks for
`scope=repo` here, for the same reason: without it the shelf offered a
reload when one arbitrary project changed and stayed quiet for the rest.

**Two tags narrow here and widen on the deck rail.** The same control over
different things. A unit's tags are subjects it could be about, so two of
them is a union and asking for both of two narrow tags on a deck would
empty it. A project's tags are facets of one thing (`cpp`, `paper`,
`reference`), so asking for `cpp` and `paper` means the paper about C++.
The word between the chips says which, because two chips side by side look
the same either way round and the answer decides whether a second choice
widens the shelf or narrows it. Each tag counts what picking it would
*leave*, over what the other choices already left; a tag that would leave
nothing is dimmed rather than dropped, so the list does not reshuffle under
the pointer.

**Material is a label, not a filter.** Where a project's material came from
is worth saying on the card, and it is not how anyone picks one: you choose
by name, by subject, or by how much is left to do. It filtered for as long
as this screen was a source picker, and it is a project picker now.

**Commands are split by what they do.** An info command shows you something
and an action command changes a file, and that difference is the whole
reason these are copied rather than launched, so it is worth more than a
sentence in a tooltip. The action commands come first, because they are the
work; each half folds, because four you run and six you read is ten boxes in
a 240px column with the one you want under the other nine.

The multi-select filter is one macro now (`_pick.html`), shared by the rail
and the shelf, and the list of commands is another (`_runs.html`), shared by
those two and the setup stage. Four spellings of the same markup is how one
of them ends up without the hover that says where to paste it.

### A command is an object, not a place it is written

`app/runs.py`. Every list of commands in the app comes from one registry:
`Offer` says what to run, what to say about it, and the one condition that
decides whether it applies; `Ambient` is every fact it may be keyed on.

An offer reads ambient state and **never which screen is asking**. `where`
says which screens may show it, so a command that belongs on two of them is
one object in two lists rather than two objects free to disagree. They did
disagree: the same command was written as a dict literal in three places,
and `/transcribe` was offered against a Zotero item on the setup stage and
refused on the triage rail. The screen that offered it was wrong, and the
one that was right could not fix the other.

The rest follows from having one table. Ordering is a property of the
command rather than of the list it lands in: `scope` runs `work`, `topic`,
`project`, `repo`, narrowest first, because you are looking at one work and
the repo-wide form is what you reach for afterwards. A condition is written
once, so a work with nothing segmented out of it yet is offered the
segmenter and not the passes that read a crop, on every screen at once. And
a project of several works gets both doors, `zotero --project` and
`extract`, which the branch-per-screen version could not express: it asked
what kind the project was and there was only room for one answer.

Writing a condition once also makes it worth getting right. `/transcribe`
was gated on the `new` count, which is a triage state standing in for
"nobody has read this crop yet": sixteen new units that had all been
transcribed still offered the pass, and running it reported nothing to do.
It is gated on an `untranscribed` count now, and the label says that
number instead of guessing from the other one.

Adding a screen is adding a name to `WHERE` and a `where` to the offers
that belong on it. Adding a command is one entry.

### Editing a scheme where you can see the marks

What a colour means, and which marks become units, is the one part of the
config you change while *looking* at the marks: you import a book, triage
twenty units, and find that the orange highlights were the ones worth
carding. Until now that meant opening the TOML and remembering the
`"kind/colour"` spelling.

It is on the work's own panel, because a scheme belongs to a document. Only
for a work that came from Zotero, because marks do; only the pairs that work
actually carries plus the ones it declares, because eight colours across six
kinds is forty-eight rows and nobody has forty-eight meanings; and the
"makes a unit" checkbox only where something is extracted from the work,
because a mark cannot make a unit in a document nothing is segmented out of.

**The writer is line-wise, not a rewrite.** A generated `project.toml` is
mostly comments, and a round trip through a TOML writer would produce a
correct file with all of them gone, which is a worse file than the one you
started with. `scheme.py` finds the one `[[sources]]` table it has to change
and edits the lines inside it. It parses the result before writing: a file
it refuses to read is a project that will not load, and the app would
otherwise have written it while saying it had saved.

Adding a work the repo already reads offers the same distinction as a
checkbox: a reference is free, and extracting is a claim on the document
that one project holds.

### What belongs to a work

A project may read several works, so every setting had to be asked which of
the three levels it is a fact about. The answer moved three things and left
the rest alone.

- **Repo.** The Anki connection and the flag map, the Zotero data directory,
  `language`, `front_char_cap`, `study_order`. None of them is about a
  document or a deck.
- **Project.** `deck` and the two deck maps, `order`, `web`, `tags`, and the
  `[conventions]` table. These are decisions about a *deck*: which pile the
  cards go in and what the reader may do while writing them.
- **Work.** `crop_context`, `crop_width`, `units_from`, the colour meanings,
  `convention_keyword`, and now `context_pages`, which moved. How much page
  a card writer needs is a fact about how a book is set, exactly like how
  much page frames an equation, and a project reading a dense textbook and a
  six-page paper has two answers. `context_pages_for` already said so in its
  own docstring while reading the project's value.

The settings panel behind the gear follows: a group per work rather than one
flat project group, because one `crop_context` under a project's name is one
book's number labelled as the deck's. The guide's "this source" card says
"per source" instead of a number when the project reads more than one.

**`[conventions]` is the open question.** It is project-level, and
`conventions.md` is one file per project, while `layout` decides what every
derivative on every card from *that book* means. A cluster whose two papers
disagree about notation has nowhere to say so. Splitting it per work is not
hard (the table would sit in `[[sources]]` and `conventions_for` would take a
document, like the rest), but it changes what an existing card's derivative
means the moment two works disagree, so it wants a deliberate sitting rather
than a quiet default. Until then, a project whose works
disagree about notation is a project to split.

### Accepting a source

Two shelves, and both have a flow now.

`references.md` is prose, and a line carries its own pending state: `- [ ]
something` is proposed and nothing else is. The checkbox is markdown anyone
would write for "not yet", `check` never reads it, and a pass that stops
proposing leaves nothing behind to clean up, so there is no second file to
keep in step. `/sources` writes the pending lines; the setup stage shows
them among the sources, with take and reject; both are the edit you would
make in an editor. Taking one writes the `[[sources]]` table, which is the
next section.

A `[[sources]]` entry is the other kind. It carries a marking scheme, crop
settings and a file, so it is not something a pass should write. What the app
does write is the half with no judgement in it: **a reference**, either a
work the repo already reads somewhere else or a page you type in. A paper can sit in two projects, cited by one and
extracted from by another, and adding it copies nothing, because a Zotero
work is its item key and a reference is its URL. `forge sources` lists every
work across every project, which is the question that had no answer once a
source stopped being a project.

Refused where the project is configured in `forge.toml` rather than its own
`project.toml`: a folder's file wins over the root file key by key, so
writing one would not add a table, it would replace that project's whole
source list with the single entry.

### A proposed source becomes a source

Proposed, accepted, set up: three steps in one list. A pass writes
`- [ ] Name (address), what it is for` into `references.md`, the setup
stage shows those lines **among the sources**, and taking one writes a
`[[sources]]` table and lands on its panel.

**The list, not the shelf.** The proposals were on the project's own panel,
under the shelf, which is where a reference lives and not where anybody
looks for a source. A pass proposed six and they read as having gone
nowhere; the report said it had written them and the sources list said
nothing had happened.

**Accepting writes the table.** It used to take the checkbox off and leave
the prose, so a proposed source never became one: no panel, no settings,
nowhere to say how to read it. The line leaves `references.md` as the table
appears, because the same fact in two files is the one that drifts.

Nothing accepted this way is authoritative. It has no files and no item
key, which is the whole of what that means, so no pass runs against it and
`check_sources` has nothing to say about it.

**Three parts, split on the address.** A name, a URL in brackets, and what
it is for. The URL is the only part with a syntax, so it is what the split
is made on: everything before is the name, everything after is the purpose.
A line with no address is all name, which is right for a book you own.

**`note` is the half that is not an address.** Which questions a source
answers, which part to read, what to cite. It comes across from the
proposal and is editable on the work's panel, which is the "setting up the
source" step: for a reference it is the *only* setting, because every other
one on that panel is about cutting a crop out of a page.

`forge context` hands it over, with the declared references above the prose
half of `references.md`. A reference nothing reaches is a line in a config
file, and that was the argument for putting it in prose in the first place;
it is answered by the writer of the context handing over both.

**What a key looks like.** Slugged from the title and cut at a word, not at
a character: it goes in a table, in a unit id and on a command line, and
`cppreference-the-containers-libr` is a word you have to check against the
file every time. A collision takes a `-2`.

### One source per site

Several pages of one site are one source, read in several places, and the
note says which. Six rows for six pages of cppreference is six times the
same source: a card writer handed all six learns nothing the first one did
not say, and the shelf that was meant to be short is a list to skim.

So adding a page of somewhere the project already reads does not add a row.
It widens that source to the deepest address both are under and folds the
new part into its note, labelled by the tail of its address:

    url  = "https://en.cppreference.com/w/cpp"
    note = "container: the complexity tables; algorithm: equal_range and
            lower_bound; named_req: what a comparator must satisfy"

Both halves are labelled, not just the new one: widening
`.../w/cpp/container` leaves the old note describing a page the address no
longer names, so it takes the tail it used to carry. Only while the address
is moving, because after that the note is already labelled.

**The host alone is not the rule.** Two arXiv papers are
`arxiv.org/abs/<id>` each, and merging them would make one source out of
two unrelated documents, which is a worse error than six rows for one
manual. Two shared path segments is the line: it is where a path stops
naming the site and starts naming a section of something. It is a
heuristic, it is written down in `SHARED_SEGMENTS`, and the case it is
wrong about is two sections of one book hosted at `site.com/a` and
`site.com/b`, which stay two rows until somebody merges them by hand.

**And the ask is the other half of the rule.** Two asks reading two parts
of one site are two sources, because the thing a card is checked against
is the part and not the domain: widening them together would hand whoever
is writing about containers a note about threads. So a source records
which ask it serves (`topics`), and the merge only folds a page into a
source with the same one.

Where that comes from: a `##` heading in `references.md`, naming the ask,
with the proposals for it underneath. A heading is what anybody writing
the file by hand would use, and reading one is the same thing the outline
counter already does with a prefix: read, not parsed. It is taken off the
*file* when the line is accepted, rather than from whatever the browser
had selected, because the file is what survives an edit.

Never into a work something is extracted from. A page of a website is not
part of a book somebody is segmenting, whatever the addresses share.

### A source you can take out again

`forge sources --remove <key> --project <p>`, and a folded control on the
source's own panel, with the key typed to confirm.

What goes: the `[[sources]]` table, and **the units that came out of it**.
A unit whose work is gone has no crop to render, no scheme to read and no
settings to resolve, and `extract` writes them again from the document if
it comes back. The document itself is never touched.

Cards are the gate, as they are for a whole project: `--force` is how you
say you mean it, and the app does not offer the override. The ledger keeps
every line that was not this work's, byte for byte, because it is a record
of decisions and rewriting the lines nobody asked about makes a diff
nobody can read.

### What a proposed book is

A reference with a name, and no address, because nothing here can open it:
"Josuttis, The C++ Standard Library, 2nd edition" is a work you have on a
shelf. It reaches a card writer as a line, which is all a reference is.

It has the same three parts as a page, with nothing in the middle one, and
`, for ` is what ends the name where an address would. That is a guess
about prose rather than a syntax, so it takes the **last** one (a title can
carry one: "A Course in Combinatorics, for Beginners") and what it
produces is editable on the panel. Getting it wrong costs one field
somebody retypes; not trying costs a title with a whole sentence in it.

It is also one step away from being more than a reference, and the panel
**proposes that step rather than taking it**: put the document in Zotero,
mark up what is worth carding, and run `forge zotero <citekey> --project
<name>`. That command writes the item key, the attachments and the marks
together, which is what turns a reference into something units come out
of. Declaring `zotero = "..."` by hand would name an item nobody marked.

### Authoritative is a property, not only a shape

It was derived: a work with files, a tex file or an item key was
authoritative, and nothing else was. That is the right default and it was
the only answer available, so a paper you own, want cited, and want no
units out of could not be said. `extract = false` says it, and the
work's own panel has the switch.

It only ever turns extraction **off**. A work with no document has
nothing to segment, and `extract = true` on one would be a claim the
folder cannot honour; the honest way to make something authoritative is
to give it a document.

**It is reversible, and that took two goes.** Turning it off deleted
every untouched unit of the work, on the reasoning that a unit whose work
nothing is extracted from is one no pass can render. That reasoning was
wrong: `extract = false` does not remove the document, so the crops still
render from the geometry the units carry and the scheme still resolves.
What it produced was a switch that destroyed work in one direction and
did nothing in the other, so turning it off to see what it did cost five
units and turning it back on did not return them.

Off now stops units coming out of the work and leaves the ledger alone,
in both directions. The import refuses to add units to such a work and
says how many marks it passed over, which is the one place new ones would
have arrived. The scheme rule is unaffected: unchecking a colour still
forgets the untouched units that colour made, because those units should
not exist under the scheme you just wrote.

### Provenance is not permission

`ProjectConfig.source(document)` answers two questions through one
fallback, and they want different rules. **Which work did this unit come
out of** must survive `extract = false`: the units you already triaged
keep naming its attachments, and asking for `authoritative` there left
every one of them belonging to nothing the moment the switch went off,
taking their crops, their scheme and their mark counts with them. **Which
work do I segment now** must keep reading `extract`, or `forge extract`
is handed a work somebody refused.

So they are two functions. `source(document)` is provenance and never
reads `extract`; `segments()` is permission and always does, and
`extract.run` is its only caller. Both keep the older rule that stops the
guessing: exactly one candidate or none, because reading one book's
scheme onto another's crops is the failure this function exists to
prevent. Provenance counts the works that hold a *document*, permission
the ones the switch is on for, and that is the whole difference between
them.

Counting the wrong set was not hypothetical. With two books in a project
and one switched off, `source` fell through to "the single authoritative
work" and handed **every** unit to the other book: the works filter
showed none under the switched-off one and all of them under its
neighbour, its panel said "nothing has been imported from this work yet",
and removing the neighbour offered to take the other book's units with
it.

The import refuses rather than warns. `extract = false` says no units
come out of this work and an import is the one place they would arrive,
so it reports the marks it passed over and writes none. Re-running to
refresh a title, the other reason to run it, still works, and so does
the text layer: that is context for the units already there.

### Two readers of references.md

`shelf()` is what a card writer is handed: the declared references and
the prose, composed. `references_prose()` is what the setup stage shows:
the file, and nothing else.

They were one function, and the page read the composed version, so every
accepted reference came back as a shelf line with an accept button on it,
for a source that was already accepted. The buttons did nothing either
way: `drop_proposal` cannot find a line that is not in the file, and
accepting one would have written a second table for a work already
declared.

The page also never drew the prose half, so a `references.md` written as
paragraphs rendered as "No references.md". It draws it now, and the empty
state keys on the file rather than on the list items.

### A zero is an answer, and ten zeroes are not

The mark tally counts what is in the ledger. A work nothing has been
imported from has nothing to count, and the column printed ten blanks,
each of which reads as a lookup that failed. The column is drawn only
where there is something to count, and the reason is said once. Where
there is a ledger, a pair nobody used prints `0` rather than nothing.

### Two gates and a label

Three settings on a work's panel look like three answers to one question,
and they are not. Worth saying once, because the panel now says it too:

- **`extract`** is the gate. Anything segmented out of this work here, yes
  or no. `authoritative` is not a fourth thing: it is the name this answer
  goes by once the work has a document, and the derivation is
  `has a document and extract is not false`.
- **`units_from`** is the second gate, under the first. Given that
  extraction is on, which marks start a unit. Unchecking every row is the
  same answer as closing the gate above, for this work.
- **`meanings`** is a **label**, not a gate. What a colour means shows on
  the unit and in triage whether or not anything is extracted, and it
  never decides whether something exists.

**An empty answer is an answer.** `units_from = []` was read as "nobody
said" and inherited the repo-wide list, so the one action that says "stop
making units out of this" was the one action with no effect: unchecking
every box in the editor wrote a list that meant the opposite of what it
said. `None` is nobody said and `frozenset()` is none of them, and the
resolver asks `is not None`.

**The editor offers the scheme, not the marks it happens to find.** Its
rows came from the marks in the ledger alone, so a narrowed scheme, which
takes the untouched units of a dropped colour with it, emptied the table:
the mapping read as deleted and came back only after a re-import. The vocabulary is the
union of what is marked, what the work declares and what the scheme in
force names, so the table is the same before the first import, after it,
and after switching extraction off and on.

### A setting that changes the ledger

Unchecking a colour in the scheme editor left its units in place, as full
units, in every count and every filter and every pass. The editor calls
`apply_scheme` now, which is `drop_from_scheme` pointed at a project
rather than at one import: untouched units of a pair that no longer makes
one are forgotten, decided ones stay and are reported.

The switch above does **not** call it. It used to, on the reasoning that
the two questions were one question a level apart, and that let the one
control promising to keep your units delete some of them for a reason it
never named. The scheme rule lives in the scheme editor.

### What else was reading the switch

A work that holds units and makes no more was unreachable until the
switch stopped deleting them, so everything that had been using
`authoritative` as shorthand for something else was correct by accident.
Nine places were not, and each had picked a different wrong synonym:

- **"is this project made of anything"**, four views deep. A project with
  a Zotero item and a full ledger reported "nothing declared", lost the
  import from its command rail and was offered `forge extract`, which
  errors. `project_origin` answers what the material *is*, and the switch
  does not change that.
- **"are there units here to read"**, on the panel's command rail. It
  said "nothing to run" over three untranscribed crops. The passes that
  read units ask `readable` now; the two that make units keep asking
  `extracted`.
- **"does a setting apply"**. The crop width, the crop context and the
  page window are in force for the units already there, and the panel
  stopped showing them. A setting in force with nowhere to read it off is
  the one that drifts.
- **"which marks make a unit"**. The column was drawn only for a
  switched-on work, so the save omitted `units_from`, and `scheme.write`
  dropped the key rather than leaving it alone as its docstring promised.
  Saving a caption deleted the work's own scheme and then judged its
  units against the repo-wide one.
- **"is this two projects extracting one work"**, in `check`. Turning the
  switch off in the second one left both ledgers full and silenced the
  error, which is the duplication the check exists to catch. It counts
  the projects a work has units in.
- **"is this shelf material"**, for a card writer. A book you stopped
  segmenting is a reference to every other card in the project and is
  still the book *its own* units were cropped from, so `context.shelf`
  takes a work off its own shelf and leaves it on everyone else's.
- **"does anything settle what this card says"**. A unit from a `.tex`
  work has no crop, so the switch was the whole answer for it: switching
  the work off told a card writer there was no source at all and withheld
  the page the unit was printed on.
- **"what kind of thing is this"**, in `forge sources`. A book with
  extraction off printed as `reference`, in the same column as a URL
  somebody put on the shelf. Three states, three words.
- **the diagram**, which printed three invented mark pairs whenever the
  project's own list came back empty.

### Which source, and which ask, in the rail

The two coarsest divisions there are, and the triage rail had neither as a
control. `document` was filtered but its group appeared only for a project
declaring two works, and it dimmed a row by `authoritative`, so a book
switched off with fifty-six units in it read as unavailable. `topic` was
filtered and had no control at all: it appeared as a read-only line saying
where the deck had been opened from, because the only way to set one was
to arrive from the setup stage.

Both are `_pick.html` now, the control the tags already use, which prints
the word that joins two chips on the control itself. **Sources take the
union** and **asks take the intersection**, and those are not arbitrary: a
cluster of related papers is read as one deck, so a second paper adds; an
ask states what the deck should contain, so a second ask asks what is
under both.

The intersection is well defined and thin. A unit joins an ask by its
slug and carries one, so two asks leave something only where both
outlines list the same entry. That is a real state and a rare one, and
the per-row counts are computed over what the other filters left, so a
pair that would empty the deck reads 0 before the click rather than
after it.

**The rows add up to the deck.** A Zotero unit names the *attachment* it
was printed in and a work declares the *item*, and the two meet only
through `attachments`, which the import leaves empty to mean "all of
them". With one work holding a document that is enough, because there is
one answer to fall back on. With two it is not, and every row read 0 over
a full deck. A document no declared work answers for now gets a row of
its own, under the only name anything here knows it by, and naming the
attachments on the work gives it its title back.

A card is not one unit. `unit:` takes a list, and the units it merges may
sit under different asks and come out of different books, so both filters
read `Card.units` rather than the first of them.

`/api/counts` reads the same three filters the page drew with. The mini
diagram is repainted from it a few seconds after the page settles, so a
filter the endpoint did not read showed as the numbers moving on their
own.

### An empty ledger is not a filter

`/units` with no `?project=` steps past a project with no units, and the
test was whether the ledger *file* was there. `Ledger.save()` writes an
empty file for zero units, so the guard stepped onto exactly the project
it was meant to step past: the first one in the config, no units, and
"nothing here with this filter" over a rail with no filter on. It reads
the ledger's contents now, walks the configured order rather than the
glob order, and redirects so the URL says where it landed, because the
script polls `/api/counts` with `location.search` and was painting one
project's numbers onto another's rail.

### The setup stage says less

Twenty-eight blocks of explanation came off it. The rule applied: a label
says what a control does, and an explainer that repeats the label is
noise. What stayed is what a reader could get wrong and act on, which is
mostly consequences (what deleting a project takes with it, what the
extract switch does *not* do) and provenance (set here, or inherited).
The Jinja comments stayed in full: they are for whoever edits the
template, and the reasoning is the thing worth keeping.

Two are worth naming because they were not trims. The topic panel's list
of sources was a row per work reading name, kind, and a checkbox labelled
"reads it"; the label is a heading over the list now and the rows are
checkboxes, which is the same fact said once instead of once per row.
And the boxes are kept in step across panes: one pane per ask means one
box per ask, each rendered with its own copy of that work's set of asks,
so ticking a work under two asks in a row posted the copy made before the
first write and silently unsaid it.

### Opening the file is the whole cost of a crop

A crop renders off an open document in about 4ms, which is the number the
ledger holds geometry instead of PNGs on. `open` on a 16MB, 312-page book
is 1.2 *seconds*, and `render_crop` opened the file per call: a deck of
five units opened one PDF five times and the crops trickled in over seven
seconds, while the same book's full-page view, which is one request, came
up at once. Measured on A Tour of C++: 1317ms a crop before, 44ms after,
and the second visit to a page 50ms.

Documents are pooled now, one lock each because a PyMuPDF document is not
safe to use from two threads and the app answers from a thread pool. A
pooled renderer is dropped and never closed: whoever is rendering holds a
reference, and closing it to save a file handle would pull the document out
from under a thread mid-render. Invisible on the Cookbook, where the open
costs 4ms, which is why it stood for so long.

### A zero written in a file is not an answer

`settled` walked its arguments with `is not`, which reads as the careful
choice and is the wrong one for a number: a `0` parsed out of TOML is a
different object from the `0.0` the resolver calls empty. So `[cards]
crop_context = 0`, which `forge.toml`'s own comment calls the default,
resolved to a real zero. Every crop in the repo was cut tight to its box
with none of the ninety points of page around it that `TRIAGE_CONTEXT`
exists to give, and the setup stage printed "0 points of page" beside it.

By value now, with one carve-out: a bool is never the same answer as a
number, because `False == 0` in Python and they mean different things here.

### The cached text lives with the extraction

`projects/<name>/text-<document>.md`, where `<name>` is the project that
**extracts** from the document rather than the one that asked. A work is
authoritative in at most one project, so its text has one home; cached
under whichever project ran the import, three projects citing one paper
would have three copies with nothing saying which is current.

A document nothing extracts from has no such project, and then the
caller's own folder is the only answer there is.

### How much a card writer is handed

Three answers, not two. `context` on the repo or the project:

- **`none`.** This page, the conventions, and nothing else. A closed
  deck, for when anything read around the source is a way to drift.
- **`references`.** The default, and what the tool did before there was a
  name for it: the project's shelf goes over with every unit.
- **`web`.** The shelf and a search.

`web = true` still says the web and `web = false` still says the shelf
without it, because that is what it always said: the old key was never
the strict answer, it was the middle one. A unit still overrides, which
is the exception the per-unit grant exists for, and a refusal on a unit
of a project that allows the web keeps the shelf: saying "not the web for
this one" is not saying "nothing at all".

**And which references, not just whether.** A reference carries `offer`,
defaulting to the project's, defaulting to `true`. Off, it stays
declared, cited and findable and stops arriving with every unit: six
places to look is a reading list nobody works through, and the
standard's wording belongs on the shelf rather than in front of every
card about a container.

The writers were told none of this. `card-writer` and `augmenter` now
say what the three answers are and that **the references are theirs to
read** when they are handed over: each is a place somebody agreed a card
here can be checked against, with a line saying what it is for. Where to
look, never what to write, because the crop is still authoritative for
what is printed.

### Which ask reads which source

Derived and declared, unioned. The derivation walks what an ask
produced, which is free and cannot answer for a work nothing has come out
of yet: a reference, or a book you imported this morning. So a source can
also say which asks it serves (`topics`).

**A box per source, on the ask, drawn open.** It went to the source's
panel once, as a fold over the asks, on the reading that a list of
sources on the ask duplicated the one in the rail. Two things were wrong
with that: the duplicate the complaint was about turned out to be the
shelf rendering declared sources as lines, and a closed `<details>`
labelled "which asks read it 0" reads as a heading with a stray number
rather than as a control. The relation is set where you would go to set
it, and the source's panel says it in chips.

What a box cannot do is unsay the derived half. An ask whose units came
out of a book read that book, and those are shown checked and fixed.

### An import declares the work

`forge zotero <item> --project <name>` wrote the units and not the source.
The only thing that ever wrote a `[[sources]]` table was
`write_source_stub`, which writes a whole `project.toml` and never
overwrites, so it fired exactly once, for a project that did not exist
yet. Two holes came out of that, and both look like the command doing
nothing:

- **Into a project you already have**, the marks landed in the ledger and
  the work was never declared. The units' `locator.document` then belonged
  to no source, so the crop settings, the marking scheme and the work's
  own panel had nothing to resolve against. The same shape as the
  `/transcribe` bug on a Zotero item: a unit whose work cannot be found.
- **A book you have not marked up yet** produced no units, and the write
  was gated on there being some, so nothing at all was written. The
  command said what it found and recorded none of it.

Both are one rule now: an import declares the work, marks or no marks,
and says where. A book you own and have not read is a source with no
units, which is a normal state and the state the setup stage is for.
`declare_zotero` appends the table, refuses a second project claiming an
item somebody already extracts from, and writes nothing when the project
already declares it, so re-running stays safe.

### The app adds references, and nothing else

Adding a work the repo already reads takes it as a **reference**, whatever
the other project reads it as, and there is no checkbox to say otherwise.
The item key and the files are what make a work authoritative, and writing
those from a web page is the wrong shape twice over: the same document
segmented twice is two ledgers of units and two notes per card in Anki,
and deciding to segment something carries crop settings and a marking
scheme with it. That decision is `forge zotero`, typed where you can see
it, and the setup stage proposes the command.

It follows that "a work is extracted from by one project" is no longer a
rule the app has to *refuse*: it has no way to break it. `check_sources`
still reports a pair somebody wrote by hand.

### A work is extracted from by one project

Read by as many as you like. A paper cited by one deck and segmented by
another is the case the shelf exists for, and a reference costs nothing
because nothing is extracted from it.

Authoritative in two is a different thing, and the answer is to forbid it. A
unit lives in one project's ledger and its id starts with that project's
name, so the same document imported twice produces two ledgers of units, two
piles of cards and two Anki notes per equation, with nothing anywhere that
knows they are the same. Deduplicating them afterwards would mean a unit
identity that spans projects, which is a much larger change than the problem
deserves.

So `check` refuses it (`source-extracted-twice`) and the app will not create
it. An error rather than a warning, because every view here is scoped to one
project: two copies look like one copy from wherever you are standing, right
up until they are both in Anki.

### One folder per project, and several works in it

`projects/<name>/` holds the ledger, the prose files, and whatever documents
the project reads. It already carries several works, and nothing needs a
subfolder per work, because a work is not a folder:

- **A file is a path.** `files = ["projects/x/vol1/ch1.pdf"]` already works;
  the layout under the project is yours, and two works can use subfolders
  today without the tool knowing. What a unit records is not the path,
  though: `locator.document` is matched against a file's **name** or the
  work's key, so two documents in one project that share a basename are one
  document as far as `ProjectConfig.source` is concerned, and the first
  declared wins.
- **A Zotero work has no file here at all.** It is an item key, and the PDF
  lives in Zotero's `storage/`.
- **The derived artefacts are keyed by document, not by work**:
  `text-<document>.md` per attachment, and crops are rendered on demand from
  geometry rather than written out.

So the shared namespace is the document *name*, in two places: the lookup
above, and the cached text, where two documents with the same name collide
on `text-<name>.md`. A Zotero attachment key never collides, and a file you
placed yourself you can rename; `vol1/ch1.pdf` and `vol2/ch1.pdf` is the
case that does not work, and naming them `vol1-ch1.pdf` and `vol2-ch1.pdf`
is the whole fix. Worth teaching the tool about paths only if renaming
stops being enough.

**Not built, and deliberately.** A chip for choosing among a unit's
references. It was listed here while the context chip was still offering
page counts to a unit with no pages; fixing that made the case for it
disappear. `forge context` hands over every reference a unit names, a unit
names one or two, and a setting nobody would change is worse than no
setting. Build it the first time you have a unit with five references and
want three of them.

### Deleting a project

`forge project <name> --delete`, and a folded control on the project's own
panel. One function behind both (`projects.remove`), for the reason
`scaffold` gives: two writers of the same thing drift.

**Three places, or none.** A project is a folder under `projects/`, a pile
of cards under `cards/`, and possibly a table in `forge.toml`. Removing one
and not the others leaves a project that half exists: a folder with no
declaration still shows on the shelf, and a declaration with no folder shows
as a project with nothing in it. The TOML edit is line-wise, like
`scheme.py`, and for the same reason.

**Cards are the gate, units are not.** A project with no cards is a decision
you can make again in one command; one with thirty-nine is weeks of review.
So it refuses when cards are there and `--force` is how you say you mean it.
Units are derived from a document and `extract` writes them again, so they
are reported and not a gate.

**The app never forces.** It offers the delete, refuses the same way, and
names the flag. The override belongs in a terminal, where you type it.

**Anki is not ours to clean up.** An approved card is already a note there,
nothing local records a note id, and deleting the file here leaves the note
behind. The count of approved cards is printed, and that is the whole of
what can honestly be said.

**A name is a folder, never a path.** The function ends in `rmtree`, and
`Path` does not normalise `..`, so `projects/..` reads as a child of
`projects/`: the parent check alone would have deleted the repo. It takes
both, a plain component and a resolved parent, and a test passes it `..`,
`../..` and `a/b`.

### Two bugs the delete was needed for

**`c++` became `c`.** `slugify` maps everything outside `[a-z0-9]` to a
separator, so the pluses went and the folder was `c`, which is a different
language. Names whose usual spelling is mostly punctuation now have one:
`c++` is `cpp`, `c#` is `c-sharp`. Whole tokens only, so `a+b` keeps its
plus, and the title stays what you typed while the folder is the slug.

**A card with no unit haunted every project.** Which project a card belongs
to is read off its unit id, and a card with no unit answered "all of them"
rather than "none" so that it would be visible somewhere rather than lost.
With one book that was right. With a shelf of projects it meant an unfiled
card appeared in a project created a minute ago with nothing in it.

`model.home_of` is the rule now: what the card declares, and failing that
the folder it is filed under, which is the only evidence a card with no unit
has. Filed nowhere and declaring nothing, it still belongs to all of them,
because that case is what the old rule was written for.

Deliberately **not** the same question as which Anki deck it lands in.
`sync` routes by what the card declares, and one that declares nothing takes
the repo default rather than being moved into a project's deck by a rule
about where its file happens to sit: a display fix should not move a note
that is already in Anki. `check` warns (`unit-missing`), and writing `unit:`
closes the gap in both directions.

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

## 13. Keeping the suite fast

1299 tests in about 80 seconds, four workers, and the cap is the point:
`-n auto` on a machine with sixteen cores is sixteen Chromes, which is a way
to run out of memory rather than a way to go faster. `--dist loadscope`
keeps a module's tests on one worker, because the browser modules start a
uvicorn per module and scattering their tests would start it once per
worker instead.

What actually costs time here is worth writing down, because it was not what
it looked like:

- **A broken page costs 30 seconds per test, silently.** Deleting a helper
  that `graph.js` used made every graph page throw on load, and the 22
  graph tests each sat through a Playwright timeout: eleven minutes of
  waiting that read as "the suite is slow". The lesson is the assertion, not
  the speed. `test_the_page_loads_without_the_console_complaining` is the
  one that would have said so in one line, and it is worth having on every
  view that runs a script.
- **No single test is slow.** The worst in the unit suite is 2.4s and the
  worst in the browser suite is 3.7s, nearly all of it fixture setup. There
  is nothing to optimise one at a time, which is exactly the shape that
  parallelises well.
- **Serial runs vary by 3x** with whatever else the machine is doing, so a
  single timing is not evidence. The numbers above are the median of three.

## 12. Running a command from the website

The commands panel gives you a line to copy. Some of those commands need no
Claude and no watching: `zotero`, `sync`, `check`, and everything in §10 that
is a file edit. A button for them is not the thing "Triggering Claude from
the website" rejects, which is about pushing a prompt into a session. The
aim is that every command with no model behind it is reachable from the app.

Two kinds. **A file edit** writes a directory or rewrites a line and
answers immediately. Three are built, all on the setup stage: starting a
project, recording an ask, and dropping a line from the shelf. Each goes
through the same function the command does, which is how invariant 2 stays
true rather than being asserted. Adding a *source* to a project is the one
left, and it is the awkward one: a `[[sources]]` table has a marking scheme
and crop settings in it, so a form for it is a form for the whole of
`SourceConfig`, and editing the TOML is still the better answer until
somebody has done it twice.

Making those work needed one fix behind them. The app read `forge.toml`
once at start, so a project created while it was running was one it had
never heard of, and an edited deck showed the old name until a restart.
DESIGN.md §6 already promised it re-reads from disk on every request; now
the project table does too. Only that table, because `create_app` is handed
a config and must honour it.

**A long run** is `zotero`, `sync`, `extract`. Those want a job to start,
report and finish, which the app has none of.

### What a long run should look like

Three shapes were on the table. They are not equally good, and the third is
mostly right for the reason that makes this feature worth building at all.

1. **A console in the corner**: a collapsible panel bottom right with live
   output and a cancel button.
2. **A chat view**: an indicator in the header, and clicking it opens a list
   of runs with their output in the main pane.
3. **No output at all**: these are wrappers around plain Python, so show the
   *result* rather than the transcript.

**Three is right, with one piece of one.** The output of `sync` is not a log,
it is a table: one row per card, an action, and a reason. `feedback` is a
list of comments taken. `zotero` is a list of items, each with how many
units it made. Every one of them is already a structured object in Python
(`SyncReport`, `CardOutcome`) and gets flattened to lines only because a
terminal has nothing else. `--json` exists on all of them for exactly this
reason. Rendering a table of outcomes, with the skips explained and the
errors first, is both easier to read than the console and *less* code than
streaming: no transport, no buffering, no cancel semantics.

The piece worth keeping from one and two is **progress, not output**. A
sync of 150 cards takes a while and a screen that says nothing looks
broken. So: a small indicator in the header while a run is in flight, a
count when the run knows one (`42 of 150`), and the result rendered as a
table when it finishes. No transcript, no chat.

**Cancel is worth less than it looks.** None of these is long enough to
abandon, and the two that write outside the repo (`sync`, `feedback`) are
worse to stop halfway than to let finish: a half-pushed deck is a state
nobody can read off the files. `extract` is the only one where cancel makes
sense, and it is also the one you run from a terminal anyway.

**A model-driven pass stays copied.** That line is the whole bargain
(invariant 1 in spirit): you paste it where you can watch it, so nothing
writes cards with nobody looking. The commands panel says which end each one
runs at, and only the plain-Python half is ever a candidate for a button.

**What to build first**, when a button is what you actually miss: `POST
/api/run/<verb>` for a named, argument-free subset (`check`, `sync
--dry-run`, `feedback --dry-run`), each returning the same structured
report its `--json` already returns, and one component that renders an
outcome table. The dry runs first, because a button that changes nothing is
the one that needs no confirmation.

## 14. A visual pass, and a theme you can swap

The functionality is roughly settled, so the next pass is how it looks. Two
halves that are easy to confuse: **naming the decisions** so a theme is a
file, and **making the decisions better** so the thing reads well. The first
is mechanical and testable; the second is taste and needs eyes. Doing the
first makes the second cheap, which is the order to take them in.

### What is already true

`app.css` is one file, 3713 lines, 890 rules. It is in better shape than a
file that size sounds:

- **Nine colour tokens** on `:root`, and 634 uses of `var()` against about
  forty colour literals. Almost every colour in the app already comes from
  one of nine names.
- **Dark mode already works**, under `@media (prefers-color-scheme: dark)`,
  by redefining eight of the nine. It has no switch, so it follows the
  operating system and nobody who has not read the CSS knows it is there.
- **The states derive rather than being listed.** `queued` is
  `color-mix(in srgb, var(--accent) 45%, var(--line))`, so one accent moves
  the whole pipeline strip, both bars and the diagram together. That is the
  pattern the rest should follow.

And where it is not in good shape, the numbers say where:

- **23 distinct font sizes** across 246 declarations: 8.5, 9, 9.5, 10, 10.5,
  11, 11.5, 12, 12.5, 13, 13.5, 14, 15 and up. The gaps between neighbours
  are below what anyone can see, so they are not decisions, they are drift.
  Six steps would cover every one of them.
- **Eight corner radii** across 90 declarations (2, 3, 4, 5, 6, 8, 99, 999).
  `--radius` exists and is used in 12 of the 90.
- **128 distinct padding values and 29 gaps.** Some of that is real: a rail
  is not a card. Most of it is one rule copied and nudged.
- **`--hover` is used twelve times and defined nowhere.** Every use is
  `var(--hover, rgba(127, 127, 127, 0.12))`, so the literal always wins. The
  grey is half-transparent to survive both themes, which is the workaround
  for the token that was never declared, and it is the seam leaking in
  miniature: a theme cannot currently change what a hover looks like.

### Naming the decisions

Sweep the literals and the un-named constants. Each one either becomes a
token or is written down as **not a theme decision**, and the second list
matters as much as the first:

- **Zotero's palette is not themeable.** `#ffd400` is what a yellow
  highlight looks like in the PDF, and a swatch that does not match the
  document it came from makes you translate. Same for anything else whose
  job is to match an external thing.
- **Meaning is not themeable either.** `warn` and `bad` may change hue; what
  may not change is which state is drawn as which.

What the vocabulary needs beyond the nine: surfaces (ground, panel, raised,
hover, selected), text (ink, muted, faint, on-accent), lines (hairline,
strong), the accent and two derived from it, the type scale, a spacing
scale, radii, and one shadow. Perhaps thirty names. Thirty names is the
whole of the work, because with them in place a theme is a thirty-line file
and without them a theme is a rewrite.

### The seam

`static/theme.css`, loaded before `app.css`, holding nothing but tokens.
`app.css` then contains no colour literal at all outside the external
palettes, and that is a rule a test can hold: grep the file, allow the named
exceptions, fail on the rest. A seam nothing checks is a seam that closes
again in three commits.

### Light, dark, and system

Three positions, not two, because following the operating system is the
right default and is what happens today:

- `:root` carries light. `@media (prefers-color-scheme: dark) :root` carries
  dark, as now, so `system` needs no script.
- `:root[data-theme="dark"]` and `[data-theme="light"]` pin it, overriding
  the media query.
- The choice is remembered the way the rail widths already are, in
  `localStorage`, and applied by a two-line inline script in `<head>` before
  the first paint. Without that the page paints light and then flips, which
  is worse than not having the switch.
- The control goes in the bar beside the settings gear. It is the same kind
  of thing: a preference about the window rather than about the deck.

Dark is also the one that will find the remaining literals, because every
one of them was written by looking at the light theme. One it already
finds: a crop is a picture of a white page, so in dark mode the triage view
is a bright rectangle on a dark ground. That is the same category as
Zotero's palette, content rather than chrome, so the answer is how it is
framed and not what colour it is: a border and a little dimming, or
nothing, but decided rather than inherited.

### About the Claude look

Worth naming because the palette here is already in that family: a warm
off-white ground (`#fbfbfa`), near-black ink, one accent, thin lines, very
little chrome. The differences are the accent, a green rather than a
terracotta, and the density, since this app is deliberately dense: a rail of
counts, a diagram, a keymap along the bottom.

So it is **a theme, not a redesign**, which is itself the argument for doing
the token pass first. Two cautions. A borrowed palette is fine and a
borrowed name is not, so if this ships it ships as what it is, a warm paper
theme, not as somebody's trademark. And the fonts are the expensive half of
that look; the app currently uses the system stack and loads nothing, which
is a real property worth keeping unless a webfont earns its two requests.

### Clutter, which is a content question

The pass people mean by "make it look nice" is mostly not colour. This app
explains itself a great deal: every panel has a sentence under it saying
what it is for. That was right while the shapes were moving and is not free
now. A line of standing prose earns its place when it says something the
control cannot: what a command will do to your files, why a pass is
missing, which of two similar things you are looking at. It does not earn
its place by naming the control again.

Two notes on the triage rail were removed for exactly this: they said the
transcription pass does not apply to a marked-up work, and how to
transcribe one unit anyway. They were written when an absent pass left the
panel empty. The panel is not empty any more, so they were two lines of
permanent text about the absence of something nobody was looking for.

The rest of the pass, in the order the evidence supports:

1. **One type scale, one spacing scale, one radius set.** Mechanical, and
   it is most of the visible inconsistency.
2. **Density per surface.** A rail, a card and a document are three
   densities and should be three, stated once rather than per rule.
3. **Borders.** Almost everything is a 1px hairline, including things that
   are grouped and would read better with space than with a line.
4. **The empty states.** Several panels say "nothing yet" in a different
   voice each.

### What a narrow window does

Checked at 1600, 1366, 1180 and 1024 with the shelf, the setup stage, triage
and review: **nothing overflows horizontally at any of them.** Three real
defects came out of it and are fixed: a command breaking mid-token in the
rail, so `--project "demo"` became `--project "de` and `mo"`; the shelf's
totals wrapping and making the bar two rows deep; and a rail heading whose
label and hint became two ragged columns.

What is left is the one thing worth a decision rather than a patch. Both
rails are a fixed width you can drag, and their widths are remembered, so at
1024 the deck column is about 290px between them. The rails already fold and
there is already a `@media (max-width: 1200px)` that hides the guide, but
only while the guide is in its default state, so anyone who opened it keeps
it. Folding a rail the reader opened, because the window got smaller, is a
choice that has to survive the window getting bigger again, and that wants
deciding rather than guessing: remember a fold done by hand, treat a fold
done by width as temporary.

**Trigger:** now, for the naming half, because the numbers above only grow.
The taste half wants the shapes to stop moving first.

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
