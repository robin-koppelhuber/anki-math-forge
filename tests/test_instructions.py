"""The agent and command instructions must survive a change of source.

This project turns *mathematical source material* into cards, plural. The
instructions are the part most likely to quietly assume the one source that
happens to be loaded -- they are prose, nothing compiles them, and an
assumption reads as fact. Illustrations are welcome; a rule stated in one
source's vocabulary is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = sorted(
    list((ROOT / ".claude" / "agents").glob("*.md"))
    + list((ROOT / ".claude" / "commands").glob("*.md"))
)


@pytest.mark.parametrize("path", INSTRUCTIONS, ids=lambda p: p.name)
def test_no_source_is_named(path: Path) -> None:
    """A source name in an instruction is a default nobody chose.

    `--section 2.4 of matrix-cookbook` in an example becomes the section a
    future pass runs against a different book.
    """
    text = path.read_text(encoding="utf-8")
    for name in (d.name for d in (ROOT / "sources").iterdir() if d.is_dir()):
        assert name not in text, f"{path.name} names the source {name!r}; use <source>"


@pytest.mark.parametrize("path", INSTRUCTIONS, ids=lambda p: p.name)
def test_no_bare_equation_or_section_numbers(path: Path) -> None:
    """Numbers from one document are the clearest overfitting there is."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"DESIGN\.md §\d+", "", text)  # our own design doc, not a source
    offenders = re.findall(r"(?:\beq\.? \d+|\bequation \d+|§\d+(?:\.\d+)*)", text)
    assert not offenders, f"{path.name} cites {offenders}; describe the case instead"


@pytest.mark.parametrize("path", INSTRUCTIONS, ids=lambda p: p.name)
def test_no_control_characters(path: Path) -> None:
    """`\frac` and `\text` in a shell-written file lose their escapes.

    A `\f` became a form feed and a `\t` a tab in the card-writing skill,
    silently, and the instruction it broke was one about LaTeX.
    """
    raw = path.read_bytes()
    bad = sorted({b for b in raw if b < 32 and b not in (10, 13)})
    assert not bad, f"{path.name} contains control bytes {bad}"


def test_the_skill_says_its_examples_are_examples() -> None:
    """The skill keeps its illustrations, so it has to say they are illustrations."""
    skill = (ROOT / ".claude" / "skills" / "card-writing" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "A note on the examples" in skill
    raw = (ROOT / ".claude" / "skills" / "card-writing" / "SKILL.md").read_bytes()
    assert not [b for b in raw if b < 32 and b not in (10, 13)], "control bytes in the skill"


def test_the_project_contract_declares_no_source_conventions() -> None:
    """CLAUDE.md must not hold values that belong to one source.

    It said "denominator layout", "entries are real", "in a derivative every
    other symbol is constant" -- all true of one book, none true of the tool.
    A second source would have made the contract silently wrong, and card
    writers were told to read it as authoritative.
    """
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = text[text.index("## Conventions") : text.index("## Commands")]
    for claim in ("denominator layout", "entries are real", "conjugate transpose"):
        assert claim not in section.lower().replace("**", ""), (
            f"CLAUDE.md still declares {claim!r}; that belongs in "
            "sources/<name>/conventions.md"
        )
    assert "sources/<name>/conventions.md" in section, "it must say where they do live"


def test_the_loaded_source_declares_its_own() -> None:
    """And the mechanism is only real if the current source actually uses it."""
    for source in (ROOT / "sources").iterdir():
        if not source.is_dir() or not (source / "units.jsonl").exists():
            continue
        conventions = source / "conventions.md"
        assert conventions.exists(), (
            f"{source.name} has units but no conventions.md; every card written "
            "from it is guessing at what is ambient"
        )


# The bytes a halved backslash turns into. TAB is legal in Markdown tables and
# in JS, so it is not in the list; the rest never are.
MANGLED = {8: "backspace", 11: "vertical tab", 12: "formfeed"}


def test_no_control_bytes_anywhere_in_the_repo() -> None:
    """The Bash tool halves runs of backslashes, so a LaTeX or regex escape
    can arrive as a control byte. It is silent: KaTeX accepts the result, and
    a regex simply stops matching. This has now bitten in a card, in the
    skill, and twice in Python source, so the check covers all of them."""
    suffixes = {".py", ".md", ".html", ".js", ".css", ".toml"}
    bad: list[str] = []
    for name in ("src", "tests", "cards", ".claude", "sources"):
        base = ROOT / name
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            if "__pycache__" in path.parts:
                continue
            if path.name == "text.md":
                # The extracted PDF text layer. Its formfeeds are the book's
                # own page breaks, and it is generated and gitignored.
                continue
            raw = path.read_bytes()
            for byte, what in MANGLED.items():
                if bytes([byte]) in raw:
                    where = raw[: raw.index(bytes([byte]))].count(b"\n") + 1
                    bad.append(f"{path.relative_to(ROOT)}:{where} has a {what}")
            other = {b for b in raw if b < 32 and b not in (9, 10, 13)} - set(MANGLED)
            if other:
                bad.append(f"{path.relative_to(ROOT)} has control bytes {sorted(other)}")
    assert not bad, "; ".join(bad)
