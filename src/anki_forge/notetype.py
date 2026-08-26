"""The Anki note type, versioned in the repo (DESIGN.md §9).

One note type covers cards with and without proofs or prose: the optional
sections are conditionally rendered, so a bare stub and a fully augmented card
are the same shape to Anki.

`uid` is the first field, which makes it Anki's own duplicate key as well as
the one sync queries. Bump `note_type_version` in the config rather than
mutating a live note type in place.
"""

from __future__ import annotations

from typing import Any

# Field order matters: the first field is Anki's duplicate key.
FIELDS = ["uid", "Front", "Back", "Conditions", "Proof", "Prose", "Source"]

FRONT_TEMPLATE = '<div class="front">{{Front}}</div>'

# Assembled line by line rather than as one triple-quoted block, so the
# conditional sections stay readable and inside the line limit.
BACK_TEMPLATE = "\n".join(
    [
        "{{FrontSide}}",
        "",
        "<hr id=answer>",
        "",
        '<div class="back">{{Back}}</div>',
        "",
        "{{#Conditions}}"
        '<div class="conditions"><span class="label">conditions</span>{{Conditions}}</div>'
        "{{/Conditions}}",
        '{{#Proof}}<div class="proof"><span class="label">proof</span>{{Proof}}</div>{{/Proof}}',
        '{{#Prose}}<div class="prose">{{Prose}}</div>{{/Prose}}',
        '{{#Source}}<div class="source">{{Source}}</div>{{/Source}}',
        "",
    ]
)

CSS = """.card {
  font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
  font-size: 20px;
  text-align: center;
  color: #1a1a1a;
  background: #fbfbfa;
}
.nightMode.card { color: #e8e8e8; background: #202124; }
.front { font-size: 24px; margin: 1em 0; }
.back { font-size: 24px; margin: 1em 0; }
.conditions, .proof, .prose {
  font-size: 15px;
  text-align: left;
  margin: 0.9em auto;
  max-width: 34em;
  line-height: 1.5;
}
.conditions { color: #6a5000; }
.nightMode .conditions { color: #d8c06a; }
.proof { color: #444; }
.nightMode .proof { color: #b8b8b8; }
.prose { color: #555; font-style: italic; }
.nightMode .prose { color: #a8a8a8; }
.label {
  display: block;
  font-size: 11px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  opacity: 0.55;
  margin-bottom: 0.25em;
}
.source { font-size: 12px; opacity: 0.5; margin-top: 1.6em; }
"""


def card_template_name(model: str) -> str:
    return f"{model} card"


def spec(model: str) -> dict[str, Any]:
    """The `createModel` payload for this note type."""
    return {
        "modelName": model,
        "inOrderFields": FIELDS,
        "css": CSS,
        "isCloze": False,
        "cardTemplates": [
            {
                "Name": card_template_name(model),
                "Front": FRONT_TEMPLATE,
                "Back": BACK_TEMPLATE,
            }
        ],
    }


def templates(model: str) -> dict[str, dict[str, str]]:
    """The `updateModelTemplates` payload."""
    return {card_template_name(model): {"Front": FRONT_TEMPLATE, "Back": BACK_TEMPLATE}}
