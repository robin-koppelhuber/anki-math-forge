"""`topics.md` -- what you asked for, and what it means to cover (ROADMAP.md 10).

A source answers "what does this say". A topic answers "what should we
cover", and it exists for the case where no source can: a project on a
subject has no book to read the coverage off, so the ask and its outline are
the only statement of what the deck is meant to contain.

**Prose, counted rather than interpreted.** A heading per topic, the ask in
your own words under it, and a list of what it should cover. Nothing here
parses meaning: finding the entries is finding the list items, which is the
same thing `annotation_audience` does with a prefix at line start. The file
stays something you edit in an editor, and deleting a line is how you say a
subject is not wanted.

**The slug is the join.** An outline entry and the unit proposed from it
slugify to the same id, which is what `units --add` was built around, so
"which entries have nothing yet" is a set difference rather than a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import TOPICS_FILE, Config
from .ledger import Ledger
from .model import slugify

#: A topic starts at a level-two heading. Level one is the file's own title,
#: so `# Topics` at the top is not a subject called "Topics".
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
#: An outline entry is a list item at the left margin. Indented ones are
#: somebody's sub-points about an entry, not entries of their own.
ENTRY_RE = re.compile(r"^[-*]\s+(.+?)\s*$")


@dataclass(frozen=True)
class Entry:
    """One line of an outline, and whether anything came of it."""

    text: str
    slug: str
    #: Unit ids that slugify to this entry. Usually one, occasionally none,
    #: and more than one where a subject was proposed under two wordings.
    units: tuple[str, ...] = ()

    @property
    def covered(self) -> bool:
        return bool(self.units)


@dataclass(frozen=True)
class Topic:
    """One ask, and the outline of what it should cover."""

    name: str
    slug: str
    #: What you wanted, in your own words. Everything between the heading and
    #: the first list item, which is where `/propose` records it.
    ask: str = ""
    outline: tuple[Entry, ...] = ()

    @property
    def covered(self) -> int:
        return sum(1 for entry in self.outline if entry.covered)

    @property
    def open(self) -> tuple[Entry, ...]:
        """The entries nothing has been proposed for yet.

        The whole point of writing an outline down: a pass that stops halfway
        looks exactly like a subject that was smaller than you thought, and
        this is the difference.
        """
        return tuple(entry for entry in self.outline if not entry.covered)


def path_for(config: Config, project: str) -> Path:
    return config.projects_dir / project / TOPICS_FILE


def read(config: Config, project: str, ledger: Ledger | None = None) -> list[Topic]:
    """Every topic in a project, with its outline matched against the ledger.

    A project with no `topics.md` has no topics, which is the normal case:
    most projects have a source doing the job a topic would.
    """
    path = path_for(config, project)
    if not path.exists():
        return []
    if ledger is None:
        ledger = Ledger.load(config.units_path(project))
    # Slug to the ids that carry it. A unit id is `<project>:<slug>`, and a
    # segmented one is `<project>:<section>:<number>`, which no outline entry
    # will ever match -- so a book with a topic file matches on the proposed
    # units and ignores the rest without being told to.
    by_slug: dict[str, list[str]] = {}
    for unit in ledger:
        by_slug.setdefault(unit.id.split(":", 1)[-1], []).append(unit.id)

    text = path.read_text(encoding="utf-8")
    out: list[Topic] = []
    for match, body in _sections(text):
        ask_lines: list[str] = []
        entries: list[Entry] = []
        for line in body.splitlines():
            found = ENTRY_RE.match(line)
            if found:
                item = found.group(1).strip()
                slug = slugify(item)
                entries.append(Entry(item, slug, tuple(by_slug.get(slug, ()))))
            elif not entries:
                # Before the first entry: the ask. After it, a stray line is
                # somebody's note about an entry and is left where it is.
                ask_lines.append(line)
        out.append(
            Topic(
                name=match,
                slug=slugify(match),
                ask="\n".join(ask_lines).strip(),
                outline=tuple(entries),
            )
        )
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    """`(heading, body)` for each level-two heading, in file order."""
    heads = list(HEADING_RE.finditer(text))
    out: list[tuple[str, str]] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((head.group(1), text[head.end() : end]))
    return out


def append(config: Config, project: str, name: str, ask: str = "") -> Topic:
    """Record a new ask, and return it.

    Appends rather than rewrites: the file is something you edit, and a tool
    that reformats it on every write would fight you for it. A heading that
    is already there is left alone and returned as it stands, so asking twice
    is not two topics.
    """
    existing = {topic.slug: topic for topic in read(config, project)}
    slug = slugify(name)
    if slug in existing:
        return existing[slug]

    path = path_for(config, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "" if path.exists() else "# What this deck is for\n"
    body = path.read_text(encoding="utf-8") if path.exists() else ""
    block = f"\n## {name}\n\n" + (f"{ask.strip()}\n" if ask.strip() else "")
    path.write_text((head + body).rstrip("\n") + "\n" + block, encoding="utf-8")
    return Topic(name=name, slug=slug, ask=ask.strip())


@dataclass(frozen=True)
class Coverage:
    """How much of a project's outlines has been proposed for."""

    entries: int = 0
    covered: int = 0
    topics: tuple[Topic, ...] = field(default_factory=tuple)

    @property
    def open(self) -> int:
        return self.entries - self.covered


def coverage(config: Config, project: str, ledger: Ledger | None = None) -> Coverage:
    topics = tuple(read(config, project, ledger))
    return Coverage(
        entries=sum(len(t.outline) for t in topics),
        covered=sum(t.covered for t in topics),
        topics=topics,
    )
