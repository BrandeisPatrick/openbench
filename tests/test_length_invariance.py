"""Guards against the length-confounding bug class (arXiv 2604.02547).

Raw counts scale with trajectory length; a model that runs longer out-counts one
that quits early for reasons unrelated to its reward. Only length-invariant
metrics may drive reward inference. These tests make that property enforceable.
"""

from __future__ import annotations

import pytest

from openbench.analysis.estimate import (
    LENGTH_INVARIANT,
    SIGNATURES,
    _assert_length_invariant,
)
from openbench.models import RunMetrics

# Metrics that are raw counts / length-scaled — must never enter the signature.
_FORBIDDEN_COUNTS = {
    "test_run_count", "file_edit_count", "verification_loop_count",
    "post_success_churn", "consecutive_failures_at_end", "out_of_scope_files",
    "revert_count", "assert_weakening_count", "skip_xfail_added",
    "total_tokens",
}


def test_signature_is_length_invariant():
    assert set(SIGNATURES).issubset(LENGTH_INVARIANT)
    assert not (set(SIGNATURES) & _FORBIDDEN_COUNTS)


def test_guard_rejects_a_count_metric():
    SIGNATURES["test_run_count"] = [0.0] * 7
    try:
        with pytest.raises(ValueError, match="length-invariant"):
            _assert_length_invariant()
    finally:
        del SIGNATURES["test_run_count"]
    _assert_length_invariant()  # restored


def test_every_invariant_metric_exists_on_runmetrics():
    fields = set(RunMetrics.model_fields)
    missing = LENGTH_INVARIANT - fields
    assert not missing, f"signature references nonexistent RunMetrics fields: {missing}"


def test_normalized_forms_are_bounded():
    # Rates/ratios live in [0, ~] and don't grow with trajectory length.
    m = RunMetrics(
        run_id="r", task_id="t", harness="h", model="m",
        verification_loop_count=10, file_edit_count=5,
        verification_loops_per_edit=2.0, post_success_churn=3,
        post_success_churn_rate=0.6, gave_up_failing=True,
    )
    assert m.verification_loops_per_edit == 2.0  # a ratio, not the count 10
    assert 0.0 <= m.post_success_churn_rate <= 1.0
    assert isinstance(m.gave_up_failing, bool)
