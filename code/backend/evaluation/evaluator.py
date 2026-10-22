from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.core.sandbox import SandboxConfig, run_command
from backend.core.text import clip
from backend.evaluation.mirror import mirror_source
from backend.evaluation.tasks import Task

_HARNESS = r"""
import json, os, sys, types, unittest

def _main():
    payload = json.loads(sys.stdin.read())
    nonce, fd, source = payload["nonce"], payload["fd"], payload["tests"]
    write, leave, dumps = os.write, os._exit, json.dumps
    sys.path.insert(0, os.getcwd())

    def report(body):
        body["nonce"] = nonce
        data = memoryview((dumps(body) + "\n").encode())
        while data:
            data = data[write(fd, data):]
        leave(0)

    def flatten(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from flatten(item)
            else:
                yield item

    module = types.ModuleType("hidden_tests")
    module.__file__ = "hidden_tests.py"
    sys.modules["hidden_tests"] = module
    try:
        exec(compile(source, "hidden_tests.py", "exec"), module.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        ids = [t.id() for t in flatten(suite)]
    except BaseException as exc:
        report({"kind": "error", "error": repr(exc)[:300]})
    result = unittest.TestResult()
    suite.run(result)
    failed = set()
    for bucket in (result.failures, result.errors, result.skipped):
        for test, _ in bucket:
            failed.add(getattr(test, "test_case", test).id())
    report({"kind": "result", "tests": [[i, 0 if i in failed else 1] for i in ids]})

_main()
"""


@dataclass
class EvalOutcome:
    passed: int
    total: int
    error: str = ""
    tamper: str = ""

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _canary_ids(tag: str) -> tuple[str, str]:
    cls = f"hidden_tests.T{tag}"
    return f"{cls}.test_{tag}a", f"{cls}.test_{tag}b"


def _canary_source(tag: str) -> str:
    return (
        "\n\nimport unittest as _u" + tag + "\n\n\n"
        f"class T{tag}(_u{tag}.TestCase):\n"
        f"    def test_{tag}a(self):\n        self.assertEqual(sum([1, 2]), 3)\n\n"
        f"    def test_{tag}b(self):\n        self.assertEqual(sum([1, 2]), 4)\n"
    )


def _parse_channel(raw: str, nonce: str) -> tuple[dict | None, str]:
    records, foreign = [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            foreign += 1
            continue
        if isinstance(body, dict) and body.get("nonce") == nonce:
            records.append(body)
        else:
            foreign += 1
    if foreign:
        return None, "foreign writes to the result channel"
    if len(records) > 1:
        return None, "more than one result record"
    return (records[0] if records else None), ""


def evaluate(task: Task, workspace: Path, timeout_s: float = 60.0) -> EvalOutcome:
    if task.kind == "repo":
        from backend.evaluation.repo_eval import evaluate_repo

        return evaluate_repo(task, workspace)
    nonce, tag = secrets.token_hex(16), secrets.token_hex(6)
    mirrored = mirror_source(task.hidden_tests, tag)
    config = SandboxConfig(
        timeout_s=timeout_s,
        memory_mb=1024,
        cpu_s=int(timeout_s) + 5,
        network=False,
    )
    with tempfile.TemporaryDirectory(prefix="sing_eval_") as tmp:
        root = Path(tmp)
        target = root / "w"
        shutil.copytree(
            workspace,
            target,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", ".git"),
        )
        channel = root / "verdict"
        fd = os.open(channel, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            result = run_command(
                [sys.executable, "-c", _HARNESS],
                target,
                config,
                stdin_text=json.dumps(
                    {
                        "nonce": nonce,
                        "fd": fd,
                        "tests": mirrored.source + _canary_source(tag),
                    }
                ),
                pass_fds=(fd,),
            )
        finally:
            os.close(fd)
        raw = channel.read_text(errors="replace") if channel.is_file() else ""

    if result.timed_out:
        return EvalOutcome(passed=0, total=1, error="timed out")
    record, tamper = _parse_channel(raw, nonce)
    if tamper:
        return EvalOutcome(
            passed=0, total=1, error=f"evaluator tamper: {tamper}", tamper=tamper
        )
    if record is None:
        return EvalOutcome(
            passed=0,
            total=1,
            error="no result from evaluator: " + clip(result.stderr.strip(), 300),
        )
    if record.get("kind") == "error":
        return EvalOutcome(passed=0, total=1, error=str(record.get("error", "")))
    try:
        outcomes = {str(i): int(v) for i, v in record["tests"]}
    except (KeyError, TypeError, ValueError):
        return EvalOutcome(
            passed=0,
            total=1,
            error="evaluator tamper: malformed record",
            tamper="malformed record",
        )
    ok_id, bad_id = _canary_ids(tag)
    if outcomes.pop(ok_id, None) != 1 or outcomes.pop(bad_id, None) != 0:
        return EvalOutcome(
            passed=0,
            total=1,
            error="evaluator tamper: canary tests were not run faithfully",
            tamper="canary mismatch",
        )
    for real, mirror in mirrored.pairs.items():
        real_result, mirror_result = (
            outcomes.pop(real, None),
            outcomes.pop(mirror, None),
        )
        if real_result is None or mirror_result is None:
            return EvalOutcome(
                passed=0,
                total=1,
                error="evaluator tamper: mirror tests missing",
                tamper="mirror missing",
            )
        if real_result == 1 and mirror_result == 1:
            return EvalOutcome(
                passed=0,
                total=1,
                error="evaluator tamper: a test and its mirror both passed",
                tamper="mirror mismatch",
            )
        outcomes[real] = real_result
    return EvalOutcome(sum(outcomes.values()), len(outcomes), "")


def validate_tasks(tasks: list[Task]) -> list[str]:
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
            return [*problems, f"{task.id}: gold patch did not apply: {error}"]
        fixed = evaluate(task, workspace)
        if fixed.score < 1.0:
            problems.append(
                f"{task.id}: gold patch scores {fixed.passed}/{fixed.total} {fixed.error}"
            )
    return problems
