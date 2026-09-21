"""Free text out of a file, rendered.

`conventions.md`, the ask under a topic heading, a line of `references.md`:
all of them markdown in practice, because that is what you type into a `.md`
file. Shown literally they were a wall of `-` and `$\\partial$`, which is the
app saying it has not read the file you are looking at (ROADMAP.md 10).

The rule that matters is the first one: **maths comes out before anything
else and goes back untouched.** An emphasis pass over `$a_1 * b_2$` would eat
the underscore and the star.
"""

from __future__ import annotations

from anki_math_forge.app import prose


def test_a_bullet_list_is_a_list() -> None:
    out = str(prose.render("- one\n- two"))

    assert out == "<ul><li>one</li><li>two</li></ul>"


def test_a_wrapped_bullet_stays_in_the_list() -> None:
    """How anyone writes a long one in a file. Starting a paragraph at the
    wrap put half the sentence outside the list."""
    out = str(prose.render("- one that runs\n  on to a second line\n- two"))

    assert out == "<ul><li>one that runs on to a second line</li><li>two</li></ul>"


def test_a_numbered_list_is_its_own_kind() -> None:
    assert str(prose.render("1. one\n2. two")) == "<ol><li>one</li><li>two</li></ol>"


def test_wrapped_prose_is_one_sentence() -> None:
    """Hard-wrapped in the file is the editor's column width, not a break to
    render."""
    assert str(prose.render("a sentence\nwrapped in the file")) == (
        "<p>a sentence wrapped in the file</p>"
    )


def test_maths_survives_the_emphasis_pass() -> None:
    """The whole reason the spans come out first."""
    out = str(prose.render("- one $a_1 * b_2$"))

    assert "$a_1 * b_2$" in out
    assert "<em>" not in out


def test_an_identifier_is_not_emphasis() -> None:
    """`crop_width` and `units_from` are in this prose constantly, and a rule
    that fires inside a word slants the middle of one."""
    out = str(prose.render("set crop_width and units_from on a_long_name"))

    assert "<em>" not in out
    assert "crop_width" in out


def test_the_four_inline_forms() -> None:
    out = str(prose.render("**bold** *stars* _under_ `code`"))

    assert "<strong>bold</strong>" in out
    assert out.count("<em>") == 2
    assert "<code>code</code>" in out


def test_a_heading_cannot_outrank_the_page() -> None:
    """A fragment inside a page that already has a heading."""
    assert "<h4>" in str(prose.render("# a title"))
    assert "<h1>" not in str(prose.render("# a title"))


def test_a_link_has_to_point_somewhere_sensible() -> None:
    out = str(prose.render("[docs](https://example.com) [no](javascript:alert(1))"))

    assert '<a href="https://example.com" rel="noreferrer">docs</a>' in out
    assert "javascript:" in out, "shown as the text it is"
    assert "<a href=\"javascript:" not in out


def test_html_in_the_file_is_text() -> None:
    assert "&lt;script&gt;" in str(prose.render("<script>x</script>"))


def test_a_fence_is_code_and_not_prose() -> None:
    out = str(prose.render("```python\nx = 1\n```"))

    assert out == "<pre class='code'>x = 1</pre>"


def test_one_line_has_no_paragraph_round_it() -> None:
    """For a cell or a heading that wants the maths and not the margin."""
    assert str(prose.line("a $x$ b")) == "a $x$ b"
    assert "<p>" not in str(prose.line("**b**"))


def test_nothing_renders_as_nothing() -> None:
    assert str(prose.render("")) == ""
    assert str(prose.render("   \n  ")) == ""
