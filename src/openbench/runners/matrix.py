"""Parallel (task × model) execution.

Agent runs are ~all latency: the host waits on the LLM API while the container
sits idle, so several runs overlap cleanly. The bottleneck is the VM's memory
(each container is capped), not CPU — so per-container resources are lowered for
parallel execution and concurrency is capped accordingly.

Each run is fully isolated (own container, own run_id), so a ThreadPoolExecutor
is enough; no shared state crosses runs. Failures are caught per-run so one bad
run never sinks the matrix.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from openbench.models import RunLimits, RunResult
from openbench.runners import get_runner, resolve_runner
from openbench.runners.execute import execute_run


@dataclass
class MatrixCell:
    task_id: str
    model: str
    runner: str = "native"
    result: RunResult | None = None
    error: str | None = None


def run_matrix(
    cells: list[MatrixCell],
    limits: RunLimits,
    max_concurrency: int = 3,
    cpus: int = 2,
    memory: str = "3g",
    on_done=None,
) -> list[MatrixCell]:
    """Run every (task, model) cell, up to max_concurrency at once.

    cpus/memory are per-container; defaults (2 cpu / 3g × 3) fit a 6-cpu / 10g
    VM. `on_done(cell)` is called as each finishes (for live progress).
    Returns the cells with `.result` or `.error` populated.
    """

    def _one(cell: MatrixCell) -> MatrixCell:
        try:
            cell.result = execute_run(
                task_id=cell.task_id,
                runner=get_runner(resolve_runner(cell.runner, cell.model)),
                model=cell.model,
                limits=limits,
                cpus=cpus,
                memory=memory,
            )
        except Exception as exc:
            cell.error = f"{type(exc).__name__}: {exc}"
        if on_done is not None:
            on_done(cell)
        return cell

    with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        futures = [pool.submit(_one, c) for c in cells]
        for _ in as_completed(futures):
            pass
    return cells
