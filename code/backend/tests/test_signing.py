import json

from backend.cli import main
from backend.evolution.archive import Archive
from backend.evolution.signing import verify_agent, verify_all
from testkit import good_meta_script, make_evolver


def run_experiment(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script())
    evolver.run()
    return tmp_path / "exp"


def test_all_records_verify_after_a_run(tmp_path):
    root = run_experiment(tmp_path)
    results = verify_all(root, Archive(root))
    assert set(results) == {"a0000", "a0001"} and all(
        problems == [] for problems in results.values()
    )


def test_editing_a_genome_after_the_fact_is_detected(tmp_path):
    root = run_experiment(tmp_path)
    archive = Archive(root)
    (archive.genome_dir("a0001") / "prompts.py").write_text(
        'SYSTEM_PROMPT = "tampered"\n'
    )
    assert any("genome_sha256" in p for p in verify_agent(root, archive, "a0001"))
    assert verify_agent(root, archive, "a0000") == []


def test_editing_result_files_or_scores_is_detected(tmp_path):
    root = run_experiment(tmp_path)
    archive = Archive(root)
    results = archive.agent_dir("a0001") / "results_train.json"
    data = json.loads(results.read_text())
    data["mean_score"] = 0.0
    results.write_text(json.dumps(data))
    assert any(
        "results_train_sha256" in p for p in verify_agent(root, archive, "a0001")
    )
    archive.update("a0000", heldout_score=0.123)
    assert any("heldout_score" in p for p in verify_agent(root, archive, "a0000"))


def test_wrong_key_fails_verification(tmp_path, monkeypatch):
    root = run_experiment(tmp_path)
    monkeypatch.setenv("SINGULARIS_SIGNING_KEY", "some-other-key")
    assert any(
        "signature does not match" in p
        for p in verify_agent(root, Archive(root), "a0000")
    )


def test_missing_signature_is_reported(tmp_path):
    root = run_experiment(tmp_path)
    archive = Archive(root)
    (archive.agent_dir("a0001") / "signature.json").unlink()
    assert verify_agent(root, archive, "a0001") == ["no signature"]


def test_cli_verify_exit_codes(tmp_path, capsys):
    root = run_experiment(tmp_path)
    assert main(["verify", "--root", str(root)]) == 0
    (Archive(root).genome_dir("a0001") / "prompts.py").write_text(
        "SYSTEM_PROMPT = 'x'\n"
    )
    assert main(["verify", "--root", str(root)]) == 1
    assert "FAIL a0001" in capsys.readouterr().out
