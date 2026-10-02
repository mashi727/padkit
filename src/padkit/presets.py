"""Style presets mapped onto padtools_ts CLI options.

Layout values (margin, box padding) are not exposed by the padtools_ts CLI;
only typography and colours can be set here.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
from functools import lru_cache

NAVY = "#142850"  # RGB(20,40,80), shared with the LuaLaTeX house style

# First installed family wins. Noto is the house face; the rest are fallbacks
# so that a machine without Noto (e.g. stock macOS) still gets a CJK sans.
SANS_CJK = (
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Yu Gothic",
    "IPAexGothic",
)

PRESETS: dict[str, dict] = {
    "house": {
        "font_family": SANS_CJK,
        "font_size": 13,
        "stroke_color": NAVY,
        "text_color": NAVY,
        "stroke_width": 1,
        "background_color": "#ffffff",
        "base_background_color": "#ffffff",
    },
    "mono": {
        # padtools_ts defaults
        "font_family": ("monospace",),
        "font_size": 14,
        "stroke_color": "#000000",
        "text_color": "#000000",
        "stroke_width": 1,
        "background_color": "#ffffff",
    },
    "print": {
        "font_family": SANS_CJK,
        "font_size": 13,
        "stroke_color": "#000000",
        "text_color": "#000000",
        "stroke_width": 1.6,
        "background_color": "#ffffff",
        "base_background_color": "#ffffff",
    },
}


GENERIC = ("monospace", "sans-serif", "serif")


def has_fvar(path: str) -> bool:
    """True if the (first face of the) font file is a variable font.

    cairo draws variable fonts at their default instance, which for Noto Sans
    JP is Thin, so such files must not be selected.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            offset = 0
            if head[:4] == b"ttcf":
                f.seek(12)
                offset = struct.unpack(">I", f.read(4))[0]
                f.seek(offset)
                head = f.read(12)
            num_tables = struct.unpack(">H", head[4:6])[0]
            f.seek(offset + 12)
            for _ in range(num_tables):
                if f.read(16)[:4] == b"fvar":
                    return True
    except (OSError, struct.error):
        return False
    return False


@lru_cache(maxsize=None)
def _match(family: str) -> tuple[list[str], str] | None:
    if not shutil.which("fc-match"):
        return None
    out = subprocess.run(["fc-match", "-f", "%{family}\t%{file}", f"{family}:weight=regular"],
                         capture_output=True, text=True).stdout
    if "\t" not in out:
        return None
    fams, path = out.split("\t", 1)
    return [n.strip().lower() for n in fams.split(",")], path


def resolve_family(candidates: tuple[str, ...]) -> tuple[str, bool]:
    """Pick the first installed, non-variable family. Returns (family, verified)."""
    if not shutil.which("fc-match"):
        return candidates[0], False
    for name in candidates:
        if name in GENERIC:
            return name, True
        m = _match(name)
        if m and name.lower() in m[0] and not has_fvar(m[1]):
            return name, True
    return candidates[0], False


def render_options(preset: str, overrides: dict | None = None) -> tuple[dict, list[str]]:
    """padtools_ts options for a preset, plus warnings for the user."""
    if preset not in PRESETS:
        raise KeyError(f"unknown style '{preset}' (choose from {', '.join(PRESETS)})")
    opts = dict(PRESETS[preset])
    notes: list[str] = []
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    if "font_family" in overrides:
        opts["font_family"] = (overrides.pop("font_family"),)
    family, ok = resolve_family(opts["font_family"])
    if not ok:
        notes.append(f"font '{family}' not found by fontconfig; PDF glyphs may fall back")
    opts["font_family"] = family
    opts.update(overrides)
    return opts, notes
