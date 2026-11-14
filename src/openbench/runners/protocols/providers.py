"""Provider routing, pricing, and usage normalization for OpenAI-compatible APIs.

Leaf module: stdlib only, no imports from the rest of the package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

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
    # 1.2/4.8 — see research/corpus/ READMEs).
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (0.435, 0.87),
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


# --- Claude (Anthropic Messages API, claude-native protocol) -----------------
#
# Source: the bundled claude-api skill reference (shared/models.md,
# shared/model-migration.md, shared/prompt-caching.md), read 2026-11-13. Not
# the live pricing page. USD per 1M tokens. Models whose price the reference
# does not state (claude-opus-4-7, claude-opus-4-6, claude-opus-4-5-20251101,
# claude-sonnet-4-5-20250929) are deliberately absent: the claude-native
# protocol refuses an unpriced model rather than billing it at $0.
#
# Cache multipliers (prompt-caching.md "Economics"): 5-minute cache writes
# 1.25x input, 1-hour writes 2x input. Cache reads are per model: 0.025x on
# Fable 5.1/5.2, 0.05x on Opus 5.5 and Sonnet 5.5, 0.1x on every other model
# (model-migration.md, Fable 5.1 pricing bullet).
#
# Minimum cacheable prefix (prompt-caching.md, API reference table): 512 tokens
# on Opus 5.5, Opus 5, Fable 5/5.1/5.2, Sonnet 5.5, Haiku 5.5; 1024 on Opus 4.8,
# Sonnet 5, Sonnet 4.6; 4096 on Haiku 4.5. Shorter prefixes silently do not
# cache (no write charge, no read). Our tool-use system prompt + bash tool is
# far below 512, so caching only kicks in once the task prompt and history
# push the prefix past the minimum.


@dataclass(frozen=True)
class ClaudePrice:
    """One rate card, USD per 1M tokens."""

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    # Long-prompt rate card: applies to the WHOLE request (input, cache and
    # output) when the prompt (input + cache writes + cache reads) is larger
    # than `long_prompt_threshold` tokens.
    long_prompt_threshold: int | None = None
    long_prompt: ClaudePrice | None = None


def _card(inp: float, out: float, read_mult: float) -> ClaudePrice:
    return ClaudePrice(
        input=inp,
        output=out,
        cache_read=round(inp * read_mult, 6),
        cache_write_5m=round(inp * 1.25, 6),
        cache_write_1h=round(inp * 2.0, 6),
    )


CLAUDE_PRICES: dict[str, ClaudePrice] = {
    # models.md:78; model-migration.md:2420 (writes $10 5m / $16 1h, reads $0.20)
    "claude-fable-5-2": _card(8.0, 40.0, 0.025),
    # models.md:80; model-migration.md:1710 (writes $12.50 5m / $20 1h, reads $0.25)
    "claude-fable-5-1": _card(10.0, 50.0, 0.025),
    # models.md:81 (Fable 5.1 per-token price, cache reads $1 = 0.1x)
    "claude-fable-5": _card(10.0, 50.0, 0.1),
    # models.md:83; model-migration.md:2055 (writes $5 5m / $8 1h, reads $0.20)
    "claude-opus-5-5": _card(4.0, 20.0, 0.05),
    # models.md:84; model-migration.md:2471 (reads $0.50)
    "claude-opus-5": _card(5.0, 25.0, 0.1),
    # models.md:84 + model-migration.md:951 ("at Opus 4.8's pricing", $5/$25);
    # models.md:85: 1M context at standard pricing, no long-context premium.
    "claude-opus-4-8": _card(5.0, 25.0, 0.1),
    # Not priced in the bundled reference; taken from the official pricing page
    # (platform.claude.com/docs/en/about-claude/pricing, read 2026-11-13):
    # $5 / $25, writes $6.25 5m / $10 1h, reads $0.50 for each of the three.
    "claude-opus-4-7": _card(5.0, 25.0, 0.1),
    "claude-opus-4-6": _card(5.0, 25.0, 0.1),
    "claude-opus-4-5-20251101": _card(5.0, 25.0, 0.1),
    # Same page: $3 / $15, writes $3.75 5m / $6 1h, reads $0.30.
    "claude-sonnet-4-5-20250929": _card(3.0, 15.0, 0.1),
    # models.md:89; model-migration.md:2103 (writes $2.50 5m / $4 1h, reads $0.10)
    "claude-sonnet-5-5": _card(2.0, 10.0, 0.05),
    # model-migration.md:1238 ($2/$10); reads 0.1x = $0.20 (2103: 5.5's $0.10 is half)
    "claude-sonnet-5": _card(2.0, 10.0, 0.1),
    # model-migration.md:1238 / 1323 ($3/$15). The reference does not say whether
    # a long-context premium applies above some prompt size; none is modeled.
    "claude-sonnet-4-6": _card(3.0, 15.0, 0.1),
    # model-migration.md:2256 ("$1 / $5 at any prompt length")
    "claude-haiku-4-5-20251001": _card(1.0, 5.0, 0.1),
    # models.md:91; model-migration.md:2256: two rate cards by prompt length,
    # $0.10/$0.50 at <=100K prompt tokens, $0.50/$2.50 above; cache reads 0.1x,
    # writes 1.25x (5m) / 2x (1h) of the card's input rate. "100K" is taken as
    # 100,000 (the lower reading, so the higher card kicks in no later).
    "claude-haiku-5-5": replace(
        _card(0.10, 0.50, 0.1),
        long_prompt_threshold=100_000,
        long_prompt=_card(0.50, 2.50, 0.1),
    ),
}

# The dated alias of Haiku 4.5 (models.md:75) bills the same.
CLAUDE_PRICES["claude-haiku-4-5"] = CLAUDE_PRICES["claude-haiku-4-5-20251001"]

# Flat (input, output) view for the OpenAI-compatible path ("claude" prefix in
# PROVIDERS). A tiered model gets its HIGHER card there, since that path cannot
# see the prompt-size split.
for _m, _p in CLAUDE_PRICES.items():
    _top = _p.long_prompt or _p
    PRICES_PER_MTOK[_m] = (_top.input, _top.output)


def claude_price(model: str) -> ClaudePrice:
    """The Claude rate card for `model`, or a RuntimeError naming the file to edit."""
    try:
        return CLAUDE_PRICES[model]
    except KeyError:
        raise RuntimeError(
            f"no price for model {model!r}: add it to CLAUDE_PRICES in "
            "src/openbench/runners/protocols/providers.py (an unpriced model would "
            "bill at $0 and the cost cap would never fire)"
        ) from None


def claude_cost(usage: dict, model: str) -> float:
    """USD for one Messages API response `usage` object.

    `input_tokens` is the uncached remainder only; the prompt is input +
    cache_creation_input_tokens + cache_read_input_tokens (prompt-caching.md,
    Verifying cache hits). Each part bills at its own rate.
    """
    price = claude_price(model)
    tin = int(usage.get("input_tokens") or 0)
    write = int(usage.get("cache_creation_input_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
    tout = int(usage.get("output_tokens") or 0)
    prompt = tin + write + read
    if price.long_prompt is not None and price.long_prompt_threshold is not None:
        if prompt > price.long_prompt_threshold:
            price = price.long_prompt
    # Split writes by TTL when the breakdown is present; otherwise all 5-minute
    # (the only TTL this harness requests).
    breakdown = usage.get("cache_creation") or {}
    write_1h = min(write, int(breakdown.get("ephemeral_1h_input_tokens") or 0))
    write_5m = write - write_1h
    return (
        tin * price.input
        + write_5m * price.cache_write_5m
        + write_1h * price.cache_write_1h
        + read * price.cache_read
        + tout * price.output
    ) / 1e6


def _resolve_provider(model: str) -> tuple[str, str, str]:
    for prefix, (base_url, env) in PROVIDERS.items():
        if model.startswith(prefix):
            key = os.environ.get(env, "")
            if not key and env == "ANTHROPIC_API_KEY":
                # Fall back to ANTHROPIC_AUTH_TOKEN / the `ant` CLI login. Lazy
                # import keeps this module a leaf. The token is fixed for the
                # run here (no refresh), unlike the claude-native protocol.
                from openbench import anthropic_auth

                key = anthropic_auth.bearer_token() or ""
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
