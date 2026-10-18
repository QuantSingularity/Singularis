# infrastructure

A network-isolated runtime for running experiments with a real API key.

## Files

| File                 | Purpose                                                                                |
| -------------------- | -------------------------------------------------------------------------------------- |
| `Dockerfile`         | Python 3.12 slim image with git, non-root user `sing`, editable install, smoke fixture |
| `docker-compose.yml` | Two services and two networks (see below)                                              |
| `squid.conf`         | Egress allowlist: HTTPS `CONNECT` to `api.anthropic.com:443` only                      |
| `smoke/solve.json`   | Scripted agent run used to prove the stack works under its limits                      |

## Services and networks

| Name           | Kind    | Role                                                                                                                                           |
| -------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `singularis`   | Service | Runs the CLI as your host uid and gid, read-only root, `/tmp` as tmpfs, capabilities dropped, `no-new-privileges`, 256 processes, 8 GB, 4 CPUs |
| `egress-proxy` | Service | Squid, the only service that can reach the internet                                                                                            |
| `sandbox`      | Network | `internal: true`, no route to the internet; both services attach                                                                               |
| `egress`       | Network | Normal network; only the proxy attaches                                                                                                        |

## Commands

| Goal                           | Command                                                                                                       |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| Run any command in the stack   | `scripts/docker_run.sh evolve --root runs/exp1 --iterations 5`                                                |
| Verify the stack               | `scripts/verify_docker.sh`                                                                                    |
| Check the proxy log            | `docker compose -f infrastructure/docker-compose.yml exec egress-proxy tail -f /var/log/squid/access.log`     |
| Validate the compose file only | `ANTHROPIC_API_KEY= LOCAL_UID=1000 LOCAL_GID=1000 docker compose -f infrastructure/docker-compose.yml config` |

## What `verify_docker.sh` proves

| Step              | Proves                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Build             | The image builds                                                                                                                                                    |
| `isolation-check` | Proxy allowlist, no direct egress from tool code, no secrets in tool environments, read-only root, non-root, no capabilities, `no-new-privileges`, writable `runs/` |
| `validate-suite`  | The benchmark works inside the container                                                                                                                            |
| Scripted `eval`   | A worker runs a task end to end under all limits                                                                                                                    |

## Status

| Item                              | Status                                                                       |
| --------------------------------- | ---------------------------------------------------------------------------- |
| Compose file                      | Validated with the official Compose binary                                   |
| Dockerfile                        | hadolint clean                                                               |
| `squid.conf`                      | Tested against a real squid: allowed host tunnels, four other probes refused |
| Image build and container runtime | Not verified in the authoring environment; run `scripts/verify_docker.sh`    |

## Notes

| Topic            | Note                                                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| API key          | Optional in compose; scripted runs need none. Real runs pass `ANTHROPIC_API_KEY` from your shell                                |
| Host permissions | `LOCAL_UID` and `LOCAL_GID` map the container user to you so `./runs` is writable; the scripts set them                         |
| Proxy logs       | Squid writes to its default log files, not to stdout, because redirecting to `/dev/stderr` stopped squid from starting          |
| Residual channel | Tool code can reach the proxy, which allows only the model API host; tools have no key                                          |
| Repository tasks | The image includes git so test patches can be applied; cloning repositories belongs on the host (`scripts/prepare_swebench.sh`) |
