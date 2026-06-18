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


def test_load_limits_default_override_and_fallback(tmp_path):
    from openbench.runners.matrix import load_limits

    cfg = tmp_path / "limits.yaml"
    cfg.write_text(
        "default:\n  max_turns: 100\n  max_cost_usd: 4.0\n"
        "models:\n  gpt-4.1:\n    max_turns: 80\n    max_cost_usd: 2.5\n"
    )
    fallback = RunLimits(max_turns=999, wall_clock_s=1234, max_cost_usd=99.0)
    resolve = load_limits(cfg, fallback)

    g = resolve("gpt-4.1")  # per-model override wins; default + fallback fill the rest
    assert (g.max_turns, g.max_cost_usd, g.wall_clock_s) == (80, 2.5, 1234)
    d = resolve("unlisted-model")  # default block over fallback
    assert (d.max_turns, d.max_cost_usd, d.wall_clock_s) == (100, 4.0, 1234)
    miss = load_limits(tmp_path / "nope.yaml", fallback)  # missing file -> pure fallback
    assert (miss("x").max_turns, miss("x").max_cost_usd) == (999, 99.0)


def test_per_cell_limits_override_shared(monkeypatch):
    from datetime import UTC, datetime

    seen: dict[str, RunLimits] = {}

    def fake_execute(task_id, runner, model, limits, cpus, memory):
        seen[model] = limits
        return RunResult(run_id=f"{task_id}-{model}", task_id=task_id, harness="native",
                         model=model, started_at=datetime.now(UTC), exit_reason="completed")

    monkeypatch.setattr("openbench.runners.matrix.execute_run", fake_execute)
    monkeypatch.setattr("openbench.runners.matrix.get_runner", lambda n: object())

    cheap = RunLimits(max_turns=150, max_cost_usd=1.0)
    shared = RunLimits(max_turns=80, max_cost_usd=4.0)
    cells = [MatrixCell("t", "deepseek", limits=cheap), MatrixCell("t", "gpt")]
    run_matrix(cells, shared, max_concurrency=2)

    assert seen["deepseek"] is cheap   # per-cell caps win
    assert seen["gpt"] is shared       # no per-cell limits -> shared fallback
