from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from ai_models.llm import Budget, BudgetedClient, make_llm
from backend.core.loader import check_contract, load_genome
from backend.core.sandbox import SandboxConfig
from backend.core.text import clip
from backend.core.trace import RunTrace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.core.worker")
    parser.add_argument("--genome", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--llm", required=True)
    parser.add_argument("--sandbox-json", required=True)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-tokens", type=int, default=400_000)
    parser.add_argument("--max-calls", type=int, default=60)
    args = parser.parse_args(argv)

    started = time.monotonic()
    try:
        task = Path(args.task_file).read_text()
        solve = load_genome(Path(args.genome))
        check_contract(solve)
        llm = BudgetedClient(
            make_llm(args.llm), Budget(args.max_tokens, args.max_calls)
        )
        trace = solve(
            task,
            Path(args.workspace),
            llm,
            SandboxConfig.from_json(args.sandbox_json),
            max_steps=args.max_steps,
        )
        if not isinstance(trace, RunTrace):
            raise TypeError(f"solve returned {type(trace).__name__}, expected RunTrace")
    except BaseException:
        trace = RunTrace(
            stop_reason="genome_error", error=clip(traceback.format_exc(), 3000)
        )
    trace.wall_s = round(time.monotonic() - started, 3)
    Path(args.out).write_text(json.dumps(trace.to_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
