"""Anthropic protocol (name 'claude-native'): Anthropic Messages API with a real
bash tool + extended thinking. Structural stop + native format + summarized CoT.
"""

from __future__ import annotations

import os

import httpx

from openbench.runners.protocols.base import (
    _API_TIMEOUT_S,
    DONE_MARKER,
    Action,
    BaseProtocol,
    ChatFn,
    _post_with_retry,
)
from openbench.runners.protocols.prompts import SYSTEM_PROMPT_TOOLUSE
from openbench.runners.protocols.providers import PRICES_PER_MTOK
from openbench.runners.protocols.tools import BASH_TOOL

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 16000  # output budget per turn (covers adaptive thinking + answer)
_EFFORT = "high"     # output_config.effort — extended thinking enabled, high effort


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


class AnthropicToolUseProtocol(BaseProtocol):
    name = "claude-native"

    def __init__(self, chat_fn: ChatFn | None = None, effort: str | None = _EFFORT) -> None:
        super().__init__(chat_fn)
        self._effort = effort  # None => no extended thinking (factorial control)

    def initial_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]

    def meta(self) -> dict:
        return {"scaffold": "claude-native", "thinking_effort": self._effort}

    def _make_client(self, model: str) -> httpx.Client:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError(f"ANTHROPIC_API_KEY is not set (required for model {model})")
        return httpx.Client(
            headers={
                "x-api-key": key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=_API_TIMEOUT_S,
        )

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        body = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": SYSTEM_PROMPT_TOOLUSE,
            "messages": messages,
            "tools": [BASH_TOOL],
        }
        # effort=None omits thinking params entirely (lets a factorial isolate
        # protocol from thinking). display:"summarized" — Opus 4.8/4.7 omit
        # thinking text by default ("omitted"); without it the thinking blocks
        # come back empty.
        if self._effort is not None:
            body["thinking"] = {"type": "adaptive", "display": "summarized"}
            body["output_config"] = {"effort": self._effort}
        return _post_with_retry(client, _ANTHROPIC_URL, body)

    def parse_action(self, resp: dict) -> Action:
        blocks = resp.get("content") or []
        text, thinking, tool_use = _parse_blocks(blocks)
        command = (tool_use.get("input") or {}).get("command") or "" if tool_use else None
        return Action(
            command=command, text=text, reasoning=thinking,
            well_formed=tool_use is not None,
            tool_call_id=tool_use.get("id") if tool_use else None,
            # Preserve the raw content blocks (incl. thinking signatures) when
            # passing the assistant turn back — required for thinking+tool-use.
            raw_assistant={"role": "assistant", "content": blocks},
        )

    def usage(self, resp: dict, model: str) -> dict:
        u = resp.get("usage") or {}
        details = u.get("output_tokens_details") or {}
        tin = int(u.get("input_tokens") or 0)
        tout = int(u.get("output_tokens") or 0)
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))
        return {
            "tokens_in": tin,
            "tokens_out": tout,
            # Exact thinking-token count; billed within output_tokens (a subset).
            "tokens_thinking": int(details.get("thinking_tokens") or 0),
            "cost_usd": (tin * price_in + tout * price_out) / 1e6,
        }

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        # Every tool_use block needs a matching tool_result or the API errors.
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": action.tool_call_id,
                "content": f"exit_code: {exit_code}\n{output}",
            }],
        }

    def nudge(self) -> dict:
        return {"role": "user",
                "content": f"Continue with the bash tool, or run `echo {DONE_MARKER}` if the task is complete."}
