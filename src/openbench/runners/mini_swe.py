"""Minimal shell-loop scaffold for OpenAI-compatible APIs (DeepSeek, etc.).

The counterweight to Claude Code's rich scaffold: one bash command per turn,
no tools, no plan mode. The LLM API is called from the HOST; the task
container runs with network=none, so the agent cannot reach the internet and
the API key never enters the container.

Transcript format (one JSON per line, raw_transcript.jsonl):
  {"type": "meta", "model": ..., "task_id": ...}
  {"type": "api_response", "turn": n, "content": ..., "reasoning_content": ...,
   "usage": {"prompt_tokens": ..., "completion_tokens": ...}}
  {"type": "exec", "turn": n, "command": ..., "exit_code": ..., "output": ...}
  {"type": "final", "exit_reason": ..., "turns": n, "usage_totals": {...}}
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

import httpx

from openbench import dockerutil, paths
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage
from openbench.runners.common import (
    API_TIMEOUT_S,
    DONE_MARKER,
    EXEC_TIMEOUT_S,
    PRICES_PER_MTOK,
    accumulate_openai_usage,
    request_with_retries,
    resolve_provider,
    truncate,
)

# Few-shot system prompt (variant "B"). A measured prompt-A/B (Opus, n=5/task)
# showed this SHOW-don't-tell form roughly halves the multi-step "dreaming"
# (over-generation) vs an instruction-only prompt — 80%->40% of turns on the
# easy task, and ~6% on harder tasks — by demonstrating the one-command-then-stop
# pattern and an explicit WRONG example of fabricated output. It does not fully
# eliminate the behavior (the format prior is deep); the reactive _CORRECTION
# below catches the residual. Both are uniform across all models, so consistency
# across the (model, harness) cells is preserved. See docs/EXPERIMENTS.md.
SYSTEM_PROMPT = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

CRITICAL FORMAT RULE: every reply is EXACTLY one ```bash block, then you STOP. You never write a second block, never write a line starting with "system", and never write what you think the output will be. The ENVIRONMENT produces output, not you. Any output you write is a hallucination — it is discarded and you are corrected.

CORRECT (do this) — one command, then nothing, then you wait:
```bash
grep -n "def foo" src/app.py
```

WRONG (never do this) — fabricating the result and continuing:
```bash
grep -n "def foo" src/app.py
```
system```
42:def foo(...):   <-- FABRICATED, forbidden
```

Other rules:
- The command runs with bash in /repo. No internet access.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, reply with exactly:
```bash
echo {DONE_MARKER}
```"""

# Pre-fix instruction-only prompt (variant "A" / OFF). Kept verbatim from the
# commit before the few-shot fix so an in-session A/B can be run with identical
# settings. Selected when OPENBENCH_MINISWE_VARIANT=off; default is the ON prompt
# above. Used only for the E13 dream-fix validation — see docs/EXPERIMENTS.md.
_SYSTEM_PROMPT_OFF = f"""You are an expert software engineer working alone in a sandboxed repository at /repo (current directory).

Rules:
- Reply with exactly ONE shell command per turn, in a ```bash fenced block. Nothing outside the block is executed.
- The command runs with bash in /repo. You see stdout/stderr (truncated) next turn.
- No internet access. Do not try to fetch anything.
- Do not modify existing test files.
- Edit files with heredocs (cat > file << 'EOF') or python - << 'EOF' scripts.
- Work iteratively: explore, implement, run the relevant tests, fix, repeat.
- When the task is complete and tests pass, reply with exactly:
```bash
echo {DONE_MARKER}
```"""


# Reactive anti-confabulation correction (uniform across all models): some models
# (esp. native-tool-trained ones on this bare text protocol) emit a whole imagined
# session in one reply — multiple commands plus fabricated outputs — and then form
# a false belief they have finished. We execute only the first real command; this
# note confronts the model with reality so the dream doesn't drive control flow.
_CORRECTION = (
    "NOTE: your previous reply contained more than one command and/or made-up "
    "output. Only your FIRST command was actually run. Everything you wrote after "
    "it (including any predicted output or a premature done) is NOT real — ignore "
    "it. The REAL output of your first command is below. Reply with exactly ONE "
    "command next, and never predict outputs.\n\n"
)


def _overgenerated(content: str) -> bool:
    """The model emitted more than one fenced block — i.e. it kept generating past
    the first command (a dreamed continuation), instead of stopping to wait for the
    real output. One command = one ```...``` block = two fence markers."""
    return (content or "").count("```") > 2


def _default_chat(model: str) -> Callable[[list[dict]], dict]:
    base_url, key, wire_model = resolve_provider(model)
    client = httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {key}"},
        timeout=API_TIMEOUT_S,
    )

    def chat(messages: list[dict]) -> dict:
        return request_with_retries(client, {"model": wire_model, "messages": messages})

    return chat


def _extract_command(text: str) -> str | None:
    """The model's FIRST proposed command.

    Models routinely hallucinate a whole multi-step trajectory in one reply —
    several ```bash blocks with fabricated outputs between them, sometimes
    ending in a premature DONE. We must execute only the first action and feed
    back the REAL output; taking the last fence would let the model's
    hallucinated continuation (incl. a fake DONE) drive control flow.
    """
    fences = re.findall(r"```(?:bash|sh)?\s*\n(.*?)```", text or "", re.DOTALL)
    for fence in fences:
        if fence.strip():
            return fence.strip()
    return None


class MiniSweRunner:
    """name 'mini-swe'. chat_fn is injectable for offline tests."""

    name = "mini-swe"
    needs_network = False  # API is called from the host; container stays offline.

    def __init__(self, chat_fn: Callable[[list[dict]], dict] | None = None) -> None:
        self._chat_fn = chat_fn

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        transcript = run_path / "raw_transcript.jsonl"
        prompt = (paths.task_dir(task.task_id) / task.prompt_path).read_text()
        chat = self._chat_fn or _default_chat(model)
        price_in, price_out = PRICES_PER_MTOK.get(model, (0.0, 0.0))

        # A/B toggle for the dream-fix validation: "on" (default) = few-shot +
        # reactive correction; "off" = pre-fix instruction-only prompt, no correction.
        variant = os.environ.get("OPENBENCH_MINISWE_VARIANT", "on").lower()
        system_prompt = SYSTEM_PROMPT if variant != "off" else _SYSTEM_PROMPT_OFF

        usage = zero_usage()
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        exit_reason: ExitReason = "turn_cap"
        started = time.monotonic()

        with transcript.open("w") as log:
            log.write(json.dumps({"type": "meta", "model": model, "task_id": task.task_id, "variant": variant}) + "\n")
            for turn in range(1, limits.max_turns + 1):
                if time.monotonic() - started > limits.wall_clock_s:
                    exit_reason = "timeout"
                    break
                # Cost cap BEFORE the next API call: every loop path reaches this
                # (a fence-less reply `continue`s past any check placed later —
                # that path once burned 2.2x the cap; see tests #8).
                if usage["cost_usd"] > limits.max_cost_usd:
                    exit_reason = "cost_cap"
                    break
                try:
                    data = chat(messages)
                except Exception as exc:
                    (run_path / "runner_error.log").write_text(str(exc))
                    exit_reason = "crash"
                    break

                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                u = data.get("usage") or {}
                accumulate_openai_usage(usage, u, price_in, price_out)
                usage["num_turns"] = turn
                log.write(json.dumps({
                    "type": "api_response",
                    "turn": turn,
                    "content": content,
                    "reasoning_content": reasoning,
                    "usage": {
                        "prompt_tokens": u.get("prompt_tokens", 0),
                        "completion_tokens": u.get("completion_tokens", 0),
                    },
                }) + "\n")
                log.flush()

                messages.append({"role": "assistant", "content": content})
                command = _extract_command(content)
                if command is None:
                    messages.append({
                        "role": "user",
                        "content": "No ```bash block found. Reply with exactly one command in a ```bash fence.",
                    })
                    continue
                if DONE_MARKER in command:
                    log.write(json.dumps({
                        "type": "exec", "turn": turn, "command": command,
                        "exit_code": 0, "output": DONE_MARKER,
                    }) + "\n")
                    exit_reason = "completed"
                    break

                res = dockerutil.exec_in(
                    container, command, timeout=EXEC_TIMEOUT_S, user="agent"
                )
                output = truncate((res.stdout or "") + (res.stderr or ""))
                log.write(json.dumps({
                    "type": "exec", "turn": turn, "command": command,
                    "exit_code": res.exit_code, "output": output,
                }) + "\n")
                log.flush()
                # If the model dreamed a multi-step session, prepend a correction
                # so the fabricated continuation can't drive the next turn.
                prefix = _CORRECTION if (variant != "off" and _overgenerated(content)) else ""
                messages.append({
                    "role": "user",
                    "content": f"{prefix}exit_code: {res.exit_code}\n{output}",
                })

            log.write(json.dumps({
                "type": "final", "exit_reason": exit_reason,
                "turns": usage["num_turns"], "usage_totals": usage,
            }) + "\n")

        return exit_reason, usage
