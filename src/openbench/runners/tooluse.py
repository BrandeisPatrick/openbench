"""Native function-calling scaffold for OpenAI-compatible providers.

The structural counterpart to `mini_swe`: instead of parsing a ```bash fence out
of free text, the model emits a `bash` tool call and the API ends the turn at the
call (`finish_reason="tool_calls"`). That removes the two things the text-fence
protocol lacks — a hard stop at the action and an environment-owned observation
channel — so a tool-trained model cannot over-generate a fabricated session
("dream"). It is the in-distribution arm for DeepSeek/GPT/Qwen/GLM/Kimi.

This runner is the missing wrapper around `protocols.OpenAIToolUseProtocol`
(request build / action parse / observation round-trip). It reuses `mini_swe`'s
provider routing and usage accounting, and `claude_native`'s loop shape, and
writes the SAME raw_transcript.jsonl schema (meta / api_response / exec / final)
so the existing mini-swe adapter normalizes it unchanged — only the protocol
differs, not the parsing.

`NativeRunner` (name "native") is the common harness: it dispatches Anthropic
models to `claude_native` (native Messages API tool_use + thinking) and everything
else to this runner, so the whole roster runs one minimal native-tool-use protocol.
"""

from __future__ import annotations

import json
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
    accumulate_openai_usage,
    request_with_retries,
    resolve_provider,
    truncate,
)
from openbench.runners.protocols import OpenAIToolUseProtocol

# The shared native-tool-use system prompt keeps the common harness uniform
# (Anthropic and OpenAI-compat models read identical instructions).
SYSTEM_PROMPT = NATIVE_SYSTEM_PROMPT


def _default_chat(
    model: str, protocol: OpenAIToolUseProtocol, system: str
) -> Callable[[list[dict]], dict]:
    """A `/chat/completions` caller that declares the bash tool via the protocol.

    `messages` is the conversation WITHOUT the system turn; the protocol prepends
    it. Provider routing/keys come from `common.resolve_provider`."""
    base_url, key, wire_model = resolve_provider(model)
    client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {key}"},
        timeout=API_TIMEOUT_S,
    )

    def chat(messages: list[dict]) -> dict:
        return request_with_retries(client, protocol.build_request(wire_model, messages, system))

    return chat


class ToolUseRunner:
    """name 'tooluse'. Native function-calling over OpenAI-compatible providers.

    chat_fn is injectable for offline tests. Writes the mini-swe transcript schema
    so pipeline.py routes it through the mini_swe adapter.
    """

    name = "tooluse"
    needs_network = False  # API is called from the host; container stays offline.

    def __init__(self, chat_fn: Callable[[list[dict]], dict] | None = None) -> None:
        self._chat_fn = chat_fn
        self._protocol = OpenAIToolUseProtocol()

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
        protocol = self._protocol
        chat = self._chat_fn or _default_chat(model, protocol, SYSTEM_PROMPT)
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))

        usage = zero_usage()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        exit_reason: ExitReason = "turn_cap"
        started = time.monotonic()

        with transcript.open("w") as log:
            log.write(json.dumps({
                "type": "meta", "model": model, "task_id": task.task_id,
                "scaffold": "tooluse",
            }) + "\n")
            for turn in range(1, limits.max_turns + 1):
                if time.monotonic() - started > limits.wall_clock_s:
                    exit_reason = "timeout"
                    break
                # Cost cap BEFORE the next API call (matches mini_swe ordering).
                if usage["cost_usd"] > limits.max_cost_usd:
                    exit_reason = "cost_cap"
                    break
                try:
                    data = chat(messages)
                except Exception as exc:
                    (run_path / "runner_error.log").write_text(str(exc))
                    exit_reason = "crash"
                    break

                action = protocol.parse_action(data)
                u = data.get("usage") or {}
                accumulate_openai_usage(usage, u, price_in, price_out)
                usage["num_turns"] = turn
                log.write(json.dumps({
                    "type": "api_response", "turn": turn,
                    "content": action.text, "reasoning_content": action.reasoning,
                    "usage": {
                        "prompt_tokens": u.get("prompt_tokens", 0),
                        "completion_tokens": u.get("completion_tokens", 0),
                    },
                }) + "\n")
                log.flush()

                if not action.well_formed:
                    # No usable tool call. Preserve the assistant prose, then nudge.
                    # Crucially, no fabricated output is ever fed back as real — the
                    # structural reason the "dream" cannot drive control flow here.
                    if action.raw_assistant is not None:
                        messages.append(action.raw_assistant)
                    messages.append({
                        "role": "user",
                        "content": "You did not call the `bash` tool. Call `bash` with "
                        f"one command, or `echo {DONE_MARKER}` if the task is complete.",
                    })
                    continue

                command = action.command or ""
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
                # Append the assistant turn carrying the tool call (verbatim, so the
                # tool_call_id matches) then the real tool result.
                for msg in protocol.observation(action, f"exit_code: {res.exit_code}\n{output}"):
                    messages.append(msg)

            log.write(json.dumps({
                "type": "final", "exit_reason": exit_reason,
                "turns": usage["num_turns"], "usage_totals": usage,
            }) + "\n")

        return exit_reason, usage


class NativeRunner:
    """name 'native' — the common harness. Minimal native tool-use for every model,
    dispatched to the right wire adapter by provider: Anthropic models use the
    native Messages API (claude_native, with thinking); all others use the
    OpenAI-compatible function-calling runner above. One protocol, two transports.

    Both delegates write the same transcript schema; `execute_run` records
    harness='native' uniformly, so analysis groups all runs into one harness.
    """

    name = "native"
    needs_network = False

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        if model.startswith("claude"):
            # Direct Anthropic models -> native Messages API tool_use + thinking.
            from openbench.runners.claude_native import ClaudeNativeRunner

            delegate: object = ClaudeNativeRunner()
        else:
            # Everything else (incl. openrouter/*) -> OpenAI-compat function-calling.
            delegate = ToolUseRunner()
        return delegate.run(task, container, run_path, model, limits)
