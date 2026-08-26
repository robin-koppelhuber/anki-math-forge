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

**Partly mitigated already.** The triage view now renders each crop with 40pt
of surrounding page and the unit's own box drawn on it, so a split equation
shows its missing lines just outside the box and a merged one shows two
numbers inside it. The human meets the problem while deciding, instead of it
surviving into a card. The eq-48 units are also annotated and its fragments
skipped.

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
