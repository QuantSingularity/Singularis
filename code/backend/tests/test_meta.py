import json

import pytest
from backend.evolution.meta import INVALID_REWARD, MetaPromptStore, validate_template
from testkit import (
    NEW_META_TEMPLATE,
    breaking_meta_script,
    dual_meta_script,
    make_evolver,
)

DEFAULT = "Default template {parent} {digest} {focus}"


def test_template_validation():
    assert validate_template(DEFAULT) is None
    assert "missing placeholders" in validate_template("no placeholders here")
    assert "missing placeholders" in validate_template("{parent} {digest}")
    assert "does not format" in validate_template("{parent} {digest} {focus} {unknown}")
    assert "does not format" in validate_template("{parent} {digest} {focus} { stray")
    assert validate_template("{parent} {digest} {focus} " + "x" * 6001) is not None
    assert validate_template("{parent} {digest} {focus} literal {{braces}}") is None


def test_untried_variants_come_first_then_ucb(tmp_path):
    store = MetaPromptStore(tmp_path, DEFAULT)
    assert store.choose()[0] == "m0"
    store.record("m0", 0.01)
    variant, reason = store.add_variant("Alternative {parent} {digest} {focus}")
    assert variant == "m1" and reason == "ok"
    assert store.choose()[0] == "m1"
    store.record("m1", 0.2)
    for _ in range(5):
        store.record("m1", 0.2)
        store.record("m0", 0.0)
    assert store.choose()[0] == "m1" and store.best() == "m1"


def test_duplicates_and_invalid_variants_are_rejected(tmp_path):
    store = MetaPromptStore(tmp_path, DEFAULT)
    assert store.add_variant(DEFAULT + "\n")[0] is None
    assert store.add_variant("bad template")[0] is None
    assert store.count() == 1


def test_state_persists_across_instances(tmp_path):
    first = MetaPromptStore(tmp_path, DEFAULT)
    first.record("m0", 0.1)
    second = MetaPromptStore(
        tmp_path, "different default that must be ignored {parent} {digest} {focus}"
    )
    assert second.template("m0") == DEFAULT and second.summary()["m0"]["uses"] == 1


def test_step_records_reward_for_the_chosen_variant(tmp_path):
    evolver = make_evolver(tmp_path, dual_meta_script())
    report = evolver.run()[0]
    summary = evolver.meta_store.summary()
    assert report["variant"] == "m0" and summary["m0"]["uses"] == 1
    assert summary["m0"]["mean_delta"] == pytest.approx(report["delta"])


def test_invalid_child_is_penalized(tmp_path):
    evolver = make_evolver(tmp_path, breaking_meta_script())
    evolver.run()
    assert evolver.meta_store.summary()["m0"]["mean_delta"] == pytest.approx(
        INVALID_REWARD
    )
    assert evolver.archive.get("a0001").delta == pytest.approx(INVALID_REWARD)


def test_meta_prompt_evolves_and_is_used_next(tmp_path):
    evolver = make_evolver(tmp_path, dual_meta_script(), iterations=2, meta_every=1)
    reports = evolver.run()
    assert "variant m1 added" in reports[0]["meta_prompt"]
    assert evolver.meta_store.template("m1") == NEW_META_TEMPLATE
    assert reports[1]["variant"] == "m1"
    assert "meta prompt change rejected" in reports[1]["meta_prompt"]
    stats = json.loads((tmp_path / "exp" / "meta_prompts" / "stats.json").read_text())
    assert stats["m1"]["uses"] == 1
