"""Starting a project that reads no document (ROADMAP.md 10).

A project with a book behind it is created by importing the book, and
`forge zotero` writes its file. One on a subject has nothing to import, so
without this the only way to start is to write the TOML by hand and guess at
the key names.

Here rather than in `cli.py` because two callers write it: the command, and
the setup stage in the app. They must produce the same file, which is the
whole of invariant 2 -- anything the app does is doable by editing a file,
and the way to keep that true is for both to go through one function.
"""

from __future__ import annotations

import re

from .config import PROJECT_TOML, Config
from .model import slugify


def scaffold(
    config: Config,
    name: str,
    *,
    title: str = "",
    deck: str = "",
    citation: str = "",
) -> str | None:
    """Write `projects/<name>/project.toml`, and return the project's name.

    `None` when the name has nothing to make an id from, or when the file is
    already there. **Never overwrites**: everything in it is a starting
    point you will edit, and re-running must not undo that.

    It declares no `[[sources]]`, and that absence is what says the project
    has no authoritative source. There is no kind key to set.
    """
    if not re.search(r"[a-zA-Z0-9]", name):
        return None
    slug = slugify(name)
    path = config.projects_dir / slug / PROJECT_TOML
    if path.exists():
        return None

    shown = title or name
    lines = [f'title = "{shown}"', f'citation = "{citation or shown}"']
    if deck:
        lines.append(f'deck = "{deck}"')
    lines += [
        "",
        "# No `[[sources]]` table: this project reads no document, and that",
        "# absence is the whole of what that means. Add one when you have a",
        "# work to read against:",
        "#",
        "# [[sources]]",
        '# url = "https://example.org/the-reference"',
        "",
        "# Reference material goes in `references.md` beside this file, as",
        "# prose. It is a shelf to check a card against, never a set of things",
        "# to card, and `forge context` hands it to whoever writes one.",
        "",
        "# What is ambient here goes in `conventions.md`. With no book to read",
        "# it off, this file *decides* it rather than describing it: which",
        "# language version, how an example is written, what is assumed. Write",
        "# it before the first proposal, not after the first batch reads",
        "# inconsistent.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return slug
