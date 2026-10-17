import pytest
from backend.evaluation.integrity import scan_workspace
from backend.evaluation.runner import RunConfig, run_task
from backend.evolution.evolve import BUILTIN_GENOME
from testkit import FIZZ


def scan(tmp_path, code):
    (tmp_path / "s.py").write_text(code)
    return scan_workspace(tmp_path)


def test_clean_code_has_no_flags(tmp_path):
    assert (
        scan(
            tmp_path,
            "import math\n\ndef f(x):\n    return math.sqrt(x)\n\nif __name__ == '__main__':\n    print(f(4))\n",
        )
        == []
    )


@pytest.mark.parametrize(
    "code, expected",
    [
        ("import atexit\n", "import:atexit"),
        ("from subprocess import run\n", "import:subprocess"),
        ("import os\nos._exit(0)\n", "call:os._exit"),
        ("import sys\nsys.exit(0)\n", "module_level_exit"),
        ("x = eval('1+1')\n", "dynamic:eval"),
        ("open('hidden_tests.py')\n", "evaluator_reference"),
        (
            "import unittest\nunittest.TestCase.run = lambda s, r=None: None\n",
            "patch:unittest",
        ),
    ],
)
def test_tampering_patterns_are_flagged(tmp_path, code, expected):
    assert any(expected in flag for flag in scan(tmp_path, code))


def test_exit_inside_function_is_not_flagged(tmp_path):
    assert scan(tmp_path, "import sys\n\ndef main():\n    sys.exit(0)\n") == []


def test_syntax_errors_and_pycache_are_ignored(tmp_path):
    (tmp_path / "bad.py").write_text("def (:\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("import atexit\n")
    assert scan_workspace(tmp_path) == []


def cheating_script():
    code = FIZZ.reference["solution.py"] + "\nimport atexit\n"
    return [
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {"path": "solution.py", "content": code},
                }
            ]
        },
        {"tool_calls": [{"name": "finish", "arguments": {"summary": "done"}}]},
    ]


def test_strict_mode_zeroes_a_flagged_solution(tmp_path, write_script):
    cfg = RunConfig(
        llm_spec=write_script("cheat.json", cheating_script()), integrity="strict"
    )
    result = run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    assert (
        result.score == 0.0
        and result.integrity_flags
        and "integrity violation" in result.error
    )


def test_warn_mode_keeps_the_score_but_records_flags(tmp_path, write_script):
    cfg = RunConfig(
        llm_spec=write_script("cheat.json", cheating_script()), integrity="warn"
    )
    result = run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    assert result.score == 1.0 and result.integrity_flags


def test_off_mode_does_not_scan(tmp_path, write_script):
    cfg = RunConfig(
        llm_spec=write_script("cheat.json", cheating_script()), integrity="off"
    )
    result = run_task(FIZZ, BUILTIN_GENOME, cfg, tmp_path)
    assert result.score == 1.0 and result.integrity_flags == []
