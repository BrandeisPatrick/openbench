"""Report figures for E1/E2/E3 (docs/EXPERIMENTS.md). Pure matplotlib, Agg.

Each function degrades to None when its data is absent, so figure generation
never blocks the markdown report. PNGs land in <report dir>/figures/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from openbench import paths
from openbench.analysis.estimate import (
    COMPONENTS,
    estimate_mixture,
    signature_matrix,
)
from openbench.analysis.fingerprint import build_fingerprints
from openbench.analysis.metrics import _is_green, _recall_scan, _tests_failed, _tests_passed
from openbench.models import RunMetrics, RunResult, TraceEvent

_PALETTE = ["#378ADD", "#7F77DD", "#888780", "#1D9E75", "#D85A30", "#D4537E"]


def _model_colors(models: list[str]) -> dict[str, str]:
    return {m: _PALETTE[i % len(_PALETTE)] for i, m in enumerate(sorted(models))}


def _load_run_dirs() -> list[Path]:
    from openbench.report.generate import _crashed

    if not paths.RUNS.exists():
        return []
    return sorted(
        d for d in paths.RUNS.iterdir() if (d / "run.json").exists() and not _crashed(d)
    )


def _load_metrics() -> list[RunMetrics]:
    out = []
    for rdir in _load_run_dirs():
        mpath = rdir / "metrics.json"
        if mpath.exists():
            out.append(RunMetrics.model_validate_json(mpath.read_text()))
    return out


def _load_events(rdir: Path) -> list[TraceEvent]:
    epath = rdir / "events.jsonl"
    if not epath.exists():
        return []
    return [
        TraceEvent.model_validate_json(line)
        for line in epath.read_text().splitlines()
        if line.strip()
    ]


# --- E1: reward decomposition ------------------------------------------------


def fig_composition(all_metrics: list[RunMetrics], out: Path) -> Path | None:
    estimates = estimate_mixture(all_metrics)
    estimates = {m: e for m, e in estimates.items() if m != "none"}
    if not estimates:
        return None
    models = sorted(estimates)
    fig, axes = plt.subplots(
        len(models), 1, figsize=(7, 1.0 + 1.4 * len(models)), sharex=True
    )
    axes = np.atleast_1d(axes)
    for ax, model in zip(axes, models, strict=True):
        e = estimates[model]
        ys = np.arange(len(COMPONENTS))
        for k, comp in enumerate(COMPONENTS):
            w = e.weights[comp]
            if e.estimable(comp):
                lo, hi = e.weight_cis[comp]
                ax.barh(k, w, color="#378ADD")
                ax.errorbar(
                    w, k, xerr=[[max(0.0, w - lo)], [max(0.0, hi - w)]],
                    fmt="none", ecolor="#0C447C", capsize=3,
                )
            else:
                ax.barh(k, max(w, 0.02), color="#D3D1C7")
        ax.set_yticks(ys, COMPONENTS, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, 1)
        ax.set_title(
            f"{model}  (n={e.n_runs}, residual {e.residual:.2f})", fontsize=9, loc="left"
        )
    axes[-1].set_xlabel("mixture weight (grey = not estimable, CI∋0)", fontsize=8)
    fig.suptitle("E1 — estimated reward composition", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_fingerprint_heatmap(all_metrics: list[RunMetrics], out: Path) -> Path | None:
    fps = build_fingerprints([m for m in all_metrics if m.model != "none"])
    if len(fps) < 2:
        return None
    models = sorted(fps)
    metric_names = sorted({n for fp in fps.values() for n in fp})
    z = np.array(
        [[fps[m].get(n, {}).get("z", 0.0) for n in metric_names] for m in models]
    )
    fig, ax = plt.subplots(figsize=(max(7, 0.32 * len(metric_names)), 1.2 + 0.5 * len(models)))
    im = ax.imshow(z, cmap="RdBu_r", vmin=-2, vmax=2, aspect="auto")
    ax.set_xticks(range(len(metric_names)), metric_names, rotation=60, ha="right", fontsize=7)
    ax.set_yticks(range(len(models)), models, fontsize=8)
    fig.colorbar(im, ax=ax, label="z (within cohort)", shrink=0.8)
    ax.set_title("E1 — behavioral fingerprint (z-scores)", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_collinearity(out: Path) -> Path:
    s, _ = signature_matrix()
    n = len(COMPONENTS)
    cos = np.eye(n)
    for i in range(n):
        for j in range(n):
            denom = np.linalg.norm(s[:, i]) * np.linalg.norm(s[:, j])
            cos[i, j] = float(s[:, i] @ s[:, j] / denom) if denom else 0.0
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    ax.imshow(cos, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n), COMPONENTS, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(n), COMPONENTS, fontsize=7)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{cos[i, j]:+.2f}", ha="center", va="center", fontsize=6)
    ax.set_title("E1 — component collinearity (|cos|≥0.8 not separable passively)", fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


# --- E2: progress curves -----------------------------------------------------


def _progress_series(events: list[TraceEvent]) -> list[tuple[float, float]]:
    """(normalized position, pass fraction) at each test_run with parsed counts."""
    events = sorted(events, key=lambda e: e.step_idx)
    n = len(events)
    pts = []
    for i, ev in enumerate(events):
        if ev.type != "test_run":
            continue
        total = _tests_passed(ev) + _tests_failed(ev)
        if total == 0 and not _is_green(ev):
            continue
        pts.append((i / max(1, n - 1), _tests_passed(ev) / total if total else 0.0))
    return pts


def fig_progress(out: Path) -> Path | None:
    grid = np.linspace(0, 1, 11)
    per_model: dict[str, list[np.ndarray]] = {}
    for rdir in _load_run_dirs():
        run = RunResult.model_validate_json((rdir / "run.json").read_text())
        if run.model == "none":
            continue
        events = _load_events(rdir)
        # _backfill_test_outcomes equivalent: counts already on tool_result are
        # joined by compute_metrics; here read whichever event carries them.
        from openbench.analysis.metrics import _backfill_test_outcomes

        _backfill_test_outcomes(sorted(events, key=lambda e: e.step_idx))
        pts = _progress_series(events)
        if not pts:
            # A run with zero test signal is a flat zero line — that IS the
            # E2 finding for never-verifying models; include it honestly.
            per_model.setdefault(run.model, []).append(np.zeros_like(grid))
            continue
        xs, ys = zip(*pts, strict=True)
        # step-interpolate onto the grid (last observed pass fraction).
        curve = np.zeros_like(grid)
        for gi, g in enumerate(grid):
            prior = [y for x, y in pts if x <= g]
            curve[gi] = prior[-1] if prior else 0.0
        per_model.setdefault(run.model, []).append(curve)
    if not per_model:
        return None
    colors = _model_colors(list(per_model))
    fig, ax = plt.subplots(figsize=(7, 4))
    for model, curves in sorted(per_model.items()):
        arr = np.stack(curves)
        mean = arr.mean(axis=0)
        ax.plot(grid, mean, label=f"{model} (n={len(curves)})", color=colors[model], lw=2)
        if len(curves) > 1:
            sem = arr.std(axis=0) / np.sqrt(len(curves))
            ax.fill_between(grid, mean - sem, mean + sem, color=colors[model], alpha=0.15)
    ax.set_xlabel("position in trajectory (normalized)")
    ax.set_ylabel("pass fraction of agent-run tests")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(fontsize=8)
    ax.set_title("E2 — progress curves (AgentPRM proxy; flat 0 = never measures)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


# --- E3: H13 context recall ---------------------------------------------------


def fig_recall(all_metrics: list[RunMetrics], out: Path) -> Path | None:
    per_model: dict[str, dict[str, list[float]]] = {}
    for m in all_metrics:
        if m.model == "none":
            continue
        b = per_model.setdefault(m.model, {"recall": [], "reread": []})
        if m.long_range_recall_rate is not None:
            b["recall"].append(m.long_range_recall_rate)
        if m.re_read_rate is not None:
            b["reread"].append(m.re_read_rate)
    per_model = {k: v for k, v in per_model.items() if v["recall"] and v["reread"]}

    # recall-distance distributions, re-scanned from events (raw distances are
    # not a scalar metric; the scalar lives in RunMetrics as the median).
    dist_per_model: dict[str, list[float]] = {}
    for rdir in _load_run_dirs():
        run = RunResult.model_validate_json((rdir / "run.json").read_text())
        if run.model == "none":
            continue
        events = _load_events(rdir)
        if not events:
            continue
        tdir = paths.task_dir(run.task_id)
        prompt = None
        ppath = tdir / "prompt.md"
        if ppath.exists():
            prompt = ppath.read_text()
        _, _, distances, total_turns = _recall_scan(
            sorted(events, key=lambda e: e.step_idx), prompt
        )
        if distances and total_turns:
            dist_per_model.setdefault(run.model, []).extend(distances)

    if not per_model and not dist_per_model:
        return None
    colors = _model_colors(list(set(per_model) | set(dist_per_model)))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    for model, b in sorted(per_model.items()):
        x = float(np.mean(b["reread"]))
        y = float(np.mean(b["recall"]))
        xe = float(np.std(b["reread"]) / max(1, np.sqrt(len(b["reread"]))))
        ye = float(np.std(b["recall"]) / max(1, np.sqrt(len(b["recall"]))))
        ax1.errorbar(x, y, xerr=xe, yerr=ye, fmt="o", ms=9, color=colors[model], label=model)
    ax1.set_xlabel("re-read rate (memory via re-action, H7)")
    ax1.set_ylabel("long-range recall rate (H13)")
    ax1.set_title("recalls without re-reading → top-left", fontsize=9)
    ax1.legend(fontsize=7)

    bins = [11, 15, 20, 30, 50, 100]
    for model, dists in sorted(dist_per_model.items()):
        ax2.hist(
            dists, bins=bins, density=True, histtype="step", lw=2,
            color=colors[model], label=f"{model} (n={len(dists)} refs)",
        )
    ax2.set_xlabel("recall distance (turns since artifact last seen)")
    ax2.set_ylabel("density of recall references")
    ax2.set_title("fat tail = deep context reach", fontsize=9)
    if dist_per_model:
        ax2.legend(fontsize=7)
    else:
        ax2.text(0.5, 0.5, "no long-range recalls observed", ha="center", va="center",
                 transform=ax2.transAxes, fontsize=9)
    fig.suptitle("E3 — H13 long-context recall fingerprint", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def generate_figures(report_out: Path) -> list[Path]:
    """Write all available figures next to the report; return what was written."""
    fig_dir = report_out.parent / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    all_metrics = _load_metrics()
    written: list[Path] = []
    if all_metrics:
        for fn, name in (
            (fig_composition, "e1_composition.png"),
            (fig_fingerprint_heatmap, "e1_fingerprint_heatmap.png"),
        ):
            p = fn(all_metrics, fig_dir / name)
            if p:
                written.append(p)
        written.append(fig_collinearity(fig_dir / "e1_collinearity.png"))
        p = fig_recall(all_metrics, fig_dir / "e3_recall.png")
        if p:
            written.append(p)
    p = fig_progress(fig_dir / "e2_progress.png")
    if p:
        written.append(p)
    return written
