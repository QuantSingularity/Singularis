import sys

import pytest
from backend.core.sandbox import (
    SandboxConfig,
    SandboxViolation,
    resolve_in_workspace,
    run_command,
)


def test_path_inside_workspace(tmp_path):
    assert (
        resolve_in_workspace(tmp_path, "a/b.txt") == tmp_path.resolve() / "a" / "b.txt"
    )


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "a/../../x", "", "a\x00b"])
def test_path_escape_rejected(tmp_path, bad):
    with pytest.raises(SandboxViolation):
        resolve_in_workspace(tmp_path, bad)


def test_symlink_escape_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(SandboxViolation):
        resolve_in_workspace(root, "link/file.txt")


def test_run_command_captures_output(tmp_path):
    result = run_command(
        [sys.executable, "-c", "print('hi')"], tmp_path, SandboxConfig()
    )
    assert (
        result.returncode == 0
        and result.stdout.strip() == "hi"
        and not result.timed_out
    )


def test_timeout_kills_process(tmp_path):
    result = run_command(
        [sys.executable, "-c", "while True: pass"], tmp_path, SandboxConfig(timeout_s=1)
    )
    assert result.timed_out


def test_output_is_clipped(tmp_path):
    cfg = SandboxConfig(max_output_chars=100)
    result = run_command([sys.executable, "-c", "print('x' * 5000)"], tmp_path, cfg)
    assert len(result.stdout) < 200 and "truncated" in result.stdout


def test_environment_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "abc")
    code = "import os; print(os.environ.get('SECRET_TOKEN'))"
    result = run_command([sys.executable, "-c", code], tmp_path, SandboxConfig())
    assert result.stdout.strip() == "None"


def test_config_env_is_passed(tmp_path):
    cfg = SandboxConfig(env={"FOO": "bar"})
    result = run_command(
        [sys.executable, "-c", "import os; print(os.environ['FOO'])"], tmp_path, cfg
    )
    assert result.stdout.strip() == "bar"


def test_config_json_round_trip():
    cfg = SandboxConfig(timeout_s=5, env={"A": "1"})
    assert SandboxConfig.from_json(cfg.to_json()) == cfg
