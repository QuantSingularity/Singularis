from __future__ import annotations

import json
from pathlib import Path

from ai_models.llm import DEFAULT_MODEL

from backend.core.meter import get_meter, load_api_key
from backend.evaluation.tasks import Task
from backend.evolution.archive import Archive


def plan(
    tasks: list[Task],
    iterations: int,
    train_trials: int,
    heldout_trials: int,
    max_tokens_per_run: int,
) -> dict:
    train = sum(1 for t in tasks if t.split == "train")
    heldout = sum(1 for t in tasks if t.split == "heldout")
    seed_runs = train * train_trials + heldout * heldout_trials
    per_iteration = 1 + train * train_trials + heldout * heldout_trials
    runs = seed_runs + iterations * per_iteration
    return {
        "train_tasks": train,
        "heldout_tasks": heldout,
        "seed_runs": seed_runs,
        "runs_per_iteration_max": per_iteration,
        "agent_runs_max": runs,
        "tokens_upper_bound": runs * max_tokens_per_run,
    }


def preflight(llm_spec: str) -> tuple[list[str], dict]:
    """Return (problems, info)."""
    kind, _, model = llm_spec.partition(":")
    if kind != "anthropic":
        return [f"a live run needs --llm anthropic:<model>, got {llm_spec!r}"], {}
    problems: list[str] = []
    if not load_api_key():
        problems.append(
            "no API key: set ANTHROPIC_API_KEY, or ANTHROPIC_API_KEY_FILE to a file holding it"
        )
    try:
        import anthropic
    except ImportError:
        problems.append(
            "the anthropic SDK is not installed: pip install -e '.[anthropic]'"
        )
    if problems:
        return problems, {}
    model = model or DEFAULT_MODEL
    meter = get_meter()
    run_id = meter.open_run(max_tokens=2_000, max_calls=1)
    try:
        client = anthropic.Anthropic(
            api_key="metered", base_url=meter.base_url(run_id), max_retries=0
        )
        reply = client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        text = "".join(getattr(b, "text", "") for b in reply.content).strip()
    except Exception as exc:
        meter.close_run(run_id)
        return [f"the test call through the meter failed: {exc}"], {}
    usage = meter.close_run(run_id)
    info = {
        "model": model,
        "reply": text,
        "metered_tokens": usage.tokens,
        "metered_calls": usage.calls,
        "process_hardened": meter.hardened,
    }
    if usage.calls != 1 or usage.tokens == 0:
        problems.append(f"the meter did not record the call as expected: {info}")
    return problems, info


def _load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def summarize(root: Path, planned: dict | None = None) -> str:
    root = Path(root)
    archive = Archive(root)
    agents = archive.all()
    usage = _load(root / "usage.json") or {}
    seed = agents[0] if agents else None
    children = [a for a in agents if a.parent_id]
    valid = [a for a in children if a.status == "valid"]
    improved = [a for a in valid if a.delta is not None and a.delta > 0]
    best = archive.best()

    solution_hard = solution_review = mismatches = 0
    genome_review = 0
    for agent in agents:
        base = archive.agent_dir(agent.id)
        if (base / "integrity.json").is_file():
            genome_review += 1
        for split in ("train", "heldout"):
            data = _load(base / f"results_{split}.json")
            for r in (data or {}).get("results", []):
                solution_hard += bool(r.get("integrity_flags"))
                reviews = r.get("review_flags") or []
                solution_review += bool(reviews)
                mismatches += any("meter" in x for x in reviews)

    def fmt(v):
        return "-" if v is None else f"{v:.3f}"

    lines = ["# Live run summary", ""]
    spent = usage.get("meta_tokens", 0) + usage.get("eval_tokens", 0)
    line = (
        f"Iterations completed: {usage.get('iterations', 0)}. Metered tokens: {spent:,} "
        f"(self-modification {usage.get('meta_tokens', 0):,}, evaluation {usage.get('eval_tokens', 0):,})."
    )
    if planned:
        line += f" Worst-case bound for this configuration: {planned['tokens_upper_bound']:,}."
    lines += [
        line,
        "",
        "| agent | parent | status | train | fitness | heldout | delta | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for a in agents:
        lines.append(
            f"| {a.id} | {a.parent_id or '-'} | {a.status} | {fmt(a.train_score)} | {fmt(a.fitness)} | "
            f"{fmt(a.heldout_score)} | {fmt(a.delta)} | {a.note[:60].replace('|', '/')} |"
        )
    lines += ["", "## What this run measured", ""]
    lines.append(
        f"- Children produced: {len(children)}; valid: {len(valid)}; invalid: {len(children) - len(valid)}."
    )
    lines.append(
        f"- Children with a higher training fitness than their parent: {len(improved)}."
    )
    if seed and best:
        lines.append(
            f"- Seed train/heldout: {fmt(seed.train_score)}/{fmt(seed.heldout_score)}; best agent {best.id}: "
            f"{fmt(best.train_score)}/{fmt(best.heldout_score)}."
        )
    lines.append(
        f"- Integrity: {solution_hard} task results with hard findings (scored zero in strict mode), "
        f"{solution_review} with review findings, {genome_review} genomes with findings, "
        f"{mismatches} runs where the genome's own token report differed from the meter."
    )
    lines += [
        "",
        "## How to read it",
        "",
        "A short run measures whether the loop works against a real model (valid-child rate, cost, whether "
        "the integrity layers fire) and gives a first look at direction. It does not show an improvement: the "
        "training split is small and noisy, and a gain needs the `experiment` command's comparison on the "
        "held-out and fresh splits, which only calls a result reliable with enough tasks.",
        "",
    ]
    return "\n".join(lines)
