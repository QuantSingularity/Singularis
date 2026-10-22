from __future__ import annotations

import os
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from backend.core.sandbox import SandboxConfig, run_command

ALLOWED_TARGET = "api.anthropic.com:443"
BLOCKED_TARGETS = (
    "example.com:443",
    "api.anthropic.com:8443",
    "api.anthropic.com.attacker.test:443",
)
SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "https_proxy",
    "http_proxy",
    "SINGULARIS_SIGNING_KEY",
)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def connect_status(proxy_url: str, target: str, timeout: float = 8.0) -> int:
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"proxy url needs a host and port: {proxy_url!r}")
    with socket.create_connection(
        (parsed.hostname, parsed.port), timeout=timeout
    ) as conn:
        conn.settimeout(timeout)
        conn.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        reply = conn.recv(512).decode("latin1")
    return int(reply.split("\r\n", 1)[0].split()[1])


def check_proxy_policy(proxy_url: str | None) -> list[Check]:
    if not proxy_url:
        return [
            Check(
                "proxy configured",
                False,
                "no proxy url (set HTTPS_PROXY or pass --proxy)",
            )
        ]
    checks: list[Check] = []
    try:
        status = connect_status(proxy_url, ALLOWED_TARGET)
        checks.append(
            Check(
                "proxy allows the model API",
                status == 200,
                f"CONNECT {ALLOWED_TARGET} -> {status}",
            )
        )
    except (OSError, ValueError, IndexError) as exc:
        return [Check("proxy reachable", False, f"{type(exc).__name__}: {exc}")]
    leaked = []
    for target in BLOCKED_TARGETS:
        try:
            status = connect_status(proxy_url, target)
        except (OSError, ValueError, IndexError):
            continue
        if status == 200:
            leaked.append(target)
    checks.append(
        Check(
            "proxy refuses everything else",
            not leaked,
            (
                "refused all probes"
                if not leaked
                else "proxy allowed: " + ", ".join(leaked)
            ),
        )
    )
    return checks


def check_direct_egress_blocked(
    target: tuple[str, int] = ("1.1.1.1", 443), timeout_s: float = 4.0
) -> Check:
    code = (
        "import socket, sys\n"
        f"s = socket.socket(); s.settimeout({timeout_s})\n"
        f"try:\n    s.connect(({target[0]!r}, {target[1]}))\nexcept OSError:\n    sys.exit(3)\n"
        "sys.exit(0)\n"
    )
    result = run_command(
        [sys.executable, "-c", code],
        Path(tempfile.gettempdir()),
        SandboxConfig(timeout_s=timeout_s + 6),
    )
    reachable = result.returncode == 0 and not result.timed_out
    return Check(
        "tool code has no direct internet",
        not reachable,
        (
            f"connected to {target[0]}:{target[1]}"
            if reachable
            else f"cannot reach {target[0]}:{target[1]}"
        ),
    )


def check_tool_environment(config: SandboxConfig | None = None) -> Check:
    names = ", ".join(repr(n) for n in SECRET_ENV_NAMES)
    code = f"import os\nprint(','.join(n for n in ({names},) if n in os.environ))\n"
    result = run_command(
        [sys.executable, "-c", code],
        Path(tempfile.gettempdir()),
        config or SandboxConfig(),
    )
    leaked = [n for n in result.stdout.strip().split(",") if n]
    return Check(
        "tool environment has no secrets or proxy",
        result.returncode == 0 and not leaked,
        "clean" if not leaked else "leaked: " + ", ".join(leaked),
    )


def root_is_readonly(mounts_text: str) -> bool | None:
    root_options = None
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/":
            root_options = parts[3].split(",")
    return None if root_options is None else "ro" in root_options


def proc_status_flag(status_text: str, key: str) -> str | None:
    for line in status_text.splitlines():
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return None


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def check_runs_writable(runs_dir: Path) -> Check:
    try:
        Path(runs_dir).mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=runs_dir):
            pass
    except OSError as exc:
        return Check(
            "runs directory is writable", False, f"{type(exc).__name__}: {exc}"
        )
    return Check("runs directory is writable", True, str(runs_dir))


def container_checks() -> list[Check]:
    checks: list[Check] = []
    mounts = _read("/proc/mounts")
    readonly = root_is_readonly(mounts) if mounts else None
    checks.append(
        Check(
            "root filesystem is read-only",
            bool(readonly),
            "unknown (no /proc/mounts)" if readonly is None else f"ro={readonly}",
        )
    )
    checks.append(
        Check("not running as root", os.geteuid() != 0, f"uid {os.geteuid()}")
    )
    status = _read("/proc/self/status") or ""
    effective = proc_status_flag(status, "CapEff")
    checks.append(
        Check(
            "all capabilities dropped",
            effective is not None and int(effective, 16) == 0,
            f"CapEff={effective}",
        )
    )
    no_new_privs = proc_status_flag(status, "NoNewPrivs")
    checks.append(
        Check(
            "no-new-privileges is set",
            no_new_privs == "1",
            f"NoNewPrivs={no_new_privs}",
        )
    )
    return checks


def run_isolation_checks(
    proxy_url: str | None, runs_dir: Path, container: bool = True
) -> list[Check]:
    checks = check_proxy_policy(proxy_url)
    checks.append(check_direct_egress_blocked())
    checks.append(check_tool_environment())
    checks.append(check_runs_writable(runs_dir))
    if container:
        checks.extend(container_checks())
    return checks
