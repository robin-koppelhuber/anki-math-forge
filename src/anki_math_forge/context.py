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
from dataclasses import dataclass, field
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
    marks: list[dict[str, Any]] = field(default_factory=list)
    # `[conventions]` from the source's own file: the keyed half of what is
    # ambient here, beside the prose half above.
    declared: dict[str, str] = field(default_factory=dict)
    # Whether whoever writes this card may look things up on the web, already
    # resolved through unit, source and repo -- so the pass reading this never
    # has to work out whose setting won.
    web: bool = False
    web_from: str = "repo"

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "locator": self.locator,
            "transcription": self.transcription,
            "conventions": self.conventions,
            "declared": self.declared,
            "web": self.web,
            "web_from": self.web_from,
            "page_text": self.page_text,
            "page_units": self.page_units,
            "marks": self.marks,
        }

    def format(self) -> str:
        out = [f"{self.unit}  {self.locator}"]
        if self.transcription:
            out.append(f"\n  {self.transcription}")
        out.append(
            "\n## the setting this source is read in\n"
            + (
                self.conventions
                or "(none recorded -- write sources/<name>/conventions.md,"
                " or whoever writes a card here is guessing at what is ambient)"
            )
        )
        if self.declared:
            out.append("\n### and what it declares as keys")
            for key, value in sorted(self.declared.items()):
                out.append(f"   {key:<16} {value}")
        # Said plainly and in both directions. An absent line would read as
        # "nobody thought about it", and the whole value of the permission is
        # that somebody did.
        out.append(
            "\n## looking things up\n   "
            + (
                f"Web research is ALLOWED for this unit (granted by the {self.web_from})."
                " Use it for what the source assumes and does not state, and say"
                " in `## notes` what came from off the page."
                if self.web
                else "No web access. Everything on the card comes from the pages"
                " below and from the conventions above; if the source does not"
                " settle it, annotate the unit rather than guessing."
            )
        )
        if self.marks:
            out.append(
                "\n## what the reader marked here\n"
                "   The first is why this unit exists; the rest are what was"
                " marked on the pages around it. What a colour means is"
                " declared in the config, not inferred here."
            )
            for entry in self.marks:
                flag = "*" if entry["own"] else " "
                label = entry["meaning"] or f"{entry['kind']}/{entry['colour']}"
                out.append(f" {flag} {label:<34} {entry['text'][:76]}")
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


def assemble(
    config: Config, unit_id: str, *, spread: int | None = None
) -> UnitContext | None:
    source = unit_id.split(":", 1)[0]
    ledger = open_ledgers(config.sources_dir).get(source)
    if ledger is None:
        return None
    unit = ledger.get(unit_id)
    if unit is None:
        return None

    if spread is None:
        spread = config.context_pages_for(source, unit.context_pages)
    scheme = config.zotero_for(source)
    text = ""
    path = source_text_path(config, source, unit.locator.document)
    if path.exists():
        text = path.read_text(encoding="utf-8")

    spec = config.sources.get(source)
    web_from = (
        "unit" if unit.web is not None else "source" if spec and spec.web is not None else "repo"
    )
    return UnitContext(
        unit=unit.id,
        locator=unit.locator.describe(),
        transcription=unit.tex_source or unit.tex_auto or "",
        conventions=source_conventions(config, source),
        declared=dict(config.conventions_for(source)),
        web=config.web_for(source, unit.web),
        web_from=web_from,
        page_text=_page(text, unit.locator.page, spread),
        page_units=_page_units(ledger, unit.locator.page),
        marks=[
            {
                "kind": m.kind,
                "colour": m.colour,
                # Resolved now, not at import: editing your scheme should
                # change what every unit reads as, not only the new ones.
                "meaning": scheme.means(m.kind, m.colour),
                "text": m.content,
                "own": m.key in unit.id,
            }
            for m in unit.marks
        ],
    )


def _page(text: str, page: int | None, spread: int = 0) -> str:
    """The page, and `spread` pages either side of it.

    Triage wants one page: you are deciding whether a region is worth carding
    and a wall of text makes that harder. A pass that writes the card wants as
    much as is reasonable, because an identity's conditions are printed around
    it and the sentence that states them is as likely to be on the previous
    page as this one. There is no reason to be stingy there, so `--pages` opens
    it up rather than making the caller ask page by page.
    """
    if not text or page is None:
        return ""
    wanted = [p for p in range(page - spread, page + spread + 1) if p > 0]
    out = []
    for number in wanted:
        match = re.search(rf"^## page {number}$(.*?)(?=^## page |\Z)", text, re.S | re.M)
        if not match:
            continue
        body = match.group(1).strip()
        out.append(f"### page {number}\n{body}" if spread else body)
    return "\n\n".join(out)


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

def source_conventions(config: Config, source: str) -> str:
    """The ambient setting cards from this source are read in.

    Per source, not per project: "denominator layout" and "entries are real"
    are facts about one book, and a second source brings its own. Keeping them
    in the project's own contract would make that contract wrong the moment
    the deck grows.

    It is `sources/<name>/conventions.md`: a plain Markdown document beside
    `source.toml`, which holds the keys. They were one file for a while, TOML
    fenced above prose, on the argument that a convention kept away from the
    keys it qualifies is the one nobody opens. What that produced was a file
    that is neither -- no editor checks the TOML above the fence *and* renders
    the Markdown below it. The prose half of a `source.md` is still read where
    a repo has not been migrated.
    """
    from .config import CONVENTIONS_FILE, SOURCE_FILE, split_source_file

    folder = config.sources_dir / source
    path = folder / CONVENTIONS_FILE
    if path.exists():
        body = path.read_text(encoding="utf-8")
    else:
        path = folder / SOURCE_FILE
        if not path.exists():
            return ""
        body = split_source_file(path)[1]
    return re.sub(r"^#.*$", "", body, count=1, flags=re.M).strip()
