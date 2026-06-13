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


def list_instances(repo: str | None = None, limit: int = 20, max_patch: int = 1500) -> list[dict]:
    """Smallest (easiest) SWE-bench Verified instances, optionally one repo."""
    import duckdb

    where = "where length(patch) <= ?"
    params: list = [max_patch]
    if repo:
        where += " and repo = ?"
        params.append(repo)
    con = duckdb.connect()
    rows = con.execute(
        f"select instance_id, repo, base_commit, patch, test_patch, "
        f"problem_statement, \"FAIL_TO_PASS\", \"PASS_TO_PASS\", version "
        f"from '{_PARQUET}' {where} order by length(patch) asc limit ?",
        [*params, limit],
    ).fetchall()
    cols = ["instance_id", "repo", "base_commit", "patch", "test_patch",
            "problem_statement", "fail_to_pass", "pass_to_pass", "version"]
    return [dict(zip(cols, r, strict=True)) for r in rows]


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return list(v)
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return [v] if v else []
    return list(v) if v is not None else []


def import_instance(inst: dict) -> Task:
    """Map one SWE-bench instance dict to an openbench Task on disk.

    Their `patch` is the gold solution MINUS tests; `test_patch` is the tests.
    Our gold.patch is the full diff, so we concatenate the two — equivalent.
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
        fail_to_pass=_as_list(inst["fail_to_pass"]),
        pass_to_pass=_as_list(inst["pass_to_pass"]),
    )
    (tdir / "task.json").write_text(task.model_dump_json(indent=2))
    return task
