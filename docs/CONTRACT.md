# The contract

What the tool promises, in full. [CLAUDE.md](../CLAUDE.md) states each rule in
one line for a working session; this is the reasoning behind them, and the
place to look when a rule seems to be getting in the way.

Tests cite these by number.

## Invariants

### 1. Nothing reaches Anki without human approval

`sync` only touches cards marked `status: approved`.

Traffic is one-way, with one exception. `feedback` pulls review comments and
flags out of Anki, writes them into the card's `## notes` as `@claude` lines,
and erases them from Anki in the same pass. The erase is not tidiness: without
it, every run re-imports the same comment, and a note you had already resolved
comes back on the next pull. It is also what keeps invariant 2 true. Anki holds
that text until you pull it and never longer.

### 2. Files are the source of truth

The web app is a view over them. Anything it does, you can do by editing a
file.

### 3. Extraction produces units, never cards

If `extract` is tempted to write a `front`, it has overstepped. It produces
geometry and no image files: each unit carries `locator.bbox`, and crops render
from the source document on demand.

**Every unit arrives `new`, whichever door it came in by.** Importing what
someone marked in Zotero is not triage. Marking says "this mattered while I was
reading". Triage answers a different question: "is this worth a card on its
own". Landing an import in `queued` answers the second question on the reader's
behalf and removes the only gate before the card queue.

### 4. `tex_auto` is a hint

When writing a stub from a unit, the crop wins. A transcription error must not
become a card by inheritance.

### 5. Editing an approved card un-approves it

Enforced by `content_hash`, which covers the card's content and nothing else.
Outside it: `status`, `content_hash`, `## notes`, `## verify`, `verify`,
`requires`, `frequency`, `derivation`, `web`.

The last four are not claims the card makes. Three decide when you meet it, one
is a permission granted to whoever writes it, and approving a card is not
approving its position in the queue.

Nothing rewrites a file to enforce this. An approval that no longer holds is
reported by `Card.demotion` and counts as a draft everywhere it matters, so
fixing whatever broke it restores the approval with no re-review.

### 6. Card content guidelines live in the skill, not in code

The Python never generates or rewrites card text.

### 7. A crop is authoritative for what is printed and silent about the rest

Conditions are usually printed around an identity rather than inside it.
`forge context <unit>` prints the page it came from, and that is all it does.

Whether an identity needs a condition is mathematics, and it belongs to whoever
writes the card. Check it, prefer the source's wording where there is one, and
note in `## notes` any condition you added that the source does not state.

### 8. A bounding box means what its origin means

A segmenter that found a display equation stopped where the equation stopped,
so the box's edges are an answer.

A *mark's* box is the union of the lines a sentence happened to span. Its left
and right edges are wherever that sentence started and stopped mid-column, and
they carry no information, so those crops are cut to the full page width
(`crop_width`).

Marks are painted back onto the crop in the colours the reader used: the unit's
own at full strength, its neighbours faded. A page with six highlights on it
has to say which one the card is about.

### 9. A unit is a decision; a card is the content

Two stages, two questions, and neither does the other's work.

**The unit stage** answers two things: is this worth a card at all, and roughly
what would the card be about. That is the whole of triage. Everything on screen
there serves those two questions: the crop, the sentence you marked, what you
wrote beside it, the neighbouring marks, and a transcription where one exists.
An answer that needs more than "yes, and it is about X" is a brief (`@claude`),
not a decision to postpone. `Q` queues and records one in the same keystroke.

**`gist`** is the second question answered in advance. `/gist` reads each crop
and writes one line saying what a card from it would be about: "Lemma 2", "why
the bound needs independence".

It is a reading, and nothing downstream consumes it. `/extract-cards` still
works from the crop, the page and the brief. Keeping it out of that path is the
safety property: a machine's guess, written where the next pass reads
instructions, is indistinguishable from yours one pass later. Its value is that
disagreeing with it costs one keystroke here, where the same misunderstanding
found after a card exists costs a rewrite.

**The card stage** is where content is settled. `/extract-cards` and `/augment`
pull whatever context the unit was granted (the page it was printed on, the
pages either side, the source's conventions, web lookups where those were
granted) and iterate until `check` passes and a human can approve.

Depth belongs here. At triage it buys nothing and costs the throughput the
stage exists for.

One consequence worth stating: **you do not have to be able to transcribe a
unit in order to triage it.** `tex_auto` exists to keep a segmented source
legible enough to judge ([DESIGN.md](DESIGN.md) §4), which is the same two
questions, not a head start on the answer (invariant 4). A marked passage
carries the sentence it covers and needs nothing more. A boxed figure carries
neither text nor maths and is still obviously worth a card or obviously not.
On a prose source the subject of a unit is what you highlighted and what you
wrote about it, never a formula, which is why the triage view shows those and
renders no transcription pane at all rather than an empty one.

---

## Card format

One markdown file per card in [cards/](../cards/), named
`<source>/<uid>-<slug>.md`. The folder is filing only. `unit:` is the one place
a card's source is recorded, and every loader `rglob`s, so a card in the wrong
folder still loads and still syncs.

Frontmatter: `uid` (6 hex), `type` (`identity | intuition`), `status`
(`draft | approved | rejected`), `content_hash` (set on approval), `source`,
`unit`, `tags`, `verify`, and optionally `frequency`, `derivation` and `web`.

Sections: `## front` and `## back` are required. `conditions`, `prose`, `uses`,
`proof`, `verify`, `notes` are optional. They read in that order on the card:
`prose` is one sentence and the only unlabelled block, so it sits directly
under the answer and everything after it is labelled. `content_hash` sorts
sections by name, so changing the reading order costs no approvals.

Math is written `$...$` / `$$...$$` and converted to MathJax delimiters on the
way into Anki. `## notes` and `## verify` never reach Anki.

### A card is not one-to-one with a unit, in either direction

One unit splits into several cards (`uids` on the unit). Several units merge
into one card (`unit` accepts a list, or a comma-separated string), which is
what a multi-line display cut into pieces needs.

`forge context <unit>` lists every unit on the page in reading order, so the
pieces are visible and nameable. `new` takes `--unit` repeatedly and marks each
one carded.

### `identity` states a fact; `intuition` explains one

An identity has a definite answer and `verify` can check it numerically.

An intuition is what a marked passage in a prose source becomes: why a bound is
tight, what a term is really measuring, which of two hypotheses is doing the
work. It has no `## verify`, because there is nothing numeric to check, and no
`## conditions`, because a hypothesis belongs to a statement and anything
needing one is an identity wearing the wrong type.

Both reach Anki as a `type::` tag, and a source may send each to its own
subdeck under `[decks]`. Five restatements a day is comfortable; five pieces of
intuition a day is not.

### Study order

`frequency` (`core | common | rare`) is how often the identity turns up.
`derivation` (`definitional | short | long`) is what reconstructing it would
take, with `definitional` for facts that are true by definition.

Both are optional and both are coarse on purpose. They reach Anki as `freq::`
and `derive::` tags. An unrecognised value is a `check` error, because a typo
would silently become its own tag and split the deck.

`requires` is a list of uids that must be introduced before this card, and it
decides the order `sync` adds new cards in. Only for a real dependency: this
card's proof or notation rests on that one. It is outside `content_hash`.

Within the graph, order is `frequency`, then `derivation`, then the order the
source prints it in.

---

## Conventions belong to a source, not to this file

Which layout a derivative uses, what the entries are, what a bare symbol means:
each is a fact about one book and one deck, not about this tool. Naming any of
them repo-wide would make this contract wrong the moment a second source
arrived, and a card writer told to read it as authoritative would apply
conventions that do not hold for the page in front of them.

So they live in **`sources/<name>/`**, in two files, because they are two
things: a config and a document. The fenced single file they replaced was
neither, since no editor checks the TOML above the fence *and* renders the
Markdown below it.

### `source.toml`

What a key can express, and what the tool acts on: `title`, `citation`,
`pdf`/`tex`, `zotero`, `documents`, `deck`, `order`, `tags`,
`crop_context`/`crop_width`, `context_pages`, `web`, a `[conventions]` table,
and the source's own reading of its Zotero marks.

`crop_width` outside `box | page` is refused at load. An unrecognised value
would read as "not box" and silently change every crop.

`documents` names which of a Zotero item's PDFs to read, by title or key. An
item routinely carries the paper and a preprint of the paper, and marks made in
one are not marks in the other.

`tags` are yours to invent. Nothing writes one for you: a label the tool made
up means whatever the tool guessed, and you would be filtering by it without
having decided what it says.

### `[conventions]`

The keyed half of what is ambient, and it is **open**. Any key is accepted, and
every one of them is handed to whoever writes a card through `forge context`.
What a source assumes is not a vocabulary this tool can enumerate, so the table
carries what it is given rather than checking it against a list.

**There is no repo-wide counterpart, deliberately.** A convention is a fact
about one book, and defaulting one in `forge.toml` is how a statistics paper
came to be told which matrix-derivative convention it writes. `[cards] layout`
now raises at load rather than being quietly ignored.

Exactly one entry is acted on rather than only shown: `layout`, one of
`denominator | numerator`, because `verify`'s numerical gradient computes one
of the two. A value outside them is refused at load, since an unrecognised one
would read as "not the one you meant" and silently change what every derivative
from that source means. Which of the two a source uses is that source's
business to declare.

### `web`

Whether whoever writes or augments a card from this source may look things up.
Off repo-wide, and overridable per source, per unit (from triage, `w`) and per
card.

Off by default because the failure is invisible. A card should say what *this
source* says, hypotheses and notation included. The web's cleaner statement of
the general theorem, substituted for the printed one, reads as a better card
until the condition the paper had, and the general version does not, turns out
to be the point.

`forge context` resolves unit over source over repo and says the answer in
words, so the pass reading it never has to work out whose setting won.

### `conventions.md`

What a key cannot express: the ambient mathematical setting, what is assumed
constant, how a contested convention was settled. `forge context <unit>` prints
it, so whoever writes or reviews a card sees the right one without knowing it
exists.

**There is no file until you write one.** Nothing generates a placeholder,
because a placeholder saying "nothing recorded yet" is indistinguishable from a
real one to everything that reads it, and would silence the warning it should
raise. If a source has none, `context` says so. An absent convention means a
card writer is guessing.

### Why TOML

Every key in `source.toml` overrides one in `forge.toml`, so a block copied
between the two has to work unchanged. TOML is also the stricter language: in
YAML a tag or colour written `no`, `on` or `y` is silently a boolean.

A folder with neither `source.toml` nor the older `source.md` is not a source.
Discovery does not guess.

`forge.toml` keeps what is genuinely repo-wide: `[cards] language`, the note
type, `[anki] deck` as a fallback, `[cards] web` as the floor under every
source's permission, `[zotero]` defaults. A `[sources.<name>]` block there still
works for a repo that has not moved yet. Conventions are the one thing it does
not keep.

---

## What is true of the tool

- **`verify` backend:** numpy plus central-difference numerical gradients. No
  torch, no jax.
- **Mixing conventions silently is the failure that poisons a deck.** Whatever
  a source declares, a card that could be read either way says so in
  `## conditions`. `verify` refuses a source whose layout its gradient does not
  compute rather than checking against the wrong one. The two agree on every
  square matrix, so a mismatch would pass review and first bite on a
  rectangular one.
