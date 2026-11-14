"""Anthropic protocol (name 'claude-native'): Anthropic Messages API with a real
bash tool + extended thinking. Structural stop + native format + summarized CoT.
"""

from __future__ import annotations

import httpx

from openbench import anthropic_auth
from openbench.runners.protocols.base import (
    _API_TIMEOUT_S,
    DONE_MARKER,
    Action,
    BaseProtocol,
    ChatFn,
    _post_with_retry,
)
from openbench.runners.protocols.prompts import SYSTEM_PROMPT_TOOLUSE
from openbench.runners.protocols.providers import claude_cost, claude_price
from openbench.runners.protocols.tools import BASH_TOOL

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_MAX_TOKENS = 16000  # output budget per turn (covers adaptive thinking + answer)
# output_config.effort (valid: low|medium|high|xhigh|max). Default `xhigh` — more
# thinking budget than `high` (richer CoT on substantive steps) at lower cost than
# `max`. Thinking is adaptive, so truly trivial steps may still skip; only `max`
# forces a thinking block even on easy steps (at higher token cost).
_EFFORT = "xhigh"
_SKIPPED = "skipped: the harness executes only the first tool call per turn"


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

    def chat(self, messages: list[dict], model: str) -> dict:
        # Refuse an unpriced model BEFORE any request: priced at $0 the cost
        # cap would never fire. Checked on every call (a dict lookup) so an
        # injected chat_fn is held to the same rule.
        claude_price(model)
        return super().chat(messages, model)

    def _make_client(self, model: str) -> httpx.Client:
        # API key, ANTHROPIC_AUTH_TOKEN, or the `ant` CLI login — see anthropic_auth.
        return anthropic_auth.make_client(_API_TIMEOUT_S, purpose=f"for model {model}")

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        body = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "system": SYSTEM_PROMPT_TOOLUSE,
            "messages": messages,
            "tools": [BASH_TOOL],
            # Prompt caching, automatic form (shared/prompt-caching.md, "Automatic
            # vs explicit breakpoints"): the API puts the breakpoint on the last
            # cacheable block and moves it forward each turn, so every request
            # reads the prior conversation from cache and writes only the new
            # tail. It changes no content and no order (system stays the same
            # string, messages are not touched). 5-minute TTL: turns start well
            # under 5 minutes apart. No explicit system breakpoint: system +
            # tool are far below every model's minimum cacheable prefix.
            "cache_control": {"type": "ephemeral"},
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
            n_tool_calls=sum(1 for b in blocks if b.get("type") == "tool_use"),
            # Preserve the raw content blocks (incl. thinking signatures) when
            # passing the assistant turn back — required for thinking+tool-use.
            raw_assistant={"role": "assistant", "content": blocks},
        )

    def usage(self, resp: dict, model: str) -> dict:
        u = resp.get("usage") or {}
        details = u.get("output_tokens_details") or {}
        uncached = int(u.get("input_tokens") or 0)
        written = int(u.get("cache_creation_input_tokens") or 0)
        read = int(u.get("cache_read_input_tokens") or 0)
        return {
            # Same meaning as the OpenAI-style protocols: tokens_in is the whole
            # prompt and tokens_cached the part served from cache (a subset).
            # Anthropic's input_tokens is only the uncached remainder, so add
            # the cache writes and reads back in.
            "tokens_in": uncached + written + read,
            "tokens_out": int(u.get("output_tokens") or 0),
            "tokens_cached": read,
            # Exact thinking-token count; billed within output_tokens (a subset).
            "tokens_thinking": int(details.get("thinking_tokens") or 0),
            # Writes, reads, uncached input and output each at their own rate.
            "cost_usd": claude_cost(u, model),
        }

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        # Every tool_use block needs a matching tool_result or the API 400s the
        # next request. The harness runs only the FIRST command of a turn, so
        # any further tool_use blocks in the same reply (parallel tool use) are
        # answered with the same "skipped" stub the OpenAI tool-use protocol
        # uses (_heal_tool_calls): the one-command-per-turn contract holds, the
        # run does not crash, and the model is told what did not run.
        results = [{
            "type": "tool_result",
            "tool_use_id": action.tool_call_id,
            "content": f"exit_code: {exit_code}\n{output}",
        }]
        for block in (action.raw_assistant or {}).get("content") or []:
            if block.get("type") == "tool_use" and block.get("id") != action.tool_call_id:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": _SKIPPED,
                })
        return {"role": "user", "content": results}

    def nudge(self) -> dict:
        return {"role": "user",
                "content": f"Continue with the bash tool, or run `echo {DONE_MARKER}` if the task is complete."}
