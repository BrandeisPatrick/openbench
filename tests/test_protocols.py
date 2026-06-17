"""Offline wire-format tests for the OpenAI-compatible tool-use adapter."""

from __future__ import annotations

from openbench.runners.protocols import BASH_FUNCTION, OpenAIToolUseProtocol


def _resp(message: dict) -> dict:
    return {"choices": [{"message": message}]}


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


def test_observation_round_trips_assistant_then_tool_result():
    p = OpenAIToolUseProtocol()
    act = p.parse_action(_resp({
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "call_9", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}],
    }))
    msgs = p.observation(act, "file_a.py\nfile_b.py")
    assert msgs[0] == act.raw_assistant  # the assistant turn carrying the tool call
    assert msgs[1] == {"role": "tool", "tool_call_id": "call_9", "content": "file_a.py\nfile_b.py"}
