from pathlib import Path

import pytest

from padkit import engine

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
OK = sorted((FIXTURES / "ok").glob("*.spd"))
BROKEN = sorted((FIXTURES / "broken").glob("*.spd"))

needs_engine = pytest.mark.skipif(
    not engine.is_installed(), reason="padtools_ts not installed (run `padkit setup`)"
)


def expected_codes(path: Path) -> set[str]:
    """Broken fixtures declare what they must trigger: `# expect: E001 E104`."""
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("# expect:"), path
    return set(first.split(":", 1)[1].split())


def to_spaces(src: str, width: int) -> str:
    """The canonical breakage: leading tabs turned into spaces."""
    out = []
    for line in src.splitlines(keepends=True):
        rest = line.lstrip("\t")
        out.append(" " * width * (len(line) - len(rest)) + rest)
    return "".join(out)
