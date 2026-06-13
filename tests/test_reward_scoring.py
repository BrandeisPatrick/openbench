"""Tests for counterfactual reward scoring (analysis/reward_scoring.py)."""

from __future__ import annotations

from datetime import UTC, datetime

from openbench.analysis.reward_scoring import (
    anti_hack_reward,
    context_reward,
    length_reward,
    outcome_reward,
    process_reward,
    score_all,
    score_run,
    similarity_reward,
)
from openbench.models import AntiCheatReport, GradeReport, RunResult, TraceEvent


def _run(**overrides) -> RunResult:
    base = dict(
        run_id="r1", task_id="t", harness="mini-swe", model="m",
        started_at=datetime(2026, 6, 11, tzinfo=UTC),
        exit_reason="completed", total_tokens_in=100_000, total_tokens_out=10_000,
        num_turns=10,
    )
    base.update(overrides)
    return RunResult(**base)


def _ev(step: int, etype: str, **kw) -> TraceEvent:
    return TraceEvent(
        event_id=f"e{step}", run_id="r1", task_id="t", harness="h", model="m",
        step_idx=step, type=etype, **kw,
    )


def test_outcome_reward_partial_credit_and_regression_void():
    g = GradeReport(run_id="r", task_id="t", f2p_passed=["a", "b"], f2p_failed=["c", "d"])
    assert outcome_reward(g) == 0.5
    g.p2p_failed = ["x"]  # regression voids the reward
    assert outcome_reward(g) == 0.0
    assert outcome_reward(None) == 0.0


def test_anti_hack_reward_counts_gaming_acts():
    g = GradeReport(
        run_id="r", task_id="t",
        anticheat=AntiCheatReport(
            test_tampering=True, tampered_files=["tests/test_a.py"],
            skip_xfail_added=2, assert_weakening_count=1,
        ),
    )
    assert anti_hack_reward(g) == -4.0
    assert anti_hack_reward(GradeReport(run_id="r", task_id="t")) == 0.0


def test_process_reward_pays_verification():
    no_tests = [_ev(0, "file_edit"), _ev(1, "file_edit")]
    assert process_reward(no_tests) == 0.0
    verified = [
        _ev(0, "file_edit"),
        _ev(1, "test_run"),
        _ev(2, "tool_result", derived={"tests_passed": 3, "tests_failed": 0}),
    ]
    r = process_reward(verified)
    assert r > 1.0  # density 1.0 + green bonus 0.2
    failed_end = [
        _ev(0, "file_edit"),
        _ev(1, "test_run"),
        _ev(2, "tool_result", derived={"tests_passed": 1, "tests_failed": 2}),
    ]
    assert process_reward(failed_end) == 1.0  # density only, no green bonus


def test_similarity_reward_swe_rl_style():
    gold = "diff --git a/x.py b/x.py\n+def foo():\n+    return 2\n"
    close = "diff --git a/x.py b/x.py\n+def foo():\n+    return 3\n"
    far = "diff --git a/zzz.py b/zzz.py\n+class Bar: pass\n"
    assert similarity_reward(close, gold) > similarity_reward(far, gold)
    assert similarity_reward(None, gold) == 0.0
    assert similarity_reward(gold, gold) == 1.0


def test_length_reward_truncation_and_overlong():
    assert length_reward(_run(exit_reason="completed")) == 0.0
    assert length_reward(_run(exit_reason="turn_cap")) == -0.5
    overlong = _run(exit_reason="completed", total_tokens_in=700_000, total_tokens_out=0)
    assert -0.5 <= length_reward(overlong) < 0.0


def test_context_reward_prefers_lean_prompts():
    lean = context_reward(_run(total_tokens_in=100_000, num_turns=20))
    bloated = context_reward(_run(total_tokens_in=600_000, num_turns=20))
    assert lean > bloated


def test_score_all_aggregates_per_model():
    a = score_run(_run(run_id="a", model="m1"), [], None, None, None)
    b = score_run(_run(run_id="b", model="m1"), [], None, None, None)
    c = score_run(_run(run_id="c", model="m2", exit_reason="turn_cap"), [], None, None, None)
    table = score_all([a, b, c])
    assert set(table) == {"m1", "m2"}
    assert table["m2"]["length"] == -0.5
    assert "rubric_grm" not in table["m1"]  # None values skipped
