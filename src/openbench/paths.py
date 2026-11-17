"""Canonical filesystem layout for datasets and runs."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("OPENBENCH_ROOT", Path(__file__).resolve().parents[2]))
DATASETS = ROOT / "datasets"
CANDIDATES = DATASETS / "candidates"
TASKS = DATASETS / "tasks"
RUNS = ROOT / "runs"
CONFIGS = ROOT / "configs"
GH_CACHE = DATASETS / "candidates" / ".gh_cache"


def task_dir(task_id: str) -> Path:
    return TASKS / task_id


def run_dir(run_id: str) -> Path:
    return RUNS / run_id
