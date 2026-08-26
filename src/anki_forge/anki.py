"""AnkiConnect client (DESIGN.md §9).

Thin on purpose: one `invoke`, a few named wrappers, no model of Anki's world
beyond what sync needs. Talks to localhost over urllib -- no extra dependency,
and nothing here reaches the network in tests (AnkiConnect is mocked).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

API_VERSION = 6
TIMEOUT = 15.0


class AnkiError(Exception):
    """AnkiConnect refused, or is not listening."""


class AnkiConnect:
    def __init__(self, url: str, timeout: float = TIMEOUT) -> None:
        self.url = url
        self.timeout = timeout

    def invoke(self, action: str, **params: Any) -> Any:
        payload = json.dumps({"action": action, "version": API_VERSION, "params": params})
        request = urllib.request.Request(
            self.url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AnkiError(
                f"cannot reach AnkiConnect at {self.url} ({exc.reason}). "
                "Is Anki running with the AnkiConnect add-on installed?"
            ) from exc
        except (TimeoutError, ValueError) as exc:
            raise AnkiError(f"AnkiConnect returned something unusable: {exc}") from exc

        if isinstance(body, dict) and body.get("error"):
            raise AnkiError(f"{action}: {body['error']}")
        if not isinstance(body, dict) or "result" not in body:
            raise AnkiError(f"{action}: malformed response {body!r}")
        return body["result"]

    # -- the handful of calls sync makes ----------------------------------
    def version(self) -> int:
        return int(self.invoke("version"))

    def deck_names(self) -> list[str]:
        return [str(d) for d in self.invoke("deckNames")]

    def create_deck(self, name: str) -> None:
        self.invoke("createDeck", deck=name)

    def model_names(self) -> list[str]:
        return [str(m) for m in self.invoke("modelNames")]

    def model_field_names(self, model: str) -> list[str]:
        return [str(f) for f in self.invoke("modelFieldNames", modelName=model)]

    def create_model(self, spec: dict[str, Any]) -> None:
        self.invoke("createModel", **spec)

    def update_model_templates(self, model: str, templates: dict[str, dict[str, str]]) -> None:
        self.invoke("updateModelTemplates", model={"name": model, "templates": templates})

    def update_model_styling(self, model: str, css: str) -> None:
        self.invoke("updateModelStyling", model={"name": model, "css": css})

    def find_notes(self, query: str) -> list[int]:
        return [int(n) for n in self.invoke("findNotes", query=query)]

    def notes_info(self, note_ids: list[int]) -> list[dict[str, Any]]:
        if not note_ids:
            return []
        return list(self.invoke("notesInfo", notes=note_ids))

    def add_note(
        self, deck: str, model: str, fields: dict[str, str], tags: list[str]
    ) -> int | None:
        return self.invoke(
            "addNote",
            note={
                "deckName": deck,
                "modelName": model,
                "fields": fields,
                "tags": tags,
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            },
        )

    def update_note_fields(self, note_id: int, fields: dict[str, str]) -> None:
        self.invoke("updateNoteFields", note={"id": note_id, "fields": fields})

    def add_tags(self, note_ids: list[int], tags: str) -> None:
        self.invoke("addTags", notes=note_ids, tags=tags)

    def remove_tags(self, note_ids: list[int], tags: str) -> None:
        self.invoke("removeTags", notes=note_ids, tags=tags)
