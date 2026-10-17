from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from ai_models.llm import DEFAULT_MODEL
from backend.core.isolation import run_isolation_checks
from backend.core.logging_config import setup_logging
from backend.core.sandbox import SandboxConfig
from backend.evaluation.evaluator import validate_tasks
from backend.evaluation.runner import RunConfig, run_suite
from backend.evaluation.suite import BUILTIN_TASKS
from backend.evaluation.tasks import load_tasks_from_dir, select_tasks
from backend.evolution.archive import Archive
from backend.evolution.evolve import BUILTIN_GENOME, EvolveConfig, Evolver, diff_genomes
from backend.evolution.experiment import ExperimentConfig, run_experiment
from backend.evolution.report import write_report
from backend.evolution.serve import serve as serve_report
from backend.evolution.signing import verify_all


def _add_run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--llm",
        default=f"anthropic:{DEFAULT_MODEL}",
        help="anthropic:<model> or scripted:<path>",
    )
    p.add_argument("--max-steps", type=int, default=30)
    p.add_argument(
        "--max-tokens", type=int, default=400_000, help="token budget per task"
    )
    p.add_argument(
        "--timeout", type=float, default=600.0, help="wall clock seconds per task"
    )
    p.add_argument("--workers", type=int, default=4)
    p.add_argument(
        "--tasks-dir",
        type=Path,
        help="load tasks from a directory instead of the builtin suite",
    )
    p.add_argument(
        "--integrity",
        choices=["strict", "warn", "off"],
        default="strict",
        help="scan agent code for evaluator tampering",
    )


def _run_config(args, llm: str | None = None) -> RunConfig:
    return RunConfig(
        llm_spec=llm or args.llm,
        max_steps=args.max_steps,
        max_tokens=args.max_tokens,
        wall_timeout_s=args.timeout,
        tool_sandbox=SandboxConfig(),
        trials=getattr(args, "trials", 1),
        integrity=args.integrity,
    )


def _tasks(args):
    return (
        load_tasks_from_dir(args.tasks_dir) if args.tasks_dir else list(BUILTIN_TASKS)
    )


def cmd_suite(args) -> int:
    for t in _tasks(args):
        print(f"{t.id:<18} {t.split}")
    return 0


def cmd_validate_suite(args) -> int:
    problems = validate_tasks(_tasks(args))
    for p in problems:
        print("PROBLEM:", p)
    print("suite ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_eval(args) -> int:
    tasks = select_tasks(
        _tasks(args), args.split, args.only.split(",") if args.only else None
    )
    genome = args.genome or BUILTIN_GENOME
    result = run_suite(tasks, Path(genome), _run_config(args), args.out, args.workers)
    for r in result.results:
        print(
            f"{r.task_id:<18} {r.score:.2f}  {r.passed}/{r.total}  tokens={r.tokens}  {r.stop_reason}"
        )
    print(
        f"mean score {result.mean_score:.3f}  pass rate {result.pass_rate:.2f}  mean tokens {result.mean_tokens:.0f}"
    )
    return 0


def cmd_evolve(args) -> int:
    config = EvolveConfig(
        eval_run=_run_config(args),
        meta_run=_run_config(args, args.meta_llm),
        iterations=args.iterations,
        workers=args.workers,
        seed=args.seed,
        selection=args.selection,
        meta_evolve_every=args.meta_evolve_every,
    )
    Evolver(
        args.root, _tasks(args), config, log=logging.getLogger("singularis").info
    ).run()
    return cmd_lineage(args)


def cmd_lineage(args) -> int:
    archive = Archive(args.root)
    print(
        f"{'id':<7}{'parent':<8}{'gen':<4}{'status':<9}{'train':<7}{'fitness':<9}{'heldout':<8}note"
    )
    for a in archive.all():
        fmt = lambda v: "-" if v is None else f"{v:.3f}"
        print(
            f"{a.id:<7}{a.parent_id or '-':<8}{a.generation:<4}{a.status:<9}"
            f"{fmt(a.train_score):<7}{fmt(a.fitness):<9}{fmt(a.heldout_score):<8}{a.note[:60]!r}"
        )
    best = archive.best()
    if best:
        print(f"\nbest by fitness: {best.id}")
    return 0


def cmd_export(args) -> int:
    archive = Archive(args.root)
    record = archive.get(args.agent)
    genome = archive.genome_dir(record.id)
    patch = diff_genomes(BUILTIN_GENOME, genome)
    print(patch or "(identical to the seed genome)")
    dest = Path(args.dest)
    if dest.exists() and any(dest.iterdir()):
        print(f"destination is not empty: {dest}", file=sys.stderr)
        return 1
    if (
        not args.yes
        and input(f"Copy {record.id} to {dest}? [y/N] ").strip().lower() != "y"
    ):
        return 1
    shutil.copytree(
        genome, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
    )
    print(f"exported {record.id} to {dest}")
    return 0


def cmd_experiment(args) -> int:
    from dataclasses import replace

    eval_run = replace(_run_config(args), trials=1)
    meta_run = replace(_run_config(args, args.meta_llm), trials=1)
    config = ExperimentConfig(
        arms=tuple(a for a in args.arms.split(",") if a),
        iterations=args.iterations,
        trials=args.trials,
        meta_evolve_every=args.meta_evolve_every,
        workers=args.workers,
        seed=args.seed,
    )
    run_experiment(
        args.root,
        _tasks(args),
        eval_run,
        meta_run,
        config,
        log=logging.getLogger("singularis").info,
    )
    print((Path(args.root) / "EXPERIMENT.md").read_text())
    return 0


def cmd_serve(args) -> int:
    serve_report(args.root, args.host, args.port, args.allow_remote)
    return 0


def cmd_verify(args) -> int:
    archive = Archive(args.root)
    failed = 0
    for agent_id, problems in verify_all(args.root, archive).items():
        if problems:
            failed += 1
            print(f"FAIL {agent_id}: " + "; ".join(problems))
        else:
            print(f"ok   {agent_id}")
    print(
        "all records verified"
        if not failed
        else f"{failed} record(s) failed verification"
    )
    return 1 if failed else 0


def cmd_isolation_check(args) -> int:
    import os

    proxy = args.proxy or os.environ.get("HTTPS_PROXY")
    checks = run_isolation_checks(
        proxy, args.runs, container=not args.skip_container_checks
    )
    for check in checks:
        print(f"{'ok  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
    failed = [c for c in checks if not c.ok]
    print(
        "isolation verified"
        if not failed
        else f"{len(failed)} isolation check(s) failed"
    )
    return 1 if failed else 0


def cmd_swebench_prepare(args) -> int:
    from backend.evaluation.swebench import (
        SwebenchError,
        load_instances,
        prepare_instance,
    )

    instances = load_instances(args.dataset)
    if args.repos:
        wanted = set(args.repos.split(","))
        instances = [i for i in instances if i.get("repo") in wanted]
    if args.limit:
        instances = instances[: args.limit]
    failures = 0
    for instance in instances:
        try:
            path = prepare_instance(
                instance,
                args.out,
                args.cache,
                python=args.python,
                repo_source=args.repo_source,
                split=args.split,
                test_timeout_s=args.test_timeout,
            )
            print(f"prepared {instance['instance_id']} -> {path}")
        except (SwebenchError, KeyError, OSError) as exc:
            failures += 1
            print(f"FAILED {instance.get('instance_id', '?')}: {exc}", file=sys.stderr)
    print(
        f"{len(instances) - failures} prepared, {failures} failed. Next: singularis validate-suite --tasks-dir {args.out}"
    )
    return 1 if failures else 0


def cmd_report(args) -> int:
    out = args.out or Path(args.root) / "report.json"
    path = write_report(args.root, out)
    print(f"wrote {path}")
    print("open frontend/index.html in a browser and load this file")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="singularis", description="Self-improving agent research framework"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("suite", help="list tasks")
    p.add_argument("--tasks-dir", type=Path)
    p.set_defaults(func=cmd_suite)

    p = sub.add_parser(
        "validate-suite", help="check that starters fail and reference solutions pass"
    )
    p.add_argument("--tasks-dir", type=Path)
    p.set_defaults(func=cmd_validate_suite)

    p = sub.add_parser("eval", help="evaluate a genome on a task split")
    _add_run_args(p)
    p.add_argument(
        "--genome", type=Path, help="genome directory (default: the seed genome)"
    )
    p.add_argument("--split", choices=["train", "heldout", "fresh"])
    p.add_argument("--trials", type=int, default=1, help="repetitions per task")
    p.add_argument("--only", help="comma separated task ids")
    p.add_argument("--out", type=Path, default=Path("runs/eval"))
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser(
        "evolve", help="run the recursive self-improvement loop (resumable)"
    )
    _add_run_args(p)
    p.add_argument(
        "--meta-llm", help="model used for self-modification (default: same as --llm)"
    )
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--selection", choices=["open_ended", "greedy"], default="open_ended"
    )
    p.add_argument(
        "--meta-evolve-every",
        type=int,
        default=0,
        help="evolve the meta prompt every N iterations (0 = off)",
    )
    p.set_defaults(func=cmd_evolve)

    p = sub.add_parser(
        "experiment",
        help="compare evolution arms against the seed with confidence intervals",
    )
    _add_run_args(p)
    p.add_argument(
        "--meta-llm", help="model used for self-modification (default: same as --llm)"
    )
    p.add_argument("--root", type=Path, default=Path("runs/experiment"))
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument(
        "--trials", type=int, default=3, help="final evaluation repetitions per task"
    )
    p.add_argument(
        "--arms",
        default="open_ended,greedy",
        help="comma separated selection strategies",
    )
    p.add_argument("--meta-evolve-every", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_experiment)

    p = sub.add_parser("serve", help="live lineage dashboard on localhost")
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow binding a non-loopback address",
    )
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "isolation-check",
        help="verify the container stack: proxy allowlist, no direct egress, hardening",
    )
    p.add_argument("--proxy", help="proxy url (default: $HTTPS_PROXY)")
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument(
        "--skip-container-checks",
        action="store_true",
        help="skip read-only root, uid, capability checks",
    )
    p.set_defaults(func=cmd_isolation_check)

    p = sub.add_parser(
        "verify", help="check signed records: genome hashes, scores, result files"
    )
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("lineage", help="show the archive")
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.set_defaults(func=cmd_lineage)

    p = sub.add_parser("swebench", help="SWE-bench style repository tasks")
    swe = p.add_subparsers(dest="swebench_command", required=True)
    q = swe.add_parser("prepare", help="turn a dataset file into task directories")
    q.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="SWE-bench JSONL (or JSON array) file",
    )
    q.add_argument("--out", type=Path, required=True)
    q.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "singularis")
    q.add_argument(
        "--repo-source",
        default="https://github.com/{repo}.git",
        help="clone url template",
    )
    q.add_argument(
        "--python",
        default="",
        help="interpreter with the repositories' dependencies and pytest installed",
    )
    q.add_argument("--limit", type=int, default=0)
    q.add_argument("--repos", default="", help="comma separated owner/name filter")
    q.add_argument(
        "--split", choices=["auto", "train", "heldout", "fresh"], default="auto"
    )
    q.add_argument("--test-timeout", type=float, default=900)
    q.set_defaults(func=cmd_swebench_prepare)

    p = sub.add_parser(
        "report", help="write report.json for the frontend lineage viewer"
    )
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.add_argument("--out", type=Path)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "export", help="copy an evolved genome out after reviewing its diff"
    )
    p.add_argument("--root", type=Path, default=Path("runs/exp"))
    p.add_argument("--agent", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
