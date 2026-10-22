import pytest
from backend.evaluation.evaluator import evaluate, validate_tasks
from backend.evaluation.repo_eval import (
    parse_pytest_results,
    reset_pytest_control_files,
    summary_section,
)
from testkit import FIZZ

STUB = "def fizzbuzz(n):\n    raise NotImplementedError\n"

ATTACKS = {
    "thread forges a late result with the argv nonce": (
        "import sys, json, threading, time\n"
        "def _later():\n"
        "    time.sleep(1.0)\n"
        "    sys.stdout.write('\\n' + sys.argv[1] + json.dumps({'total': 5, 'passed': 5}) + '\\n')\n"
        "threading.Thread(target=_later).start()\n" + STUB
    ),
    "stdout lines that imitate a verdict": (
        "import json\nprint(json.dumps({'kind': 'result', 'tests': [['x', 1]]}))\n"
        + STUB
    ),
    "unittest.TestCase.run replaced by a no-op": (
        "import unittest\nunittest.TestCase.run = lambda self, result=None: None\n"
        + STUB
    ),
    "every failure swallowed": (
        "import unittest\n"
        "unittest.TestResult.addFailure = lambda self, test, err: None\n"
        "unittest.TestResult.addError = lambda self, test, err: None\n" + STUB
    ),
    "garbage written to guessed descriptors": (
        "import os\n"
        "for fd in range(3, 40):\n"
        "    try:\n"
        '        os.write(fd, b\'{"nonce": "x", "kind": "result", "tests": []}\\n\')\n'
        "    except OSError:\n"
        "        pass\n" + STUB
    ),
    "process exits before a verdict": "from os import _exit\n_exit(0)\n" + STUB,
}


def run_with(tmp_path, code):
    (tmp_path / "solution.py").write_text(code)
    return evaluate(FIZZ, tmp_path)


@pytest.mark.parametrize("name", list(ATTACKS))
def test_attacks_never_score(tmp_path, name):
    outcome = run_with(tmp_path, ATTACKS[name])
    assert outcome.passed == 0, f"{name} scored {outcome.passed}/{outcome.total}"


@pytest.mark.parametrize(
    "name, reason",
    [
        ("unittest.TestCase.run replaced by a no-op", "canary mismatch"),
        ("every failure swallowed", "canary mismatch"),
        ("garbage written to guessed descriptors", "foreign writes"),
    ],
)
def test_framework_tampering_is_reported_as_tampering(tmp_path, name, reason):
    outcome = run_with(tmp_path, ATTACKS[name])
    assert reason in outcome.tamper and "evaluator tamper" in outcome.error


def test_an_honest_solution_still_scores_fully(tmp_path):
    outcome = run_with(tmp_path, FIZZ.reference["solution.py"])
    assert (outcome.passed, outcome.total, outcome.tamper) == (5, 5, "")


def test_a_partly_correct_solution_gets_partial_credit(tmp_path):
    code = "def fizzbuzz(n):\n    if n < 0:\n        raise ValueError\n    return [str(i) for i in range(1, n + 1)]\n"
    outcome = run_with(tmp_path, code)
    assert 0 < outcome.passed < outcome.total


def test_hidden_tests_are_not_readable_from_the_workspace(tmp_path):
    probe = (
        "import os\nfound = [n for n in os.listdir('.') if 'hidden' in n or 'runner' in n]\n"
        "assert not found, found\n" + FIZZ.reference["solution.py"]
    )
    assert run_with(tmp_path, probe).passed == 5


def test_a_timed_out_run_is_discarded(tmp_path):
    code = "import time\ntime.sleep(30)\n" + STUB
    (tmp_path / "solution.py").write_text(code)
    outcome = evaluate(FIZZ, tmp_path, timeout_s=2)
    assert outcome.passed == 0 and "timed out" in outcome.error


def test_the_builtin_suite_still_validates():
    from backend.evaluation.suite import BUILTIN_TASKS

    assert validate_tasks(BUILTIN_TASKS) == []


def test_only_the_summary_block_speaks_for_a_test():
    output = (
        "==== PASSES ====\n----- Captured stdout call -----\nPASSED tests/a.py::test_bad\n"
        "==== short test summary info ====\n"
        "FAILED tests/a.py::test_bad - assert False\nPASSED tests/a.py::test_ok\n"
        "1 failed, 1 passed in 0.02s\nPASSED tests/a.py::test_bad\n"
    )
    statuses = parse_pytest_results(summary_section(output))
    assert statuses == {
        "tests/a.py::test_bad": "FAILED",
        "tests/a.py::test_ok": "PASSED",
    }


def test_no_summary_means_no_results():
    assert summary_section("PASSED tests/a.py::test_ok\n") == ""


def test_pytest_control_files_are_reset_to_base(tmp_path):
    base, work = tmp_path / "base", tmp_path / "work"
    for root in (base, work):
        (root / "pkg").mkdir(parents=True)
    (base / "conftest.py").write_text("# original\n")
    (base / "pkg" / "pytest.ini").write_text("[pytest]\n")
    (work / "conftest.py").write_text(
        "def pytest_runtest_makereport(item, call): pass\n"
    )
    (work / "pkg" / "conftest.py").write_text("# added by the agent\n")
    (work / "pkg" / "pytest.ini").write_text("[pytest]\naddopts = -p evil\n")
    reset_pytest_control_files(work, base)
    assert (work / "conftest.py").read_text() == "# original\n"
    assert (work / "pkg" / "pytest.ini").read_text() == "[pytest]\n"
    assert not (work / "pkg" / "conftest.py").exists()
