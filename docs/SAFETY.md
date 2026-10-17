# Safety and threat model

Self-modifying agents run code that no human has reviewed. Treat every candidate genome and every task
workspace as untrusted.

## What the framework does

- Runs each genome in a separate worker process with memory, CPU, and file size rlimits and a wall-clock kill
  of the whole process group.
- Scrubs the environment: the worker receives only `PATH`, `HOME`, `PYTHONPATH`, and, for Anthropic runs,
  the API key and proxy variables. Tools the agent calls run with an even smaller environment and **no** API key.
- Confines file tools to the workspace (resolved paths, symlink escapes rejected).
- Enforces token and call budgets outside the genome and caps tool output size.
- Validates candidate genomes (file types, size, no symlinks, compile, import, contract) before any evaluation.
- Writes only inside the archive directory. Promotion to anywhere else is a manual `export` after reading the diff.
- Keeps hidden tests outside the agent workspace and writes them only after the agent finishes.
- Scans agent-written code for evaluator tampering (`backend/evaluation/integrity.py`): suspicious imports
  (`atexit`, `ctypes`, `subprocess`, `socket`, and similar), `os._exit` and `os.kill`, module-level exits,
  `eval`, `exec` and `__import__`, patching `unittest`, and references to the hidden tests. In `strict` mode a
  flagged solution scores zero. The scan is heuristic and can produce false positives; use `--integrity warn`
  to record flags without penalizing.
- Signs every evaluated agent (`signing.py`): an HMAC over the code hash, scores, and result files. Use
  `singularis verify` to detect edits made after the fact. Set `SINGULARIS_SIGNING_KEY` to keep the key out of the
  archive directory; it is never passed to workers.
- Binds the meta prompt to a frozen validator: variants must keep the required placeholders and cannot change
  evaluation, selection, or budgets, which live outside the mutable surfaces.
- The live server (`singularis serve`) exposes only `/`, `/report.json` and `/healthz`, binds to loopback, and
  refuses other addresses without `--allow-remote`. The frontend renders report content as text only, so
  agent-written notes and diffs cannot inject markup.

## What process-level isolation does not do

- **No network isolation.** Subprocess limits cannot block sockets.
- **No filesystem isolation.** A script run through `run_python` can read any file the OS user can read.
- **Evaluator integrity is best effort.** Candidate code and the test runner share an interpreter. A nonce
  makes casual forgery hard, but code that reads `sys.argv` could forge a result. The integrity scan catches the
  obvious attempts, not obfuscated ones. Held-out and fresh tasks, trace review, and spot checks of high scoring
  agents are the practical defenses.
- **Signed records are tamper evidence, not tamper prevention.** They show that stored results changed after
  signing. A process running as the same OS user that can read the key file (or the parent's environment) could
  re-sign. Keep the key outside the sandbox and run the container stack to remove that path.
- **API key exposure to the genome.** The genome runs in a process that holds the key. Use a key with a hard
  spend limit and a dedicated workspace.

## The container stack (`infrastructure/`)

`docker-compose.yml` closes the network and filesystem gaps:

- The agent container is on an `internal: true` network with no route to the internet.
- The only exit is a Squid proxy (`squid.conf`) that allows HTTPS CONNECT to `api.anthropic.com:443` only.
- The worker gets the proxy variables. Tool subprocesses do not, so code the agent executes has no network.
- Read-only root filesystem, `/tmp` as tmpfs, all capabilities dropped, `no-new-privileges`, 256 process cap,
  8 GB memory and 4 CPU limits. Only `runs/` is writable and mounted.

Run it with `scripts/docker_run.sh <singularis command>`.

**What has been verified, and what has not.**

Verified (in the environment where this was authored, which had no Docker daemon):

- `docker-compose.yml` parses and resolves with the official Docker Compose binary; `Dockerfile` passes hadolint.
- `squid.conf` was run in a real squid. `api.anthropic.com:443` tunnels; another host, plain HTTP, a lookalike
  domain (`api.anthropic.com.attacker.test`) and the wrong port (`:8443`) are all refused with 403. This testing
  found and fixed a real bug: redirecting squid's logs to `/dev/stderr` made the proxy fail to start.
- The pipeline (eval, evolve, verify) runs as a non-root user against a source tree it cannot write to, writing
  only to `runs/` and `/tmp`, which is what the read-only container requires.
- `singularis isolation-check` is unit tested against fake proxies (strict and permissive), open and closed
  routes, a leaky tool configuration, and run against the real squid. It correctly reported open internet
  access in the unrestricted environment where it was tried.
- The compose file maps the container user to your host uid and gid (`LOCAL_UID`, `LOCAL_GID`) so `runs/` is
  writable; `scripts/docker_run.sh` and `scripts/verify_docker.sh` set them.

Not verified: building the image, starting the containers, the internal network actually having no route out,
and the read-only root, dropped capabilities and `no-new-privileges` taking effect under Docker. Run
`scripts/verify_docker.sh` once on a machine with Docker. It builds the stack, runs `singularis isolation-check`
inside the container (proxy allowlist, no direct egress from tool code, no secrets in tool environments, read-only
root, non-root user, no capabilities, `no-new-privileges`, writable `runs/`), validates the suite, and runs a
scripted agent end to end under those limits.

One residual channel to know about: tool code can open a connection to the proxy itself, which allows only the
model API host. Tools do not receive the API key, so this cannot authenticate, but it is the only route out.

## Hardening checklist for real experiments

1. Use the container stack, or an equivalent VM, with no host mounts except the archive directory.
2. Block cloud metadata endpoints at the host.
3. Use a dedicated API key with a monthly cap and alerting.
4. Keep a human approval step before any evolved genome is used outside the sandbox.
5. Read `diff.patch` for every genome you intend to keep, with particular attention to anything touching
   process, network, file, or environment APIs.
6. Re-evaluate promoted genomes on fresh held-out tasks the search never saw.
7. Retain meta traces (`runs/<exp>/meta/`) so the reasoning behind each modification can be audited.

## Failure modes to watch for in results

- **Reward hacking**: the agent learns to pass tests without solving tasks (special-casing, probing the
  environment). Compare train and held-out gaps and read traces.
- **Overfitting to the benchmark**: gains on train that vanish on held-out.
- **Cost drift**: genomes that quietly raise token use. The fitness penalty is small by design, so also track
  mean tokens in `lineage` or the viewer.
