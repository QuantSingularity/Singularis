from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Callable

REQUIRED_PARAMS = ("task", "workspace", "llm", "sandbox")


class GenomeError(Exception):
    pass


def load_genome(path: Path) -> Callable:
    path = Path(path).resolve()
    init = path / "__init__.py"
    if not init.is_file():
        raise GenomeError(f"genome has no __init__.py: {path}")
    name = "_genome_" + hashlib.sha1(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(
        name, init, submodule_search_locations=[str(path)]
    )
    if spec is None or spec.loader is None:
        raise GenomeError(f"cannot load genome: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    solve = getattr(module, "solve", None)
    if not callable(solve):
        raise GenomeError("genome does not export a callable 'solve'")
    return solve


def check_contract(solve: Callable) -> None:
    params = list(inspect.signature(solve).parameters)
    if tuple(params[: len(REQUIRED_PARAMS)]) != REQUIRED_PARAMS:
        raise GenomeError(
            f"solve must start with parameters {REQUIRED_PARAMS}, got {params}"
        )
    if "max_steps" not in params:
        raise GenomeError("solve must accept a max_steps parameter")
