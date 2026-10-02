"""SVG -> vector PDF with paper fitting.

cairosvg embeds the glyphs it draws, so the PDF looks the same on machines
without the font. Pages of different sizes/orientations can be bound together.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

PAPERS = {  # portrait (width, height) in pt
    "a4": (595.0, 842.0),
    "a3": (842.0, 1191.0),
}
AUTO_ORDER = ("a4", "a3")
MARGIN = 36.0  # 0.5 inch
MIN_SCALE = 0.7  # below this, auto mode moves up to the next paper size
MAX_SCALE = 1.0  # do not blow small diagrams up: keeps the type size equal across pages


@dataclass
class Placement:
    paper: str
    orientation: str  # portrait | landscape
    page_size: tuple[float, float]
    scale: float
    content_size: tuple[float, float]

    def describe(self) -> str:
        w, h = self.content_size
        return f"{self.paper.upper()} {self.orientation} ({w:.0f}x{h:.0f}pt, scale {self.scale:.3f})"


def _page(paper: str, orientation: str) -> tuple[float, float]:
    w, h = PAPERS[paper]
    return (h, w) if orientation == "landscape" else (w, h)


def _scale(content: tuple[float, float], page: tuple[float, float], margin: float,
           max_scale: float) -> float:
    fit = min((page[0] - 2 * margin) / content[0], (page[1] - 2 * margin) / content[1])
    return min(fit, max_scale)


def choose_placement(content: tuple[float, float], paper: str = "auto",
                     orientation: str = "auto", margin: float = MARGIN,
                     max_scale: float = MAX_SCALE) -> Placement:
    orient = orientation
    if orient == "auto":
        orient = "landscape" if content[0] > content[1] else "portrait"
    papers = AUTO_ORDER if paper == "auto" else (paper,)
    chosen = None
    for p in papers:
        page = _page(p, orient)
        sc = _scale(content, page, margin, max_scale)
        chosen = Placement(p, orient, page, sc, content)
        if sc >= MIN_SCALE:
            break
    assert chosen is not None
    return chosen


def svg_to_pdf_page(svg: str):
    import cairosvg
    from pypdf import PdfReader

    data = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
    return PdfReader(io.BytesIO(data)).pages[0]


def build_pdf(svgs: list[str], paper: str = "auto", orientation: str = "auto",
              margin: float = MARGIN, max_scale: float = MAX_SCALE) -> tuple[bytes, list[Placement]]:
    from pypdf import PageObject, PdfWriter, Transformation

    writer = PdfWriter()
    placements = []
    for svg in svgs:
        src = svg_to_pdf_page(svg)
        content = (float(src.mediabox.width), float(src.mediabox.height))
        pl = choose_placement(content, paper, orientation, margin, max_scale)
        pw, ph = pl.page_size
        tx = (pw - content[0] * pl.scale) / 2
        ty = (ph - content[1] * pl.scale) / 2
        page = PageObject.create_blank_page(width=pw, height=ph)
        page.merge_transformed_page(src, Transformation().scale(pl.scale).translate(tx, ty))
        writer.add_page(page)
        placements.append(pl)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue(), placements
