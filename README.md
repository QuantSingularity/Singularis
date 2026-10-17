# Singularis

A research framework for **recursive self-improvement of coding agents**. An agent evaluates itself on a
benchmark, diagnoses its own failures, rewrites its own source code, and keeps the rewrite only if a frozen
evaluator says it got better. The improved agent then performs the next round of self-modification.

The foundation model stays fixed. What evolves is the agent around it: its prompts, tools, loop logic, and
memory strategy (called the **genome**). This follows the line of work behind the Darwin Godel Machine, STOP,
Voyager, and AlphaEvolve, with the engineering needed to run it reproducibly and safely.

## Repository layout

```
singularis/
  LICENSE
  README.md
  pytest.ini
  pyproject.toml
  code/
    README.md
    conftest.py              shared pytest fixtures
    testkit.py               shared test helpers (scripted models, ready-made evolver)
    logs/                    runtime logs (singularis.log)
    ai_models/               everything that talks to or is a model
      llm.py                   provider interface, Anthropic client, scripted client, budgets
      genome/                  the mutable agent: prompts.py, tools.py, agent.py
      tests/
    backend/                 the frozen engine
      core/                    sandbox, worker, loader, trace, text, logging
      evaluation/              frozen evaluator, 20 benchmark tasks, SWE-bench adapter, runner, stats, integrity
      evolution/               archive, self-modification loop, meta prompts, experiment protocol,
                               signed records, manifest, report export, live server
      cli.py                   the `singularis` command
      tests/
  docs/                      architecture, safety, roadmap
  frontend/                  static lineage viewer (open index.html, load report.json)
  infrastructure/            Dockerfile, compose stack with egress allowlist proxy
  scripts/                   setup, tests, baseline, evolution, docker, report helpers
```

## How the loop works

```
            frozen (agent cannot touch)                    mutable
  +----------------------------------------------+   +-----------------+
  | evaluator + hidden tests | budgets | sandbox |   |  ai_models/     |
  | archive | selection | validation | worker    |   |    genome/      |
  +----------------------------------------------+   +--------+--------+
                      |                                        |
                      v                                        v
   select parent --> meta task: "improve ./genome" --> candidate child genome
        ^             (run by the PARENT genome itself)          |
        |                                                        v
        +--- archive child <--- evaluate on train/heldout <--- validate
```

1. **Select** a parent from the archive: `open_ended` (fitness weighted, with a bonus for under-explored
   branches) or `greedy` (always the fittest, used as a control arm).
2. **Diagnose**: the parent's failing traces are clustered into failure classes (wrong answer, budget, timeout,
   integrity violation, and so on) and summarized into a digest.
3. **Modify**: the parent genome runs a meta task whose workspace is a copy of its own source. The task names a
   rotating focus (prompts, tools, loop, context management, efficiency, error recovery) and uses the currently
   selected meta prompt variant.
4. **Validate**: file policy, compile check, import check, interface contract check, in a subprocess.
5. **Evaluate**: train split first, with an integrity scan of everything the agent wrote. Only candidates that
   match or beat the parent are evaluated on the held-out split.
6. **Record**: every valid child is kept with its diff, scores, lineage, and a signed record binding its exact
   code to its results. The child's fitness change is the reward for the meta prompt variant that produced it.
7. **Meta level** (optional, `--meta-evolve-every N`): the best agent proposes a new meta prompt variant, which
   enters a UCB bandit with the others. The process of self-improvement is itself subject to selection, while
   evaluation, selection of agents, budgets, and the sandbox stay frozen.

## Quickstart

```bash
scripts/setup.sh                        # venv + editable install (anthropic client and pytest)
source .venv/bin/activate
export ANTHROPIC_API_KEY=...

scripts/run_tests.sh                    # 136 tests, no API key needed
scripts/run_baseline.sh                 # validate benchmark, score the seed genome on both splits
scripts/run_evolution.sh runs/exp1 5    # 5 self-improvement iterations, then write the report
scripts/run_experiment.sh runs/exp 5 3  # arms vs the seed, 3 trials per task, with confidence intervals
scripts/serve.sh runs/exp1              # live dashboard at http://127.0.0.1:8765/
```

Or call the CLI directly:

```bash
singularis validate-suite               # every task: starter fails, reference solution passes
singularis eval --split train
singularis evolve --root runs/exp1 --iterations 5
singularis lineage --root runs/exp1
singularis report --root runs/exp1      # writes runs/exp1/report.json for the viewer
singularis serve --root runs/exp1       # live dashboard, localhost only
singularis verify --root runs/exp1      # check signed records against genomes, scores, result files
singularis export --root runs/exp1 --agent a0003 --dest my_agent   # shows the diff, asks to confirm

singularis evolve --root runs/exp1 --selection greedy --meta-evolve-every 3
singularis eval --split fresh --trials 5
singularis experiment --root runs/exp --iterations 5 --trials 3 --arms open_ended,greedy
singularis isolation-check              # inside the container: proxy allowlist, no tool egress, hardening
scripts/prepare_swebench.sh data/verified.jsonl tasks/swebench /path/to/env/bin/python --limit 10
```

Open `frontend/index.html` in a browser and load `runs/exp1/report.json`, or run `singularis serve` for a
dashboard that refreshes every few seconds while an experiment runs. It shows the lineage chart, archive
table with focus, prompt variant and fitness change per agent, meta prompt statistics, token usage, per task
results with integrity flags, and diffs. `frontend/sample/report.json` is sample data from a scripted run.

Models are selected with `--llm anthropic:<model>` (default `anthropic:claude-sonnet-5-5`). Use
`--meta-llm` to run self-modification with a different model than evaluation. `scripted:<path.json>` replays a
fixed script and is what the test suite uses.

Run it inside the network-isolated container stack (see `docs/SAFETY.md`):

```bash
scripts/docker_run.sh evolve --root runs/exp1 --iterations 5
```

## Bring your own benchmark

The builtin suite has 20 tasks in three tracks: 7 general programming tasks, 8 finance tasks (drawdown and
Sharpe, EWMA volatility, historical VaR and CVaR, SMA crossover backtest with costs and no lookahead, CSV price
cleaning, minimum variance weights, rolling z-scores, Black-Scholes), and 5 multi-file **issue tasks** modeled on
real bug reports (invoice rounding, ledger replay, TTL cache, rate limiter, migrations) where every one of several
fixes is required. Splits: 11 train, 5 held-out, 4 fresh. The `fresh` split is never touched during search and
is used only by `experiment` for final scores. Every task is checked by `validate-suite`.

For results that mean something, add **SWE-bench style repository tasks**: `singularis swebench prepare` turns a
dataset file into real-repository tasks (checkout without git history, hidden test patch, FAIL_TO_PASS and
PASS_TO_PASS scoring, test files reset before grading). See `docs/BENCHMARKS.md` for setup, what is verified, and
the limits. You can also create a directory per task:

```
mytasks/
  parse_logs/
    task.json          {"prompt": "...", "split": "train" | "heldout" | "fresh", "track": "finance"}
    files/             starter files copied into the agent workspace
    hidden_tests.py    unittest module, run after the agent finishes
```

Pass `--tasks-dir mytasks` to `eval` or `evolve`. Reference solutions exist only for builtin tasks, so validate
your own tasks by hand.

## Design decisions that matter

- **Frozen evaluator.** Hidden tests live outside the genome and are written only after the agent finishes,
  into a separate copy of the workspace. The genome cannot read or edit them.
- **Held-out and fresh splits.** Selection pressure on the train split inevitably overfits. The held-out score is
  reported but never used for selection, and the fresh split is not evaluated at all until the final comparison.
- **Statistics, not anecdotes.** `experiment` evaluates the seed and the best agent of each arm with repeated
  trials, reports bootstrap confidence intervals, and compares arms to the seed with a paired bootstrap over
  tasks. The generated `EXPERIMENT.md` says plainly when a difference is not distinguishable from zero.
- **Integrity scan.** Agent-written code is scanned for evaluator tampering (exit hooks, process and signal
  tricks, dynamic code, patching unittest, references to the hidden tests). In `strict` mode (default) a flagged
  solution scores zero and the digest tells the next generation why.
- **Signed records.** Each evaluated agent gets an HMAC over its exact code hash, scores, and result files.
  `singularis verify` detects edits made after the fact.
- **Reproducibility.** `manifest.json` records configuration, versions, a hash of the frozen engine, and
  fingerprints of the tasks, and warns on resume if any of them changed.
- **Budgets the agent cannot raise.** Token and call budgets are enforced by the harness around the LLM
  client, with a wall-clock kill as the backstop.
- **Open-ended archive.** All valid children are kept, so a temporary regression that unlocks a later gain is
  not discarded.
- **Cost-aware fitness.** `fitness = mean_score - 0.05 * (mean_tokens / token_cap)`. Correctness dominates,
  but efficiency can evolve.
- **Human in the loop.** The loop writes only inside its archive directory. `export` shows the diff and asks
  before copying a genome out.

## Limitations (read before running experiments)

- Without the container stack, isolation is process level (rlimits, scrubbed environment, path confinement).
  It is **not** a security boundary against a determined adversary. See `docs/SAFETY.md`.
- The evaluator shares an interpreter with the code under test, so a malicious solution could in principle
  forge a result. The integrity scan and signed records reduce and expose this; they do not eliminate it.
- Nothing here has been run against a live model. All tests use scripted models, so real-world behavior of the
  loop (cost, how often children pass validation, whether fitness improves) is unmeasured.
- Self-modification targets prompts, tools, and loop logic. Weight updates are out of scope.
- The container stack could not be built where this repository was authored (no Docker daemon). Its compose file, Dockerfile
  and proxy policy were validated with the official tools and a real squid, and `scripts/verify_docker.sh` proves the
  rest on your machine. See `docs/SAFETY.md`.
- No result in this repository is evidence of improvement. It ships infrastructure, not claims.

## Docs

- `docs/ARCHITECTURE.md`: module contracts and data flow
- `docs/SAFETY.md`: threat model and hardening checklist
- `docs/BENCHMARKS.md`: task tracks, issue tasks, running SWE-bench style data
- `docs/ROADMAP.md`: what is implemented and what remains for publishable results

## License

MIT. Developed under QuantSingularity Research Institute.
