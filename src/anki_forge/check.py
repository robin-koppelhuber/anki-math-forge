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
from .config import Config
from .model import Card

ERROR = "error"
WARN = "warn"


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

    # -- identity ---------------------------------------------------------
    if not card.uid:
        add(ERROR, "uid-missing", "no `uid` in frontmatter")
    elif not model.UID_RE.match(card.uid):
        add(ERROR, "uid-malformed", f"uid {card.uid!r} is not 6 lowercase hex characters")

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
        if section.name in {"notes", "verify"}:
            continue  # scratchpad and executable python, not rendered math
        if latex.unbalanced_dollars(section.body):
            add(ERROR, "latex-dollars", f"`## {section.name}`: unbalanced `$` delimiters")
        for err in tex.validate_text(section.body):
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
