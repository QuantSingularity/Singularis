from __future__ import annotations

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


def paired_bootstrap(
    candidate: Sequence[float],
    baseline: Sequence[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict:
    """Bootstrap the mean paired difference (candidate minus baseline), resampling tasks.

    The inputs are aligned per task (for example the mean score of each task over its trials).
    """
    if len(candidate) != len(baseline):
        raise ValueError("candidate and baseline must have the same length")
    diffs = [c - b for c, b in zip(candidate, baseline)]
    low, high = bootstrap_ci(diffs, n_boot, alpha, seed)
    return {
        "n": len(diffs),
        "mean_diff": mean(diffs),
        "ci_low": low,
        "ci_high": high,
        "significant": bool(diffs) and (low > 0 or high < 0),
    }
