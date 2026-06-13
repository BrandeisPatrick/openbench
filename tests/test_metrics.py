"""Offline tests for analysis.metrics.compute_metrics over synthetic traces."""

from __future__ import annotations

from datetime import UTC, datetime

from openbench.analysis.metrics import compute_metrics
from openbench.models import (
    AntiCheatReport,
    GradeReport,
    RunResult,
    TraceEvent,
)


def _run(**kw) -> RunResult:
    defaults = dict(
        run_id="r1",
        task_id="t1",
        harness="claude-code",
        model="m1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(kw)
    return RunResult(**defaults)


def _ev(
    idx: int,
    type: str,
    files: list[str] | None = None,
    tool_name: str | None = None,
    failed: int | None = None,
    passed: int | None = None,
) -> TraceEvent:
    derived = {}
    if failed is not None:
        derived["tests_failed"] = failed
    if passed is not None:
        derived["tests_passed"] = passed
    return TraceEvent(
        event_id=f"e{idx}",
        run_id="r1",
        task_id="t1",
        harness="claude-code",
        model="m1",
        step_idx=idx,
        type=type,
        tool_name=tool_name,
        files_touched=files or [],
        derived=derived,
    )


def test_disciplined_run_verified_before_done() -> None:
    events = [
        _ev(0, "run_start"),
        _ev(1, "search", files=["src/a.py"]),
        _ev(2, "tool_result", files=["src/b.py"]),
        _ev(3, "file_edit", files=["src/a.py"]),
        _ev(4, "test_run", failed=2, passed=0),
        _ev(5, "file_edit", files=["src/a.py"]),
        _ev(6, "file_edit", files=["src/b.py"]),
        _ev(7, "test_run", failed=1, passed=1),
        _ev(8, "file_edit", files=["src/a.py"]),
        _ev(9, "test_run", failed=0, passed=3),
    ]
    m = compute_metrics(_run(), events, None, None)
    assert m.test_run_count == 3
    assert m.file_edit_count == 4
    assert m.test_runs_per_edit == 0.75
    assert m.verified_before_done is True
    assert m.early_stop is False
    assert m.verification_loop_count == 3
    assert m.post_success_churn == 0
    assert m.consecutive_failures_at_end == 0
    assert m.exploration_fraction == 0.3
    assert m.search_before_edit_rate == 1.0
    assert m.guess_first_rate == 0.0
    assert m.revert_count == 1  # src/a.py edited 3 times (churn proxy)


def test_early_stop_with_trailing_failures() -> None:
    events = [
        _ev(0, "run_start"),
        _ev(1, "file_edit", files=["src/x.py"]),
        _ev(2, "test_run", failed=1, passed=0),
        _ev(3, "file_edit", files=["src/x.py"]),
        _ev(4, "test_run", failed=1, passed=0),
    ]
    m = compute_metrics(_run(), events, None, None)
    assert m.early_stop is True
    assert m.verified_before_done is False
    assert m.consecutive_failures_at_end == 2
    assert m.verification_loop_count == 2
    assert m.exploration_fraction == 0.2
    # No search/read before edits.
    assert m.search_before_edit_rate == 0.0
    assert m.guess_first_rate == 1.0


def test_no_test_runs_is_early_stop() -> None:
    events = [
        _ev(0, "run_start"),
        _ev(1, "file_edit", files=["src/x.py"]),
        _ev(2, "file_edit", files=["src/y.py"]),
    ]
    m = compute_metrics(_run(), events, None, None)
    assert m.early_stop is True
    assert m.test_run_count == 0
    assert m.verified_before_done is False
    assert m.test_runs_per_edit == 0.0
    assert m.exploration_fraction == 1 / 3


def test_post_success_churn() -> None:
    events = [
        _ev(0, "run_start"),
        _ev(1, "file_edit", files=["src/a.py"]),
        _ev(2, "test_run", failed=0, passed=2),
        _ev(3, "file_edit", files=["src/a.py"]),
        _ev(4, "file_edit", files=["src/b.py"]),
        _ev(5, "test_run", failed=0, passed=2),
        _ev(6, "file_edit", files=["src/c.py"]),
    ]
    m = compute_metrics(_run(), events, None, None)
    assert m.post_success_churn == 3  # edits at 3, 4, 6 after first green at 2
    assert m.early_stop is False
    # No green test_run in the last 10% (the tail is the final edit).
    assert m.verified_before_done is False
    assert m.verification_loop_count == 2


def test_edit_after_final_green_test_blocks_verified() -> None:
    events = (
        [_ev(0, "run_start")]
        + [_ev(i, "assistant_msg") for i in range(1, 18)]
        + [_ev(18, "test_run", failed=0, passed=1), _ev(19, "file_edit", files=["src/a.py"])]
    )
    m = compute_metrics(_run(), events, None, None)
    # Green test_run sits in the last 10% of 20 events, but an edit follows it.
    assert m.verified_before_done is False
    assert m.early_stop is False
    assert m.post_success_churn == 1


def test_tokens_and_grade_copy() -> None:
    run = _run(total_tokens_in=700, total_tokens_out=200, total_thinking_tokens=100)
    grade = GradeReport(
        run_id="r1",
        task_id="t1",
        anticheat=AntiCheatReport(
            test_tampering=True, assert_weakening_count=3, skip_xfail_added=2
        ),
    )
    m = compute_metrics(run, [_ev(0, "run_start")], grade, None)
    assert m.total_tokens == 1000
    assert m.thinking_fraction == 0.1
    assert m.test_tampering is True
    assert m.assert_weakening_count == 3
    assert m.skip_xfail_added == 2


AGENT_PATCH = """\
--- a/src/a.py
+++ b/src/a.py
@@ -1,2 +1,2 @@
 import os
-X = 1
+X = 2
"""

GOLD_PATCH = """\
--- a/src/a.py
+++ b/src/a.py
@@ -1,2 +1,2 @@
 import os
-X = 1
+X = 2
--- a/src/b.py
+++ b/src/b.py
@@ -1,2 +1,2 @@
 import os
-Y = 1
+Y = 2
"""

OFF_SCOPE_PATCH = AGENT_PATCH + """\
--- a/src/zzz.py
+++ b/src/zzz.py
@@ -1,2 +1,2 @@
 import os
-Z = 1
+Z = 2
"""


def test_scope_metrics_vs_gold() -> None:
    m = compute_metrics(
        _run(), [], None, None, agent_patch_text=AGENT_PATCH, gold_patch_text=GOLD_PATCH
    )
    assert m.diff_size_ratio == 0.5  # 2 changed lines vs 4
    assert m.file_jaccard == 0.5  # {a} vs {a, b}
    assert m.out_of_scope_files == 0

    m2 = compute_metrics(
        _run(), [], None, None, agent_patch_text=OFF_SCOPE_PATCH, gold_patch_text=GOLD_PATCH
    )
    assert m2.out_of_scope_files == 1  # src/zzz.py not in gold
    assert m2.diff_size_ratio == 1.0

    m3 = compute_metrics(_run(), [], None, None)
    assert m3.diff_size_ratio is None
    assert m3.file_jaccard is None
    assert m3.out_of_scope_files is None


def test_re_read_rate_and_context_tokens() -> None:
    events = [
        _ev(0, "search", files=["a.py"]),
        _ev(1, "search", files=["b.py"]),
        _ev(2, "search", files=["a.py"]),  # re-read
        _ev(3, "search", files=["a.py", "c.py"]),  # re-read (a.py seen)
    ]
    run = _run(total_tokens_in=50_000, num_turns=10)
    m = compute_metrics(run, events, None, None)
    assert m.re_read_rate == 0.5
    # No reads at all -> None, not 0 (unknown, excluded from fingerprints).
    m2 = compute_metrics(run, [_ev(0, "file_edit", files=["a.py"])], None, None)
    assert m2.re_read_rate is None


def test_grounded_metrics_recovery_progress_redundancy():
    # fail -> fail -> pass : recovers; progress improves on each transition
    events = [
        _ev(0, "test_run", failed=2, passed=1),
        _ev(1, "test_run", failed=1, passed=2),
        _ev(2, "test_run", failed=0, passed=3),
        _ev(3, "file_edit", files=["a.py"]),
        _ev(4, "file_edit", files=["a.py"]),  # redundant re-edit of a.py
    ]
    m = compute_metrics(_run(), events, None, None)
    assert m.recovery_rate == 1.0          # both failing runs eventually pass
    assert m.progress_proxy == 1.0         # passing rose on every transition
    assert m.redundancy_rate == 0.5        # 2 edits, 1 distinct path

    # never recovers
    bad = [_ev(0, "test_run", failed=2, passed=0), _ev(1, "test_run", failed=2, passed=0)]
    assert compute_metrics(_run(), bad, None, None).recovery_rate == 0.0


def test_action_efficiency_and_plan_ned():
    gold = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/y.py b/y.py\n--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    # agent touches x.py (matches gold) + z.py (extra) → efficiency 2/2 capped? 
    agent = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/z.py b/z.py\n--- a/z.py\n+++ b/z.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    events = [_ev(0, "file_edit", files=["x.py"]), _ev(1, "file_edit", files=["z.py"])]
    m = compute_metrics(_run(), events, None, None, agent_patch_text=agent, gold_patch_text=gold)
    assert m.action_efficiency == 1.0      # 2 gold / 2 agent files
    assert m.plan_ned is not None and m.plan_ned > 0  # z.py != y.py, ordering differs
