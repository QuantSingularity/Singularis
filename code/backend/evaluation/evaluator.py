from __future__ import annotations

import json
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.core.sandbox import SandboxConfig, run_command
from backend.core.text import clip
from backend.evaluation.tasks import Task

_RUNNER = """\
import importlib.util, json, sys, unittest

NONCE = sys.argv[1]


def emit(payload):
    sys.stdout.write("\\n" + NONCE + json.dumps(payload) + "\\n")
    sys.stdout.flush()


spec = importlib.util.spec_from_file_location("hidden_tests", "hidden_tests.py")
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
except BaseException as exc:
    emit({"total": 1, "passed": 0, "error": repr(exc)[:300]})
    raise SystemExit(0)
result = unittest.TestResult()
suite.run(result)
total = suite.countTestCases()
failed = len(result.failures) + len(result.errors) + len(result.skipped)
emit({"total": total, "passed": max(0, total - failed), "error": ""})
"""


@dataclass
class EvalOutcome:
    passed: int
    total: int
    error: str = ""

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def evaluate(task: Task, workspace: Path, timeout_s: float = 60.0) -> EvalOutcome:
    """Run the task's hidden tests against a copy of the agent's workspace.

    The hidden tests are written only after the agent has finished, into a separate
    copy, so the agent never sees them."""
    if task.kind == "repo":
        from backend.evaluation.repo_eval import evaluate_repo

        return evaluate_repo(task, workspace)
    nonce = secrets.token_hex(12)
    config = SandboxConfig(
        timeout_s=timeout_s, memory_mb=1024, cpu_s=int(timeout_s) + 5
    )
    with tempfile.TemporaryDirectory(prefix="sing_eval_") as tmp:
        target = Path(tmp) / "w"
        shutil.copytree(
            workspace,
            target,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", ".git"),
        )
        (target / "hidden_tests.py").write_text(task.hidden_tests)
        (target / "_runner.py").write_text(_RUNNER)
        result = run_command([sys.executable, "_runner.py", nonce], target, config)

    payload = None
    for line in result.stdout.splitlines():
        if line.startswith(nonce):
            try:
                payload = json.loads(line[len(nonce) :])
            except json.JSONDecodeError:
                payload = None
    if payload is None:
        reason = "timed out" if result.timed_out else clip(result.stderr.strip(), 300)
        return EvalOutcome(
            passed=0, total=1, error=f"no result from evaluator: {reason}"
        )
    return EvalOutcome(
        int(payload["passed"]), int(payload["total"]), str(payload.get("error", ""))
    )


def validate_tasks(tasks: list[Task]) -> list[str]:
    """Check that every task fails with its starter files and passes with its reference solution."""
    problems: list[str] = []
    for task in tasks:
        if task.kind == "repo":
            problems.extend(_validate_repo_task(task))
            continue
        with tempfile.TemporaryDirectory(prefix="sing_validate_") as tmp:
            workspace = Path(tmp)
            for rel, content in task.files.items():
                path = workspace / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            starter = evaluate(task, workspace)
            if starter.score >= 1.0:
                problems.append(
                    f"{task.id}: starter files already pass the hidden tests"
                )
            if not task.reference:
                problems.append(f"{task.id}: no reference solution to validate against")
                continue
            for rel, content in task.reference.items():
                path = workspace / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            solved = evaluate(task, workspace)
            if solved.score < 1.0:
                problems.append(
                    f"{task.id}: reference scores {solved.passed}/{solved.total} {solved.error}"
                )
    return problems


def _validate_repo_task(task: Task) -> list[str]:
    """A repository task is sound when the base state is unresolved and the gold patch resolves it."""
    from backend.evaluation.repo_eval import IGNORED, apply_patch

    if not task.gold_patch:
        return [f"{task.id}: no gold patch to validate against"]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sing_validate_") as tmp:
        workspace = Path(tmp) / "w"
        shutil.copytree(task.repo_dir, workspace, symlinks=True, ignore=IGNORED)
        base = evaluate(task, workspace)
        if base.score >= 1.0:
            problems.append(
                f"{task.id}: the base state already passes the target tests"
            )
        error = apply_patch(workspace, task.gold_patch)
        if error:
            return problems + [f"{task.id}: gold patch did not apply: {error}"]
        fixed = evaluate(task, workspace)
        if fixed.score < 1.0:
            problems.append(
                f"{task.id}: gold patch scores {fixed.passed}/{fixed.total} {fixed.error}"
            )
    return problems
