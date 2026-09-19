"""The one prose rule a test can hold: maths is LaTeX where it will be copied.

docs/STYLE.md rule 4. Everything else in that file is read by a person, which
is the honest description of a prose rule.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Characters that only appear in maths. `x` for dimensions and `->` for arrows
# are ordinary prose and are deliberately absent: the rule is about notation a
# card writer might copy into a `$...$`, not about every non-ASCII glyph.
#
# By codepoint, not by glyph. Spelling them out would fill the one file that
# forbids these characters with the characters, and ruff flags several of them
# as confusable with Latin letters, which is true and is half of why they do
# not belong in a card.
MATHS_RANGES = (
    (0x2202, 0x2202),  # partial
    (0x221A, 0x221A),  # root
    (0x2211, 0x222B),  # sum through integral
    (0x2264, 0x2266),  # <=, >=, and their kin
    (0x2260, 0x2262),  # !=, equivalences
    (0x207A, 0x207F),  # superscript signs, digits, parentheses
    # The transpose marks sit in Phonetic Extensions rather than with the other
    # superscripts, which is how two of them survived the first run of this.
    (0x1D2C, 0x1D6A),
    (0x00B9, 0x00B9),  # to the one
    (0x00B2, 0x00B3),  # squared, cubed
    (0x2080, 0x209C),  # subscripts
    (0x2102, 0x2124),  # blackboard bold
    (0x0391, 0x03C9),  # Greek
)
MATHS = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in MATHS_RANGES) + "]")

# What a card writer reads immediately before emitting LaTeX. The skill and the
# agents are its instructions; `conventions.md` is handed over by
# `forge context`. An example in the wrong notation, here, is an example that
# gets copied.
READ_BEFORE_WRITING = sorted(
    [*(ROOT / ".claude").rglob("*.md")]
    + [p for p in (ROOT / "projects").glob("*/conventions.md")]
)


@pytest.mark.parametrize(
    "path", READ_BEFORE_WRITING, ids=lambda p: str(p.relative_to(ROOT)).replace("\\", "/")
)
def test_maths_is_latex_where_a_card_writer_will_copy_it(path: Path) -> None:
    """`d tr(AX)/dX = A^T` written in Unicode is the notation a card must not
    carry, sitting in the file the next pass reads for examples. `check` gates
    a card's LaTeX through KaTeX and has nothing to say about a stray Unicode
    partial in the front field, so this is the only gate there is."""
    offenders = [
        f"line {n}: {line.strip()[:70]}"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if MATHS.search(line)
    ]
    assert not offenders, (
        f"{path.name} writes maths in Unicode; use $...$ (STYLE.md rule 4)\n  "
        + "\n  ".join(offenders)
    )


def test_the_rule_names_the_files_it_governs() -> None:
    """A scoped rule with no list of what it scopes to is a rule nobody can
    apply. STYLE.md names both halves, and this is the list."""
    assert READ_BEFORE_WRITING, "no instruction files found; the glob moved"
    style = (ROOT / "docs" / "STYLE.md").read_text(encoding="utf-8")
    assert ".claude/**" in style
    assert "projects/*/conventions.md" in style
