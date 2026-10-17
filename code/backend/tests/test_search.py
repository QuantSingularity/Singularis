import random

import pytest
from backend.evolution.archive import Archive
from backend.evolution.evolve import FOCI, cluster_failures, failure_class
from testkit import good_meta_script, make_evolver


def result(task_id, score=0.0, stop="finished", flags=None, trial=0):
    return {
        "task_id": task_id,
        "score": score,
        "stop_reason": stop,
        "integrity_flags": flags or [],
        "trial": trial,
        "passed": 0,
        "total": 5,
        "input_tokens": 1,
        "output_tokens": 1,
        "error": "",
    }


def test_failure_classes():
    assert failure_class(result("a", 0.0, "finished")) == "wrong_answer"
    assert failure_class(result("a", 0.4, "finished")) == "partial_credit"
    assert failure_class(result("a", 0.0, "budget")) == "budget"
    assert failure_class(result("a", 0.0, "genome_error")) == "genome_error"
    assert (
        failure_class(result("a", 0.0, "finished", ["x.py: import:atexit"]))
        == "integrity_violation"
    )


def test_clusters_are_grouped_and_ordered_by_size():
    results = [
        result("a", 0.0, "budget"),
        result("b", 0.0, "budget"),
        result("c", 0.5),
        result("d", 1.0),
    ]
    assert cluster_failures(results) == [
        ("budget", ["a", "b"]),
        ("partial_credit", ["c"]),
    ]


def test_greedy_always_extends_the_fittest(tmp_path):
    archive = Archive(tmp_path)
    for agent_id, fit in (("a0000", 0.5), ("a0001", 0.9), ("a0002", 0.7)):
        archive.add(agent_id, None, 0, "valid")
        archive.update(agent_id, fitness=fit)
    rng = random.Random(0)
    assert {archive.select_parent(rng, "greedy").id for _ in range(20)} == {"a0001"}


def test_unknown_strategy_is_rejected(tmp_path):
    archive = Archive(tmp_path)
    archive.add("a0000", None, 0, "valid")
    archive.update("a0000", fitness=0.5)
    with pytest.raises(ValueError):
        archive.select_parent(random.Random(0), "random_walk")


def test_focus_rotates_with_the_archive_size(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script(), iterations=2)
    evolver.run()
    assert evolver.archive.get("a0001").focus == FOCI[1]
    assert evolver.archive.get("a0002").focus == FOCI[2]


def test_greedy_evolver_runs(tmp_path):
    evolver = make_evolver(
        tmp_path, good_meta_script(), iterations=2, selection="greedy"
    )
    reports = evolver.run()
    assert len(reports) == 2 and all(r["status"] == "valid" for r in reports)


def test_evolver_rejects_unknown_selection(tmp_path):
    with pytest.raises(ValueError):
        make_evolver(tmp_path, good_meta_script(), selection="nope")


def test_usage_and_manifest_are_written(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script())
    evolver.run()
    root = tmp_path / "exp"
    usage = __import__("json").loads((root / "usage.json").read_text())
    assert (
        usage["iterations"] == 1
        and usage["meta_tokens"] > 0
        and usage["eval_tokens"] > 0
    )
    assert (root / "manifest.json").is_file()
