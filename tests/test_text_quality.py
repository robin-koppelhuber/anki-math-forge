"""Is the cached text layer worth reading?

A PDF's text layer is the *prose* a card writer is handed: the paragraph that
states the conditions, the notation section, the sentence before the equation.
Mangled mathematics in it is expected and harmless -- the crop is authoritative
(invariant 4), and every cached file says so in its own header.

A layer that is **missing or garbled** is a different thing, and nothing said
so. A scan has none at all; a broken font encoding gives pages of replacement
characters. Either way `forge context` handed over noise, and to whoever was
writing the card that reads as "this source does not say much", which is the
wrong conclusion to draw in silence.
"""

from __future__ import annotations

from pathlib import Path

from anki_math_forge import context as context_mod
from anki_math_forge.config import Config
from anki_math_forge.extract import source_text_quality, text_quality

HEADER = "<!-- demo: text layer, cached by `forge extract`.\n     Generated. -->\n\n"
GOOD = HEADER + "\n\n".join(
    f"## page {n}\n\nThe determinant of a product is the product of the "
    f"determinants, provided both are square."
    for n in range(1, 6)
)


def test_an_ordinary_text_layer_is_fine() -> None:
    """Measured across the four in this repo, all healthy: letters are 57 to
    75 per cent of the characters. The Matrix Cookbook is the low end, because
    it is dense mathematics and half its tokens are single symbols -- which is
    why the threshold sits well under it."""
    quality = text_quality(GOOD)
    assert quality.verdict == "ok"
    assert quality.usable
    assert quality.pages == 5


def test_a_scan_has_no_text_layer() -> None:
    assert text_quality("").verdict == "missing"
    assert "scan" in text_quality("").describe()


def test_a_layer_of_empty_pages_is_poor() -> None:
    """A PDF whose pages carry an image and nothing else. It is not missing --
    there is a file, and it has page markers -- which is exactly why it needs
    catching separately."""
    quality = text_quality(HEADER + "".join(f"## page {n}\n\n\n" for n in range(1, 9)))
    assert quality.verdict == "poor"
    assert "no text on them" in quality.describe()


def test_a_broken_font_encoding_is_poor() -> None:
    quality = text_quality(HEADER + "## page 1\n" + "�" * 500)
    assert quality.verdict == "poor"
    assert "replacement characters" in quality.describe()


def test_the_header_is_not_measured(config: Config) -> None:
    """It is prose the tool wrote, and counting it would make a short document
    look better than it is."""
    assert text_quality(HEADER).verdict == "missing"


def test_a_source_with_no_cached_text_says_so(config: Config) -> None:
    assert source_text_quality(config, "demo").verdict == "missing"


def test_it_is_resolved_per_document(config: Config) -> None:
    """An item routinely carries a paper and its preprint, and the layers are
    cached per attachment. Asking about the source without naming one looks for
    `text.md`, which a multi-document source does not have."""
    folder = config.projects_dir / "demo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "text-ABCD1234.md").write_text(GOOD, encoding="utf-8")
    assert source_text_quality(config, "demo", "ABCD1234").verdict == "ok"
    assert source_text_quality(config, "demo").verdict == "missing"


def test_the_card_writer_is_told_before_it_reads_the_noise(config: Config) -> None:
    """Before the text, not after it: by the time you have read a page of
    garbage you have already formed an impression of what the source says."""
    from anki_math_forge import extract

    extract.run(config, "demo")
    unit = next(iter(__import__("anki_math_forge.ledger", fromlist=["Ledger"]).Ledger.load(
        config.units_path("demo")
    )))
    folder = config.projects_dir / "demo"
    (folder / "text.md").write_text(
        HEADER + "".join(f"## page {n}\n\n\n" for n in range(1, 9)), encoding="utf-8"
    )
    rendered = context_mod.assemble(config, unit.id).format()
    assert "text layer here is unusable" in rendered
    assert rendered.index("unusable") < len(rendered)
    assert "Read the crop and write the card from that" in rendered


def test_a_good_layer_says_nothing(config: Config) -> None:
    """The warning is worth having because it is rare. One on every card is a
    line nobody reads."""
    from anki_math_forge import extract

    extract.run(config, "demo")
    unit = next(iter(__import__("anki_math_forge.ledger", fromlist=["Ledger"]).Ledger.load(
        config.units_path("demo")
    )))
    (config.projects_dir / "demo" / "text.md").write_text(GOOD, encoding="utf-8")
    assert "unusable" not in context_mod.assemble(config, unit.id).format()


def test_the_payload_carries_it(config: Config) -> None:
    """`forge context --json` is what a pass actually reads."""
    from anki_math_forge import extract

    extract.run(config, "demo")
    unit = next(iter(__import__("anki_math_forge.ledger", fromlist=["Ledger"]).Ledger.load(
        config.units_path("demo")
    )))
    payload = context_mod.assemble(config, unit.id).as_dict()
    assert "text_quality" in payload and "text_trouble" in payload


def test_the_real_repo_is_healthy() -> None:
    """Not a property of the tool, but the thing the thresholds were calibrated
    against: if a real layer here ever reads as poor, the thresholds are wrong
    rather than the book."""
    root = Path(__file__).resolve().parents[1]
    layers = sorted((root / "projects").glob("*/text*.md"))
    for path in layers:
        quality = text_quality(path.read_text(encoding="utf-8", errors="replace"))
        assert quality.verdict == "ok", f"{path.name}: {quality.describe()}"
