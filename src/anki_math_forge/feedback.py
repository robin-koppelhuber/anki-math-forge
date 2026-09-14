"""`feedback` -- pull review notes back out of Anki (DESIGN.md §9).

This is the one place anything is *read* from Anki, and the invariant survives
only because the read is a hand-off rather than a source of truth. A comment
is imported, written into the card's `## notes` as an annotation, and then
**erased from Anki in the same pass**. Nothing consults Anki about that text
again, and nothing in Anki ever wins over a file.

An imported note is addressed like any other: `@claude` unless it says
otherwise, and a comment that opens `@me` stays a decision parked for you
rather than a brief for the card writer. `model.annotation_line` decides that
for every writer, here included.

Erasing is not tidiness. Without it every run would re-import the same
comment, and a note you had already resolved through `/triage` would come back
from the dead on the next pull.

Two ways in, because they suit different moments:

* the **Feedback field**, for when you have the words. It is on the note type
  but on no template, so it never renders during review and always shows in
  the editor.
* a **flag**, for when you do not. One keystroke, and `[anki.flags]` in
  `forge.toml` says what each colour means, so the meaning is yours to
  set rather than baked in here. A meaning may open `@me`, which is how one
  colour comes back as a decision for you.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

from . import model
from .anki import AnkiConnect, AnkiError
from .config import Config

FEEDBACK_FIELD = "Feedback"
NO_FLAG = 0

# Both ends of a block tag, not just the closing one: Anki wraps each
# line of the editor in its own <div>, so "a<div>b</div>" is two lines
# and would otherwise come back as "ab".
_BREAK = re.compile(r"<\s*/?\s*(?:br|div|p|li|tr|blockquote)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")


def plain_text(raw: str) -> str:
    """Anki's editor stores HTML; an annotation is one line of text.

    Block ends become spaces rather than newlines because `## notes` is
    line-based: a note that wrapped onto a second line would read back as a
    second, unaddressed annotation.
    """
    text = _BREAK.sub(" ", raw)
    text = _TAG.sub("", text)
    # A non-breaking space is still a space once it is out of HTML.
    text = html.unescape(text).replace("\u00a0", " ")
    return " ".join(text.split())


@dataclass(frozen=True)
class Comment:
    uid: str
    text: str
    kind: str  # "field" or "flag"
    note_id: int
    card_ids: tuple[int, ...] = ()


@dataclass
class FeedbackReport:
    dry_run: bool = False
    imported: list[Comment] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(reason.startswith("error") for _, reason in self.skipped)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "imported": [
                {"uid": c.uid, "kind": c.kind, "text": c.text} for c in self.imported
            ],
            "skipped": [{"ref": ref, "reason": reason} for ref, reason in self.skipped],
        }


def collect(config: Config, client: AnkiConnect) -> tuple[list[Comment], list[tuple[str, str]]]:
    """Everything waiting in Anki, and everything that could not be taken."""
    comments: list[Comment] = []
    skipped: list[tuple[str, str]] = []

    known = {card.uid for card in model.load_all(config.cards_dir)}
    note_ids = client.find_notes(f'"note:{config.note_type}"')
    if not note_ids:
        return comments, skipped

    by_note: dict[int, dict[str, Any]] = {}
    for info in client.notes_info(note_ids):
        by_note[int(info["noteId"])] = info

    # Flags live on cards, comments on notes, so both have to be looked up.
    flags: dict[int, list[tuple[int, int]]] = {}
    card_ids = client.find_cards(f'"note:{config.note_type}"')
    for info in client.cards_info(card_ids):
        flags.setdefault(int(info["note"]), []).append(
            (int(info["cardId"]), int(info.get("flags") or NO_FLAG))
        )

    for note_id, info in sorted(by_note.items()):
        fields = info.get("fields", {})
        uid = str(fields.get("uid", {}).get("value", "")).strip()
        raw = str(fields.get(FEEDBACK_FIELD, {}).get("value", ""))
        text = plain_text(raw)
        flagged = [(cid, n) for cid, n in flags.get(note_id, []) if n != NO_FLAG]

        if not text and not flagged:
            continue
        if uid not in known:
            # Leave it in Anki. A card file may be renamed or not yet written,
            # and clearing the only copy of a comment would destroy it.
            what = "a comment" if text else "a flag"
            skipped.append((uid or f"note {note_id}", f"{what}, but no card file with this uid"))
            continue

        if text:
            comments.append(Comment(uid, text, "field", note_id))
        for card_id, number in flagged:
            meaning = config.flags.get(number)
            if not meaning:
                skipped.append(
                    (uid, f"flag {number} is set, but [anki.flags] gives it no meaning")
                )
                continue
            comments.append(
                Comment(uid, flag_note(number, meaning), "flag", note_id, (card_id,))
            )
    return comments, skipped


def flag_note(number: int, meaning: str) -> str:
    """What a flag becomes, addressed to whoever its meaning names.

    A flag is one keystroke, so `[anki.flags]` is the only place there is to
    say what it meant -- and therefore the only place to say who it is for. A
    meaning written `@me consider dropping this` parks the decision with you;
    anything else is work for whoever writes the card, like every other
    annotation with no prefix of its own.
    """
    head, _, rest = meaning.partition(" ")
    if model.annotation_audience(head):
        return f"{head} flagged {number}: {rest.strip()}"
    return f"flagged {number}: {meaning}"


def run(
    config: Config, *, client: AnkiConnect | None = None, dry_run: bool = False
) -> FeedbackReport:
    """Import every waiting comment, then clear it from Anki."""
    client = client or AnkiConnect(config.anki_url)
    report = FeedbackReport(dry_run=dry_run)
    try:
        comments, skipped = collect(config, client)
    except AnkiError as exc:
        report.skipped.append(("-", f"error: {exc}"))
        return report
    report.skipped.extend(skipped)

    for comment in comments:
        card = model.find(config.cards_dir, comment.uid)
        if card is None or card.path is None:
            report.skipped.append((comment.uid, "card file disappeared mid-run"))
            continue
        line = model.annotation_line(comment.text)
        if line in card.annotations():
            # Already recorded and not yet resolved. Clear the source anyway,
            # so it does not queue up behind itself.
            report.skipped.append((comment.uid, "already recorded; cleared in Anki"))
        elif not dry_run:
            card.add_annotation(line)
            card.save()

        if not dry_run:
            try:
                if comment.kind == "field":
                    client.update_note_fields(comment.note_id, {FEEDBACK_FIELD: ""})
                else:
                    for card_id in comment.card_ids:
                        client.set_card_flag(card_id, NO_FLAG)
            except AnkiError as exc:
                report.skipped.append((comment.uid, f"error: recorded but not cleared: {exc}"))
                continue
        report.imported.append(comment)
    return report
