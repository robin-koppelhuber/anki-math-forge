"""One object per command, keyed on ambient state and nothing else.

`test_commands.py` asks what the deck rail offers. This asks the question
behind it: whether a command can still say two different things on two
screens. It used to, and the drift was not theoretical: `/transcribe` was
offered against a Zotero item on the setup stage and refused on the triage
rail, and the screen that offered it was wrong.
"""

from __future__ import annotations

from anki_math_forge.app import runs
from anki_math_forge.app.runs import Ambient, Offer


def labels(where: str, at: Ambient) -> list[str]:
    return [row["label"] for row in runs.propose(where, at)]


def commands(where: str, at: Ambient) -> list[str]:
    return [row["run"] for row in runs.propose(where, at) if row["run"]]


def test_every_offer_is_shown_somewhere_real() -> None:
    """A typo in a `where` is a command that renders nowhere and is noticed
    months later, because the panel it belongs on still has other rows in
    it."""
    for offer in runs.OFFERS:
        assert offer.where, offer.label
        assert set(offer.where) <= set(runs.WHERE + runs.PANES), offer.where
        assert offer.scope in runs.SCOPES, offer.scope
        assert offer.kind in {"shell", "claude", "note"}, offer.kind


def test_a_note_is_not_copyable_and_a_command_is() -> None:
    """A note says why a pass is absent. A button that copies an empty
    string is a button that looks broken."""
    for offer in runs.OFFERS:
        if offer.kind == "note":
            assert not offer.run, offer.label
            assert offer.scope == "note", "it frames the list, it is not in it"
        else:
            assert offer.run, offer.label
            assert offer.why, offer.label


def test_a_command_on_two_screens_is_one_object() -> None:
    """The point of the registry. `sync --dry-run` is proposed from the
    shelf, from the review rail and from the setup stage, and the three used
    to be three dict literals free to describe it differently."""
    shared = [o for o in runs.OFFERS if len(o.where) > 1]

    assert len(shared) >= 6, "most of these belong in more than one place"
    everywhere = next(o for o in runs.OFFERS if o.run == "uv run forge anki")
    assert set(everywhere.where) == {"shelf", "review", "project"}


def test_no_screen_offers_the_same_command_twice() -> None:
    """Two offers that render the same string are two objects describing one
    command, which is the thing this module exists to stop."""
    rich = Ambient(
        project="book",
        counts={"new": 4, "queued": 2, "ungisted": 2, "unaugmented": 1,
                "approved": 3, "annotated_claude_card": 1},
        origin="mixed",
        subject="an ask",
        zotero_key="ABCD",
    )
    for where in runs.WHERE:
        out = commands(where, rich)
        assert len(out) == len(set(out)), where


def test_a_reference_gets_one_note_and_no_passes() -> None:
    """Nothing is extracted from it, so every pass here would have nothing
    to read. A panel of commands that all do nothing is worse than a
    sentence saying why there are none."""
    out = runs.propose(
        "work", Ambient(project="book", authoritative=False, origin="zotero")
    )

    assert len(out) == 1
    assert out[0]["kind"] == "note"
    assert "a reference is read by whoever writes a card" in out[0]["label"]


def test_a_zotero_work_is_never_offered_a_crop_pass() -> None:
    """The bug the registry is for. An imported item is re-read with
    `zotero`, not segmented with `extract`, and a mark you highlighted needs
    no transcription to triage."""
    marked = Ambient(
        project="krause", origin="zotero", zotero_key="T7Q",
        from_marks=True, counts={"new": 56},
    )
    out = commands("work", marked)

    assert not any("/transcribe" in run for run in out)
    assert not any("/classify" in run for run in out)
    assert not any("forge units extract" in run for run in out)
    assert any("forge zotero" in run for run in out)


def test_a_work_with_nothing_segmented_out_of_it_yet_is_offered_the_segmenter() -> None:
    """And not the passes that read a crop: there are no crops until it has
    run. The order is the order you do them in."""
    fresh = Ambient(project="book", origin="pdf", counts={})
    out = commands("work", fresh)

    assert any("forge units extract" in run for run in out)
    assert not any("/transcribe" in run for run in out), "nothing to read yet"

    segmented = commands(
        "work", Ambient(project="book", origin="pdf", counts={"new": 9, "untranscribed": 9})
    )
    assert any("/transcribe" in run for run in segmented)


def test_the_repo_wide_form_comes_last() -> None:
    """Most specific to more general. You are looking at one project, so the
    command about that project is the one you want and the repo-wide form is
    the one you reach for afterwards."""
    out = commands("review", Ambient(project="book", counts={"approved": 2}))
    mine = out.index('uv run forge anki --project "book"')

    assert mine < out.index("uv run forge anki")
    assert out.index("uv run forge anki pull") > mine


def test_a_subject_project_is_proposed_into_rather_than_segmented() -> None:
    """There is no document, so the crop passes have nothing to read and the
    pass that writes units has to be offered somewhere."""
    out = commands("project", Ambient(project="cpp", has_document=False))

    assert any("/propose" in run for run in out)
    assert not any("forge units extract" in run for run in out)
    assert not any("forge audit" in run for run in out), "nothing to index"


def test_a_project_of_both_kinds_gets_both_doors() -> None:
    """Several works in one project can arrive by different doors: one
    marked up in Zotero, one segmented here. Offering only the door the
    first work came through leaves the other one with no way to re-read it."""
    out = commands("project", Ambient(project="mix", origin="mixed"))

    assert any(run.startswith("uv run forge zotero import --project") for run in out)
    assert any("forge units extract" in run for run in out)


def test_an_offer_reads_ambient_state_and_not_the_screen() -> None:
    """The contract. Two screens handed the same facts propose the same
    thing about them, so a command cannot mean one thing on the setup stage
    and another on the rail."""
    at = Ambient(
        project="book", origin="pdf", counts={"new": 5, "untranscribed": 5}
    )
    both = {o.run for o in runs.OFFERS if {"units", "work"} <= set(o.where)}
    rail = set(commands("units", at))
    pane = set(commands("work", at))

    assert both, "some commands belong on both"
    for offer in (o for o in runs.OFFERS if {"units", "work"} <= set(o.where)):
        rendered = offer.render(at)["run"]
        assert (rendered in rail) == (rendered in pane), rendered

    marked = Ambient(project="book", origin="pdf", from_marks=True, counts={"new": 5})
    assert not any("/transcribe" in run for run in commands("units", marked))
    assert not any("/transcribe" in run for run in commands("work", marked))


def test_an_offer_declares_its_own_condition() -> None:
    """`when` is the whole of it. A command whose availability depended on
    something the caller did before calling is a command that appears on one
    screen and not on another for no reason anybody can read."""
    quiet = Ambient(project="book")
    for offer in runs.OFFERS:
        assert isinstance(offer, Offer)
        # Callable, total, and cheap: it runs once per offer per render.
        assert isinstance(offer.when(quiet), bool)


def test_every_pane_list_comes_from_here() -> None:
    """The setup stage built four command lines by hand, in a template,
    while this module's docstring said every list came from here."""
    from pathlib import Path

    setup = (
        Path(runs.__file__).parent / "templates" / "setup.html"
    ).read_text(encoding="utf-8")

    assert "runs([" not in setup, "a list written in the template"
    for pane in runs.PANES:
        assert runs.propose(pane, runs.Ambient(project="p")), f"{pane} offers nothing"


def test_the_audit_is_offered_where_it_has_something_to_audit() -> None:
    """On the project it audits, once it holds a unit. Not on a source's
    panel, since it takes the whole project, and not before extraction."""
    from anki_math_forge.app import runs as runs_mod

    def offered(where: str, **ambient: object) -> bool:
        rows = runs_mod.propose(where, runs_mod.Ambient(project="demo", **ambient))  # type: ignore[arg-type]
        return any(row["label"] == "audit" for row in rows)

    assert offered("project", counts={"units": 3})
    assert not offered("project", counts={"units": 0}), "nothing extracted yet"
    assert not offered("project", counts={"units": 3}, has_document=False)
    assert not offered("work", counts={"units": 3})


def test_a_headline_is_the_command_in_a_word_or_two() -> None:
    """The sentence is the `why` below it; the headline is what you would
    say. A note is the exception: it is not a command."""
    from anki_math_forge.app import runs as runs_mod

    for offer in runs_mod.OFFERS:
        if offer.kind == "note":
            continue
        at = runs_mod.Ambient(project="demo", counts={"units": 1, "new": 1}, inbox=1)
        label = offer.render(at)["label"]
        assert len(label.split()) <= 3, label


def test_a_run_names_the_action_it_is() -> None:
    """So the window opened on it starts the builder on the same command."""
    from anki_math_forge.app.jobs import Run

    argv = ["zotero", "import", "--project", "krause", "--json"]
    run = Run(id="r1", argv=argv, started=0.0, effect="repo")
    row = run.row()

    assert row["action"] == "zotero-project"
    assert row["values"] == {"project": "krause"}


def test_stubs_and_augmenting_in_one_run_is_offered_beside_stubs_alone() -> None:
    from anki_math_forge.app import runs as runs_mod

    rows = runs_mod.propose("units", runs_mod.Ambient(project="demo", counts={"queued": 3}))
    lines = [row["run"] for row in rows if row["label"] == "/extract-cards"]

    assert lines == ['/extract-cards --project "demo"', '/extract-cards --project "demo" --augment']
