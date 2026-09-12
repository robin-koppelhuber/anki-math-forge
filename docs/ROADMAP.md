# Roadmap

What is left, what the Cookbook taught us about its own extraction, and what
was rejected and why.

The milestones in [DESIGN.md](DESIGN.md) §13 (M0–M6) are built, and so is
everything the 2026-09-11 planning round scheduled: Zotero as a source, the
`identity` / `intuition` split, per-source configuration, crop context and the
whole-page view, the triage and review surface, the rename, and publishing.
Those sections are gone from this file. Git history has them.

Two things about the shape of what remains. **The dependency canvas is
built**, so §1 is now what it deliberately stopped short of rather than a plan
to build it. And **the largest unbuilt section, the model page extractor, has
been demoted to an idea**: §5 says why, and it is worth reading before anyone
picks it up out of habit.

---

# What is left

## 1. The dependency canvas: what it does not do yet

Built, at `/graph`, per source. `src/anki_math_forge/graph.py` is the graph and
its layout with no app in it, `app/static/graph.js` draws it, and
`sources/<name>/graph.json` holds whatever you dragged. The design notes it was
built from are gone: what survived them is in comments at the seams they
describe, and the rest is here.

What v1 stops short of, and the trigger for each.

- **Drawing an edge in the browser.** A position is a view preference and costs
  a drag if it is wrong. An edge is card content: making one writes `requires`
  into frontmatter, which `check` validates for cycles, self-reference and
  dangling uids. So it needs three things this does not have: the cycle check
  *before* the write rather than after, the `mtime` guard, and an undo, because
  a mis-dragged arrow is as easy to make as a mis-pressed key. `Edge.kind` is
  the only affordance v1 owes it.
- **Concept nodes.** The open question from the old plan, still open. A node is
  a card, and "the adjugate" is one idea carried by three cards, so a concept
  graph would be smaller and more honest about the material. It is a second
  builder function beside `card_graph` and a `?graph=concepts` on the route;
  the layout, the position file and the canvas are untouched, which is what
  that seam is for. Worth building when one idea is carried by enough cards
  that the card graph reads as duplication.
- **Zoom.** Pan is enough and the browser zooms. Revisit when a real source
  does not fit.
- **Quadtree hit-testing.** Linear over every node on `pointermove` is
  microseconds at 108 and fine at 700. Revisit past a few thousand.

What it taught about the deck, which is the answer to the density objection
this item used to carry: 18 of the Cookbook's 108 cards touch an edge, and
**one of the 18 has a caption**. A box reading `no caption yet` is the view
being honest rather than inventing a name from the filename slug, and it is
also the list of cards `/augment` should be run over next.

## 2. Two audit checks that would have caught dropped content

Small, mechanical, and independent of everything else. These belong in
`audit.py`, which is not frozen, and they catch failures the existing oracles
are blind to. The evidence for both is in "What the Cookbook taught us" below.

- **`fragment-suspected`:** an unnumbered unit sitting directly above or below
  a numbered one, in the same horizontal band, with a gap smaller than a line
  height, is almost certainly a continuation of it. The contiguity oracle is
  satisfied either way, because the number exists.
- **A numbered unit whose crop holds no relation symbol.** The mirror of the
  `no-relation` rule `classify` already applies to unnumbered units. It would
  have caught `matrix-cookbook:3.2:178`, which contains nothing but the number
  `(178)`.

There is a third signal, free and mechanical, that belongs to whatever segments
next rather than to the audit: **a line ending in a trailing binary operator
cannot be the end of an equation.** Every continuation line in §6.2 and
§7.7–7.9 ends in `×` or `+`.

## 3. Small and named

- **The `§` prefix on every section label.** Cosmetic, except that it reaches a
  card's `Source` field in Anki.
- **`front_char_cap` is not per-source.** 160 characters suits a formula
  reference and is tight for a statement from a paper.
- **Nothing writes an `intuition` card yet.** The card-writing skill is about
  identities throughout. Teaching it the second kind is guidance, not code, and
  it belongs with the first prose source that has marks worth explaining.

## 4. Publishing, what is left

Most of this shipped. What has not:

- **Rename the repository.** The README badge points at
  `robin-koppelhuber/anki-math-forge`; the remote is `robin-koppelhuber/Anki`.
  The badge is broken until they agree.
- **The demo recording.** `assets/make_assets.py` carries the shot list in its
  docstring. Not scriptable: the interesting part is the pace of triage and no
  script knows how long to pause.
- **The marked-up screenshot.** `make_assets.py` will take it as soon as one
  Zotero source tags itself `demo`, and refuses until then, because that shot
  is a legible page of whatever you were reading.
- **The Cookbook's licence.** Its front matter states none at all: a
  disclaimer, an errata address, acknowledgements, nothing granting
  redistribution or derivative rights. Freely downloadable is not licensed, and
  `cards/matrix-cookbook/` is 108 derived cards. Worth two minutes on
  matrixcookbook.com before anyone points at the deck.
- **There is no `.mcp.json`**, though `.env.example` tells you to configure
  one. Anybody following the Zotero path has nothing to copy.

**Half of this does not run without Claude Code**, which is the flip side of
having no LLM code in the tool. The committed ledger and the `.apkg` export are
the mitigation: they show the output without running the half a stranger
cannot.

---

# Ideas, not scheduled

## 5. The model page extractor, and why it stopped being the plan

This was item 2 of three in the old plan, described as "the risky half" that
everything else was buying time for. **The argument for it has been overtaken
by what got built.**

The case was: `extract/pdf.py` is a heuristic specialised to one book (§9
measures exactly how specialised), so a second source needs a general extractor
that reads page images and reports `(kind, label, page, bbox)` per statement.

Two things happened.

**Zotero arrived, and it brings its own geometry.** An annotation carries
rects, a page index and a sort index, so a marked-up source is crop-backed with
no segmenter at all. Two of the three sources here came in that way.

**Prose stopped being segmented.** The planning round settled that only
mechanically identified things become units, and that a unit from free-form
text must be triggered by an annotation. That removed the two hardest pieces of
the original extractor: a prose segmenter, and the triage bottleneck several
thousand paragraph-level candidates would have created.

What is left for a general extractor is a narrow case: **a second
formula-reference-shaped PDF that is not the Matrix Cookbook and that you do
not want to read through Zotero.** That is a real case and it is not this
month's.

If it is built, the design still holds and is worth keeping:

- `equation: int` on the locator becomes `kind: str` (`"equation"`,
  `"theorem"`, `"lemma"`) plus `label: str` (`"2.4"`, `"61"`). `pdf.py` keeps
  emitting `equation: int` untouched and a shim maps across, so generalising
  the locator never means editing a frozen module.
- **The contiguity oracle survives**, which is the good news. `audit` checking
  1..N with no gaps sounds like an equation-number trick and is not: theorems
  are numbered contiguously within a chapter, so the same oracle runs per label
  family.
- **Judgement stays where it is.** Extraction produces units, never cards
  (invariant 3). No new stage, no new state machine.
- **Run it in subagents.** `/transcribe` already dispatches one per section,
  because seven hundred crops would fill the main session's context. Any pass
  that reads pages has the same problem. There is no fork primitive, so the two
  savings that are real are the ones `/transcribe` uses: give each agent a
  disjoint slice, and have the parent pass a short brief rather than each agent
  re-deriving the shared setting.

**Trigger:** a source you want to card that is neither the Cookbook nor
marked up in Zotero.

## 6. Figures, and everything that is not a text block

`page_blocks()` skips every block whose `type != 0`, so embedded rasters are
invisible, and vector drawings (`page.get_drawings()`) are never consulted.
Three consequences, worst last: a diagram worth carding never enters the ledger
and so cannot be triaged; equations set as images return nothing and say so in
no way at all; vector-drawn math is lost the same way, and that includes
fraction rules, which TeX draws as thin filled rectangles and which are a
font-independent "there is math here" signal.

The Cookbook has zero image blocks and no heavy vector art, which is why this
has never bitten.

**Two of the three blockers dissolved.** Zotero's image and area annotations
are figure units already: a box, no text, crop authoritative. And "a figure
card needs a `type` beyond `identity`" stopped being a blocker when the
`intuition` type landed. What is left is segmenter work, and the segmenter is
frozen, which is why this sits here rather than above.

A cheap piece worth doing on its own if the fallback segmenter is ever touched:
use fraction rules from the vector layer as a math signal in `score_line`,
which would make it far less dependent on Computer Modern font names.

## 7. The cross-check between two extractions

Designed, not built. The principle that makes it legitimate: an LLM is not
mechanical, but **agreement between two independent extractors is**, and the
equation number is an exact join key.

Contiguity is built (`forge audit`). Transcription is built (`/transcribe`),
but it is one extractor, so it reconciles nothing.

- **Cross-extractor join:** a pass that reads the *page* and reports the
  equations it finds, joined against the ledger on equation number. It must
  read the page, not our crops: fed our own crops it inherits our segmentation
  errors and cannot report them.
- **Round-trip render:** the strongest check, and the only one that catches a
  *wrong* transcription rather than a missing equation. Render `tex_auto` with
  KaTeX, compare against the crop, store the agreement as a number. Without it,
  transcription trades a detectable failure (a gap in the numbering) for an
  undetectable one (confident wrong LaTeX).

**This needs §5 to exist.** A second extractor is the whole idea, and §9's
frozen heuristic plus a model is the cheapest pair. Until then there is one
extractor and nothing to reconcile.

### The coverage oracle

Extraction knows every text block on the page. A block that ends up inside no
unit's bbox was dropped, and measuring that is cheap and exact. Contiguity
asks "is every equation number present"; coverage asks "is every mark on the
page inside some unit". Neither the audit nor the KaTeX gate asks the second.

**Narrowed by the decision not to segment prose.** Most of a prose page is now
meant to be outside every box, so a literal coverage check would scream on
every page. What survives is "is every *named statement* inside a unit", which
is weaker and closer to contiguity. It is still the only thing that could say
whether a new extractor is better or merely differently wrong, so it belongs
with §5 rather than before it.

## 8. A "daily proof" challenge

One theorem a day, presented as something to reconstruct rather than recall.

This is a **different object from a card**, which is why it is not another
`type` and why adding `intuition` did not change that. A card asks for one
answer and is graded in a second. A proof is a structure: you either
reconstruct the argument or you do not, the answer is a paragraph, and grading
it against a stored back is not what makes it useful. Forcing it into the card
format would produce a front too broad to have one answer, which the
card-writing skill exists to prevent.

Two shapes, not equivalent. **As Anki**, a `proof` card type: cheap, reuses the
pipeline, inherits the wrong grading model. **As a standalone page**, one
theorem a day with the steps revealed on demand: escapes that model entirely,
but is a second product with its own state.

Open first: what is the source (the Cookbook has no proofs, so this needs its
own corpus and the pipeline may not apply), what is being reviewed (the
statement, the key idea, the full argument), and whether spaced repetition is
even the right schedule for something you work through rather than recall.

---

# What the Cookbook taught us

Not work items. This is measured evidence about the committed ledger, kept
because it says which units not to trust and why the checks in §2 are worth
building. Every fix is a change to `extract/pdf.py`, which is
[frozen](#13-extractpdfpy-is-frozen-not-deleted), so these are closed as "use a
different extractor for that source" rather than repaired.

## Multi-line displays get split

`anchored_regions` grows a region only by vertical overlap. Stacked lines do
not overlap, so a three-line display becomes three units: two unnumbered
fragments and one carrying the number, each holding a third of the identity.

The audit does not catch it. The crops are adjacent rather than overlapping, so
`crop-overlap` stays quiet, and the numbering oracle is satisfied because the
number exists.

Measured over the whole book by the `/classify` pass, which read all 117
unnumbered units. Of the ~100 skips proposed, the large majority are this one
defect, and it is concentrated rather than a long tail:

| where | what |
|---|---|
| §8.2.4 quartic forms | **25 of §8.2's 36 units** are fragments, from seven identities of 2–5 lines each |
| §6.2 cubic forms | one equation into three units, another into two |
| §7.7–7.9 | Student-t / Wishart / inverse-Wishart densities, cut mid-formula |
| §2.8 | a four-crop chain, all of it equation 143 |
| §2.4, §2.5 | number on the *last* line, continuations orphaned above it |

The number attaches to whichever line carries it, so orphans appear both above
and below the numbered unit. Any fix handles both directions.

Not everything unnumbered is a bug: §11.1 and §11.2 have a high unnumbered rate
because the book genuinely states long runs of unnumbered moment identities.

**Partly mitigated already.** The triage view renders each crop with
`crop_context` points of surrounding page and the unit's own box drawn on it,
so a split equation shows its missing lines just outside the box and a merged
one shows two numbers inside it.

## The three failures that do not announce themselves

Everything above is visibly *missing* something. These are not.

**A bbox that clips mid-glyph.** Unit `9.2:409` has a box tight enough to shave
the left stroke off `W_N`, so the crop reads `V_N`: a different and perfectly
legible symbol. A transcriber reading only the crop records a wrong symbol with
full confidence, the KaTeX gate accepts it, and the card is wrong forever. It
was caught only because the agent distrusted the shape and rendered a wider
region to compare. No check on the *text* can catch a faithful transcription of
a corrupted *picture*, which is why the crop stays beside the transcription.

**A bbox that clips the relation.** §9.1.5 produced ~77pt-wide boxes that cut
`C1 =` off the front and the trailing subscript off the back. Worse than a
split, because the crop still looks complete.

**Content in no unit at all.** Equation 27 is a three-line display; two lines
survive across `1.2:p7y169` and `1.2:27`, and the third is in no unit anywhere.
It recurs by two further mechanisms. In §6.2, `p36y310` has a bbox whose left
edge starts after the `=`, so the entire left-hand side appears in no crop.
And on the page-5 notation table, a two-column layout, some bboxes cover only
the description column, so the symbol — the point of the row — is in no unit.
`anchored_regions` reasons about vertical bands and has no notion of a column.
Two confirmed cases in the first 355 units read.

**One outright bug.** `matrix-cookbook:3.2:178` contains nothing but the number
`(178)`; the equation's content is in its unnumbered sibling `3.2:p20y147`.

## §12.1 (Appendix B) should probably not be units

The proofs appendix is not a list of identities, it is continuous multi-line
algebra. Reading all 35 of its units found the segmenter tearing fractions,
parentheses and summation limits across crop boundaries roughly every other
unit: 11 of 35 needed bracket-splitting or were pure debris.

The transcriptions are faithful, but they are proof *fragments*, and the useful
content is the chain rather than any single line. Two honest options: treat the
whole appendix as prose and skip it, or segment it by proof block rather than
by rendered line. Either way, do not author cards from §12.1 as currently
extracted.

## 9. `extract/pdf.py` is frozen, not deleted

It is the only PDF segmenter there is, and it is frozen anyway. Those two
facts sit together because the reason to freeze it is not that something
replaced it: it is that every heuristic in it is specialised to one book and
documented as such, so extending it means teaching one book's habits to the
next one. The seam is a single function pinned by contract tests, which is what
keeps a second implementation cheap whenever there is a reason to write one.

How specialised, measured by ablation:

| | equations found |
|---|---|
| as shipped | 571/571 |
| without math-font detection | 571/571 |
| without equation numbers | locators gone; 936 unverifiable regions |
| without either | **9** |

Two producer-specific signals carry everything: a right-margin `(61)` and
Computer Modern font names. It is a specialisation, and the Cookbook happens to
be exactly the specialisation.

**Frozen means frozen.** Do not fix its heuristics. When a shared type changes
under it, give it a shim. What it owes is one function, `segment()`, returning
units whose `locator` carries `section`, `equation`, `page` and `bbox`, pinned
by `tests/test_extract_pdf.py`. Everything valuable lives elsewhere and is
unaffected: `extract/render.py` crops from `locator.bbox` alone, `audit.py`'s
oracle is a property of the *document* and scores any extractor, and
`ledger.py`'s ids come from the book's own numbering, which is why triage
survives a change of extractor.

**Delete it** if it ever costs something real: a shared change it cannot absorb
behind a shim, or a second book where it is chosen and then found to mislead.

---

# Considered and rejected

The reason is the part worth having later.

**A database.** The files *are* the product: a card is a markdown file you can
read in a diff, the ledger is JSONL so a re-segmentation shows as reviewable
lines, and crops were removed from git for exactly this reason. A database is
either a second copy that drifts or a replacement that throws the property
away. What scale actually wants is an **index, not a store**: sqlite under
`.forge/`, gitignored, rebuilt when stale, deletable without consequence. Build
it when a units page render passes ~300 ms, which at 751 units and 108 cards is
several books away. Measure, do not guess.

**Triggering Claude from the website.** No supported way to push a prompt into
a running session. Shelling out to `claude -p` is a separate headless run, and
a button that writes cards with nobody watching is what invariant 1 exists to
prevent. Superseded by copyable commands, which keep a human at the point of
execution.

**A collection of documents inside one source, and `locator.document`.** Each
paper is a first-level source instead, so the field would exist for zero
instances. Revisit only if a source genuinely needs many documents.

**A subdeck per paper.** Fifty three-card decks and fifty deck configurations,
to express something a tag expresses better. Subdecks are for a different
new-card rate; tags are for filtering.

**Mermaid diagrams in the README.** Text that renders natively on GitHub and
cannot go stale, rejected in favour of committed images and a helper script, on
the grounds that more visualisations are coming and they will not all be state
machines.

**pdf.js in the triage view.** A whole-page render with the unit's box drawn on
it answers the same question in one glance and adds no dependency. Reconsider
when you want to drag a box in the browser to create a unit.

**BYOK and LLM calls in the tool.** "No LLM API code in the Python" is why
there is no torch, no key handling, no cost model, no injection surface inside
the tool and no vendor in the dependency tree. That is a position, and it is
more interesting than the feature. If it ever happens it belongs in a separate
package implementing the same contracts the slash commands do. It is also the
real fix for "half of it needs Claude Code".

**A hosted live demo.** The app writes to the local filesystem, so a public
instance is either read-only, and therefore not the thing, or a vandalism
target, and it would need the source documents hosted. A recording gets the
same point across for an hour's work.

**Docling** (and marker, MinerU). Measured on this book: 19.7 s/page against
0.18, five regions where we find twenty on the packed page, and no LaTeX
without a second model. Its real advantage is generality, and §5 gets that more
cheaply. It would earn its place on a **scanned** PDF with no text layer, which
is also §6.

**Auto-generating units from free prose.** A prose unit must be triggered by a
Zotero annotation. This removed a prose segmenter and the triage bottleneck
several thousand paragraph-level candidates would have created, and it is what
demoted §5.

**A placeholder `conventions.md`.** An empty one saying "nothing recorded yet"
is indistinguishable from a real one to everything that reads it, and would
silence the warning it should raise.

**An htmx or SPA rewrite.** FastAPI plus Jinja2 is already the simple
framework, and an auto-updating counts strip is about twenty lines of fetch and
swap. Trigger for revisiting: if the same fetch-and-replace-a-fragment code
gets written a third time, adopt htmx then.
