"""Configuration: one TOML at the repo root (DESIGN.md ss11)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "anki-forge.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SourceConfig:
    name: str
    title: str
    citation: str
    tex: Path | None
    pdf: Path | None

    @property
    def dir_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class Config:
    root: Path
    cards_dir: Path
    sources_dir: Path
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
        )

    return Config(
        root=root,
        cards_dir=root / repo.get("cards_dir", "cards"),
        sources_dir=root / repo.get("sources_dir", "sources"),
        language=cards.get("language", "en"),
        layout=cards.get("layout", "denominator"),
        front_char_cap=int(cards.get("front_char_cap", 160)),
        anki_url=os.environ.get("ANKI_CONNECT_URL", anki.get("url", "http://127.0.0.1:8765")),
        deck=anki.get("deck", "Default"),
        note_type_version=int(anki.get("note_type_version", 1)),
        tag_prefix=anki.get("tag_prefix", "forge"),
        extra_macros=tuple(check.get("extra_macros", ())),
        host=app.get("host", "127.0.0.1"),
        port=int(app.get("port", 8000)),
        katex_base=app.get("katex_base", ""),
        sources=sources,
    )


def _opt_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else root / p
