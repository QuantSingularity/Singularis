"""Shared helpers for the test suite: scripted model runs and a ready-made evolver."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from backend.evaluation.runner import RunConfig
from backend.evaluation.suite import BUILTIN_TASKS
from backend.evaluation.tasks import Task
from backend.evolution.evolve import EvolveConfig, Evolver

NEW_PROMPT = 'SYSTEM_PROMPT = "You are a careful engineer. Verify every change by running code, then call finish."\n'


def get_task(task_id: str) -> Task:
    return next(t for t in BUILTIN_TASKS if t.id == task_id)


FIZZ = get_task("fizzbuzz")


def write_script(directory: Path, name: str, steps: list[dict]) -> str:
    path = Path(directory) / name
    path.write_text(json.dumps(steps))
    return f"scripted:{path}"


def solving_script(task: Task = FIZZ) -> list[dict]:
    writes = [
        {
            "tool_calls": [
                {"name": "write_file", "arguments": {"path": rel, "content": content}}
            ]
        }
        for rel, content in task.reference.items()
    ]
    return [
        *writes,
        {"tool_calls": [{"name": "finish", "arguments": {"summary": "done"}}]},
    ]


def good_meta_script() -> list[dict]:
    return [
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {"path": "genome/prompts.py", "content": NEW_PROMPT},
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "run_python",
                    "arguments": {"args": ["-c", "import genome; print(genome.solve)"]},
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "finish",
                    "arguments": {"summary": "tightened the system prompt"},
                }
            ]
        },
    ]


def breaking_meta_script() -> list[dict]:
    return [
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {
                        "path": "genome/__init__.py",
                        "content": "def solve(a, b):\n    pass\n",
                    },
                }
            ]
        },
        {"tool_calls": [{"name": "finish", "arguments": {"summary": "oops"}}]},
    ]


NEW_META_TEMPLATE = (
    "Improve the agent in ./genome without breaking solve(). Focus: {focus}. Parent: {parent}.\n"
    "Evaluation digest:\n{digest}\nVerify the import, then call finish."
)


def dual_meta_script() -> list[dict]:
    return [
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {"path": "genome/prompts.py", "content": NEW_PROMPT},
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "write_file",
                    "arguments": {
                        "path": "meta_prompt.md",
                        "content": NEW_META_TEMPLATE,
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "run_python",
                    "arguments": {"args": ["-c", "import genome; print(genome.solve)"]},
                }
            ]
        },
        {
            "tool_calls": [
                {"name": "finish", "arguments": {"summary": "tightened the prompts"}}
            ]
        },
    ]


def fizz_tasks() -> list[Task]:
    return [
        FIZZ,
        dataclasses.replace(FIZZ, id="fizzbuzz_heldout", split="heldout"),
        dataclasses.replace(FIZZ, id="fizzbuzz_fresh", split="fresh"),
    ]


def make_evolver(
    tmp_path: Path,
    meta_steps: list[dict],
    iterations: int = 1,
    selection: str = "open_ended",
    meta_every: int = 0,
) -> Evolver:
    tasks = fizz_tasks()[:2]
    config = EvolveConfig(
        eval_run=RunConfig(
            llm_spec=write_script(tmp_path, "solve.json", solving_script())
        ),
        meta_run=RunConfig(llm_spec=write_script(tmp_path, "meta.json", meta_steps)),
        iterations=iterations,
        workers=2,
        selection=selection,
        meta_evolve_every=meta_every,
    )
    return Evolver(tmp_path / "exp", tasks, config, log=lambda message: None)
