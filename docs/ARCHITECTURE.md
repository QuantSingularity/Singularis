# Architecture

## Trust boundaries

| Zone    | Contents                                                                                             | Who may change it                             |
| ------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| Frozen  | `code/backend/**`, `code/ai_models/llm.py`, hidden tests, meta prompt validation, selection, budgets | Humans only                                   |
| Mutable | `code/ai_models/genome/`                                                                             | The agent, through the self-modification loop |
| Data    | `runs/<experiment>/**`                                                                               | The loop writes it; humans read it            |

The agent can only change a copy of the genome. The copy is placed in a scratch workspace as `./genome`, edited there,
and only that directory is read back.

## Modules

| Module                                                               | Role                                                                                                     |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ai_models/llm.py`                                                   | `LLMClient` protocol, `AnthropicClient`, `ScriptedClient`, `BudgetedClient`                              |
| `ai_models/genome/agent.py`                                          | `solve()`: the tool-use loop with context compaction                                                     |
| `ai_models/genome/tools.py`                                          | Seven tools: `list_files`, `read_file`, `search_text`, `write_file`, `edit_file`, `run_python`, `finish` |
| `ai_models/genome/prompts.py`                                        | System prompt                                                                                            |
| `backend/core/sandbox.py`                                            | Subprocess runner with rlimits, scrubbed environment, workspace path confinement                         |
| `backend/core/worker.py`                                             | Process entry point: load a genome, apply the budget, run `solve()`, write the trace                     |
| `backend/core/loader.py`                                             | Load a genome by path, check the interface contract                                                      |
| `backend/core/trace.py`                                              | `RunTrace`, `Step`, `ToolRecord`                                                                         |
| `backend/core/isolation.py`                                          | Checks behind `singularis isolation-check`                                                               |
| `backend/core/logging_config.py`                                     | Console and file logging                                                                                 |
| `backend/evaluation/evaluator.py`                                    | Hidden test execution for function tasks, suite validation                                               |
| `backend/evaluation/repo_eval.py`                                    | Repository evaluation: reset tests, apply patch, run pytest, score                                       |
| `backend/evaluation/swebench.py`                                     | SWE-bench dataset to task directories                                                                    |
| `backend/evaluation/tasks.py`                                        | `Task` model, directory loader, split selection                                                          |
| `backend/evaluation/suite.py`, `suite_finance.py`, `suite_issues.py` | The 20 built-in tasks                                                                                    |
| `backend/evaluation/runner.py`                                       | Run a task or suite with trials, integrity enforcement, fitness function                                 |
| `backend/evaluation/integrity.py`                                    | AST scan for evaluator tampering                                                                         |
| `backend/evaluation/stats.py`                                        | Bootstrap intervals and paired comparison                                                                |
| `backend/evolution/archive.py`                                       | SQLite lineage tree, parent selection strategies                                                         |
| `backend/evolution/evolve.py`                                        | The loop: diagnose, modify, validate, evaluate, record                                                   |
| `backend/evolution/meta.py`                                          | Meta prompt variants and the UCB bandit                                                                  |
| `backend/evolution/experiment.py`                                    | Seed versus arms protocol and report generation                                                          |
| `backend/evolution/signing.py`                                       | HMAC records                                                                                             |
| `backend/evolution/manifest.py`                                      | Reproducibility manifest and change detection                                                            |
| `backend/evolution/report.py`, `serve.py`                            | Archive export and the localhost server                                                                  |
| `backend/cli.py`                                                     | The `singularis` command                                                                                 |

## Genome contract

```python
def solve(task: str, workspace: Path, llm: LLMClient, sandbox: SandboxConfig, max_steps: int = 30) -> RunTrace
```

| Rule      | Detail                                                                                                                                   |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Export    | `genome/__init__.py` exports `solve`                                                                                                     |
| Signature | The first four parameters are named `task`, `workspace`, `llm`, `sandbox`, and `max_steps` is accepted                                   |
| Imports   | `ai_models.llm`, `backend.core.sandbox`, `backend.core.text`, `backend.core.trace`, standard library; relative imports inside the genome |
| Files     | `.py`, `.md`, `.txt`, `.json` only; at most 30 files and 200 KB; no symlinks                                                             |
| Return    | A `RunTrace`; anything else is recorded as a `genome_error`                                                                              |

## Running one task

| Step | Action                                                                                                | Module                         |
| ---- | ----------------------------------------------------------------------------------------------------- | ------------------------------ |
| 1    | Create a fresh workspace: starter files, or a copy of the repository checkout without `.git`          | `runner.py`                    |
| 2    | Start `python -m backend.core.worker` under rlimits and a wall clock timeout                          | `runner.py`                    |
| 3    | The worker loads the genome, wraps the model in a budget, calls `solve()`, writes a JSON trace        | `worker.py`                    |
| 4    | Crash, timeout or bad return becomes a trace with `genome_error`, `timeout` or `worker_failure`       | `runner.py`                    |
| 5    | Copy the workspace, add hidden tests, run them, parse the result (nonce protected for function tasks) | `evaluator.py`, `repo_eval.py` |
| 6    | Scan agent-written code for tampering; in strict mode a flag zeroes the score                         | `integrity.py`                 |
| 7    | Return a `TaskResult` with score, tokens, stop reason, flags                                          | `runner.py`                    |

Stop reasons: `finished`, `no_tool_calls`, `max_steps`, `budget`, `llm_error`, `genome_error`, `timeout`, `worker_failure`.

## Scoring

| Task kind                                       | Score                                                                                           |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Function and issue tasks                        | Passing hidden tests divided by total hidden tests                                              |
| Repository tasks                                | FAIL_TO_PASS tests fixed divided by FAIL_TO_PASS total, or 0 if any PASS_TO_PASS test now fails |
| Any task in `strict` integrity mode with a flag | 0                                                                                               |
| Fitness (used for selection)                    | `mean_score - 0.05 * min(1, mean_tokens / token_cap)`                                           |

## One evolution step

| Step | Action                                                                                               |
| ---- | ---------------------------------------------------------------------------------------------------- |
| 1    | Select a parent (`open_ended` or `greedy`)                                                           |
| 2    | Choose a meta prompt variant by UCB and a focus area by rotation                                     |
| 3    | Copy the parent genome into a scratch workspace and build the prompt with the failure digest         |
| 4    | Run the parent genome on that workspace as an agent                                                  |
| 5    | Check the candidate: file policy, then compile, import and contract in a subprocess                  |
| 6    | If invalid: archive as `invalid`, reward the variant -0.05, stop                                     |
| 7    | If valid: store it, write the diff, evaluate on train, compute the fitness change against the parent |
| 8    | Evaluate on held-out only if the change is zero or positive; sign the record                         |
| 9    | Record the change as the meta prompt variant's reward                                                |
| 10   | Every N iterations, run the meta level                                                               |

| Mutation focus       | Instruction given to the agent                     |
| -------------------- | -------------------------------------------------- |
| `prompts`            | Improve the system prompt                          |
| `tools`              | Add or improve a tool                              |
| `loop`               | Improve control flow in the main loop              |
| `context_management` | Keep the conversation compact and relevant         |
| `efficiency`         | Reach the same results with fewer steps and tokens |
| `error_recovery`     | Detect failures earlier and recover reliably       |

| Failure class                                 | Meaning                                         |
| --------------------------------------------- | ----------------------------------------------- |
| `wrong_answer`                                | Finished normally, score 0                      |
| `partial_credit`                              | Finished normally, some but not all tests pass  |
| `budget`, `timeout`, `max_steps`              | A limit was hit                                 |
| `llm_error`, `genome_error`, `worker_failure` | The model call, the genome or the worker failed |
| `no_tool_calls`                               | The model stopped without finishing             |
| `integrity_violation`                         | The tamper scan flagged the solution            |

### Parent selection

| Strategy     | Rule                                                                                                                                 |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `open_ended` | Sample with weight `sigmoid(10 * (fitness - midpoint)) / (1 + children)`, where midpoint is between the mean and the maximum fitness |
| `greedy`     | Always the fittest valid agent (the hill-climbing control)                                                                           |

## Meta level

| Aspect          | Detail                                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------------------------- |
| What is evolved | The instruction template used to ask an agent to modify itself                                                        |
| Who proposes    | The best agent, editing `meta_prompt.md` in a scratch workspace                                                       |
| Validation      | Keeps `{parent}`, `{digest}`, `{focus}`; formats cleanly; at most 6000 characters; not a duplicate                    |
| Selection       | UCB1 on the mean fitness change of the children each variant produced (exploration 0.1); new variants are tried first |
| Penalty         | An invalid child counts as -0.05 for its variant                                                                      |
| Storage         | `runs/<exp>/meta_prompts/m0.md`, `m1.md`, ... and `stats.json`, outside the genome                                    |
| Not evolvable   | Evaluation, selection of agents, budgets, sandbox, the validator itself                                               |

## Experiment protocol

| Stage            | Action                                                                                |
| ---------------- | ------------------------------------------------------------------------------------- |
| Control          | Evaluate the unmodified seed on held-out and fresh tasks with repeated trials         |
| Arms             | For each arm, run a full evolution in its own directory                               |
| Best agent       | Highest train fitness in the arm                                                      |
| Final evaluation | The same repeated trials on held-out and fresh tasks                                  |
| Comparison       | Paired bootstrap over tasks of the per-task mean difference from the seed             |
| Output           | `experiment.json` and `EXPERIMENT.md` with confidence intervals and an honest reading |

## Archive and run directory

| Path under `runs/<experiment>/`                          | Content                                                                      |
| -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `archive.db`                                             | SQLite table of agents (see below)                                           |
| `manifest.json`                                          | Configuration, versions, frozen code hash, task fingerprints, change history |
| `usage.json`                                             | Meta tokens, evaluation tokens, iteration count                              |
| `signing.key`                                            | HMAC key (unless `SINGULARIS_SIGNING_KEY` is set)                            |
| `report.json`                                            | Written by `singularis report`, read by the dashboard                        |
| `meta_prompts/`                                          | Meta prompt variants and `stats.json`                                        |
| `agents/<id>/genome/`                                    | The exact code that was evaluated                                            |
| `agents/<id>/diff.patch`                                 | Change relative to the parent                                                |
| `agents/<id>/results_train.json`, `results_heldout.json` | Per-task scores, tokens, flags                                               |
| `agents/<id>/train/traces/*.trace.json`                  | Full tool call traces                                                        |
| `agents/<id>/signature.json`                             | HMAC record for this agent                                                   |
| `meta/<id>/`                                             | The self-modification run that produced the agent                            |
| `work/<id>/`                                             | Scratch workspace                                                            |

| Archive column                           | Meaning                                                                |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| `id`, `parent_id`, `generation`          | Lineage (`a0000` is the seed)                                          |
| `status`                                 | `valid` or `invalid`                                                   |
| `note`                                   | The agent's own description of its change, or the rejection reason     |
| `train_score`, `train_tokens`, `fitness` | Train split results                                                    |
| `heldout_score`                          | Held-out result, only for promising children                           |
| `focus`, `meta_variant`, `delta`         | Mutation focus, meta prompt variant, fitness change against the parent |

## Extension points

| To add               | Do this                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| A model provider     | Implement `LLMClient.complete` in `ai_models/` and register it in `make_llm`                            |
| Benchmark tasks      | Task directories (`--tasks-dir`), `Task` objects in a suite module, or SWE-bench data                   |
| A mutable surface    | Add modules inside `ai_models/genome/`, then update `META_PROMPT` so the agent knows it may change them |
| A focus area         | Add it to `FOCI` and `FOCUS_TEXT` in `evolution/evolve.py`                                              |
| A selection strategy | Add it to `SELECTIONS` and `Archive.select_parent`                                                      |
