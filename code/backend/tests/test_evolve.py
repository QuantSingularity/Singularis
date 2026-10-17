import shutil

from backend.evolution.evolve import (
    BUILTIN_GENOME,
    check_genome_files,
    diff_genomes,
    validate_genome,
)
from testkit import breaking_meta_script, good_meta_script, make_evolver


def test_full_recursive_step_with_valid_child(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script())
    reports = evolver.run()
    records = {r.id: r for r in evolver.archive.all()}
    assert set(records) == {"a0000", "a0001"}
    seed, child = records["a0000"], records["a0001"]
    assert seed.train_score == 1.0 and seed.heldout_score == 1.0
    assert (
        child.status == "valid" and child.parent_id == "a0000" and child.generation == 1
    )
    assert child.train_score == 1.0 and child.heldout_score == 1.0
    assert "tightened" in child.note
    patch = (evolver.archive.agent_dir("a0001") / "diff.patch").read_text()
    assert "careful engineer" in patch
    assert reports[0]["promising"] is True


def test_child_that_breaks_the_contract_is_rejected(tmp_path):
    evolver = make_evolver(tmp_path, breaking_meta_script())
    report = evolver.run()[0]
    child = evolver.archive.get("a0001")
    assert report["status"] == "invalid" and child.status == "invalid"
    assert not evolver.archive.genome_dir("a0001").exists()
    assert evolver.archive.best().id == "a0000"


def test_genome_file_checks(tmp_path):
    g = tmp_path / "genome"
    shutil.copytree(BUILTIN_GENOME, g, ignore=shutil.ignore_patterns("__pycache__"))
    assert check_genome_files(g, 200_000, 30) is None
    (g / "payload.bin").write_bytes(b"\x00")
    assert "not allowed" in check_genome_files(g, 200_000, 30)
    (g / "payload.bin").unlink()
    assert "too large" in check_genome_files(g, 100, 30)
    (g / "link.py").symlink_to(g / "agent.py")
    assert "symlink" in check_genome_files(g, 200_000, 30)


def test_validate_genome_accepts_seed_and_rejects_syntax_error(tmp_path):
    g = tmp_path / "genome"
    shutil.copytree(BUILTIN_GENOME, g, ignore=shutil.ignore_patterns("__pycache__"))
    assert validate_genome(g) is None
    (g / "prompts.py").write_text("SYSTEM_PROMPT = (\n")
    assert "validation failed" in validate_genome(g)


def test_diff_of_identical_genomes_is_empty():
    assert diff_genomes(BUILTIN_GENOME, BUILTIN_GENOME) == ""
