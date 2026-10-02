"""Lint: syntax errors from the parser plus structural review heuristics.

The warning/info checks encode the review checklist (skill/reference/
review-checklist.md). They flag *design* smells, not syntax: a PAD that is
syntactically fine can still describe a plan with no feedback loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .spd import Diagnostic, Document, Stmt, display_width, iter_stmts, parse

MAX_DEPTH = 5
MAX_WIDTH = 40  # cells; 全角 20 字
MAX_SIBLINGS = 15
LARGE_WITHOUT_CALL = 60


@dataclass
class LintResult:
    path: str
    doc: Document
    diagnostics: list[Diagnostic]
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    def failed(self, strict: bool = False) -> bool:
        return bool(self.errors or (strict and self.warnings))


def lint_text(src: str, path: str = "<stdin>") -> LintResult:
    doc = parse(src)
    diags = list(doc.diagnostics)
    stmts = list(iter_stmts(doc.roots))
    diags += _review(doc.roots, stmts)
    diags.sort(key=lambda d: (d.line, d.col, d.code))
    return LintResult(path, doc, diags, _stats(stmts))


def _review(roots: list[Stmt], stmts: list[Stmt]) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for s in stmts:
        if s.depth == MAX_DEPTH + 1:
            out.append(Diagnostic(
                s.line, 1, "warning", "W201",
                f"nesting deeper than {MAX_DEPTH}; granularity is inconsistent",
                "cut this subtree out into its own diagram and reference it with ':call'",
            ))
        for seg in s.text.split("\n"):
            w = display_width(seg)
            if w > MAX_WIDTH:
                out.append(Diagnostic(
                    s.line, 1, "warning", "W202",
                    f"box text is {w} cells wide (> {MAX_WIDTH}, i.e. 全角 {MAX_WIDTH // 2} 字)",
                    "shorten it or break the line with '@'",
                ))
                break

    for parent, block in [(None, roots)] + [(s, s.children) for s in stmts]:
        n = sum(1 for s in block if s.kind not in ("else", "case"))
        if n > MAX_SIBLINGS:
            line = parent.line if parent else block[0].line
            out.append(Diagnostic(
                line, 1, "warning", "W203",
                f"{n} boxes under one parent (> {MAX_SIBLINGS}); an intermediate grouping is missing",
            ))

    boxes = [s for s in stmts if s.kind not in ("else", "case")]
    if len(boxes) > LARGE_WITHOUT_CALL and not any(s.kind == "call" for s in stmts):
        out.append(Diagnostic(
            1, 1, "warning", "W204",
            f"{len(boxes)} boxes and no ':call'; split the diagram",
        ))

    if boxes and not any(s.kind in ("while", "dowhile") for s in stmts):
        out.append(Diagnostic(
            1, 1, "info", "I301",
            "no ':while' / ':dowhile': the process has no iteration or learning loop",
        ))

    for block in [roots] + [s.children for s in stmts]:
        for idx, s in enumerate(block):
            if s.kind == "if":
                nxt = block[idx + 1] if idx + 1 < len(block) else None
                if nxt is None or nxt.kind != "else":
                    out.append(Diagnostic(
                        s.line, 1, "info", "I302",
                        "':if' without ':else': the failure path is undefined",
                    ))
            elif s.kind == "terminal":
                after = [t for t in block[idx + 1:] if t.kind != "comment"]
                if after:
                    out.append(Diagnostic(
                        s.line, 1, "info", "I303",
                        "':terminal' in the middle of a flow: a point with no way back",
                    ))
    return out


def _stats(stmts: list[Stmt]) -> dict:
    counts: dict[str, int] = {}
    for s in stmts:
        counts[s.kind] = counts.get(s.kind, 0) + 1
    return {
        "statements": len(stmts),
        "max_depth": max((s.depth for s in stmts), default=0),
        "counts": dict(sorted(counts.items())),
    }


REPEAT_LIMIT = 3


def format_text(res: LintResult) -> str:
    """One line per diagnostic; a code repeated many times is cut after a few."""
    lines = []
    seen: dict[str, int] = {}
    for d in res.diagnostics:
        seen[d.code] = seen.get(d.code, 0) + 1
        if seen[d.code] > REPEAT_LIMIT:
            continue
        lines.append(f"{res.path}:{d.line}:{d.col}: {d.severity}[{d.code}] {d.message}")
        if d.hint and seen[d.code] == 1:
            lines.append(f"    hint: {d.hint}")
    for code, n in seen.items():
        if n > REPEAT_LIMIT:
            lines.append(f"{res.path}: ... and {n - REPEAT_LIMIT} more [{code}]")
    return "\n".join(lines)


def format_summary(res: LintResult) -> str:
    c = res.stats["counts"]
    kinds = ", ".join(f"{k}={v}" for k, v in c.items())
    n_err = len(res.errors)
    n_warn = len(res.warnings)
    n_info = len(res.diagnostics) - n_err - n_warn
    return (
        f"{res.path}: {n_err} error(s), {n_warn} warning(s), {n_info} info; "
        f"{res.stats['statements']} statements, max depth {res.stats['max_depth']} [{kinds}]"
    )
