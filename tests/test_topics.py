"""Topics, their outlines, and the setup stage over them.

A source answers "what does this say". A topic answers "what should we
cover", and it exists for the case where no source can (ROADMAP.md 10). The
outline is the only defence against a proposing pass that stops halfway,
which otherwise looks exactly like a subject that was smaller than you
thought.

The join between an outline entry and the unit proposed from it is the slug,
which is what `units --add` was built around, so coverage is a set
difference rather than a guess.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from anki_math_forge import cli, topics
from anki_math_forge import config as config_mod
from anki_math_forge.app import create_app

OUTLINE = """# What this deck is for

## the standard containers

I care about choosing between them and about invalidation, not the full API.

- vector erase-remove
- when a vector invalidates
- deque vs vector
"""


def run(repo: Path, *args: str) -> int:
    return cli.main(["--root", str(repo), *args])


def a_project(repo: Path, outline: str = OUTLINE) -> Path:
    run(repo, "project", "cpp", "--title", "Modern C++", "--deck", "Cpp")
    folder = repo / "projects" / "cpp"
    if outline:
        (folder / "topics.md").write_text(outline, encoding="utf-8")
    return folder


def client(repo: Path) -> TestClient:
    return TestClient(create_app(config_mod.load(repo)))


# -- reading the file -------------------------------------------------------


def test_a_topic_is_a_heading_an_ask_and_a_list(repo: Path) -> None:
    a_project(repo)

    found = topics.read(config_mod.load(repo), "cpp")

    assert [t.name for t in found] == ["the standard containers"]
    assert found[0].ask.startswith("I care about choosing")
    assert [e.text for e in found[0].outline] == [
        "vector erase-remove",
        "when a vector invalidates",
        "deque vs vector",
    ]


def test_the_file_title_is_not_a_topic(repo: Path) -> None:
    """Level one is the file's own heading. A subject called "What this deck
    is for" would be one nobody wrote."""
    a_project(repo)

    assert len(topics.read(config_mod.load(repo), "cpp")) == 1


def test_a_project_with_no_file_has_no_topics(repo: Path) -> None:
    """The normal case: most projects have a source doing the job."""
    a_project(repo, outline="")

    assert topics.read(config_mod.load(repo), "cpp") == []


# -- coverage ---------------------------------------------------------------


def test_an_entry_is_covered_by_the_unit_it_slugifies_to(repo: Path) -> None:
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")

    cover = topics.coverage(config_mod.load(repo), "cpp")

    assert (cover.entries, cover.covered, cover.open) == (3, 1, 2)
    assert [e.text for e in cover.topics[0].open] == [
        "when a vector invalidates",
        "deque vs vector",
    ]


def test_a_differently_typed_entry_still_matches(repo: Path) -> None:
    """The slug settles identity, which is the same rule that makes a
    re-run of a request add only what is new."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "Vector Erase-Remove!", "--gist", "x")

    assert topics.coverage(config_mod.load(repo), "cpp").covered == 1


def test_segmented_units_are_not_mistaken_for_coverage(repo: Path) -> None:
    """A book's unit is `<project>:<section>:<number>`, which no outline
    entry will ever slugify to. A project with both is not confused by it."""
    a_project(repo)
    cover = topics.coverage(config_mod.load(repo), "cpp")

    assert cover.covered == 0


# -- recording an ask -------------------------------------------------------


def test_appending_records_the_ask(repo: Path) -> None:
    a_project(repo, outline="")
    config = config_mod.load(repo)

    topics.append(config, "cpp", "iterator invalidation", "when each one invalidates.")

    found = topics.read(config, "cpp")
    assert [t.name for t in found] == ["iterator invalidation"]
    assert found[0].ask == "when each one invalidates."


def test_asking_twice_is_not_two_topics(repo: Path) -> None:
    """The file is something you edit, and a tool that appended a second
    heading for the same subject would be fighting you for it."""
    a_project(repo)
    config = config_mod.load(repo)

    topics.append(config, "cpp", "the standard containers", "again")

    assert len(topics.read(config, "cpp")) == 1
    assert "again" not in (repo / "projects" / "cpp" / "topics.md").read_text(encoding="utf-8")


def test_the_existing_file_is_not_rewritten(repo: Path) -> None:
    a_project(repo)
    config = config_mod.load(repo)

    topics.append(config, "cpp", "ownership")

    text = (repo / "projects" / "cpp" / "topics.md").read_text(encoding="utf-8")
    assert "I care about choosing between them" in text, "the ask you wrote is untouched"
    assert "- deque vs vector" in text


# -- the setup stage --------------------------------------------------------


def test_the_setup_view_shows_the_outline_and_what_is_open(repo: Path) -> None:
    """The one thing you cannot read off the file: which entries have units."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")

    page = client(repo).get("/setup?project=cpp").text

    assert "the standard containers" in page
    assert "1 of 3" in page
    assert "when a vector invalidates" in page


def test_the_setup_view_works_for_a_project_with_a_document(repo: Path) -> None:
    """Every project has had this stage all along; it just had no screen."""
    page = client(repo).get("/setup?project=demo")

    assert page.status_code == 200
    assert "demo.tex" in page.text or "authoritative" in page.text


def test_the_view_says_when_the_ambient_setting_is_missing(repo: Path) -> None:
    """With no book to read it off, `conventions.md` decides what the deck
    does rather than describing it, so its absence is worth saying."""
    a_project(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert "No <code>conventions.md</code>" in page


def test_recording_an_ask_from_the_view_writes_the_file(repo: Path) -> None:
    """The one write, and it is a file edit you could make by hand."""
    a_project(repo, outline="")

    answer = client(repo).post("/api/topics/cpp", json={"name": "ownership", "ask": "who owns it"})

    assert answer.status_code == 200
    assert answer.json()["slug"] == "ownership"
    text = (repo / "projects" / "cpp" / "topics.md").read_text(encoding="utf-8")
    assert "## ownership" in text and "who owns it" in text


def test_a_nameless_ask_is_refused(repo: Path) -> None:
    a_project(repo, outline="")

    assert client(repo).post("/api/topics/cpp", json={"name": "  "}).status_code == 400


# -- the canvas -------------------------------------------------------------


def a_card(repo: Path, uid: str, gist: str, *tags: str, requires: str = "") -> None:
    path = repo / "cards" / "demo" / f"{uid}-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = ", ".join(f'"{t}"' for t in tags)
    needs = f"requires: [{requires}]\n" if requires else ""
    path.write_text(
        f"---\nuid: {uid}\ntype: identity\nstatus: draft\n"
        f'source: "Demo"\nunit: "demo:1:1"\ngist: {gist}\ntags: [{listed}]\n{needs}---\n\n'
        "## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )


def test_the_canvas_narrows_to_a_subject(repo: Path) -> None:
    """"Filter on these in the graph view" was half of what the rail
    answers on the other two."""
    a_card(repo, "aa11bb", "a trace fact", "traces")
    a_card(repo, "cc22dd", "a determinant fact", "determinants")

    drawn = client(repo).get("/api/graph/demo?all=1&tag=traces").json()

    assert [n["id"] for n in drawn["nodes"]] == ["aa11bb"]
    assert drawn["tag"] == "traces"


def test_a_foundation_outside_the_subject_is_still_drawn(repo: Path) -> None:
    """Hiding what a card rests on would draw it as a foundation it is not,
    which is the one mistake this picture must not make."""
    a_card(repo, "aa11bb", "the foundation", "determinants")
    a_card(repo, "cc22dd", "the dependent", "traces", requires='"aa11bb"')

    drawn = client(repo).get("/api/graph/demo?all=1&tag=traces").json()

    assert {n["id"] for n in drawn["nodes"]} == {"aa11bb", "cc22dd"}


def test_the_canvas_offers_the_subjects_before_the_filter(repo: Path) -> None:
    """Offered from every card here, so the control does not empty itself
    out on the first click."""
    a_card(repo, "aa11bb", "a trace fact", "traces")
    a_card(repo, "cc22dd", "a determinant fact", "determinants")

    drawn = client(repo).get("/api/graph/demo?all=1&tag=traces").json()

    assert {row["name"] for row in drawn["tags"]} == {"traces", "determinants"}


# -- the resolver -----------------------------------------------------------


def test_the_chain_takes_the_first_answer_somebody_gave() -> None:
    """Every per-unit setting walks outwards the same way. Written out at
    each call site, adding a level meant editing all of them."""
    assert config_mod.settled(None, "source", "repo") == "source"
    assert config_mod.settled("unit", "source", "repo") == "unit"
    assert config_mod.settled(None, None, "repo") == "repo"


def test_a_real_refusal_is_an_answer_and_not_a_gap() -> None:
    """The bug this shape is most likely to hide: `False` means "no" for a
    permission, and falling through to the next level would turn a refusal
    into whatever the project happened to say."""
    assert config_mod.settled(False, True, empty=None) is False
    assert config_mod.settled(None, True, empty=None) is True
    # And where zero is a real value, it is only `-1` that means nobody said.
    assert config_mod.settled(0, 3, empty=-1) == 0
    assert config_mod.settled(-1, 3, empty=-1) == 3


# -- the rest of the file edits §12 asks for --------------------------------


def test_a_project_can_be_started_from_the_view(repo: Path) -> None:
    """A file edit with no model behind it. `forge project` writes the same
    file, through the same function, which is how invariant 2 stays true."""
    answer = client(repo).post("/api/projects", json={"name": "Modern C++", "deck": "Cpp"})

    assert answer.status_code == 200
    assert answer.json()["project"] == "modern-c"
    assert config_mod.load(repo).project("modern-c").deck == "Cpp"


def test_the_new_project_is_on_the_picker_without_a_restart(repo: Path) -> None:
    """The app read its config once at start, so a project created while it
    was running was one it had never heard of. DESIGN.md §6 already said it
    re-reads from disk on every request; the config was the part that did
    not."""
    app = create_app(config_mod.load(repo))
    live = TestClient(app)
    assert "later" not in {row["name"] for row in live.get("/api/projects").json()["projects"]}

    live.post("/api/projects", json={"name": "later"})

    assert "later" in {row["name"] for row in live.get("/api/projects").json()["projects"]}


def test_starting_one_twice_leaves_the_first_alone(repo: Path) -> None:
    client(repo).post("/api/projects", json={"name": "cpp", "deck": "Mine"})

    assert client(repo).post("/api/projects", json={"name": "cpp"}).status_code == 400
    assert config_mod.load(repo).project("cpp").deck == "Mine"


def test_a_shelf_line_can_be_dropped(repo: Path) -> None:
    """Deleting the line is how you say you do not want a reference, the
    same shape as resolving an annotation."""
    folder = a_project(repo, outline="")
    (folder / "references.md").write_text(
        "# References\n\n- cppreference\n- a blog post I am not sure about\n", encoding="utf-8"
    )

    answer = client(repo).post(
        "/api/references/cpp", json={"line": "- a blog post I am not sure about"}
    )

    assert answer.status_code == 200
    left = (folder / "references.md").read_text(encoding="utf-8")
    assert "cppreference" in left
    assert "blog post" not in left


def test_dropping_a_line_that_is_not_there_is_refused(repo: Path) -> None:
    folder = a_project(repo, outline="")
    (folder / "references.md").write_text("- cppreference\n", encoding="utf-8")

    assert client(repo).post("/api/references/cpp", json={"line": "- nope"}).status_code == 404


# -- routing a deck by tag --------------------------------------------------


def with_decks(repo: Path, block: str) -> config_mod.Config:
    a_project(repo, outline="")
    path = repo / "projects" / "cpp" / "project.toml"
    path.write_text(f'title = "C++"\ndeck = "Cpp"\n\n{block}', encoding="utf-8")
    return config_mod.load(repo)


BY_TAG = (
    "[decks.by_tag]\ncontainers = \"Cpp::Containers\"\nalgorithms = \"Cpp::Algorithms\"\n"
)


def test_a_tag_routes_a_card_to_its_own_deck(repo: Path) -> None:
    """A project on a subject splits by what its cards are about, not by
    what kind of card they are."""
    config = with_decks(repo, BY_TAG)

    assert config.deck_for("cpp", "identity", ["containers"]) == "Cpp::Containers"
    assert config.deck_for("cpp", "identity", ["nothing"]) == "Cpp"


def test_file_order_settles_a_card_with_two(repo: Path) -> None:
    """Somewhere predictable rather than somewhere alphabetical."""
    config = with_decks(repo, BY_TAG)

    assert config.deck_for("cpp", "", ["algorithms", "containers"]) == "Cpp::Containers"


def test_a_tag_outranks_a_type(repo: Path) -> None:
    """A tag names one card's subject; a type names a whole class of card."""
    config = with_decks(repo, BY_TAG + '\n[decks.by_type]\nintuition = "Cpp::Ideas"\n')

    assert config.deck_for("cpp", "intuition", ["containers"]) == "Cpp::Containers"
    assert config.deck_for("cpp", "intuition", []) == "Cpp::Ideas"


def test_the_flat_form_is_still_the_type_map(repo: Path) -> None:
    """`[decks]` meant type to deck before there were two tables."""
    config = with_decks(repo, '[decks]\nintuition = "Cpp::Ideas"\n')

    assert config.deck_for("cpp", "intuition", []) == "Cpp::Ideas"


def test_re_tagging_moves_the_deck_without_un_approving(repo: Path) -> None:
    """The two halves of this had to land together: routing by tag is no use
    if re-tagging demotes the card, and the exemption is no use without
    something that routes."""
    from anki_math_forge import model

    config = with_decks(repo, BY_TAG)
    path = repo / "cards" / "cpp" / "aa11bb-x.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nuid: aa11bb\ntype: identity\nstatus: draft\n"
        'source: "C++"\nunit: "cpp:x"\ntags: ["containers"]\n---\n\n'
        "## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )
    card = model.load(path)
    card.approve()
    card.save()
    assert config.deck_for("cpp", card.type, card.tags) == "Cpp::Containers"

    card = model.load(path)
    card.frontmatter["tags"] = ["algorithms"]
    card.save()

    moved = model.load(path)
    assert moved.effective_status == "approved", "filing is not what a reviewer read"
    assert config.deck_for("cpp", moved.type, moved.tags) == "Cpp::Algorithms"


def test_the_command_and_the_view_write_the_same_file(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Two ways to write one file is how the two drift, so both go through
    one function. Invariant 2 is only true while they cannot disagree."""
    a_project(repo, outline="")
    run(repo, "topic", "--project", "cpp", "the standard containers", "--ask", "why")
    by_command = (repo / "projects" / "cpp" / "topics.md").read_text(encoding="utf-8")

    other = tmp_path_factory.mktemp("other")
    (other / "forge.toml").write_text(
        '[repo]\ncards_dir = "cards"\nprojects_dir = "projects"\n', encoding="utf-8"
    )
    (other / "cards").mkdir()
    a_project(other, outline="")
    client(other).post(
        "/api/topics/cpp", json={"name": "the standard containers", "ask": "why"}
    )
    by_view = (other / "projects" / "cpp" / "topics.md").read_text(encoding="utf-8")

    assert by_command == by_view


def test_the_command_refuses_a_project_that_is_not_there(repo: Path) -> None:
    assert run(repo, "topic", "--project", "nope", "a subject") == 1
