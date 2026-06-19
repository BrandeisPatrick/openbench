"""Wire protocols for the unified harness (see runners/harness.py).

The harness loop (one bash command per turn, sandboxed exec, shared transcript,
cost/wall/turn caps) is fixed; the *protocol* — how an action is requested from
and parsed back out of the model — is pluggable. Four protocols, one loop:

- ``TextFenceProtocol`` (``mini-swe``): /chat/completions, one ```bash fence,
  no tools — the legacy / scaffold-probe baseline.
- ``OpenAIToolUseProtocol`` (``tooluse``): OpenAI-compatible function-calling.
- ``OpenAIResponsesProtocol`` (``gpt-responses``): OpenAI Responses API + reasoning summary.
- ``AnthropicToolUseProtocol`` (``claude-native``): Anthropic Messages + thinking.

All emit the SAME transcript schema so one trace adapter and one metrics pipeline
normalize every protocol unchanged. The LLM API is called from the HOST; the task
container stays network=none.

Layout: base (contract + BaseProtocol/OpenAICompatProtocol + HTTP) · providers
(routing/pricing/usage) · prompts · tools · one module per protocol.
"""

from __future__ import annotations

from openbench.runners.protocols.anthropic import AnthropicToolUseProtocol
from openbench.runners.protocols.base import (
    Action,
    BaseProtocol,
    OpenAICompatProtocol,
    WireProtocol,
)
from openbench.runners.protocols.openai_responses import OpenAIResponsesProtocol
from openbench.runners.protocols.openai_tooluse import OpenAIToolUseProtocol
from openbench.runners.protocols.text_fence import TextFenceProtocol, _extract_command
from openbench.runners.protocols.tools import (
    BASH_FUNCTION,
    BASH_FUNCTION_RESPONSES,
    BASH_TOOL,
)

__all__ = [
    "Action",
    "WireProtocol",
    "BaseProtocol",
    "OpenAICompatProtocol",
    "TextFenceProtocol",
    "OpenAIToolUseProtocol",
    "OpenAIResponsesProtocol",
    "AnthropicToolUseProtocol",
    "BASH_FUNCTION",
    "BASH_TOOL",
    "BASH_FUNCTION_RESPONSES",
    "_extract_command",
]
