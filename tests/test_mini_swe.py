"""Offline tests for the mini-swe shell-loop runner and its trace adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openbench import paths
from openbench.models import HardnessTier, RunLimits, RunResult, Task
from openbench.runners.mini_swe import DONE_MARKER, MiniSweRunner, _extract_command
from openbench.traces.adapters.transcript import normalize


def _scripted_chat(responses: list[dict]):
    it = iter(responses)

    def chat(messages: list[dict]) -> dict:
        return next(it)

    return chat


def _resp(content: str, reasoning: str = "", prompt_tokens: int = 100, completion_tokens: int = 50) -> dict:
    return {
        "choices": [{"message": {"content": content, "reasoning_content": reasoning}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


@pytest.fixture()
def task_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Task:
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
    (tdir / "task.json").write_text(task.model_dump_json())
    return task


def test_extract_command():
    assert _extract_command("text\n```bash\nls -la\n```") == "ls -la"
    # Multiple fences (hallucinated multi-step): take the FIRST real action,
    # never the last (which may be a hallucinated DONE marker).
    assert _extract_command("```bash\nls\n```\nfake out\n```bash\necho OPENBENCH_DONE\n```") == "ls"
    assert _extract_command("no fence here") is None


def test_loop_runs_until_done(task_env: Task, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executed: list[str] = []

    def fake_exec(container, command, timeout=0, user=None, workdir="/repo"):
        executed.append(command)
        from openbench.dockerutil import ExecResult
        out = "1 failed, 2 passed in 0.1s" if "pytest" in command else "ok"
        return ExecResult(0, out, "")

    monkeypatch.setattr("openbench.runners.mini_swe.dockerutil.exec_in", fake_exec)
    runner = MiniSweRunner(chat_fn=_scripted_chat([
        _resp("Look around first.\n```bash\nls src/\n```", reasoning="I should explore."),
        _resp("Now test.\n```bash\npython -m pytest -x\n```"),
        _resp("All good.\n```bash\necho " + DONE_MARKER + "\n```"),
    ]))
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(task_env, "fake-container", run_path, "deepseek-v4-flash", RunLimits(max_turns=10))

    assert exit_reason == "completed"
    assert executed == ["ls src/", "python -m pytest -x"]
    assert usage["num_turns"] == 3
    assert usage["tokens_in"] == 300 and usage["tokens_out"] == 150
    assert usage["cost_usd"] > 0  # deepseek pricing table applied
    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    assert [ln["type"] for ln in lines] == [
        "meta", "api_response", "exec", "api_response", "exec", "api_response", "exec", "final",
    ]


def test_turn_cap_and_no_fence_nudge(task_env: Task, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "openbench.runners.mini_swe.dockerutil.exec_in",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not exec")),
    )
    runner = MiniSweRunner(chat_fn=_scripted_chat([_resp("no command here")] * 3))
    run_path = tmp_path / "run2"
    run_path.mkdir()
    exit_reason, usage = runner.run(task_env, "c", run_path, "deepseek-v4-flash", RunLimits(max_turns=3))
    assert exit_reason == "turn_cap"
    assert usage["num_turns"] == 3


def test_adapter_normalizes_transcript(tmp_path: Path):
    raw = tmp_path / "raw_transcript.jsonl"
    records = [
        {"type": "meta", "model": "deepseek-v4-pro", "task_id": "t"},
        {"type": "api_response", "turn": 1, "content": "```bash\npython -m pytest -q\n```",
         "reasoning_content": "Let me check the tests first.",
         "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        {"type": "exec", "turn": 1, "command": "python -m pytest -q",
         "exit_code": 1, "output": "2 failed, 3 passed in 1.2s"},
        {"type": "api_response", "turn": 2, "content": "```bash\ncat > src/fix.py << 'EOF'\nx=1\nEOF\n```",
         "reasoning_content": "", "usage": {"prompt_tokens": 20, "completion_tokens": 8}},
        {"type": "exec", "turn": 2, "command": "cat > src/fix.py << 'EOF'\nx=1\nEOF",
         "exit_code": 0, "output": ""},
        {"type": "final", "exit_reason": "completed", "turns": 2,
         "usage_totals": {"cost_usd": 0.01, "tokens_in": 30, "tokens_out": 13,
                          "tokens_thinking": 0, "num_turns": 2}},
    ]
    raw.write_text("".join(json.dumps(r) + "\n" for r in records))
    run = RunResult(
        run_id="r1", task_id="t", harness="mini-swe", model="deepseek-v4-pro",
        started_at=datetime(2026, 6, 11, tzinfo=UTC),
    )
    events = normalize(run, raw)
    types = [e.type for e in events]
    assert types == [
        "run_start", "thinking", "assistant_msg", "test_run", "tool_result",
        "assistant_msg", "file_edit", "tool_result", "run_end",
    ]
    assert events[1].content == "Let me check the tests first."
    assert events[4].derived == {"tests_passed": 3, "tests_failed": 2, "tests_errored": 0}
    assert "src/fix.py" in events[6].files_touched
    assert events[-1].cum_cost_usd == 0.01
    assert [e.step_idx for e in events] == list(range(len(events)))
