# anki-math-forge: design

---

## 1. Purpose

A small toolbox for turning mathematical source material into good Anki cards, with triage and approval steps that aren't painful.

**First target:** matrix-calculus cards, sourced from *The Matrix Cookbook*. The card format is generic. Nothing in the schema assumes the Cookbook.

**Success criterion:** triaging a hundred extracted units takes a few minutes; a re-run produces zero duplicates; scribbling `@claude this looks wrong` on a card gets it fixed and back into review.

---

## 2. Shape

Cards are **files in a git repo**, and **Claude Code is the generator**. The Python contains no LLM API code.

```
  a PDF or a tex ────→ units extract ──┐
  a marked-up PDF ───→ zotero import ──┤
  a subject, no book ─→ propose ───────┘
                                       │
                                       ▼
                                  units.jsonl ──→ [ triage ] ──→ [Claude Code] ──→ cards/*.md
                                    (ledger)       web app        writes stubs             │
                                                                                           ▼
                                                    check ──→ [ review ] ──→ anki push ──→ Anki
                                                    (lint)     web app         (AnkiConnect)
                                                                  │
                                              @claude annotations ┘ ──→ triage → back to draft
```

**Three doors in, one pipeline after them.** A frontend owes a stable id, a
locator as far as it has one, something scannable, and `state: new`, and
nothing past that, because a unit is a decision and a card is the content
(invariant 9). Everything after the ledger reads a unit without asking which
door it came in by, which is what lets a deck on a subject with no book
behind it use the same triage, the same review and the same push to Anki
(ROADMAP.md 10).

Every command, with its flags, is in [COMMANDS.md](COMMANDS.md). One word reads and two words write ([VERBS.md](VERBS.md)).

---

## 3. Principles

1. **Nothing reaches Anki without human approval.**
2. **Idempotent.** Stable ids everywhere; `units extract` and `anki push` are both safe to re-run.
3. **Files are the source of truth.** The web app is a view over them, never a store. Everything it does is also doable by editing a file.
4. **Checks are mechanical or they don't exist.**
5. **Editing an approved card un-approves it.** Enforced by a content hash.

---

## 4. Extraction

Extraction produces **units**: one equation, its context, a stable locator, and a best-effort transcription.

```json
{
  "id": "matrix-cookbook:2.4:61",
  "locator": {"section": "2.4", "equation": 61, "page": 12, "bbox": [x0, y0, x1, y1]},
  "tex_auto": "\\frac{\\partial}{\\partial X}\\log\\det X = X^{-\\top}",
  "tex_source": null,
  "transcription": "ok",
  "context": "surrounding paragraph text",
  "state": "new"
}
```

### First-pass transcription

You need to see the actual mathematics to decide whether a unit is worth carding, so extraction transcribes rather than handing you a wall of crops.

- **If LaTeX source is available**, `tex_source` is populated and it's authoritative. No OCR needed.
- **Otherwise**, `/transcribe` reads the crop into `tex_auto`.
- **Mechanical confidence check**: does the transcription parse under KaTeX strict mode? If not, `transcription: "failed"` and the unit shows the crop only.

**`tex_auto` is a preview, not content.** It exists so you can triage. When Claude Code writes the stub, the crop is the authority and `tex_auto` is a hint. A transcription error must not become a card by inheritance. The units view shows crop and rendered transcription side by side precisely so bad transcriptions are obvious, which also gives you free OCR quality feedback.

### Producing units

1. **LaTeX source**, if it exists: parse equation environments. The locator falls out of the numbering.
2. **PDF:** segment pages, locate equation regions, record each region's bbox, capture surrounding text. Assume math in the text layer is mangled and don't rely on it.
3. **Zotero marks:** each mark you declared worth a card is a unit with its own box (`zotero import`).
4. **A subject:** `/propose` writes units through `units add`, where there is nothing to segment.

### The ledger

`state ∈ {new, queued, skipped, carded}`.

- `new`: extracted, not yet looked at
- `queued`: you decided it's worth a card. This is the work list Claude Code reads.
- `skipped`: decided against, with a reason. **Sticky**, never re-offered.
- `carded`: records the `uid`s produced

Splitting `queued` from `carded` keeps human triage separate from generation. Re-running `units extract` preserves all states and only adds genuinely new units, so processing a book is an incrementally resumable queue rather than a one-shot dump.

### Stubs

Claude Code turns a `queued` unit into a stub: `front`, `back`, `source`, `unit`, nothing else. Augmentation is a separate pass. A stub is a valid card file. `check` passes on it, though it is not good yet.

Extraction accuracy isn't a correctness risk on its own, because every card is `draft` and goes through review. `verify` (§7) is the deeper net for identities where a subtle transcription error would survive a visual check.

---

## 5. Card format

One markdown file per card. YAML frontmatter, sections in the body.

```yaml
---
uid: 7f3a2b
type: identity
status: draft            # draft | approved | rejected
content_hash: a91f...    # set on approval; check fails if content drifts
source: "Matrix Cookbook §2.4, eq. 61"
unit: "matrix-cookbook:2.4:61"
tags: [matrix-calculus, derivatives]
verify: false
---

## front
$\frac{\partial}{\partial X} \log \det X$

## back
$X^{-\top}$

## conditions
$X$ invertible. Denominator layout.

## proof
Jacobi's formula: $d(\log\det X) = \operatorname{tr}(X^{-1}\,dX)$.

## prose
The matrix analogue of $(\log x)' = 1/x$.

## notes
@claude check the transpose against §2.4 — I think this is numerator layout
```

The frontmatter keys are listed in [CLAUDE.md](../CLAUDE.md). `front` and `back` are required; everything else is optional and conditionally rendered in Anki (`{{#Proof}}...{{/Proof}}`), so one note type covers cards with and without proofs or prose.

`type` reaches Anki as a `type::` tag. One note type carries both `identity` and `intuition`.

---

## 6. The companion app

`forge serve` is FastAPI and KaTeX, local only. Five views over the same files: two before you triage anything, and three over the deck.

### The shelf (`/projects`)

Where the app opens. Every project as a card with two bars on it, units and cards, so "which one do I work on next" is answered by looking rather than by opening each in turn. Filter by tag; two tags narrow, because a project's tags are facets of one thing.

The one screen that is not about a project, so it carries none of the row that is: no project name, no setup link, no canvas, no settings. It starts a project, which is the other thing you come here to do.

### Setup stage (`/setup`)

What a project is before it has units: what it reads, what you asked for, and which asks have outline entries with nothing behind them yet. Three columns you can drag: the commands to copy, the list of topics and sources, and the panel for whichever one you picked.

The inbox is here too: facts and corrections you type in, in two lists, unsorted and sorted. `/sort-notes` places each one (ROADMAP.md 20).

A source's panel is where the per-document settings live, each with where it was settled, because "40 points" and "40 points, because nobody said otherwise" are different answers. For a source that came from Zotero it is also where the marking scheme is edited: what each colour means, and which marks make units.

### Units view (`/units`)

Fast triage. One unit at a time: the crop, the rendered transcription beside it, the surrounding context, the locator.

- `q` queue · `s` skip · `S` skip with a one-word reason, stored in the ledger · `n` annotate · `j`/`k` navigate
- filter by state and by section

Designed for flipping through a hundred units in a few minutes. Everything is a single keystroke and nothing requires reading raw LaTeX.

### Review view (`/review`)

Card approval. Rendered exactly as it will appear in Anki (front, back, conditions, proof, prose), plus source ref, link back to the originating unit's crop, and check results.

- `a` approve · `r` reject · `e` open in `$EDITOR` · `E` edit the card in the page · `/` find a card · `n` annotate · `j`/`k` navigate
- approve writes `status` and `content_hash` back to the file

The crop link matters: when a card looks off, the fastest resolution is comparing it against the original page image.

### Graph view (`/graph`)

The `requires` of one project, on a canvas you arrange by hand. The review view answers what the card in front of you rests on; this answers which results everything rests on, and whether a chapter recorded any dependencies at all. Reached from the button in the top bar, on every view that is about one project.

- every box has a dot on each side. **Drag from a dot to another card** to connect them, and which dot you grabbed decides which card ends up with the `requires` line
- `click` selects a box or an arrow · `double-click` opens the card · `del` removes what is selected
- `drag` a box to arrange it, `drag` the background to pan
- `+` puts a card with no dependencies on the canvas · `x` puts a box back · `z` undo · `f` every card · `0` recentre
- the arrangement is written to `projects/<name>/graph.json`, a plain file you can diff

An arrow runs dot to dot, out of the prerequisite's right port and into the dependent's left port, so the line you drew is the line you get. Dropping one on empty space opens the card picker and connects whatever you choose, because the card you meant may have no arrow yet, and a card with none is not drawn.

Writing an arrow writes `requires` into the card that needs the other, which is a write to a card file and is checked like one: refused before the write for a self-reference, an unknown uid, or a cycle, with the loop named. `requires` sits outside `content_hash`, so linking two approved cards demotes neither.

The default picture is the part of the deck that has edges, and the count it left out is on screen beside the toggle. A card with no dependency either way is drawn once it has a position, which is what `+` writes: being on the canvas is a position in `graph.json`, not a change to the card.

`[app] graph = false` turns the whole view off. `requires` still decides the order Anki introduces cards in.

### Running commands

The rail lists the commands that apply to what is on screen. The ones with no model behind them run from the page, in the background, and the runs window keeps their history in `.forge/`. The ones that need Claude give the line to paste into Claude Code.

### Annotations

Available from both triage and review via `n`, and **equally available by editing a file directly**. The app is one entry point, not the entry point. An annotation written in the browser lands in the card's `## notes` section, byte-identical to one you'd type by hand.

### State handling

The app holds no state about cards or units. A parsed file is kept only until it changes on disk. On write, compare mtime against load time and refuse if the file changed underneath. Run history and the record of what changed on each card live in `.forge/`, which is not in git and which nothing else depends on. You'll have an editor open alongside this, and silent clobbering is worse than an occasional retry.

---

## 7. Checks

**`check` always runs and blocks `anki push`:**

- required sections present (`front`, `back`)
- LaTeX parses (KaTeX, strict)
- `uid` present, well-formed, unique
- section whitelist for the declared `type`
- rendered `front` under a character cap
- no open annotations (`@claude` or `@me`) on cards headed for Anki
- `content_hash` matches when `status: approved`
- no `uid` collision with the live collection (with `check --anki`)

Some findings only warn and do not block: prose over the cap, a section that wraps across lines (each wrap is a `<br>` on the card), a numeric `uid`.

**`verify` is opt-in per card:**

Sample random conforming matrices, evaluate both sides (or compare a closed-form gradient against autodiff), assert agreement. Default off. Worth enabling on the gnarly ones (Woodbury, block inverses), where a stray transpose survives proofreading and then gets memorized confidently. Executable forms live in a `## verify` section, out of the way of cards that don't use it.

---

## 8. Annotations

`## notes` is a scratchpad that **never reaches Anki**. Lines starting `@claude` are open requests.

- `anki push` **refuses** any card with an open annotation, regardless of status. "Not ready" should be mechanical, not remembered.
- `todo` lists them for Claude Code.
- Resolving means replacing the line with a `resolved:` record and making the edit. Git holds the history for the Cookbook; `forge cards --changes` records what moved between review decisions for the rest.
- The edit no longer matches `content_hash`, so the card counts as a draft and re-enters review automatically.

Not only for fixes: `@claude add a proof sketch`, `@claude split this into two cards`, `@claude this duplicates 4b2e1c` all work. The `content_hash` rule is what stops annotation-driven edits from silently bypassing review.

---

## 9. Pushing to Anki

AnkiConnect on localhost. Note type created once via `createModel`, versioned in the repo with a version suffix in the name.

`uid` is a real field, not a tag, and `anki push` queries it for add-vs-update. Tags assigned mechanically from frontmatter plus a `src::` tag from the unit id, so a bad batch can be suspended wholesale. `## notes` and `## verify` never reach any field.

---

## 10. Claude Code's role

**`CLAUDE.md`**: always loaded, kept short. Repo invariants, card format, the un-approval rule.

**`.claude/skills/card-writing/SKILL.md`**: loaded on demand. The craft: what makes a cardable unit, how to phrase a `front` so it admits one answer, when a proof section earns its place, length expectations. Worked good/bad examples live here and accumulate as you reject things during review.

**`.claude/commands/`** and **`.claude/agents/`**: one command per pass. `/transcribe`, `/classify`, `/gist`, `/extract-cards`, `/augment` and `/sort-notes` hand each section or dump to a subagent, so the crops stay out of the main context.
- `/transcribe`, `/classify`, `/gist`: read the crops of units
- `/propose`, `/sources`: start from a subject
- `/extract-cards`: read `units --state queued`, write stubs, mark `carded`
- `/augment`: fill conditions, proof, prose and tags on stubs
- `/triage`: work the `todo` list
- `/sort-notes`: place what is waiting in the inbox

---

## 11. Repo and tooling

```
anki-math-forge/
  CLAUDE.md
  docs/
  pyproject.toml
  .claude/
    skills/card-writing/SKILL.md
    commands/                  # one file per pass
    agents/                    # the subagents they hand work to
  cards/                       # source of truth
  projects/matrix-cookbook/
    units.jsonl
    project.toml
  src/anki_math_forge/
    model.py                   # frontmatter + section parsing
    config.py                  # forge.toml and project.toml
    ledger.py                  # units and their states
    extract/                   # tex/pdf segmenters, Zotero import, crops
    app/                       # FastAPI, templates, static
    check.py
    sync.py
    verify.py
    cli.py
  tests/                       # tests/browser drives the app in Chrome
  scripts/                     # affected.py: the tests a change is likely to touch
```

- **uv** for env and deps, lockfile committed
- **ruff** lint + format · **pytest** · **mypy** on `src/` · **pre-commit**
- **GitHub Actions**: lint, types, tests, no network, and `forge check` on the deck

There is no OCR dependency. Transcription is the `/transcribe` skill reading crops, so the core tool installs fast and CI never pulls in a vision stack.

Config in one TOML: deck name, note type version, character cap, Anki URL, source definitions.

---

## 12. Tests

- **Parser round-trip**: file → model → file byte-stable. Everything depends on this.
- **Lint fixtures**: deliberately broken cards, each failing on the right check.
- **Ledger idempotency**: run `units extract` twice, assert states preserved, no duplicates.
- **Transcription gating**: unparseable OCR output flags `transcription: failed` rather than storing garbage.
- **Annotation gating**: card with an open `@claude` is refused by `anki push`.
- **Hash gating**: edit an approved card, assert `check` fails and the card counts as a draft.
- **App writes**: browser-made annotation is byte-identical to a hand-written one; stale-mtime write is refused.
- **`anki push` is idempotent**: mocked AnkiConnect, run twice, no second add.
- **`verify` corruption suite**: flip a transpose or sign, assert rejection.
- **Browser tests** (`tests/browser`, opt in with `uv sync --extra browser`) drive the real pages, because the canvas has no markup to assert against.
- No network in tests; AnkiConnect is mocked.

---

## 13. Build order

M0 to M6 are built, and their order is in git. [ROADMAP.md](ROADMAP.md) lists what is left.

---

## 14. Non-goals

- Card types beyond `identity` and `intuition`.
- Databases, containers, servers, scheduled runs, remote access.
- Near-duplicate detection beyond exact `uid` collision.
- Editing Anki cards this tool didn't create.
- Card content coming back from Anki. It goes files → Anki only; `anki pull` brings back review comments and flags, nothing else.
- Perfect OCR. `tex_auto` is a triage aid; the crop is the authority.

---

## 15. Decisions that were open

1. **Card language**, German or English for prose sections. Set as `[cards] language` in `forge.toml`.
2. **Layout convention**, denominator or numerator. Declared per project, as `[conventions] layout`. Mixing is the failure that quietly poisons the deck.
3. **Cookbook source form.** There is no usable LaTeX, so it goes down the PDF path: `units extract` segments it and `/transcribe` reads the crops.
4. **Tensor backend for `verify`:** numpy with central differences; no torch, no jax.
5. **Deck placement:** `[anki] deck` for the repo, `deck` per project, and `[decks]` to split by type, tag or topic.

---

## 16. Notes for Claude Code

- Boring implementations. This has to stay legible in six months.
- Files are the source of truth. The app is a view; any feature that makes it a store is wrong.
- Extraction produces units, never cards. If it's tempted to write a `front`, it's overstepping.
- `tex_auto` is a hint. When writing a stub from a unit, the crop is authoritative.
- Card content guidelines belong in the skill, not in code. The Python never generates or rewrites card text. A model may write it, reading the skill as it stands and going through the same verbs ([CONTRACT.md](CONTRACT.md) §6).
- When this doc doesn't answer something, make a small call and note it in a comment. Don't block.