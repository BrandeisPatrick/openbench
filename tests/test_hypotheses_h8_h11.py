"""Tests for H8-H11: proxies, judge stubs, and difficulty-stratified metrics."""

from __future__ import annotations

import pytest

from openbench.analysis.estimate import COMPONENTS, _assert_length_invariant
from openbench.analysis.fingerprint import difficulty_stratified
from openbench.models import HardnessTier, RunMetrics


def _m(model, tier, **kw):
    return RunMetrics(run_id=f"{model}-{tier}-x", task_id="t", harness="h", model=model,
                      tier=tier, **kw)


def test_h8_h9_not_in_estimator_components():
    # H8/H9 have no valid deterministic metric (a file-overlap proxy cannot
    # measure inferred intent / convention recall — IFBench 2025). They must NOT
    # be estimator components; they live in the docs registry, judge-pending.
    assert "spec_literalism" not in COMPONENTS
    assert "pattern_recall" not in COMPONENTS
    _assert_length_invariant()


def test_judges_are_stubbed_with_prompts():
    from openbench.analysis import judges
    assert "{prompt}" in judges.INTENT_INFERENCE_PROMPT
    assert "{prompt}" in judges.RECALL_VS_DERIVE_PROMPT
    with pytest.raises(NotImplementedError):
        judges.intent_inference_score("p", "a", "g")
    with pytest.raises(NotImplementedError):
        judges.recall_vs_derive("p", "a", "x")


def test_h11_effort_slope_needs_two_tiers():
    # one tier only -> slope None (cannot estimate)
    one = [_m("A", HardnessTier.MAIN, test_runs_per_edit=1.0)]
    assert difficulty_stratified(one)["A"]["effort_difficulty_slope"] is None
    # effort rises with difficulty -> positive slope
    two = [
        _m("A", HardnessTier.EXTENDED, test_runs_per_edit=1.0),
        _m("A", HardnessTier.DIAMOND, test_runs_per_edit=5.0),
    ]
    assert difficulty_stratified(two)["A"]["effort_difficulty_slope"] > 0


def test_h10_verifies_when_easy():
    runs = [
        _m("A", HardnessTier.EXTENDED, verified_before_done=True),
        _m("A", HardnessTier.DIAMOND, verified_before_done=False),
    ]
    out = difficulty_stratified(runs)["A"]
    assert out["verifies_when_easy"] == 1.0  # verified on the easiest (extended) tier
