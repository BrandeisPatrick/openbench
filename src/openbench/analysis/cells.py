"""Cell = the unit of analysis: runs grouped by (model, harness).

Cross-model reward comparison is only valid within a fixed harness (same tools,
prompts, limits), so the fundamental group is the **(model, harness) cell**,
never the model alone. Pooling a model's runs across harnesses averages
behaviours produced under different protocols — e.g. a confabulated text-fence
session with a real native-tool session — into a fingerprint that describes
neither (the bug this module fixes).

Labelling: a model that ran under a single harness in the cohort keeps its plain
name, so single-harness cohorts are labelled exactly as before; a model that ran
under several harnesses is split into ``model · harness`` cells.

Pure/stdlib — callers pass anything exposing ``.model`` / ``.harness`` and the
metric fields (``RunMetrics`` in practice). No heavy deps; fully offline-testable.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

CellKey = tuple[str, str]  # (model, harness)

_LABEL_SEP = " · "
# A cell is treated as degenerate when at least this fraction of its runs are
# themselves degenerate (the typical run was a dreamed, no-op trajectory).
_DEGENERATE_CELL_FRACTION = 0.5


def cell_key(m) -> CellKey:
    """(model, harness) for one run's metrics."""
    return (m.model, m.harness)


def group_cells(all_metrics: Iterable) -> dict[CellKey, list]:
    """Group runs into (model, harness) cells, preserving first-seen order."""
    cells: dict[CellKey, list] = defaultdict(list)
    for m in all_metrics:
        cells[cell_key(m)].append(m)
    return dict(cells)


def cohort_labels(keys: Iterable[CellKey]) -> dict[CellKey, str]:
    """Display label per cell: plain ``model`` when that model used one harness in
    the cohort, else ``model · harness``. Keeps single-harness cohorts identical
    to the old model-keyed behaviour."""
    keys = list(keys)
    harnesses: dict[str, set[str]] = defaultdict(set)
    for model, harness in keys:
        harnesses[model].add(harness)
    return {
        (model, harness): (
            model if len(harnesses[model]) <= 1 else f"{model}{_LABEL_SEP}{harness}"
        )
        for (model, harness) in keys
    }


def is_degenerate(m) -> bool:
    """True for a 'dreamed' trajectory that never really acted: it ran no tests,
    edited no files, yet declared completion.

    This is the signature of a model pushed out of distribution by a foreign
    scaffold (e.g. a tool-use model forced through a text-fence harness): it
    hallucinates a whole session instead of taking real actions. Such runs are
    scaffold artifacts, not reward signal, and must be kept out of reward
    estimation."""
    no_tests = (getattr(m, "test_run_count", 0) or 0) == 0
    no_edits = (getattr(m, "file_edit_count", 0) or 0) == 0
    declared_done = bool(getattr(m, "confabulated_completion", False))
    return no_tests and no_edits and declared_done


def cell_is_degenerate(runs: list, fraction: float = _DEGENERATE_CELL_FRACTION) -> bool:
    """A cell is degenerate when at least ``fraction`` of its (non-empty) runs are
    degenerate — i.e. the typical trajectory was a dreamed no-op, so a reward read
    off this cell would describe the scaffold mismatch, not the policy."""
    if not runs:
        return False
    degenerate = sum(1 for m in runs if is_degenerate(m))
    return degenerate / len(runs) >= fraction
