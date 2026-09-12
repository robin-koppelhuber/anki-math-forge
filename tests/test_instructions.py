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
    # The skill was excluded, which is how "as exactly `Denominator layout.`"
    # survived: a rule about one book, in the file that tells a card writer
    # what the rules are.
    + list((ROOT / ".claude" / "skills").rglob("*.md"))
)

# What a *user* is shown. The guide taught that a unit is an equation with a
# number, which is true of one source out of three.
SURFACES = sorted((ROOT / "src" / "anki_math_forge" / "app" / "templates").glob("*.html"))

# Facts about matrix calculus, not about this tool. Stated as a rule rather
# than shown as an example, any of these is the deck-poisoning failure
# CLAUDE.md names, arriving through an instruction.
CONVENTIONS = ("denominator layout", "numerator layout", "entries are real")


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
def test_no_convention_is_mandated(path: Path) -> None:
    """An instruction may *illustrate* a convention; it may not require one.

    "as exactly `Denominator layout.`" made every card from every source claim
    a matrix-calculus convention, whatever the source had declared. The
    difference is a rule versus an example, so this checks the imperative
    forms rather than the words themselves.
    """
    text = path.read_text(encoding="utf-8").lower()
    for convention in CONVENTIONS:
        for lead in ("as exactly `", "always say ", "must say ", "say the "):
            assert lead + convention not in text, (
                f"{path.name} mandates {convention!r}; the source declares it, "
                "so name whatever `forge context` prints"
            )


@pytest.mark.parametrize("path", SURFACES, ids=lambda p: p.name)
def test_no_surface_claims_every_unit_is_an_equation(path: Path) -> None:
    """Two of three sources have no equations and no numbers.

    The guide said "the equation number is the book's own, and it is what makes
    this unit's id stable" -- which is the opposite of true for a unit imported
    from a marked-up PDF, where the id is the annotation key.
    """
    text = path.read_text(encoding="utf-8").lower()
    for claim in ("an equation in the book", "the equation number is the book's own"):
        assert claim not in text, f"{path.name} says {claim!r}, true of one source in three"


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
            f"CLAUDE.md still declares {claim!r}; that belongs with the source"
        )
    assert "conventions.md" in section, "it must say where they do live"


def test_every_source_that_has_produced_cards_declares_its_conventions() -> None:
    """The mechanism is only real if the sources actually use it.

    Gated on **cards**, not units: a source with fifteen untriaged units has
    not written anything yet, and demanding a conventions file before you have
    read the paper is how you end up with a placeholder that says nothing and
    silences `forge context` for ever. An absent file is the honest state
    until there is something to record.
    """
    carded = {
        path.parent.name for path in (ROOT / "cards").glob("*/*.md")
    }
    for source in (ROOT / "sources").iterdir():
        if not source.is_dir() or source.name not in carded:
            continue
        # `conventions.md` is where they live; the prose half of an unmigrated
        # `source.md` is still read.
        assert (source / "conventions.md").exists() or (source / "source.md").exists(), (
            f"{source.name} has cards but declares no conventions; every one of "
            "them was written guessing at what is ambient"
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
