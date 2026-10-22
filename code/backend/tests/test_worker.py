import json

from backend.core import worker
from backend.core.sandbox import SandboxConfig
from testkit import FIZZ, solving_script, write_script


def run_worker(tmp_path, llm, extra=()):
    genome = tmp_path / "genome"
    genome.mkdir()
    import shutil

    from backend.evolution.evolve import BUILTIN_GENOME

    shutil.copytree(BUILTIN_GENOME, genome, dirs_exist_ok=True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    task_file = tmp_path / "task.txt"
    task_file.write_text(FIZZ.prompt)
    out = tmp_path / "out.json"
    argv = [
        "--genome",
        str(genome),
        "--workspace",
        str(workspace),
        "--task-file",
        str(task_file),
        "--out",
        str(out),
        "--llm",
        llm,
        "--sandbox-json",
        SandboxConfig().to_json(),
        *extra,
    ]
    return worker.main(argv), out, workspace


def test_worker_runs_a_scripted_solution(tmp_path):
    llm = write_script(tmp_path, "s.json", solving_script())
    code, out, workspace = run_worker(tmp_path, llm)
    assert code == 0
    assert (workspace / "solution.py").is_file()
    assert json.loads(out.read_text())


def test_worker_reports_a_bad_task_file(tmp_path):
    llm = write_script(tmp_path, "s.json", solving_script())
    _code, _out, _ = run_worker(tmp_path, llm)
    (tmp_path / "task.txt").unlink()
    argv = [
        "--genome",
        str(tmp_path / "genome"),
        "--workspace",
        str(tmp_path / "ws"),
        "--task-file",
        str(tmp_path / "task.txt"),
        "--out",
        str(tmp_path / "out2.json"),
        "--llm",
        llm,
        "--sandbox-json",
        SandboxConfig().to_json(),
    ]
    assert worker.main(argv) != 0 or json.loads((tmp_path / "out2.json").read_text())
