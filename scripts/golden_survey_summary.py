"""Summarize the golden-control survey: per task, does the known-correct human
patch grade to 100% F2P / 100% P2P? Anything short = a calibration bug (the task
was never validated), since the merged PR passed CI by definition.
"""
from __future__ import annotations
import json, glob, os

RUNS = "runs"

def pct(passed, failed):
    n = passed + failed
    return (passed / n * 100) if n else 0.0

tasks = sorted({os.path.basename(d).split("--golden--")[0] for d in glob.glob(f"{RUNS}/*--golden--*")})
rows = []
for t in tasks:
    g = rid = None
    for d in sorted(glob.glob(f"{RUNS}/{t}--golden--*"), reverse=True):
        if os.path.exists(d + "/grade.json"):
            g = json.load(open(d + "/grade.json")); rid = os.path.basename(d); break
    rows.append((t, g))

print(f"{'task':<34}{'builds':>7}{'f2p':>6}{'p2p':>6}{'CLEAN':>7}  failing_p2p (first 4)")
clean = 0
for t, g in rows:
    if g is None:
        print(f"{t:<34}{'—':>7}{'—':>6}{'—':>6}{'NOGRADE':>7}")
        continue
    fp, ff = len(g.get("f2p_passed") or []), len(g.get("f2p_failed") or [])
    pp, pf = len(g.get("p2p_passed") or []), len(g.get("p2p_failed") or [])
    f2p, p2p = pct(fp, ff), pct(pp, pf)
    is_clean = (f2p == 100.0 and p2p == 100.0 and g.get("builds"))
    clean += is_clean
    print(f"{t:<34}{str(g.get('builds')):>7}{f2p:>5.0f}%{p2p:>5.0f}%{('YES' if is_clean else 'no'):>7}  "
          f"{(g.get('p2p_failed') or [])[:4]}")
print(f"\nclean (golden 100/100): {clean}/{len([r for r in rows if r[1] is not None])} graded tasks")
