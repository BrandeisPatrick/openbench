"""Unit tests for BehaviorProfile metrics over synthetic TraceEvents."""

from __future__ import annotations

from datetime import UTC, datetime

from openbench.behavior.profile import compute_profile
from openbench.models import GradeReport, HardnessTier, RunResult, Task, TraceEvent

RUN_ID = "demo__repo-1--tooluse--m--20260706-000000"


def _run(exit_reason: str = "completed", num_turns: int = 0, **kw) -> RunResult:
    return RunResult(
        run_id=RUN_ID, task_id="demo__repo-1", harness="tooluse", model="m",
        started_at=datetime(2026, 7, 6, tzinfo=UTC), exit_reason=exit_reason,
        num_turns=num_turns, **kw,
    )


def _task(**kw) -> Task:
    return Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0, **kw,
    )


def _grade(f2p_passed=(), f2p_failed=("t::a",)) -> GradeReport:
    return GradeReport(
        run_id=RUN_ID, task_id="demo__repo-1", applies_cleanly=True, builds=True,
        f2p_passed=list(f2p_passed), f2p_failed=list(f2p_failed),
        graded_at=datetime(2026, 7, 6, tzinfo=UTC),
    )


_STEP = 0


def _ev(etype: str, **kw) -> TraceEvent:
    global _STEP
    _STEP += 1
    return TraceEvent(
        event_id=f"{RUN_ID}-{_STEP}", run_id=RUN_ID, task_id="demo__repo-1",
        harness="tooluse", model="m", step_idx=_STEP, type=etype, **kw,
    )


def _turn(command: str | None, output: str = "", exit_code: int = 0,
          etype: str = "shell", files: list[str] | None = None) -> list[TraceEvent]:
    """One assistant turn: assistant_msg then (optionally) an action + result."""
    events = [_ev("assistant_msg", content="working")]
    if command is not None:
        events.append(_ev(etype, tool_name="Bash",
                          tool_args_digest={"command": command},
                          files_touched=files or []))
        derived = {}
        from openbench.traces.schema import parse_pytest_counts

        counts = parse_pytest_counts(output)
        if counts:
            derived = counts
        events.append(_ev("tool_result", content=output, exit_code=exit_code,
                          derived=derived))
    return events


def test_verification_axis_green_and_verified():
    events = (
        _turn("pytest -q", "1 failed, 2 passed in 0.1s", 1, "test_run")
        + _turn("cat > src/foo.py", files=["src/foo.py"], etype="file_edit")
        + _turn("pytest -q", "3 passed in 0.1s", 0, "test_run")
    )
    p = compute_profile(_run(num_turns=3), events, _grade(("t::a",), ()), _task())
    assert p.test_run_count == 2
    assert p.green_observed is True
    assert p.verified_before_done is True
    assert p.tested_before_first_edit is True  # reproduced before editing
    assert p.verification_loop_rate == 1.0  # one edit->test loop / one edit
    assert p.test_run_rate == 2 / 3
    assert p.gave_up_failing is False
    assert p.recovery_rate == 1.0  # the one failing episode reached green
    assert p.turns_to_first_green == 3
    assert p.confabulated_completion is False


def test_never_tests_never_verifies():
    events = (
        _turn("cat > src/foo.py", files=["src/foo.py"], etype="file_edit")
        + _turn("echo OPENBENCH_DONE", "OPENBENCH_DONE", 0)
    )
    p = compute_profile(_run(num_turns=2), events, _grade(), _task())
    assert p.test_run_count == 0
    assert p.green_observed is False
    assert p.verified_before_done is False
    assert p.tested_before_first_edit is False
    assert p.gave_up_failing is None  # no tests ever run — not measurable
    assert p.recovery_rate is None
    assert p.confabulated_completion is True  # declared done, never saw green, failed


def test_persistence_retry_verbatim_and_grind():
    events = (
        _turn("pytest -q", "2 failed in 0.1s", 1, "test_run")
        + _turn("pytest -q", "2 failed in 0.1s", 1, "test_run")  # identical retry
        + _turn("pytest -q tests/test_x.py", "2 failed in 0.1s", 1, "test_run")  # adapted
    )
    p = compute_profile(_run(exit_reason="turn_cap", num_turns=3), events, _grade(), _task())
    # failures with a next action: turns 1 and 2; turn 1's retry is verbatim
    assert p.retry_verbatim_rate == 0.5
    assert p.grind_to_cap is True
    assert p.gave_up_failing is True
    assert p.consecutive_failures_at_end == 3
    assert p.test_progress_rate == 0.0
    assert p.recovery_rate == 0.0
    # cap exits are not "completed": no confabulation claim
    assert p.confabulated_completion is False


def test_exploration_axis():
    events = (
        _turn("grep -r foo src/", "src/foo.py: def foo", 0, "search", files=["src/foo.py"])
        + _turn("grep -r foo src/", "src/foo.py: def foo", 0, "search", files=["src/foo.py"])
        + _turn("cat > src/foo.py", files=["src/foo.py"], etype="file_edit")
        + _turn("cat > src/new_module.py", files=["src/new_module.py"], etype="file_edit")
    )
    p = compute_profile(_run(num_turns=4), events, None, _task())
    assert p.search_before_edit_rate == 1.0  # foo.py was seen; new_module is creation
    assert p.re_read_rate == 0.5  # second grep re-touches foo.py
    assert p.files_explored == 1
    assert p.exploration_event_share == 0.5  # 2 searches / 4 actions
    assert 0 < p.exploration_fraction < 1


def test_scope_and_redundancy_against_gold():
    gold = (
        "diff --git a/src/foo.py b/src/foo.py\n"
        "--- a/src/foo.py\n+++ b/src/foo.py\n"
        "@@ -1,2 +1,2 @@\n def foo():\n-    return 1\n+    return 2\n"
    )
    agent = (
        "diff --git a/src/foo.py b/src/foo.py\n"
        "--- a/src/foo.py\n+++ b/src/foo.py\n"
        "@@ -1,2 +1,3 @@\n def foo():\n-    return 1\n+    return 2\n+# noqa\n"
        "diff --git a/src/bar.py b/src/bar.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/src/bar.py\n"
        "@@ -0,0 +1 @@\n+BAR = 1\n"
    )
    events = (
        _turn("cat > src/foo.py", files=["src/foo.py"], etype="file_edit")
        + _turn("cat > src/foo.py", files=["src/foo.py"], etype="file_edit")
        + _turn("cat > src/bar.py", files=["src/bar.py"], etype="file_edit")
    )
    p = compute_profile(_run(num_turns=3), events, None, _task(),
                        agent_patch_text=agent, gold_patch_text=gold)
    assert p.diff_size_ratio == 2.0  # 4 changed lines vs 2 gold
    assert p.file_jaccard == 0.5  # foo.py shared; bar.py extra
    assert p.out_of_scope_ratio == 0.5
    assert p.redundancy_rate == 1 - 2 / 3  # 3 path-edits over 2 distinct paths
    assert p.file_edit_count == 3


def test_malformed_action_rate_counts_nudged_turns():
    events = (
        _turn("ls src/", "foo.py", 0, "search")
        + _turn(None)  # prose-only turn: harness had to nudge
        + _turn("echo OPENBENCH_DONE", "OPENBENCH_DONE", 0)
    )
    p = compute_profile(_run(num_turns=3), events, None, _task())
    assert p.malformed_action_rate == 1 / 3


def test_empty_trace_yields_outcome_only_profile():
    p = compute_profile(_run(exit_reason="crash"), [], None, None)
    assert p.test_run_count == 0
    assert p.test_run_rate is None
    assert p.exploration_fraction is None
    assert p.malformed_action_rate is None
    assert p.resolved is None


def test_task_metadata_flows_through():
    task = _task(difficulty="<15 min fix", source="swebench-verified")
    p = compute_profile(_run(), [], _grade(("t::a",), ()), task)
    assert p.difficulty == "<15 min fix"
    assert p.source == "swebench-verified"
    assert p.resolved is True
    assert p.f2p_pass_rate == 1.0
