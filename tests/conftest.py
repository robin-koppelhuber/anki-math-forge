"""Shared fixtures. No test touches the network: AnkiConnect and OCR are both
faked in-process (DESIGN.md §12)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from anki_forge import config as config_mod
from anki_forge.anki import AnkiConnect, AnkiError
from anki_forge.config import Config

CONFIG_TOML = """
[repo]
cards_dir = "cards"
sources_dir = "sources"

[cards]
language = "en"
layout = "denominator"
front_char_cap = 160

[anki]
url = "http://127.0.0.1:8765"
deck = "Test::Matrix Calculus"
note_type_version = 1
tag_prefix = "forge"

[app]
katex_base = "/static/vendor/katex"

[sources.demo]
title = "Demo Source"
citation = "Demo"
tex = "sources/demo/demo.tex"
"""

GOOD_CARD = """---
uid: 7f3a2b
type: identity
status: draft
source: "Demo §2.4, eq. 61"
unit: "demo:2.4:61"
tags: [matrix-calculus, derivatives]
verify: false
---

## front
$\\frac{\\partial}{\\partial X} \\log \\det X$

## back
$X^{-\\top}$

## conditions
$X$ invertible. Denominator layout.

## prose
The matrix analogue of $(\\log x)' = 1/x$.
"""

DEMO_TEX = r"""
\documentclass{article}
\begin{document}
\section{Basics}
Some prose about traces and norms.
\begin{equation}
\operatorname{tr}(AB) = \operatorname{tr}(BA)
\end{equation}

\subsection{Derivatives}
The determinant identity everyone forgets. % a comment
\begin{equation}
\frac{\partial}{\partial X}\log\det X = X^{-\top}
\end{equation}

\begin{align}
\frac{\partial}{\partial X} \operatorname{tr}(AX) &= A^\top \\
\frac{\partial}{\partial X} \operatorname{tr}(X^\top A X) &= (A + A^\top) X
\end{align}

\begin{equation*}
\text{this one is unnumbered}
\end{equation*}
\end{document}
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "anki-forge.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (tmp_path / "cards").mkdir()
    (tmp_path / "sources" / "demo").mkdir(parents=True)
    (tmp_path / "sources" / "demo" / "demo.tex").write_text(DEMO_TEX, encoding="utf-8")
    return tmp_path


@pytest.fixture
def config(repo: Path) -> Config:
    return config_mod.load(repo)


@pytest.fixture
def card_path(repo: Path) -> Path:
    path = repo / "cards" / "7f3a2b-log-det.md"
    path.write_text(GOOD_CARD, encoding="utf-8")
    return path


fitz = pytest.importorskip("fitz", reason="needs the `pdf` extra: uv sync --extra pdf")

BODY_X = 72.0
EQUATION_X = 250.0


def build_pdf(path: Path) -> None:
    """Two pages of body text with numbered display equations between them."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((BODY_X, 100), "2.4 Derivatives of determinants", fontsize=13)
    page.insert_text((BODY_X, 130), "The determinant identity everyone forgets.", fontsize=11)
    page.insert_text(
        (EQUATION_X, 170),
        "d/dX log det X = X^-1 + (A + B)^-1                       (61)",
        fontsize=11,
    )
    page.insert_text((BODY_X, 210), "and a second paragraph of ordinary prose.", fontsize=11)
    page.insert_text(
        (EQUATION_X, 250),
        "tr(AB) = tr(BA) = sum_i sum_j a_ij b_ji                  (62)",
        fontsize=11,
    )

    page = doc.new_page(width=595, height=842)
    page.insert_text((BODY_X, 100), "3.1 Traces", fontsize=13)
    page.insert_text((BODY_X, 130), "Nothing but prose on this part of the page.", fontsize=11)
    doc.save(str(path))
    doc.close()


@pytest.fixture
def pdf_source(repo: Path) -> Config:
    """A repo with a PDF-backed source registered alongside the tex one."""
    (repo / "sources" / "book").mkdir(parents=True)
    build_pdf(repo / "sources" / "book" / "book.pdf")
    toml = (repo / "anki-forge.toml").read_text(encoding="utf-8")
    toml += '\n[sources.book]\ntitle = "A Book"\ncitation = "Book"\npdf = "sources/book/book.pdf"\n'
    (repo / "anki-forge.toml").write_text(toml, encoding="utf-8")
    return config_mod.load(repo)


class FakeAnki(AnkiConnect):
    """An in-memory Anki. Subclasses the real client so the wrappers, the
    query strings and the response shapes are all exercised for real."""

    def __init__(self) -> None:
        super().__init__("http://fake")
        self.decks: list[str] = ["Default"]
        self.models: dict[str, list[str]] = {}
        self.templates: dict[str, dict[str, dict[str, str]]] = {}
        self.css: dict[str, str] = {}
        self.notes: dict[int, dict[str, Any]] = {}
        # One card per note, which is what this note type produces. A new
        # card's `due` is its position in the new queue, counting up from
        # wherever the collection already was.
        self.cards: dict[int, dict[str, Any]] = {}
        self.calls: list[str] = []
        self._next_id = 1000
        self._next_position = 1
        # Set to an action name to make it raise, for the paths where a write
        # to Anki fails after the file has already been changed.
        self.fail_on: str | None = None

    def invoke(self, action: str, **params: Any) -> Any:
        self.calls.append(action)
        if action == self.fail_on:
            raise AnkiError(f"{action} refused (test)")
        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            raise AssertionError(f"unexpected AnkiConnect action {action!r}")
        return handler(**params)

    # -- actions ----------------------------------------------------------
    def _do_version(self) -> int:
        return 6

    def _do_deckNames(self) -> list[str]:
        return list(self.decks)

    def _do_createDeck(self, deck: str) -> int:
        if deck not in self.decks:
            self.decks.append(deck)
        return 1

    def _do_modelNames(self) -> list[str]:
        return list(self.models)

    def _do_modelFieldNames(self, modelName: str) -> list[str]:
        return list(self.models[modelName])

    def _do_createModel(self, **spec: Any) -> dict[str, Any]:
        self.models[spec["modelName"]] = list(spec["inOrderFields"])
        self.templates[spec["modelName"]] = {
            t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in spec["cardTemplates"]
        }
        self.css[spec["modelName"]] = spec.get("css", "")
        return {"id": 1}

    def _do_modelTemplates(self, modelName: str) -> dict[str, Any]:
        return self.templates.get(modelName, {})

    def _do_modelStyling(self, modelName: str) -> dict[str, Any]:
        return {"css": self.css.get(modelName, "")}

    def _do_updateModelTemplates(self, model: dict[str, Any]) -> None:
        self.templates[model["name"]] = {
            k: dict(v) for k, v in model["templates"].items()
        }

    def _do_updateModelStyling(self, model: dict[str, Any]) -> None:
        self.css[model["name"]] = model["css"]

    def _do_findNotes(self, query: str) -> list[int]:
        model = _quoted(query, "note")
        uid = _quoted(query, "uid")
        return [
            note_id
            for note_id, note in self.notes.items()
            if (model is None or note["model"] == model)
            and (uid is None or note["fields"].get("uid") == uid)
        ]

    def _do_notesInfo(self, notes: list[int]) -> list[dict[str, Any]]:
        return [
            {
                "noteId": note_id,
                "modelName": self.notes[note_id]["model"],
                "tags": list(self.notes[note_id]["tags"]),
                "fields": {
                    name: {"value": value, "order": i}
                    for i, (name, value) in enumerate(self.notes[note_id]["fields"].items())
                },
            }
            for note_id in notes
            if note_id in self.notes
        ]

    def _do_addNote(self, note: dict[str, Any]) -> int:
        self._next_id += 1
        self.notes[self._next_id] = {
            "model": note["modelName"],
            "deck": note["deckName"],
            "fields": dict(note["fields"]),
            "tags": list(note["tags"]),
        }
        self.cards[self._next_id] = {
            "cardId": self._next_id,
            "note": self._next_id,
            "deck": note["deckName"],
            "uid": note["fields"].get("uid", ""),
            "type": 0,
            "queue": 0,
            "flags": 0,
            "due": self._next_position,
        }
        self._next_position += 1
        return self._next_id

    def note_by_uid(self, uid: str) -> tuple[int, dict[str, Any]]:
        return next(
            (nid, n) for nid, n in self.notes.items() if n["fields"].get("uid") == uid
        )

    def set_feedback(self, uid: str, html: str) -> None:
        self.notes[self.note_by_uid(uid)[0]]["fields"]["Feedback"] = html

    def get_feedback(self, uid: str) -> str:
        return self.note_by_uid(uid)[1]["fields"].get("Feedback", "")

    def set_flag(self, uid: str, flag: int) -> None:
        self.cards_by_uid(uid)["flags"] = flag

    def _do_modelFieldAdd(self, modelName: str, fieldName: str, index: int) -> None:
        fields = self.models[modelName]
        fields.insert(index, fieldName)

    def cards_by_uid(self, uid: str) -> dict[str, Any]:
        return next(c for c in self.cards.values() if c["uid"] == uid)

    def _do_findCards(self, query: str) -> list[int]:
        deck = query.split('deck:"', 1)[-1].rstrip('"') if 'deck:"' in query else ""
        return [c["cardId"] for c in self.cards.values() if not deck or c["deck"] == deck]

    def _do_cardsInfo(self, cards: list[int]) -> list[dict[str, Any]]:
        return [
            {
                "cardId": c["cardId"],
                "type": c["type"],
                "queue": c["queue"],
                "due": c["due"],
                "flags": c.get("flags", 0),
                "note": c["note"],
                "deckName": c["deck"],
                "fields": {"uid": {"value": c["uid"], "order": 0}},
            }
            for cid in cards
            if (c := self.cards.get(cid)) is not None
        ]

    def _do_setSpecificValueOfCard(
        self, card: int, keys: list[str], newValues: list[Any], warning_check: bool = False
    ) -> list[bool]:
        assert warning_check, "AnkiConnect refuses this without the flag"
        for key, value in zip(keys, newValues, strict=True):
            self.cards[card][key] = value
        return [True]

    def _do_updateNoteFields(self, note: dict[str, Any]) -> None:
        self.notes[note["id"]]["fields"].update(note["fields"])

    def _do_addTags(self, notes: list[int], tags: str) -> None:
        for note_id in notes:
            for tag in tags.split():
                if tag not in self.notes[note_id]["tags"]:
                    self.notes[note_id]["tags"].append(tag)

    def _do_removeTags(self, notes: list[int], tags: str) -> None:
        for note_id in notes:
            self.notes[note_id]["tags"] = [
                t for t in self.notes[note_id]["tags"] if t not in tags.split()
            ]


def _quoted(query: str, key: str) -> str | None:
    match = re.search(rf'"{key}:([^"]*)"', query)
    return match.group(1) if match else None


@pytest.fixture
def anki() -> FakeAnki:
    return FakeAnki()
