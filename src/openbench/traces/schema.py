"""Trace-event vocabulary and classifiers shared by adapters and metrics."""

from __future__ import annotations

import re

from openbench.models import TraceEvent

__all__ = [
    "TraceEvent",
    "TEST_CMD_RE",
    "SEARCH_TOOLS",
    "READ_TOOLS",
    "EDIT_TOOLS",
    "classify_bash",
    "parse_pytest_counts",
]

# pytest / python -m pytest / tox invocations (any python3.x variant).
TEST_CMD_RE = re.compile(
    r"(?:^|[;&|\s])(?:pytest|py\.test|tox)\b"
    r"|python[0-9.]*\s+-m\s+(?:pytest|tox)\b"
)

SEARCH_TOOLS = {"Grep", "Glob", "WebSearch"}
READ_TOOLS = {"Read"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

_SEARCH_CMD_RE = re.compile(r"(?:^|[;&|]\s*)(?:grep|rg|find|ls)\b")


def classify_bash(command: str) -> str:
    """Classify a Bash command into "test_run" | "search" | "shell"."""
    if TEST_CMD_RE.search(command):
        return "test_run"
    if _SEARCH_CMD_RE.search(command.strip()):
        return "search"
    return "shell"


_PYTEST_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|errors?)\b")


def parse_pytest_counts(output: str) -> dict | None:
    """Extract pass/fail/error counts from a pytest summary line.

    Handles "3 passed, 1 failed, 2 errors in 0.12s" variants. Returns None
    when no pytest counts appear in the output. The last occurrence of each
    kind wins (re-runs print multiple summaries).
    """
    counts = {"tests_passed": 0, "tests_failed": 0, "tests_errored": 0}
    found = False
    for num, kind in _PYTEST_COUNT_RE.findall(output):
        found = True
        if kind == "passed":
            counts["tests_passed"] = int(num)
        elif kind == "failed":
            counts["tests_failed"] = int(num)
        else:  # error / errors
            counts["tests_errored"] = int(num)
    return counts if found else None
