import json

import pytest
from ai_models.genome.agent import CONTEXT_CHAR_LIMIT, _compact, solve
from ai_models.genome.tools import ToolContext, build_tools, execute
from ai_models.llm import BudgetExceeded, Message, ToolCall, make_llm
from backend.core.loader import GenomeError, check_contract, load_genome
from backend.core.sandbox import SandboxConfig
from backend.evaluation.tasks import load_tasks_from_dir, select_tasks
from backend.evolution.evolve import BUILTIN_GENOME
from testkit import FIZZ, solving_script


def call(tmp_path, name, **arguments):
    ctx = ToolContext(workspace=tmp_path, sandbox=SandboxConfig(network=False))
    return execute(build_tools(), ctx, ToolCall("1", name, arguments)), ctx


def scripted(tmp_path, steps):
    path = tmp_path / "script.json"
    path.write_text(json.dumps(steps))
    return make_llm(f"scripted:{path}")


def test_list_and_read_tools(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("one\ntwo\nthree\n")
    (tmp_path / ".hidden").write_text("x")
    (listing, error), _ = call(tmp_path, "list_files")
    assert not error and "pkg/a.py" in listing and ".hidden" not in listing
    (single, _), _ = call(tmp_path, "list_files", path="pkg/a.py")
    assert single == "pkg/a.py"
    (ranged, error), _ = call(
        tmp_path, "read_file", path="pkg/a.py", start_line=2, end_line=3
    )
    assert not error and "2: two" in ranged and "[lines 2-3 of 3]" in ranged
    (empty, error), _ = call(
        tmp_path, "read_file", path="pkg/a.py", start_line=9, end_line=3
    )
    assert error and "empty" in empty
    (_, error), _ = call(tmp_path, "list_files", path="nope")
    assert error
    (_, error), _ = call(tmp_path, "read_file", path="nope.txt")
    assert error


def test_write_search_and_path_escape(tmp_path):
    (written, error), _ = call(
        tmp_path, "write_file", path="d/x.py", content="alpha\nbeta\n"
    )
    assert not error and "wrote 11" in written
    (found, _), _ = call(tmp_path, "search_text", pattern="bet")
    assert "d/x.py:2: beta" in found
    (none, _), _ = call(tmp_path, "search_text", pattern="zzz", path="d")
    assert none == "(no matches)"
    (_, error), _ = call(tmp_path, "search_text", pattern="(")
    assert error
    (_, error), _ = call(tmp_path, "write_file", path="../evil.py", content="x")
    assert error
    (_, error), _ = call(tmp_path, "write_file", path="a.py", content=5)
    assert error
    (_, error), _ = call(tmp_path, "write_file", path="a.py", content="x" * 200_001)
    assert error


def test_search_truncates_many_matches(tmp_path):
    (tmp_path / "big.txt").write_text("hit\n" * 300)
    (found, _), _ = call(tmp_path, "search_text", pattern="hit")
    assert found.endswith("...(truncated)")


def test_run_python_finish_and_unknown_tool(tmp_path):
    (output, error), _ = call(tmp_path, "run_python", args=["-c", "print(41 + 1)"])
    assert not error and "exit code 0" in output and "42" in output
    (_, error), _ = call(tmp_path, "run_python", args="nope")
    assert error
    (done, _), ctx = call(tmp_path, "finish", summary="all done")
    assert done == "finished" and ctx.finished and ctx.summary == "all done"
    (message, error), _ = call(tmp_path, "missing_tool")
    assert error and "unknown tool" in message


def test_compact_elides_old_tool_output_only_when_large():
    messages = [Message(role="tool", content="x" * 500) for _ in range(12)]
    _compact(messages)
    assert messages[0].content.endswith("[elided]") is False
    big = [
        Message(role="tool", content="y" * (CONTEXT_CHAR_LIMIT // 5)) for _ in range(12)
    ]
    _compact(big)
    assert big[0].content.endswith("...[elided]") and not big[-1].content.endswith(
        "[elided]"
    )


def test_solve_stops_when_finished(tmp_path):
    llm = scripted(tmp_path, solving_script())
    work = tmp_path / "w"
    work.mkdir()
    trace = solve(FIZZ.prompt, work, llm, SandboxConfig(network=False))
    assert trace.stop_reason == "finished" and trace.finished
    assert (work / "solution.py").is_file()


def test_solve_stops_without_tool_calls(tmp_path):
    llm = scripted(tmp_path, [{"text": "nothing to do"}])
    trace = solve("task", tmp_path, llm, SandboxConfig(network=False))
    assert trace.stop_reason == "no_tool_calls" and trace.final_text == "nothing to do"


def test_solve_reports_max_steps(tmp_path):
    steps = [{"tool_calls": [{"name": "list_files", "arguments": {}}]}] * 3
    trace = solve(
        "task",
        tmp_path,
        scripted(tmp_path, steps),
        SandboxConfig(network=False),
        max_steps=2,
    )
    assert trace.stop_reason == "max_steps" and len(trace.steps) == 2


class Failing:
    def __init__(self, error):
        self.error = error

    def complete(self, *args, **kwargs):
        raise self.error


def test_solve_reports_llm_errors_and_budget(tmp_path):
    sandbox = SandboxConfig(network=False)
    trace = solve("task", tmp_path, Failing(RuntimeError("boom")), sandbox)
    assert trace.stop_reason == "llm_error" and "boom" in trace.error
    trace = solve("task", tmp_path, Failing(BudgetExceeded("spent")), sandbox)
    assert trace.stop_reason == "budget"


def test_loader_accepts_the_seed_and_rejects_broken_genomes(tmp_path):
    solve_fn = load_genome(BUILTIN_GENOME)
    check_contract(solve_fn)
    with pytest.raises(GenomeError):
        load_genome(tmp_path)
    broken = tmp_path / "g"
    broken.mkdir()
    (broken / "__init__.py").write_text("x = 1\n")
    with pytest.raises(GenomeError):
        load_genome(broken)
    wrong = tmp_path / "w"
    wrong.mkdir()
    (wrong / "__init__.py").write_text("def solve(a, b):\n    return None\n")
    with pytest.raises(GenomeError):
        check_contract(load_genome(wrong))
    nosteps = tmp_path / "n"
    nosteps.mkdir()
    (nosteps / "__init__.py").write_text(
        "def solve(task, workspace, llm, sandbox):\n    return None\n"
    )
    with pytest.raises(GenomeError):
        check_contract(load_genome(nosteps))


def test_load_tasks_from_dir_and_select(tmp_path):
    task_dir = tmp_path / "t1"
    (task_dir / "files").mkdir(parents=True)
    (task_dir / "files" / "a.py").write_text("x = 1\n")
    (task_dir / "task.json").write_text(
        json.dumps({"prompt": "fix", "split": "heldout", "track": "general"})
    )
    (task_dir / "hidden_tests.py").write_text("import unittest\n")
    (tmp_path / "ignored").mkdir()
    tasks = load_tasks_from_dir(tmp_path)
    assert [t.id for t in tasks] == ["t1"] and tasks[0].files == {"a.py": "x = 1\n"}
    assert select_tasks(tasks, "heldout") == tasks
    assert select_tasks(tasks, "train") == []
    assert select_tasks(tasks, None, ["t1"]) == tasks
    assert select_tasks(tasks, None, ["zzz"]) == []
