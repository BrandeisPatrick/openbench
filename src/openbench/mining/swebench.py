"""Import human-annotated SWE-bench Verified instances as openbench tasks.

SWE-bench Verified (princeton-nlp/SWE-bench_Verified, 500 human-validated
instances) is the trusted, solvability-curated counterpart to our size-mined
tasks. The schema maps 1:1 onto our Task (we adopted SWE-bench's conventions),
so importing is a field rename + the same gold/test split we already do.

Use this to (a) validate the whole instrument against a benchmark with known
reference scores, and (b) get an uncontaminated capability read — these tasks
are self-contained text, human-confirmed solvable, unlike our mined PRs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from openbench import paths
from openbench.models import HardnessTier, Task

_PARQUET = (
    "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/"
    "resolve/main/data/test-00000-of-00001.parquet"
)

_DELIVERABLE = (
    "\n\n---\n\n## Deliverable\n\n"
    "Implement a complete, mergeable fix for the issue above. Existing tests "
    "must keep passing; stay in scope; do not modify existing tests."
)

# Parquet column names (FAIL_TO_PASS/PASS_TO_PASS are upper-case there) paired
# with the dict keys we expose. `difficulty` is the human annotation we keep.
_SELECT = (
    'instance_id, repo, base_commit, patch, test_patch, problem_statement, '
    '"FAIL_TO_PASS", "PASS_TO_PASS", version, difficulty'
)
_COLS = [
    "instance_id", "repo", "base_commit", "patch", "test_patch",
    "problem_statement", "fail_to_pass", "pass_to_pass", "version", "difficulty",
]


def list_instances(
    repo: str | None = None,
    max_patch: int | None = None,
    smallest_first: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """SWE-bench Verified instances as row dicts, including the human `difficulty`.

    Defaults to the FULL set (optionally one repo), ordered by instance_id — no
    bias toward small/easy patches (the old default silently grabbed the 20
    smallest). `smallest_first`/`limit`/`max_patch` remain available for quick
    spot pulls or to cap patch size, but none are applied unless asked.
    """
    import duckdb

    clauses: list[str] = []
    params: list = []
    if max_patch is not None:
        clauses.append("length(patch) <= ?")
        params.append(max_patch)
    if repo:
        clauses.append("repo = ?")
        params.append(repo)
    where = ("where " + " and ".join(clauses)) if clauses else ""
    order = "order by length(patch) asc" if smallest_first else "order by instance_id"
    tail = ""
    if limit is not None:
        tail = "limit ?"
        params.append(limit)
    con = duckdb.connect()
    rows = con.execute(f"select {_SELECT} from '{_PARQUET}' {where} {order} {tail}", params).fetchall()
    return [dict(zip(_COLS, r, strict=True)) for r in rows]


def stratify(
    rows: list[dict], per_cell: int, repos: list[str] | None = None
) -> tuple[list[dict], list[dict]]:
    """Pick up to ``per_cell`` instances for each (repo, difficulty) cell.

    Deterministic and patch-size-blind: within a cell, instances are sorted by
    instance_id and the first ``per_cell`` taken. Returns (selected, coverage),
    where coverage is one ``{repo, difficulty, available, selected, requested}``
    row per cell so callers can surface cells that under-fill — e.g. Verified has
    only 3 ``>4 hours`` instances, so a high per_cell can't be met there.
    """
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if repos and r["repo"] not in repos:
            continue
        by_cell[(r["repo"], r.get("difficulty") or "unknown")].append(r)

    selected: list[dict] = []
    coverage: list[dict] = []
    for (repo, diff), insts in sorted(by_cell.items()):
        insts.sort(key=lambda r: r["instance_id"])
        take = insts[:per_cell]
        selected.extend(take)
        coverage.append({
            "repo": repo, "difficulty": diff,
            "available": len(insts), "selected": len(take), "requested": per_cell,
        })
    return selected, coverage


def select_by_repo_and_difficulty(
    per_cell: int, repos: list[str] | None = None, max_patch: int | None = None
) -> tuple[list[dict], list[dict]]:
    """Fetch the full Verified set (optionally a repo subset) and stratify it."""
    rows = list_instances(max_patch=max_patch)
    return stratify(rows, per_cell, repos=repos)


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        items = list(v)
    elif isinstance(v, str):
        try:
            items = json.loads(v)
        except json.JSONDecodeError:
            items = [v] if v else []
    else:
        items = list(v) if v is not None else []
    # The dataset occasionally carries pytest OUTPUT artifacts (e.g. "[100%]")
    # in its test lists; a progress marker is never a test id, and passing it
    # to pytest fails the whole grading chunk.
    return [t for t in items if t and not t.startswith("[")]


def import_instance(inst: dict) -> Task:
    """Map one SWE-bench instance dict to an openbench Task on disk.

    Their `patch` is the gold solution MINUS tests; `test_patch` is the tests —
    exactly our convention (gold.patch = source only), so both map 1:1.
    """
    task_id = inst["instance_id"]
    tdir = paths.task_dir(task_id)
    tdir.mkdir(parents=True, exist_ok=True)

    # gold.patch = SOLUTION ONLY (SWE-bench's `patch`); the grader injects the
    # gold tests separately from test.patch. Concatenating them would make the
    # golden run carry the tests, so the grader's test.patch re-apply conflicts.
    (tdir / "gold.patch").write_text(inst["patch"] or "")
    (tdir / "test.patch").write_text(inst["test_patch"] or "")
    (tdir / "prompt.md").write_text((inst["problem_statement"] or "").strip() + _DELIVERABLE)

    # Preserve a previously-built image_tag if this task was imported before.
    prior = tdir / "task.json"
    prior_image = None
    if prior.exists():
        try:
            prior_image = Task.model_validate_json(prior.read_text()).image_tag
        except Exception:
            prior_image = None

    org, name = inst["repo"].split("/", 1)
    task = Task(
        image_tag=prior_image,
        task_id=task_id,
        repo=inst["repo"],
        pr_number=int(task_id.rsplit("-", 1)[-1]) if task_id.rsplit("-", 1)[-1].isdigit() else 0,
        base_commit=inst["base_commit"],
        merge_commit=inst["base_commit"],  # SWE-bench has no merge sha; grading uses gold patch
        merged_at=datetime.now(timezone.utc),
        tier=HardnessTier.MAIN,
        hardness_score=0.0,
        difficulty=inst.get("difficulty"),  # human annotation, kept for balancing
        source="swebench-verified",
        fail_to_pass=_as_list(inst["fail_to_pass"]),
        pass_to_pass=_as_list(inst["pass_to_pass"]),
    )
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))
    return task
