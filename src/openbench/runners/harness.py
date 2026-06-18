"""One agent-harness loop, parameterized by a wire Protocol.

`mini-swe`, `claude-native`, and `tooluse` are NOT three runners — they are three
*protocols* behind one identical loop. The loop is fixed: one bash command per
turn, sandboxed exec, the shared `meta`/`api_response`/`exec`/`final` transcript,
and the cost/wall-clock/turn caps. The *protocol* is pluggable: how a request is
built, how the action is parsed back out, how usage is read, and how the
observation is fed back. See `runners/protocols.py` for the implementations.

The loop never touches a provider-shaped message or field — everything provider-
specific goes through the protocol — so the only thing that differs between a
mini-swe run and a claude-native run of the same model is the model's behavior
under the two protocols, not the parsing. That makes protocol-vs-protocol a clean
controlled comparison and keeps `(model, protocol)` cells separable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from openbench import dockerutil, paths
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage

DONE_MARKER = "OPENBENCH_DONE"
_OUTPUT_CAP = 5000
_EXEC_TIMEOUT_S = 600
_API_TIMEOUT_S = 600


def _truncate(text: str, cap: int = _OUTPUT_CAP) -> str:
    if len(text) <= cap:
        return text
    half = cap // 2
    return f"{text[:half]}\n... [{len(text) - cap} chars truncated] ...\n{text[-half:]}"


@runtime_checkable
class WireProtocol(Protocol):
    """How an action is requested from and parsed back out of one model family.

    The harness loop owns control flow; a `WireProtocol` owns the wire format.
    `parse_action` returns an `Action` (see protocols.py) whose `raw_assistant`
    is the assistant turn to append verbatim (so thinking signatures / tool_call
    ids survive); `result_message` is the observation appended after exec.
    """

    name: str
    needs_network: bool

    def initial_messages(self, prompt: str) -> list[dict]: ...
    def meta(self) -> dict: ...
    def chat(self, messages: list[dict], model: str) -> dict: ...
    def parse_action(self, resp: dict): ...  # -> Action
    def usage(self, resp: dict, model: str) -> dict: ...  # tokens_in/out/thinking, cost_usd
    def result_message(self, action, output: str, exit_code: int) -> dict: ...
    def nudge(self) -> dict: ...


class Harness:
    """An `AgentRunner` (see base.py) that drives a `WireProtocol` through the loop.

    `name`/`needs_network` come from the protocol so `RunResult.harness` (and thus
    the `(model, harness)` cell key) records which protocol ran.
    """

    def __init__(self, protocol: WireProtocol) -> None:
        self.protocol = protocol
        self.name = protocol.name
        self.needs_network = getattr(protocol, "needs_network", False)

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        proto = self.protocol
        transcript = run_path / "raw_transcript.jsonl"
        prompt = (paths.task_dir(task.task_id) / task.prompt_path).read_text()

        usage = zero_usage()
        messages: list[dict] = proto.initial_messages(prompt)
        exit_reason: ExitReason = "turn_cap"
        started = time.monotonic()

        with transcript.open("w") as log:
            log.write(
                json.dumps({"type": "meta", "model": model, "task_id": task.task_id, **proto.meta()})
                + "\n"
            )
            for turn in range(1, limits.max_turns + 1):
                # Caps BEFORE the next API call: every loop path reaches this
                # (a not-well-formed reply `continue`s past any later check —
                # that once burned 2.2x the cap; see mini-swe history).
                if time.monotonic() - started > limits.wall_clock_s:
                    exit_reason = "timeout"
                    break
                if usage["cost_usd"] > limits.max_cost_usd:
                    exit_reason = "cost_cap"
                    break
                try:
                    resp = proto.chat(messages, model)
                except Exception as exc:
                    (run_path / "runner_error.log").write_text(str(exc))
                    exit_reason = "crash"
                    break

                action = proto.parse_action(resp)
                u = proto.usage(resp, model)
                usage["tokens_in"] += u["tokens_in"]
                usage["tokens_out"] += u["tokens_out"]
                usage["tokens_thinking"] += u["tokens_thinking"]
                usage["cost_usd"] += u["cost_usd"]
                usage["num_turns"] = turn

                log.write(
                    json.dumps({
                        "type": "api_response", "turn": turn,
                        "content": action.text, "reasoning_content": action.reasoning,
                        "usage": {"prompt_tokens": u["tokens_in"], "completion_tokens": u["tokens_out"]},
                    })
                    + "\n"
                )
                log.flush()

                # Append the assistant turn verbatim (protocol-shaped): plain
                # string for text-fence, raw content blocks for Anthropic, the
                # tool_calls message for OpenAI tool-use.
                messages.append(action.raw_assistant)

                if not action.well_formed:
                    # `well_formed=False` is the out-of-distribution / confab
                    # signal (no usable action in protocol). Nudge and retry.
                    messages.append(proto.nudge())
                    continue

                command = action.command or ""
                if DONE_MARKER in command:
                    log.write(
                        json.dumps({"type": "exec", "turn": turn, "command": command,
                                    "exit_code": 0, "output": DONE_MARKER})
                        + "\n"
                    )
                    exit_reason = "completed"
                    break

                res = dockerutil.exec_in(container, command, timeout=_EXEC_TIMEOUT_S, user="agent")
                output = _truncate((res.stdout or "") + (res.stderr or ""))
                log.write(
                    json.dumps({"type": "exec", "turn": turn, "command": command,
                                "exit_code": res.exit_code, "output": output})
                    + "\n"
                )
                log.flush()
                messages.append(proto.result_message(action, output, res.exit_code))

            log.write(
                json.dumps({"type": "final", "exit_reason": exit_reason,
                            "turns": usage["num_turns"], "usage_totals": usage})
                + "\n"
            )

        return exit_reason, usage
