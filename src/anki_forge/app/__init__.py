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
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import check, latex, model
from ..config import Config
from ..ledger import Ledger, Unit, open_ledgers
from ..model import Card, StaleFileError

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="anki-forge", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES))
    app.state.config = config

    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

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
                    "pipeline": pipeline_counts(config),
                },
            )
        name = source if source in ledgers else next(iter(ledgers))
        ledger = ledgers[name]
        units = ledger.select(state=state or "all", section=section or None)
        if suggested:
            units = [u for u in units if u.suggestion is not None]
        transcribed = transcribed or readable
        if transcribed:
            # Triage is much faster when you can read the maths rather than
            # squint at a picture of it.
            units = [u for u in units if u.transcription == "ok"]
        return templates.TemplateResponse(
            request,
            "units.html",
            {
                "config": config,
                "source": name,
                "sources": sorted(ledgers),
                "units": [_unit_payload(u, config) for u in units],
                "counts": ledger.counts(),
                "sections": ledger.sections(),
                "section_tree": section_tree(ledger),
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
                "pipeline": pipeline_counts(config),
                "transcribed": transcribed,
                "suggested": suggested,
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
    def review_view(request: Request, status: str = "draft") -> Any:
        cards, findings = check.check_repo(config)
        if not cards:
            return templates.TemplateResponse(
                request,
                "empty.html",
                {
                    "what": "cards",
                    "hint": ("queue some units in the units view, then run `/extract-cards`"),
                    "view": "review",
                    "config": config,
                    "pipeline": pipeline_counts(config),
                },
            )
        selected = [c for c in cards if status in ("all", "") or c.effective_status == status]
        counts = {s: sum(1 for c in cards if c.effective_status == s) for s in model.STATUSES}
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "config": config,
                "cards": [_card_payload(c, findings, config) for c in selected],
                "counts": counts,
                "pipeline": pipeline_counts(config),
                "total": len(cards),
                "status": status,
            },
        )

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



def section_tree(ledger: Ledger) -> list[dict[str, Any]]:
    """Sections grouped by chapter, with what is in each.

    The filter rail's data. Sixty-four sections is too many for a flat list,
    and the thing you want to know before opening one is whether there is
    anything left to do in it -- so every row carries its own counts and the
    chapter carries their sum.
    """
    chapters: dict[str, dict[str, Any]] = {}
    for name in ledger.sections():
        units = list(ledger.select(state="all", section=name))
        row = {
            "name": name,
            "total": len(units),
            "transcribed": sum(1 for u in units if u.transcription == "ok"),
            "suggested": sum(1 for u in units if u.suggestion is not None),
            "annotated": sum(1 for u in units if u.notes),
            "undecided": sum(1 for u in units if u.state == "new"),
        }
        chapter = name.split(".", 1)[0]
        group = chapters.setdefault(
            chapter,
            {"chapter": chapter, "sections": [], "total": 0, "undecided": 0, "suggested": 0},
        )
        group["sections"].append(row)
        for key in ("total", "undecided", "suggested"):
            group[key] += row[key]
    return list(chapters.values())



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


def pipeline_counts(config: Config) -> dict[str, int]:
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

    for ledger in open_ledgers(config.sources_dir).values():
        for state, number in ledger.counts().items():
            counts[state] += number
        for unit in ledger:
            counts["suggested"] += unit.suggestion is not None
            counts["annotated"] += bool(unit.notes)
    for card in model.load_all(config.cards_dir):
        counts[card.effective_status] = counts.get(card.effective_status, 0) + 1
        counts["annotated"] += bool(card.annotations())
    return counts


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
        "notes": card.section("notes") or "",
        "annotations": card.annotations(),
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
