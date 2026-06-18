"""The single bash tool, rendered into each provider's wire format.

One command per turn, identical semantics everywhere — only the JSON shape differs:
chat-completions nests under "function"; Anthropic uses "input_schema"; the
Responses API uses a flat "function" with name/parameters at the top level.
"""

from __future__ import annotations

_BASH_NAME = "bash"
_BASH_DESCRIPTION = (
    "Run one bash command in /repo (current directory) and get its "
    "stdout/stderr. No internet access. Use heredocs to edit files."
)
_BASH_PARAMETERS = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "the command"}},
    "required": ["command"],
}

# OpenAI chat-completions function tool (nested under "function").
BASH_FUNCTION = {
    "type": "function",
    "function": {
        "name": _BASH_NAME,
        "description": _BASH_DESCRIPTION,
        "parameters": _BASH_PARAMETERS,
    },
}

# Anthropic Messages-API tool ("input_schema").
BASH_TOOL = {
    "name": _BASH_NAME,
    "description": _BASH_DESCRIPTION,
    "input_schema": _BASH_PARAMETERS,
}

# OpenAI Responses-API function tool (flat: name/parameters at top level).
BASH_FUNCTION_RESPONSES = {
    "type": "function",
    "name": _BASH_NAME,
    "description": _BASH_DESCRIPTION,
    "parameters": _BASH_PARAMETERS,
}
