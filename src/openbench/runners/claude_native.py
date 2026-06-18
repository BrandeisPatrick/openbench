"""Native tool-use scaffold for Anthropic models (the fix for the scaffold confound).

`mini-swe` forces one ```bash fence parsed from free text — a protocol foreign to
Claude, which is trained to act through structured tool-use content blocks. Denied
its native channel, Claude (esp. Opus) hallucinates the tool loop instead of acting
(confabulated_completion 0.75, 3-turn dreamed sessions, zero-line patches). This
runner gives Claude the protocol it was trained on: the Anthropic Messages API with a
real `bash` tool and extended thinking enabled.

CRITICAL DESIGN: this runner writes the SAME raw_transcript.jsonl schema as mini-swe
(meta / api_response / exec / final), so the identical metrics pipeline and adapter
normalize it. The ONLY thing that differs between a `claude-native` run and a
`mini-swe` run of the same model is the model's actual behavior under the two
protocols — not the parsing. That makes claude-native vs mini-swe a clean controlled
falsification of the scaffold-mismatch hypothesis.

Tool surface is deliberately bash-only (one command per turn), identical to mini-swe,
so the sole manipulated variable is structured tool_use vs text-fence — not the tool
set. The API key is called from the HOST; the container stays network=none.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import httpx

from openbench import dockerutil, paths
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage
from openbench.runners.common import (
    API_TIMEOUT_S,
    DONE_MARKER,
    EXEC_TIMEOUT_S,
    NATIVE_SYSTEM_PROMPT,
    PRICES_PER_MTOK,
    truncate,
)

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 16000  # output budget per turn (covers adaptive thinking + answer)
_EFFORT = "high"     # output_config.effort — extended thinking enabled, high effort

BASH_TOOL = {
    "name": "bash",
    "description": (
        "Run one bash command in /repo (current directory) and get its "
        "stdout/stderr. No internet access. Use heredocs to edit files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "the command"}},
        "required": ["command"],
    },
}

# Native-tool-use prompt is shared via common (also used by the tooluse runner).
SYSTEM_PROMPT = NATIVE_SYSTEM_PROMPT


def _default_chat(model: str, effort: str | None = _EFFORT) -> Callable[[list[dict]], dict]:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(f"ANTHROPIC_API_KEY is not set (required for model {model})")
    client = httpx.Client(
        headers={
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        timeout=API_TIMEOUT_S,
    )

    def chat(messages: list[dict]) -> dict:
        body = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "tools": [BASH_TOOL],
        }
        # effort=None omits the thinking params entirely (no extended thinking) —
        # lets a factorial isolate protocol from thinking. Newer Anthropic config:
        # adaptive + effort (the older enabled+budget_tokens shape is rejected).
        if effort is not None:
            # display:"summarized" — Opus 4.8/4.7 omit thinking text by default
            # ("omitted"); without this the thinking blocks come back empty (the
            # cause of the all-empty reasoning_content in the bundled corpus).
            body["thinking"] = {"type": "adaptive", "display": "summarized"}
            body["output_config"] = {"effort": effort}
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = client.post(_ANTHROPIC_URL, json=body)
                if resp.status_code in (429, 500, 502, 503, 529):
                    time.sleep(2**attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_err = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"anthropic API failed after retries: {last_err}")

    return chat


def _parse_blocks(content: list[dict]) -> tuple[str, str, dict | None]:
    """(assistant_text, thinking_text, first_tool_use_block) from response content."""
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    first_tool: dict | None = None
    for block in content:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text") or "")
        elif btype == "thinking":
            thinking_parts.append(block.get("thinking") or "")
        elif btype == "tool_use" and first_tool is None:
            first_tool = block
    return "\n".join(text_parts), "\n".join(thinking_parts), first_tool


class ClaudeNativeRunner:
    """name 'claude-native'. chat_fn is injectable for offline tests.

    Writes mini-swe-format transcripts so the mini-swe adapter normalizes them
    (pipeline.py routes claude-native -> mini_swe adapter).
    """

    name = "claude-native"
    needs_network = False  # API called from host; container stays offline.

    def __init__(
        self,
        chat_fn: Callable[[list[dict]], dict] | None = None,
        effort: str | None = _EFFORT,
    ) -> None:
        self._chat_fn = chat_fn
        self._effort = effort  # None => no extended thinking (factorial control)

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        transcript = run_path / "raw_transcript.jsonl"
        prompt = (paths.task_dir(task.task_id) / task.prompt_path).read_text()
        chat = self._chat_fn or _default_chat(model, self._effort)
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))

        usage = zero_usage()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        exit_reason: ExitReason = "turn_cap"
        started = time.monotonic()

        with transcript.open("w") as log:
            log.write(json.dumps({
                "type": "meta", "model": model, "task_id": task.task_id,
                "scaffold": "claude-native",
                "thinking_effort": self._effort,  # None => no extended thinking
            }) + "\n")
            for turn in range(1, limits.max_turns + 1):
                if time.monotonic() - started > limits.wall_clock_s:
                    exit_reason = "timeout"
                    break
                if usage["cost_usd"] > limits.max_cost_usd:
                    exit_reason = "cost_cap"
                    break
                try:
                    data = chat(messages)
                except Exception as exc:
                    (run_path / "runner_error.log").write_text(str(exc))
                    exit_reason = "crash"
                    break

                content_blocks = data.get("content") or []
                text, thinking, tool_use = _parse_blocks(content_blocks)
                u = data.get("usage") or {}
                tok_in = int(u.get("input_tokens") or 0)
                tok_out = int(u.get("output_tokens") or 0)
                usage["tokens_in"] += tok_in
                usage["tokens_out"] += tok_out
                # Exact thinking-token count (output_tokens_details.thinking_tokens);
                # thinking is billed within output_tokens, so this is a subset.
                details = u.get("output_tokens_details") or {}
                usage["tokens_thinking"] += int(details.get("thinking_tokens") or 0)
                usage["num_turns"] = turn
                usage["cost_usd"] += (tok_in * price_in + tok_out * price_out) / 1e6

                log.write(json.dumps({
                    "type": "api_response", "turn": turn,
                    "content": text, "reasoning_content": thinking,
                    "usage": {"prompt_tokens": tok_in, "completion_tokens": tok_out},
                }) + "\n")
                log.flush()

                # Preserve the raw content blocks (incl. thinking signatures) when
                # passing the assistant turn back — required for thinking+tool-use.
                messages.append({"role": "assistant", "content": content_blocks})

                if tool_use is None:
                    # Model stopped calling tools without signalling done; nudge it.
                    messages.append({
                        "role": "user",
                        "content": "Continue with the bash tool, or run `echo "
                        f"{DONE_MARKER}` if the task is complete.",
                    })
                    continue

                command = (tool_use.get("input") or {}).get("command") or ""
                if DONE_MARKER in command:
                    log.write(json.dumps({
                        "type": "exec", "turn": turn, "command": command,
                        "exit_code": 0, "output": DONE_MARKER,
                    }) + "\n")
                    exit_reason = "completed"
                    break

                res = dockerutil.exec_in(
                    container, command, timeout=EXEC_TIMEOUT_S, user="agent"
                )
                output = truncate((res.stdout or "") + (res.stderr or ""))
                log.write(json.dumps({
                    "type": "exec", "turn": turn, "command": command,
                    "exit_code": res.exit_code, "output": output,
                }) + "\n")
                log.flush()
                # Every tool_use block in the assistant turn needs a matching
                # tool_result or the API errors; we executed the first one.
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use.get("id"),
                        "content": f"exit_code: {res.exit_code}\n{output}",
                    }],
                })

            log.write(json.dumps({
                "type": "final", "exit_reason": exit_reason,
                "turns": usage["num_turns"], "usage_totals": usage,
            }) + "\n")

        return exit_reason, usage
