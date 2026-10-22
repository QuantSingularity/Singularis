import sys

from backend.cli import main
from backend.evaluation.suite import BUILTIN_TASKS
from backend.evolution.live import plan, preflight, summarize
from testkit import good_meta_script, make_evolver


def test_plan_gives_a_hard_upper_bound():
    p = plan(
        list(BUILTIN_TASKS),
        iterations=5,
        train_trials=1,
        heldout_trials=1,
        max_tokens_per_run=400_000,
    )
    assert p["train_tasks"] == 11 and p["heldout_tasks"] == 9
    assert p["seed_runs"] == 20 and p["runs_per_iteration_max"] == 21
    assert p["agent_runs_max"] == 20 + 5 * 21
    assert p["tokens_upper_bound"] == p["agent_runs_max"] * 400_000


def test_preflight_rejects_a_scripted_model():
    problems, _ = preflight("scripted:x.json")
    assert problems and "anthropic" in problems[0]


def test_preflight_reports_a_missing_key_and_sdk(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY_FILE", raising=False)
    monkeypatch.setitem(sys.modules, "anthropic", None)
    problems, _ = preflight("anthropic:some-model")
    assert any("API key" in p for p in problems) and any("SDK" in p for p in problems)


def test_dry_run_prints_the_ceiling_and_touches_nothing(capsys, tmp_path):
    code = main(["live", "--dry-run", "--root", str(tmp_path / "r")])
    out = capsys.readouterr().out
    assert code == 0 and "worst case" in out
    assert not (tmp_path / "r").exists()


def test_a_live_run_stops_at_the_preflight_without_a_key(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY_FILE", raising=False)
    monkeypatch.setitem(sys.modules, "anthropic", None)
    assert main(["live", "--root", str(tmp_path / "r")]) == 2
    assert "preflight failed" in capsys.readouterr().err


def test_summary_reports_tokens_children_and_integrity(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script())
    evolver.run()
    text = summarize(evolver.root, plan(list(BUILTIN_TASKS), 1, 1, 1, 1000))
    assert "# Live run summary" in text and "a0001" in text
    assert "Children produced: 1; valid: 1" in text
    assert "Integrity:" in text and "Worst-case bound" in text
