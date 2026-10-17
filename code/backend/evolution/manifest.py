from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path

from backend import __version__
from backend.evaluation.tasks import Task

CODE_ROOT = Path(__file__).resolve().parents[2]


def frozen_code_hash() -> str:
    """Hash of the frozen engine (backend and the LLM layer). Excludes tests and the mutable genome."""
    files = [
        p
        for p in sorted((CODE_ROOT / "backend").rglob("*.py"))
        if "tests" not in p.parts
    ]
    files.append(CODE_ROOT / "ai_models" / "llm.py")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(CODE_ROOT).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def task_fingerprints(tasks: list[Task]) -> dict[str, str]:
    out = {}
    for task in tasks:
        digest = hashlib.sha256()
        digest.update(
            json.dumps(
                [
                    task.prompt,
                    task.files,
                    task.hidden_tests,
                    task.split,
                    task.kind,
                    task.test_patch,
                    list(task.fail_to_pass),
                    list(task.pass_to_pass),
                ],
                sort_keys=True,
            ).encode()
        )
        out[task.id] = digest.hexdigest()[:16]
    return out


def write_manifest(root: Path, config, tasks: list[Task]) -> list[str]:
    """Record how an experiment was run. On resume, report anything that changed since it started."""
    path = Path(root) / "manifest.json"
    current = {
        "frozen_code_sha256": frozen_code_hash(),
        "tasks": task_fingerprints(tasks),
    }
    warnings: list[str] = []
    if path.is_file():
        manifest = json.loads(path.read_text())
        if manifest["frozen_code_sha256"] != current["frozen_code_sha256"]:
            warnings.append(
                "warning: frozen engine code changed since this experiment started"
            )
        if manifest["tasks"] != current["tasks"]:
            warnings.append(
                "warning: the task set changed since this experiment started"
            )
        if warnings:
            manifest.setdefault("history", []).append(
                {"at": time.time(), "warnings": warnings, **current}
            )
            path.write_text(json.dumps(manifest, indent=2))
        return warnings
    path.write_text(
        json.dumps(
            {
                "singularis_version": __version__,
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "created_at": time.time(),
                "config": asdict(config),
                **current,
            },
            indent=2,
        )
    )
    return warnings
