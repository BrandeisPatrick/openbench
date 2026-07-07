"""Regression guards for bugs found during live use.

Each test pins a fix for a bug that previously produced a *wrong result* (not a
crash) and was caught by manual audit rather than a test. If any of these fails,
a result-corrupting regression has slipped back in.
"""

from __future__ import annotations

from datetime import UTC, datetime

from openbench import paths
from openbench.models import HardnessTier

# --- #infra: provider slugs broke Docker container names ----------------------

def test_slugify_model_strips_slashes():
    from openbench.runners.execute import slugify_model

    assert slugify_model("openrouter/deepseek/deepseek-chat-v3-0324") == \
        "openrouter_deepseek_deepseek-chat-v3-0324"
    assert "/" not in slugify_model("a/b/c")
    assert slugify_model("deepseek-v4-pro") == "deepseek-v4-pro"  # already safe


# --- #8: the cost cap must bind on EVERY loop path, incl. fence-less replies ---

def test_cost_cap_fires_on_fenceless_turns(tmp_path, monkeypatch):
    """A model replying without a bash fence skips exec via `continue`; the cap
    check must still run (it once sat after exec only — a fence-less model
    burned 2.2x the cap on pure prompt tokens before the turn cap saved it)."""
    from openbench.models import RunLimits, Task
    from openbench.runners.harness import Harness
    from openbench.runners.protocols import TextFenceProtocol

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
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not exec")),
    )

    def chat(messages):  # fence-less reply, $1.00 provider-reported per call
        return {
            "choices": [{"message": {"content": "thinking out loud, no fence"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 9, "cost": 1.0},
        }

    runner = Harness(TextFenceProtocol(chat_fn=chat))
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "any-model", RunLimits(max_turns=50, max_cost_usd=2.5)
    )
    assert exit_reason == "cost_cap"
    assert usage["num_turns"] == 3  # 3 x $1.00 crosses $2.50; turn 4 never calls out


# --- #1: the harness must execute the FIRST action, not a hallucinated DONE ----

def test_first_fence_not_hallucinated_done():
    from openbench.runners.protocols import _extract_command

    # model hallucinates a whole trajectory ending in DONE; we take the first real act
    reply = "Let me look.\n```bash\nls src/\n```\n(fake output)\n```bash\necho OPENBENCH_DONE\n```"
    assert _extract_command(reply) == "ls src/"
