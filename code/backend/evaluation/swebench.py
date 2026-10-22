from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

DEFAULT_SOURCE = "https://github.com/{repo}.git"
REQUIRED_FIELDS = (
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "patch",
    "test_patch",
    "FAIL_TO_PASS",
)

PROMPT = (
    "Resolve the following issue in this repository, which is your working directory. Change the source code "
    "so that the behavior described in the issue is fixed. Do not modify existing tests. Read the relevant code "
    "before editing it, and run the tests you can to check your change.\n\nIssue:\n{statement}"
)


class SwebenchError(Exception):
    pass


def _as_list(value) -> list[str]:
    """SWE-bench stores the test id lists as JSON strings; accept real lists too."""
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else []
    return [str(v) for v in value]


def load_instances(path: Path) -> list[dict]:
    """Read a SWE-bench style dataset file: JSON Lines, or a JSON array."""
    text = Path(path).read_text().strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def assign_split(instance_id: str, ratios: tuple[int, int, int] = (60, 20, 20)) -> str:
    bucket = int(hashlib.sha256(instance_id.encode()).hexdigest(), 16) % sum(ratios)
    if bucket < ratios[0]:
        return "train"
    return "heldout" if bucket < ratios[0] + ratios[1] else "fresh"


def _git(args: list[str], cwd: Path | None = None, timeout: int = 900) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise SwebenchError(
            f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}"
        )
    return result.stdout


def prepare_instance(
    instance: dict,
    out_dir: Path,
    cache_dir: Path,
    python: str = "",
    repo_source: str = DEFAULT_SOURCE,
    split: str = "auto",
    test_timeout_s: float = 900,
) -> Path:
    """Turn one dataset instance into a task directory the loader understands."""
    missing = [f for f in REQUIRED_FIELDS if f not in instance]
    if missing:
        raise SwebenchError(f"instance is missing fields: {', '.join(missing)}")
    if shutil.which("git") is None:
        raise SwebenchError("git is required")
    instance_id = instance["instance_id"]
    cached = Path(cache_dir) / "repos" / instance["repo"].replace("/", "__")
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        _git(
            ["clone", "--quiet", repo_source.format(repo=instance["repo"]), str(cached)]
        )

    task_dir = Path(out_dir) / instance_id
    shutil.rmtree(task_dir, ignore_errors=True)
    task_dir.mkdir(parents=True)
    repo_dir = task_dir / "repo"
    _git(["clone", "--quiet", "--shared", str(cached), str(repo_dir)])
    _git(["checkout", "--quiet", instance["base_commit"]], cwd=repo_dir)
    shutil.rmtree(repo_dir / ".git")

    (task_dir / "test.patch").write_text(instance["test_patch"])
    (task_dir / "gold.patch").write_text(instance["patch"])
    meta = {
        "id": instance_id,
        "kind": "repo",
        "prompt": PROMPT.format(statement=instance["problem_statement"].strip()),
        "split": assign_split(instance_id) if split == "auto" else split,
        "track": "swebench",
        "python": python,
        "fail_to_pass": _as_list(instance["FAIL_TO_PASS"]),
        "pass_to_pass": _as_list(instance.get("PASS_TO_PASS", [])),
        "test_timeout_s": test_timeout_s,
        "repo": instance["repo"],
        "base_commit": instance["base_commit"],
    }
    (task_dir / "task.json").write_text(json.dumps(meta, indent=2))
    return task_dir
