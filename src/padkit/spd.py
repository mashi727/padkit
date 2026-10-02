"""SPD (Simple PAD Description) parser.

This parser is deliberately independent of padtools_ts. It encodes the
structure the *author intended*, so that its AST can be compared against the
one padtools_ts produces: any difference means the renderer would silently
drop or reshape part of the diagram (see ``padkit.engine.compare``).

Standard library only, so the Skill can ship it without dependencies.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

COMMANDS = ("if", "else", "while", "dowhile", "call", "switch", "case", "terminal", "comment")
# Commands whose block must be empty. padtools_ts raises IllegalIndent for these.
CHILDLESS = frozenset({"terminal", "comment", "switch"})

_CONTINUATION = re.compile(r"(?<!\\)@[ \t]*$")
_COMMAND = re.compile(r":(\S*)[ \t]*(.*)", re.S)


@dataclass
class Diagnostic:
    line: int
    col: int
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict:
        d = {
            "line": self.line,
            "col": self.col,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.hint:
            d["hint"] = self.hint
        return d


@dataclass
class Stmt:
    line: int
    depth: int
    kind: str  # "process" or a command name
    text: str  # process content, or the command argument (cleaned)
    raw_text: str  # first physical segment as written, before @ handling
    children: list[Stmt] = field(default_factory=list)


@dataclass
class Document:
    roots: list[Stmt]
    diagnostics: list[Diagnostic]
    indent_unit: int | None  # spaces per level inferred from a broken file

    @property
    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self.diagnostics)


def display_width(s: str) -> int:
    """Cell width as padtools_ts measures it (npm eastasianwidth: F/W/A count 2)."""
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W", "A") else 1 for c in s)


def unescape(s: str) -> str:
    """Apply SPD inline markup: ``@`` is a line break, ``\\@`` a literal at-sign."""
    return re.sub(r"(?<!\\)@", "\n", s).replace("\\@", "@")


def _is_comment_or_blank(line: str) -> bool:
    rest = line.lstrip(" \t")
    return rest == "" or rest.startswith("#")


def infer_indent_unit(lines: list[str]) -> int:
    """Spaces per level in a space-indented file (gcd of all space indents)."""
    unit = 0
    for line in lines:
        if _is_comment_or_blank(line):
            continue
        lead = line[: len(line) - len(line.lstrip(" \t"))]
        if " " in lead:
            unit = math.gcd(unit, len(lead.replace("\t", "")))
    return unit or 4


def _depth_of(lead: str, unit: int) -> int:
    tabs = lead.count("\t")
    spaces = len(lead) - tabs
    return tabs + spaces // unit


def fix_indent(src: str, unit: int | None = None) -> tuple[str, int]:
    """Rewrite space/mixed indentation as tabs. Returns (text, lines changed)."""
    lines = src.splitlines(keepends=True)
    unit = unit or infer_indent_unit([ln.rstrip("\r\n") for ln in lines])
    changed = 0
    out = []
    for ln in lines:
        rest = ln.lstrip(" \t")
        lead = ln[: len(ln) - len(rest)]
        if " " in lead and rest.strip():
            tabs = lead.count("\t")
            spaces = len(lead) - tabs
            ln = "\t" * (tabs + spaces // unit) + rest
            changed += 1
        out.append(ln)
    return "".join(out), changed


def parse(src: str) -> Document:
    lines = src.splitlines()
    diags: list[Diagnostic] = []
    stmts: list[Stmt] = []
    unit: int | None = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        i += 1
        if _is_comment_or_blank(raw):
            continue

        rest = raw.lstrip(" \t")
        lead = raw[: len(raw) - len(rest)]
        if " " in lead:
            if unit is None:
                unit = infer_indent_unit(lines)
            if "\t" in lead:
                diags.append(Diagnostic(
                    lineno, lead.index(" ") + 1, "error", "E002",
                    "indentation mixes tabs and spaces",
                    "SPD indents with tabs only; run `padkit fix-indent`",
                ))
            else:
                diags.append(Diagnostic(
                    lineno, 1, "error", "E001",
                    "indented with spaces; padtools_ts silently flattens this (exit 0)",
                    "SPD indents with tabs only; run `padkit fix-indent`",
                ))
            depth = _depth_of(lead, unit)
        else:
            depth = len(lead)

        # `@` at end of line continues the box on the next line. Full-line
        # comments in between are skipped, matching padtools_ts.
        segments: list[str] = []
        seg: str | None = rest
        while seg is not None and _CONTINUATION.search(seg):
            segments.append(_CONTINUATION.sub("", seg))
            while i < len(lines) and lines[i].lstrip(" \t").startswith("#"):
                i += 1
            if i >= len(lines):
                seg = None
                break
            seg = lines[i].lstrip(" \t")
            i += 1
        if seg is not None:
            segments.append(seg)
        body = "\n".join(segments)

        if body.startswith(":"):
            m = _COMMAND.match(body)
            assert m is not None
            name, arg_raw = m.group(1), m.group(2)
            if name not in COMMANDS:
                guess = _suggest(name)
                diags.append(Diagnostic(
                    lineno, len(lead) + 1, "error", "E103",
                    f"unknown command ':{name}'"
                    + (f" (padtools_ts would read it as ':{guess}' + text)" if guess else ""),
                    f"did you mean ':{guess}'?" if guess else None,
                ))
                stmts.append(Stmt(lineno, depth, "process", unescape(body), rest))
                continue
            arg = unescape(arg_raw).strip()
            stmts.append(Stmt(lineno, depth, name, arg, arg_raw))
            col = len(lead) + 1 + len(name) + 1
            if name == "else":
                if arg.startswith("#"):
                    diags.append(Diagnostic(
                        lineno, col, "error", "E109",
                        "comment on the ':else' line; padtools_ts drops the whole else branch",
                        "move the comment to its own line",
                    ))
                elif arg:
                    diags.append(Diagnostic(lineno, col, "error", "E108", "':else' takes no argument"))
            elif not arg:
                diags.append(Diagnostic(lineno, col, "error", "E107", f"':{name}' requires an argument"))
        else:
            stmts.append(Stmt(lineno, depth, "process", unescape(body), rest))
            if len(rest) > 1 and rest[1] == "#":
                diags.append(_hash_quirk(lineno, len(lead) + 2))

    roots = _build_tree(stmts, diags)
    _check_blocks(roots, diags)
    _check_last_statement(stmts, diags)
    diags.sort(key=lambda d: (d.line, d.col))
    return Document(roots, diags, unit)


def _hash_quirk(line: int, col: int) -> Diagnostic:
    return Diagnostic(
        line, col, "error", "E106",
        "'#' as the 2nd character makes padtools_ts swallow the following line",
        "reword so that '#' is not the second character",
    )


def _check_last_statement(stmts: list[Stmt], diags: list[Diagnostic]) -> None:
    """padtools_ts drops an indented one-character box on the last line.

    Observed at the pinned commit: it does not matter which construct holds the
    box, nor whether the file ends with a newline, CRLF, blanks or comments.
    """
    if not stmts:
        return
    last = stmts[-1]
    if last.kind == "process" and last.depth > 0 and len(last.text.strip()) == 1:
        diags.append(Diagnostic(
            last.line, 1, "error", "E115",
            "a one-character box on the last line is dropped by padtools_ts",
            "write at least two characters, or add a statement after it",
        ))


def _suggest(name: str) -> str | None:
    import difflib

    for cmd in sorted(COMMANDS, key=len, reverse=True):
        if name.startswith(cmd):
            return cmd
    hits = difflib.get_close_matches(name, COMMANDS, n=1, cutoff=0.5)
    return hits[0] if hits else None


def _build_tree(stmts: list[Stmt], diags: list[Diagnostic]) -> list[Stmt]:
    roots: list[Stmt] = []
    path: list[Stmt] = []  # path[d] = most recent statement at depth d
    for s in stmts:
        if s.depth > len(path):
            diags.append(Diagnostic(
                s.line, 1, "error", "E104",
                f"indentation jumps from depth {len(path) - 1} to {s.depth}"
                if path else "first statement is indented",
            ))
            s.depth = len(path)
        del path[s.depth:]
        if s.depth == 0:
            roots.append(s)
        else:
            parent = path[-1]
            if parent.kind in CHILDLESS:
                diags.append(Diagnostic(
                    s.line, 1, "error", "E105",
                    f"':{parent.kind}' (line {parent.line}) cannot have a child block",
                ))
            parent.children.append(s)
        path.append(s)
    return roots


def _check_blocks(block: list[Stmt], diags: list[Diagnostic]) -> None:
    prev: Stmt | None = None  # last statement that is not :else / :case
    has_else = False
    cases: set[str] = set()
    for s in block:
        if s.kind == "else":
            if prev is None or prev.kind != "if" or has_else:
                diags.append(Diagnostic(
                    s.line, 1, "error", "E110",
                    "':else' must directly follow an ':if' at the same depth",
                ))
            has_else = True
        elif s.kind == "case":
            if prev is None or prev.kind != "switch":
                diags.append(Diagnostic(
                    s.line, 1, "error", "E111",
                    "':case' must follow a ':switch' at the same depth",
                ))
            elif s.text in cases:
                diags.append(Diagnostic(s.line, 1, "error", "E112", f"duplicate case '{s.text}'"))
            cases.add(s.text)
        else:
            prev, has_else, cases = s, False, set()
        _check_blocks(s.children, diags)



def iter_stmts(block: list[Stmt]):
    for s in block:
        yield s
        yield from iter_stmts(s.children)


def to_ast(doc: Document) -> dict | None:
    """Build an AST in the same shape as padtools_ts ``--export-ast``."""
    node = _block_ast(doc.roots)
    if node is None:
        return None
    if node["type"] != "nodeList":
        node = {"type": "nodeList", "children": [node]}
    return node


def _block_ast(block: list[Stmt]) -> dict | None:
    nodes: list[dict] = []
    for s in block:
        if s.kind == "else":
            if nodes and nodes[-1]["type"] == "if":
                nodes[-1]["falseNode"] = _block_ast(s.children)
        elif s.kind == "case":
            if nodes and nodes[-1]["type"] == "switch":
                nodes[-1]["cases"]["value"].append([s.text, _block_ast(s.children)])
        else:
            nodes.append(_stmt_ast(s))
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    return {"type": "nodeList", "children": nodes}


def _stmt_ast(s: Stmt) -> dict:
    child = _block_ast(s.children)
    if s.kind == "process":
        return {"type": "process", "text": s.text, "childNode": child}
    if s.kind == "if":
        return {"type": "if", "text": s.text, "trueNode": child, "falseNode": None}
    if s.kind in ("while", "dowhile"):
        return {"type": "loop", "isWhile": s.kind == "while", "text": s.text, "childNode": child}
    if s.kind == "call":
        return {"type": "call", "text": s.text, "childNode": child}
    if s.kind == "switch":
        return {"type": "switch", "text": s.text, "cases": {"__type": "Map", "value": []}}
    return {"type": s.kind, "text": s.text}  # terminal, comment
