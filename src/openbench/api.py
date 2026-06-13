"""The openbench programmatic API — a thin, Pythonic facade over the pipeline.

The whole benchmark composes in a few lines:

    import openbench as ob

    task   = ob.build_task("sympy/sympy", 28109)   # mine + construct one PR
    ob.build_env(task)                              # per-task Docker image
    ob.validate(task)                               # base-fails / merged-passes gate

    run    = ob.run(task, model="deepseek-v4-pro")  # drive an agent harness
    grade  = ob.grade(run)                           # mergeable? F2P / P2P / anti-cheat
    metric = ob.analyze(run)                         # behavioral + reward metrics

    ob.report("report.md")                           # cross-model fingerprints

Every verb accepts either the rich object (`Task`, `RunResult`) or its id
string, and returns the same typed models the rest of the codebase speaks.
The functions here only normalize arguments and delegate — all behavior lives
in the stage modules (mining/, tasks/, runners/, grading/, analysis/).
"""

from __future__ import annotations

from pathlib import Path

from openbench.models import (
    GradeReport,
    RunLimits,
    RunMetrics,
    RunResult,
    Task,
)
from openbench.runners.base import AgentRunner


def _task_id(task: Task | str) -> str:
    return task.task_id if isinstance(task, Task) else task


def _run_id(run: RunResult | str) -> str:
    return run.run_id if isinstance(run, RunResult) else run


# --- build a task ------------------------------------------------------------

def build_task(repo: str, pr: int) -> Task:
    """Mine one merged PR and construct a runnable task (prompt, gold/test, F2P)."""
    from openbench.tasks.construct import build_task as _f

    return _f(repo=repo, pr_number=pr)


def build_env(task: Task | str) -> str:
    """Build the per-task Docker image pinned at the base commit; returns its tag."""
    from openbench.envs.builder import build_task_image

    return build_task_image(_task_id(task))


def validate(task: Task | str, rounds: int = 3):
    """Run the base-fails / merged-passes gate; returns the TaskValidation."""
    from openbench.tasks.validate import validate_task

    return validate_task(_task_id(task), rounds=rounds)


# --- probes ------------------------------------------------------------------

def honeypot(task: Task | str) -> Task:
    """Derive a honeypot variant: weak visible tests, strict hidden grading."""
    from openbench.tasks.honeypot import build_honeypot

    return build_honeypot(_task_id(task))


def impossible(task: Task | str) -> Task:
    """Derive a contradictory-spec variant to probe sycophancy vs push-back."""
    from openbench.tasks.impossible import build_impossible

    return build_impossible(_task_id(task))


# --- run · grade · analyze ---------------------------------------------------

def run(
    task: Task | str,
    model: str,
    runner: str | AgentRunner = "mini-swe",
    *,
    max_turns: int = 150,
    wall_clock_s: int = 5400,
    max_cost_usd: float = 5.0,
) -> RunResult:
    """Drive an agent harness against a task; returns the RunResult.

    `runner` is a registry name ("mini-swe", "claude-code", "golden", "null")
    or an AgentRunner instance.
    """
    from openbench.runners import get_runner
    from openbench.runners.execute import execute_run

    agent = get_runner(runner) if isinstance(runner, str) else runner
    limits = RunLimits(
        max_turns=max_turns, wall_clock_s=wall_clock_s, max_cost_usd=max_cost_usd
    )
    return execute_run(task_id=_task_id(task), runner=agent, model=model, limits=limits)


def grade(run: RunResult | str) -> GradeReport:
    """Grade a run: apply patch, anti-cheat, build, F2P / P2P."""
    from openbench.grading.mergeability import grade_run

    return grade_run(_run_id(run))


def analyze(run: RunResult | str) -> RunMetrics:
    """Normalize the trace and compute behavioral + reward metrics for one run."""
    from openbench.analysis.pipeline import analyze_runs

    metrics = analyze_runs(run_id=_run_id(run))
    if not metrics:
        raise ValueError(f"no analyzable run found for {_run_id(run)}")
    return metrics[0]


def report(out: str | Path = "report.md") -> Path:
    """Generate the cross-model fingerprint report over every analyzed run."""
    from openbench.report.generate import generate_report

    return generate_report(Path(out))
