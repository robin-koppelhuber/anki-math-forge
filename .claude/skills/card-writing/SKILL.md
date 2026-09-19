---
name: card-writing
description: How to turn a mathematical unit into a card worth reviewing - what makes a cardable unit, how to phrase a front so it admits exactly one answer, when a proof section earns its place, and how long any of it should be. Use when writing or augmenting cards in cards/, running /extract-cards or /augment, or judging whether a unit is worth carding at all.
---

# Writing cards

The Python enforces structure. This file is the craft: nothing here is
checkable by a linter, which is exactly why it is written down.

**Which stage you are at matters.** A unit is a decision; a card is the
content (CLAUDE.md invariant 9). Triage answered two questions — is this worth
a card, and roughly what about — and a unit's `@claude` brief is that second
answer written down. Read it first: it is the only instruction this pass gets.
Everything else on this page is the *card* stage, where depth belongs. Take
the context you need and iterate; a draft is not a commitment.

**A note on the examples.** The rules here are meant to survive a change of
source: each is stated without reference to any particular subject. The worked
examples are matrix calculus because that is what this deck currently holds,
and they are illustrations, not part of the rule. If an example stops making
sense because the deck moved on, replace the example — the rule above it
should still stand.

## Two kinds of card

`type: identity` states a fact: it has one definite answer, and `verify` can
check it numerically. Everything below is written for one.

`type: intuition` explains a fact instead — why a bound is tight, what a term
is really measuring, which of two hypotheses is doing the work. It is what a
passage you marked in a prose source becomes. Three differences, and the rest
of this file still applies:

- **no `## conditions`** — a hypothesis belongs to the statement, not to a
  reading of it. If a card genuinely needs one, it is an identity wearing the
  wrong type.
- **no `## verify`** — there is nothing numeric to check about an explanation.
- **the front asks *why* or *which*, not *what*.** "Why does the bound need
  independence?" has one answer; "tell me about the bound" has none. The
  one-answer rule below is the same rule, applied to a different question.

Both are still a single idea, still short, and still refuse to be a paragraph.

## What makes a cardable unit

A unit is worth a card when **you would be annoyed to have to look it up**.

Card it when:

- it is a named or reusable result ($\partial/\partial X \log\det X$, Woodbury,
  the cyclic property of the trace);
- the answer is short and the prompt is unambiguous;
- getting it wrong quietly (a stray transpose) would cost you real time.

Skip it when:

- it is a step in a derivation rather than a result — you would never recall
  it out of context;
- it is trivially recoverable from another card you already have (if you know
  $\partial \operatorname{tr}(AX)/\partial X = A^\top$, then
  $\partial \operatorname{tr}(XA)/\partial X$ is not a second card);
- it is notation-specific to that book;
- it is a special case of a card you already have, with nothing new in it.

When in doubt, skip. A skip is sticky and cheap; a bad card is a small tax on
every review session for years.

**This is the triage question, and on a prose source it is asked differently.**
Everything above is written for an identity: a named result, a short answer, a
stray transpose that would cost you time. None of those tests fires on a
marked paragraph, and applying them there skips every intuition card in the
book. What to ask instead: *would I be annoyed to have to reconstruct this
reasoning?* A passage earns a card when it settles something — why a bound is
tight, which hypothesis is load-bearing, what a term is actually measuring —
and not merely because it was worth marking while reading. Marking says "this
mattered as I read"; carding says "this is worth meeting again, cold, in six
months", and the gap between those two is most of what triage is for.

Judge it from the passage and what you wrote beside it. **Do not demand a
transcription first** — the sentence is right there, and a boxed figure has no
transcription to wait for.

## Fronts

**One question, one answer.** If a front admits two defensible answers, it is
two cards or a badly phrased one.

Good:

``
$\frac{\partial}{\partial X} \log \det X$
``

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

### The card must stand alone

**Every object on the front is defined before the front uses it**, either
ambiently or on the card itself. **Ambient means whatever the source declares**
— `forge context <unit>` prints it, and it is per source, because
"entries are real" and "denominator layout" are facts about one book rather
than about this tool. Read it rather than assuming. Everything it does not
cover is the card's job.

If `context` says no conventions are recorded for a source, that is not
permission to invent them: write them down first, or every card after this one
is guessing at the same things independently.

A front reading `$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B})$`
is unanswerable as it stands: nothing says what `A` and `B` are, and the answer
depends on their shapes. Either the shapes are forced by the expression being
defined and you say so in `## conditions`, or they are not and the front is
incomplete.

The test: **could someone who has never seen this book answer it?** They have
the ambient conventions and nothing else. No neighbouring card, no section
heading, no page. If answering needs something that is not on the card, the
card is not finished.

Two failure shapes to watch for, both of which look fine while writing:

- a symbol introduced by the source's surrounding prose (`where `W` is the
  inverse of `A`) and silently inherited onto the card;
- a shape constraint that the reviewer must reconstruct to know what the answer
  even looks like.

## Backs

The shortest complete answer. `$X^{-\top}$`, not a sentence explaining it.
Explanation goes in `## prose`, derivation in `## proof`.

If the back needs more than one line of mathematics, ask whether the front was
too broad.

## Conditions

Include when the identity is false without them: invertibility, symmetry,
positive definiteness, conformability, layout convention. One line. If a card
has no real conditions, leave the section out rather than writing "none".

Every card whose shape depends on layout says so. Which layout is the
source's to declare, not this file's: `forge context <unit>` prints it.

### Form: mathematics, in a fixed order

Write the mathematics, not a sentence about the mathematics. One line, clauses
separated by `;`, always in this order:

1. **shapes** — `$\mathbf{A} \in \mathbb{R}^{m \times n}$`, `$\mathbf{B} \in \mathbb{R}^{n \times m}$`
2. **structural properties** — `$\mathbf{A}$ invertible`, `$\mathbf{A} = \mathbf{A}^T$`,
   `$\text{rank}(\mathbf{X}) = m$`
3. **domain restrictions** — `$\det(\mathbf{X}) > 0$`, `$\mathbf{X} \neq 0$`
4. **layout**, last and only when the shape depends on it, naming whichever
   layout the source declares, and nothing appended to it. `forge context`
   prints the source's setting; when a source declares none, there is no
   layout clause to write and inventing one would be asserting a convention
   the source never claimed.

**The typographic convention gives you the type, not the shape.** The source's
declared setting says `\mathbf{X}` is a matrix with real entries. It does not say
`\mathbf{X}` is *square*, and a matrix generally is not.

So for `$\frac{\partial}{\partial \mathbf{X}}\prod_i \lambda_i$` the squareness is load-bearing: eigenvalues exist
only for a square matrix, and without that clause the card asks something
undefined. Write `$\mathbf{X} \in \mathbb{R}^{n \times n}$`, not "`\mathbf{X}` square" and not nothing.

Use the set-membership form as the single spelling, everywhere:

- it is mathematics rather than an English word, which is the rule above;
- it names `n`, which the answer and the later clauses usually refer to;
- it is the same shape of clause as the rectangular cases (`$\mathbf{X} \in \mathbb{R}^{m \times n}$`), where
  giving the dimensions is not optional -- one form covers both, so the reader
  never has to notice which kind of card this is.

Stating `\mathbb{R}` is mildly redundant against the ambient "entries are real", and
worth it: the deck also has complex cards, where the clause reads `$\mathbf{X} \in \mathbb{C}^{n \times n}$`, and
the contrast only works if both are always written.

| write | not |
|---|---|
| `$\mathbf{A} \in \mathbb{R}^{m \times n}$; $\mathbf{B} \in \mathbb{R}^{n \times m}$.` | "A is m×n and B is n×m so that both products are defined and square." |
| `$\mathbf{X}$ invertible; $\det(\mathbf{X}) > 0$. Denominator layout.` | "Denominator layout: the result has the shape of X, which need not be square." |

The fixed order and the fixed layout sentence are the point. A reviewer reads
hundreds of these: when every card puts shapes first and ends the same way,
the eye goes straight to what differs. Two spellings of the same requirement
read as two different requirements.

**Conditions state requirements. They do not explain them.** Why a condition
is needed, what breaks without it, what a reader might wrongly assume — those
go in `## prose`, or in `## notes` when they are addressed to someone. A
condition that argues is doing another section's job and crowds out the one
thing this section is for.

### A condition must be worth stating

A `## conditions` line earns its place when **violating it changes something**:
the identity becomes false, or a reader applies it where it does not hold.

What does not earn its place is restating that the expression is well-formed.
"`A` and `B` are conformable" on a card whose front is `Tr(AXB)` says only
that the front means something, which the reader already assumed by reading
it. If the shapes are forced, put them in the statement where they inform the
answer, not in a condition where they inform nothing.

**When the real condition is existence, ask about existence.** For a
derivative identity there is usually a genuine question hiding in the
conditions: *where does this hold?* If the answer is the generic one --
wherever the expression is defined -- it is not a card and barely a condition.
If the answer is specific, it is often the more valuable card of the two:

| identity | the interesting question |
|---|---|
| $\partial \ln\det(X)/\partial X$ | not "is `X` invertible" but $\det(X) > 0$, over $\mathbb{R}$ |
| $\partial \ln\det(X^\top X)/\partial X$ | `X` of full **column** rank, not merely nonzero |
| $\partial \operatorname{Tr}[(A + X^\top CX)^{-1}X^\top BX]/\partial X$ | the printed form needs `A` **symmetric**, which the book never says |

So: **do not** add "when does this exist?" as a second card by reflex. Across
a table of derivative identities the answer is the same generic sentence, and
a hundred cards with one answer teach nothing. **Do** make it a card when the
answer is specific enough to be got wrong -- and then it is a real card, not a
restatement, because its front asks something the identity card does not.

The check either way: read the condition and ask what a reader would do
differently on being told it. If the answer is "nothing", cut it.

### Conditions are shown with the prompt

They render **above the answer**, in Anki and in the review view alike, under
the heading *given*. Two consequences.

They are part of the question, so they must read as setting rather than as
commentary. `$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible` tells you
which question you are being asked; "invertibility is needed here because the
right-hand side would otherwise be undefined" is an answer to a different one.

And a condition must not give the answer away. If stating it would make the
front trivial, it is not a condition -- it is part of the answer, and belongs
in `## back` or `## prose`.

### Where a notation gloss goes

A symbol the deck declares no ambient meaning for has to be explained
somewhere. Which section depends on **where the symbol appears**, not on where
it is convenient:

- **In the front** -- the gloss belongs in `## conditions`. You cannot answer a
  question posed in notation you do not have.
- **Only in the back** -- the gloss belongs in `## prose`. Conditions are the
  setting of the question, and a symbol that is not in the question is not
  part of its setting. Putting it there also leaks: naming the Hadamard
  product before the answer tells the reader the answer contains one.

The second case is easy to get wrong, because the gloss feels like a
precondition for understanding the card. It is a precondition for
understanding the *answer*, and the answer is where it should sit.

### Define, don't rename

A gloss that swaps a symbol for a proper name has not glossed anything.
*"Here $\circ$ Hadamard product"* tells a reader who does not know $\circ$ the
name of a thing they also do not know; *"here $\circ$ multiplies entry by
entry (the Hadamard product)"* is shorter and usable. The same trap catches
"the transposed cofactor matrix", "the elementary symmetric polynomials",
"the generalised Rayleigh quotient": each is a name defined by more names.

So, everywhere a name appears on a card, in `## conditions`, `## prose` or
`## uses`:

**Say the thing in the shortest plain words that make it usable, then put the
formal name in parentheses.** The plain half carries the meaning; the name
rides along so the reader can look it up and so the card matches how the
result is spoken about.

| Renames | Defines |
| --- | --- |
| `Here $\circ$ Hadamard product.` | `Here $\circ$ multiplies entry by entry (the Hadamard product).` |
| `$(\cdot)^{+}$ is the Moore-Penrose pseudo-inverse.` | `$(\cdot)^{+}$ inverts what is invertible and zeroes the rest (the Moore-Penrose pseudo-inverse).` |
| `L-optimal experimental design.` | `Choosing where to measure so the estimate comes out most precise (L-optimal design).` |

This catches ordinary words too, not just proper names. **"free"** was on
nine cards ("$\mathbf{X} = \mathbf{X}^T$ with $X_{ij}, i \le j$ free") and
never said what it meant: which entries you actually vary, the rest following
from the constraint. Written out, *"varied over $X_{ij}$ with $i \le j$ only,
the rest following by symmetry"*, it needs no gloss at all, which is the
better outcome. The same goes for a symbol like $\delta$: say *"$1$ when
$i = j$ and $0$ otherwise"* and the Kronecker delta needs no introduction.

And when a card names a function, **say what it is a function of.**
"$f$ scalar-valued" does not tell a reader that $f$ eats the matrix being
differentiated; `$f : \mathbb{R}^{n \times n} \to \mathbb{R}$` does, in
fewer words.

**A structure named on the front is defined in `## conditions`, as
mathematics.** Conditions render with the prompt, so this puts the definition
inside the question without cluttering it: the front says *"for Toeplitz
`T`"*, the conditions say `$T_{ij} = t_{i-j}$`, and a reader who does not know
the word can still answer. Do not explain the structure on the front itself,
which turns a prompt into a lecture, and do not leave it to prose, which is
only read after the answer.

| Front | Conditions |
| --- | --- |
| `for Toeplitz $\mathbf{T}$` | `$T_{ij} = t_{i-j}$` |
| `for symmetric $\mathbf{X}$` | `$\mathbf{X} = \mathbf{X}^T$` |
| `for diagonal $\mathbf{X}$` | `$X_{ij} = 0$ for $i \neq j$` |
| `for positive definite $\mathbf{A}$` | `$\mathbf{x}^T\mathbf{A}\mathbf{x} > 0$ for every $\mathbf{x} \neq \mathbf{0}$` |

The last one is the trap. `$\mathbf{A} \succ 0$` looks like mathematics but
is only the same name in symbols, so it defines nothing a reader did not
already have to know.

A name with no short plain version does not go on the card at all. If five
words will not carry it, it is not a pointer, it is a second card's worth of
material: cut it. *"Bearing-only sensor Jacobians"* fails this; *"how a
bearing to a target swings as the sensor moves"* passes and needs no name.

The exception is a name the deck's own front or back already spells out. When
the defining equation is sitting next to the word, the word is glossed:
`$\text{Tr}(\mathbf{X}^T\mathbf{X}) = \|\mathbf{X}\|_F^2$` defines the
Frobenius norm on the spot, and repeating it in words is padding.

### Vague is not plain

The rule above bans a name that stands in for the meaning. This is the other
direction: a paraphrase that stands in for a name the source has already
earned.

*"the random variable falls off fast"* is not the plain version of *"the
random variable is sub-Gaussian"*. It is a weaker claim and a different one.
Sub-Gaussian is an inequality you can check and use; "falls off fast" is a
feeling about a plot. A card that teaches the feeling has taught something you
cannot cite, cannot look up, and will not recognise when the next paper says
the word.

So, wherever the source has named the thing:

**Use the most specific name the source licenses, and then define it the way
the rule above says.** Both halves. The name is what the literature says and
what you will meet again; the plain version is what makes the card answerable
by somebody holding only this card.

| Vague | Named |
| --- | --- |
| `$X$ falls off fast` | `$X$ is sub-Gaussian: $\mathbb{E}\,e^{\lambda(X-\mu)} \le e^{\lambda^2\sigma^2/2}$` |
| `the error shrinks quickly` | `the error is $O(1/n)$` |
| `for large $n$` | `for $n \ge 2d$` |

The third is rule 3 under **Language** wearing a different hat: an unwitnessed
"large" and an unwitnessed "often" fail for the same reason, which is that the
reader cannot check either one.

**Most specific, not most impressive.** "Light tail" is itself vague: lighter
than exponential, sub-exponential and sub-Gaussian are all light to somebody.
If the source proves a sub-Gaussian bound, the card says sub-Gaussian. If the
source only says the tail decays and never says which class, the card says
what the source says, and the imprecision is the source's rather than yours.

**Some words name no property at all.** "Well-behaved", "nice", "reasonable":
there is no more specific version of these because there is nothing there.
Say which property the result actually needs, or cut the word.

**Inside the source's scope, and that bound is structural.** A card must not
name a term the source never introduces. The deck orders itself by `requires`,
so a term no card here defines is a forward reference to nothing, and a reader
meeting it has been tested on material this deck never taught. When the right
word is outside the source, either it is a card of its own first, or the claim
stays in the source's language and `## notes` records that a sharper name
exists elsewhere.

**An `intuition` card still has to explain.** Naming the class is the anchor,
not the answer: a back that says "because it is sub-Gaussian" has answered
"what is this called". Say what the property buys, and name it while you do.

### How far down to go

The test: **would omitting it make the card false, or make a plausible reader
apply it wrongly?** If violating it is impossible inside the deck's declared
setting, it is ambient, not a condition.

Three tiers, and only the middle one belongs on a card.

1. **Ambient, declared once.** Finite-dimensional; entries real unless the card
   says otherwise; $A^\top$ transpose and $A^\mathsf{H}$ conjugate transpose.
   Those are examples; the source declares its own. In its `project.toml`, not
   on 500 cards. A sentence repeated on every card stops being read, and then
   the one card where it is load-bearing reads like all the others.
2. **On the card, because the identity turns on it.** Conformability
   ($\operatorname{Tr}(AB) = \operatorname{Tr}(BA)$ needs A to be $m \times n$
   and B $n \times m$, and *neither* square). Dimension
   ($\det(I+A) = 1 + \det(A) + \operatorname{Tr}(A)$ holds at $n = 2$ and
   nowhere else). Field, when it changes the claim or the reading: eigenvalues
   are counted over $\mathbb{C}$ with algebraic multiplicity, or a real matrix
   with no real eigenvalues breaks the identity; $a^\top a$ is $\sum_i a_i^2$
   in both fields but is the squared norm only over $\mathbb{R}$.
3. **Out of scope, not stated.** Infinite dimensions, trace-class operators,
   Fredholm determinants. The source is about matrices. Saying "finite
   dimensional" on every card buys nothing, because nothing in the deck is
   not.

The interesting cases are the ones where tier 3 is where a reader's intuition
already lives: state the tier-2 condition that keeps them out of it, rather
than the tier-3 fact that would not have occurred to them.

## Proof

A proof section earns its place when the derivation is **short and load-bearing**
— two or three lines that make the result reconstructible rather than
memorised. Jacobi's formula for the log-det identity is worth it; "expand and
collect terms" is not.

**Write the steps, not a description of the steps.** Where the source prints a
derivation, or a short standard one exists, give it as display maths line by
line, one step per line, each following from the one above. Prose compressing
three lines of algebra into a sentence is the failure to avoid: "expand,
collect and use the cyclic property" is a sentence you can only follow if you
could already do the derivation, which is the opposite of what a proof section
is for.

```markdown
## proof
$$\operatorname{tr}(ABC) = \operatorname{tr}(BCA)$$
$$= \operatorname{tr}(CAB)$$
```

### Line up the relation symbol, where there is room for it

Two or more display lines that all hang off the same relation are easier to
read aligned on it than stacked: the eye finds the step by looking at what
changed, which is the right-hand side, and an aligned block puts all of those
in one column.

```markdown
$$\begin{aligned}
\operatorname{tr}(ABC) &= \operatorname{tr}(BCA) \\
                       &= \operatorname{tr}(CAB)
\end{aligned}$$
```

**It is a judgement call every time, and the thing to judge is the width the
right-hand side is left with.** An aligned block reserves as much width as the
widest left-hand side, for every row. Where one side is a long expression and
the other has real content, that column tax is paid by the part you are
actually reading, and on a phone it is paid by wrapping or by shrinking the
whole block. In that case keep the steps as separate display blocks and let
each use the full width.

The same goes for aligning things that are not the same relation. Lining up an
`=` under a `\le` because both are relations produces a table, and a table of
unrelated lines is harder to read than the lines were.

Both shapes are one section either way: a newline inside `$$...$$`, and the
newline that ends a display block, are not hard breaks on the card. `check`
only counts the ones that fall in prose.

Prose belongs around the steps, not instead of them: one clause naming the
move, where the move is not evident from the line, and the line itself
underneath. Where the source's own derivation is longer than a card can hold,
prefer the two or three steps that carry the result over a summary of all of
them; a partial derivation you can follow beats a complete one you cannot.

Leave it out for definitional facts and for anything whose proof is a page.
A wrong or hand-wavy proof is worse than no proof.

## Pictures

A card can show a figure, a diagram or a table:

```markdown
![the graphical model, with the plate](unit:krause...:FI39W9FM)
![the figure](unit)
```

The bare form means the unit the card was written from, which is the usual
case. There is no image file anywhere: the reference names a unit, and the
crop is rendered from the source document and uploaded when `sync` runs. So
the unit has to be one with geometry -- an image or area annotation, or any
mark on a PDF -- and `check` refuses the card if the picture cannot be drawn.

**Which section it goes in is yours to decide, and it is the whole decision.**
The same figure is three different cards depending on where you put it:

- `## front` asks you to read it. "What does this diagram say about $X_1$ and
  $X_n$?" The answer is in `## back`, in words.
- `## back` makes it the answer. The front asks a question the picture
  settles: "what does a directed graphical model of conditionally independent
  $X_i$ look like?"
- `## prose` supports an explanation that stands without it. The card is
  already complete; the picture is there because seeing it once is worth a
  paragraph.

A figure on both sides is a card that answers itself. If the front and the
back want the same picture, the card is a `## front` one and the question
needs sharpening.

**A picture is not an excuse for a vague front.** "Explain this figure" is the
same failure as "everything about determinants": it admits many answers and
grades none of them. Ask for the one thing the figure is on the card to
teach.

**Caption it for the reader who cannot see it.** The alt text becomes the
card's `alt` attribute, and it is also what you will read in a diff six
months from now: "the graphical model, with the plate" and not "figure".

## Uses

Optional, and **one clause** — `check` caps it at 150 rendered characters.
Written the way **Define, don't rename** requires: the setting in plain
words, its formal name in parentheses behind them.
Where this result actually gets used: the setting you would meet it in, not a
restatement of what it says.

Past a clause it stops being a pointer and becomes a paragraph on the back of
a flashcard, which is what `## prose` is for. If naming the setting needs a
sentence of explanation, the explanation is prose and the name is the uses
line.

```
## uses
Choosing where to measure so the estimate comes out most precise
(D-optimal design).
```

Good ones name a place: an algorithm, a derivation you would recognise, a
standard result it feeds. Bad ones fail in one of two directions. Generic
("useful in optimisation") is true of everything here and so says nothing.
Bare jargon ("L-optimal experimental design") says something, but only to a
reader who already knew it, and that reader did not need the line.

Reserve it for results where the answer alone leaves you asking *why would I
ever need this*. On an identity whose use is obvious from its shape, leave it
out. Most cards should not have one; the section exists for the handful where
knowing the setting is what makes the card stick.

It is not `## prose`. Prose says what the result *means*; uses says where it
*turns up*.

## Prose

One sentence of intuition, ideally connecting to something scalar you already
know: *"the matrix analogue of (log x)' = 1/x"*. Optional. Cut it if it is
just the formula in words, and apply the punchline test in **Language**: if
the halves of its one sentence already live in other sections, it is a
restatement.

Written in the language `[cards] language` declares.

## When the source is wrong

Transcription and carding answer to different rules, and conflating them is
how a known-false formula ends up being drilled for years.

A **transcription** records what the book prints. The crop is authoritative,
errors included (DESIGN.md §4).

A **card** is what you review. A back you have shown to be false does not
belong in it, whatever the book prints. Correct it, and record both the
book's form and the evidence in `## notes` — the deck is a record of the
mathematics, and `projects/<name>/README.md` is the record of the book.

The bar is evidence, not suspicion. `verify` exists for this: one identity in
this deck has a printed denominator wrong by 8.6 against a numerical gradient
while the transposed form matches to 1.8e-08, and *that* is what licenses
changing the back. Where you only suspect, card it as printed and say so.

## What earns a `@me` note

A note is read by a human, blocks `sync` until resolved, and is the only part
of a card nobody can skim past. Three things earn one:

- the **source is wrong**, or its stated conditions are insufficient;
- this card stands in a **relation to another card** -- it duplicates one,
  overlaps one, or was kept despite being a special case of one;
- something is **undecided** and you are handing the decision over.

Nothing else. In particular, **"the source did not state this condition, so I
added it" is not a note**: the condition is sitting on the card, and if adding
conditions is the normal case for a source, that belongs in its
the source's own file, once.

The first pass over this deck wrote 151 notes across 87 of 98 cards, 3,769
words, most of them that one sentence. Every card was blocked from syncing by
a note nobody would read. Eleven survived the cut.

## Language

Adopted from the writing guidelines in `SML-Summer-2026/shared/UBIQUITOUS_LANGUAGE.md`,
kept only where a flashcard makes the case stronger than a paper does.

1. **Name, do not point.** No "this condition", "the same identity", "the map
   above". **A card is reviewed with no context at all** — no preceding
   sentence, no page, no neighbouring card. A bare pointer that a paper could
   just about carry has nothing to resolve against here. Write the symbol or
   the formula.
2. **State, do not announce.** No opener whose content arrives after a colon:
   "two cases, and the second is the useful one: ...". Write the fact as the
   sentence. On a front, an announcement is not a question.
3. **No unwitnessed quantifiers.** "often", "in general", "most of the time"
   name a case the reader can check, or come out. On a card there is no
   surrounding text in which the witness might be found later.
4. **Contrast must earn its negation.** "X, not Y" is worth the words only
   when Y is a misreading someone would actually form. *"Neither factor need
   be square"* earns it, because assuming both are square is the natural
   error. A vague Y is emphasis; cut it and let X stand.
5. **No scaffolding.** A sentence about the card rather than the mathematics
   ("note that this generalises the scalar case") either binds a choice to a
   consequence in the same sentence or goes.
6. **The punchline test**, for `## prose`. It should have a punchline statable
   in one sentence. If the halves of that sentence already live in `## front`,
   `## back` or `## conditions`, the prose is a restatement.
7. **Say which quantity you mean.** The guideline that bans "hardness" as a
   word covering four different quantities is why this deck's field is called
   `derivation` and takes `definitional | short | long` rather than a
   difficulty score.
8. **One section, one job.** `front` asks, `back` answers, `conditions` bounds,
   `proof` derives, `prose` interprets. A claim that needs its own
   justification does not belong in `prose`: it is a `proof`, or it is another
   card.
9. **Simple grammar.** Short declarative sentences, one idea each. Prefer a
   full stop to a subordinate clause. A card is read in a few seconds under
   time pressure, which is the shortest attention any prose in this repo gets.
10. **No line breaks inside a section.** Write each section body as one long
    line and let the editor wrap it. **A newline is not whitespace here**: it
    becomes a `<br>` on the Anki card, so a body wrapped at column 78 renders
    with hard breaks mid-sentence at whatever column you happened to stop.
    Break a line only where you want a break to appear. `check` warns.
11. **No em-dashes.** Use a colon to introduce, commas or parentheses for an
    aside, or two sentences. An em-dash aside inside a sentence that already
    carries a formula gives the reader two suspensions to hold at once.

**Not adopted, deliberately.** That document bans "display" for mathematics.
Here the display/inline distinction is load-bearing: the segmenter keys on
display maths being indented clear of the text margin, so "display equation"
stays, meaning the typographic thing.

Its environment discipline (definition / lemma / remark) does not transfer
either. Cards have no numbered environments, and rule 8 above already splits
the same work across sections.

The em-dash ban **was** declined here, on the grounds that card text is short
enough not to need it. That was wrong twice over: five uses across three cards
made "retrofitting is churn" false, and a card is exactly where a suspended
aside costs most, since there is no surrounding paragraph to recover the
thread from.

## Length

| Section | Target |
|---|---|
| `front` | one formula; `check` caps the rendered length at 160 chars |
| `back` | one line |
| `conditions` | one line |
| `uses` | one clause, ~120 chars, and usually absent |
| `proof` | 2–4 lines |
| `prose` | one sentence |

## Verify

Set `verify: true` and write a `## verify` snippet for identities where a
stray transpose, index or sign would survive proofreading — Woodbury, block
inverses, a density with several parameters, anything with a sum whose limits
you had to think about. Not for the easy ones; the point is coverage where the
eye fails.

**The bar is high, and it is not about how important the card is.** Ask
whether a plausible typo in this card would still pass the check you are about
to write. If it would, the check is decoration: it reports coverage the deck
does not have, and the next person reads a green `verify` badge as evidence.
Three ways that happens:

- **Both sides from one expression.** If `rhs` is `lhs` rearranged the way you
  would rearrange it on paper, the snippet tests your algebra twice and the
  card not at all. Write `rhs` from the card's *back*, independently.
- **One fixed case.** A snippet that draws nothing random checks a single
  point, usually a convenient one. `check` warns about this (`verify-fixed`).
  Sample instead, and sample the shape that makes the claim falsifiable: a
  rectangular matrix where the transpose matters, a non-symmetric one where
  the symmetry does.
- **Nothing to get wrong.** A definitional fact has no numerical content to
  check. Leave `verify: false` and say so by omission.

``python
X = invertible(4)
lhs = grad(lambda M: np.log(abs(np.linalg.det(M))), X)
rhs = np.linalg.inv(X).T
``

Set `lhs` and `rhs`; the runner samples several draws and compares. Available:
`np`, `rng`, `grad`, `randn`, `spd`, `sym`, `invertible`, `orth`. Sample a
matrix whose structure makes the claim falsifiable — testing a transpose on a
symmetric matrix proves nothing.

## Frequency and derivation

Two optional frontmatter fields, both coarse, both reaching Anki as tags.

`frequency: core | common | rare` — how often this identity actually turns up.
`core` is what you would be embarrassed to look up; `rare` is worth having on
file but not worth drilling. If everything looks `core`, you are grading the
subject rather than the identity.

`derivation: definitional | short | long` — what reconstructing it would take.

- `definitional` — true by definition; there is nothing to derive. "An
  orthogonal matrix satisfies $Q^\top Q = I$" is not a result, it is what the word
  means. These are **recognised, not reconstructed**, which is a different
  kind of review, and it is why "how hard to derive" is the wrong question
  for them rather than merely an easy one.
- `short` — a couple of lines from something you already know.
- `long` — you would want the proof in front of you.

Leave both off when you are unsure. An absent judgement costs nothing; a
confidently wrong one gets filtered on later and shapes what you drill.

Three values each, deliberately. A 1–10 scale would be invented precision that
no two sessions would apply the same way.

## Working from a unit

**A card is not one-to-one with a unit.** A display equation the segmenter cut
into three lines is three units and one identity: card it whole with repeated
`--unit`, and all three are marked carded. Conversely one unit stating two
independent facts is two cards citing the same unit. `forge context
<unit>` lists every unit on the page in reading order so the pieces are
visible. Most units are still one card — merge when the pieces are meaningless
apart, split when one card would have two answers.


**Read the book's notation section before you write anything.**
`forge source-text <source>` prints the cached text layer; the Notation
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

Keep the source citation exact — whatever `forge new` generated from the
unit's locator, down to the section and the number — because the review view
links back to it, and that is how a suspect card gets settled.

## Worked examples

**Good.**

``markdown
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
``

**Bad**, same unit:

``markdown
## front
What is the derivative of the log-determinant of a matrix?

## back
It is the inverse transpose, $X^{-\top}$, which you can derive from Jacobi's
formula, though note that in numerator layout you would write $X^{-1}$ instead.
``

The front is a topic prompt, the back mixes answer, derivation and a second
convention, and nothing states the layout the card actually uses.

*Add rejected cards here as you meet them during review — a rejection with a
one-line reason is the most useful thing this file can accumulate.*
