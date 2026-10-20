from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from backend.core.text import clip


class SandboxViolation(Exception):
    pass


@dataclass(frozen=True)
class SandboxConfig:
    timeout_s: float = 30.0
    memory_mb: int = 1024
    cpu_s: int = 60
    max_file_mb: int = 64
    max_output_chars: int = 20_000
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


def _preexec(config: SandboxConfig):
    def apply() -> None:
        import resource

        limits = [
            (resource.RLIMIT_AS, config.memory_mb * 1024 * 1024),
            (resource.RLIMIT_CPU, config.cpu_s),
            (resource.RLIMIT_FSIZE, config.max_file_mb * 1024 * 1024),
        ]
        for kind, value in limits:
            try:
                resource.setrlimit(kind, (value, value))
            except (ValueError, OSError):
                pass

    return apply


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
    """Run a command with resource limits and a scrubbed environment.

    `stdin_text` is delivered on stdin, which is how secrets (a nonce, test source) reach a child without
    appearing in argv or the environment. `pass_fds` keeps the listed file descriptors open in the child.
    """
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
        argv,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=posix,
        preexec_fn=_preexec(config) if posix else None,
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
