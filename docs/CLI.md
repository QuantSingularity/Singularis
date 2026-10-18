# Command reference

All commands are subcommands of `singularis`. Run `singularis <command> --help` for the built-in help.

## Contents

| Command                               | Purpose                               |
| ------------------------------------- | ------------------------------------- |
| [suite](#suite)                       | List tasks                            |
| [validate-suite](#validate-suite)     | Check task soundness                  |
| [eval](#eval)                         | Score a genome                        |
| [evolve](#evolve)                     | Run the self-improvement loop         |
| [experiment](#experiment)             | Compare arms against the seed         |
| [lineage](#lineage)                   | Print the archive                     |
| [report](#report)                     | Write `report.json`                   |
| [serve](#serve)                       | Live dashboard                        |
| [verify](#verify)                     | Check signed records                  |
| [export](#export)                     | Copy an evolved genome out            |
| [isolation-check](#isolation-check)   | Verify the container stack            |
| [swebench prepare](#swebench-prepare) | Build repository tasks from a dataset |

## Options shared by eval, evolve and experiment

| Option         | Default                       | Meaning                                                                                |
| -------------- | ----------------------------- | -------------------------------------------------------------------------------------- |
| `--llm`        | `anthropic:claude-sonnet-5-5` | Model for agent runs. `anthropic:<model>` or `scripted:<path>`                         |
| `--max-steps`  | 30                            | Maximum tool-use steps per task                                                        |
| `--max-tokens` | 400000                        | Token budget per task, enforced outside the genome                                     |
| `--timeout`    | 600                           | Wall clock seconds per task, enforced by killing the worker                            |
| `--workers`    | 4                             | Tasks run in parallel                                                                  |
| `--tasks-dir`  | none                          | Load tasks from a directory instead of the built-in suite                              |
| `--integrity`  | `strict`                      | `strict` zeroes a flagged solution, `warn` records flags only, `off` disables the scan |

Repository tasks usually need more than the defaults, for example `--max-steps 60 --max-tokens 1500000 --timeout 1800`.

## suite

List the tasks that would run.

| Option        | Default | Meaning                             |
| ------------- | ------- | ----------------------------------- |
| `--tasks-dir` | none    | List tasks from a directory instead |

## validate-suite

For every task, check that the starting state fails the hidden tests and that the reference solution (or the gold
patch for repository tasks) passes. Exit code 1 if any problem is found.

| Option        | Default | Meaning                                                     |
| ------------- | ------- | ----------------------------------------------------------- |
| `--tasks-dir` | none    | Validate a directory of tasks instead of the built-in suite |

## eval

Score a genome on a split of the suite.

| Option         | Default     | Meaning                               |
| -------------- | ----------- | ------------------------------------- |
| shared options | see above   |                                       |
| `--genome`     | seed genome | Directory of a genome to evaluate     |
| `--split`      | all tasks   | `train`, `heldout` or `fresh`         |
| `--trials`     | 1           | Repetitions per task                  |
| `--only`       | all         | Comma separated task ids              |
| `--out`        | `runs/eval` | Output directory (traces, workspaces) |

## evolve

Run the recursive self-improvement loop. Resumable: running it again on the same `--root` continues the archive.

| Option                | Default         | Meaning                                                |
| --------------------- | --------------- | ------------------------------------------------------ |
| shared options        | see above       |                                                        |
| `--meta-llm`          | same as `--llm` | Model used for self-modification runs                  |
| `--root`              | `runs/exp`      | Experiment directory                                   |
| `--iterations`        | 5               | Self-modification steps to run                         |
| `--seed`              | 0               | Random seed for parent selection                       |
| `--selection`         | `open_ended`    | `open_ended` or `greedy`                               |
| `--meta-evolve-every` | 0               | Evolve the meta prompt every N iterations (0 disables) |

## experiment

Run the unmodified seed and each arm, then compare them on held-out and fresh tasks with repeated trials.

| Option                | Default             | Meaning                                   |
| --------------------- | ------------------- | ----------------------------------------- |
| shared options        | see above           |                                           |
| `--meta-llm`          | same as `--llm`     | Model used for self-modification runs     |
| `--root`              | `runs/experiment`   | Experiment directory                      |
| `--iterations`        | 5                   | Self-modification steps per arm           |
| `--trials`            | 3                   | Final evaluation repetitions per task     |
| `--arms`              | `open_ended,greedy` | Comma separated selection strategies      |
| `--meta-evolve-every` | 0                   | Evolve the meta prompt every N iterations |
| `--seed`              | 0                   | Random seed                               |

Writes `experiment.json` and `EXPERIMENT.md` under `--root`, and one evolution directory per arm.

## lineage

Print the archive as a table, with the best agent by fitness.

| Option   | Default    | Meaning              |
| -------- | ---------- | -------------------- |
| `--root` | `runs/exp` | Experiment directory |

## report

Write `report.json` for the dashboard.

| Option   | Default              | Meaning              |
| -------- | -------------------- | -------------------- |
| `--root` | `runs/exp`           | Experiment directory |
| `--out`  | `<root>/report.json` | Output file          |

## serve

Serve the dashboard and a live `report.json` for an experiment. Routes: `/`, `/index.html`, `/report.json`, `/healthz`.

| Option           | Default     | Meaning                                   |
| ---------------- | ----------- | ----------------------------------------- |
| `--root`         | `runs/exp`  | Experiment directory                      |
| `--host`         | `127.0.0.1` | Address to bind                           |
| `--port`         | 8765        | Port to bind                              |
| `--allow-remote` | off         | Required to bind any non-loopback address |

## verify

Recompute each valid agent's genome hash and compare scores and result files with its signed record.
Exit code 1 if any record fails.

| Option   | Default    | Meaning              |
| -------- | ---------- | -------------------- |
| `--root` | `runs/exp` | Experiment directory |

## export

Print an agent's diff against the seed genome, then copy it out after confirmation.

| Option    | Default    | Meaning                                         |
| --------- | ---------- | ----------------------------------------------- |
| `--root`  | `runs/exp` | Experiment directory                            |
| `--agent` | required   | Agent id, for example `a0003`                   |
| `--dest`  | required   | Destination directory (must be empty or absent) |
| `--yes`   | off        | Skip the confirmation prompt                    |

## isolation-check

Run inside the container stack to verify its guarantees. Exit code 1 if any check fails.

| Option                    | Default        | Meaning                                                            |
| ------------------------- | -------------- | ------------------------------------------------------------------ |
| `--proxy`                 | `$HTTPS_PROXY` | Proxy URL to probe                                                 |
| `--runs`                  | `runs`         | Directory that must be writable                                    |
| `--skip-container-checks` | off            | Skip read-only root, user, capability and no-new-privileges checks |

| Check                                    | Passes when                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| proxy allows the model API               | `CONNECT api.anthropic.com:443` returns 200                              |
| proxy refuses everything else            | Other hosts, a lookalike domain and the wrong port are refused           |
| tool code has no direct internet         | A tool-style subprocess cannot connect to `1.1.1.1:443`                  |
| tool environment has no secrets or proxy | API key, proxy and signing key variables are absent in tool subprocesses |
| runs directory is writable               | A file can be created under `--runs`                                     |
| root filesystem is read-only             | `/proc/mounts` shows `/` mounted `ro` (container checks)                 |
| not running as root                      | Effective uid is not 0 (container checks)                                |
| all capabilities dropped                 | `CapEff` is all zeros (container checks)                                 |
| no-new-privileges is set                 | `NoNewPrivs` is 1 (container checks)                                     |

## swebench prepare

Convert a SWE-bench format dataset file (JSON Lines or a JSON array) into task directories.
Exit code 1 if any instance fails.

| Option           | Default                         | Meaning                                                                  |
| ---------------- | ------------------------------- | ------------------------------------------------------------------------ |
| `--dataset`      | required                        | Dataset file                                                             |
| `--out`          | required                        | Output directory for task directories                                    |
| `--cache`        | `~/.cache/singularis`           | Where repository clones are cached                                       |
| `--repo-source`  | `https://github.com/{repo}.git` | Clone URL template (`{repo}` is `owner/name`)                            |
| `--python`       | empty                           | Interpreter that has the repository's dependencies and pytest            |
| `--limit`        | 0 (all)                         | Stop after this many instances                                           |
| `--repos`        | all                             | Comma separated `owner/name` filter                                      |
| `--split`        | `auto`                          | `auto` assigns by hash of the instance id (60/20/20), or force one split |
| `--test-timeout` | 900                             | Seconds allowed for the hidden tests                                     |

## Model specifications

| Spec                | Meaning                                                                                             |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| `anthropic:<model>` | The Anthropic API with the given model name (needs `ANTHROPIC_API_KEY` and the `anthropic` package) |
| `scripted:<path>`   | Replay a JSON script of model turns. Used by the tests and the Docker smoke run                     |

A script is a JSON list of turns:

| Field                           | Type   | Meaning                                         |
| ------------------------------- | ------ | ----------------------------------------------- |
| `text`                          | string | Assistant text for the turn (optional)          |
| `tool_calls`                    | list   | Each item has `name` and `arguments` (optional) |
| `input_tokens`, `output_tokens` | int    | Reported usage, default 10 and 5                |

When the script is exhausted the model answers "script exhausted" with no tool calls, which ends the run.

## Environment variables

| Variable                                                                                 | Used by        | Meaning                                                                                  |
| ---------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`                                                                      | Worker only    | API key for `anthropic:` models. Never passed to tool subprocesses                       |
| `ANTHROPIC_BASE_URL`, `HTTPS_PROXY`, `HTTP_PROXY`, `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` | Worker only    | Passed through for `anthropic:` runs                                                     |
| `SINGULARIS_LOG_DIR`                                                                     | All commands   | Log directory, default `code/logs`                                                       |
| `SINGULARIS_SIGNING_KEY`                                                                 | evolve, verify | HMAC key for signed records. Default is a generated `signing.key` in the experiment root |
| `LOCAL_UID`, `LOCAL_GID`                                                                 | Docker scripts | Host user mapped into the container so `runs/` is writable                               |

## Exit codes

| Code | Meaning                                                                                               |
| ---- | ----------------------------------------------------------------------------------------------------- |
| 0    | Success                                                                                               |
| 1    | A check failed, a task or record is unsound, an export was declined, or an instance failed to prepare |
