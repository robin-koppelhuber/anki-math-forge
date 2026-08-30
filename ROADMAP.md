# Roadmap

The milestones in [proposal.md](proposal.md) §13 (M0–M6) are built. This is
what is left, and what we chose not to build and why.

Ordered by what would bite first.

---

## 1. Images and figures in PDFs

**The segmenter is blind to anything that is not a text block.**
`page_blocks()` skips every block whose `type != 0`, so embedded rasters are
invisible, and vector drawings (`page.get_drawings()`) are never consulted at
all. Three consequences, in increasing severity:

- **Figures are not units.** A diagram worth carding — a geometric picture of
  a projection, a plot of a matrix norm — cannot be triaged, because it never
  enters the ledger.
- **Equations set as images are silently lost.** In a scanned book, or one
  where a publisher rasterised the display math, extraction returns *nothing*
  and says so in no way at all.
- **Vector-drawn math is lost the same way**, and that includes fraction
  rules: TeX draws them as thin filled rectangles, which is a font-independent
  "there is math here" signal we currently throw away (see §4 below).

The Matrix Cookbook has **zero** image blocks and no heavy vector art, which
is why this has not bitten yet. It will on the next book.

**Shape of the work:**

- treat `type == 1` blocks as candidate units, with a `kind` on the unit
  (`equation` | `figure`) so the units view can render them differently;
- cluster vector drawings into regions the same way text blocks are clustered,
  so a plot becomes one unit rather than four hundred line segments;
- decide what a figure card even *is* — probably a new `type` beyond
  `identity`, which is currently a §14 non-goal, so this needs a design call
  before it needs code.

A cheap first step that is worth doing on its own: use fraction rules from the
vector layer as a math signal in `score_line`, which would make the fallback
segmenter far less dependent on Computer Modern font names.

## 2. Multi-line display equations get split

Found during the first §2.1 review. Equation 48 is a three-line display, and
`anchored_regions` grows a region only by *vertical overlap* — stacked lines
do not overlap, so it produced three units: two unnumbered fragments and one
carrying the number, each holding a third of the identity.

The audit does not catch it: the crops are adjacent, not overlapping, so
`crop-overlap` stays quiet and the numbering oracle is satisfied.

**Detectable signal:** an unnumbered unit that sits directly above a numbered
one, in the same horizontal band, with a gap smaller than a line height, is
almost certainly a continuation of it. That is an audit check
(`fragment-suspected`) before it is a segmentation fix.

**Also detectable mechanically.** `anki-forge classify` flags unnumbered
units whose text contains no relation symbol, which is exactly what a
continuation fragment looks like — it caught the eq-48 middle line and 52
others without being told about them. Those are skipped with reason
`no-relation`, so they are reviewable rather than lost.

**Partly mitigated already.** The triage view now renders each crop with 40pt
of surrounding page and the unit's own box drawn on it, so a split equation
shows its missing lines just outside the box and a merged one shows two
numbers inside it. The human meets the problem while deciding, instead of it
surviving into a card. The eq-48 units are also annotated and its fragments
skipped.

### Measured, over the whole book (the `/classify` pass)

Six classifier agents read all 117 unnumbered units. Of the ~100 skips they
proposed, the large majority are this one defect. It is not a long tail — it
is concentrated:

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
ends in a trailing binary operator — `×`, `+`. A line ending in an operator
cannot be the end of an equation. That is mechanical, needs no model, and
would merge most of these before a human ever sees them.

**The worst variant: a bbox that clips mid-glyph.** Unit `9.2:409` has a box
tight enough to shave the left stroke off `W_N`, so the crop reads `V_N` --
a different, perfectly legible symbol. Every other defect here announces
itself as *missing* something. This one does not: a transcriber reading only
the crop records a wrong symbol with full confidence, the KaTeX gate accepts
it, and the card is wrong forever. It was caught only because the agent
distrusted the shape and rendered a wider region to compare.

This is the strongest argument for the coverage oracle below, and for keeping
the crop visible next to the transcription in the triage view: no check on the
*text* can catch a faithful transcription of a corrupted *picture*.

**A second, distinct failure: the bbox clips the relation.** §9.1.5 produced
~77pt-wide boxes that cut `C1 =` off the front and the trailing subscript off
the back. The same page has an LDU identity whose `=` may be outside its box.
This is not line-splitting — it is a too-tight box on a short line, and it is
worse than a split, because the crop still *looks* complete.

**One outright bug.** `matrix-cookbook:3.2:178` contains nothing but the
number `(178)`; the equation's content is in its unnumbered sibling
`3.2:p20y147`. The contiguity oracle is satisfied — 178 exists — so nothing
mechanical catches an empty numbered unit. **A numbered unit whose crop holds
no relation symbol is an audit check worth adding**, and it is the mirror of
the `no-relation` rule already used on unnumbered ones.

**Not everything unnumbered is a bug.** §11.1/§11.2 have a high unnumbered
rate because the book genuinely states long runs of unnumbered moment
identities. There the agent found only row-splitting of aligned blocks, where
each row *is* a complete identity — a consolidation question for the human,
not a segmentation defect.

### Worse than splitting: content dropped entirely (eq 27)

Found by the transcribe pass. Equation 27 is a three-line display. Two of its
lines survive, spread across `1.2:p7y169` and `1.2:27`. **The remaining line
is in no unit at all** -- it was never extracted.

This is a different severity from everything above. A split equation is
annoying but recoverable, because every piece is on file and a human sees the
neighbours in the crop. A dropped line is *invisible*: the numbering oracle is
satisfied (27 exists), no crop overlaps, and nothing in the units view hints
that a third of the identity is missing. It was caught only because a model
read the crop and compared it against the page.

**It recurs, and by a second mechanism.** In §6.2 the unit `p36y310` has a
bbox whose *left edge* starts after the `=` sign, so the entire left-hand side
`E[(Ax+a)b^T(Cx+c)(Dx+d)^T] =` appears in no crop anywhere. Confirmed by
rendering the full page width straight from the PDF. So content is lost both
vertically (a line between two units) and horizontally (a bbox that begins
mid-line). Two confirmed cases in the first 355 units read.

**A third mechanism: multi-column layout.** The page-5 notation table is two
columns, symbol | description. Some units' bboxes cover only the description
column, so the symbol -- the entire point of the row -- is in no unit; others
merge two or three table rows into one. `anchored_regions` reasons about
vertical bands and has no notion of a column. It costs nothing here (all eight
are front-matter skips anyway), but the same heuristic runs over §5.1's
Condition/Solution table and §10.4's norm-relation table, which are real
content.

**What would catch it mechanically.** Extraction knows every text block on
the page. A block -- or part of one -- that ends up inside no unit's bbox is
dropped, and measuring that is cheap and exact: a **coverage oracle** to sit
beside the contiguity one. Contiguity asks "is every equation number present";
coverage asks "is every mark on the page inside some unit". The second
question is the one that catches this, and neither the audit nor the KaTeX
gate asks it today.

Build it *before* the pdf.py replacement. It is the only check that can tell
you whether the replacement is actually better rather than differently wrong,
and right now the honest answer is that nothing measures this at all.

### §12.1 (Appendix B) should probably not be extracted as units

The proofs appendix is not a list of identities; it is continuous multi-line
algebra. Reading all 35 of its units found the segmenter tearing fractions,
parentheses and summation limits across crop boundaries roughly every other
unit -- 11 of 35 needed bracket-splitting or were pure debris (a stray `r=0`
summation limit; a duplicate top-sliver of the next crop; torn denominator
strokes).

The transcriptions are faithful, but they are *proof fragments*. The useful
content is the chain, not any single line, and the deck's card type is
`identity`. Two honest options:

- treat the whole appendix as prose and skip it, or
- segment it by **proof block** rather than by rendered line.

Either way, do not author cards from 12.1 as currently extracted. This is a
scoping decision for the human, not something extraction should decide.

## 3. The cross-check, and reconciling two extractions

Designed, not built. The principle that makes it legitimate: an LLM is not
mechanical, but **agreement between two independent extractors is**, and the
equation number is an exact join key.

- **Contiguity** — built (`anki-forge audit`).
- **Transcription** — built (`/transcribe` + the `transcriber` subagent). It
  is one extractor, not two, so it does not reconcile anything yet.
- **Cross-extractor join** — a page-level `/transcribe`-style pass that reads
  the *page* and reports the equations it finds, joined against the ledger on
  equation number. It must read the page, not our crops: fed our own crops it
  inherits our segmentation errors and cannot report them.
- **Round-trip render** — the strongest check, and the one that catches a
  *wrong* transcription rather than a missing equation. Render `tex_auto` with
  KaTeX, compare against the crop, store the agreement as a number. Without
  it, a transcription pass trades a detectable failure (a gap in the
  numbering) for an undetectable one (confident wrong LaTeX).

## 4. `extract/pdf.py` — deprecated, delete when replaced

**Status: marked for deletion.** It works — 571/571 on the Cookbook — and it
is the single largest piece of code in the project for the least durable
value. The module docstring carries the notice; this is the plan.

Why it goes: the ablation is unambiguous.

| | equations found |
|---|---|
| as shipped | 571/571 |
| without math-font detection | 571/571 |
| without equation numbers | locators gone; 936 unverifiable regions |
| without either | **9** |

Two producer-specific signals carry everything — a right-margin `(61)` and
Computer Modern font names. It is a specialisation, and the Cookbook happens
to be exactly the specialisation.

**Do not extend it.** Bug reports against its heuristics should be closed as
"replace the module", not fixed.

### The replacement

Let a model read page images and report `(equation number, page, bbox)` per
display equation, then check the result with the contiguity oracle in
`audit.py` — the same check that scores the current segmenter. That is roughly
72 page reads for this book, produces the transcription in the same pass, and
generalises to documents this heuristic cannot touch.

### What it owes, and what survives without it

The contract is one function: `segment()` returning units whose `locator`
carries `section`, `equation`, `page` and `bbox`. It is pinned by tests in
`tests/test_extract_pdf.py` under *the deprecation contract*, so a replacement
can be checked against four assertions rather than 700 lines.

Everything valuable already lives elsewhere and is unaffected:

- `extract/render.py` — crops, from `locator.bbox` alone. Split out of
  `pdf.py` precisely so it does not go down with it.
- `audit.py` — the 1..N oracle. A property of the *document*, so it scores any
  extractor.
- `ledger.py` — stable ids and triage state. Ids come from the book's own
  numbering, not from anything in the segmenter, which is why triage survives
  a replacement.

### Deletion criteria

Delete `pdf.py` when a replacement produces, for the Matrix Cookbook,
571/571 numbered equations with no duplicates (`anki-forge audit` reports
`complete`), and the deprecation-contract tests pass against it. Until then it
stays, because it is what produced the 751 units currently in the ledger.

## 5. `verify` coverage

`verify` works and the corruption suite passes, but exactly one card opts in.
The gnarly identities — Woodbury, block inverses, anything with three
transposes — are where it earns its keep, and none of them are carded yet.

---

## Considered and rejected

**Docling** (and marker, MinerU). Measured on this book: 19.7 s/page against
0.18, five regions where we find twenty on the packed page, and no LaTeX
without a second model. Its real advantage is generality, and §4 above gets
that more cheaply. It would earn its place on a **scanned** PDF with no text
layer — which is also case §1 above.

**Refreshing transcriptions on re-extract.** `upsert` used to treat
`tex_auto`/`transcription` as extraction output, so a single
`anki-forge extract` silently wiped every transcription in the ledger. They
are work product now, like triage state: filled when empty, never overwritten.
Two regression tests hold the line.

**Local math OCR** (pix2text). Removed. Transcription is `/transcribe`, a
Claude Code skill reading crops on the subscription — which keeps torch, CUDA,
Intel XPU builds and a 4 GB dependency tree out of the project entirely.

**Committing crops as PNGs.** Removed: 751 files, 7 MB, opaque diffs, stale
after every re-extract. The ledger stores `locator.bbox` and crops render from
the document on demand (~150 ms over HTTP). A re-segmentation is now a diff
you can read.

**Moving the model cache into the repo.** The shared HuggingFace cache is
doing its job; a per-project copy duplicates weights and drags them into
whatever backs up the project directory.
