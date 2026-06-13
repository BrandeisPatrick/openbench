"""Offline tests for hardness scoring and tier assignment."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from openbench.mining.hardness import score_candidates
from openbench.models import HardnessTier, PRCandidate

CFG = {
    "hardness_weights": {
        "loc_changed": 0.20,
        "changed_files": 0.15,
        "module_spread": 0.15,
        "review_iterations": 0.15,
        "f2p_test_count": 0.15,
        "commit_count": 0.10,
        "dependency_depth": 0.10,
    },
    "tiers": {"main_percentile": 50, "diamond_percentile": 85},
}


def make_candidate(i: int) -> PRCandidate:
    """Synthetic candidate where every hardness feature grows with i."""
    return PRCandidate(
        repo="org/name",
        pr_number=i,
        title=f"PR {i}",
        base_commit="a" * 40,
        merge_commit="b" * 40,
        merged_at=datetime(2025, 7, 1, tzinfo=UTC),
        additions=100 * (i + 1),
        deletions=50 * (i + 1),
        changed_files=5 * (i + 1),
        commits=i + 1,
        review_comments=2 * (i + 1),
        top_level_dirs=[f"d{j}" for j in range(i + 1)],
        test_files_changed=[f"tests/test_{j}.py" for j in range(i + 1)],
        test_functions_changed=i + 1,
        dependency_depth=i,
    )


def test_scores_and_tiers_assigned():
    scored = score_candidates([make_candidate(i) for i in range(10)], CFG)
    assert len(scored) == 10
    assert all(c.hardness_score is not None for c in scored)
    assert all(c.tier is not None for c in scored)


def test_sorted_desc_and_monotonic():
    scored = score_candidates([make_candidate(i) for i in range(10)], CFG)
    scores = [c.hardness_score for c in scored]
    assert scores == sorted(scores, reverse=True)
    # bigger everything -> higher score: rank order matches pr_number order
    assert [c.pr_number for c in scored] == list(range(9, -1, -1))
    by_pr = {c.pr_number: c.hardness_score for c in scored}
    assert all(by_pr[i] < by_pr[i + 1] for i in range(9))


def test_tier_counts_match_percentiles():
    # 10 distinct scores: p85 cuts above the top 2, p50 above the top 5.
    scored = score_candidates([make_candidate(i) for i in range(10)], CFG)
    counts = Counter(c.tier for c in scored)
    assert counts[HardnessTier.DIAMOND] == 2
    assert counts[HardnessTier.MAIN] == 3
    assert counts[HardnessTier.EXTENDED] == 5
    # tiers must be ordered consistently with scores
    tiers = [c.tier for c in scored]
    assert tiers == sorted(tiers, key=[
        HardnessTier.DIAMOND, HardnessTier.MAIN, HardnessTier.EXTENDED
    ].index)


def test_single_candidate_no_zero_division():
    scored = score_candidates([make_candidate(0)], CFG)
    assert scored[0].hardness_score == 0.0
    assert scored[0].tier == HardnessTier.DIAMOND


def test_identical_pool_no_zero_division():
    scored = score_candidates([make_candidate(3) for _ in range(4)], CFG)
    assert all(c.hardness_score == 0.0 for c in scored)
    assert all(c.tier == HardnessTier.DIAMOND for c in scored)


def test_empty_pool():
    assert score_candidates([], CFG) == []
