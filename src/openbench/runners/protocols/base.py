"""Protocol foundation: the wire contract, shared base classes, and HTTP plumbing.

A *protocol* is how an action is requested from and parsed back out of one model
family; the harness loop (runners/harness.py) drives it. `WireProtocol` is the
structural contract the loop type-hints against; `BaseProtocol` factors out the
shared `chat()` dance (chat_fn → lazy client → send) so each concrete protocol
only implements `_make_client` + `_send` + the parse/format hooks.

Depends only on `providers` (a leaf); imported by `harness` and every concrete
protocol — so it must not import them back (keeps the import graph acyclic).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

import httpx

from openbench.runners.protocols.providers import _resolve_provider

# The sentinel a model echoes (`echo OPENBENCH_DONE`) to declare completion; the
# loop checks for it and protocols embed it in prompts/nudges.
DONE_MARKER = "OPENBENCH_DONE"
_API_TIMEOUT_S = 600

ChatFn = Callable[[list[dict]], dict]


def _post_with_retry(client: httpx.Client, url: str, body: dict) -> dict:
    last_err: str | None = None
    for attempt in range(6):
        try:
            resp = client.post(url, json=body)
            if resp.status_code in (429, 500, 502, 503, 529):
                # Record WHAT failed (a 429 storm used to exit as "None") and
                # wait long enough to matter: TPM windows are 60s, so honor
                # Retry-After and back off toward a minute, not 8 seconds.
                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                retry_after = float(resp.headers.get("retry-after") or 0)
                time.sleep(max(retry_after, min(60.0, 2.0**attempt)))
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            detail = f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            if exc.response.status_code < 500:
                # 4xx (not 429): the request itself is bad — retrying is futile.
                raise RuntimeError(f"API rejected request: {detail}") from exc
            last_err = detail
            time.sleep(min(60.0, 2.0**attempt))
        except httpx.HTTPError as exc:
            last_err = str(exc)
            time.sleep(min(60.0, 2.0**attempt))
    raise RuntimeError(f"API failed after retries: {last_err}")


@dataclass
class Action:
    """One parsed model action.

    ``well_formed`` is the protocol-compliance signal: did the model emit a usable
    action in the expected format? A low rate across a run is the out-of-
    distribution signature (confabulation when a tool-use model is forced through
    a foreign protocol). ``raw_assistant`` is the assistant turn appended verbatim
    next turn (string for text-fence, content blocks for Anthropic, tool_calls
    message for OpenAI).
    """

    command: str | None
    text: str
    reasoning: str
    well_formed: bool
    tool_call_id: str | None = None
    raw_assistant: dict | None = None


@runtime_checkable
class WireProtocol(Protocol):
    """How an action is requested from and parsed back out of one model family.

    The harness loop owns control flow; a `WireProtocol` owns the wire format.
    `parse_action` returns an `Action` whose `raw_assistant` is the assistant turn
    to append verbatim (so thinking signatures / tool_call ids survive);
    `result_message` is the observation appended after exec.
    """

    name: str
    needs_network: bool

    def initial_messages(self, prompt: str) -> list[dict]: ...
    def meta(self) -> dict: ...
    def chat(self, messages: list[dict], model: str) -> dict: ...
    def parse_action(self, resp: dict) -> Action: ...
    def usage(self, resp: dict, model: str) -> dict: ...
    def result_message(self, action: Action, output: str, exit_code: int) -> dict: ...
    def nudge(self) -> dict: ...


class BaseProtocol:
    """Shared `chat()` dance for every protocol.

    `chat()` returns the injected `chat_fn` (offline tests) when present; otherwise
    it lazily builds a client (model-dependent, so not buildable in `__init__`) and
    delegates to `_send`. Concrete protocols implement `_make_client` + `_send`
    (and the parse/usage/format hooks). `needs_network=False`: the API is called
    from the host, the task container stays network=none.
    """

    name: str = ""
    needs_network: bool = False

    def __init__(self, chat_fn: ChatFn | None = None) -> None:
        self._chat_fn = chat_fn
        self._client: httpx.Client | None = None

    def chat(self, messages: list[dict], model: str) -> dict:
        if self._chat_fn is not None:
            return self._chat_fn(messages)
        if self._client is None:
            self._client = self._make_client(model)
        return self._send(self._client, messages, model)

    def _make_client(self, model: str) -> httpx.Client:
        raise NotImplementedError

    def _send(self, client: httpx.Client, messages: list[dict], model: str) -> dict:
        raise NotImplementedError


class OpenAICompatProtocol(BaseProtocol):
    """Base for OpenAI-compatible providers: Bearer + base_url client, wire model id.

    `_make_client` resolves the provider and stores `self._wire` (the provider's own
    model id, e.g. `deepseek/deepseek-chat` after stripping an `openrouter/` prefix)
    for `_send` to use. Subclasses still implement `_send` (chat-completions vs
    responses) and the parse/usage/format hooks.
    """

    def __init__(self, chat_fn: ChatFn | None = None) -> None:
        super().__init__(chat_fn)
        self._wire: str = ""

    def _make_client(self, model: str) -> httpx.Client:
        base_url, key, wire = _resolve_provider(model)
        self._wire = wire
        return httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {key}"}, timeout=_API_TIMEOUT_S
        )
