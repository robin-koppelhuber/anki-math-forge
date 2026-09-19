"""`forge context` for a unit with no page.

Everything the tool hands a card writer assumed a document: a crop to read,
a page of prose around it, a transcription of the maths. A unit proposed
into a project with no authoritative source has none of those, and the
honest thing is to say so rather than to hand over an empty page and let the
pass fill the gap from memory (ROADMAP.md 10).

What replaces them is weaker and is described as weaker: the references the
unit stands on, the project's shelf, and a plain statement that nothing here
settles what the card says.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import cli
from anki_math_forge import config as config_mod
from anki_math_forge.context import assemble
from anki_math_forge.extract import source_text_path
from anki_math_forge.ledger import Ledger, Locator, Unit


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def a_project(repo: Path, name: str = "cpp") -> Path:
    folder = repo / "projects" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n', encoding="utf-8"
    )
    return folder


def a_unit(repo: Path, **extra: str) -> None:
    args = ["units", "--project", "cpp", "--add", "vector erase-remove",
            "--gist", "erase-remove on a vector"]
    for flag, value in extra.items():
        args += [f"--{flag.replace('_', '-')}", value]
    run(repo, *args)


def test_it_says_that_nothing_settles_the_card(repo: Path) -> None:
    a_project(repo)
    a_unit(repo)

    ctx = assemble(config_mod.load(repo), "cpp:vector-erase-remove")

    assert ctx is not None
    assert ctx.settled is False
    body = ctx.format()
    assert "no authoritative source" in body
    assert "weaker guarantees" in body
    assert "`## notes`" in body, "the one half of invariant 7 that still applies"


def test_a_page_backed_unit_is_unaffected(repo: Path) -> None:
    """Nothing here is new behaviour for a book. The warning is keyed on what
    the unit has, not on what kind of project it is in."""
    config = config_mod.load(repo)
    led = Ledger(config.units_path("demo"))
    led.units.append(Unit(id="demo:2.2:61", locator=Locator(section="2.2", page=1)))
    led.save()
    text = source_text_path(config, "demo")
    text.parent.mkdir(parents=True, exist_ok=True)
    text.write_text("<!-- page 1 -->\nthe statement, as printed\n", encoding="utf-8")

    ctx = assemble(config, "demo:2.2:61")

    assert ctx is not None
    assert ctx.settled is True
    body = ctx.format()
    assert "no authoritative source" not in body
    assert f"## {ctx.window}" in body, "it still gets the page section"


def test_the_references_are_handed_over_as_references(repo: Path) -> None:
    a_project(repo)
    a_unit(repo, ref="https://en.cppreference.com/w/cpp/algorithm/remove")

    ctx = assemble(config_mod.load(repo), "cpp:vector-erase-remove")

    assert ctx is not None
    assert ctx.refs == ["https://en.cppreference.com/w/cpp/algorithm/remove"]
    body = ctx.format()
    assert "https://en.cppreference.com/w/cpp/algorithm/remove" in body
    assert "where to look, never what to write" in body, (
        "a reference is checked against; only a source settles anything"
    )


def test_the_project_shelf_comes_too(repo: Path) -> None:
    """`references.md` is prose with no schema, so it is handed over whole."""
    folder = a_project(repo)
    (folder / "references.md").write_text(
        "# References\n\n- cppreference, the container overview.\n", encoding="utf-8"
    )
    a_unit(repo)

    ctx = assemble(config_mod.load(repo), "cpp:vector-erase-remove")

    assert ctx is not None
    assert "cppreference, the container overview." in ctx.format()
    assert "# References" not in ctx.shelf, "the title is the file's, not content"


def test_a_snippet_is_fenced_and_a_formula_is_not(repo: Path) -> None:
    """A preview handed over bare reads as prose, and a reader has to guess
    where the code ends."""
    a_project(repo)
    a_unit(repo, preview="v.erase(it);", lang="cpp")

    ctx = assemble(config_mod.load(repo), "cpp:vector-erase-remove")

    assert ctx is not None
    assert ctx.lang == "cpp"
    assert "```cpp\nv.erase(it);\n```" in ctx.format()


def test_no_web_access_does_not_promise_pages_that_are_not_there(repo: Path) -> None:
    """The refusal used to say everything comes from "the pages below", which
    on a unit with no page is an instruction to read nothing."""
    a_project(repo)
    a_unit(repo, ref="https://example.invalid/x")

    ctx = assemble(config_mod.load(repo), "cpp:vector-erase-remove")

    assert ctx is not None
    body = ctx.format()
    assert "comes from the references below" in body
    assert "the pages below" not in body
