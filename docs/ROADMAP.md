# Roadmap

What is left, what the Cookbook taught us about its own extraction, and what
was rejected and why. The milestones in [DESIGN.md](DESIGN.md) §13 are built
and gone from this file; git history has them.

**The numbers are names, not an order.** Code cites them (`ROADMAP.md §1`,
`§9`), so a section keeps its number wherever it moves to and a new one takes
the next free number.

---

# What is left

## 1. The dependency canvas: what it does not do yet

Built, at `/graph`, per source, and `[app] graph = false` turns it off.
`graph.py` holds the graph and its layout with no app in it, `graph.js` draws
it, and `sources/<name>/graph.json` holds whatever you dragged.

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

## 10. A card that carries a picture

A card can only say things in text. Anki fields take an `<img>` and
AnkiConnect takes `storeMediaFile`; neither is used, so a figure or a diagram
cannot be carded at all. The material exists: Zotero's image and area
annotations arrive as units with a box and no text, and `extract/render.py`
renders a crop from any unit's geometry.

- **No image files in the repo.** Invariant 3: extraction produces geometry,
  never image files. A card names a unit and the crop is rendered from the
  source document at sync time, so the picture is reproducible rather than a
  binary somebody has to carry.
- **The reference lives in `## front` or `## back`**, which puts it inside
  `content_hash` for free. A picture is content: swapping it must un-approve
  the card the way swapping a formula does.
- **`sync` renders, uploads and rewrites**, under one deterministic media name
  per card and slot, so a re-sync overwrites rather than accumulating orphans.
- **`check` gates it:** the unit exists, it has geometry, and the document is
  present. A card whose picture cannot be rendered is refused rather than
  pushed broken, which is invariant 1 applied to media.

**Trigger:** the first marked-up paper where an area annotation is the point
rather than a note on it.

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

**Two of the three blockers dissolved:** Zotero's image and area annotations
are figure units already, and "a figure card needs a `type` beyond `identity`"
stopped being one when `intuition` landed. What is left is segmenter work, and
the segmenter is frozen. §10 is the other half.

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
