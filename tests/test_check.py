"""Lint fixtures: deliberately broken cards, each failing on the right check."""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_forge import check, model
from anki_forge.config import Config

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
