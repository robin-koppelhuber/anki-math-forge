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

from .config import CHAPTER, Config
from .extract import source_text_path, source_text_quality
from .ledger import open_ledgers


@dataclass
class UnitContext:
    unit: str
    locator: str
    transcription: str
    conventions: str
    page_text: str
    page_units: list[dict[str, Any]]
    # What `page_text` covers, named the way the reader would name it: "the
    # page it was printed on", or the chapter and its span. The heading says
    # it, because a pass handed eleven pages under a heading that says "page"
    # has no way to tell how much it is holding.
    window: str = "the page it was printed on"
    pages: list[int] = field(default_factory=list)
    # Whether the prose above is worth reading, or is a scan's worth of
    # nothing. Mechanical: see `extract.text_quality`.
    text_quality: str = "ok"
    text_trouble: str = ""
    # What was written on the unit at triage, verbatim. An instruction for
    # whoever comes next rather than a fact about the source, which is why it
    # is printed first and separately.
    notes: list[str] = field(default_factory=list)
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
            "window": self.window,
            "pages": self.pages,
            "text_quality": self.text_quality,
            "text_trouble": self.text_trouble,
            "page_units": self.page_units,
            "notes": self.notes,
            "marks": self.marks,
        }

    def format(self) -> str:
        out = [f"{self.unit}  {self.locator}"]
        if self.transcription:
            out.append(f"\n  {self.transcription}")
        if self.notes:
            # First, because it is the only part of this that was written *to*
            # you. Everything else describes the source; this says what
            # somebody wanted done about it, and it routinely says something
            # the page cannot ("two cards, one per convention").
            out.append("\n## what triage asked for, on this unit")
            for note in self.notes:
                out.append(f"   {note}")
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
                "\n   A `>` line is what the reader wrote about the mark, in"
                " their own words rather than the page's."
            )
            for entry in self.marks:
                flag = "*" if entry["own"] else " "
                label = entry["meaning"] or f"{entry['kind']}/{entry['colour']}"
                # Collapsed: this is a column of aligned rows, and a mark
                # spanning a line break carried the newline through and broke
                # the alignment for everything under it.
                said = " ".join(str(entry["text"]).split())
                out.append(f" {flag} {label:<34} {said[:76]}")
                if entry.get("comment"):
                    wrote = " ".join(str(entry["comment"]).split())
                    out.append(f"   {'':<34} > {wrote}")
        proposed = [e for e in self.marks if e.get("proposes")]
        if proposed:
            # Loud and separate, because it asks for something no other part of
            # this context does. A convention governs every card written here
            # afterwards and has no review of its own, so what this pass may do
            # with one is write it down for the human, never adopt it.
            out.append(
                "\n## conventions this unit proposes\n"
                "   The reader marked these as ambient rather than as card"
                " material. **Do not write them into `conventions.md`.**"
                " Record each as an `@me` annotation on the unit, verbatim,"
                " for the human to accept or reject: a convention decides how"
                " every later card here is read, and nothing reviews it."
            )
            for entry in proposed:
                out.append(f"   - {entry['proposes']}")
        if self.text_quality != "ok":
            # Before the text rather than after it: by the time you have read a
            # page of noise you have already formed an impression of what this
            # source says.
            out.append(
                f"\n## {self.window}\n"
                f"**The text layer here is unusable ({self.text_trouble}).** "
                "Read the crop and write the card from that. Do not take the "
                "absence of a condition below as the source not stating one, "
                "and say in `## notes` if you had nothing but the crop."
            )
        out.append(
            f"\n## {self.window}\n{self.page_text or '(no text layer)'}"
            if self.text_quality == "ok"
            else self.page_text
        )
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
    config: Config, unit_id: str, *, spread: int | str | None = None
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
    quality = source_text_quality(config, source, unit.locator.document)

    wanted, window = _window(ledger, unit, text, spread)
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
        page_text=_pages(text, wanted),
        window=window,
        pages=wanted,
        text_quality=quality.verdict,
        text_trouble=quality.describe() if quality.verdict != "ok" else "",
        page_units=_page_units(ledger, unit.locator.page),
        notes=list(unit.notes),
        marks=[
            {
                "kind": m.kind,
                "colour": m.colour,
                # Resolved now, not at import: editing your scheme should
                # change what every unit reads as, not only the new ones.
                "meaning": scheme.means(m.kind, m.colour),
                "text": m.content,
                # What the reader wrote *about* the passage, beside what the
                # passage says. `Mark.content` gives the comment only for a
                # note, so a sentence typed onto a highlight reached the units
                # view and stopped there: the one pass that most needs to know
                # what you meant was the one that could not see it.
                "comment": "" if m.kind == "note" else m.comment,
                "proposes": scheme.convention_in(m.comment),
                "own": m.key in unit.id,
            }
            for m in unit.marks
        ],
    )


def _window(
    ledger: Any, unit: Any, text: str, spread: int | str | None
) -> tuple[list[int], str]:
    """Which pages to hand over, and how to say what they are.

    Triage wants one page: you are deciding whether a region is worth carding
    and a wall of text makes that harder. A pass that writes the card wants as
    much as is reasonable, because an identity's conditions are printed around
    it and the sentence that states them is as likely to be on the previous
    page as this one. There is no reason to be stingy there, so the window
    opens up rather than making the caller ask page by page.

    `chapter` is the size that is not a count. Ten pages either side of a
    result is most of one chapter and a slice of the next; the chapter itself
    is the span the book states its standing assumptions in, and where it
    starts is a fact about the book rather than a number a caller can guess.
    """
    page = unit.locator.page
    if page is None:
        return [], "the page it was printed on"
    if spread == CHAPTER:
        ends = _last_page(text, page)
        name, first, last = _chapter_span(ledger, unit, ends)
        if name:
            where = f'the chapter it was printed in, "{name}"'
        elif first > 1 or last < ends:
            # Printed before the first chapter starts: front matter, a preface,
            # or a segmenter that filed this one nowhere. Named for what it is
            # rather than promised as a chapter.
            where = "the pages before the first chapter"
        else:
            where = "the whole document, which declares no chapters"
        return list(range(first, last + 1)), f"{where} (pages {first} to {last})"
    span = int(spread or 0)
    wanted = [p for p in range(page - span, page + span + 1) if p > 0]
    if not span:
        return wanted, "the page it was printed on"
    return wanted, f"the pages it was printed among ({span} either side of page {page})"


def _pages(text: str, wanted: list[int]) -> str:
    """The text of each page asked for, in order, skipping the ones the
    document does not have."""
    if not text or not wanted:
        return ""
    out = []
    for number in wanted:
        match = re.search(rf"^## page {number}$(.*?)(?=^## page |\Z)", text, re.S | re.M)
        if not match:
            continue
        body = match.group(1).strip()
        out.append(f"### page {number}\n{body}" if len(wanted) > 1 else body)
    return "\n\n".join(out)


def _last_page(text: str, fallback: int) -> int:
    """The highest page the text layer has, for a chapter that runs to the end
    of the document with no unit on its final pages."""
    found = [int(n) for n in re.findall(r"^## page (\d+)$", text, re.M)]
    return max(found) if found else fallback


def chapter_of(section: str) -> str:
    """Which chapter a section belongs to.

    `2.4` is in chapter `2`; `3 Bayesian Linear Regression` is in chapter `3`;
    a section that is a bare title is its own chapter, because a source whose
    divisions are not numbered has no coarser grouping to offer. A source with
    no sections at all -- nothing declared a table of contents -- lands every
    unit in one unnamed chapter, which is the document, and the window says so
    rather than naming a chapter it cannot see.
    """
    head = section.split()[0] if section.split() else ""
    if re.fullmatch(r"\d+(\.\d+)*\.?", head):
        return head.split(".")[0]
    return section.strip()


def _chapter_span(ledger: Any, unit: Any, last: int) -> tuple[str, int, int]:
    """`(chapter, first page, last page)` for the chapter this unit is in.

    Worked out from the ledger rather than from the PDF outline: the units are
    already here and already carry the section the document declared for them,
    so this needs no second reader and cannot disagree with the section rail.
    A chapter runs from its first unit's page to the page before the next
    chapter starts, which covers the pages at its end that hold no unit.

    By page rather than by this unit's own section, because plenty of units
    have no section -- a segmenter files what it can -- and one printed in the
    middle of chapter 3 wants chapter 3 either way. It is the same reading
    `zotero.section_at` applies to a table of contents: the last chapter to
    have started.
    """
    page = unit.locator.page
    starts: dict[str, int] = {}
    for other in ledger:
        # Page 17 of the appendix is not page 17 of the paper, so a
        # multi-document source groups within one document only.
        if other.locator.document != unit.locator.document or other.locator.page is None:
            continue
        key = chapter_of(other.locator.section)
        if not key:
            continue
        starts[key] = min(starts.get(key, other.locator.page), other.locator.page)
    ordered = sorted(starts.items(), key=lambda pair: pair[1])
    if not ordered:
        return "", 1, last
    here, first = "", 1
    for name, begins in ordered:
        if begins > page:
            break
        here, first = name, begins
    after = [begins for _, begins in ordered if begins > first]
    end = after[0] - 1 if after else last
    return here, first, max(end, page)


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
