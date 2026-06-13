"""Offline tests for the DuckDB trace store (no docker)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from openbench import paths
from openbench.models import GradeReport, RunMetrics, RunResult, TraceEvent
from openbench.traces import store

RUN_ID = "demo__repo-1--null--m--20260610-000000"


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "openbench.duckdb")
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")


def _run() -> RunResult:
    return RunResult(
        run_id=RUN_ID,
        task_id="demo__repo-1",
        harness="null",
        model="m",
        started_at=datetime(2026, 6, 10, tzinfo=UTC),
        finished_at=datetime(2026, 6, 10, 0, 1, tzinfo=UTC),
        exit_reason="completed",
        total_cost_usd=0.5,
        num_turns=2,
    )


def _events() -> list[TraceEvent]:
    common = {"run_id": RUN_ID, "task_id": "demo__repo-1", "harness": "null", "model": "m"}
    return [
        TraceEvent(event_id=f"{RUN_ID}-0", step_idx=0, type="run_start", **common),
        TraceEvent(
            event_id=f"{RUN_ID}-1",
            step_idx=1,
            type="test_run",
            tool_name="Bash",
            tool_args_digest={"command": "python -m pytest"},
            derived={"tests_passed": 3},
            **common,
        ),
    ]


def test_write_and_load_events_roundtrip() -> None:
    events = _events()
    out = store.write_events(RUN_ID, events)
    assert out == paths.run_dir(RUN_ID) / "events.jsonl"
    loaded = store.load_events(RUN_ID)
    assert loaded == events
    assert store.load_events("missing-run") == []


def test_ensure_db_creates_tables() -> None:
    conn = store.ensure_db()
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    finally:
        conn.close()
    assert {"tasks", "runs", "grades", "events", "metrics"} <= tables


def test_ingest_run_is_idempotent() -> None:
    run = _run()
    events = _events()
    grade = GradeReport(
        run_id=RUN_ID,
        task_id="demo__repo-1",
        applies_cleanly=True,
        builds=True,
        f2p_passed=["tests/test_foo.py::test_bar"],
        graded_at=datetime(2026, 6, 10, tzinfo=UTC),
    )
    metrics = RunMetrics(
        run_id=RUN_ID,
        task_id="demo__repo-1",
        harness="null",
        model="m",
        test_run_count=1,
        file_edit_count=2,
    )

    store.ingest_run(run, events, grade, metrics)
    store.ingest_run(run, events, grade, metrics)  # upsert: no duplicates

    conn = store.ensure_db()
    try:
        counts = {
            table: conn.execute(
                f"SELECT count(*) FROM {table} WHERE run_id = ?", [RUN_ID]
            ).fetchone()[0]
            for table in ("runs", "events", "grades", "metrics")
        }
        cost, turns = conn.execute(
            "SELECT total_cost_usd, num_turns FROM runs WHERE run_id = ?", [RUN_ID]
        ).fetchone()
        resolved = conn.execute(
            "SELECT resolved FROM grades WHERE run_id = ?", [RUN_ID]
        ).fetchone()[0]
    finally:
        conn.close()

    assert counts == {"runs": 1, "events": 2, "grades": 1, "metrics": 1}
    assert cost == pytest.approx(0.5)
    assert turns == 2
    assert resolved is True


def test_ingest_run_without_grade_or_metrics() -> None:
    store.ingest_run(_run(), [], None, None)
    conn = store.ensure_db()
    try:
        n_runs = conn.execute("SELECT count(*) FROM runs").fetchone()[0]
        n_grades = conn.execute("SELECT count(*) FROM grades").fetchone()[0]
    finally:
        conn.close()
    assert n_runs == 1
    assert n_grades == 0
