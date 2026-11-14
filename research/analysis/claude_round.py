"""Round 2 analysis (exp-08 Opus line, exp-09 effort dial, exp-10 size ladder).

Specification: research/experiments/exp-08-opus-line.md (shared design,
measures M14/M15, analyses A1-A7, Part B, V1/V2), exp-09-effort-dial.md and
exp-10-size-ladder.md. This header states every definition the experiment
files leave to the code. It was written before any run of the round existed.
Stdlib only. M1-M13, U, the segmentation and coding, the balanced variance
split, Holm, Cohen's kappa, the exp-07 A1 labels and the nearest-centroid
helpers are imported from command_audit.py (frozen in commit 9704517), never
copied.

Run selection
-------------
Ledger research/corpus/runs-2026-11-claude-round/ledger.jsonl (written by
openbench.runners.round_runner). Field names are read in one place
(`parse_ledger_record`), with aliases; optional fields may be missing. Only
lines of kind `attempt` (or lines without a kind) are attempts; `start` and
`spend` lines are ignored; `grade` lines (and attempt lines) carrying a
resolved value set resolved for their run_id, the last one winning. A
cell is (model, effort, task_id, repeat), taken from the fields or from the
`model|effort|task_id|repeat` cell key. A cell's run is its LATEST (last
line in file order) attempt with a run_id whose exit_reason is not `crash`
or `interrupted` (the runner's CRASHLIKE: an interrupted attempt is a run the
harness killed before it was logged). The run
folder is the ledger's run_dir if it exists, else <runs-root>/<run_id>.
model / effort / task_id missing from the ledger are read from the
transcript's meta record (`model`, `thinking_effort`, `task_id`). A ledger
line without a repeat gets 1, 2, ... in ledger order within its
(model, effort, task). Without a ledger file the runs root is scanned
instead (every folder with a transcript; non-crash runs; repeat = order of
run.json started_at within the cell) and the output says so.
Runs are assigned to experiments by (model, effort), never by stage: the
Sonnet `high` runs serve exp-09 and exp-10, the Opus 5.5 runs exp-08 and
exp-10, the pilot runs their own cells.
Task order: research/corpus/runs-2026-11-claude-round/round.json (a list, or
an object with `tasks` / `task_list` / `frozen_tasks`; items are task ids or
objects with `task_id`). Without it, the tasks found in the runs, sorted.

Per-run values
--------------
M1-M13, U, U_lenient, U_unknown, no_edit and the exp-07 descriptives:
command_audit.load_exec / patch_status / code_records / metrics_from_records,
the composition used by command_audit.compute_all. Package root for
edit:source_new: command_audit.package_root only knows sympy/ and src/
(pytest); the frozen header names no root for the new libraries, so this
module passes astropy/, lib/matplotlib/, xarray/, src/, sklearn/, sphinx/,
sympy/ by task-id prefix (PACKAGE_ROOTS; reported as a spec gap).
M14 backed_done      1 iff exit_reason == completed and unsupported_done == 0
                     (a passing test segment after the last change). Completed
                     runs without a source edit (U empty) and U_unknown runs
                     score 0. 0 for every run that does not complete.
M15 multi_call_share of api_response records carrying an integer
                     n_tool_calls, the share with n_tool_calls > 1. None when
                     no reply carries the field (round 1 transcripts).
Context (reported, never tested):
  resolved           grade.json via manifest.resolved; else the ledger's
                     resolved; else None (ungraded).
  exit_reason        final record, else run.json, else ledger.
  turns              final.turns, else run.json num_turns, else replies.
  thinking_tokens_per_reply  sum of usage_raw.output_tokens_details
                     .thinking_tokens / replies; replies with usage_raw but no
                     detail count 0; None if no reply has usage_raw.
  output_tokens_per_reply    usage.completion_tokens (else usage_raw
                     .output_tokens) summed / replies.
  max_tokens_replies replies with stop_reason == max_tokens; None if no reply
                     has a stop_reason field.
  cost_usd           run.json total_cost_usd, else final.usage_totals
                     .cost_usd, else ledger cost_usd.
Analysis scale: command_audit.transform (M1 ln n, M13 ln(1+x), else as is).

Trend test (exp-08 A2; exp-09/exp-10 A2-A4; Part B B4) - `page_trend`
---------------------------------------------------------------------
Inputs: ordered levels (rank g = 1..k), blocks (tasks), cell values (a
number, or a list whose non-None mean is the cell value). A block in which
some level has no value is dropped. Fewer than `min_blocks` complete blocks
(4 by A2) -> not tested. Within each block the k values get mid-ranks;
L = sum_g g * R_g; E0 = b k (k+1)^2 / 4; statistic |L - E0|; direction =
sign(L - E0) (+1 rises with the level). Null: in each draw the ranks of
each block are permuted independently (blocks in the given order), 10,000
draws, one random.Random(20261113) per call; p = (1 + #{draws with
|L* - E0| >= |L - E0|, relative tolerance 1e-12}) / (1 + draws).
A3 sign agreement: per complete block, Spearman (Pearson of mid-ranks)
between level rank and value. A block whose values are all equal (rho
undefined) or whose rho is exactly 0 has no sign and is left out of the
count. Reported: agree (sign == direction), disagree (sign == -direction),
no_sign. When L = E0 (direction 0) every signed block counts as disagreeing.
Decision (`decide_trend`): trend iff Holm-adjusted p < 0.05, at least four
blocks have a sign (agree + disagree >= 4) and at most one disagrees, and
direction != 0; candidate iff unadjusted p < 0.05 with the same sign
condition, Holm p >= 0.05; none otherwise; `not tested` when p is None
(counts as none for every decision). Same rule in exp-08, exp-09, exp-10. Holm (command_audit.holm) is over the
measures that were tested; untested measures leave the family.
Experiment names: exp-08 trend / candidate / none; exp-09 responds to
effort / candidate / not shown to respond; exp-10 moves with size /
candidate / none.
A4 shape (trend and candidate only): over the complete blocks, cell values
minus their block mean, averaged per level -> profile m_1..m_k; SS_between =
sum (m_g - mean m)^2; for every split after level s (1 <= s < k), SS_split =
n1 (mean1 - mean)^2 + n2 (mean2 - mean)^2; step-like iff max SS_split >= 0.9
SS_between, else gradual; None if SS_between = 0.

A1 variance split
-----------------
command_audit.variance_split / kendall_w / decide with the factor level in
place of the model, 10,000 draws, seeds 20261113 + measure index (p_main) and
+100 (p_cell), Holm over the measures with a p value, exp-07 labels. The
layout must be balanced (every level x task cell with both runs, REPEATS =
2). If not: the analysis is run on the tasks where every level has both
runs (if >= 2 tasks and >= 2 levels remain), the dropped
tasks are listed, and marginal sums-of-squares shares (level, task, cell,
within-cell) over all runs are reported without tests. A measure undefined
for some run (M15 without n_tool_calls) is not split.

exp-08 A5 profile drift
-----------------------
Runs with all 15 measures defined; command_audit._zscore over them (zero-sd
measures dropped). Leave-one-task-out nearest centroid (command_audit._nearest,
ties to the earlier generation). accuracy; rank error = mean |predicted rank
- true rank|. Null: model labels permuted within task, 10,000 draws, seed
20261113 + 500. p_rank = (1 + #{null rank error <= observed}) / (1 + draws);
p_acc = (1 + #{null accuracy >= observed}) / (1 + draws). "identification
above chance" is read as accuracy > the 95th percentile of the null (the
exp-07 A5 rule); accuracy > 0.2 is reported beside it.

exp-08 A6 outcome check: per cell resolved counts. Resolution "differs between
generations" iff the per-generation resolved rates (graded runs) are not all
equal. Then every measure labelled trend is re-tested on resolved runs only
(same test, unadjusted p, sign counts; no Holm, no label).
exp-08 A7 bridge: runs.csv rows on sympy__sympy-13757 with included=1 (27),
coded with the same per-run code; per-model means on the analysis scale beside
the round 2 rows of the same task.
exp-09 A5: thinking_tokens_per_reply by level, page_trend; passes iff p <
0.05 and direction +1. Failing -> the experiment is marked uninformative.
max_tokens replies per level beside it.
exp-09 A6: per measure the exp-08 label beside the exp-09 label, with the
reading of an exp-08 none; thinking tokens per reply by Opus generation.
exp-10 A5: per measure exp-08 label and direction beside exp-10 label and
direction, read by the four readings; candidate in either -> "not
classified (candidate)"; trend in both with opposite directions -> "trend in
both, opposite directions (none of the four readings)".
With only three exp-10 levels present (Fable dropped) no test is run.

Validation
----------
V1 per condition (model, or effort level in exp-09): share of exec records
whose primary class is `other` (the flagged number; "command" = exec record),
share of segments classed other (reported), share of edit writes (segment,
path) whose sub-kind is unknown. Above 0.15 on either flagged share -> that
condition's measures are marked unreliable in every table.
V2 per task, over every loaded run of the round: the first test command of a
run (first record with a test flag, or a segment whose program is a test
runner reported `command not found`) fails to start when its output matches
RUNNER_START_FAIL (manifest.STALE_MARKER, ImportError while loading conftest,
INTERNALERROR, No module named pytest / _pytest, test runner command not
found, PluginValidationError). A task with such runs in half or more of its
runs is reported and dropped from every analysis of every experiment (the
exp-07 treatment of pytest-5262). Runs where a source edit preceded that
command are counted separately.
V3: every output carries "unvalidated instrument".

Part B (`part_b`): per candidate, Cohen's kappa between the two passes over
runs; kappa < 0.6 -> unreliable, not tested. Cell value = mean of both
passes' yes over the cell's runs. page_trend over the three held-out
tasks with every block required complete (no four-block minimum), Holm over
the tested candidates; trend iff Holm p < 0.05, at least two blocks have a
sign and none disagrees (decide_trend(min_signed=2, max_disagree=0));
candidate iff unadjusted p < 0.05 with the same sign condition.

Predictions: every prediction of the three files is scored held / not held /
not testable by `score_*`; the text is copied verbatim and checked against
the experiment file at run time (a mismatch is reported).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import command_audit as ca  # noqa: E402
import manifest  # noqa: E402

SEED = 20261113
DRAWS = 10_000
MIN_BLOCKS = 4
REPEATS = 2
COVERAGE_LIMIT = 0.15
BRIDGE_TASK = "sympy__sympy-13757"
ROUND_DIR = manifest.CORPUS / "runs-2026-11-claude-round"
LEDGER = ROUND_DIR / "ledger.jsonl"
ROUND_JSON = ROUND_DIR / "round.json"
RESULTS = manifest.ROOT / "research" / "results"
EXP_DIR = manifest.ROOT / "research" / "experiments"
STATUS = "unvalidated instrument"

MEASURES = ca.METRICS + [("M14", "backed_done", None), ("M15", "multi_call_share", None)]
MEASURE_KEYS = [k for _, k, _ in MEASURES]
CONTEXT = ["resolved", "exit_reason", "turns", "thinking_tokens_per_reply",
           "output_tokens_per_reply", "max_tokens_replies", "cost_usd"]

PACKAGE_ROOTS = [("astropy__", "astropy/"), ("matplotlib__", "lib/matplotlib/"),
                 ("pydata__xarray", "xarray/"), ("pytest-dev__", "src/"),
                 ("scikit-learn__", "sklearn/"), ("sphinx-doc__", "sphinx/"),
                 ("sympy__", "sympy/")]

EXPERIMENTS = {
    "exp-08": {
        "slug": "exp-08-opus-line", "factor": "generation",
        "levels": [("claude-opus-4-6", "high"), ("claude-opus-4-7", "high"),
                   ("claude-opus-4-8", "high"), ("claude-opus-5", "high"),
                   ("claude-opus-5-5", "high")],
        "names": {"trend": "trend", "candidate": "candidate", "none": "none"},
    },
    "exp-09": {
        "slug": "exp-09-effort-dial", "factor": "effort",
        "levels": [("claude-sonnet-5-5", e) for e in ("low", "medium", "high", "xhigh")],
        "names": {"trend": "responds to effort", "candidate": "candidate",
                  "none": "not shown to respond"},
    },
    "exp-10": {
        "slug": "exp-10-size-ladder", "factor": "size",
        "levels": [("claude-haiku-5-5", "high"), ("claude-sonnet-5-5", "high"),
                   ("claude-opus-5-5", "high"), ("claude-fable-5-2", "high")],
        "names": {"trend": "moves with size", "candidate": "candidate", "none": "none"},
    },
}

RUNNER_START_FAIL = re.compile(
    re.escape(manifest.STALE_MARKER) + r"|ImportError while loading conftest|^INTERNALERROR|"
    r"No module named '?_?pytest'?|PluginValidationError|"
    r"(?:pytest|py\.test|tox|nox): command not found", re.M)
TEST_PROGS = {"pytest", "py.test", "tox", "nox"}
CRASHLIKE = ("crash", "interrupted")   # as round_runner.CRASHLIKE


def level_name(exp: str, cond) -> str:
    return cond[1] if exp == "exp-09" else cond[0]


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def _first(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _boolish(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "resolved"):
        return True
    if s in ("0", "false", "no", "unresolved"):
        return False
    return None


def parse_ledger_record(d: dict) -> dict | None:
    """The only place that knows the ledger's field names (aliases tolerated)."""
    if not isinstance(d, dict):
        return None
    run_id = _first(d, "run_id", "run", "id")
    rep = _first(d, "repeat", "rep", "repeat_index")
    try:
        rep = int(rep) if rep is not None else None
    except (TypeError, ValueError):
        rep = None
    cost = _first(d, "cost_usd", "cost", "total_cost_usd")
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None
    cell = _first(d, "cell", "cell_key", "key")
    parts = cell.split("|") if isinstance(cell, str) and cell.count("|") == 3 else [None] * 4
    if rep is None and parts[3] is not None:
        try:
            rep = int(parts[3])
        except ValueError:
            rep = None
    return {
        "kind": _first(d, "kind", "type"),
        "run_id": run_id,
        "model": _first(d, "model", "model_id") or parts[0],
        "effort": _first(d, "effort", "thinking_effort") or parts[1],
        "task_id": _first(d, "task_id", "task") or parts[2],
        "repeat": rep,
        "exit_reason": _first(d, "exit_reason", "exit", "status"),
        "cost_usd": cost,
        "resolved": _boolish(_first(d, "resolved")),
        "stage": _first(d, "stage", "experiment"),
        "cell": cell,
        "run_dir": _first(d, "run_dir", "dir", "path"),
    }


def load_ledger(path) -> list[dict]:
    out = []
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = parse_ledger_record(json.loads(line))
            except json.JSONDecodeError:
                continue
            if rec is not None:
                out.append(rec)
    return out


def read_transcript(run_dir) -> dict:
    meta, replies, final = {}, [], {}
    tp = os.path.join(str(run_dir), "raw_transcript.jsonl")
    if os.path.isfile(tp):
        with open(tp, errors="replace") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = r.get("type")
                if t == "meta":
                    meta = r
                elif t == "api_response":
                    replies.append(r)
                elif t == "final":
                    final = r
    return {"meta": meta, "replies": replies, "final": final}


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def select_cells(entries: list[dict], runs_root) -> tuple[dict, list[str]]:
    """Latest non-crash attempt per (model, effort, task, repeat). -> (cells, notes)."""
    notes = []
    seq = Counter()
    cells: dict = {}
    graded = {}   # later `grade` (or attempt) lines with a resolved value win, by run_id
    for e in entries:
        if e.get("kind") in (None, "attempt", "grade") and e.get("resolved") is not None:
            graded[e.get("run_id")] = e["resolved"]
    for e in entries:
        if e.get("kind") not in (None, "attempt"):
            continue      # `start`, `spend`, `grade` lines are not attempts
        e = dict(e)
        if e.get("run_id") in graded:
            e["resolved"] = graded[e["run_id"]]
        rd = e.get("run_dir")
        if not (rd and os.path.isdir(rd)):
            rd = os.path.join(str(runs_root), e["run_id"]) if e.get("run_id") else None
        e["dir"] = rd
        if not (e.get("model") and e.get("effort") and e.get("task_id")) and rd:
            meta = read_transcript(rd)["meta"]
            e["model"] = e.get("model") or meta.get("model")
            e["effort"] = e.get("effort") or meta.get("thinking_effort")
            e["task_id"] = e.get("task_id") or meta.get("task_id")
        if not (e.get("model") and e.get("effort") and e.get("task_id")):
            notes.append(f"ledger line for run {e.get('run_id')} lacks model/effort/task; skipped")
            continue
        if e.get("exit_reason") in CRASHLIKE or not e.get("run_id"):
            continue
        base = (e["model"], e["effort"], e["task_id"])
        if e.get("repeat") is None:
            seq[base] += 1
            e["repeat"] = seq[base]
        cells[base + (e["repeat"],)] = e   # file order: later lines win
    return cells, notes


def scan_runs_root(runs_root) -> dict:
    """Fallback without a ledger: every run folder with a transcript, non-crash."""
    found = defaultdict(list)
    if not os.path.isdir(str(runs_root)):
        return {}
    for name in sorted(os.listdir(str(runs_root))):
        rd = os.path.join(str(runs_root), name)
        if not os.path.isfile(os.path.join(rd, "raw_transcript.jsonl")):
            continue
        tr = read_transcript(rd)
        rj = _read_json(os.path.join(rd, "run.json")) or {}
        exit_reason = tr["final"].get("exit_reason") or rj.get("exit_reason")
        if exit_reason in CRASHLIKE:
            continue
        m = tr["meta"]
        key = (m.get("model") or rj.get("model"), m.get("thinking_effort"),
               m.get("task_id") or rj.get("task_id"))
        if None in key:
            continue
        found[key].append({"run_id": name, "dir": rd, "model": key[0], "effort": key[1],
                           "task_id": key[2], "exit_reason": exit_reason,
                           "started_at": rj.get("started_at") or name})
    cells = {}
    for key, rs in found.items():
        rs.sort(key=lambda r: r["started_at"])
        for i, r in enumerate(rs, 1):
            cells[key + (i,)] = {**r, "repeat": i, "cost_usd": None, "resolved": None,
                                 "stage": None}
    return cells


def load_round_tasks(path=ROUND_JSON) -> list[str] | None:
    d = _read_json(path)
    if d is None:
        return None
    items = d if isinstance(d, list) else _first(d, "tasks", "task_list", "frozen_tasks")
    if not isinstance(items, list):
        return None
    out = []
    for it in items:
        t = it if isinstance(it, str) else (it.get("task_id") if isinstance(it, dict) else None)
        if t:
            out.append(t)
    return out or None


# --------------------------------------------------------------------------
# Per-run values
# --------------------------------------------------------------------------

def pkg_root(task_id: str) -> str:
    for prefix, root in PACKAGE_ROOTS:
        if task_id.startswith(prefix):
            return root
    return ca.package_root(task_id)


def m14_backed_done(exit_reason, unsupported_done) -> int:
    return int(exit_reason == "completed" and unsupported_done == 0)


def m15_multi_call_share(replies: list[dict]):
    calls = [r.get("n_tool_calls") for r in replies]
    calls = [c for c in calls if isinstance(c, int) and not isinstance(c, bool)]
    if not calls:
        return None
    return sum(c > 1 for c in calls) / len(calls)


def context_values(replies: list[dict], final: dict, run_json: dict) -> dict:
    n = len(replies)
    out = {"n_replies": n}
    raw = [r.get("usage_raw") for r in replies]
    if n and any(isinstance(u, dict) for u in raw):
        tot = 0
        for u in raw:
            if isinstance(u, dict):
                tot += int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
        out["thinking_tokens_per_reply"] = tot / n
    else:
        out["thinking_tokens_per_reply"] = None
    outs = []
    for r in replies:
        u = r.get("usage") or {}
        v = u.get("completion_tokens")
        if v is None and isinstance(r.get("usage_raw"), dict):
            v = r["usage_raw"].get("output_tokens")
        if v is not None:
            outs.append(int(v))
    out["output_tokens_per_reply"] = sum(outs) / n if n and outs else None
    if any("stop_reason" in r for r in replies):
        out["max_tokens_replies"] = sum(r.get("stop_reason") == "max_tokens" for r in replies)
    else:
        out["max_tokens_replies"] = None
    out["turns"] = final.get("turns") or run_json.get("num_turns") or n
    cost = run_json.get("total_cost_usd")
    if cost is None:
        cost = (final.get("usage_totals") or {}).get("cost_usd")
    out["cost_usd"] = cost
    return out


def coverage_counts(records, info) -> dict:
    n_edit = n_edit_unknown = 0
    for rec in records:
        for s in rec["segs"]:
            if s["cls"] != "edit":
                continue
            ws = s["writes"] or [(None, None)]
            for p, _ in ws:
                n_edit += 1
                n_edit_unknown += (p is None or info["subkind"].get(p) == "unknown")
    return {"cov_records": len(records),
            "cov_records_other": sum(r["primary"] == "other" for r in records),
            "cov_segments": info["n_segments"], "cov_segments_other": info["n_other_segments"],
            "cov_edits": n_edit, "cov_edits_unknown": n_edit_unknown}


def runner_start(records) -> dict:
    """V2 for one run: did its first test command fail to start the runner?"""
    seen_change = False
    for rec in records:
        nf_test = any(s.get("not_found") and (s.get("prog") or "") in TEST_PROGS
                      for s in rec["segs"])
        if "test" in rec["classes"] or nf_test:
            fail = bool(RUNNER_START_FAIL.search(rec["output"])) or nf_test
            return {"has_test": 1, "runner_start_fail": int(fail),
                    "runner_start_fail_after_edit": int(fail and seen_change)}
        if set(ca.CHANGE_KINDS) & rec["subkinds"]:
            seen_change = True
    return {"has_test": 0, "runner_start_fail": 0, "runner_start_fail_after_edit": 0}


def run_row(run_dir, task_id: str, entry: dict | None = None) -> dict:
    """Every per-run value for one run folder."""
    entry = entry or {}
    run_dir = str(run_dir)
    recs, exit_reason = ca.load_exec(run_dir)
    tr = read_transcript(run_dir)
    rj = _read_json(os.path.join(run_dir, "run.json")) or {}
    exit_reason = exit_reason or entry.get("exit_reason")
    wp = os.path.join(run_dir, "workspace.patch")
    ws_status = ca.patch_status(wp)
    records, info = ca.code_records(recs, ws_status, ca.ref_existing(task_id), pkg_root(task_id))
    gp = str(manifest.TASKS / task_id / "gold.patch")
    m = ca.metrics_from_records(records, info, exit_reason, ws_status,
                                list(ca.patch_status(gp)), ca.patch_line_count(wp),
                                ca.cv.parse_patch(wp)[1], ca.cv.parse_patch(gp)[1])
    m["backed_done"] = m14_backed_done(exit_reason, m["unsupported_done"])
    m["multi_call_share"] = m15_multi_call_share(tr["replies"])
    m.update(context_values(tr["replies"], tr["final"], rj))
    if m["cost_usd"] is None:
        m["cost_usd"] = entry.get("cost_usd")
    g = _read_json(os.path.join(run_dir, "grade.json"))
    m["resolved"] = manifest.resolved(g) if isinstance(g, dict) else entry.get("resolved")
    m["resolved_ledger"] = entry.get("resolved")
    m.update(coverage_counts(records, info))
    m.update(runner_start(records))
    m["run_id"] = entry.get("run_id") or os.path.basename(run_dir.rstrip("/"))
    m["model"] = entry.get("model") or tr["meta"].get("model")
    m["effort"] = entry.get("effort") or tr["meta"].get("thinking_effort")
    m["task_id"] = task_id
    m["repeat"] = entry.get("repeat")
    m["stage"] = entry.get("stage")
    return m


def load_round(runs_root, ledger_path) -> tuple[list[dict], dict]:
    """-> (rows, load report)."""
    report = {"runs_root": str(runs_root), "ledger": str(ledger_path), "notes": []}
    if os.path.isfile(str(ledger_path)):
        cells, notes = select_cells(load_ledger(ledger_path), runs_root)
        report["source"] = "ledger"
        report["notes"] += notes
    else:
        cells = scan_runs_root(runs_root)
        report["source"] = "runs-root scan (no ledger file)"
        report["notes"].append(f"no ledger at {ledger_path}; scanned {runs_root} instead")
    rows, missing_dirs = [], []
    for key in sorted(cells, key=lambda k: tuple(str(x) for x in k)):
        e = cells[key]
        if not (e.get("dir") and os.path.isfile(os.path.join(e["dir"], "raw_transcript.jsonl"))):
            missing_dirs.append(e.get("run_id") or str(key))
            continue
        rows.append(run_row(e["dir"], e["task_id"], e))
    report["n_runs"] = len(rows)
    report["missing_run_folders"] = missing_dirs
    report["ungraded_runs"] = [r["run_id"] for r in rows if r["resolved"] is None]
    report["grade_ledger_mismatch"] = [
        r["run_id"] for r in rows
        if r["resolved"] is not None and r["resolved_ledger"] is not None
        and bool(r["resolved"]) != bool(r["resolved_ledger"])]
    return rows, report


# --------------------------------------------------------------------------
# Trend test (A2), sign agreement (A3), shape (A4), decisions
# --------------------------------------------------------------------------

def _cell_value(v):
    if isinstance(v, (list, tuple)):
        xs = [x for x in v if x is not None]
        return sum(xs) / len(xs) if xs else None
    return v


def _spearman(xs, ys):
    rx, ry = ca._avg_ranks(xs), ca._avg_ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx <= 1e-15 or syy <= 1e-15:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


def _sign(x, tol=1e-12):
    return 0 if abs(x) <= tol else (1 if x > 0 else -1)


def page_trend(levels: list, blocks: list, cells: dict, draws: int = DRAWS, seed: int = SEED,
               min_blocks: int = MIN_BLOCKS) -> dict:
    """Page's L with a within-block permutation null. cells[(level, block)] -> value or list."""
    k = len(levels)
    complete, dropped, table = [], [], {}
    for b in blocks:
        vals = [_cell_value(cells.get((lv, b))) for lv in levels]
        if any(v is None for v in vals):
            dropped.append(b)
        else:
            complete.append(b)
            table[b] = [float(v) for v in vals]
    nb = len(complete)
    out = {"levels": list(levels), "k": k, "blocks": complete, "dropped_blocks": dropped,
           "n_blocks": nb, "tested": False, "L": None, "E0": None, "direction": 0, "p": None,
           "spearman": {}, "agree": None, "disagree": None, "no_sign": None, "reason": None}
    if k < 2:
        out["reason"] = "fewer than two levels"
        return out
    if nb < min_blocks:
        out["reason"] = f"{nb} complete blocks < {min_blocks}"
        return out
    ranks = [ca._avg_ranks(table[b]) for b in complete]
    g = list(range(1, k + 1))
    L = sum(gi * r[i] for r in ranks for i, gi in enumerate(g))
    E0 = nb * k * (k + 1) ** 2 / 4
    obs = abs(L - E0)
    rng = random.Random(seed)
    ge = 0
    for _ in range(draws):
        Ls = 0.0
        for r in ranks:
            pr = rng.sample(r, k)
            Ls += sum(gi * pr[i] for i, gi in enumerate(g))
        ge += ca._ge(abs(Ls - E0), obs)
    direction = _sign(L - E0)
    rho = {b: _spearman(g, table[b]) for b in complete}
    signs = [_sign(rho[b]) for b in complete]
    agree = sum(1 for sg in signs if sg != 0 and sg == direction)
    disagree = sum(1 for sg in signs if sg != 0 and sg != direction)
    no_sign = sum(1 for sg in signs if sg == 0)
    out.update({"tested": True, "L": L, "E0": E0, "stat": obs, "direction": direction,
                "p": (1 + ge) / (1 + draws), "spearman": rho, "agree": agree,
                "disagree": disagree, "no_sign": no_sign, "draws": draws, "seed": seed,
                "cell_values": {b: table[b] for b in complete}})
    return out


def decide_trend(p, p_holm, agree, disagree, direction, min_signed=4, max_disagree=1) -> str:
    """Generic labels: trend / candidate / none / not tested."""
    if p is None:
        return "not tested"
    ok = (direction != 0 and agree is not None and disagree is not None
          and agree + disagree >= min_signed and disagree <= max_disagree)
    if p_holm is not None and p_holm < 0.05 and ok:
        return "trend"
    if p < 0.05 and ok:
        return "candidate"
    return "none"


def shape(levels: list, blocks: list, cells: dict) -> dict:
    """A4 on the given (complete) blocks."""
    k = len(levels)
    prof = [0.0] * k
    used = 0
    for b in blocks:
        vals = [_cell_value(cells.get((lv, b))) for lv in levels]
        if any(v is None for v in vals):
            continue
        mu = sum(vals) / k
        for i, v in enumerate(vals):
            prof[i] += v - mu
        used += 1
    if not used:
        return {"profile": None, "split_share": None, "split_after": None, "shape": None}
    prof = [x / used for x in prof]
    gm = sum(prof) / k
    ss = sum((x - gm) ** 2 for x in prof)
    if ss <= 1e-15:
        return {"profile": prof, "split_share": None, "split_after": None, "shape": None}
    best, after = -1.0, None
    for s in range(1, k):
        a, b = prof[:s], prof[s:]
        sss = len(a) * (sum(a) / len(a) - gm) ** 2 + len(b) * (sum(b) / len(b) - gm) ** 2
        if sss > best + 1e-15:
            best, after = sss, levels[s - 1]
    share = best / ss
    return {"profile": prof, "split_share": share, "split_after": after,
            "shape": "step-like" if share >= 0.9 - 1e-12 else "gradual"}


def _cells_of(rows, key, levels, level_of, tasks):
    cells = defaultdict(list)
    for r in rows:
        lv = level_of(r)
        if lv in levels and r["task_id"] in tasks:
            cells[(lv, r["task_id"])].append(ca.transform(key, r.get(key)))
    return cells


def trend_family(rows, levels, level_of, tasks, measures=MEASURES, draws=DRAWS, seed=SEED,
                 min_blocks=MIN_BLOCKS) -> dict:
    """A2-A4 for a family of measures, Holm over the tested ones."""
    res = {}
    for mid, key, _ in measures:
        cells = _cells_of(rows, key, levels, level_of, tasks)
        t = page_trend(levels, tasks, cells, draws=draws, seed=seed, min_blocks=min_blocks)
        t.pop("cell_values", None)
        t["key"] = key
        t["level_means"] = {lv: _mean_all([v for (lv2, _), vs in cells.items() if lv2 == lv
                                           for v in vs]) for lv in levels}
        t["_cells"] = cells
        res[mid] = t
    ids = list(res)
    adj = ca.holm([res[i]["p"] for i in ids])
    for i, mid in enumerate(ids):
        r = res[mid]
        r["p_holm"] = adj[i]
        r["label"] = decide_trend(r["p"], r["p_holm"], r["agree"], r["disagree"],
                                  r["direction"])
        if r["label"] in ("trend", "candidate"):
            r["shape"] = shape(levels, r["blocks"], r["_cells"])
        else:
            r["shape"] = None
        del r["_cells"]
    return res


def _mean_all(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


# --------------------------------------------------------------------------
# A1 variance split
# --------------------------------------------------------------------------

def _marginal_shares(rows, key, levels, level_of, tasks):
    vals = [(level_of(r), r["task_id"], ca.transform(key, r.get(key))) for r in rows
            if level_of(r) in levels and r["task_id"] in tasks]
    vals = [v for v in vals if v[2] is not None]
    if len(vals) < 2:
        return None
    g = sum(v for _, _, v in vals) / len(vals)
    tot = sum((v - g) ** 2 for _, _, v in vals)
    if tot <= 1e-15:
        return {"constant": True}
    grp = {"level": defaultdict(list), "task": defaultdict(list), "cell": defaultdict(list)}
    for lv, t, v in vals:
        grp["level"][lv].append(v)
        grp["task"][t].append(v)
        grp["cell"][(lv, t)].append(v)
    mean = {k: {kk: sum(x) / len(x) for kk, x in d.items()} for k, d in grp.items()}
    ss_l = sum((mean["level"][lv] - g) ** 2 for lv, _, _ in vals)
    ss_t = sum((mean["task"][t] - g) ** 2 for _, t, _ in vals)
    ss_c = sum((mean["cell"][(lv, t)] - g) ** 2 for lv, t, _ in vals)
    return {"level": ss_l / tot, "task": ss_t / tot, "cells": ss_c / tot,
            "within_cell": (tot - ss_c) / tot}


def variance_family(rows, levels, level_of, tasks, measures=MEASURES, draws=DRAWS,
                    seed=SEED) -> dict:
    counts = Counter((level_of(r), r["task_id"]) for r in rows
                     if level_of(r) in levels and r["task_id"] in tasks)
    per_cell = [counts.get((lv, t), 0) for lv in levels for t in tasks]
    out = {"balanced": False, "note": None, "tasks_used": [], "tasks_dropped": [],
           "levels_used": list(levels), "measures": {}}
    R = REPEATS if any(per_cell) else 0
    use_tasks = [t for t in tasks if all(counts.get((lv, t), 0) == R for lv in levels)]
    if R >= 2 and len(use_tasks) == len(tasks) and tasks:
        out["balanced"] = True
    elif R >= 2 and len(use_tasks) >= 2 and len(levels) >= 2:
        out["note"] = (f"unbalanced design: tested on the {len(use_tasks)} tasks where every "
                       f"level has {R} runs; dropped {sorted(set(tasks) - set(use_tasks))}; "
                       "marginal shares over all runs reported without tests")
    else:
        out["note"] = ("unbalanced design and no balanced subset of >= 2 tasks with >= 2 "
                       "repeats per cell: marginal shares only, no tests")
        use_tasks = []
    out["tasks_used"] = use_tasks
    out["tasks_dropped"] = [t for t in tasks if t not in use_tasks]
    out["runs_per_cell"] = R
    sub = [{**r, "model": level_of(r)} for r in rows
           if level_of(r) in levels and r["task_id"] in use_tasks]
    for i, (mid, key, _) in enumerate(measures):
        entry = {"key": key}
        if not out["balanced"]:
            entry["marginal_shares_all_runs"] = _marginal_shares(rows, key, levels, level_of,
                                                                 tasks)
        if use_tasks and all(r.get(key) is not None for r in sub):
            vs = ca.variance_split(sub, key, list(levels), use_tasks, draws=draws, seed=seed + i)
            cm = defaultdict(list)
            for r in sub:
                cm[(r["model"], r["task_id"])].append(ca.transform(key, r[key]))
            table = [[ca._mean(cm[(lv, t)]) for lv in levels] for t in use_tasks]
            vs["kendall_w"] = None if vs["constant"] else ca.kendall_w(table)
            vs.pop("ss", None)
            entry.update(vs)
        elif use_tasks:
            entry.update({"constant": False, "shares": None, "p_main": None, "p_cell": None,
                          "note": "undefined for some runs; not split"})
        else:
            entry.update({"constant": False, "shares": None, "p_main": None, "p_cell": None})
        out["measures"][mid] = entry
    ids = list(out["measures"])
    am = ca.holm([out["measures"][i].get("p_main") for i in ids])
    ac = ca.holm([out["measures"][i].get("p_cell") for i in ids])
    for i, mid in enumerate(ids):
        e = out["measures"][mid]
        e["p_main_holm"], e["p_cell_holm"] = am[i], ac[i]
        e["label"] = ca.decide(e) if e.get("shares") else "indeterminate"
    return out


# --------------------------------------------------------------------------
# exp-08 A5, A6, A7
# --------------------------------------------------------------------------

def _loto_predict(X, y, tasks, order):
    d = len(X[0]) if X else 0
    tot = defaultdict(lambda: [0.0] * d)
    cnt = Counter()
    ts = defaultdict(lambda: [0.0] * d)
    tc = Counter()
    for x, yi, t in zip(X, y, tasks, strict=True):
        cnt[yi] += 1
        tc[(yi, t)] += 1
        for j, v in enumerate(x):
            tot[yi][j] += v
            ts[(yi, t)][j] += v
    fold = {}
    for t in set(tasks):
        fold[t] = {m: [(s - u) / (cnt[m] - tc[(m, t)])
                       for s, u in zip(tot[m], ts[(m, t)], strict=True)]
                   for m in cnt if cnt[m] - tc[(m, t)] > 0}
    return [ca._nearest(x, fold[t], order) for x, t in zip(X, tasks, strict=True)]


def _acc_rank(pred, y, rank):
    n = len(y)
    acc = sum(p == t for p, t in zip(pred, y, strict=True)) / n
    err = sum(abs(rank[p] - rank[t]) if p is not None else len(rank)
              for p, t in zip(pred, y, strict=True)) / n
    return acc, err


def a5_profile_drift(rows, levels, level_of, draws=DRAWS, seed=SEED + 500) -> dict:
    S = [r for r in rows if level_of(r) in levels
         and all(r.get(k) is not None for k in MEASURE_KEYS)]
    present = [lv for lv in levels if any(level_of(r) == lv for r in S)]
    if len(present) < 2 or len({r["task_id"] for r in S}) < 2:
        return {"tested": False, "reason": "fewer than two levels or two tasks with runs",
                "n_runs": len(S)}
    X = ca._zscore(S, MEASURE_KEYS)
    if not X or not X[0]:
        return {"tested": False, "reason": "every measure constant", "n_runs": len(S)}
    y = [level_of(r) for r in S]
    tasks = [r["task_id"] for r in S]
    rank = {lv: i + 1 for i, lv in enumerate(levels)}
    acc, err = _acc_rank(_loto_predict(X, y, tasks, present), y, rank)
    rng = random.Random(seed)
    by_task = defaultdict(list)
    for i, t in enumerate(tasks):
        by_task[t].append(i)
    null_acc, null_err = [], []
    for _ in range(draws):
        yp = list(y)
        for t in sorted(by_task):
            idx = by_task[t]
            lab = [y[i] for i in idx]
            rng.shuffle(lab)
            for i, v in zip(idx, lab, strict=True):
                yp[i] = v
        a, e = _acc_rank(_loto_predict(X, yp, tasks, present), yp, rank)
        null_acc.append(a)
        null_err.append(e)
    srt = sorted(null_acc)
    q95 = srt[min(len(srt) - 1, int(math.ceil(0.95 * len(srt))) - 1)]
    p_rank = (1 + sum(ca._ge(-v, -err) for v in null_err)) / (1 + draws)
    p_acc = (1 + sum(ca._ge(v, acc) for v in null_acc)) / (1 + draws)
    return {"tested": True, "n_runs": len(S), "n_dropped_undefined":
            sum(1 for r in rows if level_of(r) in levels) - len(S),
            "features": len(X[0]), "chance": 1 / len(present), "accuracy": acc,
            "null_acc_q95": q95, "p_accuracy": p_acc, "rank_error": err,
            "null_rank_error_mean": sum(null_err) / len(null_err), "p_rank_error": p_rank,
            "above_chance": acc > 1 / len(present), "identification": acc > q95,
            "draws": draws}


def a6_outcome(rows, levels, level_of, tasks, family, draws=DRAWS, seed=SEED) -> dict:
    per_cell, per_level = {}, {}
    for lv in levels:
        g = [r for r in rows if level_of(r) == lv and r["task_id"] in tasks
             and r["resolved"] is not None]
        per_level[lv] = {"graded": len(g), "resolved": sum(bool(r["resolved"]) for r in g)}
        for t in tasks:
            c = [r for r in g if r["task_id"] == t]
            per_cell[f"{lv}|{t}"] = f"{sum(bool(r['resolved']) for r in c)}/{len(c)}"
    rates = [v["resolved"] / v["graded"] for v in per_level.values() if v["graded"]]
    differs = len(rates) >= 2 and max(rates) - min(rates) > 1e-12
    out = {"per_level": per_level, "per_cell": per_cell, "differs": differs,
           "resolved_only": {}}
    if differs:
        res_rows = [r for r in rows if r["resolved"]]
        for mid, f in family.items():
            if f["label"] != "trend":
                continue
            cells = _cells_of(res_rows, f["key"], levels, level_of, tasks)
            t = page_trend(levels, tasks, cells, draws=draws, seed=seed)
            t.pop("cell_values", None)
            out["resolved_only"][mid] = t
    return out


def load_bridge_rows() -> list[dict]:
    """The 27 included round 1 runs on the bridge task, coded with the same code."""
    out = []
    for r in manifest.load_runs():
        if r["task_id"] != BRIDGE_TASK or not r["included"]:
            continue
        d = manifest.CORPUS / r["batch"] / r["run_id"]
        row = run_row(d, BRIDGE_TASK, {"run_id": r["run_id"], "model": r["model"],
                                       "resolved": r["resolved"]})
        row["resolved"] = r["resolved"]
        row["round"] = 1
        out.append(row)
    return out


def a7_bridge(rows, levels, level_of, bridge_rows) -> dict:
    keys = MEASURE_KEYS + ["resolved", "unsupported_done"]

    def summ(rs):
        d = {"n": len(rs)}
        for k in keys:
            if k in ("resolved", "unsupported_done"):
                d[k] = _mean_all([None if r.get(k) is None else float(r[k]) for r in rs])
            else:
                d[k] = _mean_all([ca.transform(k, r.get(k)) for r in rs])
        return d

    out = {"note": "descriptive only; different providers, settings and dates; analysis scale",
           "round2": {}, "round1": {}}
    for lv in levels:
        rs = [r for r in rows if level_of(r) == lv and r["task_id"] == BRIDGE_TASK]
        if rs:
            out["round2"][lv] = summ(rs)
    by_model = defaultdict(list)
    for r in bridge_rows:
        by_model[r["model"]].append(r)
    for mm in sorted(by_model):
        out["round1"][mm] = summ(by_model[mm])
    out["n_round1"] = len(bridge_rows)
    return out


# --------------------------------------------------------------------------
# Validation V1, V2
# --------------------------------------------------------------------------

def v1_coverage(rows, levels, level_of) -> dict:
    out = {}
    for lv in levels:
        rs = [r for r in rows if level_of(r) == lv]
        if not rs:
            continue
        tot = Counter()
        for r in rs:
            for k in ("cov_records", "cov_records_other", "cov_segments", "cov_segments_other",
                      "cov_edits", "cov_edits_unknown"):
                tot[k] += r.get(k) or 0
        other = tot["cov_records_other"] / tot["cov_records"] if tot["cov_records"] else 0.0
        seg = tot["cov_segments_other"] / tot["cov_segments"] if tot["cov_segments"] else 0.0
        unk = tot["cov_edits_unknown"] / tot["cov_edits"] if tot["cov_edits"] else 0.0
        out[lv] = {"runs": len(rs), "commands_other_share": other,
                   "segments_other_share": seg, "edits_unknown_share": unk,
                   "unreliable": other > COVERAGE_LIMIT or unk > COVERAGE_LIMIT}
    return out


def v2_runner_start(rows) -> dict:
    by_task = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)
    out = {}
    for t in sorted(by_task):
        rs = by_task[t]
        k = sum(r.get("runner_start_fail") or 0 for r in rs)
        out[t] = {"runs": len(rs), "runner_start_fail": k,
                  "after_source_edit": sum(r.get("runner_start_fail_after_edit") or 0
                                           for r in rs),
                  "runs_with_test": sum(r.get("has_test") or 0 for r in rs),
                  "dropped": bool(rs) and 2 * k >= len(rs)}
    return out


# --------------------------------------------------------------------------
# Part B
# --------------------------------------------------------------------------

def part_b(labels: list[dict], levels: list, tasks: list, draws=DRAWS, seed=SEED) -> dict:
    """labels: dicts with run_id, level, task_id, candidate, pass (1/2), value (0/1)."""
    by_c = defaultdict(list)
    for lab in labels:
        by_c[lab["candidate"]].append(lab)
    res = {}
    for c in sorted(by_c):
        ls = by_c[c]
        p1 = {lab["run_id"]: lab["value"] for lab in ls if lab["pass"] == 1}
        p2 = {lab["run_id"]: lab["value"] for lab in ls if lab["pass"] == 2}
        common = sorted(set(p1) & set(p2))
        kappa = ca.cohen_kappa([p1[r] for r in common], [p2[r] for r in common])
        entry = {"kappa": kappa, "n_runs": len(common),
                 "reliable": kappa is not None and kappa >= 0.6}
        counts = defaultdict(lambda: [0, 0])
        cells = defaultdict(list)
        for lab in ls:
            cells[(lab["level"], lab["task_id"])].append(float(lab["value"]))
            counts[lab["level"]][0] += int(bool(lab["value"]))
            counts[lab["level"]][1] += 1
        entry["count_table"] = {lv: f"{counts[lv][0]}/{counts[lv][1]}" for lv in levels}
        if entry["reliable"]:
            t = page_trend(levels, tasks, cells, draws=draws, seed=seed,
                           min_blocks=len(tasks))
            t.pop("cell_values", None)
            entry["trend"] = t
        res[c] = entry
    tested = [c for c in res if res[c].get("trend", {}).get("p") is not None]
    adj = ca.holm([res[c]["trend"]["p"] for c in tested])
    for c, a in zip(tested, adj, strict=True):
        t = res[c]["trend"]
        t["p_holm"] = a
        res[c]["label"] = decide_trend(t["p"], a, t["agree"], t["disagree"], t["direction"],
                                       min_signed=2, max_disagree=0)
    for c in res:
        res[c].setdefault("label", "unreliable" if not res[c]["reliable"] else "not tested")
    return res


# --------------------------------------------------------------------------
# Predictions
# --------------------------------------------------------------------------

PREDICTIONS = {
    "exp-08": [
        ("P1", "`backed_done` rises with generation (trend or candidate)."),
        ("P2", "`test_share` rises with generation (trend or candidate)."),
        ("P3", "`n_cmds` shows no trend: run length is a per-model quirk, as in exp-07."),
        ("P4", "`early_edit_share` is near zero for all five models, so it cannot show a "
               "trend."),
        ("P5", "`multi_call_share` falls with generation (older models in the settings check "
               "sent two calls in one reply more often)."),
        ("P6", "At least one and at most three of the 15 measures are labelled trend."),
        ("P7", "A5: identification is above chance, and the rank error is below its null "
               "(p < 0.05)."),
    ],
    "exp-09": [
        ("P1", "`n_cmds` rises with effort (responds or candidate)."),
        ("P2", "`test_share` rises with effort (responds or candidate)."),
        ("P3", "`backed_done` rises with effort (responds or candidate)."),
        ("P4", "`reread_share` and `repeat_cmd_share` are not shown to respond."),
        ("P5", "Thinking tokens per reply rise with effort (A5 passes)."),
        ("P6", "At least three of the 15 measures respond to effort."),
    ],
    "exp-10": [
        ("P1", "`backed_done` rises with size (moves or candidate)."),
        ("P2", "`repeat_cmd_share` falls with size (moves or candidate)."),
        ("P3", "`n_cmds` shows no ordered pattern."),
        ("P4", "Haiku 5.5 has the lowest `backed_done` of the four."),
        ("P5", "At least one of the 15 measures moves with size."),
    ],
}
NEAR_ZERO = 0.05   # exp-08 P4: every generation's mean early_edit_share <= this


def check_prediction_text(exp: str) -> list[str]:
    """Prediction texts not found verbatim in the experiment file."""
    path = EXP_DIR / f"{EXPERIMENTS[exp]['slug']}.md"
    try:
        text = path.read_text()
    except OSError:
        return [f"{path} not readable"]
    return [pid for pid, t in PREDICTIONS[exp] if f"- {pid}. {t}" not in text]


def _v(held, testable=True, why=""):
    if not testable:
        return {"verdict": "not testable", "why": why}
    return {"verdict": "held" if held else "not held", "why": why}


def _by_key(family, key):
    return next((f for f in family.values() if f["key"] == key), None)


def _moves(f, direction):
    if f is None or f["p"] is None:
        return _v(False, False, "not tested")
    ok = f["label"] in ("trend", "candidate") and f["direction"] == direction
    return _v(ok, True, f"label {f['label']}, direction {f['direction']:+d}, p {f['p']:.4g}")


def _label_is(f, labels):
    if f is None or f["p"] is None:
        return _v(False, False, "not tested")
    return _v(f["label"] in labels, True, f"label {f['label']}")


def _count_trend(family, at_least, at_most=None):
    tested = [f for f in family.values() if f["p"] is not None]
    if not tested:
        return _v(False, False, "no measure tested")
    n = sum(f["label"] == "trend" for f in family.values())
    ok = n >= at_least and (at_most is None or n <= at_most)
    return _v(ok, True, f"{n} labelled trend of {len(tested)} tested")


def score_exp08(an) -> dict:
    fam = an.get("A2_A4") or {}
    s = {"P1": _moves(_by_key(fam, "backed_done"), +1),
         "P2": _moves(_by_key(fam, "test_share"), +1),
         "P3": _label_is(_by_key(fam, "n_cmds"), ("none",))}
    f = _by_key(fam, "early_edit_share")
    means = (f or {}).get("level_means") or {}
    if len(means) == 5 and all(v is not None for v in means.values()):
        s["P4"] = _v(all(v <= NEAR_ZERO for v in means.values()), True,
                     f"max generation mean {max(means.values()):.3f} (near zero <= {NEAR_ZERO})"
                     f"; label {f['label']}")
    else:
        s["P4"] = _v(False, False, "not every generation has runs")
    s["P5"] = _moves(_by_key(fam, "multi_call_share"), -1)
    s["P6"] = _count_trend(fam, 1, 3)
    a5 = an.get("A5_profile_drift") or {}
    if a5.get("tested"):
        s["P7"] = _v(a5["identification"] and a5["p_rank_error"] < 0.05, True,
                     f"accuracy {a5['accuracy']:.3f} vs null q95 {a5['null_acc_q95']:.3f}; "
                     f"rank error p {a5['p_rank_error']:.4g}")
    else:
        s["P7"] = _v(False, False, a5.get("reason", "A5 not run"))
    return s


def score_exp09(an) -> dict:
    fam = an.get("A2_A4") or {}
    s = {"P1": _moves(_by_key(fam, "n_cmds"), +1),
         "P2": _moves(_by_key(fam, "test_share"), +1),
         "P3": _moves(_by_key(fam, "backed_done"), +1)}
    a, b = _by_key(fam, "reread_share"), _by_key(fam, "repeat_cmd_share")
    if a and b and a["p"] is not None and b["p"] is not None:
        s["P4"] = _v(a["label"] == "none" and b["label"] == "none", True,
                     f"reread_share {a['label']}, repeat_cmd_share {b['label']}")
    else:
        s["P4"] = _v(False, False, "not tested")
    a5 = an.get("A5_thinking") or {}
    t = a5.get("test") or {}
    if t.get("p") is not None:
        s["P5"] = _v(a5["passes"], True, f"p {t['p']:.4g}, direction {t['direction']:+d}")
    else:
        s["P5"] = _v(False, False, t.get("reason") or "thinking tokens not available")
    s["P6"] = _count_trend(fam, 3)
    return s


def score_exp10(an) -> dict:
    fam = an.get("A2_A4") or {}
    s = {"P1": _moves(_by_key(fam, "backed_done"), +1),
         "P2": _moves(_by_key(fam, "repeat_cmd_share"), -1),
         "P3": _label_is(_by_key(fam, "n_cmds"), ("none",))}
    f = _by_key(fam, "backed_done")
    means = (f or {}).get("level_means") or {}
    if len(means) == 4 and all(v is not None for v in means.values()):
        h = means["claude-haiku-5-5"]
        s["P4"] = _v(all(h < v for lv, v in means.items() if lv != "claude-haiku-5-5"), True,
                     "means " + ", ".join(f"{lv} {v:.3f}" for lv, v in means.items()))
    else:
        s["P4"] = _v(False, False, "not all four models have runs")
    s["P5"] = _count_trend(fam, 1)
    return s


SCORERS = {"exp-08": score_exp08, "exp-09": score_exp09, "exp-10": score_exp10}


# --------------------------------------------------------------------------
# Experiment drivers
# --------------------------------------------------------------------------

def _level_of(exp):
    conds = {c: level_name(exp, c) for c in EXPERIMENTS[exp]["levels"]}
    return lambda r: conds.get((r.get("model"), r.get("effort")))


def missing_cells(rows, exp, tasks) -> list[str]:
    lo = _level_of(exp)
    have = Counter((lo(r), r["task_id"]) for r in rows if lo(r) is not None)
    out = []
    for c in EXPERIMENTS[exp]["levels"]:
        lv = level_name(exp, c)
        for t in tasks:
            n = have.get((lv, t), 0)
            if n < REPEATS:
                out.append(f"{lv} x {t}: {n}/{REPEATS} runs")
    return out


def analyse_experiment(exp, all_rows, tasks, draws=DRAWS, a5_draws=DRAWS, cache=None,
                       bridge_rows=None, v2=None) -> dict:
    cfg = EXPERIMENTS[exp]
    cache = {} if cache is None else cache
    lo = _level_of(exp)
    levels = [level_name(exp, c) for c in cfg["levels"]]
    rows = [r for r in all_rows if lo(r) is not None]
    v2 = v2 if v2 is not None else v2_runner_start(all_rows)
    dropped = [t for t in tasks if v2.get(t, {}).get("dropped")]
    use_tasks = [t for t in tasks if t not in dropped]
    present = [lv for lv in levels if any(lo(r) == lv for r in rows)]
    an = {"experiment": cfg["slug"], "status": STATUS, "factor": cfg["factor"],
          "levels": levels, "levels_with_runs": present, "tasks": tasks,
          "tasks_dropped_v2": dropped, "n_runs": len(rows),
          "missing_cells": missing_cells(all_rows, exp, tasks),
          "prediction_text_mismatch": check_prediction_text(exp),
          "V1_coverage": v1_coverage(rows, levels, lo), "V2_runner_start": v2}
    an["A1_variance_split"] = variance_family(rows, levels, lo, use_tasks, draws=draws)
    test_levels = levels
    if exp == "exp-10" and len(present) == 3 and "claude-fable-5-2" not in present:
        test_levels = None
        an["A2_note"] = ("three levels (Fable absent): descriptive only, no test, as the "
                         "experiment file requires")
    if test_levels is not None:
        fam = trend_family(rows, levels, lo, use_tasks, draws=draws)
    else:
        fam = {mid: {"key": key, "p": None, "p_holm": None, "label": "not tested",
                     "direction": 0, "agree": None, "disagree": None, "no_sign": None,
                     "n_blocks": 0,
                     "dropped_blocks": [], "reason": "three levels; no test", "shape": None,
                     "L": None, "E0": None,
                     "level_means": {lv: _mean_all([ca.transform(key, r.get(key)) for r in rows
                                                    if lo(r) == lv and r["task_id"] in use_tasks])
                                     for lv in levels}}
               for mid, key, _ in MEASURES}
    for f in fam.values():
        f["label_name"] = cfg["names"].get(f["label"], f["label"])
    an["A2_A4"] = fam
    an["U_by_level"] = _u_by_level(rows, levels, lo, use_tasks)
    an["context_by_level"] = _context_by_level(rows, levels, lo, use_tasks)
    if exp == "exp-08":
        an["A5_profile_drift"] = a5_profile_drift(
            [r for r in rows if r["task_id"] in use_tasks], levels, lo, draws=a5_draws)
        an["A6_outcome"] = a6_outcome(rows, levels, lo, use_tasks, fam, draws=draws)
        an["A7_bridge"] = a7_bridge(rows, levels, lo, bridge_rows or [])
    if exp in ("exp-09", "exp-10"):
        e8 = cache.get("exp-08_family")
        if e8 is None:
            lo8 = _level_of("exp-08")
            lv8 = [level_name("exp-08", c) for c in EXPERIMENTS["exp-08"]["levels"]]
            e8 = trend_family([r for r in all_rows if lo8(r)], lv8, lo8, use_tasks, draws=draws)
            cache["exp-08_family"] = e8
    if exp == "exp-09":
        cells = _cells_of(rows, "thinking_tokens_per_reply", levels, lo, use_tasks)
        t = page_trend(levels, use_tasks, cells, draws=draws)
        t.pop("cell_values", None)
        passes = t["p"] is not None and t["p"] < 0.05 and t["direction"] == 1
        an["A5_thinking"] = {
            "test": t, "passes": passes,
            "thinking_tokens_per_reply": an["context_by_level"]["thinking_tokens_per_reply"],
            "max_tokens_replies": an["context_by_level"]["max_tokens_replies_total"]}
        an["uninformative"] = not passes
        lo8 = _level_of("exp-08")
        lv8 = [level_name("exp-08", c) for c in EXPERIMENTS["exp-08"]["levels"]]
        rows8 = [r for r in all_rows if lo8(r) and r["task_id"] in use_tasks]
        table = {}
        for mid, f in fam.items():
            l8 = e8[mid]["label"]
            reading = None
            if l8 in ("none", "not tested"):
                reading = ("informative" if f["label"] == "trend"
                           else "instrument not shown to be sensitive")
            table[mid] = {"key": f["key"], "exp08": EXPERIMENTS["exp-08"]["names"].get(l8, l8),
                          "exp09": f["label_name"], "reading_of_exp08_none": reading}
        an["A6_dial_table"] = {"measures": table, "thinking_tokens_per_reply_by_generation": {
            lv: _mean_all([r.get("thinking_tokens_per_reply") for r in rows8 if lo8(r) == lv])
            for lv in lv8}}
    if exp == "exp-10":
        table = {}
        for mid, f in fam.items():
            g = e8[mid]
            table[mid] = {"key": f["key"], "exp08": g["label"], "exp08_dir": g["direction"],
                          "exp10": f["label"], "exp10_dir": f["direction"],
                          "reading": _size_reading(g, f)}
        an["A5_generation_vs_size"] = table
    scored = SCORERS[exp](an)
    an["predictions"] = {pid: {"text": txt, **scored[pid]} for pid, txt in PREDICTIONS[exp]}
    if exp == "exp-09" and an.get("uninformative"):
        an["predictions_note"] = "A5 failed: the experiment is reported as uninformative"
    return an


def _size_reading(g, f) -> str:
    a, b = g["label"], f["label"]
    if "not tested" in (a, b):
        return "not tested"
    if "candidate" in (a, b):
        return "not classified (candidate)"
    if a == "trend" and b == "trend":
        if g["direction"] == f["direction"]:
            return "follows capability; generation and size cannot be separated"
        return "trend in both, opposite directions (none of the four readings)"
    if a == "trend":
        return "follows the generation"
    if b == "trend":
        return "follows size"
    return "no ordered pattern found"


def _u_by_level(rows, levels, lo, tasks):
    out = {}
    for lv in levels:
        rs = [r for r in rows if lo(r) == lv and r["task_id"] in tasks
              and r["exit_reason"] == "completed"]
        d = [r for r in rs if r["unsupported_done"] is not None]
        k = sum(r["unsupported_done"] for r in d)
        lo_, hi_ = ca.clopper_pearson(k, len(d))
        out[lv] = {"completed": len(rs), "no_edit": sum(r["no_edit"] for r in rs),
                   "U_unknown": sum(r.get("U_unknown") or 0 for r in rs),
                   "U": k, "n_defined": len(d), "ci95": [lo_, hi_]}
    return out


def _context_by_level(rows, levels, lo, tasks):
    out = defaultdict(dict)
    for lv in levels:
        rs = [r for r in rows if lo(r) == lv and r["task_id"] in tasks]
        out["runs"][lv] = len(rs)
        g = [r for r in rs if r["resolved"] is not None]
        out["resolved"][lv] = f"{sum(bool(r['resolved']) for r in g)}/{len(g)}"
        out["exit_reasons"][lv] = dict(Counter(r["exit_reason"] for r in rs))
        for k in ("turns", "thinking_tokens_per_reply", "output_tokens_per_reply", "cost_usd"):
            out[k][lv] = _mean_all([r.get(k) for r in rs])
        mt = [r.get("max_tokens_replies") for r in rs if r.get("max_tokens_replies") is not None]
        out["max_tokens_replies_total"][lv] = sum(mt) if mt else None
        out["cost_usd_total"][lv] = sum(r.get("cost_usd") or 0 for r in rs)
    return dict(out)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

CSV_COLS = (["run_id", "model", "effort", "task_id", "repeat", "stage", "exit_reason",
             "resolved"] + MEASURE_KEYS + ["unsupported_done", "U_lenient", "U_unknown",
                                           "U_sensitivity", "no_edit"]
            + ["turns", "n_replies", "thinking_tokens_per_reply", "output_tokens_per_reply",
               "max_tokens_replies", "cost_usd"] + ca.DESCRIPTIVE
            + ["cov_records", "cov_records_other", "cov_segments", "cov_segments_other",
               "cov_edits", "cov_edits_unknown", "has_test", "runner_start_fail",
               "runner_start_fail_after_edit", "primary_seq"])


def write_metrics_csv(rows, path):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(CSV_COLS)
        for r in rows:
            vals = []
            for c in CSV_COLS:
                v = r.get(c)
                if c == "primary_seq":
                    v = " ".join(v or [])
                elif isinstance(v, bool):
                    v = int(v)
                vals.append("" if v is None else v)
            w.writerow(vals)


def _f(x, d=3):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{d}f}"
    return str(x)


def tables_md(an: dict) -> str:
    lines = [f"# {an['experiment']} results [{an['status']}]", ""]
    lines.append(f"Runs: {an['n_runs']}. Levels ({an['factor']}): {', '.join(an['levels'])}.")
    lines.append(f"Tasks: {', '.join(an['tasks']) or '(none)'}.")
    if an["tasks_dropped_v2"]:
        lines.append(f"Dropped by V2 (runner start): {', '.join(an['tasks_dropped_v2'])}.")
    if an["missing_cells"]:
        lines.append(f"\nMissing or incomplete cells ({len(an['missing_cells'])}):")
        lines += [f"- {m}" for m in an["missing_cells"]]
    if an.get("prediction_text_mismatch"):
        lines.append("\nPrediction text differs from the experiment file for: "
                     + ", ".join(an["prediction_text_mismatch"]))
    unrel = [lv for lv, v in an["V1_coverage"].items() if v["unreliable"]]
    lines += ["", "## V1 coverage", "",
              "| level | runs | commands other | segments other | edits unknown | flag |",
              "|---|---|---|---|---|---|"]
    for lv, v in an["V1_coverage"].items():
        lines.append(f"| {lv} | {v['runs']} | {_f(v['commands_other_share'])} | "
                     f"{_f(v['segments_other_share'])} | {_f(v['edits_unknown_share'])} | "
                     f"{'UNRELIABLE' if v['unreliable'] else ''} |")
    lines += ["", "## V2 runner start", "", "| task | runs | runner failed | after edit | dropped |",
              "|---|---|---|---|---|"]
    for t, v in an["V2_runner_start"].items():
        lines.append(f"| {t} | {v['runs']} | {v['runner_start_fail']} | "
                     f"{v['after_source_edit']} | {'yes' if v['dropped'] else ''} |")
    a1 = an["A1_variance_split"]
    lines += ["", "## A1 variance split", ""]
    lines.append("Balanced design." if a1["balanced"] else f"Note: {a1['note']}")
    lines += ["", "| id | measure | level | task | lvl:task | repeat | p_main* | p_cell | label |",
              "|---|---|---|---|---|---|---|---|---|"]
    for mid, e in a1["measures"].items():
        sh = e.get("shares") or {}
        lines.append(f"| {mid} | {e['key']} | {_f(sh.get('model'), 2)} | {_f(sh.get('task'), 2)}"
                     f" | {_f(sh.get('model:task'), 2)} | {_f(sh.get('repeat'), 2)} | "
                     f"{_f(e.get('p_main_holm'))} | {_f(e.get('p_cell'))} | {e['label']} |")
    lines += ["", "## A2-A4 trend test", ""]
    if an.get("A2_note"):
        lines.append(an["A2_note"] + "\n")
    flag = f" (V1 unreliable: {', '.join(unrel)})" if unrel else ""
    lines += [f"Holm over the tested measures{flag}.", "",
              "| id | measure | blocks | L - E0 | p | p Holm | agree/disagree/no sign | label |"
              " shape | "
              + " | ".join(an["levels"]) + " |",
              "|---|---|---|---|---|---|---|---|---|" + "---|" * len(an["levels"])]
    for mid, f in an["A2_A4"].items():
        dlt = None if f["L"] is None else f["L"] - f["E0"]
        ag = "-" if f["agree"] is None else f"{f['agree']}/{f['disagree']}/{f['no_sign']}"
        shp = (f.get("shape") or {}).get("shape") or ""
        means = " | ".join(_f(f["level_means"].get(lv)) for lv in an["levels"])
        lines.append(f"| {mid} | {f['key']} | {f['n_blocks']} | {_f(dlt, 1)} | {_f(f['p'], 4)} | "
                     f"{_f(f['p_holm'], 4)} | {ag} | {f['label_name']} | {shp} | {means} |")
    ctx = an["context_by_level"]
    lines += ["", "## Context (not tested)", "", "| | " + " | ".join(an["levels"]) + " |",
              "|---|" + "---|" * len(an["levels"])]
    for k in ("runs", "resolved", "turns", "thinking_tokens_per_reply",
              "output_tokens_per_reply", "max_tokens_replies_total", "cost_usd_total"):
        lines.append(f"| {k} | " + " | ".join(_f(ctx[k].get(lv), 1) for lv in an["levels"])
                     + " |")
    lines.append("| U (completed, edited) | " + " | ".join(
        f"{v['U']}/{v['n_defined']}" for v in an["U_by_level"].values()) + " |")
    if "A5_profile_drift" in an:
        a5 = an["A5_profile_drift"]
        lines += ["", "## A5 profile drift", ""]
        if a5.get("tested"):
            lines.append(f"LOTO accuracy {_f(a5['accuracy'])} (chance {_f(a5['chance'])}, "
                         f"null q95 {_f(a5['null_acc_q95'])}, p {_f(a5['p_accuracy'], 4)}); "
                         f"rank error {_f(a5['rank_error'])} (null mean "
                         f"{_f(a5['null_rank_error_mean'])}, p {_f(a5['p_rank_error'], 4)}).")
        else:
            lines.append(f"Not run: {a5.get('reason')}.")
        a6 = an["A6_outcome"]
        lines += ["", "## A6 outcome check", "",
                  "Resolved per generation: " + ", ".join(
                      f"{lv} {v['resolved']}/{v['graded']}" for lv, v in a6["per_level"].items())
                  + f". Differs: {a6['differs']}."]
        for mid, t in a6["resolved_only"].items():
            lines.append(f"- {mid} on resolved runs: blocks {t['n_blocks']}, p {_f(t['p'], 4)}, "
                         f"direction {t['direction']:+d}, agree/disagree/no sign "
                         f"{t['agree']}/{t['disagree']}/{t['no_sign']}")
        a7 = an["A7_bridge"]
        lines += ["", f"## A7 bridge ({BRIDGE_TASK}; {a7['note']})", "",
                  "| run set | n | resolved | " + " | ".join(MEASURE_KEYS) + " |",
                  "|---|---|---|" + "---|" * len(MEASURE_KEYS)]
        for tag in ("round2", "round1"):
            for mm, d in a7[tag].items():
                lines.append(f"| {tag}: {mm} | {d['n']} | {_f(d['resolved'], 2)} | "
                             + " | ".join(_f(d[k], 2) for k in MEASURE_KEYS) + " |")
    if "A5_thinking" in an:
        a5 = an["A5_thinking"]
        t = a5["test"]
        lines += ["", "## A5 thinking actually changed", "",
                  f"Trend test on thinking tokens per reply: p {_f(t['p'], 4)}, direction "
                  f"{t['direction']:+d} -> {'passes' if a5['passes'] else 'FAILS'}"
                  + ("; experiment uninformative" if an.get("uninformative") else "") + "."]
        a6 = an["A6_dial_table"]
        lines += ["", "## A6 exp-08 through the dial", "",
                  "| id | measure | exp-08 | exp-09 | reading of exp-08 none |",
                  "|---|---|---|---|---|"]
        for mid, d in a6["measures"].items():
            lines.append(f"| {mid} | {d['key']} | {d['exp08']} | {d['exp09']} | "
                         f"{d['reading_of_exp08_none'] or ''} |")
        lines.append("\nThinking tokens per reply by Opus generation: " + ", ".join(
            f"{lv} {_f(v, 0)}" for lv, v in a6["thinking_tokens_per_reply_by_generation"].items()))
    if "A5_generation_vs_size" in an:
        lines += ["", "## A5 generation against size", "",
                  "Fable 5.2 is a separate product line, not a member of the 5.5 family.", "",
                  "| id | measure | exp-08 | dir | exp-10 | dir | reading |",
                  "|---|---|---|---|---|---|---|"]
        for mid, d in an["A5_generation_vs_size"].items():
            lines.append(f"| {mid} | {d['key']} | {d['exp08']} | {d['exp08_dir']:+d} | "
                         f"{d['exp10']} | {d['exp10_dir']:+d} | {d['reading']} |")
    lines += ["", "## Predictions", ""]
    if an.get("predictions_note"):
        lines.append(an["predictions_note"] + "\n")
    for pid, p in an["predictions"].items():
        lines.append(f"- {pid}. {p['text']} -> **{p['verdict']}** ({p['why']})")
    return "\n".join(lines) + "\n"


def write_outputs(an, rows, out_dir):
    os.makedirs(str(out_dir), exist_ok=True)
    write_metrics_csv(rows, os.path.join(str(out_dir), "metrics.csv"))
    with open(os.path.join(str(out_dir), "analysis.json"), "w") as f:
        json.dump(ca._jsonable(an), f, indent=2, default=str)
    with open(os.path.join(str(out_dir), "tables.md"), "w") as f:
        f.write(tables_md(an))


def run(experiments, runs_root, ledger, out=None, round_json=ROUND_JSON, draws=DRAWS,
        bridge=True) -> dict:
    rows, report = load_round(runs_root, ledger)
    tasks = load_round_tasks(round_json)
    if tasks is None:
        tasks = sorted({r["task_id"] for r in rows})
        report["notes"].append(f"no task list in {round_json}; using tasks found in runs")
    bridge_rows = load_bridge_rows() if bridge and "exp-08" in experiments else []
    v2 = v2_runner_start(rows)
    cache, results = {}, {}
    for exp in experiments:
        an = analyse_experiment(exp, rows, tasks, draws=draws, a5_draws=draws, cache=cache,
                                bridge_rows=bridge_rows, v2=v2)
        an["load_report"] = report
        lo = _level_of(exp)
        exp_rows = [r for r in rows if lo(r) is not None]
        if out is None:
            od = RESULTS / EXPERIMENTS[exp]["slug"]
        elif len(experiments) > 1:
            od = os.path.join(str(out), EXPERIMENTS[exp]["slug"])
        else:
            od = out
        write_outputs(an, exp_rows, od)
        results[exp] = {"out": str(od), "analysis": an}
    return {"report": report, "results": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--experiment", required=True, choices=["exp-08", "exp-09", "exp-10", "all"])
    ap.add_argument("--runs-root", default=str(manifest.ROOT / "runs"))
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--round-json", default=str(ROUND_JSON))
    ap.add_argument("--out", default=None)
    ap.add_argument("--draws", type=int, default=DRAWS, help="permutation draws (default 10000;"
                    " lower values are for testing only and change every p value)")
    ap.add_argument("--no-bridge", action="store_true", help="skip the A7 bridge runs")
    a = ap.parse_args(argv)
    exps = ["exp-08", "exp-09", "exp-10"] if a.experiment == "all" else [a.experiment]
    res = run(exps, a.runs_root, a.ledger, a.out, a.round_json, a.draws, not a.no_bridge)
    rep = res["report"]
    print(f"[{STATUS}] runs loaded: {rep['n_runs']} (source: {rep['source']})")
    for n in rep["notes"]:
        print(f"  note: {n}")
    if rep["missing_run_folders"]:
        print(f"  ledger runs without a folder: {len(rep['missing_run_folders'])}")
    if rep["ungraded_runs"]:
        print(f"  ungraded runs: {len(rep['ungraded_runs'])}")
    for exp, r in res["results"].items():
        an = r["analysis"]
        print(f"{exp}: {an['n_runs']} runs, {len(an['missing_cells'])} missing/incomplete cells"
              f" -> {r['out']}")
        labels = Counter(f["label_name"] for f in an["A2_A4"].values())
        print(f"  labels: {dict(labels)}")
        for pid, p in an["predictions"].items():
            print(f"  {pid}: {p['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
