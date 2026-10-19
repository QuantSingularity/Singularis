# Roadmap

## Implemented

| Area             | Capability                                                                                                           | Evidence                                                                            |
| ---------------- | -------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Core loop        | Seven-tool agent, sandboxed worker, frozen evaluator, lineage archive, self-modification of prompts, tools and logic | End-to-end tests with scripted models                                               |
| Search           | Open-ended and greedy selection, rotating focus, failure clustering                                                  | `test_search.py`, `test_archive.py`                                                 |
| Meta level       | Evolvable meta prompt with validation and a UCB bandit                                                               | `test_meta.py`                                                                      |
| Benchmark        | 20 tasks in general, finance and issues tracks with three splits                                                     | Validated; issue tasks require every fix                                            |
| Repository tasks | SWE-bench adapter, checkout without history, test reset, FAIL_TO_PASS scoring with a regression rule                 | Verified on a real git repository in SWE-bench format                               |
| Measurement      | Repeated trials, bootstrap intervals, paired comparison, experiment command, manifest, token accounting              | `test_stats.py`, `test_experiment.py`, `test_trials_and_manifest.py`                |
| Integrity        | Tamper scan, signed records, `verify`                                                                                | `test_integrity.py`, `test_signing.py`                                              |
| Operations       | Live dashboard with automatic refresh, report export, logging                                                        | Real server plus jsdom, including server loss and recovery                          |
| Containment      | Compose stack, egress allowlist, `isolation-check`, Docker verification script                                       | Compose and Dockerfile validated, proxy tested on a real squid                      |
| CI/CD            | One workflow with 14 jobs: checks, Python 3.10 to 3.13 matrix, packaging, container verification, releases           | actionlint, and the job scripts were executed locally on passing and failing inputs |

## Not yet done

| Priority | Item                                             | Why it matters                                                                                                  | Needs                                                       |
| -------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1        | Run against a live model                         | Cost per iteration, validity rate and any improvement are unmeasured                                            | An API key and a short budget                               |
| 2        | Run `scripts/verify_docker.sh`                   | Closes the unverified container rows in the safety doc; the `docker-stack` CI job does this on every push       | A machine with Docker, or GitHub Actions                    |
| 3        | Real SWE-bench instances                         | The adapter is proven on a synthetic instance only                                                              | A dataset file and one pure Python repository environment   |
| 4        | Real browser check                               | The dashboard was tested in jsdom only                                                                          | `scripts/test_frontend_browser.sh`, or the `browser` CI job |
| 5        | Compute-matched control                          | The seed and greedy arms do not spend equal compute; repeated sampling of the seed would                        | Experiment design                                           |
| 6        | Multiple seeds per condition                     | Current intervals reflect task variance, not search variance                                                    | Compute                                                     |
| 7        | Richer search                                    | Crossover between branches, novelty scoring, island populations, tool synthesis with unit tests                 | Engineering                                                 |
| 8        | Deeper meta-recursion                            | Let the agent propose changes to parent selection and focus scheduling, rewarded by descendant improvement rate | Engineering and care                                        |
| 9        | Stronger evaluator isolation                     | Run hidden tests in a process that never loads candidate code, closing forgery instead of detecting it          | Engineering                                                 |
| 10       | Per-task containers                              | Remove the shared worker process as an attack surface                                                           | Docker integration                                          |
| 11       | Non-pytest runners and per-instance environments | Broader SWE-bench coverage (Django and others)                                                                  | Engineering                                                 |
| 12       | Release                                          | Preprint and open-source release with lineages, traces and signed records                                       | Results from items 1 to 6                                   |

## Suggested first week

| Day | Step                       | Command                                            | What to look at                                                       |
| --- | -------------------------- | -------------------------------------------------- | --------------------------------------------------------------------- |
| 1   | Install and test           | `scripts/setup.sh`, `scripts/run_tests.sh`         | 139 passing                                                           |
| 1   | Verify the container stack | `scripts/verify_docker.sh`                         | All isolation checks pass                                             |
| 2   | Baseline                   | `scripts/run_baseline.sh`                          | Seed scores per split, tokens per task                                |
| 2   | Cheap smoke evolution      | `scripts/run_evolution.sh runs/smoke 2`            | Child validity, cost per iteration                                    |
| 3   | Inspect                    | `scripts/serve.sh runs/smoke`                      | Diffs, notes, integrity flags, token use                              |
| 4   | Real data                  | `scripts/prepare_swebench.sh ...` with 3 instances | `validate-suite` passes on real instances                             |
| 5   | First experiment           | `scripts/run_experiment.sh runs/exp 5 3`           | Intervals in `EXPERIMENT.md`; do not claim gains if they include zero |
