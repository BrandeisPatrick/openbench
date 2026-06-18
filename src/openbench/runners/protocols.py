"""Wire protocols for the unified harness (see runners/harness.py).

The harness loop (one bash command per turn, sandboxed exec, shared transcript,
cost/wall/turn caps) is fixed; the *protocol* — how an action is requested from
and parsed back out of the model — is pluggable. Three protocols, one loop:

- ``TextFenceProtocol`` (name ``mini-swe``): OpenAI ``/chat/completions``, one
  ```bash fence per turn, NO tools. Out-of-distribution for tool-trained models
  (they "dream" a whole session), so it carries a few-shot anti-confabulation
  prompt + a reactive correction. Kept as the legacy / scaffold-probe baseline.
- ``OpenAIToolUseProtocol`` (name ``tooluse``): native function-calling for
  OpenAI-compatible providers (DeepSeek/Qwen/GLM/Kimi/OpenAI). Structural stop.
- ``AnthropicToolUseProtocol`` (name ``claude-native``): Anthropic Messages API
  with a real ``bash`` tool + extended thinking. Structural stop + native format.

All three emit the SAME transcript schema (meta / api_response / exec / final) so
one trace adapter and one metrics pipeline normalize every protocol unchanged.
The LLM API is called from the HOST; the task container stays network=none.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

import httpx

from openbench.runners.harness import _API_TIMEOUT_S, DONE_MARKER

# --- providers & pricing (OpenAI-compatible) ---------------------------------

# model-name prefix -> (base_url, api-key env var). Longest prefix wins, so
# "openrouter/" routes through OpenRouter even for deepseek-* slugs.
PROVIDERS: dict[str, tuple[str, str]] = {
    "openrouter/": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "gpt": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "kimi": ("https://api.moonshot.ai/v1", "MOONSHOT_API_KEY"),
    # Anthropic's OpenAI-compatible chat endpoint (Bearer auth works there).
    "claude": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
}

# USD per 1M tokens (prompt, completion) for the cost cap. Approximate — token
# counts are always recorded exactly; where unsure, prices are set HIGH so the
# cap errs toward stopping early.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.3, 1.2),
    "deepseek-v4-pro": (1.2, 4.8),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-fable-5": (25.0, 100.0),
    "gpt-5.5": (3.0, 15.0),
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
}


def _resolve_provider(model: str) -> tuple[str, str, str]:
    for prefix, (base_url, env) in PROVIDERS.items():
        if model.startswith(prefix):
            key = os.environ.get(env, "")
            if not key:
                raise RuntimeError(f"{env} is not set (required for model {model})")
            # Strip a trailing-slash routing prefix (e.g. "openrouter/"); the
            # remainder is the provider's own model id (e.g. deepseek/deepseek-chat).
            wire_model = model[len(prefix):] if prefix.endswith("/") else model
            return base_url, key, wire_model
    raise RuntimeError(f"no provider configured for model {model}")


def _post_with_retry(client: httpx.Client, url: str, body: dict) -> dict:
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.post(url, json=body)
            if resp.status_code in (429, 500, 502, 503, 529):
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_err = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"API failed after retries: {last_err}")


def _openai_usage(resp: dict, model: str) -> dict:
    """Normalize OpenAI-compatible usage to the harness's canonical shape."""
    u = resp.get("usage") or {}
    details = u.get("completion_tokens_details") or {}
    tin = int(u.get("prompt_tokens") or 0)
    tout = int(u.get("completion_tokens") or 0)
    # Prefer the provider's exact per-call cost (OpenRouter reports usage.cost);
    # fall back to the local price table otherwise.
    if u.get("cost") is not None:
        cost = float(u["cost"])
    else:
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))
        cost = (tin * price_in + tout * price_out) / 1e6
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_thinking": int(details.get("reasoning_tokens") or 0),
        "cost_usd": cost,
    }


# --- system prompts ----------------------------------------------------------

# Few-shot anti-confabulation prompt for the text-fence protocol. A measured
# prompt-A/B (Opus) showed this SHOW-don't-tell form roughly halves the
# multi-step "dreaming" (over-generation) vs an instruction-only prompt, by
# demonstrating the one-command-then-stop pattern and an explicit WRONG example
# of fabricated output. It does not fully eliminate it (the format prior is
# deep); the reactive _CORRECTION below catches the residual.
SYSTEM_PROMPT_TEXTFENCE = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

CRITICAL FORMAT RULE: every reply is EXACTLY one ```bash block, then you STOP. You never write a second block, never write a line starting with "system", and never write what you think the output will be. The ENVIRONMENT produces output, not you. Any output you write is a hallucination — it is discarded and you are corrected.

CORRECT (do this) — one command, then nothing, then you wait:
```bash
grep -n "def foo" src/app.py
```

WRONG (never do this) — fabricating the result and continuing:
```bash
grep -n "def foo" src/app.py
```
system```
42:def foo(...):   <-- FABRICATED, forbidden
```

Other rules:
- The command runs with bash in /repo. No internet access.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, reply with exactly:
```bash
echo {DONE_MARKER}
```"""

# Shared tool-use prompt (Anthropic + OpenAI function-calling). The structural
# stop makes the fence-format rules unnecessary.
SYSTEM_PROMPT_TOOLUSE = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

Use the `bash` tool to act — one command per call. You see its stdout/stderr in the result.

Rules:
- No internet access. Do not try to fetch anything.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, call bash with exactly: echo {DONE_MARKER}"""

# Reactive anti-confabulation correction (text-fence only): some models emit a
# whole imagined session in one reply — multiple commands plus fabricated
# outputs — then form a false belief they finished. We execute only the first
# real command; this note confronts the model with reality so the dream doesn't
# drive control flow.
_CORRECTION = (
    "NOTE: your previous reply contained more than one command and/or made-up "
    "output. Only your FIRST command was actually run. Everything you wrote after "
    "it (including any predicted output or a premature done) is NOT real — ignore "
    "it. The REAL output of your first command is below. Reply with exactly ONE "
    "command next, and never predict outputs.\n\n"
)


def _overgenerated(content: str) -> bool:
    """The model emitted more than one fenced block — it kept generating past the
    first command (a dreamed continuation) instead of stopping. One command = one
    ```...``` block = two fence markers."""
    return (content or "").count("```") > 2


def _extract_command(text: str) -> str | None:
    """The model's FIRST proposed command.

    Models routinely hallucinate a whole multi-step trajectory in one reply —
    several ```bash blocks with fabricated outputs between them, sometimes ending
    in a premature DONE. We execute only the first action and feed back the REAL
    output; taking the last fence would let the hallucinated continuation (incl. a
    fake DONE) drive control flow.
    """
    fences = re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", text or "", re.DOTALL)
    for fence in fences:
        if fence.strip():
            return fence.strip()
    return None


# --- tool surfaces -----------------------------------------------------------

# OpenAI function-calling tool, identical in semantics to the text-fence command
# and the Anthropic BASH_TOOL: one bash command per turn.
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

# Anthropic Messages-API tool.
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


@dataclass
class Action:
    """One parsed model action.

    ``well_formed`` is the protocol-compliance signal: did the model emit a usable
    action in the expected format? A low rate across a run is the out-of-
    distribution signature (confabulation when a tool-use model is forced through
    a foreign protocol). ``raw_assistant`` is the assistant turn appended verbatim
    next turn (string for text-fence, content blocks for Anthropic, tool_calls
    message for OpenAI).
    """

    command: str | None
    text: str
    reasoning: str
    well_formed: bool
    tool_call_id: str | None = None
    raw_assistant: dict | None = None


# --- protocols ---------------------------------------------------------------

class TextFenceProtocol:
    """name 'mini-swe'. OpenAI /chat/completions, one ```bash fence per turn."""

    name = "mini-swe"
    needs_network = False

    def __init__(self, chat_fn=None) -> None:
        self._chat_fn = chat_fn
        self._client = None

    def initial_messages(self, prompt: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT_TEXTFENCE},
            {"role": "user", "content": prompt},
        ]

    def meta(self) -> dict:
        return {}

    def chat(self, messages: list[dict], model: str) -> dict:
        if self._chat_fn is not None:
            return self._chat_fn(messages)
        if self._client is None:
            base_url, key, wire = _resolve_provider(model)
            self._wire = wire
            self._client = httpx.Client(
                base_url=base_url, headers={"Authorization": f"Bearer {key}"}, timeout=_API_TIMEOUT_S
            )
        return _post_with_retry(self._client, "/chat/completions",
                                {"model": self._wire, "messages": messages})

    def parse_action(self, resp: dict) -> Action:
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        command = _extract_command(content)
        return Action(
            command=command, text=content, reasoning=reasoning,
            well_formed=command is not None,
            raw_assistant={"role": "assistant", "content": content},
        )

    def usage(self, resp: dict, model: str) -> dict:
        return _openai_usage(resp, model)

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        # If the model dreamed a multi-step session, prepend a correction so the
        # fabricated continuation can't drive the next turn.
        prefix = _CORRECTION if _overgenerated(action.text) else ""
        return {"role": "user", "content": f"{prefix}exit_code: {exit_code}\n{output}"}

    def nudge(self) -> dict:
        return {"role": "user",
                "content": "No ```bash block found. Reply with exactly one command in a ```bash fence."}


class OpenAIToolUseProtocol:
    """name 'tooluse'. Native function-calling for OpenAI-compatible providers."""

    name = "tooluse"
    needs_network = False

    def __init__(self, chat_fn=None) -> None:
        self._chat_fn = chat_fn
        self._client = None

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

    def chat(self, messages: list[dict], model: str) -> dict:
        if self._chat_fn is not None:
            return self._chat_fn(messages)
        if self._client is None:
            base_url, key, wire = _resolve_provider(model)
            self._wire = wire
            self._client = httpx.Client(
                base_url=base_url, headers={"Authorization": f"Bearer {key}"}, timeout=_API_TIMEOUT_S
            )
        body = self.build_request(self._wire, messages, SYSTEM_PROMPT_TOOLUSE)
        return _post_with_retry(self._client, "/chat/completions", body)

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


class AnthropicToolUseProtocol:
    """name 'claude-native'. Anthropic Messages API, native tool_use + thinking."""

    name = "claude-native"
    needs_network = False

    def __init__(self, chat_fn=None, effort: str | None = _EFFORT) -> None:
        self._chat_fn = chat_fn
        self._effort = effort  # None => no extended thinking (factorial control)
        self._client = None

    def initial_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]

    def meta(self) -> dict:
        return {"scaffold": "claude-native", "thinking_effort": self._effort}

    def chat(self, messages: list[dict], model: str) -> dict:
        if self._chat_fn is not None:
            return self._chat_fn(messages)
        if self._client is None:
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise RuntimeError(f"ANTHROPIC_API_KEY is not set (required for model {model})")
            self._client = httpx.Client(
                headers={
                    "x-api-key": key,
                    "anthropic-version": _ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                timeout=_API_TIMEOUT_S,
            )
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
        return _post_with_retry(self._client, _ANTHROPIC_URL, body)

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


# OpenAI Responses-API function tool — flat shape (name/parameters at top level),
# unlike the chat-completions BASH_FUNCTION (nested under "function").
BASH_FUNCTION_RESPONSES = {
    "type": "function",
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
}


class OpenAIResponsesProtocol:
    """name 'gpt-responses'. OpenAI Responses API with reasoning summaries.

    GPT's /chat/completions path returns NO reasoning text; the Responses API does
    (``reasoning.summary``) — the only way to get GPT CoT into the transcript.
    Reasoning context is carried server-side via ``previous_response_id``, so each
    turn after the first sends only the new function result. The Harness still
    appends to ``messages`` and we read ``messages[-1]`` as that delta; the
    appended assistant marker isn't resent (state lives server-side).
    """

    name = "gpt-responses"
    needs_network = False

    def __init__(self, chat_fn=None, summary: str = "auto") -> None:
        self._chat_fn = chat_fn
        self._summary = summary
        self._client = None
        self._prev_id: str | None = None

    def initial_messages(self, prompt: str) -> list[dict]:
        return [{"role": "user", "content": prompt}]

    def meta(self) -> dict:
        return {"scaffold": "gpt-responses", "reasoning_summary": self._summary}

    def chat(self, messages: list[dict], model: str) -> dict:
        if self._chat_fn is not None:
            return self._chat_fn(messages)
        if self._client is None:
            base_url, key, wire = _resolve_provider(model)
            self._wire = wire
            self._client = httpx.Client(
                base_url=base_url, headers={"Authorization": f"Bearer {key}"}, timeout=_API_TIMEOUT_S
            )
        body = {
            "model": self._wire,
            "tools": [BASH_FUNCTION_RESPONSES],
            "tool_choice": "auto",
            "instructions": SYSTEM_PROMPT_TOOLUSE,
            "reasoning": {"summary": self._summary},
            "store": True,
        }
        if self._prev_id is None:
            body["input"] = messages           # first turn: seed user message(s)
        else:
            body["input"] = [messages[-1]]     # only the new function result / nudge
            body["previous_response_id"] = self._prev_id
        resp = _post_with_retry(self._client, "/responses", body)
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
        return {"role": "user",
                "content": f"Call the bash tool with one command, or run `echo {DONE_MARKER}` if the task is complete."}
