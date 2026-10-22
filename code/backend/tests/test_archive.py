import random

import pytest

from backend.evolution.archive import Archive


def make(tmp_path):
    a = Archive(tmp_path)
    a.add("a0000", None, 0, "valid")
    a.update("a0000", train_score=0.5, fitness=0.5)
    a.add("a0001", "a0000", 1, "valid")
    a.update("a0001", train_score=0.9, fitness=0.9)
    a.add("a0002", "a0001", 2, "invalid", "broke import")
    return a


def test_ids_and_lineage(tmp_path):
    a = make(tmp_path)
    assert a.new_id() == "a0003"
    assert [r.id for r in a.lineage("a0002")] == ["a0000", "a0001", "a0002"]
    assert a.children_count("a0000") == 1


def test_best_ignores_invalid(tmp_path):
    assert make(tmp_path).best().id == "a0001"


def test_select_parent_only_valid_and_favors_fitness(tmp_path):
    a = make(tmp_path)
    rng = random.Random(1)
    picks = [a.select_parent(rng).id for _ in range(300)]
    assert set(picks) <= {"a0000", "a0001"}
    assert picks.count("a0001") > picks.count("a0000")


def test_update_rejects_unknown_field(tmp_path):
    with pytest.raises(ValueError):
        make(tmp_path).update("a0000", id="x")


def test_empty_archive_cannot_select(tmp_path):
    with pytest.raises(RuntimeError):
        Archive(tmp_path).select_parent(random.Random(0))
