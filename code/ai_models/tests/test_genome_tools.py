from ai_models.genome.tools import ToolContext, build_tools, execute
from ai_models.llm import ToolCall
from backend.core.sandbox import SandboxConfig


def run(tmp_path, name, **arguments):
    ctx = ToolContext(workspace=tmp_path, sandbox=SandboxConfig())
    return execute(build_tools(), ctx, ToolCall("1", name, arguments))


def test_edit_file_replaces_exactly_one_occurrence(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    output, is_error = run(
        tmp_path, "edit_file", path="a.py", old_str="x = 1", new_str="x = 10"
    )
    assert not is_error and (tmp_path / "a.py").read_text() == "x = 10\ny = 2\n"


def test_edit_file_rejects_missing_and_ambiguous_matches(tmp_path):
    (tmp_path / "a.py").write_text("v = 1\nv = 1\n")
    missing, missing_error = run(
        tmp_path, "edit_file", path="a.py", old_str="zzz", new_str="q"
    )
    ambiguous, ambiguous_error = run(
        tmp_path, "edit_file", path="a.py", old_str="v = 1", new_str="v = 2"
    )
    assert missing_error and "not found" in missing
    assert ambiguous_error and "2 places" in ambiguous
    assert (tmp_path / "a.py").read_text() == "v = 1\nv = 1\n"


def test_edit_file_cannot_leave_workspace(tmp_path):
    output, is_error = run(
        tmp_path, "edit_file", path="../x.py", old_str="a", new_str="b"
    )
    assert is_error and "escapes workspace" in output


def test_search_text_finds_matches_with_line_numbers(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("x = foo()\n")
    output, is_error = run(tmp_path, "search_text", pattern=r"foo\(")
    assert not is_error
    assert "a.py:1:" in output and "sub/b.py:1:" in output


def test_search_text_handles_no_match_and_bad_pattern(tmp_path):
    (tmp_path / "a.py").write_text("hello\n")
    assert run(tmp_path, "search_text", pattern="zzz")[0] == "(no matches)"
    output, is_error = run(tmp_path, "search_text", pattern="(")
    assert is_error and "invalid regular expression" in output


def test_search_text_skips_hidden_and_binary_files(tmp_path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "a.txt").write_text("needle\n")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe needle \x00")
    assert run(tmp_path, "search_text", pattern="needle")[0] == "(no matches)"
