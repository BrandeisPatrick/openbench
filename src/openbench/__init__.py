"""openbench — long-horizon PR benchmark with RL reward-fingerprint analysis.

Two ways in:

- **Library:** the verbs and models are re-exported here, so an experiment is a
  handful of lines (see `openbench.api`)::

      import openbench as ob
      task = ob.build_task("sympy/sympy", 28109)
      run  = ob.run(task, model="deepseek-v4-pro")
      ob.grade(run); ob.analyze(run); ob.report()

- **CLI:** ``uv run openbench <verb>`` (see `openbench.cli`).
"""

from openbench.api import (
    analyze,
    build_env,
    build_task,
    grade,
    honeypot,
    impossible,
    report,
    run,
    validate,
)
from openbench.models import (
    GradeReport,
    HardnessTier,
    PRCandidate,
    RunLimits,
    RunMetrics,
    RunResult,
    Task,
    TraceEvent,
)

__all__ = [
    # verbs
    "build_task", "build_env", "validate", "honeypot", "impossible",
    "run", "grade", "analyze", "report",
    # core models (the unified data contracts)
    "Task", "RunResult", "TraceEvent", "GradeReport", "RunMetrics",
    "RunLimits", "PRCandidate", "HardnessTier",
]
