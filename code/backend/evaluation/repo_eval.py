from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

from backend.core.sandbox import SandboxConfig, run_command
from backend.core.text import clip
from backend.evaluation.tasks import Task

DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)
RESULT_LINE = re.compile(
    r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (.+)$", re.MULTILINE
)
IGNORED = shutil.ignore_patterns("__pycache__", ".git", ".pytest_cache")
# Files that change how pytest collects, runs and reports. An agent's edits to them are discarded before
# judging, because a conftest hook can turn failures into passes without touching the code under test.
PYTEST_CONTROL_FILES = ("conftest.py", "pytest.ini", "tox.ini")
SUMMARY_HEADER = "short test summary info"
FOOTER = re.compile(r"^=*\s*\d+ .*\bin [\d.]+s\b.*$")


def summary_section(output: str) -> str:
    """The block pytest prints under 'short test summary info', and nothing around it.

    Captured stdout of individual tests appears earlier in `-rA` output and anything printed after the
    footer line comes from code running after pytest finished, so neither is allowed to speak for a test.
    """
    if SUMMARY_HEADER not in output:
        return ""
    lines = output.rsplit(SUMMARY_HEADER, 1)[1].splitlines()[1:]
    kept = []
    for line in lines:
        if FOOTER.match(line):
            break
        kept.append(line)
    return "\n".join(kept)


def reset_pytest_control_files(workspace: Path, base: Path) -> None:
    """Put every conftest.py / pytest.ini / tox.ini back to the base state (deleting ones the agent added)."""

    def control_files(root: Path) -> set[str]:
        found = set()
        for name in PYTEST_CONTROL_FILES:
            for path in root.rglob(name):
                rel = path.relative_to(root)
                if not any(part in {".git", "__pycache__"} for part in rel.parts):
                    found.add(rel.as_posix())
        return found

    for rel in control_files(workspace) | control_files(base):
        destination, original = workspace / rel, base / rel
        if original.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                destination.unlink()
            shutil.copy2(original, destination)
        elif destination.exists() or destination.is_symlink():
            destination.unlink()


def patch_paths(patch: str) -> list[str]:
    """Files a unified git diff touches (the b/ side)."""
    return sorted({m.group(2) for m in DIFF_HEADER.finditer(patch)})


def apply_patch(directory: Path, patch: str) -> str | None:
    """Apply a git-format patch to a directory (a repository is not required). Returns an error or None."""
    if shutil.which("git") is None:
        return "git is required to apply patches"
    with tempfile.TemporaryDirectory(prefix="sing_patch_") as tmp:
        patch_file = Path(tmp) / "change.patch"
        patch_file.write_text(patch)
        result = run_command(
            ["git", "apply", "--whitespace=nowarn", str(patch_file)],
            directory,
            SandboxConfig(timeout_s=60, memory_mb=1024),
        )
    return (
        None
        if result.returncode == 0
        else clip(result.stderr.strip() or result.stdout.strip(), 400)
    )


def parse_pytest_results(output: str) -> dict[str, str]:
    """Map test node ids to a status from `pytest -rA` summary lines."""
    statuses: dict[str, str] = {}
    for status, rest in RESULT_LINE.findall(output):
        node = (
            rest.split(" - ", 1)[0].strip()
            if status in {"FAILED", "ERROR"}
            else rest.strip()
        )
        statuses[node] = status
    return statuses


def prepare_eval_dir(task: Task, workspace: Path, target: Path) -> str | None:
    """Copy the agent's result, reset the test files the patch touches to the base state, then apply the patch.

    Resetting first means the agent cannot pass by editing the tests it will be judged on.
    """
    shutil.copytree(workspace, target, symlinks=True, ignore=IGNORED)
    base = Path(task.repo_dir)
    reset_pytest_control_files(target, base)
    for rel in patch_paths(task.test_patch):
        destination = target / rel
        if (base / rel).is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / rel, destination)
        elif destination.exists():
            destination.unlink()
    return apply_patch(target, task.test_patch)


def evaluate_repo(task: Task, workspace: Path):
    from backend.evaluation.evaluator import EvalOutcome

    total = len(task.fail_to_pass)
    with tempfile.TemporaryDirectory(prefix="sing_repo_eval_") as tmp:
        target = Path(tmp) / "w"
        error = prepare_eval_dir(task, workspace, target)
        if error:
            return EvalOutcome(
                passed=0, total=total, error=f"test patch did not apply: {error}"
            )
        listed = list(task.fail_to_pass) + list(task.pass_to_pass)
        files = sorted({node.split("::", 1)[0] for node in listed})
        config = SandboxConfig(
            timeout_s=task.test_timeout_s,
            memory_mb=4096,
            cpu_s=int(task.test_timeout_s) + 30,
            max_output_chars=2_000_000,
        )
        result = run_command(
            [
                task.python or sys.executable,
                "-m",
                "pytest",
                "-q",
                "-rA",
                "-p",
                "no:cacheprovider",
                *files,
            ],
            target,
            config,
        )
    if result.timed_out:
        return EvalOutcome(passed=0, total=total, error="tests timed out")
    statuses = parse_pytest_results(summary_section(result.stdout))
    if not statuses:
        return EvalOutcome(
            passed=0,
            total=total,
            error="no test results: " + clip(result.stderr or result.stdout, 300),
        )
    fixed = sum(1 for node in task.fail_to_pass if statuses.get(node) == "PASSED")
    regressions = [node for node in task.pass_to_pass if statuses.get(node) != "PASSED"]
    if regressions:
        return EvalOutcome(
            passed=0,
            total=total,
            error=f"{len(regressions)} previously passing test(s) now fail, e.g. {regressions[0]}",
        )
    return EvalOutcome(passed=fixed, total=total)
