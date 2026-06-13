"""Normalize Claude Code stream-json transcripts into TraceEvents.

The raw format may drift between CLI versions, so every field access is
defensive: bad JSON lines are skipped, unknown event types are skipped and
counted in the module-level `last_skipped`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from openbench.models import RunResult, TraceEvent
from openbench.traces.schema import (
    EDIT_TOOLS,
    READ_TOOLS,
    SEARCH_TOOLS,
    classify_bash,
    parse_pytest_counts,
)

_DIGEST_KEYS = ("command", "file_path", "pattern")
_DIGEST_MAX_CHARS = 500

# Number of raw lines skipped (bad JSON / unknown type) by the last
# normalize() call. Diagnostic only.
last_skipped: int = 0


def _parse_ts(event: dict) -> datetime | None:
    raw = event.get("timestamp") or event.get("ts")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw)
        except (ValueError, OSError, OverflowError):
            return None
    return None


def _digest(tool_input: Any) -> dict[str, Any]:
    if not isinstance(tool_input, dict):
        return {}
    out: dict[str, Any] = {}
    for key in _DIGEST_KEYS:
        if key in tool_input:
            value = tool_input[key]
            if isinstance(value, str):
                value = value[:_DIGEST_MAX_CHARS]
            out[key] = value
    return out


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for piece in content:
            if isinstance(piece, dict) and isinstance(piece.get("text"), str):
                parts.append(piece["text"])
        return "\n".join(parts)
    return ""


def normalize(run: RunResult, raw_path: Path) -> list[TraceEvent]:
    global last_skipped
    last_skipped = 0
    events: list[TraceEvent] = []
    step_idx = 0
    cum_cost = 0.0
    # tool_use id -> derived event type, so tool_results can inherit context.
    call_kinds: dict[str, str] = {}

    def emit(type_: str, ts: datetime | None = None, **kw: Any) -> TraceEvent:
        nonlocal step_idx
        ev = TraceEvent(
            event_id=f"{run.run_id}-{step_idx}",
            run_id=run.run_id,
            task_id=run.task_id,
            harness=run.harness,
            model=run.model,
            step_idx=step_idx,
            ts=ts,
            type=type_,  # type: ignore[arg-type]
            cum_cost_usd=cum_cost,
            **kw,
        )
        events.append(ev)
        step_idx += 1
        return ev

    if not raw_path.exists():
        return events

    for line in raw_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            last_skipped += 1
            continue
        if not isinstance(raw, dict):
            last_skipped += 1
            continue

        etype = raw.get("type")
        ts = _parse_ts(raw)

        if etype == "system" and raw.get("subtype") == "init":
            emit("run_start", ts=ts, content=str(raw.get("model") or ""))

        elif etype == "assistant":
            message = raw.get("message") or {}
            if not isinstance(message, dict):
                last_skipped += 1
                continue
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            usage_pending = True
            blocks = message.get("content")
            if not isinstance(blocks, list):
                blocks = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                ev: TraceEvent | None = None
                if btype == "thinking":
                    ev = emit("thinking", ts=ts, content=str(block.get("thinking") or ""))
                elif btype == "text":
                    ev = emit("assistant_msg", ts=ts, content=str(block.get("text") or ""))
                elif btype == "tool_use":
                    tool_name = str(block.get("name") or "")
                    tool_input = block.get("input")
                    digest = _digest(tool_input)
                    derived_type = "tool_call"
                    files: list[str] = []
                    file_path = (
                        tool_input.get("file_path") if isinstance(tool_input, dict) else None
                    )
                    if tool_name in EDIT_TOOLS:
                        derived_type = "file_edit"
                        if isinstance(file_path, str):
                            files = [file_path]
                    elif tool_name == "Bash":
                        command = digest.get("command")
                        derived_type = classify_bash(command) if isinstance(command, str) else "shell"
                    elif tool_name in READ_TOOLS or tool_name in SEARCH_TOOLS:
                        derived_type = "search"
                        if isinstance(file_path, str):
                            files = [file_path]
                    ev = emit(
                        derived_type,
                        ts=ts,
                        tool_name=tool_name,
                        tool_args_digest=digest,
                        files_touched=files,
                    )
                    tool_id = block.get("id")
                    if isinstance(tool_id, str):
                        call_kinds[tool_id] = derived_type
                if ev is not None and usage_pending and usage:
                    # attach per-message usage to this message's first event
                    try:
                        ev.tokens_in = int(usage.get("input_tokens") or 0)
                        ev.tokens_out = int(usage.get("output_tokens") or 0)
                    except (TypeError, ValueError):
                        pass
                    usage_pending = False

        elif etype == "user":
            message = raw.get("message") or {}
            blocks = message.get("content") if isinstance(message, dict) else None
            if not isinstance(blocks, list):
                last_skipped += 1
                continue
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                text = _result_text(block)
                derived: dict[str, Any] = {}
                tool_id = block.get("tool_use_id")
                if isinstance(tool_id, str) and call_kinds.get(tool_id) == "test_run":
                    counts = parse_pytest_counts(text)
                    if counts:
                        derived.update(counts)
                exit_code = None
                if "is_error" in block:
                    exit_code = 1 if block.get("is_error") else 0
                emit(
                    "tool_result",
                    ts=ts,
                    content=text,
                    exit_code=exit_code,
                    derived=derived,
                )

        elif etype == "result":
            try:
                cum_cost = float(raw.get("total_cost_usd") or 0.0)
            except (TypeError, ValueError):
                cum_cost = 0.0
            emit("run_end", ts=ts, content=str(raw.get("result") or ""))

        else:
            # stream_event partials, future event types, etc.
            last_skipped += 1

    return events
