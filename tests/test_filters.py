"""Offline tests for mining filters; PRCandidate objects are constructed directly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openbench.mining.filters import passes_filters
from openbench.models import PRCandidate

CFG = {
    "filters": {
        "min_loc_changed": 600,
        "max_loc_changed": 8000,
        "min_changed_files": 10,
        "min_commits": 5,
        "min_top_level_dirs": 3,
        "min_test_files": 2,
        "min_test_functions": 5,
        "min_review_comments": 10,
        "min_body_chars": 500,
    }
}


def make_candidate(**overrides) -> PRCandidate:
    base = dict(
        repo="org/name",
        pr_number=1,
        title="Refactor the frobnicator",
        body="x" * 600,
        linked_issues=[],
        base_commit="a" * 40,
        merge_commit="b" * 40,
        merged_at=datetime(2025, 7, 1, tzinfo=UTC),
        additions=500,
        deletions=300,
        changed_files=12,
        commits=6,
        review_comments=12,
        top_level_dirs=["docs", "src", "tests"],
        test_files_changed=["tests/test_a.py", "tests/test_b.py"],
        test_functions_changed=6,
    )
    base.update(overrides)
    return PRCandidate(**base)


def test_passing_candidate():
    ok, reasons = passes_filters(make_candidate(), CFG)
    assert ok
    assert reasons == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"additions": 100, "deletions": 100}, "min_loc_changed"),
        ({"additions": 9000, "deletions": 0}, "max_loc_changed"),
        ({"changed_files": 5}, "min_changed_files"),
        ({"commits": 2}, "min_commits"),
        ({"top_level_dirs": ["src"]}, "min_top_level_dirs"),
        ({"test_files_changed": ["tests/test_a.py"]}, "min_test_files"),
        ({"test_functions_changed": 2}, "min_test_functions"),
        ({"review_comments": 3}, "min_review_comments"),
        ({"body": "short"}, "min_body_chars"),
    ],
)
def test_each_threshold_fails(overrides: dict, reason: str):
    ok, reasons = passes_filters(make_candidate(**overrides), CFG)
    assert not ok
    assert reasons == [reason]


def test_linked_issue_rescues_short_body():
    c = make_candidate(body="", linked_issues=[{"number": 7, "title": "bug", "body": "..."}])
    ok, reasons = passes_filters(c, CFG)
    assert ok
    assert reasons == []


def test_lockfile_dominated_excluded():
    files = ["poetry.lock", "package-lock.json", "web/app.min.js", "proto/x_pb2.py", "src/core.py"]
    ok, reasons = passes_filters(make_candidate(), CFG, files=files)
    assert not ok
    assert "lockfile_dominated" in reasons


def test_lockfile_minority_passes():
    files = ["poetry.lock", "src/a.py", "src/b.py", "tests/test_a.py"]
    ok, reasons = passes_filters(make_candidate(), CFG, files=files)
    assert ok
    assert reasons == []


def test_docs_only_excluded():
    files = ["README.md", "docs/guide.rst", "docs/index.md"]
    ok, reasons = passes_filters(make_candidate(), CFG, files=files)
    assert not ok
    assert "docs_only" in reasons


def test_max_test_loc_fraction():
    cfg = {"filters": {**CFG["filters"], "max_test_loc_fraction": 0.5}}
    ok, reasons = passes_filters(make_candidate(), cfg, test_loc_fraction=0.96)
    assert not ok and reasons == ["max_test_loc_fraction"]
    ok, _ = passes_filters(make_candidate(), cfg, test_loc_fraction=0.3)
    assert ok
    # Unknown fraction (None) never rejects.
    ok, _ = passes_filters(make_candidate(), cfg, test_loc_fraction=None)
    assert ok
    # Config without the key never rejects either.
    ok, _ = passes_filters(make_candidate(), CFG, test_loc_fraction=0.96)
    assert ok
