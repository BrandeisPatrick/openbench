"""Agent harness adapters.

Common harness: ``native`` (minimal native tool-use, dispatched per provider to
``tooluse`` for OpenAI-compatible models and ``claude-native`` for Anthropic).
``mini-swe`` is the legacy text-fence baseline; ``claude-code`` and the golden/null
CI fixtures round out the registry.
"""

from __future__ import annotations

from openbench.runners.base import AgentRunner


def get_runner(name: str) -> AgentRunner:
    from openbench.runners.claude_code import ClaudeCodeRunner
    from openbench.runners.claude_native import ClaudeNativeRunner
    from openbench.runners.fixtures import GoldenRunner, NullRunner
    from openbench.runners.mini_swe import MiniSweRunner
    from openbench.runners.tooluse import NativeRunner, ToolUseRunner

    registry: dict[str, type] = {
        "native": NativeRunner,  # common harness: native tool-use, dispatched per provider
        "tooluse": ToolUseRunner,  # OpenAI-compat function-calling arm
        "claude-code": ClaudeCodeRunner,
        "claude-native": ClaudeNativeRunner,
        "mini-swe": MiniSweRunner,  # legacy text-fence baseline
        "golden": GoldenRunner,
        "null": NullRunner,
    }
    try:
        return registry[name]()
    except KeyError:
        raise ValueError(f"unknown runner {name!r}; expected one of {sorted(registry)}") from None
