"""What to run next, as one object per command.

Every list of commands in this app comes from here. Nothing is launched:
you copy it and paste it where you can watch it, so nothing writes cards
with nobody looking. That bargain is why the *arguments* are the product. A
command that silently acts on a different population than the one you were
looking at is worse than no command, because you cannot see that it did.

**One object per command, not one per screen.** These used to be dict
literals written wherever they happened to be shown, and there were three
such places: the deck rail, the setup stage, the shelf. The same command was
written three times in three spellings, and the drift showed. `/transcribe`
was offered against a Zotero item on one screen and refused on another, and
the screen that offered it was wrong.

So a command is an `Offer`: what to run, what to say about it, and the one
condition that decides whether it applies. It reads **ambient state** and
nothing else (counts, what the selection has, which project is in
force), never which screen is asking. `where` says which screens may show it, so a
command that belongs on two of them is one object in two lists rather than
two objects free to disagree.

**Narrowest first.** You are looking at one work, so the command about that
work comes before the one about its project, and the repo-wide form comes
last. That is `scope`, and it is the only thing that reorders a list: within
a scope the order is the order they are written here, which is the order
you would do them in.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

#: The screens that ask. `units` and `review` are the two deck rails,
#: `project`, `topic` and `work` the three kinds of selection on the setup
#: stage, and `shelf` the project picker, which is the one screen that is
#: not about a project at all.
WHERE = ("shelf", "units", "review", "project", "topic", "work")

#: How wide a command reaches, narrowest first. A note is not a command and
#: frames the list rather than sitting in it, so it goes above everything.
SCOPES = ("note", "work", "topic", "project", "repo")


def flag(name: str, value: str) -> str:
    """` --name "value"`, or nothing at all.

    Double quotes throughout, which both `sh` and PowerShell read the same
    way. Single quotes, which the CLI's own examples use, are a literal in
    PowerShell and would pass the quote marks along.

    A value containing a double quote gets **no flag**, because there is no
    spelling that quotes it correctly for both shells: `""` escapes it in
    PowerShell and concatenates two strings in `sh`. Dropping the scope makes
    a command that does too much, which you can see; mis-quoting makes one
    that does something else, which you cannot.
    """
    return "" if not value or '"' in value else f' {name} "{value}"'


def quoted(value: str) -> str:
    """A shell argument in double quotes, or nothing.

    Same rule as `flag`, and for the same reason: `sh` and PowerShell read
    double quotes the same way and single quotes differently, and a value
    with a double quote in it has no spelling that works in both.
    """
    return "" if not value or '"' in value else f'"{value}"'


@dataclass(frozen=True)
class Ambient:
    """Everything a command may be keyed on, and nothing about the screen.

    One record, filled by whoever is rendering. A field left at its default
    means "not asked here": a deck rail knows nothing about which work you
    have selected, so `authoritative` defaults to true and the offers that
    turn on it simply do not name the deck rail in their `where`.
    """

    project: str = ""
    section: str = ""
    #: Which unit state the deck is filtered to, for the command that
    #: re-asks the same question as JSON.
    state: str = ""
    #: Unit and card states by name, over whatever the caller is counting:
    #: the project for a deck rail, the selected work for its panel. Also
    #: carries the derived ones, `ungisted`, `unaugmented` and
    #: `annotated_claude_card`, which are why this is a flat map rather
    #: than two typed fields.
    counts: Mapping[str, int] = field(default_factory=dict)
    #: The project reads a work at all. One that does not is proposed into
    #: rather than segmented, so every pass that reads a crop has nothing to
    #: read and the pass that writes units has to be offered somewhere.
    has_document: bool = True
    #: The units came from somebody marking the document up rather than from
    #: segmenting it.
    from_marks: bool = False
    #: Something is extracted from this work. A reference is read by whoever
    #: writes a card and by no pass here.
    authoritative: bool = True
    #: `zotero`, `pdf`, `tex`, `mixed`, or empty. What the material is, which
    #: decides which door units come in by.
    origin: str = ""
    zotero_key: str = ""
    #: The ask you have selected, and how much of its outline has no unit.
    subject: str = ""
    open_entries: int = 0

    @property
    def src(self) -> str:
        return flag("--project", self.project)

    @property
    def sec(self) -> str:
        return flag("--section", self.section)

    @property
    def scope(self) -> str:
        """The section you filtered to, or the whole work. A pass with
        neither would read the section that happened to be first."""
        return self.sec or " --all"

    def count(self, key: str) -> int:
        return int(self.counts.get(key, 0))


Text = str | Callable[[Ambient], str]


def _say(text: Text, at: Ambient) -> str:
    return text(at) if callable(text) else text


def _always(at: Ambient) -> bool:
    return True


@dataclass(frozen=True)
class Offer:
    """One command, and the only ambient facts it depends on.

    `label` says which pass and how much is waiting; `why` says what the
    pass *is*, in a sentence, because these are commands you run rarely
    enough to have forgotten between times and this panel is the only place
    they are described anywhere near where you press them.

    `kind` is `shell`, `claude` or `note`. A shell command is plain Python
    and does exactly what it says; a slash command puts a model in the loop,
    which costs tokens, takes minutes and produces something to review. The
    two are pasted into different windows, which is why it is on the button
    and not in a tooltip. A note is neither: it says why a pass is absent.

    `reads` marks the half that only shows you something. It is what splits
    an info command from an action command in the list, and the difference
    is the whole reason these are copied rather than launched.
    """

    where: tuple[str, ...]
    label: Text
    run: Text = ""
    why: str = ""
    kind: str = "shell"
    scope: str = "project"
    reads: bool = False
    when: Callable[[Ambient], bool] = _always

    def render(self, at: Ambient) -> dict[str, Any]:
        row: dict[str, Any] = {
            "label": _say(self.label, at),
            "run": _say(self.run, at),
            "kind": self.kind,
        }
        if self.why:
            row["why"] = self.why
        if self.reads:
            row["reads"] = True
        return row


def extracted(at: Ambient) -> bool:
    """May a pass make units here?

    A reference may not: nothing is segmented out of it, so the import has
    nothing to import and the segmenter has no page to cut.

    The passes that *read* units ask `readable` instead. The two parted
    when the extract switch stopped deleting the units it had made: a
    work can now hold three untranscribed crops and be switched off, and
    keying `/transcribe` on this one left the panel saying there was
    nothing to run over them.
    """
    return at.authoritative and at.has_document


def readable(at: Ambient) -> bool:
    """Is there anything here for a pass that reads units?

    Either more are still coming, or some are already here. A work you
    switched off keeps the ones it made: their crops render, they still
    want transcribing and triaging, and the switch decides only whether
    any more arrive.
    """
    return at.has_document and (at.authoritative or bool(at.count("units")))


#: Every command this app proposes, written once.
#:
#: Read it as a table: which screens may show it, what decides whether it
#: applies, and how wide it reaches. Adding a screen to a `where` is how a
#: command appears in a second place without being written a second time.
OFFERS: tuple[Offer, ...] = (
    # -- notes: why a pass is absent ---------------------------------------
    Offer(
        where=("work",),
        when=lambda at: not at.authoritative and not at.count("units"),
        kind="note",
        scope="note",
        label="nothing to run: a reference is read by whoever writes a card,"
        " not by a pass here",
    ),
    # A work you switched off that already produced units is the other
    # case, and it is not empty: the crop passes below are offered on it,
    # and what is absent is only the two that would add more.
    Offer(
        where=("work",),
        when=lambda at: not at.authoritative and bool(at.count("units")),
        kind="note",
        scope="note",
        label=lambda at: (
            f"nothing new is extracted from this work. Its {at.count('units')}"
            " units stay, and the passes that read them still apply"
        ),
    ),
    # No note about the transcription pass on a marked-up work. There were
    # two, saying it does not apply and how to transcribe one unit anyway,
    # and they were written when an absent pass left the panel empty. The
    # panel is not empty any more: a marked-up work is offered the import,
    # the index check and the repo-wide passes, so the notes were two lines
    # of standing text explaining the absence of something nobody was
    # looking for. The rule they described still holds and lives in
    # `extracted` and in the `from_marks` conditions below.
    # -- the work you have selected ----------------------------------------
    Offer(
        where=("work",),
        when=lambda at: extracted(at) and at.origin == "zotero" and bool(at.zotero_key),
        scope="work",
        label="re-read the marks on this work",
        run=lambda at: f"uv run forge zotero {quoted(at.zotero_key)}{at.src}".rstrip(),
        why="an item you marked up is imported rather than segmented: this"
        " re-reads the annotations and turns the ones your scheme names into"
        " units. Re-running is safe, and a unit already in the ledger keeps"
        " its id and its state.",
    ),
    # -- the ask you have selected -----------------------------------------
    Offer(
        where=("topic",),
        when=lambda at: bool(at.subject),
        kind="claude",
        scope="topic",
        label=lambda at: (
            f"write units for {at.open_entries} open entries"
            if at.open_entries
            else "propose more for this ask"
        ),
        run=lambda at: f"/propose{at.src} {quoted(at.subject)}",
        why="reads the ask and its outline, and writes a unit per entry that"
        " has none. Subjects, never drafts: triage still decides.",
    ),
    Offer(
        where=("topic",),
        when=lambda at: bool(at.subject),
        kind="claude",
        scope="topic",
        label="propose references for it",
        run=lambda at: f"/sources{at.src} {quoted(at.subject)}",
        why="places a card on this subject can be checked against. Proposed,"
        " never accepted: each line waits for you on the project's panel.",
    ),
    # -- the project -------------------------------------------------------
    Offer(
        where=("units", "project"),
        when=lambda at: not at.has_document,
        kind="claude",
        label="propose units for a subject",
        run=lambda at: f"/propose{at.src} '<what you want cards for>'",
        why="there is no document to segment here, so a pass writes the units"
        " instead: a subject, a line on what a card from it would be about,"
        " and the page it read. Subjects, never drafts. Record the ask first"
        " and the pass has an outline to work down.",
    ),
    Offer(
        where=("project",),
        # A project of several works can hold both kinds, and then both
        # doors are open: this one re-reads the items, and `extract` below
        # segments the files.
        when=lambda at: at.origin in ("zotero", "mixed"),
        label="re-read this project's items",
        run=lambda at: f"uv run forge zotero{at.src}",
        why="its works came from Zotero, which imports rather than segments."
        " With no item named, --project re-reads the ones this project"
        " already declares. Run it with Zotero open.",
    ),
    Offer(
        where=("work", "project"),
        when=lambda at: extracted(at) and at.origin != "zotero",
        label="segment this project into units",
        run=lambda at: f"uv run forge extract {quoted(at.project)}",
        why="geometry only, and it never reads the maths. It takes a project"
        " rather than one work: every document the project declares as files"
        " is segmented, and anything that came from Zotero is left alone."
        " Re-running is safe, and a unit already in the ledger keeps its id"
        " and its state.",
    ),
    # Gated on what the pass would actually work on, not on the triage
    # state: a deck of sixteen new units that have all been read offered
    # this anyway, and running it reported nothing to do.
    Offer(
        where=("units", "work"),
        when=lambda at: (
            readable(at) and not at.from_marks and bool(at.count("untranscribed"))
        ),
        kind="claude",
        label=lambda at: f"read the crops — {at.count('untranscribed')} still untranscribed",
        run=lambda at: f"/transcribe{at.src}{at.scope}",
        why="so triage shows the maths written out instead of a picture to"
        " squint at. A hint only: the crop stays the authority"
        " (invariant 4).",
    ),
    Offer(
        where=("units", "work"),
        when=lambda at: readable(at) and not at.from_marks and bool(at.count("new")),
        kind="claude",
        label="propose which of them to skip",
        run=lambda at: f"/classify{at.src}{at.scope}",
        why="fragments, headings, notation-table rows. It only proposes:"
        " every suggestion waits for you, and nothing may propose skipping"
        " a numbered equation.",
    ),
    Offer(
        where=("units",),
        when=lambda at: bool(at.count("ungisted")),
        kind="claude",
        label=lambda at: f"name {at.count('ungisted')} queued units in a line each",
        run=lambda at: f"/gist{at.src}{at.sec}",
        why="one line saying what a card from each would be about, so the"
        " list, the graph and every link to a card read as something rather"
        " than as a uid. Cheap, and it makes the stub-writing pass easier to"
        " check.",
    ),
    Offer(
        where=("units", "topic"),
        when=lambda at: bool(at.count("queued")),
        kind="claude",
        label=lambda at: f"write stubs for {at.count('queued')} queued",
        run=lambda at: f"/extract-cards{at.src}{at.sec}",
        why="reads the page each unit came from and your @claude brief, and"
        " writes a draft. Approving is still yours. The whole project's"
        " queue rather than one ask's: stub writing reads a unit and its"
        " page, and neither knows which ask it came from.",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("unaugmented")),
        kind="claude",
        label=lambda at: f"augment {at.count('unaugmented')} drafts nobody has been over",
        run=lambda at: f"/augment{at.src}",
        why="adds conditions, a proof where it earns its place, the gradings."
        " Run it before approving, not after: augmenting an approved card"
        " sends it back to draft.",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("annotated_claude_card")),
        kind="claude",
        label=lambda at: f"{at.count('annotated_claude_card')} open requests",
        run=lambda at: f"/triage claude{at.src}",
        why="works the @claude notes and deletes each line it has acted on."
        " Every one of them is holding a card out of sync until it goes.",
    ),
    # -- what to check afterwards ------------------------------------------
    Offer(
        where=("units",),
        reads=True,
        label="this list, as JSON",
        run=lambda at: (
            f"uv run forge units{at.src}"
            f" --state {at.state or 'all'}{at.sec} --json"
        ),
        why="the same units this filter is showing, for a script or a"
        " subagent. Read from this rather than from the printed output.",
    ),
    Offer(
        where=("work", "project"),
        # Over the ledger, so it has an answer for a work that has stopped
        # producing units as much as for one that has not.
        when=readable,
        reads=True,
        label="is the index trustworthy",
        run=lambda at: f"uv run forge audit{at.src}",
        why="1..N with no gaps. It answers whether anything was dropped,"
        " which no amount of reading the list can.",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("approved")),
        reads=True,
        label="check the maths numerically",
        run=lambda at: f"uv run forge verify{at.src}",
        why="runs the `## verify` snippets. Opt-in, and it caught three"
        " errors in the source. Never reaches Anki.",
    ),
    Offer(
        where=("review", "project"),
        reads=True,
        label="what would reach Anki, from this project",
        run=lambda at: f"uv run forge sync{at.src} --dry-run",
        why="a rehearsal: approved cards only, nothing written, and it names"
        " every card it would skip and why. The lint behind it is repo-wide"
        " either way, because a duplicate uid is.",
    ),
    # -- the repo ----------------------------------------------------------
    Offer(
        where=("shelf",),
        scope="repo",
        reads=True,
        label="every work this repo reads",
        run="uv run forge sources",
        why="across every project, with which one reads it. The answer to"
        ' "have I got this already" without opening five TOMLs.',
    ),
    Offer(
        where=("shelf",),
        scope="repo",
        reads=True,
        label="what is on the Zotero shelf",
        run="uv run forge zotero --list",
        why="and which of them are already here. Reads Zotero and writes"
        " nothing.",
    ),
    Offer(
        where=("shelf", "project"),
        scope="repo",
        reads=True,
        label="lint every card in the repo",
        run="uv run forge check",
        why="always safe, and it is what blocks sync. It says which LaTeX"
        " parser ran.",
    ),
    Offer(
        where=("shelf", "review", "project"),
        scope="repo",
        reads=True,
        label="what would reach Anki, from everything",
        run="uv run forge sync --dry-run",
        why="the same rehearsal over every project in the repo: approved"
        " cards only, nothing written, and it names every card it would"
        " skip.",
    ),
    Offer(
        where=("shelf", "work", "project"),
        when=lambda at: extracted(at) and at.origin in ("", "zotero", "mixed"),
        scope="repo",
        label="import every Zotero item you tagged",
        run="uv run forge zotero --tag anki",
        why="each one into a project of its own where it is new, and a"
        " re-read where it is not: a unit already in the ledger keeps its id"
        " and its state. Run it with Zotero open.",
    ),
    Offer(
        where=("shelf",),
        scope="repo",
        label="import one item",
        run="uv run forge zotero <citekey>",
        why="add --project to file it under a project that already exists,"
        " rather than making one named after the cite key.",
    ),
    # The one flow *back*. Offered without a count, because nothing here can
    # know you left a comment in Anki last night, and until this runs that
    # comment is not a note on any card and no list in this app is showing
    # it. A row gated on a count would be a row you only see once it is too
    # late to be told.
    Offer(
        where=("shelf", "review"),
        scope="repo",
        label="pull what you wrote in Anki",
        run="uv run forge feedback",
        why="a comment or a flag you left while reviewing becomes an @claude"
        " note on the card, and is erased in Anki as it is taken: after this"
        " the line here is the only copy. Repo-wide, like the sync it"
        " mirrors.",
    ),
)


def propose(where: str, at: Ambient) -> list[dict[str, Any]]:
    """What to run on this screen, given this much ambient state.

    Narrowest scope first, and stable within a scope: the order inside one
    is the order the offers are written in, which is the order you would do
    them in.
    """
    if where not in WHERE:  # pragma: no cover - a typo, not a state
        raise ValueError(f"no screen called {where!r}")
    ranked = [
        (SCOPES.index(offer.scope), n, offer)
        for n, offer in enumerate(OFFERS)
        if where in offer.where and offer.when(at)
    ]
    return [offer.render(at) for _, _, offer in sorted(ranked, key=lambda row: row[:2])]
