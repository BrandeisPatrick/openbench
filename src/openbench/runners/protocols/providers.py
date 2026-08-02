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
    # OpenAI o-series (thinking lineage: o1, o3, o3-mini, ...).
    "o1": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "o3": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "kimi": ("https://api.moonshot.ai/v1", "MOONSHOT_API_KEY"),
    # Anthropic's OpenAI-compatible chat endpoint (Bearer auth works there).
    "claude": ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
}

# USD per 1M tokens (prompt, completion) for the cost cap. Approximate — token
# counts are always recorded exactly; where unsure, prices are set HIGH so the
# cap errs toward stopping early.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # Verified against published provider pricing 2026-08-02. Historical runs
    # keep the cost_usd computed at run time; recompute from token counts if a
    # price was wrong then (July runs priced gpt-5.5 at 3/15 and v4-pro at
    # 1.2/4.8 — see data/ freeze READMEs).
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-fable-5": (25.0, 100.0),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
    "o1": (15.0, 60.0),
    "o3": (2.0, 8.0),
    # Moonshot first-party (no usage.cost in responses — table must be right).
    "kimi-k2.6": (0.95, 4.0),
    "kimi-k3": (3.0, 15.0),
}

# Cache-hit input price where the provider discounts cached prefix tokens and
# the rate is verified (2026-08-02). Absent → cached tokens bill at full input
# price, which keeps the old conservative behavior for unknown models.
PRICES_CACHED_PER_MTOK: dict[str, float] = {
    "gpt-5.5": 0.50,
    "deepseek-v4-flash": 0.0028,
    "deepseek-v4-pro": 0.003625,
    "kimi-k3": 0.30,
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
    # Cached prefix tokens, in every dialect seen in the wild: OpenAI nests
    # them under prompt_tokens_details, DeepSeek reports prompt_cache_hit_tokens
    # at top level, Moonshot reports cached_tokens at top level.
    in_details = u.get("prompt_tokens_details") or {}
    cached = min(
        tin,
        int(
            u.get("prompt_cache_hit_tokens")
            or u.get("cached_tokens")
            or in_details.get("cached_tokens")
            or 0
        ),
    )
    # Prefer the provider's exact per-call cost (OpenRouter reports usage.cost);
    # fall back to the local price table otherwise. July 2026 kimi-k3 runs were
    # cost_cap-killed on this fallback billing all input at full price.
    if u.get("cost") is not None:
        cost = float(u["cost"])
    else:
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))
        price_cached = PRICES_CACHED_PER_MTOK.get(model, price_in)
        cost = (
            (tin - cached) * price_in + cached * price_cached + tout * price_out
        ) / 1e6
    return {
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_cached": cached,
        "tokens_thinking": int(details.get("reasoning_tokens") or 0),
        "cost_usd": cost,
    }
