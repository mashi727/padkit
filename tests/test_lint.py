import json

import pytest
from conftest import BROKEN, OK, expected_codes, to_spaces

from padkit.cli import main
from padkit.lint import lint_text
from padkit.spd import display_width, fix_indent, parse, to_ast


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_ok_fixtures_have_no_errors(path):
    res = lint_text(path.read_text(encoding="utf-8"), str(path))
    assert res.errors == []


@pytest.mark.parametrize("path", BROKEN, ids=lambda p: p.name)
def test_broken_fixtures_raise_exactly_the_declared_errors(path):
    res = lint_text(path.read_text(encoding="utf-8"), str(path))
    assert {d.code for d in res.errors} == expected_codes(path)


@pytest.mark.parametrize("width", [2, 4, 8])
@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_tabs_replaced_by_spaces_always_fail(path, width, capsys, tmp_path):
    """Acceptance 2: the breakage padtools_ts ignores must exit non-zero."""
    broken = tmp_path / path.name
    broken.write_text(to_spaces(path.read_text(encoding="utf-8"), width), encoding="utf-8")
    assert main(["lint", "--no-engine", str(broken)]) == 1
    assert "E001" in capsys.readouterr().out


@pytest.mark.parametrize("path", OK, ids=lambda p: p.name)
def test_fix_indent_restores_the_original(path):
    src = path.read_text(encoding="utf-8")
    fixed, n = fix_indent(to_spaces(src, 4))
    assert fixed == src
    assert n > 0


def test_strict_turns_warnings_into_failure(tmp_path):
    f = tmp_path / "wide.spd"
    f.write_text("根\n\t" + "あ" * 25 + "\n", encoding="utf-8")
    assert main(["lint", "--no-engine", str(f)]) == 0
    assert main(["lint", "--no-engine", "--strict", str(f)]) == 1


def test_json_output_is_machine_readable(tmp_path, capsys):
    f = tmp_path / "a.spd"
    f.write_text("根\n\t:if 条件か\n\t\t真の処理\n", encoding="utf-8")
    main(["lint", "--no-engine", "--format", "json", str(f)])
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert {d["code"] for d in report["diagnostics"]} == {"I301", "I302"}
    assert report["stats"]["counts"] == {"if": 1, "process": 2}


def test_review_heuristics():
    deep = "根\n" + "".join("\t" * d + f"段{d}\n" for d in range(1, 8))
    assert "W201" in {d.code for d in lint_text(deep).diagnostics}

    many = "根\n" + "".join(f"\t処理{i}\n" for i in range(16))
    assert "W203" in {d.code for d in lint_text(many).diagnostics}

    term = "根\n\t:terminal 破綻\n\t続き\n"
    assert "I303" in {d.code for d in lint_text(term).diagnostics}

    tail = "根\n\t続き\n\t:terminal 完了\n\t:comment 注記\n"
    assert "I303" not in {d.code for d in lint_text(tail).diagnostics}


def test_display_width_matches_eastasianwidth():
    assert display_width("abc") == 3
    assert display_width("処理") == 4
    assert display_width("→") == 2  # ambiguous counts as wide, as in padtools_ts


def test_markup_semantics():
    ast = to_ast(parse("根\n\tA@B\n\tC@\n\t\t\tD\n\tE\\@F\n"))
    texts = [n["text"] for n in ast["children"][0]["childNode"]["children"]]
    assert texts == ["A\nB", "C\nD", "E@F"]


def test_unknown_command_suggests_the_prefix():
    res = lint_text("根\n\t:whilex 条件\n")
    (d,) = res.errors
    assert d.code == "E103" and "':while'" in d.message
