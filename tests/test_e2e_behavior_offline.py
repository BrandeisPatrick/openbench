"""Offline end-to-end: harness transcripts -> profiles -> compare -> report.

Builds a miniature generational corpus (2 models x 2 tasks x 2 reps) in the
shared Harness transcript format (meta / api_response / exec / final — what
every wire protocol writes), with deliberately different behavior: the new
model verifies-and-solves briskly, the old model edits blind and grinds red
to the turn cap. Exercises adapter, profile, stats, compare, figures, and
report together — no Docker or network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openbench import paths
from openbench.behavior.compare import GEN_PAIRS
from openbench.models import GradeReport, HardnessTier, RunResult, Task

PAIR = GEN_PAIRS["gpt"]
TASKS = {
    "demo__easy-1": ("swebench-verified", "<15 min fix"),
    "demo__hard-2": ("mined", "1-4 hours"),
}

GOLD_PATCH = """\
diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@ -1,2 +1,2 @@
 def foo():
-    return 1
+    return 2
"""


def _rec(**kw) -> str:
    return json.dumps(kw)


def _new_model_transcript(model: str) -> str:
    """Search -> reproduce -> edit -> verify green -> done."""
    lines = [
        _rec(type="meta", model=model),
        _rec(type="api_response", content="explore first",
             usage={"prompt_tokens": 100, "completion_tokens": 10}),
        _rec(type="exec", command="grep -n foo src/foo.py", output="1:def foo",
             exit_code=0),
        _rec(type="api_response", content="reproduce",
             usage={"prompt_tokens": 120, "completion_tokens": 10}),
        _rec(type="exec", command="python -m pytest -q", output="1 failed, 2 passed in 0.1s",
             exit_code=1),
        _rec(type="api_response", content="fix foo",
             usage={"prompt_tokens": 150, "completion_tokens": 20}),
        _rec(type="exec", command="cat > src/foo.py <<'EOF'\ndef foo():\n    return 2\nEOF",
             output="", exit_code=0),
        _rec(type="api_response", content="verify",
             usage={"prompt_tokens": 180, "completion_tokens": 10}),
        _rec(type="exec", command="python -m pytest -q", output="3 passed in 0.1s",
             exit_code=0),
        _rec(type="api_response", content="done",
             usage={"prompt_tokens": 200, "completion_tokens": 5}),
        _rec(type="exec", command="echo OPENBENCH_DONE", output="OPENBENCH_DONE", exit_code=0),
        _rec(type="final", exit_reason="completed", usage_totals={"cost_usd": 0.4}),
    ]
    return "\n".join(lines) + "\n"


def _old_model_transcript(model: str) -> str:
    """Edit blind -> red tests -> identical retry -> turn cap."""
    lines = [
        _rec(type="meta", model=model),
        _rec(type="api_response", content="I know the fix",
             usage={"prompt_tokens": 100, "completion_tokens": 30}),
        _rec(type="exec", command="cat > src/foo.py <<'EOF'\ndef foo():\n    return 3\nEOF",
             output="", exit_code=0),
        _rec(type="api_response", content="run tests",
             usage={"prompt_tokens": 130, "completion_tokens": 10}),
        _rec(type="exec", command="python -m pytest -q", output="2 failed in 0.3s",
             exit_code=1),
        _rec(type="api_response", content="try again",
             usage={"prompt_tokens": 160, "completion_tokens": 10}),
        _rec(type="exec", command="python -m pytest -q", output="2 failed in 0.3s",
             exit_code=1),
        _rec(type="final", exit_reason="turn_cap", usage_totals={"cost_usd": 2.0}),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture()
def bench_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(paths, "DATASETS", tmp_path / "datasets")
    monkeypatch.setattr(paths, "TASKS", tmp_path / "datasets" / "tasks")
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "datasets" / "openbench.duckdb")

    for task_id, (source, difficulty) in TASKS.items():
        tdir = paths.task_dir(task_id)
        tdir.mkdir(parents=True)
        task = Task(
            task_id=task_id, repo="demo/repo", pr_number=1,
            base_commit="a" * 40, merge_commit="b" * 40,
            merged_at=datetime(2026, 6, 1, tzinfo=UTC),
            tier=HardnessTier.MAIN, hardness_score=1.0,
            difficulty=difficulty, source=source,
            fail_to_pass=["tests/test_foo.py::test_foo"],
        )
        (tdir / "task.json").write_text(task.model_dump_json(indent=2))
        (tdir / "gold.patch").write_text(GOLD_PATCH)
        (tdir / "prompt.md").write_text("Fix foo to return 2.")

    for model, transcript_fn, exit_reason, cost in (
        (PAIR.old_model, _old_model_transcript, "turn_cap", 2.0),
        (PAIR.new_model, _new_model_transcript, "completed", 0.4),
    ):
        for task_id in TASKS:
            for rep in (1, 2):
                run_id = f"{task_id}--gpt-responses--{model}--rep{rep}"
                rdir = paths.run_dir(run_id)
                rdir.mkdir(parents=True)
                run = RunResult(
                    run_id=run_id, task_id=task_id, harness="gpt-responses",
                    model=model, started_at=datetime(2026, 7, 6, tzinfo=UTC),
                    finished_at=datetime(2026, 7, 6, 0, 30, tzinfo=UTC),
                    exit_reason=exit_reason, total_cost_usd=cost,
                    total_tokens_in=500, total_tokens_out=100,
                    num_turns=5 if exit_reason == "completed" else 3,
                )
                (rdir / "run.json").write_text(run.model_dump_json(indent=2))
                (rdir / "raw_transcript.jsonl").write_text(transcript_fn(model))
                (rdir / "workspace.patch").write_text(GOLD_PATCH)
                # New model solves the easy task only; old model solves nothing.
                solved = model == PAIR.new_model and task_id == "demo__easy-1"
                grade = GradeReport(
                    run_id=run_id, task_id=task_id, applies_cleanly=True, builds=True,
                    f2p_passed=["tests/test_foo.py::test_foo"] if solved else [],
                    f2p_failed=[] if solved else ["tests/test_foo.py::test_foo"],
                    graded_at=datetime(2026, 7, 6, 1, tzinfo=UTC),
                )
                (rdir / "grade.json").write_text(grade.model_dump_json(indent=2))
    return tmp_path


def test_profiles_then_compare_then_report(bench_root: Path) -> None:
    from openbench.behavior import compare_pair, generate_comparison_report, profile_runs

    profiles = profile_runs()
    assert len(profiles) == 8
    by_model = {m: [p for p in profiles if p.model == m]
                for m in (PAIR.old_model, PAIR.new_model)}

    for p in by_model[PAIR.new_model]:
        assert p.verified_before_done is True
        assert p.tested_before_first_edit is True
        assert p.green_observed is True
        assert p.grind_to_cap is False
        assert p.search_before_edit_rate == 1.0
        assert p.turns_to_first_green == 4
    for p in by_model[PAIR.old_model]:
        assert p.verified_before_done is False
        assert p.tested_before_first_edit is False
        assert p.grind_to_cap is True
        assert p.gave_up_failing is True
        assert p.retry_verbatim_rate == 1.0  # the one mid-run failure retried verbatim
        assert p.recovery_rate == 0.0
    # task metadata flowed through
    assert {p.source for p in profiles} == {"swebench-verified", "mined"}
    # events.jsonl was materialized by the adapter path
    assert all((d / "events.jsonl").exists() for d in paths.RUNS.iterdir())

    comp = compare_pair(profiles, "gpt")
    assert (comp.n_old, comp.n_new) == (4, 4)
    assert comp.solve["overall"]["old_solved"] == 0
    assert comp.solve["overall"]["new_solved"] == 2
    assert comp.solve["swebench-verified"]["new_solved"] == 2
    assert comp.solve["mined"]["new_solved"] == 0
    verified = next(d for d in comp.deltas if d.metric == "verified_before_done")
    assert verified.cliffs == 1.0 and verified.sign_agreement == "2/2 tasks ↑"
    grind = next(d for d in comp.deltas if d.metric == "grind_to_cap")
    assert grind.cliffs == -1.0
    cost = next(d for d in comp.deltas if d.metric == "cost_usd")
    assert cost.cliffs == -1.0  # new generation is cheaper on this corpus

    report_path = generate_comparison_report(["gpt"], bench_root / "runs" / "behavior_report.md")
    text = report_path.read_text()
    assert PAIR.new_model in text and PAIR.old_model in text
    assert "verified_before_done" in text
    assert "Solve rate" in text and "swebench-verified" in text
    fig_dir = report_path.parent / "figures"
    assert (fig_dir / "paired_deltas.png").exists()
    assert (fig_dir / "outcome_composition.png").exists()
    assert (fig_dir / "pass_trajectories.png").exists()
    assert (fig_dir / "efficiency_frontier.png").exists()
