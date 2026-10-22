"""Frontend tests."""

import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from backend.evolution.archive import Archive
from backend.evolution.serve import make_server
from testkit import good_meta_script, make_evolver

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"


def _jsdom_available() -> bool:
    if (
        shutil.which("node") is None
        or not (FRONTEND / "node_modules" / "jsdom").is_dir()
    ):
        return False
    return (
        subprocess.run(
            ["node", "-e", "require('jsdom')"], cwd=FRONTEND, capture_output=True
        ).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(
    not _jsdom_available(), reason="needs node and jsdom (cd frontend && npm install)"
)


def test_render_checks_pass():
    result = subprocess.run(
        ["node", "test/render.js"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "render checks passed" in result.stdout


class Page:
    def __init__(self, url: str):
        self.proc = subprocess.Popen(
            ["node", "test/live.js", url],
            cwd=FRONTEND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line.strip())
        self.lines.put("<eof>")

    def expect(self, prefix: str, timeout: float = 30) -> str:
        line = self.lines.get(timeout=timeout)
        assert line.startswith(prefix), f"expected {prefix!r}, page said {line!r}"
        return line

    def send(self, command: str):
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()


def serve_in_thread(root, port=0):
    server = make_server(root, port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop(server):
    server.shutdown()
    server.server_close()


def test_live_refresh_follows_the_archive_keeps_selection_and_recovers(tmp_path):
    make_evolver(tmp_path, good_meta_script()).run()
    root = tmp_path / "exp"
    server = serve_in_thread(root)
    port = server.server_address[1]
    page = Page(f"http://127.0.0.1:{port}")
    try:
        ready = page.expect("READY")
        assert "rows=2" in ready and "selected=a0001" in ready

        archive = Archive(root)
        archive.add("a0002", "a0001", 2, "valid", "added while the page is open")
        archive.update("a0002", train_score=0.5, fitness=0.5)
        page.send("go")
        updated = page.expect("UPDATED")
        assert "rows=3" in updated and "selected=a0001" in updated

        stop(server)
        page.send("stop")
        assert "rows=3" in page.expect("PAUSED")

        server = serve_in_thread(root, port)
        page.send("restart")
        page.expect("RECOVERED")
        page.expect("DONE")
        assert page.proc.wait(timeout=20) == 0
    finally:
        page.close()
        stop(server)
