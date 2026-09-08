"""The page an equation was printed on.

The crop is authoritative for what is printed, and silent about everything
printed around it -- and an identity's conditions are usually printed around
it, as a sentence, not inside the equation. So hand over the page.

That is the whole idea. Deciding which sentence bears on this equation, and
whether the identity needs a condition the page never states, is mathematics.
It belongs to whoever is writing the card, not to a keyword list here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import Config
from .extract import source_text_path
from .ledger import open_ledgers


@dataclass
class UnitContext:
    unit: str
    locator: str
    transcription: str
    conventions: str
    page_text: str
    page_units: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "locator": self.locator,
            "transcription": self.transcription,
            "conventions": self.conventions,
            "page_text": self.page_text,
            "page_units": self.page_units,
        }

    def format(self) -> str:
        out = [f"{self.unit}  {self.locator}"]
        if self.transcription:
            out.append(f"\n  {self.transcription}")
        out.append(
            "\n## the setting this source is read in\n"
            + (
                self.conventions
                or "(none recorded -- write sources/<name>/conventions.md, or"
                " whoever writes a card here is guessing at what is ambient)"
            )
        )
        out.append(f"\n## the page it was printed on\n{self.page_text or '(no text layer)'}")
        if self.page_units:
            out.append(
                "\n## every unit on this page, in reading order\n"
                "   A display equation is often several units. Card from all"
                " of them with repeated --unit, or from part of one --"
                " whichever matches what is actually being learned."
            )
            for row in self.page_units:
                mark = "*" if row["unit"] == self.unit else " "
                label = str(row["equation"] or "")
                out.append(f" {mark} {row['unit']:<34} {label:>5}  {row['tex'][:70]}")
        return "\n".join(out)


def assemble(config: Config, unit_id: str) -> UnitContext | None:
    source = unit_id.split(":", 1)[0]
    ledger = open_ledgers(config.sources_dir).get(source)
    if ledger is None:
        return None
    unit = ledger.get(unit_id)
    if unit is None:
        return None

    text = ""
    path = source_text_path(config, source)
    if path.exists():
        text = path.read_text(encoding="utf-8")

    return UnitContext(
        unit=unit.id,
        locator=unit.locator.label(),
        transcription=unit.tex_source or unit.tex_auto or "",
        conventions=_conventions(config, source),
        page_text=_page(text, unit.locator.page),
        page_units=_page_units(ledger, unit.locator.page),
    )


def _page(text: str, page: int | None) -> str:
    if not text or page is None:
        return ""
    match = re.search(rf"^## page {page}$(.*?)(?=^## page |\Z)", text, re.S | re.M)
    return match.group(1).strip() if match else ""


def _page_units(ledger: Any, page: int | None) -> list[dict[str, Any]]:
    """Every unit on the page, top to bottom.

    A multi-line display is usually several units, and the only way to card it
    whole is to name each one. Reading order because that is the order the
    lines belong in.
    """
    if page is None:
        return []
    rows = [u for u in ledger if u.locator.page == page]
    rows.sort(key=lambda u: (u.locator.bbox or (0, 0, 0, 0))[1])
    return [
        {
            "unit": u.id,
            "equation": u.locator.equation,
            "state": u.state,
            "tex": u.tex_source or u.tex_auto or "",
        }
        for u in rows
    ]

def _conventions(config: Config, source: str) -> str:
    """The ambient setting cards from this source are read in.

    Per source, not per project: "denominator layout" and "entries are real"
    are facts about one book, and a second source brings its own. Keeping them
    in the project's own contract would make that contract wrong the moment
    the deck grows.
    """
    path = config.sources_dir / source / "conventions.md"
    if not path.exists():
        return ""
    text = re.sub(r"^#.*$", "", path.read_text(encoding="utf-8"), count=1, flags=re.M)
    return text.strip()
