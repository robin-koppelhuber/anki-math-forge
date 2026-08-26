"""`anki-forge` -- the command line (DESIGN.md §2).

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
from . import extract as extract_mod
from . import latex, model, todo, verify
from . import ledger as ledger_mod
from .anki import AnkiConnect, AnkiError
from .config import Config, ConfigError, load

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
    except BrokenPipeError:  # pragma: no cover - `anki-forge source-text | head`
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
    parser = argparse.ArgumentParser(prog="anki-forge", description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: nearest anki-forge.toml)")
    subs = parser.add_subparsers(dest="verb", required=True)

    p = subs.add_parser("extract", help="segment a source into units; never writes cards")
    p.add_argument("source", nargs="?", default=None)
    p.add_argument("--pages", default=None, help="page range, e.g. 10-40 (pdf sources)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_extract)

    p = subs.add_parser("serve", help="the companion app: units triage + card review")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.set_defaults(run=cmd_serve)

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
        "--resolve-notes",
        action="store_true",
        help="clear the @claude annotations on --id, once you have acted on them",
    )
    p.add_argument("--flagged", action="store_true", help="only units the audit is unsure about")
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
    p.add_argument("--out", required=True, help="directory to write PNGs into (working files)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_crops)

    p = subs.add_parser("audit", help="mechanical confidence checks over a ledger")
    p.add_argument("--source", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_audit)

    p = subs.add_parser("source-text", help="the cached text layer, for card-writing context")
    p.add_argument("source", nargs="?", default=None)
    p.set_defaults(run=cmd_source_text)

    p = subs.add_parser("new", help="scaffold a stub card from a queued unit")
    p.add_argument("--unit", default=None, help="unit id; the card is marked carded on success")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_todo)

    p = subs.add_parser("sync", help="push approved cards to Anki, upserting by uid")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_sync)

    p = subs.add_parser("verify", help="opt-in numeric check of identities")
    p.add_argument("--uid", default=None)
    p.add_argument("--trials", type=int, default=verify.TRIALS)
    p.add_argument("--json", action="store_true")
    p.set_defaults(run=cmd_verify)

    return parser


# -- verbs -----------------------------------------------------------------


def cmd_extract(args: argparse.Namespace, config: Config) -> int:
    names = [args.source] if args.source else sorted(config.sources)
    if not names:
        print("no sources configured in anki-forge.toml", file=sys.stderr)
        return MISUSE
    reports = []
    for name in names:
        report = extract_mod.run(config, name, pages=_page_range(args.pages))
        reports.append(report)
        if not args.json:
            print(report.summary())
            for warning in report.warnings:
                print(f"  warning: {warning}", file=sys.stderr)
    if args.json:
        print(json.dumps([_report_json(r) for r in reports], indent=2))
    return OK


def cmd_serve(args: argparse.Namespace, config: Config) -> int:
    from .app import serve

    host = args.host or config.host
    port = args.port or config.port
    print(f"anki-forge on http://{host}:{port}  (units triage + card review)")
    serve(config, host=host, port=port)
    return OK


def cmd_units(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `anki-forge extract`", file=sys.stderr)
        return FAILED

    if args.id and (args.set_state or args.annotate or args.tex_auto or args.resolve_notes):
        return _mutate_unit(args, ledgers, config)

    flagged: dict[str, set[str]] = {}
    if args.flagged:
        flagged = {name: audit_mod.audit(led, name).flagged for name, led in ledgers.items()}

    rows: list[dict[str, Any]] = []
    for name, led in ledgers.items():
        for unit in led.select(state=args.state, section=args.section):
            if args.flagged and unit.id not in flagged.get(name, set()):
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
        locator = ledger_mod.Locator(**row.get("locator", {})).label()
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
    for led in ledgers.values():
        if led.get(args.id) is None:
            continue
        if args.tex_auto is not None:
            state, stored = led.transcribe(
                args.id, args.tex_auto, latex.checker(config.extra_macros)
            )
            print(f"{args.id} transcription: {state}" + (f"  {stored[:80]}" if stored else ""))
            if state == "failed":
                print("  (did not parse under KaTeX; nothing stored)", file=sys.stderr)
        if args.resolve_notes:
            cleared = led.resolve_notes(args.id)
            print(f"{args.id}: {cleared} annotation(s) resolved")
        if args.set_state:
            unit = led.set_state(args.id, args.set_state, reason=args.reason)
            print(f"{unit.id} -> {unit.state}" + (f" ({unit.reason})" if unit.reason else ""))
        if args.annotate:
            led.annotate(args.id, args.annotate)
            print(f"{args.id} annotated")
        led.save()
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
        print("no units ledger yet; run `anki-forge extract`", file=sys.stderr)
        return FAILED

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []

    for name, led in ledgers.items():
        document = config.source(name).pdf
        if document is None or not document.exists():
            continue
        units = [
            u
            for u in led.select(state=args.state, section=args.section)
            if u.has_crop and (not args.untranscribed or u.transcription in ("none", "failed"))
        ]
        if args.limit:
            units = units[: args.limit]
        if not units:
            continue
        with render_mod.CropRenderer(document) as renderer:
            for unit in units:
                geometry = unit.crop_geometry()
                if geometry is None:
                    continue
                path = out / (re.sub(r"[^A-Za-z0-9._-]+", "_", unit.id) + ".png")
                path.write_bytes(renderer.render(*geometry))
                manifest.append(
                    {
                        "unit": unit.id,
                        "file": str(path),
                        "section": unit.locator.section,
                        "equation": unit.locator.equation,
                        "page": unit.locator.page,
                        "context": unit.context,
                    }
                )

    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    else:
        for entry in manifest:
            print(f"{entry['unit']:<34} {entry['file']}")
        print(f"\n{len(manifest)} crops written to {out}")
    return OK


def cmd_audit(args: argparse.Namespace, config: Config) -> int:
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.source:
        ledgers = {k: v for k, v in ledgers.items() if k == args.source}
    if not ledgers:
        print("no units ledger yet; run `anki-forge extract`", file=sys.stderr)
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
            print(f"no cached text for {name!r}; run `anki-forge extract`", file=sys.stderr)
            return FAILED
        print(path.read_text(encoding="utf-8"))
    return OK


def cmd_new(args: argparse.Namespace, config: Config) -> int:
    existing = model.load_all(config.cards_dir)
    taken = {c.uid for c in existing}

    unit = None
    source_text = args.source or ""
    ledgers = ledger_mod.open_ledgers(config.sources_dir)
    if args.unit:
        source_name = args.unit.split(":", 1)[0]
        led = ledgers.get(source_name)
        unit = led.get(args.unit) if led else None
        if unit is None:
            print(f"no unit {args.unit!r} in {source_name}/units.jsonl", file=sys.stderr)
            return FAILED
        if not source_text:
            source_text = unit.citation(config.source(source_name).citation)

    uid = model.mint_uid(args.unit or args.front, taken)
    card = model.stub(
        uid=uid,
        front=args.front,
        back=args.back,
        source=source_text,
        unit=args.unit or "",
        card_type=args.type,
        tags=list(args.tag),
    )
    path = config.cards_dir / f"{uid}-{model.slugify(args.front)}.md"
    card.save(path)

    if args.unit and unit is not None:
        led = ledgers[args.unit.split(":", 1)[0]]
        led.mark_carded(args.unit, [uid])
        led.save()

    findings = check_mod.check_card(card, config)
    if args.json:
        print(
            json.dumps(
                {
                    "uid": uid,
                    "path": str(path.relative_to(config.root)),
                    "unit": args.unit or "",
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
    if args.json:
        print(json.dumps([i.as_dict() for i in items], indent=2, ensure_ascii=False))
        return OK
    if not items:
        print("no open annotations")
        return OK
    for item in items:
        print(item.format())
    print(f"\n{len(items)} open annotation(s)")
    return OK


def cmd_sync(args: argparse.Namespace, config: Config) -> int:
    from . import sync as sync_mod

    report = sync_mod.run(config, dry_run=args.dry_run)
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
