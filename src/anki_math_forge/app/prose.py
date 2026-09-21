"""Free text from a file, as HTML: a list is a list and the maths renders.

Everything on the setup stage comes out of a file somebody writes by hand --
`conventions.md`, the ask under a topic heading, a line of `references.md` --
and every one of them is markdown in practice, because that is what you type
into a `.md` file. Shown in a `<pre>` they were a wall of literal `-` and
`$\\partial$`, which is the app telling you it has not read the file you are
looking at.

Deliberately small. Not a markdown implementation: paragraphs, lists,
headings, and the four inline forms that turn up in this repo's prose. Half a
library would be a second renderer to keep in step with the card one, and
what these files hold is a paragraph and a list of bullets.

**Maths comes out first and goes back untouched.** `$a_1 * b_2$` has an
underscore and a star in it, and an emphasis pass over that text would eat
both. So the spans are lifted out before anything else runs, along with code,
which has the same problem for the same reason. KaTeX renders them in the
browser, out of the text the escape puts back.
"""

from __future__ import annotations

import re
from html import escape

from markupsafe import Markup

from .. import latex
from ..model import CODE_FENCE_RE

#: A run of `- ` or `* ` lines is a list; `1. ` is a numbered one. At the left
#: margin only, like `topics.md`: an indented bullet is somebody's sub-point
#: about the line above, and this is not the renderer to start nesting in.
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\d+[.)]\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(\S(?:[^*]*\S)?)\*\*")
#: Emphasis, at word boundaries only. `crop_width` and `units_from` are
#: written in this prose constantly, and a rule that fires inside a word turns
#: `a_long_name` into one with a slanted middle.
_STAR_RE = re.compile(r"(?<![\w*])\*(\S(?:[^*\n]*\S)?)\*(?![\w*])")
_UNDER_RE = re.compile(r"(?<![\w_])_(\S(?:[^_\n]*\S)?)_(?![\w_])")
#: Where a link may point. Anything else is shown as the text it is: these
#: files are handwritten rather than fetched, so this is hygiene and not a
#: defence, and a `javascript:` in one would be a surprise worth not running.
_SAFE_LINK = ("http://", "https://", "mailto:", "/")


def render(text: str) -> Markup:
    """One file, or one paragraph of one, as HTML."""
    if not text or not text.strip():
        return Markup("")
    out: list[str] = []
    cursor = 0
    for match in CODE_FENCE_RE.finditer(text):
        out.append(_blocks(text[cursor : match.start()]))
        out.append(f"<pre class='code'>{escape(match.group(2).strip())}</pre>")
        cursor = match.end()
    out.append(_blocks(text[cursor:]))
    return Markup("".join(out))


def line(text: str) -> Markup:
    """One line, inline only: no paragraph around it.

    For the places that are already a heading or a cell and want the maths
    rendered and the `**` honoured without a `<p>` taking a margin.
    """
    return Markup(_inline(text.strip()))


def _blocks(text: str) -> str:
    """Paragraphs, lists and headings, separated by blank lines."""
    html: list[str] = []
    items: list[str] = []
    kind = ""
    lines: list[str] = []

    def flush_list() -> None:
        nonlocal items, kind
        if items:
            html.append(f"<{kind}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{kind}>")
        items, kind = [], ""

    def flush_para() -> None:
        nonlocal lines
        if lines:
            # Joined with a space: prose hard-wrapped in a file is one
            # sentence, and a `<br>` per wrap would be the editor's column
            # width showing up on the screen.
            html.append(f"<p>{_inline(' '.join(lines))}</p>")
        lines = []

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush_para()
            flush_list()
            continue
        if found := _HEADING_RE.match(stripped):
            flush_para()
            flush_list()
            # Capped at `h4`: this is a fragment inside a page that already
            # has a heading, and a file's `#` must not outrank it.
            level = min(4, 3 + len(found.group(1)))
            html.append(f"<h{level}>{_inline(found.group(2))}</h{level}>")
            continue
        bullet = _BULLET_RE.match(stripped)
        number = None if bullet else _NUMBER_RE.match(stripped)
        if bullet or number:
            flush_para()
            wanted = "ul" if bullet else "ol"
            if kind and kind != wanted:
                flush_list()
            kind = wanted
            items.append(_inline((bullet or number).group(1)))  # type: ignore[union-attr]
            continue
        if items:
            # A wrapped bullet, which is how anyone writes a long one in a
            # file. Starting a paragraph at the wrap put half the sentence
            # outside the list and the other half in it.
            items[-1] += " " + _inline(stripped)
            continue
        lines.append(stripped)
    flush_para()
    flush_list()
    return "".join(html)


def _inline(raw: str) -> str:
    """Escape, keep maths and code verbatim, and honour the four forms."""
    kept: list[str] = []

    def keep(html: str) -> str:
        kept.append(html)
        # NUL cannot occur in the escaped text, so the placeholder cannot be
        # produced by anything the file contains.
        return f"\x00{len(kept) - 1}\x00"

    out: list[str] = []
    cursor = 0
    for span in latex.math_spans(raw):
        out.append(raw[cursor : span.start])
        out.append(keep(escape(raw[span.start : span.end])))
        cursor = span.end
    out.append(raw[cursor:])
    text = "".join(out)
    text = _CODE_SPAN_RE.sub(lambda m: keep(f"<code>{escape(m.group(1))}</code>"), text)
    text = escape(text)
    text = _LINK_RE.sub(_link, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _STAR_RE.sub(r"<em>\1</em>", text)
    text = _UNDER_RE.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)


def _link(match: re.Match[str]) -> str:
    label, href = match.group(1), match.group(2)
    if not href.startswith(_SAFE_LINK):
        return match.group(0)
    return f'<a href="{href}" rel="noreferrer">{label}</a>'
