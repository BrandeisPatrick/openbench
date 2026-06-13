"""Offline end-to-end smoke: raw transcript -> analyze -> metrics -> report.

Exercises the cross-module integration (adapter, metrics, store, report)
without Docker or network — the Docker-dependent half is covered by the
golden/null runner fixtures against a real task.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openbench import paths
from openbench.models import GradeReport, HardnessTier, RunResult, Task

RUN_ID = "demo__repo-1--claude-code--claude-sonnet-4-6--20260610-000000"
TASK_ID = "demo__repo-1"

GOLD_PATCH = """\
diff --git a/src/foo.py b/src/foo.py
index 0000001..0000002 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,2 @@
 def foo():
-    return 1
+    return 2
"""

AGENT_PATCH = """\
diff --git a/src/foo.py b/src/foo.py
index 0000001..0000002 100644
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,3 @@
 def foo():
-    return 1
+    return 2
+# noqa
diff --git a/src/bar.py b/src/bar.py
new file mode 100644
--- /dev/null
+++ b/src/bar.py
@@ -0,0 +1 @@
+BAR = 1
"""


def _transcript() -> list[str]:
    raw = [
        {"type": "system", "subtype": "init", "session_id": "s", "model": "claude-sonnet-4-6"},
        {"type": "assistant", "message": {"role": "assistant", "usage": {"input_tokens": 100, "output_tokens": 20}, "content": [
            {"type": "thinking", "thinking": "Need to inspect foo first."},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "src/foo.py"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "def foo(): return 1"}]}},
        {"type": "assistant", "message": {"role": "assistant", "usage": {"input_tokens": 120, "output_tokens": 15}, "content": [
            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "python -m pytest -q"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "1 failed, 2 passed in 0.1s"}]}},
        {"type": "assistant", "message": {"role": "assistant", "usage": {"input_tokens": 150, "output_tokens": 40}, "content": [
            {"type": "tool_use", "id": "t3", "name": "Edit", "input": {"file_path": "src/foo.py", "old_string": "return 1", "new_string": "return 2"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t3", "content": "ok"}]}},
        {"type": "assistant", "message": {"role": "assistant", "usage": {"input_tokens": 180, "output_tokens": 25}, "content": [
            {"type": "tool_use", "id": "t4", "name": "Bash", "input": {"command": "python -m pytest -q"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t4", "is_error": False, "content": "3 passed in 0.1s"}]}},
        {"type": "result", "subtype": "success", "total_cost_usd": 0.10, "num_turns": 4, "result": "Done."},
    ]
    return [json.dumps(e) for e in raw]


@pytest.fixture()
def bench_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(paths, "DATASETS", tmp_path / "datasets")
    monkeypatch.setattr(paths, "TASKS", tmp_path / "datasets" / "tasks")
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "datasets" / "openbench.duckdb")

    tdir = paths.task_dir(TASK_ID)
    tdir.mkdir(parents=True)
    task = Task(
        task_id=TASK_ID, repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
        fail_to_pass=["tests/test_foo.py::test_foo"],
        pass_to_pass=["tests/test_foo.py::test_other"],
    )
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))
    (tdir / "gold.patch").write_text(GOLD_PATCH)
    (tdir / "test.patch").write_text("")
    (tdir / "prompt.md").write_text("Fix foo to return 2.")

    rdir = paths.run_dir(RUN_ID)
    rdir.mkdir(parents=True)
    run = RunResult(
        run_id=RUN_ID, task_id=TASK_ID, harness="claude-code", model="claude-sonnet-4-6",
        started_at=datetime(2026, 6, 10, tzinfo=UTC),
        finished_at=datetime(2026, 6, 10, 0, 30, tzinfo=UTC),
        exit_reason="completed", total_cost_usd=0.10,
        total_tokens_in=550, total_tokens_out=100, num_turns=4,
    )
    (rdir / "run.json").write_text(run.model_dump_json(indent=2))
    (rdir / "raw_transcript.jsonl").write_text("\n".join(_transcript()) + "\n")
    (rdir / "workspace.patch").write_text(AGENT_PATCH)
    grade = GradeReport(
        run_id=RUN_ID, task_id=TASK_ID, applies_cleanly=True, builds=True,
        f2p_passed=["tests/test_foo.py::test_foo"],
        p2p_passed=["tests/test_foo.py::test_other"],
        graded_at=datetime(2026, 6, 10, 1, tzinfo=UTC),
    )
    (rdir / "grade.json").write_text(grade.model_dump_json(indent=2))
    return tmp_path


def test_analyze_then_report(bench_root: Path) -> None:
    from openbench.analysis.pipeline import analyze_runs
    from openbench.report.generate import generate_report

    metrics = analyze_runs(run_id=RUN_ID)
    assert len(metrics) == 1
    m = metrics[0]
    assert m.test_run_count == 2
    assert m.file_edit_count == 1
    assert m.verification_loop_count >= 1
    assert not m.early_stop  # last test run was green
    assert m.verified_before_done  # green test, no edits after
    assert m.exploration_fraction > 0  # Read happened before the first edit
    assert m.diff_size_ratio is not None and m.diff_size_ratio > 1.0  # agent diff > gold
    assert m.out_of_scope_files == 1  # src/bar.py is not in the gold patch
    assert (paths.run_dir(RUN_ID) / "metrics.json").exists()
    assert (paths.run_dir(RUN_ID) / "events.jsonl").exists()

    report_path = generate_report(bench_root / "report.md")
    text = report_path.read_text()
    assert TASK_ID in text
    assert "claude-sonnet-4-6" in text
    assert "consistent with" in text.lower() or "propensities" in text.lower()
