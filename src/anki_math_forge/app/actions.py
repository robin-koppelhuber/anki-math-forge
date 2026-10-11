"""Actions: the commands with no model behind them, as forms.

The runs window builds a command from one of these: pick an action, fill in
its fields and scope, read the command line it comes to, and run it here or
copy it. The rails keep their short lists of what to run next; each of
those is an action with its fields already filled in, and opens here to be
changed before it runs.

**The argv is built from the fields, never parsed from text.** A field is a
value in a known slot, so nothing typed into one can become a flag: a value
that starts with `-` is refused. What an action changes is the parser's
answer (`effect`), read off the words it runs, the same rule the run
button follows (docs/VERBS.md).

A slash command is not here and never will be. It puts a model in the loop,
so it is copied and pasted where you can watch it (invariant 1).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any


class Invalid(ValueError):
    """A field value the action cannot run with, and why."""


@dataclass(frozen=True)
class Field:
    """One slot of a command."""

    name: str
    label: str
    #: `text`, `number`, `choice`, `flag` or `project`.
    kind: str = "text"
    #: The CLI flag, or empty for a positional argument.
    flag: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""
    required: bool = False
    #: What an empty project choice means, for a field that may be left empty.
    empty: str = "every project"

    def as_dict(self, projects: list[str]) -> dict[str, Any]:
        choices: list[list[str]] = [list(c) for c in self.choices]
        if self.kind == "project":
            choices = ([] if self.required else [["", self.empty]]) + [[p, p] for p in projects]
        return {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "flag": self.flag,
            "choices": choices,
            "placeholder": self.placeholder,
            "required": self.required,
        }


@dataclass(frozen=True)
class Action:
    key: str
    #: The headline: the command in a word or two, as you would say it
    #: (`anki push test`). The same words the rails use for it.
    label: str
    #: One line: what it does. Shown beside the label, so it stays short.
    what: str
    words: tuple[str, ...]
    fields: tuple[Field, ...] = ()
    #: Which group the window lists it under.
    group: str = "other"
    defaults: dict[str, Any] = field(default_factory=dict)
    #: What tells two actions with one headline apart: `zotero import` is
    #: three, by what it is given.
    variant: str = ""

    @property
    def verb(self) -> str:
        return " ".join(self.words)

    def argv(self, values: dict[str, Any], projects: list[str]) -> list[str]:
        """The arguments after `forge`, from the fields. Raises `Invalid`."""
        out = list(self.words)
        tail: list[str] = []
        for slot in self.fields:
            raw = values.get(slot.name, self.defaults.get(slot.name, ""))
            if slot.kind == "flag":
                if raw in (True, "true", "on", "1", "yes"):
                    tail.append(slot.flag)
                continue
            value = str(raw if raw is not None else "").strip()
            if not value:
                if slot.required:
                    raise Invalid(f"{slot.label} is needed")
                continue
            if value.startswith("-"):
                raise Invalid(f"{slot.label}: a value may not start with '-'")
            if slot.kind == "number" and not value.isdigit():
                raise Invalid(f"{slot.label} is a number")
            if slot.kind == "choice" and value not in {c for c, _ in slot.choices}:
                raise Invalid(f"{slot.label}: {value!r} is not one of the choices")
            if slot.kind == "project" and value not in projects:
                raise Invalid(f"no project {value!r}")
            if slot.flag:
                tail += [slot.flag, value]
            else:
                out.append(value)
        return out + tail

    def as_dict(self, projects: list[str], effects: dict[str, str]) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "variant": self.variant,
            "what": self.what,
            "group": self.group,
            "verb": self.verb,
            "effect": effects.get(self.verb, "reads"),
            "fields": [f.as_dict(projects) for f in self.fields],
        }


def effect_for(verb: str, argv: list[str], effects: dict[str, str]) -> str:
    """What running `argv` changes. A `--dry-run` changes nothing, whatever
    the command does without it, which is what lets a test of a push run on
    a click while the push itself asks first."""
    return "reads" if "--dry-run" in argv else effects.get(verb, "reads")


def line(argv: list[str]) -> str:
    """The command as you would type it."""
    return "uv run forge " + shlex.join(argv)


PROJECT = Field("project", "project", "project", "--project")
#: `--dry-run`, called "test" in the window. The longer wording is its hover
#: text: a flag has no box for a placeholder to sit in.
DRY = Field(
    "dry_run", "test", "flag", "--dry-run", placeholder="say what it would do, and change nothing"
)

ACTIONS: tuple[Action, ...] = (
    # -- bringing sources in ----------------------------------------------------
    Action(
        "zotero-new",
        "zotero import",
        "an item's marks become units; a project is made for it unless you pick one",
        ("zotero", "import"),
        (
            Field(
                "item",
                "Zotero item",
                placeholder="a cite key or a Zotero item key",
                required=True,
            ),
            Field(
                "project",
                "into project",
                "project",
                "--project",
                empty="a new project named after the item",
            ),
            DRY,
        ),
        group="sources",
        variant="a new item",
    ),
    Action(
        "zotero-project",
        "zotero import",
        "new marks become units, untouched units of dropped marks go",
        ("zotero", "import"),
        (Field("project", "project", "project", "--project", required=True), DRY),
        group="sources",
        variant="a project's items",
    ),
    Action(
        "zotero-tag",
        "zotero import",
        "every item with the tag, each into the project that already reads it",
        ("zotero", "import"),
        (Field("tag", "Zotero tag", flag="--tag", required=True), DRY),
        group="sources",
        defaults={"tag": "anki"},
        variant="by tag",
    ),
    Action(
        "sources-update",
        "sources update",
        "its Zotero items and its PDF and TeX files, in one run",
        ("sources", "update"),
        (Field("project", "project", "project", "--project"),),
        group="sources",
    ),
    Action(
        "units-extract",
        "units extract",
        "PDF or TeX into units; never reads the maths, never writes cards",
        ("units", "extract"),
        (
            Field("project", "project", "project", required=True),
            Field("pages", "pages", flag="--pages", placeholder="e.g. 10-40, PDF only"),
        ),
        group="sources",
    ),
    Action(
        "units-classify",
        "units classify",
        "fragments and headings, proposed for triage; nothing is applied",
        ("units", "classify"),
        (PROJECT, DRY),
        group="sources",
    ),
    # -- Anki -----------------------------------------------------------------
    Action(
        "anki-push",
        "anki push",
        "adds and updates notes by uid; test changes nothing",
        ("anki", "push"),
        (
            PROJECT,
            DRY,
            Field("templates", "also push the card template", "flag", "--templates"),
            Field("reposition", "reorder cards not yet studied", "flag", "--reposition"),
            Field("move_decks", "move cards filed under an old deck", "flag", "--move-decks"),
        ),
        group="anki",
    ),
    Action(
        "anki-pull",
        "anki pull",
        "comments and flags become @claude notes and are cleared in Anki",
        ("anki", "pull"),
        (DRY,),
        group="anki",
    ),
    # -- checking ---------------------------------------------------------------
    Action(
        "check",
        "check",
        "every card file, against the format and KaTeX; blocks a push on error",
        ("check",),
        (Field("anki", "also check uids against Anki", "flag", "--anki"),),
        group="checks",
    ),
    Action(
        "audit",
        "audit",
        "numbering with no gaps, overlapping crops, cut-off equations",
        ("audit",),
        (PROJECT,),
        group="checks",
    ),
    Action(
        "verify",
        "verify",
        "the cards that opt in, against random matrices",
        ("verify",),
        (PROJECT, Field("uid", "one card", flag="--uid", placeholder="a uid")),
        group="checks",
    ),
    Action(
        "todo",
        "todo",
        "every open @claude and @me annotation",
        ("todo",),
        (PROJECT,),
        group="checks",
    ),
    # -- looking ----------------------------------------------------------------
    Action(
        "sources",
        "sources",
        "every source, and which project reads it",
        ("sources",),
        (PROJECT,),
        group="looking",
    ),
    Action(
        "remarks",
        "remarks",
        "what the passes said about the tool and their instructions",
        ("remarks",),
        (),
        group="looking",
    ),
    Action(
        "zotero-list",
        "zotero",
        "the items tagged for import, and which are already sources",
        ("zotero",),
        (),
        group="looking",
    ),
)

BY_KEY = {action.key: action for action in ACTIONS}


def match(argv: list[str]) -> tuple[Action, dict[str, Any]] | None:
    """The action an offered command line is, with its fields filled in.

    So a quick pick on a rail opens in the window ready to change. A word in
    angle brackets (`<citekey>`) is a slot left for you, and leaves its
    field empty. `None` for a command no action has.
    """
    words = [w for w in argv if w != "--json"]
    if words[:1] == ["anki"] and words[1:2] not in (["push"], ["pull"], ["export"]):
        # `forge anki` is the rehearsal of a push: the push with test ticked.
        words = ["anki", "push", "--dry-run", *words[1:]]
    for action in sorted(ACTIONS, key=lambda a: -len(a.words)):
        if tuple(words[: len(action.words)]) != action.words:
            continue
        values = _fill(action, words[len(action.words) :])
        if values is not None and _fits(action, values):
            return action, values
    return None


def _fits(action: Action, values: dict[str, Any]) -> bool:
    """`zotero import` is three actions, told apart by what it was given:
    an item, a tag, or only a project."""
    if action.verb != "zotero import":
        return True
    item, tag, project = "item" in values, bool(values.get("tag")), bool(values.get("project"))
    return {
        "zotero-new": item,
        "zotero-tag": tag and not item,
        "zotero-project": project and not item and not tag,
    }.get(action.key, False)


def _fill(action: Action, rest: list[str]) -> dict[str, Any] | None:
    """Field values from the words after an action's own, or `None` where a
    word fits no field."""
    values: dict[str, Any] = {}
    by_flag = {f.flag: f for f in action.fields if f.flag}
    positional = [f for f in action.fields if not f.flag]
    i = 0
    while i < len(rest):
        word = rest[i]
        slot = by_flag.get(word)
        if slot is not None and slot.kind == "flag":
            values[slot.name] = True
            i += 1
        elif slot is not None:
            if i + 1 >= len(rest):
                return None
            values[slot.name] = _slot(rest[i + 1])
            i += 2
        elif word.startswith("-") or not positional:
            return None
        else:
            values[positional.pop(0).name] = _slot(word)
            i += 1
    return values


def _slot(word: str) -> str:
    return "" if word.startswith("<") and word.endswith(">") else word
