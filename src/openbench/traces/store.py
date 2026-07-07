"""Persistence: events.jsonl per run + the DuckDB warehouse."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from openbench import paths
from openbench.models import GradeReport, RunResult, TraceEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR PRIMARY KEY,
    repo VARCHAR,
    pr_number INTEGER,
    base_commit VARCHAR,
    merge_commit VARCHAR,
    merged_at TIMESTAMP,
    tier VARCHAR,
    hardness_score DOUBLE,
    fail_to_pass VARCHAR,        -- JSON list
    pass_to_pass VARCHAR,        -- JSON list
    image_tag VARCHAR,
    install_cmd VARCHAR,
    test_cmd VARCHAR
);
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    task_id VARCHAR,
    harness VARCHAR,
    model VARCHAR,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    exit_reason VARCHAR,
    raw_transcript_path VARCHAR,
    workspace_patch_path VARCHAR,
    total_cost_usd DOUBLE,
    total_tokens_in BIGINT,
    total_tokens_out BIGINT,
    total_thinking_tokens BIGINT,
    num_turns INTEGER
);
CREATE TABLE IF NOT EXISTS grades (
    run_id VARCHAR PRIMARY KEY,
    task_id VARCHAR,
    applies_cleanly BOOLEAN,
    builds BOOLEAN,
    f2p_passed VARCHAR,          -- JSON list
    f2p_failed VARCHAR,
    p2p_passed VARCHAR,
    p2p_failed VARCHAR,
    anticheat VARCHAR,           -- JSON object
    resolved BOOLEAN,
    graded_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    run_id VARCHAR,
    task_id VARCHAR,
    harness VARCHAR,
    model VARCHAR,
    step_idx INTEGER,
    ts TIMESTAMP,
    type VARCHAR,
    content VARCHAR,
    tool_name VARCHAR,
    tool_args_digest VARCHAR,    -- JSON object
    files_touched VARCHAR,       -- JSON list
    exit_code INTEGER,
    tokens_in BIGINT,
    tokens_out BIGINT,
    tokens_thinking BIGINT,
    cum_cost_usd DOUBLE,
    derived VARCHAR              -- JSON object
);
"""


def write_events(run_id: str, events: list[TraceEvent]) -> Path:
    run_path = paths.run_dir(run_id)
    run_path.mkdir(parents=True, exist_ok=True)
    out = run_path / "events.jsonl"
    out.write_text("".join(e.model_dump_json() + "\n" for e in events))
    return out


def load_events(run_id: str) -> list[TraceEvent]:
    path = paths.run_dir(run_id) / "events.jsonl"
    if not path.exists():
        return []
    return [
        TraceEvent.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def ensure_db() -> duckdb.DuckDBPyConnection:
    db_path = paths.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(_SCHEMA)
    return conn


def ingest_run(
    run: RunResult,
    events: list[TraceEvent],
    grade: GradeReport | None,
) -> None:
    """Upsert one run (delete-then-insert by run_id) into the warehouse."""
    conn = ensure_db()
    try:
        conn.execute("BEGIN")
        for table in ("runs", "grades", "events"):
            conn.execute(f"DELETE FROM {table} WHERE run_id = ?", [run.run_id])

        conn.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run.run_id, run.task_id, run.harness, run.model,
                run.started_at, run.finished_at, run.exit_reason,
                run.raw_transcript_path, run.workspace_patch_path,
                run.total_cost_usd, run.total_tokens_in, run.total_tokens_out,
                run.total_thinking_tokens, run.num_turns,
            ],
        )

        if events:
            conn.executemany(
                "INSERT INTO events VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        e.event_id, e.run_id, e.task_id, e.harness, e.model,
                        e.step_idx, e.ts, e.type, e.content, e.tool_name,
                        json.dumps(e.tool_args_digest), json.dumps(e.files_touched),
                        e.exit_code, e.tokens_in, e.tokens_out, e.tokens_thinking,
                        e.cum_cost_usd, json.dumps(e.derived),
                    ]
                    for e in events
                ],
            )

        if grade is not None:
            conn.execute(
                "INSERT INTO grades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    grade.run_id, grade.task_id, grade.applies_cleanly, grade.builds,
                    json.dumps(grade.f2p_passed), json.dumps(grade.f2p_failed),
                    json.dumps(grade.p2p_passed), json.dumps(grade.p2p_failed),
                    grade.anticheat.model_dump_json(), grade.resolved, grade.graded_at,
                ],
            )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
