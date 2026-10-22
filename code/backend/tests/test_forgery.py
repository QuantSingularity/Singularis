import sys

import pytest
from backend.core.sandbox import (
    SandboxConfig,
    build_argv,
    network_isolation_available,
    run_command,
)
from backend.evaluation.evaluator import evaluate
from backend.evaluation.integrity import scan_findings
from backend.evaluation.mirror import mirror_source
from backend.evaluation.suite import BUILTIN_TASKS
from testkit import FIZZ

WALKER = """
import ast
import sys

def fizzbuzz(n):
    raise NotImplementedError

{getframe}
{attr}
while frame is not None:
    local = {read}
    if "report" in local and "source" in local:
        classes = [n for n in ast.parse(local["source"]).body if isinstance(n, ast.ClassDef)]
        out = []
        for index, cls in enumerate(classes):
            names = [m.name for m in cls.body if isinstance(m, ast.FunctionDef) and m.name.startswith("test")]
            for name in names:
                last = index == len(classes) - 1 and name == names[-1]
                out.append(["hidden_tests.%s.%s" % (cls.name, name), 0 if last else 1])
        local["report"]({{"kind": "result", "tests": out}})
    frame = {back}
"""

PLAIN = WALKER.format(
    getframe="frame = sys._getframe(0)",
    attr="",
    read="frame.f_locals",
    back="frame.f_back",
)

OBFUSCATED = WALKER.format(
    getframe='frame = getattr(sys, "_get" + "frame")(0)',
    attr='pick = lambda o, n: getattr(o, "f" + "_" + n)',
    read='pick(frame, "locals")',
    back='pick(frame, "back")',
)


@pytest.mark.parametrize("code", [PLAIN, OBFUSCATED], ids=["plain", "obfuscated"])
def test_a_forged_all_pass_report_is_detected(tmp_path, code):
    (tmp_path / "solution.py").write_text(code)
    outcome = evaluate(FIZZ, tmp_path)
    assert outcome.passed == 0
    assert outcome.tamper == "mirror mismatch"


def test_obfuscated_frame_access_is_a_hard_finding(tmp_path):
    (tmp_path / "solution.py").write_text(OBFUSCATED)
    assert any("obfuscated_attribute" in item for item in scan_findings(tmp_path).hard)


def test_plain_dynamic_getattr_is_not_flagged(tmp_path):
    (tmp_path / "solution.py").write_text(
        "def pick(obj, name):\n    return getattr(obj, name)\n"
    )
    assert scan_findings(tmp_path).hard == []


def test_every_builtin_task_gets_mirrors():
    for task in BUILTIN_TASKS:
        if task.kind == "repo":
            continue
        mirrored = mirror_source(task.hidden_tests, "t0")
        assert mirrored.pairs, task.id
        compile(mirrored.source, task.id, "exec")


def test_mirror_names_differ_between_runs():
    first = mirror_source(FIZZ.hidden_tests, "a1")
    second = mirror_source(FIZZ.hidden_tests, "a1")
    assert set(first.pairs.values()).isdisjoint(second.pairs.values())


def test_decorated_tests_are_left_alone():
    source = (
        "import unittest\n\nclass T(unittest.TestCase):\n"
        "    @unittest.skip('x')\n    def test_a(self):\n        pass\n"
    )
    assert mirror_source(source, "t1").pairs == {}


def test_network_is_blocked_when_isolation_is_available(tmp_path):
    if not network_isolation_available():
        pytest.skip("user namespaces unavailable")
    code = (
        "import socket\ns = socket.socket()\ns.settimeout(2)\n"
        "try:\n    s.connect(('1.1.1.1', 80))\n    print('open')\nexcept OSError:\n    print('blocked')\n"
    )
    result = run_command(
        [sys.executable, "-c", code], tmp_path, SandboxConfig(network=False)
    )
    assert result.stdout.strip() == "blocked"


def test_launcher_applies_process_limits(tmp_path):
    code = "import resource\nprint(resource.getrlimit(resource.RLIMIT_NPROC)[0])\n"
    result = run_command(
        [sys.executable, "-c", code], tmp_path, SandboxConfig(max_procs=300)
    )
    assert result.stdout.strip() == "300"


def test_launcher_argv_has_no_preexec_dependency():
    argv = build_argv(["echo", "hi"], SandboxConfig())
    assert argv[-2:] == ["echo", "hi"]
