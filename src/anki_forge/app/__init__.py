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
        request: Request, source: str = "", state: str = "new", section: str = ""
    ) -> Any:
        ledgers = _ledgers(config)
        if not ledgers:
            return templates.TemplateResponse(
                request, "empty.html", {"what": "units", "hint": "run `anki-forge extract`"}
            )
        name = source if source in ledgers else next(iter(ledgers))
        ledger = ledgers[name]
        units = ledger.select(state=state or "all", section=section or None)
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
                "state": state,
                "section": section,
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
                {"what": "cards", "hint": "write one by hand, or run `/extract-cards`"},
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

        return _mutate_ledger(config, source, body, act)

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
        "uids": unit.uids,
        "notes": unit.notes,
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
    action(card)
    try:
        card.save(expect_mtime_ns=expected)
    except StaleFileError as exc:
        return JSONResponse({"error": str(exc), "stale": True}, status_code=409)
    _, findings = check.check_repo(config)
    return {"card": _card_payload(model.load(card.path), findings, config)}


def _mutate_ledger(config: Config, source: str, body: dict[str, Any], action: Any) -> Any:
    path = config.units_path(source)
    if not path.exists():
        raise HTTPException(404, f"no ledger for source {source!r}")
    expected = _expected_mtime(body)
    if expected is not None and path.stat().st_mtime_ns != expected:
        return JSONResponse(
            {"error": f"{path.name} changed on disk; reload and retry", "stale": True},
            status_code=409,
        )
    ledger = Ledger.load(path)
    try:
        unit = action(ledger)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    ledger.save()
    return {"unit": _unit_payload(unit, config), "mtime": _mtime(path)}


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
