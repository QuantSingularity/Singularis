# Safety and threat model

A self-modifying agent runs code that no human has reviewed. Treat every candidate genome and every task workspace
as untrusted. This document states what is protected, how, and how well that has been verified.

## Threat model

| Threat                                              | Mitigation                                                                                                                                                                                                                                                           | Residual risk                                                                                                                                              |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent code exhausts CPU, memory, disk or output     | rlimits, wall clock kill of the process group, output clipping                                                                                                                                                                                                       | Limits are per process; a container adds a hard cap                                                                                                        |
| Agent writes outside its workspace                  | Resolved path checks in file tools, symlink escapes rejected                                                                                                                                                                                                         | `run_python` code can write anywhere the OS user can                                                                                                       |
| Agent steals the API key                            | The key lives only in the framework's metering proxy; a worker gets a loopback URL and a placeholder; the framework process is non-dumpable so a same-user child cannot read its environment or memory                                                               | An environment-variable key is still in the framework's initial environment block for root or a debugger; prefer `ANTHROPIC_API_KEY_FILE` and a capped key |
| Agent calls out to the network                      | Container stack: internal network plus an allowlist proxy                                                                                                                                                                                                            | Process-only mode has no network control                                                                                                                   |
| Agent edits or reads the hidden tests               | Function-task tests are sent to the harness on stdin and never exist on disk; repository tests, conftest.py, pytest.ini and tox.ini are reset to base first                                                                                                          | Same-interpreter evaluator can be attacked by obfuscated code                                                                                              |
| Agent forges a result                               | Verdict read from a private descriptor, nonce on stdin, two canary tests with known outcomes and random names, a single record required, timeouts discarded, `os._exit` right after reporting; static tamper scan; signed records                                    | A solution that deliberately patches the test framework with knowledge of this harness can still try; see below                                            |
| Agent raises its own budget or under-reports tokens | The metering proxy counts the tokens the API reports and refuses calls past the budget; the runner records its numbers and flags any mismatch with the genome's own report; genomes that touch the wrapper are rejected by the scan; the worker is killed on timeout | The in-worker wrapper is only a convenience; streaming calls are refused by the proxy                                                                      |
| Agent breaks the interface or ships odd files       | File policy, compile, import and contract validation before any evaluation                                                                                                                                                                                           | None known for what is checked                                                                                                                             |
| Meta prompt drifts toward dangerous instructions    | Validator requires placeholders, formats, length cap; evaluation and budgets are outside its reach                                                                                                                                                                   | The template can still say unwise things inside those limits; review variants                                                                              |
| Stored results change after the fact                | Signed records and `verify`                                                                                                                                                                                                                                          | Same-user processes that can read the key can re-sign                                                                                                      |
| Dashboard injects markup from agent text            | Everything rendered with `textContent`                                                                                                                                                                                                                               | None known                                                                                                                                                 |
| Dashboard exposed to the network                    | Loopback only unless `--allow-remote`; three fixed routes                                                                                                                                                                                                            | Remote mode shows diffs and notes to anyone who can reach it                                                                                               |

## Controls in the framework

| Control              | Where                     | Behavior                                                                                                                                          |
| -------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| rlimits and timeouts | `core/sandbox.py`         | Address space, CPU seconds and file size per process; process group kill on timeout                                                               |
| Scrubbed environment | `core/sandbox.py`         | Only `PATH`, `HOME`, `LANG`, Python flags and explicit values reach a subprocess                                                                  |
| Path confinement     | `core/sandbox.py`         | `resolve_in_workspace` rejects escapes and symlink tricks                                                                                         |
| Budgets              | `core/meter.py`           | The metering proxy holds the key, counts tokens and refuses calls past the budget; `ai_models/llm.py` wraps the client too, as a fast local check |
| Evaluator channel    | `evaluation/evaluator.py` | Verdict over a private descriptor, canary tests, stdin delivery, timeouts discarded                                                               |
| Genome validation    | `evolution/evolve.py`     | Types, size, no symlinks, compile, import and signature checks in a subprocess                                                                    |
| Integrity scan       | `evaluation/integrity.py` | Two tiers and two profiles, below; hard findings score 0 in strict mode                                                                           |
| Signed records       | `evolution/signing.py`    | HMAC over code hash, scores and result files                                                                                                      |
| Manifest             | `evolution/manifest.py`   | Warns on resume if the engine or tasks changed                                                                                                    |
| Human gate           | `cli.py export`           | Shows the diff and asks before copying a genome out                                                                                               |
| Localhost server     | `evolution/serve.py`      | Loopback only, three routes, no directory listing                                                                                                 |

### Integrity scan rules

Two tiers, because a rule that zeroes honest work teaches the search to dodge the rule instead of cheating less.
A hard finding has no legitimate use in the code being judged and scores 0 in strict mode (or rejects a genome).
A review finding is unusual but can be honest; it is recorded and shown, and never scored.

| Tier   | Solutions (task workspaces)                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hard   | `atexit`, `ctypes`, `gc`; `os._exit`, `os.kill`, `os.abort`; module-level `sys.exit`, `exit`, `quit`; `sys._getframe`, `settrace`, `setprofile`; `inspect.stack` and `currentframe`; frame attributes (`f_back`, `f_locals`, ...); assigning into `unittest` or `builtins` or `setattr` on them; `sys.modules['unittest']`; starting a thread or process at import time; pytest result hooks (`pytest_runtest_makereport`, `pytest_report_teststatus`, ...) |
| Review | `subprocess`, `socket`, `threading`, `multiprocessing`, `signal`, `builtins`, `importlib`, `inspect` imports; `os.system`, `os.popen`, `os.fork`; `eval`, `exec`, `__import__`; threads inside functions; `sys.modules`; a string mentioning `hidden_tests` or `_runner` (docstrings are ignored); any edited `conftest.py`; files too large or unparsable to scan                                                                                          |

Code under `if __name__ == "__main__":` is skipped, because the tests import modules and never run that block.

Genomes are scanned with a stricter profile before they are ever executed. Hard findings reject the child:
network, process and thread modules, `inspect`, `importlib`; `os.environ`, `os.getenv`; `eval`, `exec`, `compile`;
`sys.modules`; attributes `budget`, `_inner` and `_client`; assignment to token and budget counters; imports of
framework modules outside the genome contract (only `ai_models.llm`, `backend.core.sandbox`, `backend.core.text`
and `backend.core.trace` are allowed); symlinks and files too large to scan. Review findings (such as a direct
`open` call) are written to the child's `integrity.json`. The seed genome has no findings of either kind.

Repository tasks run the same scan on the files the agent changed, with the import and dynamic-code rules
relaxed. Whatever the scan says, edits to `conftest.py`, `pytest.ini` and `tox.ini` are discarded before judging.

| Mode               | Behavior                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------- |
| `strict` (default) | A solution or genome with a hard finding is zeroed or rejected, and the next generation is told why |
| `warn`             | Findings are recorded, scores and genomes are kept                                                  |
| `off`              | No scan                                                                                             |

Repository tasks use a relaxed scan (changed files only, no import or dynamic code rules).

## What process-level isolation does not do

| Gap                                                  | Consequence                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No network isolation                                 | Subprocess limits cannot block sockets                                                                                                                                                                                                                                                                                                                                     |
| No filesystem isolation                              | Agent code can read anything the OS user can read                                                                                                                                                                                                                                                                                                                          |
| Candidate code runs in the same process as the tests | Forging by output, threads or guessed descriptors fails, and patching `unittest` is caught by canary tests. A solution written against this exact harness that patches the framework selectively could still try; held-out and fresh tasks, review findings and spot checks are the defense. Full separation would need an RPC boundary between the tests and the solution |
| Signed records are tamper evidence, not prevention   | A process that can read the key (file or environment) can re-sign; keep the key outside the sandbox                                                                                                                                                                                                                                                                        |
| The key is held by the framework process             | The genome never receives it, but root, a debugger or an environment dump of the framework can; use `ANTHROPIC_API_KEY_FILE` and a dedicated key with a spend cap                                                                                                                                                                                                          |

## The container stack

| Control                   | Mechanism                                                                                    |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| No route to the internet  | Compose network `sandbox` with `internal: true`                                              |
| One exit                  | Squid proxy on both networks, allowing `CONNECT api.anthropic.com:443` only                  |
| Tools get no proxy or key | The worker receives proxy variables and the key; tool subprocesses do not                    |
| Read-only root filesystem | `read_only: true`, `tmpfs` for `/tmp`, only `runs/` writable                                 |
| No privileges             | `cap_drop: [ALL]`, `no-new-privileges:true`, non-root user mapped from your host uid and gid |
| Resource caps             | `pids_limit: 256`, `mem_limit: 8g`, `cpus: 4`                                                |

### Verification status

| Item                                          | How it was checked                                                                                                            | Result                                                                                 |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Compose file                                  | Official Docker Compose binary, `config`                                                                                      | Valid                                                                                  |
| Dockerfile                                    | hadolint                                                                                                                      | Clean                                                                                  |
| Proxy allowlist                               | Real squid with the repo's config                                                                                             | Behaves as designed (table below)                                                      |
| Proxy start-up                                | Same run                                                                                                                      | Found and fixed a bug: logging to `/dev/stderr` stopped squid from starting            |
| Non-root, unwritable source                   | Pipeline run as uid 10001 against a root-owned source tree                                                                    | Works; writes only to `runs/` and `/tmp`                                               |
| `isolation-check` logic                       | Unit tests with fake strict and permissive proxies, open and closed routes, a leaky configuration; run against the real squid | Correct; it reported open internet access in an unrestricted environment, as it should |
| Host `runs/` permissions                      | Reasoned and fixed with `LOCAL_UID` and `LOCAL_GID` mapping                                                                   | Not run under Docker                                                                   |
| Building the image                            | Not possible, no Docker daemon in the authoring environment                                                                   | Not verified                                                                           |
| Containers actually running with these limits | Same                                                                                                                          | Not verified                                                                           |
| Internal network blocking egress              | Same                                                                                                                          | Not verified                                                                           |

| Proxy probe                                               | Result with the real squid                                           |
| --------------------------------------------------------- | -------------------------------------------------------------------- |
| `CONNECT api.anthropic.com:443`                           | Tunnel established (the API answered 404 to a bare GET, as expected) |
| `CONNECT example.com:443`                                 | 403                                                                  |
| Plain HTTP request to `example.com`                       | 403                                                                  |
| `CONNECT api.anthropic.com.attacker.test:443` (lookalike) | 403                                                                  |
| `CONNECT api.anthropic.com:8443` (wrong port)             | 403                                                                  |

Run `scripts/verify_docker.sh` once on a machine with Docker to close the unverified rows. It builds the stack, runs
`singularis isolation-check` inside the container, validates the suite, and runs a scripted agent under all limits.

One residual channel: tool code can open a connection to the proxy itself, which allows only the model API host. Tools
do not receive the API key, so they cannot authenticate, but this is the only route out.

## Hardening checklist

| Item                                                          | Why                                                   |
| ------------------------------------------------------------- | ----------------------------------------------------- |
| Run experiments in the container stack or a VM                | Real network and filesystem isolation                 |
| Block cloud metadata endpoints at the host                    | Prevent credential theft through the metadata service |
| Use a dedicated API key with a spend cap and alerts           | The genome process holds the key                      |
| Keep `SINGULARIS_SIGNING_KEY` outside the archive             | Stops a same-directory process from re-signing        |
| Read `diff.patch` for every genome you keep                   | Look for process, network, file or environment APIs   |
| Re-evaluate promoted genomes on fresh tasks                   | Detect overfitting to the search                      |
| Keep meta traces (`runs/<exp>/meta/`)                         | Audit why each change was made                        |
| Review meta prompt variants before trusting them              | They steer self-modification                          |
| Do not use evolved genomes outside the sandbox without review | They are unreviewed code                              |

## Failure modes to watch for in results

| Failure mode          | Signal                                                                            |
| --------------------- | --------------------------------------------------------------------------------- |
| Reward hacking        | High train score, flags in results, special-casing visible in diffs               |
| Benchmark overfitting | Train gains that vanish on held-out and fresh                                     |
| Cost drift            | Mean tokens rising in `lineage` or the dashboard                                  |
| Invalid child streak  | Many `invalid` rows; the meta prompt or focus may be steering badly               |
| Noisy comparison      | Confidence interval includes zero; add tasks or trials before concluding anything |
