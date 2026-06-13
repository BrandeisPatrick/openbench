"""Runner protocol implemented by every agent harness adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from openbench.models import ExitReason, RunLimits, Task


@runtime_checkable
class AgentRunner(Protocol):
    """An agent harness that can be executed inside a started task container."""

    name: str
    needs_network: bool

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        """Execute inside the started container; write raw_transcript.jsonl into run_path; return (exit_reason, usage_totals)."""
        ...


def zero_usage() -> dict:
    """Canonical usage_totals dict with all counters at zero."""
    return {
        "cost_usd": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_thinking": 0,
        "num_turns": 0,
    }
