"""claude-native runner: native tool-use scaffold (the Claude scaffold fix).

Offline tests with an injected fake Anthropic client — verifies the tool_use
loop, thinking capture, DONE handling and the cost cap.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from openbench import paths
from openbench.models import HardnessTier, RunLimits, Task
from openbench.runners.harness import Harness
from openbench.runners.protocols import AnthropicToolUseProtocol


def _task(tmp) -> Task:
    paths_tasks = tmp / "tasks"
    tdir = paths_tasks / "demo__repo-1"
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("Implement the feature.")
    return Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
    )


def _assistant(blocks: list[dict], in_tok=100, out_tok=50, think_tok=0) -> dict:
    # thinking_tokens defaults to a count when a thinking block is present
    if think_tok == 0 and any(b.get("type") == "thinking" for b in blocks):
        think_tok = 20
    return {
        "content": blocks,
        "usage": {
            "input_tokens": in_tok, "output_tokens": out_tok,
            "output_tokens_details": {"thinking_tokens": think_tok},
        },
    }


def _tool_use(cmd: str, tid="t1") -> dict:
    return {"type": "tool_use", "id": tid, "name": "bash", "input": {"command": cmd}}


def test_tooluse_loop_executes_and_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    monkeypatch.setattr(
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: type("R", (), {"exit_code": 0, "stdout": "ok", "stderr": ""})(),
    )
    task = _task(tmp_path)
    replies = iter([
        _assistant([
            {"type": "thinking", "thinking": "let me look at the repo first"},
            {"type": "text", "text": "I'll list files."},
            _tool_use("ls src/"),
        ]),
        _assistant([_tool_use("echo OPENBENCH_DONE")]),
    ])
    runner = Harness(AnthropicToolUseProtocol(chat_fn=lambda messages: next(replies)))
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "claude-opus-4-8", RunLimits(max_turns=10, max_cost_usd=5.0)
    )
    assert exit_reason == "completed"
    assert usage["num_turns"] == 2
    assert usage["tokens_thinking"] > 0  # thinking text captured (proxy count)

    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    kinds = [r["type"] for r in lines]
    assert kinds[0] == "meta" and kinds[-1] == "final"
    # mini-swe schema: api_response carries content + reasoning_content
    api = [r for r in lines if r["type"] == "api_response"]
    assert api[0]["reasoning_content"] == "let me look at the repo first"
    assert "ls src/" in [r["command"] for r in lines if r["type"] == "exec"]


def test_cost_cap_binds(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    task = _task(tmp_path)
    # opus-4-8 output $25/Mtok; 1M out tokens/turn => $25/turn, cap 5.0 -> stop fast
    big = _assistant([_tool_use("ls")], in_tok=0, out_tok=1_000_000)
    monkeypatch.setattr(
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: type("R", (), {"exit_code": 0, "stdout": "", "stderr": ""})(),
    )
    runner = Harness(AnthropicToolUseProtocol(chat_fn=lambda m: big))
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "claude-opus-4-8", RunLimits(max_turns=50, max_cost_usd=5.0)
    )
    assert exit_reason == "cost_cap"
    assert usage["num_turns"] <= 2  # one $25 turn already crosses $5


def test_registered_in_get_runner():
    from openbench.runners import get_runner

    assert get_runner("claude-native").name == "claude-native"
