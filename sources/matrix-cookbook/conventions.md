# Conventions for this source

The ambient setting every card from this source is read in, declared once here
so that no card repeats it. `anki-forge context <unit>` prints this file, so
whoever writes or reviews a card sees it without having to know it exists.

Machine-readable knobs live in `anki-forge.toml` — `[cards] layout`,
`[cards] language`, `[anki] deck`. This file is for what a configuration key
cannot say.

## The setting

- Finite-dimensional. Matrix and vector entries are real unless a card says
  otherwise; `ᵀ` is transpose and `ᴴ` conjugate transpose.
- **Denominator layout.** `∂(scalar)/∂X` has the shape of **`X`**: entry
  `(i,j)` of the result is `∂f/∂X_ij`. `∂y/∂x` for vectors has shape
  `(dim x, dim y)`. Any card that could be read either way says so in
  `## conditions`.
- **In a derivative, every symbol other than the variable of differentiation
  is constant in it.** `∂Tr(AX)/∂X = Aᵀ` holds because `A` does not depend on
  `X`. The book states this once, in §2.4's preamble; around thirty cards
  depend on it and none of them repeats it, which is right — a sentence on
  every card stops being read.

## Conditions, and who states them

**This source states conditions rarely.** Its tables print identities bare and
put whatever hypothesis they need in the surrounding prose, or leave it to the
reader. So most cards from it carry conditions the book does not: squareness,
invertibility, conformability, the shapes.

That is deliberate and it is the normal case here, which is why no card says
so. It was recorded on ninety of them once -- "source states no conditions;
squareness added" -- and 140 such notes were archived to
[notes-archive.md](notes-archive.md) because a sentence repeated on every card
stops being read, and an open note blocks `sync`.

A `@me` note is for what a card cannot show by itself: the source being wrong,
this card's relation to another, or something still undecided. If the note
would only say "the condition next to it was added", the condition next to it
already says that.

## How the layout convention was settled

It was recorded backwards, as the shape of `Xᵀ`, until two card-writing passes
flagged the contradiction independently. `verify.grad()` has always computed
the `X`-shaped gradient and the book uses it. On a square `X` the two are
indistinguishable, which is why the error survived every review; it first
bites on a rectangular `X`, where eq. 55 gives `2(X⁺)ᵀ`, an `X`-shaped matrix.
Checked numerically against `grad()` on a 5×3 `X`, residual 7e-10.

Kept because it is the argument, not the conclusion: the next source will have
its own layout question, and this is what settling one looks like.

## Source form

PDF. No LaTeX source is published, so the crop is the artefact. See
[README.md](README.md) for what extraction gets and for the errors found in
the book so far.
