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
import time
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
from ..sync import in_study_order, source_positions

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
    app = FastAPI(title="forge", docs_url=None, redoc_url=None)
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

    @app.get("/api/config")
    def config_api(source: str = "") -> Any:
        """Every resolved setting, and where it came from. Read-only.

        A panel over the view you were on rather than a page of its own: it
        answers a question you have *while deciding something else* -- which
        layout did this card resolve to -- and a navigation away and back is a
        poor way to look something up mid-decision.

        The source in force comes first. With fifty of them, landing at the top
        of an alphabetical list and scrolling is not an answer.
        """
        name = resolve_source(config, source)
        focus = f"source: {name}"
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in effective_config(config):
            where = str(row["where"])
            # The repo-wide settings and *this* source. The other fifty are a
            # different question -- which book to work on -- and the gallery
            # answers that one; listing them here buried the two groups you
            # opened the panel for.
            if where.startswith("source: ") and where != focus:
                continue
            grouped.setdefault(where, []).append(row)
        order = [focus, *(g for g in grouped if g != focus)]
        return {
            "source": name,
            "focus": focus,
            "groups": [
                {"where": where, "rows": grouped[where], "focused": where == focus}
                for where in order
                if where in grouped
            ],
        }

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
        mark: str = "",
        counts_scope: str = "",
    ) -> Any:
        ledgers = _ledgers(config)
        if not ledgers:
            return templates.TemplateResponse(
                request,
                "empty.html",
                {
                    "what": "units",
                    "hint": "run `forge extract`",
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
        if mark:
            unsectioned = [u for u in unsectioned if unit_mark(u) == mark]
        if suggested:
            units = [u for u in units if u.suggestion is not None]
        if annotated:
            units = [u for u in units if has_annotation(u.notes, annotated)]
        if mark:
            units = [u for u in units if unit_mark(u) == mark]
        transcribed = transcribed or readable
        if transcribed:
            # Triage is much faster when you can read the maths rather than
            # squint at a picture of it.
            units = [u for u in units if u.transcription == "ok"]
        everything = list(ledger)
        known = {u.id for u in everything}
        # Whether this source was read and marked up, or segmented. It decides
        # which passes are offered and how wide a crop is cut, and it is a
        # property of the units rather than a setting: a source is what it is.
        from_marks = any(u.marks for u in everything)
        pipeline = pipeline_counts(config, name)
        filters = {
            "source": name,
            "state": state,
            "section": section,
            "annotated": annotated,
            "suggested": suggested,
            "transcribed": transcribed,
            "mark": mark,
            "counts_scope": counts_scope,
        }
        return templates.TemplateResponse(
            request,
            "units.html",
            {
                "config": config,
                "source": name,
                "sources": source_names(config),
                "units": [_unit_payload(u, config, known) for u in units],
                "counts": ledger.counts(),
                "sections": ledger.sections(),
                "section_tree": section_rows(
                    everything,
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
                "pipeline": pipeline,
                "transcribed": transcribed,
                "annotated": annotated,
                "suggested": suggested,
                "counts_scope": counts_scope,
                "filters": filters,
                "commands": commands_for("units", filters, pipeline, from_marks=from_marks),
                "mark": mark,
                "mark_matrix": mark_matrix(
                    ledger.select(state=state or "all", section=section or None), config, name
                ),
                "scheme": scheme_legend(scheme_rows(everything, config, name)),
                "source_facts": source_facts(config, name, from_marks=from_marks),
                "fsm_counts": (
                    scoped_counts(config, name, filters)
                    if counts_scope == "filtered"
                    else pipeline
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
        everywhere = cards  # kept: the filters below rebind `cards`
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
        # A dependency may name a card in another source: `check` validates
        # `requires` against the whole repo, not one book. Linking it with the
        # *current* source would land on a card that is not there, and the
        # hash lookup would find nothing and say nothing.
        homes = {c.uid: c.source_name for c in everywhere}

        def link(uid: str) -> dict[str, Any]:
            known = uid in homes
            where = homes.get(uid) or name
            return {
                "uid": uid,
                "known": known,
                # `status=all` and no annotation filter, so following a link
                # never lands on a deck that excludes what you asked for.
                "href": filter_url("/review", {}, source=where, status="all") + f"#{uid}",
            }

        # One ordering for the whole source, so a card can say where it sits
        # and what put it there. The reverse edges are only computable here:
        # a card's file says what it needs, never what needs it.
        by_uid_card = {c.uid: c for c in in_source}
        ordered = in_study_order(in_source, source_positions(config))
        places: dict[str, dict[str, Any]] = {
            c.uid: {"position": i + 1, "total": len(ordered), "required_by": []}
            for i, c in enumerate(ordered)
        }
        for c in in_source:
            for need in c.requires:
                if need in places:
                    places[need]["required_by"].append(link(c.uid))
        for uid, place in places.items():
            place["requires"] = [link(n) for n in by_uid_card[uid].requires]

        selected = [c for c in cards if status in ("all", "") or c.effective_status == status]
        filters = {
            "source": name,
            "status": status,
            "section": section,
            "annotated": annotated,
            "counts_scope": counts_scope,
        }
        counts = {s: sum(1 for c in cards if c.effective_status == s) for s in model.STATUSES}
        pipeline = pipeline_counts(config, name)
        units_here = list(_ledgers(config).get(name, Ledger(config.units_path(name))))
        from_marks = any(u.marks for u in units_here)
        return templates.TemplateResponse(
            request,
            "review.html",
            {
                "config": config,
                "cards": [
                    _card_payload(c, findings, config, places.get(c.uid)) for c in selected
                ],
                "counts": counts,
                "pipeline": pipeline,
                "total": len(cards),
                "status": status,
                "source": name,
                "sources": source_names(config),
                "annotated": annotated,
                "section": section,
                "filters": filters,
                "commands": commands_for("review", filters, pipeline, from_marks=from_marks),
                "scheme": scheme_legend(scheme_rows(units_here, config, name)),
                "source_facts": source_facts(config, name, from_marks=from_marks),
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
                    else pipeline
                ),
            },
        )

    @app.get("/api/sources")
    def sources_api() -> Any:
        """Every source with its counts, for the picker.

        On demand rather than on every page, because it walks every ledger and
        every card. Nothing is cached: the picker is opened once in a while
        and being right matters more there than being instant.
        """
        return source_gallery(config)

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
            return {"pipeline": whole, "fsm": whole, "stale": code_is_newer_than_this_process()}
        return {
            "pipeline": whole,
            "stale": code_is_newer_than_this_process(),
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

    @app.post("/api/units/{source}/{unit_id:path}/answer")
    def answer_unit_note(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """Settle one annotation, keeping what settled it.

        Deleting the line throws away the question along with the answer, and
        the question is half of what made the decision worth recording. A
        `@me` note asking "same as 2.4?" resolved with "no" leaves
        `same as 2.4? — no` behind, unaddressed, so it is a record rather than
        new work.
        """
        index = int(body.get("index", -1))
        reply = str(body.get("answer", "")).strip()

        def act(led: Ledger) -> Unit:
            return led.answer(unit_id, index, reply)

        return _mutate_ledger(config, source, body, act, unit_id)

    @app.post("/api/units/{source}/{unit_id:path}/context")
    def set_unit_context(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """How much of the document a card writer gets for this unit.

        Set here rather than only in the config, because triage is the moment
        you can see it: the theorem is on this page and its hypotheses are two
        pages back, and no per-source default knows that.
        """
        raw = body.get("pages")
        pages = None if raw is None or int(raw) < 0 else int(raw)

        def apply(led: Ledger) -> Unit:
            unit = led.get(unit_id)
            if unit is None:
                raise HTTPException(404, f"no unit {unit_id!r}")
            unit.context_pages = pages
            return unit

        return _mutate_ledger(config, source, body, apply)

    @app.post("/api/units/{source}/{unit_id:path}/web")
    def set_unit_web(source: str, unit_id: str, body: dict[str, Any] = Body(...)) -> Any:
        """Whether whoever writes this card may look things up on the web.

        Three states, not two: yes, no, and "whatever the source says". The
        third is not the same as `no` -- it is the absence of a decision here,
        and collapsing the two would make a source-wide grant unrevokable per
        unit and a source-wide refusal impossible to lift.
        """
        raw = body.get("web")
        allow = None if raw is None else bool(raw)

        def apply(led: Ledger) -> Unit:
            unit = led.get(unit_id)
            if unit is None:
                raise HTTPException(404, f"no unit {unit_id!r}")
            unit.web = allow
            return unit

        return _mutate_ledger(config, source, body, apply)

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

    @app.post("/api/cards/{uid}/grade")
    def set_grade(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """`frequency` or `derivation`, cycled from the review view.

        Both are coarse judgements about *when* you should meet this card, and
        both were previously reachable only by opening the file -- which is
        also why so many cards carry neither. You learn that a result is
        `common` rather than `core` by meeting it, which is to say during
        review, which is here.

        An empty value takes the grading off again, so the cycle can pass
        through "unset" rather than trapping a card in a grade it was given by
        a mis-click.
        """
        key = str(body.get("key", ""))
        if key not in ("frequency", "derivation"):
            raise HTTPException(400, f"{key!r} is not a grading")
        value = str(body.get("value", ""))
        allowed = model.FREQUENCIES if key == "frequency" else model.DERIVATIONS
        if value and value not in allowed:
            raise HTTPException(400, f"{value!r} is not one of {', '.join(allowed)}")
        return _mutate_card(config, uid, body, lambda card: card.set_grade(key, value))

    @app.post("/api/cards/{uid}/web")
    def set_card_web(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Whether whoever augments this card may look things up on the web.

        Same three states as the unit's, and it goes through `set_grade`
        because it is unhashed for the same reason: a permission is not a
        claim the card makes, and granting one is not an edit to review.
        """
        raw = body.get("web")
        value = "" if raw is None else bool(raw)
        return _mutate_card(config, uid, body, lambda card: card.set_grade("web", value))

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
    def crop(
        source: str,
        unit_id: str,
        context: float = 0.0,
        outline: bool = False,
        width: str = "",
        marks: bool = True,
    ) -> Response:
        """Render a unit's crop from the source document, on request.

        The ledger stores geometry, not pictures (DESIGN.md §4: the crop is
        the authority, but it is derived). About 4ms a crop, and it can never
        go stale against the bounding box it came from.

        `width` overrides how wide it is cut; left empty the config decides,
        which is where the "a mark's box has no meaningful left edge" rule
        lives. `marks` paints what the reader marked back onto the page, in
        the colours they used.
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
        if width and width not in render_mod.WIDTHS:
            raise HTTPException(400, f"unknown crop width {width!r}")
        width = width or config.crop_width_for(source, from_a_mark=bool(unit.marks))
        regions = render_mod.regions_for(unit, geometry[0]) if marks else []

        document = config.document_for(source, unit.locator.document)
        if document is None or not document.exists():
            raise HTTPException(
                409,
                f"source document for {source!r} is not here "
                f"({document or 'unset'}); crops are rendered from it on demand",
            )
        try:
            png = render_mod.render_crop(
                document,
                *geometry,
                context=context,
                outline=outline,
                width=width,
                regions=regions,
            )
        except (render_mod.PdfUnavailable, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    def _unit_document(source: str, unit_id: str) -> tuple[Unit, Path]:
        """The unit and the file its geometry refers to, or an HTTP error."""
        ledger_path = config.units_path(source)
        if not ledger_path.exists():
            raise HTTPException(404, f"no ledger for source {source!r}")
        unit = Ledger.load(ledger_path).get(unit_id)
        if unit is None:
            raise HTTPException(404, f"no unit {unit_id!r}")
        document = config.document_for(source, unit.locator.document)
        if document is None or not document.exists():
            raise HTTPException(
                409,
                f"source document for {source!r} is not here "
                f"({document or 'unset'}); pages are rendered from it on demand",
            )
        return unit, document

    @app.get("/api/document/{source}/{unit_id:path}")
    def document_api(source: str, unit_id: str) -> Any:
        """How long the document is, and where in it this unit sits.

        Asked for only when the scrolling view is first opened, because it
        opens the PDF: a units page carrying this for every row would pay that
        cost 750 times to answer a question nobody asked.
        """
        from ..extract import render as render_mod

        unit, document = _unit_document(source, unit_id)
        try:
            total = render_mod.page_count(document)
        except render_mod.PdfUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"pages": total, "page": unit.locator.page or 1}

    @app.get("/page/{source}/{unit_id:path}.png")
    def page_image(source: str, unit_id: str, n: int = 1, marks: bool = True) -> Response:
        """One whole page of the unit's document, for the scrolling view.

        The page number is a query parameter rather than another path segment:
        `{unit_id:path}` is greedy and would swallow it, and a unit id already
        contains the colons that make it look like a path.
        """
        from ..extract import render as render_mod

        unit, document = _unit_document(source, unit_id)
        try:
            png = render_mod.render_page(
                document,
                n,
                regions=render_mod.regions_for(unit, n) if marks else [],
                # The red box only on the page the unit is actually on.
                outline=unit.locator.bbox if n == unit.locator.page else None,
            )
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



# When this process started. Compared against the Python on disk, because the
# two halves of this app reload on completely different schedules and the
# mismatch is silent.
_STARTED_AT = time.time()


def code_is_newer_than_this_process() -> bool:
    """Has the Python changed since `forge serve` started?

    Jinja re-reads a template on every request and Python is imported once, so
    editing both and not restarting leaves a server rendering **new templates
    against old code**. Every new template guarded by `{% if thing is defined %}`
    then renders nothing, and every new endpoint 404s -- so a feature that
    exists and works reads, on screen, as a feature that was never built.

    That failure mode cost three bug reports in one afternoon, all of them
    "this does not exist", and none of them visible from inside the app. Hence
    the check: not a guess about what is wrong, just the one fact that settles
    it -- a file on disk is newer than the interpreter holding it.

    Cheap enough to run on the counts poll: ~30 files, stat only, and it stops
    entirely once it has said yes.
    """
    package = Path(__file__).resolve().parent.parent
    try:
        return any(
            path.stat().st_mtime > _STARTED_AT for path in package.rglob("*.py")
        )
    except OSError:
        # A file vanishing mid-walk is an editor writing atomically, not an
        # answer. Say no rather than crying stale on every save.
        return False


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
    counts["unannotated_unit"] = 0
    counts["unannotated_card"] = 0
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
            counts["unannotated_unit"] += has_annotation(unit.notes, "none")
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
        counts["unannotated_card"] += has_annotation(notes, "none")
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
    """Does any of these notes address `audience`?

    `any` matches an annotation to anyone; `none` matches a card carrying no
    annotation at all -- the ones actually waiting on your judgement. Without
    that, an annotated draft sat in the review queue for ever and the only way
    to stop meeting it was to reject it, which claims something quite
    different and is not what you meant.
    """
    if audience == "none":
        return not any(model.annotation_audience(n) for n in notes)
    if audience == "any":
        return any(model.annotation_audience(n) for n in notes)
    return any(model.annotation_audience(n) == audience for n in notes)


# What to call a group of marks of one kind. Plural and plain, because the
# heading is a container label -- "what you highlighted" -- and not a reading
# of any one mark; that is the legend's job, on the other rail.
KIND_GROUPS = {
    "highlight": "highlighted",
    "underline": "underlined",
    "note": "notes in the margin",
    "image": "boxed regions",
    "ink": "drawn on the page",
    "text": "typed on the page",
}


def grouped_marks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The unit's own mark, and the rest gathered by kind.

    Its own comes out of the grouping entirely: it is not one of several
    highlights to be read through, it is the thing the decision is about.

    The rest group because thirty rows of mixed kinds is a list you scroll
    rather than read, and the kinds answer different questions -- what the
    paper says, versus what you thought about it. Each group collapses, so the
    two-word terms can be shut away while the claims stay open.
    """
    groups: dict[str, dict[str, Any]] = {}
    colours: dict[str, int] = {}
    own = None
    for row in rows:
        if row["own"]:
            own = row
            continue
        kind = str(row["kind"]) or "highlight"
        group = groups.setdefault(
            kind, {"kind": kind, "label": KIND_GROUPS.get(kind, kind), "marks": []}
        )
        group["marks"].append(row)
        # What the swatch filter offers. Keyed the way the row is drawn --
        # colour, or the kind when a mark has no colour -- so the two cannot
        # disagree about what a chip turns off.
        key = str(row["colour"]) or kind
        colours[key] = colours.get(key, 0) + 1
    ordered = sorted(groups.values(), key=lambda g: -len(g["marks"]))
    for group in ordered:
        group["count"] = len(group["marks"])
    return {
        "own": own,
        "groups": ordered,
        "count": len(rows),
        "colours": [
            {"colour": c, "count": n}
            for c, n in sorted(colours.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def mark_payloads(
    unit: Unit, config: Config, known: set[str] | None = None
) -> list[dict[str, Any]]:
    """Every mark on or around this unit, as the triage view shows them.

    What the reader wrote is the most useful thing on the page and it was
    nowhere in the app: the crop showed a highlight and said nothing about the
    sentence beside it in the margin. Text and comment are both here, kept
    apart, because they are not the same claim -- one is the document's words
    and one is the reader's.

    `meaning` is resolved now rather than stored, so editing `[zotero.meanings]`
    changes every unit at once instead of only the ones imported since.
    """
    scheme = config.zotero_for(unit.source)
    rows: list[dict[str, Any]] = []
    for index, mark in enumerate(unit.marks):
        own = not index
        elsewhere = f"{unit.source}:{mark.key}"
        rows.append({
            "key": mark.key,
            "kind": mark.kind,
            "colour": mark.colour,
            "meaning": scheme.means(mark.kind, mark.colour),
            "text": mark.text,
            "comment": mark.comment,
            "page": mark.page if mark.page is not None else (unit.locator.page if own else None),
            "own": own,
            # Whether this neighbour is a unit in its own right, and so
            # something you will meet again rather than context for this one.
            "unit": elsewhere if known and elsewhere in known else "",
        })
    return rows


# The sizes the chip offers. Coarse on purpose: the decision is "a bit more" or
# "all of it", not a measurement. `999` means the whole document.
CONTEXT_STEPS = (0, 1, 3, 10, 999)


def context_label(pages: int, *, chosen: bool = False) -> str:
    """One step of the context chip.

    The chosen one is written out and the rest are bare numbers, so the chip
    reads as a sentence with the answer in it -- `context: 1 · 3 pages either
    side · 10 · all` -- rather than as five numbers you have to decode.

    **"3 pages" means three pages either side**, seven in total: `context.py`
    takes `range(page - n, page + n + 1)`. Saying "3 pages" and handing over
    seven is the kind of quiet mismatch that makes a card writer think they
    have the whole story when they have more of it than they expected, so the
    chosen label spells it out and the tooltip repeats it.
    """
    if pages >= 100:
        return "the whole document" if chosen else "all"
    if pages == 0:
        return "this page only" if chosen else "0"
    if not chosen:
        return str(pages)
    return f"{pages} page{'' if pages == 1 else 's'} either side"


def context_steps(current: int) -> list[dict[str, Any]]:
    """Every size, with the one in force written out and marked."""
    return [
        {
            "pages": step,
            "label": context_label(step, chosen=step == current),
            "on": step == current,
        }
        for step in CONTEXT_STEPS
    ]


def unit_mark(unit: Unit) -> str:
    """`kind/colour` of the mark this unit came from, or empty.

    The unit's *own* mark, not the ones shown beside it: those belong to their
    own units and matching on them would return every neighbour too.
    """
    if not unit.marks:
        return ""
    own = unit.marks[0]
    return f"{own.kind}/{own.colour}" if own.colour else own.kind


def mark_matrix(units: list[Unit], config: Config, source: str) -> dict[str, Any]:
    """The marks you can filter by, as a grid: kinds down, colours across.

    A prose source is triaged by what you meant, not by what state a unit is
    in: "the claims first, the terms never". Five annotation kinds times eight
    colours is forty labelled lines, and as a flat list that is the whole rail.

    A grid is the right shape because the data *is* two-dimensional and every
    other arrangement hides one axis. Kind-major rows of chips -- what this
    was -- made "every green mark, whatever I drew it with" something you had
    to assemble by eye from four different rows, and left no place at all to
    show the combinations you have never used. Here a column is a colour, a
    row is a kind, and the empty cells are as informative as the full ones:
    they are the reader's scheme, drawn.

    Cells come in three states, and they are three different facts:

    * **declared** -- you said what this combination means. Full strength.
    * **default only** -- it reads as what Zotero's annotation kind is, which
      is not the same as a decision. Still filterable, drawn dashed, and the
      tooltip says so.
    * **empty** -- nothing in this source is marked that way. Not clickable,
      because a filter that can only ever return nothing is a dead control.

    Nothing appears for a source with no marks, so the Cookbook's rail is
    unchanged: all of this is Zotero's, and a segmented book has none of it.
    """
    scheme = config.zotero_for(source)
    tally: dict[str, int] = {}
    for unit in units:
        key = unit_mark(unit)
        if key:
            tally[key] = tally.get(key, 0) + 1

    # Only combinations the scheme gives a reading to, so a kind Zotero does
    # not define never becomes a row -- the floor under your declarations is
    # Zotero's closed set, not a guess at what "doodle" might have meant.
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    kind_total: dict[str, int] = {}
    colour_total: dict[str, int] = {}
    for key, count in tally.items():
        kind, _, colour = key.partition("/")
        meaning, where = scheme.reading(kind, colour)
        if not meaning:
            continue
        cells[kind, colour] = {
            "key": key,
            "kind": kind,
            "colour": colour,
            "meaning": meaning,
            "declared": where == "declared",
            "count": count,
        }
        kind_total[kind] = kind_total.get(kind, 0) + count
        colour_total[colour] = colour_total.get(colour, 0) + count
    if not cells:
        return {}

    # Commonest first on both axes, so the corner of the grid you look at
    # first is the part of the scheme you actually use.
    colours = sorted(colour_total, key=lambda c: (-colour_total[c], c))
    rows = []
    for kind in sorted(kind_total, key=lambda k: (-kind_total[k], k)):
        rows.append({
            "kind": kind,
            "label": KIND_GROUPS.get(kind, kind),
            "count": kind_total[kind],
            "cells": [
                cells.get(
                    (kind, colour),
                    # A cell that exists only to hold the grid square. It
                    # carries what it *would* mean, because that is what the
                    # hover has to say about a combination you have not used.
                    {
                        "key": "",
                        "kind": kind,
                        "colour": colour,
                        "meaning": scheme.reading(kind, colour)[0],
                        "declared": False,
                        "count": 0,
                    },
                )
                for colour in colours
            ],
        })
    return {
        "colours": [{"colour": c, "count": colour_total[c]} for c in colours],
        "rows": rows,
    }


def _scheme_key(scheme: Any, kind: str, colour: str) -> str:
    """Which line of the scheme a mark of this kind and colour falls under.

    The same walk `ZoteroConfig.means` does, so the legend groups marks exactly
    the way the config resolves them: an entry for `note` really does collect
    every colour of sticky note, and seeing that is the point of showing it.
    An undeclared mark falls back to its own colour, which is what you would
    reach for if you were about to declare it.
    """
    for probe in (f"{kind}/{colour}", kind, colour):
        if scheme.meanings.get(probe):
            return probe
    # Nothing declared. Group at full specificity rather than under the colour,
    # so every combination you have not decided about is its own row: a grey
    # highlight and a magenta one are two different undecided things, and
    # collapsing them hides exactly the information you need to decide.
    return f"{kind}/{colour}" if kind and colour else (kind or colour)


def scheme_rows(units: list[Unit], config: Config, source: str) -> list[dict[str, Any]]:
    """What this source's marks mean, and which of them make units.

    The legend, not the filter. Every colour and kind declared for this source
    -- including ones nothing is marked with yet -- plus anything marked that
    has *not* been declared, which is the row worth seeing: an unmapped mark is
    one whose meaning exists only in your head, and it will reach a card
    writer as a coloured box with no caption.

    Counted over marks rather than units, deduplicated by key, because a mark
    appears in the neighbour list of every unit near it and counting those
    would report the same highlight five times.
    """
    from ..zotero import HEX_BY_NAME

    scheme = config.zotero_for(source)
    seen: dict[str, set[str]] = {}
    for unit in units:
        for mark in unit.marks:
            seen.setdefault(_scheme_key(scheme, mark.kind, mark.colour), set()).add(mark.key)
    if not seen:
        # Nothing in this source was marked, so there is no scheme in force
        # here. `[zotero.meanings]` is repo-wide and would otherwise render a
        # full colour legend, every count zero, beside a book nobody has ever
        # highlighted -- the rail saying something about a different source.
        return []

    rows: list[dict[str, Any]] = []
    for probe in {*scheme.meanings, *seen}:
        left, slash, right = probe.partition("/")
        if slash:
            kind, colour = left, right
        elif left in HEX_BY_NAME:
            kind, colour = "", left
        else:
            kind, colour = left, ""
        declared = scheme.meanings.get(probe, "")
        rows.append({
            "key": probe,
            "kind": kind,
            "colour": colour,
            # What it reads as, and whether that is a decision you took or the
            # floor under it. They are not the same claim -- a default says
            # what Zotero's annotation kind *is*, a declaration says what you
            # meant by it -- and the difference is the whole point of showing
            # the scheme rather than just a tally.
            "meaning": declared or scheme.reading(kind, colour)[0],
            "declared": bool(declared),
            "count": len(seen.get(probe, ())),
            "makes_a_unit": scheme.makes_a_unit(kind, colour),
        })
    rows.sort(key=lambda r: (not r["makes_a_unit"], -int(r["count"]), str(r["key"])))
    return rows


def scheme_legend(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The scheme grouped by what it *means*, for the information rail.

    `scheme_rows` is the facts -- one entry per line of the config. This is how
    they are read, and the two differ because the interesting structure is not
    the keys, it is the meanings.

    Zotero gives eight colours and six annotation kinds, so a source can reach
    forty-eight combinations; the rail is 240px wide and the old legend spent
    two lines on each one. But nobody has forty-eight *meanings*. `kind` beats
    `colour` in the config's own lookup, so one `note = "..."` line already
    covers every colour of sticky note -- and a legend that lists those
    separately is repeating one sentence eight times and calling it detail.

    Grouping by meaning collapses exactly that, and it collapses nothing real:
    two keys that genuinely mean different things stay two rows. Where they do
    land together, the swatches sit side by side on one line and the sentence
    is written once. Seeing two colours share a meaning is also worth knowing
    -- it is usually a scheme you have half-changed.

    `makes_a_unit` and `declared` are ORed across the group deliberately. A
    meaning that *any* of its marks turns into units is one you meet in the
    queue, which is what the tag is telling you; and a group with one declared
    key is not an undecided one, it is a decided one you have used twice.
    """
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = groups.setdefault(
            str(row["meaning"]),
            {
                "meaning": row["meaning"],
                # Not `keys`: Jinja resolves `row.keys` on a dict to the bound
                # `dict.keys` method before it looks at the item, so the
                # template iterated a builtin and 500ed.
                "entries": [],
                "count": 0,
                "makes_a_unit": False,
                "declared": False,
            },
        )
        group["entries"].append(row)
        group["count"] += int(row["count"])
        group["makes_a_unit"] = group["makes_a_unit"] or bool(row["makes_a_unit"])
        group["declared"] = group["declared"] or bool(row["declared"])
    for group in groups.values():
        group["entries"].sort(key=lambda r: (-int(r["count"]), str(r["key"])))
    # What makes units first -- those are the rows you meet in the queue --
    # then by how much of the document carries them.
    return sorted(
        groups.values(),
        key=lambda g: (not g["makes_a_unit"], not g["declared"], -int(g["count"])),
    )


def source_origin(config: Config, source: str) -> str:
    """Where this source's material comes from: `zotero`, `pdf`, `tex`, or ``.

    Not cosmetic. It decides which passes make sense, how wide crops are cut,
    and where to go when a document is missing -- and it was invisible, so a
    paper imported from Zotero and a PDF sitting in the repo looked identical
    in every view.
    """
    spec = config.sources.get(source)
    if spec is None:
        return ""
    if spec.zotero_key:
        return "zotero"
    if spec.pdf:
        return "pdf"
    return "tex" if spec.tex else ""


def source_facts(config: Config, source: str, *, from_marks: bool = False) -> dict[str, Any]:
    """This source's resolved settings, for the information rail.

    The same numbers `/config` lists, for the one source you are actually
    looking at. There was no way to see which layout the card in front of you
    resolved to without leaving the view, and layout decides what every
    derivative on it means.
    """
    from ..context import source_conventions

    spec = config.sources.get(source)
    origin = source_origin(config, source)
    scheme = config.zotero_for(source)
    return {
        # Which marks become units, and *only* for a source that came from
        # Zotero: a segmented book has no marks and no scheme, and showing it
        # one would be the rail describing machinery that is not running.
        "units_from": sorted(scheme.units_from) if origin == "zotero" else [],
        "name": source,
        "configured": spec is not None,
        "title": spec.title if spec else source,
        "citation": spec.citation if spec else "",
        "tags": list(spec.tags) if spec else [],
        "origin": origin,
        "zotero_key": spec.zotero_key if spec else "",
        "deck": config.deck_for(source),
        "decks": sorted(spec.decks.items()) if spec else [],
        # `[conventions]`: what this source declares as keys, all of it, not
        # only the one entry `verify` acts on. A convention the tool has never
        # heard of is still a fact whoever writes a card here needs.
        "declared": sorted(config.conventions_for(source).items()),
        "web": config.web_for(source),
        "web_own": spec is not None and spec.web is not None,
        "order": spec.order if spec else "",
        "crop_width": config.crop_width_for(source, from_a_mark=from_marks),
        "crop_context": config.crop_context_for(source),
        "context_pages": config.context_pages_for(source),
        # Whether anyone has written down what is ambient here. An absent
        # convention is a card writer guessing, so it is worth saying out loud
        # rather than leaving as a blank.
        "conventions": bool(source_conventions(config, source).strip()) if spec else False,
    }


def source_gallery(config: Config) -> dict[str, Any]:
    """Every source, with where it came from and how far along it is.

    A dropdown answers "which one am I on" and nothing else. With a shelf of
    papers the question is which one to work on next, and that is a comparison
    -- so this carries the counts for both halves of the pipeline per source,
    the tags to narrow by, and where each one came from.

    Everything is recomputed per request, like every other read here. It walks
    every ledger and every card, which is why it is asked for on demand rather
    than rendered into each page.
    """
    ledgers = _ledgers(config)
    by_source: dict[str, list[Card]] = {}
    for card in model.load_all(config.cards_dir):
        by_source.setdefault(card.source_name, []).append(card)

    rows: list[dict[str, Any]] = []
    for name in source_names(config):
        spec = config.sources.get(name)
        units = list(ledgers.get(name, ()))
        counts = dict.fromkeys((*UNIT_STATES, *CARD_STATES), 0)
        for unit in units:
            counts[unit.state] = counts.get(unit.state, 0) + 1
        for card in by_source.get(name, []):
            counts[card.effective_status] = counts.get(card.effective_status, 0) + 1
        rows.append({
            "name": name,
            "title": spec.title if spec else name,
            "citation": spec.citation if spec else "",
            "tags": list(spec.tags) if spec else [],
            "origin": source_origin(config, name),
            "from_marks": any(u.marks for u in units),
            "counts": counts,
            "units": len(units),
            "cards": len(by_source.get(name, [])),
            "deck": config.deck_for(name),
            "layout": config.layout_for(name),
            "configured": spec is not None,
        })

    totals = dict.fromkeys((*UNIT_STATES, *CARD_STATES), 0)
    for row in rows:
        for state, number in row["counts"].items():
            totals[state] += number
    return {
        "sources": rows,
        "totals": totals,
        "units": sum(int(r["units"]) for r in rows),
        "cards": sum(int(r["cards"]) for r in rows),
        "tags": sorted({t for r in rows for t in r["tags"]}),
        # Only the origins actually present, so the filter never offers a
        # button that matches nothing.
        "origins": sorted({str(r["origin"]) for r in rows if r["origin"]}),
    }


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
    that should be a choice you make by editing `forge.toml` rather than
    an accident of spelling. Ledgers with no `[sources.*]` entry follow.
    """
    names = list(config.sources)
    names += sorted(set(open_ledgers(config.sources_dir)) - set(names))
    return names


def effective_config(config: Config) -> list[dict[str, Any]]:
    """Every resolved setting, and where the value came from.

    Read-only on purpose. Editing would not break invariant 2 -- it would edit
    the file -- but the config is read at startup, so a change here would take
    effect at some unrelated later moment. And half these keys change the
    meaning of *existing* content: `layout` decides what every derivative on
    every card from that source means. A box that silently changes one, with a
    restart between cause and effect, is a trap dressed as convenience.

    What was actually missing was seeing. There is no way today to tell which
    layout a card resolved to, or whether that came from the source or the
    default, without reading Python.
    """
    rows: list[dict[str, Any]] = []

    def add(where: str, key: str, value: Any, source: str) -> None:
        rows.append({"where": where, "key": key, "value": value, "from": source})

    add("repo", "language", config.language, "forge.toml")
    add("repo", "front_char_cap", config.front_char_cap, "forge.toml")
    add("repo", "crop_context", config.crop_context_for(""), "forge.toml")
    add(
        "repo",
        "crop_width",
        config.crop_width or "page for marks, box for the rest",
        "forge.toml" if config.crop_width else "by where the geometry came from",
    )
    add("repo", "context_pages", config.context_pages, "forge.toml")
    add("repo", "web", "allowed" if config.web else "off", "forge.toml")
    add("anki", "deck", config.deck, "forge.toml")
    add("anki", "note type", config.note_type, "forge.toml")
    add("anki", "tag prefix", config.tag_prefix, "forge.toml")
    add("anki", "url", config.anki_url, "ANKI_CONNECT_URL or forge.toml")
    add("zotero", "data dir", str(config.zotero.data_dir), "forge.toml")
    add("zotero", "units from", ", ".join(sorted(config.zotero.units_from)), "forge.toml")

    for name, spec in config.sources.items():
        where = f"source: {name}"
        origin = f"sources/{name}/source.toml"
        inherited = "inherited"
        add(where, "material", source_origin(config, name) or "unset", origin)
        add(where, "deck", config.deck_for(name), origin if spec.deck else inherited)
        add(where, "order", spec.order, origin)
        add(
            where,
            "web",
            "allowed" if config.web_for(name) else "off",
            origin if spec.web is not None else inherited,
        )
        # Everything under `[conventions]`, not only the one key `verify` acts
        # on. A convention the tool has never heard of is still a fact a card
        # writer needs, and the table is where it is stated.
        for key, value in sorted(spec.conventions.items()):
            add(where, f"conventions.{key}", value, origin)
        add(
            where,
            "crop_context",
            config.crop_context_for(name),
            origin if spec.crop_context else inherited,
        )
        add(
            where,
            "crop_width",
            spec.crop_width or "page for marks, box for the rest",
            origin if spec.crop_width else "by where the geometry came from",
        )
        add(
            where,
            "context_pages",
            config.context_pages_for(name),
            origin if spec.context_pages >= 0 else inherited,
        )
        if spec.tags:
            add(where, "tags", ", ".join(spec.tags), origin)
        for card_type, deck in sorted(spec.decks.items()):
            add(where, f"deck [{card_type}]", deck, origin)
        scheme = config.zotero_for(name)
        if scheme.units_from:
            add(
                where,
                "units from",
                ", ".join(sorted(scheme.units_from)),
                origin if spec.units_from else inherited,
            )
    return rows


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


def commands_for(
    view: str,
    filters: dict[str, Any],
    counts: dict[str, int],
    *,
    from_marks: bool = False,
) -> list[dict[str, str]]:
    """What to run next, scoped to the source and section on screen.

    The honest version of "trigger Claude from the website": you filter here,
    copy, and paste it where you can watch it. Nothing is launched, so nothing
    writes cards with nobody looking.

    `counts` is the whole source rather than the filtered deck, deliberately:
    you triage in the `new` view and the units you queue as you go are the
    reason to run `/extract-cards` next. Counting only what is on screen would
    hide that step at exactly the moment you earned it, so the number in each
    label says which population it is talking about.

    `from_marks` says the units came from someone marking the document up
    rather than from segmenting it. Both crop-reading passes are off for those:
    `/transcribe` records what an equation says as LaTeX, and a highlight
    already carries its own text; `/classify` proposes skipping fragments and
    table rows, which is a judgement about a page of formulas.
    """
    source = str(filters.get("source", ""))
    section = str(filters.get("section", ""))
    src, sec = flag("--source", source), flag("--section", section)
    scope = sec or " --all"
    out: list[dict[str, str]] = []

    if view == "units":
        if from_marks:
            out.append({
                "kind": "note",
                "label": "nothing to transcribe here — a mark carries its own text",
                "run": "",
            })
        elif counts.get("new"):
            out.append({
                "label": f"read the crops — {counts['new']} still untranscribed",
                "run": f"/transcribe{src}{scope}",
                "kind": "claude",
            })
            out.append({
                "label": "propose which of them to skip",
                "run": f"/classify{src}{scope}",
                "kind": "claude",
            })
        if counts.get("queued"):
            out.append({
                "label": f"write stubs for {counts['queued']} queued",
                "run": f"/extract-cards{src}{sec}",
                "kind": "claude",
            })
        out.append({
            "label": "this list, as JSON",
            "run": (
                f"uv run forge units{src}"
                f" --state {filters.get('state') or 'all'}{sec} --json"
            ),
            "kind": "shell",
        })
    else:
        if counts.get("draft"):
            out.append({
                "label": f"fill in {counts['draft']} thin drafts",
                "run": f"/augment{src}",
                "kind": "claude",
            })
        if counts.get("annotated_claude_card"):
            out.append({
                "label": f"{counts['annotated_claude_card']} open requests",
                "run": "/triage claude",
                "kind": "claude",
            })
        if counts.get("approved"):
            out.append({
                "label": "check the maths numerically",
                "run": f"uv run forge verify{src}",
                "kind": "shell",
            })
        out.append({
            "label": "what would reach Anki",
            "run": "uv run forge sync --dry-run",
            "kind": "shell",
        })
    return out


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


def pdf_context(config: Config | None = None, source: str = "") -> float:
    """Points of page shown around a crop at triage."""
    from ..extract.render import TRIAGE_CONTEXT

    if config is None:
        return TRIAGE_CONTEXT
    return config.crop_context_for(source)

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


def _unit_payload(
    unit: Unit, config: Config, known: set[str] | None = None
) -> dict[str, Any]:
    image = crop_url(unit, context=pdf_context(config, unit.source))
    return {
        # What the reader marked here and on the pages around it: the text
        # each one covers and whatever they wrote about it. The crop shows
        # where the marks are; this is what they say.
        "marks": grouped_marks(mark_payloads(unit, config, known)),
        # Every annotation with the index that identifies it, so one can be
        # answered without the browser guessing which line it was.
        "annotations": [
            {
                "index": index,
                "audience": model.annotation_audience(note) or "claude",
                "text": _note_text(note),
            }
            for index, note in enumerate(unit.notes)
        ],
        "id": unit.id,
        "gist": unit.gist,
        "state": unit.state,
        "reason": unit.reason,
        "image": image,
        "tex": unit.tex,
        "transcription": unit.transcription,
        "authoritative": unit.authoritative,
        "context": unit.context,
        "locator": unit.locator.describe(),
        "section": unit.locator.section,
        # The view distinguishes "nothing proposed a skip" from "nothing was
        # allowed to": a numbered equation is off limits to the classifier.
        "equation": unit.locator.equation,
        "uids": unit.uids,
        "notes": unit.notes,
        "suggestion": vars(unit.suggestion) if unit.suggestion else None,
        # How much of the document a card writer will be handed, and whether
        # this unit asked for it or inherited it.
        "context_pages": config.context_pages_for(unit.source, unit.context_pages),
        "context_steps": context_steps(
            config.context_pages_for(unit.source, unit.context_pages)
        ),
        "context_own": unit.context_pages is not None,
        # Whether whoever writes this card may look things up, resolved the
        # same way and shown the same way: the answer, and whose answer it is.
        "web": config.web_for(unit.source, unit.web),
        "web_own": unit.web is not None,
    }


def _card_payload(
    card: Card,
    findings: list[check.Finding],
    config: Config,
    place: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mine = [f.as_dict() for f in check.findings_for(findings, card)]
    return {
        "uid": card.uid,
        "status": card.effective_status,
        # `status` above is what the card *counts as*; this is what the file
        # says, and `demotion` is why the two differ. An approval held by an
        # open note is not withdrawn -- resolving the note restores it -- so
        # the view has to show both halves or it reads as a lost approval.
        "declared": card.status,
        "demotion": card.demotion,
        "source": card.source,
        "unit": card.unit,
        "tags": card.tags,
        # What decides where this card lands in the new-card queue. All of it
        # was invisible here: you author `frequency`, `derivation` and
        # `requires` by hand in the file and could not see any of them while
        # reviewing, which is a poor way to keep a dependency graph honest.
        "frequency": card.frequency,
        "derivation": card.derivation,
        # The same permission the unit carries, resolved for this card: its own
        # answer if it has one, else the unit's, else the source's, else off.
        "web": _card_web(card, config),
        "web_own": card.web is not None,
        # Resolved links, not bare uids: each one knows which source its
        # target lives in, and whether it exists at all.
        "requires": (place or {}).get(
            "requires", [{"uid": u, "known": False, "href": ""} for u in card.requires]
        ),
        "required_by": (place or {}).get("required_by", []),
        "position": (place or {}).get("position"),
        "total": (place or {}).get("total"),
        "verify": card.verify_enabled,
        "path": str(card.path.relative_to(config.root)) if card.path else "",
        "mtime": str(card.mtime_ns or 0),
        # Canonical order, not file order: the app is a view, and a card whose
        # file has not been rewritten since `SECTION_ORDER` changed should
        # still read the way the Anki card does.
        "sections": [
            {"name": s.name, "body": s.body}
            for s in card.canonical().sections
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


def _card_web(card: Card, config: Config) -> bool:
    """Whether whoever augments this card may look things up.

    Card, then the unit it came from, then source, then repo. The unit sits in
    the chain because a card is written *from* a unit: granting the permission
    during triage and then having it evaporate the moment a stub exists would
    make the grant useless exactly where it was aimed.
    """
    if card.web is not None:
        return card.web
    source = card.source_name
    unit = None
    if card.unit:
        path = config.units_path(source)
        if path.exists():
            found = Ledger.load(path).get(card.unit)
            unit = found.web if found else None
    return config.web_for(source, unit)


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
