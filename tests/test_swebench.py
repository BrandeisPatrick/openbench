"""Offline tests for SWE-bench Verified stratified selection (no network).

`stratify` is pure (operates on in-memory row dicts), so these never touch the
parquet — duckdb is only imported inside `list_instances`.
"""

from __future__ import annotations

from openbench.mining.swebench import stratify


def _rows() -> list[dict]:
    # repo A: 3 easy + 1 hard ; repo B: 2 easy
    rows = [{"instance_id": f"a-{i}", "repo": "A", "difficulty": "<15 min fix"} for i in range(3)]
    rows.append({"instance_id": "a-hard", "repo": "A", "difficulty": ">4 hours"})
    rows += [{"instance_id": f"b-{i}", "repo": "B", "difficulty": "<15 min fix"} for i in range(2)]
    return rows


def test_stratify_even_per_cell():
    selected, coverage = stratify(_rows(), per_cell=2)
    counts = {(c["repo"], c["difficulty"]): c["selected"] for c in coverage}
    assert counts[("A", "<15 min fix")] == 2  # 3 available, capped at 2
    assert counts[("A", ">4 hours")] == 1     # only 1 available -> under-fills
    assert counts[("B", "<15 min fix")] == 2
    assert len(selected) == 5


def test_stratify_reports_shortfall():
    _, coverage = stratify(_rows(), per_cell=2)
    hard = next(c for c in coverage if c["difficulty"] == ">4 hours")
    assert (hard["requested"], hard["available"], hard["selected"]) == (2, 1, 1)


def test_stratify_deterministic_and_size_blind():
    rows = _rows()
    a = stratify(rows, per_cell=2)[0]
    b = stratify(list(reversed(rows)), per_cell=2)[0]
    # same instances chosen regardless of input order (sorted by instance_id)
    assert [r["instance_id"] for r in a] == [r["instance_id"] for r in b]
    chosen = sorted(
        r["instance_id"] for r in a if r["repo"] == "A" and r["difficulty"] == "<15 min fix"
    )
    assert chosen == ["a-0", "a-1"]  # first two by id, never by patch size


def test_stratify_repo_filter():
    selected, coverage = stratify(_rows(), per_cell=5, repos=["B"])
    assert {r["repo"] for r in selected} == {"B"}
    assert all(c["repo"] == "B" for c in coverage)


def test_stratify_missing_difficulty_bucketed_as_unknown():
    selected, coverage = stratify([{"instance_id": "x-1", "repo": "X"}], per_cell=1)
    assert len(selected) == 1
    assert coverage[0]["difficulty"] == "unknown"
