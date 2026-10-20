"""A local metering proxy: the only place the real API key lives, and the only source of token counts.

Genome code runs in a worker process that can be rewritten by the agent. Anything that process reports about
itself (token counts, budgets) or holds (an API key) is under the agent's influence. The meter moves both
out of reach:

- The framework process starts the meter and keeps the real key in it. A worker receives a loopback URL with
  an unguessable per-run path and a placeholder key, so there is no secret in its environment to read.
- Every model call passes through the meter, which adds up the token usage the API itself reports and
  refuses calls once the run's budget is spent. The runner records these numbers, not the genome's own.
- On Linux the framework process marks itself non-dumpable, so a same-user child cannot read the key out of
  /proc/<pid>/environ or /proc/<pid>/mem.

Only non-streaming `POST /v1/messages` is supported, which is what `AnthropicClient` uses.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_UPSTREAM = "https://api.anthropic.com"
PLACEHOLDER_KEY = "metered"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
UPSTREAM_TIMEOUT_S = 300
API_VERSION = "2023-06-01"
BUDGET_MARKER = "singularis_budget_exhausted"


@dataclass
class RunUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class _Run:
    max_tokens: int
    max_calls: int
    usage: RunUsage


def harden_process() -> bool:
    """Make this process non-dumpable (Linux), so same-user children cannot read its memory or environment."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        return libc.prctl(4, 0, 0, 0, 0) == 0  # PR_SET_DUMPABLE = 4
    except Exception:
        return False


def load_api_key(explicit: str | None = None) -> str | None:
    """An explicit key wins, then the file named by ANTHROPIC_API_KEY_FILE, then ANTHROPIC_API_KEY.

    The file form is preferred: an environment variable is also visible to anything that can read this
    process's environment block."""
    if explicit:
        return explicit
    key_file = os.environ.get("ANTHROPIC_API_KEY_FILE")
    if key_file:
        return Path(key_file).read_text().strip() or None
    return os.environ.get("ANTHROPIC_API_KEY") or None


class Meter:
    def __init__(
        self,
        upstream: str | None = None,
        api_key: str | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self.upstream = (
            upstream or os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_UPSTREAM
        ).rstrip("/")
        self._key = load_api_key(api_key)
        self._runs: dict[str, _Run] = {}
        self._lock = threading.Lock()
        self.hardened = harden_process()
        meter = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep the console quiet
                pass

            def _send(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _error(self, status: int, kind: str, message: str) -> None:
                self._send(
                    status,
                    json.dumps(
                        {
                            "type": "error",
                            "error": {"type": kind, "message": message},
                        }
                    ).encode(),
                )

            def do_POST(self) -> None:
                parts = self.path.split("?", 1)[0].strip("/").split("/")
                if (
                    len(parts) != 4
                    or parts[0] != "r"
                    or parts[2:] != ["v1", "messages"]
                ):
                    return self._error(404, "not_found_error", "unsupported path")
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_REQUEST_BYTES:
                    return self._error(413, "request_too_large", "request too large")
                body = self.rfile.read(length)
                status, payload = meter._handle(parts[1], body)
                self._send(status, payload)

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    # -- lifecycle -----------------------------------------------------------------------------------
    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def open_run(self, max_tokens: int, max_calls: int) -> str:
        run_id = secrets.token_urlsafe(24)
        with self._lock:
            self._runs[run_id] = _Run(max_tokens, max_calls, RunUsage())
        return run_id

    def close_run(self, run_id: str) -> RunUsage:
        with self._lock:
            run = self._runs.pop(run_id, None)
        return run.usage if run else RunUsage()

    def base_url(self, run_id: str) -> str:
        return f"http://127.0.0.1:{self.port}/r/{run_id}"

    # -- request handling ----------------------------------------------------------------------------
    def _handle(self, run_id: str, body: bytes) -> tuple[int, bytes]:
        def fail(status: int, kind: str, message: str) -> tuple[int, bytes]:
            return (
                status,
                json.dumps(
                    {"type": "error", "error": {"type": kind, "message": message}}
                ).encode(),
            )

        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return fail(404, "not_found_error", "unknown run")
            if run.usage.calls >= run.max_calls:
                return fail(
                    403, "permission_error", f"{BUDGET_MARKER}: call budget spent"
                )
            if run.usage.tokens >= run.max_tokens:
                return fail(
                    403, "permission_error", f"{BUDGET_MARKER}: token budget spent"
                )
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            return fail(400, "invalid_request_error", "body is not JSON")
        if isinstance(request, dict) and request.get("stream"):
            return fail(400, "invalid_request_error", "streaming is not supported")
        if not self._key:
            return fail(500, "api_error", "the meter has no API key configured")

        upstream = urllib.request.Request(
            self.upstream + "/v1/messages",
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "anthropic-version": API_VERSION,
                "x-api-key": self._key,
            },
        )
        try:
            with urllib.request.urlopen(upstream, timeout=UPSTREAM_TIMEOUT_S) as reply:
                status, payload = reply.status, reply.read()
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return fail(502, "api_error", f"upstream unreachable: {exc}")

        self._record(run_id, payload)
        return status, payload

    def _record(self, run_id: str, payload: bytes) -> None:
        try:
            usage = json.loads(payload).get("usage") or {}
        except (json.JSONDecodeError, AttributeError):
            usage = {}
        read = lambda name: int(usage.get(name) or 0)  # noqa: E731
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.usage.calls += 1
            run.usage.input_tokens += (
                read("input_tokens")
                + read("cache_creation_input_tokens")
                + read("cache_read_input_tokens")
            )
            run.usage.output_tokens += read("output_tokens")


_METER: Meter | None = None
_METER_LOCK = threading.Lock()


def get_meter() -> Meter:
    """The process-wide meter, started on first use."""
    global _METER
    with _METER_LOCK:
        if _METER is None:
            _METER = Meter()
        return _METER


def set_meter(meter: Meter | None) -> None:
    """Install a specific meter (tests and custom gateways)."""
    global _METER
    with _METER_LOCK:
        _METER = meter


def worker_env(meter: Meter, run_id: str) -> dict[str, str]:
    """Everything a worker needs to reach the model, and nothing that is a secret."""
    return {
        "ANTHROPIC_BASE_URL": meter.base_url(run_id),
        "ANTHROPIC_API_KEY": PLACEHOLDER_KEY,
        "NO_PROXY": "127.0.0.1,localhost",
    }
