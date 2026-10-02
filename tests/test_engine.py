"""Tests against the real padtools_ts. Skipped when the engine is not installed."""

import os
import re

import pytest
from conftest import BROKEN, GOLDEN, OK, needs_engine, to_spaces

from padkit import engine
from padkit.cli import main
from padkit.spd import parse, to_ast

pytestmark = needs_engine

GOLDEN_OPTS = {  # fixed family so the golden files do not depend on the host fonts
    "font_family": "Noto Sans CJK JP", "font_size": 13,
    "stroke_color": "#142850", "text_color": "#142850",
}


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_oracle_matches_engine_on_valid_input(path):
    src = path.read_text(encoding="utf-8")
    assert engine.compare(to_ast(parse(src)), engine.export_ast(src)) is None


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_padtools_silently_flattens_spaces(path):
    """Documents the upstream behaviour that motivates `lint`.

    If this starts failing, padtools_ts began rejecting space indentation; E001
    stays useful but the wording in the docs should be revisited.
    """
    src = to_spaces(path.read_text(encoding="utf-8"), 4)
    actual = engine.export_ast(src)  # no exception: exit 0
    assert engine.compare(to_ast(parse(src)), actual) is not None


SILENT = ["unknown_command", "hash_second_char", "else_comment", "last_single_char"]


@pytest.mark.parametrize("name", SILENT)
def test_engine_cross_check_catches_known_silent_drops(name):
    """Even without the specific rule, E900 must fire for these inputs."""
    path = next(p for p in BROKEN if p.stem == name)
    src = path.read_text(encoding="utf-8")
    actual = engine.export_ast(src)  # padtools_ts accepts it
    assert engine.compare(to_ast(parse(src)), actual) is not None


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_golden_svg(path):
    svg = engine.render_svg(path.read_text(encoding="utf-8"), GOLDEN_OPTS)
    golden = GOLDEN / f"{path.stem}.svg"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(svg, encoding="utf-8")
    assert golden.exists(), f"missing {golden.name}; run with UPDATE_GOLDEN=1"
    assert svg == golden.read_text(encoding="utf-8")


def _strip_title(svg: str) -> str:
    # padtools_ts embeds the SPD source as <title> only when the input is SPD.
    return re.sub(r"<title>.*?</title>\s*", "", svg, flags=re.S)


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_ast_round_trip(path, tmp_path):
    """Acceptance 5: `padkit ast` fed back with --from-ast gives the same SVG."""
    ast_file, a, b = tmp_path / "x.json", tmp_path / "a.svg", tmp_path / "b.svg"
    style = ["--font-family", "Noto Sans CJK JP"]
    assert main(["ast", str(path), "-o", str(ast_file)]) == 0
    assert main(["svg", str(path), "-o", str(a), *style]) == 0
    assert main(["svg", "--from-ast", str(ast_file), "-o", str(b), *style]) == 0
    assert _strip_title(a.read_text()) == _strip_title(b.read_text())


def test_svg_refuses_broken_input(tmp_path, capsys):
    src = (OK[0]).read_text(encoding="utf-8")
    f = tmp_path / "broken.spd"
    f.write_text(to_spaces(src, 4), encoding="utf-8")
    out = tmp_path / "x.svg"
    assert main(["svg", str(f), "-o", str(out)]) == 1
    assert not out.exists()


def _boxed_widths(svg: str) -> set[str]:
    # stroked rects are the boxes; the page background rect has no stroke
    return set(re.findall(r'<rect x="0" y="0" width="([\d.]+)"[^>]*stroke=', svg))


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_align_depth_gives_one_width_per_column(path):
    src = path.read_text(encoding="utf-8")
    doc = parse(src)
    boxed_depths = {s.depth for s in _iter(doc.roots)
                    if s.kind not in ("comment", "else", "case", "switch", "if")}
    svg = engine.render_svg(src, {**GOLDEN_OPTS, "align_depth": True})
    assert len(_boxed_widths(svg)) <= len(boxed_depths)
    assert len(_boxed_widths(svg)) < len(_boxed_widths(engine.render_svg(src, GOLDEN_OPTS)))


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_golden_svg_align_depth(path):
    svg = engine.render_svg(path.read_text(encoding="utf-8"), {**GOLDEN_OPTS, "align_depth": True})
    golden = GOLDEN / f"{path.stem}.align-depth.svg"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(svg, encoding="utf-8")
    assert golden.exists(), f"missing {golden.name}; run with UPDATE_GOLDEN=1"
    assert svg == golden.read_text(encoding="utf-8")


def _iter(block):
    for s in block:
        yield s
        yield from _iter(s.children)


@pytest.mark.parametrize("align", [False, True], ids=["standard", "align-depth"])
def test_sequence_line_stops_at_the_branch_shape(align):
    """patches/0002: the line along a list must not run past the last element's
    own shape down the subtree hanging below it (here: the else branch)."""
    src = "根\n\t前の処理をする\n\t:if 条件か\n\t\t真の処理をする\n\t:else\n\t\t偽の処理をする\n"
    svg = engine.render_svg(src, {**GOLDEN_OPTS, "align_depth": align})
    (line_end,) = [float(m) for m in re.findall(r'<line x1="0.0" y1="0.0" x2="0.0" y2="([\d.]+)"', svg)]
    top = float(re.search(r'<g transform="translate\(0.0, ([\d.]+)\)">\s*<g transform="translate\([\d.]+, 0.0\)">', svg).group(1))
    poly = re.search(r'<polygon points="([^"]+)"', svg).group(1)
    shape_bottom = max(float(p.split(",")[1]) for p in poly.split())
    assert line_end == pytest.approx(top + shape_bottom)


CONNECT_TO_TERMINAL = {
    "branch": "根\n\t:if 続けられるか\n\t\t処理を続ける\n\t:else\n\t\t:terminal 中断する\n\t後の処理をする\n",
    "box": "根\n\t前の処理をする\n\t\t:terminal 中断する\n\t後の処理をする\n",
    "list": "根\n\t前の処理をする\n\t\t:terminal 開始する\n\t\t中の処理をする\n\t後の処理をする\n",
}


@pytest.mark.parametrize("align", [False, True], ids=["standard", "align-depth"])
@pytest.mark.parametrize("case", CONNECT_TO_TERMINAL, ids=CONNECT_TO_TERMINAL.keys())
def test_connector_reaches_rounded_terminal(case, align):
    """patches/0003: a connector into a terminal ends where the rounded outline
    starts (x + radius), not in the air at the corner of its bounding box."""
    svg = engine.render_svg(CONNECT_TO_TERMINAL[case], {**GOLDEN_OPTS, "align_depth": align})
    # group placing the terminal (directly, or as the first element of a list)
    terminals = re.findall(r'<g transform="translate\(([\d.]+), ([\d.]+)\)">\s*'
                           r'(?:<g transform="translate\(0.0, 0.0\)">\s*)?'
                           r'<rect x="0" y="0" width="[\d.]+" height="[\d.]+" rx="([\d.]+)"', svg)
    (gx, gy, rx), = terminals
    horizontal = {(float(y), float(x2)) for y, x2 in
                  re.findall(r'<line x1="[\d.]+" y1="([\d.]+)" x2="([\d.]+)" y2="\1"', svg)}
    want = float(gx) + float(rx)
    assert any(y == pytest.approx(float(gy)) and x2 == pytest.approx(want) for y, x2 in horizontal), \
        f"no connector ends at ({want}, {gy}); horizontal lines: {sorted(horizontal)}"
