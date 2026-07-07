"""Comparison figures (matplotlib Agg — headless, deterministic).

Every function degrades to None when its data is missing rather than raising:
a partial corpus should still produce a partial report.
"""

from __future__ import annotations

import json
from pathlib import Path

from openbench.behavior.compare import PairComparison
from openbench.behavior.profile import AXES, BehaviorProfile

_PAIR_COLORS = {"deepseek": "#4C72B0", "gpt": "#DD8452"}


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def fig_paired_deltas(comps: list[PairComparison], out_dir: Path) -> Path | None:
    """THE 'what changed' figure: one row per metric (grouped by axis), a
    Cliff's-delta point + task-clustered CI per lab. Positive = new gen higher."""
    rows = [
        (axis, metric)
        for axis, metrics in AXES.items()
        for metric in metrics
        if any(
            d.metric == metric and d.cliffs is not None
            for c in comps
            for d in c.deltas
        )
    ]
    if not rows or not comps:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(rows) + 2))
    yticks, ylabels = [], []
    prev_axis = None
    for i, (axis, metric) in enumerate(rows):
        y = len(rows) - i
        yticks.append(y)
        ylabels.append(f"{metric}" + (f"   [{axis}]" if axis != prev_axis else ""))
        prev_axis = axis
        for c in comps:
            d = next((d for d in c.deltas if d.metric == metric), None)
            if d is None or d.cliffs is None:
                continue
            color = _PAIR_COLORS.get(c.pair, "#555555")
            jitter = 0.15 if c.pair == "gpt" else -0.15
            if d.ci is not None:
                ax.plot(list(d.ci), [y + jitter] * 2, color=color, lw=2, alpha=0.5)
            ax.plot(
                d.cliffs, y + jitter, "o", color=color,
                markersize=7 if d.large_and_clear else 5,
                markeredgecolor="black" if d.large_and_clear else color,
            )
    ax.axvline(0, color="grey", lw=1)
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8)
    ax.set_xlim(-1.05, 1.05)
    ax.set_xlabel("Cliff's δ (old → new; >0 = new generation higher)")
    handles = [
        _plt().Line2D([0], [0], marker="o", color=_PAIR_COLORS.get(c.pair, "#555"),
                      linestyle="", label=f"{c.pair}: {c.old_model.split('/')[-1]} → {c.new_model}")
        for c in comps
    ]
    ax.legend(handles=handles, fontsize=8, loc="lower right")
    ax.set_title("Generational behavior deltas (task-clustered 95% CI)")
    fig.tight_layout()
    out = out_dir / "paired_deltas.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_axis_radar(
    profiles: list[BehaviorProfile], comps: list[PairComparison], out_dir: Path
) -> Path | None:
    """Per-lab radar over the four behavior axes (old dashed, new solid).

    Each axis value is the mean of its metrics after min-max normalization
    across the four models — a shape summary, not a statistic.
    """
    import math

    models = [m for c in comps for m in (c.old_model, c.new_model)]
    by_model = {m: [p for p in profiles if p.model == m and p.exit_reason != "crash"] for m in models}
    if not any(by_model.values()):
        return None
    axes_names = [a for a in AXES if a != "failure_modes"]

    def model_axis_score(model: str, axis: str) -> float | None:
        # mean over metrics of the model's mean value, min-max scaled across models
        vals = []
        for metric in AXES[axis]:
            per_model = {}
            for m, ps in by_model.items():
                xs = [float(getattr(p, metric)) for p in ps if getattr(p, metric) is not None]
                if xs:
                    per_model[m] = sum(xs) / len(xs)
            if model not in per_model or len(per_model) < 2:
                continue
            lo, hi = min(per_model.values()), max(per_model.values())
            if hi > lo:
                vals.append((per_model[model] - lo) / (hi - lo))
        return sum(vals) / len(vals) if vals else None

    plt = _plt()
    fig, axs = plt.subplots(
        1, len(comps), figsize=(5.5 * len(comps), 5), subplot_kw={"projection": "polar"}
    )
    if len(comps) == 1:
        axs = [axs]
    angles = [2 * math.pi * i / len(axes_names) for i in range(len(axes_names))]
    drew = False
    for ax, c in zip(axs, comps, strict=False):
        for model, style in ((c.old_model, "--"), (c.new_model, "-")):
            scores = [model_axis_score(model, a) for a in axes_names]
            if any(s is None for s in scores):
                continue
            drew = True
            closed = scores + scores[:1]
            ax.plot(angles + angles[:1], closed, style,
                    color=_PAIR_COLORS.get(c.pair, "#555"), label=model.split("/")[-1])
            ax.fill(angles + angles[:1], closed, alpha=0.08,
                    color=_PAIR_COLORS.get(c.pair, "#555"))
        ax.set_xticks(angles)
        ax.set_xticklabels(axes_names, fontsize=9)
        ax.set_yticklabels([])
        ax.set_title(c.lab, fontsize=11)
        ax.legend(fontsize=8, loc="lower right", bbox_to_anchor=(1.15, -0.1))
    if not drew:
        plt.close(fig)
        return None
    fig.suptitle("Behavior-axis shape, old (dashed) vs new (solid)")
    fig.tight_layout()
    out = out_dir / "axis_radar.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_efficiency_frontier(
    profiles: list[BehaviorProfile], comps: list[PairComparison], out_dir: Path
) -> Path | None:
    """x = median cost per run, y = solve rate; old→new arrow per lab."""
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.5, 5))
    drew = False
    for c in comps:
        pts = {}
        for model in (c.old_model, c.new_model):
            ps = [p for p in profiles if p.model == model and p.exit_reason != "crash"]
            solved = [p for p in ps if p.resolved]
            costs = sorted(p.cost_usd for p in ps)
            if not ps:
                continue
            pts[model] = (costs[len(costs) // 2], len(solved) / len(ps))
        if len(pts) == 2:
            (x0, y0), (x1, y1) = pts[c.old_model], pts[c.new_model]
            color = _PAIR_COLORS.get(c.pair, "#555")
            ax.annotate(
                "", xy=(x1, y1), xytext=(x0, y0),
                arrowprops={"arrowstyle": "->", "color": color, "lw": 1.5},
            )
            ax.plot([x0], [y0], "o", color=color, fillstyle="none", markersize=9)
            ax.plot([x1], [y1], "o", color=color, markersize=9)
            ax.annotate(c.old_model.split("/")[-1], (x0, y0), fontsize=8,
                        xytext=(4, 6), textcoords="offset points")
            ax.annotate(c.new_model, (x1, y1), fontsize=8,
                        xytext=(4, 6), textcoords="offset points")
            drew = True
    if not drew:
        plt.close(fig)
        return None
    ax.set_xlabel("median cost per run (USD)")
    ax.set_ylabel("solve rate")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Efficiency frontier: does the new generation buy solves with less?")
    fig.tight_layout()
    out = out_dir / "efficiency_frontier.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_pass_trajectories(
    run_dirs: list[Path], model_pairs: list[PairComparison], out_dir: Path
) -> Path | None:
    """Best-so-far test greenness vs normalized position, per model.

    Reads events.jsonl; each run contributes a step curve of "has a green test
    been observed by fraction t of the trajectory"; per model the mean curve.
    """
    curves: dict[str, list[list[float]]] = {}
    models = {m for c in model_pairs for m in (c.old_model, c.new_model)}
    for rdir in run_dirs:
        ev_path = rdir / "events.jsonl"
        run_path = rdir / "run.json"
        if not ev_path.exists() or not run_path.exists():
            continue
        run = json.loads(run_path.read_text())
        if run.get("model") not in models or run.get("exit_reason") == "crash":
            continue
        events = [json.loads(ln) for ln in ev_path.read_text().splitlines() if ln.strip()]
        test_marks = []
        for i, e in enumerate(events):
            # pytest counts live on the tool_result of a test command (the
            # adapter attaches them where the output is) — match any carrier.
            d = e.get("derived") or {}
            if "tests_passed" in d:
                green = (d.get("tests_failed") or 0) == 0 and (d.get("tests_passed") or 0) > 0
                test_marks.append((i / max(len(events) - 1, 1), green))
        if not test_marks:
            continue
        grid = [i / 20 for i in range(21)]
        best = 0.0
        curve = []
        for t in grid:
            for pos, green in test_marks:
                if pos <= t and green:
                    best = 1.0
            curve.append(best)
        curves.setdefault(run["model"], []).append(curve)
    if not curves:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for c in model_pairs:
        for model, style in ((c.old_model, "--"), (c.new_model, "-")):
            runs = curves.get(model)
            if not runs:
                continue
            grid = [i / 20 for i in range(21)]
            mean = [sum(r[i] for r in runs) / len(runs) for i in range(21)]
            ax.plot(grid, mean, style, color=_PAIR_COLORS.get(c.pair, "#555"),
                    label=f"{model.split('/')[-1]} (n={len(runs)})")
    ax.set_xlabel("normalized trajectory position")
    ax.set_ylabel("fraction of runs with a green test by t")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=8)
    ax.set_title("When (if ever) does each model first see green?")
    fig.tight_layout()
    out = out_dir / "pass_trajectories.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_outcome_composition(comps: list[PairComparison], out_dir: Path) -> Path | None:
    """Stacked bar per model: resolved / gave-up / grind-to-cap / confabulated."""
    order = ["resolved", "confabulated", "grind_to_cap", "gave_up_failing", "other_fail"]
    colors = {
        "resolved": "#55A868",
        "confabulated": "#C44E52",
        "grind_to_cap": "#8172B2",
        "gave_up_failing": "#CCB974",
        "other_fail": "#B0B0B0",
    }
    bars: list[tuple[str, dict[str, int]]] = []
    for c in comps:
        bars.append((c.old_model.split("/")[-1], c.outcome_counts.get("old", {})))
        bars.append((c.new_model, c.outcome_counts.get("new", {})))
    bars = [(label, counts) for label, counts in bars if counts]
    if not bars:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(1.6 * len(bars) + 2, 4.5))
    for x, (_label, counts) in enumerate(bars):
        total = sum(counts.values())
        bottom = 0.0
        for key in order:
            frac = counts.get(key, 0) / total if total else 0
            if frac:
                ax.bar(x, frac, bottom=bottom, color=colors[key], width=0.6,
                       label=key if x == 0 or key not in {k for _, cs in bars[:x] for k in cs} else None)
                bottom += frac
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([label for label, _ in bars], fontsize=8, rotation=15)
    ax.set_ylabel("fraction of non-crash runs")
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[k]) for k in order]
    ax.legend(handles, order, fontsize=8, loc="upper right")
    ax.set_title("How runs end, per model")
    fig.tight_layout()
    out = out_dir / "outcome_composition.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out
