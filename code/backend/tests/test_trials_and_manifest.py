import dataclasses
import json

from backend.evaluation.runner import RunConfig, run_suite
from backend.evolution.evolve import BUILTIN_GENOME, EvolveConfig
from backend.evolution.manifest import (
    frozen_code_hash,
    task_fingerprints,
    write_manifest,
)
from testkit import FIZZ, solving_script, write_script


def test_trials_repeat_each_task(tmp_path):
    cfg = RunConfig(
        llm_spec=write_script(tmp_path, "s.json", solving_script()), trials=3
    )
    suite = run_suite([FIZZ], BUILTIN_GENOME, cfg, tmp_path / "out", workers=3)
    assert [(r.task_id, r.trial) for r in suite.results] == [
        ("fizzbuzz", 0),
        ("fizzbuzz", 1),
        ("fizzbuzz", 2),
    ]
    assert suite.by_task() == {"fizzbuzz": 1.0}
    assert (tmp_path / "out" / "traces" / "fizzbuzz__t2.trace.json").is_file()


def config(tmp_path):
    run = RunConfig(llm_spec="scripted:x")
    return EvolveConfig(eval_run=run, meta_run=run)


def test_manifest_records_environment_and_fingerprints(tmp_path):
    assert write_manifest(tmp_path, config(tmp_path), [FIZZ]) == []
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["frozen_code_sha256"] == frozen_code_hash()
    assert manifest["tasks"] == task_fingerprints([FIZZ])
    assert manifest["config"]["iterations"] == 5


def test_resume_warns_when_tasks_change(tmp_path):
    write_manifest(tmp_path, config(tmp_path), [FIZZ])
    assert write_manifest(tmp_path, config(tmp_path), [FIZZ]) == []
    changed = dataclasses.replace(
        FIZZ, hidden_tests=FIZZ.hidden_tests + "\n# changed\n"
    )
    warnings = write_manifest(tmp_path, config(tmp_path), [changed])
    assert any("task set changed" in w for w in warnings)
    assert json.loads((tmp_path / "manifest.json").read_text())["history"]


def test_frozen_hash_ignores_the_mutable_genome_and_tests():
    assert len(frozen_code_hash()) == 64
