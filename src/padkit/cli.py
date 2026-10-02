"""padkit command line: lint / svg / pdf / ast / fix-indent / setup / info."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, engine
from .lint import LintResult, format_summary, format_text, lint_text
from .presets import PRESETS, render_options
from .spd import Diagnostic, fix_indent, to_ast

EXIT_OK, EXIT_LINT, EXIT_ENV = 0, 1, 2


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _err(msg: str) -> None:
    print(f"padkit: {msg}", file=sys.stderr)


def cross_check(res: LintResult, src: str) -> Diagnostic | None:
    """Compare our AST with padtools_ts's. Returns an E9xx diagnostic on mismatch."""
    try:
        actual = engine.export_ast(src)
    except engine.EngineParseError as e:
        return Diagnostic(e.line or 1, 1, "error", "E901", f"padtools_ts rejected the file: {e}")
    d = engine.compare(to_ast(res.doc), actual)
    if d is None:
        return None
    return Diagnostic(
        1, 1, "error", "E900",
        "padtools_ts would draw a different structure than written " + d.describe(),
        "the renderer silently drops or merges boxes here; restructure this part",
    )


def run_lint(path: str, src: str, use_engine: bool) -> tuple[LintResult, bool]:
    """Lint, then cross-check against the engine if possible. Returns (result, checked)."""
    res = lint_text(src, path)
    if not use_engine or res.errors:
        return res, False
    if not engine.is_installed():
        return res, False
    extra = cross_check(res, src)
    if extra:
        res.diagnostics.insert(0, extra)
    return res, True


def cmd_lint(a: argparse.Namespace) -> int:
    failed = False
    reports = []
    unchecked = False
    for path in a.files:
        res, checked = run_lint(path, _read(path), not a.no_engine)
        unchecked |= not checked and not res.errors and not a.no_engine
        failed |= res.failed(a.strict)
        if a.format == "json":
            reports.append({
                "path": path,
                "ok": not res.failed(a.strict),
                "engine_checked": checked,
                "stats": res.stats,
                "diagnostics": [d.to_dict() for d in res.diagnostics],
            })
        else:
            text = format_text(res)
            if text:
                print(text)
            print(format_summary(res))
    if a.format == "json":
        print(json.dumps(reports if len(reports) > 1 else reports[0], ensure_ascii=False, indent=2))
    if unchecked:
        _err("engine cross-check skipped (run `padkit setup` to enable it)")
    return EXIT_LINT if failed else EXIT_OK


def _gate(path: str, src: str, force: bool) -> bool:
    """Refuse to render a file that would come out silently wrong."""
    if not engine.is_installed():
        raise engine.EngineError("padtools_ts is not installed; run `padkit setup`")
    res, _ = run_lint(path, src, use_engine=True)
    if res.errors:
        print(format_text(LintResult(res.path, res.doc, res.errors, res.stats)), file=sys.stderr)
        if not force:
            _err(f"{path}: {len(res.errors)} error(s); not rendering (use --force to override)")
            return False
    return True


def _style_overrides(a: argparse.Namespace) -> dict:
    keys = ("font_family", "font_size", "stroke_width", "stroke_color", "text_color",
            "background_color", "base_background_color", "line_height", "list_render_type",
            "align_depth")
    return {k: getattr(a, k) for k in keys}


def _render(path: str, a: argparse.Namespace) -> str | None:
    src = _read(path)
    opts, notes = render_options(a.style, _style_overrides(a))
    for n in notes:
        _err(n)
    if getattr(a, "from_ast", False):
        return engine.render_svg(src, opts, import_ast=True)
    if not _gate(path, src, a.force):
        return None
    return engine.render_svg(src, opts)


def cmd_svg(a: argparse.Namespace) -> int:
    svg = _render(a.file, a)
    if svg is None:
        return EXIT_LINT
    if a.output and a.output != "-":
        Path(a.output).write_text(svg, encoding="utf-8")
    else:
        sys.stdout.write(svg)
    return EXIT_OK


def cmd_pdf(a: argparse.Namespace) -> int:
    from .pdf import build_pdf

    svgs = []
    for path in a.files:
        svg = _render(path, a)
        if svg is None:
            return EXIT_LINT
        svgs.append(svg)
    data, placements = build_pdf(svgs, a.paper, a.orientation, a.margin, a.max_scale)
    out = a.output or str(Path(a.files[0]).with_suffix(".pdf"))
    Path(out).write_bytes(data)
    for path, pl in zip(a.files, placements):
        print(f"{path}: {pl.describe()}")
    print(f"wrote {out}")
    return EXIT_OK


def cmd_ast(a: argparse.Namespace) -> int:
    src = _read(a.file)
    if a.oracle:
        res = lint_text(src, a.file)
        ast = to_ast(res.doc)
    else:
        if not _gate(a.file, src, a.force):
            return EXIT_LINT
        ast = engine.export_ast(src)
    text = json.dumps(ast, ensure_ascii=False, indent=2) + "\n"
    if a.output and a.output != "-":
        Path(a.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_fix_indent(a: argparse.Namespace) -> int:
    src = _read(a.file)
    fixed, n = fix_indent(src, a.unit)
    if a.write and a.file != "-":
        if n:
            Path(a.file).write_text(fixed, encoding="utf-8")
        _err(f"{a.file}: {n} line(s) re-indented")
    else:
        sys.stdout.write(fixed)
    return EXIT_OK


def cmd_setup(a: argparse.Namespace) -> int:
    engine.setup(force=a.force)
    print(f"ready: {engine.cli_js()}")
    return EXIT_OK


def cmd_info(a: argparse.Namespace) -> int:
    p = engine.pin()
    print(f"padkit {__version__}")
    print(f"padtools_ts {p['repo']}@{p['commit']} (vendored {p['vendored_at']})")
    print(f"engine dir  {engine.engine_dir()} ({'installed' if engine.is_installed() else 'not installed'})")
    try:
        print(f"node        {engine.node_bin()}")
    except engine.EngineError as e:
        print(f"node        {e}")
    for name in PRESETS:
        opts, notes = render_options(name)
        print(f"style {name:6} font={opts['font_family']!r}" + (f"  ! {notes[0]}" if notes else ""))
    return EXIT_OK


def _add_style(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("style")
    g.add_argument("--style", default="house", choices=sorted(PRESETS))
    g.add_argument("--font-family")
    g.add_argument("--font-size", type=float)
    g.add_argument("--stroke-width", type=float)
    g.add_argument("--stroke-color")
    g.add_argument("--text-color")
    g.add_argument("--background-color")
    g.add_argument("--base-background-color")
    g.add_argument("--line-height", type=float)
    g.add_argument("--list-render-type", choices=["Original", "TerminalOffset"])
    g.add_argument("--align-depth", action="store_true", default=None,
                   help="align boxes of the same depth into equal-width columns (not standard PAD)")
    p.add_argument("--force", action="store_true", help="render even if lint finds errors")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="padkit", description="SPD (Simple PAD Description) toolchain")
    ap.add_argument("-V", "--version", action="version", version=f"padkit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lint", help="check SPD files; exit 1 on errors")
    p.add_argument("files", nargs="+", metavar="FILE")
    p.add_argument("--strict", action="store_true", help="warnings also fail")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--no-engine", action="store_true", help="skip the padtools_ts AST cross-check")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("svg", help="render SPD to SVG")
    p.add_argument("file", metavar="FILE")
    p.add_argument("-o", "--output")
    p.add_argument("--from-ast", action="store_true", help="input is AST JSON from `padkit ast`")
    _add_style(p)
    p.set_defaults(func=cmd_svg)

    p = sub.add_parser("pdf", help="render one or more SPD files to a vector PDF")
    p.add_argument("files", nargs="+", metavar="FILE")
    p.add_argument("-o", "--output")
    p.add_argument("--paper", choices=["auto", "a4", "a3"], default="auto")
    p.add_argument("--orientation", choices=["auto", "portrait", "landscape"], default="auto")
    p.add_argument("--margin", type=float, default=36.0, help="pt (default 36 = 0.5in)")
    p.add_argument("--max-scale", type=float, default=1.0,
                   help="upper bound on enlargement (default 1.0; raise it to fill the page)")
    _add_style(p)
    p.set_defaults(func=cmd_pdf)

    p = sub.add_parser("ast", help="dump the parsed AST as JSON")
    p.add_argument("file", metavar="FILE")
    p.add_argument("-o", "--output")
    p.add_argument("--oracle", action="store_true", help="padkit's own parse instead of padtools_ts")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_ast)

    p = sub.add_parser("fix-indent", help="convert space indentation to tabs")
    p.add_argument("file", metavar="FILE")
    p.add_argument("-w", "--write", action="store_true", help="rewrite the file in place")
    p.add_argument("--unit", type=int, help="spaces per level (default: inferred)")
    p.set_defaults(func=cmd_fix_indent)

    p = sub.add_parser("setup", help="install the pinned padtools_ts runtime (needs node>=22, npm)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("info", help="show engine, pin and font resolution")
    p.set_defaults(func=cmd_info)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except engine.EngineError as e:
        _err(str(e))
        return EXIT_ENV
    except (FileNotFoundError, KeyError) as e:
        _err(str(e))
        return EXIT_ENV
