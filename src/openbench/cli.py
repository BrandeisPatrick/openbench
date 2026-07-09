"""openbench CLI: mine -> build-task -> validate -> build-env -> run -> grade -> behavior -> compare."""

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


def _enable_verbose_logging() -> None:
    """Stream the harness's per-turn INFO logs to stderr (for `run --verbose`)."""
    import logging
    import sys

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("openbench")
    lg.handlers.clear()
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.propagate = False


@app.command()
def run(
    task_id: str = typer.Argument(...),
    runner: str = typer.Option("native", help="native (=tooluse) | tooluse | claude-native | mini-swe | golden | null"),
    model: str = typer.Option("claude-sonnet-4-6"),
    wall_clock_s: int = typer.Option(5400),
    max_turns: int = typer.Option(200),
    max_cost_usd: float = typer.Option(15.0),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Stream each turn (reasoning, command, result) live."),
) -> None:
    """Run an agent harness against a task and capture the raw transcript."""
    from openbench.models import RunLimits
    from openbench.runners import get_runner, resolve_runner
    from openbench.runners.execute import execute_run

    if verbose:
        _enable_verbose_logging()
    limits = RunLimits(wall_clock_s=wall_clock_s, max_turns=max_turns, max_cost_usd=max_cost_usd)
    runner_obj = get_runner(resolve_runner(runner, model))
    result = execute_run(task_id=task_id, runner=runner_obj, model=model, limits=limits)
    console.print(f"[green]Run finished:[/green] {result.run_id} ({result.exit_reason})")
    console.print(f"  cost: ${result.total_cost_usd:.2f}  turns: {result.num_turns}")


@app.command("run-matrix")
def run_matrix_cmd(
    tasks: str = typer.Option(..., help="Comma-separated task ids"),
    models: str = typer.Option(..., help="Comma-separated model names"),
    runner: str = typer.Option("native"),
    reps: int = typer.Option(1, help="Repetitions per (task × model) cell"),
    concurrency: int = typer.Option(3, help="Max runs in parallel"),
    max_turns: int = typer.Option(80),
    wall_clock_s: int = typer.Option(3600),
    max_cost_usd: float = typer.Option(4.0),
) -> None:
    """Run every (task × model × rep) cell in parallel, isolated containers."""
    from openbench.models import RunLimits
    from openbench.runners.matrix import MatrixCell, run_matrix

    cells = [
        MatrixCell(task_id=t.strip(), model=m.strip(), runner=runner)
        for t in tasks.split(",") if t.strip()
        for m in models.split(",") if m.strip()
        for _ in range(max(reps, 1))
    ]
    limits = RunLimits(max_turns=max_turns, wall_clock_s=wall_clock_s, max_cost_usd=max_cost_usd)
    console.print(f"[bold]running {len(cells)} cells, {concurrency} at a time[/bold]")

    def _done(cell) -> None:
        if cell.error:
            console.print(f"[red]✗ {cell.task_id} / {cell.model}: {cell.error}[/red]")
        else:
            r = cell.result
            console.print(
                f"[green]✓[/green] {cell.task_id} / {cell.model.split('/')[-1]} "
                f"({r.exit_reason}, {r.num_turns} turns, ${r.total_cost_usd:.2f})"
            )

    run_matrix(cells, limits, max_concurrency=concurrency, on_done=_done)
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
def behavior(
    run_id: Optional[str] = typer.Argument(None, help="One run; omit for all runs"),
) -> None:
    """Normalize traces and compute per-run behavior profiles (offline)."""
    from openbench.behavior import profile_runs

    profiles = profile_runs(run_id=run_id)
    table = Table("run_id", "model", "resolved", "test_runs", "verified", "exit")
    for p in profiles:
        table.add_row(
            p.run_id,
            p.model.split("/")[-1],
            str(p.resolved),
            str(p.test_run_count),
            str(p.verified_before_done),
            p.exit_reason or "-",
        )
    console.print(table)
    console.print(f"[green]{len(profiles)} profile(s) written[/green]")


@app.command()
def compare(
    pair: list[str] = typer.Option(
        ["deepseek", "gpt"], "--pair", help="Generation pair(s) to compare"
    ),
    out: Path = typer.Option(Path("runs/behavior_report.md"), help="Output markdown path"),
    source: Optional[str] = typer.Option(
        None, help="Restrict to one task-provenance stratum (e.g. swebench-verified)"
    ),
) -> None:
    """Generate the generational behavior-comparison report (offline)."""
    from openbench.behavior import GEN_PAIRS, generate_comparison_report

    unknown = [p for p in pair if p not in GEN_PAIRS]
    if unknown:
        console.print(f"[red]unknown pair(s) {unknown}[/red]; known: {sorted(GEN_PAIRS)}")
        raise typer.Exit(1)
    path = generate_comparison_report(pair, out, source=source)
    console.print(f"[green]Report written:[/green] {path}")


@app.command("import-swebench")
def import_swebench(
    per_cell: int = typer.Option(1, help="Instances per (repo × difficulty) cell"),
    repos: Optional[str] = typer.Option(
        None, help="Comma-separated repos to limit to (default: all 12 Verified repos)"
    ),
    max_patch: Optional[int] = typer.Option(None, help="Optional max gold-patch size in bytes"),
) -> None:
    """Import SWE-bench Verified instances, balanced across repo × difficulty.

    Keeps each instance's human difficulty label and fills every (repo,
    difficulty) cell up to --per-cell — no bias toward the smallest patches.
    Cells it can't fill (e.g. the 3 '>4 hours' instances) are flagged.
    """
    from openbench.mining.swebench import import_instance, select_by_repo_and_difficulty

    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else None
    selected, coverage = select_by_repo_and_difficulty(per_cell, repos=repo_list, max_patch=max_patch)
    if not selected:
        console.print("[yellow]no matching instances[/yellow]")
        return
    for inst in selected:
        t = import_instance(inst)
        console.print(f"[green]imported[/green] {t.task_id}  [{t.difficulty}]  (f2p {len(t.fail_to_pass)})")

    table = Table("repo", "difficulty", "available", "imported")
    short = 0
    for c in coverage:
        gap = max(0, c["requested"] - c["selected"])
        short += gap
        table.add_row(
            c["repo"], c["difficulty"], str(c["available"]),
            str(c["selected"]) + (f" [red](-{gap})[/red]" if gap else ""),
        )
    console.print(table)
    msg = f"[bold]{len(selected)} imported[/bold]"
    if short:
        msg += f"; [yellow]{short} cell-slots unfilled (scarce buckets — mine the hard end)[/yellow]"
    console.print(msg)


@app.command("assess-difficulty")
def assess_difficulty_cmd(
    task_id: Optional[str] = typer.Argument(
        None, help="One task; omit to label every unlabeled (mined) task"
    ),
    model: str = typer.Option("claude-sonnet-4-6", help="Judge model for the PR review"),
    force: bool = typer.Option(False, help="Re-label even if a difficulty is already set"),
) -> None:
    """Assign a difficulty label to mined task(s) by reviewing the PR (one model call each)."""
    from openbench.tasks.difficulty import assess_difficulty, tasks_missing_difficulty

    ids = [task_id] if task_id else tasks_missing_difficulty()
    if not ids:
        console.print("[yellow]nothing to label[/yellow] (every task already has a difficulty)")
        return
    for tid in ids:
        t = assess_difficulty(tid, model=model, force=force)
        console.print(f"[green]{tid}[/green]  [{t.difficulty}]  {t.difficulty_note or ''}")


@app.command("list-tasks")
def list_tasks() -> None:
    """List tasks in the dataset with their difficulty + repo spread."""
    from collections import Counter

    from openbench import paths
    from openbench.models import DIFFICULTY_LEVELS, Task

    table = Table("task_id", "difficulty", "tier", "f2p", "p2p", "image")
    by_difficulty: Counter[str] = Counter()
    by_repo: Counter[str] = Counter()
    if paths.TASKS.exists():
        for tj in sorted(paths.TASKS.glob("*/task.json")):
            t = Task.model_validate_json(tj.read_text())
            table.add_row(
                t.task_id, t.difficulty or "-", t.tier.value,
                str(len(t.fail_to_pass)), str(len(t.pass_to_pass)), t.image_tag or "-",
            )
            by_difficulty[t.difficulty or "(unlabeled)"] += 1
            by_repo[t.repo] += 1
    console.print(table)
    # Distribution summaries — the two axes we're balancing for.
    diff_order = [*DIFFICULTY_LEVELS, "(unlabeled)"]
    diff_summary = "  ".join(
        f"{lvl}: {by_difficulty[lvl]}" for lvl in diff_order if by_difficulty.get(lvl)
    )
    console.print(f"[bold]difficulty[/bold]  {diff_summary or '(none)'}")
    console.print(f"[bold]repos[/bold]       {len(by_repo)} — " + "  ".join(
        f"{r.split('/')[-1]}: {n}" for r, n in by_repo.most_common()
    ))


def _load_dotenv() -> None:
    """Load ROOT/.env into the environment (existing vars win, never overridden).

    The docs say `cp .env.example .env` is enough; without this, keys had to be
    exported manually. Plain KEY=VALUE lines only — no interpolation.
    """
    import os

    from openbench import paths

    env_file = paths.ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_dotenv()
    app()


if __name__ == "__main__":
    main()
