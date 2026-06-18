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
from pathlib import Path
from typing import Callable

import yaml

from openbench.models import RunLimits, RunResult
from openbench.runners import get_runner
from openbench.runners.execute import execute_run


@dataclass
class MatrixCell:
    task_id: str
    model: str
    runner: str = "native"  # common harness: native tool-use (per-provider dispatch)
    limits: RunLimits | None = None  # per-cell caps; falls back to run_matrix's `limits`
    result: RunResult | None = None
    error: str | None = None


def load_limits(path: Path | None, fallback: RunLimits) -> Callable[[str], RunLimits]:
    """Build a model -> RunLimits resolver from a per-model YAML config.

    The config has an optional ``default:`` block (overrides ``fallback`` for every
    model) and a ``models:`` map of exact-model-id -> partial overrides. Each field
    inherits down the chain model > default > fallback, so every model gets its own
    turn / cost / wall cap — the lever for cost control (a $-pricey model can be
    capped tighter than a cheap one). A missing/empty file means every model uses
    ``fallback``.
    """
    cfg: dict = {}
    if path is not None and path.exists():
        cfg = yaml.safe_load(path.read_text()) or {}
    base = {**fallback.model_dump(), **(cfg.get("default") or {})}
    overrides = cfg.get("models") or {}

    def resolve(model: str) -> RunLimits:
        return RunLimits(**{**base, **(overrides.get(model) or {})})

    return resolve


def run_matrix(
    cells: list[MatrixCell],
    limits: RunLimits,
    max_concurrency: int = 3,
    cpus: int = 2,
    memory: str = "3g",
    on_done=None,
) -> list[MatrixCell]:
    """Run every (task, model) cell, up to max_concurrency at once.

    `limits` is the shared fallback; a cell with its own `cell.limits` (e.g. from
    `load_limits`) overrides it, so caps can be set per model. cpus/memory are
    per-container; defaults (2 cpu / 3g × 3) fit a 6-cpu / 10g VM. `on_done(cell)`
    is called as each finishes (for live progress). Returns the cells with
    `.result` or `.error` populated.
    """

    def _one(cell: MatrixCell) -> MatrixCell:
        try:
            cell.result = execute_run(
                task_id=cell.task_id,
                runner=get_runner(cell.runner),
                model=cell.model,
                limits=cell.limits or limits,  # per-cell caps win; else the shared default
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
