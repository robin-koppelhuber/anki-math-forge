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

    def model_templates(self, model: str) -> dict[str, dict[str, str]]:
        return dict(self.invoke("modelTemplates", modelName=model))

    def model_styling(self, model: str) -> str:
        return str(self.invoke("modelStyling", modelName=model).get("css", ""))

    def model_field_add(self, model: str, field: str, index: int) -> None:
        """Add a field to a note type that already has notes.

        The alternative is a new note type, and `sync` finds notes by note
        type name -- so renaming it would orphan every existing note along
        with its whole review history and re-add all of them as new.
        """
        self.invoke("modelFieldAdd", modelName=model, fieldName=field, index=index)

    def set_card_flag(self, card_id: int, flag: int) -> None:
        """Set or clear a card's flag.

        AnkiConnect has no flag action, so this goes through the generic
        column writer. `flags` is an integer column on the card; 0 is none.
        """
        self.invoke(
            "setSpecificValueOfCard",
            card=card_id,
            keys=["flags"],
            newValues=[flag],
            warning_check=True,
        )

    def find_cards(self, query: str) -> list[int]:
        return list(self.invoke("findCards", query=query))

    def cards_info(self, card_ids: list[int]) -> list[dict[str, Any]]:
        if not card_ids:
            return []
        return list(self.invoke("cardsInfo", cards=card_ids))

    def set_new_position(self, card_id: int, position: int) -> None:
        """Move a card in the new-card queue.

        For a card that has never been studied, `due` *is* its position, so
        this is the reposition the GUI offers. It means a date for anything
        further along, which is why the caller checks `type == 0` first;
        AnkiConnect will happily write nonsense here.
        """
        self.invoke(
            "setSpecificValueOfCard",
            card=card_id,
            keys=["due"],
            newValues=[position],
            warning_check=True,
        )

    def add_tags(self, note_ids: list[int], tags: str) -> None:
        self.invoke("addTags", notes=note_ids, tags=tags)

    def remove_tags(self, note_ids: list[int], tags: str) -> None:
        self.invoke("removeTags", notes=note_ids, tags=tags)
