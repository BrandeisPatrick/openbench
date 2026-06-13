"""Normalize mini-swe shell-loop transcripts into TraceEvents.

Raw format is defined in runners/mini_swe.py: meta / api_response / exec /
final records. Each api_response yields a thinking event (when the model
emitted reasoning_content), an assistant_msg, and — when a command was parsed
— a derived tool event classified like the Claude Code adapter (test_run /
search / shell / file_edit). Each exec yields a tool_result with pytest counts
parsed into `derived`.
"""

from __future__ import annotations

import json
from pathlib import Path

from openbench.models import RunResult, TraceEvent
from openbench.traces.schema import classify_bash, parse_pytest_counts

# Heredoc / inline-python writes are this scaffold's file edits.
_EDIT_HINTS = ("cat >", "cat >>", "tee ", "> /repo", "applypatch", "git apply")


def _classify(command: str) -> str:
    lowered = command.lower()
    if any(h in lowered for h in _EDIT_HINTS):
        return "file_edit"
    return classify_bash(command)


def _edited_files(command: str) -> list[str]:
    files: list[str] = []
    for token in command.replace(">", " > ").split():
        if "/" in token and "." in token.rsplit("/", 1)[-1]:
            files.append(token.strip("'\""))
    return files[:5]


def normalize(run: RunResult, raw_path: Path) -> list[TraceEvent]:
    if not raw_path.exists():
        return []
    events: list[TraceEvent] = []
    step = 0

    def emit(**kwargs) -> None:
        nonlocal step
        events.append(
            TraceEvent(
                event_id=f"{run.run_id}-{step}",
                run_id=run.run_id,
                task_id=run.task_id,
                harness=run.harness,
                model=run.model,
                step_idx=step,
                **kwargs,
            )
        )
        step += 1

    cum_cost = 0.0
    for line in raw_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rtype = rec.get("type")

        if rtype == "meta":
            emit(type="run_start", content=rec.get("model"))
        elif rtype == "api_response":
            u = rec.get("usage") or {}
            tokens_in = int(u.get("prompt_tokens") or 0)
            tokens_out = int(u.get("completion_tokens") or 0)
            if rec.get("reasoning_content"):
                emit(
                    type="thinking",
                    content=rec["reasoning_content"],
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
                tokens_in = tokens_out = 0  # attach usage once per turn
            content = rec.get("content") or ""
            emit(type="assistant_msg", content=content, tokens_in=tokens_in, tokens_out=tokens_out)
        elif rtype == "exec":
            command = rec.get("command") or ""
            etype = _classify(command)
            # Searches/reads need files_touched too, else every later edit
            # looks "unread" and guess_first_rate saturates at 1.0.
            emit(
                type=etype,
                tool_name="Bash",
                tool_args_digest={"command": command[:500]},
                files_touched=_edited_files(command),
            )
            derived = {}
            counts = parse_pytest_counts(rec.get("output") or "")
            if counts:
                derived = counts
            emit(
                type="tool_result",
                content=(rec.get("output") or "")[:2000],
                exit_code=rec.get("exit_code"),
                derived=derived,
                cum_cost_usd=cum_cost,
            )
        elif rtype == "final":
            totals = rec.get("usage_totals") or {}
            cum_cost = float(totals.get("cost_usd") or 0.0)
            emit(type="run_end", content=rec.get("exit_reason"), cum_cost_usd=cum_cost)

    return events
