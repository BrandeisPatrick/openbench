"""Offline wire-format tests for the OpenAI-compatible tool-use protocol, plus an
end-to-end run of it through the unified Harness loop."""

from __future__ import annotations

from datetime import UTC, datetime

from openbench import paths
from openbench.models import HardnessTier, RunLimits, Task
from openbench.runners.harness import Harness
from openbench.runners.protocols import BASH_FUNCTION, OpenAIToolUseProtocol


def _resp(message: dict) -> dict:
    return {"choices": [{"message": message}]}


def _resp_usage(message: dict, prompt: int = 100, completion: int = 50) -> dict:
    return {"choices": [{"message": message}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


def _tool_call(cmd: str, tid: str = "c1") -> dict:
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": tid, "type": "function",
                            "function": {"name": "bash", "arguments": '{"command": "%s"}' % cmd}}]}


def _responses(reasoning=None, command=None, text=None, call_id="fc1", rid="resp_1") -> dict:
    """A canned OpenAI Responses-API response (reasoning summary + function_call)."""
    out = []
    if reasoning:
        out.append({"type": "reasoning", "summary": [{"type": "summary_text", "text": reasoning}]})
    if command is not None:
        out.append({"type": "function_call", "call_id": call_id, "name": "bash",
                    "arguments": '{"command": "%s"}' % command})
    if text:
        out.append({"type": "message", "content": [{"type": "output_text", "text": text}]})
    return {"id": rid, "output": out,
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "output_tokens_details": {"reasoning_tokens": 30}}}


def test_build_request_declares_bash_and_keeps_choice_auto():
    p = OpenAIToolUseProtocol()
    body = p.build_request("deepseek-chat", [{"role": "user", "content": "go"}], "SYS")
    assert body["tools"] == [BASH_FUNCTION]
    assert body["tool_choice"] == "auto"  # never "required" — keep emission voluntary
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["model"] == "deepseek-chat"


def test_parse_well_formed_tool_call():
    p = OpenAIToolUseProtocol()
    act = p.parse_action(_resp({
        "role": "assistant", "content": "I'll list files.",
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "bash", "arguments": '{"command": "ls /repo"}'}}],
    }))
    assert act.well_formed is True
    assert act.command == "ls /repo"
    assert act.tool_call_id == "call_1"


def test_parse_prose_only_is_not_well_formed():
    p = OpenAIToolUseProtocol()
    act = p.parse_action(_resp({"role": "assistant", "content": "Sure, I would run ls."}))
    assert act.well_formed is False
    assert act.command is None


def test_parse_bad_or_empty_arguments_not_well_formed():
    p = OpenAIToolUseProtocol()
    bad_json = p.parse_action(_resp({"tool_calls": [
        {"id": "c", "function": {"name": "bash", "arguments": "{not json"}}]}))
    empty_cmd = p.parse_action(_resp({"tool_calls": [
        {"id": "c", "function": {"name": "bash", "arguments": '{"command": "  "}'}}]}))
    assert bad_json.well_formed is False and bad_json.command is None
    assert empty_cmd.well_formed is False and empty_cmd.command is None


def test_assistant_turn_and_tool_result_round_trip():
    p = OpenAIToolUseProtocol()
    act = p.parse_action(_resp({
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "call_9", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}],
    }))
    # The harness appends the assistant turn verbatim (so tool_call ids survive),
    # then the protocol's tool result keyed by that id (now incl. the exit code).
    assert act.raw_assistant["role"] == "assistant"
    assert act.tool_call_id == "call_9"
    msg = p.result_message(act, "file_a.py\nfile_b.py", 0)
    assert msg == {"role": "tool", "tool_call_id": "call_9",
                   "content": "exit_code: 0\nfile_a.py\nfile_b.py"}


def test_tooluse_runs_through_unified_harness(tmp_path, monkeypatch):
    """The genuinely new path: tooluse driven by the shared Harness loop produces
    the same meta/api_response/exec/final transcript as the other protocols."""
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
    monkeypatch.setattr(
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: type("R", (), {"exit_code": 0, "stdout": "ok", "stderr": ""})(),
    )
    replies = iter([
        _resp_usage(_tool_call("ls src/")),
        _resp_usage(_tool_call("echo OPENBENCH_DONE")),
    ])
    runner = Harness(OpenAIToolUseProtocol(chat_fn=lambda messages: next(replies)))
    assert runner.name == "tooluse"
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(
        task, "c", run_path, "deepseek-v4-flash", RunLimits(max_turns=10, max_cost_usd=5.0)
    )
    assert exit_reason == "completed"
    assert usage["num_turns"] == 2
    assert usage["tokens_in"] == 200 and usage["tokens_out"] == 100

    import json
    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    assert [ln["type"] for ln in lines] == ["meta", "api_response", "exec", "api_response", "exec", "final"]
    assert "ls src/" in [ln["command"] for ln in lines if ln["type"] == "exec"]


def test_responses_parse_and_result_message():
    from openbench.runners.protocols import OpenAIResponsesProtocol
    p = OpenAIResponsesProtocol()
    act = p.parse_action(_responses(reasoning="think", command="ls", text="hi"))
    assert act.well_formed and act.command == "ls"
    assert act.reasoning == "think" and act.text == "hi" and act.tool_call_id == "fc1"
    assert p.result_message(act, "out", 0) == {
        "type": "function_call_output", "call_id": "fc1", "output": "exit_code: 0\nout"}
    # prose-only (no function_call) is not well-formed
    assert p.parse_action(_responses(reasoning="hmm", text="just talking")).well_formed is False


def test_gpt_responses_captures_cot_through_harness(tmp_path, monkeypatch):
    """CoT-for-all: GPT reasoning summary lands in the transcript's reasoning_content
    via the same Harness loop, and previous_response_id threading works."""
    from openbench.runners.protocols import OpenAIResponsesProtocol
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    tdir = paths.task_dir("demo__repo-1")
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("fix it")
    task = Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0,
    )
    (tdir / "task.json").write_text(task.model_dump_json())
    monkeypatch.setattr(
        "openbench.runners.harness.dockerutil.exec_in",
        lambda *a, **k: type("R", (), {"exit_code": 0, "stdout": "ok", "stderr": ""})(),
    )
    replies = iter([
        _responses(reasoning="I should inspect symbol.py first.", command="ls src/", text="listing"),
        _responses(command="echo OPENBENCH_DONE", rid="resp_2"),
    ])
    runner = Harness(OpenAIResponsesProtocol(chat_fn=lambda m: next(replies)))
    assert runner.name == "gpt-responses"
    run_path = tmp_path / "run"
    run_path.mkdir()
    exit_reason, usage = runner.run(task, "c", run_path, "gpt-5.5", RunLimits(max_turns=10, max_cost_usd=5.0))
    assert exit_reason == "completed"
    assert usage["tokens_thinking"] > 0  # reasoning tokens counted

    import json
    lines = [json.loads(ln) for ln in (run_path / "raw_transcript.jsonl").read_text().splitlines()]
    api = [r for r in lines if r["type"] == "api_response"]
    assert api[0]["reasoning_content"] == "I should inspect symbol.py first."  # CoT visible
    assert "ls src/" in [r["command"] for r in lines if r["type"] == "exec"]


def test_responses_reasoning_param_only_for_reasoning_models(monkeypatch):
    """gpt-4.1 (no reasoning channel) must not receive the `reasoning` body param —
    the Responses API 400s on it; gpt-5.5 must still get it."""
    from openbench.runners.protocols import openai_responses as mod

    bodies: list[dict] = []
    monkeypatch.setattr(
        mod, "_post_with_retry",
        lambda client, path, body: (bodies.append(body), {"id": "r1", "output": []})[1],
    )
    for wire in ("gpt-4.1", "gpt-5.5"):
        p = mod.OpenAIResponsesProtocol()
        p._wire = wire
        p._send(None, [{"role": "user", "content": "go"}], wire)
    assert "reasoning" not in bodies[0]                      # gpt-4.1: omitted
    assert bodies[1]["reasoning"] == {"summary": "auto"}     # gpt-5.5: present
