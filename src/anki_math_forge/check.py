"""`check` -- structural lint over card files (DESIGN.md §7).

Every check here is mechanical. Nothing in this module has an opinion about
whether a card is *good*; that lives in the card-writing skill, and in the
human at the review view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import latex, model
from .config import Config, SourceConfig
from .model import Card

ERROR = "error"
WARN = "warn"

# One clause, glanceable. Not a knob: if this needs tuning the section is
# being used for something else.
USES_CHAR_CAP = 150

# A few words. "Lemma 2", "why the bound needs independence", "the adjugate in
# terms of the inverse". Long enough to name a card, short enough to fit in a
# box on a graph without being cut.
GIST_CAP = 60


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str
    path: Path | None = None
    uid: str = ""

    @property
    def where(self) -> str:
        if self.path is not None:
            return self.path.name
        return self.uid or "(deck)"

    def format(self) -> str:
        return f"{self.where}: {self.level}: [{self.code}] {self.message}"

    def as_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "path": str(self.path) if self.path else "",
            "uid": self.uid,
        }


def _prose_only(text: str) -> str:
    """The section with its maths and its code taken out, for the one check
    that counts lines.

    `to_anki_html` turns a newline into a `<br>` **outside** maths only:
    inside a span it collapses the whitespace, because a `<br>` in the middle
    of a formula splits the text node and breaks the render. So a newline
    inside `$$...$$` is not a hard break on the card, and neither is the one
    that ends a display block.

    That distinction is the whole point here. A proof is meant to be written
    as steps, one display block per line (see the card-writing skill), and an
    `aligned` environment is four lines of one formula. Counting raw lines
    reported every one of those as wrapped prose -- a lint firing on exactly
    the shape the guidance asks for, which teaches you to stop reading the
    lint.

    Display spans come out entirely, so a line that was one of them is left
    empty and stops counting. Inline spans keep their place but lose their
    newlines, since a wrapped `$x +\n y$` is not a wrapped sentence either.

    Fenced code goes the same way and for the same reason: it is written one
    statement per line on purpose, and `to_anki_html` puts it in a `<pre>`
    where a newline is a newline rather than a `<br>`.
    """
    text = model.code_free(text)
    out: list[str] = []
    cursor = 0
    for span in latex.math_spans(text):
        out.append(text[cursor : span.start])
        out.append("" if span.display else " ".join(span.tex.split()))
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


def check_card(
    card: Card,
    config: Config,
    *,
    checker: latex.LatexChecker | None = None,
    for_sync: bool = False,
) -> list[Finding]:
    """Lint one card. `for_sync` promotes "not ready yet" into a hard error."""
    tex = checker or latex.checker(config.extra_macros)
    findings: list[Finding] = []

    def add(level: str, code: str, message: str) -> None:
        findings.append(Finding(level, code, message, path=card.path, uid=card.uid))

    # -- the two optional judgements ---------------------------------------
    # Both are optional; a value outside the vocabulary is not, because a
    # typo would silently become its own Anki tag and quietly split the deck.
    for field_name, vocabulary in (
        ("frequency", model.FREQUENCIES),
        ("derivation", model.DERIVATIONS),
    ):
        value = str(card.frontmatter.get(field_name, "") or "")
        if value and value not in vocabulary:
            add(
                ERROR,
                f"{field_name}-unknown",
                f"{field_name}: {value!r} is not one of {', '.join(vocabulary)}",
            )

    # `augmented` is a receipt, so it is a yes or a no. A string here reads as
    # true to Python and as a date or a name to a person, and the two would
    # disagree about a card nobody looks at twice.
    stamp = card.frontmatter.get("augmented")
    if stamp is not None and not isinstance(stamp, bool):
        add(ERROR, "augmented-not-a-flag", f"augmented: {stamp!r} is not true or false")

    # -- identity ---------------------------------------------------------
    if not card.uid:
        add(ERROR, "uid-missing", "no `uid` in frontmatter")
    elif not model.UID_RE.match(card.uid):
        add(ERROR, "uid-malformed", f"uid {card.uid!r} is not 6 lowercase hex characters")
    elif model.looks_numeric(card.uid):
        # `uid` is the note type's first field, and Anki keeps the sort field in
        # a column that takes a number or text. A uid shaped `4e6166` is a float
        # literal that overflows a double, lands as NULL, and takes the whole
        # deck's export down with a NOT NULL constraint on `notes.sfld`.
        # A warning rather than an error: the card is fine, and renaming a uid
        # would orphan the note already synced under it.
        add(
            WARN,
            "uid-numeric",
            f"uid {card.uid!r} reads as a number to Anki, which sorts it oddly in "
            "the browser and can break `export`. Set the note type to sort by "
            "`Front` instead of `uid` (Manage Note Types > Fields). New uids "
            "avoid this shape.",
        )

    if card.type not in model.SECTIONS_BY_TYPE:
        known = ", ".join(sorted(model.SECTIONS_BY_TYPE))
        add(ERROR, "type-unknown", f"type {card.type!r} is not one of: {known}")

    if card.status not in model.STATUSES:
        add(
            ERROR,
            "status-unknown",
            f"status {card.status!r} is not one of: {', '.join(model.STATUSES)}",
        )

    if not card.source:
        add(WARN, "source-missing", "no `source` -- a card should say where it came from")

    # Which project a card belongs to is read off its unit id, so a card with
    # no unit belongs to none of them. It still syncs, to the repo's default
    # deck, and the app still shows it under the folder it is filed in; what
    # it cannot do is inherit a deck, a layout or a crop. A warning rather
    # than an error, like `source-missing`: the card is fine, it is unfiled.
    if not card.project_name:
        add(
            WARN,
            "unit-missing",
            "no `unit`: nothing says which project this card belongs to, so it "
            "takes the repo's default deck and conventions rather than a "
            "project's",
        )

    # -- sections ---------------------------------------------------------
    names = card.section_names()
    for required in model.REQUIRED_SECTIONS:
        if not (card.section(required) or "").strip():
            add(ERROR, "section-missing", f"`## {required}` is missing or empty")

    duplicates = {n for n in names if names.count(n) > 1}
    for name in sorted(duplicates):
        add(ERROR, "section-duplicate", f"`## {name}` appears more than once")

    allowed = model.SECTIONS_BY_TYPE.get(card.type, frozenset())
    for name in sorted(set(names) - allowed):
        add(ERROR, "section-unknown", f"`## {name}` is not allowed on a `{card.type}` card")

    if card.preamble.strip():
        add(WARN, "stray-text", "text outside any `## section` will not reach Anki")

    # -- latex ------------------------------------------------------------
    for section in card.sections:
        if section.name in model.UNRENDERED_SECTIONS:
            continue  # scratchpad and executable python, not rendered math
        # Fenced code first: it is full of braces, backslashes and `$`, and
        # feeding it to KaTeX reports a card as broken for being correct.
        body = model.code_free(section.body)
        if latex.unbalanced_dollars(body):
            add(ERROR, "latex-dollars", f"`## {section.name}`: unbalanced `$` delimiters")
        for err in tex.validate_text(body):
            add(ERROR, "latex-parse", f"`## {section.name}`: {err.message} in `{err.tex}`")

    # -- length -----------------------------------------------------------
    front = card.section("front") or ""
    length = latex.rendered_length(front)
    if length > config.front_char_cap:
        add(
            ERROR,
            "front-too-long",
            f"rendered front is ~{length} chars, cap is {config.front_char_cap} "
            "-- a prompt this long is usually two cards",
        )

    # A gist is a caption, not a sentence: it labels the card in a list or on a
    # graph node, where anything past a few words is truncated by whatever is
    # drawing it. Warn rather than error, because a long one is still better
    # than none and no card is blocked from syncing by its caption.
    if len(card.gist) > GIST_CAP:
        add(
            WARN,
            "gist-too-long",
            f"`gist` is {len(card.gist)} chars, and it is a label rather than a "
            f"sentence -- past about {GIST_CAP} it is cut off wherever it is shown",
        )

    # A `uses` line is meant to be glanceable: one clause naming where the
    # result turns up. Past a certain length it stops being a pointer and
    # becomes a paragraph nobody reads on the back of a flashcard, which is
    # what `## prose` is for.
    # A newline in a body is not whitespace: `to_anki_html` turns it into a
    # `<br>`, so a section wrapped at some column renders with hard breaks
    # mid-sentence on the card. `verify` is code and never reaches Anki.
    for section in card.sections:
        if section.name in model.UNRENDERED_SECTIONS:
            continue
        body = _prose_only(section.body.strip())
        if len(body.splitlines()) > 1 and all(line.strip() for line in body.splitlines()):
            add(
                WARN,
                "section-wrapped",
                f"`## {section.name}`: prose is wrapped across lines, and "
                "each newline outside maths becomes a <br> on the card. Write "
                "the sentence as one line unless the break is deliberate",
            )

    uses = latex.rendered_length(card.section("uses") or "")
    if uses > USES_CHAR_CAP:
        add(
            WARN,
            "uses-too-long",
            f"`## uses` is ~{uses} chars, cap is {USES_CHAR_CAP}: name the "
            "setting in plain words, do not explain it",
        )

    # -- approval (DESIGN.md §3.5) ----------------------------------------
    if card.status == "approved":
        if not card.stored_hash:
            add(ERROR, "hash-missing", "approved card has no `content_hash`")
        elif not card.hash_matches():
            add(
                ERROR,
                "hash-stale",
                "content changed since approval -- set `status: draft` and review it again "
                f"(stored {card.stored_hash}, actual {card.content_hash()})",
            )

    # -- annotations (DESIGN.md §8) ---------------------------------------
    open_notes = card.annotations()
    if open_notes:
        level = ERROR if (for_sync or card.status == "approved") else WARN
        add(
            level,
            "annotation-open",
            f"{len(open_notes)} open @claude annotation(s): {open_notes[0][:70]}",
        )

    if card.verify_enabled and not (card.section("verify") or "").strip():
        add(ERROR, "verify-missing", "`verify: true` but there is no `## verify` section")
    elif card.verify_enabled and not _samples_anything(card):
        # A warning, not an error: a closed form checked at one point is a
        # legitimate thing to write. But an *identity* checked at one fixed
        # point usually passes because both sides were typed from the same
        # expression, and a check that cannot fail is worse than no check --
        # it reports coverage the deck does not have.
        add(
            WARN,
            "verify-fixed",
            "`## verify` draws nothing random, so it checks one fixed case. "
            f"Sample with {', '.join(sorted(VERIFY_DRAWS)[:3])} or `rng` unless the "
            "claim really is about one point",
        )

    return findings


#: The helpers a `## verify` snippet draws inputs from. A snippet touching
#: none of them evaluates one fixed case every trial, which is what
#: `verify-fixed` is about.
VERIFY_DRAWS = frozenset({"randn", "spd", "sym", "invertible", "orth", "rng"})


def _samples_anything(card: Card) -> bool:
    """Whether the snippet draws its inputs rather than writing them out.

    By name over the parsed tree: `spd_cache = 1` is not a draw. A snippet
    that does not parse is left alone, because `verify` reports the syntax
    error and one complaint about it is enough.
    """
    import ast

    from .verify import code_of

    try:
        tree = ast.parse(code_of(card))
    except SyntaxError:
        return True
    return any(
        isinstance(node, ast.Name) and node.id in VERIFY_DRAWS for node in ast.walk(tree)
    )


def check_requires(cards: list[Card]) -> list[Finding]:
    """The dependency graph, which decides the order cards are introduced in.

    An unknown name is a typo that silently does nothing -- the ordering
    ignores what it cannot resolve, so nothing would ever look wrong. A cycle
    has no valid order at all. Both are errors; a prerequisite that is merely
    not approved yet is a warning, because `sync` will introduce the card
    without its foundation and that is worth knowing rather than blocking.
    """
    findings: list[Finding] = []
    by_uid = {card.uid: card for card in cards if card.uid}

    for card in sorted(cards, key=lambda c: c.uid):
        for need in card.requires:
            if need == card.uid:
                findings.append(
                    Finding(
                        ERROR,
                        "requires-self",
                        f"`requires` names its own uid {need}",
                        card.path,
                        card.uid,
                    )
                )
            elif need not in by_uid:
                findings.append(
                    Finding(
                        ERROR,
                        "requires-unknown",
                        f"`requires` names {need}, which is not a card here -- "
                        "the ordering ignores what it cannot resolve, so this "
                        "would quietly do nothing",
                        card.path,
                        card.uid,
                    )
                )
            elif (
                card.effective_status == "approved"
                and by_uid[need].effective_status != "approved"
            ):
                findings.append(
                    Finding(
                        WARN,
                        "requires-unapproved",
                        f"needs {need}, which is {by_uid[need].effective_status}; "
                        "sync would introduce this card without it",
                        card.path,
                        card.uid,
                    )
                )

    # Cycles: no order satisfies them, so say which cards are in one.
    colour: dict[str, int] = {}
    reported: set[str] = set()

    def walk(uid: str, trail: list[str]) -> None:
        colour[uid] = 1
        for need in by_uid[uid].requires:
            if need not in by_uid or need == uid:
                continue
            if colour.get(need) == 1:
                loop = trail[trail.index(need) :] if need in trail else [need]
                for member in loop:
                    if member not in reported:
                        reported.add(member)
                        findings.append(
                            Finding(
                                ERROR,
                                "requires-cycle",
                                "`requires` forms a cycle: "
                                + " -> ".join([*loop, loop[0]]),
                                by_uid[member].path,
                                member,
                            )
                        )
            elif colour.get(need) is None:
                walk(need, [*trail, need])
        colour[uid] = 2

    for uid in sorted(by_uid):
        if colour.get(uid) is None:
            walk(uid, [uid])
    return findings


def check_deck(
    cards: list[Card],
    config: Config,
    *,
    for_sync: bool = False,
    live_uids: dict[str, int] | None = None,
) -> list[Finding]:
    """Lint every card plus the deck-level invariants."""
    tex = latex.checker(config.extra_macros)
    # One batch for the whole deck: the katex backend costs a process per call.
    tex.prime(
        [
            span.tex
            for card in cards
            for section in card.sections
            if section.name not in {"notes", "verify"}
            for span in latex.math_spans(section.body)
        ]
    )
    findings: list[Finding] = []
    for card in cards:
        findings.extend(check_card(card, config, checker=tex, for_sync=for_sync))

    findings.extend(check_requires(cards))
    findings.extend(check_images(cards, config))
    findings.extend(check_sources(config))

    by_uid: dict[str, list[Card]] = defaultdict(list)
    for card in cards:
        if card.uid:
            by_uid[card.uid].append(card)
    for uid, group in sorted(by_uid.items()):
        if len(group) > 1:
            where = ", ".join(sorted(c.path.name for c in group if c.path))
            findings.append(
                Finding(
                    ERROR,
                    "uid-duplicate",
                    f"uid {uid} used by {len(group)} files: {where}",
                    uid=uid,
                )
            )

    # `live_uids` maps uid -> number of notes carrying it in Anki. More than
    # one means sync cannot tell which note to update (DESIGN.md §7).
    for uid, count in sorted((live_uids or {}).items()):
        if count > 1 and uid in by_uid:
            findings.append(
                Finding(
                    ERROR,
                    "uid-collision",
                    f"uid {uid} is on {count} notes in the live collection; "
                    "deduplicate in Anki first",
                    uid=uid,
                )
            )

    return findings


def check_sources(config: Config) -> list[Finding]:
    """A work is extracted from by **at most one** project.

    Read by as many as you like: a paper cited by one deck and segmented by
    another is the case the shelf exists for, and a reference with no
    document of its own costs nothing.

    Counted over the projects a work has units in, not only the ones its
    extract switch is on for. Turning the switch off stops new units and
    leaves the ones already in that ledger, so reading only the switch let
    this go quiet on two full ledgers, which is the duplication it exists
    to catch. Declaring the same paper in a second project and extracting
    nothing from it stays what it always was: a citation, and fine.

    Authoritative in two is a different thing. A unit lives in one project's
    ledger and its id starts with that project's name, so the same document
    imported twice produces two ledgers of units, two piles of cards and two
    Anki notes per equation, with nothing anywhere that knows they are the
    same. Nobody would choose that, and the way you reach it is by adding a
    work to a second project without noticing it was already segmented in the
    first.

    An error rather than a warning, because the duplication is invisible
    until it is in Anki: every view here is scoped to one project, so two
    copies look like one copy from wherever you are standing.
    """
    from .ledger import Ledger

    findings: list[Finding] = []
    where: dict[str, list[str]] = defaultdict(list)

    def holds_units(project: str, work: SourceConfig) -> bool:
        """Has this project got units out of this work. Only asked of a
        switched-off work, so the usual answer costs no read at all."""
        path = config.units_path(project)
        if not path.exists():
            return False
        spec = config.projects[project]
        return any(spec.source(unit.locator.document) is work for unit in Ledger.load(path))

    for name, spec in config.projects.items():
        for work in spec.sources:
            if not work.key:
                continue
            if work.authoritative or holds_units(name, work):
                where[work.key].append(name)
    for key, projects in sorted(where.items()):
        if len(projects) > 1:
            findings.append(
                Finding(
                    ERROR,
                    "source-extracted-twice",
                    f"{key!r} has units in {', '.join(sorted(projects))}. "
                    "A work is extracted from by at most one project: two make two "
                    "ledgers of units and two notes per card in Anki, with nothing "
                    "that knows they are the same. Keep it in one and cite it from "
                    "the other with `url`",
                )
            )
    return findings


def check_images(cards: list[Card], config: Config) -> list[Finding]:
    """Every picture a card asks for can actually be drawn.

    A card names a unit and `sync` renders its crop from the source document
    (invariant 3: geometry, never image files). That is three things which can
    each be true today and false tomorrow -- the unit is in the ledger, it has
    a bounding box, and the document is on this machine -- and all three fail
    silently at the far end, as a broken image on a card somebody approved
    weeks ago.

    Deck-level rather than per card, because it reads ledgers: one per source,
    loaded once, however many cards point into it.
    """
    from .ledger import Ledger

    findings: list[Finding] = []
    ledgers: dict[str, Ledger | None] = {}

    def ledger_for(source: str) -> Ledger | None:
        if source not in ledgers:
            path = config.units_path(source)
            ledgers[source] = Ledger.load(path) if path.exists() else None
        return ledgers[source]

    for card in cards:
        def add(code: str, message: str, where: Card = card) -> None:
            findings.append(Finding(ERROR, code, message, path=where.path, uid=where.uid))

        for image in card.images():
            if not image.unit:
                add(
                    "image-unresolved",
                    f"`{image.raw}` names no unit and the card has none of its own; "
                    "write `![...](unit:<id>)`",
                )
                continue
            source = image.unit.split(":", 1)[0]
            ledger = ledger_for(source)
            unit = ledger.get(image.unit) if ledger else None
            if unit is None:
                add("image-unit-unknown", f"`{image.raw}`: no unit {image.unit!r}")
                continue
            if not unit.has_crop:
                # A unit from a `.tex` source has no geometry at all, and one
                # whose box was lost in a re-extraction has none any more.
                add(
                    "image-no-geometry",
                    f"`{image.raw}`: unit {image.unit} has no page geometry, so "
                    "there is nothing to render",
                )
                continue
            document = config.document_for(source, unit.locator.document)
            if document is None or not document.exists():
                add(
                    "image-document-missing",
                    f"`{image.raw}`: the source document for {source!r} is not here "
                    f"({document or 'unset'}); crops are rendered from it at sync",
                )
    return findings


def check_repo(
    config: Config,
    *,
    for_sync: bool = False,
    live_uids: dict[str, int] | None = None,
) -> tuple[list[Card], list[Finding]]:
    """Load every card under the configured deck directory and lint it."""
    findings: list[Finding] = []
    cards: list[Card] = []
    for path in sorted(config.cards_dir.rglob("*.md")) if config.cards_dir.exists() else []:
        try:
            cards.append(model.load(path))
        except model.CardError as exc:
            findings.append(Finding(ERROR, "unparseable", str(exc), path=path))
    cards.sort(key=lambda c: (c.uid, str(c.path)))
    findings.extend(check_deck(cards, config, for_sync=for_sync, live_uids=live_uids))
    return cards, findings


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == ERROR]


def findings_for(findings: list[Finding], card: Card) -> list[Finding]:
    return [f for f in findings if f.uid == card.uid or (card.path and f.path == card.path)]
