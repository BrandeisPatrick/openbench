"""OpenAI tool-use protocol (name 'tooluse'): native function-calling for
OpenAI-compatible providers (DeepSeek/Qwen/GLM/Kimi/OpenAI). Structural stop.
"""

from __future__ import annotations

import json

import httpx

from openbench.runners.protocols.base import (
    DONE_MARKER,
    Action,
    OpenAICompatProtocol,
    _post_with_retry,
)
from openbench.runners.protocols.prompts import SYSTEM_PROMPT_TOOLUSE
from openbench.runners.protocols.providers import _openai_usage
from openbench.runners.protocols.tools import BASH_FUNCTION


class OpenAIToolUseProtocol(OpenAICompatProtocol):
    name = "tooluse"

    def initial_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]

    def meta(self) -> dict:
        return {"scaffold": "tooluse"}

    def build_request(self, model: str, messages: list[dict], system: str) -> dict:
        """Body for `/chat/completions`. tool_choice='auto' (never 'required') so
        voluntary action emission stays measurable — forcing a call would erase
        the out-of-distribution / confabulation signal we want to observe."""
        return {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": [BASH_FUNCTION],
            "tool_choice": "auto",
        }

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        body = self.build_request(self._wire, messages, SYSTEM_PROMPT_TOOLUSE)
        return _post_with_retry(client, "/chat/completions", body)

    def parse_action(self, resp: dict) -> Action:
        """Extract the first tool call's `command`. Prose with no tool call, or a
        tool call whose arguments don't parse / lack a non-empty `command`, is
        ``well_formed=False`` (failed to act in protocol) — never a crash."""
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        text = msg.get("content") or ""
        # DeepSeek returns `reasoning_content`; OpenRouter returns `reasoning` —
        # capture either so CoT is visible for every OpenAI-compatible provider.
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        calls = msg.get("tool_calls") or []
        if not calls:
            return Action(None, text, reasoning, well_formed=False, raw_assistant=msg)
        call = calls[0]
        command: str | None = None
        try:
            args = json.loads((call.get("function") or {}).get("arguments") or "")
            candidate = args.get("command")
            if isinstance(candidate, str) and candidate.strip():
                command = candidate
        except (json.JSONDecodeError, AttributeError, TypeError):
            command = None
        return Action(
            command=command, text=text, reasoning=reasoning,
            well_formed=command is not None,
            tool_call_id=call.get("id"), raw_assistant=msg,
        )

    def usage(self, resp: dict, model: str) -> dict:
        return _openai_usage(resp, model)

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        return {"role": "tool", "tool_call_id": action.tool_call_id,
                "content": f"exit_code: {exit_code}\n{output}"}

    def nudge(self) -> dict:
        return {"role": "user",
                "content": f"Call the bash tool with one command, or run `echo {DONE_MARKER}` if the task is complete."}
