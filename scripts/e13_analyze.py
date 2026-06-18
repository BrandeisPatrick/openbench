"""E13 Stage-1 readout: OFF vs ON Opus·mini-swe on sympy-23534.

Gradeless. Reads raw_transcript.jsonl from the worktree runs/ dir, keys arms by
the `variant` field in the meta record, and reports the dream-fix metrics:
  - over_gen_rate: fraction of model turns that over-generated (>1 fence) — the
    metric the fix's "80%->40%" claim is about (`_overgenerated` in mini_swe.py).
  - confab: declared done (exit completed) without ever running a test.
  - is_degenerate: no tests AND no edits AND declared done (cells.py criterion).
"""
from __future__ import annotations
import json, glob, os
from collections import defaultdict

RUNS = "/Users/patrickli/Documents/openbench/.claude/worktrees/sleepy-galileo-9d737d/runs"
TASK = "sympy__sympy-23534"
EDIT_HINTS = ("cat >", "cat >>", "tee ", "> /repo", "applypatch", "git apply", "python - <<", "python3 - <<")

def is_test(c): c=c.lower(); return ("pytest" in c) or ("py.test" in c) or ("-m unittest" in c) or ("bin/test" in c)
def is_edit(c): c=c.lower(); return any(h in c for h in EDIT_HINTS)

def analyze(rt):
    variant=None; turns=0; over=0; tests=0; edits=0; exit_reason=None
    for line in open(rt):
        try: r=json.loads(line)
        except: continue
        t=r.get("type")
        if t=="meta": variant=r.get("variant")
        elif t=="api_response":
            turns+=1
            if (r.get("content") or "").count("```")>2: over+=1
        elif t=="exec":
            cmd=r.get("command","")
            if is_test(cmd): tests+=1
            if is_edit(cmd): edits+=1
        elif t=="final": exit_reason=r.get("exit_reason")
    declared_done = (exit_reason=="completed")
    return dict(variant=variant, turns=turns, over_gen_rate=(over/turns if turns else 0.0),
               tests=tests, edits=edits, exit=exit_reason, declared_done=declared_done,
               confab=(declared_done and tests==0),
               degenerate=(tests==0 and edits==0 and declared_done))

rows=[]
for d in sorted(glob.glob(f"{RUNS}/{TASK}--mini-swe--claude-opus-4-8--*")):
    rt=os.path.join(d,"raw_transcript.jsonl")
    if os.path.exists(rt):
        a=analyze(rt); a["run"]=os.path.basename(d)[-13:]; rows.append(a)

print(f"{'run':<14}{'arm':<5}{'turns':>5}{'overgen%':>9}{'tests':>6}{'edits':>6}{'exit':<11}{'confab':>7}{'degen':>6}")
for r in rows:
    print(f"{r['run']:<14}{str(r['variant']):<5}{r['turns']:>5}{r['over_gen_rate']*100:>8.0f}%{r['tests']:>6}{r['edits']:>6}  {str(r['exit']):<9}{('Y' if r['confab'] else '.'):>6}{('Y' if r['degenerate'] else '.'):>6}")

print("\n=== arm summary ===")
by=defaultdict(list)
for r in rows: by[r['variant']].append(r)
for arm in ("off","on"):
    g=by.get(arm,[])
    if not g: continue
    n=len(g)
    print(f"{arm.upper():<4} n={n}  over_gen={sum(x['over_gen_rate'] for x in g)/n*100:4.0f}%  "
          f"confab={sum(x['confab'] for x in g)}/{n}  degenerate={sum(x['degenerate'] for x in g)}/{n}  "
          f"mean_turns={sum(x['turns'] for x in g)/n:.1f}  mean_edits={sum(x['edits'] for x in g)/n:.1f}  "
          f"mean_tests={sum(x['tests'] for x in g)/n:.1f}")
