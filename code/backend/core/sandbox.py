from __future__ import annotations

import functools
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from backend.core.text import clip

_LAUNCHER = (
    "import json, os, sys\n"
    "limits = json.loads(sys.argv[1])\n"
    "try:\n"
    "    import resource\n"
    "    for name, value in limits.items():\n"
    "        try:\n"
    "            resource.setrlimit(getattr(resource, name), (value, value))\n"
    "        except (ValueError, OSError, AttributeError):\n"
    "            pass\n"
    "except ImportError:\n"
    "    pass\n"
    "os.execvp(sys.argv[2], sys.argv[2:])\n"
)


class SandboxViolation(Exception):
    pass


@dataclass(frozen=True)
class SandboxConfig:
    timeout_s: float = 30.0
    memory_mb: int = 1024
    cpu_s: int = 60
    max_file_mb: int = 64
    max_output_chars: int = 20_000
    max_procs: int = 512
    network: bool = True
    env: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, payload: str) -> "SandboxConfig":
        return cls(**json.loads(payload))


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float


def resolve_in_workspace(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise SandboxViolation("invalid path")
    root_resolved = Path(root).resolve()
    candidate = (root_resolved / relative).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise SandboxViolation(f"path escapes workspace: {relative}")
    return candidate


@functools.lru_cache(maxsize=1)
def network_isolation_available() -> bool:
    if os.name != "posix" or not shutil.which("unshare"):
        return False
    try:
        probe = subprocess.run(
            ["unshare", "-rn", "true"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _limits(config: SandboxConfig) -> dict[str, int]:
    return {
        "RLIMIT_AS": config.memory_mb * 1024 * 1024,
        "RLIMIT_CPU": config.cpu_s,
        "RLIMIT_FSIZE": config.max_file_mb * 1024 * 1024,
        "RLIMIT_NPROC": config.max_procs,
    }


def build_argv(argv: list[str], config: SandboxConfig) -> list[str]:
    if os.name != "posix":
        return list(argv)
    wrapped = [sys.executable, "-c", _LAUNCHER, json.dumps(_limits(config)), *argv]
    if not config.network and network_isolation_available():
        return ["unshare", "-rn", "--", *wrapped]
    return wrapped


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


def run_command(
    argv: list[str],
    cwd: Path,
    config: SandboxConfig,
    stdin_text: str | None = None,
    pass_fds: Sequence[int] = (),
) -> ExecResult:
    cwd = Path(cwd)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    env.update(config.env)
    posix = os.name == "posix"
    started = time.monotonic()
    proc = subprocess.Popen(
        build_argv(argv, config),
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=posix,
        pass_fds=tuple(pass_fds) if posix else (),
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(input=stdin_text, timeout=config.timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        stdout, stderr = proc.communicate()
    return ExecResult(
        returncode=proc.returncode,
        stdout=clip(stdout or "", config.max_output_chars),
        stderr=clip(stderr or "", config.max_output_chars),
        timed_out=timed_out,
        duration_s=round(time.monotonic() - started, 3),
    )
