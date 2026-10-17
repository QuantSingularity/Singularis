# Architecture

## Trust boundaries

| Zone    | Contents                                                 | Who may change it                             |
| ------- | -------------------------------------------------------- | --------------------------------------------- |
| Frozen  | `code/backend/**`, `code/ai_models/llm.py`, hidden tests | Humans only                                   |
| Mutable | `code/ai_models/genome/`                                 | The agent, through the self-modification loop |

The genome is the only code the agent is ever allowed to change. A candidate is copied into a scratch
workspace as `./genome`, edited there, and only that directory is read back.

## Modules

| Module                                                                           | Role                                                                                                                 |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `ai_models/llm.py`                                                               | `LLMClient` protocol, `AnthropicClient`, `ScriptedClient`, `BudgetedClient`                                          |
| `ai_models/genome/`                                                              | Seed agent: `prompts.py`, `tools.py`, `agent.py` with `solve()`                                                      |
| `backend/core/sandbox.py`                                                        | Subprocess runner with rlimits, scrubbed env, workspace path confinement                                             |
| `backend/core/worker.py`                                                         | Process entry point that loads a genome and runs `solve()` under a budget                                            |
| `backend/core/loader.py`                                                         | Load a genome by path, check the interface contract                                                                  |
| `backend/core/trace.py`                                                          | `RunTrace`, `Step`, `ToolRecord`                                                                                     |
| `backend/core/logging_config.py`                                                 | Console and file logging (`code/logs`)                                                                               |
| `backend/core/isolation.py`                                                      | `isolation-check`: proxy policy, tool egress, secrets, container hardening checks                                    |
| `backend/evaluation/evaluator.py`                                                | Hidden test execution and benchmark validation (function and repository tasks)                                       |
| `backend/evaluation/repo_eval.py`                                                | Repository evaluation: reset test files, apply the test patch, run pytest, score FAIL_TO_PASS with a regression rule |
| `backend/evaluation/swebench.py`                                                 | SWE-bench dataset to task directories (checkout without git history, deterministic splits)                           |
| `backend/evaluation/tasks.py`, `suite.py`, `suite_finance.py`, `suite_issues.py` | `Task`, directory loader, general, finance and multi-file issue tasks                                                |
| `backend/evaluation/runner.py`                                                   | Run one task or a suite (with trials), integrity enforcement, fitness function                                       |
| `backend/evaluation/integrity.py`                                                | AST scan for evaluator tampering in agent-written code                                                               |
| `backend/evaluation/stats.py`                                                    | Bootstrap confidence intervals and paired comparisons                                                                |
| `backend/evolution/archive.py`                                                   | SQLite lineage tree, `open_ended` and `greedy` parent selection                                                      |
| `backend/evolution/evolve.py`                                                    | Propose, validate, evaluate, select; failure clustering; usage accounting                                            |
| `backend/evolution/meta.py`                                                      | Versioned meta prompt templates with a UCB bandit                                                                    |
| `backend/evolution/experiment.py`                                                | Seed vs arms protocol, final trials on held-out and fresh splits                                                     |
| `backend/evolution/signing.py`                                                   | HMAC records binding code, scores, and result files                                                                  |
| `backend/evolution/manifest.py`                                                  | Reproducibility manifest and change detection on resume                                                              |
| `backend/evolution/report.py`, `serve.py`                                        | Archive export and the live localhost server                                                                         |
| `backend/cli.py`                                                                 | `singularis` command                                                                                                 |

## Genome contract

```python
def solve(task: str, workspace: Path, llm: LLMClient, sandbox: SandboxConfig, max_steps: int = 30) -> RunTrace
```

- Exported from `genome/__init__.py`.
- May import `ai_models.llm`, `backend.core.sandbox`, `backend.core.text`, `backend.core.trace`, plus the
  standard library. Internal imports must be relative.
- Allowed file types inside the genome: `.py`, `.md`, `.txt`, `.json`. At most 30 files and 200 KB. No symlinks.

`loader.check_contract` enforces the signature (first four parameter names and a `max_steps` parameter).

## One task run

1. `runner.run_task` writes starter files into a fresh workspace.
2. `runner.run_agent` starts `python -m backend.core.worker` under rlimits and a wall-clock timeout. The
   worker loads the genome by path, wraps the LLM client in a `BudgetedClient`, and calls `solve`.
3. The worker writes a JSON `RunTrace`. A crash, timeout, or malformed return becomes a trace with
   `stop_reason` set to `genome_error`, `timeout`, or `worker_failure`.
4. `evaluator.evaluate` copies the workspace, adds the hidden tests and a runner script, and executes them.
   The result is passed back with a per-run random nonce. Score is `passed / total`.

## One evolution step

1. `Archive.select_parent` samples a valid agent with weight `sigmoid(10 * (fitness - midpoint)) / (1 + children)`.
2. A scratch workspace is created containing a copy of the parent genome at `./genome`.
3. The **parent genome** runs the meta prompt against that workspace. The digest in the prompt lists the
   parent's lowest scoring training tasks with their last tool calls and errors.
4. The candidate passes `check_genome_files`, then `validate_genome` (compile every file, import, contract).
   Failures are archived as `invalid` with the reason.
5. Valid candidates get a unified diff, are evaluated on train, and are evaluated on held-out only when
   `fitness >= parent.fitness`. Each evaluation is followed by a signed record.
6. The child's fitness change (or a fixed penalty for an invalid child) is recorded as the reward of the meta
   prompt variant that produced it.

Parent selection is `open_ended` or `greedy` (`Archive.select_parent`). The focus of each step rotates through
`FOCI` by archive size. Failing results are clustered by `failure_class` and the digest leads with the clusters.

## Meta level

Every N iterations (`--meta-evolve-every`) the best agent edits `meta_prompt.md` in a scratch workspace, using
`META_META_PROMPT`. `meta.validate_template` accepts the result only if it keeps the placeholders `{parent}`,
`{digest}`, `{focus}`, formats cleanly, and stays under 6000 characters. Accepted variants are tried once
immediately, then compete through UCB1 on the mean fitness change of the children they produced. The templates
live in `runs/<exp>/meta_prompts/`, outside the genome, so the agent cannot rewrite its own objective, the
evaluator, selection, or budgets.

## Experiment protocol

`run_experiment` evaluates the unmodified seed genome (control) on the held-out and fresh splits with repeated
trials. For each arm it runs a full evolution in its own directory, takes the best agent by train fitness, and
evaluates it the same way. Per task means feed `paired_bootstrap`, which resamples tasks to produce a
confidence interval for the difference from the seed. Output: `experiment.json` and `EXPERIMENT.md`.

## Archive layout

```
runs/exp/
  archive.db                     SQLite: id, parent, generation, status, scores, note
  report.json                    written by `singularis report`, read by the frontend
  manifest.json                  configuration, versions, frozen code hash, task fingerprints
  usage.json                     meta and evaluation token totals, iteration count
  meta_prompts/                  meta prompt variants (m0.md, m1.md, ...) and stats.json
  signing.key                    HMAC key unless SINGULARIS_SIGNING_KEY is set
  agents/a0003/
    genome/                      the exact code that was evaluated
    diff.patch                   change relative to the parent
    signature.json               HMAC record for this agent
    results_train.json           per task scores, token use, integrity flags
    results_heldout.json
    train/traces/*.trace.json    full tool call traces
  meta/a0003/meta.trace.json     the self-modification run that produced a0003
  work/a0003/                    scratch workspace
```

## Extending

- **New provider**: implement `LLMClient.complete` and register it in `make_llm`.
- **New benchmark**: use the task directory format, or build `Task` objects directly.
- **Different mutation targets**: change `META_PROMPT` in `backend/evolution/evolve.py` to focus the search,
  for example on tools only or on memory only. Keep this outside the genome so the agent cannot rewrite its
  own objective.
