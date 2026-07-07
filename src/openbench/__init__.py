"""openbench — long-horizon PR benchmark for agentic coding models.

Two ways in:

- **Library:** the verbs and models are re-exported here, so a study is a
  handful of lines (see `openbench.api`)::

      import openbench as ob
      task = ob.build_task("sympy/sympy", 28109)
      run  = ob.run(task, model="deepseek-v4-pro")
      ob.grade(run)

- **CLI:** ``uv run openbench <verb>`` (see `openbench.cli`).
"""

from openbench.api import (
    build_env,
    build_task,
    grade,
    run,
    validate,
)
from openbench.models import (
    GradeReport,
    HardnessTier,
    PRCandidate,
    RunLimits,
    RunResult,
    Task,
    TraceEvent,
)

__all__ = [
    # verbs
    "build_task", "build_env", "validate",
    "run", "grade",
    # core models (the unified data contracts)
    "Task", "RunResult", "TraceEvent", "GradeReport",
    "RunLimits", "PRCandidate", "HardnessTier",
]
