"""Offline tests for the Claude Code stream-json trace adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openbench.models import RunResult
from openbench.traces.adapters import claude_code as adapter
from openbench.traces.schema import classify_bash, parse_pytest_counts


def _run_result() -> RunResult:
    return RunResult(
        run_id="demo__repo-1--claude-code--sonnet--20260610-000000",
        task_id="demo__repo-1",
        harness="claude-code",
        model="claude-sonnet-4-6",
        started_at=datetime(2026, 6, 10, tzinfo=UTC),
    )


def _transcript_lines() -> list[str]:
    events = [
        {"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-sonnet-4-6"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 120, "output_tokens": 45},
                "content": [
                    {"type": "thinking", "thinking": "The failing test points at foo()."},
                    {"type": "text", "text": "Let me run the test suite first."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Bash",
                        "input": {"command": "python -m pytest -x"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "is_error": False,
                        "content": "1 passed in 0.03s",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 200, "output_tokens": 30},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_02",
                        "name": "Edit",
                        "input": {
                            "file_path": "src/foo.py",
                            "old_string": "return 1",
                            "new_string": "return 2",
                        },
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_02", "content": "ok"}
                ],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.42,
            "num_turns": 2,
            "result": "Fixed foo().",
        },
    ]
    lines = [json.dumps(e) for e in events]
    # Adapter must skip unknown event types and malformed JSON silently.
    lines.insert(1, json.dumps({"type": "stream_event", "event": {"delta": "..."}}))
    lines.append("{not valid json")
    return lines


def test_normalize_sequence_and_derivations(tmp_path: Path) -> None:
    raw = tmp_path / "raw_transcript.jsonl"
    raw.write_text("\n".join(_transcript_lines()) + "\n")
    run = _run_result()

    events = adapter.normalize(run, raw)

    assert [e.type for e in events] == [
        "run_start",
        "thinking",
        "assistant_msg",
        "test_run",
        "tool_result",
        "file_edit",
        "tool_result",
        "run_end",
    ]
    # step ordering + ids
    assert [e.step_idx for e in events] == list(range(len(events)))
    assert events[0].event_id == f"{run.run_id}-0"
    assert all(e.run_id == run.run_id for e in events)

    # Bash test_run keeps tool_name and the command digest
    test_run = events[3]
    assert test_run.tool_name == "Bash"
    assert test_run.tool_args_digest == {"command": "python -m pytest -x"}

    # tool_result for a test_run gets pytest counts + exit_code from is_error
    result = events[4]
    assert result.derived == {"tests_passed": 1, "tests_failed": 0, "tests_errored": 0}
    assert result.exit_code == 0

    # Edit becomes file_edit with files_touched; digest drops old/new strings
    edit = events[5]
    assert edit.tool_name == "Edit"
    assert edit.files_touched == ["src/foo.py"]
    assert edit.tool_args_digest == {"file_path": "src/foo.py"}

    # second tool_result had no is_error and no pytest output
    assert events[6].exit_code is None
    assert events[6].derived == {}

    # usage lands on the first event of each assistant message
    assert (events[1].tokens_in, events[1].tokens_out) == (120, 45)
    assert (events[2].tokens_in, events[2].tokens_out) == (0, 0)
    assert (edit.tokens_in, edit.tokens_out) == (200, 30)

    # run_end carries result text and cumulative cost
    assert events[-1].content == "Fixed foo()."
    assert events[-1].cum_cost_usd == pytest.approx(0.42)

    # one unknown event type + one bad JSON line skipped
    assert adapter.last_skipped == 2


def test_normalize_missing_file(tmp_path: Path) -> None:
    assert adapter.normalize(_run_result(), tmp_path / "nope.jsonl") == []


def test_classify_bash() -> None:
    assert classify_bash("python -m pytest tests/ -x") == "test_run"
    assert classify_bash("pytest -k foo") == "test_run"
    assert classify_bash("tox -e py312") == "test_run"
    assert classify_bash("rg 'def foo' src") == "search"
    assert classify_bash("grep -r foo .") == "search"
    assert classify_bash("ls -la src") == "search"
    assert classify_bash("pip install -e .") == "shell"


def test_parse_pytest_counts() -> None:
    assert parse_pytest_counts("== 3 passed, 1 failed, 2 errors in 0.12s ==") == {
        "tests_passed": 3,
        "tests_failed": 1,
        "tests_errored": 2,
    }
    assert parse_pytest_counts("1 passed in 0.01s") == {
        "tests_passed": 1,
        "tests_failed": 0,
        "tests_errored": 0,
    }
    assert parse_pytest_counts("no tests ran here") is None
