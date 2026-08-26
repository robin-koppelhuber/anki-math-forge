# matrix-cookbook

**The Matrix Cookbook**, Petersen & Pedersen, version **November 15, 2012** —
the last release the authors made. Extracted from `matrixcookbook.pdf`
(692 KB, 72 pages, pdfTeX, 571 numbered equations).

The PDF is not committed (see `.gitignore`); fetch it with:

```
curl -o sources/matrix-cookbook/matrixcookbook.pdf \
  https://www.math.uwaterloo.ca/~hwolkowi/matrixcookbook.pdf
uv sync --extra pdf
uv run anki-forge extract matrix-cookbook
```

## Source form (DESIGN.md §15.3, decided)

**PDF.** No usable LaTeX source is published — the authors released the
PDF only, and no source repository exists. So this goes down the crop path,
and `tex_auto` is written by `/transcribe` reading the crops, rather than
coming from the document.

The PDF is at least well-behaved: pdfTeX output with hyperref bookmarks, so
section numbers come from the outline's named destinations (`subsection.2.4`)
rather than being guessed, and each display equation carries a right-margin
number that anchors its crop.

## What extraction gets

| | |
|---|---|
| numbered equations found | **571 of 571** (no gaps, no duplicates) |
| crops holding exactly one equation | 564 (98.8%) |
| crops holding two or more | 7 (1.2%) — stacked `cases` equations set very close together |
| unnumbered display math | 180 further units |
| run time | ~13 s |

The 7 merged crops are readable, just not one-equation-per-card; they show up
in triage like anything else.

## Corrections

**There is no published errata.** The authors' only channel was
`cookbook@2302.dk`, the DTU record ends at version 20121115, and nothing has
been issued since. The book's own front matter says as much: *"Very likely
there are errors, typos, and mistakes."*

The one systematic check that exists is
[eric-wieser/lean-matrix-cookbook](https://github.com/eric-wieser/lean-matrix-cookbook),
which re-proves the book's identities in Lean against mathlib. It targets this
exact November 2012 version and, across the sections it covers, flags a single
statement as wrong:

- **eq (28)** — `det(I + εA) ≅ 1 + det(A) + εTr(A) + ½ε²Tr(A)² − ½ε²Tr(A²)`.
  The `+ det(A)` term does not belong. Counterexample `A = I`, `n = 2`:
  `det(I + εI) = (1+ε)² = 1 + 2ε + ε²`, but the right-hand side starts at
  `1 + det(I) = 2`. ([issue 18](https://github.com/eric-wieser/lean-matrix-cookbook/issues/18))

That unit is already `skipped` in the ledger with the reason recorded, so it
will not be offered for carding again. Treat everything else as unverified:
that is what `verify: true` and the `## verify` section are for.

## Files

- `units.jsonl` — the ledger, and the only thing here worth committing. Triage
  decisions live in it, and `extract` never overwrites a state you have set.
- `text.md` — the book's text layer, cached by `extract` (~90 KB, ~26k tokens).
  This is what a card writer reads for context: the notation table defines
  every symbol, and the surrounding section is what stops you writing ten
  near-duplicate cards. Generated; regenerated on every extract.
- `matrixcookbook.pdf` — gitignored, not ours to redistribute. Crops are
  rendered from it on demand, so the app needs it present to show them.

There is deliberately **no `assets/` directory**. Each unit carries the
bounding box the segmenter found (`locator.bbox`, PDF points, top-left
origin) and the crop is rendered from the PDF when something asks for it —
about 150 ms over HTTP, imperceptible when you are looking at one unit at a
time. That keeps the ledger textual and diffable: a change in segmentation
shows up as a bbox you can read in a diff, rather than 751 changed PNGs.
