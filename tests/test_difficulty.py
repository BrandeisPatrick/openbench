"""Offline tests for PR-review difficulty assignment (injected chat_fn, no network)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openbench import paths
from openbench.models import HardnessTier, Task
from openbench.tasks.difficulty import _parse, assess_difficulty, tasks_missing_difficulty


def _write_task(tmp_path, task_id="demo__repo-1", difficulty=None) -> None:
    tdir = tmp_path / "tasks" / task_id
    tdir.mkdir(parents=True)
    (tdir / "prompt.md").write_text("Fix the bug in foo().")
    (tdir / "gold.patch").write_text("--- a/foo.py\n+++ b/foo.py\n@@\n-bad\n+good\n")
    task = Task(
        task_id=task_id, repo="demo/repo", pr_number=1,
        base_commit="a" * 40, merge_commit="b" * 40,
        merged_at=datetime(2026, 6, 1, tzinfo=UTC),
        tier=HardnessTier.MAIN, hardness_score=0.0,
        fail_to_pass=["test_foo"], difficulty=difficulty,
    )
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))


def test_assess_writes_label_and_note(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _write_task(tmp_path)
    captured = {}

    def fake_chat(system, user):
        captured["user"] = user
        return '{"difficulty": "1-4 hours", "note": "multi-file refactor"}'

    t = assess_difficulty("demo__repo-1", chat_fn=fake_chat)
    assert t.difficulty == "1-4 hours"
    assert t.difficulty_note == "multi-file refactor"
    # persisted to disk
    reloaded = Task.model_validate_json(
        (tmp_path / "tasks" / "demo__repo-1" / "task.json").read_text()
    )
    assert reloaded.difficulty == "1-4 hours"
    # the prompt + gold diff actually reached the model
    assert "Fix the bug" in captured["user"] and "good" in captured["user"]


def test_assess_skips_when_already_labeled(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _write_task(tmp_path, difficulty="<15 min fix")

    def boom(system, user):
        raise AssertionError("model must not be called when already labeled")

    t = assess_difficulty("demo__repo-1", chat_fn=boom)
    assert t.difficulty == "<15 min fix"


def test_assess_force_relabels(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _write_task(tmp_path, difficulty="<15 min fix")
    t = assess_difficulty(
        "demo__repo-1",
        chat_fn=lambda s, u: '{"difficulty": ">4 hours", "note": "x"}',
        force=True,
    )
    assert t.difficulty == ">4 hours"


def test_parse_rejects_invalid_label():
    with pytest.raises(ValueError):
        _parse('{"difficulty": "trivial", "note": "x"}')  # not on the shared scale


def test_parse_extracts_from_noisy_text():
    label, note = _parse('Sure!\n{"difficulty": "15 min - 1 hour", "note": "small"}\nDone.')
    assert label == "15 min - 1 hour" and note == "small"


def test_tasks_missing_difficulty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TASKS", tmp_path / "tasks")
    _write_task(tmp_path, task_id="a__a-1", difficulty=None)
    _write_task(tmp_path, task_id="b__b-2", difficulty="1-4 hours")
    assert tasks_missing_difficulty() == ["a__a-1"]
