import json

from backend.evaluation.runner import RunConfig, run_task
from backend.evolution.evolve import BUILTIN_GENOME
from testkit import FIZZ, solving_script


def trace_of(tmp_path):
    return json.loads((tmp_path / "traces" / "fizzbuzz.trace.json").read_text())


def test_scripted_agent_solves_task_end_to_end(tmp_path, write_script):
    steps = [
        {"text": "plan", "tool_calls": [{"name": "list_files", "arguments": {}}]},
        *solving_script(),
    ]
    steps.insert(
        -1,
        {
            "tool_calls": [
                {
                    "name": "run_python",
                    "arguments": {
                        "args": ["-c", "import solution; print(solution.fizzbuzz(5))"]
                    },
                }
            ]
        },
    )
    cfg = RunConfig(llm_spec=write_script("solve.json", steps))
    result = run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    assert (
        result.score == 1.0 and result.stop_reason == "finished" and result.tokens > 0
    )
    trace = trace_of(tmp_path)
    assert trace["finished"] and trace["steps"][2]["calls"][0]["output"].startswith(
        "exit code 0"
    )


def test_agent_that_does_nothing_scores_zero(tmp_path, write_script):
    cfg = RunConfig(llm_spec=write_script("idle.json", [{"text": "I give up"}]))
    result = run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    assert result.score == 0.0 and result.stop_reason == "no_tool_calls"


def test_path_escape_is_reported_to_agent_not_executed(tmp_path, write_script):
    script = [
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {"path": "../escape.txt", "content": "x"},
                }
            ]
        },
        {"tool_calls": [{"name": "finish", "arguments": {"summary": "done"}}]},
    ]
    cfg = RunConfig(llm_spec=write_script("escape.json", script))
    run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    first = trace_of(tmp_path)["steps"][0]["calls"][0]
    assert first["is_error"] and "escapes workspace" in first["output"]
    assert not (tmp_path / "workspaces" / "escape.txt").exists()


def test_budget_stops_runaway_agent(tmp_path, write_script):
    loop = [{"tool_calls": [{"name": "list_files", "arguments": {}}]}] * 50
    cfg = RunConfig(llm_spec=write_script("loop.json", loop), max_calls=3)
    assert run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path).stop_reason == "budget"


def test_broken_genome_is_contained(tmp_path, write_script):
    broken = tmp_path / "broken_genome"
    broken.mkdir()
    (broken / "__init__.py").write_text("raise RuntimeError('boom')\n")
    cfg = RunConfig(llm_spec=write_script("x.json", [{}]))
    result = run_task(FIZZ, broken, cfg, tmp_path / "out")
    assert (
        result.stop_reason == "genome_error"
        and result.score == 0.0
        and "boom" in result.error
    )


def test_tool_errors_do_not_crash_loop(tmp_path, write_script):
    script = [
        {
            "tool_calls": [
                {"name": "read_file", "arguments": {"path": "missing.py"}},
                {"name": "nope", "arguments": {}},
            ]
        },
        {"tool_calls": [{"name": "finish", "arguments": {"summary": "ok"}}]},
    ]
    cfg = RunConfig(llm_spec=write_script("err.json", script))
    run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    trace = trace_of(tmp_path)
    assert all(c["is_error"] for c in trace["steps"][0]["calls"]) and trace["finished"]
