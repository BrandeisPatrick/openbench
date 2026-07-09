"""Thin wrappers around the docker CLI.

We shell out instead of using docker-py: fewer deps, identical behavior on
Docker Desktop/colima, and every invocation is loggable as a plain command.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class DockerError(RuntimeError):
    pass


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


def _run(cmd: list[str], timeout: int | None = None, check: bool = False) -> ExecResult:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    result = ExecResult(proc.returncode, proc.stdout, proc.stderr)
    if check and proc.returncode != 0:
        raise DockerError(f"{' '.join(cmd[:6])}... failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return result


def image_exists(tag: str) -> bool:
    return _run(["docker", "image", "inspect", tag]).exit_code == 0


def build_image(context_dir: Path, tag: str, timeout: int = 1800) -> None:
    _run(["docker", "build", "-t", tag, str(context_dir)], timeout=timeout, check=True)


def start_container(
    image: str,
    name: str,
    network: str = "none",
    cpus: int = 4,
    memory: str = "8g",
    env: dict[str, str] | None = None,
    mounts: dict[Path, str] | None = None,
) -> str:
    """Start a detached container kept alive with sleep; returns container id."""
    cmd = [
        "docker", "run", "-d", "--name", name,
        "--network", network, f"--cpus={cpus}", f"--memory={memory}",
        "--tmpfs", "/tmp",
    ]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    for host, cont in (mounts or {}).items():
        cmd += ["-v", f"{host}:{cont}"]
    cmd += [image, "sleep", "infinity"]
    return _run(cmd, check=True).stdout.strip()


def exec_in(
    container: str,
    command: str,
    workdir: str = "/repo",
    timeout: int = 1200,
    user: str | None = None,
) -> ExecResult:
    cmd = ["docker", "exec", "-w", workdir]
    if user:
        cmd += ["-u", user]
    cmd += [container, "bash", "-lc", command]
    try:
        return _run(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ExecResult(124, "", f"timeout after {timeout}s: {command[:200]}")


def disconnect_network(container: str, network: str = "bridge") -> None:
    """Detach a running container from a network (leaves only loopback)."""
    _run(["docker", "network", "disconnect", network, container], check=True)


def copy_in(container: str, src: Path, dest: str) -> None:
    _run(["docker", "cp", str(src), f"{container}:{dest}"], check=True)


def copy_out(container: str, src: str, dest: Path) -> None:
    _run(["docker", "cp", f"{container}:{src}", str(dest)], check=True)


def remove_container(name: str) -> None:
    _run(["docker", "rm", "-f", name])
