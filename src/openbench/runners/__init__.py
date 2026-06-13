"""Agent harness adapters: claude-code, mini-swe, plus CI fixtures."""

from __future__ import annotations

from openbench.runners.base import AgentRunner


def get_runner(name: str) -> AgentRunner:
    from openbench.runners.claude_code import ClaudeCodeRunner
    from openbench.runners.claude_native import ClaudeNativeRunner
    from openbench.runners.fixtures import GoldenRunner, NullRunner
    from openbench.runners.mini_swe import MiniSweRunner

    registry: dict[str, type] = {
        "claude-code": ClaudeCodeRunner,
        "claude-native": ClaudeNativeRunner,
        "mini-swe": MiniSweRunner,
        "golden": GoldenRunner,
        "null": NullRunner,
    }
    try:
        return registry[name]()
    except KeyError:
        raise ValueError(f"unknown runner {name!r}; expected one of {sorted(registry)}") from None
