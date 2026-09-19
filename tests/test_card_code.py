"""Code on a card.

Everything that reads a card body assumed it was prose with maths in it.
Code is neither: it is full of braces, backslashes and `$`, so KaTeX refuses
it; it is written one statement per line on purpose, so a line-counting lint
fires on exactly the right shape; and its newlines are what make it
readable, so turning them into `<br>` destroys it.

One regex decides where a fence starts and stops, shared by `check`, `sync`
and the review view, because three answers to that question is three
different cards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anki_math_forge import check as check_mod
from anki_math_forge import model
from anki_math_forge.config import Config
from anki_math_forge.sync import to_anki_html

SNIPPET = (
    "```cpp\n"
    "auto it = std::remove(v.begin(), v.end(), x);\n"
    "v.erase(it, v.end());\n"
    "```"
)


def a_card(path: Path, back: str, front: str = "$a$") -> model.Card:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: aa11bb\ntype: identity\nstatus: draft\n"
        'source: "Modern C++"\nunit: "cpp:erase-remove"\n---\n\n'
        f"## front\n\n{front}\n\n## back\n\n{back}\n",
        encoding="utf-8",
    )
    return model.load(path)


def codes(card: model.Card, config: Config) -> set[str]:
    return {f.code for f in check_mod.check_card(card, config)}


# -- check ------------------------------------------------------------------


def test_a_snippet_is_not_read_as_maths(tmp_path: Path, config: Config) -> None:
    """Braces and `$` inside a fence are C++, not a broken formula. Before
    this, a correct card reported `latex-parse` and could not be approved."""
    card = a_card(tmp_path / "c.md", SNIPPET)

    assert "latex-parse" not in codes(card, config)
    assert "latex-dollars" not in codes(card, config)


def test_an_unbalanced_dollar_inside_code_is_not_an_error(
    tmp_path: Path, config: Config
) -> None:
    """A shell snippet is mostly `$`, and none of them opens a formula."""
    card = a_card(tmp_path / "c.md", "```sh\necho \"$HOME is $USER\"\n```")

    assert "latex-dollars" not in codes(card, config)


def test_broken_maths_outside_a_fence_is_still_caught(
    tmp_path: Path, config: Config
) -> None:
    """The exemption is the fence, not the card. A formula beside a snippet
    is checked exactly as it was."""
    card = a_card(tmp_path / "c.md", f"{SNIPPET}\n\nand $x + is unclosed")

    assert "latex-dollars" in codes(card, config)


def test_multi_line_code_is_not_wrapped_prose(tmp_path: Path, config: Config) -> None:
    """`section-wrapped` exists because a newline in prose becomes a `<br>`.
    In a fence it becomes a newline, and one statement per line is the point."""
    card = a_card(tmp_path / "c.md", SNIPPET)

    assert "section-wrapped" not in codes(card, config)


def test_wrapped_prose_on_its_own_still_warns(tmp_path: Path, config: Config) -> None:
    """The exemption is the fence, not the card: a section that is only
    wrapped prose is caught exactly as it was. A section holding *both* is
    not, but that predates code and is why a two-paragraph section is not
    flagged either: the check fires only when every line is non-empty."""
    card = a_card(tmp_path / "c.md", "this sentence\nis wrapped\n")

    assert "section-wrapped" in codes(card, config)


# -- what Anki is sent ------------------------------------------------------


def test_a_fence_becomes_a_pre_and_keeps_its_newlines(tmp_path: Path) -> None:
    html = to_anki_html(SNIPPET)

    assert html.startswith('<pre class="code">') and html.endswith("</pre>")
    assert "<br>" not in html, "a newline in code is a newline, not a break"
    assert "\n" in html, "and it survives"


def test_the_code_is_escaped(tmp_path: Path) -> None:
    html = to_anki_html("```cpp\nstd::vector<int> v;\n```")

    assert "<int>" not in html, "a raw tag would be markup on the card"
    assert "&lt;" in html and "&gt;" in html


def test_prose_and_maths_around_it_are_unaffected(tmp_path: Path) -> None:
    html = to_anki_html(f"Use this:\n\n{SNIPPET}\n\nwhich is $O(n)$.")

    assert html.startswith("Use this:")
    assert "\\(O(n)\\)" in html
    assert "<br><br><pre" not in html, "a block element needs no breaks around it"


def test_a_fence_with_no_language_still_renders(tmp_path: Path) -> None:
    html = to_anki_html("```\nplain text, no language\n```")

    assert '<pre class="code">' in html
    assert "plain text, no language" in html


@pytest.mark.parametrize("lang", ["cpp", "python", "sh"])
def test_highlighting_marks_up_the_tokens(lang: str) -> None:
    """Highlighted at sync, the way a picture is rendered at sync: the file
    keeps plain code and the field gets classes the note type colours, so
    nobody needs an add-on."""
    html = to_anki_html(f"```{lang}\nreturn 1\n```")

    assert "<span" in html, "Pygments is installed, so the tokens carry classes"


def test_code_free_leaves_the_line_count_alone() -> None:
    """Whatever reports a line number still points at the right line."""
    text = f"one\n\n{SNIPPET}\n\nlast"

    assert len(model.code_free(text).splitlines()) == len(text.splitlines())
