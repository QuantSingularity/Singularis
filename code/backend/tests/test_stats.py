import pytest
from backend.evaluation.stats import bootstrap_ci, mean, paired_bootstrap, sign_flip_p


def test_mean_and_empty():
    assert mean([1, 2, 3]) == 2 and mean([]) == 0.0


def test_ci_of_constant_is_degenerate_and_deterministic():
    assert bootstrap_ci([0.5] * 8) == (0.5, 0.5)
    values = [0.1, 0.9, 0.4, 0.6, 0.5]
    assert bootstrap_ci(values, seed=3) == bootstrap_ci(values, seed=3)


def test_ci_contains_the_mean_and_is_ordered():
    values = [0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    low, high = bootstrap_ci(values)
    assert low <= mean(values) <= high and low < high


def test_paired_bootstrap_detects_a_consistent_gain():
    base = [0.4, 0.5, 0.3, 0.6, 0.5, 0.4, 0.5, 0.3, 0.6, 0.4]
    gain = [b + 0.3 for b in base]
    result = paired_bootstrap(gain, base)
    assert result["significant"] and result["ci_low"] > 0 and result["n"] == 10
    assert result["p_value"] < 0.01 and not result["underpowered"]


def test_a_perfect_gain_on_four_tasks_is_called_underpowered_not_significant():
    result = paired_bootstrap([0.9, 1.0, 0.8, 0.9], [0.5, 0.6, 0.4, 0.5])
    assert result["ci_low"] > 0  # the bootstrap alone would have claimed a win
    assert result["underpowered"] and not result["significant"]
    assert result["p_value"] == pytest.approx(2 / 16)


def test_paired_bootstrap_does_not_claim_noise_is_signal():
    result = paired_bootstrap([0.5, 0.6, 0.4, 0.5], [0.6, 0.5, 0.5, 0.4])
    assert not result["significant"] and result["ci_low"] <= 0 <= result["ci_high"]


def test_sign_flip_is_exact_for_small_samples():
    assert sign_flip_p([1, 1, 1]) == pytest.approx(2 / 8)
    assert sign_flip_p([1, -1]) == 1.0
    assert sign_flip_p([]) == 1.0
    assert sign_flip_p([0.0, 0.0, 0.0]) == 1.0


def test_sign_flip_uses_monte_carlo_for_many_tasks():
    p = sign_flip_p([0.2] * 20)
    assert 0 < p < 0.001


def test_paired_bootstrap_requires_aligned_inputs():
    with pytest.raises(ValueError):
        paired_bootstrap([1.0], [1.0, 2.0])
