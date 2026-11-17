"""Run manifest for the frozen corpora under research/corpus/.

Generates two CSV files next to the corpora and verifies them:

  research/corpus/runs.csv   one row per run directory
  research/corpus/tasks.csv  one row per task that appears in the corpus

Both files are GENERATED. To change them: edit the constants below, re-run
this script, commit the result.

Scope: the round 1 batches. A batch folder that carries its own ledger.jsonl
(round 2 onward, written by `openbench run-round`) is indexed by that ledger
and skipped here; its analysis reads the ledger, never runs.csv.  `--check` regenerates both in memory and
exits 1 if the committed files differ or if any invariant listed under
"Invariants" is broken.  Analysis code reads runs.csv and never parses
directory names.

runs.csv columns
----------------
run_id            directory name; asserted equal to run.json run_id
batch             parent folder under research/corpus/
kind              model | golden | null  (from run.json harness)
harness           run.json harness verbatim (tooluse, gpt-responses, golden, null)
task_id           run.json task_id
model             short name used by analysis (MODELS table); "none" for fixtures
model_raw         run.json model string verbatim. Fixture runs may carry the
                  runner's default stamp (e.g. claude-sonnet-4-6): no model ran.
lab               deepseek | openai | kimi; "" for fixtures
generation        1, 2, 3 within the lab's lineage; "" for fixtures
host              openrouter | first-party; "" for fixtures
started_at        run.json started_at
exit_reason       run.json exit_reason (completed, crash, turn_cap, cost_cap, timeout)
cap_usd, cap_turns, cap_wall_s
                  run limits. From run.json `limits` when recorded (harness
                  records them since 2026-08-02); else from BATCH_CAPS, the
                  values stated in the batch README; else "".
caps_source       run.json | README | ""
condition         base | raised-cap | fixture
stale_image       1 if raw_transcript.jsonl contains STALE_MARKER: the
                  pytest-5262 task image was silently stale for runs on/after
                  2026-07-12 and the repo's pytest could not start inside the
                  workspace (Python 3.12 removed `imp`). Else 0.
resolved          1 if grade.json says applies_cleanly and builds and
                  f2p_passed non-empty and f2p_failed empty and p2p_failed
                  empty; else 0.  Same rule as the pre-registered
                  convergence.py header.
image_id          grade.json image_id; "" when absent (crashed runs were
                  never graded on an image)
extra_files       files in the run dir beyond the standard four
                  (run.json, raw_transcript.jsonl, workspace.patch,
                  grade.json), ';'-joined
included          1 if kind == model and exit_reason != crash and
                  condition == base; else 0
exclusion_reason  why included == 0; "" otherwise

No task filter and no repeat cap live here. Each analysis script states its
own (convergence.py restricts to the four verified tasks and asserts three
runs per cell).

tasks.csv columns
-----------------
task_id           every task_id that appears in runs.csv
image_id          the single grading image every graded run of the task used
golden_runs       run_ids of the golden-fixture receipts for that image, ';'-joined
gold_patch_sha256, test_patch_sha256
                  of datasets/tasks/<task_id>/gold.patch and test.patch

Invariants (checked on every generate and on --check)
-----------------------------------------------------
- every run dir has the standard four files and run.json run_id == dir name
- harness is one of tooluse, gpt-responses, golden, null
- model runs have model_raw in MODELS; fixture runs have it in FIXTURE_STAMPS
- exit_reason == crash  <=>  runner_error.log present
- all graded runs of a task share one image_id
- every SEPARATE_CONDITION key is an existing run dir
- gold.patch and test.patch exist for every task in the corpus
- --check only: regenerated CSV text == committed CSV text

Hand-entered facts
------------------
Exactly three: MODELS, BATCH_CAPS, SEPARATE_CONDITION.  Nothing else in
this file or in the CSVs is typed by a person.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "research" / "corpus"
TASKS = ROOT / "datasets" / "tasks"
RUNS_CSV = CORPUS / "runs.csv"
TASKS_CSV = CORPUS / "tasks.csv"

STANDARD_FILES = {"run.json", "raw_transcript.jsonl", "workspace.patch", "grade.json"}
HARNESSES = {"tooluse", "gpt-responses", "golden", "null"}
FIXTURE_HARNESSES = {"golden", "null"}
STALE_MARKER = "No module named 'imp'"

# run.json model string -> (model, lab, generation, host)
MODELS = {
    "openrouter/deepseek/deepseek-r1-0528": ("r1-0528", "deepseek", 1, "openrouter"),
    "openrouter/deepseek/deepseek-v3.2": ("v3.2", "deepseek", 2, "openrouter"),
    "deepseek-v4-pro": ("v4-pro", "deepseek", 3, "first-party"),
    "o1": ("o1", "openai", 1, "first-party"),
    "o3": ("o3", "openai", 2, "first-party"),
    "gpt-5.5": ("gpt-5.5", "openai", 3, "first-party"),
    "openrouter/moonshotai/kimi-k2-thinking": ("kimi-k2-thinking", "kimi", 1, "openrouter"),
    "kimi-k2.6": ("kimi-k2.6", "kimi", 2, "first-party"),
    "kimi-k3": ("kimi-k3", "kimi", 3, "first-party"),
}
# Model strings the runner stamps on golden / null fixture runs. No model ran.
FIXTURE_STAMPS = {"none", "claude-sonnet-4-6"}

# (batch, model) -> (cap_usd, cap_turns, cap_wall_s or None) for runs whose
# run.json predates cap recording (2026-08-02). Values as stated in each
# batch README; None where the README does not state the wall clock.
BATCH_CAPS = {
    ("runs-2026-07-generational-study", "gpt-5.5"): (2.5, 100, 7200),
    ("runs-2026-07-generational-study", "v4-pro"): (2.5, 100, 7200),
    ("runs-2026-07-thinking-extension", "o1"): (10.0, 100, 7200),
    ("runs-2026-07-thinking-extension", "o3"): (10.0, 100, 7200),
    ("runs-2026-07-thinking-extension", "r1-0528"): (2.5, 100, 14400),
    ("runs-2026-07-thinking-extension", "v3.2"): (2.5, 100, None),
    ("runs-2026-07-thinking-extension", "kimi-k2.6"): (2.5, 100, None),
    ("runs-2026-07-thinking-extension", "kimi-k3"): (2.5, 100, None),
}

# run_id -> reason. Model runs under a condition other than the base cells.
SEPARATE_CONDITION = {
    "sympy__sympy-13757--tooluse--kimi-k3--20260802-194913-889114":
        "raised-cap rerun 2026-08-02 ($10 / 100 turns / 2 h); not a base repeat",
}

RUN_FIELDS = [
    "run_id", "batch", "kind", "harness", "task_id", "model", "model_raw",
    "lab", "generation", "host", "started_at", "exit_reason",
    "cap_usd", "cap_turns", "cap_wall_s", "caps_source", "condition",
    "stale_image", "resolved", "image_id", "extra_files",
    "included", "exclusion_reason",
]
TASK_FIELDS = ["task_id", "image_id", "golden_runs", "gold_patch_sha256", "test_patch_sha256"]


def resolved(g: dict) -> bool:
    return bool(
        g.get("applies_cleanly") and g.get("builds") and g.get("f2p_passed")
        and not g.get("f2p_failed") and not g.get("p2p_failed")
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(v)


def scan() -> tuple[list[dict], list[dict]]:
    """Walk research/corpus/ and build the rows for both CSVs, asserting invariants."""
    problems: list[str] = []
    rows: list[dict] = []
    image_by_task: dict[str, dict[str, list[str]]] = {}
    golden_by_task: dict[str, list[str]] = {}

    for batch_dir in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        if (batch_dir / "ledger.jsonl").is_file():
            continue  # indexed by its own ledger (see "Scope" above)
        for run_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
            run_id = run_dir.name
            files = {p.name for p in run_dir.iterdir()}
            missing = STANDARD_FILES - files
            if missing:
                problems.append(f"{run_id}: missing {sorted(missing)}")
                continue
            run = json.loads((run_dir / "run.json").read_text())
            grade = json.loads((run_dir / "grade.json").read_text())
            if run["run_id"] != run_id:
                problems.append(f"{run_id}: run.json run_id is {run['run_id']!r}")
            harness = run["harness"]
            if harness not in HARNESSES:
                problems.append(f"{run_id}: unknown harness {harness!r}")
            exit_reason = run["exit_reason"]
            if (exit_reason == "crash") != ("runner_error.log" in files):
                problems.append(f"{run_id}: exit_reason={exit_reason!r} but runner_error.log "
                                f"{'present' if 'runner_error.log' in files else 'absent'}")

            model_raw = run["model"]
            fixture = harness in FIXTURE_HARNESSES
            if fixture:
                if model_raw not in FIXTURE_STAMPS:
                    problems.append(f"{run_id}: fixture run with model {model_raw!r}")
                model, lab, gen, host = "none", "", "", ""
                kind, condition = harness, "fixture"
            else:
                if model_raw not in MODELS:
                    problems.append(f"{run_id}: model {model_raw!r} not in MODELS")
                    model, lab, gen, host = model_raw, "", "", ""
                else:
                    model, lab, gen, host = MODELS[model_raw]
                kind = "model"
                condition = "raised-cap" if run_id in SEPARATE_CONDITION else "base"

            limits = run.get("limits")
            if limits:
                caps = (limits["max_cost_usd"], limits["max_turns"], limits["wall_clock_s"])
                caps_source = "run.json"
            elif (batch_dir.name, model) in BATCH_CAPS:
                caps, caps_source = BATCH_CAPS[(batch_dir.name, model)], "README"
            else:
                caps, caps_source = (None, None, None), ""

            stale = STALE_MARKER in (run_dir / "raw_transcript.jsonl").read_text(errors="replace")
            image_id = grade.get("image_id", "")
            task_id = run["task_id"]
            if image_id:
                image_by_task.setdefault(task_id, {}).setdefault(image_id, []).append(run_id)
                if harness == "golden":
                    golden_by_task.setdefault(task_id, []).append(run_id)

            if kind != "model":
                included, why = False, f"{kind} fixture, not a model run"
            elif exit_reason == "crash":
                included, why = False, "crash (provider-side failure)"
            elif condition != "base":
                included, why = False, SEPARATE_CONDITION[run_id]
            else:
                included, why = True, ""

            rows.append({
                "run_id": run_id, "batch": batch_dir.name, "kind": kind, "harness": harness,
                "task_id": task_id, "model": model, "model_raw": model_raw,
                "lab": lab, "generation": gen, "host": host,
                "started_at": run["started_at"], "exit_reason": exit_reason,
                "cap_usd": caps[0], "cap_turns": caps[1], "cap_wall_s": caps[2],
                "caps_source": caps_source, "condition": condition,
                "stale_image": stale, "resolved": resolved(grade), "image_id": image_id,
                "extra_files": ";".join(sorted(files - STANDARD_FILES)),
                "included": included, "exclusion_reason": why,
            })

    known = {r["run_id"] for r in rows}
    for rid in SEPARATE_CONDITION:
        if rid not in known:
            problems.append(f"SEPARATE_CONDITION names a run dir that does not exist: {rid}")

    tasks: list[dict] = []
    for task_id in sorted({r["task_id"] for r in rows}):
        images = image_by_task.get(task_id, {})
        if len(images) != 1:
            problems.append(f"{task_id}: graded runs cite {len(images)} image ids: "
                            f"{ {k[:19]: len(v) for k, v in images.items()} }")
        image_id = next(iter(images)) if images else ""
        gp, tp = TASKS / task_id / "gold.patch", TASKS / task_id / "test.patch"
        for p in (gp, tp):
            if not p.is_file():
                problems.append(f"{task_id}: missing {p.relative_to(ROOT)}")
        tasks.append({
            "task_id": task_id, "image_id": image_id,
            "golden_runs": ";".join(golden_by_task.get(task_id, [])),
            "gold_patch_sha256": sha256(gp) if gp.is_file() else "",
            "test_patch_sha256": sha256(tp) if tp.is_file() else "",
        })

    if problems:
        raise SystemExit("manifest invariants violated:\n  " + "\n  ".join(problems))
    rows.sort(key=lambda r: r["run_id"])
    return rows, tasks


def render(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(fields)
    for r in rows:
        w.writerow([_fmt(r[f]) for f in fields])
    return buf.getvalue()


def load_runs() -> list[dict]:
    """Rows of the committed runs.csv with typed fields (the analysis entry point)."""
    with RUNS_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["included"] = r["included"] == "1"
        r["resolved"] = r["resolved"] == "1"
        r["stale_image"] = r["stale_image"] == "1"
        r["generation"] = int(r["generation"]) if r["generation"] else None
    return rows


def main(argv: list[str]) -> int:
    rows, tasks = scan()
    runs_txt, tasks_txt = render(rows, RUN_FIELDS), render(tasks, TASK_FIELDS)
    n_inc = sum(r["included"] for r in rows)
    if "--check" in argv:
        stale = [p.name for p, txt in ((RUNS_CSV, runs_txt), (TASKS_CSV, tasks_txt))
                 if not p.is_file() or p.read_text() != txt]
        if stale:
            print(f"manifest --check FAILED: {', '.join(stale)} differ from regenerated "
                  f"(re-run without --check and commit)")
            return 1
        print(f"manifest --check OK: {len(rows)} runs ({n_inc} included), {len(tasks)} tasks")
        return 0
    RUNS_CSV.write_text(runs_txt)
    TASKS_CSV.write_text(tasks_txt)
    print(f"wrote {RUNS_CSV.relative_to(ROOT)} ({len(rows)} runs, {n_inc} included) and "
          f"{TASKS_CSV.relative_to(ROOT)} ({len(tasks)} tasks)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
