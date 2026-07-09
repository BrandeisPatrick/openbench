"""Markdown report: generational behavior comparison over >=1 pairs."""

from __future__ import annotations

from pathlib import Path

from openbench import paths
from openbench.behavior import figures
from openbench.behavior.compare import GEN_PAIRS, PairComparison, compare_pair
from openbench.behavior.pipeline import load_profiles
from openbench.behavior.profile import AXES

_CAVEATS = """\
> **Read me first.** This is a *descriptive* comparison, not hypothesis
> confirmation: n per model is small and the true degrees of freedom are the
> number of tasks, so every interval is a task-clustered bootstrap and the
> per-task sign agreement matters more than any single number. Contrasts are
> within-lab only (same wire protocol per pair — scaffold effects cancel);
> cross-lab differences are confounded by protocol and pricing. Solve rates
> are stratified by task provenance because SWE-bench-Verified PRs predate
> every model's training cutoff while mined PRs postdate the old generation's.
"""


def _fmt(v, digits: int = 2) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _solve_line(name: str, s: dict) -> str:
    if s.get("old_rate") is None and s.get("new_rate") is None:
        return ""
    ci = s.get("ci")
    ci_txt = f" (95% CI [{ci[0]:+.2f}, {ci[1]:+.2f}])" if ci else ""
    return (
        f"- **{name}**: {s['old_solved']}/{s['old_n']} → {s['new_solved']}/{s['new_n']}"
        f" (Δ {_fmt(s.get('diff'))}{ci_txt})\n"
    )


def _pair_section(comp: PairComparison) -> str:
    md = f"## {comp.lab}: `{comp.old_model}` → `{comp.new_model}`\n\n"
    md += (
        f"Runs: {comp.n_old} old / {comp.n_new} new"
        f" (crashes excluded: {comp.crashed_old} / {comp.crashed_new})\n\n"
    )
    md += "### Solve rate\n\n"
    for name, s in comp.solve.items():
        md += _solve_line(name, s)
    md += "\n### What changed (headline effects)\n\n"
    big = [d for d in comp.deltas if d.large_and_clear]
    if big:
        for d in sorted(big, key=lambda d: -abs(d.cliffs or 0)):
            direction = "↑" if (d.cliffs or 0) > 0 else "↓"
            md += (
                f"- `{d.metric}` [{d.axis}] {direction} — δ {_fmt(d.cliffs)}"
                f" (CI [{d.ci[0]:+.2f}, {d.ci[1]:+.2f}]), {d.sign_agreement};"
                f" median {_fmt(d.old_median)} → {_fmt(d.new_median)}\n"
            )
    else:
        md += "- no metric clears the large-effect bar (|δ| ≥ 0.474 with CI excluding 0)\n"
    md += "\n### Full delta table\n\n"
    md += "| axis | metric | old median | new median | Cliff's δ | 95% CI | tasks agree | n |\n"
    md += "|---|---|---:|---:|---:|---|---|---|\n"
    for axis in AXES:
        for d in comp.deltas:
            if d.axis != axis:
                continue
            ci = f"[{d.ci[0]:+.2f}, {d.ci[1]:+.2f}]" if d.ci else "—"
            mark = " **" if d.large_and_clear else ""
            md += (
                f"| {axis} | `{d.metric}`{mark.strip()} | {_fmt(d.old_median)} |"
                f" {_fmt(d.new_median)} | {_fmt(d.cliffs)} | {ci} |"
                f" {d.sign_agreement} | {d.n_old}/{d.n_new} |\n"
            )
    md += "\n### How runs end\n\n| outcome | old | new |\n|---|---:|---:|\n"
    keys = sorted(set(comp.outcome_counts.get("old", {})) | set(comp.outcome_counts.get("new", {})))
    for k in keys:
        md += (
            f"| {k} | {comp.outcome_counts.get('old', {}).get(k, 0)} |"
            f" {comp.outcome_counts.get('new', {}).get(k, 0)} |\n"
        )
    return md + "\n"


def generate_comparison_report(
    pair_names: list[str], out: Path | None = None, source: str | None = None
) -> Path:
    """Profiles must exist (run `openbench behavior` first); writes report + figures.

    `source` restricts the corpus to one task-provenance stratum (e.g.
    "swebench-verified") — used when a stratum's tasks are audited out.
    """
    out = out or (paths.RUNS / "behavior_report.md")
    profiles = load_profiles()
    if source is not None:
        profiles = [p for p in profiles if p.source == source]
    if not profiles:
        raise FileNotFoundError(
            "no profile.json files under runs/ — run `openbench behavior` first"
        )
    comps = [compare_pair(profiles, name) for name in pair_names]

    fig_dir = out.parent / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    kept_tasks = {p.task_id for p in profiles}
    run_dirs = (
        sorted(
            d for d in paths.RUNS.iterdir()
            if d.is_dir() and d.name.split("--")[0] in kept_tasks
        )
        if paths.RUNS.exists()
        else []
    )
    figs = {
        "Paired deltas": figures.fig_paired_deltas(comps, fig_dir),
        "Axis radar": figures.fig_axis_radar(profiles, comps, fig_dir),
        "Efficiency frontier": figures.fig_efficiency_frontier(profiles, comps, fig_dir),
        "Pass trajectories": figures.fig_pass_trajectories(run_dirs, comps, fig_dir),
        "Outcome composition": figures.fig_outcome_composition(comps, fig_dir),
    }

    md = "# Generational behavior comparison\n\n"
    if source is not None:
        md += f"> **Corpus restricted to `source == {source}` tasks.**\n\n"
    md += _CAVEATS + "\n"
    for name, path in figs.items():
        if path is not None:
            md += f"![{name}]({path.relative_to(out.parent)})\n\n"
    for comp in comps:
        md += _pair_section(comp)
    md += "## Pairs\n\n"
    for name, pair in GEN_PAIRS.items():
        md += f"- `{name}`: {pair.old_model} → {pair.new_model} ({pair.lab})\n"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    return out
