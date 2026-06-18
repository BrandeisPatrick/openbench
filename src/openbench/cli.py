"""openbench CLI: mine -> build-task -> validate -> build-env -> run -> grade -> analyze -> report."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="openbench", no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


@app.command()
def mine(
    config: Path = typer.Option(Path("configs/mining.yaml"), help="Mining config"),
    repo: Optional[str] = typer.Option(None, help="Mine a single org/repo instead of the config allowlist"),
    limit: int = typer.Option(50, help="Max candidates per repo"),
) -> None:
    """Search GitHub for merged super-long PRs, score hardness, write candidates JSONL."""
    from openbench.mining.pipeline import mine_candidates

    out = mine_candidates(config_path=config, only_repo=repo, limit_per_repo=limit)
    console.print(f"[green]Wrote {out.count} candidates -> {out.path}[/green]")
    for tier, n in sorted(out.tier_counts.items()):
        console.print(f"  {tier}: {n}")


@app.command("build-task")
def build_task(
    repo: str = typer.Option(..., help="org/repo"),
    pr: int = typer.Option(..., help="PR number"),
) -> None:
    """Construct a task dir (prompt.md, gold.patch, test.patch, f2p/p2p) from a merged PR."""
    from openbench.tasks.construct import build_task as _build

    task = _build(repo=repo, pr_number=pr)
    console.print(f"[green]Task built: {task.task_id}[/green] -> datasets/tasks/{task.task_id}/")
    console.print(f"  F2P tests: {len(task.fail_to_pass)}  P2P tests: {len(task.pass_to_pass)}")


@app.command()
def validate(
    task_id: str = typer.Argument(...),
    rounds: int = typer.Option(3, help="Flakiness re-run rounds"),
) -> None:
    """Run the base-fails/merged-passes gate for a task (requires Docker)."""
    from openbench.tasks.validate import validate_task

    result = validate_task(task_id, rounds=rounds)
    status = "[green]ACCEPTED[/green]" if result.accepted else "[red]REJECTED[/red]"
    console.print(f"{task_id}: {status}")
    console.print_json(result.model_dump_json())


@app.command("build-env")
def build_env(task_id: str = typer.Argument(...)) -> None:
    """Build the per-task Docker image pinned at the base commit."""
    from openbench.envs.builder import build_task_image

    tag = build_task_image(task_id)
    console.print(f"[green]Built image:[/green] {tag}")


@app.command()
def run(
    task_id: str = typer.Argument(...),
    runner: str = typer.Option("native", help="native | tooluse | claude-native | mini-swe | golden | null"),
    model: str = typer.Option("claude-sonnet-4-6"),
    wall_clock_s: int = typer.Option(5400),
    max_turns: int = typer.Option(200),
    max_cost_usd: float = typer.Option(15.0),
) -> None:
    """Run an agent harness against a task and capture the raw transcript."""
    from openbench.models import RunLimits
    from openbench.runners import get_runner
    from openbench.runners.execute import execute_run

    limits = RunLimits(wall_clock_s=wall_clock_s, max_turns=max_turns, max_cost_usd=max_cost_usd)
    result = execute_run(task_id=task_id, runner=get_runner(runner), model=model, limits=limits)
    console.print(f"[green]Run finished:[/green] {result.run_id} ({result.exit_reason})")
    console.print(f"  cost: ${result.total_cost_usd:.2f}  turns: {result.num_turns}")


@app.command("run-matrix")
def run_matrix_cmd(
    tasks: str = typer.Option(..., help="Comma-separated task ids"),
    models: str = typer.Option(..., help="Comma-separated model names"),
    runner: str = typer.Option("native"),
    concurrency: int = typer.Option(3, help="Max runs in parallel"),
    limits_config: Path = typer.Option(
        Path("configs/runners/limits.yaml"),
        help="Per-model limits YAML (default + per-model turn/cost/wall caps)",
    ),
    max_turns: int = typer.Option(100, help="Fallback cap when no config / model unlisted"),
    wall_clock_s: int = typer.Option(2400, help="Fallback cap when no config / model unlisted"),
    max_cost_usd: float = typer.Option(4.0, help="Fallback cap when no config / model unlisted"),
) -> None:
    """Run every (task × model) cell in parallel, isolated containers.

    Caps are resolved per model from --limits-config (default + per-model
    overrides); the --max-* flags are the fallback for models not listed there.
    """
    from openbench.models import RunLimits
    from openbench.runners.matrix import MatrixCell, load_limits, run_matrix

    fallback = RunLimits(max_turns=max_turns, wall_clock_s=wall_clock_s, max_cost_usd=max_cost_usd)
    resolve = load_limits(limits_config if limits_config.exists() else None, fallback)

    cells = [
        MatrixCell(task_id=t.strip(), model=m.strip(), runner=runner, limits=resolve(m.strip()))
        for t in tasks.split(",") if t.strip()
        for m in models.split(",") if m.strip()
    ]
    src = str(limits_config) if limits_config.exists() else "fallback flags (no config)"
    console.print(f"[bold]running {len(cells)} cells, {concurrency} at a time[/bold]  limits: {src}")
    # Show each model's resolved caps once, so cost is predictable before launch.
    for m in dict.fromkeys(c.model for c in cells):
        lim = resolve(m)
        console.print(
            f"  [dim]{m}[/dim]: ≤{lim.max_turns} turns, ≤${lim.max_cost_usd:.2f}, ≤{lim.wall_clock_s}s"
        )

    def _done(cell) -> None:
        if cell.error:
            console.print(f"[red]✗ {cell.task_id} / {cell.model}: {cell.error}[/red]")
        else:
            r = cell.result
            console.print(
                f"[green]✓[/green] {cell.task_id} / {cell.model.split('/')[-1]} "
                f"({r.exit_reason}, {r.num_turns} turns, ${r.total_cost_usd:.2f})"
            )

    run_matrix(cells, fallback, max_concurrency=concurrency, on_done=_done)
    console.print("[bold green]matrix done[/bold green] — grade with `openbench grade <run_id>`")


@app.command()
def grade(run_id: str = typer.Argument(...)) -> None:
    """Grade a run: apply patch, anti-cheat, build, F2P, P2P."""
    from openbench.grading.mergeability import grade_run

    report = grade_run(run_id)
    verdict = "[green]RESOLVED[/green]" if report.resolved else "[red]NOT RESOLVED[/red]"
    console.print(f"{run_id}: {verdict}")
    console.print(
        f"  applies={report.applies_cleanly} builds={report.builds} "
        f"f2p={report.f2p_pass_rate:.0%} p2p={report.p2p_pass_rate:.0%} "
        f"tampering={report.anticheat.test_tampering}"
    )


@app.command()
def analyze(
    run_id: Optional[str] = typer.Option(None, help="Analyze one run; omit for all runs"),
) -> None:
    """Normalize traces, compute behavioral metrics, ingest into DuckDB."""
    from openbench.analysis.pipeline import analyze_runs

    metrics = analyze_runs(run_id=run_id)
    table = Table("run_id", "test_runs", "edits", "verified_before_done", "early_stop", "revert_count")
    for m in metrics:
        table.add_row(
            m.run_id,
            str(m.test_run_count),
            str(m.file_edit_count),
            str(m.verified_before_done),
            str(m.early_stop),
            str(m.revert_count),
        )
    console.print(table)


@app.command()
def report(
    out: Path = typer.Option(Path("runs/report.md"), help="Output markdown path"),
) -> None:
    """Generate the cross-model report with reward fingerprints."""
    from openbench.report.generate import generate_report

    path = generate_report(out)
    console.print(f"[green]Report written:[/green] {path}")


@app.command()
def demo() -> None:
    """Build a reward-fingerprint report from local run traces (runs/), offline.
    No API keys, no Docker, no GitHub token required — needs local runs present
    (generate them with `openbench run-matrix`, or keep a corpus under runs/)."""
    from openbench import paths
    from openbench.report.generate import generate_report

    runs = paths.RUNS
    n = sum(1 for d in runs.iterdir() if (d / "metrics.json").exists()) if runs.exists() else 0
    if n == 0:
        console.print(
            "[yellow]No local runs found under runs/[/yellow] — run a matrix first "
            "([bold]openbench run-matrix[/bold]) or restore a run corpus."
        )
        raise typer.Exit(1)
    out = paths.ROOT / "report.md"
    path = generate_report(out)
    console.print(f"[green]Report written:[/green] {path}  ({n} local runs)")
    console.print(
        "Per-model reward fingerprints, computed offline — no keys or Docker. "
        "Open the file, or run [bold]openbench analyze[/bold] on the same traces."
    )


@app.command("import-swebench")
def import_swebench(
    repo: Optional[str] = typer.Option("sympy/sympy", help="Limit to one repo (proven env)"),
    n: int = typer.Option(3, help="How many of the smallest (easiest) instances"),
    max_patch: int = typer.Option(1500, help="Max gold-patch size in bytes"),
) -> None:
    """Import human-validated SWE-bench Verified instances as tasks (clean capability test)."""
    from openbench.mining.swebench import import_instance, list_instances

    insts = list_instances(repo=repo, limit=n, max_patch=max_patch)
    if not insts:
        console.print("[yellow]no matching instances[/yellow]")
        return
    for inst in insts:
        t = import_instance(inst)
        console.print(
            f"[green]imported[/green] {t.task_id}  "
            f"(f2p {len(t.fail_to_pass)}, p2p {len(t.pass_to_pass)}, patch {len(inst['patch'])}b)"
        )


@app.command("build-honeypot")
def build_honeypot(task_id: str = typer.Argument(..., help="A validated parent task id")) -> None:
    """Create a honeypot variant: weak visible smoke tests, strict hidden grading."""
    from openbench.tasks.honeypot import build_honeypot as _build

    hp = _build(task_id)
    console.print(f"[green]Honeypot built:[/green] {hp.task_id} (image: {hp.image_tag})")
    console.print("  run it like any task; grade records honeypot_smoke_passed")


@app.command("build-impossible")
def build_impossible(task_id: str = typer.Argument(..., help="A validated parent task id")) -> None:
    """Create a contradictory-spec variant to probe sycophancy vs push-back."""
    from openbench.tasks.impossible import build_impossible as _build

    imp = _build(task_id)
    console.print(f"[green]Impossible probe built:[/green] {imp.task_id}")
    console.print("  run it; metrics records flagged_impossible (did the model push back?)")


@app.command("list-tasks")
def list_tasks() -> None:
    """List validated tasks in the dataset."""
    from openbench import paths
    from openbench.models import Task

    table = Table("task_id", "tier", "hardness", "f2p", "p2p", "image")
    if paths.TASKS.exists():
        for tj in sorted(paths.TASKS.glob("*/task.json")):
            t = Task.model_validate_json(tj.read_text())
            table.add_row(
                t.task_id, t.tier.value, f"{t.hardness_score:.2f}",
                str(len(t.fail_to_pass)), str(len(t.pass_to_pass)), t.image_tag or "-",
            )
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
