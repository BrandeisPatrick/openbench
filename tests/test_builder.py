"""build_task_image resolves the base image per task (the grade-env fix).

Old base_commits need an older python (e.g. pre-3.10 code doing
`from collections import Mapping`); without a per-task base the lib fails to
import under python:3.12 and the whole grade scores 0%.
"""

from __future__ import annotations

from datetime import UTC, datetime

from openbench import paths
from openbench.envs import builder
from openbench.models import HardnessTier, Task


def _task(tmp, **extra) -> str:
    tdir = tmp / "tasks" / "demo__repo-1"
    tdir.mkdir(parents=True, exist_ok=True)
    t = Task(
        task_id="demo__repo-1", repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=1.0, **extra,
    )
    (tdir / "task.json").write_text(t.model_dump_json())
    return "demo__repo-1"


def _capture_dockerfile(monkeypatch, tmp) -> dict:
    monkeypatch.setattr(paths, "TASKS", tmp / "tasks")
    captured: dict = {}

    def fake_build(context_dir, tag, timeout):
        captured["dockerfile"] = (context_dir / "Dockerfile").read_text()

    monkeypatch.setattr(builder.dockerutil, "build_image", fake_build)
    return captured


def test_default_base_when_unset(tmp_path, monkeypatch):
    cap = _capture_dockerfile(monkeypatch, tmp_path)
    builder.build_task_image(_task(tmp_path))  # base_image None -> default
    assert "FROM python:3.12-slim" in cap["dockerfile"]


def test_per_task_base_image_used(tmp_path, monkeypatch):
    cap = _capture_dockerfile(monkeypatch, tmp_path)
    builder.build_task_image(_task(tmp_path, base_image="python:3.9-slim"))
    assert "FROM python:3.9-slim" in cap["dockerfile"]


def test_explicit_arg_overrides_task(tmp_path, monkeypatch):
    cap = _capture_dockerfile(monkeypatch, tmp_path)
    builder.build_task_image(_task(tmp_path, base_image="python:3.9-slim"), base_image="python:3.8-slim")
    assert "FROM python:3.8-slim" in cap["dockerfile"]
