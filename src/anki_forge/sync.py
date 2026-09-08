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
from dataclasses import dataclass, field
from typing import Any

from . import check, latex, model, notetype
from .anki import AnkiConnect, AnkiError
from .config import Config
from .model import Card

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
    if card.unit:
        parts = [p for p in card.unit.split(":") if p][:2]
        tags.add("src::" + "::".join(parts))
    elif card.source:
        tags.add("src::" + model.slugify(card.source))
    return sorted(_TAG_SAFE.sub("_", t).strip("_") for t in tags if t.strip())


def fields_for(card: Card, config: Config) -> dict[str, str]:
    fields = {
        "uid": card.uid,
        "Front": to_anki_html(card.section("front") or ""),
        "Back": to_anki_html(card.section("back") or ""),
        "Source": html.escape(card.source, quote=False),
    }
    for name, section in OPTIONAL_FIELD_SECTIONS.items():
        fields[name] = to_anki_html(card.section(section) or "")
    # `## notes` and `## verify` never reach any field (§9).
    return fields


# -- planning and execution ------------------------------------------------


@dataclass
class CardOutcome:
    uid: str
    action: str  # setup | add | update | unchanged | skip | error
    detail: str = ""

    def format(self) -> str:
        suffix = f" -- {self.detail}" if self.detail else ""
        return f"{self.action:9} {self.uid}{suffix}"


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
        actions = ("add", "update", "unchanged", "skip", "error")
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
            skipped.append(CardOutcome(card.uid, "skip", "open @claude annotation"))
        elif card.effective_status != "approved":
            # Say *why* a card that claims to be approved is not going: an
            # edit since approval is a different situation from a draft.
            detail = (
                "approved, but edited since -- re-review it"
                if card.status == "approved"
                else f"status is {card.status}"
            )
            skipped.append(CardOutcome(card.uid, "skip", detail))
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
    return sorted({config.deck_for(card.source_name) for card in cards})


def study_key(card: Card) -> tuple[int, int, str]:
    """Where a card belongs in the new-card queue.

    Most useful first, then easiest first: `frequency` core before common
    before rare, and within a frequency `derivation` definitional before
    short before long. Both vocabularies are already declared in that order,
    so the rank is their index and adding a value in the right place is all
    it takes to keep this honest.

    A card missing either annotation sorts last within its group rather than
    first, because an unannotated card is unjudged, not easy. `uid` breaks
    ties so the order is stable across runs.
    """
    frequency = model.FREQUENCIES.index(card.frequency) if card.frequency else len(
        model.FREQUENCIES
    )
    derivation = model.DERIVATIONS.index(card.derivation) if card.derivation else len(
        model.DERIVATIONS
    )
    return (frequency, derivation, card.uid)


def in_study_order(cards: list[Card]) -> list[Card]:
    return sorted(cards, key=study_key)


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
    if config.note_type not in client.model_names():
        if not dry_run:
            client.create_model(notetype.spec(config.note_type))
        created.append(f"note type {config.note_type!r}")
    else:
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
                    "anki-forge.toml rather than mutating a live note type."
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
    wanted = [c.uid for c in in_study_order(cards)]

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
) -> SyncReport:
    """Lint, then upsert every approved card."""
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
        for card in in_study_order(ready):
            try:
                report.outcomes.append(_upsert(client, config, card, dry_run=dry_run))
            except AnkiError as exc:
                report.outcomes.append(CardOutcome(card.uid, "error", str(exc)))

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


def _upsert(client: AnkiConnect, config: Config, card: Card, *, dry_run: bool) -> CardOutcome:
    fields = fields_for(card, config)
    tags = tags_for(card, config)
    note_ids = client.find_notes(f'"note:{config.note_type}" "uid:{card.uid}"')

    if len(note_ids) > 1:
        return CardOutcome(card.uid, "error", f"{len(note_ids)} notes already carry this uid")

    if not note_ids:
        deck = config.deck_for(card.source_name)
        if not dry_run:
            client.add_note(deck, config.note_type, fields, tags)
        return CardOutcome(card.uid, "add", f"-> {deck}")

    note_id = note_ids[0]
    info = client.notes_info([note_id])
    current_fields, current_tags = _note_state(info)
    field_changes = {k: v for k, v in fields.items() if current_fields.get(k, "") != v}
    tag_changes = sorted(set(tags) - current_tags), sorted(current_tags - set(tags))

    if not field_changes and not any(tag_changes):
        return CardOutcome(card.uid, "unchanged")

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
    return CardOutcome(card.uid, "update", ", ".join(changed))


def _note_state(info: list[dict[str, Any]]) -> tuple[dict[str, str], set[str]]:
    if not info:
        return {}, set()
    raw_fields = info[0].get("fields", {}) or {}
    fields = {name: str(value.get("value", "")) for name, value in raw_fields.items()}
    return fields, {str(t) for t in info[0].get("tags", []) or []}
