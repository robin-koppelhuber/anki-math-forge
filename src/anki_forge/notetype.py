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
# `Feedback` is inbound only: `sync` never writes it and no template renders
# it, so it is invisible during review and always present in the editor.
# That is the whole mechanism behind `anki-forge feedback`.
# Field lists this tool has shipped, oldest first. `sync` will add fields to
# a live note type only when the collection matches one of these exactly --
# that is an upgrade. Anything else is drift somebody made by hand, and
# re-adding a field they deleted would not bring its contents back.
# Names this note type has shipped under, oldest first. The current name comes
# from `[anki] note_type_name`, deliberately: a note type is a thing in
# somebody's collection, and it should not change because the project changed
# its own name. `sync` refuses to create a fresh note type while one of these
# is still in the collection, because creating one would silently orphan every
# note on it along with its review history.
PREVIOUS_NAMES = [
    "anki-forge identity v1",
]

PREVIOUS_FIELDS = [
    ["uid", "Front", "Back", "Conditions", "Uses", "Proof", "Prose", "Source"],
]

FIELDS = [
    "uid",
    "Front",
    "Back",
    "Conditions",
    "Uses",
    "Proof",
    "Prose",
    "Source",
    "Feedback",
]

# Conditions are shown with the *prompt*, not with the answer. They fix the
# setting the question is asked in -- which matrix is square, which family is
# being varied over, which dimension -- and a setting revealed after you have
# answered is not a condition, it is a verdict. This is what makes "could
# someone answer this front with the ambient conventions and nothing else"
# a rule a card can actually satisfy.
FRONT_TEMPLATE = "\n".join(
    [
        '<div class="front">{{Front}}</div>',
        "{{#Conditions}}"
        '<div class="conditions given"><span class="label">given</span>{{Conditions}}</div>'
        "{{/Conditions}}",
    ]
)

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
        # `{{FrontSide}}` already carries them.
        # `Prose` first, and it is the only block with no label: one sentence
        # of interpretation sitting directly under the answer. Everything
        # after it is labelled, so the boundaries are visible.
        '{{#Prose}}<div class="prose">{{Prose}}</div>{{/Prose}}',
        '{{#Uses}}<div class="uses"><span class="label">used for</span>{{Uses}}</div>{{/Uses}}',
        '{{#Proof}}<div class="proof"><span class="label">proof</span>{{Proof}}</div>{{/Proof}}',
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
.conditions, .uses, .proof, .prose {
  font-size: 15px;
  text-align: left;
  margin: 0.9em auto;
  max-width: 34em;
  line-height: 1.5;
}
.conditions { color: #6a5000; }
.uses { color: #17506b; }
.nightMode .uses { color: #8fc6e6; }
.conditions.given { margin-top: 0.6em; opacity: 0.85; }
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


# The one card template's name, and Anki's own default for a fresh note type.
# It used to be f"{model} card", which meant renaming the note type left the
# template still carrying the old name: `template_drift` then compared a
# template that did not exist, and pushing it would have added a *second*
# template and a second card for every note.
CARD_TEMPLATE = "Card 1"


def card_template_name(model: str) -> str:
    return CARD_TEMPLATE


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
