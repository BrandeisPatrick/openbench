"""The public facade re-exports verbs/models and normalizes id-or-object args."""

from __future__ import annotations

import openbench as ob
from openbench.models import RunResult, Task


def test_all_verbs_and_models_exported():
    for name in [
        "build_task", "build_env", "validate", "honeypot", "impossible",
        "run", "grade", "analyze", "report",
        "Task", "RunResult", "TraceEvent", "GradeReport", "RunMetrics",
    ]:
        assert hasattr(ob, name), f"openbench.{name} missing from public API"


def test_id_normalizers_accept_object_or_string():
    from openbench.api import _run_id, _task_id

    t = Task(
        task_id="o__r-1", repo="o/r", pr_number=1, base_commit="a"*40,
        merge_commit="b"*40, merged_at="2026-06-01T00:00:00Z",
        tier="main", hardness_score=1.0,
    )
    assert _task_id(t) == "o__r-1"
    assert _task_id("o__r-1") == "o__r-1"
    r = RunResult(
        run_id="o__r-1--mini-swe--m--t", task_id="o__r-1", harness="mini-swe",
        model="m", started_at="2026-06-11T00:00:00Z",
    )
    assert _run_id(r) == "o__r-1--mini-swe--m--t"
    assert _run_id("rid") == "rid"
