from backend.evaluation.runner import RunConfig, absolute_llm_spec, run_task
from backend.evolution.evolve import BUILTIN_GENOME
from testkit import FIZZ, solving_script


def test_relative_scripted_paths_become_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (
        absolute_llm_spec("scripted:solve.json")
        == f"scripted:{(tmp_path / 'solve.json').resolve()}"
    )
    assert (
        absolute_llm_spec("scripted:sub/solve.json")
        == f"scripted:{(tmp_path / 'sub' / 'solve.json').resolve()}"
    )


def test_other_specs_are_left_alone(tmp_path):
    absolute = f"scripted:{tmp_path / 'solve.json'}"
    assert absolute_llm_spec(absolute) == absolute
    assert (
        absolute_llm_spec("anthropic:claude-sonnet-5-5")
        == "anthropic:claude-sonnet-5-5"
    )
    assert absolute_llm_spec("scripted:") == "scripted:"


def test_a_relative_scripted_model_works_end_to_end(tmp_path, monkeypatch):
    import json

    (tmp_path / "solve.json").write_text(json.dumps(solving_script()))
    monkeypatch.chdir(tmp_path)
    result = run_task(
        FIZZ,
        BUILTIN_GENOME,
        RunConfig(llm_spec="scripted:solve.json"),
        tmp_path / "out",
    )
    assert result.score == 1.0 and result.stop_reason == "finished"
