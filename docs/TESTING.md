# Testing

139 automated tests run in about 40 seconds. None of them need an API key or network access. Model behavior is
replaced by scripted models that replay fixed tool calls, so the loop, the evaluator and the containment logic are
tested for real while the model itself is not.

## Running the tests

| Goal               | Command                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------ |
| Everything         | `scripts/run_tests.sh` or `python -m pytest`                                               |
| One file           | `python -m pytest code/backend/tests/test_evolve.py`                                       |
| One test           | `python -m pytest code/backend/tests/test_evolve.py -k valid_child`                        |
| Dashboard tests    | `cd frontend && npm install`, then `python -m pytest code/backend/tests/test_frontend.py`  |
| Real browser check | `scripts/test_frontend_browser.sh` (installs Playwright and Chromium; not part of the 139) |

Configuration lives in `pytest.ini` at the repository root (`testpaths = code`, `pythonpath = code`, prepend import mode).
Shared helpers are in `code/testkit.py` and fixtures in `code/conftest.py`; the fixtures send logs to a temporary
directory so tests never write to `code/logs`.

## Coverage by test file

### Model side (`code/ai_models/tests/`)

| File                   | Tests | Covers                                                                                                                                                                                                           |
| ---------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_genome_agent.py` | 6     | A scripted agent solving a task end to end; an idle agent; path escape reported to the agent and not executed; runaway agent stopped by the budget; a broken genome contained; tool errors do not crash the loop |
| `test_genome_tools.py` | 6     | `edit_file` (unique match, missing, ambiguous, outside workspace) and `search_text` (matches, no match, bad pattern, hidden and binary files)                                                                    |
| `test_llm.py`          | 6     | Message conversion for the Anthropic API, scripted client, token and call budgets, model spec parsing                                                                                                            |

### Engine (`code/backend/tests/`)

| File                          | Tests | Covers                                                                                                                                                                            |
| ----------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_archive.py`             | 5     | Ids, lineage, best agent, parent selection, update guard, empty archive                                                                                                           |
| `test_evolve.py`              | 5     | A full self-modification step with a valid child; a child that breaks the contract is rejected; genome file policy; import and contract validation; diffs                         |
| `test_experiment.py`          | 3     | Arms versus seed with confidence intervals; unknown arm; report wording for reliable gains                                                                                        |
| `test_frontend.py`            | 2     | Dashboard render checks including hostile input; live refresh against the real server (update, selection kept, server loss, recovery)                                             |
| `test_integrity.py`           | 13    | Every tamper pattern, harmless code, strict, warn and off modes                                                                                                                   |
| `test_isolation.py`           | 11    | Strict and permissive proxies, unreachable proxy, open and closed routes, scrubbed tool environment, leaky configuration, mount and status parsing, exit codes                    |
| `test_meta.py`                | 7     | Template validation, UCB choice, duplicates, persistence, reward recording, invalid child penalty, meta prompt evolution                                                          |
| `test_report_and_cli.py`      | 5     | Report content, `report`, `suite` and `lineage` commands, log file                                                                                                                |
| `test_runner_paths.py`        | 3     | Relative scripted model paths resolved before a worker starts, other specs untouched, a relative path working end to end                                                          |
| `test_sandbox.py`             | 13    | Path confinement, symlink escape, timeouts, output clipping, scrubbed environment, config round trip                                                                              |
| `test_search.py`              | 8     | Failure classes and clusters, greedy selection, unknown strategy, focus rotation, greedy evolver, usage and manifest files                                                        |
| `test_serve.py`               | 4     | Live report, index and health routes, 404s and traversal attempts, remote bind refused                                                                                            |
| `test_signing.py`             | 6     | Verification after a run, edited genome, edited results and scores, wrong key, missing signature, `verify` exit codes                                                             |
| `test_stats.py`               | 6     | Mean, bootstrap interval, determinism, paired comparison, noise not reported as signal                                                                                            |
| `test_suite.py`               | 14    | All tasks validate, splits and tracks, directory loader, issue task guarantees                                                                                                    |
| `test_swebench.py`            | 12    | Prepare, load, validate, base fails and fix passes, edited tests earn nothing, regressions score 0, scripted agent end to end, CLI, error handling, parsing, splits, relaxed scan |
| `test_trials_and_manifest.py` | 4     | Repeated trials, manifest contents, change warnings on resume, frozen hash                                                                                                        |

## Guarantees the suite enforces

| Guarantee                                                                           | Test                                                                                   |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Every task starts failing and its reference passes                                  | `test_suite.py::test_builtin_suite_is_sound`                                           |
| Visible tests on issue task starters pass, so they are not misleading               | `test_suite.py::test_visible_tests_pass_on_the_starter_so_they_are_not_misleading`     |
| Each required fix in an issue task is individually necessary                        | `test_suite.py::test_every_fix_is_individually_necessary`                              |
| A child that breaks the interface never enters the archive as valid                 | `test_evolve.py::test_child_that_breaks_the_contract_is_rejected`                      |
| Editing the tests does not help on repository tasks                                 | `test_swebench.py::test_editing_the_tests_does_not_help`                               |
| A flagged solution scores 0 in strict mode                                          | `test_integrity.py::test_strict_mode_zeroes_a_flagged_solution`                        |
| Tampering with a stored genome or score is detected                                 | `test_signing.py`                                                                      |
| A relative scripted model path works from any directory                             | `test_runner_paths.py::test_a_relative_scripted_model_works_end_to_end`                |
| The dashboard keeps your selection across refreshes and recovers from a lost server | `test_frontend.py::test_live_refresh_follows_the_archive_keeps_selection_and_recovers` |

## Configuration notes

| Setting         | Value                                | Why                                                                                                                                                                        |
| --------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--import-mode` | `prepend`                            | The source folder is named `code/`. In `importlib` mode pytest registers a module called `code` that shadows the standard library one, which crashes pytest on Python 3.13 |
| Test file names | Must be unique across the repository | Prepend mode imports each test file by its basename                                                                                                                        |
| `pythonpath`    | `code`                               | Lets tests import `ai_models`, `backend` and `testkit` by name                                                                                                             |

## Skips and requirements

| Test group         | Needs                                                     | When missing                |
| ------------------ | --------------------------------------------------------- | --------------------------- |
| `test_swebench.py` | `git` on the path                                         | The whole module is skipped |
| `test_frontend.py` | `node` and the `jsdom` package in `frontend/node_modules` | Skipped with a message      |
| Everything else    | Python 3.10 or newer and pytest                           | Always runs                 |

## Checks that were done once, not in the suite

| Check                                                                                          | Result                                                     |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Mutation checks of the live refresh test (polling disabled, selection reset, no paused status) | The test failed each time, so it can detect those bugs     |
| Compose file against the official Docker Compose binary                                        | Valid                                                      |
| Dockerfile against hadolint                                                                    | Clean                                                      |
| Proxy allowlist against a real squid                                                           | Correct; found one real start-up bug                       |
| Pipeline as a non-root user with an unwritable source tree                                     | Works                                                      |
| `isolation-check` against a real squid                                                         | Correct, including reporting open internet where it exists |

## Not tested

| Gap                                      | How to close it                                                     |
| ---------------------------------------- | ------------------------------------------------------------------- |
| Behavior with a live model               | Run `scripts/run_baseline.sh` and a short evolution with an API key |
| Building and running the container stack | `scripts/verify_docker.sh` on a machine with Docker                 |
| The dashboard in a real browser          | `scripts/test_frontend_browser.sh`                                  |
| Real SWE-bench instances                 | Prepare a few and run `validate-suite` on them                      |
