from __future__ import annotations

import itertools
import random
from typing import Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(
    values: Sequence[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot)
    )
    low = means[int((alpha / 2) * n_boot)]
    high = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (low, high)


MIN_TASKS = 8


def sign_flip_p(diffs: Sequence[float], n_mc: int = 20000, seed: int = 0) -> float:
    """Two-sided paired permutation (sign-flip) test of 'the mean difference is zero'.

    Exact for up to 16 tasks, Monte Carlo above that. Unlike a percentile bootstrap it stays honest when the
    number of tasks is small."""
    n = len(diffs)
    if n == 0:
        return 1.0
    observed = abs(sum(diffs))
    eps = 1e-12
    if n <= 16:
        hits = sum(
            1
            for signs in itertools.product((1, -1), repeat=n)
            if abs(sum(s * d for s, d in zip(signs, diffs))) >= observed - eps
        )
        return hits / (2**n)
    rng = random.Random(seed)
    hits = sum(
        1
        for _ in range(n_mc)
        if abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed - eps
    )
    return (hits + 1) / (n_mc + 1)


def paired_bootstrap(
    candidate: Sequence[float],
    baseline: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
    min_tasks: int = MIN_TASKS,
) -> dict:
    """Compare candidate to baseline per task: bootstrap interval plus an exact sign-flip test.

    The inputs are aligned per task (for example the mean score of each task over its trials). A result is
    only called significant when the interval excludes zero, the permutation test agrees (p < alpha) and
    there are at least `min_tasks` tasks. With fewer tasks the percentile bootstrap is too optimistic to
    trust, so the comparison is reported as underpowered instead.
    """
    if len(candidate) != len(baseline):
        raise ValueError("candidate and baseline must have the same length")
    diffs = [c - b for c, b in zip(candidate, baseline)]
    low, high = bootstrap_ci(diffs, n_boot, alpha, seed)
    p_value = sign_flip_p(diffs, seed=seed)
    underpowered = len(diffs) < min_tasks
    return {
        "n": len(diffs),
        "mean_diff": mean(diffs),
        "ci_low": low,
        "ci_high": high,
        "p_value": p_value,
        "underpowered": underpowered,
        "significant": bool(diffs)
        and not underpowered
        and (low > 0 or high < 0)
        and p_value < alpha,
    }
