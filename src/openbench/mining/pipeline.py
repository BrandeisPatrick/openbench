"""End-to-end mining: search -> filter -> hardness-score -> candidates.jsonl."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml
from rich.console import Console

from openbench import paths
from openbench.mining import github
from openbench.mining.filters import passes_filters
from openbench.mining.hardness import score_candidates
from openbench.models import PRCandidate
from openbench.tasks.tests_split import is_test_path

console = Console()


@dataclass
class MiningOutput:
    count: int
    path: Path
    tier_counts: dict[str, int]


def _count_test_defs_in_test_files(diff_text: str) -> int:
    """Count added `def test_*` lines inside test files of a full unified diff."""
    from openbench.tasks.tests_split import split_patch

    _, test_patch = split_patch(diff_text)
    if not test_patch:
        return 0
    return sum(
        1
        for line in test_patch.splitlines()
        if line.startswith("+") and line.lstrip("+").lstrip().startswith("def test_")
    )


def mine_candidates(config_path: Path, only_repo: str | None, limit_per_repo: int) -> MiningOutput:
    cfg = yaml.safe_load(config_path.read_text())
    repos: list[str] = [only_repo] if only_repo else list(cfg["repos"])
    merged_after = str(cfg["min_merged_at"])

    pool: list[PRCandidate] = []
    for repo in repos:
        console.log(f"[bold]{repo}[/bold]: searching merged PRs since {merged_after}")
        try:
            cands = github.search_long_prs(
                repo,
                merged_after=merged_after,
                limit=limit_per_repo,
                prescreen=cfg.get("filters"),
            )
        except Exception as exc:
            console.log(f"[red]{repo}: search failed ({exc}); skipping repo[/red]")
            continue
        kept = 0
        for c in cands:
            try:
                file_entries = github.fetch_pr_files(c.repo, c.pr_number)
                files = [f["filename"] for f in file_entries]
                total_loc = sum(
                    int(f.get("additions") or 0) + int(f.get("deletions") or 0)
                    for f in file_entries
                )
                test_loc = sum(
                    int(f.get("additions") or 0) + int(f.get("deletions") or 0)
                    for f in file_entries
                    if is_test_path(f["filename"])
                )
                test_loc_fraction = test_loc / total_loc if total_loc else 0.0
                # The REST files endpoint omits `patch` for large files, so the
                # hydrated test-function count undercounts on exactly the PRs we
                # want. Recount from the full diff when it looks suspect.
                if c.test_files_changed and c.test_functions_changed < int(
                    cfg["filters"].get("min_test_functions", 0)
                ):
                    diff = github.fetch_pr_diff(c.repo, c.pr_number)
                    c.test_functions_changed = max(
                        c.test_functions_changed, _count_test_defs_in_test_files(diff)
                    )
                ok, reasons = passes_filters(
                    c, cfg, files=files, test_loc_fraction=test_loc_fraction
                )
            except Exception as exc:
                console.log(f"[red]{repo}#{c.pr_number}: filter check failed ({exc}); skipping[/red]")
                continue
            if ok:
                pool.append(c)
                kept += 1
            else:
                console.log(f"  {repo}#{c.pr_number} rejected: {', '.join(reasons)}")
        console.log(f"{repo}: {kept}/{len(cands)} candidates passed filters")

    scored = score_candidates(pool, cfg)

    out_path = paths.CANDIDATES / "candidates.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        for c in scored:
            fh.write(c.model_dump_json() + "\n")
    console.log(f"wrote {len(scored)} candidates -> {out_path}")

    tier_counts = Counter(c.tier.value for c in scored if c.tier is not None)
    return MiningOutput(count=len(scored), path=out_path, tier_counts=dict(tier_counts))
