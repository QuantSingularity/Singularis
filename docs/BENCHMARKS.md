# Benchmarks

Singularis scores agents on tasks with hidden tests. All tasks are scored the same way and belong to a split.

## Kinds of task

| Kind             | Track                | What it is                                                                                     | Source                            |
| ---------------- | -------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------- |
| Function tasks   | `general`, `finance` | One or two functions to implement from a written spec                                          | Built in, 15 tasks                |
| Issue tasks      | `issues`             | A small multi-file project with a bug report; several coordinated fixes and regression checks  | Built in, 5 tasks                 |
| Repository tasks | `swebench`           | A real repository at a base commit, a GitHub issue, hidden FAIL_TO_PASS and PASS_TO_PASS tests | Your SWE-bench style dataset file |

| Split     | Built-in tasks | Role                                                      |
| --------- | -------------- | --------------------------------------------------------- |
| `train`   | 11             | Used for selection during search                          |
| `heldout` | 5              | Reported for promising children, never used for selection |
| `fresh`   | 4              | Not evaluated until the final experiment comparison       |

`singularis validate-suite` checks every task. The starting state must fail, and the reference solution (or the gold
patch for repository tasks) must pass.

## Built-in function tasks

### General track (7 tasks)

| Task         | Split   | Hidden tests | Specification                                                                                 |
| ------------ | ------- | ------------ | --------------------------------------------------------------------------------------------- |
| `fizzbuzz`   | train   | 5            | List of strings for 1..n, empty for 0, `ValueError` for negatives                             |
| `median_bug` | train   | 8            | Fix `median` and `mean`: even length, empty input, no mutation                                |
| `roman`      | train   | 6            | `to_roman` and strict canonical `from_roman`, round trip for 1..3999                          |
| `lru_cache`  | train   | 7            | `LRUCache` with recency rules, `in` that does not refresh                                     |
| `intervals`  | train   | 9            | `merge_intervals` with touching ranges, validation, no mutation                               |
| `calculator` | heldout | 9            | Expression evaluator without `eval`: precedence, right-associative power, unary minus, errors |
| `toposort`   | heldout | 9            | Deterministic topological sort, dependency-only nodes, cycle detection                        |

### Finance track (8 tasks)

| Task              | Split   | Hidden tests | Specification                                                               |
| ----------------- | ------- | ------------ | --------------------------------------------------------------------------- |
| `drawdown_sharpe` | heldout | 9            | Maximum drawdown, annualized Sharpe with sample standard deviation          |
| `ewma_volatility` | train   | 5            | RiskMetrics style EWMA volatility series                                    |
| `historical_var`  | train   | 6            | Historical VaR and CVaR with a precisely defined quantile index             |
| `sma_backtest`    | train   | 6            | SMA crossover with no lookahead, transaction costs, trade counts            |
| `clean_prices`    | train   | 6            | Messy CSV cleaning: dates, duplicates, non-finite and non-positive closes   |
| `min_variance`    | heldout | 7            | Global minimum variance weights by Gaussian elimination, singular detection |
| `rolling_zscore`  | fresh   | 6            | Rolling z-scores with `None` warm-up and zero-variance handling             |
| `black_scholes`   | fresh   | 4            | European call and put, put-call parity, input validation                    |

## Built-in issue tasks (5 tasks)

Each task is a small package with a realistic bug report. The visible tests in each starter pass, so they are not
misleading. Removing any single required fix keeps the score below 1, so every bug must really be fixed.

| Task            | Split   | Hidden tests | Files to fix | Bugs                                                                                                                                                                                                            |
| --------------- | ------- | ------------ | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `invoice_cents` | train   | 13           | 5            | Float price parsing; truncating discount; discount applied per line instead of once; tax on the wrong base with banker's rounding; negative and thousands formatting; quantity validation                       |
| `ledger_replay` | train   | 12           | 3            | Snapshot boundary off by one; ordering by time only; duplicate retries applied twice; no overdraft rule; interest uses 360 days and truncation                                                                  |
| `ttl_cache`     | heldout | 13           | 2            | Expired entries counted as hits and never removed; `len` and `in` include expired entries; eviction before purging expired; decorator key depends on keyword order; `None` results recomputed; no `cache_clear` |
| `rate_limiter`  | fresh   | 10           | 2            | Mutable default shared across instances; fractional refill lost; `retry_after` ignores current tokens; no validation                                                                                            |
| `migrations`    | fresh   | 8            | 1            | Versions sorted as strings; version recorded before the script runs; no atomicity; semicolons in strings; string `current_version`; version validation                                                          |

A no-op agent still earns partial credit on these tasks (roughly 30 to 50 percent of hidden tests pass on the
starter), so compare the pass rate as well as the mean score.

## Repository tasks (SWE-bench style)

### Task directory produced by `swebench prepare`

| Path         | Content                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------ |
| `repo/`      | Checkout at the base commit, without `.git`, so the agent cannot read the fix from history |
| `test.patch` | Hidden tests, applied only at evaluation time                                              |
| `gold.patch` | Reference fix, used by `validate-suite`                                                    |
| `task.json`  | Prompt, split, test ids, interpreter, timeout, repository and base commit                  |

### Evaluation protocol

| Step | Action                                                                                |
| ---- | ------------------------------------------------------------------------------------- |
| 1    | Copy the agent's workspace to a temporary directory                                   |
| 2    | Reset every file the test patch touches to its base state (editing tests cannot help) |
| 3    | Apply the test patch with `git apply`                                                 |
| 4    | Run the test files with `python -m pytest -rA` using your interpreter                 |
| 5    | Score the fraction of FAIL_TO_PASS tests that pass                                    |
| 6    | If any PASS_TO_PASS test fails, the score is 0                                        |

### Running real data

| Step                      | Command or action                                                                                                                                                                |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Get a dataset          | Export a SWE-bench file (for example SWE-bench Verified from Hugging Face) to JSONL; start with a few instances from one repository                                              |
| 2. Prepare an environment | A Python with the repository's dependencies and pytest installed; the agent's edited code is the code under test because `python -m pytest` puts the workspace first on the path |
| 3. Prepare and validate   | `scripts/prepare_swebench.sh data/verified.jsonl tasks/swebench /path/to/env/bin/python --limit 10 --repos pallets/flask` (needs network for cloning; run on the host)           |
| 4. Evaluate               | `singularis eval --tasks-dir tasks/swebench --split train --max-steps 60 --max-tokens 1500000 --timeout 1800`                                                                    |
| 5. Experiment             | `singularis experiment --tasks-dir tasks/swebench --iterations 5 --trials 3`                                                                                                     |

### What is verified

| Item                                           | Status                                                        |
| ---------------------------------------------- | ------------------------------------------------------------- |
| Prepare, load, validate with the gold patch    | Verified on a real git repository in SWE-bench format         |
| Reset-and-patch evaluation                     | Verified: editing the tests earns nothing                     |
| Regression rule                                | Verified: a fix that breaks existing tests scores 0           |
| Integrity scan on changed files only           | Verified                                                      |
| A scripted agent resolving an issue end to end | Verified                                                      |
| Actual SWE-bench data                          | Not verified; it could not be downloaded where this was built |

### Known limits

| Limit                               | Detail                                                                                                                                                                     |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pytest only                         | Repositories with their own runner (Django, some SymPy and Sphinx tests) are not supported                                                                                 |
| Environments are yours              | The official harness builds a Docker image per instance; this adapter uses one interpreter you provide                                                                     |
| Python version and system libraries | A repository that needs a specific version or native libraries needs a matching interpreter                                                                                |
| Parametrized ids with spaces        | May not match the result parser                                                                                                                                            |
| Large files                         | `read_file` clips at 20,000 characters; the agent reads ranges with `start_line` and `end_line`                                                                            |
| Integrity scan is relaxed here      | Only changed files, no import or `eval` rules, because real code uses them legitimately; exit hooks, `os._exit`, `unittest` patching and test references are still flagged |

## Writing your own tasks

| Kind            | Layout                                                                                 | Notes                                                               |
| --------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Function task   | `<name>/task.json`, `<name>/files/...`, `<name>/hidden_tests.py`                       | `hidden_tests.py` is a unittest module run after the agent finishes |
| Repository task | `<name>/task.json` with `"kind": "repo"`, `repo/`, `test.patch`, optional `gold.patch` | Produced by `swebench prepare` or written by hand                   |

| `task.json` field                                          | Meaning                                                                                 |
| ---------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `prompt`                                                   | Instructions shown to the agent                                                         |
| `split`                                                    | `train`, `heldout` or `fresh` (default `train`)                                         |
| `track`                                                    | Free text label used in reports (default `general`, or `swebench` for repository tasks) |
| `id`                                                       | Defaults to the directory name                                                          |
| `fail_to_pass`, `pass_to_pass`, `python`, `test_timeout_s` | Repository tasks only                                                                   |

Load a directory with `--tasks-dir`. Validate repository tasks by including a `gold.patch`.
