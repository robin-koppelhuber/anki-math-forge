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

import pathlib
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


def test_everything_the_project_holds_is_a_row_and_a_panel(repo: Path) -> None:
    """A list on the left, a panel on the right. Both are rendered here, so
    the page is still a plain document with the script doing nothing."""
    a_project(repo)

    page = client(repo).get("/setup?project=cpp").text

    for pane in ("project", "topic:the-standard-containers", "new-topic"):
        assert page.count(f'data-pane="{pane}"') == 2, f"{pane}: a row and a panel"
    assert "new-project" not in page, "starting another one belongs in the picker"


def test_a_source_pane_says_where_each_setting_was_settled(repo: Path) -> None:
    """"40 points" and "40 points, because nobody said otherwise" are
    different answers to the question you open the pane with."""
    page = client(repo).get("/setup?project=demo").text

    assert 'data-pane="source:' in page
    assert "crop_context" in page and "crop_width" in page
    assert "inherited" in page


def test_a_source_with_no_title_is_still_named(repo: Path) -> None:
    """A work migrated from a project-wide `tex` has neither a title nor a
    key, and a pane headed by nothing reads as a broken one."""
    page = client(repo).get("/setup?project=demo").text

    assert "demo.tex" in page


def test_a_segmented_source_is_not_asked_about_its_marks(repo: Path) -> None:
    """A book with no marking scheme has none and never will. A row reading
    "nothing declared" describes machinery that is not running."""
    page = client(repo).get("/setup?project=demo").text

    assert "units_from" not in page


# -- which works an ask drew on --------------------------------------------


def two_sources(repo: pathlib.Path) -> None:
    """A project that reads a book and checks itself against a website.

    Written by hand rather than through `forge project`, because the point is
    two `[[sources]]` in one project: that is the cluster case, and nothing
    on the command line makes one yet.
    """
    a_project(repo)
    folder = repo / "projects" / "cpp"
    (folder / "book.tex").write_text("the book\n", encoding="utf-8")
    (folder / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n\n'
        "[[sources]]\n"
        'key = "book"\ntitle = "The Standard Library"\n'
        'files = ["projects/cpp/book.tex"]\ncontext_pages = 2\n\n'
        "[[sources]]\n"
        'key = "cppref"\ntitle = "cppreference"\n'
        'url = "https://en.cppreference.com/"\n',
        encoding="utf-8",
    )


def test_an_ask_is_linked_to_the_work_its_units_came_out_of(repo: Path) -> None:
    """Derived, not declared: a unit records the document it was printed in,
    and an outline entry joins to its units by slug. A third list in a file
    would be a fourth thing to keep in step."""
    two_sources(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove",
        "--gist", "x", "--document", "book")

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-works="book"' in page
    assert 'data-topics="the-standard-containers"' in page


def test_a_reference_is_linked_by_the_url_a_unit_cites(repo: Path) -> None:
    """A unit cites the page; the source is the site. The deeper one is the
    one that starts with the other."""
    two_sources(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x",
        "--ref", "https://en.cppreference.com/w/cpp/container/vector")

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-works="cppref"' in page


def test_a_unit_with_no_document_links_to_nothing(repo: Path) -> None:
    """A project with one work resolves an empty document to it, which would
    link every ask to the book whether or not anything was read out of it."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-works=""' in page


def test_a_source_row_says_what_it_is(repo: Path) -> None:
    """The filter above the list needs something to filter on, and the row
    should say which kind it is without one."""
    two_sources(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-kind="authoritative"' in page
    assert 'data-kind="reference"' in page
    assert 'id="source-filter"' in page


def test_a_window_can_be_a_fact_about_one_document(repo: Path) -> None:
    """How much a page carries is a fact about how a book is set, and a
    project reading a textbook and a paper has two answers."""
    two_sources(repo)
    loaded = config_mod.load(repo)

    assert loaded.context_pages_for("cpp", document="book") == 2
    assert loaded.context_pages_for("cpp", document="cppref") == loaded.context_pages
    # The unit still outranks the work: triage is where you can see that the
    # hypotheses are two pages back.
    assert loaded.context_pages_for("cpp", 5, "book") == 5


# -- carrying a selection into triage ---------------------------------------


def test_the_units_view_narrows_to_one_ask(repo: Path) -> None:
    """The selection you made on the setup stage is worth carrying. Re-making
    it by hand in the triage view was the one thing that screen could not
    hand over."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")
    run(repo, "units", "--project", "cpp", "--add", "unrelated thing", "--gist", "y")

    page = client(repo).get(
        "/units?project=cpp&topic=the-standard-containers&state=all"
    ).text

    assert "cpp:vector-erase-remove" in page
    assert "cpp:unrelated-thing" not in page


def test_the_units_view_narrows_to_one_work(repo: Path) -> None:
    """By work, and the work is asked for rather than matched: a Zotero item
    declares its *item* key while its units carry *attachment* keys, so a
    string comparison against the key matched nothing at all."""
    two_sources(repo)
    (repo / "projects" / "cpp" / "paper.tex").write_text("x\n", encoding="utf-8")
    path = repo / "projects" / "cpp" / "project.toml"
    second = "\n".join(
        ['[[sources]]', 'key = "paper"', 'files = ["projects/cpp/paper.tex"]', "", ""]
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '[[sources]]\nkey = "cppref"', second + '[[sources]]\nkey = "cppref"'
        ),
        encoding="utf-8",
    )
    run(repo, "units", "--project", "cpp", "--add", "from the book", "--gist", "x",
        "--document", "book")
    run(repo, "units", "--project", "cpp", "--add", "from the paper", "--gist", "y",
        "--document", "paper")

    page = client(repo).get("/units?project=cpp&document=book&state=all").text

    assert "cpp:from-the-book" in page
    assert "cpp:from-the-paper" not in page


def test_a_work_claims_the_units_nobody_placed(repo: Path) -> None:
    """With one work to read, a unit that names no document came out of it:
    that is what `ProjectConfig.source("")` says, and it is what makes the
    Cookbook's own panel count its units rather than zero."""
    two_sources(repo)
    run(repo, "units", "--project", "cpp", "--add", "from nowhere", "--gist", "y")

    page = client(repo).get("/units?project=cpp&document=book&state=all").text

    assert "cpp:from-nowhere" in page


def test_an_ask_arrived_at_is_a_chip_you_can_take_off(repo: Path) -> None:
    """It used to be a read-only line saying where the deck came in from,
    because the rail had no control for it. It is the same control as the
    tags now, so what is on shows as a chip with its own way out."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")

    page = client(repo).get(
        "/units?project=cpp&topic=the-standard-containers&state=all"
    ).text

    assert ">topics<" in page
    assert "pick-chip f-topic" in page
    assert "the standard containers" in page
    assert "filter-scope" not in page


def test_the_review_view_takes_the_same_two(repo: Path) -> None:
    """A card carries neither, so both resolve through the unit it was
    written from."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "vector erase-remove", "--gist", "x")
    folder = repo / "cards" / "cpp"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "aa11bb-x.md").write_text(
        "---\nuid: aa11bb\ntype: identity\nstatus: draft\n"
        'source: "Modern C++"\nunit: "cpp:vector-erase-remove"\ngist: the erase-remove idiom\n'
        "---\n\n## front\n\n$a$\n\n## back\n\n$b$\n",
        encoding="utf-8",
    )

    mine = client(repo).get(
        "/review?project=cpp&topic=the-standard-containers&status=all"
    ).text
    assert "the erase-remove idiom" in mine

    other = client(repo).get("/review?project=cpp&topic=nothing-like-it&status=all").text
    assert "the erase-remove idiom" not in other


def test_each_panel_offers_what_to_run_from_it(repo: Path) -> None:
    """An ask and a work want different passes, and the scope is the thing
    this screen can say that the triage rail cannot."""
    two_sources(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-runs="project"' in page
    assert 'data-runs="topic:the-standard-containers"' in page
    assert 'data-runs="source:book"' in page
    # The ask by name, because that is the argument the pass takes.
    assert "/propose --project &#34;cpp&#34; &#34;the standard containers&#34;" in page


def test_a_reference_has_nothing_to_run(repo: Path) -> None:
    """Every pass on a work is about cutting a crop out of a page, and a
    reference has no page here to cut."""
    two_sources(repo)

    page = client(repo).get("/setup?project=cpp").text
    at = page.index('data-runs="source:cppref"')

    assert "nothing to run" in page[at : at + 400]


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

    drawn = client(repo).get("/api/graph/demo?all=1&has=traces").json()

    assert [n["id"] for n in drawn["nodes"]] == ["aa11bb"]
    assert drawn["has"] == "traces"


def test_a_foundation_outside_the_subject_is_still_drawn(repo: Path) -> None:
    """Hiding what a card rests on would draw it as a foundation it is not,
    which is the one mistake this picture must not make."""
    a_card(repo, "aa11bb", "the foundation", "determinants")
    a_card(repo, "cc22dd", "the dependent", "traces", requires='"aa11bb"')

    drawn = client(repo).get("/api/graph/demo?all=1&has=traces").json()

    assert {n["id"] for n in drawn["nodes"]} == {"aa11bb", "cc22dd"}


def test_the_canvas_offers_the_subjects_before_the_filter(repo: Path) -> None:
    """Offered from every card here, so the control does not empty itself
    out on the first click."""
    a_card(repo, "aa11bb", "a trace fact", "traces")
    a_card(repo, "cc22dd", "a determinant fact", "determinants")

    drawn = client(repo).get("/api/graph/demo?all=1&has=traces").json()

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
    assert answer.json()["project"] == "modern-cpp", "`c++` spells `cpp`"
    assert config_mod.load(repo).project("modern-cpp").deck == "Cpp"


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


def test_a_cluster_is_not_badged_as_unconfigured(repo: Path) -> None:
    """`spec.source()` answers nothing for a project reading two books, by
    design. Read as "no material at all", it badged a cluster of three
    papers in the picker as having no `project.toml`."""
    two_sources(repo)
    config = config_mod.load(repo)

    from anki_math_forge.app import project_origin

    assert project_origin(config, "cpp") == "pdf", "one kind of work, said plainly"

    # A second work that arrived another way. They disagree, and saying so is
    # the honest answer: nobody resolves anything against this.
    text = (repo / "projects" / "cpp" / "project.toml").read_text(encoding="utf-8")
    text = text.replace(
        '[[sources]]\nkey = "cppref"',
        '[[sources]]\nkey = "ABCD1234"\nzotero = "ABCD1234"\n\n[[sources]]\nkey = "cppref"',
    )
    (repo / "projects" / "cpp" / "project.toml").write_text(text, encoding="utf-8")

    assert project_origin(config_mod.load(repo), "cpp") == "mixed"


def test_a_project_with_no_work_has_no_origin(repo: Path) -> None:
    """Which is not the same as having no config: a project for a subject
    declares topics and no sources, and that is the shape the feature is
    for."""
    a_project(repo)

    from anki_math_forge.app import project_origin

    assert project_origin(config_mod.load(repo), "cpp") == ""


def test_a_zotero_work_is_not_offered_extract(repo: Path) -> None:
    """`extract` segments a document in the repo. Against an imported item
    it does nothing, and a command that does nothing is worse than none."""
    a_project(repo)
    (repo / "projects" / "cpp" / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n\n'
        '[[sources]]\nkey = "ABCD1234"\nzotero = "ABCD1234"\ntitle = "A paper"\n',
        encoding="utf-8",
    )

    page = client(repo).get("/setup?project=cpp").text
    at = page.index('data-runs="source:ABCD1234"')
    pane = page[at : at + 1200]

    assert "forge zotero" in pane
    assert "forge extract" not in pane


def test_a_file_work_is_offered_extract(repo: Path) -> None:
    two_sources(repo)

    page = client(repo).get("/setup?project=cpp").text
    at = page.index('data-runs="source:book"')

    assert "forge extract" in page[at : at + 1200]


def test_creating_a_topic_is_not_called_recording_an_ask(repo: Path) -> None:
    """The panel writes a topic. "Record an ask" named the field, not the
    thing, and read like something nobody says out loud."""
    a_project(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert "create a topic" in page
    assert "record an ask" not in page and "record the ask" not in page
    # And the command it hands you afterwards is a copy button like every
    # other, not a `<code>` in a sentence.
    at = page.index('data-pane="new-topic"', page.index("setup-detail"))
    assert 'data-copy="/propose' in page[at : at + 2000]

# -- which work a unit belongs to -------------------------------------------


def test_a_zotero_work_owns_the_units_that_name_its_attachments(repo: Path) -> None:
    """A Zotero work declares the *item* key while its units carry
    *attachment* keys, and empty `attachments` means all of them. Matched by
    hand, the Krause book's panel counted zero units for a work with
    fifty-six, and offered it the transcription pass it had ruled out."""
    import json as json_mod

    from anki_math_forge.app import source_facts

    a_project(repo)
    (repo / "projects" / "cpp" / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n\n'
        '[[sources]]\nzotero = "ITEMKEY1"\n',
        encoding="utf-8",
    )
    (repo / "projects" / "cpp" / "units.jsonl").write_text(
        json_mod.dumps({
            "id": "cpp:ABC",
            "state": "new",
            "locator": {"document": "ATTACH99", "page": 1},
            "marks": [{"kind": "highlight", "colour": "blue", "bbox": [0, 0, 1, 1]}],
        })
        + "\n",
        encoding="utf-8",
    )
    config = config_mod.load(repo)
    spec = config.projects["cpp"]
    units = list(topics.Ledger.load(config.units_path("cpp")))

    facts = source_facts(config, "cpp", spec.sources[0], units)

    assert facts["units"] == 1, "the attachment belongs to the item"
    assert facts["from_marks"] is True


def test_a_marked_up_work_is_not_offered_the_transcription_pass(repo: Path) -> None:
    """You do not need a transcription to triage a mark, and the triage rail
    has known that for a while. The setup column had not."""
    import json as json_mod

    a_project(repo)
    (repo / "projects" / "cpp" / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n\n'
        '[[sources]]\nzotero = "ITEMKEY1"\n',
        encoding="utf-8",
    )
    (repo / "projects" / "cpp" / "units.jsonl").write_text(
        json_mod.dumps({
            "id": "cpp:ABC",
            "state": "new",
            "locator": {"document": "ATTACH99", "page": 1},
            "marks": [{"kind": "highlight", "colour": "blue", "bbox": [0, 0, 1, 1]}],
        })
        + "\n",
        encoding="utf-8",
    )

    page = client(repo).get("/setup?project=cpp").text
    pane = page[page.index('data-runs="source:ITEMKEY1"') :][:3000]

    assert "/transcribe" not in pane
    assert "run-note" not in pane, "left out, not explained: this pane has work in it"
    assert "forge zotero" in pane and "forge extract" not in pane


# -- narrow first, then the whole repo --------------------------------------


def test_the_narrow_command_comes_before_the_repo_wide_one(repo: Path) -> None:
    """You are looking at one project, so the command about that project is
    the one you want, and the repo-wide form is the one you reach for
    afterwards."""
    a_project(repo)

    page = client(repo).get("/setup?project=cpp").text
    # This pane only: the next one starts at the next `data-runs`, and the
    # commands for a project run long enough that a fixed window would clip
    # the last of them.
    rest = page[page.index('data-runs="project"') + 1 :]
    pane = rest[: rest.find("data-runs=")]

    mine = pane.index("forge sync --project")
    every = pane.index("uv run forge sync --dry-run")
    assert mine < every, "this project first"


# -- every work in the repo, once -------------------------------------------


def test_the_index_lists_a_work_from_every_project(repo: Path) -> None:
    """A source used to *be* a project, so "which sources are there" was the
    project list. It is a thing inside one now, and a paper can sit in two."""
    from anki_math_forge.app import every_work

    two_sources(repo)
    rows = every_work(config_mod.load(repo))

    assert {r["key"] for r in rows} >= {"book", "cppref"}
    assert {r["project"] for r in rows} >= {"cpp", "demo"}


def test_a_known_work_can_be_added_to_another_project(repo: Path) -> None:
    """Adding copies nothing on disk: a Zotero work is its item key and a
    reference is its URL, so both projects read the same thing.

    A reference, because that is the half of this that is safe to share: a
    work something is extracted from belongs to one project (see below)."""
    two_sources(repo)
    # `demo` cites what `cpp` reads on the web.
    seen = client(repo).post("/api/sources/demo", json={"key": "cppref"})
    assert seen.status_code == 409, "demo is configured in forge.toml"

    # So the other way round, into a project with a file of its own.
    (repo / "projects" / "other").mkdir(parents=True)
    (repo / "projects" / "other" / "project.toml").write_text(
        'title = "Another"\n', encoding="utf-8"
    )
    seen = client(repo).post("/api/sources/other", json={"key": "cppref"})

    assert seen.status_code == 200
    text = (repo / "projects" / "other" / "project.toml").read_text(encoding="utf-8")
    assert 'key = "cppref"' in text
    assert "https://en.cppreference.com/" in text


def test_a_project_configured_in_the_root_file_says_so(repo: Path) -> None:
    """A folder's file wins over the root file key by key, so writing one
    here would not add a table to `forge.toml`: it would replace that
    project's whole source list with this single entry."""
    two_sources(repo)
    # A reference, so the refusal is about where the config lives rather
    # than about the work already being extracted from somewhere.
    seen = client(repo).post("/api/sources/demo", json={"key": "cppref"})

    assert seen.status_code == 409
    assert "forge.toml" in seen.json()["detail"]


def test_the_same_work_is_not_added_twice(repo: Path) -> None:
    """Two tables with one key is the same work twice, and every count on
    the setup stage would say so."""
    two_sources(repo)

    assert client(repo).post("/api/sources/cpp", json={"key": "book"}).status_code == 409


def test_the_panel_offers_what_this_project_does_not_read(repo: Path) -> None:
    two_sources(repo)

    page = client(repo).get("/setup?project=demo").text

    assert 'data-pane="add-source"' in page
    assert 'data-add-source="book"' in page
    assert 'data-add-source="demo.tex"' not in page, "it already reads that one"


# -- proposing a source, and settling it ------------------------------------


def test_a_proposed_line_is_pending_until_you_take_it(repo: Path) -> None:
    """The checkbox is the whole of the pending state: markdown everyone
    already writes for "not yet", and nothing to keep in step."""
    a_project(repo)
    (repo / "projects" / "cpp" / "references.md").write_text(
        "# References\n\n- [ ] cppreference\n- Bishop, chapter 2\n", encoding="utf-8"
    )

    page = client(repo).get("/setup?project=cpp").text

    assert "proposed, not yet yours" in page
    assert 'data-take-reference="- [ ] cppreference"' in page
    assert "/sources --project" in page, "and a way to get more"


def test_taking_one_makes_it_a_source(repo: Path) -> None:
    """Accepting used to take the checkbox off and leave the prose, so a
    proposed *source* never became one: no panel, no settings, and nowhere
    to write down how to read it. It becomes a `[[sources]]` table now, and
    leaves the shelf, because the same fact in two files is the one that
    drifts."""
    a_project(repo)
    path = repo / "projects" / "cpp" / "references.md"
    line = (
        "- [ ] cppreference, the containers library"
        " (https://en.cppreference.com/w/cpp/container), for the complexity tables"
    )
    path.write_text(f"# References\n\n{line}\n", encoding="utf-8")

    answer = client(repo).post("/api/references/cpp/accept", json={"line": line})

    assert answer.status_code == 200
    assert answer.json()["key"] == "cppreference-the-containers-library"
    assert "cppreference" not in path.read_text(encoding="utf-8"), "off the shelf"

    work = config_mod.load(repo).project("cpp").sources[0]
    assert work.title == "cppreference, the containers library"
    assert work.url == "https://en.cppreference.com/w/cpp/container"
    assert work.note == "for the complexity tables"
    assert not work.authoritative, "nothing is extracted from a reference"


def test_dropping_a_proposed_line_removes_it(repo: Path) -> None:
    """Rejecting is deleting the line, which is the same shape as resolving
    an annotation."""
    a_project(repo)
    path = repo / "projects" / "cpp" / "references.md"
    path.write_text("# References\n\n- [ ] cppreference\n- Bishop\n", encoding="utf-8")

    client(repo).post("/api/references/cpp", json={"line": "- [ ] cppreference"})

    assert "cppreference" not in path.read_text(encoding="utf-8")


# -- carrying the selection over --------------------------------------------


def test_every_panel_offers_the_way_over(repo: Path) -> None:
    """The counts are links too, but each is one state and only exists when
    something is in it, so a topic with nothing proposed yet offered no way
    through at all."""
    two_sources(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert page.count("open in triage") >= 3, "the project, the topic and each work"
    assert "topic=the-standard-containers" in page
    assert "document=book" in page


# -- which work, from the rail ----------------------------------------------


def test_the_rail_offers_the_works_when_there_are_two(repo: Path) -> None:
    """A section answers "where in the book" and this answers "which book",
    which is the question a cluster of papers asks first. The setup stage
    could send you here scoped to a work and the rail could not."""
    two_sources(repo)
    run(repo, "units", "--project", "cpp", "--add", "from the book", "--gist", "x",
        "--document", "book")

    page = client(repo).get("/units?project=cpp&state=all").text

    assert ">sources<" in page
    assert "document=book" in page


def test_one_work_is_the_project_and_needs_no_filter(repo: Path) -> None:
    """A row that selects what is already on screen."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "a subject", "--gist", "x")

    page = client(repo).get("/units?project=cpp&state=all").text

    assert ">sources<" not in page


def test_a_deck_with_no_sections_is_offered_no_section_filter(repo: Path) -> None:
    """Everything lands in one bucket called "no section", which is a
    control that selects what is on screen and reads as a workaround for
    one. The bucket stays wherever there are real sections beside it: it is
    where the units the segmenter could not place go."""
    a_project(repo)
    run(repo, "units", "--project", "cpp", "--add", "a subject", "--gist", "x")

    page = client(repo).get("/units?project=cpp&state=all").text

    assert "no section" not in page
    assert ">sections<" not in page


def test_unplaced_units_keep_their_bucket_beside_real_sections() -> None:
    """Those are the ones most worth finding."""
    from anki_math_forge.app import section_rows

    class Item:
        def __init__(self, section: str, uid: str) -> None:
            self.section, self.uid = section, uid

    rows = section_rows(
        [Item("2.4", "a"), Item("", "b")],
        {"a", "b"},
        lambda i: i.section,
        lambda i: "new",
        lambda i: i.uid,
        ("new",),
    )
    labels = [row["label"] for group in rows for row in group["sections"]]

    assert "no section" in labels


def test_two_works_select_the_union(repo: Path) -> None:
    """A cluster of related papers is read as one deck, so two of them is a
    question you actually ask. Or, like the tags, not and."""
    two_sources(repo)
    (repo / "projects" / "cpp" / "paper.tex").write_text("x\n", encoding="utf-8")
    path = repo / "projects" / "cpp" / "project.toml"
    second = "\n".join(
        ["[[sources]]", 'key = "paper"', 'files = ["projects/cpp/paper.tex"]', "", ""]
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            '[[sources]]\nkey = "cppref"', second + '[[sources]]\nkey = "cppref"'
        ),
        encoding="utf-8",
    )
    for slug, doc in (("one", "book"), ("two", "paper"), ("three", "cppref")):
        run(repo, "units", "--project", "cpp", "--add", slug, "--gist", slug,
            "--document", doc)

    page = client(repo).get("/units?project=cpp&document=book,paper&state=all").text

    assert "cpp:one" in page and "cpp:two" in page
    assert "cpp:three" not in page
    assert page.count("pick-chip f-source") == 2, "and both show as chips"
    assert ">or<" in page, "with the word that says a second one widens"


def test_a_work_is_extracted_from_by_one_project(repo: Path) -> None:
    """A unit lives in one project's ledger and its id starts with that
    project's name, so the same document imported twice is two ledgers of
    units and two notes per card in Anki, with nothing that knows they are
    the same."""
    from anki_math_forge import check as check_mod

    two_sources(repo)
    # The app cannot make a second one at all now: adding a work the repo
    # already reads takes it as a reference, whatever the other project
    # reads it as, because the item key and the files are what make a work
    # authoritative and this does not copy them.
    seen = client(repo).post("/api/sources/cpp", json={"key": "demo.tex"})
    assert seen.status_code == 200
    taken = config_mod.load(repo).project("cpp").source("demo.tex")
    assert taken is not None and not taken.authoritative
    assert not check_mod.check_sources(config_mod.load(repo)), "one extraction"

    # And the rule from the other side, for a pair somebody wrote by hand:
    # every view here is scoped to one project, so two copies look like one
    # copy from wherever you are standing.
    path = repo / "projects" / "cpp" / "project.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'key = "demo.tex"', 'key = "demo.tex"\nfiles = ["projects/demo/demo.tex"]'
        ),
        encoding="utf-8",
    )
    found = check_mod.check_sources(config_mod.load(repo))

    assert [f.code for f in found] == ["source-extracted-twice"]
    assert "cpp" in found[0].message and "demo" in found[0].message


# -- the marking scheme, edited where you can see the marks -----------------


def a_zotero_project(repo: Path) -> Path:
    """One work, imported, with two marks in the ledger."""
    import json as json_mod

    a_project(repo)
    folder = repo / "projects" / "cpp"
    (folder / "project.toml").write_text(
        'title = "Modern C++"\ndeck = "Cpp"\n\n'
        "# What your marks mean here. Uncomment to override.\n"
        "# [meanings]\n\n"
        "[[sources]]\n"
        "# Which Zotero item this came from.\n"
        'zotero = "ITEM1"\n'
        'units_from = ["highlight/blue"]\n',
        encoding="utf-8",
    )
    (folder / "units.jsonl").write_text(
        "\n".join(
            json_mod.dumps({
                "id": f"cpp:{n}",
                "state": "new",
                "locator": {"document": "ATTACH", "page": 1},
                "marks": [{"kind": kind, "colour": colour, "bbox": [0, 0, 1, 1],
                           "key": f"m{n}"}],
            })
            for n, (kind, colour) in enumerate(
                [("highlight", "blue"), ("highlight", "orange")]
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return folder


def test_the_editor_offers_the_pairs_this_work_carries(repo: Path) -> None:
    """Eight colours across six kinds is forty-eight rows and nobody has
    forty-eight meanings. A pair you have never used is not worth a box."""
    a_zotero_project(repo)

    page = client(repo).get("/setup?project=cpp").text

    assert 'data-pair="highlight/blue"' in page
    assert 'data-pair="highlight/orange"' in page
    assert 'data-pair="note/green"' not in page, "nothing is marked with it"


def test_only_an_authoritative_work_is_asked_which_marks_make_units(repo: Path) -> None:
    """A mark cannot make a unit in a document nothing is segmented out of,
    and a box that changes nothing is worse than no box."""
    a_zotero_project(repo)
    page = client(repo).get("/setup?project=cpp").text
    assert "makes a unit" in page

    (repo / "projects" / "cpp" / "project.toml").write_text(
        'title = "Modern C++"\n\n[[sources]]\nkey = "ref"\nurl = "https://x.test/"\n',
        encoding="utf-8",
    )
    page = client(repo).get("/setup?project=cpp").text
    assert "makes a unit" not in page
    assert "scheme-edit" not in page, "and no editor at all: marks are a Zotero thing"


def test_saving_the_scheme_keeps_the_comments(repo: Path) -> None:
    """A generated `project.toml` is mostly comments, and a round trip
    through a TOML writer would produce a correct file with all of them
    gone, which is a worse file than the one you started with."""
    folder = a_zotero_project(repo)

    answer = client(repo).post(
        "/api/scheme/cpp/ITEM1",
        json={
            "meanings": {"highlight/orange": "a definition", "highlight/blue": ""},
            "units_from": ["highlight/orange"],
        },
    )

    assert answer.status_code == 200
    text = (folder / "project.toml").read_text(encoding="utf-8")
    assert "# Which Zotero item this came from." in text
    assert "# What your marks mean here." in text
    work = config_mod.load(repo).projects["cpp"].sources[0]
    assert dict(work.meanings) == {"highlight/orange": "a definition"}
    assert set(work.units_from) == {"highlight/orange"}


def test_a_reference_is_not_asked_which_marks_make_units(repo: Path) -> None:
    """Saved anyway, it would be an answer nobody gave."""
    a_project(repo)
    (repo / "projects" / "cpp" / "project.toml").write_text(
        'title = "Modern C++"\n\n[[sources]]\nkey = "ref"\n'
        'url = "https://x.test/"\nzotero = ""\n',
        encoding="utf-8",
    )

    answer = client(repo).post(
        "/api/scheme/cpp/ref",
        json={"meanings": {"note/yellow": "a thought"}, "units_from": ["note/yellow"]},
    )

    assert answer.status_code == 200
    assert answer.json()["units_from"] is None
    assert "units_from" not in (
        repo / "projects" / "cpp" / "project.toml"
    ).read_text(encoding="utf-8")
