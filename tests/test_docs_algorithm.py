"""docs/algorithm: padkit's own algorithm written in SPD."""

import re
from pathlib import Path

import pytest

from padkit.lint import lint_text

DIR = Path(__file__).resolve().parent.parent / "docs" / "algorithm"
FILES = sorted(DIR.glob("*.spd"))


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_algorithm_diagrams_are_valid(path):
    assert lint_text(path.read_text(encoding="utf-8")).errors == []


def test_one_diagram_per_file():
    # several top-level boxes in one file would be drawn as one sequence
    for path in FILES:
        assert sum(1 for ln in _lines(path) if not ln.startswith("\t")) == 1, path.name


def test_call_graph_is_closed():
    titles = {_lines(p)[0] for p in FILES}
    calls = {m.group(1).strip() for p in FILES for ln in _lines(p)
             if (m := re.match(r"\t*:call (.*)", ln))}
    assert calls <= titles, calls - titles
    assert titles - calls == {"padkit を実行する"}
