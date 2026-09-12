# How this project is written

Adapted from the `UBIQUITOUS_LANGUAGE.md` of the SML Summer 2026 notes, which
states its prose rules without reference to its own subject matter so they can
be carried between projects. This is that carry, with what was kept, what was
changed and what was dropped.

Two halves, and the second is why the first works. **The rules** govern prose
in this repo: markdown, docstrings, template text, and the `.claude/`
instructions. **The vocabulary** fixes what each object is called, because rule
3 has nothing to check against without it.

## The rules

1. **Simple grammar.** Short declarative sentences, one idea each. Prefer a
   full stop over a subordinate clause.
2. **No em dashes in prose.** Use a colon to introduce, a pair of commas or
   parentheses for an aside, or two sentences. They stay where they separate a
   label from its value in the interface, which is what a dash is for:
   `green — 12 units`.
3. **No undefined jargon.** Use a term from the vocabulary below. If the right
   word is missing, do not coin one silently: add an entry here first.
4. **Math in LaTeX, in every file a card writer reads.** `.claude/**` and
   `sources/*/conventions.md` reach whoever writes a card, through the skill
   and through `forge context`, immediately before they emit `$...$` into a
   card. An example written `∂ tr(AX)/∂X = Aᵀ` is an example in the notation
   the card must not use, sitting in the one file the next pass copies from.
   Write `$\partial \operatorname{tr}(AX)/\partial X = A^\top$`, which renders
   as maths wherever markdown does and is the LaTeX a card would carry.
   Unicode maths belongs in a chat window, where LaTeX would not render, and
   in a source document's own cached text, which is not ours to rewrite.
5. **State, do not announce.** No opener whose content arrives only after a
   colon. "Not scriptable: the interesting part is the pace of triage" says
   nothing until the second half. Write the fact as the sentence. A colon may
   introduce a list, a block, or a value; as glue between an assertion and its
   elaboration it stacks two clauses into one sentence and is the announcing
   pattern in miniature.
6. **No unwitnessed quantifiers.** "Several", "many", "most", "usually" name
   at least one instance the reader can check, or the claim is cut. This repo
   measures things, so the witness is usually already to hand: "25 of §8.2's
   36 units" rather than "most of them".
7. **No scaffolding prose.** A sentence whose subject is the exposition
   ("this section explains…", "stating it this way lets…") either names a
   choice and binds it to its consequence in the same sentence, or is cut.
8. **Name, do not point.** Bare anaphora ("the identity", "this condition",
   "the map") makes the reader resolve a reference before parsing the claim.
   Write the symbol, the filename, or the term. A bare pointer is fine only
   when its referent is in the same or the previous sentence and nothing else
   competes for it.
9. **Contrast must earn its negation.** "X, not Y" and "X rather than Y" are
   admissible when Y is a specific misreading a reader could form, ideally one
   this project has a name for. "Frozen, not deleted" earns it: a frozen
   module looks exactly like a dead one. A vague or strawman Y is empty
   emphasis, so cut the contrast and let X stand.
10. **The punchline test.** Interpretive prose should have a point statable in
    one sentence. If both halves of that sentence already have homes
    elsewhere, the paragraph is a cross-reference. Failing the test is a flag
    to raise rather than an automatic cut.
11. **Causality.** Every term a sentence uses is defined earlier in reading
    order. A forward reference is allowed as a pointer ("see below") in
    interpretive prose, never inside a rule or a definition. A dependence that
    cannot be satisfied in the current order means moving the definition.
12. **Corrections are applied at the site.** A document may not correct a
    claim in another file by recording the correction only in itself. Edit the
    original, or leave a one-line pointer there. When a limitation belongs to
    one line of code, it is a comment on that line and not a roadmap entry.
13. **A restatement may only weaken.** [CLAUDE.md](../CLAUDE.md) states each
    invariant in one line and [CONTRACT.md](CONTRACT.md) states it in full.
    The short form may drop a qualifier; it may never add a guarantee the long
    form does not make. This is the live hazard in having two of them.

## Enforced, not just written down

`tests/test_style.py` checks rule 4 on the files it scopes to. The rest are
read by a person, which is the honest description of a prose rule.

## The vocabulary

One concept, one name. The "do not call it" column is the working half: most
of these words are confusable with a neighbour, and the confusion is what the
entry exists to stop.

| Term | What it is | Do not call it |
|---|---|---|
| **source** | one book or paper, a folder under `sources/` | document, book, deck |
| **document** | one PDF inside a source. An item routinely carries a paper and its preprint | source, file |
| **unit** | a located region of a source: document, page, bbox, section, label. Geometry, never an image file | item, region, equation, annotation |
| **locator** | where a unit is. Carries the document, so re-filing never renames a unit | position, coordinates |
| **ledger** | `sources/<name>/units.jsonl`, the units and their triage state | database, index, store |
| **crop** | an image of a unit's box, rendered from the document on demand | asset, thumbnail |
| **card** | a markdown file in `cards/` with `## front` and `## back` | note |
| **note** | what a card becomes *in Anki*. Anki's word, used only about Anki | card |
| **mark** | one Zotero annotation as the reader made it: kind, colour, covered text, comment, box | highlight (one kind of mark), annotation |
| **scheme** | what each `kind/colour` pair means, declared in `[zotero.meanings]` | legend, palette, mapping |
| **annotation** | a `@claude` or `@me` line in `## notes`. Blocks sync wherever it sits | note, comment, mark |
| **brief** | the `@claude` annotation on a unit: the only instruction `/extract-cards` gets | note, prompt |
| **gist** | a few words naming what something is about. On a unit, what a card from it would be about; on a card, what the card is. Read as a caption, never as instructions | summary, description, title |
| **suggestion** | a state `classify` proposed. Never applied on its own | decision, skip |
| **triage** | the unit stage. Is this worth a card, and roughly about what | review, sorting |
| **review** | the card stage. Is the content right | triage, checking |
| **demotion** | why an approval is not holding: `edited` or `annotated`. The file still says `approved` | un-approval, rejection |

### Banned and dangerous words

- **"note" on its own — dangerous.** Three objects answer to it: an Anki note,
  a `@claude`/`@me` annotation, and a Zotero sticky note (one kind of mark).
  Say which.
- **"annotation" on its own — dangerous.** It is a `## notes` line here and a
  Zotero mark in the Zotero literature, and both appear on the same screen.
  Use **mark** for the reader's, **annotation** for ours.
- **"knob", "what this buys", "escape hatch", "this is structural" — banned.**
  Mechanism metaphors and empty emphasis. Name the thing being changed and
  state what changes.
- **"just" and "simply" — banned.** They assert the reader's experience.

## Changed from the source, and why

- **Rule 4 is scoped rather than global.** The original applies it to every
  repo file. Here the failure is specific and so is the scope: an agent about
  to write LaTeX reads `.claude/**` and `conventions.md`, and copies the
  notation it finds. Nothing reads `sources/*/README.md`, which is an errata
  record for a person, so its Unicode maths stays.
- **Rule 2 keeps the dash as a separator.** The original bans the character
  outright, which suits continuous prose. Half this project's text is
  interface labels, where `green — 12 units` is a dash doing its job.
- **Rule 9 arrived as a calibration rather than a cleanup.** Fifty-six
  contrasts were measured across the docs, and nearly all of them name an
  alternative that was really considered. The rule is what says which to keep.

## Dropped from the source

- **"Don't add artificial line breaks."** Every markdown file and docstring
  here is hard-wrapped at 79 columns, and rewrapping them would produce one
  enormous diff and no reader benefit. A wrap width is a project convention,
  not a portable rule.
- **Environment discipline** (definition / lemma / remark / problem). LaTeX
  environments, with no analogue here. Its principle survives as rule 13: the
  statement and the reasoning behind it live apart, and the short one may not
  outclaim the long one.
- **The scope header, the note discipline, and the mathematical vocabulary.**
  Those belong to a paper about one result. The corresponding thing here is a
  source's own `conventions.md`, which is per source by design.
