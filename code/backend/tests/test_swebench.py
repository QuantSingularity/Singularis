import json
import shutil
import subprocess

import pytest
from backend.cli import main
from backend.evaluation.evaluator import evaluate, validate_tasks
from backend.evaluation.integrity import changed_python_files, scan_workspace
from backend.evaluation.repo_eval import (
    IGNORED,
    apply_patch,
    parse_pytest_results,
    patch_paths,
)
from backend.evaluation.runner import RunConfig, run_task
from backend.evaluation.swebench import (
    SwebenchError,
    assign_split,
    load_instances,
    prepare_instance,
)
from backend.evaluation.tasks import load_tasks_from_dir
from backend.evolution.evolve import BUILTIN_GENOME

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BUGGY_OPS = "def average(values):\n    return sum(values) / len(values)\n\n\ndef total(values):\n    return sum(values)\n"
FIXED_OPS = (
    "def average(values):\n    if not values:\n        raise ValueError('average of empty sequence')\n"
    "    return sum(values) / len(values)\n\n\ndef total(values):\n    return sum(values)\n"
)
TESTS_V1 = (
    "from calc.ops import average, total\n\n\ndef test_average_basic():\n    assert average([2, 4]) == 3\n\n\n"
    "def test_total_basic():\n    assert total([1, 2, 3]) == 6\n"
)
TESTS_V2 = (
    TESTS_V1
    + "\n\ndef test_average_empty_raises():\n    import pytest\n    with pytest.raises(ValueError):\n        average([])\n"
)


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def git_out(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def swe_env(tmp_path):
    source = tmp_path / "src" / "acme" / "calc"
    (source / "calc").mkdir(parents=True)
    (source / "tests").mkdir()
    (source / "calc" / "__init__.py").write_text("")
    (source / "calc" / "ops.py").write_text(BUGGY_OPS)
    (source / "tests" / "test_ops.py").write_text(TESTS_V1)
    git(source, "init", "-q")
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", "base")
    base = git_out(source, "rev-parse", "HEAD").strip()
    (source / "calc" / "ops.py").write_text(FIXED_OPS)
    (source / "tests" / "test_ops.py").write_text(TESTS_V2)
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", "fix")
    head = git_out(source, "rev-parse", "HEAD").strip()
    instance = {
        "instance_id": "acme__calc-1",
        "repo": "acme/calc",
        "base_commit": base,
        "problem_statement": "average() of an empty list raises ZeroDivisionError. It should raise ValueError.",
        "patch": git_out(source, "diff", base, head, "--", "calc"),
        "test_patch": git_out(source, "diff", base, head, "--", "tests"),
        "FAIL_TO_PASS": json.dumps(["tests/test_ops.py::test_average_empty_raises"]),
        "PASS_TO_PASS": json.dumps(
            [
                "tests/test_ops.py::test_average_basic",
                "tests/test_ops.py::test_total_basic",
            ]
        ),
    }
    dataset = tmp_path / "data.jsonl"
    dataset.write_text(json.dumps(instance) + "\n")
    return {
        "tmp": tmp_path,
        "dataset": dataset,
        "instance": instance,
        "source_template": str(tmp_path / "src" / "{repo}"),
    }


def prepare(env, out_name="tasks"):
    out = env["tmp"] / out_name
    prepare_instance(
        env["instance"], out, env["tmp"] / "cache", repo_source=env["source_template"]
    )
    return out


def load_task(env):
    return load_tasks_from_dir(prepare(env))[0]


def fresh_workspace(task, tmp_path, name="ws"):
    workspace = tmp_path / name
    shutil.copytree(task.repo_dir, workspace, symlinks=True, ignore=IGNORED)
    return workspace


def test_prepare_builds_a_loadable_task_without_git_history(swe_env):
    out = prepare(swe_env)
    task_dir = out / "acme__calc-1"
    assert not (task_dir / "repo" / ".git").exists()
    assert (task_dir / "repo" / "calc" / "ops.py").read_text() == BUGGY_OPS
    task = load_tasks_from_dir(out)[0]
    assert (
        task.kind == "repo" and task.track == "swebench" and task.id == "acme__calc-1"
    )
    assert task.fail_to_pass == ("tests/test_ops.py::test_average_empty_raises",)
    assert len(task.pass_to_pass) == 2 and task.gold_patch and task.test_patch
    assert task.split in {"train", "heldout", "fresh"}


def test_validation_accepts_a_sound_instance(swe_env):
    assert validate_tasks([load_task(swe_env)]) == []


def test_validation_rejects_a_broken_gold_patch(swe_env):
    task = load_task(swe_env)
    import dataclasses

    broken = dataclasses.replace(
        task, gold_patch=task.gold_patch.replace("ValueError", "KeyError")
    )
    assert any("gold patch" in p for p in validate_tasks([broken]))


def test_base_state_is_unresolved_and_the_fix_resolves(swe_env):
    task = load_task(swe_env)
    workspace = fresh_workspace(task, swe_env["tmp"])
    assert evaluate(task, workspace).score == 0.0
    assert apply_patch(workspace, task.gold_patch) is None
    outcome = evaluate(task, workspace)
    assert (outcome.passed, outcome.total, outcome.error) == (1, 1, "")


def test_editing_the_tests_does_not_help(swe_env):
    task = load_task(swe_env)
    workspace = fresh_workspace(task, swe_env["tmp"])
    (workspace / "tests" / "test_ops.py").write_text(
        TESTS_V1 + "\n\ndef test_average_empty_raises():\n    assert True\n"
    )
    assert evaluate(task, workspace).score == 0.0


def test_a_fix_that_breaks_existing_tests_scores_zero(swe_env):
    task = load_task(swe_env)
    workspace = fresh_workspace(task, swe_env["tmp"])
    (workspace / "calc" / "ops.py").write_text(
        "def average(values):\n    raise ValueError('always')\n\n\ndef total(values):\n    return sum(values)\n"
    )
    outcome = evaluate(task, workspace)
    assert outcome.score == 0.0 and "previously passing" in outcome.error


def test_scripted_agent_resolves_the_issue_end_to_end(swe_env, write_script):
    task = load_task(swe_env)
    script = [
        {"tool_calls": [{"name": "list_files", "arguments": {}}]},
        {
            "tool_calls": [
                {
                    "name": "read_file",
                    "arguments": {
                        "path": "calc/ops.py",
                        "start_line": 1,
                        "end_line": 2,
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "edit_file",
                    "arguments": {
                        "path": "calc/ops.py",
                        "old_str": "def average(values):\n    return sum(values) / len(values)",
                        "new_str": "def average(values):\n    if not values:\n        raise ValueError('empty')\n    return sum(values) / len(values)",
                    },
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "name": "finish",
                    "arguments": {"summary": "average now rejects empty input"},
                }
            ]
        },
    ]
    cfg = RunConfig(llm_spec=write_script("swe.json", script))
    result = run_task(task, BUILTIN_GENOME, cfg, swe_env["tmp"] / "out")
    assert (
        result.score == 1.0
        and result.stop_reason == "finished"
        and result.integrity_flags == []
    )
    assert not (swe_env["tmp"] / "out" / "workspaces" / task.id / ".git").exists()


def test_cli_prepare_and_validate(swe_env, capsys):
    out = swe_env["tmp"] / "cli_tasks"
    code = main(
        [
            "swebench",
            "prepare",
            "--dataset",
            str(swe_env["dataset"]),
            "--out",
            str(out),
            "--cache",
            str(swe_env["tmp"] / "cli_cache"),
            "--repo-source",
            swe_env["source_template"],
        ]
    )
    assert code == 0 and "1 prepared, 0 failed" in capsys.readouterr().out
    assert main(["validate-suite", "--tasks-dir", str(out)]) == 0


def test_prepare_reports_missing_fields_and_bad_commits(swe_env):
    with pytest.raises(SwebenchError, match="missing fields"):
        prepare_instance(
            {"instance_id": "x"}, swe_env["tmp"] / "o", swe_env["tmp"] / "c"
        )
    bad = dict(swe_env["instance"], base_commit="0" * 40)
    with pytest.raises(SwebenchError):
        prepare_instance(
            bad,
            swe_env["tmp"] / "o",
            swe_env["tmp"] / "c",
            repo_source=swe_env["source_template"],
        )


def test_patch_paths_and_pytest_output_parsing():
    patch = "diff --git a/tests/a.py b/tests/a.py\n--- a/tests/a.py\n+++ b/tests/a.py\ndiff --git a/new.py b/new.py\n"
    assert patch_paths(patch) == ["new.py", "tests/a.py"]
    output = (
        "PASSED tests/a.py::test_ok\nFAILED tests/a.py::test_bad - AssertionError: nope\n"
        "ERROR tests/b.py::test_err - ImportError\nSKIPPED [1] tests/a.py:3: reason\nPASSED tests/a.py::test_p[1-2]\n"
    )
    statuses = parse_pytest_results(output)
    assert statuses["tests/a.py::test_ok"] == "PASSED"
    assert (
        statuses["tests/a.py::test_bad"] == "FAILED"
        and statuses["tests/b.py::test_err"] == "ERROR"
    )
    assert statuses["tests/a.py::test_p[1-2]"] == "PASSED"


def test_dataset_formats_and_split_assignment(tmp_path):
    rows = [{"instance_id": f"r__x-{i}"} for i in range(3)]
    (tmp_path / "a.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (tmp_path / "b.json").write_text(json.dumps(rows))
    assert (
        load_instances(tmp_path / "a.jsonl")
        == load_instances(tmp_path / "b.json")
        == rows
    )
    splits = [assign_split(f"inst-{i}") for i in range(500)]
    assert splits == [assign_split(f"inst-{i}") for i in range(500)]
    shares = {s: splits.count(s) / 500 for s in ("train", "heldout", "fresh")}
    assert (
        0.5 < shares["train"] < 0.7
        and 0.1 < shares["heldout"] < 0.3
        and 0.1 < shares["fresh"] < 0.3
    )


def test_relaxed_integrity_only_flags_real_tampering_in_changed_files(tmp_path):
    base, work = tmp_path / "base", tmp_path / "work"
    base.mkdir()
    (base / "lib.py").write_text(
        "import subprocess\n\ndef run():\n    return subprocess\n"
    )
    shutil.copytree(base, work)
    assert changed_python_files(work, base) == set()
    (work / "lib.py").write_text("import subprocess\nimport atexit\nx = eval('1')\n")
    only = changed_python_files(work, base)
    assert only == {"lib.py"} and scan_workspace(work, only=only, relaxed=True) == []
    (work / "lib.py").write_text("import os\nos._exit(0)\n")
    assert any(
        "os._exit" in f for f in scan_workspace(work, only={"lib.py"}, relaxed=True)
    )
