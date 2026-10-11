"""What a finished run says, for a person: a summary line and some blocks.

Each command prints its result as JSON, and each shape is different: a
list of findings, a push report, a list of units. Drawing that as one
generic table answers "what came back" and not "how did it go". So each
command gets a function here that reads its own shape and says three
things: one line of summary, a tone (`ok`, `warn`, `bad`), and the blocks
worth looking at, most important first.

**A command that changes something says the change and the state after.**
"3 new" alone does not say whether the source now has three units or three
hundred, and "140 in the ledger" alone does not say whether this run did
anything. So a writer's view opens with two rows of counts, titled `this
run` and `now`; a command that only reads has one, the state.

The page draws blocks and knows nothing about commands. Four kinds:

- `stats`: a row of counts, `{"label", "value", "tone"}` each.
- `table`: `title`, `columns` as `[key, label]` pairs, `rows` as dicts,
  and `more` for rows left out.
- `lines`: `title` and `items`, a list of strings.
- `data`: anything else, drawn by the page's generic renderer.

A command with no function here gets the `data` block, which is what every
run looked like before this module existed. A function that trips over a
shape it did not expect falls back the same way, so a run never loses its
result to the code that describes it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import PurePath
from typing import Any

#: Rows a table shows before saying how many it left out. The raw output
#: is still there for the rest.
ROWS = 200

View = dict[str, Any]


def describe(verb: str, data: Any, ok: bool, said: str = "") -> View:
    """The summary, tone and blocks for one finished run."""
    if data is None:
        line = said.splitlines()[0] if said.strip() else ""
        return {
            "summary": line or ("done, nothing printed" if ok else "failed"),
            "tone": "ok" if ok else "bad",
            "blocks": [],
        }
    if isinstance(data, dict) and set(data) == {"text"}:
        text = [line for line in str(data["text"]).splitlines() if line.strip()]
        return {
            "summary": text[0] if text else ("done" if ok else "failed"),
            "tone": "ok" if ok else "bad",
            "blocks": [_lines("", text)],
        }
    shape = VIEWS.get(verb)
    if shape is not None:
        try:
            view = shape(data)
        except (KeyError, TypeError, ValueError, AttributeError):
            view = None
        if view is not None:
            if not ok and view["tone"] != "bad":
                view["tone"] = "bad"
            return view
    return {
        "summary": _count(data) if ok else "failed",
        "tone": "ok" if ok else "bad",
        "blocks": [{"kind": "data", "title": "", "data": data}],
    }


# -- blocks -------------------------------------------------------------------


def _stats(*items: tuple[str, Any, str], title: str = "") -> dict[str, Any]:
    return {
        "kind": "stats",
        "title": title,
        "items": [{"label": label, "value": value, "tone": tone} for label, value, tone in items],
    }


def _table(
    title: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]], tone: str = ""
) -> dict[str, Any]:
    return {
        "kind": "table",
        "title": title,
        "tone": tone,
        "columns": [list(c) for c in columns],
        "rows": rows[:ROWS],
        "more": max(0, len(rows) - ROWS),
    }


def _lines(title: str, items: list[str], tone: str = "") -> dict[str, Any]:
    return {"kind": "lines", "title": title, "tone": tone, "items": items}


def _plural(n: int, word: str, many: str = "") -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def _count(data: Any) -> str:
    if isinstance(data, list):
        return _plural(len(data), "row")
    return "done"


def _card(row: dict[str, Any]) -> str:
    """A card as a reader names it: its file, else its uid."""
    path = str(row.get("path") or "")
    return PurePath(path).name if path else str(row.get("uid") or "")


# -- one per command ----------------------------------------------------------


def _check(data: list[dict[str, Any]]) -> View:
    errors = [f for f in data if f.get("level") == "error"]
    warns = [f for f in data if f.get("level") != "error"]
    cards = {_card(f) for f in data if _card(f)}
    if not data:
        return {"summary": "clean: no findings", "tone": "ok", "blocks": []}
    columns = [("card", "card"), ("code", "check"), ("message", "what")]

    def rows(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"card": _card(f), "code": f.get("code"), "message": f.get("message")} for f in found
        ]

    blocks = [
        _stats(
            ("errors", len(errors), "bad" if errors else ""),
            ("warnings", len(warns), "warn" if warns else ""),
            ("cards", len(cards), ""),
        )
    ]
    if errors:
        blocks.append(_table("errors: these block anki push", columns, rows(errors), "bad"))
    if warns:
        blocks.append(_table("warnings", columns, rows(warns), "warn"))
    return {
        "summary": f"{_plural(len(errors), 'error')}, {_plural(len(warns), 'warning')}",
        "tone": "bad" if errors else "warn",
        "blocks": blocks,
    }


#: The order a push report is read in: what changed, then what did not.
ACTIONS = ("error", "add", "update", "relearn", "move", "setup", "skip", "unchanged")
CHANGES = ("add", "update", "relearn", "move", "setup")


def _push(data: dict[str, Any]) -> View:
    outcomes: list[dict[str, Any]] = list(data.get("outcomes", []))
    findings = [f for f in data.get("findings", []) if f.get("level") == "error"]
    warned = [f for f in data.get("findings", []) if f.get("level") != "error"]
    dry = bool(data.get("dry_run"))
    count = Counter(str(o.get("action")) for o in outcomes)
    tones = {"error": "bad", "skip": "warn", "add": "ok", "update": "ok"}
    changed_now = [a for a in ("add", "update", "relearn", "move", "setup", "error") if count[a]]
    # Every card Anki holds for this scope once the run is done: what was
    # added or updated, and what was there already and still matches.
    held = count["add"] + count["update"] + count["unchanged"]
    blocks: list[dict[str, Any]] = [
        _stats(
            *([(a, count[a], tones.get(a, "")) for a in changed_now] or [("nothing", 0, "")]),
            title="would change" if dry else "this run",
        ),
        _stats(
            ("in Anki" if not dry else "in Anki after", held, ""),
            ("unchanged", count["unchanged"], ""),
            ("not ready", count["skip"], "warn" if count["skip"] else ""),
            title="now",
        ),
    ]
    if findings:
        blocks.append(
            _table(
                "check errors: nothing was pushed",
                [("card", "card"), ("code", "check"), ("message", "what")],
                [
                    {"card": _card(f), "code": f.get("code"), "message": f.get("message")}
                    for f in findings
                ],
                "bad",
            )
        )
    columns = [("uid", "card"), ("gist", "gist"), ("detail", "what")]
    by = {a: [o for o in outcomes if o.get("action") == a] for a in ACTIONS}
    if by["error"]:
        blocks.append(_table("errors", columns, by["error"], "bad"))
    changed = [o for a in CHANGES for o in by[a]]
    if changed:
        blocks.append(
            _table(
                "would change" if dry else "changed",
                [("action", ""), *columns],
                changed,
            )
        )
    if by["skip"]:
        blocks.append(_table("skipped", columns, by["skip"], "warn"))
    if warned:
        blocks.append(
            _table(
                "check warnings: these do not block a push",
                [("card", "card"), ("code", "check"), ("message", "what")],
                [
                    {"card": _card(f), "code": f.get("code"), "message": f.get("message")}
                    for f in warned
                ],
                "warn",
            )
        )

    moved = [f"{count[a]} {a}" for a in ("add", "update", "relearn", "move") if count[a]]
    if findings:
        summary = f"refused: {_plural(len(findings), 'check error')}"
    elif moved:
        summary = ("would push: " if dry else "pushed: ") + ", ".join(moved)
    else:
        summary = "nothing to push"
    rest = [f"{count[a]} {a}" for a in ("unchanged", "skip", "error") if count[a]]
    if rest:
        summary += "; " + ", ".join(rest)
    tone = "bad" if findings or count["error"] else "warn" if count["skip"] else "ok"
    return {"summary": summary, "tone": tone, "blocks": blocks}


def _pull(data: dict[str, Any]) -> View:
    taken = list(data.get("imported", []))
    left = list(data.get("skipped", []))
    dry = bool(data.get("dry_run"))
    errors = [s for s in left if str(s.get("reason", "")).startswith("error")]
    blocks: list[dict[str, Any]] = [
        _stats(
            ("waiting" if dry else "taken", len(taken), "ok" if taken else ""),
            title="would take" if dry else "this run",
        ),
        _stats(("left in Anki", len(left), "warn" if left else ""), title="now"),
    ]
    if taken:
        blocks.append(
            _table(
                "comments and flags" + (" waiting" if dry else ", now @claude notes"),
                [("uid", "card"), ("kind", "from"), ("text", "what it says")],
                taken,
            )
        )
    if left:
        blocks.append(_table("left in Anki", [("ref", "card"), ("reason", "why")], left, "warn"))
    if not taken:
        summary = "nothing waiting in Anki"
    elif dry:
        summary = f"{_plural(len(taken), 'comment')} waiting in Anki"
    else:
        summary = f"{_plural(len(taken), 'comment')} taken from Anki"
    tone = "bad" if errors else "warn" if left else "ok"
    return {"summary": summary, "tone": tone, "blocks": blocks}


def _audit(data: list[dict[str, Any]]) -> View:
    findings = [{"project": r.get("source"), **f} for r in data for f in r.get("findings", [])]
    codes = Counter(str(f.get("code")) for f in findings)
    projects = [
        {
            "project": r.get("source"),
            "units": r.get("total"),
            "numbered": (
                f"{r.get('numbered')}/{r.get('expected')}"
                if r.get("expected")
                else r.get("numbered")
            ),
            "complete": "yes" if r.get("complete") else ("no" if r.get("expected") else "-"),
            "flagged": len(r.get("flagged", [])),
        }
        for r in data
    ]
    blocks: list[dict[str, Any]] = []
    if codes:
        blocks.append(_stats(*((code, n, "warn") for code, n in codes.most_common())))
    blocks.append(
        _table(
            "projects",
            [
                ("project", "project"),
                ("units", "units"),
                ("numbered", "numbered"),
                ("complete", "1..N"),
                ("flagged", "flagged"),
            ],
            projects,
        )
    )
    if findings:
        blocks.append(
            _table(
                "findings",
                [("project", "project"), ("code", "check"), ("unit", "unit"), ("message", "what")],
                findings,
                "warn",
            )
        )
    broken = [p for p in projects if p["complete"] == "no"]
    summary = (
        f"{_plural(len(findings), 'finding')} over {_plural(len(data), 'project')}"
        if findings
        else f"nothing flagged over {_plural(len(data), 'project')}"
    )
    tone = "bad" if broken else "warn" if findings else "ok"
    return {"summary": summary, "tone": tone, "blocks": blocks}


def _units(data: list[dict[str, Any]]) -> View:
    states = Counter(str(u.get("state", "new")) for u in data)
    rows = [
        {
            "id": u.get("id"),
            "state": u.get("state", "new"),
            "where": u.get("citation") or "",
            "gist": u.get("gist") or "",
            "read": u.get("transcription") or "",
            "notes": len(u.get("notes") or []) or "",
        }
        for u in data
    ]
    return {
        "summary": _plural(len(data), "unit")
        + (": " + ", ".join(f"{n} {s}" for s, n in states.most_common()) if states else ""),
        "tone": "ok",
        "blocks": [
            _stats(*((s, n, "") for s, n in states.most_common())),
            _table(
                "units",
                [
                    ("id", "unit"),
                    ("state", "state"),
                    ("where", "where"),
                    ("gist", "gist"),
                    ("read", "transcription"),
                    ("notes", "open notes"),
                ],
                rows,
            ),
        ],
    }


def _extract(data: list[dict[str, Any]]) -> View:
    found = sum(int(r.get("found", 0)) for r in data)
    added = sum(int(r.get("added", 0)) for r in data)
    refreshed = sum(int(r.get("refreshed", 0)) for r in data)
    warnings = [f"{r.get('project')}: {w}" for r in data for w in r.get("warnings", [])]
    rows = [
        {
            "project": r.get("project"),
            "mode": r.get("mode"),
            "found": r.get("found"),
            "added": r.get("added"),
            "refreshed": r.get("refreshed"),
            "total": r.get("total"),
            "transcription": ", ".join(
                f"{n} {state}" for state, n in sorted(dict(r.get("transcription", {})).items())
            ),
            "text": f"{int(r.get('text_chars') or 0):,} chars" if r.get("text_chars") else "none",
        }
        for r in data
    ]
    total = sum(int(r.get("total", 0)) for r in data)
    blocks = [
        _stats(
            ("found", found, ""),
            ("new", added, "ok" if added else ""),
            ("refreshed", refreshed, ""),
            title="this run",
        ),
        _stats(("units in the ledger", total, ""), title="now"),
        _table(
            "projects",
            [
                ("project", "project"),
                ("mode", "from"),
                ("found", "found"),
                ("added", "new"),
                ("refreshed", "refreshed"),
                ("total", "in the ledger"),
                ("transcription", "transcription"),
                ("text", "text layer cached"),
            ],
            rows,
        ),
    ]
    if warnings:
        blocks.append(_lines("warnings", warnings, "warn"))
    return {
        "summary": f"{added} new, {refreshed} refreshed; {_plural(total, 'unit')} in the ledger",
        "tone": "warn" if warnings else "ok",
        "blocks": blocks,
    }


def _classify(data: list[dict[str, Any]]) -> View:
    proposed = [{"project": r.get("source"), **c} for r in data for c in r.get("classified", [])]
    considered = sum(int(r.get("considered", 0)) for r in data)
    dry = any(r.get("dry_run") for r in data)
    blocks: list[dict[str, Any]] = [
        _stats(
            ("proposed skips", len(proposed), "warn" if proposed else ""),
            title="this run" if not dry else "would propose",
        ),
        _stats(("units considered", considered, ""), title="now"),
    ]
    if proposed:
        blocks.append(
            _table(
                "proposed skips"
                + (" (dry run, nothing recorded)" if dry else ", waiting in triage"),
                [("unit_id", "unit"), ("reason", "reason"), ("detail", "why")],
                proposed,
            )
        )
    return {
        "summary": f"{_plural(len(proposed), 'skip')} proposed of {considered} considered",
        "tone": "ok",
        "blocks": blocks,
    }


def _sources(data: list[dict[str, Any]]) -> View:
    def kind(row: dict[str, Any]) -> str:
        if row.get("authoritative"):
            return "extracted"
        return "extraction off" if row.get("document") else "reference"

    rows = [
        {
            "title": r.get("title"),
            "project": r.get("project"),
            "kind": kind(r),
            "where": r.get("url") or r.get("zotero") or ", ".join(r.get("files", [])),
            "note": r.get("note") or "",
        }
        for r in data
    ]
    kinds = Counter(str(row["kind"]) for row in rows)
    projects = {row["project"] for row in rows}
    return {
        "summary": f"{_plural(len(rows), 'source')} in {_plural(len(projects), 'project')}",
        "tone": "ok",
        "blocks": [
            _stats(*((k, n, "") for k, n in kinds.most_common())),
            _table(
                "sources",
                [
                    ("title", "title"),
                    ("project", "project"),
                    ("kind", "kind"),
                    ("where", "where"),
                    ("note", "what it is for"),
                ],
                rows,
            ),
        ],
    }


def _zotero(data: list[dict[str, Any]]) -> View:
    rows = [
        {
            "citation": r.get("citation"),
            "title": r.get("title"),
            "item": r.get("item"),
            "source": r.get("source") or "not yet",
        }
        for r in data
    ]
    known = sum(1 for r in data if r.get("source"))
    return {
        "summary": f"{_plural(len(rows), 'item')} tagged, {known} already a source",
        "tone": "ok",
        "blocks": [
            _stats(
                ("tagged", len(rows), ""),
                ("already a source", known, ""),
                ("new", len(rows) - known, "ok" if len(rows) > known else ""),
            ),
            _table(
                "items",
                [
                    ("citation", "citation"),
                    ("title", "title"),
                    ("item", "item key"),
                    ("source", "project"),
                ],
                rows,
            ),
        ],
    }


def _size(value: Any) -> int:
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _attachments(raw: Any) -> str:
    """`2 of 3`, with the ones left out named."""
    if not isinstance(raw, list) or not raw:
        return ""
    read = [a for a in raw if isinstance(a, dict) and a.get("read")]
    left = [
        str(a.get("title") or a.get("key"))
        for a in raw
        if isinstance(a, dict) and not a.get("read")
    ]
    return f"{len(read)} of {len(raw)}" + (f" (not {', '.join(left)})" if left else "")


def _zotero_import(data: list[dict[str, Any]]) -> View:
    rows = [
        {
            "citation": r.get("citation") or r.get("item"),
            "project": r.get("source"),
            "marks": _size(r.get("marks")),
            "added": r.get("added", ""),
            "refreshed": r.get("refreshed", ""),
            "dropped": r.get("dropped") or "",
            "in_ledger": r.get("in_ledger", _size(r.get("units"))),
            "read": _attachments(r.get("attachments")),
            "note": "; ".join(
                part
                for part in (
                    (
                        f"{r['refused']}: would have made {_size(r.get('would_make'))}"
                        if r.get("refused")
                        else ""
                    ),
                    (
                        f"{_size(r.get('unmapped'))} marks with no meaning"
                        if _size(r.get("unmapped"))
                        else ""
                    ),
                    f"{_size(r.get('skipped'))} skipped" if _size(r.get("skipped")) else "",
                )
                if part
            ),
        }
        for r in data
    ]
    added = sum(int(r.get("added") or 0) for r in data)
    refreshed = sum(int(r.get("refreshed") or 0) for r in data)
    dropped = sum(int(r.get("dropped") or 0) for r in data)
    held = sum(int(row["in_ledger"] or 0) for row in rows)
    # One count per project, not per item: two items in one project report
    # the same project total.
    projects = {str(r.get("source")): int(r.get("project_units") or 0) for r in data}
    refused = [row for row, raw in zip(rows, data, strict=True) if raw.get("refused")]
    return {
        "summary": f"{added} new, {refreshed} refreshed; "
        f"{_plural(held, 'unit')} from {_plural(len(rows), 'item')} in the ledger",
        "tone": "warn" if refused else "ok",
        "blocks": [
            _stats(
                ("new", added, "ok" if added else ""),
                ("refreshed", refreshed, ""),
                ("dropped", dropped, "warn" if dropped else ""),
                ("refused", len(refused), "warn" if refused else ""),
                title="this run",
            ),
            _stats(
                ("units from these items", held, ""),
                *((f"in {name}", total, "") for name, total in sorted(projects.items()) if total),
                title="now",
            ),
            _table(
                "items",
                [
                    ("citation", "item"),
                    ("project", "project"),
                    ("marks", "marks"),
                    ("added", "new"),
                    ("refreshed", "refreshed"),
                    ("dropped", "dropped"),
                    ("in_ledger", "in the ledger"),
                    ("read", "attachments read"),
                    ("note", ""),
                ],
                rows,
            ),
        ],
    }


def _sources_update(data: dict[str, Any]) -> View:
    """`sources update`: the import and the segmenter, one view each, under
    one summary."""
    zotero = _zotero_import(list(data.get("zotero", []))) if data.get("zotero") else None
    extract = _extract(list(data.get("extract", []))) if data.get("extract") else None
    said = [str(line) for line in data.get("said", [])]
    parts = [v["summary"] for v in (zotero, extract) if v]
    blocks: list[dict[str, Any]] = []
    for name, view in (("Zotero items", zotero), ("files", extract)):
        if view:
            blocks.append(_lines(name, [view["summary"]]))
            blocks += view["blocks"]
    if said:
        blocks.insert(0, _lines("said", said, "warn"))
    return {
        "summary": "; ".join(parts) or "nothing to re-read",
        "tone": "warn" if said else "ok",
        "blocks": blocks,
    }


def _verify(data: list[dict[str, Any]]) -> View:
    status = Counter(str(r.get("status")) for r in data)
    wrong = [r for r in data if r.get("status") in ("fail", "error")]
    blocks: list[dict[str, Any]] = [
        _stats(
            ("pass", status["pass"], "ok" if status["pass"] else ""),
            ("fail", status["fail"], "bad" if status["fail"] else ""),
            ("error", status["error"], "bad" if status["error"] else ""),
            ("skip", status["skip"], ""),
        )
    ]
    if wrong:
        blocks.append(
            _table(
                "failed",
                [("uid", "card"), ("status", ""), ("detail", "what"), ("worst", "worst")],
                wrong,
                "bad",
            )
        )
    why = Counter(
        str(r.get("detail") or "no reason given") for r in data if r.get("status") == "skip"
    )
    if why:
        blocks.append(
            _lines("skipped, by reason", [f"{n}  {reason}" for reason, n in why.most_common()])
        )
    return {
        "summary": ", ".join(f"{status[s]} {s}" for s in ("pass", "fail", "error", "skip")),
        "tone": "bad" if wrong else "ok",
        "blocks": blocks,
    }


def _todo(data: list[dict[str, Any]]) -> View:
    who = Counter(str(r.get("audience")) for r in data)
    rows = [
        {
            "audience": "@" + str(r.get("audience")),
            "kind": r.get("kind"),
            "ref": r.get("ref"),
            "where": r.get("status") or r.get("where"),
            "note": r.get("note"),
        }
        for r in data
    ]
    return {
        "summary": f"{_plural(len(data), 'open annotation')}: "
        f"{who['claude']} @claude, {who['me']} @me",
        "tone": "warn" if data else "ok",
        "blocks": [
            _stats(("@claude", who["claude"], ""), ("@me", who["me"], "")),
            _table(
                "open",
                [
                    ("audience", ""),
                    ("kind", ""),
                    ("ref", "on"),
                    ("where", "state"),
                    ("note", "what"),
                ],
                rows,
            ),
        ],
    }


def _cards(data: list[dict[str, Any]]) -> View:
    states = Counter(str(c.get("status")) for c in data)
    return {
        "summary": _plural(len(data), "card")
        + (": " + ", ".join(f"{n} {s}" for s, n in states.most_common()) if states else ""),
        "tone": "ok",
        "blocks": [
            _stats(*((s, n, "") for s, n in states.most_common())),
            _table(
                "cards",
                [
                    ("uid", "card"),
                    ("status", "status"),
                    ("type", "type"),
                    ("project", "project"),
                    ("gist", "gist"),
                ],
                list(data),
            ),
        ],
    }


VIEWS: dict[str, Callable[[Any], View]] = {
    "check": _check,
    "anki": _push,
    "anki push": _push,
    "sync": _push,
    "anki pull": _pull,
    "feedback": _pull,
    "audit": _audit,
    "units": _units,
    "units extract": _extract,
    "extract": _extract,
    "units classify": _classify,
    "classify": _classify,
    "sources": _sources,
    "zotero": _zotero,
    "zotero import": _zotero_import,
    "sources update": _sources_update,
    "verify": _verify,
    "todo": _todo,
    "cards": _cards,
}


def verb_of(argv: list[str], names: set[str] | dict[str, str]) -> str:
    """The command an argv names, by the words typed: two if the parser
    has that pair, else one. The same rule `jobs.argv_for` settles arity
    by."""
    two = " ".join(argv[:2])
    return two if two in names else (argv[0] if argv else "")
