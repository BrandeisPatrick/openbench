"""Synthetic-recovery tests for the Tier-2 reward-mixture estimator.

Build cohorts of RunMetrics whose behavior matches one component's signature
and check the estimator puts the most weight there. This validates the
machinery (z-scoring, NNLS, normalization), not the signature matrix itself —
that needs Tier-3 calibration models.
"""

from __future__ import annotations

import numpy as np

from openbench.analysis.estimate import (
    COMPONENTS,
    SIGNATURES,
    collinear_pairs,
    contrastive_weights,
    estimate_mixture,
    signature_matrix,
)
from openbench.models import RunMetrics


def _run(model: str, i: int, **overrides) -> RunMetrics:
    base = dict(
        run_id=f"t-{model}-{i}",
        task_id="t",
        harness="h",
        model=model,
        test_run_count=5,
        file_edit_count=5,
        test_runs_per_edit=1.0,
        verification_loop_count=2,
        exploration_fraction=0.3,
        search_before_edit_rate=0.5,
        guess_first_rate=0.5,
        thinking_fraction=0.2,
        total_tokens=1000,
    )
    base.update(overrides)
    return RunMetrics(**base)


def _jitter(rng: np.random.Generator, value: float, scale: float = 0.05) -> float:
    return float(value + rng.normal(0, scale))


def _cohort(gamer_overrides: dict, n: int = 12) -> list[RunMetrics]:
    """One deviant model + two background models forming the cohort."""
    rng = np.random.default_rng(7)
    runs: list[RunMetrics] = []
    for i in range(n):
        runs.append(_run("deviant", i, **{
            k: (v if isinstance(v, (bool, int)) else _jitter(rng, v))
            for k, v in gamer_overrides.items()
        }))
        runs.append(_run("background-a", i, test_runs_per_edit=_jitter(rng, 1.0)))
        runs.append(_run("background-b", i, test_runs_per_edit=_jitter(rng, 1.0)))
    return runs


def test_signature_matrix_shape():
    s, metrics = signature_matrix()
    assert s.shape == (len(SIGNATURES), len(COMPONENTS))
    assert metrics == list(SIGNATURES)


def test_recovers_outcome_gamer():
    runs = _cohort({
        "test_tampering": True,
        "assert_weakened": True,
        "skip_xfail_inserted": True,
        "post_success_churn_rate": 0.0,
        "guess_first_rate": 0.9,
        "search_before_edit_rate": 0.1,
        "verified_before_done": False,
    })
    est = estimate_mixture(runs, bootstrap_b=50)
    weights = est["deviant"].weights
    assert max(weights, key=weights.get) == "outcome_only"
    assert weights["outcome_only"] > 0.3


def test_recovers_process_verifier():
    runs = _cohort({
        "verification_loops_per_edit": 1.5,
        "verified_before_done": True,
        "test_runs_per_edit": 4.0,
    })
    est = estimate_mixture(runs, bootstrap_b=50)
    weights = est["deviant"].weights
    assert max(weights, key=weights.get) == "process_verifier"


def test_recovers_length_penalty():
    runs = _cohort({
        "early_stop": True,
        "gave_up_failing": True,
        "thinking_fraction": 0.02,
        "exploration_fraction": 0.05,
    })
    est = estimate_mixture(runs, bootstrap_b=50)
    weights = est["deviant"].weights
    assert max(weights, key=weights.get) == "length_penalty"


def test_weights_normalized_and_cis_present():
    runs = _cohort({"test_tampering": True, "assert_weakened": True})
    est = estimate_mixture(runs, bootstrap_b=50)
    for e in est.values():
        total = sum(e.weights.values())
        assert total == 0.0 or abs(total - 1.0) < 1e-6
        if e.weight_cis:
            for lo, hi in e.weight_cis.values():
                assert lo <= hi


def test_collinear_pairs_flags_gaming_suppressors():
    """outcome_only and anti_hack_penalty are near-antiparallel by design —
    passive observation cannot separate 'never games' from 'penalized for
    gaming'; that is exactly what the honeypot probe is for."""
    pairs = {(a, b) for a, b, _ in collinear_pairs()}
    assert ("outcome_only", "anti_hack_penalty") in pairs


def test_contrastive_weights_directionality():
    runs = _cohort({"test_tampering": True, "assert_weakened": True, "skip_xfail_inserted": True})
    coef = contrastive_weights(runs, "deviant")
    assert coef["test_tampering"] > 0
    assert coef["assert_weakened"] > 0


def test_prune_drops_zero_variance_and_correlated():
    from openbench.analysis.estimate import prune_redundant_metrics
    # >=8 runs (the min-correlation-sample floor); verified_before_done and
    # early_stop are perfect inverses (redundant); thinking_fraction is constant.
    runs = []
    for i in range(10):
        vb = i % 2 == 0
        runs.append(RunMetrics(
            run_id=f"r{i}", task_id="t", harness="h", model="m",
            verified_before_done=vb, early_stop=not vb,   # -1.0 correlated
            test_runs_per_edit=(2.0 if vb else 0.5),       # independent signal
            thinking_fraction=0.0,                          # zero variance
        ))
    keep, report = prune_redundant_metrics(runs, corr_threshold=0.85)
    # one of the inverse pair is dropped (the first in signature order is kept)
    assert not ({"verified_before_done", "early_stop"} <= keep)
    assert "thinking_fraction" in report["dropped_zero_variance"]
    assert report["merged_correlated"]  # the inverse pair was merged


def test_cells_split_by_harness_and_exclude_degenerate():
    """A model run under two harnesses is NOT pooled into one fingerprint: the
    degenerate (dreamed) cell is excluded, and the clean cell is labelled
    `model · harness` — never collapsed back to the bare model name."""
    runs: list[RunMetrics] = []
    # opus on a text-fence harness: dreamed sessions (no tests, no edits, "done").
    for i in range(4):
        runs.append(RunMetrics(
            run_id=f"opus-mini-{i}", task_id="t", harness="mini-swe", model="opus",
            test_run_count=0, file_edit_count=0, confabulated_completion=True,
        ))
    # opus on native: real work (edits, tests, verifies before done).
    for i in range(4):
        runs.append(RunMetrics(
            run_id=f"opus-native-{i}", task_id="t", harness="native", model="opus",
            test_run_count=5, file_edit_count=4, test_runs_per_edit=1.25,
            verification_loops_per_edit=1.0, verified_before_done=True,
        ))
    # two single-harness background models so the cohort can z-score.
    for name in ("bg-a", "bg-b"):
        for i in range(4):
            runs.append(RunMetrics(
                run_id=f"{name}-{i}", task_id="t", harness="native", model=name,
                test_run_count=3, file_edit_count=3, test_runs_per_edit=1.0,
            ))

    est = estimate_mixture(runs, bootstrap_b=20)

    assert "opus · native" in est           # clean cell kept, harness-labelled
    assert "opus" not in est                # never pooled into a bare-model fingerprint
    assert "opus · mini-swe" not in est     # degenerate cell excluded from estimation
    assert est["opus · native"].harness == "native"
    assert "bg-a" in est and "bg-b" in est  # single-harness models keep plain labels
