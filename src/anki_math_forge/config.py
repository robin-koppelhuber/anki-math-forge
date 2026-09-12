"""Configuration: one TOML at the repo root (DESIGN.md ss11)."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

# The conventions table: `[conventions]` in `source.toml`, free-form.
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


@dataclass(frozen=True)
class SourceConfig:
    name: str
    title: str
    citation: str
    tex: Path | None
    pdf: Path | None
    # Empty means "inherit the repo default": which deck this source's cards
    # belong in. A repo with one source never sets it.
    deck: str = ""
    order: str = "printed"
    # Points of page shown around this source's crops; 0 inherits.
    crop_context: float = 0.0
    # `box` or `page`; empty inherits, and what it inherits depends on where
    # the geometry came from -- see `Config.crop_width_for`.
    crop_width: str = ""
    # Pages either side handed to a card writer; -1 inherits.
    context_pages: int = -1
    # The Zotero item this source was imported from, when it was. Not used to
    # find anything -- the units carry their own attachment keys -- but it is
    # what makes "where did this come from" answerable without opening Zotero.
    zotero_key: str = ""
    # Card type -> deck, for a source whose restatements and explanations want
    # different new-card rates. Empty means every type lands in `deck`.
    decks: Mapping[str, str] = field(default_factory=dict)
    # Free labels, so a picker with fifty papers in it can be narrowed. Not a
    # hierarchy: a source is one thing that may be several kinds of thing.
    # **Yours to invent.** Nothing writes one for you: a label the tool made up
    # is a label that means whatever the tool guessed, and you would be
    # filtering by it without ever having decided what it says.
    tags: tuple[str, ...] = ()
    # Which of a Zotero item's attachments to read, by title or by key. Empty
    # means all of them, which is right until it is not: an item routinely
    # carries the paper and a preprint of the paper, and marks made in one are
    # not marks in the other.
    documents: tuple[str, ...] = ()
    # What this source's marks mean, overriding the repo-wide `[zotero]`.
    # Colour schemes drift between a book you read last year and a paper you
    # read last week, and a scheme that is wrong is worse than none.
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)
    # What is ambient in this source, as keys rather than prose: `[conventions]`
    # in `source.toml`. Free-form -- see `CONVENTIONS_ACTED_ON`. There is no
    # repo-wide counterpart, deliberately: a default convention is a claim
    # about a book nobody has read yet.
    conventions: Mapping[str, str] = field(default_factory=dict)
    # Whether whoever writes a card from this source may look things up on the
    # web. `None` inherits the repo setting, which is off.
    web: bool | None = None

    @property
    def dir_name(self) -> str:
        return self.name

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
# repo-wide in `[zotero.meanings]`, or per source in `source.toml` -- sits on
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


@dataclass(frozen=True)
class ZoteroConfig:
    """Reading a marked-up PDF out of Zotero.

    `units_from` is the point of the whole section: a mark of one of these
    colours or kinds becomes a unit, and everything else you marked on the
    pages around it comes with it. A two-word term is not a card, but it is
    worth reading next to the claim it belongs to.

    `meanings` maps a **kind and colour together** to what you meant by it,
    the way `[anki.flags]` maps a flag number. Both halves, always: a green
    highlight and a green underline are two marks a reader made deliberately
    differently, and a scheme that cannot tell them apart is not the scheme
    they were using. An unmapped pair is reported rather than guessed at, for
    the same reason a flag with no entry is: a guess about what your own
    colours mean would be invisible by the time it reached a card.
    """

    data_dir: Path
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)

    def makes_a_unit(self, kind: str, colour: str) -> bool:
        """Whether a mark of this kind or colour is worth a card of its own."""
        return kind in self.units_from or colour in self.units_from

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
        pair = f"{kind}/{colour}" if colour else kind
        if self.meanings.get(pair):
            return self.meanings[pair], "declared"
        fallback = DEFAULT_MEANINGS.get(kind, "")
        return (fallback, "default") if fallback else ("", "")


@dataclass(frozen=True)
class Config:
    root: Path
    cards_dir: Path
    sources_dir: Path
    work_dir: Path
    language: str
    front_char_cap: int
    crop_context: float
    crop_width: str
    context_pages: int
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
    sources: dict[str, SourceConfig] = field(default_factory=dict)
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

    def source(self, name: str) -> SourceConfig:
        try:
            return self.sources[name]
        except KeyError:
            known = ", ".join(sorted(self.sources)) or "(none)"
            raise ConfigError(f"unknown source {name!r}; configured: {known}") from None

    def zotero_for(self, source: str) -> ZoteroConfig:
        """This source's reading of its own marks, over the repo default.

        `data_dir` is a fact about the machine, so it never varies per source;
        the meanings do, and an override replaces rather than merges, because
        a half-inherited colour scheme is the failure this exists to prevent.
        """
        spec = self.sources.get(source)
        if spec is None or (not spec.units_from and not spec.meanings):
            return self.zotero
        return ZoteroConfig(
            data_dir=self.zotero.data_dir,
            units_from=spec.units_from or self.zotero.units_from,
            meanings=dict(spec.meanings) or dict(self.zotero.meanings),
        )

    def crop_context_for(self, source: str) -> float:
        """How much page to show around this source's crops.

        A fact about how a book is set: forty points frames a one-line display
        equation and cuts a theorem off mid-preamble. Falls back to the repo
        default, and then to the module's, which is deliberately generous.
        """
        from .extract.render import TRIAGE_CONTEXT

        spec = self.sources.get(source)
        if spec and spec.crop_context:
            return spec.crop_context
        return self.crop_context or TRIAGE_CONTEXT

    def crop_width_for(self, source: str, from_a_mark: bool = False) -> str:
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
        spec = self.sources.get(source)
        if spec and spec.crop_width:
            return spec.crop_width
        if self.crop_width:
            return self.crop_width
        return "page" if from_a_mark else "box"

    def context_pages_for(self, source: str, unit: int | None = None) -> int:
        """How many pages either side a card writer gets, most specific first.

        The unit wins, because triage is where you can see that this theorem's
        hypotheses are two pages back. Then the source, because how much a page
        carries is a fact about how a book is set. Then the repo.
        """
        if unit is not None:
            return unit
        spec = self.sources.get(source)
        if spec and spec.context_pages >= 0:
            return spec.context_pages
        return self.context_pages

    def document_for(self, source: str, document: str = "") -> Path | None:
        """The file a unit's page and bbox refer to.

        A source used to be one document, so `source.pdf` answered this. A
        Zotero item is routinely several -- a paper and its appendix, a book as
        fifteen chapter PDFs -- and page 17 of one is not page 17 of another,
        so the unit names its own on `locator.document`.

        Zotero keeps each attachment in its own folder under `storage/`, one
        file per folder, so the key is enough to find it and no filename has to
        be recorded anywhere.
        """
        if document:
            folder = self.zotero.data_dir / "storage" / document
            files = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
            return files[0] if files else None
        spec = self.sources.get(source)
        return spec.pdf if spec else None

    def units_path(self, source: str) -> Path:
        return self.sources_dir / source / "units.jsonl"

    def deck_for(self, source: str, card_type: str = "") -> str:
        """Which Anki deck this source's cards belong in.

        Per source, because two books are two subjects far more often than
        they are one. A card that names no source falls back to the repo
        default rather than going nowhere.

        Per *type* as well, when a source says so, because a restatement and an
        explanation want different new-card rates: five mechanical facts a day
        is comfortable and five pieces of intuition a day is not, and a
        per-deck limit is the only way Anki lets you say that. Subdecks under a
        shared parent, so studying the parent still sees both.
        """
        spec = self.sources.get(source)
        if spec and card_type and spec.decks.get(card_type):
            return spec.decks[card_type]
        return spec.deck if spec and spec.deck else self.deck

    def conventions_for(self, source: str) -> Mapping[str, str]:
        """What is ambient in this source, as keys: `[conventions]`.

        **There is no repo-wide layer to fall back to, and that is the point.**
        A convention is a fact about one book. Defaulting one here is how a
        statistics paper came to be told it writes matrix calculus in
        denominator layout -- the silent mixing CLAUDE.md names, arriving
        through a default rather than through a mistake.
        """
        spec = self.sources.get(source)
        return dict(spec.conventions) if spec else {}

    def layout_for(self, source: str) -> str:
        """Which derivative layout this source's cards are written in.

        One entry in that source's `[conventions]`, and the only one anything
        acts on: `verify`'s numerical gradient computes denominator layout,
        the two conventions agree on every square matrix, and a mismatch would
        pass review and first bite on a rectangular one.

        **Empty is an answer.** A source that has not said gets no layout,
        `verify` refuses to run rather than checking against a guess, and a
        card from it carries no layout clause.
        """
        return self.conventions_for(source).get("layout", "")

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
        if unit is not None:
            return unit
        spec = self.sources.get(source)
        if spec is not None and spec.web is not None:
            return spec.web
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

    # A source's own folder is authoritative; `[sources.<name>]` in this file
    # is the older way and still works, so a repo does not have to migrate all
    # at once. Where both speak, the folder wins: it sits next to the document
    # it describes, and one file per source is what keeps a root file readable
    # once there are fifty papers in it.
    specs: dict[str, dict[str, Any]] = dict(raw.get("sources", {}))
    sources_dir = root / repo.get("sources_dir", "sources")
    for found, spec in discover_sources(sources_dir).items():
        specs.setdefault(found, {}).update(spec)

    sources: dict[str, SourceConfig] = {}
    for name, spec in specs.items():
        sources[name] = SourceConfig(
            name=name,
            title=spec.get("title", name),
            citation=spec.get("citation", spec.get("title", name)),
            tex=_opt_path(root, spec.get("tex")),
            pdf=_opt_path(root, spec.get("pdf")),
            deck=str(spec.get("deck", "") or ""),
            conventions=_conventions(spec, f"[sources.{name}]"),
            web=_opt_bool(spec.get("web")),
            order=_order(spec.get("order", "printed"), f"[sources.{name}]"),
            crop_context=float(spec.get("crop_context", 0.0)),
            crop_width=_crop_width(spec.get("crop_width", ""), f"[sources.{name}]"),
            context_pages=int(spec.get("context_pages", -1)),
            zotero_key=str(spec.get("zotero", "") or ""),
            decks={str(k): str(v) for k, v in (spec.get("decks") or {}).items()},
            tags=tuple(str(x) for x in spec.get("tags", ())),
            documents=tuple(str(x) for x in spec.get("documents", ())),
            units_from=frozenset(str(x) for x in spec.get("units_from", ())),
            meanings=_meanings(spec.get("meanings") or {}, f"[sources.{name}.meanings]"),
        )

    return Config(
        root=root,
        cards_dir=root / repo.get("cards_dir", "cards"),
        sources_dir=root / repo.get("sources_dir", "sources"),
        work_dir=root / repo.get("work_dir", ".forge"),
        language=cards.get("language", "en"),
        front_char_cap=int(cards.get("front_char_cap", 160)),
        crop_context=float(cards.get("crop_context", 0.0)),
        crop_width=_crop_width(cards.get("crop_width", ""), "[cards]"),
        context_pages=int(cards.get("context_pages", 1)),
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
        sources=sources,
        zotero=_zotero(raw.get("zotero", {})),
    )


SOURCE_TOML = "source.toml"
SOURCE_FILE = "source.md"  # the older form: the same TOML, between `+++` fences
CONVENTIONS_FILE = "conventions.md"
FENCE = "+++"


def split_source_file(path: Path) -> tuple[dict[str, Any], str]:
    """The older source file: TOML between `+++` fences, then prose.

    Kept because a repo should not have to migrate all at once, and because
    reading it is four lines. New sources are `source.toml` next to a plain
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
    """`sources/<name>/source.toml`: plain TOML, no fences.

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


def discover_sources(sources_dir: Path) -> dict[str, dict[str, Any]]:
    """Every `sources/<name>/source.toml`, and the older `source.md` beside it.

    A folder with neither is not a source. Discovery is not a guess.
    """
    found: dict[str, dict[str, Any]] = {}
    if not sources_dir.is_dir():
        return found
    for path in sorted(sources_dir.glob(f"*/{SOURCE_FILE}")):
        found[path.parent.name] = split_source_file(path)[0]
    # Second, and therefore winning where a folder still has both: the file
    # you are being migrated *to* is the one that should decide.
    for path in sorted(sources_dir.glob(f"*/{SOURCE_TOML}")):
        found[path.parent.name] = read_source_toml(path)
    return found


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
                "The pair decides what a mark means: a bare kind used to shadow "
                "every colour under it, and a bare colour claimed that green "
                "means the same highlighted as underlined."
            )
        if slash and not (kind and colour):
            raise ConfigError(f"{where} {name!r} is not a kind/colour pair")
        out[name] = text
    return out


def _zotero(raw: Any) -> ZoteroConfig:
    section = raw if isinstance(raw, dict) else {}
    data_dir = str(section.get("data_dir", "") or "~/Zotero")
    return ZoteroConfig(
        data_dir=Path(data_dir).expanduser(),
        units_from=frozenset(str(t) for t in section.get("units_from", ())),
        meanings=_meanings(section.get("meanings", {}), "[zotero.meanings]"),
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
            "`sources/<name>/source.toml`, under [conventions]."
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
