from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    files: dict[str, str]
    hidden_tests: str
    reference: dict[str, str] = field(default_factory=dict)
    split: str = "train"
    track: str = "general"
    kind: str = "files"
    repo_dir: str = ""
    test_patch: str = ""
    gold_patch: str = ""
    fail_to_pass: tuple[str, ...] = ()
    pass_to_pass: tuple[str, ...] = ()
    python: str = ""
    test_timeout_s: float = 600.0


def load_tasks_from_dir(root: Path) -> list[Task]:
    """Load tasks from a directory."""
    root = Path(root)
    tasks: list[Task] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        meta_path = directory / "task.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("kind") == "repo":
            tasks.append(_load_repo_task(directory, meta))
            continue
        files_dir = directory / "files"
        files: dict[str, str] = {}
        if files_dir.is_dir():
            for path in sorted(files_dir.rglob("*")):
                if path.is_file():
                    files[path.relative_to(files_dir).as_posix()] = path.read_text()
        tasks.append(
            Task(
                id=meta.get("id", directory.name),
                prompt=meta["prompt"],
                files=files,
                hidden_tests=(directory / "hidden_tests.py").read_text(),
                split=meta.get("split", "train"),
                track=meta.get("track", "general"),
            )
        )
    return tasks


def _load_repo_task(directory: Path, meta: dict) -> Task:
    gold = directory / "gold.patch"
    return Task(
        id=meta.get("id", directory.name),
        prompt=meta["prompt"],
        files={},
        hidden_tests="",
        split=meta.get("split", "train"),
        track=meta.get("track", "swebench"),
        kind="repo",
        repo_dir=str((directory / "repo").resolve()),
        test_patch=(directory / "test.patch").read_text(),
        gold_patch=gold.read_text() if gold.is_file() else "",
        fail_to_pass=tuple(meta["fail_to_pass"]),
        pass_to_pass=tuple(meta.get("pass_to_pass", [])),
        python=meta.get("python", ""),
        test_timeout_s=float(meta.get("test_timeout_s", 600)),
    )


def select_tasks(
    tasks: list[Task], split: str | None = None, ids: list[str] | None = None
) -> list[Task]:
    chosen = tasks
    if split:
        chosen = [t for t in chosen if t.split == split]
    if ids:
        chosen = [t for t in chosen if t.id in ids]
    return chosen
