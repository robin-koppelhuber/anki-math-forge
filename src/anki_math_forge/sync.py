"""`sync` -- push approved cards to Anki, upserting by `uid` (DESIGN.md §9).

Rules this module exists to enforce:

* only `status: approved` cards go anywhere;
* a card with an open `@claude` annotation is refused regardless of status;
* `check` must be clean first;
* running twice adds nothing the second time.

Files → Anki only. Nothing here reads a card back out of Anki, and nothing
deletes: a card that is no longer approved is *reported*, not removed, because
silently deleting somebody's review history is not a thing a lint tool does.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from . import check, latex, model, notetype, study
from .anki import AnkiConnect, AnkiError
from .config import Config
from .model import Card

#: A sort key: one integer per criterion, then the uid. The uid is always last
#: and is not a criterion (`study.py` says why), so the tuple is only ever
#: compared against another built from the same declared order.
StudyKey = tuple[int | str, ...]

OPTIONAL_FIELD_SECTIONS = {
    "Conditions": "conditions",
    "Uses": "uses",
    "Proof": "proof",
    "Prose": "prose",
}


# -- rendering -------------------------------------------------------------


def to_anki_html(text: str) -> str:
    r"""Section body -> Anki field HTML.

    Math becomes MathJax (`\(...\)` / `\[...\]`) because Anki does not treat
    `$` as a delimiter. Everything is HTML-escaped -- MathJax v3 reads text
    nodes, so the browser hands it back the decoded `&`, `<` and `>` that TeX
    wants. Newlines become `<br>` only *outside* math, since a `<br>` inside a
    formula would split the text node and break the render.
    """
    if not text.strip():
        return ""
    out: list[str] = []
    cursor = 0
    for span in latex.math_spans(text):
        out.append(_escape_prose(text[cursor : span.start]))
        tex = " ".join(span.tex.split())
        body = html.escape(tex, quote=False)
        out.append(f"\\[{body}\\]" if span.display else f"\\({body}\\)")
        cursor = span.end
    out.append(_escape_prose(text[cursor:]))
    return "".join(out).strip()


def _escape_prose(text: str) -> str:
    return html.escape(text, quote=False).replace("\n", "<br>")


_TAG_SAFE = re.compile(r"[^A-Za-z0-9_:.-]+")


def tags_for(card: Card, config: Config) -> list[str]:
    """Frontmatter tags, a marker tag, and a `src::` tag from the unit (§9).

    The `src::` tag is what makes a bad batch suspendable wholesale.
    """
    tags = {config.tag_prefix, *card.tags}
    # Both optional, both coarse. As tags they are filterable in Anki, which
    # is where the decision they inform actually gets made -- "drill the core
    # ones", "leave the definitional ones on a longer interval".
    if card.frequency:
        tags.add(f"freq::{card.frequency}")
    if card.derivation:
        tags.add(f"derive::{card.derivation}")
    # Which kind of card this is, for the same reason: a deck holding both
    # restatements and explanations is one you want to be able to drill
    # separately without splitting it.
    if card.type:
        tags.add(f"type::{card.type}")
    if card.unit:
        # The source, and the section only when the id actually encodes one.
        # Taking the first two segments unconditionally assumed every id was
        # `<source>:<section>:<number>`. A unit imported from a marked-up PDF
        # is `<source>:<annotation key>`, so that produced one unique tag per
        # card -- defeating the only thing this tag is for, and filling the
        # collection with tags that name a single note each.
        parts = [p for p in card.unit.split(":") if p]
        tags.add("src::" + "::".join(parts[:2] if len(parts) >= 3 else parts[:1]))
    elif card.source:
        tags.add("src::" + model.slugify(card.source))
    return sorted(_TAG_SAFE.sub("_", t).strip("_") for t in tags if t.strip())


def media_name(card: Card, image: model.ImageRef) -> str:
    """What Anki stores this picture as.

    The card and the slot, and nothing about the unit: a card that swaps which
    unit it shows should overwrite its own picture rather than leave the old
    one behind under a name no note references. Prefixed, because Anki's media
    folder is one flat namespace shared with everything else in the
    collection.
    """
    return f"forge-{card.uid}-{image.index}.png"


def _with_images(body: str, card: Card, section: str) -> str:
    """Swap this section's `![...](unit:...)` for the `<img>` Anki shows.

    After the escaping rather than before it: `to_anki_html` escapes
    everything outside maths, which would turn a tag written first into
    visible angle brackets. A reference survives that escaping unchanged
    except for its alt text, so the same escaping is applied to what we look
    for.
    """
    for image in card.images():
        if image.section != section:
            continue
        tag = (
            f'<img src="{media_name(card, image)}"'
            f' alt="{html.escape(image.alt, quote=True)}">'
        )
        body = body.replace(html.escape(image.raw, quote=False), tag)
    return body


def fields_for(card: Card, config: Config) -> dict[str, str]:
    def rendered(name: str) -> str:
        return _with_images(to_anki_html(card.section(name) or ""), card, name)

    fields = {
        "uid": card.uid,
        "Front": rendered("front"),
        "Back": rendered("back"),
        "Source": html.escape(card.source, quote=False),
    }
    for name, section in OPTIONAL_FIELD_SECTIONS.items():
        fields[name] = rendered(section)
    # `## notes` and `## verify` never reach any field (§9).
    return fields


def upload_images(client: AnkiConnect, config: Config, card: Card) -> list[str]:
    """Render every picture this card asks for and put it in Anki's media.

    Before the note is written, so a field naming a file that is not there
    cannot be left behind by a failure halfway. `check` has already said the
    unit, its geometry and the document are all present -- this is where they
    are actually used, so a renderer that is not installed still surfaces
    here, as a refusal rather than a broken card.
    """
    from base64 import b64encode

    from .extract import render as render_mod
    from .ledger import Ledger

    stored: list[str] = []
    ledgers: dict[str, Ledger | None] = {}
    for image in card.images():
        source = image.unit.split(":", 1)[0]
        if source not in ledgers:
            path = config.units_path(source)
            ledgers[source] = Ledger.load(path) if path.exists() else None
        ledger = ledgers[source]
        unit = ledger.get(image.unit) if ledger else None
        geometry = unit.crop_geometry() if unit else None
        document = config.document_for(source, unit.locator.document) if unit else None
        if unit is None or geometry is None or document is None or not document.exists():
            raise AnkiError(f"cannot render {image.raw}: see `forge check`")
        try:
            png = render_mod.render_crop(
                document,
                *geometry,
                # No outline and no marks painted back on. Those are
                # triage's: they say "here is what you marked, is the box
                # right". On a card the picture *is* the content, and a
                # rectangle round it is an artefact of the tool rather than
                # something the source printed.
                #
                # Pulled in by a hair on top of that, for the copy of that
                # rectangle that lives in the PDF itself when a reader has
                # their annotations written back to the file. Nothing here can
                # switch that one off.
                context=-render_mod.CARD_INSET,
                width=config.crop_width_for(source, from_a_mark=unit.crops_to_page),
            )
        except (render_mod.PdfUnavailable, ValueError) as exc:
            raise AnkiError(f"cannot render {image.raw}: {exc}") from exc
        name = media_name(card, image)
        client.store_media_file(name, b64encode(png).decode("ascii"))
        stored.append(name)
    return stored


# -- planning and execution ------------------------------------------------


@dataclass
class CardOutcome:
    uid: str
    action: str  # setup | add | update | unchanged | move | skip | error
    detail: str = ""
    # The few words naming the card. A uid answers "which file"; a report you
    # read to decide whether something went wrong is asking "which card", and
    # a column of six hex digits answers that only if you go and look each one
    # up. Empty for a card with no gist and for the deck-level lines, which
    # are about no card at all.
    gist: str = ""

    def format(self) -> str:
        suffix = f" -- {self.detail}" if self.detail else ""
        named = f"{self.uid}  {self.gist}" if self.gist else self.uid
        return f"{self.action:9} {named}{suffix}"


@dataclass
class SyncReport:
    outcomes: list[CardOutcome] = field(default_factory=list)
    findings: list[check.Finding] = field(default_factory=list)
    dry_run: bool = False

    def count(self, action: str) -> int:
        return sum(1 for o in self.outcomes if o.action == action)

    @property
    def ok(self) -> bool:
        return not check.errors(self.findings) and self.count("error") == 0

    def summary(self) -> str:
        # `move` only when something moved: a deck change is rare, and a line
        # reading "0 move" on every sync is a number nobody reads, which is
        # how the one that is not zero gets missed.
        actions = ["add", "update", "unchanged", "skip", "error"]
        if self.count("move"):
            actions.insert(3, "move")
        parts = [f"{self.count(a)} {a}" for a in actions]
        prefix = "would sync: " if self.dry_run else "synced: "
        return prefix + ", ".join(parts)


def syncable(cards: list[Card]) -> tuple[list[Card], list[CardOutcome]]:
    """Split cards into "goes to Anki" and "explicitly does not"."""
    ready: list[Card] = []
    skipped: list[CardOutcome] = []
    for card in cards:
        if card.annotations():
            # §8: refused regardless of status. "Not ready" is mechanical.
            skipped.append(
                CardOutcome(card.uid, "skip", "open @claude annotation", gist=card.gist)
            )
        elif card.effective_status != "approved":
            # Say *why* a card that claims to be approved is not going: an
            # edit since approval is a different situation from a draft.
            detail = (
                "approved, but edited since -- re-review it"
                if card.status == "approved"
                else f"status is {card.status}"
            )
            skipped.append(CardOutcome(card.uid, "skip", detail, gist=card.gist))
        else:
            ready.append(card)
    return ready, skipped


def live_uid_counts(client: AnkiConnect, config: Config) -> dict[str, int]:
    """uid -> number of notes carrying it, for the collision check (§7)."""
    counts: dict[str, int] = {}
    if config.note_type not in client.model_names():
        return counts
    note_ids = client.find_notes(f'"note:{config.note_type}"')
    for info in client.notes_info(note_ids):
        uid = str(info.get("fields", {}).get("uid", {}).get("value", "")).strip()
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def decks_for(cards: list[Card], config: Config) -> list[str]:
    """Every deck this run will write to, in a stable order."""
    return sorted({config.deck_for(card.project_name, card.type) for card in cards})


def source_positions(config: Config) -> dict[str, int]:
    """Every unit id, numbered in the order its source prints it.

    A ledger is written in reading order, so the index is the order that
    source introduces things in. Whether that is worth following is a fact
    about the source, not about this tool: a text that builds up says
    `order = "printed"` and a table with no meaningful order says `none`,
    whose units get no position and so fall back to an arbitrary but stable
    tiebreak rather than a misleading one.

    Sources are numbered in the order `forge.toml` lists them, for the
    same reason the deck list is: which source comes first is a choice you
    make by editing the config, not an accident of spelling.
    """
    from .ledger import open_ledgers

    ledgers = open_ledgers(config.projects_dir)
    names = [n for n in config.projects if n in ledgers]
    names += sorted(set(ledgers) - set(names))

    positions: dict[str, int] = {}
    at = 0
    for name in names:
        spec = config.projects.get(name)
        if spec is not None and spec.order == "none":
            continue
        for unit in ledgers[name]:
            positions[unit.id] = at
            at += 1
    return positions


def study_values(card: Card, positions: dict[str, int] | None = None) -> dict[str, int]:
    """Each criterion's rank for one card, before any of them is ranked.

    Split out from `study_key` so that reordering the criteria is a reordering
    of this dictionary's keys and nothing else. A card missing a grading sorts
    last within its group: unannotated is unjudged, not easy.
    """
    positions = positions or {}
    return {
        "frequency": (
            model.FREQUENCIES.index(card.frequency)
            if card.frequency
            else len(model.FREQUENCIES)
        ),
        "derivation": (
            model.DERIVATIONS.index(card.derivation)
            if card.derivation
            else len(model.DERIVATIONS)
        ),
        "printed": min(
            (positions[u] for u in card.units if u in positions), default=len(positions)
        ),
    }


def study_key(
    card: Card,
    positions: dict[str, int] | None = None,
    order: Sequence[str] = (),
) -> StudyKey:
    """Where a card belongs in the new-card queue, dependencies aside.

    The criteria in the sequence `order` names, most significant first, and
    `study.py` holds both the list and the reasoning for each. The default is
    most useful first, then easiest first, then in the order the source
    introduces it.

    The last key is the uid, and it is not one of the criteria. Before it
    existed, a large bucket sorted by hash and a result could arrive well
    before what it is built from; now it only settles a tie, so that two
    machines produce the same deck.
    """
    values = study_values(card, positions)
    return (*(values[c.name] for c in study.resolve(order)), card.uid)


def effective_keys(
    cards: list[Card],
    positions: dict[str, int] | None = None,
    order: Sequence[str] = (),
) -> dict[str, StudyKey]:
    """Each card's sort key, after prerequisites inherit from their dependents.

    A prerequisite is at least as important as the most important thing that
    needs it. Without that, requiring a `rare` card drags the `core` card that
    needs it to the back of the queue -- the dependency was respected and the
    deck got worse. Pulling the prerequisite forward respects it and keeps the
    useful card early.
    """
    by_uid = {card.uid: card for card in cards}
    own = {uid: study_key(card, positions, order) for uid, card in by_uid.items()}
    dependents: dict[str, list[str]] = {uid: [] for uid in by_uid}
    for card in cards:
        for need in card.requires:
            if need in by_uid and need != card.uid:
                dependents[need].append(card.uid)

    effective: dict[str, StudyKey] = {}
    walking: set[str] = set()

    def resolve(uid: str) -> StudyKey:
        if uid in effective:
            return effective[uid]
        if uid in walking:  # a cycle; `check` refuses one, so just stop here
            return own[uid]
        walking.add(uid)
        best = min([own[uid], *(resolve(d) for d in dependents[uid])])
        walking.discard(uid)
        effective[uid] = best
        return best

    for uid in by_uid:
        resolve(uid)
    return effective


def inherited_from(
    cards: list[Card],
    positions: dict[str, int] | None = None,
    order: Sequence[str] = (),
) -> dict[str, str]:
    """For each card a dependent pulled forward, the card whose place it took.

    `effective_keys` says *that* a prerequisite was promoted; this says whose
    doing it was. Only the panel on the canvas needs it, and it needs it
    because "moved 12 places earlier" with nothing named is a fact you cannot
    act on: the answer to "should it have been?" is the card at the other end.

    An own key ends in the uid and so is unique, which is what makes the
    lookup exact rather than a search for a card with a matching grading.
    """
    own = {card.uid: study_key(card, positions, order) for card in cards}
    whose = {key: uid for uid, key in own.items()}
    return {
        uid: whose[key]
        for uid, key in effective_keys(cards, positions, order).items()
        if key != own[uid] and key in whose
    }


def in_study_order(
    cards: list[Card],
    positions: dict[str, int] | None = None,
    order: Sequence[str] = (),
) -> list[Card]:
    """Study order, with `requires` respected absolutely.

    A topological sort whose priority is `effective_keys`: of everything whose
    prerequisites are already placed, take the most useful. The gradings still
    decide nearly everything; the graph only moves a card that would otherwise
    arrive before its own foundation, and it moves the foundation forward
    rather than the result back.

    A `requires` naming a card that is not here is ignored rather than fatal --
    `sync` orders only what is approved, and a prerequisite still in draft
    should not strand everything built on it. `check` reports that instead.
    """
    import heapq

    by_uid = {card.uid: card for card in cards}
    keys = effective_keys(cards, positions, order)
    blocking = {
        card.uid: {u for u in card.requires if u in by_uid and u != card.uid} for card in cards
    }
    unblocks: dict[str, list[str]] = {uid: [] for uid in by_uid}
    for uid, needs in blocking.items():
        for need in needs:
            unblocks[need].append(uid)

    ready: list[tuple[StudyKey, str]] = [
        (keys[uid], uid) for uid, needs in blocking.items() if not needs
    ]
    heapq.heapify(ready)

    out: list[Card] = []
    while ready:
        _, uid = heapq.heappop(ready)
        out.append(by_uid[uid])
        for dependent in unblocks[uid]:
            blocking[dependent].discard(uid)
            if not blocking[dependent]:
                heapq.heappush(ready, (keys[dependent], dependent))

    if len(out) < len(cards):
        # A cycle. `check` refuses one, so this is belt and braces: place the
        # rest by key rather than dropping them on the floor.
        placed = {card.uid for card in out}
        out.extend(sorted((c for c in cards if c.uid not in placed), key=lambda c: keys[c.uid]))
    return out


def template_drift(client: AnkiConnect, config: Config) -> list[str]:
    """Where the live note type differs from `notetype.py`.

    `sync` has never pushed a template, which is deliberate: the template is
    also yours to edit in Anki, and overwriting it on every content sync would
    quietly undo any change you made there. But silence was the wrong other
    half -- a change to the card layout here simply never arrived, with
    nothing saying so.
    """
    spec = notetype.spec(config.note_type)
    drift: list[str] = []
    live_templates = client.model_templates(config.note_type)
    for template in spec["cardTemplates"]:
        name = template["Name"]
        live = live_templates.get(name)
        if live is None and len(live_templates) == 1:
            # The note type was renamed and the template has not caught up yet
            # (Anki does not rename one with the other). Compare content against
            # the only template there is; `ensure_collection` fixes the name.
            live = next(iter(live_templates.values()))
        live = live or {}
        for side in ("Front", "Back"):
            if live.get(side, "") != template[side]:
                drift.append(f"{name}/{side}")
    if client.model_styling(config.note_type).strip() != spec["css"].strip():
        drift.append("css")
    return drift


def push_templates(
    client: AnkiConnect, config: Config, *, dry_run: bool
) -> list[CardOutcome]:
    """Make the live note type's layout match `notetype.py`. Fields are not
    touched here; `ensure_collection` owns those."""
    spec = notetype.spec(config.note_type)
    if not dry_run:
        client.update_model_templates(
            config.note_type,
            {t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in spec["cardTemplates"]},
        )
        client.update_model_styling(config.note_type, spec["css"])
    return [CardOutcome("-", "setup", "pushed the card template and styling")]


def rename_card_template(
    client: AnkiConnect, config: Config, *, dry_run: bool
) -> list[str]:
    """Bring the one card template's name into line after a note type rename.

    Anki renames a note type without renaming its templates, and cards
    reference a template by ordinal rather than by name, so this is a label and
    nothing else. It still has to be right: `updateModelTemplates` keys on the
    name, so pushing under a name the note type does not have would add a
    *second* template, and with it a second card for every note.
    """
    want = notetype.CARD_TEMPLATE
    live = client.model_templates(config.note_type)
    if want in live or not live:
        return []
    # This note type has exactly one template, so a single one under any name
    # is ours, whatever it used to be called. Matching on the old name is not
    # possible anyway: it was built from the note type's *previous* name, which
    # is the one piece of information a rename destroys.
    if len(live) != 1:
        raise AnkiError(
            f"note type {config.note_type!r} has card templates {sorted(live)}, "
            f"expected one named {want!r}. Remove the one that is not ours; "
            "`sync` will not guess which of them holds your cards."
        )
    stale = next(iter(live))
    if not dry_run:
        client.model_template_rename(config.note_type, stale, want)
    return [f"card template {stale!r} renamed to {want!r}"]


def ensure_collection(
    client: AnkiConnect, config: Config, cards: list[Card], *, dry_run: bool
) -> list[str]:
    """Make sure every deck in play and the note type exist; report what was
    created."""
    created: list[str] = []
    live_decks = set(client.deck_names())
    for deck in decks_for(cards, config):
        if deck in live_decks:
            continue
        if not dry_run:
            client.create_deck(deck)
        created.append(f"deck {deck!r}")
    live_models = set(client.model_names())
    if config.note_type not in live_models:
        # A name this note type used to have, still in the collection, means the
        # name was changed here and not there. Creating the new one would leave
        # every existing note on the old type: still in Anki, invisible to
        # `sync`, and re-added as new the moment anything syncs. Anki can rename
        # a note type in place without touching a single review, so say that
        # rather than doing something irreversible.
        stale = [name for name in notetype.PREVIOUS_NAMES if name in live_models]
        if stale:
            raise AnkiError(
                f"note type {config.note_type!r} is missing, but {stale[0]!r} is in "
                "the collection. Rename it in Anki (Tools > Manage Note Types > "
                f"Rename) to {config.note_type!r}, which keeps every note and its "
                "review history, and sync again. Setting `note_type_name` back to "
                f"{stale[0].rsplit(' v', 1)[0]!r} also works."
            )
        if not dry_run:
            client.create_model(notetype.spec(config.note_type))
        created.append(f"note type {config.note_type!r}")
    else:
        created.extend(rename_card_template(client, config, dry_run=dry_run))
        existing = client.model_field_names(config.note_type)
        if existing != notetype.FIELDS:
            # A field we have and the collection does not is an *addition*, and
            # adding it in place is safe. Bumping the version instead would
            # rename the note type, and `sync` finds notes by that name -- so
            # every existing note would be orphaned with its review history and
            # re-added as new. Anything else (a renamed or removed field) is
            # still a mismatch nobody should paper over.
            if existing not in notetype.PREVIOUS_FIELDS:
                raise AnkiError(
                    f"note type {config.note_type!r} exists with fields {existing}, "
                    f"expected {notetype.FIELDS}. Bump `note_type_version` in "
                    "forge.toml rather than mutating a live note type."
                )
            missing = [f for f in notetype.FIELDS if f not in existing]
            for name in missing:
                if not dry_run:
                    client.model_field_add(
                        config.note_type, name, notetype.FIELDS.index(name)
                    )
                created.append(f"field {name!r} on {config.note_type!r}")
    return created


NEW_CARD_TYPE = 0


def reposition(
    client: AnkiConnect, config: Config, cards: list[Card], *, dry_run: bool
) -> list[CardOutcome]:
    """Put the deck's *unstudied* cards into study order.

    Adding in order is enough for cards that do not exist yet; this is for the
    ones already in Anki, which carry whatever position they happened to get
    when they were first synced.

    Only `type == 0` cards are touched. Past that point `due` is a date, and
    rewriting it would move somebody's review to 1970 or to the year 6000.
    Cards you have already started are left exactly where they are, and said
    so in the report.
    """
    outcomes: list[CardOutcome] = []
    by_uid = {card.uid: card for card in cards}
    wanted = [c.uid for c in in_study_order(cards, source_positions(config), config.study_order)]

    positions: dict[str, tuple[int, int]] = {}
    studied: list[str] = []
    for deck in decks_for(cards, config):
        ids = client.find_cards(f'deck:"{deck}"')
        for info in client.cards_info(ids):
            uid = str(info.get("fields", {}).get("uid", {}).get("value", "")).strip()
            if uid not in by_uid:
                continue
            if int(info.get("type", 0)) != NEW_CARD_TYPE:
                studied.append(uid)
                continue
            positions[uid] = (int(info["cardId"]), int(info["due"]))

    if studied:
        outcomes.append(
            CardOutcome(
                "-",
                "skip",
                f"{len(studied)} card(s) already studied — position left alone",
            )
        )
    if not positions:
        return outcomes

    # Start where the deck already sits, so it keeps its place relative to
    # every other deck's new cards rather than jumping to the front.
    start = min(due for _, due in positions.values())
    moved = 0
    for offset, uid in enumerate(u for u in wanted if u in positions):
        card_id, current = positions[uid]
        target = start + offset
        if current == target:
            continue
        if not dry_run:
            client.set_new_position(card_id, target)
        moved += 1
    outcomes.append(
        CardOutcome(
            "-",
            "setup",
            f"repositioned {moved} of {len(positions)} new card(s) into study order",
        )
    )
    return outcomes


def run(
    config: Config,
    *,
    client: AnkiConnect | None = None,
    dry_run: bool = False,
    reposition_new: bool = False,
    templates: bool = False,
    move_decks: bool = False,
) -> SyncReport:
    """Lint, then upsert every approved card.

    `move_decks` also files cards that predate a `deck` change under the name
    the config now gives them. Off by default: everything else here adds to a
    collection, and this moves something that may have been filed by hand.
    """
    client = client or AnkiConnect(config.anki_url)
    report = SyncReport(dry_run=dry_run)

    cards, findings = check.check_repo(config)
    ready, skipped = syncable(cards)
    report.outcomes.extend(skipped)

    live = live_uid_counts(client, config)
    report.findings = check.check_deck(ready, config, for_sync=True, live_uids=live)
    report.findings.extend(
        f for f in findings if f.level == check.ERROR and f.code == "unparseable"
    )
    if check.errors(report.findings):
        return report

    # Nothing approved: do not conjure a deck or a note type for it.
    if ready:
        try:
            created = ensure_collection(client, config, ready, dry_run=dry_run)
        except AnkiError as exc:
            report.outcomes.append(CardOutcome("-", "error", str(exc)))
            return report
        for what in created:
            report.outcomes.append(CardOutcome("-", "setup", f"created {what}"))

        # Added in study order: Anki numbers a new card by when it arrives,
        # and its default new-card order is that position. Getting the order
        # right at insertion costs nothing and needs no repositioning later.
        for card in in_study_order(ready, source_positions(config), config.study_order):
            try:
                report.outcomes.append(_upsert(client, config, card, dry_run=dry_run))
            except AnkiError as exc:
                report.outcomes.append(CardOutcome(card.uid, "error", str(exc)))

    if ready:
        # After the upserts, so a card added by this run is already where it
        # belongs and only the ones that predate the setting are named.
        named = {c.uid: c.gist for c in ready}
        for moved in deck_drift(client, config, ready):
            if move_decks and not dry_run:
                client.change_deck(moved.cards, moved.wanted)
                report.outcomes.append(
                    CardOutcome(
                        moved.uid,
                        "move",
                        f"{moved.now} -> {moved.wanted}",
                        gist=named.get(moved.uid, ""),
                    )
                )
            else:
                report.outcomes.append(
                    CardOutcome(
                        moved.uid,
                        "skip",
                        f"filed under \"{moved.now}\" but this source now asks for "
                        f"\"{moved.wanted}\"; `sync --move-decks` moves it",
                        gist=named.get(moved.uid, ""),
                    )
                )

    if ready:
        try:
            drift = template_drift(client, config)
            if drift and templates:
                report.outcomes.extend(push_templates(client, config, dry_run=dry_run))
            elif drift:
                report.outcomes.append(
                    CardOutcome(
                        "-",
                        "skip",
                        f"card layout in Anki differs from notetype.py ({', '.join(drift)}); "
                        "`--templates` pushes it",
                    )
                )
        except AnkiError as exc:
            report.outcomes.append(CardOutcome("-", "error", str(exc)))

    if reposition_new and ready:
        try:
            report.outcomes.extend(reposition(client, config, ready, dry_run=dry_run))
        except AnkiError as exc:
            report.outcomes.append(CardOutcome("-", "error", str(exc)))

    # Notes in Anki whose card is no longer approved. Reported, never deleted.
    approved_uids = {c.uid for c in ready}
    repo_uids = {c.uid for c in cards}
    for uid in sorted(set(live) - approved_uids):
        detail = "card is no longer approved" if uid in repo_uids else "no card file in the repo"
        report.outcomes.append(CardOutcome(uid, "skip", f"in Anki but {detail}"))

    return report


@dataclass
class DeckDrift:
    """Cards sitting in a deck their source no longer asks for."""

    uid: str
    now: str
    wanted: str
    cards: list[int]


def deck_drift(client: AnkiConnect, config: Config, cards: list[Card]) -> list[DeckDrift]:
    """Approved cards whose notes are filed somewhere the config disagrees with.

    Anki settles a card's deck when the note is added, so editing `deck`
    afterwards changes where the *next* card goes and nothing else. Without
    this the only symptom is one source spread over two decks, noticed weeks
    later.

    Two calls for the whole deck rather than two per card: every card of this
    note type, then their decks in one batch.
    """
    wanted = {c.uid: config.deck_for(c.project_name, c.type) for c in cards}
    if not wanted:
        return []
    found = client.cards_info(client.find_cards(f'"note:{config.note_type}"'))
    where: dict[str, tuple[str, list[int]]] = {}
    for info in found:
        uid = str((info.get("fields", {}).get("uid") or {}).get("value", ""))
        deck = str(info.get("deckName", ""))
        card_id = int(info.get("cardId", 0))
        if not uid or uid not in wanted:
            continue
        # A note can have several cards, and they can sit in different decks.
        # The first deck seen names the drift; every card of the note moves.
        here, ids = where.get(uid, (deck, []))
        where[uid] = (here, [*ids, card_id])
    return [
        DeckDrift(uid, now, wanted[uid], ids)
        for uid, (now, ids) in sorted(where.items())
        if now != wanted[uid]
    ]


def _upsert(client: AnkiConnect, config: Config, card: Card, *, dry_run: bool) -> CardOutcome:
    fields = fields_for(card, config)
    # Before the note, and not on a rehearsal: a dry run must not write to the
    # media folder any more than it writes a note.
    if card.images() and not dry_run:
        upload_images(client, config, card)
    tags = tags_for(card, config)
    note_ids = client.find_notes(f'"note:{config.note_type}" "uid:{card.uid}"')

    if len(note_ids) > 1:
        return CardOutcome(
            card.uid,
            "error",
            f"{len(note_ids)} notes already carry this uid",
            gist=card.gist,
        )

    if not note_ids:
        deck = config.deck_for(card.project_name, card.type)
        if not dry_run:
            client.add_note(deck, config.note_type, fields, tags)
        return CardOutcome(card.uid, "add", f"-> {deck}", gist=card.gist)

    note_id = note_ids[0]
    info = client.notes_info([note_id])
    current_fields, current_tags = _note_state(info)
    field_changes = {k: v for k, v in fields.items() if current_fields.get(k, "") != v}
    tag_changes = sorted(set(tags) - current_tags), sorted(current_tags - set(tags))

    if not field_changes and not any(tag_changes):
        return CardOutcome(card.uid, "unchanged", gist=card.gist)

    if not dry_run:
        if field_changes:
            client.update_note_fields(note_id, fields)
        if tag_changes[0]:
            client.add_tags([note_id], " ".join(tag_changes[0]))
        if tag_changes[1]:
            client.remove_tags([note_id], " ".join(tag_changes[1]))

    changed = [
        *sorted(field_changes),
        *(f"+{t}" for t in tag_changes[0]),
        *(f"-{t}" for t in tag_changes[1]),
    ]
    return CardOutcome(card.uid, "update", ", ".join(changed), gist=card.gist)


def _note_state(info: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    if not info:
        return {}, set()
    raw_fields = info[0].get("fields", {}) or {}
    fields = {name: str(value.get("value", "")) for name, value in raw_fields.items()}
    return fields, {str(t) for t in info[0].get("tags", []) or []}
