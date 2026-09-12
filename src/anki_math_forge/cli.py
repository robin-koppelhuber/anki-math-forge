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
from . import check as check_mod
from . import classify as classify_mod
from . import extract as extract_mod
from . import latex, model, todo, verify
from . import ledger as ledger_mod
from .anki import AnkiConnect, AnkiError
from .config import SOURCE_TOML, Config, ConfigError, load

OK, FAILED, MISUSE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: nearest forge.toml)")
    subs = parser.add_subparsers(dest="verb", required=True)

    p = subs.add_parser("extract", help="segment a source into units; never writes cards")
    p.add_argument("source", nargs="?", default=None)
    p.add_argument("--pages", default=None, help="page range, e.g. 10-40 (pdf sources)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_extract)

    p = subs.add_parser(
        "zotero",
        help="what you marked up in Zotero, as units",
    )
    p.add_argument(
        "item",
        nargs="?",
        default=None,
        help="a cite key or a Zotero item key; omit to take everything tagged",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="import every item carrying this Zotero tag",
    )
    p.add_argument(
        "--source",
        default=None,
        help="which source to file the units under (default: the cite key)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="say what would be imported and write nothing",
    )
    p.add_argument(
        "--list",
        action="store_true",
        dest="list_items",
        help=(
            "what is in Zotero and what is already a source here. Reads "
            "nothing else and writes nothing: it is the answer to 'which of "
            "these have I not imported yet'"
        ),
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_zotero)

    p = subs.add_parser(
        "export",
        help="a deck as an .apkg, for sharing or for keeping",
    )
    p.add_argument("source", nargs="?", default=None, help="whose deck to export")
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
    p.set_defaults(run=cmd_export)

    p = subs.add_parser("serve", help="the companion app: units triage + card review")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(run=cmd_serve)

    p = subs.add_parser(
        "context",
        help="the page an equation was printed on, for writing its card",
    )
    p.add_argument("unit", help="unit id, shaped <source>:<section>:<equation>")
    p.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help=(
            "pages either side to print. Defaults to whatever the unit, its "
            "source or the repo asks for, so a unit marked during triage as "
            "needing more gets it without the caller knowing"
        ),
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_context)

    p = subs.add_parser("units", help="view or re-state the ledger")
    p.add_argument("--source", default=None)
    p.add_argument("--state", default="all", help=f"one of: {', '.join(ledger_mod.STATES)}, all")
    p.add_argument("--section", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--id", default=None, help="unit to change (with --set-state / --annotate)")
    p.add_argument("--set-state", default=None, choices=ledger_mod.STATES)
    p.add_argument("--reason", default="", help="why it was skipped")
    p.add_argument("--annotate", default=None, metavar="TEXT")
    p.add_argument(
        "--tex-auto",
        default=None,
        metavar="TEX",
        help="record a transcription for --id; gated through KaTeX before it is stored",
    )
    p.add_argument(
        "--context-pages",
        type=int,
        default=None,
        metavar="N",
        help=(
            "how many pages either side a card writer should get for --id. "
            "Set it during triage, when you can see the hypotheses are two "
            "pages back. A large number means the whole document; -1 goes "
            "back to inheriting the source's setting"
        ),
    )
    p.add_argument(
        "--resolve-notes",
        action="store_true",
        help="clear the @claude annotations on --id, once you have acted on them",
    )
    p.add_argument(
        "--audience",
        choices=("claude", "me", "all"),
        default="claude",
        help=(
            "whose notes --resolve-notes clears, and who --annotate addresses. "
            "Defaults to `claude`: resolving your own requests must not delete a "
            "`@me` decision parked on the same unit"
        ),
    )
    p.add_argument("--flagged", action="store_true", help="only units the audit is unsure about")
    p.add_argument("--suggested", action="store_true", help="only units with an open suggestion")
    p.add_argument(
        "--suggest",
        nargs=2,
        default=None,
        metavar=("STATE", "REASON"),
        help="propose a decision for --id; records it, applies nothing",
    )
    p.add_argument("--detail", default="", help="the argument for a --suggest, for a human")
    p.add_argument("--by", default="claude", help="who is proposing (with --suggest)")
    p.add_argument("--accept", action="store_true", help="act on --id's suggestion")
    p.add_argument("--dismiss", action="store_true", help="discard --id's suggestion")
    p.set_defaults(run=cmd_units)

    p = subs.add_parser("crops", help="render unit crops to a directory, for transcription")
    p.add_argument("--source", default=None)
    p.add_argument("--section", default=None)
    p.add_argument("--state", default="all", help=f"one of: {', '.join(ledger_mod.STATES)}, all")
    p.add_argument(
        "--untranscribed",
        action="store_true",
        help="only units that still need reading (transcription: none or failed)",
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
    p.set_defaults(run=cmd_crops)

    p = subs.add_parser(
        "classify", help="skip units that were never going to be cards, with a reason"
    )
    p.add_argument("--source", default=None)
    p.add_argument(
        "--dry-run", action="store_true", help="report the proposals without recording them"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_classify)

    p = subs.add_parser("audit", help="mechanical confidence checks over a ledger")
    p.add_argument("--source", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_audit)

    p = subs.add_parser("source-text", help="the cached text layer, for card-writing context")
    p.add_argument("source", nargs="?", default=None)
    p.set_defaults(run=cmd_source_text)

    p = subs.add_parser("new", help="scaffold a stub card from a queued unit")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_new)

    p = subs.add_parser("check", help="lint card files; structural only")
    p.add_argument("--sync", action="store_true", help="apply the stricter sync rules")
    p.add_argument(
        "--anki", action="store_true", help="also check uids against the live collection"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_check)

    p = subs.add_parser("todo", help="open @claude annotations")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_todo)

    p = subs.add_parser("sync", help="push approved cards to Anki, upserting by uid")
    p.add_argument("--dry-run", action="store_true")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_sync)

    p = subs.add_parser(
        "feedback", help="pull review comments and flags back out of Anki"
    )
    p.add_argument("--dry-run", action="store_true", help="say what would come back")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_feedback)

    p = subs.add_parser("verify", help="opt-in numeric check of identities")
    p.add_argument("--uid", default=None)
    p.add_argument("--source", default=None, help="only this source's cards")
    p.add_argument("--trials", type=int, default=verify.TRIALS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_verify)

    return parser


# -- verbs -----------------------------------------------------------------


def cmd_extract(args: argparse.Namespace, config: Config) -> int:
    names = [args.source] if args.source else sorted(config.sources)
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
            # over one such source meant the bare `forge extract` in the docs
            # always exited non-zero once a second kind of source existed.
            if args.source:
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
        else:
            print(
                "name an item (cite key or Zotero key), or --tag to take a whole shelf",
                file=sys.stderr,
            )
            return MISUSE

        reports = []
        for item in items:
            source = args.source or _source_name(item)
            spec = config.sources.get(source)
            report = zotero_units.build(
                client,
                item,
                source=source,
                zotero=config.zotero_for(source),
                documents=spec.documents if spec else (),
                text_for=None if args.dry_run else _text_cacher(config, source),
            )
            reports.append((source, item, report))
            if not args.dry_run and report.units:
                stub = config.sources_dir / source / SOURCE_TOML
                fresh = zotero_units.write_source_stub(stub, item)
                ledger = ledger_mod.Ledger.load(config.units_path(source))
                added, refreshed = ledger.upsert(report.units)
                # Narrowing `documents` leaves the earlier import behind,
                # describing a PDF this source has stopped reading. Untouched
                # units go; anything decided stays and is reported.
                dropped, kept = ledger.drop_from_documents(report.excluded)
                ledger.save()
                # And the text layer cached for a document nothing reads any
                # more. `source-text` prints every one it finds, so leaving it
                # would hand a card writer a paper this source has dropped.
                for key in report.excluded:
                    extract_mod.source_text_path(config, source, key).unlink(missing_ok=True)
                report_line = f"{added} new, {refreshed} refreshed"
                if dropped:
                    report_line += f", {dropped} dropped"
                if kept:
                    report_line += f"; {kept} triaged units kept from excluded documents"
                if fresh:
                    report_line += f"; wrote {stub.relative_to(config.root)}"
            else:
                report_line = "nothing written" if args.dry_run else "no units"
            if not args.json:
                _print_zotero(source, item, report, report_line)
    except zotero_api.ZoteroError as exc:
        print(str(exc), file=sys.stderr)
        return FAILED

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source": source,
                        "item": item.key,
                        "citation": item.citation,
                        "documents": r.documents,
                        "attachments": [
                            {"key": key, "title": title, "read": taken}
                            for key, title, taken in r.attachments
                        ],
                        "marks": r.annotations,
                        "units": [u.id for u in r.units],
                        "unmapped": r.unmapped,
                        "skipped": r.skipped,
                    }
                    for source, item, r in reports
                ],
                indent=2,
            )
        )
    return OK if all(r.ok for _, _, r in reports) else FAILED


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

    known = {name: spec.zotero_key for name, spec in config.sources.items()}
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
        print(f"{len(fresh)} not imported yet: `uv run forge zotero --tag {tag}`")
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


def _source_name(item: Any) -> str:
    """The cite key if Better BibTeX gave it one, else the Zotero key.

    Never the title: a source name ends up in every unit id, and a title that
    gets tidied later would orphan every one of them.
    """
    return item.citation_key or item.key


def _print_zotero(source: str, item: Any, report: Any, written: str) -> None:
    print(f"{item.citation}  ->  {source}")
    print(
        f"  {report.annotations} marks on {report.documents} document(s): "
        f"{len(report.units)} units; {written}"
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
    elif args.source:
        deck = config.deck_for(args.source)
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
            "`forge sync` puts them there.",
            file=sys.stderr,
        )
        return FAILED

    size = out.stat().st_size // 1024 if out.exists() else 0
    history = "with your review history" if args.scheduling else "no review history"
    print(f"{deck} -> {out} ({size}k, {history})")
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
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `forge extract`", file=sys.stderr)
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
    ):
        return _mutate_unit(args, ledgers, config)

    flagged: dict[str, set[str]] = {}
    if args.flagged:
        flagged = {name: audit_mod.audit(led, name).flagged for name, led in ledgers.items()}

    rows: list[dict[str, Any]] = []
    for name, led in ledgers.items():
        for unit in led.select(state=args.state, section=args.section):
            if args.flagged and unit.id not in flagged.get(name, set()):
                continue
            if args.suggested and unit.suggestion is None:
                continue
            row = unit.to_json()
            row["source"] = name
            row["citation"] = unit.citation(config.source(name).citation)
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
        if tex:
            print(f"         {tex[:110]}")
    counts = {name: led.counts() for name, led in ledgers.items()}
    print("\n" + "  ".join(f"{n}: {c}" for n, c in counts.items()))
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
                target.context_pages = None if args.context_pages < 0 else args.context_pages
                led.save()
                asked = config.context_pages_for(target.source, target.context_pages)
                print(
                    f"{args.id}: card writers get {asked} page(s) either side"
                    + ("" if target.context_pages is not None else " (inherited)")
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

    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `forge extract`", file=sys.stderr)
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
            if u.has_crop and (not args.untranscribed or u.transcription in ("none", "failed"))
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


def cmd_classify(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `forge extract`", file=sys.stderr)
        return FAILED

    reports = []
    for name, probe in ledgers.items():
        if args.dry_run:
            reports.append(classify_mod.classify(probe, config.source(name).pdf, name, write=False))
            continue
        with ledger_mod.Ledger.edit(probe.path) as led:
            reports.append(classify_mod.classify(led, config.source(name).pdf, name, write=True))

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source": r.source,
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
            print(f"  review them with: forge units --state skipped --source {report.source}")
    return OK


def cmd_audit(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `forge extract`", file=sys.stderr)
        return FAILED

    reports = [audit_mod.audit(led, name) for name, led in ledgers.items()]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "source": r.source,
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
    names = [args.source] if args.source else sorted(config.sources)
    for name in names:
        path = extract_mod.source_text_path(config, name)
        if not path.exists():
            print(f"no cached text for {name!r}; run `forge extract`", file=sys.stderr)
            return FAILED
        print(path.read_text(encoding="utf-8"))
    return OK


def cmd_new(args: argparse.Namespace, config: Config) -> int:
    existing = model.load_all(config.cards_dir)
    taken = {c.uid for c in existing}

    units: list[ledger_mod.Unit] = []
    unit_ids: list[str] = list(args.unit or [])
    source_text = args.source or ""
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    for unit_id in unit_ids:
        source_name = unit_id.split(":", 1)[0]
        led = ledgers.get(source_name)
        found = led.get(unit_id) if led else None
        if found is None:
            print(f"no unit {unit_id!r} in {source_name}/units.jsonl", file=sys.stderr)
            return FAILED
        units.append(found)
    if units and not source_text:
        # One citation, from the first unit: the pieces of a split display are
        # the same equation, so citing each of them would just be noise.
        first = unit_ids[0].split(":", 1)[0]
        source_text = units[0].citation(config.source(first).citation)

    uid = model.mint_uid((unit_ids[0] if unit_ids else "") or args.front, taken)
    card = model.stub(
        uid=uid,
        front=args.front,
        back=args.back,
        source=source_text,
        unit=", ".join(unit_ids),
        card_type=args.type,
        tags=list(args.tag),
    )
    # Filed under the source it came from. This is filing only: `unit:` stays
    # the one place a card's source is recorded, because a directory and a
    # frontmatter field that both claim to say it will eventually disagree.
    # Every loader rglobs, so a card in the wrong folder still loads.
    folder = unit_ids[0].split(":", 1)[0] if unit_ids else ""
    path = config.cards_dir / folder / f"{uid}-{model.slugify(args.front)}.md"
    card.save(path)

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
    return bool(args.audience or args.kind or args.status)


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


def cmd_sync(args: argparse.Namespace, config: Config) -> int:
    from . import sync as sync_mod

    report = sync_mod.run(
        config,
        dry_run=args.dry_run,
        reposition_new=args.reposition,
        templates=args.templates,
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
    if args.source:
        # Layout is per source and `verify` refuses a source that declares
        # none, so "check this paper" is a question worth being able to ask
        # without the other books' skips burying the answer.
        cards = [c for c in cards if c.source_name == args.source]
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
