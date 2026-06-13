"""Top-level run orchestration: load task, start sandbox, run agent, snapshot."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

from openbench import dockerutil, paths
from openbench.models import RunLimits, RunResult, Task
from openbench.runners import sandbox
from openbench.runners.base import AgentRunner


def slugify_model(model: str) -> str:
    """Make a model name safe for run_ids, paths, and Docker container names.

    Provider slugs contain '/' (e.g. openrouter/deepseek/deepseek-chat-v3-0324),
    which Docker rejects in container names and which would fork a run-dir path.
    Only [A-Za-z0-9_.-] survive. The real model string is still passed to the
    runner — this is purely for the identifier.
    """
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model)


def execute_run(
    task_id: str,
    runner: AgentRunner,
    model: str,
    limits: RunLimits,
    cpus: int = 4,
    memory: str = "8g",
) -> RunResult:
    task_json = paths.task_dir(task_id) / "task.json"
    if not task_json.exists():
        raise FileNotFoundError(f"no task.json at {task_json}; run build-task first")
    task = Task.model_validate_json(task_json.read_text())
    if not task.image_tag:
        raise ValueError(
            f"task {task_id} has no image_tag; run `openbench build-env {task_id}` first"
        )

    started = datetime.now(UTC)
    # microsecond suffix keeps run_ids unique under parallel execution
    run_id = (
        f"{task_id}--{runner.name}--{slugify_model(model)}--"
        f"{started.strftime('%Y%m%d-%H%M%S-%f')}"
    )
    run_path = paths.run_dir(run_id)
    run_path.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] = {}
    if runner.needs_network and os.environ.get("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]

    with sandbox.agent_container(
        task, run_id, runner.needs_network, env, cpus=cpus, memory=memory
    ) as container:
        # World-writable: the claude-code runner writes its transcript here as
        # the non-root `agent` user (and /tmp is tmpfs, unreachable by docker cp).
        dockerutil.exec_in(container, "mkdir -p /task && chmod 777 /task", workdir="/")
        # Honeypot payloads: files under the task's inject/ dir are planted in
        # /repo before the agent starts (e.g. visible smoke tests).
        inject_dir = paths.task_dir(task_id) / "inject"
        if inject_dir.is_dir():
            for f in sorted(p for p in inject_dir.rglob("*") if p.is_file()):
                rel = f.relative_to(inject_dir)
                dockerutil.exec_in(container, f"mkdir -p /repo/{rel.parent}", workdir="/")
                dockerutil.copy_in(container, f, f"/repo/{rel}")
                dockerutil.exec_in(container, f"chown agent /repo/{rel}", workdir="/")
        dockerutil.copy_in(container, paths.task_dir(task_id) / task.prompt_path, "/task/prompt.md")
        exit_reason, usage = runner.run(task, container, run_path, model, limits)
        sandbox.snapshot_workspace_patch(container, run_path)

    result = RunResult(
        run_id=run_id,
        task_id=task_id,
        harness=runner.name,
        model=model,
        started_at=started,
        finished_at=datetime.now(UTC),
        exit_reason=exit_reason,
        total_cost_usd=float(usage.get("cost_usd", 0.0)),
        total_tokens_in=int(usage.get("tokens_in", 0)),
        total_tokens_out=int(usage.get("tokens_out", 0)),
        total_thinking_tokens=int(usage.get("tokens_thinking", 0)),
        num_turns=int(usage.get("num_turns", 0)),
    )
    (run_path / "run.json").write_text(result.model_dump_json(indent=2))
    return result
