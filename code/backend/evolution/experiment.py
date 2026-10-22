from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from backend.evaluation.runner import RunConfig, SuiteResult, run_suite
from backend.evaluation.stats import bootstrap_ci, mean, paired_bootstrap
from backend.evaluation.tasks import Task
from backend.evolution.archive import SELECTIONS
from backend.evolution.evolve import BUILTIN_GENOME, EvolveConfig, Evolver

FINAL_SPLITS = ("heldout", "fresh")


@dataclass
class ExperimentConfig:
    arms: tuple[str, ...] = ("open_ended", "greedy")
    iterations: int = 5
    trials: int = 3
    train_trials: int = 2
    meta_evolve_every: int = 0
    workers: int = 4
    seed: int = 0


def _summarize(suite: SuiteResult, tasks: list[Task]) -> dict:
    per_task = suite.by_task()
    scores = [per_task[t.id] for t in tasks if t.id in per_task]
    low, high = bootstrap_ci(scores)
    by_track = {}
    for track in sorted({t.track for t in tasks}):
        track_scores = [
            per_task[t.id] for t in tasks if t.track == track and t.id in per_task
        ]
        by_track[track] = mean(track_scores)
    return {
        "mean": mean(scores),
        "ci_low": low,
        "ci_high": high,
        "n_tasks": len(scores),
        "mean_tokens": suite.mean_tokens,
        "by_track": by_track,
        "per_task": per_task,
    }


def _final_eval(
    genome: Path, tasks: list[Task], cfg: RunConfig, out: Path, workers: int
) -> dict:
    final = {}
    for split in FINAL_SPLITS:
        split_tasks = [t for t in tasks if t.split == split]
        if not split_tasks:
            continue
        suite = run_suite(split_tasks, genome, cfg, out / split, workers)
        final[split] = _summarize(suite, split_tasks)
    return final


def _compare(arm_final: dict, seed_final: dict, tasks: list[Task]) -> dict:
    comparison = {}
    for split, summary in arm_final.items():
        ids = sorted(summary["per_task"])
        comparison[split] = paired_bootstrap(
            [summary["per_task"][i] for i in ids],
            [seed_final[split]["per_task"][i] for i in ids],
        )
    return comparison


def run_experiment(
    root: Path,
    tasks: list[Task],
    eval_run: RunConfig,
    meta_run: RunConfig,
    cfg: ExperimentConfig,
    log: Callable[[str], None] = print,
) -> dict:
    unknown = [a for a in cfg.arms if a not in SELECTIONS]
    if unknown:
        raise ValueError(f"unknown arms: {unknown}")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    final_cfg = replace(eval_run, trials=cfg.trials)

    log("evaluating the seed genome (control)")
    seed_final = _final_eval(
        BUILTIN_GENOME, tasks, final_cfg, root / "seed", cfg.workers
    )
    report: dict = {
        "config": {
            "arms": list(cfg.arms),
            "iterations": cfg.iterations,
            "trials": cfg.trials,
        },
        "seed": seed_final,
        "arms": {},
    }

    for arm in cfg.arms:
        log(f"arm: {arm}")
        evolver = Evolver(
            root / arm,
            tasks,
            EvolveConfig(
                eval_run=eval_run,
                meta_run=meta_run,
                iterations=cfg.iterations,
                workers=cfg.workers,
                seed=cfg.seed,
                train_trials=cfg.train_trials,
                selection=arm,
                meta_evolve_every=cfg.meta_evolve_every,
            ),
            log=log,
        )
        evolver.run()
        best = evolver.archive.best()
        if best is None:
            raise RuntimeError(f"arm {arm} produced no valid agent")
        final = _final_eval(
            evolver.archive.genome_dir(best.id),
            tasks,
            final_cfg,
            root / arm / "final",
            cfg.workers,
        )
        report["arms"][arm] = {
            "best_agent": best.id,
            "generation": best.generation,
            "train_fitness": best.fitness,
            "usage": evolver.usage,
            "final": final,
            "vs_seed": _compare(final, seed_final, tasks),
        }

    (root / "experiment.json").write_text(json.dumps(report, indent=2))
    (root / "EXPERIMENT.md").write_text(render_markdown(report))
    return report


def render_markdown(report: dict) -> str:
    def cell(summary: dict) -> str:
        return (
            f"{summary['mean']:.3f} [{summary['ci_low']:.3f}, {summary['ci_high']:.3f}]"
        )

    cfg = report["config"]
    lines = [
        "# Experiment report",
        "",
        f"Arms: {', '.join(cfg['arms'])}. Iterations per arm: {cfg['iterations']}. Final trials per task: {cfg['trials']}.",
        "Scores are means over tasks with 95% bootstrap confidence intervals in brackets.",
        "",
    ]
    splits = [s for s in FINAL_SPLITS if s in report["seed"]]
    header = (
        "| Condition | Best agent | " + " | ".join(splits) + " | Tokens (meta + eval) |"
    )
    lines += [header, "|" + "---|" * (len(splits) + 3)]
    lines.append(
        "| seed (control) | a0000 | "
        + " | ".join(cell(report["seed"][s]) for s in splits)
        + " | 0 |"
    )
    for arm, data in report["arms"].items():
        usage = data["usage"]
        row = f"| {arm} | {data['best_agent']} | " + " | ".join(
            cell(data["final"][s]) for s in splits
        )
        lines.append(row + f" | {usage['meta_tokens'] + usage['eval_tokens']} |")
    lines += [
        "",
        "## Change relative to the seed (paired bootstrap interval and exact sign-flip test over tasks)",
        "",
    ]
    any_significant = False
    for arm, data in report["arms"].items():
        for split, comparison in data["vs_seed"].items():
            if comparison["significant"]:
                verdict = "reliable"
            elif comparison.get("underpowered"):
                verdict = "underpowered: too few tasks to call"
            else:
                verdict = "not distinguishable from zero"
            any_significant = any_significant or comparison["significant"]
            lines.append(
                f"- {arm}, {split}: {comparison['mean_diff']:+.3f} [{comparison['ci_low']:+.3f}, "
                f"{comparison['ci_high']:+.3f}] p={comparison.get('p_value', float('nan')):.3f} "
                f"over {comparison['n']} tasks ({verdict})"
            )
    lines += ["", "## Reading these results", ""]
    lines.append(
        "At least one comparison passes both the interval and the permutation test. Check that the gain holds on the fresh split, repeat with more seeds, "
        "and read the diffs before drawing conclusions."
        if any_significant
        else "No comparison is reliable. With few tasks the intervals are wide, so this does not show that "
        "self-modification fails, only that this run cannot tell it apart from the seed."
    )
    return "\n".join(lines) + "\n"
