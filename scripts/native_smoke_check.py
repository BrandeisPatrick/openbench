"""Smoke readout for any harness on sympy-23534 (native/tooluse vs the mini-swe baseline).

Gradeless. For each run: turns, real exec commands, tests run, edits, no-tool-call
nudges (tool-use only), exit reason, declared-done, and is_degenerate. The point of
the native-tool-use switch is that degenerate/confab should be structurally 0.
"""
from __future__ import annotations
import json, glob, os, sys

RUNS = "/Users/patrickli/Documents/openbench/.claude/worktrees/sleepy-galileo-9d737d/runs"
TASK = "sympy__sympy-23534"
EDIT_HINTS = ("cat >", "cat >>", "tee ", "> /repo", "applypatch", "git apply", "python - <<", "python3 - <<")

def is_test(c): c=c.lower(); return ("pytest" in c) or ("py.test" in c) or ("-m unittest" in c)
def is_edit(c): c=c.lower(); return any(h in c for h in EDIT_HINTS)

def analyze(rt):
    meta={}; turns=0; tests=0; edits=0; real_execs=0; exit_reason=None; nudges=0
    for line in open(rt):
        try: r=json.loads(line)
        except: continue
        t=r.get("type")
        if t=="meta": meta=r
        elif t=="api_response":
            turns+=1
            # tool-use turns with no command produce a nudge user-message next; we
            # can't see messages here, so approximate "no action" by an exec gap.
        elif t=="exec":
            cmd=r.get("command","")
            if "OPENBENCH_DONE" not in cmd:
                real_execs+=1
                if is_test(cmd): tests+=1
                if is_edit(cmd): edits+=1
        elif t=="final": exit_reason=r.get("exit_reason")
    declared_done = (exit_reason=="completed")
    degenerate = (tests==0 and edits==0 and real_execs==0 and declared_done)
    return dict(scaffold=meta.get("scaffold") or meta.get("harness") or "?",
                turns=turns, real_execs=real_execs, tests=tests, edits=edits,
                exit=exit_reason, declared_done=declared_done, degenerate=degenerate)

pat = sys.argv[1] if len(sys.argv)>1 else "*"
rows=[]
for d in sorted(glob.glob(f"{RUNS}/{TASK}--{pat}")):
    rt=os.path.join(d,"raw_transcript.jsonl")
    if os.path.exists(rt):
        a=analyze(rt); a["run"]=os.path.basename(d); rows.append(a)

if not rows:
    print("no matching runs"); sys.exit(0)
print(f"{'harness':<10}{'turns':>5}{'execs':>6}{'tests':>6}{'edits':>6}{'exit':<12}{'degen':>6}  run")
for r in rows:
    short = r["run"].split("--")[1] + "/" + r["run"].split("--")[-1][:13]
    print(f"{r['scaffold']:<10}{r['turns']:>5}{r['real_execs']:>6}{r['tests']:>6}{r['edits']:>6}"
          f"{str(r['exit']):<12}{('YES' if r['degenerate'] else '.'):>6}  {short}")
