from __future__ import annotations

import difflib
import json
import random
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai_models import genome as _genome_pkg
from backend.core.sandbox import SandboxConfig, run_command
from backend.core.text import clip
from backend.evaluation.runner import (
    SRC_ROOT,
    RunConfig,
    fitness,
    run_agent,
    run_suite,
    with_package_on_path,
)
from backend.evaluation.tasks import Task
from backend.evolution.archive import SELECTIONS, AgentRecord, Archive
from backend.evolution.manifest import write_manifest
from backend.evolution.meta import INVALID_REWARD, MetaPromptStore
from backend.evolution.signing import sign_agent

BUILTIN_GENOME = Path(_genome_pkg.__file__).resolve().parent
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json"}

FOCI = (
    "prompts",
    "tools",
    "loop",
    "context_management",
    "efficiency",
    "error_recovery",
)
FOCUS_TEXT = {
    "prompts": "improve the system prompt in genome/prompts.py",
    "tools": "add or improve a tool in genome/tools.py",
    "loop": "improve the control flow in genome/agent.py",
    "context_management": "keep the conversation compact and relevant as it grows",
    "efficiency": "reach the same correct results with fewer steps and tokens",
    "error_recovery": "detect failures earlier and recover from them more reliably",
}

META_PROMPT = """You are improving the source code of an autonomous coding agent. That agent is you: the code \
you are running on is the Python package in ./genome (the project directory you are in).

Interface contract, which you must not break:
- genome/__init__.py exports solve(task, workspace, llm, sandbox, max_steps=30) and returns an \
backend.core.trace.RunTrace.
- Use relative imports inside the genome. The genome may import from ai_models.llm, backend.core.sandbox, \
backend.core.text and backend.core.trace.
- Only files inside ./genome are kept. Do not add dependencies beyond the standard library.
- Never try to read, modify, or influence tests, evaluators, budgets, or anything outside ./genome. Code that \
does is detected and scored zero.

Files: genome/prompts.py (system prompt), genome/tools.py (tools), genome/agent.py (main loop).

Focus for this change: {focus}

Latest evaluation of the current version (parent {parent}):
{digest}

Make ONE focused improvement that addresses what you see above and fits the focus. Do not rewrite everything. \
After editing, verify the package still imports by calling run_python with args \
["-c", "import genome; print(genome.solve)"]. Then call finish with a one or two sentence description of the \
change."""

META_META_PROMPT = """You maintain the instruction template that is used to ask an autonomous coding agent to \
modify its own source code. The current template is in ./meta_prompt.md. Statistics on how each template \
version performed (mean change in fitness of the child relative to its parent, higher is better) are in \
./variant_stats.md.

Improve the template with ONE focused change that you expect to raise the mean fitness gain: clearer \
instructions, a better order of steps, stronger guidance on verification, or better use of the evaluation digest.

Hard requirements:
- Keep the three placeholders {parent}, {digest} and {focus} exactly as written, each at least once.
- Any other curly brace must be doubled (write {{ and }}) because the file is rendered with str.format.
- Keep the instruction that the agent must not break the solve() interface. Keep the file under 6000 characters.
- Do not instruct the agent to touch evaluation, budgets, tests, or anything outside ./genome.
Edit ./meta_prompt.md in place. When finished, call finish with a short description of the change."""

VALIDATE_CODE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from backend.core.loader import check_contract, load_genome\n"
    "for p in Path(sys.argv[1]).rglob('*.py'):\n"
    "    compile(p.read_text(), str(p), 'exec')\n"
    "check_contract(load_genome(Path(sys.argv[1])))\n"
    "print('ok')\n"
)

TERMINAL_STOPS = {
    "budget",
    "timeout",
    "max_steps",
    "llm_error",
    "genome_error",
    "worker_failure",
    "no_tool_calls",
}


@dataclass
class EvolveConfig:
    eval_run: RunConfig
    meta_run: RunConfig
    iterations: int = 5
    workers: int = 4
    seed: int = 0
    selection: str = "open_ended"
    meta_evolve_every: int = 0
    max_genome_bytes: int = 200_000
    max_genome_files: int = 30


def check_genome_files(genome: Path, max_bytes: int, max_files: int) -> str | None:
    files = [p for p in genome.rglob("*") if p.is_file() or p.is_symlink()]
    files = [p for p in files if "__pycache__" not in p.parts]
    if not (genome / "__init__.py").is_file():
        return "missing __init__.py"
    if len(files) > max_files:
        return f"too many files ({len(files)})"
    total = 0
    for p in files:
        if p.is_symlink():
            return f"symlink not allowed: {p.name}"
        if p.suffix not in ALLOWED_SUFFIXES:
            return f"file type not allowed: {p.name}"
        total += p.stat().st_size
    if total > max_bytes:
        return f"genome too large ({total} bytes)"
    return None


def validate_genome(genome: Path) -> str | None:
    config = SandboxConfig(
        timeout_s=30, memory_mb=1024, cpu_s=40, env={"PYTHONPATH": str(SRC_ROOT)}
    )
    result = run_command(
        [sys.executable, "-c", VALIDATE_CODE, str(genome)], genome.parent, config
    )
    if result.returncode == 0 and "ok" in result.stdout:
        return None
    reason = "timed out" if result.timed_out else clip(result.stderr.strip(), 800)
    return f"validation failed: {reason}"


def _genome_files(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(errors="replace")
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def diff_genomes(parent: Path, child: Path) -> str:
    before, after = _genome_files(parent), _genome_files(child)
    chunks = []
    for name in sorted(set(before) | set(after)):
        diff = difflib.unified_diff(
            before.get(name, "").splitlines(keepends=True),
            after.get(name, "").splitlines(keepends=True),
            fromfile=f"parent/{name}",
            tofile=f"child/{name}",
        )
        chunks.append("".join(diff))
    return "".join(chunks)


def failure_class(result: dict) -> str:
    if result.get("integrity_flags"):
        return "integrity_violation"
    if result["stop_reason"] in TERMINAL_STOPS:
        return result["stop_reason"]
    return "wrong_answer" if result["score"] == 0 else "partial_credit"


def cluster_failures(results: list[dict]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if result["score"] < 1.0:
            groups[failure_class(result)].append(result["task_id"])
    return sorted(
        ((label, ids) for label, ids in groups.items()),
        key=lambda item: (-len(item[1]), item[0]),
    )


def _trace_label(result: dict) -> str:
    trial = result.get("trial", 0)
    return result["task_id"] if trial == 0 else f"{result['task_id']}__t{trial}"


def _digest_result(result: dict, trace: dict) -> str:
    lines = [
        f"Task {result['task_id']}: score {result['score']:.2f} ({result['passed']}/{result['total']} tests), "
        f"class={failure_class(result)}, stop_reason={result['stop_reason']}, "
        f"steps={len(trace.get('steps', []))}, tokens={result['input_tokens'] + result['output_tokens']}"
    ]
    if result.get("error"):
        lines.append(f"  error: {clip(result['error'], 300)}")
    recent = [c for s in trace.get("steps", []) for c in s.get("calls", [])][-4:]
    for call in recent:
        lines.append(
            f"  - {call['name']} {json.dumps(call['arguments'])[:160]} -> {clip(call['output'], 240)!r}"
        )
    if trace.get("final_text"):
        lines.append(f"  final message: {clip(trace['final_text'], 300)}")
    return "\n".join(lines)


class Evolver:
    def __init__(
        self,
        root: Path,
        tasks: list[Task],
        config: EvolveConfig,
        log: Callable[[str], None] = print,
    ):
        if config.selection not in SELECTIONS:
            raise ValueError(f"selection must be one of {SELECTIONS}")
        self.root = Path(root)
        self.archive = Archive(self.root)
        self.tasks = tasks
        self.config = config
        self.log = log
        self.rng = random.Random(config.seed)
        self.meta_run = with_package_on_path(config.meta_run)
        self.meta_store = MetaPromptStore(self.root, META_PROMPT)
        self.usage = self._load_usage()
        for warning in write_manifest(self.root, config, tasks):
            self.log(warning)

    def _load_usage(self) -> dict:
        path = self.root / "usage.json"
        if path.is_file():
            return json.loads(path.read_text())
        return {"meta_tokens": 0, "eval_tokens": 0, "iterations": 0}

    def _save_usage(self) -> None:
        (self.root / "usage.json").write_text(json.dumps(self.usage, indent=2))

    def _split(self, name: str) -> list[Task]:
        return [t for t in self.tasks if t.split == name]

    def _evaluate_split(self, agent_id: str, split: str):
        suite = run_suite(
            self._split(split),
            self.archive.genome_dir(agent_id),
            self.config.eval_run,
            self.archive.agent_dir(agent_id) / split,
            self.config.workers,
        )
        (self.archive.agent_dir(agent_id) / f"results_{split}.json").write_text(
            json.dumps(suite.to_dict(), indent=2)
        )
        self.usage["eval_tokens"] += suite.total_tokens
        return suite

    def _evaluate_train(self, agent_id: str) -> None:
        suite = self._evaluate_split(agent_id, "train")
        self.archive.update(
            agent_id,
            train_score=suite.mean_score,
            train_tokens=suite.mean_tokens,
            fitness=fitness(
                suite.mean_score, suite.mean_tokens, self.config.eval_run.max_tokens
            ),
        )
        sign_agent(self.root, self.archive, agent_id)

    def _evaluate_heldout(self, agent_id: str) -> None:
        if not self._split("heldout"):
            return
        suite = self._evaluate_split(agent_id, "heldout")
        self.archive.update(agent_id, heldout_score=suite.mean_score)
        sign_agent(self.root, self.archive, agent_id)

    def bootstrap(self) -> None:
        if self.archive.count() > 0:
            return
        agent_id = self.archive.new_id()
        shutil.copytree(
            BUILTIN_GENOME,
            self.archive.genome_dir(agent_id),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        self.archive.add(agent_id, None, 0, "valid", "seed genome")
        self.log(f"[{agent_id}] evaluating seed genome")
        self._evaluate_train(agent_id)
        self._evaluate_heldout(agent_id)
        self._save_usage()

    def _failure_digest(self, parent: AgentRecord) -> str:
        base = self.archive.agent_dir(parent.id)
        results_path = base / "results_train.json"
        if not results_path.is_file():
            return "(no evaluation data available)"
        data = json.loads(results_path.read_text())
        results = data["results"]
        failing = sorted(
            (r for r in results if r["score"] < 1.0), key=lambda r: r["score"]
        )
        if not failing:
            return (
                f"All training tasks passed. Mean tokens per task: {data['mean_tokens']:.0f}. "
                "Improve efficiency (fewer steps and tokens) or robustness without reducing correctness."
            )
        clusters = "; ".join(
            f"{label} x{len(ids)} ({', '.join(sorted(set(ids)))})"
            for label, ids in cluster_failures(results)
        )
        parts = [f"Failure classes: {clusters}"]
        for result in failing[:4]:
            trace_path = (
                base / "train" / "traces" / f"{_trace_label(result)}.trace.json"
            )
            trace = json.loads(trace_path.read_text()) if trace_path.is_file() else {}
            parts.append(_digest_result(result, trace))
        return clip("\n\n".join(parts), 8000)

    def _evolve_meta_prompt(self) -> str:
        best = self.archive.best()
        if best is None:
            return "no evaluated agent available"
        index = self.meta_store.count()
        work = self.root / "work" / f"meta_{index}"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        (work / "meta_prompt.md").write_text(
            self.meta_store.template(self.meta_store.best())
        )
        (work / "variant_stats.md").write_text(self.meta_store.summary_text())
        trace, _ = run_agent(
            self.archive.genome_dir(best.id),
            work,
            META_META_PROMPT,
            self.meta_run,
            self.root / "meta" / f"meta_{index}",
            "meta",
        )
        self.usage["meta_tokens"] += trace.get("input_tokens", 0) + trace.get(
            "output_tokens", 0
        )
        candidate = work / "meta_prompt.md"
        variant_id, reason = (
            self.meta_store.add_variant(candidate.read_text())
            if candidate.is_file()
            else (None, "file missing")
        )
        message = (
            f"meta prompt variant {variant_id} added"
            if variant_id
            else f"meta prompt change rejected: {reason}"
        )
        self.log(message)
        return message

    def step(self) -> dict:
        cfg = self.config
        parent = self.archive.select_parent(self.rng, cfg.selection)
        child_id = self.archive.new_id()
        generation = parent.generation + 1
        focus = FOCI[self.archive.count() % len(FOCI)]
        variant_id, template = self.meta_store.choose()
        work = self.root / "work" / child_id
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        shutil.copytree(
            self.archive.genome_dir(parent.id),
            work / "genome",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        prompt = template.format(
            parent=parent.id,
            digest=self._failure_digest(parent),
            focus=f"{focus}: {FOCUS_TEXT[focus]}",
        )
        self.log(
            f"[{child_id}] parent {parent.id} (fitness {parent.fitness:.3f}), focus {focus}, prompt {variant_id}"
        )
        trace, _ = run_agent(
            self.archive.genome_dir(parent.id),
            work,
            prompt,
            self.meta_run,
            self.root / "meta" / child_id,
            "meta",
        )
        self.usage["meta_tokens"] += trace.get("input_tokens", 0) + trace.get(
            "output_tokens", 0
        )
        note = clip(trace.get("final_text", "") or trace.get("error", ""), 500)
        report = {
            "agent": child_id,
            "parent": parent.id,
            "status": "valid",
            "note": note,
            "focus": focus,
            "variant": variant_id,
        }

        candidate = work / "genome"
        problem = None
        if not candidate.is_dir():
            problem = "genome directory missing after self-modification"
        else:
            problem = check_genome_files(
                candidate, cfg.max_genome_bytes, cfg.max_genome_files
            )
        if problem is None:
            problem = validate_genome(candidate)
        if problem is not None:
            self.archive.add(
                child_id, parent.id, generation, "invalid", problem, focus, variant_id
            )
            self.archive.update(child_id, delta=INVALID_REWARD)
            self.meta_store.record(variant_id, INVALID_REWARD)
            report.update(status="invalid", note=problem)
            self.log(f"[{child_id}] rejected: {problem}")
            return self._finish_step(report)

        shutil.copytree(
            candidate,
            self.archive.genome_dir(child_id),
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        patch = diff_genomes(
            self.archive.genome_dir(parent.id), self.archive.genome_dir(child_id)
        )
        (self.archive.agent_dir(child_id) / "diff.patch").write_text(patch)
        self.archive.add(
            child_id, parent.id, generation, "valid", note, focus, variant_id
        )
        self._evaluate_train(child_id)
        child = self.archive.get(child_id)
        delta = child.fitness - parent.fitness
        self.archive.update(child_id, delta=delta)
        self.meta_store.record(variant_id, delta)
        promising = delta >= 0
        if promising:
            self._evaluate_heldout(child_id)
        child = self.archive.get(child_id)
        report.update(
            train_score=child.train_score,
            fitness=child.fitness,
            heldout_score=child.heldout_score,
            parent_fitness=parent.fitness,
            delta=delta,
            promising=promising,
        )
        self.log(
            f"[{child_id}] train {child.train_score:.3f} fitness {child.fitness:.3f} "
            f"(delta {delta:+.3f}) heldout {child.heldout_score}"
        )
        return self._finish_step(report)

    def _finish_step(self, report: dict) -> dict:
        self.usage["iterations"] += 1
        every = self.config.meta_evolve_every
        if every and self.usage["iterations"] % every == 0:
            report["meta_prompt"] = self._evolve_meta_prompt()
        self._save_usage()
        return report

    def run(self) -> list[dict]:
        self.bootstrap()
        return [self.step() for _ in range(self.config.iterations)]
