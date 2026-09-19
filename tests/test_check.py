"""Lint fixtures: deliberately broken cards, each failing on the right check."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import check, model
from anki_math_forge.config import Config

HEAD = """---
uid: {uid}
type: {type}
status: {status}
source: Demo
unit: "demo:1:1"
tags: []
verify: {verify}
---
"""


def write(
    repo: Path,
    body: str,
    *,
    uid: str = "aa11bb",
    type: str = "identity",
    status: str = "draft",
    verify: str = "false",
    name: str = "card.md",
) -> Path:
    path = repo / "cards" / name
    head = HEAD.format(uid=uid, type=type, status=status, verify=verify)
    path.write_text(head + body, encoding="utf-8")
    return path


def codes(findings: list[check.Finding]) -> set[str]:
    return {f.code for f in findings}


def lint(repo: Path, config: Config) -> list[check.Finding]:
    _, findings = check.check_repo(config)
    return findings


BROKEN = [
    ("no front", "\n## back\n$x$\n", {}, "section-missing"),
    ("empty front", "\n## front\n\n## back\n$x$\n", {}, "section-missing"),
    ("bad uid", "\n## front\n$a$\n\n## back\n$b$\n", {"uid": "NOPE"}, "uid-malformed"),
    ("unknown type", "\n## front\n$a$\n\n## back\n$b$\n", {"type": "cloze"}, "type-unknown"),
    ("bad status", "\n## front\n$a$\n\n## back\n$b$\n", {"status": "maybe"}, "status-unknown"),
    (
        "unknown section",
        "\n## front\n$a$\n\n## back\n$b$\n\n## mnemonic\nhm\n",
        {},
        "section-unknown",
    ),
    (
        "duplicate section",
        "\n## front\n$a$\n\n## back\n$b$\n\n## back\n$c$\n",
        {},
        "section-duplicate",
    ),
    ("unbalanced braces", "\n## front\n$\\frac{a}{b$\n\n## back\n$b$\n", {}, "latex-parse"),
    ("unknown macro", "\n## front\n$\\bogusmacro{x}$\n\n## back\n$b$\n", {}, "latex-parse"),
    ("stray dollar", "\n## front\n$a$ and $b\n\n## back\n$c$\n", {}, "latex-dollars"),
    (
        "unclosed environment",
        "\n## front\n$\\begin{pmatrix} a & b$\n\n## back\n$c$\n",
        {},
        "latex-parse",
    ),
    (
        "front too long",
        "\n## front\n" + ("a very long prompt that goes on and on " * 6) + "\n\n## back\n$b$\n",
        {},
        "front-too-long",
    ),
    (
        "verify without section",
        "\n## front\n$a$\n\n## back\n$b$\n",
        {"verify": "true"},
        "verify-missing",
    ),
    (
        "approved without hash",
        "\n## front\n$a$\n\n## back\n$b$\n",
        {"status": "approved"},
        "hash-missing",
    ),
]


@pytest.mark.parametrize(
    ("label", "body", "overrides", "expected"), BROKEN, ids=[b[0] for b in BROKEN]
)
def test_broken_cards_fail_on_the_right_check(
    repo: Path, config: Config, label: str, body: str, overrides: dict[str, str], expected: str
) -> None:
    write(repo, body, **overrides)
    found = codes(lint(repo, config))
    assert expected in found, f"{label}: expected {expected}, got {found or 'nothing'}"


def test_a_good_card_lints_clean(repo: Path, config: Config, card_path: Path) -> None:
    _, findings = check.check_repo(config)
    assert check.errors(findings) == []


def test_a_stub_lints_clean(repo: Path, config: Config) -> None:
    """A stub is a valid card file -- it is just not good yet (§4)."""
    card = model.stub(uid="abc123", front="$a$", back="$b$", source="Demo", unit="demo:1:1")
    card.save(repo / "cards" / "abc123-stub.md")
    _, findings = check.check_repo(config)
    assert check.errors(findings) == []


def test_duplicate_uids_are_an_error(repo: Path, config: Config) -> None:
    body = "\n## front\n$a$\n\n## back\n$b$\n"
    write(repo, body, name="one.md")
    write(repo, body, name="two.md")
    assert "uid-duplicate" in codes(lint(repo, config))


def test_uid_collision_in_the_live_collection(repo: Path, config: Config, card_path: Path) -> None:
    cards, _ = check.check_repo(config)
    findings = check.check_deck(cards, config, live_uids={"7f3a2b": 2})
    assert "uid-collision" in codes(findings)


# -- hash gating (DESIGN.md §3.5) ------------------------------------------


def test_editing_an_approved_card_fails_the_check(
    repo: Path, config: Config, card_path: Path
) -> None:
    card = model.load(card_path)
    card.approve()
    card.save()
    assert not check.errors(check.check_repo(config)[1])

    text = card_path.read_text(encoding="utf-8").replace(r"$X^{-\top}$", r"$X^{-1}$")
    card_path.write_text(text, encoding="utf-8")

    findings = check.check_repo(config)[1]
    assert "hash-stale" in codes(findings)
    assert check.errors(findings)


def test_resetting_to_draft_clears_the_stale_hash(
    repo: Path, config: Config, card_path: Path
) -> None:
    card = model.load(card_path)
    card.approve()
    card.save()
    card = model.load(card_path)
    card.set_section("back", r"$X^{-1}$")
    card.unapprove()
    card.save()
    assert not check.errors(check.check_repo(config)[1])
    assert model.load(card_path).status == "draft"


# -- annotation gating (DESIGN.md §8) --------------------------------------


def test_an_open_annotation_is_a_warning_on_a_draft(
    repo: Path, config: Config, card_path: Path
) -> None:
    card = model.load(card_path)
    card.add_annotation("check the transpose")
    card.save()
    findings = check.check_repo(config)[1]
    assert "annotation-open" in codes(findings)
    assert not check.errors(findings)


def test_an_open_annotation_is_an_error_for_sync(
    repo: Path, config: Config, card_path: Path
) -> None:
    card = model.load(card_path)
    card.add_annotation("check the transpose")
    card.save()
    findings = check.check_repo(config, for_sync=True)[1]
    assert "annotation-open" in codes(check.errors(findings))


def test_unparseable_files_are_reported_not_raised(repo: Path, config: Config) -> None:
    (repo / "cards" / "junk.md").write_text("no frontmatter here", encoding="utf-8")
    cards, findings = check.check_repo(config)
    assert cards == []
    assert "unparseable" in codes(findings)


def test_an_edited_approval_returns_to_the_review_queue(
    repo: Path, config: Config, card_path: Path
) -> None:
    """§8: resolving an annotation drops the card back to draft *automatically*."""
    card = model.load(card_path)
    card.approve()
    card.save()
    assert model.load(card_path).effective_status == "approved"

    card = model.load(card_path)
    card.set_section("back", r"$X^{-1}$")
    card.save()

    reloaded = model.load(card_path)
    assert reloaded.status == "approved", "the file is untouched; nothing rewrites it silently"
    assert reloaded.effective_status == "draft", "but it counts as a draft again"


def test_a_typo_in_frequency_is_an_error(config: Config) -> None:
    """Optional, but not free-form.

    An unrecognised value would become its own Anki tag and quietly split the
    deck in two -- `freq::core` and `freq::cores` reviewed separately, with
    nothing to notice it.
    """
    card = model.Card(
        frontmatter={
            "uid": "aa11bb",
            "type": "identity",
            "status": "draft",
            "frequency": "cores",
        },
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    codes = {f.code for f in check.check_card(card, config)}
    assert "frequency-unknown" in codes

    card.frontmatter["frequency"] = "core"
    assert "frequency-unknown" not in {f.code for f in check.check_card(card, config)}


def test_both_judgements_are_optional(config: Config) -> None:
    card = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity", "status": "draft"},
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    codes = {f.code for f in check.check_card(card, config)}
    assert "frequency-unknown" not in codes
    assert "derivation-unknown" not in codes


def test_definitional_is_a_derivation_value(config: Config) -> None:
    """Some facts are true by definition; "how hard to derive" does not apply."""
    assert "definitional" in model.DERIVATIONS
    card = model.Card(
        frontmatter={
            "uid": "aa11bb",
            "type": "identity",
            "status": "draft",
            "derivation": "definitional",
        },
        sections=[model.Section("front", "$a$"), model.Section("back", "$b$")],
    )
    assert "derivation-unknown" not in {f.code for f in check.check_card(card, config)}


def test_a_long_uses_line_is_flagged(config: Config) -> None:
    """`uses` is a pointer, not a paragraph.

    The first pass produced one at 246 characters, which is prose wearing the
    wrong section's name -- and on the back of a flashcard nobody reads it.
    """
    card = model.Card(
        frontmatter={"uid": "aa11bb", "type": "identity", "status": "draft"},
        sections=[
            model.Section("front", "$a$"),
            model.Section("back", "$b$"),
            model.Section("uses", "x" * (check.USES_CHAR_CAP + 1)),
        ],
    )
    assert "uses-too-long" in {f.code for f in check.check_card(card, config)}

    card.sections[-1].body = "Backpropagation through a linear layer."
    assert "uses-too-long" not in {f.code for f in check.check_card(card, config)}


# -- a check that cannot fail -----------------------------------------------

DRAWN = (
    "\n## front\n$x$\n\n## back\n$y$\n\n"
    "## verify\n```python\n"
    "X = spd(3)\n"
    "lhs = np.trace(X)\n"
    "rhs = float(np.sum(np.diag(X)))\n"
    "```\n"
)
FIXED = (
    "\n## front\n$x$\n\n## back\n$y$\n\n"
    "## verify\n```python\n"
    "lhs = np.zeros(2)\n"
    "rhs = np.zeros(2)\n"
    "```\n"
)


def test_a_verify_block_that_draws_nothing_is_flagged(repo: Path, config: Config) -> None:
    """Both sides typed from the same expression and evaluated once is a check
    that reports coverage the deck does not have."""
    write(repo, FIXED, verify="true")

    findings = lint(repo, config)

    assert "verify-fixed" in codes(findings)
    said = next(f for f in findings if f.code == "verify-fixed")
    assert said.level == check.WARN, "a closed form checked at one point is legitimate"


def test_a_verify_block_that_samples_is_not(repo: Path, config: Config) -> None:
    write(repo, DRAWN, verify="true")

    assert "verify-fixed" not in codes(lint(repo, config))


def test_a_draw_is_found_by_name_not_by_substring(repo: Path, config: Config) -> None:
    """`spd_cache = 1` draws nothing."""
    body = FIXED.replace("lhs = np.zeros(2)", "spd_cache = 1\nlhs = np.zeros(2)")
    write(repo, body, verify="true")

    assert "verify-fixed" in codes(lint(repo, config))


def test_a_card_without_verify_is_not_asked(repo: Path, config: Config) -> None:
    write(repo, FIXED)

    assert "verify-fixed" not in codes(lint(repo, config))


def test_augmented_has_to_be_a_flag(repo: Path, config: Config) -> None:
    """A string reads as true to Python and as a date to a person."""
    path = write(repo, "\n## front\n$x$\n\n## back\n$y$\n")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "verify: false", 'verify: false\naugmented: "2026-09-18"'
        ),
        encoding="utf-8",
    )

    assert "augmented-not-a-flag" in codes(lint(repo, config))


# -- a newline is only a break where Anki makes one --------------------------


def wrapped(repo: Path, config: Config, proof: str) -> bool:
    """Whether `## proof` written this way is called wrapped prose."""
    write(repo, f"\n## front\n$a$\n\n## back\n$b$\n\n## proof\n{proof}\n")
    return "section-wrapped" in codes(lint(repo, config))


def test_a_proof_written_as_steps_is_not_wrapped_prose(repo: Path, config: Config) -> None:
    """One display block per line is what the card-writing skill asks a proof
    to look like. `to_anki_html` turns a newline into a `<br>` outside maths
    only, so none of these breaks reaches the card as one -- and a lint firing
    on the recommended shape is a lint you learn to scroll past."""
    assert not wrapped(repo, config, "$$a = b$$\n$$= c$$")


def test_an_aligned_environment_is_one_formula(repo: Path, config: Config) -> None:
    """Four lines of one display block. The whitespace inside it is collapsed
    on the way to Anki, which is why `\\\\` and not a newline is what breaks
    a line there."""
    assert not wrapped(
        repo,
        config,
        "$$\\begin{aligned}\na &= b \\\\\n  &= c\n\\end{aligned}$$",
    )


def test_a_clause_above_a_step_is_a_deliberate_break(repo: Path, config: Config) -> None:
    """Prose belongs around the steps: one line naming the move, the move
    under it."""
    assert not wrapped(repo, config, "By the cyclic property,\n$$a = b$$")


def test_a_sentence_split_across_lines_still_is(repo: Path, config: Config) -> None:
    """Which is the case the check exists for, and the one shape the skill
    tells you not to write a proof in."""
    assert wrapped(
        repo,
        config,
        "$\\det(\\mathbf{X})$ and Jacobi's formula\nread together give the result.",
    )


def test_maths_wrapped_inside_one_inline_span_is_not_a_wrapped_sentence(
    repo: Path, config: Config
) -> None:
    assert not wrapped(repo, config, "$a +\nb$")
