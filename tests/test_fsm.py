"""The state-machine diagram is hand-authored SVG, so its geometry is checked.

Three times now a hand-placed arrow has run straight through a box, and the
first two checkers missed colliding *labels* because they only looked at
boxes. Nobody reviewing a template diff sees any of that; a test does.

The text metrics are deliberate approximations -- enough to catch a real
collision, loose enough not to fail on a font that renders slightly narrower.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "anki_math_forge" / "app" / "templates"
FSM = TEMPLATES / "_fsm.html"
MINI = TEMPLATES / "_fsm_mini.html"

# class -> (font size, anchor). Mirrors app.css; a label drawn at a size the
# checker does not know about would be measured with the default.
FONTS = {
    "lane": (11.0, "start"),
    "state": (13.0, "middle"),
    "source": (12.0, "start"),
    # The lit door, when the diagram is rendered for a source.
    "source on": (12.0, "start"),
    "lbl": (10.5, "middle"),
    "lbl you": (12.0, "middle"),
    "lbl cycle": (10.5, "middle"),
    "lbl warn": (10.5, "start"),  # .lbl.warn sets text-anchor: start
    "sub": (10.0, "start"),
    "name": (11.0, "start"),
    "count": (17.0, "end"),
    "count small": (13.0, "end"),
    "key you": (11.0, "middle"),
    "step": (9.0, "start"),
    "anki": (11.0, "start"),
    "blocked": (9.5, "start"),
    "state out": (13.0, "middle"),
    "state ok": (13.0, "middle"),
    # `carded` and `draft`: one moment seen from either side of the lane rule.
    "state twin": (13.0, "middle"),
    "lbl twin": (10.5, "start"),
    "step twin": (9.0, "start"),
    "prop": (11.0, "start"),
    # A statement about an object rather than a pass over it.
    "carries": (11.0, "start"),
    "overlay": (11.0, "start"),
    "overlay warn": (11.0, "start"),
}
DEFAULT_FONT = (11.0, "start")
CHAR_W = 0.55  # of the font size; a generous average for proportional text


@pytest.fixture(scope="module", params=[FSM, MINI], ids=["full", "mini"])
def svg(request: pytest.FixtureRequest) -> str:
    """Both diagrams get the same geometry checks.

    The compact one is generated from a template, so its counts are Jinja
    expressions; they are replaced with a plausible width so the text metrics
    mean something.
    """
    text = Path(request.param).read_text(encoding="utf-8")
    return re.sub(r"\{\{[^}]*\}\}", "999", text)


def boxes(svg: str) -> list[tuple[float, float, float, float]]:
    out = []
    for m in re.finditer(
        r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg
    ):
        x, y, w, h = (float(v) for v in m.groups())
        out.append((x, y, x + w, y + h))
    return out


def labels(svg: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Approximate bounding boxes for every <text> that carries a position.

    A `<text>` inside `<g class="state">` is styled by the group, not by
    itself -- CSS says `.fsm .state text`. Missing that made the checker
    measure box labels at the wrong size and anchor, and it reported a
    collision that was not there.
    """
    out = []
    group = ""
    for m in re.finditer(
        r'<g class="([^"]*)"'
        r'|</g>'
        r'|<text(?: class="([^"]*)")? x="([\d.]+)" y="([\d.]+)"[^>]*>(.*?)</text>',
        svg,
        re.S,
    ):
        if m.group(0).startswith("<g"):
            group = m.group(1)
            continue
        if m.group(0) == "</g>":
            group = ""
            continue
        cls = m.group(2) or group
        x, y, body = float(m.group(3)), float(m.group(4)), m.group(5)
        text = re.sub(r"<[^>]+>", "", body)
        text = re.sub(r"&[a-z]+;", "x", text).strip()
        size, anchor = FONTS.get(cls, DEFAULT_FONT)
        width = len(text) * size * CHAR_W
        if anchor == "middle":
            left = x - width / 2
        elif anchor == "end":
            left = x - width
        else:
            left = x
        # y is the baseline; ascenders sit above it
        out.append((text, (left, y - size * 0.8, left + width, y + size * 0.25)))
    return out


def segments(d: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    cur: tuple[float, float] | None = None
    out = []
    for cmd, arg in re.findall(r"([MHVL])([-\d.,\s]*)", d):
        nums = [float(n) for n in re.findall(r"-?[\d.]+", arg)]
        if cmd == "M":
            cur = (nums[0], nums[1])
        elif cmd == "H" and cur:
            for x in nums:
                out.append((cur, (x, cur[1])))
                cur = (x, cur[1])
        elif cmd == "V" and cur:
            for y in nums:
                out.append((cur, (cur[0], y)))
                cur = (cur[0], y)
        elif cmd == "L" and cur:
            for i in range(0, len(nums), 2):
                out.append((cur, (nums[i], nums[i + 1])))
                cur = (nums[i], nums[i + 1])
    return out


def overlap(a: tuple[float, ...], b: tuple[float, ...], pad: float = 0.0) -> bool:
    return (
        a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad
    )


def test_no_two_boxes_overlap(svg: str) -> None:
    found = boxes(svg)
    assert len(found) >= 5, "the diagram lost its boxes"
    clashes = [
        (a, b) for i, a in enumerate(found) for b in found[i + 1 :] if overlap(a, b)
    ]
    assert not clashes, f"overlapping boxes: {clashes}"


def test_no_edge_runs_through_a_box(svg: str) -> None:
    found = boxes(svg)
    bad = []
    for m in re.finditer(r'<path class="edge[^"]*" d="([^"]+)"', svg):
        for p, q in segments(m.group(1)):
            for box in found:
                for step in range(1, 40):
                    x = p[0] + (q[0] - p[0]) * step / 40
                    y = p[1] + (q[1] - p[1]) * step / 40
                    if box[0] + 2 < x < box[2] - 2 and box[1] + 2 < y < box[3] - 2:
                        bad.append((m.group(1), box))
                        break
                else:
                    continue
                break
    assert not bad, f"edges crossing a box: {bad}"


def test_no_label_overlaps_another_label(svg: str) -> None:
    found = labels(svg)
    clashes = [
        (a[0], b[0])
        for i, a in enumerate(found)
        for b in found[i + 1 :]
        if overlap(a[1], b[1], pad=1.0)
    ]
    assert not clashes, f"overlapping labels: {clashes}"


def test_no_label_sits_on_a_box_it_does_not_belong_to(svg: str) -> None:
    """A label may sit inside its own box; it must not stray into another."""
    own = {t for t, _ in labels(svg)}
    boxed = boxes(svg)
    strays = []
    for text, rect in labels(svg):
        inside = [b for b in boxed if overlap(rect, b, pad=2.0)]
        if len(inside) > 1:
            strays.append((text, inside))
    assert not strays, f"labels spanning more than one box: {strays}"
    assert own, "no labels parsed at all -- the regex stopped matching"


def test_no_edge_runs_through_a_label(svg: str) -> None:
    """An arrow drawn across its own caption is the commonest way this gets ugly.

    Four of these existed at once before the check did: the suggestion arrow
    passed through the word `extract`, the bridge clipped the draft-loop
    caption, the self-loop crossed the CARD lane title, and one label was
    centred on top of the very arrow it described.
    """
    bad = []
    for m in re.finditer(r'<path class="(?:edge|gate)[^"]*" d="([^"]+)"', svg):
        for p, q in segments(m.group(1)):
            for text, box in labels(svg):
                for step in range(0, 41):
                    x = p[0] + (q[0] - p[0]) * step / 40
                    y = p[1] + (q[1] - p[1]) * step / 40
                    if box[0] < x < box[2] and box[1] < y < box[3]:
                        bad.append((m.group(1), text))
                        break
                else:
                    continue
                break
    assert not bad, f"edges crossing a label: {sorted(set(bad))}"


def test_the_checker_agrees_with_the_stylesheet() -> None:
    """The metrics above are only meaningful if they match what is rendered.

    `.lbl.warn` already caught this out once: the checker assumed a centred
    label while the stylesheet anchored it at the start, so every warn label
    was measured in the wrong place.
    """
    css = (FSM.parents[1] / "static" / "app.css").read_text(encoding="utf-8")
    for cls, (_, anchor) in FONTS.items():
        rule = None
        for selector in (".fsm ." + cls.replace(" ", "."), ".fsm.mini ." + cls.replace(" ", ".")):
            found = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", css)
            if found and "text-anchor" in found.group(1):
                rule = found
                break
        if rule is None:
            continue
        declared = re.search(r"text-anchor:\s*(\w+)", rule.group(1))
        assert declared and declared.group(1) == anchor, (
            f"{selector} is anchored {declared.group(1) if declared else '?'} "
            f"in app.css but measured as {anchor} here"
        )
