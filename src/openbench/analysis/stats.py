"""Small, deterministic statistics helpers (fixed seeds, no global RNG state)."""

from __future__ import annotations

import random
import statistics


def bootstrap_ci(
    values: list[float],
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI of the mean. Returns (mean, lo, hi)."""
    if not values:
        return (0.0, 0.0, 0.0)
    mean = statistics.fmean(values)
    if len(values) == 1:
        return (mean, mean, mean)
    rng = random.Random(seed)
    boot_means = sorted(
        statistics.fmean(rng.choices(values, k=len(values))) for _ in range(n_boot)
    )
    lo_idx = int((alpha / 2) * (n_boot - 1))
    hi_idx = int((1 - alpha / 2) * (n_boot - 1))
    return (mean, boot_means[lo_idx], boot_means[hi_idx])


def ci_includes_zero(ci: tuple[float, float], tol: float = 1e-6) -> bool:
    """True if a (lo, hi) interval is indistinguishable from zero at the low end.

    Used as a noise floor: a mixture weight whose CI starts at ~0 is not
    estimable from the data and must not be shown as a rankable number.
    """
    lo, _hi = ci
    return lo <= tol


def zscore_within(group: dict[str, list[float]]) -> dict[str, float]:
    """Z-score of each key's mean against the pooled distribution of means."""
    means = {k: statistics.fmean(v) for k, v in group.items() if v}
    if not means:
        return {}
    pooled = list(means.values())
    center = statistics.fmean(pooled)
    spread = statistics.pstdev(pooled)
    if spread == 0:
        return {k: 0.0 for k in means}
    return {k: (m - center) / spread for k, m in means.items()}
