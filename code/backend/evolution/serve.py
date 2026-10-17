from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend.evolution.report import build_report

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def make_server(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    frontend_dir: Path | None = None,
    allow_remote: bool = False,
) -> ThreadingHTTPServer:
    """Serve the lineage viewer and a live report.json for an experiment root.

    Only three fixed routes exist (/, /report.json, /healthz). The report contains agent-written text
    and code diffs, so the server binds to loopback unless allow_remote is set explicitly.
    """
    if host not in LOOPBACK and not allow_remote:
        raise ValueError(
            "refusing to bind a non-loopback address without allow_remote=True"
        )
    index = Path(frontend_dir or FRONTEND_DIR) / "index.html"
    experiment_root = Path(root)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                if index.is_file():
                    self._send(200, index.read_bytes(), "text/html; charset=utf-8")
                else:
                    self._send(404, b"frontend/index.html not found", "text/plain")
            elif path == "/report.json":
                body = json.dumps(build_report(experiment_root)).encode()
                self._send(200, body, "application/json")
            elif path == "/healthz":
                self._send(200, b"ok", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, format: str, *args) -> None:
            pass

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    root: Path, host: str = "127.0.0.1", port: int = 8765, allow_remote: bool = False
) -> None:
    server = make_server(root, host, port, allow_remote=allow_remote)
    print(
        f"serving {root} at http://{host}:{server.server_address[1]}/  (Ctrl+C to stop)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
