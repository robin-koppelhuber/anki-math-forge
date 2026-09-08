"""Configuration: one TOML at the repo root (DESIGN.md ss11)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "anki-forge.toml"

# Which layout a derivative is written in. A typo here would read as
# "not denominator" and silently change what every card means, so it is
# refused at load rather than discovered by a wrong `verify`.
LAYOUTS = ("denominator", "numerator")


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

    @property
    def dir_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class Config:
    root: Path
    cards_dir: Path
    sources_dir: Path
    work_dir: Path
    language: str
    layout: str
    front_char_cap: int
    anki_url: str
    deck: str
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

    @property
    def note_type(self) -> str:
        return f"anki-forge identity v{self.note_type_version}"

    def source(self, name: str) -> SourceConfig:
        try:
            return self.sources[name]
        except KeyError:
            known = ", ".join(sorted(self.sources)) or "(none)"
            raise ConfigError(f"unknown source {name!r}; configured: {known}") from None

    def units_path(self, source: str) -> Path:
        return self.sources_dir / source / "units.jsonl"

    def deck_for(self, source: str) -> str:
        """Which Anki deck this source's cards belong in.

        Per source, because two books are two subjects far more often than
        they are one. A card that names no source falls back to the repo
        default rather than going nowhere.
        """
        spec = self.sources.get(source)
        return spec.deck if spec and spec.deck else self.deck

    def layout_for(self, source: str) -> str:
        """Which derivative layout this source's cards are written in.

        `[cards] layout` is the default and a source overrides it. Mixing the
        two silently is the failure that poisons a deck: on a square matrix
        the conventions are indistinguishable, so the error survives review
        and first bites on a rectangular one.
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
    """Nearest ancestor holding anki-forge.toml, else the start directory."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return here


def load(root: Path | None = None) -> Config:
    root = (root or find_root()).resolve()
    path = root / CONFIG_NAME
    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open("rb") as fh:
            raw = tomllib.load(fh)

    repo = raw.get("repo", {})
    cards = raw.get("cards", {})
    anki = raw.get("anki", {})
    check = raw.get("check", {})
    app = raw.get("app", {})

    sources: dict[str, SourceConfig] = {}
    for name, spec in raw.get("sources", {}).items():
        sources[name] = SourceConfig(
            name=name,
            title=spec.get("title", name),
            citation=spec.get("citation", spec.get("title", name)),
            tex=_opt_path(root, spec.get("tex")),
            pdf=_opt_path(root, spec.get("pdf")),
            deck=str(spec.get("deck", "") or ""),
            layout=_layout(spec.get("layout", ""), f"[sources.{name}]"),
        )

    return Config(
        root=root,
        cards_dir=root / repo.get("cards_dir", "cards"),
        sources_dir=root / repo.get("sources_dir", "sources"),
        work_dir=root / repo.get("work_dir", ".forge"),
        language=cards.get("language", "en"),
        layout=_layout(cards.get("layout", "denominator"), "[cards]") or "denominator",
        front_char_cap=int(cards.get("front_char_cap", 160)),
        anki_url=os.environ.get("ANKI_CONNECT_URL", anki.get("url", "http://127.0.0.1:8765")),
        deck=anki.get("deck", "Default"),
        note_type_version=int(anki.get("note_type_version", 1)),
        tag_prefix=anki.get("tag_prefix", "forge"),
        extra_macros=tuple(check.get("extra_macros", ())),
        flags=_flags(anki.get("flags", {})),
        host=app.get("host", "127.0.0.1"),
        port=int(app.get("port", 8000)),
        katex_base=app.get("katex_base", ""),
        sources=sources,
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


def _layout(value: Any, where: str) -> str:
    text = str(value or "").strip()
    if text and text not in LAYOUTS:
        raise ConfigError(
            f"{where} layout = {text!r}; expected one of {', '.join(LAYOUTS)}. "
            "A layout that is not recognised would silently be treated as "
            "'not denominator' and change what every card from it means."
        )
    return text


def _opt_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else root / p
