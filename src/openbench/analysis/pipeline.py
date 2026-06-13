"""Analysis pipeline: normalize traces, compute metrics, ingest into DuckDB.

Imports of the traces package are lazy and fault-tolerant: analysis still
produces metrics.json files even if the store/adapters are unavailable.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

from openbench import paths
from openbench.analysis.metrics import compute_metrics
from openbench.models import GradeReport, RunMetrics, RunResult, Task, TraceEvent


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
    # Normalize from the raw transcript, picking the adapter by harness.
    # golden/null fixtures emit claude_code-format transcripts.
    try:
        # claude-native writes the mini-swe transcript schema on purpose, so the
        # same adapter normalizes it — only the model's behavior differs, not the
        # parsing (clean scaffold-vs-scaffold comparison).
        if run.harness in ("mini-swe", "claude-native"):
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
            # Fall back to writing the JSONL ourselves.
            events_path.write_text("".join(e.model_dump_json() + "\n" for e in events))
    return events


def analyze_runs(run_id: str | None = None) -> list[RunMetrics]:
    """Compute and persist RunMetrics for one run (or every run on disk)."""
    if run_id is not None:
        run_dirs = [paths.run_dir(run_id)]
    else:
        run_dirs = (
            sorted(d for d in paths.RUNS.iterdir() if (d / "run.json").exists())
            if paths.RUNS.exists()
            else []
        )

    results: list[RunMetrics] = []
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
        prompt_text = _read_text(tdir / task.prompt_path) if task else None

        m = compute_metrics(
            run,
            events,
            grade,
            task,
            agent_patch_text=agent_patch_text,
            gold_patch_text=gold_patch_text,
            prompt_text=prompt_text,
        )
        (rdir / "metrics.json").write_text(m.model_dump_json(indent=2))
        results.append(m)

        from openbench.analysis.reward_scoring import score_run

        rewards = score_run(run, events, grade, agent_patch_text, gold_patch_text)
        (rdir / "rewards.json").write_text(
            json.dumps({"run_id": run.run_id, "model": run.model, **rewards.as_dict()}, indent=2)
        )

        try:
            from openbench.traces.store import ensure_db, ingest_run

            ensure_db()
            ingest_run(run, events, grade, m)
        except Exception as exc:
            warnings.warn(f"{run.run_id}: duckdb ingest skipped ({exc})", stacklevel=2)

    return results
