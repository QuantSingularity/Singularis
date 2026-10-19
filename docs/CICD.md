# CI/CD

One GitHub Actions workflow, `.github/workflows/cicd.yml`, holds every job. It checks every push and pull request,
runs a weekly audit, offers a manual paid baseline against the real model, and publishes releases from tags.

## Triggers

| Trigger                  | When                                                              | What runs                                                              |
| ------------------------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `push` to `main`         | Every merge                                                       | All check jobs and the gate                                            |
| `pull_request` to `main` | Every pull request (older runs are cancelled when you push again) | All check jobs and the gate                                            |
| `schedule`               | Mondays 03:17 UTC                                                 | All check jobs, plus `audit`                                           |
| `workflow_dispatch`      | Manual                                                            | All check jobs, plus `audit`, plus `live-baseline` if you tick the box |
| Tag `v*`                 | You push a version tag                                            | All check jobs, then `release` and `docker-publish`                    |

## Jobs

| Job              | Blocks the gate | What it does                                                                                                                                                 |
| ---------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `static`         | Yes             | Python syntax, undefined names and unused imports (ruff), shellcheck, hadolint, compose file, actionlint on the workflow itself, and the documentation rules |
| `test`           | Yes             | `validate-suite`, then the full suite with coverage on Python 3.10, 3.11, 3.12 and 3.13; uploads `junit.xml` and `coverage.xml`                              |
| `frontend`       | Yes             | `npm install`, render and hostile input checks, then live refresh against the real server in jsdom                                                           |
| `smoke`          | Yes             | A scripted run through the CLI: eval, evolve with meta prompt evolution, verify, report, and the live server                                                 |
| `proxy-policy`   | Yes             | Installs squid, starts it with `infrastructure/squid.conf`, probes allowed and blocked destinations and reads squid's own access log                         |
| `docker-stack`   | Yes             | `scripts/verify_docker.sh`: builds the stack and runs `isolation-check` and a scripted agent inside the container                                            |
| `build`          | Yes             | Builds the wheel and sdist, checks the wheel contents, installs it in a clean environment and runs `validate-suite`                                          |
| `ci-passed`      | It is the gate  | Succeeds only if every job above succeeded (skipped or cancelled counts as a failure)                                                                        |
| `browser`        | No              | The live refresh scenario in real Chromium through Playwright; uploads a screenshot                                                                          |
| `codeql`         | No              | CodeQL scanning for Python and JavaScript                                                                                                                    |
| `audit`          | No              | `pip-audit` on the installed dependencies; weekly and manual only                                                                                            |
| `live-baseline`  | No              | Scores the seed genome on a few tasks with the real model; manual only, behind an environment                                                                |
| `release`        | No              | Checks the tag against the package version, then creates a GitHub release with the built distributions                                                       |
| `docker-publish` | No              | Pushes the image to `ghcr.io/<owner>/<repo>` with the version and `latest` tags                                                                              |

`release` and `docker-publish` run only on `v*` tags and only after `ci-passed`.

### What the documentation rules enforce

| Rule                                                                                                         | Checked in                        |
| ------------------------------------------------------------------------------------------------------------ | --------------------------------- |
| Every table has a header, a separator row, the same number of cells in every row, and a blank line before it | All `.md` files                   |
| Code fences are balanced                                                                                     | All `.md` files                   |
| Relative links point to files that exist                                                                     | All `.md` files                   |
| No em dashes or en dashes                                                                                    | Every text file in the repository |
| No emoji                                                                                                     | Every text file in the repository |

## Setup on GitHub

| Item                                                     | Needed for                           | How                                                                                          |
| -------------------------------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------- |
| Branch protection with `CI passed` as the required check | A merge gate                         | Settings, Branches, add a rule for `main`, require the `CI passed` status check              |
| Secret `ANTHROPIC_API_KEY`                               | `live-baseline` only                 | Settings, Secrets and variables, Actions. Use a key with a spend cap                         |
| Environment `live-model` with required reviewers         | An approval step before any paid run | Settings, Environments. Optional but recommended                                             |
| Workflow permissions                                     | `release` and `docker-publish`       | Declared in the workflow (`contents: write`, `packages: write`); no repository change needed |
| GitHub Advanced Security                                 | `codeql` on a private repository     | Public repositories get it free. The job is informational and never blocks                   |

## Cutting a release

| Step | Action                                                                                                                                                      |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Set the same version in `pyproject.toml` and in `code/backend/__init__.py`                                                                                  |
| 2    | Commit and merge to `main` once `CI passed` is green                                                                                                        |
| 3    | `git tag v<version>` and `git push origin v<version>`                                                                                                       |
| 4    | The workflow re-runs all checks, then `release` verifies the tag equals `v<version>` and publishes the distributions, and `docker-publish` pushes the image |

If the tag and the version disagree, `release` fails before publishing anything.

## Reproducing jobs locally

| Job            | Local command                                                                                                                                                          |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `static`       | `ruff check --select E9,F63,F7,F82,F401,F811,F841 code scripts frontend/test`, `shellcheck -e SC2155 scripts/*.sh`, `hadolint infrastructure/Dockerfile`, `actionlint` |
| `test`         | `python -m pip install -e ".[dev]" pytest-cov`, then `python -m pytest --cov=ai_models --cov=backend`                                                                  |
| `frontend`     | `cd frontend && npm install && node test/render.js`, then `python -m pytest code/backend/tests/test_frontend.py`                                                       |
| `browser`      | `scripts/test_frontend_browser.sh`                                                                                                                                     |
| `smoke`        | The commands in the job; use an absolute path for the scripted model                                                                                                   |
| `proxy-policy` | Install squid, run it with `infrastructure/squid.conf` on another port, probe with `curl -x`                                                                           |
| `docker-stack` | `scripts/verify_docker.sh`                                                                                                                                             |
| `build`        | `python -m pip install build twine`, `python -m build`, `twine check dist/*`                                                                                           |

## Verification status

| Item                                                                                                                                         | Status                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Workflow syntax                                                                                                                              | actionlint clean, including shellcheck on every `run:` script                                               |
| Job scripts for `static`, `test`, `frontend`, `smoke`, `proxy-policy`, `build`, `ci-passed`, `release` checks, image naming, `live-baseline` | Extracted from the YAML and executed locally, on passing and failing inputs                                 |
| Python 3.10, 3.11, 3.12, 3.13                                                                                                                | The full suite passes on each (139 tests)                                                                   |
| The documentation rules, ruff and shellcheck                                                                                                 | Shown to fail on deliberately bad input                                                                     |
| `docker-stack`                                                                                                                               | Not run anywhere yet. It is the first real build of the container stack and may need a fix on its first run |
| `browser`                                                                                                                                    | Not run (the browser download was blocked where the workflow was written)                                   |
| `codeql`, artifact upload and download, `gh release create`, the image push, `apt-get` on the runner                                         | Only GitHub can verify these                                                                                |

## Problems found while verifying, now fixed

| Problem                                                                   | Cause                                                                                                      | Fix                                                                  |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| pytest crashed on Python 3.13                                             | The folder `code/` plus pytest `importlib` mode created a module that shadowed the standard library `code` | `pytest.ini` uses prepend mode                                       |
| Scripted model runs failed with `genome_error` from a different directory | Workers run in the task workspace, so a relative script path pointed nowhere                               | `absolute_llm_spec` resolves it before the worker starts, with tests |
| Frontend job could not install                                            | `pip install -e .` ran in `frontend/`                                                                      | Split into two steps                                                 |
| Intermittent proxy job failure                                            | Squid logs a denied request as `TCP_DENIED` or `TCP_DENIED_ABORTED` depending on timing                    | The assertion accepts both                                           |
| Docker script could fail with `Permission denied`                         | Git on a Windows path can lose the executable bit                                                          | The job runs it through `bash`                                       |
| Hung or noisy proxy step                                                  | A backgrounded squid inherited the step's output pipes, and a `sudo` redirect ran as the wrong user        | Redirect inside the `sudo` shell                                     |

## Troubleshooting

| Symptom                                   | Likely cause                                                          | What to do                                                                                         |
| ----------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `docker-stack` fails at `isolation-check` | A real isolation gap, or the proxy image uses a different config path | Read the job log, which prints container logs on failure; fix `docker-compose.yml` or `squid.conf` |
| `test` fails only on one Python version   | A version-specific incompatibility                                    | Reproduce with that version, for example through `uv venv --python 3.13`                           |
| `frontend` shows skipped tests            | jsdom is not installed                                                | Run `npm install` in `frontend/`                                                                   |
| `static` fails on docs                    | A malformed table, broken link, dash or emoji                         | The job prints the file and line                                                                   |
| `release` fails on the version check      | Tag and version disagree                                              | Fix the version in both files and retag                                                            |
