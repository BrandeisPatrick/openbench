"""The offline demo must stay runnable wherever local run traces exist: it reads
the local runs/ corpus (gitignored) and renders a reward-fingerprint report with
no Docker / network / keys. On a fresh checkout with no local runs, the
corpus-dependent tests skip rather than fail.
"""

from __future__ import annotations

import json

import pytest

from openbench import paths


def _corpus() -> list:
    runs = paths.RUNS
    if not runs.exists():
        return []
    return [d for d in runs.iterdir() if (d / "metrics.json").exists()]


def test_local_corpus_valid_when_present():
    run_dirs = _corpus()
    if len(run_dirs) < 10:
        pytest.skip("no local run corpus (runs/) — generate with run-matrix")
    for d in run_dirs:
        json.loads((d / "metrics.json").read_text())
        assert (d / "run.json").exists()


def test_demo_renders_report_offline(tmp_path):
    if len(_corpus()) < 3:
        pytest.skip("no local run corpus (runs/) — generate with run-matrix")
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
