"""Container lifecycle and workspace snapshotting for agent runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from openbench import dockerutil
from openbench.models import Task


@contextmanager
def agent_container(
    task: Task,
    run_id: str,
    needs_network: bool,
    env: dict,
    cpus: int = 4,
    memory: str = "8g",
) -> Iterator[str]:
    """Start the task image and yield the container name; always remove it.

    Network is "bridge" only when the harness needs API access, otherwise
    "none". cpus/memory default to a generous single-run budget; parallel
    execution lowers them so several containers fit the VM. TODO: replace
    bridge with an egress-allowlist proxy — the MVP relies on the task image
    having git remotes removed.
    """
    if not task.image_tag:
        raise ValueError(f"task {task.task_id} has no image_tag; run build-env first")
    name = f"openbench-run-{run_id}"
    dockerutil.start_container(
        task.image_tag,
        name=name,
        network="bridge" if needs_network else "none",
        cpus=cpus,
        memory=memory,
        env=env,
    )
    try:
        yield name
    finally:
        dockerutil.remove_container(name)


def snapshot_workspace_patch(container: str, run_path: Path) -> Path:
    """Capture every workspace change in /repo as a git binary patch.

    An empty diff (agent changed nothing) yields an empty patch file, which
    is fine — grading treats it as "applies cleanly, resolves nothing".
    """
    dest = run_path / "workspace.patch"
    res = dockerutil.exec_in(
        container,
        "git -C /repo add -A && git -C /repo diff --cached --binary HEAD > /task/workspace.patch",
    )
    if res.exit_code != 0:
        dest.write_text("")
        return dest
    try:
        dockerutil.copy_out(container, "/task/workspace.patch", dest)
    except dockerutil.DockerError:
        dest.write_text("")
    if not dest.exists():
        dest.write_text("")
    return dest
