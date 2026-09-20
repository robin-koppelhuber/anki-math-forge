"""Configuration: one TOML at the repo root (DESIGN.md ss11)."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import study

CONFIG_NAME = "forge.toml"
# What the file used to be called. Still read, so a repo does not have to
# be renamed in the same sitting as the tool.
LEGACY_CONFIG_NAMES = ("anki-forge.toml",)
CONFIG_NAMES = (CONFIG_NAME, *LEGACY_CONFIG_NAMES)

# Which layout a derivative is written in. A typo here would read as
# "not denominator" and silently change what every card means, so it is
# refused at load rather than discovered by a wrong `verify`.
#
# It lives under `[conventions]` in a source's own file and **nowhere else**:
# it is a fact about one book, in the same class as "entries are real" or
# "indices are 1-based", and the only reason the tool knows the word at all is
# that `verify` has to act on it. See `CONVENTIONS` below.
LAYOUTS = ("denominator", "numerator")

# The conventions table: `[conventions]` in `project.toml`, free-form.
#
# **Open on purpose.** What is ambient in a source is not a vocabulary this
# tool can enumerate -- the next paper will assume something neither of us has
# thought of -- so any key is accepted, and every one of them is handed to
# whoever writes a card (`forge context`, and the guide's "this source" panel).
# Prose that needs a paragraph still belongs in `conventions.md`; this is for
# the one-liners worth stating as a value.
#
# Exactly one key is *acted* on rather than only shown, and it is listed here
# so the asymmetry is visible rather than buried in `verify`:
CONVENTIONS_ACTED_ON = {
    "layout": "which matrix-derivative layout the source writes; `verify` "
    "computes denominator and refuses a source that says numerator",
}

# Whether the order a source prints things in is worth following. A book
# that builds up should say `printed`; an alphabetical table or a paper
# whose results precede their lemmas should say `none`, and its cards fall
# back to an arbitrary but stable order instead of a misleading one.
ORDERS = ("printed", "none")


class ConfigError(Exception):
    pass


def settled(*asked: Any, empty: Any = None) -> Any:
    """The first answer somebody actually gave, walking outwards.

    Every per-unit setting resolves the same way: the unit, then the work,
    then the project, then the repo, most specific first. Written out at each
    call site that was four `if`s apiece, and adding a level meant editing
    every one of them -- so a parent relation or a layer for topics was a
    change in four places rather than one more argument here (ROADMAP.md 10).

    `empty` is what counts as "nobody said". `None` for a tri-state, because
    `False` is an answer; `""` for a string; `-1` for the window, whose zero
    means "just this page". Passing it explicitly is what keeps a real `False`
    from falling through to the next level, which is the bug this shape is
    most likely to hide.
    """
    for answer in asked:
        if answer is not empty:
            return answer
    return empty


@dataclass(frozen=True)
class SourceConfig:
    """One work inside a project: a book, a paper, a page on the web.

    A project is what holds a ledger, a deck and a conventions file; a source
    is a thing you read. The two were one class until a project could hold
    several works, which is what a cluster of related papers is (ROADMAP.md
    10).

    **Files, not a file.** A book delivered as fifteen chapter PDFs is one
    source with fifteen files, and `locator.document` names which of them a
    unit was printed in. That is the whole of the hierarchy: project, source,
    file, with no parent relations, because a work's parts are its files and
    anything deeper is a project that has outgrown its `conventions.md`.

    Everything here is about *reading a document*, which is why it is not on
    the project: a marking scheme belongs to a work, and a project with two
    works that disagree about one is a project to split.
    """

    #: How a unit names this source. For a Zotero item it is the item key, and
    #: a unit's `locator.document` is one of its attachments rather than this.
    key: str = ""
    title: str = ""
    citation: str = ""
    #: A source you read on the web rather than out of a file. It carries no
    #: geometry, so nothing is extracted from it and it needs none of the
    #: settings below; it is there to be checked against.
    url: str = ""
    tex: Path | None = None
    files: tuple[Path, ...] = ()
    #: The Zotero item this came from, when it did. The units carry their own
    #: attachment keys, so this is not used to find anything; it is what makes
    #: "where did this come from" answerable without opening Zotero.
    zotero_key: str = ""
    #: Which of a Zotero item's attachments to read, by title or by key. Empty
    #: means all of them, which is right until it is not: an item routinely
    #: carries the paper and a preprint of the paper, and marks made in one
    #: are not marks in the other.
    attachments: tuple[str, ...] = ()
    #: Points of page shown around this source's crops; 0 inherits.
    crop_context: float = 0.0
    #: `box` or `page`; empty inherits, and what it inherits depends on where
    #: the geometry came from -- see `Config.crop_width_for`.
    crop_width: str = ""
    #: What this source's marks mean, overriding the repo-wide `[zotero]`.
    #: Colour schemes drift between a book you read last year and a paper you
    #: read last week, and a scheme that is wrong is worse than none.
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)
    #: The word that asks for a convention here, when this document is read in
    #: another language than the rest of the shelf. Empty inherits.
    convention_keyword: str = ""

    @property
    def authoritative(self) -> bool:
        """Whether units are extracted from this, rather than read beside it.

        Derived rather than declared, because it is the same question as
        "is there something here to segment". A URL you told a pass to read
        is reference material: it settles nothing on its own, and a unit that
        stands on it says where to look rather than what to write.
        """
        return bool(self.files or self.tex or self.zotero_key)

    @property
    def pdf(self) -> Path | None:
        """The first file, for the many callers that read one document."""
        return self.files[0] if self.files else None


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    title: str
    citation: str
    #: The works this project reads. Usually one; a tight cluster of related
    #: papers is several, and a project with no authoritative source at all is
    #: one whose cards come from topics instead.
    sources: tuple[SourceConfig, ...] = ()
    # Empty means "inherit the repo default": which deck this source's cards
    # belong in. A repo with one source never sets it.
    deck: str = ""
    order: str = "printed"
    # Pages either side handed to a card writer, or `chapter`; -1 inherits.
    context_pages: int | str = -1
    # Card type -> deck, for a source whose restatements and explanations want
    # different new-card rates. Empty means every type lands in `deck`.
    decks: Mapping[str, str] = field(default_factory=dict)
    # Tag -> deck, for a project whose cards split by subject rather than by
    # kind: containers, algorithms, ownership. **File order decides**, so a
    # card carrying two of these lands somewhere predictable rather than
    # somewhere alphabetical. TOML preserves the order you wrote them in and
    # so does this.
    #
    # (Not "by type:" at the start of a line above, deliberately: mypy reads
    # a comment opening `# type:` as an annotation and fails to parse the
    # file.)
    tag_decks: Mapping[str, str] = field(default_factory=dict)
    # Free labels, so a picker with fifty papers in it can be narrowed. Not a
    # hierarchy: a source is one thing that may be several kinds of thing.
    # **Yours to invent.** Nothing writes one for you: a label the tool made up
    # is a label that means whatever the tool guessed, and you would be
    # filtering by it without ever having decided what it says.
    tags: tuple[str, ...] = ()
    # What is ambient in this source, as keys rather than prose: `[conventions]`
    # in `project.toml`. Free-form -- see `CONVENTIONS_ACTED_ON`. There is no
    # repo-wide counterpart, deliberately: a default convention is a claim
    # about a book nobody has read yet.
    conventions: Mapping[str, str] = field(default_factory=dict)
    # Whether whoever writes a card from this source may look things up on the
    # web. `None` inherits the repo setting, which is off.
    web: bool | None = None

    @property
    def dir_name(self) -> str:
        return self.name

    def source(self, document: str = "") -> SourceConfig | None:
        """Which work a unit came out of, by the file it names.

        A unit records `locator.document`, which is a file or a Zotero
        attachment, and file to source is many to one and declared, so the
        source is looked up rather than stored on the unit.

        An empty `document` means the only one, which is what a project with
        a single work always passes. With several works and no name there is
        no answer, and guessing the first would silently read one book's
        marking scheme onto another's crops.
        """
        if document:
            for source in self.sources:
                if document == source.key or document in source.attachments:
                    return source
                if any(document == f.name or document == str(f) for f in source.files):
                    return source
        real = [s for s in self.sources if s.authoritative]
        if len(real) == 1:
            return real[0]
        return self.sources[0] if len(self.sources) == 1 else None

    @property
    def layout(self) -> str:
        """The one convention the tool acts on rather than only shows.

        A property and not a field, so there is a single home for it and no
        way for the two to disagree. It used to be a first-class key beside
        `deck` and `order`, which quietly said every source has a
        matrix-derivative layout; most have nothing of the kind.
        """
        return self.conventions.get("layout", "")


# What Zotero's annotation kinds are, before you say what you use them for.
#
# These are the closed set Zotero defines, so they are the same in every
# library and the tool can state them; a *colour* is a scheme you invented and
# it cannot. So this is the floor: a mark always reads as something, and a
# fresh repo is not a wall of squares with no captions. Anything you declare --
# repo-wide in `[zotero.meanings]`, or per source in `project.toml` -- sits on
# top, and the views say which of the two a meaning came from, because "you
# have not decided about this colour yet" is worth seeing.
#
# Deliberately descriptive rather than interpretive: what the mark *is*, not
# what it is for. What it is for is the part only you know.
#
# Keyed by kind alone, and that is not an abbreviation of a pair: it says what
# Zotero's annotation *is*, which is a fact about the kind. What you meant by
# it is a fact about the kind **and** the colour, and that is what
# `[zotero.meanings]` takes.
DEFAULT_MEANINGS: Mapping[str, str] = {
    "highlight": "a passage you marked",
    "underline": "a passage you underlined",
    "note": "something you wrote in the margin",
    "image": "a region you boxed -- a figure, a table, a diagram",
    "ink": "something you drew on the page",
    "text": "a comment you typed onto the page",
}


# Zotero colours every mark it draws, so a declared key is a pair. The
# exception is a kind with nothing to colour: for one of those the kind *is*
# the pair, and asking for `ink/red` would be asking for a mark the reader
# cannot have made.
COLOURLESS_KINDS = frozenset({"ink"})

#: Where a source imported from Zotero puts its cards when it names no deck
#: of its own. A subtree rather than the repo default: what you have read is
#: not yet what you have decided to keep, and one parent deck is what makes
#: the whole import studiable, suspendable and deletable in one move.
ZOTERO_DECK = "Zotero"


def zotero_deck(title: str, key: str = "") -> str:
    """`Zotero::<title>`, safe to hand to Anki.

    `::` is Anki's subdeck separator, so a title carrying one would quietly
    nest two levels deeper than anybody asked for. Whitespace is collapsed for
    the same reason a deck called `Probabilistic  Artificial Intelligence`
    with two spaces in it is a deck you will mistype once and then wonder
    about.
    """
    name = " ".join(str(title or key or "unnamed").replace("::", ":").split())
    return f"{ZOTERO_DECK}::{name}"


#: The one window size that is not a number of pages. A card writer is given
#: the unit's page and some number either side; between "ten pages" and "the
#: whole book" the size you actually want is the chapter, because a chapter is
#: the span a book states its standing assumptions in and no count of pages
#: either side knows where it starts. Stored as the word, in the ledger and in
#: both TOML files, so the file says what it means.
CHAPTER = "chapter"


def context_size(value: Any, where: str) -> int | str:
    """A window: a number of pages either side, or `chapter`.

    Both TOML levels and the ledger accept either, and all three keep whichever
    was written. A number that is out of range is not refused -- 999 is how you
    ask for the whole document, and `_pages` simply skips the pages that are
    not there.
    """
    if isinstance(value, str):
        word = value.strip().lower()
        if word == CHAPTER:
            return CHAPTER
        if word.lstrip("-").isdigit():
            return int(word)
        raise ConfigError(f"{where} = {value!r}; expected a number of pages or {CHAPTER!r}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} = {value!r}; expected a number of pages or {CHAPTER!r}")
    return value


def context_asked(value: int | str) -> bool:
    """Whether this level has an opinion about the window.

    A negative number is how a number says it does not; `chapter` always does.
    """
    return value == CHAPTER or (isinstance(value, int) and value >= 0)


#: What a comment has to open with to be asking for a convention rather than
#: a card. Configurable because it is a word you type while reading, in
#: whatever language you read in, and overridable per source for the same
#: reason the colour scheme is: one document is not read the way the shelf is.
CONVENTION_KEYWORD = "convention"

#: What may stand between the keyword and the proposal. Anything else means
#: the comment merely starts with the same letters.
SEPARATORS = ":-,.\u2014 \t\n"

# `units_from = "declared"`: every pair `[zotero.meanings]` names, rather than
# a list you keep in step with it by hand. For a document you mark sparingly,
# where writing a colour down at all means you expect a card out of it.
#
# Not the default, and it should not become one. The two keys answer different
# questions -- what a mark means, and whether it is worth a card -- and on a
# document marked up the usual way the answers differ: "a term to know" and "a
# citation to follow up" are meanings worth declaring for marks that are
# context, not cards. Tying them together also makes writing down what a colour
# means change what the importer does, which is a surprise nobody asked for.
#
# It cannot collide with a real entry: `_pair` refuses any bare word that is
# not a colourless kind, so `declared` is not a name a list can hold.
DECLARED = "declared"


@dataclass(frozen=True)
class ZoteroConfig:
    """Reading a marked-up PDF out of Zotero.

    `units_from` is the point of the whole section: a mark of one of these
    kinds becomes a unit, and everything else you marked on the pages around
    it comes with it. A two-word term is not a card, but it is worth reading
    next to the claim it belongs to.

    **A mark is a kind and a colour together**, and both of these keys say so.
    `meanings` maps a pair to what you meant by it, the way `[anki.flags]` maps
    a flag number, and `units_from` names the pairs worth a card of their own.
    A green highlight and a green underline are two marks a reader made
    deliberately differently, so a rule that cannot tell them apart is not the
    rule they were reading by: `units_from` once took a bare `green` or a bare
    `note`, which made "every note, whatever colour" and "green, however
    drawn" the only two things it could say, and neither of them was what
    anybody meant.

    An unmapped pair is reported rather than guessed at, for the same reason a
    flag with no entry is: a guess about what your own colours mean would be
    invisible by the time it reached a card.
    """

    data_dir: Path
    #: The pairs that start a unit, or the single marker `DECLARED`. Read it
    #: through `unit_pairs`, which resolves the marker; the marker is kept
    #: rather than expanded at load because the meanings in force are not
    #: known until a source's override has been applied over the repo's.
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)
    #: The word that turns a comment into a request for a convention. A
    #: convention governs every card written here afterwards and has no review
    #: gate of its own, so what this produces is a proposal parked for you,
    #: never a line written into `conventions.md`.
    convention_keyword: str = CONVENTION_KEYWORD

    def convention_in(self, comment: str) -> str:
        """What this comment proposes as a convention, or "".

        The keyword has to open the comment and end where it ends, so a note
        beginning "conventional choice of sign" is a note about the maths. What
        comes back is the rest of it, which is the proposal itself.
        """
        text = comment.strip()
        word = self.convention_keyword.strip()
        if not word or not text.lower().startswith(word.lower()):
            return ""
        # The character the keyword ends on, before anything is stripped:
        # stripping first eats the space that separates `convention entries
        # are real` from `conventional choice of sign`.
        tail = text[len(word) :]
        if tail[:1] and tail[:1] not in SEPARATORS:
            return ""
        return tail.lstrip(SEPARATORS).strip()

    @property
    def unit_pairs(self) -> frozenset[str]:
        """Which marks start a unit, as pairs, whatever the setting said.

        `"declared"` resolves against the meanings that ended up in force, so
        a source that declares its own colours and inherits the marker reads
        its own scheme rather than the shelf's.
        """
        if DECLARED in self.units_from:
            return frozenset(self.meanings)
        return self.units_from

    def makes_a_unit(self, kind: str, colour: str) -> bool:
        """Whether a mark of this exact kind and colour is worth its own card.

        The same pair `reading` is keyed on, built the same way, so a mark that
        has a declared meaning and a mark that starts a unit are looked up by
        one name and cannot drift apart.
        """
        return self.pair(kind, colour) in self.unit_pairs

    @staticmethod
    def pair(kind: str, colour: str) -> str:
        """`kind/colour`, or the kind alone where there is no colour to pair
        with. One place, because two spellings of a mark's name is how a
        declared meaning stops matching the rule that made the unit."""
        return f"{kind}/{colour}" if colour else kind

    def means(self, kind: str, colour: str) -> str:
        """The most specific meaning in force, defaults included."""
        return self.reading(kind, colour)[0]

    def reading(self, kind: str, colour: str) -> tuple[str, str]:
        """`(meaning, where it came from)` -- `declared` or `default`.

        **The pair decides, and only the pair.** A key is `kind/colour`; a bare
        `green` or a bare `note` is refused at load.

        It used to fall back `kind/colour` -> `kind` -> `colour`, which is two
        problems wearing one rule. A bare `highlight` silently shadowed every
        colour, so declaring what a highlight "generally" is quietly undid the
        colour scheme underneath it. And a bare `green` claimed that green
        means the same thing whether you highlighted with it or underlined with
        it -- which is exactly the distinction a second annotation kind exists
        to draw, and the reader who made both marks meant them differently.

        Under the pairs sits `DEFAULT_MEANINGS`, keyed by kind alone, and that
        one *is* a fact about the kind rather than a reading of it: it says
        what Zotero's annotation is, not what you used it for. The provenance
        comes back so a view can tell the two apart -- "you have not decided
        about this combination yet" is worth seeing. `means` throws it away.
        """
        pair = self.pair(kind, colour)
        if self.meanings.get(pair):
            return self.meanings[pair], "declared"
        fallback = DEFAULT_MEANINGS.get(kind, "")
        return (fallback, "default") if fallback else ("", "")


@dataclass(frozen=True)
class Config:
    root: Path
    cards_dir: Path
    projects_dir: Path
    work_dir: Path
    language: str
    front_char_cap: int
    crop_context: float
    crop_width: str
    context_pages: int | str
    anki_url: str
    deck: str
    note_type_name: str
    note_type_version: int
    tag_prefix: str
    extra_macros: tuple[str, ...]
    host: str
    port: int
    katex_base: str
    # The dependency canvas, `/graph`. On, because a deck with no `requires`
    # anywhere never offers the link to it and so never costs anything to have
    # enabled. Off is for somebody who has decided their cards are a flat pile
    # and does not want a third view pointing at a picture of that: the route
    # stops answering, the review view stops linking, and `requires` still
    # decides the study order exactly as before. It changes what the app shows
    # and nothing about what any file means.
    graph: bool = True
    # `[cards] study_order`: which criterion outranks which when Anki decides
    # what new card you meet next. `study.py` holds the list and the reasoning;
    # this is the sequence, already completed and validated, so nothing
    # downstream has to cope with a partial or a misspelled one.
    #
    # The one setting in this file the app writes back (the panel on the
    # canvas), because it is the one whose effect you can only judge by looking
    # at the resulting order, and the order is a hundred cards long.
    study_order: tuple[str, ...] = study.DEFAULT
    # `[app.keys]`: action name -> the key that runs it. Empty means every
    # shortcut is its default. `app/keys.py` owns the list and the reasoning;
    # this is only the override table, validated at load so a typo'd action
    # says so rather than quietly changing nothing.
    keys: dict[str, str] = field(default_factory=dict)
    # Whether whoever writes a card may look things up on the web. Off, and
    # the default is the whole point: a card is supposed to say what *this
    # source* says, and the web is where a plausible statement of the general
    # theorem comes from to quietly replace the one on the page. Turned on per
    # source, or per unit from triage, where you can see that this particular
    # unit needs it.
    web: bool = False
    # Flag number -> what you meant by it. Empty by default: a flag with no
    # meaning here is reported rather than guessed at.
    flags: dict[int, str] = field(default_factory=dict)
    projects: dict[str, ProjectConfig] = field(default_factory=dict)
    zotero: ZoteroConfig = field(
        default_factory=lambda: ZoteroConfig(data_dir=Path.home() / "Zotero")
    )

    @property
    def note_type(self) -> str:
        """The note type's name in Anki: a stem you choose, plus the version.

        Nothing here is derived from the package name. The name is written into
        every note in the collection, so it has to survive this project being
        renamed; the version stays separate because it is the lever the
        field-migration error tells you to pull.
        """
        return f"{self.note_type_name} v{self.note_type_version}"

    def project(self, name: str) -> ProjectConfig:
        try:
            return self.projects[name]
        except KeyError:
            known = ", ".join(sorted(self.projects)) or "(none)"
            raise ConfigError(f"unknown source {name!r}; configured: {known}") from None

    def zotero_for(self, project: str, document: str = "") -> ZoteroConfig:
        """This source's reading of its own marks, over the repo default.

        `data_dir` is a fact about the machine, so it never varies per source;
        the meanings do, and an override replaces rather than merges, because
        a half-inherited colour scheme is the failure this exists to prevent.

        The keyword is the third thing a source may read differently, for the
        plainest reason of the three: it is a word you type while reading, and
        you do not always read in the same language.
        """
        spec = self.projects.get(project)
        work = spec.source(document) if spec else None
        if work is None or not (work.units_from or work.meanings or work.convention_keyword):
            return self.zotero
        return ZoteroConfig(
            data_dir=self.zotero.data_dir,
            units_from=work.units_from or self.zotero.units_from,
            meanings=dict(work.meanings) or dict(self.zotero.meanings),
            convention_keyword=work.convention_keyword or self.zotero.convention_keyword,
        )

    def crop_context_for(self, project: str, document: str = "") -> float:
        """How much page to show around this source's crops.

        A fact about how a book is set: forty points frames a one-line display
        equation and cuts a theorem off mid-preamble. Falls back to the repo
        default, and then to the module's, which is deliberately generous.
        """
        from .extract.render import TRIAGE_CONTEXT

        spec = self.projects.get(project)
        work = spec.source(document) if spec else None
        return float(
            settled(work.crop_context if work else 0.0, self.crop_context, TRIAGE_CONTEXT,
                    empty=0.0)
        )

    def crop_width_for(self, project: str, from_a_mark: bool = False, document: str = "") -> str:
        """`box` or `page`: how wide this source's crops are cut.

        The default depends on where the geometry came from, because the
        left and right edges of a box mean different things in the two cases.
        A segmenter that found a display equation stopped where the equation
        stopped, so its edges are the answer. A mark's box is the union of the
        lines a sentence happened to span, so its edges are wherever that
        sentence started and stopped mid-column -- cutting there slices words
        in half and drops the paragraph that gives them their meaning.

        So a mark gets the whole page width unless the source says otherwise.
        A source that says otherwise is believed in both directions.
        """
        spec = self.projects.get(project)
        work = spec.source(document) if spec else None
        return str(
            settled(
                work.crop_width if work else "",
                self.crop_width,
                "page" if from_a_mark else "box",
                empty="",
            )
        )

    def context_pages_for(self, project: str, unit: int | str | None = None) -> int | str:
        """The window a card writer gets, most specific first.

        A number of pages either side, or `chapter`. The unit wins, because
        triage is where you can see that this theorem's hypotheses are two
        pages back. Then the source, because how much a page carries is a fact
        about how a book is set. Then the repo.
        """
        spec = self.projects.get(project)
        asked = spec.context_pages if spec and context_asked(spec.context_pages) else None
        return settled(unit, asked, self.context_pages)

    def document_for(self, project: str, document: str = "") -> Path | None:
        """The file a unit's page and bbox refer to.

        A source is one work and its files are its parts, so page 17 of one
        is not page 17 of another and the unit names its own on
        `locator.document`. An empty one means the source's only file, which
        is what a book in a single PDF always passes.

        A named file is looked for among the project's own first, then under
        Zotero's `storage/`, where each attachment has a folder to itself and
        the key is enough to find it with no filename recorded anywhere.
        """
        spec = self.projects.get(project)
        if document:
            for declared in spec.sources if spec else ():
                for path in declared.files:
                    if document in (path.name, str(path), declared.key):
                        return path
            folder = self.zotero.data_dir / "storage" / document
            files = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
            return files[0] if files else None
        work = spec.source() if spec else None
        return work.pdf if work else None

    def units_path(self, project: str) -> Path:
        return self.projects_dir / project / "units.jsonl"

    def deck_for(
        self, project: str, card_type: str = "", tags: Sequence[str] = ()
    ) -> str:
        """Which Anki deck this source's cards belong in.

        Per source, because two books are two subjects far more often than
        they are one. A card that names no source falls back to the repo
        default rather than going nowhere, and one imported from Zotero falls
        back to `Zotero::<title>`: a shelf you are reading through is not the
        deck you have decided to keep, and the parent is what makes an import
        studiable or removable in one move.

        Per *type* as well, when a source says so, because a restatement and an
        explanation want different new-card rates: five mechanical facts a day
        is comfortable and five pieces of intuition a day is not, and a
        per-deck limit is the only way Anki lets you say that. Subdecks under a
        shared parent, so studying the parent still sees both.

        And per *tag*, which is how a project on a subject splits: its cards
        are not two kinds of thing, they are about different things.
        `[decks.by_tag]` in file order, so a card carrying two of them lands
        somewhere you can predict. Re-tagging a card moves it and does not
        un-approve it, because filing is not what a reviewer read
        (ROADMAP.md 10).

        Most specific first: a tag names one card's subject, a type names a
        whole class of card, and the project's own deck is the fallback.
        """
        spec = self.projects.get(project)
        if spec:
            for tag, deck in spec.tag_decks.items():
                if tag in tags:
                    return deck
        if spec and card_type and spec.decks.get(card_type):
            return spec.decks[card_type]
        if spec and spec.deck:
            return spec.deck
        if spec and any(w.zotero_key for w in spec.sources):
            # Imported reading, which is not the deck you curated. Said here
            # rather than written into the source file, so it is one decision
            # in one place and a source overrides it by naming a deck.
            key = next(w.zotero_key for w in spec.sources if w.zotero_key)
            return zotero_deck(spec.title, key)
        return self.deck

    def conventions_for(self, project: str) -> Mapping[str, str]:
        """What is ambient in this source, as keys: `[conventions]`.

        **There is no repo-wide layer to fall back to, and that is the point.**
        A convention is a fact about one book. Defaulting one here is how a
        statistics paper came to be told it writes matrix calculus in
        denominator layout -- the silent mixing CLAUDE.md names, arriving
        through a default rather than through a mistake.
        """
        spec = self.projects.get(project)
        return dict(spec.conventions) if spec else {}

    def layout_for(self, project: str) -> str:
        """Which derivative layout this source's cards are written in.

        One entry in that source's `[conventions]`, and the only one anything
        acts on: `verify`'s numerical gradient computes denominator layout,
        the two conventions agree on every square matrix, and a mismatch would
        pass review and first bite on a rectangular one.

        **Empty is an answer.** A source that has not said gets no layout,
        `verify` refuses to run rather than checking against a guess, and a
        card from it carries no layout clause.
        """
        return self.conventions_for(project).get("layout", "")

    def web_for(self, source: str, unit: bool | None = None) -> bool:
        """Whether whoever writes this card may look things up on the web.

        Most specific first, exactly like `context_pages_for`: the unit, then
        the source, then the repo -- which is `false`.

        Off by default because the failure it prevents is invisible. A card
        should say what *this source* says, hypotheses and notation included;
        the web is full of cleaner statements of the general theorem, and one
        of those substituted for the printed one looks like a better card right
        up until the exam question turns on the condition the paper had and
        Wikipedia did not. Granting it per unit is the honest shape: you grant
        it when you can see why this particular unit needs it.
        """
        spec = self.projects.get(source)
        answer = settled(unit, spec.web if spec else None)
        if answer is not None:
            return bool(answer)
        return self.web

    def scratch(self, *parts: str) -> Path:
        """A directory for intermediate files, created on demand.

        One predictable place for crops, page renders and scratch LaTeX, so a
        pass leaves nothing behind in the repo root and a crashed agent leaves
        something obviously disposable instead of `.tx-10-hi`.
        """
        path = self.work_dir.joinpath(*parts) if parts else self.work_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


def find_root(start: Path | None = None) -> Path:
    """Nearest ancestor holding forge.toml, else the start directory."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if any((candidate / name).is_file() for name in CONFIG_NAMES):
            return candidate
    return here


def load(root: Path | None = None) -> Config:
    root = (root or find_root()).resolve()
    path = next(
        (root / name for name in CONFIG_NAMES if (root / name).is_file()),
        root / CONFIG_NAME,
    )
    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open("rb") as fh:
            raw = tomllib.load(fh)

    repo = raw.get("repo", {})
    cards = raw.get("cards", {})
    _refuse_a_repo_wide_convention(cards, path)
    anki = raw.get("anki", {})
    check = raw.get("check", {})
    app = raw.get("app", {})

    # A source's own folder is authoritative; `[projects.<name>]` in this file
    # is the older way and still works, so a repo does not have to migrate all
    # at once. Where both speak, the folder wins: it sits next to the document
    # it describes, and one file per source is what keeps a root file readable
    # once there are fifty papers in it.
    specs: dict[str, dict[str, Any]] = dict(raw.get("projects", {}))
    projects_dir = root / repo.get("projects_dir", "projects")
    for found, spec in discover_projects(projects_dir).items():
        specs.setdefault(found, {}).update(spec)

    projects: dict[str, ProjectConfig] = {}
    for name, spec in specs.items():
        _refuse_a_project_wide_document(spec, f"[projects.{name}]")
        projects[name] = ProjectConfig(
            name=name,
            title=spec.get("title", name),
            citation=spec.get("citation", spec.get("title", name)),
            sources=_sources(root, spec, f"[projects.{name}]"),
            deck=str(spec.get("deck", "") or ""),
            conventions=_conventions(spec, f"[projects.{name}]"),
            web=_opt_bool(spec.get("web")),
            order=_order(spec.get("order", "printed"), f"[projects.{name}]"),
            context_pages=context_size(
                spec.get("context_pages", -1), f"[projects.{name}] context_pages"
            ),
            decks=_deck_map(spec.get("decks"), "by_type"),
            tag_decks=_deck_map(spec.get("decks"), "by_tag"),
            tags=tuple(str(x) for x in spec.get("tags", ())),
        )

    return Config(
        root=root,
        cards_dir=root / repo.get("cards_dir", "cards"),
        projects_dir=root / repo.get("projects_dir", "projects"),
        work_dir=root / repo.get("work_dir", ".forge"),
        language=cards.get("language", "en"),
        front_char_cap=int(cards.get("front_char_cap", 160)),
        crop_context=float(cards.get("crop_context", 0.0)),
        crop_width=_crop_width(cards.get("crop_width", ""), "[cards]"),
        context_pages=context_size(cards.get("context_pages", 1), "[cards] context_pages"),
        study_order=_study_order(cards.get("study_order"), "[cards]"),
        web=bool(cards.get("web", False)),
        anki_url=os.environ.get("ANKI_CONNECT_URL", anki.get("url", "http://127.0.0.1:8765")),
        deck=anki.get("deck", "Default"),
        note_type_name=str(anki.get("note_type_name", "Math Card")),
        note_type_version=int(anki.get("note_type_version", 1)),
        tag_prefix=anki.get("tag_prefix", "forge"),
        extra_macros=tuple(check.get("extra_macros", ())),
        flags=_flags(anki.get("flags", {})),
        host=app.get("host", "127.0.0.1"),
        port=int(app.get("port", 8000)),
        katex_base=app.get("katex_base", ""),
        graph=bool(app.get("graph", True)),
        keys=_keys(app.get("keys", {})),
        projects=projects,
        zotero=_zotero(raw.get("zotero", {})),
    )


#: Keys that described the one document a project used to be, and now
#: describe one of the works it reads. Refused where they used to live rather
#: than ignored, because a `pdf` nothing reads looks exactly like a `pdf`
#: nobody wrote, and the failure would be a project that silently extracts
#: nothing. Same argument as `[cards] layout`, one level down.
MOVED_TO_A_SOURCE = (
    "pdf",
    "tex",
    "zotero",
    "documents",
    "crop_context",
    "crop_width",
    "units_from",
    "meanings",
    "convention_keyword",
)


def _refuse_a_project_wide_document(spec: Mapping[str, Any], where: str) -> None:
    for key in MOVED_TO_A_SOURCE:
        if key in spec:
            moved = "attachments" if key == "documents" else "files" if key == "pdf" else key
            raise ConfigError(
                f"{where} {key} describes a document, and a project may read several, "
                f"so it belongs in a [[sources]] table as `{moved}`"
            )


def _deck_map(raw: Any, which: str) -> dict[str, str]:
    """`[decks.by_type]` or `[decks.by_tag]`, in the order they were written.

    Two tables rather than one, because a type and a tag are different
    questions and a single map would silently answer one with the other the
    first time somebody named a tag `identity`.

    A flat `[decks]` is read as the type map, which is what it always was.
    """
    table = dict(raw or {})
    inner = table.get(which)
    if isinstance(inner, dict):
        return {str(k): str(v) for k, v in inner.items()}
    if which != "by_type":
        return {}
    # The older flat form: every key that is not one of the two sub-tables.
    return {
        str(k): str(v) for k, v in table.items() if k not in ("by_type", "by_tag")
    }


def _sources(root: Path, spec: dict[str, Any], where: str) -> tuple[SourceConfig, ...]:
    """`[[sources]]`: the works a project reads.

    One table per work, each with its own files and its own marking scheme,
    because those are facts about a document and a project may hold several.
    A project that reads nothing declares none, and that absence is what says
    it has no authoritative source; there is no kind key anywhere.
    """
    out: list[SourceConfig] = []
    for i, raw in enumerate(spec.get("sources") or ()):
        if not isinstance(raw, dict):
            raise ConfigError(f"{where} sources[{i}] is not a table")
        files = raw.get("files") or ()
        if isinstance(files, str):
            raise ConfigError(f"{where} sources[{i}] files is a list, even with one file in it")
        paths = tuple(p for p in (_opt_path(root, f) for f in files) if p is not None)
        key = str(raw.get("key", "") or raw.get("zotero", "") or "")
        if not key and paths:
            key = paths[0].name
        out.append(
            SourceConfig(
                key=key,
                title=str(raw.get("title", "") or ""),
                citation=str(raw.get("citation", "") or ""),
                url=str(raw.get("url", "") or ""),
                tex=_opt_path(root, raw.get("tex")),
                files=paths,
                zotero_key=str(raw.get("zotero", "") or ""),
                attachments=tuple(str(x) for x in raw.get("attachments", ())),
                crop_context=float(raw.get("crop_context", 0.0)),
                crop_width=_crop_width(raw.get("crop_width", ""), f"{where} sources[{i}]"),
                units_from=_units_from(
                    raw.get("units_from", ()), f"{where} sources[{i}] units_from"
                ),
                convention_keyword=str(raw.get("convention_keyword", "") or ""),
                meanings=_meanings(raw.get("meanings") or {}, f"{where} sources[{i}].meanings"),
            )
        )
    return tuple(out)


def _study_order(raw: Any, where: str) -> tuple[str, ...]:
    """`[cards] study_order`: which criterion outranks which.

    Refused at load rather than at the sort, for the same reason an unknown
    key action is: a criterion nobody recognises reads exactly like the
    setting having no effect, and the effect here is the order a deck of a
    thousand cards arrives in.

    Absent means the declared default. A partial list is completed rather than
    refused, because the list grows: naming two of three criteria is a
    statement about those two, not a claim that the third does not exist.
    """
    if raw is None:
        return study.DEFAULT
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(f"{where} study_order must be a list of criterion names")
    names = [str(x).strip() for x in raw if str(x).strip()]
    try:
        study.validate(names)
    except study.StudyOrderError as exc:
        raise ConfigError(f"{where} study_order: {exc}") from exc
    return tuple(c.name for c in study.resolve(names))


def _keys(raw: Any) -> dict[str, str]:
    """`[app.keys]`, checked against the actions that exist.

    Imported here rather than at module scope: `app.keys` is a leaf with no
    imports of its own, but `config` is imported by everything and the app
    package is not.
    """
    from .app import keys as keymap

    table = {str(k): v for k, v in dict(raw or {}).items()}
    keymap.validate(table)
    return {k: str(v) for k, v in table.items()}


PROJECT_TOML = "project.toml"
SOURCE_FILE = "source.md"  # the older form: the same TOML, between `+++` fences
CONVENTIONS_FILE = "conventions.md"
# The shelf of reference material: prose, no schema, because nothing branches
# on it. A source is read *from*; this is checked *against*.
REFERENCES_FILE = "references.md"
# What you asked for here, and the outline of what each ask should cover.
# Prose with a recognisable shape rather than a schema: a heading per
# subject, and lines under it. Nothing branches on it; `forge context` hands
# it to whoever writes a card, because the ask says what you wanted and the
# unit alone cannot.
TOPICS_FILE = "topics.md"
FENCE = "+++"


def split_source_file(path: Path) -> tuple[dict[str, Any], str]:
    """The older source file: TOML between `+++` fences, then prose.

    Kept because a repo should not have to migrate all at once, and because
    reading it is four lines. New sources are `project.toml` next to a plain
    `conventions.md`.

    The frontmatter form put both halves in one file on the argument that a
    convention kept away from the keys it qualifies is the one nobody opens.
    What it actually produced was a file that is neither: no editor gives you
    TOML checking above the fence *and* Markdown below it, so both halves lost
    the tooling they would have had apart. The keys are a config file and the
    conventions are a document, and they are better off being those things.
    """
    lines = path.read_text(encoding="utf-8").lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != FENCE:
        raise ConfigError(f"{path} has no frontmatter; a source file starts with `{FENCE}`")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == FENCE)
    except StopIteration:
        raise ConfigError(f"{path}: the frontmatter block is never closed") from None
    try:
        loaded = tomllib.loads("\n".join(lines[1:end]))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: frontmatter is not valid TOML: {exc}") from exc
    return loaded, "\n".join(lines[end + 1 :])


def read_source_toml(path: Path) -> dict[str, Any]:
    """`projects/<name>/project.toml`: plain TOML, no fences.

    TOML rather than YAML because every key here overrides one in
    `forge.toml`, and a block copied between the two has to work unchanged. It
    is also the stricter language, which matters for exactly this data: in YAML
    a colour or tag written `no`, `on` or `y` is silently a boolean.
    """
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc


def discover_projects(projects_dir: Path) -> dict[str, dict[str, Any]]:
    """Every `projects/<name>/project.toml`, and the older `source.md` beside it.

    A folder with neither is not a source. Discovery is not a guess.
    """
    found: dict[str, dict[str, Any]] = {}
    if not projects_dir.is_dir():
        return found
    for path in sorted(projects_dir.glob(f"*/{SOURCE_FILE}")):
        found[path.parent.name] = split_source_file(path)[0]
    # Second, and therefore winning where a folder still has both: the file
    # you are being migrated *to* is the one that should decide.
    for path in sorted(projects_dir.glob(f"*/{PROJECT_TOML}")):
        found[path.parent.name] = read_source_toml(path)
    return found


def _pair(name: str, where: str) -> str:
    """One `kind/colour`, refused if it names only half of a mark.

    Shared by `[zotero.meanings]` and `units_from`, because they name the same
    thing and a rule that accepted a looser spelling than the meanings table
    would let a source declare what `highlight/green` means and then make units
    of something else.

    A colourless kind is the one exception, and it is not an abbreviation: an
    `ink` mark has no colour to pair with, so `ink` *is* the pair.
    """
    kind, slash, colour = name.partition("/")
    if not slash and name not in COLOURLESS_KINDS:
        from .zotero import HEX_BY_NAME

        hint = (
            f"a colour needs the kind it was drawn with, e.g. highlight/{name}"
            if name in HEX_BY_NAME
            else f"a kind needs the colour, e.g. {name}/green"
        )
        raise ConfigError(
            f"{where} {name!r} names only half of a mark; {hint}. "
            "The pair decides: a bare kind covers every colour under it, and a "
            "bare colour claims that green means the same highlighted as "
            "underlined."
        )
    if slash and not (kind and colour):
        raise ConfigError(f"{where} {name!r} is not a kind/colour pair")
    return name


def _units_from(raw: Any, where: str) -> frozenset[str]:
    """Which marks start a unit: a list of pairs, or the word `declared`.

    Validated here rather than at the first import, because the failure it
    prevents is silent: a list that names nothing your PDF actually carries
    imports zero units and looks exactly like a paper you never marked up.

    The word is a string and not a list entry on purpose. A list stays a list
    of pairs with no exceptions in it, which is the rule the whole key exists
    to keep; a keyword allowed inside one would be the loose spelling coming
    back through a side door.
    """
    if isinstance(raw, str):
        if raw != DECLARED:
            raise ConfigError(
                f"{where} {raw!r} is not a list of marks. Name them as "
                f'`["highlight/green", ...]`, or write {DECLARED!r} to take '
                "every pair the meanings table declares."
            )
        return frozenset({DECLARED})
    return frozenset(_pair(str(x).strip(), where) for x in raw or ())


def _meanings(raw: Any, where: str) -> dict[str, str]:
    """`kind/colour = "..."`, and nothing shorter.

    A bare key is refused rather than read loosely, because both loose forms
    were wrong in ways you would not notice. `highlight = "..."` shadowed every
    colour under it, so writing down what a highlight generally is quietly
    undid the scheme you had built out of colours. `green = "..."` claimed that
    green means one thing whether you highlighted with it or underlined with
    it -- which is precisely the distinction a second annotation kind exists to
    draw, and the reader who made both marks meant them differently.

    A colourless kind is the one exception, and it is not an abbreviation: an
    `ink` mark has no colour to pair with, so `ink` *is* the pair.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key).strip()
        text = str(value or "").strip()
        if not text:
            continue
        out[_pair(name, where)] = text
    return out


def _zotero(raw: Any) -> ZoteroConfig:
    section = raw if isinstance(raw, dict) else {}
    data_dir = str(section.get("data_dir", "") or "~/Zotero")
    return ZoteroConfig(
        data_dir=Path(data_dir).expanduser(),
        units_from=_units_from(section.get("units_from", ()), "[zotero] units_from"),
        meanings=_meanings(section.get("meanings", {}), "[zotero.meanings]"),
        convention_keyword=str(
            section.get("convention_keyword", CONVENTION_KEYWORD) or CONVENTION_KEYWORD
        ),
    )


def _flags(raw: Any) -> dict[int, str]:
    """`[anki.flags]` keys are TOML strings; Anki numbers its flags 1-7."""
    flags: dict[int, str] = {}
    for key, value in dict(raw or {}).items():
        try:
            number = int(str(key))
        except ValueError:
            raise ConfigError(f"[anki.flags] key {key!r} is not a flag number") from None
        if not 1 <= number <= 7:
            raise ConfigError(f"[anki.flags] {number} is not a flag; Anki has 1 to 7")
        text = str(value or "").strip()
        if text:
            flags[number] = text
    return flags


def _conventions(spec: Mapping[str, Any], where: str) -> dict[str, str]:
    """`[conventions]` for one source, with the older top-level `layout`.

    Any key is accepted: what is ambient in a source is not a vocabulary this
    tool can enumerate. `layout` is checked because something acts on it, and a
    typo there would read as "not denominator" and silently change what every
    derivative on every card from this source means.

    A top-level `layout = ` is still read, since that is where it used to live
    and a repo should not have to migrate in the same sitting as the tool. The
    table wins where both speak.
    """
    table = spec.get("conventions")
    out = {str(k): str(v).strip() for k, v in dict(table or {}).items() if str(v).strip()}
    legacy = str(spec.get("layout", "") or "").strip()
    if legacy and "layout" not in out:
        out["layout"] = legacy
    if "layout" in out:
        out["layout"] = _layout(out["layout"], f"{where} [conventions]")
    return out


def _refuse_a_repo_wide_convention(cards: Mapping[str, Any], path: Path) -> None:
    """`[cards] layout` is gone, and silence would be the wrong way to say so.

    It was the repo-wide default for a matrix-calculus convention, which is a
    claim about every book in the deck including the ones nobody has read yet.
    Ignoring a value somebody wrote there would leave `verify` checking against
    a guess while the file said otherwise -- exactly the failure the key was
    added to prevent.
    """
    if str(cards.get("layout", "") or "").strip():
        raise ConfigError(
            f"{path}: [cards] layout is no longer read. A layout is a fact about "
            "one book, not a repo-wide default -- move it to that source's "
            "`projects/<name>/project.toml`, under [conventions]."
        )


def _opt_bool(value: Any) -> bool | None:
    """A tri-state TOML flag: true, false, or absent meaning "inherit"."""
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ConfigError(f"expected true or false, got {value!r}")
    return value


def _order(value: Any, where: str) -> str:
    text = str(value or "printed").strip()
    if text not in ORDERS:
        raise ConfigError(
            f"{where} order = {text!r}; expected one of {', '.join(ORDERS)}"
        )
    return text


def _layout(value: Any, where: str) -> str:
    text = str(value or "").strip()
    if text and text not in LAYOUTS:
        raise ConfigError(
            f"{where} layout = {text!r}; expected one of {', '.join(LAYOUTS)}. "
            "A layout that is not recognised would silently be treated as "
            "'not denominator' and change what every card from it means."
        )
    return text


def _crop_width(value: Any, where: str) -> str:
    """`box`, `page`, or unset. Refused rather than guessed at, for the same
    reason `layout` is: an unrecognised value would fall through to whichever
    branch happens to be the `else`, and you would find out by wondering why
    half the crops look wrong."""
    from .extract.render import WIDTHS

    text = str(value or "").strip()
    if text and text not in WIDTHS:
        raise ConfigError(f"{where} crop_width = {text!r}; expected one of {', '.join(WIDTHS)}")
    return text


def _opt_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else root / p


# -- writing one setting back ------------------------------------------------

#: The comment written above `study_order` when this creates the line. Only
#: then: an edit of an existing line leaves whatever is written around it
#: alone, because that prose may have been written by hand.
STUDY_ORDER_NOTE = (
    "# Which criterion outranks which when Anki decides what new card you meet\n"
    "# next. `requires` comes before all of them and the uid settles a tie;\n"
    "# `src/anki_math_forge/study.py` has the list and the reasoning. The panel\n"
    "# on the canvas at /graph writes this line.\n"
)


def config_path(root: Path) -> Path:
    """The config file this root is configured by, existing or not."""
    return next(
        (root / name for name in CONFIG_NAMES if (root / name).is_file()),
        root / CONFIG_NAME,
    )


def save_study_order(root: Path, order: Sequence[str]) -> Path:
    """Write `[cards] study_order` into `forge.toml`, leaving the rest alone.

    A line edit rather than a dump of the parsed document. This config is
    mostly commentary: it explains the four values that are decisions rather
    than defaults, and re-serialising it from `tomllib` would delete every word
    of that to change three items in a list. So the table is found, the one
    line is replaced or inserted, and every other byte in the file survives.

    The only setting written from the app, and that is deliberate. The
    keyboard map and the source list are edits you make once with an editor
    open; this one is judged by looking at the order it produces, which is why
    there is a panel for it at all.
    """
    order = tuple(c.name for c in study.resolve(list(order)))
    path = config_path(root)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = "study_order = [" + ", ".join(f'"{name}"' for name in order) + "]\n"
    lines = text.splitlines(keepends=True)

    start = next(
        (i for i, raw in enumerate(lines) if raw.strip() == "[cards]"),
        None,
    )
    if start is None:
        # No `[cards]` table at all. Appending one is valid wherever the file
        # ends: a table header closes whatever table preceded it.
        joined = text if text.endswith("\n") or not text else text + "\n"
        new = f"{joined}\n[cards]\n{STUDY_ORDER_NOTE}{line}"
    else:
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
            len(lines),
        )
        at = next(
            (
                i
                for i in range(start + 1, end)
                if lines[i].lstrip().startswith("study_order")
                and "=" in lines[i]
            ),
            None,
        )
        if at is None:
            new = (
                "".join(lines[: start + 1])
                + STUDY_ORDER_NOTE
                + line
                + "".join(lines[start + 1 :])
            )
        else:
            # The value may have been written across more than one line by
            # hand, so the replacement consumes until the array closes rather
            # than assuming one line and leaving a stray `]` behind.
            stop = at
            depth = 0
            for i in range(at, end):
                depth += lines[i].count("[") - lines[i].count("]")
                stop = i
                if depth <= 0:
                    break
            new = "".join(lines[:at]) + line + "".join(lines[stop + 1 :])

    from .model import write_atomic

    write_atomic(path, new)
    return path
