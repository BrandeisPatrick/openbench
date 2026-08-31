"""Adversarial verification of exploratory findings 2-6 (2026-08-31).

Finding 1 ("gains are reliability, not capability") was already demoted:
Pass@3 is saturated on this task set, so the capability axis is censored;
its test is the harder-task expansion. This script attacks the remaining
findings at their weakest joints, from the frozen corpora only.

Decision rules, fixed before any results were inspected:

V1  Serving-determinism audit (attacks finding 3: kimi-k2-thinking's 100%
    solve with 75% byte-identical patches could be deterministic serving,
    not policy sharpness). For every model, for each cell, compare the
    first non-empty reasoning stream across repeat pairs: shared prefix
    chars and SequenceMatcher ratio over the first 2000 chars.
    Rule: a model with any repeat-pair reasoning ratio > 0.95 is flagged
    deterministic-serving-suspect and its exact-patch convergence is
    downgraded to artifact-suspect. If all its pairs diverge inside the
    first 200 chars, decoding was stochastic and identical final patches
    stand as genuine policy concentration.

V2  Style-vs-task baseline (attacks finding 2: "procedure converges" could
    be generic style — same commands on any task — not task-level policy
    concentration). verb_seq_sim (definition unchanged from convergence.py)
    over within-cell pairs (n=12 per model) vs cross-task same-model pairs
    (n=54 per model). Margin = within - cross.
    Rule: finding 2 survives per model iff margin >= 0.10. The generational
    RISE survives iff the margin itself rises along the lineage (a rise in
    raw within-cell similarity explained by the cross-task baseline is
    style rigidity, a different claim).

V3  Host map (annotates findings 2-4). Per-model serving host from the
    run-dir model field; lineage links that cross hosts are named
    confounds. Descriptive - no rule.

V4  Outcome-conditioned reasoning volume (attacks finding 4: DeepSeek's
    174k->72k->28k "compression" could be the known failures-run-long
    effect, since r1 never solves and v4 always does). Reasoning chars per
    run split by solved/failed, plus exit_reason histogram (cap censoring).
    Rule: compression survives iff the v3.2 -> v4-pro decline holds within
    solved runs alone. r1's volume is labeled failure-volume (no solved
    runs exist); any cross-outcome comparison is marked invalid.

V5  Identical-wrong-patch recount (verifies finding 5's negative
    existential directly). Count within-cell repeat pairs where both runs
    failed AND normalized edit sets are identical AND non-empty.
    Rule: finding survives iff the count is exactly 0 (both-empty pairs
    reported separately, as in convergence.py).

V6  Gold-orthogonality decomposition (attacks finding 6: OpenAI's 0.04-0.08
    gold similarity could be a line-granularity artifact rather than a
    different fix mechanism). Per solved run: edit_jaccard AND file_jaccard
    against datasets/tasks/<task>/gold.patch.
    Rule: "different mechanism" requires low file overlap OR (manual step)
    reading the patch shows a different change; same-file low-line-overlap
    alone is compatible with an equivalent fix written differently and is
    reported as such. Manual patch reading follows outside this script.
"""

import json
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convergence as cv  # noqa: E402  (pre-registered definitions)

TASKS_DIR = "datasets/tasks"


def run_extras(run_dir: str) -> dict:
    """Reasoning stream + volume + exit reason for one run."""
    first_reason, reason_chars, content_chars = None, 0, 0
    tp = os.path.join(run_dir, "raw_transcript.jsonl")
    exit_reason = None
    for line in open(tp, errors="replace"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "api_response":
            rc = r.get("reasoning_content") or ""
            reason_chars += len(rc)
            content_chars += len(r.get("content") or "")
            if first_reason is None and rc.strip():
                first_reason = rc
        elif "exit_reason" in r:
            exit_reason = r.get("exit_reason")
    rj = os.path.join(run_dir, "run.json")
    if exit_reason is None and os.path.isfile(rj):
        exit_reason = json.load(open(rj)).get("exit_reason")
    return {
        "first_reason": first_reason or "",
        "reason_chars": reason_chars,
        "content_chars": content_chars,
        "exit_reason": exit_reason,
    }


def prefix_stats(a: str, b: str):
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    ratio = SequenceMatcher(None, a[:2000], b[:2000]).ratio() if (a and b) else 0.0
    return n, ratio


def main():
    cells = cv.load_cells()
    for runs in cells.values():
        for r in runs:
            r.update(run_extras(r["dir"]))

    by_model = defaultdict(dict)  # model -> task -> runs
    for (model, task), runs in cells.items():
        if len(runs) == 3:
            by_model[model][task] = runs

    # ---------- V1 serving determinism ----------
    print("V1  reasoning-stream divergence across repeats (per model):")
    print(f'    {"model":15s}{"pairs":>6s}{"med_prefix":>11s}{"max_prefix":>11s}'
          f'{"max_ratio":>10s}{"pairs>0.95":>11s}  verdict')
    for m in cv.ORDER:
        stats = []
        for task, runs in by_model.get(m, {}).items():
            for ra, rb in combinations(runs, 2):
                if ra["first_reason"] and rb["first_reason"]:
                    stats.append(prefix_stats(ra["first_reason"], rb["first_reason"]))
        if not stats:
            print(f"    {m:15s}  (no reasoning streams recorded)")
            continue
        prefixes = sorted(p for p, _ in stats)
        ratios = [r for _, r in stats]
        med_p = prefixes[len(prefixes) // 2]
        hi = sum(1 for r in ratios if r > 0.95)
        verdict = ("DETERMINISTIC-SUSPECT" if hi else
                   "stochastic" if max(prefixes) < 200 else "stochastic (late fork)")
        print(f'    {m:15s}{len(stats):>6d}{med_p:>11d}{max(prefixes):>11d}'
              f'{max(ratios):>10.3f}{hi:>11d}  {verdict}')

    # ---------- V2 style-vs-task baseline ----------
    print("\nV2  verb_seq_sim: within-cell vs cross-task (same model):")
    print(f'    {"model":15s}{"within":>8s}{"cross":>8s}{"margin":>8s}  rule: margin >= 0.10')
    margins = {}
    for m in cv.ORDER:
        tasks = by_model.get(m, {})
        if not tasks:
            continue
        within, cross = [], []
        allruns = [(t, r) for t, runs in tasks.items() for r in runs]
        for (ta, ra), (tb, rb) in combinations(allruns, 2):
            va = [c.split(" ", 1)[0] for c in ra["cmds"]]
            vb = [c.split(" ", 1)[0] for c in rb["cmds"]]
            s = SequenceMatcher(None, va, vb).ratio()
            (within if ta == tb else cross).append(s)
        w = sum(within) / len(within)
        c = sum(cross) / len(cross)
        margins[m] = w - c
        flag = "PASS" if w - c >= 0.10 else "FAIL -> style rigidity"
        print(f'    {m:15s}{w:>8.3f}{c:>8.3f}{w - c:>+8.3f}  {flag}')
    print("    margin deltas along lineages (does the RISE survive the baseline?):")
    for label, old, new in cv.PAIRS:
        if old in margins and new in margins:
            print(f'      {label:18s} margin {margins[old]:+.3f} -> {margins[new]:+.3f}'
                  f'   delta {margins[new] - margins[old]:+.3f}')

    # ---------- V3 host map ----------
    print("\nV3  serving-host map (from run-dir model field):")
    hosts = {}
    for corpus in cv.CORPORA:
        for d in sorted(os.listdir(corpus)):
            parts = d.split("--")
            if len(parts) < 4 or parts[0] not in cv.VERIFIED:
                continue
            raw_model = parts[2]
            if raw_model == "none":
                continue
            m = cv.short_model(raw_model)
            hosts[m] = ("openrouter" if raw_model.startswith("openrouter_")
                        else "first-party")
    for lab, ms in cv.LINEAGES:
        chain = "  ->  ".join(f"{m} [{hosts.get(m, '?')}]" for m in ms)
        crossings = [f"{ms[i]}->{ms[i + 1]}" for i in range(len(ms) - 1)
                     if hosts.get(ms[i]) != hosts.get(ms[i + 1])]
        note = f"   HOST-CROSSING LINKS: {', '.join(crossings)}" if crossings else "   uniform host"
        print(f"    {lab:9s}{chain}{note}")

    # ---------- V4 outcome-conditioned reasoning volume ----------
    print("\nV4  reasoning chars per run, by outcome (mean, n) + exit reasons:")
    print(f'    {"model":15s}{"solved":>16s}{"failed":>16s}   exit_reasons')
    for m in cv.ORDER:
        tasks = by_model.get(m, {})
        sv = [r["reason_chars"] for runs in tasks.values() for r in runs if r["solved"]]
        fv = [r["reason_chars"] for runs in tasks.values() for r in runs if not r["solved"]]
        ex = defaultdict(int)
        for runs in tasks.values():
            for r in runs:
                ex[r["exit_reason"] or "?"] += 1
        fmt = lambda v: f"{sum(v) / len(v):>10,.0f} n={len(v):<2d}" if v else f'{"—":>10s} n=0 '
        print(f'    {m:15s}{fmt(sv):>16s}{fmt(fv):>16s}   {dict(ex)}')

    # ---------- V5 identical wrong patch ----------
    print("\nV5  failed-pair patch identity recount:")
    ident_wrong, both_empty, failed_pairs = 0, 0, 0
    for (m, task), runs in cells.items():
        if len(runs) != 3:
            continue
        for ra, rb in combinations(runs, 2):
            if ra["solved"] or rb["solved"]:
                continue
            failed_pairs += 1
            _, ea = ra["patch"]
            _, eb = rb["patch"]
            if not ea and not eb:
                both_empty += 1
            elif ea == eb:
                ident_wrong += 1
                print(f"      IDENTICAL WRONG PATCH: {m} / {task}")
    print(f"    failed pairs: {failed_pairs}, both-empty: {both_empty}, "
          f"identical non-empty wrong: {ident_wrong}  "
          f"({'finding 5 survives' if ident_wrong == 0 else 'finding 5 REFUTED'})")

    # ---------- V6 gold similarity decomposition ----------
    print("\nV6  solved runs vs gold patch (edit_jaccard / file_jaccard, mean over solved runs):")
    print(f'    {"model":15s}' + "".join(f"{t.split('__')[-1][:12]:>16s}" for t in cv.VERIFIED))
    gold = {}
    for t in cv.VERIFIED:
        gp = os.path.join(TASKS_DIR, t, "gold.patch")
        gold[t] = cv.parse_patch(gp) if os.path.isfile(gp) else None
    for m in cv.ORDER:
        row = f"    {m:15s}"
        for t in cv.VERIFIED:
            runs = by_model.get(m, {}).get(t, [])
            solved = [r for r in runs if r["solved"]]
            if not solved or gold[t] is None:
                row += f'{"—":>16s}'
                continue
            gf, ge = gold[t]
            ej = sum(cv.jac(r["patch"][1], ge) for r in solved) / len(solved)
            fj = sum(cv.jac(r["patch"][0], gf) for r in solved) / len(solved)
            row += f"{ej:>7.2f}/{fj:<8.2f}"
        print(row)


if __name__ == "__main__":
    main()
