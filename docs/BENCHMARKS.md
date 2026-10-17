# Benchmarks

Singularis evaluates agents on tasks with hidden tests. There are three kinds, all scored the same way and all
split into `train`, `heldout` and `fresh`.

| Kind             | Track                | What it is                                                                                     | Where it comes from               |
| ---------------- | -------------------- | ---------------------------------------------------------------------------------------------- | --------------------------------- |
| Function tasks   | `general`, `finance` | One or two functions to implement from a spec                                                  | Built in (15 tasks)               |
| Issue tasks      | `issues`             | A multi-file project with a bug report; several coordinated fixes, regression checks           | Built in (5 tasks)                |
| Repository tasks | `swebench`           | A real repository at a base commit, a GitHub issue, hidden FAIL_TO_PASS and PASS_TO_PASS tests | Your SWE-bench style dataset file |

`singularis validate-suite` checks every task: the starting state must fail, and the reference solution (or the
gold patch for repository tasks) must pass.

## Built-in tasks

15 function tasks (7 general, 8 finance) are a pipeline check: a strong model solves most of them. The 5 issue
tasks are meant to be harder. Each is a small package with a realistic bug report:

| Task            | Split   | What makes it hard                                                                                                         |
| --------------- | ------- | -------------------------------------------------------------------------------------------------------------------------- |
| `invoice_cents` | train   | Five files; float parsing, truncation vs half-up rounding, per-line vs whole-invoice discount, tax base, signed formatting |
| `ledger_replay` | train   | Snapshot boundary off-by-one, ordering by (ts, seq), duplicate retries, overdraft rule, interest day count and rounding    |
| `ttl_cache`     | heldout | Expiry bookkeeping, eviction order (purge expired before LRU), hit/miss accounting, decorator key and `None` caching       |
| `rate_limiter`  | fresh   | Mutable default argument shared across instances, lost fractional refill, wrong `retry_after`, validation                  |
| `migrations`    | fresh   | String vs numeric version order, atomic multi-statement migrations, semicolons in strings, both sqlite3 transaction modes  |

Test-suite guarantees (`code/backend/tests/test_suite.py`): the visible tests in each starter pass (so they are not
misleading), and removing any one of the reference file fixes drops the score below 1, so every bug must really
be fixed. Starting scores are partial (a no-op agent scores roughly 30 to 50 percent), so look at the pass rate, not
only the mean score.

## SWE-bench style repository tasks

### What it does

`singularis swebench prepare` reads a SWE-bench formatted file (JSON Lines or a JSON array with `instance_id`,
`repo`, `base_commit`, `problem_statement`, `patch`, `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS`) and writes one
task directory per instance:

```
tasks/swebench/<instance_id>/
  repo/          checkout at base_commit, WITHOUT .git (the agent cannot read the fix from history)
  test.patch     hidden tests, applied only at evaluation time
  gold.patch     reference fix, used by validate-suite
  task.json      prompt, split, test ids, python interpreter, timeout
```

Evaluation follows the SWE-bench protocol: copy the agent's result, reset the test files the patch touches to
their base state (so editing tests does not help), apply the test patch, run the listed test files with pytest, and
score the FAIL_TO_PASS tests. If any PASS_TO_PASS test now fails, the score is 0. Splits are assigned by a stable
hash of the instance id (60 / 20 / 20) unless you pass `--split`.

### Running it

1. Get a dataset file. For example SWE-bench Verified from Hugging Face (`princeton-nlp/SWE-bench_Verified`), exported
   to JSONL. Start with a handful of instances from one repository.
2. Create a Python environment that has the repository's dependencies and `pytest` installed. The tests run with
   `python -m pytest` from the agent's workspace, so the agent's edited code is the code under test even when the
   dependencies were installed from the original checkout.
3. Prepare and validate (needs network access for the clone, so run it on the host):
   ```bash
   scripts/prepare_swebench.sh data/verified.jsonl tasks/swebench /path/to/env/bin/python --limit 10 --repos pallets/flask
   ```
4. Run it like any other task set:
   ```bash
   singularis eval --tasks-dir tasks/swebench --split train --max-steps 60 --max-tokens 1500000 --timeout 1800
   singularis experiment --tasks-dir tasks/swebench --iterations 5 --trials 3
   ```
   Real issues need more steps and tokens than the defaults (30 steps, 400k tokens).

### Verified and not verified

- **Verified:** the whole path with a real git repository in SWE-bench format (a synthetic instance, built in the tests):
  prepare, load, validate with the gold patch, reset-and-patch evaluation, tamper resistance (edited tests, broken
  regressions), integrity scanning of only the files the agent changed, and a scripted agent resolving the issue.
- **Not verified:** actual SWE-bench data. It cannot be downloaded from the environment where this was built.
  Expect friction on real instances.

### Known limits

- pytest only. Repositories with their own test runner (Django, SymPy's runner, some Sphinx tests) are not supported.
- Environment setup is yours. The official SWE-bench harness builds one Docker image per instance; this adapter
  uses one interpreter you provide. Repositories that need a specific Python version or system libraries need a
  matching interpreter. Pure Python repositories are the easiest starting point.
- Test ids containing spaces in parametrized names may not match the summary parser.
- `read_file` clips at 20,000 characters; the agent reads large files with line ranges (`start_line`, `end_line`).
- The integrity scan on repositories is relaxed (only changed files, no import or `eval` rules) because real code
  uses them legitimately. It still flags exit hooks, `os._exit`, patching `unittest`, and references to the tests.

## Writing your own tasks

Function style (files in `files/`, hidden `hidden_tests.py`) and repository style (`kind: "repo"`) both load with
`--tasks-dir`. See the root README for the directory format. Validate repository tasks with a `gold.patch`.
