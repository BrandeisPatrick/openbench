"""H13 long-context recall: deterministic working-memory metric (EXPERIMENTS.md E3).

The metric must only fire on genuine dormant-context recall: an artifact seen
long ago, NOT in the prompt, NOT re-read in between, referenced in reasoning.
Each test plants exactly one of those escape hatches and asserts the gate holds.
"""

from __future__ import annotations

from openbench.analysis.metrics import (
    _RECALL_WINDOW_TURNS,
    _extract_artifacts,
    compute_metrics,
)
from openbench.models import RunMetrics, RunResult, TraceEvent


def _run(**kw) -> RunResult:
    from datetime import UTC, datetime

    defaults = dict(
        run_id="r1", task_id="t1", harness="mini-swe", model="m1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(kw)
    return RunResult(**defaults)


def _ev(idx: int, type: str, content: str | None = None, files: list[str] | None = None) -> TraceEvent:
    return TraceEvent(
        event_id=f"e{idx}", run_id="r1", task_id="t1", harness="mini-swe", model="m1",
        step_idx=idx, type=type, content=content, files_touched=files or [],
    )


def _trajectory(mention_at_turn: int, mention: str, n_turns: int = 16) -> list[TraceEvent]:
    """n_turns assistant turns; tool_result with the artifact at turn 1;
    the reasoning mention text injected at `mention_at_turn`."""
    events: list[TraceEvent] = [_ev(0, "run_start")]
    idx = 1
    for turn in range(1, n_turns + 1):
        text = mention if turn == mention_at_turn else f"continuing step {turn}"
        events.append(_ev(idx, "assistant_msg", content=text))
        idx += 1
        if turn == 1:
            events.append(
                _ev(idx, "tool_result", content="Traceback: ZeroDivisionError in solver_core.py")
            )
            idx += 1
    return events


def test_artifact_extraction_is_conservative() -> None:
    arts = _extract_artifacts(
        "see src/pkg/solver_core.py raising ZeroDivisionError; "
        "run tests/test_x.py::test_div; def compute_flux(x): the and from"
    )
    assert "src/pkg/solver_core.py" in arts
    assert "ZeroDivisionError" in arts
    assert "tests/test_x.py::test_div" in arts
    assert "compute_flux" in arts
    # common words never become artifacts
    assert not {"the", "and", "from", "see"} & arts


def test_long_range_recall_detected() -> None:
    events = _trajectory(
        mention_at_turn=14, mention="this matches the ZeroDivisionError from earlier"
    )
    m = compute_metrics(_run(), events, None, None)
    assert m.long_range_recall_rate is not None and m.long_range_recall_rate > 0
    assert m.recall_distance_norm is not None and m.recall_distance_norm > 0


def test_prompt_artifacts_never_count() -> None:
    events = _trajectory(
        mention_at_turn=14, mention="this matches the ZeroDivisionError from earlier"
    )
    m = compute_metrics(
        _run(), events, None, None,
        prompt_text="Fix the ZeroDivisionError reported by users.",
    )
    assert m.long_range_recall_rate == 0.0  # prompt is permanently in view


def test_reread_resets_the_clock() -> None:
    events = _trajectory(
        mention_at_turn=14, mention="this matches the ZeroDivisionError from earlier"
    )
    # Re-surface the artifact at turn 12 (< window before the mention).
    events.insert(-4, _ev(99, "tool_result", content="again: ZeroDivisionError"))
    for i, ev in enumerate(events):
        ev.step_idx = i
    m = compute_metrics(_run(), events, None, None)
    assert m.long_range_recall_rate == 0.0  # distance 2, not long-range — H7, not H13


def test_short_trajectory_is_none_not_zero() -> None:
    events = _trajectory(mention_at_turn=3, mention="x", n_turns=_RECALL_WINDOW_TURNS - 2)
    m = compute_metrics(_run(), events, None, None)
    assert m.long_range_recall_rate is None  # cannot exhibit recall — unmeasurable
    assert m.recall_distance_norm is None


def test_no_recalls_means_zero_rate_none_distance() -> None:
    events = _trajectory(mention_at_turn=0, mention="never")  # no qualifying mention
    m = compute_metrics(_run(), events, None, None)
    assert m.long_range_recall_rate == 0.0
    assert m.recall_distance_norm is None  # distance undefined without recalls


def test_h13_fields_are_length_invariant_signature_metrics() -> None:
    from openbench.analysis.estimate import LENGTH_INVARIANT, SIGNATURES

    assert "long_range_recall_rate" in LENGTH_INVARIANT
    assert "recall_distance_norm" in LENGTH_INVARIANT
    assert "long_range_recall_rate" in SIGNATURES
    assert set(RunMetrics.model_fields) >= {"long_range_recall_rate", "recall_distance_norm"}


# --- E3b: action-grounded recall (EXPERIMENTS.md E3b, registered 2026-06-12) ---

def _cmd_ev(idx: int, command: str) -> TraceEvent:
    return TraceEvent(
        event_id=f"e{idx}", run_id="r1", task_id="t1", harness="mini-swe", model="m1",
        step_idx=idx, type="shell", tool_name="Bash",
        tool_args_digest={"command": command},
    )


def _action_trajectory(command: str, result_output: str, n_turns: int = 16) -> list[TraceEvent]:
    """Plants src/pkg/solver_core.py in a turn-1 tool_result; executes `command`
    (+ its result) right after turn 14's assistant message."""
    events: list[TraceEvent] = [_ev(0, "run_start")]
    idx = 1
    for turn in range(1, n_turns + 1):
        events.append(_ev(idx, "assistant_msg", content=f"continuing step {turn}"))
        idx += 1
        if turn == 1:
            events.append(_ev(idx, "tool_result", content="error in src/pkg/solver_core.py"))
            idx += 1
        if turn == 14:
            events.append(_cmd_ev(idx, command))
            idx += 1
            events.append(_ev(idx, "tool_result", content=result_output))
            idx += 1
    return events


def test_action_recall_detected_from_executed_command() -> None:
    events = _action_trajectory("pytest src/pkg/solver_core.py -x", "1 passed")
    m = compute_metrics(_run(), events, None, None)
    assert m.action_recall_rate is not None and m.action_recall_rate > 0
    # the dormant artifact appears only in the command, never in prose
    assert m.long_range_recall_rate == 0.0


def test_action_recall_precision_target_existed() -> None:
    events = _action_trajectory("pytest src/pkg/solver_core.py -x", "3 failed, 2 passed")
    m = compute_metrics(_run(), events, None, None)
    assert m.action_recall_precision == 1.0  # failing tests still prove the path was real


def test_action_recall_precision_target_missing() -> None:
    events = _action_trajectory(
        "pytest src/pkg/solver_core.py -x",
        "ERROR: file or directory not found: src/pkg/solver_core.py",
    )
    m = compute_metrics(_run(), events, None, None)
    assert m.action_recall_precision == 0.0  # hallucinated memory, not retention


def test_error_class_recall_is_not_checkable() -> None:
    # ZeroDivisionError has no existence ground truth -> counts for the rate,
    # contributes nothing to precision.
    events = _action_trajectory("grep -rn ZeroDivisionError sympy", "no match")
    events[2] = _ev(2, "tool_result", content="Traceback: ZeroDivisionError")
    m = compute_metrics(_run(), events, None, None)
    assert m.action_recall_rate is not None and m.action_recall_rate > 0
    assert m.action_recall_precision is None


def test_fenced_command_text_does_not_count_as_prose_recall() -> None:
    # The artifact resurfaces ONLY inside a ```bash fence of the assistant
    # message (mini-swe embeds commands there) — prose channel must strip it.
    events = _trajectory(
        mention_at_turn=14,
        mention="```bash\npytest src/pkg/solver_core.py\n```",
    )
    events[2] = _ev(2, "tool_result", content="error in src/pkg/solver_core.py")
    m = compute_metrics(_run(), events, None, None)
    assert m.long_range_recall_rate == 0.0  # action text is not prose recall
    assert m.action_recall_rate is None  # never executed -> not an action either


def test_short_trajectory_action_metrics_none() -> None:
    events = [_ev(0, "run_start"), _ev(1, "assistant_msg", content="hi"),
              _cmd_ev(2, "pytest src/pkg/solver_core.py")]
    m = compute_metrics(_run(), events, None, None)
    assert m.action_recall_rate is None
    assert m.action_recall_precision is None


def test_e3b_deployed_after_calibration_pass() -> None:
    # Deployment rule (EXPERIMENTS.md E3b): SIGNATURES only after the DeepSeek
    # prose<->action calibration passes. It PASSED 2026-06-12 (rho=0.713,
    # within-model 0.70/0.76, bar 0.4) -> the metrics are now signature inputs.
    from openbench.analysis.estimate import LENGTH_INVARIANT, SIGNATURES

    assert "action_recall_rate" in LENGTH_INVARIANT
    assert "action_recall_precision" in LENGTH_INVARIANT
    assert "action_recall_rate" in SIGNATURES
    assert "action_recall_precision" in SIGNATURES
