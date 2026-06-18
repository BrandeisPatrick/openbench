"""Provider routing, pricing, and usage normalization for OpenAI-compatible APIs.

Leaf module: stdlib only, no imports from the rest of the package.
"""

from __future__ import annotations

import os

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
