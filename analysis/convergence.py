"""Cross-repeat convergence (reliability / sharpening probe).

Experiment restart 2026-08-28. Metric definitions are fixed here, in code,
before any results were inspected.

Design
------
Unit: a cell = (model, verified task) with K=3 same-condition repeats.
  - Corpora: data/runs-2026-07-generational-study, data/runs-2026-07-thinking-extension
  - Verified tasks only: pytest-5262, sympy-13757, sympy-22914, sympy-23534
  - Excluded: crashed runs; the 2026-08-02 kimi-k3 raised-cap rerun (separate
    condition). Any cell with >3 runs keeps the 3 earliest timestamps.

Per pair of repeats (3 pairs per cell), computed from artifacts only:
  patch_exact   1 if the normalized edit sets are identical, else 0.
  edit_jaccard  Jaccard over {(file, +/-, normalized line)} across the two
                workspace.patch files (context lines ignored, whitespace
                right-stripped).
  file_jaccard  Jaccard over the sets of files touched.
  verb_seq_sim  difflib.SequenceMatcher ratio over the sequences of command
                verbs (first token of each executed command).
  cmd_jaccard   Jaccard over the multiset-collapsed sets of full normalized
                command strings (order-free content overlap).
Empty patches: both empty -> patch metrics 1.0 and pair flagged both_empty
(consistently producing nothing is convergence, but is reported separately);
exactly one empty -> patch metrics 0.0.

Aggregation: cell value = mean over its 3 pairs; model value = mean over its
4 cells. Cells are also split by outcome (3/3 solved, 0/3, mixed) so that
convergent *failure* — the purest concentration signal — is visible on its
own. Solve outcome derives from grade.json: applies & builds & F2P all pass
& no P2P failures.

Interpretation boundary (fixed in advance): comparisons are made within lab
lineages only (v3-0324->v4-pro, gpt-4.1->gpt-5.5, o1->o3, r1->v3.2,
k2.6->k3); cross-lab numbers are descriptive. With 4 task clusters this is
an exploratory analysis: effect directions and sizes, no significance tests.
"""

import difflib
import json
import os
from collections import defaultdict

CORPORA = [
    "data/runs-2026-07-generational-study",
    "data/runs-2026-07-thinking-extension",
]
VERIFIED = [
    "pytest-dev__pytest-5262",
    "sympy__sympy-13757",
    "sympy__sympy-22914",
    "sympy__sympy-23534",
]
ORDER = [
    "chat-v3-0324", "r1-0528", "o1", "gpt-4.1", "v3.2",
    "kimi-k2.6", "o3", "kimi-k3", "gpt-5.5", "v4-pro",
]
PAIRS = [
    ("deepseek chat", "chat-v3-0324", "v4-pro"),
    ("openai chat", "gpt-4.1", "gpt-5.5"),
    ("openai think", "o1", "o3"),
    ("deepseek think", "r1-0528", "v3.2"),
    ("kimi", "kimi-k2.6", "kimi-k3"),
]


def short_model(model: str) -> str:
    return model.replace("openrouter_deepseek_deepseek-", "").replace("deepseek-", "")


def resolved(g: dict) -> bool:
    return bool(
        g.get("applies_cleanly") and g.get("builds") and g.get("f2p_passed")
        and not g.get("f2p_failed") and not g.get("p2p_failed")
    )


def parse_patch(path: str):
    """-> (files frozenset, edits frozenset of (file, sign, line))."""
    files, edits = set(), set()
    cur = None
    if not os.path.isfile(path):
        return frozenset(), frozenset()
    for line in open(path, errors="replace"):
        if line.startswith("+++ "):
            cur = line[4:].strip()
            cur = cur[2:] if cur.startswith("b/") else cur
            if cur != "/dev/null":
                files.add(cur)
        elif line.startswith("--- "):
            continue
        elif line.startswith("+") and cur:
            edits.add((cur, "+", line[1:].rstrip()))
        elif line.startswith("-") and cur:
            edits.add((cur, "-", line[1:].rstrip()))
    return frozenset(files), frozenset(edits)


def commands(run_dir: str):
    seq = []
    tp = os.path.join(run_dir, "raw_transcript.jsonl")
    if not os.path.isfile(tp):
        return seq
    for line in open(tp, errors="replace"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "command" in r:
            seq.append(" ".join(str(r["command"]).split()))
    return seq


def jac(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a or b) else 1.0


def pair_metrics(ra: dict, rb: dict) -> dict:
    fa, ea = ra["patch"]
    fb, eb = rb["patch"]
    both_empty = not ea and not eb
    one_empty = (not ea) != (not eb)
    if one_empty:
        p_exact, e_j, f_j = 0.0, 0.0, 0.0
    else:
        p_exact = 1.0 if ea == eb else 0.0
        e_j, f_j = jac(ea, eb), jac(fa, fb)
    va = [c.split(" ", 1)[0] for c in ra["cmds"]]
    vb = [c.split(" ", 1)[0] for c in rb["cmds"]]
    return {
        "patch_exact": p_exact,
        "edit_jaccard": e_j,
        "file_jaccard": f_j,
        "verb_seq_sim": difflib.SequenceMatcher(None, va, vb).ratio(),
        "cmd_jaccard": jac(frozenset(ra["cmds"]), frozenset(rb["cmds"])),
        "both_empty": 1.0 if both_empty else 0.0,
    }


def load_cells():
    cells = defaultdict(list)  # (model, task) -> [run dict]
    for corpus in CORPORA:
        for d in sorted(os.listdir(corpus)):
            parts = d.split("--")
            if len(parts) < 4:
                continue
            task, harness, model, ts = parts[0], parts[1], parts[2], parts[3]
            if task not in VERIFIED or model == "none" or "golden" in harness or "null" in harness:
                continue
            p = os.path.join(corpus, d)
            rp, gp = os.path.join(p, "run.json"), os.path.join(p, "grade.json")
            if not (os.path.isfile(rp) and os.path.isfile(gp)):
                continue
            if json.load(open(rp)).get("exit_reason") == "crash":
                continue
            cells[(short_model(model), task)].append({
                "ts": ts,
                "dir": p,
                "solved": resolved(json.load(open(gp))),
                "patch": parse_patch(os.path.join(p, "workspace.patch")),
                "cmds": commands(p),
            })
    for key, runs in cells.items():
        runs.sort(key=lambda r: r["ts"])
        if len(runs) > 3:  # drop later separate-condition reruns (k3 raised-cap)
            cells[key] = runs[:3]
    return cells


def main():
    cells = load_cells()
    per_model = defaultdict(list)  # model -> list of (task, cellmetrics, solved_count)
    for (model, task), runs in sorted(cells.items()):
        if len(runs) != 3:
            print(f"!! cell {model}/{task} has {len(runs)} runs, skipped")
            continue
        pairs = [pair_metrics(runs[0], runs[1]), pair_metrics(runs[0], runs[2]),
                 pair_metrics(runs[1], runs[2])]
        cell = {k: sum(p[k] for p in pairs) / 3 for k in pairs[0]}
        per_model[model].append((task, cell, sum(r["solved"] for r in runs)))

    hdr = f'{"model":13s}{"edit_jac":>9s}{"file_jac":>9s}{"exact":>7s}{"verb_seq":>9s}{"cmd_jac":>8s}{"empty%":>7s}   per-task edit_jac (solve)'
    print(hdr)
    for m in ORDER:
        if m not in per_model:
            continue
        rows = per_model[m]
        agg = {k: sum(c[k] for _, c, _ in rows) / len(rows)
               for k in rows[0][1]}
        detail = "  ".join(
            f'{t.split("__")[-1].replace("pytest-", "py")[:9]}:{c["edit_jaccard"]:.2f}({s}/3)'
            for t, c, s in rows
        )
        print(f'{m:13s}{agg["edit_jaccard"]:>9.3f}{agg["file_jaccard"]:>9.3f}'
              f'{agg["patch_exact"]:>7.2f}{agg["verb_seq_sim"]:>9.3f}'
              f'{agg["cmd_jaccard"]:>8.3f}{agg["both_empty"]:>7.2f}   {detail}')

    print("\nwithin-lab generation deltas (new - old), mean over 4 cells:")
    for label, old, new in PAIRS:
        if old not in per_model or new not in per_model:
            continue
        d = {}
        for k in ("edit_jaccard", "verb_seq_sim", "patch_exact"):
            o = sum(c[k] for _, c, _ in per_model[old]) / len(per_model[old])
            n = sum(c[k] for _, c, _ in per_model[new]) / len(per_model[new])
            d[k] = n - o
        print(f'  {label:15s} edit_jac {d["edit_jaccard"]:+.3f}   '
              f'verb_seq {d["verb_seq_sim"]:+.3f}   exact {d["patch_exact"]:+.2f}')

    print("\nconvergence split by cell outcome (edit_jaccard / verb_seq_sim, n cells):")
    for m in ORDER:
        if m not in per_model:
            continue
        buckets = {"3/3": [], "0/3": [], "mixed": []}
        for _, c, s in per_model[m]:
            buckets["3/3" if s == 3 else "0/3" if s == 0 else "mixed"].append(c)
        parts = []
        for b in ("3/3", "0/3", "mixed"):
            cs = buckets[b]
            if cs:
                ej = sum(c["edit_jaccard"] for c in cs) / len(cs)
                vs = sum(c["verb_seq_sim"] for c in cs) / len(cs)
                parts.append(f"{b}: {ej:.2f}/{vs:.2f} (n={len(cs)})")
        print(f"  {m:13s}" + "   ".join(parts))


if __name__ == "__main__":
    main()
