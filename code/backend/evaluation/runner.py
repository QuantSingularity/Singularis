from __future__ import annotations

import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.core.meter import RunUsage, get_meter, worker_env
from backend.core.sandbox import ExecResult, SandboxConfig, run_command
from backend.core.text import clip
from backend.evaluation.evaluator import evaluate
from backend.evaluation.integrity import Findings, changed_python_files, scan_findings
from backend.evaluation.repo_eval import IGNORED
from backend.evaluation.tasks import Task

SRC_ROOT = Path(__file__).resolve().parents[2]

TASK_TEMPLATE = (
    "You are working in a project directory, which is your current directory. "
    "Use the provided tools to inspect and change files and to run Python. "
    "When you are done, call the finish tool.\n\nTask:\n{prompt}"
)


@dataclass(frozen=True)
class RunConfig:
    llm_spec: str
    max_steps: int = 30
    max_tokens: int = 400_000
    max_calls: int = 60
    wall_timeout_s: float = 600.0
    worker_memory_mb: int = 4096
    tool_sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    trials: int = 1
    integrity: str = "strict"


@dataclass
class TaskResult:
    task_id: str
    score: float
    passed: int
    total: int
    input_tokens: int
    output_tokens: int
    wall_s: float
    stop_reason: str
    error: str = ""
    trial: int = 0
    integrity_flags: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class SuiteResult:
    results: list[TaskResult]

    @property
    def mean_score(self) -> float:
        return (
            sum(r.score for r in self.results) / len(self.results)
            if self.results
            else 0.0
        )

    @property
    def pass_rate(self) -> float:
        return (
            sum(1 for r in self.results if r.score >= 1.0) / len(self.results)
            if self.results
            else 0.0
        )

    @property
    def mean_tokens(self) -> float:
        return (
            sum(r.tokens for r in self.results) / len(self.results)
            if self.results
            else 0.0
        )

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens for r in self.results)

    def by_task(self) -> dict[str, float]:
        """Mean score per task over its trials."""
        groups: dict[str, list[float]] = {}
        for r in self.results:
            groups.setdefault(r.task_id, []).append(r.score)
        return {task_id: sum(v) / len(v) for task_id, v in sorted(groups.items())}

    def to_dict(self) -> dict:
        return {
            "mean_score": self.mean_score,
            "pass_rate": self.pass_rate,
            "mean_tokens": self.mean_tokens,
            "total_tokens": self.total_tokens,
            "results": [asdict(r) for r in self.results],
        }


def fitness(mean_score: float, mean_tokens: float, token_cap: int) -> float:
    """Correctness first, with a small penalty for token cost so that efficiency can evolve."""
    return mean_score - 0.05 * min(1.0, mean_tokens / max(1, token_cap))


def absolute_llm_spec(spec: str) -> str:
    """Resolve a relative scripted model path against the current directory.

    Workers run inside the task workspace, so a relative path would point somewhere else there.
    """
    kind, _, arg = spec.partition(":")
    if kind == "scripted" and arg and not Path(arg).is_absolute():
        return f"scripted:{Path(arg).resolve()}"
    return spec


def _worker_env(
    cfg: RunConfig, run_env: dict[str, str] | None = None
) -> dict[str, str]:
    """Environment for a worker. It never contains the API key or a proxy: model traffic goes through the
    meter, which holds the key (see backend.core.meter)."""
    env = {"PYTHONPATH": str(SRC_ROOT)}
    if cfg.llm_spec.startswith("anthropic") and run_env:
        env.update(run_env)
    return env


def with_package_on_path(cfg: RunConfig) -> RunConfig:
    from dataclasses import replace

    env = {**cfg.tool_sandbox.env, "PYTHONPATH": str(SRC_ROOT)}
    return replace(cfg, tool_sandbox=replace(cfg.tool_sandbox, env=env))


def run_agent(
    genome_dir: Path,
    workspace: Path,
    prompt: str,
    cfg: RunConfig,
    out_dir: Path,
    label: str,
) -> tuple[dict, ExecResult]:
    """Run a genome's solve() in an isolated worker process and return its trace."""
    out_dir.mkdir(parents=True, exist_ok=True)
    task_file = out_dir / f"{label}.task.txt"
    trace_file = out_dir / f"{label}.trace.json"
    task_file.write_text(prompt)
    trace_file.unlink(missing_ok=True)
    argv = [
        sys.executable,
        "-m",
        "backend.core.worker",
        "--genome",
        str(genome_dir),
        "--workspace",
        str(workspace),
        "--task-file",
        str(task_file),
        "--out",
        str(trace_file),
        "--llm",
        absolute_llm_spec(cfg.llm_spec),
        "--sandbox-json",
        cfg.tool_sandbox.to_json(),
        "--max-steps",
        str(cfg.max_steps),
        "--max-tokens",
        str(cfg.max_tokens),
        "--max-calls",
        str(cfg.max_calls),
    ]
    meter, run_id = None, None
    run_env = None
    if cfg.llm_spec.startswith("anthropic"):
        meter = get_meter()
        run_id = meter.open_run(cfg.max_tokens, cfg.max_calls)
        run_env = worker_env(meter, run_id)
    sandbox = SandboxConfig(
        timeout_s=cfg.wall_timeout_s,
        memory_mb=cfg.worker_memory_mb,
        cpu_s=int(cfg.wall_timeout_s) + 30,
        env=_worker_env(cfg, run_env),
    )
    try:
        result = run_command(argv, Path(workspace), sandbox)
    finally:
        metered = meter.close_run(run_id) if meter and run_id else None
    trace = None
    if trace_file.is_file():
        try:
            trace = json.loads(trace_file.read_text())
        except json.JSONDecodeError:
            trace = None
    if trace is None:
        reason = "timeout" if result.timed_out else "worker_failure"
        trace = {
            "steps": [],
            "final_text": "",
            "finished": False,
            "stop_reason": reason,
            "input_tokens": 0,
            "output_tokens": 0,
            "wall_s": result.duration_s,
            "error": clip(result.stderr.strip(), 2000),
        }
    if metered is not None:
        apply_metered_usage(trace, metered)
    trace_file.write_text(json.dumps(trace))
    return trace, result


def apply_metered_usage(trace: dict, metered: RunUsage) -> None:
    """Replace the genome's self-reported token counts with the meter's. The originals are kept for audit."""
    reported = trace.get("input_tokens", 0) + trace.get("output_tokens", 0)
    trace["reported_tokens"] = reported
    trace["input_tokens"] = metered.input_tokens
    trace["output_tokens"] = metered.output_tokens
    trace["metered_calls"] = metered.calls
    trace["token_report_mismatch"] = reported != metered.tokens


def run_task(
    task: Task, genome_dir: Path, cfg: RunConfig, out_dir: Path, trial: int = 0
) -> TaskResult:
    label = task.id if trial == 0 else f"{task.id}__t{trial}"
    workspace = out_dir / "workspaces" / label
    if workspace.exists():
        shutil.rmtree(workspace)
    if task.kind == "repo":
        shutil.copytree(task.repo_dir, workspace, symlinks=True, ignore=IGNORED)
    else:
        workspace.mkdir(parents=True)
        for rel, content in task.files.items():
            path = workspace / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    trace, _ = run_agent(
        genome_dir,
        workspace,
        TASK_TEMPLATE.format(prompt=task.prompt),
        cfg,
        out_dir / "traces",
        label,
    )
    outcome = evaluate(task, workspace)
    passed, error = outcome.passed, outcome.error or trace.get("error", "")
    findings = Findings()
    if cfg.integrity != "off":
        if task.kind == "repo":
            findings = scan_findings(
                workspace,
                only=changed_python_files(workspace, Path(task.repo_dir)),
                relaxed=True,
            )
        else:
            findings = scan_findings(workspace)
    flags = list(findings.hard)
    if (
        outcome.tamper
    ):  # the evaluator caught the run attacking it; this is not a heuristic
        flags.append(f"evaluator: {outcome.tamper}")
        passed = 0
    if flags and (cfg.integrity == "strict" or outcome.tamper):
        passed = 0
        error = "integrity violation: " + "; ".join(flags)
    review = list(findings.review)
    if trace.get("token_report_mismatch"):
        review.append("genome: reported token usage differs from the meter")
    return TaskResult(
        task_id=task.id,
        score=passed / outcome.total if outcome.total else 0.0,
        passed=passed,
        total=outcome.total,
        input_tokens=trace.get("input_tokens", 0),
        output_tokens=trace.get("output_tokens", 0),
        wall_s=trace.get("wall_s", 0.0),
        stop_reason=trace.get("stop_reason", ""),
        error=clip(error, 500),
        trial=trial,
        integrity_flags=flags,
        review_flags=review,
    )


def run_suite(
    tasks: list[Task], genome_dir: Path, cfg: RunConfig, out_dir: Path, workers: int = 4
) -> SuiteResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(task, trial) for task in tasks for trial in range(max(1, cfg.trials))]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(
            pool.map(
                lambda job: run_task(job[0], genome_dir, cfg, out_dir, job[1]), jobs
            )
        )
    return SuiteResult(sorted(results, key=lambda r: (r.task_id, r.trial)))
