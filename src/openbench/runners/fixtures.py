"""Fixture runners for CI: golden (applies the gold patch) and null (no-op).

Both write a small synthetic stream-json transcript so the trace pipeline
always has input, even without a real agent in the loop.
"""

from __future__ import annotations

import json
from pathlib import Path

from openbench import dockerutil, paths
from openbench.models import ExitReason, RunLimits, Task
from openbench.runners.base import zero_usage


def _write_transcript(run_path: Path, events: list[dict]) -> None:
    lines = "\n".join(json.dumps(e) for e in events)
    (run_path / "raw_transcript.jsonl").write_text(lines + "\n")


def _init_event(model: str, session_id: str) -> dict:
    return {
        "type": "system",
        "subtype": "init",
        "session_id": session_id,
        "model": model,
        "tools": ["Bash", "Read", "Edit"],
        "cwd": "/repo",
    }


def _result_event(result: str, num_turns: int) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "total_cost_usd": 0.0,
        "num_turns": num_turns,
        "is_error": False,
        "result": result,
    }


class GoldenRunner:
    """Applies the task's full gold patch (test changes included).

    Applying the full patch is faithful: grading reverts protected test
    files, and the gold test content equals the protected gold content, so
    the run still grades as resolved.
    """

    name = "golden"
    needs_network = False

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        gold = paths.task_dir(task.task_id) / task.gold_patch_path
        dockerutil.copy_in(container, gold, "/task/gold.patch")
        res = dockerutil.exec_in(container, "git -C /repo apply /task/gold.patch")
        if res.exit_code != 0:
            (run_path / "runner_error.log").write_text(
                f"git apply /task/gold.patch failed ({res.exit_code}):\n{res.stderr[-2000:]}\n"
            )
            return "crash", zero_usage()
        _write_transcript(
            run_path,
            [
                _init_event(model, session_id="golden"),
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Applying gold patch."}],
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_golden_1",
                                "name": "Bash",
                                "input": {"command": "git apply /task/gold.patch"},
                            }
                        ],
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
                _result_event("gold patch applied", num_turns=1),
            ],
        )
        return "completed", zero_usage()


class NullRunner:
    """Does nothing inside the container; useful as a pipeline smoke test."""

    name = "null"
    needs_network = False

    def run(
        self,
        task: Task,
        container: str,
        run_path: Path,
        model: str,
        limits: RunLimits,
    ) -> tuple[ExitReason, dict]:
        _write_transcript(
            run_path,
            [
                _init_event(model, session_id="null"),
                _result_event("no-op", num_turns=0),
            ],
        )
        return "completed", zero_usage()
