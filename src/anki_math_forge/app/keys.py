"""Every keyboard shortcut, declared once.

The keys were written down three times per view: bound in the view's
JavaScript, listed in its footer legend, and explained in the guide. Two
regression tests existed to catch the three drifting apart, both by regex over
the source, and neither covered the graph view -- so the newest view had a
keymap nothing checked.

One declaration now. The footer renders from it, the browser binds from it, and
the guide reads its key letters out of it, so a remapped key changes all three
or none. `[app.keys]` in `forge.toml` remaps one by naming its action.

**An action name is the contract**, not the key. `approve` is bound to `a` and
could be bound to anything; the JavaScript asks for the handler of `approve`
and never mentions a letter.

## Choosing a default

One key means one thing across the views that have it. `z` undoes everywhere,
`u` takes the decision back to the state before it (a unit to `new`, a card to
`draft`), `f` is about what you are shown, `g` is the source picker, `j` and
`k` move. That is the whole rule, and it is worth more than any individual
mnemonic: a key that means "approve" here and "show everything" there is a key
you have to think about.

Three broke it and two are fixed here. The canvas had `a` for *every card*
against `a` for approve and accept, and `n` for *add a card* against `n` for
the `@claude` note. They are `f` and `+`. The third is `x`, kept: it clears
the thing under the cursor in both views that have it, an annotation in one
and a position in the other.
"""

from __future__ import annotations

from dataclasses import dataclass

VIEWS = ("units", "review", "graph")


@dataclass(frozen=True)
class Key:
    """One shortcut. `action` is what the browser binds a handler to."""

    action: str
    #: What `event.key` reports: a letter, or a name like `Delete`. The
    #: declarations below give the default; `resolve` returns it overridden.
    key: str
    #: The footer legend. A few words, lower case, no full stop. Empty for a
    #: second key on an action the legend already names once.
    label: str
    #: Starts a new group in the legend, which is ordered by how often a hand
    #: reaches for it: decide, repair, move, then the view itself.
    sep: bool = False


# Two actions sharing one entry, because they are one thing in the legend and
# one line in the guide: `n` writes the brief, `N` parks a decision.
UNITS: tuple[Key, ...] = (
    Key("queue", "q", "queue"),
    Key("queue-with-brief", "Q", "queue + brief"),
    Key("skip", "s", "skip"),
    Key("accept-suggestion", "a", "accept a suggestion"),
    Key("dismiss-suggestion", "d", "dismiss it"),
    Key("undo", "z", "undo", sep=True),
    Key("note-claude", "n", "note for claude"),
    Key("note-me", "N", "note for me"),
    Key("context-size", "c", "context size"),
    Key("web-lookups", "w", "web lookups"),
    Key("pdf-view", "p", "crop/page/doc"),
    Key("skip-with-reason", "S", "skip + reason"),
    Key("back-to-new", "u", "back to new"),
    Key("next", "j", "next", sep=True),
    Key("prev", "k", "prev"),
    Key("next-alt", "ArrowDown", ""),
    Key("prev-alt", "ArrowUp", ""),
    Key("filters", "f", "filters"),
    Key("projects", "g", "projects"),
    Key("guide", "?", "guide"),
)

REVIEW: tuple[Key, ...] = (
    Key("approve", "a", "approve"),
    Key("reject", "r", "reject"),
    Key("back-to-draft", "u", "back to draft"),
    Key("undo", "z", "undo", sep=True),
    Key("editor", "e", "$EDITOR"),
    Key("note-claude", "n", "note for claude"),
    Key("note-me", "N", "note for me"),
    Key("resolve-note", "x", "resolve first note"),
    Key("next", "j", "next", sep=True),
    Key("prev", "k", "prev"),
    Key("next-alt", "ArrowDown", ""),
    Key("prev-alt", "ArrowUp", ""),
    Key("filters", "f", "filters"),
    Key("projects", "g", "projects"),
    Key("guide", "?", "guide"),
)

GRAPH: tuple[Key, ...] = (
    # `+` rather than `n`, which is the `@claude` note on both other views.
    Key("add-card", "+", "add a card"),
    # `f` rather than `a`, which approves on one view and accepts on the other.
    # This is the only filter the canvas has, so `f` is what it is elsewhere.
    Key("every-card", "f", "every card"),
    # The panel down the right: the study order this picture is half of. `o`
    # is free on every view and is the first letter of the only word for it.
    # Beside `f` because both answer "what am I being shown".
    Key("study-order", "o", "study order"),
    Key("remove-selected", "Delete", "remove what is selected"),
    Key("remove-selected-alt", "Backspace", ""),
    Key("open-card", "Enter", "open the selected card"),
    Key("undo", "z", "undo", sep=True),
    # Clears what is under the pointer, which is what `x` does on the review
    # view: an annotation there, a hand-placed position here.
    Key("forget-position", "x", "put boxes back"),
    Key("select-all", "A", "select every box"),
    # `.` and `,` rather than `+`/`-`: `+` adds a card, and on a German
    # keyboard `=` is a shifted key while these two are not, so a pair that
    # works on one layout and not the other is not a pair worth having.
    Key("zoom-in", ".", "zoom in", sep=True),
    Key("zoom-out", ",", "zoom out"),
    Key("recentre", "0", "fit on screen"),
    Key("projects", "g", "projects"),
)

# Every key that appears in more than one view, and the one thing it means
# there. Two views may spell an action differently -- `back-to-new` on a unit
# and `back-to-draft` on a card -- and still be the same key for the same
# reason; what must never happen is one key for two ideas.
#
# A new shared key fails the test until it is written down here, which is the
# point: agreeing that two actions are the same thing is a judgement, and this
# is where the judgement is recorded rather than inferred from a name.
SHARED: dict[str, str] = {
    "z": "undo the last thing you did",
    # Worth having had to decide: a draft card *is* a proposal, the same way a
    # classifier's suggested skip is, and `a` says yes to the one in front of
    # you. Had it not come out that way it would have been a key to move.
    "a": "yes to what is in front of you: a suggested skip, or the card itself",
    "u": "back to the state before the decision: a unit to `new`, a card to `draft`",
    "x": "clear what is under the cursor: an annotation, or a hand-placed position",
    "f": "what you are shown: the filter rail, or the canvas's one filter",
    "g": "the source picker",
    "n": "write the `@claude` note",
    "N": "park an `@me` decision",
    "j": "next",
    "k": "previous",
    "ArrowDown": "next",
    "ArrowUp": "previous",
    "?": "the guide",
}

BY_VIEW: dict[str, tuple[Key, ...]] = {
    "units": UNITS,
    "review": REVIEW,
    "graph": GRAPH,
}


class KeyError_(ValueError):
    """A `[app.keys]` entry that cannot mean anything."""


def actions() -> set[str]:
    return {k.action for keys in BY_VIEW.values() for k in keys}


def resolve(view: str, overrides: dict[str, str]) -> list[Key]:
    """This view's keys, with `[app.keys]` applied.

    A remap that collides with another key **in the same view** is refused
    rather than silently shadowing it: two handlers on one key means one of
    them never runs, and which one depends on dict order. Across views there
    is no collision to have, since each view binds its own map.
    """
    out = [
        Key(k.action, overrides.get(k.action, k.key), k.label, k.sep)
        for k in BY_VIEW[view]
    ]
    seen: dict[str, str] = {}
    for entry in out:
        if entry.key in seen:
            raise KeyError_(
                f"[app.keys]: {entry.key!r} is bound to both "
                f"{seen[entry.key]!r} and {entry.action!r} in the {view} view"
            )
        seen[entry.key] = entry.action
    return out


def validate(overrides: dict[str, str]) -> None:
    """Refuse an override that names no action, at load rather than never.

    An unrecognised key in a config table is normally worth ignoring. Not this
    one: the whole symptom of a typo here is that the shortcut you configured
    does not change, which is indistinguishable from the feature not working.
    """
    unknown = sorted(set(overrides) - actions())
    if unknown:
        known = ", ".join(sorted(actions()))
        raise KeyError_(
            f"[app.keys]: no such action{'s' if len(unknown) > 1 else ''}: "
            f"{', '.join(unknown)}. Known actions: {known}"
        )
    for action, key in overrides.items():
        if not isinstance(key, str) or not key:
            raise KeyError_(f"[app.keys] {action}: a key must be a non-empty string")
    for view in VIEWS:
        resolve(view, overrides)
