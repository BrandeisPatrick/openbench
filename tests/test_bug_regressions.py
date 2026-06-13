"""Regression guards for bugs found during live use.

Each test pins a fix for a bug that previously produced a *wrong result* (not a
crash) and was caught by manual audit rather than a test. If any of these fails,
a result-corrupting regression has slipped back in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from openbench import paths
from openbench.models import GradeReport, HardnessTier, RunMetrics

# --- #infra: provider slugs broke Docker container names ----------------------

def test_slugify_model_strips_slashes():
    from openbench.runners.execute import slugify_model

    assert slugify_model("openrouter/deepseek/deepseek-chat-v3-0324") == \
        "openrouter_deepseek_deepseek-chat-v3-0324"
    assert "/" not in slugify_model("a/b/c")
    assert slugify_model("deepseek-v4-pro") == "deepseek-v4-pro"  # already safe


# --- #5: partial identifiability — never rank a weight whose CI includes 0 ----

def test_noise_floor_gate_ci_includes_zero():
    from openbench.analysis.stats import ci_includes_zero

    assert ci_includes_zero((0.0, 0.44)) is True      # the V3 context_mgmt bug
    assert ci_includes_zero((0.0, 0.0)) is True
    assert ci_includes_zero((0.14, 0.99)) is False     # a genuinely estimable weight


def test_mixture_estimate_estimable_uses_ci():
    from openbench.analysis.estimate import MixtureEstimate

    e = MixtureEstimate(
        model="m", weights={"process_verifier": 0.5, "context_mgmt": 0.06},
        weight_cis={"process_verifier": (0.2, 0.8), "context_mgmt": (0.0, 0.44)},
    )
    assert e.estimable("process_verifier") is True
    assert e.estimable("context_mgmt") is False        # CI∋0 → not rankable
    assert e.estimable("missing") is False


# --- #6 + presentation: report must flag failure + composition caveats --------

def _write_run(rdir: Path, model: str, f2p_rate: float) -> None:
    rdir.mkdir(parents=True)
    m = RunMetrics(run_id=rdir.name, task_id="t", harness="mini-swe", model=model,
                   tier=HardnessTier.MAIN)
    (rdir / "metrics.json").write_text(m.model_dump_json())
    passed = ["t::a"] if f2p_rate > 0 else []
    failed = [] if f2p_rate > 0 else ["t::a"]
    g = GradeReport(run_id=rdir.name, task_id="t", applies_cleanly=True, builds=True,
                    f2p_passed=passed, f2p_failed=failed, graded_at=datetime(2026, 6, 11, tzinfo=UTC))
    (rdir / "grade.json").write_text(g.model_dump_json())


def test_failed_trajectory_banner_and_composition_caveat(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    # two real models, both 0% solve (the fixtures model "none" is excluded)
    _write_run(paths.RUNS / "t--mini-swe--A--x", "A", 0.0)
    _write_run(paths.RUNS / "t--mini-swe--B--x", "B", 0.0)
    from openbench.report.generate import generate_report

    text = generate_report(tmp_path / "r.md").read_text()
    assert "All trajectories failed" in text                      # #6 banner
    assert "not interpretable" in text                            # probe guard
    assert "down a model" in text or "composition" in text        # comp-vs-magnitude


def test_banner_absent_when_something_solves(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    _write_run(paths.RUNS / "t--mini-swe--A--x", "A", 1.0)  # A solved it
    _write_run(paths.RUNS / "t--mini-swe--B--x", "B", 0.0)
    from openbench.report.generate import generate_report

    text = generate_report(tmp_path / "r.md").read_text()
    assert "All trajectories failed" not in text


# --- #7: crashed runs are infrastructure failures, never behavioral data ------

def test_crashed_runs_excluded_from_pools(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(paths, "RUNS", tmp_path / "runs")
    _write_run(paths.RUNS / "t--mini-swe--A--ok", "A", 0.0)
    crashed = paths.RUNS / "t--mini-swe--A--bad"
    _write_run(crashed, "A", 0.0)
    run_json = {
        "run_id": crashed.name, "task_id": "t", "harness": "mini-swe", "model": "A",
        "started_at": "2026-06-11T00:00:00Z", "exit_reason": "crash",
    }
    (crashed / "run.json").write_text(json.dumps(run_json))
    from openbench.report.generate import _load_runs

    rows = _load_runs()
    assert len(rows) == 1  # the 2-turn provider-402 crash never enters the pool
    assert rows[0][0].run_id == "t--mini-swe--A--ok"


# --- #8: the cost cap must bind on EVERY loop path, incl. fence-less replies ---

def test_cost_cap_fires_on_fenceless_turns(tmp_path, monkeypatch):
    """A model replying without a bash fence skips exec via `continue`; the cap
    check must still run (it once sat after exec only — a fence-less model
    burned 2.2x the cap on pure prompt tokens before the turn cap saved it)."""
    from openbench.models import RunLimits, Task
    from openbench.runners.mini_swe import MiniSweRunner

    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    tdir = paths.task_dir("demo__repo-1")
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("Implement the feature.")
    task = Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
    )
    monkeypatch.setattr(
        "openbench.runners.mini_swe.dockerutil.exec_in",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not exec")),
    )

    def chat(messages):  # fence-less reply, $1.00 provider-reported per call
        return {
            "choices": [{"message": {"content": "thinking out loud, no fence"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 9, "cost": 1.0},
        }

    runner = MiniSweRunner(chat_fn=chat)
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "any-model", RunLimits(max_turns=50, max_cost_usd=2.5)
    )
    assert exit_reason == "cost_cap"
    assert usage["num_turns"] == 3  # 3 x $1.00 crosses $2.50; turn 4 never calls out


# --- #1: the harness must execute the FIRST action, not a hallucinated DONE ----

def test_first_fence_not_hallucinated_done():
    from openbench.runners.mini_swe import _extract_command

    # model hallucinates a whole trajectory ending in DONE; we take the first real act
    reply = "Let me look.\n```bash\nls src/\n```\n(fake output)\n```bash\necho OPENBENCH_DONE\n```"
    assert _extract_command(reply) == "ls src/"
