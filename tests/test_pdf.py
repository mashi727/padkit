import io

import pytest
from conftest import OK, needs_engine

from padkit import engine
from padkit.cli import main
from padkit.pdf import MARGIN, PAPERS, build_pdf, choose_placement

SIZES = {  # padtools_ts SVG px -> cairosvg pt (x0.75); from the handoff measurements
    "tall": (813.0, 1470.0),
    "wide": (821.0, 457.0),
    "small": (286.0, 358.0),
}


def test_auto_placement_matches_the_handoff_measurements():
    tall = choose_placement(SIZES["tall"])
    assert (tall.paper, tall.orientation) == ("a3", "portrait")
    assert tall.scale == pytest.approx(0.761, abs=1e-3)

    wide = choose_placement(SIZES["wide"])
    assert (wide.paper, wide.orientation) == ("a4", "landscape")

    small = choose_placement(SIZES["small"])
    assert (small.paper, small.scale) == ("a4", 1.0)  # not blown up


@pytest.mark.parametrize("paper", ["a4", "a3"])
@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
@pytest.mark.parametrize("size", SIZES.values(), ids=SIZES.keys())
def test_content_stays_inside_the_margins(paper, orientation, size):
    """Acceptance 3: A3/A4 x portrait/landscape all fit with margins."""
    pl = choose_placement(size, paper, orientation, max_scale=10)
    pw, ph = pl.page_size
    assert sorted((pw, ph)) == sorted(PAPERS[paper])
    assert (pw > ph) == (orientation == "landscape")
    w, h = size[0] * pl.scale, size[1] * pl.scale
    assert w <= pw - 2 * MARGIN + 1e-6 and h <= ph - 2 * MARGIN + 1e-6
    # fitted on at least one axis
    assert max(w / (pw - 2 * MARGIN), h / (ph - 2 * MARGIN)) == pytest.approx(1.0)


def _fonts(obj, seen=None):
    """Yield every font dictionary reachable from a page."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    seen = seen if seen is not None else set()
    if isinstance(obj, IndirectObject):
        if obj.idnum in seen:
            return
        seen.add(obj.idnum)
        obj = obj.get_object()
    if isinstance(obj, DictionaryObject):
        if obj.get("/Type") == "/Font":
            yield obj
        for v in obj.values():
            yield from _fonts(v, seen)
    elif isinstance(obj, ArrayObject):
        for v in obj:
            yield from _fonts(v, seen)


def _is_embedded(font) -> bool:
    if font.get("/Subtype") == "/Type3":
        return True  # glyphs are drawn by procedures in the file
    if font.get("/Subtype") == "/Type0":
        return all(_is_embedded(d.get_object()) for d in font["/DescendantFonts"])
    desc = font.get("/FontDescriptor")
    if desc is None:
        return False
    desc = desc.get_object()
    return any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))


@needs_engine
@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_pipeline_lint_svg_pdf_and_fonts_embedded(path, tmp_path):
    """Acceptance 1 and 4: the pipeline runs, and every glyph source is embedded,

    so a machine without the font renders the PDF identically.
    """
    from pypdf import PdfReader

    out = tmp_path / "x.pdf"
    assert main(["lint", str(path)]) == 0
    assert main(["pdf", str(path), "-o", str(out)]) == 0
    page = PdfReader(out).pages[0]
    fonts = list(_fonts(page["/Resources"]))
    assert fonts, "expected text to be set in a font"
    assert all(_is_embedded(f) for f in fonts)


@needs_engine
def test_pdf_binds_multiple_diagrams_with_mixed_orientation():
    from pypdf import PdfReader

    from padkit.presets import render_options

    opts, _ = render_options("house")
    tall = "根\n" + "".join(f"\t処理{i}\n" for i in range(12))
    wide = "根\n\t" + "とても長い処理の名前をここに書く" + "\n\t\t子\n\t\t\t孫\n\t\t\t\t曾孫\n"
    data, placements = build_pdf([engine.render_svg(s, opts) for s in (tall, wide)])
    pages = PdfReader(io.BytesIO(data)).pages
    assert len(pages) == 2
    assert [p.orientation for p in placements] == ["portrait", "landscape"]


EMPTY_FONTCONFIG = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><cachedir>/nonexistent</cachedir></fontconfig>
"""

UNEMBEDDED_PDF = (  # negative control: Helvetica referenced by name only
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj "
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 50]"
    b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj "
    b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj "
    b"5 0 obj<</Length 44>>stream\nBT /F1 24 Tf 10 15 Td (Hello PAD) Tj ET\nendstream endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _raster(pdf, tmp_path, name, fontless):
    import os
    import subprocess

    env = dict(os.environ)
    if fontless:
        conf = tmp_path / "empty-fonts.conf"
        conf.write_text(EMPTY_FONTCONFIG)
        env["FONTCONFIG_FILE"] = str(conf)
    out = tmp_path / name
    subprocess.run(["pdftoppm", "-r", "100", "-png", "-singlefile", str(pdf), str(out)],
                   env=env, check=True, capture_output=True)
    return (tmp_path / f"{name}.png").read_bytes()


@pytest.mark.skipif(__import__("shutil").which("pdftoppm") is None, reason="needs poppler")
@needs_engine
def test_pdf_renders_identically_without_system_fonts(tmp_path):
    """Acceptance 4, locally: hide every system font from poppler and compare pixels."""
    ctrl = tmp_path / "ctrl.pdf"
    ctrl.write_bytes(UNEMBEDDED_PDF)
    assert _raster(ctrl, tmp_path, "c1", False) != _raster(ctrl, tmp_path, "c2", True), \
        "control did not change: the fontless setup is not hiding fonts"

    pdf = tmp_path / "x.pdf"
    assert main(["pdf", str(OK[0]), "-o", str(pdf)]) == 0
    assert _raster(pdf, tmp_path, "a", False) == _raster(pdf, tmp_path, "b", True)
