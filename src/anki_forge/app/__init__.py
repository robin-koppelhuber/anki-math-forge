"""`serve` -- the companion app (DESIGN.md §6).

Two views over the same files: units triage and card review, with annotations
available from both.

**The app holds no state.** Every request re-reads from disk, nothing is
cached, and every write compares mtime against load time and refuses if the
file changed underneath. You will have an editor open alongside this, and
silent clobbering is worse than an occasional retry.

Everything the app does is also doable by editing a file. An annotation
written in the browser lands in `## notes` byte-identical to one typed by
hand -- the app is one entry point, not the entry point.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .. import check, latex, model
from ..config import Config
from ..ledger import Ledger, Unit, open_ledgers
from ..model import Card, StaleFileError

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"
CDN_KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"


def render_body(body: str) -> Markup:
    """Card text as HTML, with fenced code blocks kept out of KaTeX's way.

    A `## verify` block is Python between triple backticks. Rendered as plain
    text it showed the fences literally and KaTeX tried to read the maths-like
    parts of the code. `<pre>` is right here for the same reason it was wrong
    for notes: KaTeX skips it by default.
    """
    out: list[str] = []
    for i, chunk in enumerate(body.split("```")):
        if i % 2 == 0:
            out.append(escape(chunk))
            continue
        # a fence may name its language on the first line
        first, _, rest = chunk.partition("\n")
        code = rest if first.strip().isalpha() and rest else chunk
        out.append(f"<pre class='code'>{escape(code.strip())}</pre>")
    # Markup, not str: the filter escapes its own input, so returning a plain
    # string would have Jinja escape the tags too and show them as text.
    return Markup("".join(out))


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="anki-forge", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES))
    templates.env.filters["body"] = render_body
    app.state.config = config

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    # Serve KaTeX from node_modules when it is there. The CDN default fails
    # silently when it is unreachable -- `renderMathInElement` is simply
    # undefined, nothing throws, and every card shows raw `$...$` as if the
    # LaTeX were wrong. `npm install katex` is already required for `check`,
    # so the files are usually present; use them.
    katex_base = config.katex_base
    local_katex = config.root / "node_modules" / "katex" / "dist"
    if not katex_base and local_katex.is_dir():
        app.mount("/katex", StaticFiles(directory=str(local_katex)), name="katex")
        katex_base = "/katex"
    elif not katex_base:
        katex_base = CDN_KATEX
    templates.env.globals["katex_base"] = katex_base
    templates.env.globals["filter_url"] = filter_url

    # -- views ------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/review")

    @app.get("/units", response_class=HTMLResponse)
    def units_view(
        request: Request,
        source: str = "",
        state: str = "new",
        section: str = "",
        transcribed: bool = False,
        readable: bool = False,  # the old name for the same filter; kept for links
        suggested: bool = False,
        annotated: str = "",
        counts_scope: str = "",
    ) -> Any:
        ledgers = _ledgers(config)
        if not ledgers:
            return templates.TemplateResponse(
                request,
                "empty.html",
                {
                    "what": "units",
                    "hint": "run `anki-forge extract`",
                    "view": "units",
                    "config": config,
                    "source": resolve_source(config, source),
                    "sources": source_names(config),
                    "pipeline": pipeline_counts(config),
                },
            )
        name = resolve_source(config, source)
        if name not in ledgers:
            name = next(iter(ledgers))
        ledger = ledgers[name]
        # The section rows must show what clicking one would give, so they
        # are counted over everything the *other* filters leave -- the same
        # population, minus the section filter itself.
        unsectioned = ledger.select(state=state or "all", section=None)
        units = ledger.select(state=state or "all", section=section or None)
        if suggested:
            unsectioned = [u for u in unsectioned if u.suggestion is not None]
        if annotated:
            unsectioned = [u for u in unsectioned if has_annotation(u.notes, annotated)]
        if transcribed or readable:
            unsectioned = [u for u in unsectioned if u.transcription == "ok"]
        if suggested:
            units = [u for u in units if u.suggestion is not None]
        if annotated:
            units = [u for u in units if has_annotation(u.notes, annotated)]
        transcribed = transcribed or readable
        if transcribed:
            # Triage is much faster when you can read the maths rather than
            # squint at a picture of it.
            units = [u for u in units if u.transcription == "ok"]
        filters = {
            "source": name,
            "state": state,
            "section": section,
            "annotated": annotated,
            "suggested": suggested,
            "transcribed": transcribed,
            "counts_scope": counts_scope,
        }
        return templates.TemplateResponse(
            request,
            "units.html",
            {
                "config": config,
                "source": name,
                "sources": source_names(config),
                "units": [_unit_payload(u, config) for u in units],
                "counts": ledger.counts(),
                "sections": ledger.sections(),
                "section_tree": section_rows(
                    list(ledger),
                    {u.id for u in unsectioned},
                    lambda u: u.locator.section,
                    lambda u: u.state,
                    lambda u: u.id,
                    UNIT_STATES,
                ),
                "transcribed_by_section": {
                    name: sum(
                        1
                        for u in ledger.select(state=state or "all", section=name)
                        if u.transcription == "ok"
                    )
                    for name in ledger.sections()
                },
                "state": state,
                "section": section,
                "pipeline": pipeline_counts(config, name),
                "transcribed": transcribed,
                "annotated": annotated,
                "suggested": suggested,
                "counts_scope": counts_scope,
                "filters": filters,
                "fsm_counts": (
                    scoped_counts(config, name, filters)
                    if counts_scope == "filtered"
                    else pipeline_counts(config, name)
                ),
                "suggested_count": sum(
                    1
                    for u in ledger.select(state=state or "all", section=section or None)
                    if u.suggestion is not None
                ),
                "transcribed_count": sum(
                    1
                    for u in ledger.select(state=state or "all", section=section or None)
                    if u.transcription == "ok"
                ),
                "mtime": _mtime(ledger.path),
            },
        )

    @app.get("/review", response_class=HTMLResponse)
    def review_view(
        request: Request,
        status: str = "draft",
        source: str = "",
        annotated: str = "",
        section: str = "",
        counts_scope: str = "",
    ) -> Any:
        name = resolve_source(config, source)
        cards, findings = check.check_repo(config)
        # The emptiness test is against the repo, before any filter. A filter
        # that matches nothing is a filter that matches nothing; the deck is
        # not empty and telling you to go extract more cards is a lie.
        if not cards:
            return templates.TemplateResponse(
                request,
                "empty.html",
                {
                    "what": "cards",
                    "hint": ("queue some units in the units view, then run `/extract-cards`"),
                    "view": "review",
                    "config": config,
                    "source": name,
                    "sources": source_names(config),
                    "pipeline": pipeline_counts(config),
                },
            )
        in_source = [c for c in cards if card_in_source(c, name)]
        cards = in_source
        if section:
            cards = [c for c in cards if c.section_name == section]
        if annotated:
            cards = [c for c in cards if has_annotation(c.annotations(), annotated)]
        # Everything the other filters leave, ignoring the section: what each
        # section row would show if you clicked it.
        unsectioned = in_source
        if annotated:
            unsectioned = [c for c in unsectioned if has_annotation(c.annotations(), annotated)]
        if status not in ("all", ""):
            unsectioned = [c for c in unsectioned if c.effective_status == status]
        selected = [c for c in cards if status in ("all", "") or c.effective_status == status]
        filters = {
            "source": name,
            "status": status,
            "section": section,
            "annotated": annotated,
            "counts_scope": counts_scope,
        }
        counts = {s: sum(1 for c in cards if c.effective_status == s) for s in model.STATUSES}
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "config": config,
                "cards": [_card_payload(c, findings, config) for c in selected],
                "counts": counts,
                "pipeline": pipeline_counts(config, name),
                "total": len(cards),
                "status": status,
                "source": name,
                "sources": source_names(config),
                "annotated": annotated,
                "section": section,
                "filters": filters,
                "section_tree": section_rows(
                    in_source,
                    {c.uid for c in unsectioned},
                    lambda c: c.section_name,
                    lambda c: c.effective_status,
                    lambda c: c.uid,
                    CARD_STATES,
                ),
                "counts_scope": counts_scope,
                "fsm_counts": (
                    scoped_counts(config, name, filters)
                    if counts_scope == "filtered"
                    else pipeline_counts(config, name)
                ),
            },
        )

    @app.get("/api/counts")
    def counts(
        source: str = "",
        section: str = "",
        status: str = "",
        state: str = "",
        annotated: str = "",
        suggested: bool = False,
        transcribed: bool = False,
        counts_scope: str = "",
    ) -> Any:
        """The pipeline counts, so the rail can follow a decision.

        Every mutating route returns these too; this exists for the first
        paint after an in-page navigation, when nothing has been decided yet.
        """
        name = resolve_source(config, source)
        whole = pipeline_counts(config, name)
        if counts_scope != "filtered":
            return {"pipeline": whole, "fsm": whole}
        return {
            "pipeline": whole,
            "fsm": scoped_counts(
                config,
                name,
                {
                    "section": section,
                    "status": status,
                    "state": state,
                    "annotated": annotated,
                    "suggested": suggested,
                    "transcribed": transcribed,
                },
            ),
        }

    # -- unit actions -----------------------------------------------------

    @app.post("/api/units/{source}/{unit_id:path}/state")
    def set_unit_state(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        def act(ledger: Ledger) -> Unit:
            return ledger.set_state(
                unit_id, str(body.get("state", "")), reason=str(body.get("reason", "")).strip()
            )

        return _mutate_ledger(config, source, body, act, unit_id)

    @app.post("/api/units/{source}/{unit_id:path}/accept")
    def accept_suggestion(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """Act on a proposed decision. The human is the one who decides."""
        return _mutate_ledger(config, source, body, lambda led: led.accept(unit_id), unit_id)

    @app.post("/api/units/{source}/{unit_id:path}/dismiss")
    def dismiss_suggestion(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        return _mutate_ledger(config, source, body, lambda led: led.dismiss(unit_id), unit_id)

    @app.post("/api/units/{source}/{unit_id:path}/restore")
    def restore_unit(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """Undo: put a unit back exactly as it was before the last action."""
        snapshot = body.get("snapshot") or {}

        def act(ledger: Ledger) -> Unit:
            return ledger.restore(unit_id, dict(snapshot))

        return _mutate_ledger(config, source, body, act, unit_id)

    @app.post("/api/units/{source}/{unit_id:path}/annotate")
    def annotate_unit(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "empty annotation")
        return _mutate_ledger(config, source, body, lambda led: led.annotate(unit_id, text))

    # -- card actions -----------------------------------------------------

    @app.post("/api/cards/{uid}/approve")
    def approve(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        return _mutate_card(config, uid, body, lambda card: card.approve())

    @app.post("/api/cards/{uid}/reject")
    def reject(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        return _mutate_card(config, uid, body, lambda card: card.reject())

    @app.post("/api/cards/{uid}/unapprove")
    def unapprove(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Send an approved card back to draft, deliberately.

        Editing one does this as a side effect (`content_hash` stops
        matching), but changing your mind is not an edit -- and reaching for
        the editor to make a token change would be a worse way to say so.
        """
        return _mutate_card(config, uid, body, lambda card: card.unapprove())

    @app.post("/api/cards/{uid}/restore")
    def restore_card(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Undo: put a card's status back, with the hash that went with it."""
        snapshot = body.get("snapshot") or {}
        status = str(snapshot.get("status", ""))
        if status not in model.STATUSES:
            raise HTTPException(400, f"unknown status {status!r}")

        def act(card: Card) -> None:
            card.frontmatter["status"] = status
            digest = str(snapshot.get("content_hash", ""))
            if digest:
                card.frontmatter["content_hash"] = digest
            else:
                card.frontmatter.pop("content_hash", None)

        return _mutate_card(config, uid, body, act)

    @app.post("/api/cards/{uid}/resolve")
    def resolve_card_annotation(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Delete one annotation. The app could add a note but never remove
        one, so the only way to finish with a `@me` decision was to open the
        file."""
        index = int(body.get("index", 0))
        return _mutate_card(config, uid, body, lambda card: card.resolve_annotation(index))

    @app.post("/api/cards/{uid}/annotate")
    def annotate_card(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "empty annotation")
        return _mutate_card(config, uid, body, lambda card: card.add_annotation(text))

    @app.get("/crop/{source}/{unit_id:path}.png")
    def crop(source: str, unit_id: str, context: float = 0.0, outline: bool = False) -> Response:
        """Render a unit's crop from the source document, on request.

        The ledger stores geometry, not pictures (DESIGN.md §4: the crop is
        the authority, but it is derived). About 4ms a crop, and it can never
        go stale against the bounding box it came from.
        """
        from ..extract import render as render_mod

        ledger_path = config.units_path(source)
        if not ledger_path.exists():
            raise HTTPException(404, f"no ledger for source {source!r}")
        unit = Ledger.load(ledger_path).get(unit_id)
        if unit is None:
            raise HTTPException(404, f"no unit {unit_id!r}")
        geometry = unit.crop_geometry()
        if geometry is None:
            raise HTTPException(404, f"unit {unit_id!r} has no page geometry")

        document = config.source(source).pdf
        if document is None or not document.exists():
            raise HTTPException(
                409,
                f"source document for {source!r} is not here "
                f"({document or 'unset'}); crops are rendered from it on demand",
            )
        try:
            png = render_mod.render_crop(document, *geometry, context=context, outline=outline)
        except (render_mod.PdfUnavailable, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/api/cards/{uid}/open")
    def open_in_editor(uid: str) -> Any:
        card = model.find(config.cards_dir, uid)
        if card is None or card.path is None:
            raise HTTPException(404, f"no card {uid}")
        return {"opened": launch_editor(card.path)}

    return app


# -- payloads --------------------------------------------------------------



def filter_url(path: str, filters: dict[str, Any], **changes: Any) -> str:
    """A link to `path` with the current filters, some of them changed.

    Every rail link used to hand-assemble its query string, and every one of
    them forgot a different parameter: picking a section dropped the `@me`
    filter, toggling `@me` dropped `suggested`. Composition is not something
    to remember at each call site.

    A change of `None` (or "" or False) removes that filter, which is how a
    toggle turns itself off.
    """
    merged: dict[str, Any] = {**filters, **changes}
    query = [
        (key, "1" if value is True else str(value))
        for key, value in merged.items()
        if value not in (None, "", False)
    ]
    return f"{path}?{urlencode(query)}" if query else path


UNIT_STATES = ("new", "queued", "carded", "skipped")
CARD_STATES = ("draft", "approved", "rejected")


def section_rows(
    everything: list[Any],
    shown: set[str],
    section_of: Any,
    state_of: Any,
    id_of: Any,
    states: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Sections grouped by chapter, with what is in each.

    Two numbers and a split. `matching` is **how many rows clicking this
    section would show**: it respects every other filter in force, which is
    the promise the rest of the rail makes. Without it the row read `0/16` on
    every section for ever, because it counted one hard-coded state (`new`
    units, `draft` cards) that nothing was in any more.

    `states` is the per-state split, because with four unit states and three
    card states one ratio cannot say where a section actually stands. `bar`
    is the same thing as widths, so it can be read without hovering.
    """
    by_section: dict[str, list[Any]] = {}
    for item in everything:
        by_section.setdefault(section_of(item) or "", []).append(item)

    chapters: dict[str, dict[str, Any]] = {}
    for name in sorted(by_section, key=_section_key):
        items = by_section[name]
        split = {state: sum(1 for i in items if state_of(i) == state) for state in states}
        row = {
            "name": name or "(none)",
            "total": len(items),
            "matching": sum(1 for i in items if id_of(i) in shown),
            "states": split,
            "bar": [
                {"state": state, "n": n, "pct": round(100 * n / len(items), 2)}
                for state, n in split.items()
                if n
            ],
        }
        chapter = (name or "?").split(".", 1)[0]
        group = chapters.setdefault(
            chapter, {"chapter": chapter, "sections": [], "total": 0, "matching": 0}
        )
        group["sections"].append(row)
        group["total"] += row["total"]
        group["matching"] += row["matching"]
    return list(chapters.values())


def _section_key(name: str) -> tuple[Any, ...]:
    """Sort `2.10` after `2.9`, and anything unnumbered last."""
    if not name:
        return (1,)
    parts: list[Any] = []
    for piece in name.split("."):
        parts.append(int(piece) if piece.isdigit() else piece)
    return (0, *parts)


def _note_text(note: str) -> str:
    """An annotation without its `@claude` / `@me` prefix.

    The view already says who a note is for, so repeating it on every line is
    noise. Slicing a fixed width would mangle a hand-edited note that does not
    carry the exact prefix, so strip only what is actually there.
    """
    audience = model.annotation_audience(note)
    if not audience:
        return note.strip()
    return note.strip()[len(audience) + 1 :].strip()


def pipeline_counts(
    config: Config,
    source: str = "",
    *,
    keep_unit: Any = None,
    keep_card: Any = None,
) -> dict[str, int]:
    """Where everything currently sits, across both halves of the pipeline.

    Units and cards are separate objects with separate gates, and that is the
    single most confusing thing about this tool -- `skipped` is a unit that
    will never be carded, `rejected` is a card that will never be synced, and
    nothing about the words says so. Counting them side by side, in order, is
    the cheapest way to make the shape visible.
    """
    counts = dict.fromkeys(
        ("new", "queued", "skipped", "carded", "draft", "approved", "rejected"), 0
    )
    # The two overlays. Not states -- they sit on top of one and change what
    # is allowed next -- but they are live and actionable, so they belong in
    # the strip beside the states rather than only in the diagram.
    counts["suggested"] = 0
    counts["annotated"] = 0
    # Split by audience, because they are different jobs. `claude` is work
    # waiting to be done; `me` is a decision only the human can take, and a
    # single "annotated" number hid which of the two you were looking at.
    counts["annotated_me"] = 0
    counts["annotated_claude"] = 0
    # ...and again per kind, because the rail row is a link to one view. The
    # repo-wide total said "@me 42" on the review page and then showed no
    # cards, since all 42 of them were on units.
    counts["annotated_me_unit"] = 0
    counts["annotated_claude_unit"] = 0
    counts["annotated_me_card"] = 0
    counts["annotated_claude_card"] = 0

    for name, ledger in open_ledgers(config.sources_dir).items():
        if source and name != source:
            continue
        if keep_unit is None:
            for state, number in ledger.counts().items():
                counts[state] += number
        for unit in ledger:
            if keep_unit is not None:
                if not keep_unit(unit):
                    continue
                counts[unit.state] += 1
            counts["suggested"] += unit.suggestion is not None
            counts["annotated"] += bool(unit.notes)
            counts["annotated_me"] += has_annotation(unit.notes, "me")
            counts["annotated_claude"] += has_annotation(unit.notes, "claude")
            counts["annotated_me_unit"] += has_annotation(unit.notes, "me")
            counts["annotated_claude_unit"] += has_annotation(unit.notes, "claude")
    for card in model.load_all(config.cards_dir):
        if not card_in_source(card, source):
            continue
        if keep_card is not None and not keep_card(card):
            continue
        counts[card.effective_status] = counts.get(card.effective_status, 0) + 1
        notes = card.annotations()
        counts["annotated"] += bool(notes)
        counts["annotated_me"] += has_annotation(notes, "me")
        counts["annotated_claude"] += has_annotation(notes, "claude")
        counts["annotated_me_card"] += has_annotation(notes, "me")
        counts["annotated_claude_card"] += has_annotation(notes, "claude")
    return counts


def scoped_counts(config: Config, source: str, filters: dict[str, Any]) -> dict[str, int]:
    """The pipeline, counted over what the filters leave.

    Both lanes are filtered, not just the one the current view edits. The
    shared filters -- section and annotation audience -- mean the same thing
    on either side of the pipeline, so a section chosen on the review page
    narrows the unit lane too. Anything else applies only to its own lane.

    One implementation, because the views and `/api/counts` have to agree:
    the diagram is repainted from the API after every action, so a difference
    would show up as the numbers changing when you press a key.
    """
    section = str(filters.get("section") or "")
    annotated = str(filters.get("annotated") or "")
    status = str(filters.get("status") or "")
    state = str(filters.get("state") or "")

    def keep_unit(unit: Unit) -> bool:
        if section and unit.locator.section != section:
            return False
        if state and state != "all" and unit.state != state:
            return False
        if filters.get("suggested") and unit.suggestion is None:
            return False
        if filters.get("transcribed") and unit.transcription != "ok":
            return False
        return not annotated or has_annotation(unit.notes, annotated)

    def keep_card(card: Card) -> bool:
        if section and card.section_name != section:
            return False
        if status and status != "all" and card.effective_status != status:
            return False
        return not annotated or has_annotation(card.annotations(), annotated)

    return pipeline_counts(config, source, keep_unit=keep_unit, keep_card=keep_card)


def has_annotation(notes: list[str], audience: str) -> bool:
    """Does any of these notes address `audience`? `any` means any of them."""
    if audience == "any":
        return any(model.annotation_audience(n) for n in notes)
    return any(model.annotation_audience(n) == audience for n in notes)


def card_in_source(card: Card, source: str) -> bool:
    """Does this card belong to the source the header is scoped to?

    An empty `source` means no scope, so everything belongs. A card whose
    units name no source belongs to all of them: it is misfiled, and the
    view that hides it is worse than the one that shows it twice.
    """
    return not source or card.source_name in ("", source)


def source_names(config: Config) -> list[str]:
    """Everything the dropdown may offer: configured sources and any ledger on
    disk, so a source extracted but not yet in the TOML (or the reverse) is
    still reachable.

    In TOML order, not alphabetical, because the first one is the default and
    that should be a choice you make by editing `anki-forge.toml` rather than
    an accident of spelling. Ledgers with no `[sources.*]` entry follow.
    """
    names = list(config.sources)
    names += sorted(set(open_ledgers(config.sources_dir)) - set(names))
    return names


def resolve_source(config: Config, source: str) -> str:
    """The source actually in force. An unknown or absent name falls back
    to the first, so a stale link lands somewhere real rather than on an
    empty deck."""
    names = source_names(config)
    if source in names:
        return source
    return names[0] if names else ""


def _ledgers(config: Config) -> dict[str, Ledger]:
    return open_ledgers(config.sources_dir)


def _mtime(path: Path) -> str:
    """Stringified so JavaScript cannot round a nanosecond timestamp."""
    return str(path.stat().st_mtime_ns) if path.exists() else "0"


def pdf_context() -> float:
    """How much surrounding page the triage view asks for."""
    from ..extract.render import TRIAGE_CONTEXT

    return TRIAGE_CONTEXT


def crop_url(unit: Unit, *, context: float = 0.0) -> str:
    """Where the app fetches this unit's crop, rendered on request.

    Triage asks for surrounding page and an outline; the review view wants the
    tight crop, because by then the question is "is this card right", not "did
    segmentation get this box right".
    """
    if not unit.has_crop:
        return ""
    url = f"/crop/{quote(unit.source)}/{quote(unit.id, safe='')}.png"
    return f"{url}?context={context:g}&outline=1" if context else url


def _unit_payload(unit: Unit, config: Config) -> dict[str, Any]:
    image = crop_url(unit, context=pdf_context())
    return {
        "id": unit.id,
        "state": unit.state,
        "reason": unit.reason,
        "image": image,
        "tex": unit.tex,
        "transcription": unit.transcription,
        "authoritative": unit.authoritative,
        "context": unit.context,
        "locator": unit.locator.label(),
        "section": unit.locator.section,
        # The view distinguishes "nothing proposed a skip" from "nothing was
        # allowed to": a numbered equation is off limits to the classifier.
        "equation": unit.locator.equation,
        "uids": unit.uids,
        "notes": unit.notes,
        # Split by audience. During triage most annotations are provenance
        # left for whoever writes the card -- "line 3 of 6, follows p67y189".
        # Useful there, noise here, so they collapse; anything addressed to
        # the human does not.
        "notes_mine": [_note_text(n) for n in unit.notes if model.annotation_audience(n) == "me"],
        "notes_claude": [
            _note_text(n) for n in unit.notes if model.annotation_audience(n) != "me"
        ],
        "suggestion": vars(unit.suggestion) if unit.suggestion else None,
    }


def _card_payload(card: Card, findings: list[check.Finding], config: Config) -> dict[str, Any]:
    mine = [f.as_dict() for f in check.findings_for(findings, card)]
    return {
        "uid": card.uid,
        "status": card.status,
        "source": card.source,
        "unit": card.unit,
        "tags": card.tags,
        "verify": card.verify_enabled,
        "path": str(card.path.relative_to(config.root)) if card.path else "",
        "mtime": str(card.mtime_ns or 0),
        "sections": [
            {"name": s.name, "body": s.body}
            for s in card.sections
            if s.name != "notes" and s.body.strip()
        ],
        "plain_notes": "\n".join(
            line
            for line in (card.section("notes") or "").splitlines()
            if not model.annotation_audience(line)
        ).strip(),
        "notes": card.section("notes") or "",
        "annotations": [
            {"text": _note_text(n), "audience": model.annotation_audience(n)}
            for n in card.annotations()
        ],
        "findings": mine,
        "errors": sum(1 for f in mine if f["level"] == check.ERROR),
        "unit_image": _unit_image(card, config),
        "front_length": latex.rendered_length(card.section("front") or ""),
    }


def _unit_image(card: Card, config: Config) -> str:
    """Link back to the originating unit's crop -- the fastest way to settle
    whether a card is wrong (DESIGN.md §6)."""
    if not card.unit:
        return ""
    source = card.unit.split(":", 1)[0]
    ledger_path = config.units_path(source)
    if not ledger_path.exists():
        return ""
    unit = Ledger.load(ledger_path).get(card.unit)
    return crop_url(unit) if unit else ""


# -- writes ----------------------------------------------------------------


def _mutate_card(config: Config, uid: str, body: dict[str, Any], action: Any) -> Any:
    card = model.find(config.cards_dir, uid)
    if card is None or card.path is None:
        raise HTTPException(404, f"no card {uid}")
    expected = _expected_mtime(body)
    # What undo needs: approving stamps `content_hash` and rejecting drops it,
    # so restoring the status alone would leave the card in a state it was
    # never actually in.
    before = {
        "status": card.status,
        "content_hash": card.frontmatter.get("content_hash", ""),
    }
    action(card)
    try:
        card.save(expect_mtime_ns=expected)
    except StaleFileError as exc:
        return JSONResponse({"error": str(exc), "stale": True}, status_code=409)
    _, findings = check.check_repo(config)
    return {
        "card": _card_payload(model.load(card.path), findings, config),
        "before": before,
        "pipeline": pipeline_counts(config),
    }


def _mutate_ledger(
    config: Config,
    source: str,
    body: dict[str, Any],
    action: Any,
    unit_id: str = "",
) -> Any:
    path = config.units_path(source)
    if not path.exists():
        raise HTTPException(404, f"no ledger for source {source!r}")
    expected = _expected_mtime(body)
    if expected is not None and path.stat().st_mtime_ns != expected:
        return JSONResponse(
            {"error": f"{path.name} changed on disk; reload and retry", "stale": True},
            status_code=409,
        )
    with Ledger.edit(path) as ledger:
        # Captured inside the lock, before the action, so undo restores what
        # was actually there rather than what the browser last happened to see.
        before = ledger.snapshot(unit_id) if unit_id else {}
        try:
            unit = action(ledger)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
    return {
        "unit": _unit_payload(unit, config),
        "mtime": _mtime(path),
        "before": before,
        # So the filter rail can follow the decision without a page load.
        "pipeline": pipeline_counts(config),
    }


def _expected_mtime(body: dict[str, Any]) -> int | None:
    raw = str(body.get("mtime", "")).strip()
    return int(raw) if raw.isdigit() and raw != "0" else None


def launch_editor(path: Path) -> str:
    """Open a card in $EDITOR (DESIGN.md §6: `e` from the review view)."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.Popen([*editor.split(), str(path)])
        return editor
    code = shutil.which("code")
    if code:
        subprocess.Popen([code, "-g", str(path)])
        return "code"
    if sys.platform == "win32":
        os.startfile(str(path))
        return "shell default"
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])
    return opener


def serve(config: Config, *, host: str | None = None, port: int | None = None) -> None:
    import uvicorn

    uvicorn.run(
        create_app(config),
        host=host or config.host,
        port=port or config.port,
        log_level="warning",
    )
