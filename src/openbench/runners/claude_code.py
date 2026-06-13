"""Claude Code CLI harness adapter.

The claude CLI is assumed to be installed in the task image (pinned by
build-env). We pipe the task prompt into a single headless `claude -p`
invocation and capture the stream-json transcript.
"""

from __future__ import annotations

import json
from pathlib import Path

from openbench import dockerutil
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage

_TRANSCRIPT = "/task/raw_transcript.jsonl"
_STDERR_LOG = "/task/claude_stderr.log"


class ClaudeCodeRunner:
    name = "claude-code"
    needs_network = True

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        which = dockerutil.exec_in(container, "which claude", user="agent")
        if which.exit_code != 0:
            (run_path / "runner_error.log").write_text(
                "claude CLI not found in task image (`which claude` failed as user "
                "'agent'). The image must pin a claude CLI install; rebuild with "
                f"build-env.\nstdout: {which.stdout}\nstderr: {which.stderr}\n"
            )
            return "crash", zero_usage()

        cmd = (
            f"cat /task/prompt.md | claude -p --output-format stream-json --verbose "
            f"--include-partial-messages --max-turns {limits.max_turns} "
            f"--model {model} --dangerously-skip-permissions "
            f"> {_TRANSCRIPT} 2>{_STDERR_LOG}"
        )
        # ANTHROPIC_API_KEY reaches the CLI via the container env (sandbox env).
        res = dockerutil.exec_in(container, cmd, timeout=limits.wall_clock_s, user="agent")
        timed_out = res.exit_code == 124

        transcript = run_path / "raw_transcript.jsonl"
        try:
            dockerutil.copy_out(container, _TRANSCRIPT, transcript)
        except dockerutil.DockerError:
            transcript.write_text("")
        try:
            dockerutil.copy_out(container, _STDERR_LOG, run_path / "claude_stderr.log")
        except dockerutil.DockerError:
            pass

        usage = parse_usage_totals(transcript)
        if timed_out:
            return "timeout", usage
        # Cost cap is enforced post-hoc for the MVP: we read the final result
        # event's total_cost_usd after the run. TODO: poll the transcript
        # mid-run and kill the exec when the cap is crossed.
        if usage["cost_usd"] > limits.max_cost_usd:
            return "cost_cap", usage
        if res.exit_code != 0 and not transcript.read_text().strip():
            (run_path / "runner_error.log").write_text(
                f"claude exited {res.exit_code} with an empty transcript.\n"
                f"stderr: {res.stderr[-2000:]}\n"
            )
            return "crash", usage
        return "completed", usage


def parse_usage_totals(transcript: Path) -> dict:
    """Sum usage from a stream-json transcript; defensive against drift.

    Token counts come from usage objects on assistant message events; cost
    and turn count come from the final result event. Thinking-token counts
    are not exposed by the CLI, so tokens_thinking stays 0 and we record the
    thinking character count instead.
    """
    totals = zero_usage()
    totals["thinking_chars"] = 0
    if not transcript.exists():
        return totals
    for line in transcript.read_text().splitlines():
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        try:
            if etype == "assistant":
                message = event.get("message") or {}
                usage = message.get("usage") or {}
                totals["tokens_in"] += int(usage.get("input_tokens") or 0)
                totals["tokens_out"] += int(usage.get("output_tokens") or 0)
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        totals["thinking_chars"] += len(str(block.get("thinking") or ""))
            elif etype == "result":
                totals["cost_usd"] = float(event.get("total_cost_usd") or 0.0)
                totals["num_turns"] = int(event.get("num_turns") or 0)
        except (TypeError, ValueError):
            continue
    return totals
