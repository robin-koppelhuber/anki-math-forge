"""One word shows you something, two words change something.

The rule is only worth having while something checks it, so this is the
check. Two halves: no writing command is reachable in one word, and no
file in the repo still tells anybody to run a spelling that is gone.

docs/VERBS.md is the prose version and the map.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from anki_math_forge.cli import ANKI, ONE_WORD_WRITERS, READS, REPO, build_parser

ROOT = Path(__file__).resolve().parents[1]

SKIP = {".git", ".venv", "node_modules", "__pycache__", ".forge", "dist", "build"}
LOOK_IN = {".py", ".md", ".html", ".js", ".toml", ".yaml", ".yml", ".json"}


def subcommands() -> dict[str, object]:
    """Every parser under the top level, by the words you type to reach it."""
    top = next(
        action
        for action in build_parser()._actions
        if action.dest == "verb" and isinstance(getattr(action, "choices", None), dict)
    )
    found: dict[str, object] = {}
    for name, parser in dict(top.choices or {}).items():
        found[name] = parser
        for action in parser._actions:
            if getattr(action, "dest", "") == "change" and getattr(action, "choices", None):
                for word, child in action.choices.items():
                    found[f"{name} {word}"] = child
    return found


def effect_of(parser: object) -> str:
    return str(getattr(parser, "_defaults", {}).get("effect", ""))


# -- the rule ---------------------------------------------------------------


def test_every_command_declares_what_it_does() -> None:
    """An undeclared one is the one that slips through the check below."""
    missing = [name for name, p in subcommands().items() if not effect_of(p)]

    assert not missing, f"no `effect` on: {missing}"


def test_no_writing_command_is_reachable_in_one_word() -> None:
    """The whole rule. A one-word command records nothing, so a name you
    half remember is safe to try."""
    writers = [
        name
        for name, p in subcommands().items()
        if effect_of(p) in (REPO, ANKI)
        and " " not in name
        and not getattr(p, "_defaults", {}).get("renamed")
    ]

    assert sorted(writers) == sorted(ONE_WORD_WRITERS), (
        "a writing command can be reached in one word. Give it a second "
        f"word, or name it in ONE_WORD_WRITERS with a reason: {writers}"
    )


def test_what_reaches_outside_the_repo_says_anki_first() -> None:
    """The word before the verb names the thing you cannot rebuild from
    the files here."""
    outside = [
        name
        for name, p in subcommands().items()
        if effect_of(p) == ANKI and not getattr(p, "_defaults", {}).get("renamed")
    ]

    assert outside, "nothing is declared as writing outside the repo"
    for name in outside:
        assert name.startswith("anki "), f"{name} writes outside the repo and does not say so"


def test_the_bare_forms_of_the_outside_commands_are_reads() -> None:
    """`forge anki` is the plan and `forge anki push` does it, so the
    shortest thing you can type is the one that changes nothing."""
    assert effect_of(subcommands()["anki"]) == READS


# -- nothing still names a spelling that is gone ----------------------------


def repo_files() -> list[Path]:
    """Every tracked file worth reading.

    Tracked, because a generated file is not the repo teaching anybody
    anything: `projects/*/text-*.md` carries a header naming the command
    that wrote it, and the next run writes it again.
    """
    import subprocess

    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    out = []
    for name in listed:
        path = ROOT / name
        if not name or path.suffix not in LOOK_IN or not path.is_file():
            continue
        if any(part in SKIP for part in path.parts):
            continue
        out.append(path)
    return out


#: Spellings that were renamed. Each still *runs*, hidden and announced,
#: so this is not about breaking them: it is about nothing in the repo
#: teaching one, because a skill that says `forge sync` sends a subagent
#: down a path that prints a deprecation note instead of doing the work.
GONE = {
    "extract": "units extract",
    "classify": "units classify",
    "sync": "anki push",
    "feedback": "anki pull",
    "export": "anki export",
    "new": "cards new",
}

#: Where an old name is the subject rather than an instruction.
ALLOWED = {
    "docs/VERBS.md",  # the map: it names both halves on purpose
    "docs/ROADMAP.md",  # records what was renamed and why
    "tests/test_verbs.py",  # this file
    "src/anki_math_forge/cli.py",  # registers them, hidden, and says so
}

INVOKED = re.compile(r"(?:uv run )?forge (" + "|".join(GONE) + r")\b")


@pytest.mark.parametrize("stale", sorted(GONE))
def test_nothing_tells_you_to_run_the_old_name(stale: str) -> None:
    offenders = []
    for path in repo_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for found in INVOKED.finditer(line):
                if found.group(1) == stale:
                    offenders.append(f"{rel}:{n}")
    assert not offenders, f"`forge {stale}` is now `forge {GONE[stale]}`: {offenders}"


def test_the_old_flag_forms_on_units_are_gone_from_the_repo() -> None:
    """`forge units --id X --set-state queued` still runs. Nothing should
    teach it: the id is a positional now."""
    offenders = []
    stale = re.compile(r"forge units [^\n`]*--(add|set-state|annotate|tex-auto|resolve-notes)\b")
    for path in repo_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            if stale.search(line):
                offenders.append(f"{rel}:{n}")
    assert not offenders, f"the writing flags on `units` have moved to subcommands: {offenders}"


# -- and the app agrees with the parser -------------------------------------


def test_the_app_offers_no_command_the_parser_does_not_have() -> None:
    """`runs.py` hands you a line to paste. A line that does not parse is
    worse than no line: you find out in a terminal, several seconds later."""
    from anki_math_forge.app import runs

    known = set(subcommands())
    bad = []
    for offer in runs.OFFERS:
        if offer.kind != "shell":
            continue
        run = offer.run if isinstance(offer.run, str) else offer.run(runs.Ambient(project="x"))
        words = run.replace("uv run ", "").split()
        if not words or words[0] != "forge":
            continue
        one, two = words[1], " ".join(words[1:3]) if len(words) > 2 else ""
        if two in known or one in known:
            continue
        bad.append(run)
    assert not bad, f"offered and unparseable: {bad}"
