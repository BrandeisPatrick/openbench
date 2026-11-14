"""Agent harnesses: one loop (Harness) + pluggable protocols, plus CI fixtures.

One ``Harness`` loop (harness.py); the `native` router (resolve_runner) sends each
model to its CoT-exposing protocol (protocols.py): `claude-native` (Anthropic
Messages, thinking), `gpt-responses` (OpenAI Responses, reasoning summary),
`tooluse` (OpenAI-compatible reasoning_content). `mini-swe` is the text-fence
scaffold probe. `golden` / `null` are grade-pipeline fixtures.
"""

from __future__ import annotations

from openbench.runners.base import AgentRunner


def resolve_runner(name: str, model: str) -> str:
    """Resolve the ``native`` selector to each model's CoT-exposing protocol.

    One harness, one router: ``native`` routes every model to the protocol that
    makes its reasoning visible, so chain-of-thought is captured for ALL models
    (logged uniformly into the transcript's ``reasoning_content``):
    - ``claude*``  -> ``claude-native``  (Anthropic Messages, summarized thinking)
    - ``gpt*`` / o-series (``o1*``, ``o3*``) -> ``gpt-responses``  (OpenAI Responses
                       API, reasoning.summary; the /chat/completions path hides GPT
                       CoT entirely. o1 predates summaries — it accepts the param but
                       returns no summary text, so its arm is CoT-less like gpt-4.1)
    - everything else (deepseek / qwen / glm / kimi / openrouter) -> ``tooluse``
                       (captures ``reasoning_content`` / ``reasoning``).
    ``mini-swe`` (text-fence scaffold probe) stays available by explicit name. The
    Opus gate (2026-06-18) confirmed Claude does not dream on tool-use, so this
    routing is about CoT visibility, not confab avoidance. Any other name passes
    through unchanged.
    """
    if name == "native":
        if model.startswith("claude"):
            return "claude-native"
        if model.startswith(("gpt", "o1", "o3")):
            return "gpt-responses"
        return "tooluse"
    return name


# Sentinel: "effort not given" (None is a real value: no extended thinking).
_DEFAULT_EFFORT = object()


def get_runner(name: str, effort: object = _DEFAULT_EFFORT) -> AgentRunner:
    """Build a runner by name. ``effort`` (claude-native only) overrides the
    protocol's default thinking effort; None sends no thinking params at all.
    Omitted, every runner is built exactly as before."""
    from openbench.runners.fixtures import GoldenRunner, NullRunner
    from openbench.runners.harness import Harness
    from openbench.runners.protocols import (
        AnthropicToolUseProtocol,
        OpenAIResponsesProtocol,
        OpenAIToolUseProtocol,
        TextFenceProtocol,
    )

    if effort is not _DEFAULT_EFFORT and name != "claude-native":
        raise ValueError(f"runner {name!r} takes no effort setting (only claude-native does)")
    if name in ("mini-swe", "text-fence"):
        return Harness(TextFenceProtocol())
    if name == "tooluse":
        return Harness(OpenAIToolUseProtocol())
    if name == "gpt-responses":
        return Harness(OpenAIResponsesProtocol())
    if name == "claude-native":
        if effort is _DEFAULT_EFFORT:
            return Harness(AnthropicToolUseProtocol())
        return Harness(AnthropicToolUseProtocol(effort=effort))  # type: ignore[arg-type]
    if name == "golden":
        return GoldenRunner()
    if name == "null":
        return NullRunner()
    raise ValueError(
        f"unknown runner {name!r}; expected one of "
        "['claude-native', 'golden', 'gpt-responses', 'mini-swe', 'null', 'tooluse'] "
        "(or 'native' to route each model to its CoT-exposing protocol)"
    )
