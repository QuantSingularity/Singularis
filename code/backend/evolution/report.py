from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from backend.evolution.archive import Archive

MAX_DIFF_CHARS = 20_000


def _read_json(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def build_report(root: Path) -> dict:
    archive = Archive(root)
    agents = []
    for record in archive.all():
        base = archive.agent_dir(record.id)
        diff_path = base / "diff.patch"
        train = _read_json(base / "results_train.json")
        heldout = _read_json(base / "results_heldout.json")
        agents.append(
            {
                **asdict(record),
                "diff": (
                    diff_path.read_text()[:MAX_DIFF_CHARS]
                    if diff_path.is_file()
                    else ""
                ),
                "train_results": train["results"] if train else [],
                "heldout_results": heldout["results"] if heldout else [],
            }
        )
    best = archive.best()
    root = Path(root)
    manifest = _read_json(root / "manifest.json") or {}
    return {
        "generated_at": time.time(),
        "best": best.id if best else None,
        "usage": _read_json(root / "usage.json") or {},
        "meta_prompts": _read_json(root / "meta_prompts" / "stats.json") or {},
        "manifest": {
            k: manifest[k]
            for k in (
                "singularis_version",
                "python",
                "created_at",
                "frozen_code_sha256",
            )
            if k in manifest
        },
        "agents": agents,
    }


def write_report(root: Path, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_report(root), indent=2))
    return out
