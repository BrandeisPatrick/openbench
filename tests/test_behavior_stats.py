"""Unit tests for the comparison statistics and pair aggregation."""

from __future__ import annotations

from openbench.behavior.compare import GEN_PAIRS, compare_pair
from openbench.behavior.profile import BehaviorProfile
from openbench.behavior.stats import (
    cliffs_delta,
    per_task_deltas,
    sign_agreement,
    solve_rate_contrast,
    task_bootstrap_ci,
)


def test_cliffs_delta_hand_cases():
    assert cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    assert cliffs_delta([1, 1, 1], [2, 2, 2]) == 1.0  # new fully above old
    assert cliffs_delta([2, 2], [1, 1]) == -1.0
    assert cliffs_delta([0, 0, 1, 1], [1, 1, 1, 1]) == 0.5  # booleans -> rate diff
    assert cliffs_delta([], [1.0]) is None


def test_per_task_deltas_and_sign_agreement():
    old = {"t1": [1.0, 1.0], "t2": [2.0], "t3": [5.0]}
    new = {"t1": [2.0, 4.0], "t2": [3.0], "t4": [9.0]}  # t3/t4 don't overlap
    deltas = per_task_deltas(old, new)
    assert deltas == {"t1": 2.0, "t2": 1.0}
    assert sign_agreement(deltas) == "2/2 tasks ↑"
    assert sign_agreement({"a": -1.0, "b": -2.0, "c": 1.0}) == "2/3 tasks ↓"
    assert sign_agreement({}) == "0/0 tasks"


def test_bootstrap_is_deterministic_and_clustered():
    old = {f"t{i}": [float(i), float(i) + 0.5] for i in range(7)}
    new = {f"t{i}": [float(i) + 2, float(i) + 2.5] for i in range(7)}
    ci1 = task_bootstrap_ci(old, new, n_boot=200, seed=0)
    ci2 = task_bootstrap_ci(old, new, n_boot=200, seed=0)
    assert ci1 == ci2  # same seed, same corpus -> same numbers
    assert ci1 is not None and ci1[0] > 0  # a uniform +2 shift: CI above zero
    # fewer than 2 overlapping tasks -> not estimable
    assert task_bootstrap_ci({"t1": [1.0]}, {"t1": [2.0]}) is None


def test_solve_rate_contrast():
    old = {"t1": [False, False], "t2": [False], "t3": [False]}
    new = {"t1": [True, True], "t2": [False], "t3": [True]}
    s = solve_rate_contrast(old, new, n_boot=200, seed=0)
    assert (s["old_solved"], s["old_n"]) == (0, 4)
    assert (s["new_solved"], s["new_n"]) == (3, 4)
    assert s["diff"] == 0.75
    assert s["ci"] is not None


def _profile(model: str, task: str, *, resolved: bool, exit_reason: str = "completed",
             source: str = "swebench-verified", **metrics) -> BehaviorProfile:
    return BehaviorProfile(
        run_id=f"{task}--tooluse--{model}--{id(object())}", task_id=task,
        harness="tooluse", model=model, exit_reason=exit_reason,
        resolved=resolved, source=source, **metrics,
    )


def test_compare_pair_excludes_crashes_and_stratifies():
    pair = GEN_PAIRS["gpt"]
    profiles = [
        # old: never verifies, 1 crash (must not enter pools)
        _profile(pair.old_model, "t1", resolved=False, test_run_rate=0.1),
        _profile(pair.old_model, "t2", resolved=False, test_run_rate=0.0,
                 source="mined"),
        _profile(pair.old_model, "t2", resolved=False, exit_reason="crash",
                 test_run_rate=0.9),
        # new: verifies, solves the verified task
        _profile(pair.new_model, "t1", resolved=True, test_run_rate=0.8),
        _profile(pair.new_model, "t2", resolved=False, test_run_rate=0.7,
                 source="mined"),
    ]
    comp = compare_pair(profiles, "gpt")
    assert (comp.n_old, comp.n_new) == (2, 2)
    assert (comp.crashed_old, comp.crashed_new) == (1, 0)
    assert comp.solve["overall"]["new_solved"] == 1
    assert comp.solve["swebench-verified"]["new_solved"] == 1
    assert comp.solve["mined"]["new_solved"] == 0
    d = next(d for d in comp.deltas if d.metric == "test_run_rate")
    assert d.cliffs == 1.0  # crash's 0.9 excluded; new strictly above old
    assert d.sign_agreement == "2/2 tasks ↑"


def test_compare_pair_handles_missing_model():
    comp = compare_pair([], "deepseek")
    assert comp.n_old == comp.n_new == 0
    assert comp.solve["overall"]["old_rate"] is None
    assert all(d.cliffs is None for d in comp.deltas)
