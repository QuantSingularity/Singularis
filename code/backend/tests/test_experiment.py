import json

import pytest
from backend.evaluation.runner import RunConfig
from backend.evolution.experiment import (
    ExperimentConfig,
    render_markdown,
    run_experiment,
)
from testkit import fizz_tasks, good_meta_script, solving_script, write_script


def test_experiment_compares_arms_against_the_seed(tmp_path):
    eval_run = RunConfig(
        llm_spec=write_script(tmp_path, "solve.json", solving_script())
    )
    meta_run = RunConfig(
        llm_spec=write_script(tmp_path, "meta.json", good_meta_script())
    )
    cfg = ExperimentConfig(
        arms=("open_ended", "greedy"), iterations=1, trials=2, workers=2
    )
    root = tmp_path / "exp"
    report = run_experiment(
        root, fizz_tasks(), eval_run, meta_run, cfg, log=lambda m: None
    )

    assert set(report["arms"]) == {"open_ended", "greedy"}
    assert set(report["seed"]) == {"heldout", "fresh"}
    for data in report["arms"].values():
        assert data["usage"]["iterations"] == 1
        assert set(data["vs_seed"]) == {"heldout", "fresh"}
        assert (
            data["vs_seed"]["fresh"]["n"] == 1
            and not data["vs_seed"]["fresh"]["significant"]
        )
        assert data["final"]["fresh"]["mean"] == 1.0
    saved = json.loads((root / "experiment.json").read_text())
    assert saved["config"]["trials"] == 2
    text = (root / "EXPERIMENT.md").read_text()
    assert (
        "Experiment report" in text
        and "No comparison is reliable" in text
        and "\u2014" not in text
    )


def test_unknown_arm_is_rejected(tmp_path):
    run = RunConfig(llm_spec="scripted:x")
    with pytest.raises(ValueError):
        run_experiment(
            tmp_path, fizz_tasks(), run, run, ExperimentConfig(arms=("bogus",))
        )


def test_markdown_flags_reliable_gains():
    summary = {
        "mean": 0.9,
        "ci_low": 0.8,
        "ci_high": 1.0,
        "n_tasks": 3,
        "mean_tokens": 1,
        "by_track": {},
        "per_task": {},
    }
    base = {
        "mean": 0.5,
        "ci_low": 0.4,
        "ci_high": 0.6,
        "n_tasks": 3,
        "mean_tokens": 1,
        "by_track": {},
        "per_task": {},
    }
    report = {
        "config": {"arms": ["greedy"], "iterations": 1, "trials": 1},
        "seed": {"heldout": base},
        "arms": {
            "greedy": {
                "best_agent": "a0002",
                "usage": {"meta_tokens": 1, "eval_tokens": 2},
                "final": {"heldout": summary},
                "vs_seed": {
                    "heldout": {
                        "n": 3,
                        "mean_diff": 0.4,
                        "ci_low": 0.2,
                        "ci_high": 0.6,
                        "significant": True,
                    }
                },
            }
        },
    }
    text = render_markdown(report)
    assert "(reliable)" in text and "At least one comparison passes" in text
