"""Hardness scoring: z-score features over the candidate pool, weighted sum, percentile tiers."""

from __future__ import annotations

from collections.abc import Callable
from statistics import mean, pstdev

from openbench.models import HardnessTier, PRCandidate

_FEATURES: dict[str, Callable[[PRCandidate], float]] = {
    "loc_changed": lambda c: c.additions + c.deletions,
    "changed_files": lambda c: c.changed_files,
    "module_spread": lambda c: len(c.top_level_dirs),
    "review_iterations": lambda c: c.review_comments,
    "f2p_test_count": lambda c: c.test_functions_changed,
    "commit_count": lambda c: c.commits,
    "dependency_depth": lambda c: c.dependency_depth,
}


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy default) over pre-sorted values."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = pct / 100.0 * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (rank - lo) * (sorted_vals[hi] - sorted_vals[lo])


def score_candidates(cands: list[PRCandidate], cfg: dict) -> list[PRCandidate]:
    """Assign hardness_score and tier to every candidate; return them sorted by score desc."""
    if not cands:
        return []
    weights = cfg["hardness_weights"]
    cols = {name: [float(fn(c)) for c in cands] for name, fn in _FEATURES.items()}
    stats: dict[str, tuple[float, float]] = {}
    for name, vals in cols.items():
        sd = pstdev(vals) if len(vals) > 1 else 0.0
        stats[name] = (mean(vals), sd if sd > 0 else 1.0)

    for i, c in enumerate(cands):
        c.hardness_score = sum(
            weights[name] * (cols[name][i] - stats[name][0]) / stats[name][1]
            for name in _FEATURES
        )

    scores = sorted(c.hardness_score for c in cands)  # type: ignore[type-var]
    main_cut = _percentile(scores, cfg["tiers"]["main_percentile"])
    diamond_cut = _percentile(scores, cfg["tiers"]["diamond_percentile"])
    for c in cands:
        assert c.hardness_score is not None
        if c.hardness_score >= diamond_cut:
            c.tier = HardnessTier.DIAMOND
        elif c.hardness_score >= main_cut:
            c.tier = HardnessTier.MAIN
        else:
            c.tier = HardnessTier.EXTENDED

    return sorted(cands, key=lambda c: c.hardness_score or 0.0, reverse=True)
