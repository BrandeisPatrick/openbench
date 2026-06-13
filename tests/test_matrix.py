"""The parallel matrix executor isolates cells and survives per-cell failure."""

from __future__ import annotations

import time

from openbench.models import RunLimits, RunResult
from openbench.runners.matrix import MatrixCell, run_matrix


def test_runs_concurrently_and_isolates_failures(monkeypatch):
    started: list[float] = []

    def fake_execute(task_id, runner, model, limits, cpus, memory):
        started.append(time.monotonic())
        if task_id == "boom":
            raise RuntimeError("kaboom")
        time.sleep(0.2)  # simulate a slow run
        from datetime import UTC, datetime
        return RunResult(run_id=f"{task_id}-{model}", task_id=task_id, harness="mini-swe",
                         model=model, started_at=datetime.now(UTC), exit_reason="completed")

    monkeypatch.setattr("openbench.runners.matrix.execute_run", fake_execute)
    monkeypatch.setattr("openbench.runners.matrix.get_runner", lambda n: object())

    cells = [MatrixCell("a", "m"), MatrixCell("b", "m"), MatrixCell("boom", "m"), MatrixCell("c", "m")]
    t0 = time.monotonic()
    out = run_matrix(cells, RunLimits(), max_concurrency=4)
    elapsed = time.monotonic() - t0

    # 3 good cells (0.2s each) run in parallel → well under sequential 0.6s
    assert elapsed < 0.5
    ok = [c for c in out if c.result]
    bad = [c for c in out if c.error]
    assert len(ok) == 3 and len(bad) == 1
    assert "kaboom" in bad[0].error  # failure isolated, didn't sink the matrix
