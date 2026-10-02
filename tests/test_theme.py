"""The seam between the stylesheet and the decisions it is made of.

A theme is `theme.css`: every colour is a name there, and `app.css` reads
the names. That only stays true while something checks it, because every
new rule is written by looking at one theme and reaching for a literal.
ROADMAP.md §14.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "static"
APP = (STATIC / "app.css").read_text(encoding="utf-8")
THEME = (STATIC / "theme.css").read_text(encoding="utf-8")

COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")

#: The one place a literal colour belongs in app.css. Zotero's palette is
#: what a highlight looks like in the PDF, and a swatch that does not match
#: the document it came from makes you translate, so it is not a theme
#: decision and stays where it is.
NOT_THEMEABLE = (".swatch",)


def set_by_the_script() -> set[str]:
    """Names the page writes at runtime: a measured header height, a width
    you dragged a rail to. Those are measurements rather than decisions, so
    a fallback on one is its value before the script has run, and not a
    leak. Every one of them appears as a string in the static JS, which is
    what makes this a test rather than a list kept by hand."""
    js = "".join(p.read_text(encoding="utf-8") for p in STATIC.glob("*.js"))
    return set(re.findall(r"""["'`](--[\w-]+)""", js))


def rules(css: str) -> list[tuple[str, str]]:
    """Every `(selector, body)`, with comments out of the way."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [
        (m.group(1).strip(), m.group(2))
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def test_app_css_holds_no_colour_of_its_own() -> None:
    leaks = [
        f"{selector}: {colour}"
        for selector, body in rules(APP)
        if not any(name in selector for name in NOT_THEMEABLE)
        for colour in COLOUR.findall(body)
    ]
    assert not leaks, (
        "a colour written into app.css is one no theme can change. Name it "
        f"in theme.css and read the name: {leaks}"
    )


def test_every_name_app_css_reads_is_declared() -> None:
    """`--hover` was read twelve times and declared nowhere, so every use
    carried a fallback of its own, in four strengths, and a theme could not
    change it. A name nobody declares is the same seam leaking."""
    declared = set(re.findall(r"(--[\w-]+)\s*:", THEME + APP)) | set_by_the_script()
    read = set(re.findall(r"var\((--[\w-]+)", APP))

    assert not read - declared, f"read and never declared: {sorted(read - declared)}"


def test_no_fallback_hides_a_missing_name() -> None:
    """A fallback on a declared name is dead code, and a fallback on an
    undeclared one is the leak itself. Either way it should not be there."""
    fallbacks = set(re.findall(r"var\((--[\w-]+)\s*,", APP)) - set_by_the_script()

    assert not fallbacks, f"var() with a fallback: {sorted(fallbacks)}"


def test_dark_follows_the_system_and_can_be_pinned_either_way() -> None:
    """Three positions, not two. Following the system needs no script, and
    a pinned choice has to beat the media query in both directions."""
    assert "@media (prefers-color-scheme: dark)" in THEME
    assert ':root:not([data-theme="light"])' in THEME, "light can be pinned over dark"
    assert ':root[data-theme="dark"]' in THEME, "dark can be pinned over light"


def test_pinned_dark_is_the_same_dark_as_the_system_one() -> None:
    """Dark is written twice, once under the media query and once for the
    pin, because CSS has no way to say "this block, or that attribute".
    Two copies drift the first time somebody tunes one."""
    def block(selector: str) -> dict[str, str]:
        body = next(body for sel, body in rules(THEME) if sel.endswith(selector))
        return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body))

    system = block(':root:not([data-theme="light"])')
    pinned = block(':root[data-theme="dark"]')
    assert system and system == pinned


def test_the_pin_is_restored_before_the_first_stylesheet() -> None:
    """In `app.js` it would apply after one paint in the system theme, and
    every page load would flash the other colour."""
    base = (STATIC.parent / "templates" / "base.html").read_text(encoding="utf-8")
    restore = base.index("anki-forge.theme")
    assert restore < base.index("theme.css"), "restored after the stylesheet loads"
    assert "anki-forge.theme" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_the_names_the_canvas_reads_still_exist() -> None:
    """`graph.js` reads token names as strings off the computed style, and
    an unknown one is an empty string that `ctx.strokeStyle` silently
    ignores. A rename here breaks the canvas with no error anywhere."""
    js = (STATIC / "graph.js").read_text(encoding="utf-8")
    wanted = set(re.findall(r"""["'](--[\w-]+)["']""", js))
    declared = set(re.findall(r"(--[\w-]+)\s*:", THEME + APP))

    assert wanted, "graph.js reads no token names; this test is looking in the wrong place"
    assert not wanted - declared, f"the canvas asks for: {sorted(wanted - declared)}"
