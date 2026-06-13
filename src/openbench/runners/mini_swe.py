"""Minimal shell-loop scaffold for OpenAI-compatible APIs (DeepSeek, etc.).

The counterweight to Claude Code's rich scaffold: one bash command per turn,
no tools, no plan mode. The LLM API is called from the HOST; the task
container runs with network=none, so the agent cannot reach the internet and
the API key never enters the container.

Transcript format (one JSON per line, raw_transcript.jsonl):
  {"type": "meta", "model": ..., "task_id": ...}
  {"type": "api_response", "turn": n, "content": ..., "reasoning_content": ...,
   "usage": {"prompt_tokens": ..., "completion_tokens": ...}}
  {"type": "exec", "turn": n, "command": ..., "exit_code": ..., "output": ...}
  {"type": "final", "exit_reason": ..., "turns": n, "usage_totals": {...}}
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

import httpx

from openbench import dockerutil, paths
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage

DONE_MARKER = "OPENBENCH_DONE"
_OUTPUT_CAP = 5000
_API_TIMEOUT_S = 600
_EXEC_TIMEOUT_S = 600

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

# USD per 1M tokens (prompt, completion) for the cost cap. Approximate —
# update from provider pricing pages; token counts are always recorded exactly.
# Where unsure, prices are set HIGH so the cap errs toward stopping early.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "deepseek-v4-flash": (0.3, 1.2),
    "deepseek-v4-pro": (1.2, 4.8),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-fable-5": (25.0, 100.0),
    "gpt-5.5": (3.0, 15.0),
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
}

SYSTEM_PROMPT = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

Rules:
- Reply with exactly ONE shell command per turn, in a ```bash fenced block. Nothing outside the block is executed.
- The command runs with bash in /repo. You see stdout/stderr (truncated) next turn.
- No internet access. Do not try to fetch anything.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, reply with exactly:
```bash
echo {DONE_MARKER}
```"""


def _resolve_provider(model: str) -> tuple[str, str]:
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


def _default_chat(model: str) -> Callable[[list[dict]], dict]:
    base_url, key, wire_model = _resolve_provider(model)
    client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {key}"},
        timeout=_API_TIMEOUT_S,
    )

    def chat(messages: list[dict]) -> dict:
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = client.post(
                    "/chat/completions", json={"model": wire_model, "messages": messages}
                )
                if resp.status_code in (429, 500, 502, 503):
                    time.sleep(2**attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                last_err = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"chat API failed after retries: {last_err}")

    return chat


def _extract_command(text: str) -> str | None:
    """The model's FIRST proposed command.

    Models routinely hallucinate a whole multi-step trajectory in one reply —
    several ```bash blocks with fabricated outputs between them, sometimes
    ending in a premature DONE. We must execute only the first action and feed
    back the REAL output; taking the last fence would let the model's
    hallucinated continuation (incl. a fake DONE) drive control flow.
    """
    fences = re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", text or "", re.DOTALL)
    for fence in fences:
        if fence.strip():
            return fence.strip()
    return None


def _truncate(text: str, cap: int = _OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    return f"{text[:half]}\n... [{len(text) - cap} chars truncated] ...\n{text[-half:]}"


class MiniSweRunner:
    """name 'mini-swe'. chat_fn is injectable for offline tests."""

    name = "mini-swe"
    needs_network = False  # API is called from the host; container stays offline.

    def __init__(self, chat_fn: Callable[[list[dict]], dict] | None = None) -> None:
        self._chat_fn = chat_fn

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
        chat = self._chat_fn or _default_chat(model)
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))

        usage = zero_usage()
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        exit_reason: ExitReason = "turn_cap"
        started = time.monotonic()

        with transcript.open("w") as log:
            log.write(json.dumps({"type": "meta", "model": model, "task_id": task.task_id}) + "\n")
            for turn in range(1, limits.max_turns + 1):
                if time.monotonic() - started > limits.wall_clock_s:
                    exit_reason = "timeout"
                    break
                # Cost cap BEFORE the next API call: every loop path reaches this
                # (a fence-less reply `continue`s past any check placed later —
                # that path once burned 2.2x the cap; see tests #8).
                if usage["cost_usd"] > limits.max_cost_usd:
                    exit_reason = "cost_cap"
                    break
                try:
                    data = chat(messages)
                except Exception as exc:
                    (run_path / "runner_error.log").write_text(str(exc))
                    exit_reason = "crash"
                    break

                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                u = data.get("usage") or {}
                usage["tokens_in"] += int(u.get("prompt_tokens") or 0)
                usage["tokens_out"] += int(u.get("completion_tokens") or 0)
                details = u.get("completion_tokens_details") or {}
                usage["tokens_thinking"] += int(details.get("reasoning_tokens") or 0)
                usage["num_turns"] = turn
                # Prefer the provider's exact per-call cost (OpenRouter reports
                # usage.cost); fall back to the local price table otherwise.
                if u.get("cost") is not None:
                    usage["cost_usd"] += float(u["cost"])
                else:
                    usage["cost_usd"] += (
                        int(u.get("prompt_tokens") or 0) * price_in
                        + int(u.get("completion_tokens") or 0) * price_out
                    ) / 1e6
                log.write(json.dumps({
                    "type": "api_response",
                    "turn": turn,
                    "content": content,
                    "reasoning_content": reasoning,
                    "usage": {
                        "prompt_tokens": u.get("prompt_tokens", 0),
                        "completion_tokens": u.get("completion_tokens", 0),
                    },
                }) + "\n")
                log.flush()

                messages.append({"role": "assistant", "content": content})
                command = _extract_command(content)
                if command is None:
                    messages.append({
                        "role": "user",
                        "content": "No ```bash block found. Reply with exactly one command in a ```bash fence.",
                    })
                    continue
                if DONE_MARKER in command:
                    log.write(json.dumps({
                        "type": "exec", "turn": turn, "command": command,
                        "exit_code": 0, "output": DONE_MARKER,
                    }) + "\n")
                    exit_reason = "completed"
                    break

                res = dockerutil.exec_in(
                    container, command, timeout=_EXEC_TIMEOUT_S, user="agent"
                )
                output = _truncate((res.stdout or "") + (res.stderr or ""))
                log.write(json.dumps({
                    "type": "exec", "turn": turn, "command": command,
                    "exit_code": res.exit_code, "output": output,
                }) + "\n")
                log.flush()
                messages.append({
                    "role": "user",
                    "content": f"exit_code: {res.exit_code}\n{output}",
                })

            log.write(json.dumps({
                "type": "final", "exit_reason": exit_reason,
                "turns": usage["num_turns"], "usage_totals": usage,
            }) + "\n")

        return exit_reason, usage
