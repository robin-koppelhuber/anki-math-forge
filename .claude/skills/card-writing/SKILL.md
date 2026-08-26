---
name: card-writing
description: How to turn a mathematical unit into a card worth reviewing - what makes a cardable unit, how to phrase a front so it admits exactly one answer, when a proof section earns its place, and how long any of it should be. Use when writing or augmenting cards in cards/, running /extract-cards or /augment, or judging whether a unit is worth carding at all.
---

# Writing matrix-calculus cards

The Python enforces structure. This file is the craft: nothing here is
checkable by a linter, which is exactly why it is written down.

## What makes a cardable unit

A unit is worth a card when **you would be annoyed to have to look it up**.

Card it when:

- it is a named or reusable result (`∂/∂X log det X`, Woodbury, the cyclic
  property of the trace);
- the answer is short and the prompt is unambiguous;
- getting it wrong quietly (a stray transpose) would cost you real time.

Skip it when:

- it is a step in a derivation rather than a result — you would never recall
  it out of context;
- it is trivially recoverable from another card you already have (if you know
  `∂ tr(AX)/∂X = Aᵀ`, `∂ tr(XA)/∂X` is not a second card);
- it is notation-specific to that book;
- it is a special case of a card you already have, with nothing new in it.

When in doubt, skip. A skip is sticky and cheap; a bad card is a small tax on
every review session for years.

## Fronts

**One question, one answer.** If a front admits two defensible answers, it is
two cards or a badly phrased one.

Good:

```
$\frac{\partial}{\partial X} \log \det X$
```

Bad, and why:

| Front | Problem |
|---|---|
| `Derivatives of the determinant` | A topic, not a question. |
| `$\frac{\partial}{\partial X}\log\det X$ and $\frac{\partial}{\partial X}\det X$` | Two cards. |
| `What is the derivative of the log determinant (denominator layout, X invertible, real)?` | The conditions belong in `## conditions`; the prompt should be the formula. |
| `$\frac{\partial}{\partial X} \log \det X = ?$` | The `= ?` is noise; the front *is* the question. |

Prefer bare mathematics on the front. Prose on a front is a sign the card is
really asking "do you remember this section" — which is not a card.

If the answer depends on a convention (layout, transpose placement), either
put the convention in `## conditions` **and** make the front unambiguous, or
do not write the card.

## Backs

The shortest complete answer. `$X^{-\top}$`, not a sentence explaining it.
Explanation goes in `## prose`, derivation in `## proof`.

If the back needs more than one line of mathematics, ask whether the front was
too broad.

## Conditions

Include when the identity is false without them: invertibility, symmetry,
positive definiteness, conformability, layout convention. One line. If a card
has no real conditions, leave the section out rather than writing "none".

Every card whose shape depends on layout says so — this deck is **denominator
layout** throughout (see CLAUDE.md).

## Proof

A proof section earns its place when the derivation is **short and load-bearing**
— two or three lines that make the result reconstructible rather than
memorised. Jacobi's formula for the log-det identity is worth it; "expand and
collect terms" is not.

Leave it out for definitional facts and for anything whose proof is a page.
A wrong or hand-wavy proof is worse than no proof.

## Prose

One sentence of intuition, ideally connecting to something scalar you already
know: *"the matrix analogue of (log x)' = 1/x"*. Optional. Cut it if it is
just the formula in words.

Written in **English** (CLAUDE.md).

## Length

| Section | Target |
|---|---|
| `front` | one formula; `check` caps the rendered length at 160 chars |
| `back` | one line |
| `conditions` | one line |
| `proof` | 2–4 lines |
| `prose` | one sentence |

## Verify

Set `verify: true` and write a `## verify` snippet for identities where a
stray transpose or sign would survive proofreading — Woodbury, block inverses,
matrix-differential results with several transposes. Not for the easy ones;
the point is coverage where the eye fails.

```python
X = invertible(4)
lhs = grad(lambda M: np.log(abs(np.linalg.det(M))), X)
rhs = np.linalg.inv(X).T
```

Set `lhs` and `rhs`; the runner samples several draws and compares. Available:
`np`, `rng`, `grad`, `randn`, `spd`, `sym`, `invertible`, `orth`. Sample a
matrix whose structure makes the claim falsifiable — testing a transpose on a
symmetric matrix proves nothing.

## Working from a unit

**Read the book's notation section before you write anything.**
`anki-forge source-text <source>` prints the cached text layer; the Notation
and Nomenclature table near the front defines every symbol the book uses. A
card that says `$A^+$` without knowing it means the pseudo-inverse is a card
that teaches you the wrong thing. Read the surrounding section too — it tells
you which conditions are load-bearing and which neighbouring identities you
would be duplicating.

The **crop is authoritative**. `tex_auto` is a transcription written by
`/transcribe` to help you triage; never copy it into a card without reading the
crop. Where the two disagree,
the crop wins, and if the crop is unreadable, annotate the unit rather than
guessing.

Keep the source citation exact — `Matrix Cookbook §2.4, eq. 61` — because the
review view links back to it and that is how a suspect card gets settled.

## Worked examples

**Good.**

```markdown
## front
$\frac{\partial}{\partial X} \log \det X$

## back
$X^{-\top}$

## conditions
$X$ invertible. Denominator layout.

## proof
Jacobi's formula: $d(\log\det X) = \operatorname{tr}(X^{-1}\,dX)$; reading the
differential as $\operatorname{tr}(G^\top dX)$ gives $G = X^{-\top}$.

## prose
The matrix analogue of $(\log x)' = 1/x$.
```

**Bad**, same unit:

```markdown
## front
What is the derivative of the log-determinant of a matrix?

## back
It is the inverse transpose, $X^{-\top}$, which you can derive from Jacobi's
formula, though note that in numerator layout you would write $X^{-1}$ instead.
```

The front is a topic prompt, the back mixes answer, derivation and a second
convention, and nothing states the layout the card actually uses.

*Add rejected cards here as you meet them during review — a rejection with a
one-line reason is the most useful thing this file can accumulate.*
