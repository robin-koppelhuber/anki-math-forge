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

from . import outline as outline_mod
from .config import CHAPTER, PART, REFERENCES_FILE, TOPICS_FILE, WINDOW_WORDS, Config
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
    #: The same window as fields: which entry of the outline, its pages as
    #: printed, and whether it is large. Empty for a count of pages.
    span: dict[str, Any] = field(default_factory=dict)
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
    #: How much beyond the unit's own source this is: `none`, `references`
    #: or `web`. The `web` flag above is the last of the three read as a
    #: yes or no, kept because every pass already branches on it.
    context: str = "references"
    # What `transcription` is written in. `latex` for a formula, whatever the
    # preview says for anything else, so a snippet is fenced as code rather
    # than handed over as maths that will not parse.
    lang: str = "latex"
    # What this unit stands on besides its authoritative source, and the
    # project's shelf behind them. Both are *where to look*, never what to
    # write: a reference is checked against, and only a source settles
    # anything (invariant 7, and ROADMAP.md 10 for the case with no source).
    refs: list[str] = field(default_factory=list)
    shelf: str = ""
    # What you asked for here, verbatim, and the outline of what it should
    # cover. A unit records what a card would be *about*; only the ask says
    # what you wanted from the subject, and "I care about choosing between
    # them, not the full API" is the difference between a useful deck and an
    # even, shallow one.
    asks: str = ""
    # Whether anything here settles what the card says. False when the unit
    # has no authoritative source, which is the whole of what a project with
    # no document is: the references keep a card from being invented and the
    # review loop catches the rest, and both are weaker than a crop.
    settled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "locator": self.locator,
            "transcription": self.transcription,
            "conventions": self.conventions,
            "declared": self.declared,
            "web": self.web,
            "web_from": self.web_from,
            "context": self.context,
            "page_text": self.page_text,
            "window": self.window,
            "pages": self.pages,
            "span": self.span,
            "text_quality": self.text_quality,
            "text_trouble": self.text_trouble,
            "page_units": self.page_units,
            "notes": self.notes,
            "marks": self.marks,
            "lang": self.lang,
            "refs": self.refs,
            "shelf": self.shelf,
            "asks": self.asks,
            "settled": self.settled,
        }

    def format(self) -> str:
        out = [f"{self.unit}  {self.locator}".rstrip()]
        if self.transcription:
            # Fenced when it is not maths, because a snippet handed over bare
            # reads as prose and a reader has to guess where it ends.
            out.append(
                f"\n  {self.transcription}"
                if self.lang == "latex"
                else f"\n```{self.lang}\n{self.transcription}\n```"
            )
        if self.notes:
            # First, because it is the only part of this that was written *to*
            # you. Everything else describes the source; this says what
            # somebody wanted done about it, and it routinely says something
            # the page cannot ("two cards, one per convention").
            out.append("\n## what triage asked for, on this unit")
            for note in self.notes:
                out.append(f"   {note}")
        out.append(
            "\n## the setting this project is read in\n"
            + (
                self.conventions
                or "(none recorded: ask the human for projects/<name>/conventions.md"
                " with an @me note, or whoever writes a card here is guessing at"
                " what is ambient)"
            )
        )
        if self.declared:
            out.append("\n### and what it declares as keys")
            for key, value in sorted(self.declared.items()):
                out.append(f"   {key:<16} {value}")
        # Said plainly and in both directions. An absent line would read as
        # "nobody thought about it", and the whole value of the permission is
        # that somebody did.
        # Said plainly, in all three directions. Three, because "no web"
        # was doing the work of two different answers: read the shelf but
        # not the internet, and read nothing but this page.
        if self.web:
            allowed = (
                f"Web research is ALLOWED for this unit (granted by the {self.web_from})."
                " The shelf below comes first: look things up for what the"
                " source assumes and does not state, and say in `## notes`"
                " what came from off the page."
            )
        elif self.context == "none":
            allowed = (
                "No web access, and no shelf. Everything on the card comes from "
                + ("the pages below" if self.settled else "this unit")
                + " and from the conventions above. If that does not settle"
                " it, annotate the unit rather than reading around it: this"
                " deck is deliberately closed."
            )
        else:
            allowed = (
                "No web access. Everything on the card comes from "
                + ("the pages below" if self.settled else "the references below")
                + " and from the conventions above. **Read the references**:"
                " they are the shelf this project keeps for exactly this, and"
                " each says what it is for. If they do not settle it,"
                " annotate the unit rather than guessing."
            )
        out.append("\n## looking things up\n   " + allowed)
        if self.marks:
            out.append(
                "\n## what the reader marked here\n"
                "   The first is why this unit exists; the rest are what was"
                " marked on the pages handed over below, whether its colour"
                " makes a unit or not. A `(skipped)` is a unit the reader"
                " decided not to card, which is still something they noticed."
                " What a colour means is declared in the config, not inferred"
                " here."
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
                fate = f" ({entry['fate']})" if entry.get("fate") else ""
                page = f"p.{entry['page']} " if entry.get("page") else ""
                out.append(f" {flag} {label:<34} {page}{said[:76]}{fate}")
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
        if self.asks:
            # Before the references, because it is the only part of this that
            # was written *to* whoever comes next, the way a unit's own notes
            # are. Everything else describes the material.
            out.append(
                "\n## what was asked for in this project\n"
                "   Your words, and what each ask means to cover. Write for"
                " this, not for the subject at large: a card nobody asked for"
                " is a card that passes triage and is never wanted.\n"
            )
            out.append(self.asks)
        if self.refs or self.shelf:
            out.append(
                "\n## what to check this against\n"
                "   Reference material, not a source. **It says where to look,"
                " never what to write.** Read it, then say what is true; where"
                " it and the card disagree, the disagreement is the thing to"
                " look at rather than a licence to copy."
            )
            for ref in self.refs:
                out.append(f"   - {ref}")
            if self.shelf:
                out.append("\n### and the shelf this project keeps\n" + self.shelf)
        if not self.settled:
            # Said where the page would have been, because its absence is the
            # thing a pass has to notice. Invariant 4 has nothing to point at
            # here and invariant 7's first half does not apply, so the rule
            # that survives is the second half: note what came from off the
            # page, which is now the only record of where anything came from.
            out.append(
                "\n## there is no page, and nothing here settles what to say\n"
                "   This unit has no authoritative source: no crop, no"
                " printed statement, nothing to transcribe. A card from it is"
                " yours to get right rather than a reading of somebody else's"
                " work, and it carries weaker guarantees than one from a book.\n"
                "   So: write what is true, check it against the references"
                " above, and record in `## notes` what each part came from."
                " Where you are unsure, annotate the card rather than"
                " committing to a plausible sentence."
            )
        elif self.text_quality != "ok":
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
        if self.settled:
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
    ledger = open_ledgers(config.projects_dir).get(source)
    if ledger is None:
        return None
    unit = ledger.get(unit_id)
    if unit is None:
        return None

    if spread is None:
        spread = config.context_pages_for(source, unit.context_pages, unit.locator.document)
    scheme = config.zotero_for(source)
    text = ""
    path = source_text_path(config, source, unit.locator.document)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    quality = source_text_quality(config, source, unit.locator.document)

    found = window_for(config, unit, spread, ledger=ledger, text=text)
    wanted, window = found.pages, found.text
    spec = config.projects.get(source)
    web_from = (
        "unit" if unit.web is not None else "source" if spec and spec.web is not None else "repo"
    )
    # Whether anything settles what this card says. A property of the unit,
    # not of the kind of project it is in: a book whose segmenter found no
    # geometry for one region is in the same position as a proposal nobody
    # printed, and both want the same warning.
    work = spec.source(unit.locator.document) if spec else None
    # Whether a document stands behind this unit, which is not the same
    # question as whether its text layer happens to be cached: a missing
    # layer is a real condition with a warning of its own, and a crop still
    # settles the maths without it.
    #
    # Not the extract switch. A unit out of a `.tex` work has no crop, so
    # this is the whole answer for it, and switching the work off told a
    # card writer there was no source at all and withheld the very page
    # the unit was printed on.
    printed = work is not None and bool(work.files or work.tex or work.zotero_key)
    settled = bool(unit.has_crop or printed)
    scannable, lang = unit.scannable
    return UnitContext(
        unit=unit.id,
        locator=unit.locator.describe(),
        transcription=scannable,
        lang=lang,
        refs=list(unit.refs),
        shelf=shelf(config, source, printed_in=work.key if work else ""),
        asks=asks(config, source),
        settled=settled,
        conventions=source_conventions(config, source),
        declared=dict(config.conventions_for(source)),
        web=config.web_for(source, unit.web),
        web_from=web_from,
        context=config.context_for(source, unit.web),
        page_text=_pages(text, wanted),
        window=window,
        pages=wanted,
        span=found.as_dict() if found.word else {},
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
                # What the passage says, cut to a column when printed. A note
                # covers no passage, so it has none.
                "text": "" if m.kind == "note" else m.text,
                # What the reader wrote *about* the passage, printed whole.
                # A sticky note's comment used to ride in `text` instead, and
                # the column cut it at 76 characters: "make one card for
                # Bayesian smoothing and one for the equations of K..." lost
                # its second request. Notes are where instructions are
                # written, so they go where nothing is cut.
                "comment": m.comment,
                "proposes": scheme.convention_in(m.comment),
                "own": m.key in unit.id,
                # What came of it: a mark that made a unit says where that
                # unit stands, and `skipped` is the reader's own "not a card".
                # A mark that made none says so. Either way it is context.
                "fate": fate_of(ledger, source, m.key, unit.id),
                "page": m.page,
            }
            for m in ambient_marks(config, source, unit, wanted)
        ],
    )


@dataclass(frozen=True)
class Window:
    """What a card writer is handed, and how to say it.

    `source` says where a word's span came from: `outline`, the PDF's own
    table of contents; `labels`, the units' section labels, for a document
    with none; or `count`, a number of pages either side.
    """

    pages: list[int]
    text: str
    word: str = ""
    title: str = ""
    first: int = 0
    last: int = 0
    printed: str = ""
    source: str = "count"

    @property
    def large(self) -> bool:
        return len(self.pages) >= outline_mod.LARGE

    def as_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "title": self.title,
            "first": self.first,
            "last": self.last,
            "count": len(self.pages),
            "printed": self.printed,
            "source": self.source,
            "large": self.large,
            "text": self.text,
            "short": self.short,
        }

    @property
    def short(self) -> str:
        """The window in a few words, for a chip: which entry, which pages,
        how many. `text` is the sentence the heading uses."""
        count = len(self.pages)
        if not count:
            return "no page to hand over"
        pages = self.printed or (
            f"p. {self.first}" if self.first == self.last else f"pp. {self.first}-{self.last}"
        )
        if not self.word:
            first, last = self.pages[0], self.pages[-1]
            pages = f"p. {first}" if first == last else f"pp. {first}-{last}"
        size = f"{count} page{'' if count == 1 else 's'}"
        return " · ".join(part for part in (self.title, pages, size) if part)


def window_for(
    config: Config,
    unit: Any,
    spread: int | str | None = None,
    *,
    ledger: Any = None,
    text: str = "",
) -> Window:
    """Which pages a card writer gets for this unit, and how to say it.

    Triage wants one page: you are deciding whether a region is worth carding
    and a wall of text makes that harder. A pass that writes the card wants as
    much as is reasonable, because an identity's conditions are printed around
    it and the sentence that states them is as likely to be on the previous
    page as this one.

    A word (`section`, `chapter`, `part`) is a span the book itself states,
    read off the PDF's outline (`outline.py`). A document with no outline
    falls back to the units' section labels, and says so, because that is a
    weaker answer: it only knows sections somebody marked something in.
    """
    if spread is None:
        spread = config.context_pages_for(unit.project, unit.context_pages, unit.locator.document)
    page = unit.locator.page
    if page is None:
        # A unit out of a `.tex` file, or one proposed with no document: there
        # is no page to count from, so nothing beyond the unit is handed over.
        return Window([], "no page: the unit carries none, so no pages are handed over")
    if spread in WINDOW_WORDS:
        word = str(spread)
        found = outline_mod.of_document(config, unit.project, unit.locator.document)
        span = found.span(page, word, unit.locator.section) if found else None
        if span is not None:
            return Window(
                list(range(span.first, span.last + 1)),
                _say(word, span.title, span.first, span.last, span.printed),
                word,
                span.title,
                span.first,
                span.last,
                span.printed,
                "outline",
            )
        if ledger is None:
            from .ledger import Ledger

            ledger = Ledger.load(config.units_path(unit.project))
        return _by_labels(ledger, unit, text, word)
    count = int(spread or 0)
    wanted = [p for p in range(page - count, page + count + 1) if p > 0]
    if not count:
        return Window(wanted, "the page it was printed on")
    return Window(wanted, f"the pages it was printed among ({count} either side of page {page})")


def _say(word: str, title: str, first: int, last: int, printed: str, *, how: str = "") -> str:
    """`the chapter it was printed in, "Linear Regression" (pp. 39-50, PDF
    pages 49-60; 12 pages)`. The printed numbers first, because those are
    the ones you check against the book."""
    count = last - first + 1
    span = f"{first}-{last}" if first != last else f"{first}"
    # "PDF pages" only beside the printed numbers, where the two differ and
    # saying which is which is the point.
    pages = f"{printed}, PDF pages {span}" if printed else f"pages {span}"
    size = f"{count} page{'' if count == 1 else 's'}"
    if count >= outline_mod.LARGE:
        size += ", a large window"
    return f'the {word} it was printed in, "{title}" ({pages}; {size}{how})'


def _by_labels(ledger: Any, unit: Any, text: str, word: str) -> Window:
    """A word's span from the units' section labels, for a document with no
    outline. A numbered label groups by its leading number (`2.4` is in
    chapter 2); an unnumbered one is a span of its own."""
    page = int(unit.locator.page)
    ends = _last_page(text, page)
    how = "; from the units' section labels: the document has no outline to read"
    if word == PART or ledger is None:
        return Window(
            list(range(1, ends + 1)),
            f"the whole document, which has no outline to find a {word} in (pages 1-{ends})",
            word,
            "the whole document",
            1,
            ends,
            "",
            "labels",
        )
    group = chapter_of if word == CHAPTER else (lambda section: section.strip())
    name, first, last = _label_span(ledger, unit, ends, group)
    if not name and first == 1 and last >= ends:
        # Nothing declared a table of contents, so the chapter is the document,
        # and the heading says which of the two happened.
        return Window(
            list(range(1, ends + 1)),
            f"the whole document, which declares no {word}s (pages 1-{ends})",
            word,
            "the whole document",
            1,
            ends,
            "",
            "labels",
        )
    title = name or f"the pages before the first {word}"
    return Window(
        list(range(first, last + 1)),
        _say(word, title, first, last, "", how=how),
        word,
        title,
        first,
        last,
        "",
        "labels",
    )


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


def _label_span(ledger: Any, unit: Any, last: int, group: Any) -> tuple[str, int, int]:
    """`(name, first page, last page)` for the group of labels this unit is in.

    A group runs from its first unit's page to the page before the next group
    starts. By page rather than by this unit's own label, because plenty of
    units have none and one printed in the middle of chapter 3 wants chapter
    3 either way: the last group to have started.

    Where no later group starts, a numbered group (chapter 3 of a book that
    numbers them) runs to the end of the document. An unnamed one stops at
    the last page holding a unit of its own: the labels only know sections
    somebody marked something in, and running to the end handed a unit in
    the last marked section the rest of the book.
    """
    page = unit.locator.page
    starts: dict[str, int] = {}
    reach: dict[str, int] = {}
    for other in ledger:
        # Page 17 of the appendix is not page 17 of the paper, so a
        # multi-document source groups within one document only.
        if other.locator.document != unit.locator.document or other.locator.page is None:
            continue
        key = group(other.locator.section)
        if not key:
            continue
        starts[key] = min(starts.get(key, other.locator.page), other.locator.page)
        reach[key] = max(reach.get(key, other.locator.page), other.locator.page)
    ordered = sorted(starts.items(), key=lambda pair: pair[1])
    if not ordered:
        return "", 1, last
    here, first = "", 1
    for name, begins in ordered:
        if begins > page:
            break
        here, first = name, begins
    after = [begins for _, begins in ordered if begins > first]
    if after:
        end = after[0] - 1
    elif here.isdigit():
        end = last
    else:
        end = reach.get(here, page)
    return here, first, max(end, page)


def fate_of(ledger: Any, source: str, key: str, own: str) -> str:
    """The state of the unit a mark made, or empty for one that made none."""
    if f"{source}:{key}" == own:
        return ""
    made = ledger.get(f"{source}:{key}")
    return str(made.state) if made is not None else ""


def ambient_marks(
    config: Config, source: str, unit: Any, pages: list[int]
) -> list[Any]:
    """The marks a card writer is handed: this unit's own, then every mark in
    the pages whose text it is handed.

    The window decides, not a fixed neighbourhood. A unit used to carry the
    marks one page either side of it, and a writer given a chapter of text
    got three pages of what the reader thought about it. Now the marks are
    those inside the same pages as the text, from the whole document's marks
    as cached at import, so a colour that makes no unit and a unit that was
    skipped still say what the reader noticed. Without the cache (an import
    from before it existed) the unit's own neighbours stand in, cut to the
    window the same way.
    """
    from .extract import document_marks

    own, near = unit.marks[:1], unit.marks[1:]
    cached = document_marks(config, source, unit.locator.document)
    pool = cached or near
    found: dict[str, Any] = {}
    for mark in pool:
        if mark.key in unit.id:
            continue
        if pages and mark.page not in pages:
            continue
        found.setdefault(mark.key, mark)
    ordered = sorted(found.values(), key=lambda m: (m.page or 0, m.order, m.key))
    return [*own, *ordered]


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


def shelf(config: Config, project: str, *, printed_in: str = "") -> str:
    """The reference material a project keeps: the declared half and the prose.

    Two places, one list, because a reference arrives in two ways. An
    accepted proposal is a `[[sources]]` table with a title, an address and
    a line saying what it is for, which is what the tool acts on. Anything
    you typed into `references.md` yourself is prose with no schema, because
    nothing branches on it.

    Both are handed over, and the declared ones come first: they are the
    ones somebody agreed to. It is a shelf to check against rather than
    things to card, which is the difference between it and an authoritative
    source: a unit's source settles what the card says, and these do not.

    Only the references this project *offers*. One turned off stays
    declared, cited and findable, and stops arriving with every unit: six
    places to look is a reading list nobody works through.

    It matters most where there is no authoritative source at all. Then this
    is all that keeps a card off the model's memory alone, and handing it
    over is the difference between a deck that was checked and one that was
    remembered.

    `printed_in` is the work this unit came out of, which is never on its
    own shelf. A book you stopped extracting from is a reference to every
    other card here and is still the book this one was cropped from, and
    listing it under "it says where to look, never what to write" got that
    exactly backwards.
    """
    listed = []
    for work in config.references_for(project):
        if printed_in and work.key == printed_in:
            continue
        parts = [work.title or work.key]
        if work.url:
            parts.append(f"({work.url})")
        if work.note:
            parts.append(f"- {work.note}")
        listed.append("- " + " ".join(parts))
    prose = references_prose(config, project)
    return "\n\n".join(part for part in ("\n".join(listed), prose) if part)


def references_prose(config: Config, project: str) -> str:
    """What `references.md` itself says, without the declared sources.

    The setup stage reads this and the card writer reads `shelf`. They
    want different things out of one file: the writer wants everything
    worth checking a card against, and the page wants the lines somebody
    can still accept or reject.

    Handing the page the composed version rendered each declared source as
    a shelf line with an accept button on it, for a source that was
    already accepted, and the buttons did nothing: `drop_proposal` cannot
    find a line that is not in the file, and accepting one would write a
    second table for a work already declared.
    """
    path = config.projects_dir / project / REFERENCES_FILE
    if not path.exists():
        return ""
    return re.sub(r"^#.*$", "", path.read_text(encoding="utf-8"), count=1, flags=re.M).strip()


def asks(config: Config, project: str) -> str:
    """What was asked for in this project, verbatim.

    `projects/<name>/topics.md`, if there is one. Prose with a recognisable
    shape rather than a schema: nothing here interprets it, and a pass that
    counts outline entries against units counts lines rather than parsing
    them.

    Handed over whole. Which ask a unit belongs to is not recorded, and
    guessing from a tag would be interpretation; with a handful of subjects
    in a project, all of them is both honest and short.
    """
    path = config.projects_dir / project / TOPICS_FILE
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def source_conventions(config: Config, source: str) -> str:
    """The ambient setting cards from this source are read in.

    Per source, not per project: "denominator layout" and "entries are real"
    are facts about one book, and a second source brings its own. Keeping them
    in the project's own contract would make that contract wrong the moment
    the deck grows.

    It is `projects/<name>/conventions.md`: a plain Markdown document beside
    `project.toml`, which holds the keys. They were one file for a while, TOML
    fenced above prose, on the argument that a convention kept away from the
    keys it qualifies is the one nobody opens. What that produced was a file
    that is neither -- no editor checks the TOML above the fence *and* renders
    the Markdown below it. The prose half of a `source.md` is still read where
    a repo has not been migrated.
    """
    from .config import CONVENTIONS_FILE, SOURCE_FILE, split_source_file

    folder = config.projects_dir / source
    path = folder / CONVENTIONS_FILE
    if path.exists():
        body = path.read_text(encoding="utf-8")
    else:
        path = folder / SOURCE_FILE
        if not path.exists():
            return ""
        body = split_source_file(path)[1]
    return re.sub(r"^#.*$", "", body, count=1, flags=re.M).strip()
