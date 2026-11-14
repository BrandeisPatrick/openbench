"""claude-native pricing: per-model Claude prices, prompt-cache billing, and the
refusal of unpriced models (an unpriced model used to bill at $0, so the cost
cap never fired)."""

from __future__ import annotations

import json

import httpx
import pytest

from openbench.runners.protocols import AnthropicToolUseProtocol
from openbench.runners.protocols.prompts import SYSTEM_PROMPT_TOOLUSE
from openbench.runners.protocols.providers import (
    CLAUDE_PRICES,
    PRICES_PER_MTOK,
    claude_cost,
)

# Every model id the account can call (2026-11-13). Opus 4.5 / 4.6 / 4.7 and
# Sonnet 4.5 are priced from the official pricing page, the rest from the
# bundled reference files.
CALLABLE = [
    "claude-fable-5", "claude-fable-5-1", "claude-fable-5-2",
    "claude-haiku-4-5-20251001", "claude-haiku-5-5",
    "claude-opus-4-5-20251101", "claude-opus-4-6", "claude-opus-4-7",
    "claude-opus-4-8", "claude-opus-5", "claude-opus-5-5",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-6", "claude-sonnet-5", "claude-sonnet-5-5",
]
# Ids with no price entry: they must be refused, never billed at $0.
UNPRICED = ["claude-opus-9", "claude-not-a-model"]


def _resp(usage: dict) -> dict:
    return {"content": [{"type": "text", "text": "hi"}], "usage": usage}


@pytest.mark.parametrize("model", CALLABLE)
def test_every_callable_model_has_a_price(model):
    p = CLAUDE_PRICES[model]
    assert p.input > 0 and p.output > 0
    assert 0 < p.cache_read < p.input < p.cache_write_5m < p.cache_write_1h
    assert p.cache_write_5m == pytest.approx(1.25 * p.input)
    assert model in PRICES_PER_MTOK  # OpenAI-compatible path sees it too


@pytest.mark.parametrize("model", UNPRICED)
def test_unpriced_models_stay_out_of_the_table(model):
    assert model not in CLAUDE_PRICES


def test_cost_prices_write_read_input_output_separately():
    usage = {
        "input_tokens": 1_000,                 # uncached remainder, $4/MTok
        "cache_creation_input_tokens": 2_000,  # 5m write, 1.25x = $5/MTok
        "cache_read_input_tokens": 10_000,     # read, 0.05x = $0.20/MTok
        "output_tokens": 500,                  # $20/MTok
        "output_tokens_details": {"thinking_tokens": 120},
    }
    expected = (1_000 * 4.0 + 2_000 * 5.0 + 10_000 * 0.20 + 500 * 20.0) / 1e6
    u = AnthropicToolUseProtocol().usage(_resp(usage), "claude-opus-5-5")
    assert u["cost_usd"] == pytest.approx(expected)
    # Same meaning as the OpenAI-style protocols: whole prompt, cached subset.
    assert u["tokens_in"] == 13_000
    assert u["tokens_cached"] == 10_000
    assert u["tokens_out"] == 500
    assert u["tokens_thinking"] == 120


def test_one_hour_writes_bill_at_2x():
    usage = {
        "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 3_000,
        "cache_creation": {"ephemeral_5m_input_tokens": 1_000, "ephemeral_1h_input_tokens": 2_000},
    }
    assert claude_cost(usage, "claude-opus-5-5") == pytest.approx(
        (1_000 * 5.0 + 2_000 * 8.0) / 1e6
    )


def test_haiku_5_5_long_prompt_card():
    short = {"input_tokens": 50_000, "cache_read_input_tokens": 50_000,
             "cache_creation_input_tokens": 0, "output_tokens": 1_000}
    assert claude_cost(short, "claude-haiku-5-5") == pytest.approx(
        (50_000 * 0.10 + 50_000 * 0.01 + 1_000 * 0.50) / 1e6
    )
    # One token over 100K of prompt (cached tokens count) -> the whole request,
    # output included, moves to $0.50 / $2.50.
    long = {**short, "cache_read_input_tokens": 50_001}
    assert claude_cost(long, "claude-haiku-5-5") == pytest.approx(
        (50_000 * 0.50 + 50_001 * 0.05 + 1_000 * 2.50) / 1e6
    )


def test_unknown_model_refused_before_any_request():
    calls = []

    def chat_fn(messages):
        calls.append(messages)
        return _resp({"input_tokens": 1, "output_tokens": 1})

    proto = AnthropicToolUseProtocol(chat_fn=chat_fn)
    with pytest.raises(RuntimeError) as exc:
        proto.chat([{"role": "user", "content": "x"}], "claude-opus-9")
    msg = str(exc.value)
    assert "claude-opus-9" in msg
    assert "src/openbench/runners/protocols/providers.py" in msg
    assert calls == []
    with pytest.raises(RuntimeError):
        proto.usage(_resp({"input_tokens": 1, "output_tokens": 1}), "claude-opus-9")


def test_unknown_model_never_builds_a_client(monkeypatch):
    proto = AnthropicToolUseProtocol()
    monkeypatch.setattr(
        proto, "_make_client", lambda model: pytest.fail("client built for unpriced model")
    )
    with pytest.raises(RuntimeError, match="no price"):
        proto.chat([{"role": "user", "content": "x"}], "claude-new-model")


def test_request_enables_caching_without_changing_content():
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=_resp({"input_tokens": 1, "output_tokens": 1}))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    messages = [{"role": "user", "content": "do the task"}]
    before = json.dumps(messages)
    AnthropicToolUseProtocol()._send(client, messages, "claude-haiku-5-5")
    (body,) = sent
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["system"] == SYSTEM_PROMPT_TOOLUSE  # unchanged string
    assert body["messages"] == messages
    assert json.dumps(messages) == before  # history not mutated (no markers)


def test_extra_tool_calls_in_one_reply_are_answered_with_a_stub():
    """Two tool_use blocks in one reply: the first gets the real output, the
    second a 'skipped' stub, so the next request carries a result for every id."""
    proto = AnthropicToolUseProtocol(chat_fn=lambda messages: {})
    resp = {"content": [
        {"type": "thinking", "thinking": "t", "signature": "s"},
        {"type": "tool_use", "id": "a", "name": "bash", "input": {"command": "ls"}},
        {"type": "tool_use", "id": "b", "name": "bash", "input": {"command": "pwd"}},
    ]}
    action = proto.parse_action(resp)
    assert action.command == "ls" and action.tool_call_id == "a"
    msg = proto.result_message(action, "out", 0)
    assert [r["tool_use_id"] for r in msg["content"]] == ["a", "b"]
    assert msg["content"][0]["content"] == "exit_code: 0\nout"
    assert msg["content"][1]["content"].startswith("skipped:")
