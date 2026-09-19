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

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup

from .. import check, latex, model, study
from .. import graph as graph_mod
from ..config import (
    CHAPTER,
    DECLARED,
    DEFAULT_MEANINGS,
    Config,
    ConfigError,
    context_asked,
    context_size,
    save_study_order,
)
from ..ledger import Ledger, Unit, open_ledgers
from ..model import Card, StaleFileError
from ..sync import (
    in_study_order,
    inherited_from,
    source_positions,
    study_key,
    study_values,
)
from . import keys as keymod

HERE = Path(__file__).parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"
CDN_KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"


#: What the "nothing here yet" page can actually do. It has no deck, so none
#: of the per-item keys have anything to act on -- and it loads no view script,
#: so until `empty.js` there was nothing bound at all while the footer listed
#: all fifteen. The first screen anybody sees was the one that lied about how
#: to drive it.
EMPTY_VIEW_KEYS = ("filters", "projects", "guide")


def key_context(
    config: Config, view: str, only: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Both renderings of one keymap: the legend, and what the browser binds.

    Handed to every view rather than assembled per template, so a view cannot
    ship a footer without the bindings that go with it -- which is the shape
    the three hand-written copies were in before `app/keys.py`.

    `only` narrows both halves together, for a page that binds a subset.
    """
    resolved = keymod.resolve(view, config.keys)
    if only is not None:
        resolved = [key for key in resolved if key.action in only]
    return {
        "keymap": resolved,
        "keymap_keys": {k.action: k.key for k in resolved},
        # `Markup`, because Jinja autoescapes and a JSON payload run through
        # the HTML escaper comes out as `{&#34;approve&#34;: ...}`, which
        # `JSON.parse` refuses -- so *every* key silently stops binding, the
        # whole keyboard at once. `<` is escaped by hand instead, so a key
        # spelling `</script>` cannot close the tag it is inside.
        "keymap_json": Markup(
            json.dumps({k.action: k.key for k in resolved}).replace("<", "\u003c")
        ),
    }


def render_body(body: str, unit: str = "") -> Markup:
    """Card text as HTML, with fenced code blocks kept out of KaTeX's way.

    A `## verify` block is Python between triple backticks. Rendered as plain
    text it showed the fences literally and KaTeX tried to read the maths-like
    parts of the code. `<pre>` is right here for the same reason it was wrong
    for notes: KaTeX skips it by default.

    `unit` is the card's own, which is what a bare `![...](unit)` means. The
    picture is rendered from the source document per request, exactly as the
    crop beside the card is: the app shows what `sync` will upload rather than
    a second rendering of it.
    """
    out: list[str] = []
    for i, chunk in enumerate(body.split("```")):
        if i % 2 == 0:
            out.append(_with_images(escape(chunk), unit))
            continue
        # a fence may name its language on the first line
        first, _, rest = chunk.partition("\n")
        code = rest if first.strip().isalpha() and rest else chunk
        out.append(f"<pre class='code'>{escape(code.strip())}</pre>")
    # Markup, not str: the filter escapes its own input, so returning a plain
    # string would have Jinja escape the tags too and show them as text.
    return Markup("".join(out))


def _with_images(chunk: str, unit: str) -> str:
    """`![what it shows](unit:<id>)` -> the crop, rendered on request.

    Against the escaped text, since that is what the tag has to end up inside.
    A reference comes through `escape` unchanged apart from its alt text,
    which is why the alt is read back out of the escaped copy rather than
    matched in the original.
    """

    from ..extract.render import CARD_INSET

    def tag(match: Any) -> str:
        named = (match.group(2) or unit).strip()
        if not named:
            # Nothing to point at. `check` reports it; the view shows the line
            # as written rather than an image element with no source.
            return str(match.group(0))
        source = named.split(":", 1)[0]
        # Rendered exactly as `sync` will render it: no `width`, so the same
        # resolution the crop beside the card uses; `marks=false`, because the
        # mark an image unit came from *is* its boundary and painting it back
        # draws a frame round the picture; and the same inset, for the copy of
        # that frame that lives in the PDF itself.
        #
        # A picture you approved on screen has to be the picture Anki gets.
        url = (
            f"/crop/{quote(source)}/{quote(named, safe='')}.png"
            f"?context=-{CARD_INSET:g}&marks=false"
        )
        return (
            f'<img class="card-image" src="{url}" alt="{match.group(1)}" '
            f'loading="lazy" title="{named}">'
        )

    return model.IMAGE_RE.sub(tag, chunk)


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="forge", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES))
    templates.env.filters["body"] = render_body

    @pass_context
    def key_of(ctx: Any, action: str) -> str:
        """The key bound to `action` in the view being rendered.

        So the guide teaches the keymap in force rather than the defaults it
        was written against. A context function and not a global, because the
        answer differs per view: `a` approves on one and accepts a suggestion
        on the other, and `[app.keys]` can move either.
        """
        return str((ctx.get("keymap_keys") or {}).get(action, "")) or "?"

    templates.env.globals["key"] = key_of
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
    # So the rail can open the chapter holding the active section without
    # re-implementing the rule in Jinja -- which is how it came to split on
    # `.`, a Cookbook convention, in a template shown for every source.
    templates.env.globals["section_chapter"] = _chapter_of
    # The other half of the staleness handshake: a value only a current Python
    # can supply, so a template newer than the process renders it empty and
    # `app.js` can tell. `_STARTED_AT` is enough -- what matters is that the
    # attribute is *there*, not what it says.
    templates.env.globals["app_build"] = str(int(_STARTED_AT))
    # The guide states the study-order rule in a line of three words. It was
    # three words typed into the template, so `[cards] study_order` could
    # reorder the deck while the guide went on describing the default.
    templates.env.globals["study_criteria"] = lambda: study.resolve(study_order(config))
    templates.env.globals["mark_selection"] = mark_selection
    templates.env.globals["mark_toggle"] = mark_toggle

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
        chapter: str = "",
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
                    **key_context(config, "units", EMPTY_VIEW_KEYS),
                    "config": config,
                    "source": resolve_source(config, source),
                    "projects": project_names(config),
                    "pipeline": pipeline_counts(config, resolve_source(config, source)),
                },
            )
        name = resolve_source(config, source)
        # Asked for, or landed on: the two want opposite things.
        #
        # A source named in the URL is honoured even with nothing extracted,
        # and its view comes up empty. It used to fall through to
        # `next(iter(ledgers))`, so the URL said `hollow`, the header said
        # `hollow`, and you were triaging the first book in the config.
        #
        # Nothing named is a default, and a default that lands you on an empty
        # view reads as a broken import. So that one steps past a source with
        # no ledger to one that has units.
        if not source and name not in ledgers:
            name = next(iter(ledgers))
        ledger = ledgers.get(name) or Ledger(config.units_path(name))
        # The section rows must show what clicking one would give, so they
        # are counted over everything the *other* filters leave -- the same
        # population, minus the section filter itself.
        unsectioned = ledger.select(state=state or "all", section=None)
        units = ledger.select(state=state or "all", section=section or None)
        # A chapter is a *range* of sections, not one of them, so it cannot go
        # through `select`: it is derived from the name rather than stored.
        # Folding a chapter open was the only thing its heading did, which is
        # not filtering by it -- and on a book with eight sections per chapter
        # "everything in chapter 2" was eight separate clicks and no way to see
        # them together.
        if chapter:
            units = [u for u in units if _chapter_of(u.locator.section) == chapter]
            unsectioned = [
                u for u in unsectioned if _chapter_of(u.locator.section) == chapter
            ]
        if suggested:
            unsectioned = [u for u in unsectioned if u.suggestion is not None]
        if annotated:
            unsectioned = [u for u in unsectioned if has_annotation(u.notes, annotated)]
        if transcribed or readable:
            unsectioned = [u for u in unsectioned if u.transcription == "ok"]
        # `mark` is a *set*, comma-separated in the URL. One value at a time
        # made the grid a radio button with forty positions: "every green
        # thing, whatever I drew it with" took four page loads and could not be
        # held in view at once, which is most of what the grid is for.
        wanted = marks_wanted(mark)
        if wanted is not None:
            unsectioned = [u for u in unsectioned if unit_mark(u) in wanted]
        if suggested:
            units = [u for u in units if u.suggestion is not None]
        if annotated:
            units = [u for u in units if has_annotation(u.notes, annotated)]
        if wanted is not None:
            units = [u for u in units if unit_mark(u) in wanted]
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
            "chapter": chapter,
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
                # Every filter this view resolved, under its own name. The rail
                # marks a row active by reading these, and a filter that is in
                # `filters` but not here builds correct links and then never
                # lights the row they came from. Explicit keys below win, so
                # this only ever adds.
                **filters,
                **key_context(config, "units"),
                "config": config,
                "source": name,
                "projects": project_names(config),
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
                "project_facts": project_facts(config, name, from_marks=from_marks),
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
        augmented: str = "",
        section: str = "",
        chapter: str = "",
        counts_scope: str = "",
    ) -> Any:
        name = resolve_source(config, source)
        cards, findings = _checked(config)
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
                    **key_context(config, "review", EMPTY_VIEW_KEYS),
                    "config": config,
                    "source": name,
                    "projects": project_names(config),
                    "pipeline": pipeline_counts(config, name),
                },
            )
        in_source = [c for c in cards if card_in_source(c, name)]
        cards = in_source
        if section:
            cards = [c for c in cards if card_section(c, config) == section]
        if chapter:
            # Same as the units view: a chapter is a range of sections, derived
            # from the name rather than stored, so it filters here.
            cards = [c for c in cards if _chapter_of(card_section(c, config)) == chapter]
        if annotated:
            cards = [c for c in cards if has_annotation(c.annotations(), annotated)]
        # Which pass has been over them, which is the only thing about a
        # card this app cannot answer from the content.
        if augmented in ("yes", "no"):
            cards = [c for c in cards if c.augmented == (augmented == "yes")]
        # Everything the other filters leave, ignoring the section: what each
        # section row would show if you clicked it.
        unsectioned = in_source
        if annotated:
            unsectioned = [c for c in unsectioned if has_annotation(c.annotations(), annotated)]
        if augmented in ("yes", "no"):
            unsectioned = [c for c in unsectioned if c.augmented == (augmented == "yes")]
        if status not in ("all", ""):
            unsectioned = [c for c in unsectioned if c.effective_status == status]
        # A dependency may name a card in another source: `check` validates
        # `requires` against the whole repo, not one book. Linking it with the
        # *current* source would land on a card that is not there, and the
        # hash lookup would find nothing and say nothing.
        homes = {c.uid: c.project_name for c in everywhere}

        by_uid_everywhere = {c.uid: c for c in everywhere}

        def link(uid: str) -> dict[str, Any]:
            known = uid in homes
            where = homes.get(uid) or name
            target = by_uid_everywhere.get(uid)
            return {
                "uid": uid,
                "known": known,
                # What the dependency *is*. A row of six-hex uids says a card
                # needs two other cards and nothing about which two, which is
                # the one thing you want to know while deciding whether the
                # edge is real.
                "gist": card_gist(target, config) if target else "",
                # `status=all` and no annotation filter, so following a link
                # never lands on a deck that excludes what you asked for.
                "href": filter_url("/review", {}, source=where, status="all") + f"#{uid}",
            }

        # One ordering for the whole source, so a card can say where it sits
        # and what put it there. The reverse edges are only computable here:
        # a card's file says what it needs, never what needs it.
        by_uid_card = {c.uid: c for c in in_source}
        ordered = in_study_order(in_source, source_positions(config), study_order(config))
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
        # The way into the canvas, and the only one: the header carries no view
        # links, and this is the view you are on when the question comes up.
        #
        # It was offered only on a card that already had a dependency, in a
        # source that already had one, so that nothing pointed at an empty
        # picture. That was right while the canvas could only be read. Now that
        # an arrow is *drawn* there, a source with no arrows is exactly when
        # you want it, and the old rule made the canvas unreachable from 90 of
        # this deck's 108 cards and from a new source altogether. Two cards is
        # the real floor: one card cannot depend on anything.
        linked = config.graph and len(in_source) > 1
        # Which way round to word it. "See the whole graph" promises something
        # to look at, and a source that has recorded no dependencies has none.
        any_edges = any(p["required_by"] or p["requires"] for p in places.values())

        selected = [c for c in cards if status in ("all", "") or c.effective_status == status]
        filters = {
            "source": name,
            "status": status,
            "section": section,
            "chapter": chapter,
            "annotated": annotated,
            "augmented": augmented,
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
                # See the units view: the rail's active rows are read from
                # these, so they come from the same dict the links are built
                # from rather than from a second list kept by hand.
                **filters,
                **key_context(config, "review"),
                "config": config,
                "cards": [
                    _card_payload(c, findings, config, places.get(c.uid)) for c in selected
                ],
                "counts": counts,
                "pipeline": pipeline,
                "total": len(cards),
                "status": status,
                "source": name,
                "projects": project_names(config),
                "annotated": annotated,
                "section": section,
                "filters": filters,
                "commands": commands_for("review", filters, pipeline, from_marks=from_marks),
                "scheme": scheme_legend(scheme_rows(units_here, config, name)),
                "project_facts": project_facts(config, name, from_marks=from_marks),
                "section_tree": section_rows(
                    in_source,
                    {c.uid for c in unsectioned},
                    lambda c: card_section(c, config),
                    lambda c: c.effective_status,
                    lambda c: c.uid,
                    CARD_STATES,
                ),
                "counts_scope": counts_scope,
                "graph_href": filter_url("/graph", {}, source=name) if linked else "",
                "graph_empty": not any_edges,
                "fsm_counts": (
                    scoped_counts(config, name, filters)
                    if counts_scope == "filtered"
                    else pipeline
                ),
            },
        )

    OFF = "the dependency canvas is off: `[app] graph` in forge.toml"

    def graph_enabled() -> None:
        """`[app] graph = false` takes the canvas off.

        One guard on every door into it rather than a flag each route reads its
        own way, because a view that is off in the navigation and on at its URL
        is off in the only sense that does not matter.
        """
        if not config.graph:
            raise HTTPException(404, OFF)

    @app.get("/graph", response_class=HTMLResponse)
    def graph_view(request: Request, source: str = "") -> Any:
        """The dependency canvas, one source at a time (ROADMAP.md §1).

        A view of its own rather than a panel, because it wants the whole
        window and its own keys. No filter rail: the rail filters a deck of
        one-at-a-time items and there is no deck here, and the source picker
        in the header is the only scoping the canvas has any use for.

        The page carries no data. Everything is fetched from
        `/api/graph/{source}`, which is also what the `every card` toggle
        re-fetches, so there is one code path that decides what is drawn.
        """
        # A page rather than the JSON body FastAPI would send. Every other
        # dead end in this app is a screen with a way off it, and a bookmark
        # landing on a bare `{"detail": ...}` has none.
        if not config.graph:
            return templates.TemplateResponse(
                request,
                "empty.html",
                {
                    "what": "dependency canvas",
                    "hint": OFF,
                    "view": "review",
                    **key_context(config, "review", EMPTY_VIEW_KEYS),
                    "config": config,
                    "source": resolve_source(config, source),
                    "projects": project_names(config),
                    "pipeline": pipeline_counts(config, resolve_source(config, source)),
                },
                status_code=404,
            )
        name = resolve_source(config, source)
        return templates.TemplateResponse(
            request,
            "graph.html",
            {
                **key_context(config, "graph"),
                "config": config,
                "source": name,
                "projects": project_names(config),
            },
        )

    @app.get("/api/graph/{source}")
    def graph_api(source: str, all: str = "") -> Any:
        graph_enabled()
        return source_graph(config, resolve_source(config, source), everything=bool(all))

    @app.post("/api/graph/{source}/positions")
    def graph_positions_api(source: str, body: dict[str, Any] = Body(default={})) -> Any:
        """Where the boxes have been dragged to.

        Positions are a view preference: wrong ones cost a drag, which is why
        this writes without a confirmation while nothing else in the app does.
        An edge goes through `/api/cards/{uid}/requires` instead, which is a
        write to a card file and is checked like one.
        """
        graph_enabled()
        name = resolve_source(config, source)
        raw = body.get("positions") or {}
        # `null` is "put this one back": the entry goes away and the node
        # returns to wherever the layout puts it.
        moved: dict[str, tuple[float, float] | None] = {
            str(node_id): (None if pair is None else (float(pair[0]), float(pair[1])))
            for node_id, pair in raw.items()
            if pair is None or (isinstance(pair, (list, tuple)) and len(pair) == 2)
        }
        path = graph_mod.positions_path(config.projects_dir, name)
        # No staleness check, unlike every other write here. `graph.move` merges
        # per node, so a writer working from a stale picture cannot destroy a
        # position it never mentions -- and the guard, while it was on, made two
        # tabs arranging different halves of one graph ping-pong a 409 and a
        # reload at each other. See `graph.move` for the whole argument.
        try:
            positions = graph_mod.move(path, moved)
        except StaleFileError as exc:  # pragma: no cover - no caller passes one
            return JSONResponse({"error": str(exc), "stale": True}, status_code=409)
        return {
            "positions": {k: list(v) for k, v in positions.items()},
            "mtime": _mtime(path),
            "path": str(path.relative_to(config.root)),
        }

    @app.post("/api/study-order")
    def study_order_api(body: dict[str, Any] = Body(default={})) -> Any:
        """Reorder the criteria, by writing `[cards] study_order`.

        The one write in this app that lands in `forge.toml`, and the one that
        changes nothing about any card: it decides which approved card Anki
        hands you first, which is a judgement about the deck rather than about
        a card in it. Nothing is re-hashed and nothing is demoted, for the same
        reason drawing an arrow demotes nothing.

        Whether it takes effect straight away is the whole reason `study_order`
        re-reads the file: a control that needs a restart to do anything reads
        as a control that does not work.
        """
        graph_enabled()
        wanted = [str(name).strip() for name in (body.get("order") or []) if str(name).strip()]
        try:
            study.validate(wanted)
        except study.StudyOrderError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        path = save_study_order(config.root, wanted)
        order = study_order(config)
        return {
            "order": list(order),
            "sentence": study.sentence(order),
            "path": str(path.relative_to(config.root)),
        }

    @app.get("/api/projects")
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
        try:
            size = context_size(raw, "pages") if raw is not None else -1
        except ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        # A negative number is how the chip says "inherit again", which is not
        # a size and so never reaches the file.
        pages = None if isinstance(size, int) and size < 0 else size

        def apply(led: Ledger) -> Unit:
            unit = led.get(unit_id)
            if unit is None:
                raise HTTPException(404, f"no unit {unit_id!r}")
            unit.context_pages = pages
            return unit

        # `unit_id`, so the write captures a `before` and undo has something
        # to pop. Without it the server returned an empty snapshot, nothing
        # was recorded, and the next `z` reached past to an older action --
        # on a different unit.
        return _mutate_ledger(config, source, body, apply, unit_id)

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

        # `unit_id`, so the write captures a `before` and undo has something
        # to pop. Without it the server returned an empty snapshot, nothing
        # was recorded, and the next `z` reached past to an older action --
        # on a different unit.
        return _mutate_ledger(config, source, body, apply, unit_id)

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

    @app.post("/api/cards/{uid}/requires")
    def set_requires(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Add or remove one dependency, from the canvas.

        `uid` is the card whose file changes: the one that *needs* something.
        The other end is named in `add` or `remove`. Drawing the arrow from
        either end of the canvas lands here the same way, because the port you
        grabbed decides which card is the dependent before anything is sent.

        `requires` is outside `content_hash` under both the current rule and
        the legacy one, so linking two approved cards demotes neither. That is
        what makes this safe to do by dragging: the order cards are introduced
        in is a judgement about the deck, not a change to any card's content,
        and it was previously authorable only by opening the file.

        Refused *before* the write, rather than reported after by `check`:
        a card that names itself, one that is not in this repo, and one that
        would close a cycle. A file written into a state the lint refuses is a
        worse answer than a refusal at the moment of the drag.
        """
        graph_enabled()
        add = str(body.get("add", "") or "").strip()
        drop = str(body.get("remove", "") or "").strip()
        if bool(add) == bool(drop):
            raise HTTPException(400, "name exactly one of `add` or `remove`")
        if add:
            if add == uid:
                raise HTTPException(400, "a card cannot need itself")
            known = {c.uid for c in _cards(config)}
            if add not in known:
                raise HTTPException(400, f"{add} is not a card in this repo")
            edges = graph_mod.card_graph(_cards(config)).edges
            # Adding `requires: [add]` to `uid` draws `add -> uid`, so it
            # closes a loop exactly when `uid` already leads to `add`.
            loop = graph_mod.route(edges, uid, add)
            if loop:
                raise HTTPException(
                    400,
                    "that would make a cycle: " + " needs ".join(reversed([*loop, uid])),
                )

        def act(card: Card) -> None:
            needs = [n for n in card.requires if n != drop]
            if add and add not in needs:
                needs.append(add)
            if needs:
                card.frontmatter["requires"] = needs
            else:
                card.frontmatter.pop("requires", None)

        return _mutate_card(config, uid, body, act)

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

    @app.post("/api/cards/{uid}/augmented")
    def set_card_augmented(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Record, or withdraw, that `/augment` has been over this card.

        Two states rather than three: a card has had the pass or it has not,
        and there is nothing for it to inherit from. Withdrawing is the way to
        ask for it again, which is why this is a control rather than something
        only an agent writes.
        """
        value = bool(body.get("augmented"))
        return _mutate_card(
            config, uid, body, lambda card: card.set_grade("augmented", value or "")
        )

    @app.post("/api/cards/{uid}/restore")
    def restore_card(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Undo: put a card's status back, with the hash that went with it.

        A `note` in the snapshot is an annotation the undo is putting back,
        which is the one thing resolving deletes and nothing else records. It
        returns to the end of `## notes` rather than to the line it was on:
        the position of a note carries nothing, and reconstructing it would
        mean remembering the whole section to restore one line of it.
        """
        snapshot = body.get("snapshot") or {}
        status = str(snapshot.get("status", ""))
        if status not in model.STATUSES:
            raise HTTPException(400, f"unknown status {status!r}")
        note = str(snapshot.get("note", "")).strip()

        def act(card: Card) -> None:
            card.frontmatter["status"] = status
            digest = str(snapshot.get("content_hash", ""))
            if digest:
                card.frontmatter["content_hash"] = digest
            else:
                card.frontmatter.pop("content_hash", None)
            if note and note not in card.annotations():
                card.add_annotation(note)

        return _mutate_card(config, uid, body, act)

    @app.post("/api/cards/{uid}/resolve")
    def resolve_card_annotation(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Delete one annotation. The app could add a note but never remove
        one, so the only way to finish with a `@me` decision was to open the
        file.

        The line goes back in the response, because for a note that came from
        Anki this file is the only copy there is: `feedback` erases the
        comment as it imports it, by design. Resolving without that was the
        one unrecoverable action in the app.
        """
        index = int(body.get("index", 0))
        return _mutate_card(
            config,
            uid,
            body,
            lambda card: card.resolve_annotation(index),
            remember=lambda card: {"note": _nth_annotation(card, index)},
        )

    @app.post("/api/cards/{uid}/edit-annotation")
    def edit_card_annotation(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        """Reword one annotation, leaving it open.

        Not in the undo stack, for the same reason writing one is not: `restore`
        puts a note *back*, and putting back the line this replaced would leave
        the card carrying both. The way to undo a wording is to edit it again,
        which is the same gesture and costs one click.
        """
        index = int(body.get("index", 0))
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "empty annotation")
        return _mutate_card(config, uid, body, lambda card: card.edit_annotation(index, text))

    @app.post("/api/cards/{uid}/annotate")
    def annotate_card(uid: str, body: dict[str, Any] = Body(...)) -> Any:
        text = str(body.get("text", "")).strip()
        if not text:
            raise HTTPException(400, "empty annotation")
        return _mutate_card(config, uid, body, lambda card: card.add_annotation(text))

    @app.get("/crop/{source}/{unit_id:path}.png")
    def crop(
        request: Request,
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
        # Through the cache: the scrolling document view asks for one of these
        # per page, and re-reading a 751-line ledger fifty-eight times to
        # answer "where is this one unit" is the whole cost of opening it.
        ledger = _ledgers(config).get(source)
        unit = ledger.get(unit_id) if ledger else None
        if unit is None:
            raise HTTPException(404, f"no unit {unit_id!r}")
        geometry = unit.crop_geometry()
        if geometry is None:
            raise HTTPException(404, f"unit {unit_id!r} has no page geometry")
        if width and width not in render_mod.WIDTHS:
            raise HTTPException(400, f"unknown crop width {width!r}")
        width = width or config.crop_width_for(source, from_a_mark=unit.crops_to_page)
        regions = render_mod.regions_for(unit, geometry[0]) if marks else []

        document = config.document_for(source, unit.locator.document)
        if document is None or not document.exists():
            raise HTTPException(
                409,
                f"source document for {source!r} is not here "
                f"({document or 'unset'}); crops are rendered from it on demand",
            )
        def png() -> bytes:
            try:
                return render_mod.render_crop(
                    document,
                    *geometry,
                    context=context,
                    outline=outline,
                    width=width,
                    regions=regions,
                )
            except (render_mod.PdfUnavailable, ValueError) as exc:
                raise HTTPException(409, str(exc)) from exc

        return _rendered(
            request, png, document, source, f"crop|{unit_id}|{context}|{outline}|{width}|{marks}"
        )

    def _rendered(
        request: Request, png_for: Any, document: Path, source: str, tag: str
    ) -> Response:
        """A rendered PNG, with an ETag so looking at it twice costs nothing.

        These were `Cache-Control: no-store`, which is the strongest thing you
        can say and says the wrong thing. A crop is *derived*, not secret, and
        forbidding the browser to keep it meant every crop/page/doc toggle
        re-rendered from the PDF: 103 ms for a full page, every time, for a
        picture the browser had just been shown.

        `no-cache` keeps the opposite promise -- store it, but ask before
        reusing it -- and the ETag makes the asking cheap. It is built from
        everything that can change the image: the document's own mtime, the
        ledger's (geometry and marks live there), and the request's parameters.
        Any of them moves and the tag moves, so a stale picture is not
        reachable; none of them moves and the answer is a 304 in about five
        milliseconds.
        """
        ledger_path = config.units_path(source)
        stamp = (
            document.stat().st_mtime_ns,
            ledger_path.stat().st_mtime_ns if ledger_path.exists() else 0,
            tag,
        )
        etag = '"' + hashlib.sha256(repr(stamp).encode()).hexdigest()[:20] + '"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(png_for(), media_type="image/png", headers=headers)

    def _unit_document(source: str, unit_id: str) -> tuple[Unit, Path]:
        """The unit and the file its geometry refers to, or an HTTP error."""
        ledger_path = config.units_path(source)
        if not ledger_path.exists():
            raise HTTPException(404, f"no ledger for source {source!r}")
        # Through the cache: the scrolling document view asks for one of these
        # per page, and re-reading a 751-line ledger fifty-eight times to
        # answer "where is this one unit" is the whole cost of opening it.
        ledger = _ledgers(config).get(source)
        unit = ledger.get(unit_id) if ledger else None
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
    def page_image(
        request: Request, source: str, unit_id: str, n: int = 1, marks: bool = True
    ) -> Response:
        """One whole page of the unit's document, for the scrolling view.

        The page number is a query parameter rather than another path segment:
        `{unit_id:path}` is greedy and would swallow it, and a unit id already
        contains the colons that make it look like a path.
        """
        from ..extract import render as render_mod

        unit, document = _unit_document(source, unit_id)

        def png() -> bytes:
            try:
                return render_mod.render_page(
                    document,
                    n,
                    regions=render_mod.regions_for(unit, n) if marks else [],
                    # The red box only on the page the unit is actually on.
                    outline=unit.locator.bbox if n == unit.locator.page else None,
                )
            except (render_mod.PdfUnavailable, ValueError) as exc:
                raise HTTPException(409, str(exc)) from exc

        return _rendered(request, png, document, source, f"page|{unit_id}|{n}|{marks}")

    @app.post("/api/cards/{uid}/open")
    def open_in_editor(uid: str) -> Any:
        card = _find_card(config, uid)
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

    # Numbered sections sort numerically -- `2.10` after `2.9` -- and named
    # ones sort in the order the document introduced them. A paper's own
    # sections are titles, not numbers ("Introduction", "A uniform learning
    # bound"), and alphabetising those puts the conclusion in the middle.
    # Insertion order is document order: every ledger is written by a pass that
    # walks pages forwards.
    first_seen = {name: n for n, name in enumerate(by_section)}

    def order(name: str) -> tuple[Any, ...]:
        if name[:1].isdigit():
            return (0, *_section_key(name))
        return (1, first_seen[name]) if name else (2, 0)

    chapters: dict[str, dict[str, Any]] = {}
    for name in sorted(by_section, key=order):
        items = by_section[name]
        split = {state: sum(1 for i in items if state_of(i) == state) for state in states}
        row = {
            # A name, not a placeholder in brackets. `(none)` sat at the top
            # level beside the real chapters and read as one of them; what it
            # actually is, is the units the segmenter could not place.
            "name": name,
            "label": name or "no section",
            "total": len(items),
            "matching": sum(1 for i in items if id_of(i) in shown),
            "states": split,
            "bar": [
                {"state": state, "n": n, "pct": round(100 * n / len(items), 2)}
                for state, n in split.items()
                if n
            ],
        }
        group = chapters.setdefault(
            _chapter_of(name),
            {"chapter": _chapter_of(name), "sections": [], "total": 0, "matching": 0},
        )
        group["sections"].append(row)
        group["total"] += row["total"]
        group["matching"] += row["matching"]

    # Groups keep their chapter; whether a chapter is worth *drawing* as a
    # level is the template's call, and it turns on how many sections are in
    # it. Deciding that here, globally, was wrong: it flattened a book
    # imported as one PDF per chapter -- where each chapter genuinely holds
    # one section and the chapter is the only thing worth filtering by -- and
    # took the chapter filter away with it.
    return list(chapters.values())


# A leading number followed by a separator is the chapter, whatever the source
# spells the rest of the name. `2.4` -> `2` is the Cookbook's form; a paper
# imported from Zotero names its attachments `1 - introduction`, and splitting
# those on `.` gave every section a chapter of its own. A name with no leading
# number -- an attachment simply called `PDF` -- has no chapter, and saying so
# is better than inventing one.
#
# Hyphen first in the class so it is a literal and not a range, and the two
# long dashes as escapes rather than characters -- they are what a title
# generator actually emits, and written literally they read as a typo.
_DASHES = "-\u2013\u2014"
_CHAPTER = re.compile(rf"^\s*(\d+)\s*(?:[{_DASHES}.:]|\s|$)")


def _chapter_of(name: str) -> str:
    found = _CHAPTER.match(name or "")
    return found.group(1) if found else ""


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
    # Queued units with no one-line subject yet. Only queued ones: a gist on
    # a unit nobody has decided about is a sentence written for a card that
    # may never exist.
    counts["ungisted"] = 0
    counts["unaugmented"] = 0
    counts["augmented"] = 0
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

    for name, ledger in _ledgers(config).items():
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
            counts["ungisted"] += unit.state == "queued" and not unit.gist
            counts["annotated"] += bool(unit.notes)
            counts["annotated_me"] += has_annotation(unit.notes, "me")
            counts["annotated_claude"] += has_annotation(unit.notes, "claude")
            counts["unannotated_unit"] += has_annotation(unit.notes, "none")
            counts["annotated_me_unit"] += has_annotation(unit.notes, "me")
            counts["annotated_claude_unit"] += has_annotation(unit.notes, "claude")
    for card in _cards(config):
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
        # Only drafts: `/augment` refuses an approved card, so counting one
        # would be counting work the pass would decline to do.
        counts["unaugmented"] += card.effective_status == "draft" and not card.augmented
        counts["augmented"] += card.augmented
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
        if section and card_section(card, config) != section:
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
    own = None
    for row in rows:
        if row["own"]:
            own = row
            continue
        kind = str(row["kind"]) or "highlight"
        group = groups.setdefault(
            kind,
            {"kind": kind, "label": KIND_GROUPS.get(kind, kind), "marks": [], "tally": {}},
        )
        group["marks"].append(row)
        # What the swatch filter offers, **per group**. One row of colours for
        # the whole list could not say "the green highlights but not the green
        # notes", which is the distinction the groups exist to draw -- and it
        # offered colours that were not in the group you were looking at.
        #
        # Keyed `kind/colour` -- or the kind alone where a mark has none -- so
        # a chip and the row it hides cannot disagree about what it is.
        key = f"{kind}/{row['colour']}" if row["colour"] else kind
        group["tally"][key] = group["tally"].get(key, 0) + 1
    ordered = sorted(groups.values(), key=lambda g: -len(g["marks"]))
    for group in ordered:
        group["count"] = len(group["marks"])
        group["colours"] = [
            {"key": key, "colour": key.partition("/")[2] or key, "count": n}
            for key, n in sorted(group.pop("tally").items(), key=lambda kv: (-kv[1], kv[0]))
        ]
    return {"own": own, "groups": ordered, "count": len(rows)}


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
    scheme = config.zotero_for(unit.project)
    rows: list[dict[str, Any]] = []
    for index, mark in enumerate(unit.marks):
        own = not index
        elsewhere = f"{unit.project}:{mark.key}"
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
# "all of it", not a measurement. `999` means the whole document, and `chapter`
# is the one step that is not a count: between ten pages and the whole book the
# size you want is usually the chapter, and where it starts is a fact about the
# book rather than a number you can guess from here.
CONTEXT_STEPS: tuple[int | str, ...] = (0, 1, 3, 10, CHAPTER, 999)


def context_label(pages: int | str, *, chosen: bool = False) -> str:
    """One step of the context chip.

    The chosen one is written out and the rest are bare numbers, so the chip
    reads as a sentence with the answer in it -- `context: 1 · 3 pages either
    side · 10 · chapter · all` -- rather than as a row of sizes you have to
    decode.

    **"3 pages" means three pages either side**, seven in total: `context.py`
    takes `range(page - n, page + n + 1)`. Saying "3 pages" and handing over
    seven is the kind of quiet mismatch that makes a card writer think they
    have the whole story when they have more of it than they expected, so the
    chosen label spells it out and the tooltip repeats it.
    """
    if pages == CHAPTER:
        return "the chapter it is in" if chosen else "chapter"
    pages = int(pages)
    if pages >= 100:
        return "the whole document" if chosen else "all"
    if pages == 0:
        return "this page only" if chosen else "0"
    if not chosen:
        return str(pages)
    return f"{pages} page{'' if pages == 1 else 's'} either side"


def context_steps(current: int | str) -> list[dict[str, Any]]:
    """Every size, with the one in force written out and marked."""
    return [
        {
            "pages": step,
            "label": context_label(step, chosen=step == current),
            "on": step == current,
        }
        for step in CONTEXT_STEPS
    ]


# What an empty `mark` means, and what `mark=none` means, are different
# questions: nothing selected is "show everything" only because that is the
# resting state of a filter, while an explicit refusal has to be expressible or
# `none` would be a button that silently did nothing.
NO_MARKS = "none"


def marks_wanted(mark: str) -> set[str] | None:
    """The selected cells, or `None` for "not filtering".

    Three states rather than two. `""` is the filter at rest; a list is what to
    keep; and `none` is an explicit empty selection, which shows nothing --
    the symmetric counterpart of `all`, and one click from getting everything
    back. Without it the `none` button would be the only control on the rail
    that did nothing when pressed.
    """
    if not mark:
        return None
    if mark == NO_MARKS:
        return set()
    return {piece for piece in mark.split(",") if piece}


def mark_selection(mark: str) -> set[str]:
    """Which cells are drawn as chosen. An unfiltered grid shows none of them
    chosen rather than all: "no filter" and "every cell ticked" look the same
    in the deck and are different things to click next."""
    return marks_wanted(mark) or set()


def mark_toggle(mark: str, key: str, matrix: dict[str, Any]) -> str | None:
    """The `mark` value a cell's link should carry.

    Adding the first cell to an unfiltered grid selects *only* that one --
    starting from "everything" and removing one would need forty clicks to
    express the common case. Removing the last one goes back to no filter
    rather than to `none`, because an accidental empty deck at the end of a
    click-click-click is worse than the alternative, and `none` is still there
    as a button when you actually mean it.
    """
    chosen = mark_selection(mark)
    if key in chosen:
        chosen = chosen - {key}
    elif not mark or mark == NO_MARKS:
        chosen = {key}
    else:
        chosen = chosen | {key}
    if not chosen:
        return None
    # Every cell selected is the same deck as no filter *only when every unit
    # carries a mark*. On a source where some do not -- which is most of them,
    # since a mark makes a unit and the pages around it come along -- selecting
    # everything still excludes the unmarked ones, and returning `None` made the
    # one live cell a button that did nothing. Compare against the units, not
    # against the cells.
    live = {c["key"] for row in matrix.get("rows", ()) for c in row["cells"] if c["count"]}
    marked = sum(c["count"] for row in matrix.get("rows", ()) for c in row["cells"])
    if chosen >= live and marked >= int(matrix.get("total", marked)):
        return None
    return ",".join(sorted(chosen))


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

    **The whole grid is drawn, not only the part in use.** Every annotation
    kind the scheme reads, against every colour Zotero offers. Building the
    axes from what happened to be marked made the grid change shape between
    two sources and between two filters of one source, so the cell you reached
    for last time was somewhere else -- and it hid the combinations you have
    never used, which is half of what a scheme *is*.

    The number in a cell is **units**, because clicking it filters units and
    a control whose number does not match what it returns is worse than no
    number. A mark that is not a unit still happened, though, and the grid was
    drawing it as though it never had.

    Cells come in four states, and they are four different facts:

    * **declared** -- you said what this combination means. Full strength.
    * **default only** -- it reads as what Zotero's annotation kind is, which
      is not the same as a decision. Still filterable, drawn dashed, and the
      tooltip says so.
    * **marked, no unit here** -- you drew it and no unit in view came from
      it. Not clickable, because the filter would return nothing, but it
      carries the count of marks and says why, and *why* is two different
      answers: `units_from` does not name the pair, so there is never a unit;
      or it does, and the units it made are in another state than the one you
      are looking at. It used to be indistinguishable from a combination
      nobody has ever drawn.
    * **empty** -- nothing in this source is marked that way. Not clickable,
      because a filter that can only ever return nothing is a dead control --
      but still drawn in its own colour, because five identical grey squares
      are five things you cannot tell apart, and finding your way back to the
      purple one is the whole reason the grid is laid out this way.

    Nothing appears for a source with no marks, so the Cookbook's rail is
    unchanged: all of this is Zotero's, and a segmented book has none of it.
    """
    from ..config import DEFAULT_MEANINGS
    from ..zotero import HEX_BY_NAME

    scheme = config.zotero_for(source)
    tally: dict[str, int] = {}
    # Every mark in the source, deduplicated by key, beside the units they
    # made. A mark rides along on every unit within a few pages of it, so
    # counting appearances would report one highlight five times.
    drawn: dict[str, set[str]] = {}
    for unit in units:
        key = unit_mark(unit)
        if key:
            tally[key] = tally.get(key, 0) + 1
        for mark in unit.marks:
            pair = f"{mark.kind}/{mark.colour}" if mark.colour else mark.kind
            drawn.setdefault(pair, set()).add(mark.key)

    # Only combinations the scheme gives a reading to, so a kind Zotero does
    # not define never becomes a row -- the floor under your declarations is
    # Zotero's closed set, not a guess at what "doodle" might have meant.
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    kind_total: dict[str, int] = {}
    colour_total: dict[str, int] = {}
    for key in {*tally, *drawn}:
        kind, _, colour = key.partition("/")
        meaning, where = scheme.reading(kind, colour)
        if not meaning:
            continue
        count = tally.get(key, 0)
        cells[kind, colour] = {
            "key": key,
            "kind": kind,
            "colour": colour,
            "meaning": meaning,
            "declared": where == "declared",
            "count": count,
            "marks": len(drawn.get(key, ())),
            # Whether `units_from` names this pair at all, which is the only
            # scope-free answer to "why is there no unit here". The grid is
            # built from the state you are filtered to, so a green highlight
            # can be a unit in this source and absent from this view.
            "unit_making": scheme.makes_a_unit(kind, colour),
        }
        # The axis totals stay unit counts, because the axis header sits over a
        # column of unit counts and a row total in a different unit of measure
        # is a number nobody can add up.
        kind_total[kind] = kind_total.get(kind, 0) + count
        colour_total[colour] = colour_total.get(colour, 0) + count
    if not cells:
        return {}

    # Both axes in full, and in a **fixed** order: every kind the scheme reads
    # and every colour Zotero offers, plus anything marked that is neither.
    # Sorting by frequency made the grid rearrange itself between two filters
    # of one source, so the cell you reached for last time had moved.
    colours = list(HEX_BY_NAME) + sorted(set(colour_total) - set(HEX_BY_NAME))
    kinds = list(DEFAULT_MEANINGS) + sorted(set(kind_total) - set(DEFAULT_MEANINGS))
    rows = []
    for kind in kinds:
        rows.append({
            "kind": kind,
            "label": KIND_GROUPS.get(kind, kind),
            "count": kind_total.get(kind, 0),
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
                        "marks": 0,
                        "unit_making": scheme.makes_a_unit(kind, colour),
                    },
                )
                for colour in colours
            ],
        })
    return {
        "colours": [{"colour": c, "count": colour_total.get(c, 0)} for c in colours],
        "rows": rows,
        # How many units the grid is *about*, not how many carry a mark. The
        # difference is what makes "every cell selected" mean something: with
        # unmarked units in the deck, selecting every mark is still a filter.
        "total": len(units),
    }


def scheme_rows(units: list[Unit], config: Config, source: str) -> list[dict[str, Any]]:
    """What this source's marks mean, and which of them make units.

    The legend, not the filter. **One row per kind-and-colour pair**, because
    the pair is what decides a meaning: a green highlight and a green underline
    are two marks the reader made deliberately differently, and a row labelled
    just `green` claimed they were one thing. It also used to group by whichever
    config line happened to match, so the same row meant different things in
    two sources depending on how each had been written down.

    Every pair that occurs here, plus every pair declared for this source --
    including ones nothing is marked with yet -- because a declaration you have
    stopped using is worth seeing. And an undeclared pair that *is* used is the
    row that matters most: its meaning exists only in your head, and it reaches
    a card writer as a coloured box with no caption.

    Counted over marks rather than units, deduplicated by key, because a mark
    appears in the neighbour list of every unit near it and counting those
    would report the same highlight five times.
    """
    scheme = config.zotero_for(source)
    seen: dict[tuple[str, str], set[str]] = {}
    for unit in units:
        for mark in unit.marks:
            seen.setdefault((mark.kind, mark.colour), set()).add(mark.key)
    if not seen:
        # Nothing in this source was marked, so there is no scheme in force
        # here. `[zotero.meanings]` is repo-wide and would otherwise render a
        # full colour legend, every count zero, beside a book nobody has ever
        # highlighted -- the rail saying something about a different source.
        return []

    declared = {
        (key.partition("/")[0], key.partition("/")[2]) for key in scheme.meanings
    }
    rows: list[dict[str, Any]] = []
    for kind, colour in {*seen, *declared}:
        meaning, where = scheme.reading(kind, colour)
        rows.append({
            "key": f"{kind}/{colour}" if colour else kind,
            "kind": kind,
            "colour": colour,
            # What it reads as, and whether that is a decision you took or the
            # floor under it. They are not the same claim -- a default says
            # what Zotero's annotation kind *is*, a declaration says what you
            # meant by this kind in this colour -- and the difference is the
            # whole point of showing the scheme rather than just a tally.
            "meaning": meaning,
            "declared": where == "declared",
            "count": len(seen.get((kind, colour), ())),
            "makes_a_unit": scheme.makes_a_unit(kind, colour),
        })
    rows.sort(key=lambda r: (not r["makes_a_unit"], -int(r["count"]), str(r["key"])))
    return rows


def scheme_legend(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The scheme grouped by what it *means*, for the information rail.

    `scheme_rows` is the facts -- one entry per kind-and-colour pair. This is
    how they are read, and the two differ because the interesting structure is
    not the pairs, it is the meanings.

    Zotero gives eight colours and six annotation kinds, so a source can reach
    forty-eight pairs; the rail is 240px wide. But nobody has forty-eight
    *meanings*: several pairs usually share one -- every colour of sticky note
    means "something I thought" -- and a legend that lists those separately is
    printing one sentence eight times and calling it detail.

    Grouping collapses exactly that, and collapses nothing real: two pairs that
    genuinely mean different things stay two rows. Where they land together the
    swatches sit side by side and the sentence is written once. Seeing two
    pairs share a meaning is worth knowing too -- it is usually a scheme you
    have half-changed.

    `makes_a_unit` and `declared` are ORed across the group deliberately. A
    meaning that *any* of its marks turns into units is one you meet in the
    queue, which is what the tag is telling you; and a group with one declared
    pair is not undecided, it is decided and used twice.
    """
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = groups.setdefault(
            str(row["meaning"]),
            {
                "meaning": row["meaning"],
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
        # The short name to lead the row with. You come to this legend holding
        # a mark -- "what does a purple highlight mean" -- so the pair is the
        # lookup key and goes first and narrow; the full text is in the
        # tooltip when several pairs share one meaning.
        group["label"] = " · ".join(str(e["key"]) for e in group["entries"][:2]) + (
            f" +{len(group['entries']) - 2}" if len(group["entries"]) > 2 else ""
        )
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
    spec = config.projects.get(source)
    if spec is None:
        return ""
    if spec.zotero_key:
        return "zotero"
    if spec.pdf:
        return "pdf"
    return "tex" if spec.tex else ""


def project_facts(config: Config, source: str, *, from_marks: bool = False) -> dict[str, Any]:
    """This source's resolved settings, for the information rail.

    The same numbers `/config` lists, for the one source you are actually
    looking at. There was no way to see which layout the card in front of you
    resolved to without leaving the view, and layout decides what every
    derivative on it means.
    """
    from ..context import source_conventions

    spec = config.projects.get(source)
    origin = source_origin(config, source)
    scheme = config.zotero_for(source)
    return {
        # Which marks become units, and *only* for a source that came from
        # Zotero: a segmented book has no marks and no scheme, and showing it
        # one would be the rail describing machinery that is not running.
        "units_from": sorted(scheme.unit_pairs) if origin == "zotero" else [],
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

    Read through the same mtime-keyed cache as everything else, so the gallery
    is free to walk every ledger and every card: it is still derived per
    request, just not re-parsed per request.
    """
    ledgers = _ledgers(config)
    by_source: dict[str, list[Card]] = {}
    for card in _cards(config):
        by_source.setdefault(card.project_name, []).append(card)

    rows: list[dict[str, Any]] = []
    for name in project_names(config):
        spec = config.projects.get(name)
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
        "projects": rows,
        "totals": totals,
        "units": sum(int(r["units"]) for r in rows),
        "cards": sum(int(r["cards"]) for r in rows),
        "tags": sorted({t for r in rows for t in r["tags"]}),
        # Only the origins actually present, so the filter never offers a
        # button that matches nothing.
        "origins": sorted({str(r["origin"]) for r in rows if r["origin"]}),
    }


def card_section(card: Card, config: Config) -> str:
    """Which section of its source a card comes from.

    **Looked up, not parsed.** `Card.section_name` reads the middle segment of
    a unit id, which is a section only for the shape a numbered book produces
    (`matrix-cookbook:2.3:66`). A unit imported from a marked-up PDF is
    `<source>:<annotation key>` and has no section in its name at all, so the
    review rail offered no sections for a paper while the units view offered
    seven -- the same source, filtered two different ways.

    The section is on the unit's locator, which is where extraction put it, so
    the answer is a ledger lookup. It falls back to the parsed form for a card
    whose unit has been re-extracted away, which is the only case where the id
    knows something the ledger does not.
    """
    if not card.unit:
        return card.section_name
    ledger = _ledgers(config).get(card.project_name)
    unit = ledger.get(card.unit) if ledger else None
    return unit.locator.section if unit else card.section_name


def card_gist(card: Card, config: Config) -> str:
    """A few words naming this card, or the empty string.

    The card's own `gist` first. Failing that, the gist of the unit it was
    written from, which answered the same question one stage earlier: a unit's
    gist says what a card from it would be about, and this *is* that card.
    Inherited rather than copied into the file, so re-running `/gist` on the
    unit corrects the label everywhere at once.

    Empty when neither exists, and callers show that as a gap rather than
    inventing a name from the slug. A caption derived from
    `prod-i-lambda-i-where-lambda-i-text-eig` is a transliteration of the
    LaTeX, which is the thing a caption is supposed to spare you.
    """
    if card.gist:
        return card.gist
    if not card.unit:
        return ""
    ledger = _ledgers(config).get(card.project_name)
    unit = ledger.get(card.unit) if ledger else None
    return unit.gist if unit else ""


def source_graph(config: Config, source: str, *, everything: bool = False) -> dict[str, Any]:
    """Everything the canvas draws for one source, laid out and positioned.

    Scoped to a source because that is the only scope where the graph means
    anything: `requires` says "introduce that first", and cards from two books
    are not competing for a place in the same reading.

    A `requires` may still cross sources, and both ends are drawn. Keeping only
    this source's cards would show a card whose foundation is elsewhere as a
    foundation itself, which is the one thing the picture is read for.

    The layout is computed over what is actually shown, so the connected view
    is not the full arrangement with holes in it.
    """
    everywhere = _cards(config)
    here = [c for c in everywhere if card_in_source(c, source)]
    mine = {c.uid for c in here}
    wanted = {n for c in here for n in c.requires} | mine
    foreign = [
        c
        for c in everywhere
        if c.uid not in mine and (c.uid in wanted or mine & set(c.requires))
    ]

    def href(card: Card) -> str:
        where = card.project_name or source
        return filter_url("/review", {}, source=where, status="all") + f"#{card.uid}"

    whole = graph_mod.card_graph(
        here + foreign,
        label=lambda card: card_gist(card, config),
        href=href,
        here=source,
    )
    declared = study_order(config)
    ordered = in_study_order(here, source_positions(config), declared)
    order = [c.uid for c in ordered]
    path = graph_mod.positions_path(config.projects_dir, source)
    positions = graph_mod.load_positions(path)
    # A card with no edges is on the canvas because somebody put it somewhere.
    # That is what "add this one so I can connect it" writes, and it is the
    # only statement of intent there is.
    shown = whole if everything else whole.connected(positions)
    drawn = {n.id for n in shown.nodes}
    return {
        "source": source,
        **shown.as_dict(),
        # Where each node sits before anyone has dragged it, and what has been
        # dragged. Two maps rather than one merged one: the canvas has to be
        # able to put a node back, and a merged map cannot say which of the two
        # a coordinate came from.
        "layout": {k: list(v) for k, v in graph_mod.layered(shown, order).items()},
        "positions": {k: list(v) for k, v in positions.items()},
        "mtime": _mtime(path),
        # Per card, for the stale guard on an edge write. An edge is a write to
        # a card file and gets the same precondition every other card write in
        # this app has: an editor open beside the browser is normal, and silent
        # clobbering is worse than a retry.
        "mtimes": {
            c.uid: str(c.mtime_ns or 0) for c in here + foreign if c.uid in drawn
        },
        "everything": everything,
        "shown": len(shown.nodes),
        # Said out loud on screen. A filtered view that does not report what it
        # left out reads as the whole picture.
        "hidden": len(whole.nodes) - len(shown.nodes),
        "total": len(whole.nodes),
        # What you could put on the canvas: every card in the source that is
        # not drawn. Sent with the picture rather than fetched when the picker
        # opens, because it is the same walk over the same cards and the list
        # has to agree with what is on screen.
        "absent": [n.as_dict() for n in whole.nodes if n.id not in drawn],
        # The queue the picture is a picture of. Every card in the source, not
        # only the drawn ones, because what the canvas leaves out is exactly
        # the cards that depend on nothing.
        "order": study_reading(config, here, ordered, declared, drawn, href),
    }


def study_reading(
    config: Config,
    cards: list[Card],
    ordered: list[Card],
    declared: tuple[str, ...],
    drawn: set[str],
    href: Any,
) -> dict[str, Any]:
    """The study order for one source, with what put each card where.

    The canvas draws `requires`, which is one of the two things deciding this
    order and the only one with a shape. The other is a sort key three values
    long, and it was written down in three places and visible in none of them:
    you could see that a card was 4th of 108 and not why, and you could not see
    what would happen if easiest-first outranked most-useful-first.

    So: the order, each card's values for each criterion, and the places
    `requires` moved it. `shift` is against the order the criteria alone would
    give, positive for earlier, and `owes` names the card that pulled it there.
    Reading those two together is reading the rule work on this deck, which is
    the only way to judge a sort key that has a hundred cards under it.
    """
    positions = source_positions(config)
    criteria = study.resolve(declared)
    # What the criteria alone would do, which is the baseline `shift` is
    # measured against. Not "the order before you last dragged something":
    # the question is what `requires` is contributing, not what changed.
    flat = sorted(cards, key=lambda c: study_key(c, positions, declared))
    without = {card.uid: i for i, card in enumerate(flat)}
    owed = inherited_from(cards, positions, declared)
    labels = {c.uid: card_gist(c, config) for c in cards}
    rows = []
    for place, card in enumerate(ordered):
        ranks = study_values(card, positions)
        shown = {
            "frequency": card.frequency,
            "derivation": card.derivation,
            # A number rather than a word, because that is what it is: how far
            # into the book the unit sits. Empty when the source opted out of
            # its own order, or when this card came from no unit at all.
            "printed": "" if ranks["printed"] >= len(positions) else str(ranks["printed"] + 1),
        }
        values = {c.name: shown.get(c.name, "") for c in criteria}
        rows.append(
            {
                "id": card.uid,
                "label": labels[card.uid],
                "state": card.effective_status,
                "place": place + 1,
                "values": values,
                "shift": without[card.uid] - place,
                "owes": owed.get(card.uid, ""),
                "owes_label": labels.get(owed.get(card.uid, ""), ""),
                "needs": [n for n in card.requires if n in labels],
                # The panel's only filter on itself: a card the canvas is not
                # drawing can be clicked to put it there.
                "drawn": card.uid in drawn,
                "href": href(card),
            }
        )
    return {
        "names": list(declared),
        "criteria": [c.as_dict() for c in criteria],
        "sentence": study.sentence(declared),
        "cards": rows,
    }


def card_in_source(card: Card, source: str) -> bool:
    """Does this card belong to the source the header is scoped to?

    An empty `source` means no scope, so everything belongs. A card whose
    units name no source belongs to all of them: it is misfiled, and the
    view that hides it is worse than the one that shows it twice.
    """
    return not source or card.project_name in ("", source)


def project_names(config: Config) -> list[str]:
    """Everything the dropdown may offer: configured sources and any ledger on
    disk, so a source extracted but not yet in the TOML (or the reverse) is
    still reachable.

    In TOML order, not alphabetical, because the first one is the default and
    that should be a choice you make by editing `forge.toml` rather than
    an accident of spelling. Ledgers with no `[projects.*]` entry follow.
    """
    names = list(config.projects)
    names += sorted(set(_ledgers(config)) - set(names))
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
    # The one row here the app can also write, from the panel on the canvas.
    # Read live rather than off `config`, so the table does not contradict the
    # panel between here and the next restart.
    add("repo", "study_order", ", ".join(study_order(config)), "forge.toml")
    add("repo", "crop_context", config.crop_context_for(""), "forge.toml")
    add(
        "repo",
        "crop_width",
        config.crop_width or "page for marks, box for the rest",
        "forge.toml" if config.crop_width else "by where the geometry came from",
    )
    add("repo", "context_pages", config.context_pages, "forge.toml")
    add("repo", "web", "allowed" if config.web else "off", "forge.toml")
    add(
        "app",
        "graph",
        "the dependency canvas is on" if config.graph else "off",
        "forge.toml",
    )
    add("anki", "deck", config.deck, "forge.toml")
    add("anki", "note type", config.note_type, "forge.toml")
    add("anki", "tag prefix", config.tag_prefix, "forge.toml")
    add("anki", "url", config.anki_url, "ANKI_CONNECT_URL or forge.toml")
    # Which colours mean something. A flag with no entry is reported by
    # `feedback` and imported by nothing, so "what did I map?" is a question
    # with a consequence, and the answer was only in the file.
    add(
        "anki",
        "flags",
        (
            ", ".join(f"{n} {text}" for n, text in sorted(config.flags.items()))
            or "none declared; a flag set in Anki comes back as a skip"
        ),
        "forge.toml",
    )
    add("zotero", "data dir", str(config.zotero.data_dir), "forge.toml")
    add(
        "zotero",
        "units from",
        ", ".join(sorted(config.zotero.unit_pairs)),
        "forge.toml"
        + (" · every declared mark" if DECLARED in config.zotero.units_from else ""),
    )

    for name, spec in config.projects.items():
        where = f"source: {name}"
        origin = f"projects/{name}/project.toml"
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
            origin if context_asked(spec.context_pages) else inherited,
        )
        if spec.tags:
            add(where, "tags", ", ".join(spec.tags), origin)
        for card_type, deck in sorted(spec.decks.items()):
            add(where, f"deck [{card_type}]", deck, origin)
        scheme = config.zotero_for(name)
        if scheme.unit_pairs:
            add(
                where,
                "units from",
                ", ".join(sorted(scheme.unit_pairs)),
                (origin if spec.units_from else inherited)
                + (" · every declared mark" if DECLARED in scheme.units_from else ""),
            )
        # The whole colour scheme, **here** rather than in the rail. The rail
        # is 240px and shows only the marks that become units, because a
        # meaning is an arbitrary sentence and a source may declare forty of
        # them. This panel is a full-width dialog and is where you come to ask
        # what something resolves to, so the complete mapping belongs in it --
        # including the entries nothing in this source is marked with, which
        # the rail cannot show at all.
        for key in sorted({*scheme.meanings, *DEFAULT_MEANINGS}):
            kind, _, colour = key.partition("/")
            meaning = scheme.means(kind, colour)
            if not meaning:
                continue
            declared = key in scheme.meanings
            add(
                where,
                f"means [{key}]",
                meaning + (" · becomes a unit" if scheme.makes_a_unit(kind, colour) else ""),
                origin
                if declared and key in (spec.meanings or {})
                else "forge.toml"
                if declared
                else "Zotero's own reading of the annotation kind",
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
    src, sec = flag("--project", source), flag("--section", section)
    scope = sec or " --all"
    out: list[dict[str, str]] = []

    if view == "units":
        if from_marks:
            # Not "a mark carries its own text", which this said and which is
            # false for the two cases you would actually want transcribed: a
            # boxed region carries no text at all, and a highlight over a
            # display equation carries the PDF's mangled text layer. What is
            # true is the thing invariant 9 says -- you do not need a
            # transcription to *triage*. If one unit turns out to want LaTeX
            # beside it, that is one command on that unit.
            out.append({
                "kind": "note",
                "label": "no transcription pass here — triage reads the crop and the mark",
                "run": "",
            })
            out.append({
                "kind": "note",
                "label": "one unit that wants LaTeX anyway: forge units --id <id> --tex-auto '...'",
                "run": "",
            })
        elif counts.get("new"):
            out.append({
                "label": f"read the crops — {counts['new']} still untranscribed",
                "why": "so triage shows the maths written out instead of a"
                " picture to squint at. A hint only: the crop stays the"
                " authority.",
                "run": f"/transcribe{src}{scope}",
                "kind": "claude",
            })
            out.append({
                "label": "propose which of them to skip",
                "why": "fragments, headings, notation-table rows. It only"
                " proposes — every suggestion waits for you, and nothing may"
                " propose skipping a numbered equation.",
                "run": f"/classify{src}{scope}",
                "kind": "claude",
            })
        if counts.get("ungisted"):
            out.append({
                "label": f"name {counts['ungisted']} queued units in a line each",
                "why": "one line saying what a card from each would be about,"
                " so the list, the graph and every link to a card read as"
                " something rather than as a uid. Cheap, and it makes the"
                " stub-writing pass easier to check.",
                "run": f"/gist{src}{sec}",
                "kind": "claude",
            })
        if counts.get("queued"):
            out.append({
                "label": f"write stubs for {counts['queued']} queued",
                "why": "reads the page each unit came from and your @claude"
                " brief, and writes a draft. Approving is still yours.",
                "run": f"/extract-cards{src}{sec}",
                "kind": "claude",
            })
        out.append({
            "label": "this list, as JSON",
            "why": "the same units this filter is showing, for a script or a"
            " subagent. Read from this rather than from the printed output.",
            "run": (
                f"uv run forge units{src}"
                f" --state {filters.get('state') or 'all'}{sec} --json"
            ),
            "kind": "shell",
        })
    else:
        # Offered on what is *left*. A card records that the pass has been
        # over it, so the panel can stop suggesting a second opinion about
        # cards that already got one.
        if counts.get("unaugmented"):
            out.append({
                "label": f"augment {counts['unaugmented']} drafts nobody has been over",
                "why": "adds conditions, a proof where it earns its place, the"
                " gradings. Run it before approving, not after: augmenting an"
                " approved card sends it back to draft.",
                "run": f"/augment{src}",
                "kind": "claude",
            })
        if counts.get("annotated_claude_card"):
            out.append({
                "label": f"{counts['annotated_claude_card']} open requests",
                "why": "works the @claude notes and deletes each line it has"
                " acted on. Every one of them is holding a card out of sync"
                " until it goes.",
                "run": f"/triage claude{src}",
                "kind": "claude",
            })
        if counts.get("approved"):
            out.append({
                "label": "check the maths numerically",
                "why": "runs the `## verify` snippets — opt-in, and it caught"
                " three errors in the source. Never reaches Anki.",
                "run": f"uv run forge verify{src}",
                "kind": "shell",
            })
        out.append({
            "label": "what would reach Anki",
            "why": "a rehearsal: approved cards only, nothing written, and it"
            " names every card it would skip and why.",
            "run": "uv run forge sync --dry-run",
            "kind": "shell",
        })
        # The one flow *back*. Offered on every review page rather than on a
        # count, because nothing here can know you left a comment in Anki
        # last night -- and until this runs, that comment is not a note on any
        # card and no list in this app is showing it.
        out.append({
            "label": "pull what you wrote in Anki",
            "why": "a comment or a flag you left while reviewing becomes an"
            " @claude note on the card, and is erased in Anki as it is taken:"
            " after this the line here is the only copy.",
            "run": "uv run forge feedback",
            "kind": "shell",
        })
    return out


def resolve_source(config: Config, source: str) -> str:
    """The source actually in force. An unknown or absent name falls back
    to the first, so a stale link lands somewhere real rather than on an
    empty deck.

    `project_names` includes a source configured in `forge.toml` with nothing
    extracted yet, which is the case worth naming: it *is* a source, so it
    resolves to itself and its view comes up empty rather than silently showing
    a different book under its name. Only a name that is not a source at all
    falls back.
    """
    names = project_names(config)
    if source in names:
        return source
    return names[0] if names else ""


# -- reading the files, once per change rather than once per click ----------
#
# Every interaction in this app re-derived the world from disk. A single card
# click ran `check_repo` *and* `pipeline_counts`, which is 109 markdown files
# parsed twice and every formula on them put through KaTeX; the counts poll
# did the same every four seconds, and all of it is CPU-bound Python holding
# one GIL, so a click arriving mid-poll queued behind it. Measured on this
# repo: 111 ms to lint, 96 ms to load the cards, 120 ms for the counts.
#
# It stays a view over files (invariant 2) because the key is the files
# themselves. Stat-ing all 109 cards costs **4.4 ms** against 96 ms to parse
# them, and any write -- from this app, from an editor, from a subagent
# running `forge new` in another terminal -- moves an mtime and misses the
# cache. Nothing is invalidated by hand, so nothing can forget to.
#
# Size joins mtime in the signature because mtime resolution is a filesystem
# property and not all of them are fine-grained; two writes inside one tick
# that also happen to preserve every byte count is not a case worth losing
# sleep over.
_CACHE: dict[str, tuple[Any, Any]] = {}


def _signature(paths: Any) -> tuple[Any, ...]:
    """What the files look like from the outside, cheaply."""
    out = []
    for path in sorted(paths):
        try:
            info = path.stat()
        except OSError:
            # Vanished mid-walk: an editor writing atomically. Treat it as a
            # change rather than crashing, which is what it is.
            out.append((str(path), -1, -1))
        else:
            out.append((str(path), info.st_mtime_ns, info.st_size))
    return tuple(out)


def _cached(key: str, paths: Any, build: Any) -> Any:
    signature = _signature(paths)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == signature:
        return hit[1]
    value = build()
    _CACHE[key] = (signature, value)
    return value


def study_order(config: Config) -> tuple[str, ...]:
    """The declared study order, as `forge.toml` says it right now.

    The rest of the config is read once at startup and stays read: a server
    holding a `Config` from three minutes ago is a server that agrees with
    itself, and the stale banner covers the case where that is wrong.

    This one value is different because **this app writes it**. The panel on
    the canvas reorders the criteria, the write lands in `forge.toml`, and a
    reordering that does not reorder anything until the next restart is a
    control that appears not to work. So it is re-read, keyed on the file's
    mtime, which costs one `stat` on the requests that ask.

    A config that will not parse falls back to the loaded value rather than
    raising. The setting being edited under the server is exactly when the
    file is half-written, and taking the view down for it would be reporting
    somebody's editor rather than their config.
    """
    from ..config import config_path

    path = config_path(config.root)
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return config.study_order
    hit = _ORDER.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
        order = tuple(
            c.name for c in study.resolve(list(raw.get("cards", {}).get("study_order") or ()))
        )
    except (OSError, tomllib.TOMLDecodeError, study.StudyOrderError, TypeError):
        order = config.study_order
    _ORDER[path] = (stamp, order)
    return order


_ORDER: dict[Path, tuple[int, tuple[str, ...]]] = {}


def _ledgers(config: Config) -> dict[str, Ledger]:
    return _cached(
        f"ledgers:{config.projects_dir}",
        config.projects_dir.rglob("units.jsonl"),
        lambda: open_ledgers(config.projects_dir),
    )


# One parsed card per file, kept until that file changes. Editing one card
# should cost one parse, not 109: `check_repo` re-read the whole deck, and so
# did `model.find` looking for the uid, so a single grading click parsed every
# file in the repo twice -- 200 ms of the 246 a click took.
_PARSED: dict[Path, tuple[tuple[int, int], Card]] = {}


def _parse_deck(config: Config) -> tuple[list[Card], list[check.Finding]]:
    """`check.check_repo`, re-parsing only what moved.

    Deliberately the same shape as `check_repo` -- same walk, same tolerance
    of an unparseable file, same sort, same `check_deck` -- because the two
    must not disagree about what the deck contains. `test_app` asserts they
    agree on this repo, which is the guard against this drifting into a second
    implementation of the loader.

    The lint itself is not cached and does not need to be: it is 19 ms over
    the parsed cards, against 97 ms to parse them. And it cannot be cached per
    file anyway -- duplicate uids and dangling `requires` are facts about the
    deck, not about one card in it.
    """
    cards: list[Card] = []
    findings: list[check.Finding] = []
    seen: set[Path] = set()
    paths = sorted(config.cards_dir.rglob("*.md")) if config.cards_dir.exists() else []
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            continue
        signature = (info.st_mtime_ns, info.st_size)
        seen.add(path)
        hit = _PARSED.get(path)
        if hit is not None and hit[0] == signature:
            cards.append(hit[1])
            continue
        try:
            card = model.load(path)
        except model.CardError as exc:
            findings.append(check.Finding(check.ERROR, "unparseable", str(exc), path=path))
            _PARSED.pop(path, None)
            continue
        _PARSED[path] = (signature, card)
        cards.append(card)
    for gone in set(_PARSED) - seen:
        del _PARSED[gone]
    cards.sort(key=lambda c: (c.uid, str(c.path)))
    findings.extend(check.check_deck(cards, config))
    return cards, findings


def _checked(config: Config) -> tuple[list[Card], list[check.Finding]]:
    """Every card, parsed and linted at most once per edit.

    One entry, not two. `check_repo` already returns the cards it parsed, and
    a card click used to call it *and* `pipeline_counts` -- reading all 109
    files twice for one keystroke. Sharing the result makes the lint the only
    cost, instead of an extra parse on top of it.

    It is also the more forgiving loader: an unparseable file is reported
    rather than taking the whole view down with it. A card that cannot be
    parsed cannot be counted either, so the two agree about what matters.
    """
    return _cached(
        f"check:{config.cards_dir}",
        config.cards_dir.rglob("*.md"),
        lambda: _parse_deck(config),
    )


def _find_card(config: Config, uid: str) -> Card | None:
    """The card with this uid, read fresh from disk.

    Two steps on purpose. Finding it is a lookup over the shared parse, which
    is free; `model.find` walked and parsed the deck until it hit a match, at
    100 ms a call. Reading it is then one file, because this is what the write
    path is about to modify and it must be what is on disk right now -- a
    shared object would be both stale and, once mutated, visible to every
    other request.
    """
    for card in _cards(config):
        if card.uid == uid and card.path is not None:
            return model.load(card.path)
    return None


def _cards(config: Config) -> list[Card]:
    """Every card, from the shared parse.

    **Callers must not mutate what comes back.** It is shared, so a card object
    changed in place would be read by the next request as though the file had
    said so -- which would break invariant 2 quietly and in the worst possible
    direction. Everything that writes goes through `_mutate_card`, which loads
    its own copy with `model.find`.
    """
    return _checked(config)[0]


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
    url = f"/crop/{quote(unit.project)}/{quote(unit.id, safe='')}.png"
    return f"{url}?context={context:g}&outline=1" if context else url


def _unit_payload(
    unit: Unit, config: Config, known: set[str] | None = None
) -> dict[str, Any]:
    image = crop_url(unit, context=pdf_context(config, unit.project))
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
        "context_pages": config.context_pages_for(unit.project, unit.context_pages),
        "context_steps": context_steps(
            config.context_pages_for(unit.project, unit.context_pages)
        ),
        "context_own": unit.context_pages is not None,
        # Whether whoever writes this card may look things up, resolved the
        # same way and shown the same way: the answer, and whose answer it is.
        "web": config.web_for(unit.project, unit.web),
        "web_own": unit.web is not None,
    }


def _card_payload(
    card: Card,
    findings: list[check.Finding],
    config: Config,
    place: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mine = [f.as_dict() for f in check.findings_for(findings, card)]
    # The annotations are listed on this card as rows with a resolve button on
    # each. `annotation-open` prints the first one's text again, one block
    # above them and in the linter's voice, which reads as a note nobody
    # remembers writing -- and the banner above already says what an open note
    # costs. It stays in `forge check`, where nothing else shows the line.
    shown = [f for f in mine if f["code"] != "annotation-open"]
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
        # A few words naming the card, for anywhere the LaTeX front is
        # unreadable: a list, a graph node, a link to it from another card.
        "gist": card_gist(card, config),
        "gist_own": bool(card.gist),
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
        # The prose somebody left on the card, which is neither an open
        # request nor a record of a settled one. Invariant 7 puts real content
        # here ("note any condition you add that the source does not state"),
        # so it stays visible and is not folded away with the history.
        "plain_notes": "\n".join(
            line
            for line in (card.section("notes") or "").splitlines()
            if not model.annotation_audience(line) and not model.is_resolved(line)
        ).strip(),
        # What was asked of this card and what was done about it, oldest
        # first. Folded away by default: it is the answer to "why is this
        # different from what I remember", a question you only ask sometimes.
        "resolved": [model.resolved_body(line) for line in card.resolved()],
        "notes": card.section("notes") or "",
        "annotations": [
            {"text": _note_text(n), "audience": model.annotation_audience(n)}
            for n in card.annotations()
        ],
        "findings": shown,
        # Over everything `check` said, not only what is on screen: the number
        # answers "is this card clean", and hiding a row must not change it.
        "errors": sum(1 for f in mine if f["level"] == check.ERROR),
        "augmented": card.augmented,
        # Whether this card carries a picture. A label, not a filter: it says
        # what you are looking at while you look at it, and nobody works
        # through the pile of cards that have one.
        "has_image": card.has_image,
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
    source = card.project_name
    unit = None
    if card.unit:
        path = config.units_path(source)
        if path.exists():
            found = (_ledgers(config).get(source) or Ledger(path)).get(card.unit)
            unit = found.web if found else None
    return config.web_for(source, unit)


def _unit_image(card: Card, config: Config) -> str:
    """The originating unit's crop, which is the fastest way to settle whether
    a card is wrong (DESIGN.md §6).

    **The same crop triage looked at**: the page around the box, an outline on
    it, and the marks painted back on. The aside used to cut it to the box
    alone, on the argument that a picture this size is provenance rather than
    evidence. It is not. The question you ask beside a draft is the one you
    asked at triage, and a tight box answers it with a single line of a page.

    One URL, used for the strip and for what opens when you click it, so
    opening it is the picture the browser already has rather than a second
    render of a different framing.
    """
    if not card.unit:
        return ""
    source = card.unit.split(":", 1)[0]
    ledger_path = config.units_path(source)
    if not ledger_path.exists():
        return ""
    unit = (_ledgers(config).get(source) or Ledger(ledger_path)).get(card.unit)
    if unit is None:
        return ""
    return crop_url(unit, context=pdf_context(config, source))


# -- writes ----------------------------------------------------------------


def _nth_annotation(card: Card, index: int) -> str:
    """The line `resolve_annotation(index)` is about to delete, or "".

    Out of range rather than raising: the write itself reports that, and this
    runs before it.
    """
    notes = card.annotations()
    return notes[index] if 0 <= index < len(notes) else ""


def _mutate_card(
    config: Config,
    uid: str,
    body: dict[str, Any],
    action: Any,
    remember: Any = None,
) -> Any:
    card = _find_card(config, uid)
    if card is None or card.path is None:
        raise HTTPException(404, f"no card {uid}")
    expected = _expected_mtime(body)
    # What undo needs: approving stamps `content_hash` and rejecting drops it,
    # so restoring the status alone would leave the card in a state it was
    # never actually in. `remember` adds whatever else this particular write
    # destroys, read before it happens and sent back under `before` with the
    # rest -- which is what lets `restore` stay the single undo endpoint.
    before = {
        "status": card.status,
        "content_hash": card.frontmatter.get("content_hash", ""),
    }
    if remember is not None:
        before.update(remember(card))
    action(card)
    try:
        card.save(expect_mtime_ns=expected)
    except StaleFileError as exc:
        return JSONResponse({"error": str(exc), "stale": True}, status_code=409)
    _, findings = _checked(config)
    return {
        "card": _card_payload(model.load(card.path), findings, config),
        "before": before,
        # Scoped to the view, not to the card: the review page may legitimately
        # be showing every source, and the rail beside it has to agree with
        # what it is showing rather than with what was just clicked.
        "pipeline": pipeline_counts(config, _scope(body)),
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
        # So the filter rail can follow the decision without a page load --
        # scoped to whatever the view is showing. Unscoped, every action
        # replaced one source's counts with the whole repo's: a card graded on
        # a fifteen-unit paper made the rail jump to 127 carded and 108
        # approved, which is a number about a different book.
        "pipeline": pipeline_counts(config, _scope(body, source)),
    }


def _scope(body: dict[str, Any], fallback: str = "") -> str:
    """Which source the counts in a write's response are about.

    The browser sends it, because the *view* owns the question: a units page
    is always scoped to one source, a review page may be scoped to one or to
    all of them, and the server cannot tell which from the object being
    written. `fallback` is for the ledger routes, where the source is already
    in the path and an older client that sends nothing still gets it right.
    """
    scope = str(body.get("scope", "") or "")
    return scope or fallback


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
