"""Shared transport + constants for the OpenAI-compatible runners.

Provider routing, pricing, output truncation, the DONE marker, the retry/usage
boilerplate, and the native-tool-use system prompt live here so every runner
depends on this neutral module — not on each other. (Previously the modern
`tooluse`/`claude_native` runners imported these from the legacy `mini_swe`,
making the deprecated text-fence runner a dependency of the current ones.)
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

DONE_MARKER = "OPENBENCH_DONE"
OUTPUT_CAP = 5000
API_TIMEOUT_S = 600
EXEC_TIMEOUT_S = 600

# Native-tool-use system prompt — shared by every native runner (claude_native,
# tooluse) so the common harness reads identically across providers. The model
# acts through a single `bash` tool, one command per turn.
NATIVE_SYSTEM_PROMPT = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

Use the `bash` tool to act — one command per call. You see its stdout/stderr in the result.

Rules:
- No internet access. Do not try to fetch anything.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, call bash with exactly: echo {DONE_MARKER}"""

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


def resolve_provider(model: str) -> tuple[str, str, str]:
    """(base_url, api_key, wire_model) for an OpenAI-compatible model id."""
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


def truncate(text: str, cap: int = OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    return f"{text[:half]}\n... [{len(text) - cap} chars truncated] ...\n{text[-half:]}"


def request_with_retries(client: httpx.Client, body: dict) -> dict:
    """POST a chat-completions body with backoff on 429/5xx; return parsed JSON."""
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.post("/chat/completions", json=body)
            if resp.status_code in (429, 500, 502, 503):
                time.sleep(2**attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            last_err = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"chat API failed after retries: {last_err}")


def accumulate_openai_usage(
    usage: dict, u: dict[str, Any] | None, price_in: float, price_out: float
) -> None:
    """Fold one OpenAI-format `usage` payload into the run's running totals.

    Prefers the provider's exact per-call cost (OpenRouter reports usage.cost);
    falls back to the local price table otherwise. Does not touch num_turns
    (that's loop state). Mutates `usage` in place.
    """
    u = u or {}
    pt = int(u.get("prompt_tokens") or 0)
    ct = int(u.get("completion_tokens") or 0)
    usage["tokens_in"] += pt
    usage["tokens_out"] += ct
    usage["tokens_thinking"] += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    if u.get("cost") is not None:
        usage["cost_usd"] += float(u["cost"])
    else:
        usage["cost_usd"] += (pt * price_in + ct * price_out) / 1e6
