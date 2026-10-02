"""padtools_ts: installation, invocation, and AST cross-check.

The vendored copy under ``_vendor/padtools_ts`` holds only ``dist`` and the
lockfile. ``setup()`` copies it to a writable engine directory and runs
``npm ci`` there, so the dependency set is exactly the pinned one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

MIN_NODE_MAJOR = 22


class EngineError(RuntimeError):
    pass


class EngineParseError(EngineError):
    def __init__(self, line: int | None, message: str):
        super().__init__(message)
        self.line = line


def vendor_dir() -> Path:
    return Path(str(resources.files("padkit") / "_vendor" / "padtools_ts"))


def pin() -> dict:
    return json.loads((vendor_dir() / "PIN.json").read_text())


def engine_dir() -> Path:
    env = os.environ.get("PADKIT_ENGINE_DIR")
    if env:
        return Path(env).expanduser()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "padkit" / f"padtools_ts-{pin()['commit'][:12]}"


def cli_js() -> Path:
    return engine_dir() / "dist" / "cli" / "cli.js"


def node_bin() -> str:
    node = shutil.which("node")
    if not node:
        raise EngineError(f"node not found; Node.js >= {MIN_NODE_MAJOR} is required")
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    m = re.match(r"v(\d+)", out)
    if not m or int(m.group(1)) < MIN_NODE_MAJOR:
        raise EngineError(f"node {out} is too old; padtools_ts needs >= {MIN_NODE_MAJOR}")
    return node


STAMP = ".padkit-dist-sha256"


def _dist_digest(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted((root / "dist").rglob("*")):
        if f.is_file() and ".claude" not in f.parts:
            h.update(str(f.relative_to(root)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _sync_dist() -> None:
    """Keep the engine's dist identical to the vendored (patched) one.

    node_modules depends only on package-lock.json, so a changed patch needs a
    file copy, not a reinstall.
    """
    d, src = engine_dir(), vendor_dir()
    want = _dist_digest(src)
    stamp = d / STAMP
    if stamp.exists() and stamp.read_text() == want:
        return
    shutil.rmtree(d / "dist", ignore_errors=True)
    shutil.copytree(src / "dist", d / "dist", ignore=shutil.ignore_patterns(".claude"))
    shutil.copy2(src / "PIN.json", d / "PIN.json")
    stamp.write_text(want)


def _lock_matches() -> bool:
    lock = engine_dir() / "package-lock.json"
    return lock.exists() and lock.read_bytes() == (vendor_dir() / "package-lock.json").read_bytes()


def is_installed() -> bool:
    d = engine_dir()
    return (d / "node_modules" / "commander").exists() and _lock_matches()


def setup(force: bool = False, log=print) -> Path:
    d = engine_dir()
    if is_installed() and not force:
        log(f"engine already installed: {d}")
        return d
    npm = shutil.which("npm")
    if not npm:
        raise EngineError("npm not found")
    node_bin()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    src = vendor_dir()
    for name in ("package.json", "package-lock.json", "LICENSE"):
        shutil.copy2(src / name, d / name)
    _sync_dist()
    log(f"installing padtools_ts@{pin()['commit'][:12]} into {d}")
    cmd = [npm, "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund",
           "--cache", str(d.parent / "npm-cache")]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        raise EngineError(f"npm ci failed:\n{r.stdout}\n{r.stderr}")
    return d


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    if not is_installed():
        raise EngineError("padtools_ts is not installed or out of date; run `padkit setup --force`")
    _sync_dist()
    r = subprocess.run([node_bin(), str(cli_js()), *args], input=stdin,
                       capture_output=True, text=True)
    if r.returncode != 0:
        m = re.search(r"Error at line (\d+): (.*)", r.stderr)
        if m:
            raise EngineParseError(int(m.group(1)), m.group(2).strip())
        raise EngineParseError(None, r.stderr.strip() or f"exit {r.returncode}")
    return r


def export_ast(src: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "in.spd"
        out = Path(tmp) / "ast.json"
        inp.write_text(src, encoding="utf-8")
        _run(["-i", str(inp), "-o", os.devnull, "--export-ast", str(out)])
        return json.loads(out.read_text(encoding="utf-8"))


def render_svg(src: str, options: dict, *, import_ast: bool = False, pretty: bool = True) -> str:
    args = ["-p"] if pretty else []
    if import_ast:
        args.append("--import-ast")
    for key, value in options.items():
        if value is None or value is False:
            continue
        if value is True:  # flag option
            args.append(f"--{key.replace('_', '-')}")
            continue
        args += [f"--{key.replace('_', '-')}", str(value)]
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / ("in.json" if import_ast else "in.spd")
        inp.write_text(src, encoding="utf-8")
        return _run(["-i", str(inp), *args]).stdout


@dataclass
class Divergence:
    path: str
    expected: object
    actual: object

    def describe(self) -> str:
        return f"at {self.path}: expected {_short(self.expected)}, padtools_ts produced {_short(self.actual)}"


def _short(v: object) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 120 else s[:117] + "..."


def _norm(node):
    """Normalise both ASTs: strip box text, unwrap the Map encoding."""
    if isinstance(node, list):
        return [_norm(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "text" and isinstance(v, str):
            out[k] = "\n".join(seg.strip() for seg in v.strip().split("\n"))
        elif k == "cases" and isinstance(v, dict) and v.get("__type") == "Map":
            out[k] = [[c, _norm(b)] for c, b in v["value"]]
        else:
            out[k] = _norm(v)
    return out


def compare(expected: dict | None, actual: dict | None) -> Divergence | None:
    return _diff(_norm(expected), _norm(actual), "$")


def _diff(e, a, path: str) -> Divergence | None:
    if type(e) is not type(a):
        return Divergence(path, e, a)
    if isinstance(e, dict):
        for k in sorted(set(e) | set(a)):
            d = _diff(e.get(k), a.get(k), f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(e, list):
        if len(e) != len(a):
            return Divergence(path, e, a)
        for i, (x, y) in enumerate(zip(e, a)):
            d = _diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if e == a else Divergence(path, e, a)
