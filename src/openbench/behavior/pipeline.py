"""Behavior pipeline: runs/ artifacts -> normalized events -> profiles.

Imports of the traces store are lazy and fault-tolerant: profiling still
produces profile.json files even if DuckDB is unavailable.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from openbench import paths
from openbench.behavior.profile import BehaviorProfile, compute_profile
from openbench.models import GradeReport, RunResult, Task, TraceEvent


def _read_text(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def _load_events(run: RunResult, rdir: Path) -> list[TraceEvent]:
    events_path = rdir / "events.jsonl"
    if events_path.exists():
        return [
            TraceEvent.model_validate_json(line)
            for line in events_path.read_text().splitlines()
            if line.strip()
        ]
    # Normalize from the raw transcript. All Harness protocols (mini-swe /
    # tooluse / gpt-responses / claude-native) write the same transcript schema
    # on purpose, so one adapter covers them; golden/null fixtures emit
    # claude_code-format transcripts.
    try:
        if run.harness in ("mini-swe", "tooluse", "gpt-responses", "claude-native", "native"):
            from openbench.traces.adapters.mini_swe import normalize
        else:
            from openbench.traces.adapters.claude_code import normalize

        raw_path = rdir / run.raw_transcript_path
        events = normalize(run, raw_path) if raw_path.exists() else []
    except Exception as exc:  # adapter missing/broken: degrade gracefully
        warnings.warn(f"{run.run_id}: could not normalize trace ({exc})", stacklevel=2)
        return []
    if events:
        try:
            from openbench.traces.store import write_events

            write_events(run.run_id, events)
        except Exception:
            events_path.write_text("".join(e.model_dump_json() + "\n" for e in events))
    return events


def load_profiles(run_id: str | None = None) -> list[BehaviorProfile]:
    """Read existing profile.json files (no recomputation)."""
    run_dirs = (
        [paths.run_dir(run_id)]
        if run_id is not None
        else sorted(d for d in paths.RUNS.iterdir() if (d / "profile.json").exists())
        if paths.RUNS.exists()
        else []
    )
    return [
        BehaviorProfile.model_validate_json((d / "profile.json").read_text())
        for d in run_dirs
        if (d / "profile.json").exists()
    ]


def profile_runs(run_id: str | None = None) -> list[BehaviorProfile]:
    """Compute and persist a BehaviorProfile for one run (or every run on disk)."""
    if run_id is not None:
        run_dirs = [paths.run_dir(run_id)]
    else:
        run_dirs = (
            sorted(d for d in paths.RUNS.iterdir() if (d / "run.json").exists())
            if paths.RUNS.exists()
            else []
        )

    results: list[BehaviorProfile] = []
    for rdir in run_dirs:
        run_json = rdir / "run.json"
        if not run_json.exists():
            raise FileNotFoundError(f"no run.json in {rdir}")
        run = RunResult.model_validate_json(run_json.read_text())

        events = _load_events(run, rdir)

        grade_text = _read_text(rdir / "grade.json")
        grade = GradeReport.model_validate_json(grade_text) if grade_text else None

        tdir = paths.task_dir(run.task_id)
        task_text = _read_text(tdir / "task.json")
        task = Task.model_validate_json(task_text) if task_text else None

        agent_patch_text = _read_text(rdir / run.workspace_patch_path)
        gold_patch_text = _read_text(tdir / task.gold_patch_path) if task else None

        p = compute_profile(
            run,
            events,
            grade,
            task,
            agent_patch_text=agent_patch_text,
            gold_patch_text=gold_patch_text,
        )
        (rdir / "profile.json").write_text(p.model_dump_json(indent=2))
        results.append(p)

        try:
            from openbench.traces.store import ensure_db, ingest_run

            ensure_db()
            ingest_run(run, events, grade)
        except Exception as exc:
            warnings.warn(f"{run.run_id}: duckdb ingest skipped ({exc})", stacklevel=2)
        try:
            from openbench.traces.store import ingest_profile

            ingest_profile(p)
        except Exception as exc:
            warnings.warn(f"{run.run_id}: profile ingest skipped ({exc})", stacklevel=2)

    return results
