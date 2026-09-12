# anki-forge — Design Doc (MVP, v4)

**Status:** Draft
**Changes from v3:** extraction now produces a best-effort math transcription so units are scannable at a glance; units gain a `queued` state so human triage is separate from carding; the review page grows into a local companion app with a units view and a review view, with annotations available in both.

---

## 1. Purpose

A small toolbox for turning mathematical source material into good Anki cards, with triage and approval steps that aren't painful.

**MVP target:** matrix-calculus cards, sourced from *The Matrix Cookbook*. The card format is generic — nothing in the schema assumes the Cookbook.

**Success criterion:** ~50 reviewed cards in Anki; triaging a hundred extracted units takes a few minutes; a re-run produces zero duplicates; scribbling `@claude this looks wrong` on a card gets it fixed and back into review.

---

## 2. Shape

Cards are **files in a git repo**, and **Claude Code is the generator**. The Python contains no LLM API code.

```
  source PDF/tex
        │
        ▼
   extract ──→ units.jsonl ──→ [ triage ] ──→ [Claude Code] ──→ cards/*.md
   + transcribe   (ledger)      web app        writes stubs        │
                                                                   ▼
                                          check ──→ [ review ] ──→ sync ──→ Anki
                                          (lint)     web app      (AnkiConnect)
                                                        │
                                    @claude annotations ┘ ──→ triage → back to draft
```

Python verbs:

| Verb | Does |
|---|---|
| `extract` | Segments a source into units, attempts a first-pass transcription, updates the ledger. Never writes cards. |
| `serve` | The companion app: units triage + card review + annotations. |
| `units` | CLI view of the ledger, for scripting and for Claude Code. |
| `check` | Lints card files. Structural only. |
| `todo` | Lists cards with open `@claude` annotations. |
| `sync` | Pushes approved cards to Anki, upserting by `uid`. |
| `verify` | Opt-in numeric check (§7). |

---

## 3. Principles

1. **Nothing reaches Anki without human approval.**
2. **Idempotent.** Stable ids everywhere; `extract` and `sync` are both safe to re-run.
3. **Files are the source of truth.** The web app is a view over them, never a store. Everything it does is also doable by editing a file.
4. **Checks are mechanical or they don't exist.**
5. **Editing an approved card un-approves it.** Enforced by a content hash.

---

## 4. Extraction

Extraction produces **units**: one equation, its context, a stable locator, and a best-effort transcription.

```json
{
  "id": "matrix-cookbook:2.4:61",
  "locator": {"section": "2.4", "equation": 61, "page": 12},
  "image": "assets/eq_061.png",
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
- **Otherwise**, run math OCR (Pix2Text) over the crop into `tex_auto`.
- **Mechanical confidence check**: does the transcription parse under KaTeX strict mode? If not, `transcription: "failed"` and the unit shows the crop only.

**`tex_auto` is a preview, not content.** It exists so you can triage. When Claude Code writes the stub, the crop is the authority and `tex_auto` is a hint — an OCR error must not become a card by inheritance. The units view shows crop and rendered transcription side by side precisely so bad transcriptions are obvious, which also gives you free OCR quality feedback.

### Producing units

1. **LaTeX source**, if it exists — parse equation environments; the locator falls out of the numbering.
2. **PDF** — segment pages, locate equation regions, crop to PNG, capture surrounding text. Assume math in the text layer is mangled and don't rely on it.

### The ledger

`state ∈ {new, queued, skipped, carded}`.

- `new` — extracted, not yet looked at
- `queued` — you decided it's worth a card; this is the work list Claude Code reads
- `skipped` — decided against, with a reason; **sticky**, never re-offered
- `carded` — records the `uid`s produced

Splitting `queued` from `carded` keeps human triage separate from generation. Re-running `extract` preserves all states and only adds genuinely new units, so processing a book is an incrementally resumable queue rather than a one-shot dump.

### Stubs

Claude Code turns a `queued` unit into a stub: `front`, `back`, `source`, `unit`, nothing else. Augmentation is a separate pass. A stub is a valid card file — `check` passes on it, it's just not good yet.

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

`front` and `back` required; everything else optional and conditionally rendered in Anki (`{{#Proof}}...{{/Proof}}`), so one note type covers cards with and without proofs or prose.

`type` selects the note type — which fields exist, which cards a note generates. MVP ships `identity` only.

---

## 6. The companion app

`forge serve` — FastAPI, KaTeX, local only. Three views over the same files.

### Units view (`/units`)

Fast triage. One unit at a time: the crop, the rendered transcription beside it, the surrounding context, the locator.

- `q` queue · `s` skip · `n` annotate · `j`/`k` navigate
- filter by state and by section
- skip prompts for a one-word reason, stored in the ledger

Designed for flipping through a hundred units in a few minutes. Everything is a single keystroke and nothing requires reading raw LaTeX.

### Review view (`/review`)

Card approval. Rendered exactly as it will appear in Anki — front, back, conditions, proof, prose — plus source ref, link back to the originating unit's crop, and check results.

- `a` approve · `r` reject · `e` open in `$EDITOR` · `n` annotate · `j`/`k` navigate
- approve writes `status` and `content_hash` back to the file

The crop link matters: when a card looks off, the fastest resolution is comparing it against the original page image.

### Graph view (`/graph`)

The `requires` of one source, on a canvas you arrange by hand. The review view answers what the card in front of you rests on; this answers which results everything rests on, and whether a chapter recorded any dependencies at all.

- `drag a dot` on the left or right of a box to connect two cards, `drag` a box to arrange it, `drag` the background to pan
- `click` a box opens the card, `click` an arrow selects it, `del` removes it
- `n` puts a card with no dependencies on the canvas · `x` takes one off · `z` undo · `a` every card · `0` recentres
- the arrangement is written to `sources/<name>/graph.json`, committed and diffable

An arrow writes `requires` into the card that needs the other, which is a write to a card file and is checked like one: refused before the write for a self-reference, an unknown uid, or a cycle, with the loop named. `requires` sits outside `content_hash` under both the current rule and the legacy one, so linking two approved cards demotes neither.

The default picture is the part of the deck that has edges, and the count it left out is on screen beside the toggle. A card with no dependency either way is drawn once it has a position, which is what `n` writes: being on the canvas is a position in `graph.json`, not a change to the card.

`[app] graph = false` turns the whole view off. `requires` still decides the order Anki introduces cards in.

### Annotations

Available from both triage and review via `n`, and **equally available by editing a file directly** — the app is one entry point, not the entry point. An annotation written in the browser lands in the card's `## notes` section, byte-identical to one you'd type by hand.

### State handling

The app holds no state. Re-read from disk on every request, no caching. On write, compare mtime against load time and refuse if the file changed underneath — you'll have an editor open alongside this, and silent clobbering is worse than an occasional retry.

---

## 7. Checks

**`check` — always runs, blocks sync:**

- required sections present (`front`, `back`)
- LaTeX parses (KaTeX, strict)
- `uid` present, well-formed, unique
- section whitelist for the declared `type`
- rendered `front` under a character cap
- no open `@claude` annotations on cards headed for sync
- `content_hash` matches when `status: approved`
- no `uid` collision with the live collection

**`verify` — opt-in per card:**

Sample random conforming matrices, evaluate both sides (or compare a closed-form gradient against autodiff), assert agreement. Default off. Worth enabling on the gnarly ones — Woodbury, block inverses — where a stray transpose survives proofreading and then gets memorized confidently. Executable forms live in a `## verify` section, out of the way of cards that don't use it.

---

## 8. Annotations

`## notes` is a scratchpad that **never syncs to Anki**. Lines starting `@claude` are open requests.

- `sync` **refuses** any card with an open annotation, regardless of status. "Not ready" should be mechanical, not remembered.
- `todo` lists them for Claude Code.
- Resolving means deleting the line and making the edit. Git holds the history.
- The edit changes `content_hash`, so the card drops back to `draft` and re-enters review automatically.

Not just for fixes: `@claude add a proof sketch`, `@claude split this into two cards`, `@claude this duplicates 4b2e1c` all work. The `content_hash` rule is what stops annotation-driven edits from silently bypassing review.

---

## 9. Sync

AnkiConnect on localhost. Note type created once via `createModel`, versioned in the repo with a version suffix in the name.

`uid` is a real field, not a tag — `sync` queries it for add-vs-update. Tags assigned mechanically from frontmatter plus a `src::` tag from `source`, so a bad batch can be suspended wholesale. `## notes` and `## verify` never reach any field.

---

## 10. Claude Code's role

**`CLAUDE.md`** — always loaded, keep it short. Repo invariants, card format, declared layout convention, the un-approval rule.

**`.claude/skills/card-writing/SKILL.md`** — loaded on demand. The craft: what makes a cardable unit, how to phrase a `front` so it admits one answer, when a proof section earns its place, length expectations. Worked good/bad examples live here and accumulate as you reject things during review.

**`.claude/commands/`**
- `/extract-cards` — read `units --status queued`, write stubs, mark `carded`
- `/augment` — fill conditions/proof/prose/tags on stubs
- `/triage` — work the `todo` list

---

## 11. Repo and tooling

```
anki-forge/
  CLAUDE.md
  DESIGN.md
  pyproject.toml
  .claude/
    skills/card-writing/SKILL.md
    commands/{extract-cards,augment,triage}.md
  cards/                       # source of truth
  sources/matrix-cookbook/
    units.jsonl
    assets/
  src/anki_math_forge/
    model.py                   # frontmatter + section parsing
    extract/                   # tex/pdf segmenters, transcription, ledger
    app/                       # FastAPI, templates, static
    check.py
    sync.py
    verify.py
    cli.py
  tests/
```

- **uv** for env and deps, lockfile committed
- **ruff** lint + format · **pytest** · **mypy** on `src/` · **pre-commit**
- **GitHub Actions**: lint, types, tests, no network

Pin the OCR dependency and keep it optional — `uv sync --extra ocr` — so the core tool installs fast and CI doesn't drag a vision stack around.

Config in one TOML: deck name, note type version, character cap, Anki URL, source definitions.

---

## 12. Tests

- **Parser round-trip**: file → model → file byte-stable. Everything depends on this.
- **Lint fixtures**: deliberately broken cards, each failing on the right check.
- **Ledger idempotency**: run `extract` twice, assert states preserved, no duplicates.
- **Transcription gating**: unparseable OCR output flags `transcription: failed` rather than storing garbage.
- **Annotation gating**: card with an open `@claude` is refused by `sync`.
- **Hash gating**: edit an approved card, assert `check` fails and status resets.
- **App writes**: browser-made annotation is byte-identical to a hand-written one; stale-mtime write is refused.
- **Sync idempotency**: mocked AnkiConnect, run twice, no second add.
- **`verify` corruption suite**: flip a transpose or sign, assert rejection.
- No network in tests; AnkiConnect and OCR both mocked.

---

## 13. Build order

| M | Deliverable | Done when |
|---|---|---|
| **M0** | Skeleton + card parser + `check` | Hand-written card lints clean; broken fixtures fail correctly |
| **M1** | `sync` + note type | 3 hand-written cards land in Anki; re-run adds nothing |
| **M2** | App: review view + annotations + `todo` | Full manual loop: write, review, annotate, triage, re-review |
| **M3** | `extract` + transcription + ledger | Cookbook segmented; units carry readable math |
| **M4** | App: units view | Triage a hundred units in a few minutes |
| **M5** | `CLAUDE.md`, skill, commands + first batch | ~50 cards queued, stubbed, augmented, reviewed, synced |
| **M6** | `verify` (opt-in) | Corrupted identities rejected on cards that opt in |

Keep this order. M0–M2 is testable with hand-written cards, and if the review loop is wrong you want to know before there are three hundred stubs in the repo.

---

## 14. Non-goals

- Card types beyond `identity`.
- Databases, containers, servers, scheduled runs, remote access.
- Near-duplicate detection beyond exact `uid` collision.
- Editing Anki cards this tool didn't create.
- Two-way sync. Files → Anki only.
- Perfect OCR. `tex_auto` is a triage aid; the crop is the authority.

---

## 15. Open decisions

1. **Card language** — German or English for prose sections. Note it in `CLAUDE.md`.
2. **Layout convention** — denominator or numerator. Declare once; mixing is the failure that quietly poisons the deck.
3. **Cookbook source form** — whether usable LaTeX exists, or extraction goes down the PDF+OCR path. Determines what M3 costs.
4. **Tensor backend for `verify`** — torch or jax. Only matters at M6.
5. **Deck placement** — decide before the first sync.

---

## 16. Notes for Claude Code

- Boring implementations. This has to stay legible in six months.
- Files are the source of truth. The app is a view; any feature that makes it a store is wrong.
- Extraction produces units, never cards. If it's tempted to write a `front`, it's overstepping.
- `tex_auto` is a hint. When writing a stub from a unit, the crop is authoritative.
- Card content guidelines belong in the skill, not in code. The Python never generates or rewrites card text.
- When this doc doesn't answer something, make a small call and note it in a comment. Don't block.