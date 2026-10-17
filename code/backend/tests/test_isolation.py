import socket
import socketserver
import threading

import pytest
from backend.cli import main
from backend.core.isolation import (
    check_direct_egress_blocked,
    check_proxy_policy,
    check_runs_writable,
    check_tool_environment,
    connect_status,
    proc_status_flag,
    root_is_readonly,
    run_isolation_checks,
)
from backend.core.sandbox import SandboxConfig


def start_proxy(allowed):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            request = self.request.recv(1024).decode("latin1")
            target = request.split()[1] if request.startswith("CONNECT") else ""
            ok = allowed is None or target in allowed
            self.request.sendall(
                b"HTTP/1.1 200 Connection established\r\n\r\n"
                if ok
                else b"HTTP/1.1 403 Forbidden\r\n\r\n"
            )

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def strict_proxy():
    server, url = start_proxy({"api.anthropic.com:443"})
    yield url
    server.shutdown()
    server.server_close()


@pytest.fixture
def open_proxy():
    server, url = start_proxy(None)
    yield url
    server.shutdown()
    server.server_close()


def by_name(checks):
    return {c.name: c for c in checks}


def test_connect_status_reads_the_proxy_answer(strict_proxy):
    assert connect_status(strict_proxy, "api.anthropic.com:443") == 200
    assert connect_status(strict_proxy, "example.com:443") == 403


def test_strict_proxy_passes_the_policy_checks(strict_proxy):
    checks = by_name(check_proxy_policy(strict_proxy))
    assert (
        checks["proxy allows the model API"].ok
        and checks["proxy refuses everything else"].ok
    )


def test_permissive_proxy_is_caught(open_proxy):
    check = by_name(check_proxy_policy(open_proxy))["proxy refuses everything else"]
    assert not check.ok and "example.com:443" in check.detail


def test_unreachable_or_missing_proxy_fails(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert not check_proxy_policy(f"http://127.0.0.1:{port}")[0].ok
    assert not check_proxy_policy(None)[0].ok


def test_direct_egress_check_detects_an_open_route_and_a_closed_one():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        open_port = listener.getsockname()[1]
        assert not check_direct_egress_blocked(("127.0.0.1", open_port), timeout_s=2).ok
    assert check_direct_egress_blocked(("127.0.0.1", open_port), timeout_s=2).ok


def test_tool_environment_is_scrubbed_even_when_the_parent_has_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    assert check_tool_environment().ok


def test_tool_environment_check_flags_a_leaky_configuration():
    check = check_tool_environment(SandboxConfig(env={"ANTHROPIC_API_KEY": "oops"}))
    assert not check.ok and "ANTHROPIC_API_KEY" in check.detail


def test_runs_directory_check(tmp_path):
    assert check_runs_writable(tmp_path / "runs").ok
    blocked = tmp_path / "file"
    blocked.write_text("x")
    assert not check_runs_writable(blocked / "sub").ok


def test_mount_and_status_parsing():
    mounts = "overlay / overlay ro,relatime 0 0\ntmpfs /tmp tmpfs rw 0 0\n"
    assert root_is_readonly(mounts) is True
    assert root_is_readonly("overlay / overlay rw,relatime 0 0\n") is False
    assert root_is_readonly("") is None
    status = "Name:\tpython\nCapEff:\t0000000000000000\nNoNewPrivs:\t1\n"
    assert proc_status_flag(status, "CapEff") == "0000000000000000"
    assert proc_status_flag(status, "NoNewPrivs") == "1"
    assert proc_status_flag(status, "Missing") is None


def test_full_run_without_container_checks(strict_proxy, tmp_path):
    names = {
        c.name
        for c in run_isolation_checks(strict_proxy, tmp_path / "runs", container=False)
    }
    assert (
        "root filesystem is read-only" not in names
        and "proxy allows the model API" in names
    )


def test_cli_exit_code_reflects_failures(open_proxy, tmp_path, capsys):
    code = main(
        [
            "isolation-check",
            "--proxy",
            open_proxy,
            "--runs",
            str(tmp_path / "runs"),
            "--skip-container-checks",
        ]
    )
    assert code == 1 and "FAIL proxy refuses everything else" in capsys.readouterr().out
