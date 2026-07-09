"""Build the per-task Docker image pinned at the base commit."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from openbench import dockerutil, paths
from openbench.models import Task

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_BUILD_TIMEOUT_S = 1800


def base_image_for(task: Task) -> str:
    """python:<task.python_version>-slim — per-task, SWE-bench style, because
    old base commits cannot import on modern Python (the golden control then
    grades 0% and every model looks like a failure on that task)."""
    return f"python:{task.python_version}-slim"


def image_tag_for(task_id: str) -> str:
    return f"openbench/{task_id.lower()}:base"


def offline_install_cmd(install_cmd: str) -> str:
    """Adapt an install command for a network-none container.

    pip's default build isolation downloads build deps from PyPI, which can
    never succeed offline; the task image preinstalls the common PEP 517
    backends so --no-build-isolation works instead.
    """
    if install_cmd.startswith("pip install") and "--no-build-isolation" not in install_cmd:
        return f"{install_cmd} --no-build-isolation"
    return install_cmd


def _grading_config() -> dict[str, Any]:
    cfg = paths.CONFIGS / "grading.yaml"
    if cfg.exists():
        return yaml.safe_load(cfg.read_text()) or {}
    return {}


def render_dockerfile(task: Task, base_image: str | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    return env.get_template("Dockerfile.j2").render(
        base_image=base_image or base_image_for(task),
        repo=task.repo,
        base_commit=task.base_commit,
        install_cmd=task.install_cmd,
        # Install the package the same way grading reinstalls it (with build deps
        # preinstalled, --no-build-isolation) so meson-python editable installs
        # record persistent tool paths, not pip's ephemeral build-env.
        offline_install_cmd=offline_install_cmd(task.install_cmd),
        env_setup_cmds=task.env_setup_cmds,
    )


def build_task_image(task_id: str, base_image: str | None = None) -> str:
    """Render Dockerfile.j2, build openbench/<task_id>:base, record it in task.json."""
    task_json = paths.task_dir(task_id) / "task.json"
    task = Task.model_validate_json(task_json.read_text())

    tag = image_tag_for(task_id)
    timeout = int(_grading_config().get("build_timeout_s", DEFAULT_BUILD_TIMEOUT_S))

    with TemporaryDirectory(prefix="openbench-env-") as ctx:
        context_dir = Path(ctx)
        (context_dir / "Dockerfile").write_text(render_dockerfile(task, base_image=base_image))
        dockerutil.build_image(context_dir, tag, timeout=timeout)

    task.image_tag = tag
    task_json.write_text(task.model_dump_json(indent=2))
    return tag
