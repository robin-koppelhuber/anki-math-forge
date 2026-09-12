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
LAYOUTS = ("denominator", "numerator")

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
    # Empty means "inherit the repo default". Both of these are facts about
    # one book, not about this tool: which layout its derivatives use, and
    # which deck its cards belong in. A repo with one source never sets them.
    deck: str = ""
    layout: str = ""
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
    tags: tuple[str, ...] = ()
    # What this source's marks mean, overriding the repo-wide `[zotero]`.
    # Colour schemes drift between a book you read last year and a paper you
    # read last week, and a scheme that is wrong is worse than none.
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)

    @property
    def dir_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class ZoteroConfig:
    """Reading a marked-up PDF out of Zotero.

    `units_from` is the point of the whole section: a mark of one of these
    colours or kinds becomes a unit, and everything else you marked on the
    pages around it comes with it. A two-word term is not a card, but it is
    worth reading next to the claim it belongs to.

    `meanings` maps a colour or an annotation kind to what you meant by it,
    exactly as `[anki.flags]` maps a flag number. An unmapped one is reported
    rather than guessed at, for the same reason: a guess about what your own
    colour scheme means would be invisible once it reached a card.
    """

    data_dir: Path
    units_from: frozenset[str] = frozenset()
    meanings: Mapping[str, str] = field(default_factory=dict)

    def makes_a_unit(self, kind: str, colour: str) -> bool:
        """Whether a mark of this kind or colour is worth a card of its own."""
        return kind in self.units_from or colour in self.units_from

    def means(self, kind: str, colour: str) -> str:
        """The most specific meaning recorded, or empty when there is none.

        `kind/colour`, then `kind`, then `colour`. Kind first because it is a
        small closed set that Zotero defines, while colour is the dimension you
        assign: a yellow sticky note is a note, and reading it as "yellow" gave
        it whatever yellow means for highlights. The consequence to know is
        that a bare `highlight` entry shadows every colour, so leave it unset
        if you want colours to decide within highlights.
        """
        for probe in (f"{kind}/{colour}", kind, colour):
            if self.meanings.get(probe):
                return self.meanings[probe]
        return ""


@dataclass(frozen=True)
class Config:
    root: Path
    cards_dir: Path
    sources_dir: Path
    work_dir: Path
    language: str
    layout: str
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

    def layout_for(self, source: str) -> str:
        """Which derivative layout this source's cards are written in.

        `[cards] layout` is the default and a source overrides it. Mixing the
        two silently is the failure that poisons a deck: on a square matrix
        the conventions are indistinguishable, so the error survives review
        and first bites on a rectangular one.

        **Empty is an answer.** It used to default to `denominator`, so a
        statistics paper that had declared nothing was told it writes matrix
        calculus in denominator layout -- the same silent mixing, arriving
        through the default rather than through a mistake. A source that has
        not said gets no layout, `verify` refuses to run rather than checking
        against a guess, and a card from it carries no layout clause.
        """
        spec = self.sources.get(source)
        return spec.layout if spec and spec.layout else self.layout

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
            layout=_layout(spec.get("layout", ""), f"[sources.{name}]"),
            order=_order(spec.get("order", "printed"), f"[sources.{name}]"),
            crop_context=float(spec.get("crop_context", 0.0)),
            crop_width=_crop_width(spec.get("crop_width", ""), f"[sources.{name}]"),
            context_pages=int(spec.get("context_pages", -1)),
            zotero_key=str(spec.get("zotero", "") or ""),
            decks={str(k): str(v) for k, v in (spec.get("decks") or {}).items()},
            tags=tuple(str(x) for x in spec.get("tags", ())),
            units_from=frozenset(str(x) for x in spec.get("units_from", ())),
            meanings={str(k): str(v) for k, v in (spec.get("meanings") or {}).items()},
        )

    return Config(
        root=root,
        cards_dir=root / repo.get("cards_dir", "cards"),
        sources_dir=root / repo.get("sources_dir", "sources"),
        work_dir=root / repo.get("work_dir", ".forge"),
        language=cards.get("language", "en"),
        layout=_layout(cards.get("layout", ""), "[cards]"),
        front_char_cap=int(cards.get("front_char_cap", 160)),
        crop_context=float(cards.get("crop_context", 0.0)),
        crop_width=_crop_width(cards.get("crop_width", ""), "[cards]"),
        context_pages=int(cards.get("context_pages", 1)),
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
        sources=sources,
        zotero=_zotero(raw.get("zotero", {})),
    )


SOURCE_FILE = "source.md"
FENCE = "+++"


def split_source_file(path: Path) -> tuple[dict[str, Any], str]:
    """A source file: TOML between `+++` fences, then prose.

    **TOML, not YAML**, because everything above the fence overrides a key in
    `forge.toml` and the two should be the same language: a block you copy
    from one to the other has to work unchanged. TOML is also the stricter of
    the two, which matters for exactly this data. In YAML a colour or tag
    written `no`, `on` or `y` is silently a boolean.

    Frontmatter rather than a separate `source.toml`, because a source is two
    things at once: the keys this tool acts on, and the conventions a card
    writer has to read. Splitting them by kind only meant the prose half was
    the half nobody opened. It is `+++` rather than `---` so the fence says
    which language is inside it.
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


def discover_sources(sources_dir: Path) -> dict[str, dict[str, Any]]:
    """Every `sources/<name>/source.md`.

    A folder with no such file is not a source. Discovery is not a guess.
    """
    found: dict[str, dict[str, Any]] = {}
    if not sources_dir.is_dir():
        return found
    for path in sorted(sources_dir.glob(f"*/{SOURCE_FILE}")):
        found[path.parent.name] = split_source_file(path)[0]
    return found


def _zotero(raw: Any) -> ZoteroConfig:
    section = raw if isinstance(raw, dict) else {}
    data_dir = str(section.get("data_dir", "") or "~/Zotero")
    meanings = section.get("meanings", {})
    return ZoteroConfig(
        data_dir=Path(data_dir).expanduser(),
        units_from=frozenset(str(t) for t in section.get("units_from", ())),
        meanings=(
            {str(k): str(v) for k, v in meanings.items()} if isinstance(meanings, dict) else {}
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
