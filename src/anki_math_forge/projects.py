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

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import model, scheme
from .config import (
    PROJECT_TOML,
    REFERENCES_FILE,
    Config,
    ConfigError,
    ProjectConfig,
    SourceConfig,
)
from .ledger import Ledger, Unit
from .model import PROPOSED_RE, slugify


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


@dataclass(frozen=True)
class Removal:
    """What deleting a project takes with it, or would.

    Reported rather than printed, because the CLI writes lines and the app
    renders a panel, and both have to be talking about the same deletion.
    """

    project: str
    #: `projects/<name>/`, when it is there. A project declared only in
    #: `forge.toml` has no folder.
    folder: Path | None
    #: `cards/<name>/`, when it is there.
    cards_dir: Path | None
    units: int
    cards: int
    #: Approved cards, which are the ones already pushed to Anki. Deleting
    #: the files here does not delete the notes there, and nothing local
    #: records a note id, so this is the number to warn about.
    approved: int
    #: It has a `[projects.<name>]` table in `forge.toml` as well as, or
    #: instead of, a folder.
    declared: bool

    @property
    def empty(self) -> bool:
        """Nothing anybody worked on. Not the same as "no files": a project
        with a `project.toml` and nothing else is a decision you can make
        again in one command."""
        return not self.units and not self.cards


def _counts(config: Config, name: str) -> tuple[int, int, int]:
    """Units, cards and approved cards this project holds."""
    ledger = config.units_path(name)
    units = 0
    if ledger.exists():
        units = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())
    here = [
        card
        for card in model.load_all(config.cards_dir)
        if model.home_of(card, config.cards_dir) == name
    ]
    return units, len(here), sum(1 for c in here if c.status == "approved")


def _declaring_lines(text: str, name: str) -> list[int]:
    """The line numbers of every `[projects.<name>]` table in `forge.toml`.

    Line-wise, and for the reason `scheme.py` gives: a hand-written
    `forge.toml` is mostly comments, and a round trip through a TOML writer
    would return a correct file with all of them gone. This finds the header
    of each table belonging to the project and every line under it, up to
    the next table that does not.
    """
    heads = (f"[projects.{name}]", f'[projects."{name}"]')
    under = (f"[projects.{name}.", f'[projects."{name}".',
             f"[[projects.{name}.", f'[[projects."{name}".')
    doomed: list[int] = []
    inside = False
    for at, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if stripped in heads or stripped.startswith(under):
            inside = True
            doomed.append(at)
            continue
        if inside:
            # A new top-level table ends the one we are dropping; anything
            # else (a key, a comment, a blank) belongs to it.
            if stripped.startswith("[") and not stripped.startswith(under):
                inside = False
            else:
                doomed.append(at)
    return doomed


def _undeclare(config: Config, name: str) -> bool:
    """Drop the project's tables from `forge.toml`. True if any were there."""
    path = config.root / "forge.toml"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    doomed = set(_declaring_lines(text, name))
    if not doomed:
        return False
    kept = [line for at, line in enumerate(text.splitlines()) if at not in doomed]
    while kept and not kept[-1].strip():
        kept.pop()
    model.write_atomic(path, "\n".join(kept) + "\n")
    return True


def removal(config: Config, name: str) -> Removal:
    """What deleting this project would take, without taking it.

    Raises when there is no such project, because "deleted nothing"
    reported as success is how you find out a week later that you removed
    the wrong one and never noticed.
    """
    # A name is one folder under `projects/`, never a path. This function
    # ends in `rmtree`, and `projects/..` is the repo: `Path` does not
    # normalise `..`, so the parent of `projects/..` reads as `projects` and
    # a check on that alone lets the whole repo through. Hence both: the
    # name must be a plain component, and the resolved folder must still sit
    # directly under `projects/`.
    folder = config.projects_dir / name
    home = config.projects_dir.resolve()
    if (
        not name
        or Path(name).name != name
        or name in (".", "..")
        or folder.resolve().parent != home
        or folder.resolve() == home
    ):
        raise ConfigError(f"{name!r} is not a project name")
    cards_dir = config.cards_dir / name
    toml = config.root / "forge.toml"
    declared = bool(
        _declaring_lines(toml.read_text(encoding="utf-8"), name) if toml.exists() else []
    )
    if not folder.is_dir() and not declared:
        raise ConfigError(f"no project called {name!r}")
    units, cards, approved = _counts(config, name)
    return Removal(
        project=name,
        folder=folder if folder.is_dir() else None,
        cards_dir=cards_dir if cards_dir.is_dir() else None,
        units=units,
        cards=cards,
        approved=approved,
        declared=declared,
    )


def remove(config: Config, name: str, *, force: bool = False) -> Removal:
    """Delete a project: its folder, its cards, and its table in `forge.toml`.

    Everything a project is lives in those three places, so a delete that
    left one of them behind would leave a project that half exists: a
    folder with no declaration still shows on the shelf, and a declaration
    with no folder shows as a project with nothing in it.

    **Refused when it holds cards, unless forced.** A project with no cards
    is a decision you can make again in one command; a project with
    thirty-nine of them is weeks of review, and a button that can destroy
    that on a mis-click is the wrong shape whatever it is labelled. The
    units are not the gate: they are derived from a document and `extract`
    writes them again.

    What this cannot undo is Anki. An approved card is already a note
    there, nothing local records its id, and deleting the file here leaves
    the note behind. `Removal.approved` is that number, for whoever is
    about to be asked.
    """
    going = removal(config, name)
    if going.cards and not force:
        raise ConfigError(
            f"{name} holds {going.cards} card"
            f"{'' if going.cards == 1 else 's'}"
            f"{f', {going.approved} of them approved and in Anki' if going.approved else ''}."
            " Pass --force if that is what you mean"
        )
    if going.folder is not None:
        shutil.rmtree(going.folder)
    if going.cards_dir is not None:
        shutil.rmtree(going.cards_dir)
    if going.declared:
        _undeclare(config, name)
    return going


#: The address inside a proposed line. A pass writes
#: `Title (https://...), what it is for`, and the URL is the one part of
#: that a machine can find without guessing.
URL_RE = re.compile(r"\(?\b(https?://[^\s)]+)\)?")


#: What ends a name when there is no address to end it. A book carries its
#: purpose in the same sentence, and `, for ` is how everybody writes it:
#: "Josuttis, The C++ Standard Library, 2nd edition, **for** worked
#: container usage". The last one, not the first, because a title can have
#: one in it ("A Course in Combinatorics, for Beginners") and the purpose
#: is always at the end.
PURPOSE_RE = re.compile(r",\s+for\s+", re.I)


def parse_proposal(line: str) -> tuple[str, str, str]:
    """A proposed shelf line read as (title, url, note).

    The shape the `/sources` pass writes: a title, the address in brackets,
    and what it is for. Split on the address, because that is the only part
    with a syntax; everything before it is the name and everything after is
    what you would tell somebody handing them the link.

    A line with no address is a book you own, and it has the same three
    parts with nothing in the middle one. `, for ` ends the name there.
    It is a guess about prose rather than a syntax, which is why it is the
    *last* one and why the note it produces is editable on the panel: the
    cost of getting it wrong is one field somebody retypes, and the cost of
    not trying is a title with a whole sentence in it.
    """
    text = PROPOSED_RE.sub("", line.strip(), count=1).strip()
    found = URL_RE.search(text)
    if found:
        title = text[: found.start()].strip().rstrip(",")
        note = text[found.end() :].strip().lstrip(",").strip()
        return title, found.group(1), note
    text = text.rstrip(". ")
    splits = list(PURPOSE_RE.finditer(text))
    if not splits:
        return text.rstrip(",. "), "", ""
    last = splits[-1]
    return text[: last.start()].strip().rstrip(","), "", text[last.end() :].strip()


#: How long a key may run. Long enough to stay recognisable in a URL and in
#: a `--document` argument, short enough to read in a list.
KEY_LIMIT = 40


def _key_for(title: str) -> str:
    """A key from a title, cut at a word.

    `slugify`'s own limit cuts at a character, which is right for a
    filename nobody types and wrong here: a key goes in a `[[sources]]`
    table, in a unit id and on a command line, and
    `cppreference-the-containers-libr` is a word somebody has to check
    against the file every time.
    """
    key = ""
    for word in slugify(title, limit=400).split("-"):
        if key and len(key) + 1 + len(word) > KEY_LIMIT:
            break
        key = f"{key}-{word}" if key else word
    return key[:KEY_LIMIT].strip("-") or "reference"


def site_of(url: str) -> tuple[str, list[str]]:
    """A URL as (scheme://host, path segments). Empty for anything else."""
    found = re.match(r"(https?://[^/?#]+)(/[^?#]*)?", url.strip())
    if not found:
        return "", []
    return found.group(1), [part for part in (found.group(2) or "").split("/") if part]


#: How much two addresses must share before they are read as one source.
#:
#: The host alone is not enough. Two arXiv papers are `arxiv.org/abs/<id>`
#: each, and merging them into `arxiv.org/abs` would make one source out of
#: two unrelated documents. Two pages of a reference manual are
#: `en.cppreference.com/w/cpp/<part>`, and *not* merging those leaves six
#: entries for one book. Two shared segments is the line between them: it
#: is where a path stops naming the site and starts naming a section of
#: something.
SHARED_SEGMENTS = 2


def common_ancestor(first: str, second: str) -> str:
    """The deepest address both are under, or "" if they are not one source.

    The rule the shelf follows: several pages of one site are one source,
    read in several places, and the note says which. Anything shallower
    than `SHARED_SEGMENTS` is two things that happen to be hosted together.
    """
    host, mine = site_of(first)
    other, theirs = site_of(second)
    if not host or host != other:
        return ""
    shared: list[str] = []
    for a, b in zip(mine, theirs, strict=False):
        if a != b:
            break
        shared.append(a)
    if len(shared) < SHARED_SEGMENTS and mine != theirs:
        return ""
    return "/".join([host, *shared])


def _part(ancestor: str, url: str, note: str) -> str:
    """One entry in a merged note: which part of the site, and what for.

    The tail rather than the whole address, because the address is on the
    line above and the only new thing here is which part of it this was
    about.
    """
    tail = url[len(ancestor) :].strip("/") if url.startswith(ancestor) else url
    if tail and note:
        return f"{tail}: {note}"
    return note or tail


def _merge_note(work: SourceConfig, ancestor: str, url: str, note: str) -> str:
    """What a widened source's note becomes.

    Both halves are labelled, not just the new one. Widening
    `.../w/cpp/container` to `.../w/cpp` leaves the old note describing a
    page the address no longer names, so it takes the tail it used to
    carry. Only while the address is actually moving: after the first
    widening the note is already labelled, and re-labelling it would read
    `container: container: ...`.
    """
    said = _part(ancestor, url, note)
    mine = work.note
    if ancestor != work.url:
        mine = _part(ancestor, work.url, work.note)
    if not said or said in mine:
        return mine
    return f"{mine}; {said}" if mine else said


def add_reference(
    config: Config,
    project: str,
    *,
    title: str,
    url: str = "",
    note: str = "",
    topic: str = "",
) -> tuple[str, bool]:
    """Write a reference into `project.toml`. Returns (key, merged).

    Nothing about it is authoritative: no files and no item key, so nothing
    is extracted from it and `forge context` hands it to whoever writes a
    card, which is what a reference is for.

    **One source per site, per ask.** If the project already reads
    something at the same address *for the same ask*, this does not add a
    second row: it widens that one to the deepest address both are under
    and adds this part to its note. Six rows for six pages of cppreference
    is six times the same source, and a card writer handed six of them
    learns nothing the first one did not say.

    The ask is what stops that going too far. Two asks reading two parts
    of one site are two sources, because the thing a card is checked
    against is the part, not the domain: widening them together would hand
    whoever writes about containers a note about threads.
    """
    path = config.projects_dir / project / PROJECT_TOML
    if not path.exists():
        raise ConfigError(
            f"{project} is configured in forge.toml rather than in its own "
            f"{PROJECT_TOML}; add the [[sources]] table there"
        )
    if not title:
        raise ConfigError("a source needs a name")
    spec = config.projects.get(project)
    works = list(spec.sources if spec else ())

    wanted = (topic,) if topic else ()
    if url:
        for work in works:
            # Never into something units come out of: a page of a website
            # is not part of a book somebody is segmenting, whatever the
            # addresses have in common.
            if work.authoritative or not work.url:
                continue
            # And never across asks. Same site, different question, two
            # sources: the part is what a card is checked against.
            if tuple(work.topics) != wanted:
                continue
            ancestor = common_ancestor(work.url, url)
            if not ancestor:
                continue
            note_now = _merge_note(work, ancestor, url, note)
            if ancestor != work.url:
                scheme.set_key(config, project, work.key, "url", ancestor)
            if note_now != work.note:
                scheme.set_key(config, project, work.key, "note", note_now)
            return work.key, True

    taken = {w.key for w in works}
    key = _key_for(title)
    if key in taken:
        key = next(f"{key}-{n}" for n in range(2, 99) if f"{key}-{n}" not in taken)

    rows = ["", "[[sources]]", f"key = {model.toml_string(key)}",
            f"title = {model.toml_string(title)}"]
    if url:
        rows.append(f"url = {model.toml_string(url)}")
    if note:
        rows.append(f"note = {model.toml_string(note)}")
    if topic:
        rows.append(f"topics = [{model.toml_string(topic)}]")
    with path.open("a", encoding="utf-8") as out:
        out.write("\n".join(rows) + "\n")
    return key, False


def accept_proposal(config: Config, project: str, line: str, topic: str = "") -> str:
    """Take a proposed line and make it a source. Returns its key.

    Two writes, and they are two halves of one move: the `[[sources]]`
    table, and the line taken out of `references.md`. The table is where
    the tool acts on it (ROADMAP.md 10: structured relations go in TOML),
    and leaving the line behind as well would be the same fact in two
    files, which is the one that drifts.
    """
    title, url, note = parse_proposal(line)
    if not title:
        raise ConfigError("that line has nothing to make a source from")
    key, _ = add_reference(
        config, project, title=title, url=url, note=note, topic=topic
    )
    drop_proposal(config, project, line)
    return key


def drop_proposal(config: Config, project: str, line: str) -> bool:
    """Take a line out of `references.md`. True if it was there."""
    path = config.projects_dir / project / REFERENCES_FILE
    if not path.exists():
        return False
    kept = [
        existing
        for existing in path.read_text(encoding="utf-8").splitlines()
        if existing.strip() != line.strip()
    ]
    if len(kept) == len(path.read_text(encoding="utf-8").splitlines()):
        return False
    model.write_atomic(path, "\n".join(kept).rstrip("\n") + "\n")
    return True


@dataclass(frozen=True)
class SourceRemoval:
    """What taking a source out of a project takes with it, or would."""

    project: str
    key: str
    title: str
    authoritative: bool
    #: Units whose document belongs to this work. They go with it: a unit
    #: whose work is gone has no crop to render, no scheme to read and no
    #: settings to resolve, and `extract` writes them again from the
    #: document if it comes back.
    units: int
    #: Cards standing on those units. These are the gate.
    cards: int
    approved: int


def _ledger_rows(config: Config, project: str) -> list[dict[str, Any]]:
    path = config.units_path(project)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _belongs(spec: ProjectConfig, unit: dict[str, Any], key: str) -> bool:
    """Is this unit's document read by the work `key`?

    Asked of `ProjectConfig.source`, which is the one definition of the
    mapping: a Zotero work declares an *item* key while its units carry
    *attachment* keys, so matching the string by hand gets it wrong.
    """
    document = str((unit.get("locator") or {}).get("document", "") or "")
    found = spec.source(document)
    return found is not None and found.key == key


def source_removal(config: Config, project: str, key: str) -> SourceRemoval:
    """What removing this source would take, without taking it."""
    spec = config.projects.get(project)
    work = next((w for w in spec.sources if w.key == key), None) if spec else None
    if spec is None or work is None:
        raise ConfigError(f"{project} does not read {key!r}")
    mine = [row for row in _ledger_rows(config, project) if _belongs(spec, row, key)]
    ids = {str(row.get("id", "")) for row in mine}
    cards = [card for card in model.load_all(config.cards_dir) if ids & set(card.units)]
    return SourceRemoval(
        project=project,
        key=key,
        title=work.title or key,
        authoritative=work.authoritative,
        units=len(mine),
        cards=len(cards),
        approved=sum(1 for card in cards if card.status == "approved"),
    )


def remove_source(
    config: Config, project: str, key: str, *, force: bool = False
) -> SourceRemoval:
    """Take a source out of a project: its table, and the units it owns.

    **Refused when cards stand on it, unless forced**, which is the rule
    `remove` follows for a whole project and for the same reason: a card is
    review time and a unit is not. The units go with the source, because a
    unit whose work is gone has no crop to render and no settings to
    resolve, and `extract` writes them again from the document.

    The table goes line by line, so the file keeps its comments.
    """
    going = source_removal(config, project, key)
    if going.cards and not force:
        approved = (
            f", {going.approved} of them approved and in Anki" if going.approved else ""
        )
        raise ConfigError(
            f"{going.cards} card{'' if going.cards == 1 else 's'} stand"
            f"{'s' if going.cards == 1 else ''} on {key!r}{approved}."
            " Pass --force if that is what you mean"
        )
    scheme.drop_table(config, project, key)
    if going.units:
        _drop_units(config, project, key)
    return going


def _drop_units(config: Config, project: str, key: str) -> None:
    """Take this work's units out of the ledger.

    Every other line byte for byte: the ledger is a record of decisions,
    and rewriting the lines nobody asked about makes a diff nobody can
    read.
    """
    spec = config.projects.get(project)
    path = config.units_path(project)
    if spec is None or not path.exists():
        return
    kept = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not (line.strip() and _belongs(spec, json.loads(line), key))
    ]
    model.write_atomic(path, "\n".join(kept) + ("\n" if kept else ""))


def declare_zotero(
    config: Config, project: str, *, key: str, title: str = "", citation: str = ""
) -> bool:
    """Say that this project reads a Zotero item. True if it was written.

    `forge zotero` imports marks, and the marks are not the point on their
    own: the point is that the project reads the work. Until this, the
    import wrote a `[[sources]]` table only as part of a whole
    `project.toml` for a project that did not exist yet, and only when
    there were units. So importing a book into a project you already have
    left the work undeclared, and importing one you had not marked up yet
    left nothing at all: the command said what it found and wrote none of
    it down.

    Authoritative, unlike everything the app writes: the item key is here,
    which is what makes marks in it become units. That is the whole reason
    it is a command you type.
    """
    spec = config.projects.get(project)
    if spec is not None and any(w.zotero_key == key for w in spec.sources):
        return False
    # One extraction per document, which is the rule `check_sources`
    # reports on. Refused here as well, because a second table is easy to
    # write by accident and hard to see afterwards.
    for name, other in config.projects.items():
        if name != project and any(w.zotero_key == key for w in other.sources):
            raise ConfigError(
                f"{name} already extracts from {key!r}, and a work is"
                " extracted from by one project. Add it to"
                f" {project} as a reference instead, or remove it there first"
            )
    path = config.projects_dir / project / PROJECT_TOML
    if not path.exists():
        raise ConfigError(
            f"{project} has no {PROJECT_TOML} to add a source to"
        )
    rows = ["", "[[sources]]", f"zotero = {model.toml_string(key)}"]
    if title:
        rows.append(f"title = {model.toml_string(title)}")
    if citation:
        rows.append(f"citation = {model.toml_string(citation)}")
    with path.open("a", encoding="utf-8") as out:
        out.write("\n".join(rows) + "\n")
    return True


def apply_scheme(config: Config, project: str) -> tuple[int, int]:
    """Bring the ledger back in line with what the project now declares.

    Returns `(dropped, kept)`. One setting changes what should be in it: a
    **mark that no longer makes a unit**, unchecked in the scheme editor.
    A colour you stopped reading as a unit went on being a unit in every
    count, filter and pass until this ran.

    Untouched units go. Anything decided stays and is counted, which is the
    trade `drop_from_scheme` already makes for the import: a triaged unit
    is a decision, and changing a setting is about what to read next rather
    than about undoing one.

    **`extract = false` drops nothing.** It says stop making units out of
    this, not that the ones you have are wrong: the document is still
    declared, their crops still render from the geometry they carry, and
    the scheme still resolves. Deleting them made the switch destroy work
    in one direction and do nothing in the other, so turning it off by
    mistake cost five units and turning it back on did not return them.
    """
    spec = config.projects.get(project)
    path = config.units_path(project)
    if spec is None or not path.exists():
        return 0, 0

    def keeps(unit: Unit) -> bool:
        work = spec.source(unit.locator.document)
        if work is None:
            # Its work is gone from the file, so nothing can render it, no
            # scheme reads it and no setting resolves for it. That is the
            # one case where a unit has stopped meaning anything, and
            # `remove_source` is where it happens.
            return False
        anchor = unit.marks[0] if unit.marks else None
        if anchor is None:
            # A segmenter's unit. No colour scheme has anything to say.
            return True
        return config.zotero_for(project, work.key).makes_a_unit(
            anchor.kind, anchor.colour
        )

    # Read first, and only take the lock when there is something to take
    # out. A save rewrites every line, so a settings change that drops
    # nothing would still put the whole ledger in the next diff.
    if all(keeps(unit) for unit in Ledger.load(path)):
        return 0, 0
    with Ledger.edit(path) as ledger:
        return ledger.drop_untouched(keeps)
