"""Markdown report generation over runs/ artifacts.

Reads metrics.json + grade.json files; tolerates zero or partial data so the
report can be regenerated at any point in the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from openbench import paths
from openbench.analysis.fingerprint import build_fingerprints, hypothesis_labels
from openbench.models import GradeReport, RunMetrics

_CAVEATS = """\
## Epistemic caveats

- **Behavioral propensities, not reward functions.** Fingerprints describe what
  a model tends to do in this harness; they cannot be inverted into the
  objective it was trained on. Hypothesis labels are hedged ("consistent
  with") by construction.
- **Harness-fixed comparisons only.** Numbers are comparable across models only
  because the harness, tools, prompts, and limits are held fixed. Do not
  compare against runs from other harnesses or settings.
- **Contamination flags.** Tasks are mined from PRs merged after the configured
  cutoff (configs/mining.yaml `min_merged_at`), but post-cutoff contamination
  of newer models cannot be ruled out; treat per-task resolution rates on
  recently trained models with suspicion.
"""


def _crashed(rdir: Path) -> bool:
    """Crashed runs (provider 4xx, harness fault) are infrastructure failures,
    not model behavior — a 2-turn crash trajectory must never enter a
    behavioral pool. Regression-tested in tests/test_bug_regressions.py."""
    rpath = rdir / "run.json"
    if not rpath.exists():
        return False
    import json

    return json.loads(rpath.read_text()).get("exit_reason") == "crash"


def _load_runs() -> list[tuple[RunMetrics | None, GradeReport | None]]:
    rows: list[tuple[RunMetrics | None, GradeReport | None]] = []
    if not paths.RUNS.exists():
        return rows
    for rdir in sorted(paths.RUNS.iterdir()):
        if not rdir.is_dir() or _crashed(rdir):
            continue
        mpath = rdir / "metrics.json"
        gpath = rdir / "grade.json"
        metrics = RunMetrics.model_validate_json(mpath.read_text()) if mpath.exists() else None
        grade = GradeReport.model_validate_json(gpath.read_text()) if gpath.exists() else None
        if metrics or grade:
            rows.append((metrics, grade))
    return rows


def _task_section(rows: list[tuple[RunMetrics | None, GradeReport | None]]) -> list[str]:
    lines = ["## Per-task results", ""]
    graded = [(m, g) for m, g in rows if g is not None]
    if not graded:
        lines += ["_No graded runs yet._", ""]
        return lines
    lines += [
        "| task | tier | model | resolved | f2p | p2p |",
        "|---|---|---|---|---|---|",
    ]
    for m, g in sorted(graded, key=lambda r: (r[1].task_id, r[0].model if r[0] else "")):
        tier = m.tier.value if m and m.tier else "-"
        model = m.model if m else "-"
        resolved = "yes" if g.resolved else "no"
        lines.append(
            f"| {g.task_id} | {tier} | {model} | {resolved} "
            f"| {g.f2p_pass_rate:.0%} | {g.p2p_pass_rate:.0%} |"
        )
    lines.append("")
    return lines


def _fingerprint_section(all_metrics: list[RunMetrics]) -> list[str]:
    lines = ["## Reward fingerprints", ""]
    if not all_metrics:
        lines += ["_No metrics yet._", ""]
        return lines
    fps = build_fingerprints(all_metrics)
    for model in sorted(fps):
        lines += [
            f"### {model}",
            "",
            "| metric | mean | 95% CI | z |",
            "|---|---|---|---|",
        ]
        for name, cell in fps[model].items():
            lo, hi = cell["ci"]
            lines.append(
                f"| {name} | {cell['mean']:.3f} | [{lo:.3f}, {hi:.3f}] | {cell['z']:+.2f} |"
            )
        lines.append("")

    lines += ["## Hypothesis labels", ""]
    labels = hypothesis_labels(fps)
    any_label = False
    for model in sorted(labels):
        if labels[model]:
            any_label = True
            lines.append(f"- **{model}**:")
            lines += [f"  - {label}" for label in labels[model]]
    if not any_label:
        lines.append("_No hypothesis thresholds crossed._")
    lines.append("")
    return lines


def _estimate_section(all_metrics: list[RunMetrics]) -> list[str]:
    lines = ["## Estimated reward composition (Tier 2)", ""]
    cohort = sorted({m.model for m in all_metrics})
    if len(cohort) < 2:
        lines += ["_Needs at least two models in the cohort (z-scores are relative)._", ""]
        return lines
    from openbench.analysis.estimate import collinear_pairs, estimate_mixture

    # Reward is only partially identifiable (arXiv 2411.15951); z-scores over a
    # small cohort are directional only. Be explicit about both.
    lines += [
        "> **Read weights *down* a model, not *across* models.** Each model's "
        "weights are a composition that sums to 1, so a component's share also "
        "reflects what *else* that model loads on — a smaller share is not a "
        "smaller magnitude. For cross-model \"how much X\" comparisons use the "
        "**Realized counterfactual rewards** table (absolute units), not these "
        "shares.",
        "",
    ]
    if len(cohort) < 4:
        lines += [
            f"> ⚠ Cohort = {len(cohort)} models. Weights are z-scored *within* this "
            "cohort, so they are **directional only** — identifying a reward needs "
            "more models/environments (arXiv 2106.03498). Components whose 95% CI "
            "includes zero are shown as `—` (not estimable), not ranked.",
            "",
        ]

    from openbench.analysis.estimate import prune_redundant_metrics

    _keep, prune = prune_redundant_metrics(all_metrics)
    if prune["dropped_zero_variance"] or prune["merged_correlated"]:
        lines.append(
            "> Metrics pruned before fitting (so one behavior isn't double-counted): "
        )
        if prune["dropped_zero_variance"]:
            lines.append(
                f"> zero-variance — {', '.join(prune['dropped_zero_variance'])}. "
            )
        for kept, dropped, r in prune["merged_correlated"]:
            lines.append(f"> redundant — `{dropped}` merged into `{kept}` (r={r:+.2f}). ")
        lines.append("")

    for model in sorted(estimates := estimate_mixture(all_metrics)):
        e = estimates[model]
        cond = "well-conditioned" if e.condition_number < 30 else (
            "ill-conditioned" if e.condition_number != float("inf") else "rank-deficient"
        )
        lines += [
            f"### {model}  (n={e.n_runs} runs · residual {e.residual:.2f} · "
            f"identifiability: {cond})",
            "",
            "| component | weight | 95% CI |",
            "|---|---|---|",
        ]
        for comp, w in sorted(e.weights.items(), key=lambda kv: -kv[1]):
            if e.estimable(comp):
                lo, hi = e.weight_cis[comp]
                lines.append(f"| {comp} | {w:.2f} | [{lo:.2f}, {hi:.2f}] |")
            else:
                lines.append(f"| {comp} | — (not estimable) | CI∋0 |")
        lines.append("")

    degenerate = collinear_pairs()
    if degenerate:
        lines += [
            "**Identifiability warnings** — these component pairs are "
            "near-(anti)parallel in the signature matrix and cannot be separated "
            "by passive observation; probe experiments are required:",
            "",
        ]
        lines += [f"- {a} vs {b} (cos {c:+.2f})" for a, b, c in degenerate]
        lines.append("")
    return lines


def _rewards_section() -> list[str]:
    """Counterfactual realized rewards: per-model mean of each candidate reward
    function evaluated on its actual trajectories (analysis/reward_scoring.py)."""
    import json

    lines = ["## Realized counterfactual rewards", ""]
    rows: dict[str, dict[str, list[float]]] = {}
    if paths.RUNS.exists():
        for rpath in sorted(paths.RUNS.glob("*/rewards.json")):
            rec = json.loads(rpath.read_text())
            bucket = rows.setdefault(rec["model"], {})
            for comp, value in rec.items():
                if comp in ("run_id", "model") or value is None:
                    continue
                bucket.setdefault(comp, []).append(float(value))
    if not rows:
        lines += ["_No reward scores yet (run `openbench analyze`)._", ""]
        return lines

    components = sorted({c for comps in rows.values() for c in comps})
    lines += [
        "_Reading: 'had the model been trained with reward X, how much X did this"
        " run earn?' A policy optimized for X earns high X on-distribution;"
        " compare within a column, not across columns._",
        "",
        "| model | " + " | ".join(components) + " |",
        "|---|" + "---|" * len(components),
    ]
    for model in sorted(rows):
        cells = [
            f"{sum(rows[model][c]) / len(rows[model][c]):+.3f}" if c in rows[model] else "-"
            for c in components
        ]
        lines.append(f"| {model} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _figures_section(out: Path) -> list[str]:
    """Generate E1/E2/E3 PNGs (docs/EXPERIMENTS.md) and embed them."""
    try:
        from openbench.report.figures import generate_figures

        written = generate_figures(out)
    except Exception as exc:  # matplotlib missing/broken: report still renders
        return [f"_Figures skipped: {exc}_", ""]
    if not written:
        return []
    import os

    lines = ["## Figures", ""]
    for p in written:
        # figures live in the canonical docs/figures dir, which is generally not
        # under the report's parent — use a relative path that walks up as needed.
        rel = os.path.relpath(p, out.parent)
        lines.append(f"![{p.stem}]({rel})")
        lines.append("")
    return lines


def generate_report(out: Path) -> Path:
    rows = _load_runs()
    all_metrics = [m for m, _ in rows if m is not None]

    lines = ["# openbench report", ""]
    if not rows:
        lines += ["_No data yet: no graded or analyzed runs found under runs/._", ""]

    # Failed-trajectory guard (arXiv 2604.02547): when nothing was solved, every
    # behavioral/reward read describes *failure modes*, not strategy on success —
    # and length confounds difficulty. Flag it loudly at the top.
    # Exclude golden/null CI fixtures (model "none") — they always resolve / fail
    # by construction and would mask a genuinely all-failed model cohort.
    graded = [
        g for m, g in rows
        if g is not None and not (m is not None and m.model == "none")
    ]
    if graded and all(g.f2p_pass_rate == 0 for g in graded):
        lines += [
            "> ⚠ **All trajectories failed (0% solve).** Behavioral metrics and "
            "reward estimates below reflect how these models *fail*, not how they "
            "succeed; trajectory length here tracks task difficulty, not strategy "
            "(arXiv 2604.02547). Treat as a difficulty-censored pilot until a "
            "solvable task band exists.",
            ">",
            "> Outcome-dependent probes are **not interpretable** on this cohort: "
            "`confabulated_completion` collapses to 'declared done without verifying' "
            "(its success clause is always true at 0% solve), and `honeypot_exploit` "
            "needs achievable success to mean anything. The robust signal here is raw "
            "verification behavior (recovery_rate, verified_before_done), not these probes.",
            "",
        ]
    lines += _task_section(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines += _figures_section(out)
    lines += _fingerprint_section(all_metrics)
    lines += _estimate_section(all_metrics)
    lines += _rewards_section()
    lines += [_CAVEATS]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    return out
