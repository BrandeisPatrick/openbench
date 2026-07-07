"""Comparison statistics honest at small n.

The unit of analysis is a run; runs group into tasks (reps within a task are
correlated), so the true degrees of freedom are ~#tasks, not #runs. Every
interval here is a task-clustered bootstrap: resample TASK ids with
replacement, pool that task's runs for both models, recompute the statistic.
Deterministic seeds throughout — same corpus, same numbers.
"""

from __future__ import annotations

import random
from statistics import median


def cliffs_delta(old: list[float], new: list[float]) -> float | None:
    """Cliff's delta: P(new > old) - P(new < old). Positive = new is higher.

    Rank-based (no normality assumption); on booleans (0/1) it reduces to the
    difference in rates. None when either side is empty.
    """
    if not old or not new:
        return None
    gt = lt = 0
    for x in new:
        for y in old:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    return (gt - lt) / (len(old) * len(new))


def per_task_deltas(
    old: dict[str, list[float]], new: dict[str, list[float]]
) -> dict[str, float]:
    """task -> median(new reps) - median(old reps), over tasks present in both."""
    return {
        t: median(new[t]) - median(old[t])
        for t in sorted(set(old) & set(new))
        if old[t] and new[t]
    }


def sign_agreement(deltas: dict[str, float]) -> str:
    """The most defensible small-n statement: how many tasks moved together.

    Reports the majority direction, e.g. "5/7 tasks ↑" (ties in value count
    as neither direction).
    """
    if not deltas:
        return "0/0 tasks"
    up = sum(1 for d in deltas.values() if d > 0)
    down = sum(1 for d in deltas.values() if d < 0)
    n = len(deltas)
    return f"{up}/{n} tasks ↑" if up >= down else f"{down}/{n} tasks ↓"


def task_bootstrap_ci(
    old: dict[str, list[float]],
    new: dict[str, list[float]],
    n_boot: int = 2000,
    seed: int = 0,
) -> tuple[float, float] | None:
    """95% CI of Cliff's delta under task-clustered resampling.

    Tasks (not runs) are the resampling unit; a draw takes each sampled task's
    full rep pool on both sides. None when fewer than 2 tasks overlap.
    """
    tasks = sorted(set(old) & set(new))
    tasks = [t for t in tasks if old[t] and new[t]]
    if len(tasks) < 2:
        return None
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(n_boot):
        draw = [tasks[rng.randrange(len(tasks))] for _ in tasks]
        o = [v for t in draw for v in old[t]]
        nw = [v for t in draw for v in new[t]]
        d = cliffs_delta(o, nw)
        if d is not None:
            deltas.append(d)
    if not deltas:
        return None
    deltas.sort()
    lo = deltas[int(0.025 * (len(deltas) - 1))]
    hi = deltas[int(0.975 * (len(deltas) - 1))]
    return (lo, hi)


def solve_rate_contrast(
    old: dict[str, list[bool]],
    new: dict[str, list[bool]],
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Solve-rate difference (new - old) with a task-clustered bootstrap CI."""
    o_flat = [v for vs in old.values() for v in vs]
    n_flat = [v for vs in new.values() for v in vs]
    out: dict = {
        "old_solved": sum(o_flat),
        "old_n": len(o_flat),
        "new_solved": sum(n_flat),
        "new_n": len(n_flat),
        "old_rate": sum(o_flat) / len(o_flat) if o_flat else None,
        "new_rate": sum(n_flat) / len(n_flat) if n_flat else None,
        "diff": None,
        "ci": None,
    }
    if not o_flat or not n_flat:
        return out
    out["diff"] = out["new_rate"] - out["old_rate"]
    tasks = sorted(set(old) & set(new))
    tasks = [t for t in tasks if old[t] and new[t]]
    if len(tasks) >= 2:
        rng = random.Random(seed)
        diffs: list[float] = []
        for _ in range(n_boot):
            draw = [tasks[rng.randrange(len(tasks))] for _ in tasks]
            o = [v for t in draw for v in old[t]]
            nw = [v for t in draw for v in new[t]]
            diffs.append(sum(nw) / len(nw) - sum(o) / len(o))
        diffs.sort()
        out["ci"] = (
            diffs[int(0.025 * (len(diffs) - 1))],
            diffs[int(0.975 * (len(diffs) - 1))],
        )
    return out
