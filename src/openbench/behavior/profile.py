"""Per-run behavior profile: deterministic metrics over a normalized trace.

`compute_profile` is a pure function over already-loaded models — no docker,
no filesystem, fully offline-testable. Metrics are descriptive observations
grouped into four axes (verification, persistence, exploration, efficiency)
plus failure modes; the comparison layer (compare.py) turns them into
generational contrasts.
"""

from __future__ import annotations

from pydantic import BaseModel

from openbench.models import GradeReport, RunResult, Task, TraceEvent

# Event types that represent the agent acting on the world (one per command).
ACTION_TYPES = ("test_run", "search", "shell", "file_edit")

# Exit reasons where the harness, not the model, ended the run.
CAP_EXITS = ("turn_cap", "cost_cap", "timeout")


class BehaviorProfile(BaseModel):
    """One run's behavioral fingerprint. Lives at runs/<run_id>/profile.json.

    `None` always means "not measurable on this run" (no denominator), never
    zero — the comparison layer drops Nones instead of counting them.
    """

    # identity / outcome
    run_id: str
    task_id: str
    harness: str
    model: str
    exit_reason: str | None = None
    difficulty: str | None = None
    source: str | None = None  # task provenance: swebench-verified | mined
    resolved: bool | None = None
    f2p_pass_rate: float | None = None

    # axis: verification & testing
    test_run_count: int = 0
    test_run_rate: float | None = None  # test runs per assistant turn
    tested_before_first_edit: bool | None = None  # None when the run never edited
    verification_loop_rate: float | None = None  # edit->test loops per edit
    verified_before_done: bool = False
    green_observed: bool = False

    # axis: persistence & recovery
    recovery_rate: float | None = None  # failing episodes later seen green
    retry_verbatim_rate: float | None = None  # identical command after a failure
    test_progress_rate: float | None = None  # consecutive test pairs improving
    gave_up_failing: bool | None = None  # None when no tests were ever run
    grind_to_cap: bool = False
    consecutive_failures_at_end: int = 0

    # axis: exploration & context use
    exploration_fraction: float | None = None  # events before the first edit
    search_before_edit_rate: float | None = None
    exploration_event_share: float | None = None  # search actions / all actions
    files_explored: int = 0
    re_read_rate: float | None = None

    # axis: efficiency & scope (raw counts are first-class here)
    num_turns: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    file_edit_count: int = 0
    turns_to_first_green: int | None = None
    diff_size_ratio: float | None = None
    file_jaccard: float | None = None
    out_of_scope_ratio: float | None = None
    redundancy_rate: float | None = None

    # failure modes
    confabulated_completion: bool | None = None  # needs a grade to be meaningful
    malformed_action_rate: float | None = None  # assistant turns yielding no action


# Axis map — drives report sections, delta tables, and the radar figure.
# (metric, higher_is) where higher_is describes the *newer-generation*
# direction hypothesis used only for figure orientation, never for stats.
AXES: dict[str, list[str]] = {
    "verification": [
        "test_run_rate",
        "tested_before_first_edit",
        "verification_loop_rate",
        "verified_before_done",
        "green_observed",
    ],
    "persistence": [
        "recovery_rate",
        "retry_verbatim_rate",
        "test_progress_rate",
        "gave_up_failing",
        "grind_to_cap",
        "consecutive_failures_at_end",
    ],
    "exploration": [
        "exploration_fraction",
        "search_before_edit_rate",
        "exploration_event_share",
        "files_explored",
        "re_read_rate",
    ],
    "efficiency": [
        "num_turns",
        "total_tokens",
        "cost_usd",
        "file_edit_count",
        "turns_to_first_green",
        "diff_size_ratio",
        "file_jaccard",
        "out_of_scope_ratio",
        "redundancy_rate",
    ],
    "failure_modes": [
        "confabulated_completion",
        "malformed_action_rate",
    ],
}


def _tests_failed(ev: TraceEvent) -> int:
    return int(ev.derived.get("tests_failed") or 0)


def _tests_passed(ev: TraceEvent) -> int:
    return int(ev.derived.get("tests_passed") or 0)


def _is_green(ev: TraceEvent) -> bool:
    return _tests_failed(ev) == 0 and _tests_passed(ev) > 0


def _backfill_test_outcomes(events: list[TraceEvent]) -> None:
    """Copy pytest counts from each tool_result onto the test_run that caused it.

    Adapters attach parsed counts to the tool_result event (where the output
    lives); the metrics reason about test_run events, so join them here. The
    result for a call is the first tool_result before the next tool-invoking
    event.
    """
    pending: TraceEvent | None = None
    for ev in events:
        if ev.type == "test_run":
            pending = ev
        elif ev.type in ("tool_call", "file_edit", "search", "shell"):
            pending = None
        elif ev.type == "tool_result" and pending is not None:
            if "tests_passed" in ev.derived and "tests_passed" not in pending.derived:
                for key in ("tests_passed", "tests_failed", "tests_errored"):
                    if key in ev.derived:
                        pending.derived[key] = ev.derived[key]
            pending = None


def _patch_stats(patch_text: str) -> tuple[int, set[str]]:
    """Changed LOC (+/- lines, headers excluded by unidiff) and touched files."""
    from unidiff import PatchSet

    loc = 0
    files: set[str] = set()
    try:
        patch = PatchSet(patch_text)
    except Exception:
        return 0, set()
    for pf in patch:
        files.add(pf.path)
        for hunk in pf:
            for line in hunk:
                if line.is_added or line.is_removed:
                    loc += 1
    return loc, files


def _recovery_rate(test_runs: list[TraceEvent]) -> float | None:
    """Of failing test_run episodes, the fraction eventually followed by a
    green test_run. None when nothing ever failed."""
    fails = [i for i, ev in enumerate(test_runs) if _tests_failed(ev) > 0]
    if not fails:
        return None
    recovered = sum(1 for i in fails if any(_is_green(e) for e in test_runs[i + 1 :]))
    return recovered / len(fails)


def _test_progress_rate(test_runs: list[TraceEvent]) -> float | None:
    """Fraction of consecutive test_run pairs where passed rose or failed fell."""
    if len(test_runs) < 2:
        return None
    improved = 0
    for a, b in zip(test_runs, test_runs[1:], strict=False):
        if _tests_passed(b) > _tests_passed(a) or _tests_failed(b) < _tests_failed(a):
            improved += 1
    return improved / (len(test_runs) - 1)


def _retry_verbatim_rate(events: list[TraceEvent]) -> float | None:
    """Of actions whose result failed (exit_code != 0), the fraction whose NEXT
    action is the identical command string — looping without adapting."""
    # (command, failed) per action, in order; an action's outcome is the first
    # tool_result that follows it.
    seq: list[tuple[str, bool]] = []
    pending_cmd: str | None = None
    for ev in events:
        if ev.type in ACTION_TYPES:
            pending_cmd = (ev.tool_args_digest or {}).get("command", "")
            seq.append((pending_cmd, False))
        elif ev.type == "tool_result" and seq and pending_cmd is not None:
            failed = ev.exit_code is not None and ev.exit_code != 0
            seq[-1] = (seq[-1][0], failed)
            pending_cmd = None
    failures = [i for i, (_, failed) in enumerate(seq) if failed and i + 1 < len(seq)]
    if not failures:
        return None
    verbatim = sum(1 for i in failures if seq[i][0] and seq[i + 1][0] == seq[i][0])
    return verbatim / len(failures)


def compute_profile(
    run: RunResult,
    events: list[TraceEvent],
    grade: GradeReport | None,
    task: Task | None,
    agent_patch_text: str | None = None,
    gold_patch_text: str | None = None,
) -> BehaviorProfile:
    events = sorted(events, key=lambda e: e.step_idx)
    _backfill_test_outcomes(events)
    n = len(events)

    p = BehaviorProfile(
        run_id=run.run_id,
        task_id=run.task_id,
        harness=run.harness,
        model=run.model,
        exit_reason=run.exit_reason,
        difficulty=task.difficulty if task else None,
        source=task.source if task else None,
    )
    if grade is not None:
        p.resolved = grade.resolved
        p.f2p_pass_rate = grade.f2p_pass_rate

    test_runs = [e for e in events if e.type == "test_run"]
    edits = [e for e in events if e.type == "file_edit"]
    actions = [e for e in events if e.type in ACTION_TYPES]
    assistant_turns = sum(1 for e in events if e.type == "assistant_msg")

    # --- verification & testing ---
    p.test_run_count = len(test_runs)
    p.green_observed = any(_is_green(e) for e in test_runs)
    if assistant_turns:
        p.test_run_rate = len(test_runs) / assistant_turns
    if edits:
        first_edit_idx = next(i for i, e in enumerate(events) if e.type == "file_edit")
        p.tested_before_first_edit = any(
            e.type == "test_run" for e in events[:first_edit_idx]
        )
        # edit->test cadence: test_runs preceded by >=1 edit since the last test_run
        loops = 0
        edits_since_test = 0
        for ev in events:
            if ev.type == "file_edit":
                edits_since_test += 1
            elif ev.type == "test_run":
                if edits_since_test > 0:
                    loops += 1
                edits_since_test = 0
        p.verification_loop_rate = loops / len(edits)
    # verified_before_done: the final test_run is green and nothing was edited
    # afterwards — the agent's last knowledge of the workspace is a passing suite.
    if test_runs and _is_green(test_runs[-1]):
        last_test_idx = max(i for i, ev in enumerate(events) if ev.type == "test_run")
        if not any(ev.type == "file_edit" for ev in events[last_test_idx + 1 :]):
            p.verified_before_done = True

    # --- persistence & recovery ---
    p.recovery_rate = _recovery_rate(test_runs)
    p.retry_verbatim_rate = _retry_verbatim_rate(events)
    p.test_progress_rate = _test_progress_rate(test_runs)
    if test_runs:
        p.gave_up_failing = _tests_failed(test_runs[-1]) > 0
    p.grind_to_cap = run.exit_reason in CAP_EXITS
    for ev in reversed(test_runs):
        if _tests_failed(ev) > 0:
            p.consecutive_failures_at_end += 1
        else:
            break

    # --- exploration & context use ---
    if n:
        first_edit = next((i for i, e in enumerate(events) if e.type == "file_edit"), n)
        p.exploration_fraction = first_edit / n
    if actions:
        p.exploration_event_share = sum(
            1 for e in actions if e.type == "search"
        ) / len(actions)
    # search_before_edit: of scored edits (first edit of a never-seen path is
    # file creation, excluded), the fraction whose file appeared in an earlier
    # search / read / tool_result.
    if edits:
        seen: set[str] = set()
        edited_before: set[str] = set()
        informed = 0
        scored = 0
        for ev in events:
            if ev.type == "file_edit" and ev.files_touched:
                is_creation = all(
                    f not in seen and f not in edited_before for f in ev.files_touched
                )
                if not is_creation:
                    scored += 1
                    if any(f in seen for f in ev.files_touched):
                        informed += 1
                edited_before.update(ev.files_touched)
            if ev.type in ("search", "tool_result") or ev.tool_name == "Read":
                seen.update(ev.files_touched)
        if scored:
            p.search_before_edit_rate = informed / scored
    explored: set[str] = set()
    for ev in events:
        if ev.type in ("search", "tool_result") or ev.tool_name == "Read":
            explored.update(ev.files_touched)
    p.files_explored = len(explored)
    reads = [
        ev
        for ev in events
        if (ev.type == "search" or ev.tool_name == "Read") and ev.files_touched
    ]
    if reads:
        seen_reads: set[str] = set()
        re_reads = 0
        for ev in reads:
            if any(f in seen_reads for f in ev.files_touched):
                re_reads += 1
            seen_reads.update(ev.files_touched)
        p.re_read_rate = re_reads / len(reads)

    # --- efficiency & scope ---
    p.num_turns = run.num_turns or assistant_turns
    p.total_tokens = run.total_tokens_in + run.total_tokens_out + run.total_thinking_tokens
    p.cost_usd = run.total_cost_usd
    p.file_edit_count = len(edits)
    turn = 0
    for ev in events:
        if ev.type == "assistant_msg":
            turn += 1
        elif ev.type == "test_run" and _is_green(ev):
            p.turns_to_first_green = turn
            break
    if gold_patch_text is not None:
        gold_loc, gold_files = _patch_stats(gold_patch_text)
        agent_loc, agent_files = _patch_stats(agent_patch_text or "")
        p.diff_size_ratio = agent_loc / gold_loc if gold_loc else None
        union = agent_files | gold_files
        if union:
            p.file_jaccard = len(agent_files & gold_files) / len(union)
        if agent_files:
            p.out_of_scope_ratio = len(agent_files - gold_files) / len(agent_files)
    edited_paths = [f for ev in edits for f in ev.files_touched]
    if edited_paths:
        p.redundancy_rate = 1.0 - len(set(edited_paths)) / len(edited_paths)

    # --- failure modes ---
    # Confabulated completion: voluntarily declared done, never saw a green
    # test, and did not actually pass. Interpretable because the task suite
    # contains known-solvable anchors (not an all-fail cohort).
    if grade is not None:
        p.confabulated_completion = (
            run.exit_reason == "completed"
            and not p.verified_before_done
            and grade.f2p_pass_rate < 0.2
        )
    if assistant_turns:
        # An assistant turn that yields no action before the next assistant
        # turn was nudged by the harness — protocol non-compliance.
        malformed = 0
        acted = True
        for ev in events:
            if ev.type == "assistant_msg":
                if not acted:
                    malformed += 1
                acted = False
            elif ev.type in ACTION_TYPES:
                acted = True
        if not acted:
            malformed += 1  # trailing assistant turn with no action
        p.malformed_action_rate = malformed / assistant_turns

    return p
