# Safety and threat model

A self-modifying agent runs code that no human has reviewed. Treat every candidate genome and every task workspace
as untrusted. This document states what is protected, how, and how well that has been verified.

## Threat model

| Threat                                           | Mitigation                                                                                                 | Residual risk                                                                 |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Agent code exhausts CPU, memory, disk or output  | rlimits, wall clock kill of the process group, output clipping                                             | Limits are per process; a container adds a hard cap                           |
| Agent writes outside its workspace               | Resolved path checks in file tools, symlink escapes rejected                                               | `run_python` code can write anywhere the OS user can                          |
| Agent steals the API key                         | Key goes only to the worker; tool subprocesses get a scrubbed environment                                  | The genome runs in the worker process, which holds the key; use a capped key  |
| Agent calls out to the network                   | Container stack: internal network plus an allowlist proxy                                                  | Process-only mode has no network control                                      |
| Agent edits or reads the hidden tests            | Tests are written after the agent finishes, into a separate copy; repository tests are reset to base first | Same-interpreter evaluator can be attacked by obfuscated code                 |
| Agent forges a result                            | Per-run nonce, static tamper scan, signed records                                                          | A determined adversary can evade the scan; see below                          |
| Agent raises its own budget                      | Budgets wrap the model client outside the genome; the worker is killed on timeout                          | The genome shares a process with the wrapper                                  |
| Agent breaks the interface or ships odd files    | File policy, compile, import and contract validation before any evaluation                                 | None known for what is checked                                                |
| Meta prompt drifts toward dangerous instructions | Validator requires placeholders, formats, length cap; evaluation and budgets are outside its reach         | The template can still say unwise things inside those limits; review variants |
| Stored results change after the fact             | Signed records and `verify`                                                                                | Same-user processes that can read the key can re-sign                         |
| Dashboard injects markup from agent text         | Everything rendered with `textContent`                                                                     | None known                                                                    |
| Dashboard exposed to the network                 | Loopback only unless `--allow-remote`; three fixed routes                                                  | Remote mode shows diffs and notes to anyone who can reach it                  |

## Controls in the framework

| Control              | Where                     | Behavior                                                                            |
| -------------------- | ------------------------- | ----------------------------------------------------------------------------------- |
| rlimits and timeouts | `core/sandbox.py`         | Address space, CPU seconds and file size per process; process group kill on timeout |
| Scrubbed environment | `core/sandbox.py`         | Only `PATH`, `HOME`, `LANG`, Python flags and explicit values reach a subprocess    |
| Path confinement     | `core/sandbox.py`         | `resolve_in_workspace` rejects escapes and symlink tricks                           |
| Budgets              | `ai_models/llm.py`        | Token and call limits around the model client                                       |
| Genome validation    | `evolution/evolve.py`     | Types, size, no symlinks, compile, import and signature checks in a subprocess      |
| Integrity scan       | `evaluation/integrity.py` | AST rules below; strict mode scores 0                                               |
| Signed records       | `evolution/signing.py`    | HMAC over code hash, scores and result files                                        |
| Manifest             | `evolution/manifest.py`   | Warns on resume if the engine or tasks changed                                      |
| Human gate           | `cli.py export`           | Shows the diff and asks before copying a genome out                                 |
| Localhost server     | `evolution/serve.py`      | Loopback only, three routes, no directory listing                                   |

### Integrity scan rules

| Rule                 | Flags                                                                                                      |
| -------------------- | ---------------------------------------------------------------------------------------------------------- |
| Suspicious imports   | `atexit`, `ctypes`, `gc`, `socket`, `subprocess`, `multiprocessing`, `signal`, `builtins`, `importlib`     |
| Process tricks       | `os._exit`, `os.kill`, `os.system`, `os.popen`, `sys._getframe`, module-level `sys.exit`, `exit` or `quit` |
| Dynamic code         | `eval`, `exec`, `__import__`                                                                               |
| Evaluator references | String constants mentioning `hidden_tests` or `_runner`                                                    |
| Patching             | Assigning into `unittest` or `builtins`                                                                    |

| Mode               | Behavior                                                        |
| ------------------ | --------------------------------------------------------------- |
| `strict` (default) | A flagged solution scores 0 and the next generation is told why |
| `warn`             | Flags are recorded, the score is kept                           |
| `off`              | No scan                                                         |

Repository tasks use a relaxed scan (changed files only, no import or dynamic code rules).

## What process-level isolation does not do

| Gap                                                 | Consequence                                                                                                         |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| No network isolation                                | Subprocess limits cannot block sockets                                                                              |
| No filesystem isolation                             | Agent code can read anything the OS user can read                                                                   |
| Evaluator shares an interpreter with candidate code | Obfuscated code could try to forge a result; held-out and fresh tasks, trace review and spot checks are the defense |
| Signed records are tamper evidence, not prevention  | A process that can read the key (file or environment) can re-sign; keep the key outside the sandbox                 |
| The genome sees the API key                         | It runs in the worker process; use a dedicated key with a spend cap                                                 |

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
