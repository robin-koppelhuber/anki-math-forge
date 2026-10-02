"""`forge` -- the command line (DESIGN.md §2).

Seven verbs: extract, serve, units, check, todo, sync, verify -- plus `new`,
a scaffold for the stub-writing step so a generated card cannot be malformed
in a way `check` would only catch later.

Everything that prints for a human also prints for a machine with `--json`;
that is what Claude Code reads.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from . import audit as audit_mod
from . import changes as changes_mod
from . import check as check_mod
from . import classify as classify_mod
from . import extract as extract_mod
from . import latex, model, todo, verify
from . import ledger as ledger_mod
from . import projects as projects_mod
from . import topics as topics_mod
from .anki import AnkiConnect, AnkiError
from .config import CHAPTER, PROJECT_TOML, Config, ConfigError, context_size, load

OK, FAILED, MISUSE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    # An old spelling still runs, and says so once. On stderr, so it cannot
    # corrupt a `--json` read, and before the work rather than after it: the
    # line is about what you typed, and a reader who has already seen the
    # output has stopped looking.
    renamed = getattr(args, "renamed", "")
    if renamed:
        print(f"note: `forge {args.verb}` is now `forge {renamed}`", file=sys.stderr)
    try:
        config = load(Path(args.root) if args.root else None)
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return MISUSE
    try:
        return int(args.run(args, config))
    except (ConfigError, AnkiError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return FAILED
    except BrokenPipeError:  # pragma: no cover - `forge source-text | head`
        # Downstream closed the pipe. Silence Python's own complaint about it.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return OK
    except KeyboardInterrupt:  # pragma: no cover
        return FAILED


def _force_utf8() -> None:
    """Print section signs and math symbols rather than mojibake.

    Windows consoles still default to a legacy code page, which turns a `§` in
    a citation into an encoding error mid-report.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def _window(value: str) -> int | str:
    """`--pages` / `--context-pages`: a number of pages, or `chapter`.

    The same vocabulary the TOML files take, so what you widen one call with is
    what you write onto the unit afterwards.
    """
    try:
        return context_size(value, "--pages")
    except ConfigError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


#: What a subcommand does to your files, declared rather than described.
#:
#:   reads  nothing you would miss is recorded. One word.
#:   repo   writes files in this repo, which git can give back. Two words.
#:   anki   writes where git cannot reach: your collection, or a file you
#:          named. Two words, and the first of them is `anki`.
#:
#: `forge --help` groups by this, `app/runs.py` derives `Offer.reads` from
#: it rather than restating it, and `test_verbs.py` refuses a `repo` or
#: `anki` parser that can be reached in one word. A rule nothing checks
#: closes again in three commits.
READS, REPO, ANKI = "reads", "repo", "anki"

#: `serve` is the exception the rule is allowed: it records nothing itself,
#: and what it opens is an app that writes plenty. `crops` is not an
#: exception, it is a read: the PNGs it writes are regenerable bytes under
#: a scratch directory, not recorded state.
ONE_WORD_WRITERS = ("serve",)


def _fill_extract(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", nargs="?", default=None)
    p.add_argument("--pages", default=None, help="page range, e.g. 10-40 (pdf sources)")
    p.add_argument("--json", action="store_true")


def _fill_zotero_import(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "item",
        nargs="?",
        default=None,
        help="a cite key or a Zotero item key; omit to take everything tagged",
    )
    p.add_argument("--tag", default=None, help="import every item carrying this Zotero tag")
    p.add_argument(
        "--project",
        default=None,
        help=(
            "which project to file the units under (default: the cite key). "
            "On its own, with no item and no --tag, it re-reads the Zotero "
            "items that project already declares: the narrow form of a "
            "re-import, for when you have marked up more of a book you have "
            "already imported once"
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true", help="say what would be imported and write nothing"
    )
    p.add_argument("--json", action="store_true")


def _fill_sources_remove(p: argparse.ArgumentParser) -> None:
    p.add_argument("remove", metavar="KEY", help="the work to take out")
    p.add_argument("--project", default=None, help="the project to take it out of")
    p.add_argument(
        "--force", action="store_true", help="remove it even though cards stand on it"
    )
    p.add_argument("--dry-run", action="store_true", help="say what would go")
    p.add_argument("--json", action="store_true")


def _fill_export(p: argparse.ArgumentParser) -> None:
    p.add_argument("project", nargs="?", default=None, help="whose deck to export")
    p.add_argument("--deck", default=None, help="a deck name, instead of a source")
    p.add_argument("--out", default=None, metavar="PATH", help="where to write it")
    p.add_argument(
        "--scheduling",
        action="store_true",
        help=(
            "include your review history. Off by default: a deck you hand to "
            "somebody else should arrive unstudied, and your intervals say "
            "more about you than about the cards"
        ),
    )


def _fill_project_new(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="the folder under projects/, and the id units carry")
    p.add_argument("--title", default="", help="what it is called (default: the name)")
    p.add_argument("--deck", default="", help="which Anki deck its cards land in")
    p.add_argument(
        "--citation",
        default="",
        help="what a card's `source` line says when nothing more specific does",
    )


def _fill_project_delete(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="the project to remove")
    p.add_argument("--force", action="store_true", help="delete it even though it holds cards")
    p.add_argument("--dry-run", action="store_true", help="say what would go and take nothing")


def _fill_topic_add(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="the subject, in your own words")
    p.add_argument("--project", required=True)
    p.add_argument(
        "--ask",
        default="",
        help=(
            "what you want from it: 'choosing between them and invalidation, "
            "not the full API'. The unit says what a card is about; only this "
            "says what you wanted from the subject"
        ),
    )


def _fill_cards_new(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--unit",
        action="append",
        default=None,
        metavar="UNIT",
        help="unit id; repeat to build one card from several units, which is "
        "what a multi-line display cut into pieces needs. Each is marked carded.",
    )
    p.add_argument("--front", required=True)
    p.add_argument("--back", required=True)
    p.add_argument("--source", default=None, help="citation text (defaults to the unit's)")
    p.add_argument("--type", default="identity")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument(
        "--gist",
        default="",
        help="a few words naming the card, for a list or a graph node where the "
        "LaTeX front is unreadable. Never reaches Anki, and unhashed, so a later "
        "pass may improve the wording without un-approving anything.",
    )
    p.add_argument("--json", action="store_true")


def _fill_push(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--project",
        default=None,
        help=(
            "push only this project's approved cards. The lint stays "
            "repo-wide, because two cards sharing a uid are a collision "
            "whichever projects they are in; nothing is deleted either way, "
            "so the rest are simply left where they are"
        ),
    )
    p.add_argument(
        "--templates",
        action="store_true",
        help=(
            "also push the card layout and styling from notetype.py. Without "
            "it a layout change is reported and left alone, since the template "
            "is yours to edit in Anki too"
        ),
    )
    p.add_argument(
        "--reposition",
        action="store_true",
        help=(
            "also put cards already in Anki into study order: frequency "
            "core-to-rare, then derivation definitional-to-long. Only cards "
            "you have not started are moved"
        ),
    )
    p.add_argument(
        "--move-decks",
        action="store_true",
        help=(
            "also file cards that predate a `deck` change under the name the "
            "config now gives them. Anki settles a deck when a note is added, "
            "so without this a changed setting only moves the next card. Off "
            "by default: everything else here adds to your collection, and "
            "this moves cards you may have filed by hand"
        ),
    )
    p.add_argument("--json", action="store_true")


def _fill_pull(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true", help="say what would come back")
    p.add_argument("--json", action="store_true")


def _fill_classify(p: argparse.ArgumentParser) -> None:
    p.add_argument("--project", default=None)
    p.add_argument(
        "--dry-run", action="store_true", help="report the proposals without recording them"
    )
    p.add_argument("--json", action="store_true")


def _fill_units_add(p: argparse.ArgumentParser) -> None:
    p.add_argument("add", metavar="SLUG", help="the id this unit takes, after the project")
    p.add_argument("--project", default=None)
    p.add_argument("--gist", default=None, metavar="TEXT", help="what a card from it is about")
    p.add_argument("--preview", default=None, metavar="TEXT", help="a short sample")
    p.add_argument(
        "--document",
        default="",
        metavar="KEY",
        help=(
            "which of --project's works it came out of, by source key or file "
            "name. Only needed where a project reads several: it is what "
            "settles the crop and context settings for the unit, and what "
            "links an ask to the works it drew on"
        ),
    )
    p.add_argument("--lang", default="", help="what --preview is written in, e.g. `cpp`")
    p.add_argument(
        "--ref",
        action="append",
        default=[],
        metavar="URL",
        help="something it stands on; repeat for several. Where to look, not what to say",
    )
    p.add_argument(
        "--tag", action="append", default=[], metavar="TAG", help="a label; repeat for several"
    )
    p.add_argument("--json", action="store_true")


def _fill_units_filters(p: argparse.ArgumentParser) -> None:
    """What narrows a listing. Every one of these is a read."""
    p.add_argument("--project", default=None)
    p.add_argument("--state", default="all", help=f"one of: {', '.join(ledger_mod.STATES)}, all")
    p.add_argument("--section", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--flagged", action="store_true", help="only units the audit is unsure about")
    p.add_argument("--suggested", action="store_true", help="only units with an open suggestion")
    p.add_argument(
        "--ungisted",
        action="store_true",
        help="only units with no gist yet -- what a `/gist` pass has left to do",
    )
    p.add_argument("--json", action="store_true")


def _fill_units_writes(p: argparse.ArgumentParser) -> None:
    """The old one-word writing flags, kept and hidden.

    `forge units --id X --set-state queued` still works and still writes,
    which is the one place the arity rule is not true of a *legacy*
    spelling. Hidden from `--help` and announced on use, like every other
    old spelling; the current way to say it is `forge units set X`.
    """
    hide = argparse.SUPPRESS
    p.add_argument("--id", default=None, help=hide)
    p.add_argument("--set-state", default=None, choices=ledger_mod.STATES, help=hide)
    p.add_argument("--reason", default="", help=hide)
    p.add_argument("--annotate", default=None, metavar="TEXT", help=hide)
    p.add_argument("--tex-auto", default=None, metavar="TEX", help=hide)
    p.add_argument("--context-pages", type=_window, default=None, metavar="N", help=hide)
    p.add_argument("--gist", default=None, metavar="TEXT", help=hide)
    p.add_argument("--web", choices=("yes", "no", "inherit"), default=None, help=hide)
    p.add_argument("--resolve-notes", action="store_true", help=hide)
    p.add_argument("--audience", choices=("claude", "me", "all"), default="claude", help=hide)
    p.add_argument("--add", default=None, metavar="SLUG", help=hide)
    p.add_argument("--preview", default=None, metavar="TEXT", help=hide)
    p.add_argument("--document", default="", metavar="KEY", help=hide)
    p.add_argument("--lang", default="", help=hide)
    p.add_argument("--ref", action="append", default=[], metavar="URL", help=hide)
    p.add_argument("--tag", action="append", default=[], metavar="TAG", help=hide)
    p.add_argument("--suggest", nargs=2, default=None, metavar=("STATE", "REASON"), help=hide)
    p.add_argument("--detail", default="", help=hide)
    p.add_argument("--by", default="claude", help=hide)
    p.add_argument("--accept", action="store_true", help=hide)
    p.add_argument("--dismiss", action="store_true", help=hide)


def _fill_units_set(p: argparse.ArgumentParser) -> None:
    """One unit, one or more of the things you can say about it."""
    p.add_argument("id", metavar="UNIT")
    p.add_argument("--project", default=None)
    p.add_argument(
        "--state", dest="set_state", default=None, choices=ledger_mod.STATES,
        help="the decision: queued, skipped, carded, or back to new",
    )
    p.add_argument("--reason", default="", help="why it was skipped")
    p.add_argument(
        "--gist",
        default=None,
        metavar="TEXT",
        help=(
            "one line saying what a card from it would be about, e.g. "
            "'Lemma 2' or 'why the bound needs independence'. A reading, not "
            "an instruction: nothing downstream consumes it, so it can be "
            "wrong without costing anything but a second look"
        ),
    )
    p.add_argument(
        "--tex",
        dest="tex_auto",
        default=None,
        metavar="TEX",
        help="a transcription, gated through KaTeX before it is stored",
    )
    p.add_argument(
        "--pages",
        dest="context_pages",
        type=_window,
        default=None,
        metavar="N",
        help=(
            "how many pages either side a card writer gets, or `chapter` for "
            "the chapter it is in. Set it during triage, when you can see the "
            "hypotheses are two pages back. A large number means the whole "
            "document; -1 goes back to inheriting the source's setting"
        ),
    )
    p.add_argument(
        "--web",
        choices=("yes", "no", "inherit"),
        default=None,
        help=(
            "whether whoever writes its card may look things up on the web. "
            "Off everywhere unless granted, because a card should say what "
            "this source says; `inherit` takes the override off again"
        ),
    )
    p.add_argument("--json", action="store_true")


def _fill_cards_filters(p: argparse.ArgumentParser) -> None:
    """What narrows the card listing."""
    p.add_argument("--project", default=None)
    p.add_argument("--status", default="all", help="draft, approved, rejected, or all")
    p.add_argument("--section", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--changes",
        action="store_true",
        help="what moved on each card since you last decided on it (kept on this machine only)",
    )
    p.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    """Every command, with its effect declared beside it.

    **One word reads, two words write** (docs/VERBS.md). The shape is the
    warning: you can try a half-remembered one-word command and nothing
    recorded will move. The names that changed keep their old spellings,
    registered without a `help=` so they stay out of the listing, and each
    prints the new form once on the way past.

    A flag block is written once and registered twice, by a `_fill_*`
    helper, so the legacy spelling cannot drift from the current one.
    """
    parser = argparse.ArgumentParser(
        prog="forge",
        description=__doc__.splitlines()[0],
        epilog=(
            "one word shows you something, two words change something.\n"
            "  reads   check  audit  verify  todo  units  cards  sources\n"
            "          zotero  context  source-text  crops  serve\n"
            "  writes  units extract|classify|add|set|note|suggest\n"
            "          zotero import   sources remove   project new|delete\n"
            "          topic add       cards new\n"
            "  anki    anki push  anki pull  anki export\n"
            "          (`forge anki` on its own says what a push would do)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=None, help="repo root (default: nearest forge.toml)")
    subs = parser.add_subparsers(dest="verb", required=True, metavar="<command>")

    def legacy(name: str, fill: Any, run: Any, effect: str, now: str) -> None:
        """The old spelling, hidden from the listing and still working.

        Kept rather than dropped: these are written into skills, notes and
        shell history that nobody is going to sweep, and a command that
        stops existing teaches nothing on its way out. It says the new
        form once, on stderr, where it cannot corrupt a `--json` read.
        """
        old = subs.add_parser(name)
        fill(old)
        old.set_defaults(run=run, effect=effect, renamed=now)

    # -- units: the ledger, and everything that writes to it ---------------
    units = subs.add_parser("units", help="the ledger, filtered")
    _fill_units_filters(units)
    _fill_units_writes(units)
    units.set_defaults(run=cmd_units, effect=READS)
    changes = units.add_subparsers(dest="change", metavar="<change>")

    p = changes.add_parser("extract", help="a document into units; never reads the maths")
    _fill_extract(p)
    p.set_defaults(run=cmd_extract, effect=REPO)

    p = changes.add_parser("classify", help="propose skips; applies nothing")
    _fill_classify(p)
    p.set_defaults(run=cmd_classify, effect=REPO)

    p = changes.add_parser("add", help="a unit where there was nothing to segment")
    _fill_units_add(p)
    p.set_defaults(run=cmd_units, effect=REPO)

    p = changes.add_parser("set", help="a unit's state, gist, transcription or settings")
    _fill_units_set(p)
    p.set_defaults(run=cmd_units, effect=REPO)

    p = changes.add_parser("note", help="leave an annotation on a unit")
    p.add_argument("id", metavar="UNIT")
    p.add_argument("annotate", metavar="TEXT")
    p.add_argument("--audience", choices=("claude", "me", "all"), default="claude")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_units, effect=REPO)

    p = changes.add_parser("clear-notes", help="drop a unit's annotations, once acted on")
    p.add_argument("id", metavar="UNIT")
    p.add_argument("--audience", choices=("claude", "me", "all"), default="claude")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_units, effect=REPO, resolve_notes=True)

    p = changes.add_parser("suggest", help="propose a decision; records it, applies nothing")
    p.add_argument("id", metavar="UNIT")
    p.add_argument("suggest", nargs=2, metavar=("STATE", "REASON"))
    p.add_argument("--detail", default="", help="the argument, for a human")
    p.add_argument("--by", default="claude", help="who is proposing")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_units, effect=REPO)

    p = changes.add_parser("accept", help="act on a unit's suggestion")
    p.add_argument("id", metavar="UNIT")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_units, effect=REPO, accept=True)

    p = changes.add_parser("dismiss", help="discard a unit's suggestion")
    p.add_argument("id", metavar="UNIT")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_units, effect=REPO, dismiss=True)

    legacy("extract", _fill_extract, cmd_extract, REPO, "units extract")
    legacy("classify", _fill_classify, cmd_classify, REPO, "units classify")

    # -- cards -------------------------------------------------------------
    cards = subs.add_parser("cards", help="the cards, filtered")
    _fill_cards_filters(cards)
    cards.set_defaults(run=cmd_cards, effect=READS)
    made = cards.add_subparsers(dest="change", metavar="<change>")
    p = made.add_parser("new", help="scaffold a stub card from a queued unit")
    _fill_cards_new(p)
    p.set_defaults(run=cmd_new, effect=REPO)
    legacy("new", _fill_cards_new, cmd_new, REPO, "cards new")

    # -- sources -----------------------------------------------------------
    sources = subs.add_parser("sources", help="every work, and which project reads it")
    sources.add_argument("--project", default=None, help="only the works this one reads")
    sources.add_argument("--json", action="store_true")
    sources.set_defaults(
        run=cmd_sources, effect=READS, remove=None, force=False, dry_run=False
    )
    taken = sources.add_subparsers(dest="change", metavar="<change>")
    p = taken.add_parser("remove", help="take a work out of a project")
    _fill_sources_remove(p)
    p.set_defaults(run=cmd_sources, effect=REPO)

    # -- zotero ------------------------------------------------------------
    zotero = subs.add_parser("zotero", help="what Zotero holds, and what is already a source")
    zotero.add_argument("--project", default=None)
    zotero.add_argument("--json", action="store_true")
    zotero.set_defaults(
        run=cmd_zotero,
        effect=READS,
        list_items=True,
        item=None,
        tag=None,
        dry_run=False,
    )
    brought = zotero.add_subparsers(dest="change", metavar="<change>")
    p = brought.add_parser("import", help="the marks you made, as units")
    _fill_zotero_import(p)
    p.set_defaults(run=cmd_zotero, effect=REPO, list_items=False)

    # -- project -----------------------------------------------------------
    project = subs.add_parser("project", help="the projects this repo holds")
    project.add_argument("--json", action="store_true")
    project.set_defaults(
        run=cmd_projects, effect=READS, name=None, delete=False, force=False, dry_run=False
    )
    started = project.add_subparsers(dest="change", metavar="<change>")
    p = started.add_parser("new", help="start one with no document, for a subject")
    _fill_project_new(p)
    p.set_defaults(run=cmd_project, effect=REPO, delete=False, force=False, dry_run=False)
    p = started.add_parser("delete", help="its folder, its cards, and its table")
    _fill_project_delete(p)
    p.set_defaults(
        run=cmd_project, effect=REPO, delete=True, title="", deck="", citation=""
    )

    # -- topic -------------------------------------------------------------
    topic = subs.add_parser("topic", help="what a project has been asked for")
    topic.add_argument("--project", default=None)
    topic.add_argument("--json", action="store_true")
    topic.set_defaults(run=cmd_topics, effect=READS, name=None, ask="")
    asked = topic.add_subparsers(dest="change", metavar="<change>")
    p = asked.add_parser("add", help="record a subject you want cards for")
    _fill_topic_add(p)
    p.set_defaults(run=cmd_topic, effect=REPO)

    # -- anki: the three that reach outside this repo -----------------------
    anki = subs.add_parser("anki", help="what a push would do, pushing nothing")
    _fill_push(anki)
    anki.set_defaults(run=cmd_sync, effect=READS, dry_run=True)
    pushed = anki.add_subparsers(dest="change", metavar="<change>")
    p = pushed.add_parser("push", help="approved cards into your collection")
    _fill_push(p)
    p.set_defaults(run=cmd_sync, effect=ANKI)
    p = pushed.add_parser("pull", help="review comments and flags back out, erasing them there")
    _fill_pull(p)
    p.set_defaults(run=cmd_feedback, effect=ANKI)
    p = pushed.add_parser("export", help="a deck as an .apkg")
    _fill_export(p)
    p.set_defaults(run=cmd_export, effect=ANKI)

    legacy("sync", _fill_push, cmd_sync, ANKI, "anki push")
    legacy("feedback", _fill_pull, cmd_feedback, ANKI, "anki pull")
    legacy("export", _fill_export, cmd_export, ANKI, "anki export")

    # -- the plain reads ----------------------------------------------------
    p = subs.add_parser("serve", help="the app: setup, triage, review, the canvas")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(run=cmd_serve, effect=REPO)

    p = subs.add_parser(
        "context", help="the page an equation was printed on, for writing its card"
    )
    p.add_argument("unit", help="unit id, shaped <source>:<section>:<equation>")
    p.add_argument(
        "--pages",
        type=_window,
        default=None,
        metavar="N",
        help=(
            "pages either side to print, or `chapter` for the whole chapter "
            "this unit is in. Defaults to whatever the unit, its source or the "
            "repo asks for, so a unit marked during triage as needing more "
            "gets it without the caller knowing"
        ),
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_context, effect=READS)

    p = subs.add_parser("crops", help="render unit crops to a directory, for transcription")
    p.add_argument("--project", default=None)
    p.add_argument("--section", default=None)
    p.add_argument("--state", default="all", help=f"one of: {', '.join(ledger_mod.STATES)}, all")
    p.add_argument(
        "--untranscribed",
        action="store_true",
        help="only units that still need reading (transcription: none or failed)",
    )
    p.add_argument(
        "--ungisted",
        action="store_true",
        help="only units with no gist yet -- what a `/gist` pass has left to render",
    )
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--out",
        default=None,
        help="directory to write PNGs into (working files). "
        "Default: a fresh directory under the configured work_dir.",
    )
    p.add_argument(
        "--context",
        type=float,
        default=None,
        help="points of surrounding page to show around each crop "
        "(default: the same as the triage view). 0 for a bare crop.",
    )
    p.add_argument(
        "--no-outline",
        action="store_true",
        help="do not draw the unit's own box on the crop",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_crops, effect=READS)

    p = subs.add_parser("audit", help="mechanical confidence checks over a ledger")
    p.add_argument("--project", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_audit, effect=READS)

    p = subs.add_parser("source-text", help="the cached text layer, for card-writing context")
    p.add_argument("project", nargs="?", default=None)
    p.set_defaults(run=cmd_source_text, effect=READS)

    p = subs.add_parser("check", help="lint card files; structural only")
    p.add_argument("--sync", action="store_true", help="apply the stricter sync rules")
    p.add_argument(
        "--anki", action="store_true", help="also check uids against the live collection"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_check, effect=READS)

    p = subs.add_parser("todo", help="open @claude and @me annotations")
    p.add_argument(
        "--audience",
        choices=("claude", "me"),
        default=None,
        help=(
            "whose notes. `claude` is the work you can actually do; `me` is "
            "parked for a human and is only ever reported"
        ),
    )
    p.add_argument("--kind", choices=("card", "unit"), default=None)
    p.add_argument(
        "--status", default=None, help="a card status or a unit state, e.g. approved, queued"
    )
    p.add_argument(
        "--project",
        default=None,
        help=(
            "one source's notes. Worth reaching for on a repo with several: "
            "conventions are per source, so working two books' notes in one "
            "list means reloading the setting between every item"
        ),
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_todo, effect=READS)

    p = subs.add_parser("verify", help="opt-in numeric check of identities")
    p.add_argument("--uid", default=None)
    p.add_argument("--project", default=None, help="only this project's cards")
    p.add_argument("--trials", type=int, default=verify.TRIALS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_verify, effect=READS)

    return parser



# -- verbs -----------------------------------------------------------------


def cmd_extract(args: argparse.Namespace, config: Config) -> int:
    names = [args.project] if args.project else sorted(config.projects)
    if not names:
        print("no sources configured in forge.toml", file=sys.stderr)
        return MISUSE
    reports = []
    for name in names:
        try:
            report = extract_mod.run(config, name, pages=_page_range(args.pages))
        except ConfigError as exc:
            # A source with no `tex`/`pdf` is not a broken source: a Zotero
            # import has its documents on `locator.document` and is filled by
            # `forge zotero`, not by segmentation. Taking the whole run down
            # over one such source meant the bare `forge units extract` in the docs
            # always exited non-zero once a second kind of source existed.
            if args.project:
                raise
            print(f"  skipped {name}: {exc}", file=sys.stderr)
            continue
        reports.append(report)
        if not args.json:
            print(report.summary())
            for warning in report.warnings:
                print(f"  warning: {warning}", file=sys.stderr)
    if args.json:
        print(json.dumps([_report_json(r) for r in reports], indent=2))
    return OK


def cmd_zotero(args: argparse.Namespace, config: Config) -> int:
    """Zotero marks into units.

    Reads Zotero's local API directly, the way `sync` reads AnkiConnect: a
    documented local endpoint with no credentials. Nothing is written back,
    and nothing could be -- the local API is read-only.
    """
    from . import zotero as zotero_api
    from .extract import zotero as zotero_units

    client = zotero_api.Zotero()
    if args.list_items:
        return _list_zotero(client, config, args)
    try:
        if args.tag:
            items = client.tagged(args.tag)
            if not items:
                print(f"no Zotero items tagged {args.tag!r}", file=sys.stderr)
                return MISUSE
        elif args.item:
            items = _zotero_lookup(client, args.item)
            if not items:
                print(f"no Zotero item matches {args.item!r}", file=sys.stderr)
                return MISUSE
        elif args.project:
            # This project's own items, by the keys it already declares. The
            # narrow end of the same command: `--tag anki` is every shelf you
            # marked up, and this is the one book in front of you.
            spec = config.projects.get(args.project)
            keys = [w.zotero_key for w in spec.sources if w.zotero_key] if spec else []
            if not keys:
                print(
                    f"{args.project!r} declares no Zotero item to re-read",
                    file=sys.stderr,
                )
                return MISUSE
            items = [found for key in keys for found in _zotero_lookup(client, key)]
            if not items:
                print(f"no Zotero item matches {', '.join(keys)}", file=sys.stderr)
                return MISUSE
        else:
            print(
                "name an item (cite key or Zotero key), --project for the ones "
                "one project declares, or --tag to take a whole shelf",
                file=sys.stderr,
            )
            return MISUSE

        reports = []
        for item in items:
            source = args.project or _project_name(item)
            spec = config.projects.get(source)
            # This item's own table, if the project already declares it.
            # By the key in hand rather than by `spec.source()`, which
            # answers for the project as a whole and so answered nothing
            # once there was a second source on the shelf: the run then
            # read the repo-wide scheme and every attachment, ignoring the
            # `units_from` and the `documents` this work states.
            mine = (
                next((w for w in spec.sources if w.zotero_key == item.key), None)
                if spec
                else None
            )
            # `extract = false` means no units come out of this work, and
            # an import is the one place that would add some. Refused
            # rather than warned about: the switch says what it says, and
            # re-running to refresh the title and the attachments, which is
            # the other reason to run this, still works. So does the text
            # layer, which is context for the units already there.
            refused = mine is not None and not mine.authoritative
            report = zotero_units.build(
                client,
                item,
                source=source,
                zotero=config.zotero_for(source, item.key),
                documents=mine.attachments if mine else (),
                # Cached under whoever extracts from the *item*, which is
                # the one project that can. An attachment key is not
                # declared anywhere, so the item is what resolves it.
                text_for=None
                if args.dry_run
                else _text_cacher(config, config.extracting(item.key) or source),
            )
            reports.append((source, item, report, refused))
            if not args.dry_run:
                stub = config.projects_dir / source / PROJECT_TOML
                # This work's own scheme, by the key in hand. Without the
                # key it resolved for the project, which is the repo
                # default once there is a second source declared.
                scheme = config.zotero_for(source, item.key)
                # The scheme in force, written into the stub commented out, so
                # the first thing you see when you go to override one of these
                # keys is the value you are replacing.
                stub.parent.mkdir(parents=True, exist_ok=True)
                fresh = zotero_units.write_source_stub(stub, item, scheme=scheme)
                # And into a project that already has a file, a table of its
                # own. Whether or not anything was marked: the import says
                # this project reads the work, and you mark a book up over
                # weeks. Without this, importing into an existing project
                # declared nothing, and importing a book you had not marked
                # yet wrote nothing at all.
                declared = fresh or projects_mod.declare_zotero(
                    config,
                    source,
                    key=item.key,
                    title=item.title,
                    citation=item.citation,
                )
            if refused and report.units:
                print(
                    f"  {source} has extraction off for {item.key}, so its"
                    f" {len(report.units)} marks stay marks. Turn `units are"
                    " extracted from this` on to import them.",
                    file=sys.stderr,
                )
            if not args.dry_run and report.units and not refused:
                # Through `Ledger.edit`, under the lock, like every other
                # write. This was the one that loaded and saved bare, which is
                # the last-writer-wins case the lock exists for, and the page
                # can start an import now while you are triaging the same
                # ledger.
                with ledger_mod.Ledger.edit(config.units_path(source)) as ledger:
                    added, refreshed = ledger.upsert(report.units)
                    # Narrowing `documents` leaves the earlier import behind,
                    # describing a PDF this source has stopped reading.
                    # Untouched units go; anything decided stays and is
                    # reported.
                    dropped, kept = ledger.drop_from_documents(report.excluded)
                    # And narrowing `units_from` leaves behind units whose
                    # colour no longer starts one. Same trade, for the same
                    # reason: this run is the moment the scheme and the
                    # ledger are both in hand.
                    orphans, decided = ledger.drop_from_scheme(scheme.makes_a_unit)
                # And the text layer cached for a document nothing reads any
                # more. `source-text` prints every one it finds, so leaving it
                # would hand a card writer a paper this source has dropped.
                for key in report.excluded:
                    extract_mod.source_text_path(config, source, key).unlink(missing_ok=True)
                report_line = f"{added} new, {refreshed} refreshed"
                if dropped or orphans:
                    report_line += f", {dropped + orphans} dropped"
                if kept:
                    report_line += f"; {kept} triaged units kept from excluded documents"
                if decided:
                    report_line += (
                        f"; {decided} triaged units kept whose mark no longer makes one"
                    )
                if fresh:
                    report_line += f"; wrote {stub.relative_to(config.root)}"
                elif declared:
                    report_line += f"; declared in {stub.relative_to(config.root)}"
            elif refused:
                # Before the dry-run branch: "nothing written" is true of
                # a dry run and says the wrong reason for this one, where
                # nothing would be written either way.
                report_line = (
                    "nothing would be imported" if args.dry_run else "none imported"
                ) + ", extraction is off for this work"
            elif args.dry_run:
                report_line = "nothing written"
            else:
                # Declared and empty is a normal state, not a failure: you
                # have the book and have not marked it up yet. Saying "no
                # units" alone read as "nothing happened".
                report_line = "no marks yet"
                if fresh or declared:
                    where = stub.relative_to(config.root)
                    report_line += (
                        f"; {'wrote' if fresh else 'declared in'} {where}."
                        " Mark it up in Zotero and run this again"
                    )
            if not args.json:
                _print_zotero(source, item, report, report_line, refused=refused)
    except zotero_api.ZoteroError as exc:
        print(str(exc), file=sys.stderr)
        return FAILED

    if args.json:
        print(
            json.dumps(
                [_zotero_row(source, item, r, no) for source, item, r, no in reports],
                indent=2,
            )
        )
    return OK if all(r.ok for _, _, r, _ in reports) else FAILED


def _list_zotero(client: Any, config: Config, args: argparse.Namespace) -> int:
    """What Zotero has, and which of it this repo already reads.

    Registering a source is a command rather than a button, because it reads
    Zotero, writes files and caches a text layer. But "which of my papers have
    I not imported yet" is a question you have *before* running it, and the
    only way to answer it was to run the import and read what it said.
    """
    from . import zotero as zotero_api

    try:
        items = client.tagged(args.tag) if args.tag else client.tagged("anki")
    except zotero_api.ZoteroError as exc:
        print(str(exc), file=sys.stderr)
        return FAILED

    known = {
        name: next((w.zotero_key for w in spec.sources if w.zotero_key), "")
        for name, spec in config.projects.items()
    }
    by_key = {key: name for name, key in known.items() if key}
    rows = [
        {
            "item": item.key,
            "citation": item.citation,
            "title": item.title,
            "source": by_key.get(item.key, ""),
        }
        for item in items
    ]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return OK
    if not rows:
        print(f"no Zotero items tagged {args.tag or 'anki'!r}", file=sys.stderr)
        return MISUSE
    for row in rows:
        mark = "*" if row["source"] else " "
        where = row["source"] or "not imported"
        print(f" {mark} {row['citation']:<28} {where}")
    fresh = [r for r in rows if not r["source"]]
    if fresh:
        tag = args.tag or "anki"
        print()
        print(f"{len(fresh)} not imported yet: `uv run forge zotero import --tag {tag}`")
    return OK


def _text_cacher(config: Config, source: str) -> Any:
    """Bound here rather than in the loop, so the closure keeps this source."""

    def cache(document: str, pdf: Path) -> int:
        return extract_mod.cache_document_text(config, source, document, pdf)

    return cache


def _zotero_lookup(client: Any, wanted: str) -> list[Any]:
    """A raw Zotero item key, a Better BibTeX cite key, or a title.

    A Zotero key is eight uppercase alphanumerics and resolves directly. A cite
    key comes from Better BibTeX rather than Zotero, so it is matched against
    what the search returns rather than asked for by name.
    """
    if len(wanted) == 8 and wanted.isalnum() and wanted.upper() == wanted:
        try:
            return [client.item(wanted)]
        except Exception:
            pass
    found = client.search(wanted)
    exact = [item for item in found if item.citation_key == wanted]
    return exact or found


def _project_name(item: Any) -> str:
    """The cite key if Better BibTeX gave it one, else the Zotero key.

    Never the title: a source name ends up in every unit id, and a title that
    gets tidied later would orphan every one of them.
    """
    return item.citation_key or item.key


def _zotero_row(source: str, item: Any, report: Any, refused: bool) -> dict[str, Any]:
    """One import, as the machine interface reports it.

    `units` is what is in the ledger, so a refused run says none and puts
    what it would have made under `would_make`. The refusal used to be on
    stderr only, and `--json` is the interface this repo tells you to read
    from, so a row listing two units beside an empty ledger was the one
    place it could not be checked.
    """
    return {
        "source": source,
        "item": item.key,
        "citation": item.citation,
        "documents": report.documents,
        "attachments": [
            {"key": key, "title": title, "read": taken}
            for key, title, taken in report.attachments
        ],
        "marks": report.annotations,
        "units": [] if refused else [u.id for u in report.units],
        **(
            {
                "refused": "extraction is off for this work",
                "would_make": [u.id for u in report.units],
            }
            if refused
            else {}
        ),
        "unmapped": report.unmapped,
        "skipped": report.skipped,
    }


def _print_zotero(
    source: str, item: Any, report: Any, written: str, *, refused: bool = False
) -> None:
    print(f"{item.citation}  ->  {source}")
    # A refused run counts marks and no units. Printing the units it would
    # have made, beside a `written` reading "none imported", said both
    # things in one sentence.
    made = written if refused else f"{len(report.units)} units; {written}"
    print(
        f"  {report.annotations} marks on {report.documents} document(s): {made}"
        + (f"; {report.text_chars // 1000}k chars of text layer" if report.text_chars else "")
    )
    # Every PDF on the item, every run. You cannot choose between attachments
    # you have never been shown, and an item routinely carries the paper and a
    # preprint of it -- importing both silently doubles every mark.
    if len(report.attachments) > 1:
        print("  attachments:")
        for key, title, taken in report.attachments:
            mark = "*" if taken else " "
            print(f"   {mark} {title or '(untitled)'}  [{key}]")
        if all(taken for _, _, taken in report.attachments):
            print("     all of them; name the ones you want in `documents = [...]`")
    for name, count in sorted(report.unmapped.items(), key=lambda kv: -kv[1]):
        print(f"  unmapped: {name} x{count} -- say what it means in [zotero.meanings]")
    for line in report.skipped:
        print(f"  skip: {line}", file=sys.stderr)


def cmd_export(args: argparse.Namespace, config: Config) -> int:
    """A deck as an `.apkg`.

    Everything else here describes a pipeline; this is its output, openable by
    anyone with Anki and nothing else installed. It doubles as a fixture: a
    deck you can regenerate and diff.

    Anki does the writing, so the path is Anki's to resolve and has to be
    absolute -- a relative one would land in Anki's working directory, which is
    not where you are standing.
    """
    if args.deck:
        deck = args.deck
    elif args.project:
        deck = config.deck_for(args.project)
    else:
        print("name a source, or --deck", file=sys.stderr)
        return MISUSE

    out = Path(args.out) if args.out else Path(f"{model.slugify(deck)}.apkg")
    out = out.expanduser().resolve()

    client = AnkiConnect(config.anki_url)
    try:
        written = client.export_package(deck, str(out), include_sched=args.scheduling)
    except AnkiError as exc:
        print(str(exc), file=sys.stderr)
        if "sfld" in str(exc):
            # Bisected a 108-card deck down to one card to find this. `uid` is
            # the note type's first field, and Anki keeps the sort field in a
            # column that takes a number or text. A uid shaped `4e6166` is a
            # float literal -- 4 x 10^6166 -- which overflows a double and
            # lands as NULL. One such note takes the whole export down.
            offenders = sorted(
                card.uid
                for card in model.load_all(config.cards_dir)
                if model.looks_numeric(card.uid)
            )
            print(
                "\nA uid that Anki reads as a number: it stores the sort field "
                "in a column that takes a number or text, and one like "
                "`4e6166` overflows to NULL and takes the whole export with it."
                f"\nCandidates here: {', '.join(offenders) or '(none)'}."
                "\n\nFix it once, in Anki: Tools > Manage Note Types > "
                f"{config.note_type} > Fields > Front > 'Sort by this field in "
                "the browser'. The uid stays the first field, so duplicate "
                "detection and `sync` are unaffected. New uids avoid the shape.",
                file=sys.stderr,
            )
        return FAILED
    if not written:
        print(
            f"Anki refused to export {deck!r}. It has to exist and hold cards; "
            "`forge anki push` puts them there.",
            file=sys.stderr,
        )
        return FAILED

    size = out.stat().st_size // 1024 if out.exists() else 0
    history = "with your review history" if args.scheduling else "no review history"
    print(f"{deck} -> {out} ({size}k, {history})")
    return OK


def cmd_project(args: argparse.Namespace, config: Config) -> int:
    """Scaffold a project that reads nothing, or delete one.

    The writing lives in `projects.scaffold`, because the setup stage in the
    app offers the same thing and the two must produce the same file: that
    is invariant 2, and the way to keep it true is one function rather than
    two that agree today.
    """
    if args.delete:
        return _delete_project(args, config)
    made = projects_mod.scaffold(
        config,
        args.name,
        title=args.title,
        deck=args.deck,
        citation=args.citation,
    )
    if made is None:
        if not re.search(r"[a-zA-Z0-9]", args.name):
            print(f"{args.name!r} has nothing to make a name from", file=sys.stderr)
            return MISUSE
        print(
            f"{config.projects_dir / model.slugify(args.name) / PROJECT_TOML}"
            " is already there, left alone",
            file=sys.stderr,
        )
        return FAILED
    print(f"{config.projects_dir / made / PROJECT_TOML}")
    print(f"  propose into it with: forge units add '<subject>' --project {made}")
    return OK


def _delete_project(args: argparse.Namespace, config: Config) -> int:
    """`forge project delete <name>`.

    Prints what it takes, every time, whether or not it took it: a delete
    that says nothing is one you cannot check afterwards. `--dry-run` is the
    same report with nothing removed.

    The name, not a title: a project is a folder, and deleting the wrong one
    because two projects are called "notes" is exactly the mistake worth
    making impossible.
    """
    try:
        going = (
            projects_mod.removal(config, args.name)
            if args.dry_run
            else projects_mod.remove(config, args.name, force=args.force)
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return FAILED
    verb = "would remove" if args.dry_run else "removed"
    for path in (going.folder, going.cards_dir):
        if path is not None:
            print(f"  {verb} {path}")
    if going.declared:
        where = "would drop" if args.dry_run else "dropped"
        print(f"  {where} [projects.{going.project}] from forge.toml")
    if going.units or going.cards:
        print(f"  {going.units} units, {going.cards} cards")
    if going.approved:
        # Nothing local records a note id, so the only honest thing to do is
        # say the notes are still there and let whoever ran this decide.
        print(
            f"  {going.approved} of those cards were approved and are already"
            f" notes in Anki. This does not remove them; delete them there,"
            f" or leave them.",
            file=sys.stderr,
        )
    if going.empty and going.folder is None and not going.declared:
        print(f"  {going.project} was already gone")
    return OK


def cmd_topic(args: argparse.Namespace, config: Config) -> int:
    """Record an ask, and say what is still open under it.

    The same append the setup stage makes, through the same function: two
    ways to write one file is how the two drift, and invariant 2 is only
    true while they cannot.
    """
    if args.project not in config.projects:
        known = ", ".join(sorted(config.projects)) or "(none)"
        print(f"no project {args.project!r}; configured: {known}", file=sys.stderr)
        return FAILED
    if not re.search(r"[a-zA-Z0-9]", args.name):
        print(f"{args.name!r} has nothing to make a topic from", file=sys.stderr)
        return MISUSE

    before = {t.slug for t in topics_mod.read(config, args.project)}
    topic = topics_mod.append(config, args.project, args.name, args.ask)
    print(f"{topics_mod.path_for(config, args.project)}")
    if topic.slug in before:
        print(f"  {topic.name} was already there, left alone")
    else:
        print(f"  {topic.name}")
    print(
        f"  outline it with: /propose --project {args.project} '{args.name}'"
    )
    return OK


def cmd_serve(args: argparse.Namespace, config: Config) -> int:
    from .app import serve

    host = args.host or config.host
    port = args.port or config.port
    print(f"forge on http://{host}:{port}  (units triage + card review)")
    serve(config, host=host, port=port)
    return OK


def cmd_context(args: argparse.Namespace, config: Config) -> int:
    """The page an equation was printed on.

    Conditions are usually printed around an identity rather than inside it,
    so the crop cannot carry them. Whether the identity needs a condition the
    page never states is mathematics, and stays with whoever writes the card.
    """
    from . import context as context_mod

    found = context_mod.assemble(config, args.unit, spread=args.pages)
    if found is None:
        print(f"no unit {args.unit!r}", file=sys.stderr)
        return FAILED
    if args.json:
        print(json.dumps(found.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(found.format())
    return OK


def cmd_units(args: argparse.Namespace, config: Config) -> int:
    # Before the ledgers are opened: a project proposed into for the first
    # time has no `units.jsonl` yet, and "run `forge units extract`" is the wrong
    # advice for one with no document to extract from.
    if args.add is not None:
        return _add_unit(args, config)

    ledgers = ledger_mod.open_ledgers(config.projects_dir)
    if args.project:
        ledgers = {k: v for k, v in ledgers.items() if k == args.project}
    if not ledgers:
        print("no units ledger yet; run `forge units extract`", file=sys.stderr)
        return FAILED

    if args.id and (
        args.set_state
        or args.annotate
        or args.tex_auto
        or args.resolve_notes
        or args.suggest
        or args.accept
        or args.dismiss
        or args.context_pages is not None
        or args.web is not None
        or args.gist is not None
    ):
        return _mutate_unit(args, ledgers, config)

    flagged: dict[str, set[str]] = {}
    if args.flagged:
        flagged = {name: audit_mod.audit(led, name).flagged for name, led in ledgers.items()}

    rows: list[dict[str, Any]] = []
    for name, led in ledgers.items():
        for unit in led.select(state=args.state, section=args.section):
            # `--id` narrows the listing too, not only the writing path it
            # was built for. Reading one unit back is what a transcriber
            # does to check its own work, and the skill has been telling
            # people to pass `--id` for that all along, which quietly
            # printed the whole ledger.
            if args.id and unit.id != args.id:
                continue
            if args.flagged and unit.id not in flagged.get(name, set()):
                continue
            if args.suggested and unit.suggestion is None:
                continue
            if args.ungisted and unit.gist:
                continue
            row = unit.to_json()
            row["source"] = name
            row["citation"] = unit.citation(config.project(name).citation)
            rows.append(row)
    if args.limit:
        rows = rows[: args.limit]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return OK

    if not rows:
        print(f"no units with state={args.state}")
        return OK
    for row in rows:
        locator = ledger_mod.Locator(**row.get("locator", {})).describe()
        tex = row.get("tex_source") or row.get("tex_auto") or ""
        flag = "" if row.get("transcription") == "ok" else f"  [{row.get('transcription')}]"
        print(f"{row['state']:8} {row['id']:34} {locator:22}{flag}")
        # The gist above the transcription: it is the line that says what this
        # would become, which is what you are scanning a list of 750 for.
        if row.get("gist"):
            print(f"         {row['gist'][:110]}")
        if tex:
            print(f"         {tex[:110]}")
    counts = {name: led.counts() for name, led in ledgers.items()}
    print("\n" + "  ".join(f"{n}: {c}" for n, c in counts.items()))
    return OK


def _add_unit(args: argparse.Namespace, config: Config) -> int:
    """`units --add`: the door for a frontend that is not a segmenter.

    Extraction produces units and never cards (invariant 3), and that holds
    whichever door a unit came in by. This one is for a project with no
    document, where nothing can be segmented and a pass proposes subjects
    instead: a gist, a short sample, the references it read. It writes no
    front and no back, which is the line between triage and review.

    The id is `<project>:<slug>`, so the slug is the stable id the contract
    asks for and re-running a request adds only what it has not proposed
    before. An existing slug is reported and left exactly as it is: it may
    have been triaged since, and a proposal must not walk over a decision.
    """
    if not args.project:
        print("--add needs --project", file=sys.stderr)
        return MISUSE
    folder = config.projects_dir / args.project
    if not folder.is_dir():
        known = ", ".join(sorted(config.projects)) or "(none)"
        print(f"no project {args.project!r}; configured: {known}", file=sys.stderr)
        return FAILED
    try:
        unit, created = ledger_mod.add_unit(
            config.units_path(args.project),
            args.project,
            args.add,
            gist=args.gist or "",
            preview=args.preview or "",
            document=args.document,
            lang=args.lang,
            tags=args.tag,
            refs=args.ref,
        )
    except ValueError as exc:
        print(f"--add: {exc}", file=sys.stderr)
        return MISUSE
    if not created:
        print(f"{unit.id} is already there, left alone")
        return OK
    print(f"{unit.id}  new" + (f"  {unit.gist}" if unit.gist else ""))
    return OK


def _mutate_unit(
    args: argparse.Namespace, ledgers: dict[str, ledger_mod.Ledger], config: Config
) -> int:
    if not args.id:
        print("--set-state/--annotate/--tex-auto need --id", file=sys.stderr)
        return MISUSE
    for probe in ledgers.values():
        if probe.get(args.id) is None:
            continue
        # Re-read under the lock: `ledgers` was loaded before we knew we were
        # writing, and another process may have moved on since.
        with ledger_mod.Ledger.edit(probe.path) as led:
            if args.suggest:
                state, reason = args.suggest
                led.suggest(args.id, state, reason, args.detail, args.by)
                print(f"{args.id}: suggested {state} ({reason}) -- not applied")
            if args.accept:
                unit = led.accept(args.id)
                print(f"{args.id} -> {unit.state}" + (f" ({unit.reason})" if unit.reason else ""))
            if args.dismiss:
                led.dismiss(args.id)
                print(f"{args.id}: suggestion dismissed")
            if args.tex_auto is not None:
                state, stored = led.transcribe(
                    args.id, args.tex_auto, latex.checker(config.extra_macros)
                )
                print(f"{args.id} transcription: {state}" + (f"  {stored[:80]}" if stored else ""))
                if state == "failed":
                    print("  (did not parse under KaTeX; nothing stored)", file=sys.stderr)
            if args.context_pages is not None:
                target = led.get(args.id)
                if target is None:
                    print(f"no unit {args.id!r}", file=sys.stderr)
                    return FAILED
                # -1 is how you take the override off again, rather than
                # guessing which number meant "inherit".
                asked_for = args.context_pages
                target.context_pages = (
                    None if isinstance(asked_for, int) and asked_for < 0 else asked_for
                )
                led.save()
                asked = config.context_pages_for(
                    target.project, target.context_pages, target.locator.document
                )
                print(
                    f"{args.id}: card writers get "
                    + (
                        "the chapter it is in"
                        if asked == CHAPTER
                        else f"{asked} page(s) either side"
                    )
                    + ("" if target.context_pages is not None else " (inherited)")
                )
            if args.gist is not None:
                target = led.get(args.id)
                if target is None:
                    print(f"no unit {args.id!r}", file=sys.stderr)
                    return FAILED
                # One line. A gist that runs to a paragraph is a card being
                # written at the wrong stage, and it would not fit the one
                # place it is shown.
                target.gist = " ".join(args.gist.split()).strip()
                led.save()
                print(f"{args.id}: {target.gist or '(cleared)'}")
            if args.web is not None:
                target = led.get(args.id)
                if target is None:
                    print(f"no unit {args.id!r}", file=sys.stderr)
                    return FAILED
                target.web = None if args.web == "inherit" else args.web == "yes"
                led.save()
                allowed = config.web_for(target.project, target.web)
                whose = "this unit" if target.web is not None else "inherited"
                print(
                    f"{args.id}: web research "
                    + ("allowed" if allowed else "not allowed")
                    + f" ({whose})"
                )
            if args.resolve_notes:
                # "all" is the only way to reach the clear-everything path, and
                # it has to be asked for: 7 units carry a `@me` decision beside
                # a `@claude` request, and the old default wiped both.
                audience = "" if args.audience == "all" else args.audience
                cleared = led.resolve_notes(args.id, audience)
                print(f"{args.id}: {cleared} annotation(s) resolved")
            if args.set_state:
                unit = led.set_state(args.id, args.set_state, reason=args.reason)
                print(f"{unit.id} -> {unit.state}" + (f" ({unit.reason})" if unit.reason else ""))
            if args.annotate:
                text = args.annotate
                audience = "" if args.audience == "all" else args.audience
                if audience and not text.lstrip().startswith("@"):
                    text = f"@{audience} {text}"
                led.annotate(args.id, text)
                print(f"{args.id} annotated")
        return OK
    print(f"no unit {args.id!r} in any ledger", file=sys.stderr)
    return FAILED


def cmd_crops(args: argparse.Namespace, config: Config) -> int:
    """Render crops to disk so something can read them.

    Working files, not artefacts: the ledger holds geometry and the app
    renders on demand. This exists because a transcription pass needs actual
    PNGs on disk to open, and asking it to write its own rendering code would
    be a worse interface than a verb.
    """
    from .extract import render as render_mod

    ledgers = ledger_mod.open_ledgers(config.projects_dir)
    if args.project:
        ledgers = {k: v for k, v in ledgers.items() if k == args.project}
    if not ledgers:
        print("no units ledger yet; run `forge units extract`", file=sys.stderr)
        return FAILED

    # Context by default. A bare crop cannot show that an equation continues
    # outside it, so a reader of bare crops cannot tell a fragment from a whole
    # identity -- which is exactly the judgement the crop is being read for.
    context = render_mod.TRIAGE_CONTEXT if args.context is None else args.context

    # Default under work_dir so intermediates land in one disposable place
    # instead of whatever name the caller invents.
    out = Path(args.out) if args.out else config.scratch("crops", args.section or "all")
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    missing: set[str] = set()

    for name, led in ledgers.items():
        units = [
            u
            for u in led.select(state=args.state, section=args.section)
            if u.has_crop
            and (not args.untranscribed or u.transcription in ("none", "failed"))
            and (not args.ungisted or not u.gist)
        ]
        if args.limit:
            units = units[: args.limit]
        if not units:
            continue
        # Per unit, not per source. A source used to be one PDF named in the
        # config, so `source.pdf` answered this and a source without one was
        # skipped in silence -- which is every Zotero source, whose documents
        # hang off `locator.document`. The app's crop route already resolved it
        # this way; this verb did not, so `/transcribe` and `/classify` saw an
        # empty manifest and reported nothing to do.
        renderers: dict[str, render_mod.CropRenderer] = {}
        try:
            for unit in units:
                geometry = unit.crop_geometry()
                if geometry is None:
                    continue
                key = unit.locator.document
                if key not in renderers:
                    document = config.document_for(name, key)
                    if document is None or not document.exists():
                        missing.add(f"{name}/{key}" if key else name)
                        continue
                    renderers[key] = render_mod.CropRenderer(document)
                renderer = renderers[key]
                path = out / (re.sub(r"[^A-Za-z0-9._-]+", "_", unit.id) + ".png")
                # The same crop the app shows. Whatever reads these PNGs is
                # reading what a human would be shown for the same unit, and
                # two things called "the crop" that disagree about what is on
                # it would break the one thing the review model rests on.
                path.write_bytes(
                    renderer.render(
                        *geometry,
                        context=context,
                        outline=not args.no_outline,
                        width=config.crop_width_for(name, from_a_mark=bool(unit.marks)),
                        regions=render_mod.regions_for(unit, geometry[0]),
                    )
                )
                manifest.append(
                    {
                        "unit": unit.id,
                        "file": str(path),
                        "section": unit.locator.section,
                        # The general form; `equation` is what the frozen
                        # segmenter writes and is null for everything else.
                        "kind": unit.locator.ref[0],
                        "label": unit.locator.ref[1],
                        "equation": unit.locator.equation,
                        "page": unit.locator.page,
                        "context": unit.context,
                        # What the reader wrote on this exact mark, and nothing
                        # else. `/gist` needs it -- on a prose source the
                        # subject of a unit is the sentence you highlighted, so
                        # asking a model to infer it from the picture alone
                        # would be asking it to re-OCR text that is already
                        # here. Deliberately not the neighbours: a gist is
                        # supposed to be cheap.
                        "marked": unit.marks[0].text if unit.marks else "",
                        "comment": unit.marks[0].comment if unit.marks else "",
                        "gist": unit.gist,
                    }
                )
        finally:
            for renderer in renderers.values():
                renderer.close()

    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        for entry in manifest:
            print(f"{entry['unit']:<34} {entry['file']}")
        print(f"\n{len(manifest)} crops written to {out}")
    for where in sorted(missing):
        print(f"  no document on disk for {where}; its crops were skipped", file=sys.stderr)
    return OK


def _document(config: Config, project: str) -> Path | None:
    """The file a project's units were printed in, when it has one."""
    work = config.project(project).source()
    return work.pdf if work else None


def cmd_classify(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.projects_dir)
    if args.project:
        ledgers = {k: v for k, v in ledgers.items() if k == args.project}
    if not ledgers:
        print("no units ledger yet; run `forge units extract`", file=sys.stderr)
        return FAILED

    reports = []
    for name, probe in ledgers.items():
        if args.dry_run:
            reports.append(
                classify_mod.classify(probe, _document(config, name), name, write=False)
            )
            continue
        with ledger_mod.Ledger.edit(probe.path) as led:
            reports.append(
                classify_mod.classify(led, _document(config, name), name, write=True)
            )

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source": r.project,
                        "considered": r.considered,
                        "kept": r.kept,
                        "dry_run": args.dry_run,
                        "classified": [vars(c) for c in r.classified],
                    }
                    for r in reports
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return OK

    for report in reports:
        for item in report.classified:
            print(f"  {item.unit_id:<34} {item.reason:<13} {item.detail}")
        print(report.summary())
        if args.dry_run:
            print("  (dry run -- nothing changed)")
        elif report.classified:
            print(f"  review them with: forge units --state skipped --project {report.project}")
    return OK


def cmd_audit(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.projects_dir)
    if args.project:
        ledgers = {k: v for k, v in ledgers.items() if k == args.project}
    if not ledgers:
        print("no units ledger yet; run `forge units extract`", file=sys.stderr)
        return FAILED

    # The scheme goes in too: for a marked-up source, "is this index
    # trustworthy" includes "does it still match what you said starts a unit".
    reports = [
        audit_mod.audit(led, name, config.zotero_for(name).makes_a_unit)
        for name, led in ledgers.items()
    ]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source": r.project,
                        "total": r.total,
                        "numbered": r.numbered,
                        "expected": r.expected,
                        "complete": r.complete,
                        "flagged": sorted(r.flagged),
                        "findings": [f.as_dict() for f in r.findings],
                    }
                    for r in reports
                ],
                indent=2,
            )
        )
        return OK

    for report in reports:
        for finding in report.findings:
            print("  " + finding.format())
        print(report.summary())
    return FAILED if any(not r.complete and r.expected for r in reports) else OK


def cmd_source_text(args: argparse.Namespace, config: Config) -> int:
    """Print a source's cached text layer -- the context a card writer needs."""
    names = [args.project] if args.project else sorted(config.projects)
    for name in names:
        path = extract_mod.source_text_path(config, name)
        if not path.exists():
            print(f"no cached text for {name!r}; run `forge units extract`", file=sys.stderr)
            return FAILED
        print(path.read_text(encoding="utf-8"))
    return OK


def cmd_new(args: argparse.Namespace, config: Config) -> int:
    existing = model.load_all(config.cards_dir)
    taken = {c.uid for c in existing}

    units: list[ledger_mod.Unit] = []
    unit_ids: list[str] = list(args.unit or [])
    source_text = args.source or ""
    ledgers = ledger_mod.open_ledgers(config.projects_dir)
    for unit_id in unit_ids:
        project_name = unit_id.split(":", 1)[0]
        led = ledgers.get(project_name)
        found = led.get(unit_id) if led else None
        if found is None:
            print(f"no unit {unit_id!r} in {project_name}/units.jsonl", file=sys.stderr)
            return FAILED
        units.append(found)
    if units and not source_text:
        # One citation, from the first unit: the pieces of a split display are
        # the same equation, so citing each of them would just be noise.
        first = unit_ids[0].split(":", 1)[0]
        source_text = units[0].citation(config.project(first).citation)

    uid = model.mint_uid((unit_ids[0] if unit_ids else "") or args.front, taken)
    card = model.stub(
        uid=uid,
        front=args.front,
        back=args.back,
        source=source_text,
        unit=", ".join(unit_ids),
        card_type=args.type,
        tags=list(args.tag),
        gist=args.gist,
    )
    # Filed under the source it came from. This is filing only: `unit:` stays
    # the one place a card's source is recorded, because a directory and a
    # frontmatter field that both claim to say it will eventually disagree.
    # Every loader rglobs, so a card in the wrong folder still loads.
    folder = unit_ids[0].split(":", 1)[0] if unit_ids else ""
    path = config.cards_dir / folder / f"{uid}-{model.slugify(args.front)}.md"
    card.save(path)
    # The first snapshot, so the first review can show what the passes after
    # this one did to the stub.
    changes_mod.record(config, card, "written")

    for unit_id in unit_ids:
        with ledger_mod.Ledger.edit(ledgers[unit_id.split(":", 1)[0]].path) as led:
            led.mark_carded(unit_id, [uid])

    findings = check_mod.check_card(card, config)
    if args.json:
        print(
            json.dumps(
                {
                    "uid": uid,
                    "path": str(path.relative_to(config.root)),
                    "unit": ", ".join(unit_ids),
                    "findings": [f.as_dict() for f in findings],
                },
                indent=2,
            )
        )
    else:
        print(f"{uid}  {path.relative_to(config.root)}")
        for finding in findings:
            print("  " + finding.format())
    return FAILED if check_mod.errors(findings) else OK


def cmd_check(args: argparse.Namespace, config: Config) -> int:
    live: dict[str, int] | None = None
    if args.anki:
        from .sync import live_uid_counts

        live = live_uid_counts(AnkiConnect(config.anki_url), config)
    cards, findings = check_mod.check_repo(config, for_sync=args.sync, live_uids=live)

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        for finding in findings:
            print(finding.format())
        bad = len(check_mod.errors(findings))
        warn = len(findings) - bad
        backend = latex.checker(config.extra_macros)
        print(f"{len(cards)} cards, {bad} errors, {warn} warnings (latex: {backend.describe()})")
    return FAILED if check_mod.errors(findings) else OK


def cmd_todo(args: argparse.Namespace, config: Config) -> int:
    items = todo.collect(config)
    # Filtering here rather than by eye downstream. The audience split is what
    # decides whether a note is work or a report, so reading it off the prose
    # is the one mistake this list must not invite.
    if args.audience:
        items = [i for i in items if i.audience == args.audience]
    if args.kind:
        items = [i for i in items if i.kind == args.kind]
    if args.status:
        items = [i for i in items if i.status == args.status]
    if args.project:
        # Same rule as `app.card_in_source`: a card whose units name no source
        # belongs to all of them. It is misfiled, and a filter that hides it is
        # worse than one that shows it twice -- an open note nobody can reach
        # is an open note that blocks sync for ever.
        items = [i for i in items if i.source in ("", args.project)]
    if args.json:
        print(json.dumps([i.as_dict() for i in items], indent=2, ensure_ascii=False))
        return OK
    if not items:
        print("no open annotations" + (" matching that filter" if _todo_filtered(args) else ""))
        return OK
    for item in items:
        print(item.format())
    print(f"\n{len(items)} open annotation(s)")
    return OK


def _todo_filtered(args: argparse.Namespace) -> bool:
    return bool(args.audience or args.kind or args.status or args.project)


def cmd_feedback(args: argparse.Namespace, config: Config) -> int:
    from . import feedback as feedback_mod

    report = feedback_mod.run(config, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return OK if report.ok else FAILED

    for comment in report.imported:
        print(f"{comment.uid}  ({comment.kind})  {comment.text}")
    for ref, reason in report.skipped:
        print(f"{ref}: {reason}", file=sys.stderr)
    verb = "would import" if args.dry_run else "imported"
    print(f"\n{verb}: {len(report.imported)}, skipped {len(report.skipped)}")
    if report.imported and not args.dry_run:
        print("they are `@claude` notes now -- `/triage claude` works them")
    return OK if report.ok else FAILED


def _remove_source(args: argparse.Namespace, config: Config) -> int:
    """`forge sources remove <key> --project <name>`.

    Prints what it takes every time, whether or not it took it: a removal
    that says nothing is one you cannot check afterwards.
    """
    if not args.project:
        print("--remove needs --project: a work is read by one", file=sys.stderr)
        return MISUSE
    try:
        going = (
            projects_mod.source_removal(config, args.project, args.remove)
            if args.dry_run
            else projects_mod.remove_source(
                config, args.project, args.remove, force=args.force
            )
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return FAILED
    verb = "would remove" if args.dry_run else "removed"
    print(f"  {verb} {going.key} ({going.title}) from {going.project}")
    if going.units:
        print(f"  {'and' if not args.dry_run else 'would take'} {going.units} units with it")
    if going.cards:
        print(f"  {going.cards} cards stood on it", file=sys.stderr)
    if going.approved:
        print(
            f"  {going.approved} of them were approved and are already notes in"
            " Anki. This does not remove them; delete them there, or leave them.",
            file=sys.stderr,
        )
    return OK


def cmd_cards(args: argparse.Namespace, config: Config) -> int:
    """The cards, filtered. The read half of `cards`.

    Nothing answered "what cards are there" from a terminal: `check` lints
    them, `todo` lists their open notes, and the app draws them. So the
    noun had only a writing form, which is the arity rule saying one thing
    and the CLI doing another.
    """
    cards = model.load_all(config.cards_dir)
    if args.project:
        cards = [c for c in cards if c.project_name == args.project]
    if args.status and args.status != "all":
        cards = [c for c in cards if c.effective_status == args.status]
    if args.section:
        from .app import card_section

        cards = [c for c in cards if card_section(c, config) == args.section]
    cards.sort(key=lambda c: (c.project_name, c.unit, c.uid))
    if args.limit:
        cards = cards[: args.limit]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "uid": c.uid,
                        "project": c.project_name,
                        "status": c.effective_status,
                        "type": c.type,
                        "units": c.units,
                        "gist": c.gist,
                        "tags": c.tags,
                        "path": str(c.path),
                        **(
                            {"changes": changes_mod.view(config, c)}
                            if args.changes
                            else {}
                        ),
                    }
                    for c in cards
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return OK
    if not cards:
        print("no cards yet")
        return OK
    for card in cards:
        # The gist, not the front: a LaTeX front is unreadable in a column
        # and the gist exists for exactly this.
        print(f"{card.uid}  {card.effective_status:9} {card.gist or card.unit}")
        if args.changes:
            for line in _change_lines(changes_mod.view(config, card)):
                print("    " + line)
    print(f"\n{len(cards)} cards")
    return OK


def _change_lines(seen: dict[str, Any] | None) -> list[str]:
    """`--changes`, for a person: what moved since the last decision."""
    if seen is None:
        return ["no change record on this machine"]
    pending = seen["pending"]
    if not pending:
        return [f"unchanged since {seen['after']} {seen['since']}"]
    out = [f"since {seen['after']} {seen['since']}:"]
    out += [
        f"  {f['key']}: {f['before'] if f['before'] is not None else '-'}"
        f" -> {f['after'] if f['after'] is not None else '-'}"
        for f in pending["fields"]
    ]
    out += [f"  {s['name']}: {s['summary']}" for s in pending["sections"]]
    out += [f"  resolved: {line}" for line in pending["resolved"]]
    return out


def cmd_projects(args: argparse.Namespace, config: Config) -> int:
    """The projects this repo holds. The read half of `project`."""
    from .app import project_origin

    rows: list[dict[str, Any]] = []
    for name, spec in config.projects.items():
        path = config.units_path(name)
        units = sum(1 for _ in ledger_mod.Ledger.load(path)) if path.exists() else 0
        rows.append(
            {
                "project": name,
                "title": spec.title,
                "deck": config.deck_for(name),
                "material": project_origin(config, name),
                "sources": len(spec.sources),
                "units": units,
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return OK
    if not rows:
        print("no projects yet; start one with `forge project new <name>`")
        return OK
    width = max(len(r["project"]) for r in rows)
    for row in rows:
        print(
            f"{row['project']:<{width}}  {row['material'] or 'nothing declared':<16}"
            f"  {row['sources']} source(s)  {row['units']} units  -> {row['deck']}"
        )
    return OK


def cmd_topics(args: argparse.Namespace, config: Config) -> int:
    """What a project has been asked for. The read half of `topic`."""
    names = [args.project] if args.project else list(config.projects)
    rows: list[dict[str, Any]] = []
    for name in names:
        if name not in config.projects:
            known = ", ".join(sorted(config.projects)) or "(none)"
            print(f"no project {name!r}; configured: {known}", file=sys.stderr)
            return FAILED
        ledger = None
        path = config.units_path(name)
        if path.exists():
            ledger = ledger_mod.Ledger.load(path)
        for topic in topics_mod.coverage(config, name, ledger).topics:
            rows.append(
                {
                    "project": name,
                    "slug": topic.slug,
                    "name": topic.name,
                    "ask": topic.ask,
                    "entries": len(topic.outline),
                    "covered": topic.covered,
                }
            )
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return OK
    if not rows:
        print("nothing asked for yet; record one with `forge topic add`")
        return OK
    for row in rows:
        print(f"{row['name']}  ({row['covered']}/{row['entries']} entries have a unit)")
        if row["ask"]:
            print(f"    {row['ask'].splitlines()[0]}")
    return OK


def cmd_sources(args: argparse.Namespace, config: Config) -> int:
    """Every work, across every project.

    A source used to *be* a project, so "which sources are there" was the
    project list. It is a thing inside one now, and a paper can sit in two:
    cited by one project and extracted from by another. Nothing listed them
    across projects, so answering "have I got this already" meant opening
    every TOML (ROADMAP.md 10).
    """
    from .app import every_work

    if args.remove:
        return _remove_source(args, config)
    rows = every_work(config)
    if args.project:
        rows = [r for r in rows if r["project"] == args.project]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return OK
    if not rows:
        print("no works declared yet")
        return OK
    width = max(len(str(r["title"])) for r in rows)
    for row in rows:
        # Three words, because there are three states. A document with
        # extraction off is neither of the other two: it keeps the units
        # it made and makes no more, and calling it a plain `reference`
        # put it in the same column as a URL on the shelf.
        kind = (
            "authoritative"
            if row["authoritative"]
            else "extraction off"
            if row["document"]
            else "reference"
        )
        where = row["url"] or row["zotero"] or ", ".join(row["files"]) or "-"
        print(f"{row['title']!s:<{width}}  {row['project']}  {kind:<15}  {where}")
    return OK


def cmd_sync(args: argparse.Namespace, config: Config) -> int:
    from . import sync as sync_mod

    report = sync_mod.run(
        config,
        dry_run=args.dry_run,
        reposition_new=args.reposition,
        templates=args.templates,
        move_decks=args.move_decks,
        project=args.project or "",
    )
    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "dry_run": report.dry_run,
                    "outcomes": [vars(o) for o in report.outcomes],
                    "findings": [f.as_dict() for f in report.findings],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for finding in check_mod.errors(report.findings):
            print(finding.format(), file=sys.stderr)
        for outcome in report.outcomes:
            print(outcome.format())
        print(report.summary())
        if check_mod.errors(report.findings):
            print("nothing synced: fix the errors above", file=sys.stderr)
    return OK if report.ok else FAILED


def cmd_verify(args: argparse.Namespace, config: Config) -> int:
    cards = model.load_all(config.cards_dir)
    if args.project:
        # Layout is per source and `verify` refuses a source that declares
        # none, so "check this paper" is a question worth being able to ask
        # without the other books' skips burying the answer.
        cards = [c for c in cards if c.project_name == args.project]
    results = verify.run(cards, config, trials=args.trials, only=args.uid)
    if args.json:
        print(json.dumps([vars(r) for r in results], indent=2))
    else:
        for result in results:
            if result.status != verify.SKIP:
                print(result.format())
        states = ("pass", "fail", "error", "skip")
        tally = {s: sum(1 for r in results if r.status == s) for s in states}
        print(", ".join(f"{n} {s}" for s, n in tally.items()))
    return FAILED if any(r.status in (verify.FAIL, verify.ERROR) for r in results) else OK


# -- helpers ---------------------------------------------------------------


def _page_range(spec: str | None) -> range | None:
    if not spec:
        return None
    if "-" in spec:
        first, last = spec.split("-", 1)
        return range(int(first), int(last) + 1)
    page = int(spec)
    return range(page, page + 1)


def _report_json(report: extract_mod.ExtractReport) -> dict[str, Any]:
    data = vars(report).copy()
    data["path"] = str(report.path) if report.path else ""
    return data


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
