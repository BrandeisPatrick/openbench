"""Text-fence protocol (name 'mini-swe'): OpenAI /chat/completions, one ```bash
fence per turn, NO tools. Out-of-distribution for tool-trained models (they
"dream" a whole session), so it carries the few-shot anti-confab prompt + a
reactive correction. Kept as the legacy / scaffold-probe baseline.
"""

from __future__ import annotations

import re

import httpx

from openbench.runners.protocols.base import Action, OpenAICompatProtocol, _post_with_retry
from openbench.runners.protocols.prompts import _CORRECTION, SYSTEM_PROMPT_TEXTFENCE
from openbench.runners.protocols.providers import _openai_usage


def _overgenerated(content: str) -> bool:
    """The model emitted more than one fenced block — it kept generating past the
    first command (a dreamed continuation) instead of stopping. One command = one
    ```...``` block = two fence markers."""
    return (content or "").count("```") > 2


def _extract_command(text: str) -> str | None:
    """The model's FIRST proposed command.

    Models routinely hallucinate a whole multi-step trajectory in one reply —
    several ```bash blocks with fabricated outputs between them, sometimes ending
    in a premature DONE. We execute only the first action and feed back the REAL
    output; taking the last fence would let the hallucinated continuation (incl. a
    fake DONE) drive control flow.
    """
    fences = re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", text or "", re.DOTALL)
    for fence in fences:
        if fence.strip():
            return fence.strip()
    return None


class TextFenceProtocol(OpenAICompatProtocol):
    name = "mini-swe"

    def initial_messages(self, prompt: str) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT_TEXTFENCE},
            {"role": "user", "content": prompt},
        ]

    def meta(self) -> dict:
        return {}

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        return _post_with_retry(client, "/chat/completions",
                                {"model": self._wire, "messages": messages})

    def parse_action(self, resp: dict) -> Action:
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        command = _extract_command(content)
        return Action(
            command=command, text=content, reasoning=reasoning,
            well_formed=command is not None,
            raw_assistant={"role": "assistant", "content": content},
        )

    def usage(self, resp: dict, model: str) -> dict:
        return _openai_usage(resp, model)

    def result_message(self, action: Action, output: str, exit_code: int) -> dict:
        # If the model dreamed a multi-step session, prepend a correction so the
        # fabricated continuation can't drive the next turn.
        prefix = _CORRECTION if _overgenerated(action.text) else ""
        return {"role": "user", "content": f"{prefix}exit_code: {exit_code}\n{output}"}

    def nudge(self) -> dict:
        return {"role": "user",
                "content": "No ```bash block found. Reply with exactly one command in a ```bash fence."}
