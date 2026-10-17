import pytest
from testkit import write_script as _write_script


@pytest.fixture(autouse=True)
def isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SINGULARIS_LOG_DIR", str(tmp_path / "logs"))


@pytest.fixture
def write_script(tmp_path):
    return lambda name, steps: _write_script(tmp_path, name, steps)
