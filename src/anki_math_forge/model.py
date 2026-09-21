"""Card files: parse, render, hash, write.

A card is one markdown file: YAML frontmatter plus `## section` bodies
(DESIGN.md §5). Parsing is round-trip stable -- `parse(render(card)) == card`
and, for a file already in canonical form, `render(parse(text)) == text`.
Everything else in this package leans on that, so keep it dull.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

# Frontmatter keys in the order they are written back out. Unknown keys keep
# their relative order and land after these.
# ASCII record separator: it cannot occur in card text, so joining on it
# cannot make two different cards hash the same.
HASH_SEPARATOR = chr(30)

FRONTMATTER_ORDER = (
    "uid",
    "type",
    "status",
    "content_hash",
    "source",
    "unit",
    "gist",
    "frequency",
    "derivation",
    "requires",
    "tags",
    "verify",
    "web",
    "augmented",
)

# Two optional judgements about a card, both coarse on purpose.
#
# `frequency` -- how often this identity actually turns up. It decides what is
# worth carding at all, and what deserves to come back often.
#
# `derivation` -- what it would take to reconstruct it. `definitional` is the
# one that matters: some facts are true by definition and have nothing to
# derive, so "how hard to derive" is the wrong question for them. They are
# recognised, not reconstructed, and that is a different kind of review.
#
# Three values each, and no numbers: a 1-10 scale here would be invented
# precision that no two sessions would apply the same way.
FREQUENCIES = ("core", "common", "rare")
DERIVATIONS = ("definitional", "short", "long")

# Canonical section order. Unknown sections keep file order and land after.
# Reading order on the card, and the order sections are written in a file.
# `prose` comes straight after the answer because it is one sentence and it
# interprets: the short thing first, then the longer ones. It is also the only
# unlabelled block, so putting it between two labelled ones left no way to see
# where `proof` ended and it began.
SECTION_ORDER = (
    "front",
    "back",
    "conditions",
    "prose",
    "uses",
    "proof",
    "verify",
    "notes",
)

# Sections allowed per `type` (DESIGN.md §7: "section whitelist for the
# declared type").
#
# `identity` states a mathematical fact: it has a definite answer, and `verify`
# can check it numerically.
#
# `intuition` explains one. It is what a marked passage in a prose source turns
# into -- why a bound is tight, what a term is really measuring, which of two
# conditions is doing the work. Two sections come off it. `verify` has nothing
# to run against an explanation, and `conditions` belongs to a statement rather
# than to a reading of one; anything that genuinely needs a hypothesis stated
# is an identity wearing the wrong type.
SECTIONS_BY_TYPE: dict[str, frozenset[str]] = {
    "identity": frozenset(SECTION_ORDER),
    "intuition": frozenset(SECTION_ORDER) - {"verify", "conditions"},
}

REQUIRED_SECTIONS = ("front", "back")

# `## notes` never syncs and never enters the content hash (DESIGN.md §8):
# annotating a card is not an edit of the card, but the fix that resolves the
# annotation is.
# `verify` is a check on the author, not card content: it never reaches Anki
# (see notetype.FIELDS) and no reviewer sees it. Hashing it meant that fixing
# a test un-approved a card whose mathematics had not changed. If the claim
# itself changes, `front` or `back` changes with it and the hash moves anyway.
UNHASHED_SECTIONS = frozenset({"notes", "verify"})
# `verify` joins them for the same reason `## verify` is unhashed: it says
# whether a numeric check runs, not what the card claims. It never reaches
# Anki and no reviewer sees it. Leaving it hashed meant turning a test *on*
# un-approved a card whose mathematics had not changed -- precisely what
# exempting the section was for, undone by the flag that enables it.
# `frequency` and `derivation` join them on `requires`'s argument, spelled out
# in CLAUDE.md: approving a card is not approving its position in the queue.
# Both are coarse judgements about *when you should meet* this card, both reach
# Anki as tags that `sync` updates without re-approval, and neither changes a
# word a reviewer read. Hashing them meant that deciding a result was `common`
# rather than `core` -- which is a thing you learn months later, from meeting
# it -- silently un-approved a card whose mathematics nobody had touched.
#
# `web` is a permission granted to whoever writes or augments the card. It is
# not a claim the card makes, and it is set from the review view with one
# click; an approval is not a statement about it.
#
# `gist` is a caption. It never reaches Anki, no reviewer sees it, and nothing
# writes card content from it -- it names the card in a list or on a graph node
# where the LaTeX front is unreadable. A later pass refining the wording must
# not cost a re-review of mathematics nobody touched. Safe to add without
# re-stamping anything: no card carries the key yet, so exempting it changes no
# digest that exists.
#
# `augmented` records that a pass has been over the card, which is a fact about
# the work and not about the claim. It is also the one state here that cannot
# be read off the content: augmentation's right answer is usually to add
# nothing, so a finished card and an untouched one are the same file. Hashing
# it would mean the pass un-approved every card it decided to leave alone.
#
# `tags` is filing, and the hash covers what a reviewer read. The argument is
# already made by the two above it: `frequency` and `derivation` are exempt and
# *both become Anki tags*, so hashing `tags` meant `freq::core` could change
# without a re-review while `tags: [core]` could not, which is an accident of
# which field a value lives in rather than a policy. Change
# `matrix-calculus` to `linear-algebra` and the claim on the card is
# identical; a tag that changes what the question means belongs in
# `## conditions`, which renders with the front. It is also what lets a deck
# be routed by tag (ROADMAP.md 10) without re-tagging counting as an edit.
UNHASHED_FRONTMATTER = frozenset({
    "status",
    "content_hash",
    "requires",
    "verify",
    "frequency",
    "derivation",
    "web",
    "gist",
    "augmented",
    "tags",
})

# There used to be a second, older exemption set here, accepted as a fallback
# so that widening the one above did not report a whole deck as edited on the
# strength of a code change. Exempting `tags` retired it: tags were hashed
# under *both* earlier rules, so the fallback caught nothing, and every
# approval had to be re-stamped anyway. One rule is the simpler thing to
# reason about, and the next widening re-stamps rather than accumulating a
# third digest. See ROADMAP.md 10, "migrating rather than staying
# compatible".

STATUSES = ("draft", "approved", "rejected")

# An annotation is an instruction for the next pass over this thing, and it
# is addressed. `@claude` is work for the model -- fix this, check that.
# `@me` is a decision only the human can make, parked where it will be found
# again. Both block sync, because both mean "this is not finished".
#: What a settled annotation is written back as. Deliberately not an address:
#: `annotation_audience` reads a prefix only at the start of a line, so this
#: is not an annotation, does not hold the card out of sync, and is not work
#: the next pass will pick up. It is the same shape `Ledger.answer` leaves on
#: a unit, with a marker on the front so the view can group them.
RESOLVED_PREFIX = "resolved:"

ANNOTATION_PREFIX = "@claude"
ANNOTATION_PREFIXES = ("@claude", "@me")


def annotation_audience(line: str) -> str:
    """`claude`, `me`, or "" if this line is not an annotation at all.

    The prefix has to end where it ends: a bare `startswith` read `@metric
    space bound is wrong` as an `@me` note, which is a plausible enough
    opening for a note about mathematics to be worth ruling out.
    """
    head = line.strip().lower()
    for prefix in ANNOTATION_PREFIXES:
        if head.startswith(prefix) and not head[len(prefix) : len(prefix) + 1].isalnum():
            return prefix[1:]
    return ""


def resolved_line(asked: str, reply: str) -> str:
    """One settled annotation: what was asked, and what was done about it.

    The question is most of what makes the answer worth keeping. "Fixed" on
    its own is the thing you cannot act on six weeks later, and it is what you
    get when the line that prompted it has been deleted.
    """
    asked = " ".join(note_body(asked).split()).strip()
    reply = " ".join(reply.split()).strip()
    if not reply:
        # No answer, no record. The same call `Ledger.answer` makes: a note
        # that was a reminder rather than a request leaves nothing worth
        # keeping, and "resolved: have another look" has kept the half that
        # was never the point.
        return ""
    body = f"{asked} \u2014 {reply}" if asked else reply
    return f"{RESOLVED_PREFIX} {body}"


def is_resolved(line: str) -> bool:
    return line.strip().lower().startswith(RESOLVED_PREFIX)


def resolved_body(line: str) -> str:
    """A record without its marker, for showing."""
    return line.strip()[len(RESOLVED_PREFIX) :].strip() if is_resolved(line) else line.strip()


def note_body(note: str) -> str:
    """An annotation without its `@claude` / `@me` prefix.

    Stripping only what is actually there, rather than a fixed width, so a
    hand-edited note that does not carry the exact prefix survives intact.
    """
    audience = annotation_audience(note)
    return note.strip() if not audience else note.strip()[len(audience) + 1 :].strip()


def annotation_line(text: str) -> str:
    """One annotation as it is written to a file: collapsed, and addressed.

    The default prefix goes on only when the text does not already carry one,
    so text that names its own audience keeps it. Every writer goes through
    here rather than building the line itself: `feedback` built `"@claude " +
    text` by hand, which turned a comment typed into Anki as `@me decide
    whether to keep this` into `@claude @me decide ...` -- audience `claude`,
    a decision of yours queued as work for the agent.
    """
    text = " ".join(text.split()).strip()
    if text and not annotation_audience(text):
        text = f"{ANNOTATION_PREFIX} {text}"
    return text


#: A picture on a card: `![what it shows](unit:<id>)`, or `![...](unit)` for
#: the unit the card was written from. Markdown's own image syntax, with a
#: unit where a filename would go -- because there is no file: the crop is
#: rendered from the source document at sync time.
#:
#: **Where it goes is the writer's call.** A figure that *is* the answer
#: belongs in `## back`; one you are asked to read belongs in `## front`; a
#: diagram that supports an explanation belongs in `## prose`. No rule here
#: can tell those apart, and every section this matches is inside
#: `content_hash`, so swapping the picture un-approves the card either way.
IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(unit(?::([^)\s]+))?\)")

#: Sections a picture cannot go in. `verify` is Python and `notes` never
#: reaches Anki, so an image in either is one nobody will ever see.
UNRENDERED_SECTIONS = frozenset({"notes", "verify"})


# A fenced code block on a card, and the language it names.
#
# One regex, shared by `check`, `sync` and the review view, because the three
# have to agree about where code starts and stops or a block lints as maths in
# one place and renders as code in another. The language is optional and may
# be empty, which is what a fence with no word after it means.
#: A shelf line nobody has agreed to yet: `- [ ] cppreference, the container
#: library`. A pass proposes with the checkbox, accepting takes it off, and
#: rejecting deletes the line. Markdown everyone already writes for "not
#: yet", so the file stays something you can settle in an editor.
PROPOSED_RE = re.compile(r"^[-*]\s*\[\s*\]\s*")

CODE_FENCE_RE = re.compile(r"```([A-Za-z0-9_+#-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def code_free(text: str) -> str:
    """The section with its fenced code taken out.

    For the checks that read a body as prose or as maths. Code is neither:
    it is full of braces, backslashes and `$`, so KaTeX refuses it, and it is
    deliberately written one statement per line, so a line-counting lint
    fires on exactly the shape that is correct.

    The fence is replaced by blank lines rather than deleted, so anything
    that reports a line number still points at the right line.
    """
    return CODE_FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


@dataclass(frozen=True)
class ImageRef:
    """One `![...](unit:...)` on a card, resolved."""

    raw: str  # exactly as written, so a rewrite can replace it
    alt: str
    unit: str  # the unit named, or the card's own when none was
    section: str
    # Where among this card's images it falls. The media name Anki stores is
    # built from this, so it is stable across a re-sync and a second sync
    # overwrites rather than leaving an orphan behind.
    index: int = 0


UID_RE = re.compile(r"^[0-9a-f]{6}$")
_SECTION_RE = re.compile(r"^##[ \t]+([A-Za-z][A-Za-z0-9_-]*)[ \t]*$")
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)(?:\n)---[ \t]*(?:\n|\Z)", re.DOTALL)


class CardError(Exception):
    """A card file could not be parsed."""


class StaleFileError(Exception):
    """The file changed on disk since it was loaded (DESIGN.md §6)."""


@dataclass
class Section:
    name: str
    body: str

    def canonical(self) -> Section:
        lines = [line.rstrip() for line in self.body.replace("\r\n", "\n").split("\n")]
        return Section(self.name, "\n".join(lines).strip("\n"))


@dataclass
class Card:
    frontmatter: dict[str, Any] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    preamble: str = ""
    path: Path | None = None
    mtime_ns: int | None = None

    # -- frontmatter accessors -------------------------------------------
    @property
    def uid(self) -> str:
        return str(self.frontmatter.get("uid", "") or "")

    @property
    def type(self) -> str:
        return str(self.frontmatter.get("type", "") or "")

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status", "draft") or "draft")

    @property
    def frequency(self) -> str:
        return str(self.frontmatter.get("frequency", "") or "")

    @property
    def derivation(self) -> str:
        return str(self.frontmatter.get("derivation", "") or "")

    @property
    def web(self) -> bool | None:
        """Whether whoever augments this card may look things up on the web.

        `None` means nothing was said here, which falls back to the card's
        unit, then its source, then the repo -- resolved by `Config.web_for`,
        not here, because this object does not know what a source is.
        """
        raw = self.frontmatter.get("web")
        return None if raw is None else bool(raw)

    @property
    def units(self) -> list[str]:
        """Every unit this card came from.

        A card is not one-to-one with a unit in either direction. One unit
        splits into several cards -- that already worked, because a unit
        carries a list of uids. Several units merge into one card, which is
        the common case for a multi-line display the segmenter cut into
        pieces, and that needs `unit` to accept a list.
        """
        raw = self.frontmatter.get("unit", "")
        if isinstance(raw, list):
            return [str(u).strip() for u in raw if str(u).strip()]
        return [u.strip() for u in str(raw or "").split(",") if u.strip()]

    @property
    def unit(self) -> str:
        """The first unit, for the things that need exactly one: the crop
        shown beside the card, and the `src::` tag."""
        units = self.units
        return units[0] if units else ""

    @property
    def source(self) -> str:
        return str(self.frontmatter.get("source", "") or "")

    @property
    def project_name(self) -> str:
        """The source *key*, read off the unit ids.

        `source` is the human citation ("Some Book, ss3.1, eq. 148"); this is
        the key that indexes `projects/` and `[projects.*]`, read off the unit
        id's first segment. Derived rather than stored, so it cannot drift from
        the unit the card actually came from. Empty when the card names no
        unit, which the app treats as "belongs to every source" rather than
        to none: a card with no home should be visible, not lost.
        """
        for unit in self.units:
            head = unit.split(":", 1)[0].strip()
            if head:
                return head
        return ""

    @property
    def section_name(self) -> str:
        """The source section, when the unit id encodes one.

        `<source>:<section>:<number>` is one shape a unit id takes, and it is
        the shape a segmenter working from a numbered book produces: `2.3` in
        `matrix-cookbook:2.3:66`. It is not the only shape. A unit imported
        from a marked-up PDF is `<source>:<annotation key>`, which has no
        section in it at all, and reading the middle segment there returned the
        annotation key -- so every card got its own "section", the review
        view's section rail listed one row per card, and the `src::` tag meant
        to suspend a batch wholesale named exactly one note.

        Derived rather than stored for the same reason as `project_name`: a card
        filed under a section it does not come from is a second truth waiting
        to disagree with the first. Two segments means there is nothing to
        derive, so it says so.
        """
        for unit in self.units:
            parts = unit.split(":")
            if len(parts) >= 3 and parts[1].strip():
                return parts[1].strip()
        return ""

    @property
    def gist(self) -> str:
        """A few words naming this card, for a list or a graph node.

        A card's own content is LaTeX: `$\\frac{\\partial}{\\partial X}
        \\prod_i \\lambda_i$` is the right thing to review and the wrong thing
        to label a box with. This is the name a person would use out loud.

        **Consumed as a label and never as instructions.** That is the line
        that keeps it as safe as a unit's gist: nothing writes card content
        from it, so a machine's wrong guess here is a wrong caption rather than
        a wrong card. Unhashed for the same reason, so refining it does not
        un-approve anything.

        Empty is the honest state for a card nobody has named. Callers show
        that rather than inventing a label out of the slug.
        """
        return str(self.frontmatter.get("gist") or "").strip()

    @property
    def requires(self) -> list[str]:
        """Cards that must be introduced before this one.

        The ordering respects this absolutely: a prerequisite outranks
        frequency, because meeting a result whose proof you cannot follow is
        worse than meeting a rare one early. Everything else is a tiebreak.

        Use it only for a real dependency -- this card's proof or notation
        rests on that one. Two cards on a theme are not a dependency, and a
        graph that says they are makes the order rigid for no gain.
        """
        raw = self.frontmatter.get("requires") or []
        if isinstance(raw, str):
            return [u.strip() for u in raw.split(",") if u.strip()]
        return [str(u).strip() for u in raw if str(u).strip()]

    @property
    def tags(self) -> list[str]:
        raw = self.frontmatter.get("tags") or []
        if isinstance(raw, str):
            return [t for t in raw.split() if t]
        return [str(t) for t in raw]

    @property
    def augmented(self) -> bool:
        """Whether `/augment` has been over this card.

        Recorded rather than derived, and it is the only thing here that is.
        The pass considers every optional section and adds the ones that earn
        their place, which for most cards is none of them -- so a card it
        finished and a card it never saw are the same file, and nothing in the
        content can tell them apart.

        Outside `content_hash`: it says what has been done to the card, not
        what the card claims. Take it off to ask for the pass again.
        """
        return bool(self.frontmatter.get("augmented", False))

    @property
    def verify_enabled(self) -> bool:
        return bool(self.frontmatter.get("verify", False))

    @property
    def stored_hash(self) -> str:
        return str(self.frontmatter.get("content_hash", "") or "")

    # -- sections ---------------------------------------------------------
    def section(self, name: str) -> str | None:
        for sec in self.sections:
            if sec.name == name:
                return sec.body
        return None

    def section_names(self) -> list[str]:
        return [s.name for s in self.sections]

    def set_section(self, name: str, body: str) -> None:
        for sec in self.sections:
            if sec.name == name:
                sec.body = body
                return
        self.sections.append(Section(name, body))
        self.sections = _sorted_sections(self.sections)

    def remove_section(self, name: str) -> None:
        self.sections = [s for s in self.sections if s.name != name]

    # -- pictures ----------------------------------------------------------
    def images(self) -> list[ImageRef]:
        """Every picture this card asks for, in reading order.

        `![alt](unit)` with no id means the unit the card was written from,
        which is the common case and the one worth not repeating: the card
        already says which unit it came from in its frontmatter. A card that
        names no unit and writes the bare form has an unresolvable reference,
        which `check` reports rather than this silently dropping.
        """
        found: list[ImageRef] = []
        for section in self.canonical().sections:
            if section.name in UNRENDERED_SECTIONS:
                continue
            for match in IMAGE_RE.finditer(section.body):
                found.append(
                    ImageRef(
                        raw=match.group(0),
                        alt=match.group(1).strip(),
                        unit=(match.group(2) or self.unit).strip(),
                        section=section.name,
                        index=len(found),
                    )
                )
        return found

    @property
    def has_image(self) -> bool:
        return bool(IMAGE_RE.search(self.body_text()))

    def body_text(self) -> str:
        """Every section that reaches Anki, joined. For a cheap scan."""
        return "\n".join(
            s.body for s in self.sections if s.name not in UNRENDERED_SECTIONS
        )

    # -- annotations (DESIGN.md §8) ---------------------------------------
    def annotations(self) -> list[str]:
        """Open `@claude ...` / `@me ...` lines from `## notes`, verbatim."""
        body = self.section("notes") or ""
        return [line.strip() for line in body.split(chr(10)) if annotation_audience(line)]

    def add_annotation(self, text: str) -> None:
        """Append an annotation, byte-identical to one typed by hand.

        `annotation_line` decides what is written, and it is idempotent, so a
        caller that has already built the line to compare against
        `annotations()` can pass that.
        """
        line = annotation_line(text)
        if not line:
            return
        body = self.section("notes")
        self.set_section("notes", f"{body}\n{line}" if body else line)

    def edit_annotation(self, index: int, text: str) -> str:
        """Rewrite the `index`-th annotation in place, and return what it says.

        Editing, not resolving: the line keeps its position and stays open, so
        the card stays out of sync until somebody answers it. A note is a
        scratchpad, and what you first wrote on it is often not what you meant;
        the alternative was resolve-and-retype, which deletes the only copy of
        the line before its replacement exists.

        `annotation_line` decides what is written, so a reworded note is
        byte-identical to one typed by hand, and dropping the `@me` off the
        front of one moves it to `@claude` exactly as editing the file would.
        """
        line = annotation_line(text)
        if not line:
            raise CardError(f"an empty annotation cannot replace {index} on card {self.uid}")
        lines = (self.section("notes") or "").splitlines()
        marked = [i for i, existing in enumerate(lines) if annotation_audience(existing)]
        if not 0 <= index < len(marked):
            raise CardError(f"no annotation {index} on card {self.uid}")
        lines[marked[index]] = line
        self.set_section("notes", "\n".join(lines).strip())
        return line

    def resolve_annotation(self, index: int, reply: str = "") -> str:
        """Settle the `index`-th annotation and return the line it removed.

        Resolving a note is deleting it **as an annotation**: a line that is
        still addressed still blocks sync, so there is no reply-in-place and
        no done-flag.

        With a `reply`, what it asked and what was done are written back
        unaddressed, in its position. That is the same trade `Ledger.answer`
        makes on a unit: deleting the line throws away the question, and the
        question is most of what made the answer worth keeping. Without one
        the line goes outright, which is right when the note was a reminder
        rather than a request.

        Non-annotation lines in `## notes` are left where they are, so a
        resolve never touches the prose around it.
        """
        lines = (self.section("notes") or "").splitlines()
        marked = [i for i, line in enumerate(lines) if annotation_audience(line)]
        if not 0 <= index < len(marked):
            raise CardError(f"no annotation {index} on card {self.uid}")
        at = marked[index]
        removed = lines[at]
        record = resolved_line(removed, reply)
        if record:
            lines[at] = record
        else:
            lines.pop(at)
        self.set_section("notes", "\n".join(lines).strip())
        return removed

    def resolved(self) -> list[str]:
        """Every settled annotation on this card, oldest first, as written."""
        body = self.section("notes") or ""
        return [line.strip() for line in body.splitlines() if is_resolved(line)]

    # -- hashing (DESIGN.md §3.5, §8) -------------------------------------
    def content_hash(self) -> str:
        """Hash of everything that is card content.

        Excludes `status`, `content_hash` itself and `## notes`, so approving a
        card or scribbling an annotation on it is not an edit -- but changing
        anything a reviewer looked at is.
        """
        exempt = UNHASHED_FRONTMATTER
        # Hash the content, not the file. Rendering it would make the digest
        # depend on FRONTMATTER_ORDER, so adding an optional field to that
        # tuple silently invalidated every approval in the deck -- the card
        # was untouched and `check` reported it as edited. Sorted keys and an
        # explicit separator make the digest independent of how the file
        # happens to be laid out.
        parts = [
            f"{key}={self.frontmatter[key]!r}"
            for key in sorted(self.frontmatter)
            if key not in exempt
        ]
        parts += [
            f"##{s.name}\n{s.canonical().body}"
            for s in sorted(self.sections, key=lambda s: s.name)
            if s.name not in UNHASHED_SECTIONS
        ]
        digest = hashlib.sha256(HASH_SEPARATOR.join(parts).encode('utf-8')).hexdigest()
        return digest[:16]

    def hash_matches(self) -> bool:
        """Whether this card still says what it was approved saying.

        One digest, not two. A second was accepted for a while so that
        widening the exemption set did not report a whole deck as edited on
        the strength of a code change; exempting `tags` retired it, because
        both earlier rules hashed tags and every approval had to be re-stamped
        anyway. The next widening does the same: migrate the deck rather than
        teach this to accept another number.
        """
        if not self.stored_hash:
            return False
        return self.stored_hash == self.content_hash()

    @property
    def demotion(self) -> str:
        """Why an approved card is not really approved: `edited`, `annotated`.

        Two ways an approval stops holding, and they are different situations
        worth telling apart in the view:

        * **edited** -- the content no longer matches the hash it was approved
          under. Somebody changed the mathematics after it was signed off.
        * **annotated** -- an open `@claude` or `@me` line. Nothing about the
          card changed; a question was raised about it. `sync` has always
          refused an annotated card whatever its status, so it was never going
          to Anki -- but it sat in the approved pile looking like it was, and
          `approved 108` counted work that could not move.

        Neither rewrites the file. `status: approved` stays, so resolving the
        note restores the approval with no re-review and no re-stamped hash --
        which is the whole reason `## notes` is outside `content_hash`.
        """
        if self.status != "approved":
            return ""
        if not self.hash_matches():
            return "edited"
        return "annotated" if self.annotations() else ""

    @property
    def effective_status(self) -> str:
        """`status`, except that an approval which no longer holds is a draft.

        DESIGN.md §8 promises that resolving an annotation "drops the card back
        to `draft` and re-enters review automatically". Nothing rewrites the
        file to make that true -- and it should not, silently -- so the rule
        lives here instead: a card that cannot go to Anki counts as a draft
        everywhere it matters, which is what puts it back in the review queue.
        """
        return "draft" if self.demotion else self.status

    def set_grade(self, key: str, value: Any) -> None:
        """Change one unhashed judgement, carrying any approval with it.

        `frequency`, `derivation`, `web` and `augmented` are outside
        `content_hash`, so a card stamped under today's rule survives this
        untouched. One stamped
        under the older rule does not -- its digest covers the very key being
        changed -- and it would come back as `edited`, which is a lie: nobody
        edited the mathematics, a grading moved.

        So the stamp is refreshed, but **only when the approval was holding to
        begin with**. A card whose content had already drifted from its hash
        stays drifted; re-stamping that one would launder a real edit through a
        grading click, which is precisely the thing invariant 5 forbids.

        An empty value removes the key, which is how a grading is taken off.
        `False` is a value and not an absence: `web: false` is a refusal that
        overrides a source-wide grant, and collapsing it into "unset" would
        make that impossible to say.
        """
        held = self.status == "approved" and self.hash_matches()
        if value is None or value == "":
            self.frontmatter.pop(key, None)
        else:
            self.frontmatter[key] = value
        if held:
            self.frontmatter["content_hash"] = self.content_hash()

    def approve(self) -> None:
        self.frontmatter["status"] = "approved"
        self.frontmatter["content_hash"] = self.content_hash()

    def reject(self) -> None:
        self.frontmatter["status"] = "rejected"
        self.frontmatter.pop("content_hash", None)

    def unapprove(self) -> None:
        self.frontmatter["status"] = "draft"
        self.frontmatter.pop("content_hash", None)

    # -- serialisation ----------------------------------------------------
    def canonical(self) -> Card:
        return replace(
            self,
            frontmatter=_sorted_frontmatter(self.frontmatter),
            sections=[s.canonical() for s in _sorted_sections(self.sections)],
            preamble=self.preamble.strip("\n"),
        )

    def render(self) -> str:
        card = self.canonical()
        out = ["---\n"]
        for key, value in card.frontmatter.items():
            out.append(f"{key}: {_dump_scalar(value)}\n")
        out.append("---\n")
        if card.preamble:
            out.append("\n" + card.preamble + "\n")
        for sec in card.sections:
            out.append(f"\n## {sec.name}\n")
            if sec.body:
                out.append(sec.body + "\n")
        return "".join(out)

    def save(self, path: Path | None = None, *, expect_mtime_ns: int | None = None) -> Path:
        """Write canonically. With `expect_mtime_ns`, refuse a stale write."""
        target = path or self.path
        if target is None:
            raise CardError("card has no path to save to")
        if expect_mtime_ns is not None and target.exists():
            actual = target.stat().st_mtime_ns
            if actual != expect_mtime_ns:
                raise StaleFileError(
                    f"{target.name} changed on disk since it was loaded; reload and retry"
                )
        write_atomic(target, self.render())
        self.path = target
        self.mtime_ns = target.stat().st_mtime_ns
        return target


# -- parsing --------------------------------------------------------------


def parse(text: str, path: Path | None = None) -> Card:
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise CardError("missing YAML frontmatter (a card starts with a `---` block)")
    try:
        loaded = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CardError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CardError("frontmatter must be a mapping")

    body = text[match.end() :]
    preamble_lines: list[str] = []
    sections: list[Section] = []
    current: Section | None = None
    for line in body.split("\n"):
        header = _SECTION_RE.match(line)
        if header:
            current = Section(header.group(1).lower(), "")
            sections.append(current)
            continue
        if current is None:
            preamble_lines.append(line)
        else:
            current.body += line + "\n"

    return Card(
        frontmatter={str(k): v for k, v in loaded.items()},
        sections=[s.canonical() for s in sections],
        preamble="\n".join(preamble_lines).strip("\n"),
        path=path,
    )


def load(path: Path) -> Card:
    stat = path.stat()
    try:
        card = parse(path.read_text(encoding="utf-8"), path=path)
    except CardError as exc:
        raise CardError(f"{path}: {exc}") from exc
    card.mtime_ns = stat.st_mtime_ns
    return card


def load_all(cards_dir: Path) -> list[Card]:
    """Every card in the deck directory, sorted by uid then path."""
    if not cards_dir.exists():
        return []
    cards = [load(p) for p in sorted(cards_dir.rglob("*.md"))]
    return sorted(cards, key=lambda c: (c.uid, str(c.path)))


def toml_string(value: str) -> str:
    """`value` as a TOML basic string, escaped.

    One spelling, because everything here that writes a `.toml` writes it
    line by line to keep the comments, and three hand-rolled quoters would
    disagree about the first sentence somebody pastes in with a quote in it.

    Refused rather than escaped for a newline: every value written this way
    is a caption or a name on one line, and a value that is secretly two
    lines is a mistake worth stopping rather than encoding.
    """
    if "\n" in value or "\r" in value:
        raise ValueError(f"{value!r} runs over more than one line")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def home_of(card: Card, cards_dir: Path) -> str:
    """Which project a card belongs to, for anything that groups cards.

    Its unit says, because that is the declared relationship. Failing that,
    the folder it is filed under: `cards/<project>/<uid>-<slug>.md` is the
    convention every writer follows, and for a card with no unit it is the
    only evidence there is.

    Not the same question as which Anki deck it lands in. `sync` routes by
    what the card declares (`project_name`), and one that declares nothing
    takes the repo default rather than being moved into a project's deck by
    a rule about where its file happens to sit. `check` warns about the gap
    (`unit-missing`), and writing `unit:` closes it in both directions.
    """
    if card.project_name:
        return card.project_name
    if card.path is not None and card.path.parent != cards_dir:
        return card.path.parent.name
    return ""


def find(cards_dir: Path, uid: str) -> Card | None:
    for card in load_all(cards_dir):
        if card.uid == uid:
            return card
    return None


# Windows refuses the rename while any other process holds the destination
# open, so this waits rather than failing. The budget is generous on purpose:
# waiting costs nothing, and the alternative is throwing away a write that has
# already been computed. One second was not enough under a loaded machine --
# twelve concurrent writers plus other work made the suite flake here.
REPLACE_ATTEMPTS = 100
REPLACE_POLL = 0.05


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` so a reader sees either the old file or the new.

    On Windows `os.replace` fails with PermissionError while *any* other
    process holds the destination open -- and the app re-reads the ledger on
    every request, so a reader can break a writer even when writers are
    serialised among themselves. Retry the rename rather than raise: the
    reader's handle is short-lived, and failing here would throw away work
    that has already been done.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_POLL)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# -- new cards ------------------------------------------------------------


def looks_numeric(uid: str) -> bool:
    """Would Anki read this uid as a number rather than as text?

    `uid` is the note type's first field, and Anki stores the sort field in a
    column that takes either. A six-hex uid shaped `4e6166` is a valid float
    literal -- 4 x 10^6166 -- which overflows a double, lands as NULL, and
    breaks `exportPackage` with a NOT NULL constraint on `notes.sfld`. Found
    by bisecting a 108-card deck down to one card.

    8.4% of the 6-hex space parses as a float; a handful of those overflow.
    Only the overflowing ones break an export, but a uid that sorts as a number
    is wrong in the browser too, so the test is the broader one: does it parse.
    The cheap half of the fix is never to mint another.
    """
    try:
        float(uid)
    except ValueError:
        return False
    return True


def mint_uid(seed: str, taken: set[str] | None = None) -> str:
    """Deterministic 6-hex uid from a seed, bumped on collision.

    Skips any uid Anki would read as a number; see `looks_numeric`.
    """
    taken = taken or set()
    for salt in range(1000):
        material = seed if salt == 0 else f"{seed}#{salt}"
        uid = hashlib.sha256(material.encode("utf-8")).hexdigest()[:6]
        if uid not in taken and not looks_numeric(uid):
            return uid
    raise CardError(f"could not mint a free uid for {seed!r}")


#: Names that are mostly punctuation, and that the general rule below would
#: quietly turn into a different word. `c++` slugs to `c`, which is another
#: language, and `c#` slugs to `c` as well, so a project for each would want
#: the same folder. Whole tokens only: `a+b` keeps its plus.
SPELLINGS = {"c++": "cpp", "c#": "c-sharp", "f#": "f-sharp"}


def slugify(text: str, limit: int = 40) -> str:
    lowered = text.lower()
    for word, spelled in SPELLINGS.items():
        lowered = re.sub(
            rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", spelled, lowered
        )
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug[:limit].strip("-") or "card"


def stub(
    *,
    uid: str,
    front: str,
    back: str,
    source: str,
    unit: str,
    card_type: str = "identity",
    tags: list[str] | None = None,
    gist: str = "",
) -> Card:
    """A minimal valid card: `check` passes on it, it is just not good yet.

    `gist` is written here rather than patched in afterwards because whoever
    calls this has just decided what the card is, and that is the cheapest
    moment to say so. Omitted entirely when empty, so a stub carries no
    `gist: ''` for a later pass to mistake for a considered blank.
    """
    return Card(
        frontmatter={
            "uid": uid,
            "type": card_type,
            "status": "draft",
            "source": source,
            "unit": unit,
            **({"gist": gist.strip()} if gist.strip() else {}),
            "tags": tags or [],
            "verify": False,
        },
        sections=[Section("front", front.strip()), Section("back", back.strip())],
    )


# -- canonicalisation helpers ---------------------------------------------


def _sorted_frontmatter(fm: dict[str, Any]) -> dict[str, Any]:
    known = [k for k in FRONTMATTER_ORDER if k in fm]
    rest = [k for k in fm if k not in FRONTMATTER_ORDER]
    return {k: fm[k] for k in [*known, *rest]}


def _sorted_sections(sections: list[Section]) -> list[Section]:
    def key(item: tuple[int, Section]) -> tuple[int, int]:
        index, sec = item
        try:
            return (SECTION_ORDER.index(sec.name), index)
        except ValueError:
            return (len(SECTION_ORDER), index)

    return [sec for _, sec in sorted(enumerate(sections), key=key)]


_PLAIN_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _.\-/()+^=]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list | tuple):
        return "[" + ", ".join(_dump_scalar(v) for v in value) + "]"
    if isinstance(value, str):
        return _dump_str(value)
    # Anything exotic: let PyYAML decide, on one line.
    return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True).strip()


def _dump_str(value: str) -> str:
    if (
        value
        and value.lower() not in _RESERVED
        and _PLAIN_RE.match(value)
        and not _looks_numeric(value)
        and value == value.strip()
    ):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
