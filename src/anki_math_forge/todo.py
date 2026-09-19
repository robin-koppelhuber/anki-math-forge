"""`todo` -- the open `@claude` annotations, for Claude Code (DESIGN.md §8).

An annotation is an open request. Resolving one means deleting the line and
making the edit; the edit changes `content_hash`, so the card drops back to
`draft` and re-enters review automatically. Nothing here resolves anything --
it only reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import model
from .config import Config
from .ledger import open_ledgers


@dataclass(frozen=True)
class TodoItem:
    kind: str  # card | unit
    ref: str  # uid or unit id
    note: str
    where: str  # file path or ledger path
    status: str = ""
    audience: str = "claude"  # who it is addressed to: claude | me
    # Which source's work this is. Empty only for a card whose units name no
    # source, which is a misfiled card rather than a card belonging nowhere --
    # see the filter in `cmd_todo`.
    source: str = ""

    def format(self) -> str:
        status = f" [{self.status}]" if self.status else ""
        who = "" if self.audience == "claude" else f" ({self.audience})"
        return f"{self.kind} {self.ref}{status}{who}: {self.note}\n    {self.where}"

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "note": self.note,
            "where": self.where,
            "status": self.status,
            "audience": self.audience,
            "source": self.source,
        }


def collect(config: Config) -> list[TodoItem]:
    """Every open annotation, on cards and on units that have no card yet."""
    items: list[TodoItem] = []

    for card in model.load_all(config.cards_dir):
        where = str(_relative(card.path, config.root))
        for note in card.annotations():
            items.append(
                TodoItem(
                    "card", card.uid, note, where, card.status,
                    model.annotation_audience(note) or "claude",
                    source=card.source_name,
                )
            )

    for name, ledger in open_ledgers(config.sources_dir).items():
        where = str(_relative(ledger.path, config.root))
        for unit in ledger:
            for note in unit.notes:
                items.append(
                    TodoItem(
                        "unit", unit.id, note, where, unit.state,
                        model.annotation_audience(note) or "claude",
                        # The ledger it was read from, not the id's prefix:
                        # the file is where it actually lives.
                        source=name,
                    )
                )

    return items


def _relative(path: Path | None, root: Path) -> Path:
    if path is None:
        return Path("(unsaved)")
    try:
        return path.relative_to(root)
    except ValueError:
        return path
