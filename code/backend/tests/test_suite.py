import pytest

from backend.evaluation.evaluator import validate_tasks
from backend.evaluation.suite import BUILTIN_TASKS
from backend.evaluation.tasks import load_tasks_from_dir


def test_builtin_suite_is_sound():
    assert validate_tasks(BUILTIN_TASKS) == []


def test_suite_has_both_splits_and_unique_ids():
    ids = [t.id for t in BUILTIN_TASKS]
    assert len(ids) == len(set(ids))
    assert {t.split for t in BUILTIN_TASKS} == {"train", "heldout", "fresh"}
    assert {t.track for t in BUILTIN_TASKS} == {"general", "finance", "issues"}


def test_load_tasks_from_dir(tmp_path):
    task_dir = tmp_path / "t1"
    (task_dir / "files").mkdir(parents=True)
    (task_dir / "task.json").write_text('{"prompt": "do it", "split": "heldout"}')
    (task_dir / "files" / "a.py").write_text("x = 1\n")
    (task_dir / "hidden_tests.py").write_text("import unittest\n")
    tasks = load_tasks_from_dir(tmp_path)
    assert (
        tasks[0].id == "t1"
        and tasks[0].split == "heldout"
        and tasks[0].files == {"a.py": "x = 1\n"}
    )


ISSUE_TASKS = [t for t in BUILTIN_TASKS if t.track == "issues"]


def _workspace(task, reference_files):
    import tempfile
    from pathlib import Path

    directory = Path(tempfile.mkdtemp())
    for rel, content in task.files.items():
        (directory / rel).parent.mkdir(parents=True, exist_ok=True)
        (directory / rel).write_text(content)
    for rel in reference_files:
        (directory / rel).write_text(task.reference[rel])
    return directory


def test_issue_tasks_are_multi_file_and_cover_every_split():
    assert len(ISSUE_TASKS) >= 5
    assert {t.split for t in ISSUE_TASKS} == {"train", "heldout", "fresh"}
    for task in ISSUE_TASKS:
        assert (
            len(
                [
                    f
                    for f in task.files
                    if f.endswith(".py")
                    and "tests" not in f
                    and not f.endswith("__init__.py")
                ]
            )
            >= 2
        )


@pytest.mark.parametrize("task", ISSUE_TASKS, ids=lambda t: t.id)
def test_visible_tests_pass_on_the_starter_so_they_are_not_misleading(task):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "unittest", "-q"],
        cwd=_workspace(task, []),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("task", ISSUE_TASKS, ids=lambda t: t.id)
def test_every_fix_is_individually_necessary(task):
    from backend.evaluation.evaluator import evaluate

    for omitted in task.reference:
        others = [rel for rel in task.reference if rel != omitted]
        assert evaluate(task, _workspace(task, others)).score < 1.0, (
            f"{omitted} is not needed to pass {task.id}"
        )


def test_final_splits_have_enough_tasks_to_support_a_significance_claim():
    from collections import Counter

    from backend.evaluation.stats import MIN_TASKS

    counts = Counter(t.split for t in BUILTIN_TASKS)
    assert counts["heldout"] >= MIN_TASKS and counts["fresh"] >= MIN_TASKS
