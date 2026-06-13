"""The zero-credential demo must stay runnable: bundled example traces present,
and `openbench demo` renders a report offline (no Docker / network / keys)."""

from __future__ import annotations

import json

from openbench import paths


def test_example_corpus_present_and_valid():
    examples = paths.ROOT / "examples" / "runs"
    assert examples.exists(), "examples/runs/ (bundled demo traces) is missing"
    run_dirs = [d for d in examples.iterdir() if (d / "metrics.json").exists()]
    assert len(run_dirs) >= 10, "demo corpus should span several models"
    # every example run carries valid metrics + run metadata
    for d in run_dirs:
        json.loads((d / "metrics.json").read_text())
        assert (d / "run.json").exists()


def test_demo_renders_report_offline(tmp_path, monkeypatch):
    examples = paths.ROOT / "examples" / "runs"
    monkeypatch.setattr(paths, "RUNS", examples)
    from openbench.report.generate import generate_report

    out = generate_report(tmp_path / "demo_report.md")
    text = out.read_text()
    assert "reward fingerprints" in text.lower()
    # a real cross-model report names more than one model
    assert text.count("###") >= 3


def test_demo_command_registered():
    from openbench.cli import app

    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    assert "demo" in names
