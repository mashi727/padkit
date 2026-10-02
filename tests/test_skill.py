import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import BROKEN, OK

from padkit.lint import lint_text

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "skill" / "scripts" / "spd_lint.py"
EXAMPLES = sorted((ROOT / "skill" / "examples").glob("*.spd"))


def _builder():
    spec = importlib.util.spec_from_file_location("build_skill_lint", ROOT / "scripts" / "build_skill_lint.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bundle_is_up_to_date():
    assert BUNDLE.read_text(encoding="utf-8") == _builder().build(), (
        "skill/scripts/spd_lint.py is stale; run `uv run python scripts/build_skill_lint.py`"
    )


@pytest.mark.parametrize("path", OK + BROKEN + EXAMPLES, ids=lambda p: p.name)
def test_bundle_agrees_with_padkit(path):
    r = subprocess.run([sys.executable, str(BUNDLE), "--json", str(path)],
                       capture_output=True, text=True)
    report = json.loads(r.stdout)
    expected = lint_text(path.read_text(encoding="utf-8"), str(path))
    assert [d["code"] for d in report["diagnostics"]] == [d.code for d in expected.diagnostics]
    assert r.returncode == (1 if expected.errors else 0)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_skill_examples_are_clean(path):
    assert lint_text(path.read_text(encoding="utf-8")).errors == []


def test_skill_frontmatter():
    text = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front = text.split("---\n", 2)[1]
    keys = {line.split(":", 1)[0] for line in front.splitlines() if ":" in line and not line.startswith(" ")}
    assert {"name", "description"} <= keys


DOCS = [ROOT / "README.md", ROOT / "skill" / "SKILL.md", *sorted((ROOT / "skill" / "reference").glob("*.md"))]


def _spd_blocks(path: Path) -> list[str]:
    return re.findall(r"^```spd\n(.*?)^```$", path.read_text(encoding="utf-8"), flags=re.S | re.M)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_spd_blocks_in_docs_are_valid(path):
    for block in _spd_blocks(path):
        assert lint_text(block).errors == [], block


def test_every_lint_code_is_documented():
    src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "padkit").glob("*.py"))
    codes = set(re.findall(r'"([EWI]\d{3})"', src))
    doc = (ROOT / "skill" / "reference" / "lint-codes.md").read_text(encoding="utf-8")
    assert codes and all(f"| {c} |" in doc for c in codes), codes - set(re.findall(r"\| ([EWI]\d{3}) \|", doc))
