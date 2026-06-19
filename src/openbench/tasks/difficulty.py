"""Assign a difficulty label to a task by reviewing its PR.

SWE-bench Verified tasks arrive with a human difficulty annotation (kept by
mining/swebench.py). Mined tasks have none, so we assign one the way a human
reviewer would: read the problem statement and the gold diff and judge roughly
how long the fix would take, on the shared DIFFICULTY_LEVELS scale.

This is one model call per task — no calibration, caching, or scoring
framework. The label lands on task.json (`difficulty` + a one-line
`difficulty_note`); re-run with force=True to redo. The model client is
injectable (`chat_fn`) so tests run offline.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable

import httpx

from openbench import paths
from openbench.models import DIFFICULTY_LEVELS, Task

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-sonnet-4-6"  # difficulty triage is cheap; override for spot checks
_MAX_GOLD_CHARS = 24000  # keep large diffs from blowing the context / cost

# Chat signature: (system, user) -> model's text reply. Injectable for tests.
ChatFn = Callable[[str, str], str]

_SYSTEM = (
    "You are a staff engineer triaging a coding task for a benchmark. Read the "
    "problem statement and the reference solution diff, then estimate how long "
    "the fix would take a competent engineer who already knows the codebase.\n\n"
    "Reply with ONLY a JSON object:\n"
    '{"difficulty": <one of ' + json.dumps(list(DIFFICULTY_LEVELS)) + '>, '
    '"note": "<=15 words on why"}\n\n'
    "Judge by: how localized the fix is, how many files/hunks it spans, whether "
    "it needs design vs a mechanical change, and the domain knowledge required. "
    "Use the gold diff only to gauge effort — not as something to reproduce."
)


def _default_chat(model: str) -> ChatFn:
    """A minimal Anthropic text client (mirrors runners/claude_native.py)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (required to assess difficulty)")
    client = httpx.Client(
        headers={
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        timeout=120,
    )

    def chat(system: str, user: str) -> str:
        body = {
            "model": model,
            "max_tokens": 300,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = client.post(_ANTHROPIC_URL, json=body)
                if resp.status_code in (429, 500, 502, 503, 529):
                    time.sleep(2**attempt)
                    continue
                resp.raise_for_status()
                blocks = resp.json().get("content", [])
                return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            except httpx.HTTPError as exc:
                last_err = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"anthropic API failed after retries: {last_err}")

    return chat


def _parse(text: str) -> tuple[str, str]:
    """Extract (difficulty, note) from the model's JSON reply; validate the label."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text!r}")
    obj = json.loads(text[start : end + 1])
    label = str(obj.get("difficulty", "")).strip()
    if label not in DIFFICULTY_LEVELS:
        raise ValueError(f"difficulty {label!r} not in {DIFFICULTY_LEVELS}")
    return label, str(obj.get("note", "")).strip()


def _build_user_prompt(prompt: str, gold: str, fail_to_pass: list[str]) -> str:
    truncated = len(gold) > _MAX_GOLD_CHARS
    if truncated:
        gold = gold[:_MAX_GOLD_CHARS] + "\n... [diff truncated] ..."
    return (
        f"## Problem statement\n\n{prompt}\n\n"
        f"## Reference solution diff{' (truncated)' if truncated else ''}\n\n"
        f"```diff\n{gold}\n```\n\n"
        f"## Tests that must pass\n\n{', '.join(fail_to_pass) or '(none listed)'}"
    )


def assess_difficulty(
    task_id: str,
    chat_fn: ChatFn | None = None,
    model: str = _DEFAULT_MODEL,
    force: bool = False,
) -> Task:
    """Assign task.difficulty by reviewing the PR. No-op if already labeled.

    Verified imports already carry a human label, so they're skipped unless
    forced. Returns the (possibly updated) Task.
    """
    tdir = paths.task_dir(task_id)
    task = Task.model_validate_json((tdir / "task.json").read_text())
    if task.difficulty and not force:
        return task

    prompt = (tdir / task.prompt_path).read_text()
    gold = (tdir / task.gold_patch_path).read_text()
    user = _build_user_prompt(prompt, gold, task.fail_to_pass)

    chat = chat_fn or _default_chat(model)
    label, note = _parse(chat(_SYSTEM, user))

    task.difficulty = label
    task.difficulty_note = note
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))
    return task


def tasks_missing_difficulty() -> list[str]:
    """Task ids on disk that have no difficulty label yet (mined, unlabeled)."""
    out: list[str] = []
    if not paths.TASKS.exists():
        return out
    for tj in sorted(paths.TASKS.glob("*/task.json")):
        if not Task.model_validate_json(tj.read_text()).difficulty:
            out.append(tj.parent.name)
    return out
