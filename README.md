# Singularis

A research framework for **recursive self-improvement of coding agents**. An agent evaluates itself on a
benchmark, diagnoses its own failures, rewrites its own source code, and keeps the rewrite only if a frozen
evaluator says it got better. The improved agent then runs the next round of self-modification.

The foundation model stays fixed. What evolves is the agent around it, called the **genome**: its prompts, tools,
and control loop. The design follows the line of work behind the Darwin Godel Machine, STOP, Voyager and
AlphaEvolve, with the engineering needed to run it reproducibly, measure it honestly, and contain it.

## At a glance

| Item               | Detail                                                                                                                                          |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Language           | Python 3.10 or newer, standard library only at runtime (the `anthropic` package is optional)                                                    |
| What evolves       | `code/ai_models/genome/`: system prompt, seven tools, agent loop                                                                                |
| What never changes | Evaluator, hidden tests, budgets, sandbox, selection, archive (the frozen engine in `code/backend/`)                                            |
| Default model      | `claude-sonnet-5-5` through the Anthropic API, or a scripted model for tests                                                                    |
| Benchmark          | 28 built-in tasks in 3 tracks: 11 train, 9 held-out, 8 fresh, plus SWE-bench style repository tasks                                             |
| Search             | Open-ended archive or greedy hill climbing, rotating mutation focus, failure clustering                                                         |
| Meta level         | Optional evolvable instruction template, chosen by a bandit                                                                                     |
| Measurement        | Repeated trials in search and final runs, bootstrap interval plus exact sign-flip test, underpowered guard                                      |
| Integrity          | Private result channel with canary tests, two-tier tamper scan (tasks and genomes), token metering outside the genome, signed records, manifest |
| Containment        | Process sandbox by default, network-isolated container stack available                                                                          |
| Tests              | 217 automated tests plus 2 that need node, none need an API key                                                                                 |
| Size               | About 7,700 lines of Python excluding tests (about 2,900 of them are benchmark task data)                                                       |

## Status

This repository ships infrastructure and verified tooling. It does not ship results.

| Capability                                | Status                            | Evidence                                                                                                    |
| ----------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Self-improvement loop, archive, selection | Implemented and tested            | End-to-end tests with scripted models                                                                       |
| Meta prompt evolution                     | Implemented and tested            | Bandit, validation and step tests                                                                           |
| Benchmark (28 tasks)                      | Verified                          | Starters fail, references pass, each fix is individually required                                           |
| Statistics and experiment protocol        | Implemented and tested            | Bootstrap, exact sign-flip test, underpowered guard, trials during search                                   |
| Evaluator hardening                       | Implemented and attacked in tests | Forgery by thread, stdout, fd guessing, framework patching and early exit all fail closed                   |
| Token metering and key isolation          | Implemented and tested end to end | A real worker runs through the meter with no key in its environment; budgets enforced there                 |
| Integrity scan and signed records         | Implemented and tested            | Hard and review tiers; genomes scanned before they run; tamper evidence, not prevention                     |
| SWE-bench adapter                         | Verified on a synthetic instance  | Real git repository in SWE-bench format; real SWE-bench data not tried                                      |
| Container stack                           | Partly verified                   | Compose and Dockerfile validated, proxy tested against a real squid; image never built here                 |
| Live dashboard refresh                    | Verified in a simulated browser   | Real server plus jsdom; a real Chromium script is provided but was not run                                  |
| Runs against a live model                 | Tooling ready, not run            | `singularis live` gives a cost ceiling, a preflight and a summary; needs your API key; no result is claimed |

## How the loop works

```
      frozen (the agent cannot touch)                      mutable
 +---------------------------------------------+      +-----------------+
 | evaluator, hidden tests | budgets | sandbox |      |  ai_models/     |
 | archive | selection | validation | worker   |      |    genome/      |
 +---------------------------------------------+      +--------+--------+
                      |                                        |
 select parent --> meta task "improve ./genome" --> candidate child genome
      ^             (run by the PARENT genome)                |
      |                                                       v
      +--- archive child <--- evaluate train / held-out <--- validate
```

| Step          | What happens                                                                                                  | Where                             |
| ------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 1. Select     | Pick a parent: `open_ended` (fitness weighted, bonus for rarely extended branches) or `greedy` (fittest only) | `evolution/archive.py`            |
| 2. Diagnose   | Cluster the parent's failures by class and build a digest with traces and errors                              | `evolution/evolve.py`             |
| 3. Modify     | The parent genome edits a copy of its own source, guided by a focus area and a meta prompt variant            | `evolution/evolve.py`             |
| 4. Validate   | File policy, compile, import and interface contract checks in a subprocess                                    | `evolution/evolve.py`             |
| 5. Evaluate   | Train split with an integrity scan; held-out split only if the child is at least as fit as its parent         | `evaluation/runner.py`            |
| 6. Record     | Keep the child with diff, scores and lineage; sign the record; reward the meta prompt variant                 | `evolution/signing.py`, `meta.py` |
| 7. Meta level | Optionally let the best agent propose a new meta prompt variant (`--meta-evolve-every N`)                     | `evolution/meta.py`               |

## Repository layout

| Path                                  | Purpose                                                                                         |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `code/ai_models/`                     | Model side: `llm.py` (providers, budgets) and `genome/` (the evolving agent)                    |
| `code/backend/core/`                  | Sandbox, worker, loader, trace, metering proxy, logging, isolation checks                       |
| `code/backend/evaluation/`            | Evaluator, task suites, repository tasks, SWE-bench adapter, runner, statistics, integrity scan |
| `code/backend/evolution/`             | Archive, evolution loop, meta prompts, experiments, signing, manifest, report, live server      |
| `code/backend/cli.py`                 | The `singularis` command                                                                        |
| `code/testkit.py`, `code/conftest.py` | Shared test helpers and fixtures                                                                |
| `code/logs/`                          | Runtime logs (`singularis.log`)                                                                 |
| `docs/`                               | Architecture, CLI, benchmarks, safety, testing, roadmap                                         |
| `frontend/`                           | Single-file lineage dashboard, its tests, and sample data                                       |
| `infrastructure/`                     | Dockerfile, compose stack, egress proxy config, smoke fixture                                   |
| `scripts/`                            | Helper scripts for setup, runs, experiments, Docker and report generation                       |
| `.github/workflows/cicd.yml`          | CI/CD: 14 jobs covering checks, tests, packaging, container verification and releases           |
| `pytest.ini`, `pyproject.toml`        | Test and packaging configuration                                                                |

## Quickstart

```bash
scripts/setup.sh                        # virtual environment and editable install
source .venv/bin/activate
export ANTHROPIC_API_KEY=...            # not needed for tests or scripted runs

scripts/run_tests.sh                    # 217 tests
scripts/run_baseline.sh                 # validate the benchmark, score the seed genome
scripts/run_live.sh --dry-run           # worst-case cost of a small real-model run (no API calls)
scripts/run_live.sh                     # that run: preflight, token cap, runs/live/LIVE_SUMMARY.md
scripts/run_evolution.sh runs/exp1 5    # 5 self-improvement iterations, then write the report
scripts/serve.sh runs/exp1              # live dashboard at http://127.0.0.1:8765/
scripts/run_experiment.sh runs/exp 5 3  # arms versus the seed, 3 trials per task
```

| Script                             | Purpose                                                             |
| ---------------------------------- | ------------------------------------------------------------------- |
| `scripts/setup.sh`                 | Create `.venv` and install with the Anthropic client and pytest     |
| `scripts/run_tests.sh`             | Run the test suite (arguments pass through to pytest)               |
| `scripts/run_baseline.sh`          | Validate the suite, then score the seed on train and held-out       |
| `scripts/run_live.sh`              | Small real-model run with a cost ceiling and an automatic summary   |
| `scripts/run_evolution.sh`         | Run the evolution loop, then write `report.json`                    |
| `scripts/run_experiment.sh`        | Run the seed versus arms experiment, then verify signed records     |
| `scripts/serve.sh`                 | Start the live dashboard on localhost                               |
| `scripts/make_report.sh`           | Write `report.json` for an experiment                               |
| `scripts/make_sample_report.py`    | Regenerate the dashboard sample data from a scripted run            |
| `scripts/prepare_swebench.sh`      | Convert a SWE-bench dataset file into validated task directories    |
| `scripts/docker_run.sh`            | Run any command inside the isolated container stack                 |
| `scripts/verify_docker.sh`         | Build the stack and verify its guarantees from inside the container |
| `scripts/test_frontend_browser.sh` | Check the dashboard in real Chromium through Playwright             |

## Command line

Every command is documented with all options in [docs/CLI.md](docs/CLI.md).

| Command                       | Purpose                                                                |
| ----------------------------- | ---------------------------------------------------------------------- |
| `singularis suite`            | List tasks                                                             |
| `singularis validate-suite`   | Check that every task fails at the start and passes with its reference |
| `singularis eval`             | Score a genome on a split, with repeated trials                        |
| `singularis evolve`           | Run the self-improvement loop (resumable)                              |
| `singularis experiment`       | Compare evolution arms with the seed, with confidence intervals        |
| `singularis lineage`          | Print the archive as a table                                           |
| `singularis report`           | Write `report.json` for the dashboard                                  |
| `singularis serve`            | Live dashboard on localhost                                            |
| `singularis verify`           | Check signed records against genomes, scores and result files          |
| `singularis export`           | Show an evolved genome's diff and copy it out after confirmation       |
| `singularis isolation-check`  | Verify the container stack from inside it                              |
| `singularis swebench prepare` | Turn a SWE-bench dataset file into repository tasks                    |

## Benchmark

| Track      | Tasks | What it tests                                                                                                         | Source            |
| ---------- | ----- | --------------------------------------------------------------------------------------------------------------------- | ----------------- |
| `general`  | 7     | Classic programming specs: parsing, caching, scheduling, intervals                                                    | Built in          |
| `finance`  | 8     | Drawdown, Sharpe, EWMA volatility, VaR and CVaR, backtests, price cleaning, minimum variance, z-scores, Black-Scholes | Built in          |
| `issues`   | 5     | Multi-file bug reports where every one of several fixes is required                                                   | Built in          |
| `swebench` | any   | Real repositories at a base commit with hidden FAIL_TO_PASS and PASS_TO_PASS tests                                    | Your dataset file |

| Split     | Built-in tasks | Role                                                      |
| --------- | -------------- | --------------------------------------------------------- |
| `train`   | 11             | Used for selection during search                          |
| `heldout` | 5              | Reported for promising children, never used for selection |
| `fresh`   | 4              | Untouched until the final experiment comparison           |

Details, task tables and instructions for running real SWE-bench data are in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Continuous integration

One workflow, `.github/workflows/cicd.yml`, runs on every push and pull request. Details are in [docs/CICD.md](docs/CICD.md).

| Stage                | Jobs                                                                                                                      | Trigger               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| Checks               | `static`, `test` (Python 3.10 to 3.13), `frontend`, `smoke`, `proxy-policy`, `docker-stack`, `build`, `browser`, `codeql` | Push and pull request |
| Gate                 | `ci-passed`, the single required check                                                                                    | Push and pull request |
| Scheduled and manual | `audit`, `live-baseline` (paid, manual)                                                                                   | Weekly, manual        |
| Delivery             | `release`, `docker-publish`                                                                                               | Tags named `v*`       |

## Design decisions

| Decision                   | Why                                               | Enforced by                                                                          |
| -------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Frozen evaluator           | The agent must not be able to edit what judges it | Hidden tests are written after the agent finishes, into a separate copy              |
| Three splits               | Selection overfits the train split                | Held-out is never selected on; fresh is evaluated only in final comparison           |
| Budgets outside the genome | The agent must not raise its own limits           | The metering proxy counts tokens and refuses calls; the key never reaches the worker |
| Open-ended archive         | A temporary regression can unlock a later gain    | Every valid child is kept; parent choice favors rarely extended branches             |
| Cost-aware fitness         | Efficiency should be able to evolve               | `fitness = mean_score - 0.05 * min(1, mean_tokens / token_cap)`                      |
| Statistics over anecdotes  | One lucky run proves nothing                      | Repeated trials, bootstrap plus sign-flip test, no verdict below 8 tasks             |
| Tamper scan                | Reward hacking is the main failure mode           | Two-tier AST scan of solutions and genomes; only hard findings score zero            |
| Signed records             | Results must not change silently                  | HMAC over genome hash, scores and result files                                       |
| Human gate                 | Evolved code is unreviewed code                   | Nothing leaves the archive without `export` and a confirmation                       |

## Safety summary

| Layer             | Protects against                                                         | Strength                                      |
| ----------------- | ------------------------------------------------------------------------ | --------------------------------------------- |
| Process sandbox   | Runaway CPU, memory, file size, output; path escapes; leaked environment | Basic. Not a security boundary                |
| Genome validation | A child that breaks the interface, adds odd files, or fails to import    | Strong for what it checks                     |
| Evaluator channel | Forged or hidden verdicts from solution code                             | Strong against forgery; see docs/SAFETY.md    |
| Metering proxy    | Budget tampering, token under-reporting, API key theft by the genome     | Strong for the key and the counts             |
| Integrity scan    | Evaluator tampering by solutions and genomes                             | Heuristic. Obfuscated code can evade it       |
| Signed records    | After-the-fact edits to stored results                                   | Tamper evidence only                          |
| Container stack   | Network access and host damage from agent code                           | Strong if verified on your machine; see below |

Read [docs/SAFETY.md](docs/SAFETY.md) before running experiments with a real API key.

## Limitations

| Limitation                                                       | Consequence                                                                                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| No live-model run has happened                                   | Cost per iteration, how often children pass validation, and whether fitness improves are unmeasured                                                    |
| Process-level isolation is not a security boundary               | Use the container stack or a VM for real experiments                                                                                                   |
| Candidate code runs in the same interpreter as the tests         | Result forgery is closed (private channel, canaries); a solution that deliberately patches the test framework is made hard and visible, not impossible |
| Container stack was not built in the authoring environment       | Run `scripts/verify_docker.sh` once on a machine with Docker                                                                                           |
| SWE-bench support is pytest only and needs your own environments | Start with a few instances from one pure Python repository                                                                                             |
| Built-in tasks can saturate with a strong model                  | Use the issue tasks and SWE-bench style tasks for meaningful comparisons                                                                               |
| Self-modification covers prompts, tools and loop logic           | Weight updates are out of scope                                                                                                                        |

## Documentation

| Document                                             | Contents                                                                                    |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)         | Trust boundaries, modules, contracts, data flow, archive layout                             |
| [docs/CLI.md](docs/CLI.md)                           | Every command and option with defaults                                                      |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md)             | Task tracks, all 28 tasks, SWE-bench workflow, limits                                       |
| [docs/SAFETY.md](docs/SAFETY.md)                     | Threat model, controls, container stack, verification status                                |
| [docs/TESTING.md](docs/TESTING.md)                   | What the 217 tests cover and how to run them                                                |
| [docs/CICD.md](docs/CICD.md)                         | The GitHub Actions workflow: jobs, setup, local reproduction, releases, verification status |
| [docs/ROADMAP.md](docs/ROADMAP.md)                   | What is implemented and what remains                                                        |
| [code/README.md](code/README.md)                     | Source layout and import rules                                                              |
| [frontend/README.md](frontend/README.md)             | The dashboard and its tests                                                                 |
| [infrastructure/README.md](infrastructure/README.md) | The container stack files                                                                   |

## License

MIT. Developed under QuantSingularity Research Institute.
