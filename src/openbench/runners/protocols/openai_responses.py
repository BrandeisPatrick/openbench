"""OpenAI Responses protocol (name 'gpt-responses'): OpenAI Responses API with
reasoning summaries.

GPT's /chat/completions path returns NO reasoning text; the Responses API does
(``reasoning.summary``) — the only way to get GPT CoT into the transcript.
Reasoning context is carried server-side via ``previous_response_id``, so each
turn after the first sends only the new function result. The Harness still
appends to ``messages`` and we read ``messages[-1]`` as that delta; the appended
assistant marker isn't resent (state lives server-side).
"""

from __future__ import annotations

import json

import httpx

from openbench.runners.protocols.base import (
    DONE_MARKER,
    Action,
    ChatFn,
    OpenAICompatProtocol,
    _post_with_retry,
)
from openbench.runners.protocols.prompts import SYSTEM_PROMPT_TOOLUSE
from openbench.runners.protocols.providers import PRICES_PER_MTOK
from openbench.runners.protocols.tools import BASH_FUNCTION_RESPONSES


class OpenAIResponsesProtocol(OpenAICompatProtocol):
    name = "gpt-responses"

    def __init__(self, chat_fn: ChatFn | None = None, summary: str = "auto") -> None:
        super().__init__(chat_fn)
        self._summary = summary
        self._prev_id: str | None = None
        # A function_call whose arguments failed to parse still awaits its
        # function_call_output — a plain nudge next turn makes the API 400
        # ("No tool output found for function call ...").
        self._pending_call_id: str | None = None

    def initial_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]

    def meta(self) -> dict:
        return {"scaffold": "gpt-responses", "reasoning_summary": self._summary}

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        body = {
            "model": self._wire,
            "tools": [BASH_FUNCTION_RESPONSES],
            "tool_choice": "auto",
            "instructions": SYSTEM_PROMPT_TOOLUSE,
            "store": True,
        }
        # Non-reasoning models (gpt-4.1, gpt-4o, ...) reject the `reasoning`
        # body param outright; only send it where a reasoning channel exists.
        if not self._wire.startswith("gpt-4"):
            body["reasoning"] = {"summary": self._summary}
        if self._prev_id is None:
            body["input"] = messages           # first turn: seed user message(s)
        else:
            body["input"] = [messages[-1]]     # only the new function result / nudge
            body["previous_response_id"] = self._prev_id
        resp = _post_with_retry(client, "/responses", body)
        self._prev_id = resp.get("id") or self._prev_id
        return resp

    def parse_action(self, resp: dict) -> Action:
        text_parts: list[str] = []
        summary_parts: list[str] = []
        command: str | None = None
        call_id: str | None = None
        for item in resp.get("output") or []:
            itype = item.get("type")
            if itype == "reasoning":
                for s in item.get("summary") or []:
                    summary_parts.append(s.get("text") or "")
            elif itype == "function_call" and call_id is None:
                call_id = item.get("call_id")
                try:
                    args = json.loads(item.get("arguments") or "")
                    cand = args.get("command")
                    if isinstance(cand, str) and cand.strip():
                        command = cand
                except (json.JSONDecodeError, AttributeError, TypeError):
                    command = None
            elif itype == "message":
                for c in item.get("content") or []:
                    if c.get("type") == "output_text":
                        text_parts.append(c.get("text") or "")
        self._pending_call_id = call_id if command is None and call_id else None
        return Action(
            command=command, text="\n".join(text_parts), reasoning="\n".join(summary_parts),
            well_formed=command is not None, tool_call_id=call_id,
            raw_assistant={"role": "assistant", "content": "\n".join(text_parts)},
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
            "tokens_thinking": int(details.get("reasoning_tokens") or 0),
            "cost_usd": (tin * price_in + tout * price_out) / 1e6,
        }

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        return {
            "type": "function_call_output",
            "call_id": action.tool_call_id,
            "output": f"exit_code: {exit_code}\n{output}",
        }

    def nudge(self) -> dict:
        if self._pending_call_id is not None:
            cid, self._pending_call_id = self._pending_call_id, None
            return {
                "type": "function_call_output",
                "call_id": cid,
                "output": 'error: arguments were not valid JSON with a "command" string; '
                          f"call the bash tool again, or run `echo {DONE_MARKER}` if done.",
            }
        return {"role": "user",
                "content": f"Call the bash tool with one command, or run `echo {DONE_MARKER}` if the task is complete."}
