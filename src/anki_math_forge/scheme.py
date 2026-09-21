"""Editing one work's marking scheme, in place, without losing its comments.

What a colour means, and which marks become units, is the one part of a
project's config you change while *looking* at the marks: you import a book,
triage twenty units, and discover that the orange highlights were the ones
worth carding. Until now that meant opening `project.toml` and remembering
the `"kind/colour"` spelling.

**Line-wise, not a rewrite.** A generated `project.toml` is mostly comments:
what each key does, which lines to uncomment, what an override replaces. A
round trip through a TOML writer would produce a correct file with all of
that gone, which is a worse file than the one you started with. So this
finds the one table it has to change and edits the lines inside it, leaving
every other byte alone.

It writes exactly what a human would write, which is what keeps invariant 2
honest: `units_from` as a list of `"kind/colour"` strings, and the meanings
as a `[sources.meanings]` sub-table under the work's own `[[sources]]`.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import model
from .config import PROJECT_TOML, Config, ConfigError


#: A line that starts a top-level table or array of tables. The span of one
#: `[[sources]]` entry runs from its own header to the next of these, so a
#: sub-table of its own (`[sources.meanings]`) has to be recognised as part
#: of it rather than as the end.
def _starts_a_table(line: str) -> bool:
    return line.lstrip().startswith("[")


def _is_own_subtable(line: str) -> bool:
    """`[sources.meanings]` belongs to the `[[sources]]` above it."""
    return line.lstrip().startswith("[sources.")


def path_for(config: Config, project: str) -> Path:
    return config.projects_dir / project / PROJECT_TOML


def table_span(lines: list[str], index: int) -> tuple[int, int]:
    """Where the `index`-th `[[sources]]` table sits in the file.

    Counted by header rather than by parsing, because the parse gives values
    and this needs positions. The two agree on order: TOML arrays of tables
    are ordered by appearance, and so is this scan.
    """
    seen = -1
    start = -1
    for at, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("[[sources]]", "[[ sources ]]"):
            seen += 1
            if seen == index:
                start = at
                continue
        if start >= 0 and at > start and _starts_a_table(line) and not _is_own_subtable(line):
            return start, at
    if start < 0:
        raise ConfigError(f"no [[sources]] number {index} in this file")
    return start, len(lines)


def _drop_key(lines: list[str], key: str) -> list[str]:
    """Remove `key = ...`, including an array written across several lines.

    A commented-out example keeps its `#`, because that is documentation
    rather than a setting: the generated file explains `units_from` with one,
    and deleting it would answer a question the next reader has.
    """
    out: list[str] = []
    skipping = False
    for line in lines:
        if skipping:
            if "]" in line:
                skipping = False
            continue
        naked = line.lstrip()
        if naked.startswith(f"{key} ") or naked.startswith(f"{key}="):
            if "[" in line and "]" not in line.split("=", 1)[1]:
                skipping = True
            continue
        out.append(line)
    return out


def _drop_meanings(lines: list[str]) -> list[str]:
    """Remove the `[sources.meanings]` block, keys and all."""
    out: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[sources.meanings]":
            inside = True
            continue
        if inside:
            if _starts_a_table(line):
                inside = False
            elif (stripped and not stripped.startswith("#")) or not stripped:
                continue
        out.append(line)
    return out


def _quote(value: str) -> str:
    """A TOML basic string. Refused rather than escaped for the two
    characters that would need it: a meaning with a newline or a backslash in
    it is a sentence somebody pasted, not a caption."""
    if "\n" in value or "\\" in value or '"' in value:
        raise ConfigError(f"{value!r} cannot be written as a TOML string")
    return f'"{value}"'


def write(
    config: Config,
    project: str,
    work_key: str,
    *,
    meanings: dict[str, str],
    units_from: list[str] | None,
) -> None:
    """Record what this work's marks mean, and which of them make units.

    `units_from` of `None` leaves the key alone, which is how a work with
    no marks is saved: it has no kinds and no colours, so the question does
    not arise and a written-out empty list would be an answer nobody gave.
    An empty list *is* an answer, and it is written.

    Leaving it alone means leaving the line where it is. It used to be
    dropped first and re-appended only when there was something to append,
    so saving a caption on a work whose column was not drawn deleted the
    work's own scheme, and the next `apply_scheme` then judged its units
    against the repo-wide one.
    """
    spec = config.projects.get(project)
    if spec is None:
        raise ConfigError(f"no project {project!r}")
    index = next(
        (n for n, work in enumerate(spec.sources) if work.key == work_key), -1
    )
    if index < 0:
        raise ConfigError(f"{project} does not read {work_key!r}")
    path = path_for(config, project)
    if not path.exists():
        raise ConfigError(
            f"{project} is configured in forge.toml rather than in its own "
            f"{PROJECT_TOML}; edit the table there"
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = table_span(lines, index)
    body = lines[start + 1 : end]
    if units_from is not None:
        body = _drop_key(body, "units_from")
    body = _drop_meanings(body)
    while body and not body[-1].strip():
        body.pop()

    if units_from is not None:
        pairs = ", ".join(_quote(pair) for pair in sorted(units_from))
        body.append(f"units_from = [{pairs}]")
    if meanings:
        body.append("")
        body.append("[sources.meanings]")
        for pair, means in sorted(meanings.items()):
            body.append(f"{_quote(pair)} = {_quote(means)}")

    out = [*lines[:start], lines[start], *body, "", *lines[end:]]
    text = "\n".join(out).rstrip("\n") + "\n"
    # Parsed before it is written: a file this refuses to read is a project
    # that will not load, and the app would have written it while telling
    # you it had saved.
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - a bug, not a state
        raise ConfigError(
            f"refusing to write a {PROJECT_TOML} that will not parse: {exc}"
        ) from exc
    model.write_atomic(path, text)


def _write_key(
    config: Config, project: str, work_key: str, key: str, literal: str | None
) -> None:
    """Put `key = <literal>` in a work's `[[sources]]` table, or take it out.

    The same line-wise edit `write` makes, for the keys that are one value:
    `note`, `url`, `extract`, and whatever else turns out to be worth
    typing into a panel rather than into the file. `literal` is already
    TOML, so the caller decides whether it is a quoted string or a bare
    `true`.
    """
    spec = config.projects.get(project)
    if spec is None:
        raise ConfigError(f"no project {project!r}")
    index = next((n for n, work in enumerate(spec.sources) if work.key == work_key), -1)
    if index < 0:
        raise ConfigError(f"{project} does not read {work_key!r}")
    path = path_for(config, project)
    if not path.exists():
        raise ConfigError(
            f"{project} is configured in forge.toml rather than in its own "
            f"{PROJECT_TOML}; edit the table there"
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = table_span(lines, index)
    body = _drop_key(lines[start + 1 : end], key)
    if literal is not None:
        # Above any sub-table of its own: a key after `[sources.meanings]`
        # would belong to the sub-table, not to the work.
        at = next(
            (n for n, line in enumerate(body) if _is_own_subtable(line)), len(body)
        )
        body.insert(at, f"{key} = {literal}")
    out = [*lines[:start], lines[start], *body, *lines[end:]]
    text = "\n".join(out).rstrip("\n") + "\n"
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - a bug, not a state
        raise ConfigError(
            f"refusing to write a {PROJECT_TOML} that will not parse: {exc}"
        ) from exc
    model.write_atomic(path, text)


def drop_table(config: Config, project: str, work_key: str) -> None:
    """Remove a work's whole `[[sources]]` table from `project.toml`.

    Line-wise, like everything else here: the file is mostly comments and a
    round trip through a TOML writer would return a correct file with all
    of them gone. The comments *inside* the table go with it, because they
    describe the thing being removed; everything around it is untouched.
    """
    spec = config.projects.get(project)
    if spec is None:
        raise ConfigError(f"no project {project!r}")
    index = next((n for n, work in enumerate(spec.sources) if work.key == work_key), -1)
    if index < 0:
        raise ConfigError(f"{project} does not read {work_key!r}")
    path = path_for(config, project)
    if not path.exists():
        raise ConfigError(
            f"{project} is configured in forge.toml rather than in its own "
            f"{PROJECT_TOML}; remove the table there"
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    start, end = table_span(lines, index)
    # Any comment lines sitting directly above the header belong to it: they
    # were written about this work, and leaving them behind would caption
    # whatever table ends up in its place.
    while start and lines[start - 1].lstrip().startswith("#"):
        start -= 1
    kept = [*lines[:start], *lines[end:]]
    while kept and not kept[-1].strip():
        kept.pop()
    text = "\n".join(kept).rstrip("\n") + "\n"
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - a bug, not a state
        raise ConfigError(
            f"refusing to write a {PROJECT_TOML} that will not parse: {exc}"
        ) from exc
    model.write_atomic(path, text)


def set_flag(config: Config, project: str, work_key: str, key: str, value: bool | None) -> None:
    """Set a `true`/`false` key in a work's table, or remove it.

    `None` removes, which is not the same as `false`: nobody said is what
    lets a work inherit the ordinary answer, and writing the ordinary
    answer down makes it look chosen.
    """
    _write_key(config, project, work_key, key, None if value is None else str(value).lower())


def set_key(config: Config, project: str, work_key: str, key: str, value: str) -> None:
    """Set one plain string key in a work's `[[sources]]` table, or drop it.

    An empty value removes the key, because a `note = ""` sitting in the
    table is a caption somebody wrote and then deleted, which reads as a
    considered blank.
    """
    _write_key(config, project, work_key, key, _quote(value) if value else None)


def set_list(config: Config, project: str, work_key: str, key: str, values: list[str]) -> None:
    """Set a list-of-strings key in a work's table, or remove it when empty."""
    if not values:
        _write_key(config, project, work_key, key, None)
        return
    inside = ", ".join(_quote(value) for value in values)
    _write_key(config, project, work_key, key, f"[{inside}]")
