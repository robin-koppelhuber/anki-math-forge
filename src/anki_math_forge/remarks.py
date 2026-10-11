"""`projects/remarks.md`: what the passes say about the tool and their instructions.

A card writer meets things nobody else sees: a brief cut off mid-sentence, a
rule that makes a card worse, a command that did not say why it refused. Those
are about the tool, not about a card, so they belong in no card's notes, and
they are not yet decisions, so they belong in no roadmap. A pass says them
here, once, and a person reads the file when planning and folds what is worth
keeping into `ROADMAP.md`.

The file sits beside the projects and not in `docs/`. It is scratch that a
pass writes while it works, so it should not turn up as a change to commit,
and `projects/*` is already untracked.

A **remark** is that: one entry, with when, who said it and, where it was
about one, the project. Markdown, appended to and never rewritten wholesale,
so it is a file you can edit by hand as well (invariant 2).

    ## 2026-10-10 14:02 · card-writer · krauseProbabilisticArtificialIntelligence
    `forge context` cut a sticky note at 76 characters, so a second request in
    it never reached the writer.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Config, ConfigError
from .model import write_atomic

REMARKS_NAME = "remarks.md"

HEADER = """# Remarks

What the passes that write and check cards say about the tool and their own
instructions: a brief that arrived cut off, a rule that made a card worse. One
entry each, added by `forge remarks add`. Read this when planning, fold what is
worth keeping into ROADMAP.md, and delete the rest.
"""

_HEADING = re.compile(r"^## (.+?)\s*$", re.M)


@dataclass(frozen=True)
class Remark:
    stamp: str
    by: str
    project: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"stamp": self.stamp, "by": self.by, "project": self.project, "text": self.text}


def path_for(config: Config) -> Path:
    return config.projects_dir / REMARKS_NAME


def shown(config: Config) -> str:
    """Where the file is, as the repo spells it: `projects/remarks.md`."""
    return path_for(config).relative_to(config.root).as_posix()


def add(config: Config, text: str, *, by: str, project: str = "") -> int:
    """Append one remark and return how many there are."""
    body = " ".join(text.split()) if "\n" not in text.strip() else text.strip()
    if not body:
        raise ConfigError("nothing to say")
    who = " ".join(by.split()) or "someone"
    path = path_for(config)
    before = path.read_text(encoding="utf-8") if path.exists() else HEADER
    # Two in one minute from one pass would share a heading; the text tells
    # them apart, so the heading does not have to be unique.
    heading = " · ".join(
        part for part in (time.strftime("%Y-%m-%d %H:%M"), who, project.strip()) if part
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, before.rstrip("\n") + f"\n\n## {heading}\n\n{body}\n")
    return len(remarks(config))


def remarks(config: Config) -> list[Remark]:
    """Every remark, oldest first."""
    path = path_for(config)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    heads = list(_HEADING.finditer(text))
    out: list[Remark] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        stamp, by, project = [*head.group(1).split(" · "), "", ""][:3]
        out.append(Remark(stamp, by, project, text[head.end() : end].strip()))
    return out
