# The Matrix Cookbook

## The setting

- Finite-dimensional. Matrix and vector entries are real unless a card says
  otherwise; $A^\top$ is transpose and $A^\mathsf{H}$ conjugate transpose.
- **Denominator layout.** $\partial(\text{scalar})/\partial X$ has the shape of
  **`X`**: entry `(i,j)` of the result is $\partial f/\partial X_{ij}$.
  $\partial y/\partial x$ for vectors has shape `(dim x, dim y)`. Any card that
  could be read either way says so in `## conditions`.
- **In a derivative, every symbol other than the variable of differentiation
  is constant in it.** $\partial \operatorname{Tr}(AX)/\partial X = A^\top$
  holds because `A` does not depend on
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
squareness added" -- and 140 such notes were cut, because a sentence repeated
on every card stops being read, and an open note blocks `sync`. The cards
carry their own history now, so the lines are in git rather than in a list.

A `@me` note is for what a card cannot show by itself: the source being wrong,
this card's relation to another, or something still undecided. If the note
would only say "the condition next to it was added", the condition next to it
already says that.

## What a bare `\partial` means

A card whose front is `\partial(\det(\mathbf{X}))` is asking for the
**differential**, not a derivative with respect to anything in particular. It
is the first-order change in `\det(\mathbf{X})` produced by an arbitrary
perturbation `\partial\mathbf{X}` of the whole matrix, and the answer is
linear in `\partial\mathbf{X}`.

So it is not quite "differentiate with respect to every variable", though that
is the right instinct: no single variable is named because none is singled
out. The practical difference is that the answer keeps `\partial\mathbf{X}`
in it rather than dividing it away, which is what makes these the cards the
gradient rules are *derived from*. The book's chapter 2 opens with them for
exactly that reason.

Where a scalar parameter is named, the card writes it: `\partial\mathbf{Y}
/\partial x` is the same identity with the perturbation restricted to a
one-parameter family.

## How the layout convention was settled

It was recorded backwards, as the shape of $X^\top$, until two card-writing passes
flagged the contradiction independently. `verify.grad()` has always computed
the `X`-shaped gradient and the book uses it. On a square `X` the two are
indistinguishable, which is why the error survived every review; it first
bites on a rectangular `X`, where eq. 55 gives $2(X^{+})^\top$, an `X`-shaped
matrix. Checked numerically against `grad()` on a $5 \times 3$ `X`, residual
7e-10.

Kept because it is the argument, not the conclusion: the next source will have
its own layout question, and this is what settling one looks like.

## Source form

PDF. No LaTeX source is published, so the crop is the artefact. See
[README.md](README.md) for what extraction gets and for the errors found in
the book so far.
