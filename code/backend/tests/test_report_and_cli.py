import json
import logging

from backend.cli import main
from backend.core.logging_config import setup_logging
from backend.evolution.report import build_report
from testkit import good_meta_script, make_evolver


def test_report_contains_lineage_scores_and_diff(tmp_path):
    evolver = make_evolver(tmp_path, good_meta_script())
    evolver.run()
    report = build_report(tmp_path / "exp")
    by_id = {a["id"]: a for a in report["agents"]}
    assert report["best"] in by_id and len(by_id) == 2
    child = by_id["a0001"]
    assert child["parent_id"] == "a0000" and "careful engineer" in child["diff"]
    assert child["train_results"][0]["task_id"] == "fizzbuzz"
    assert child["heldout_results"][0]["task_id"] == "fizzbuzz_heldout"


def test_cli_report_writes_valid_json(tmp_path, capsys):
    make_evolver(tmp_path, good_meta_script()).run()
    out = tmp_path / "out" / "report.json"
    assert main(["report", "--root", str(tmp_path / "exp"), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["agents"]
    assert "frontend/index.html" in capsys.readouterr().out


def test_cli_suite_lists_tasks(capsys):
    assert main(["suite"]) == 0
    assert "fizzbuzz" in capsys.readouterr().out


def test_cli_lineage_prints_archive(tmp_path, capsys):
    make_evolver(tmp_path, good_meta_script()).run()
    assert main(["lineage", "--root", str(tmp_path / "exp")]) == 0
    out = capsys.readouterr().out
    assert "a0000" in out and "a0001" in out and "best by fitness" in out


def test_setup_logging_writes_file(tmp_path):
    logger = logging.getLogger("singularis")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    setup_logging(tmp_path / "logs")
    logging.getLogger("singularis").info("hello log")
    for handler in logging.getLogger("singularis").handlers:
        handler.flush()
    assert "hello log" in (tmp_path / "logs" / "singularis.log").read_text()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
