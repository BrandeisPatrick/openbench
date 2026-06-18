"""tooluse runner: native function-calling scaffold for OpenAI-compatible providers.

Offline tests with an injected fake `/chat/completions` client — verifies the
tool-call loop, the no-tool-call nudge (the structural anti-dream: no fabricated
output is ever fed back), tool_result round-trip, OpenRouter cost passthrough,
DONE handling, and that the transcript is mini-swe schema so the existing
adapter+metrics normalize it unchanged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from openbench import paths
from openbench.models import HardnessTier, RunLimits, Task
from openbench.runners.tooluse import ToolUseRunner


def _task(tmp) -> Task:
    tdir = tmp / "tasks" / "demo__repo-1"
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("Implement the feature.")
    return Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
    )


def _resp(message: dict, in_tok=100, out_tok=50, reasoning_tok=0, cost=None) -> dict:
    usage: dict = {
        "prompt_tokens": in_tok, "completion_tokens": out_tok,
        "completion_tokens_details": {"reasoning_tokens": reasoning_tok},
    }
    if cost is not None:
        usage["cost"] = cost
    return {"choices": [{"message": message}], "usage": usage}


def _toolcall(cmd: str, tid="call_1", text="", reasoning="") -> dict:
    msg: dict = {
        "role": "assistant", "content": text,
        "tool_calls": [{
            "id": tid, "type": "function",
            "function": {"name": "bash", "arguments": json.dumps({"command": cmd})},
        }],
    }
    if reasoning:
        msg["reasoning_content"] = reasoning
    return msg


class _FakeChat:
    """Records the messages seen on each call (snapshotted) and returns replies."""

    def __init__(self, replies: list[dict]) -> None:
        self._replies = iter(replies)
        self.seen: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> dict:
        self.seen.append(list(messages))
        return next(self._replies)


def _stub_exec(monkeypatch, stdout="ok"):
    monkeypatch.setattr(
        "openbench.runners.tooluse.dockerutil.exec_in",
        lambda *a, **k: type("R", (), {"exit_code": 0, "stdout": stdout, "stderr": ""})(),
    )


def test_loop_executes_and_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _stub_exec(monkeypatch, stdout="src/app.py")
    task = _task(tmp_path)
    chat = _FakeChat([
        _resp(_toolcall("ls src/", text="I'll list files.", reasoning="look first")),
        _resp(_toolcall("echo OPENBENCH_DONE")),
    ])
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = ToolUseRunner(chat_fn=chat).run(
        task, "c", run_path, "deepseek-chat", RunLimits(max_turns=10, max_cost_usd=5.0)
    )
    assert exit_reason == "completed"
    assert usage["num_turns"] == 2

    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    assert lines[0]["type"] == "meta" and lines[0]["scaffold"] == "tooluse"
    assert lines[-1]["type"] == "final"
    api = [r for r in lines if r["type"] == "api_response"]
    assert api[0]["content"] == "I'll list files." and api[0]["reasoning_content"] == "look first"
    assert "ls src/" in [r["command"] for r in lines if r["type"] == "exec"]


def test_no_tool_call_nudges_and_feeds_no_fabricated_output(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _stub_exec(monkeypatch)
    task = _task(tmp_path)
    chat = _FakeChat([
        _resp({"role": "assistant", "content": "Sure, I would run ls."}),  # prose, no tool call
        _resp(_toolcall("echo OPENBENCH_DONE")),
    ])
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, _ = ToolUseRunner(chat_fn=chat).run(
        task, "c", run_path, "deepseek-chat", RunLimits(max_turns=10, max_cost_usd=5.0)
    )
    assert exit_reason == "completed"
    # The second call's message history must contain a nudge, and NO tool/observation
    # message fabricated from the prose-only turn (the structural anti-dream).
    second = chat.seen[1]
    assert any(m["role"] == "user" and "did not call" in str(m["content"]) for m in second)
    assert not any(m.get("role") == "tool" for m in second)
    # Only the DONE pseudo-exec is logged; the prose turn ran nothing.
    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    execs = [r for r in lines if r["type"] == "exec"]
    assert len(execs) == 1 and execs[0]["output"] == "OPENBENCH_DONE"


def test_tool_result_round_trip_and_openrouter_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _stub_exec(monkeypatch, stdout="file_a.py\nfile_b.py")
    task = _task(tmp_path)
    chat = _FakeChat([
        _resp(_toolcall("ls", tid="call_9"), cost=0.01),
        _resp(_toolcall("echo OPENBENCH_DONE")),  # no cost -> price fallback (0 for this model)
    ])
    run_path = tmp_path / "run"
    run_path.mkdir()
    _, usage = ToolUseRunner(chat_fn=chat).run(
        task, "c", run_path, "deepseek-chat", RunLimits(max_turns=10, max_cost_usd=5.0)
    )
    # OpenRouter usage.cost is taken verbatim; unknown model -> 0 price fallback.
    assert usage["cost_usd"] == 0.01
    # The assistant turn (with tool_call) and the real tool_result round-trip in.
    second = chat.seen[1]
    tool_msgs = [m for m in second if m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_call_id"] == "call_9"
    assert "file_a.py" in tool_msgs[0]["content"]


def test_cost_cap_stops_before_next_call(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _stub_exec(monkeypatch)
    task = _task(tmp_path)
    # First reply reports a cost above the cap via OpenRouter passthrough; the loop
    # must stop at the top of turn 2 before issuing another paid call.
    chat = _FakeChat([
        _resp(_toolcall("ls"), cost=9.0),
        _resp(_toolcall("ls again")),  # should never be requested
    ])
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = ToolUseRunner(chat_fn=chat).run(
        task, "c", run_path, "deepseek-chat", RunLimits(max_turns=10, max_cost_usd=1.0)
    )
    assert exit_reason == "cost_cap"
    assert len(chat.seen) == 1  # only one paid call was made
