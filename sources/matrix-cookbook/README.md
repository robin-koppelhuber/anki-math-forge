# matrix-cookbook

**The Matrix Cookbook**, Petersen & Pedersen, version **November 15, 2012** —
the last release the authors made. Extracted from `matrixcookbook.pdf`
(692 KB, 72 pages, pdfTeX, 571 numbered equations).

The PDF is not committed (see `.gitignore`); fetch it with:

```
curl -o sources/matrix-cookbook/matrixcookbook.pdf \
  https://www.math.uwaterloo.ca/~hwolkowi/matrixcookbook.pdf
uv sync --extra pdf
uv run forge extract matrix-cookbook
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

### Confirmed by numerical check during card writing

- **eq (127)** — `∂Tr[(A + XᵀCX)⁻¹(XᵀBX)]/∂X`. The printed right-hand side is
  correct only when **A is symmetric**, which the book does not say: it states
  symmetry for B and C alone. The two halves of each differential collapse
  into the printed factors of 2 only if `M = A + XᵀCX` is symmetric, and
  `XᵀCX` already is, so the requirement falls on `A`.

  Checked against a central-difference gradient on a 4×3 `X`: with `A`
  symmetric the printed formula matches to 9e-07; with `A` non-symmetric it is
  wrong by 2.8, which is not a tolerance question. The general form is
  `−CX(M⁻¹NM⁻¹ + M⁻ᵀNM⁻ᵀ) + BX(M⁻¹ + M⁻ᵀ)` with `N = XᵀBX`.

  The card states the symmetry of `A` and records the addition.

### Suspected, not confirmed

Found by the transcribe pass reading crops. These are **not** covered by the
Lean formalisation, and nobody has checked them. They are recorded here so the
suspicion is not lost, and annotated on the unit so it reaches whoever writes
the card:

- **eq (302)** — printed as `A = LDL^T = L^T D L`. The standard LDL identity
  pairs `LDL^T` with `U^T D U` for a *distinct* unit upper-triangular `U`, not
  a repeated `L`. Transcribed as printed.
- **eq (95)** — first denominator printed `x^T B B x`, where every other term
  in the same identity uses `x^T B^T B x`. **Confirmed**: against a
  central-difference gradient with a non-symmetric `B`, the printed form is
  wrong by 8.6 and the transposed form matches to 1.8e-08. The card for this
  identity carries the corrected back, not the printed one, and says so — a
  transcription records what the book says, a card is what gets drilled.
- **eq (154) and eq (545)** — an unmatched closing parenthesis after
  `max(eig(A^{-1})`, in both places. Two independent agents found it
  separately, which makes it a repeated typo in the book rather than a
  misread. Fix both or neither.
- **§6.2, the last line of `E[(Ax+a)b^T(Cx+c)(Dx+d)^T]`** — a *minus* before
  `(Am+a)(Dm+d)^T`, where the analogous term in every sibling cubic-form
  identity on the same page carries a plus. Checked at 8x zoom and transcribed
  as printed; it may well be correct, since the sign genuinely differs between
  these identities.
- **eq (559)** — the density line prints `exp[-(s-mu)^2 / 2 sigma^2]`, with `s`
  where the surrounding line uses `x`. Transcribed as printed.
- **eq (143)**, two entries of the `α(A)` display. A card-writing pass
  reported that the offset `+2` entry is printed over `[[Aᵀ]₁ₙ]_{2,n−1}` where
  the second superdiagonal sum needs `[[Aᵀ]₁ₙ]_{1,n−1}`, and that the offset
  `−2` entry is printed over `[Aᵀ]₁ₙ` where it needs `[Aᵀ]ₙ₁`. It gave
  concrete numbers on a test matrix (34 printed against 32 correct; 33 against
  37) and reported the diagonal, both ±1 offsets and both corners as correct.
  **Not independently re-checked here** — verifying it means parsing the
  book's nested-submatrix notation exactly, which is where the doubt lives.
- **eq (202)** — the right-hand side `(A^+)^*` is set in non-bold `A` while the
  left-hand side is bold. Typography, not mathematics, but it will look like a
  different object on a card.

Each was transcribed **as printed**. Do not silently correct any of them when
writing a card: state the book's form, and put the correction in
`## notes` -- the deck is a record of this book, not of what it should have
said.

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
