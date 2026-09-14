"""What decides the order Anki introduces new cards in, declared once.

The order was a hard-coded tuple in `sync.study_key`, a sentence in the guide
listing the same three words, and a paragraph in the config comments. Three
copies of one rule, and the only one that decided anything was the tuple.

One declaration now. `sync` builds its sort key from it, the guide renders the
line from it, and the canvas's panel lets you drag the three into a different
sequence, which writes `[cards] study_order` in `forge.toml`.

## What a criterion is, and what it is not

A criterion is one comparable fact about a card, worth ordering a deck by. It
is not a filter and not a judgement: `frequency` says a `core` card comes
before a `rare` one, and nothing about whether the `rare` one is worth having.

`requires` and `uid` are deliberately not in the list.

`requires` is not, because it is not a tiebreak. It is respected absolutely,
before any of these, and it is a shape rather than a value: `in_study_order`
is a topological sort that uses these criteria only to choose among the cards
whose prerequisites are already placed. Putting it in the list would suggest
you could rank it third, and you cannot.

`uid` is not, because it is not a criterion either. It is the last element of
every key so that two cards which tie on everything still sort the same way on
two machines. Reordering it would mean choosing to be non-deterministic.

## Adding one

Add a `Criterion` here and give `sync.study_key` the value to sort by. An
existing `forge.toml` that does not name it keeps working: `resolve` appends
whatever the config leaves out, in declaration order, so a new criterion
arrives as the least significant key rather than silently reshuffling a deck
somebody has already reviewed half of.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class StudyOrderError(ValueError):
    """A declared order naming something that is not a criterion, or naming
    one twice."""


@dataclass(frozen=True)
class Criterion:
    """One key in the sort, and the words for saying what it does."""

    #: What `[cards] study_order` calls it, and the contract everything else
    #: uses. The label may be reworded; this may not.
    name: str
    #: The guide's one-line rule, where three of these sit in a row.
    label: str
    #: What it is ordering by, as a question a person would ask.
    sense: str
    #: The full sentence, for the panel where there is room for one.
    detail: str
    #: The values it ranks, best first. Empty for a criterion whose values are
    #: not a fixed set, which is `printed`: its value is a position in a book.
    values: tuple[str, ...] = ()
    #: What a card carrying no value for it is called. Such a card sorts last
    #: within its group, because unannotated is unjudged rather than easy.
    unset: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "sense": self.sense,
            "detail": self.detail,
            "values": list(self.values),
            "unset": self.unset,
        }


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        name="frequency",
        label="frequency",
        sense="how much use it gets",
        detail=(
            "core, then common, then rare. Most useful first is the default "
            "because a deck is abandoned from the front: the first fifty cards "
            "decide whether there is a fifty-first review."
        ),
        values=("core", "common", "rare"),
        unset="ungraded",
    ),
    Criterion(
        name="derivation",
        label="derivation",
        sense="how much work it is",
        detail=(
            "definitional, then short, then long. Easiest first among cards of "
            "equal use, so a run of new cards does not open with the one that "
            "needs a page of algebra behind it."
        ),
        values=("definitional", "short", "long"),
        unset="ungraded",
    ),
    Criterion(
        name="printed",
        label="source order",
        sense="where the book puts it",
        detail=(
            "the order the source introduces it in. A text that builds up "
            "introduces things in a usable order and following it costs "
            "nothing; a source that is a table says `order = \"none\"` in its "
            "`source.toml` and opts out."
        ),
        unset="no printed position",
    ),
)

#: The order the criteria are declared in, which is also the default.
DEFAULT: tuple[str, ...] = tuple(c.name for c in CRITERIA)

BY_NAME: dict[str, Criterion] = {c.name: c for c in CRITERIA}


def resolve(order: Sequence[str] = ()) -> tuple[Criterion, ...]:
    """The criteria in the declared sequence, most significant first.

    Anything the caller leaves out is appended in declaration order rather
    than dropped. A criterion cannot be turned off: leaving one out would only
    move its work onto `uid`, which is a hash, so the choice on offer is
    between orders and not between an order and none.
    """
    validate(order)
    named = [BY_NAME[name] for name in order]
    return (*named, *(c for c in CRITERIA if c.name not in set(order)))


def validate(order: Sequence[str]) -> None:
    """Refuse a sequence at the moment it is declared, not at the sort.

    A typo here reads exactly like the setting doing nothing, which is the
    same argument `keys.validate` makes about an action name.
    """
    seen: set[str] = set()
    for name in order:
        if name not in BY_NAME:
            known = ", ".join(DEFAULT)
            raise StudyOrderError(f"unknown study-order criterion {name!r}. Known: {known}")
        if name in seen:
            raise StudyOrderError(f"study-order criterion {name!r} named twice")
        seen.add(name)


def sentence(order: Sequence[str] = ()) -> str:
    """The rule as one line, for a `--json`-less caller and for `forge check`."""
    return "requires, then " + ", then ".join(c.label for c in resolve(order)) + ", then uid"
