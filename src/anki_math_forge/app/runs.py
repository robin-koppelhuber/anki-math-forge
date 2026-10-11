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
WHERE = ("shelf", "units", "review", "project", "topic", "work", "inbox")

#: The setup stage's smaller panes, each with a short list of its own. They
#: were dict literals in `setup.html`, which is the drift this module was
#: written to end: four command lines nobody could run from the page, in a
#: file whose comments said every list came from here.
#:
#: `references` is the shelf on the project pane, `bookless` a source with
#: no address, `add-source` and `new-topic` the two panes that create one.
PANES = ("references", "bookless", "add-source", "new-topic")

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
    #: Notes dumped at the project and not yet sorted.
    inbox: int = 0

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

    `label` is the headline: the command, in one or two words, the way you
    would say it (`anki push test`, `/transcribe`). `detail` is what tells
    two rows with one headline apart, or how much is waiting (`this
    project`, `3 queued`). `why` says what the pass *is*, in a sentence,
    because these are commands you run rarely enough to have forgotten
    between times and this panel is the only place they are described
    anywhere near where you press them. A note has no headline: its label
    is the sentence.

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
    detail: Text = ""
    why: str = ""
    kind: str = "shell"
    scope: str = "project"
    reads: bool = False
    when: Callable[[Ambient], bool] = _always

    def render(self, at: Ambient) -> dict[str, Any]:
        line = _say(self.run, at)
        row: dict[str, Any] = {
            "label": _say(self.label, at),
            "run": line,
            "kind": self.kind,
        }
        detail = _say(self.detail, at)
        if detail:
            row["detail"] = detail
        if self.why:
            row["why"] = self.why
        if self.reads:
            row["reads"] = True
        # What the command itself says it does, asked of the parser rather
        # than restated here. `reads` above is this repeated by hand, and
        # it stays only because it is also what splits the list in two;
        # the two cannot disagree, because a test compares them.
        #
        # Not on a line carrying a placeholder. `forge zotero import
        # <citekey>` is a shape to fill in, and running it would take the
        # angle brackets for an item key and report that no such item
        # exists. Those stay copied, which is what they were always for.
        if self.kind == "shell" and "<" not in line:
            row["effect"] = effect_of(line)
        # The action this line is, with its fields filled in, so the row can
        # open in the runs window to be changed before it runs. A line with
        # a slot to fill (`<citekey>`) opens there with that field empty,
        # which is how it becomes runnable at all.
        if self.kind == "shell":
            found = action_of(line)
            if found is not None:
                row["action"], row["values"] = found
        return row


def action_of(line: str) -> tuple[str, dict[str, Any]] | None:
    """`(action key, field values)` for an offered command line, or `None`."""
    import shlex

    from . import actions

    words = shlex.split(line.replace("uv run ", "", 1))
    if not words or words[0] != "forge":
        return None
    found = actions.match(words[1:])
    return (found[0].key, found[1]) if found else None


def effect_of(line: str) -> str:
    """What a command line changes: `reads`, `repo` or `anki`.

    Off the parser, through the same resolution the runner uses, so an
    offer cannot describe itself as safer than the command it holds. A
    line the parser does not recognise answers `reads`: it will be
    refused on the way in anyway, and calling an unknown line a writer
    would put a confirmation on a button that cannot do anything.
    """
    from . import command_effects, jobs

    try:
        return jobs.argv_for(line, command_effects())[1]
    except jobs.Refused:
        return "reads"


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


def units_in(at: Ambient) -> int:
    """How many units there are to look at: the work's own where a work is
    selected, the project's by state everywhere else."""
    return at.count("units") or sum(
        at.count(state) for state in ("new", "queued", "carded", "skipped")
    )


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
        label="zotero import",
        detail="this item",
        run=lambda at: f"uv run forge zotero import {quoted(at.zotero_key)}{at.src}".rstrip(),
        why="re-reads the marks and imports them as units",
    ),
    # -- the ask you have selected -----------------------------------------
    Offer(
        where=("topic",),
        when=lambda at: bool(at.subject),
        kind="claude",
        scope="topic",
        label="/propose",
        detail=lambda at: (
            f"{at.open_entries} open entries" if at.open_entries else "more for this ask"
        ),
        run=lambda at: f"/propose{at.src} {quoted(at.subject)}",
        why="a unit per outline entry that has none",
    ),
    Offer(
        where=("topic",),
        when=lambda at: bool(at.subject),
        kind="claude",
        scope="topic",
        label="/sources",
        detail="for this ask",
        run=lambda at: f"/sources{at.src} {quoted(at.subject)}",
        why="places to check this subject's cards against",
    ),
    # -- the project -------------------------------------------------------
    Offer(
        where=("inbox",),
        when=lambda at: at.inbox > 0,
        kind="claude",
        label="/sort-notes",
        detail=lambda at: f"{at.inbox} unsorted",
        run=lambda at: f"/sort-notes{at.src}",
        why="places each dump the way it asks",
    ),
    Offer(
        where=("units", "project"),
        when=lambda at: not at.has_document,
        kind="claude",
        label="/propose",
        detail="a subject",
        run=lambda at: f"/propose{at.src} '<what you want cards for>'",
        why="units for a subject with no document",
    ),
    Offer(
        where=("project",),
        # A project of several works can hold both kinds, and then both
        # doors are open: this one re-reads the items, and `extract` below
        # segments the files.
        when=lambda at: at.origin in ("zotero", "mixed"),
        label="zotero import",
        detail="this project",
        run=lambda at: f"uv run forge zotero import{at.src}",
        why="re-reads this project's Zotero items",
    ),
    Offer(
        where=("work", "project"),
        when=lambda at: extracted(at) and at.origin != "zotero",
        label="units extract",
        detail="this project",
        run=lambda at: f"uv run forge units extract {quoted(at.project)}",
        why="segments the project's files; Zotero items are left alone",
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
        label="/transcribe",
        detail=lambda at: f"{at.count('untranscribed')} untranscribed",
        run=lambda at: f"/transcribe{at.src}{at.scope}",
        why="the maths as text beside the crop; a hint",
    ),
    Offer(
        where=("units", "work"),
        when=lambda at: readable(at) and not at.from_marks and bool(at.count("new")),
        kind="claude",
        label="/classify",
        detail=lambda at: f"{at.count('new')} new",
        run=lambda at: f"/classify{at.src}{at.scope}",
        why="proposes skips; applies nothing",
    ),
    Offer(
        where=("units",),
        when=lambda at: bool(at.count("ungisted")),
        kind="claude",
        label="/gist",
        detail=lambda at: f"{at.count('ungisted')} without a gist",
        run=lambda at: f"/gist{at.src}{at.scope}",
        why="one line per unit saying what a card would be about",
    ),
    Offer(
        where=("units", "topic"),
        when=lambda at: bool(at.count("queued")),
        kind="claude",
        label="/extract-cards",
        detail=lambda at: f"{at.count('queued')} queued",
        run=lambda at: f"/extract-cards{at.src}{at.sec}",
        why="a draft per queued unit; approving stays yours",
    ),
    Offer(
        where=("units", "topic"),
        when=lambda at: bool(at.count("queued")),
        kind="claude",
        label="/extract-cards",
        detail=lambda at: f"{at.count('queued')} queued, then augmented",
        run=lambda at: f"/extract-cards{at.src}{at.sec} --augment",
        why="drafts, then conditions, proof and gradings in one run",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("unaugmented")),
        kind="claude",
        label="/augment",
        detail=lambda at: f"{at.count('unaugmented')} not augmented",
        run=lambda at: f"/augment{at.src}",
        why="conditions, proof and gradings; run before approving",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("annotated_claude_card")),
        kind="claude",
        label="/triage",
        detail=lambda at: f"{at.count('annotated_claude_card')} open @claude",
        run=lambda at: f"/triage claude{at.src}",
        why="works each @claude note and removes the line",
    ),
    # -- what to check afterwards ------------------------------------------
    Offer(
        where=("units",),
        reads=True,
        label="units",
        detail="this list, as JSON",
        run=lambda at: (
            f"uv run forge units{at.src}"
            f" --state {at.state or 'all'}{at.sec} --json"
        ),
        why="this list as JSON, for a script or an agent",
    ),
    # On the project it audits, once there is a unit to audit. Not on a
    # work's panel, since it takes the whole project; and not on the triage
    # rail, where every command carries the section on screen and this one
    # cannot. Over the ledger, so it has an answer for a work that has
    # stopped producing units as much as for one that has not.
    Offer(
        where=("project",),
        when=lambda at: at.has_document and units_in(at) > 0,
        reads=True,
        label="audit",
        run=lambda at: f"uv run forge audit{at.src}",
        why="dropped content, gaps in 1..N, overlapping crops",
    ),
    Offer(
        where=("review",),
        when=lambda at: bool(at.count("approved")),
        reads=True,
        label="verify",
        run=lambda at: f"uv run forge verify{at.src}",
        why="runs the ## verify snippets; never reaches Anki",
    ),
    Offer(
        where=("review", "project"),
        reads=True,
        label="anki push test",
        detail="this project",
        run=lambda at: f"uv run forge anki{at.src}",
        why="approved cards only; writes nothing; names skips",
    ),
    # -- the repo ----------------------------------------------------------
    Offer(
        where=("shelf",),
        scope="repo",
        reads=True,
        label="sources",
        detail="all projects",
        run="uv run forge sources",
        why="every source in the repo, and which project reads it",
    ),
    Offer(
        where=("shelf",),
        scope="repo",
        reads=True,
        label="zotero",
        run="uv run forge zotero",
        why="what Zotero has, and what is already here",
    ),
    Offer(
        where=("shelf", "project"),
        scope="repo",
        reads=True,
        label="check",
        detail="every card",
        run="uv run forge check",
        why="always safe; blocks sync; names the parser",
    ),
    Offer(
        where=("shelf", "review", "project"),
        scope="repo",
        reads=True,
        label="anki push test",
        detail="all projects",
        run="uv run forge anki",
        why="the same dry run over every project",
    ),
    Offer(
        where=("shelf", "work", "project"),
        when=lambda at: extracted(at) and at.origin in ("", "zotero", "mixed"),
        scope="repo",
        label="zotero import",
        detail="tag anki",
        run="uv run forge zotero import --tag anki",
        why="one project per item; re-reads known ones",
    ),
    Offer(
        where=("shelf",),
        scope="repo",
        label="zotero import",
        detail="one item",
        run="uv run forge zotero import <citekey>",
        why="add --project to file it under an existing project",
    ),
    # The one flow *back*. Offered without a count, because nothing here can
    # know you left a comment in Anki last night, and until this runs that
    # comment is not a note on any card and no list in this app is showing
    # it. A row gated on a count would be a row you only see once it is too
    # late to be told.
    Offer(
        where=("shelf", "review"),
        scope="repo",
        label="anki pull",
        run="uv run forge anki pull",
        why="comments and flags from Anki become @claude notes; erased there",
    ),
    # -- the setup stage's smaller panes ----------------------------------
    Offer(
        where=("references",),
        kind="claude",
        label="/sources",
        run=lambda at: f"/sources{at.src}",
        why="proposes places to check this project's cards against",
    ),
    Offer(
        where=("bookless",),
        label="zotero import",
        detail="once it is marked up",
        run=lambda at: f"uv run forge zotero import <citekey>{at.src}",
        why="mark up in Zotero first, then run this",
    ),
    Offer(
        where=("add-source",),
        reads=True,
        label="zotero",
        detail="what is not imported yet",
        run="uv run forge zotero",
        why="what Zotero has; writes nothing",
    ),
    Offer(
        where=("add-source",),
        label="zotero import",
        detail="one item, here",
        run=lambda at: f"uv run forge zotero import <citekey>{at.src}",
        why="imports the marks under this project",
    ),
    Offer(
        where=("new-topic",),
        kind="claude",
        label="/propose",
        detail="outline it",
        run=lambda at: f'/propose{at.src} "<the subject>"',
        why="outlines the subject, a unit per entry",
    ),
)


def propose(where: str, at: Ambient) -> list[dict[str, Any]]:
    """What to run on this screen, given this much ambient state.

    Narrowest scope first, and stable within a scope: the order inside one
    is the order the offers are written in, which is the order you would do
    them in.
    """
    if where not in WHERE + PANES:  # pragma: no cover - a typo, not a state
        raise ValueError(f"no screen called {where!r}")
    ranked = [
        (SCOPES.index(offer.scope), n, offer)
        for n, offer in enumerate(OFFERS)
        if where in offer.where and offer.when(at)
    ]
    return [offer.render(at) for _, _, offer in sorted(ranked, key=lambda row: row[:2])]
