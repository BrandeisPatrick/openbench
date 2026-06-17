"""Protocol adapters for the meta-harness.

The harness loop (one bash command per turn, sandboxed exec, shared transcript)
is fixed; the *protocol* — how an action is requested from and parsed back out of
the model — is pluggable. This is the design every serious agent benchmark
converged on: a neutral bash-only baseline plus the model's own in-distribution
tool format, reported as (model × harness) cells.

This module adds the **`tooluse`** protocol for OpenAI-compatible providers
(DeepSeek, Qwen, GLM, Kimi, OpenAI) via native function-calling — the
in-distribution arm. The text-fence baseline lives in ``mini_swe`` and the
Anthropic ``tool_use`` arm in ``claude_native``; both already share the
transcript schema, so this adapter slots into the same downstream pipeline.

Pure/stdlib (json only): request building and response parsing are side-effect
free, so the wire format is unit-testable offline with canned responses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# The single tool, identical in semantics to mini-swe's text-fence command and
# claude-native's BASH_TOOL: one bash command per turn.
BASH_FUNCTION = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run one bash command in /repo (current directory) and get its "
            "stdout/stderr. No internet access. Use heredocs to edit files."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "the command"}},
            "required": ["command"],
        },
    },
}


@dataclass
class Action:
    """One parsed model action.

    ``well_formed`` is the Aider-style protocol-compliance signal: did the model
    emit a usable action in the expected format? A low rate across a run is the
    out-of-distribution signature (the thing that shows up as confabulation when
    a tool-use model is forced through a foreign protocol).
    """

    command: str | None
    text: str
    reasoning: str
    well_formed: bool
    tool_call_id: str | None = None
    raw_assistant: dict | None = None  # assistant message to append verbatim next turn


class OpenAIToolUseProtocol:
    """Native function-calling for OpenAI-compatible `/chat/completions` providers."""

    name = "tooluse"

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

    def parse_action(self, resp: dict) -> Action:
        """Extract the first tool call's `command` from a chat-completions response.

        Prose with no tool call, or a tool call whose arguments don't parse / lack
        a non-empty `command`, is ``well_formed=False`` (the model failed to act in
        protocol) — never a crash.
        """
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        text = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
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
            command=command,
            text=text,
            reasoning=reasoning,
            well_formed=command is not None,
            tool_call_id=call.get("id"),
            raw_assistant=msg,
        )

    def observation(self, action: Action, output: str) -> list[dict]:
        """Messages to append after executing the command: the assistant turn that
        carried the tool call (verbatim, so tool_call ids match) then the tool
        result keyed by that id."""
        return [
            action.raw_assistant,
            {"role": "tool", "tool_call_id": action.tool_call_id, "content": output},
        ]
