# Findings: generational behavior study (July 2026 corpora)

Status: verified 2026-08-03 after two audit rounds. Corpora:
`data/runs-2026-07-generational-study/` (chat lineages) and
`data/runs-2026-07-thinking-extension/` (thinking lineages) — see each
README for provenance, the grading-env incident, and audit details.
Every number below was reproduced from raw `grade.json`/transcripts by
independent recount; the full 133-run re-grade reproduced every model-run
verdict and per-test count exactly.

## 1. Solve rates (SWE-bench-Verified stratum, 3 seeds × 4 tasks)

| pair | old → new | validity-adjusted* |
|---|---|---|
| deepseek | V3-0324 0/12 → v4-pro 12/12 | unchanged |
| gpt | 4.1 3/12 → 5.5 12/12 | unchanged |
| gpt-think-early | o1 1/12 → o3 9/12 | o1 **1/11** |
| gpt-think-late | o3 9/12 → 5.5 12/12 | unchanged |
| deepseek-think-early | R1-0528 0/12 → V3.2 5/12 | R1 **0/10**, V3.2 **5/10** |
| deepseek-think-late | V3.2 5/12 → v4-pro 12/12 | V3.2 **5/10** |
| kimi-think | k2.6 8/12 → k3 11/12 | unchanged; k3 **12/12 at budget parity** |

\* Runs that faced the broken pytest-5262 runtime and FAILED are dropped
(uninterpretable); solves under the broken runtime stand (achieved without
runnable tests). kimi-k3's banked failure is a $2.50 cost-cap kill under
~5x-overstated billing; at the o-series caps the cell resolves.

Reading the zeros: 0/12 on this task mix bounds solve rate at ≲25% (95%),
and V3-0324's excluded crash run had already solved pytest-5262 when the
API died. The zeros measure *autonomous agentic reliability on a minimal
harness* (one bash tool, `tool_choice=auto`), not coding knowledge — they
coexist with much higher scaffolded public numbers, and that gap is itself
the phenomenon under study.

## 2. Why old models fail: ungrounded state, not facts or context

**Not context**: scored failures end at turns 9–25 with small prompts; no
scored run hit a context limit (a few excluded crashes have uncaptured
400 bodies — status-only logs — and are outside the scored set).

**Not (primarily) knowledge**: R1's final messages *describe the gold fix
correctly* while its patch destroys the file. The knowledge–execution
dissociation is the finding.

**The mechanism — belief about repo state never reconciled with the repo**.
Specimen (R1-0528 on pytest-5262, run `…155537-427074`, full command log in
its transcript):

1. Never reads `capture.py` — only `find`s its path (t5–t6).
2. Overwrites the 433-line file from memory via `cat > … <<EOF`, twice
   (t4 wrong path, t8 "succeeds"), leaving a 41-line stub that ends
   `# ... rest of file remains unchanged ...` — narration in place of code.
   (Its t2 `sed -i ''` is BSD/macOS syntax on a Linux container — priors
   about the *environment* too.)
3. "Verifies" by directly importing its new `EncodedFile.mode` property
   (t9, t12) — the one thing it added — never the test suite.
4. Declares success with a 3-point verification claim (t13, `DONE`).

**Quantified across the verified stratum (usable runs):**

- Destructive placeholder patches (large deletion + "rest unchanged"-style
  comment): **R1 3/12, o1 2/12** (o1's largest: −2,193 lines; R1 deleted
  7,068 lines of sympy's polytools.py behind one comment). **Zero** in
  every model from o3/V3.2 onward. (Manually triaged; three regex
  near-hits in o3/V3.2/k3 are benign inline comments in balanced diffs.)
- Confabulated completions: **26/60 old-generation vs 2/60 new-generation**.
- The metrics that improve in *every* pair where headroom exists are the
  grounding ones: `green_observed`, `verified_before_done`, diff-size ratio
  (o1 706× gold → o3 16× → 5.5 7×), `file_jaccard` → 1.0.
- Corroborating: R1 is the only model that weakens tests (128 asserts on
  sympy-22914) — the same ungrounded-claim defect pointed at the grader.

**Interpretation** (one hypothesis, stated as such): old-generation
policies were optimized toward *plausible completion* — outputs that sound
finished — while new-generation policies behave as if optimized toward
*verified completion*: read before write, edit surgically, gate claims on
observed green. Strong priors are not the defect — o3 and kimi-k3 solved
pytest-5262 *without runnable tests* by localizing carefully and editing
surgically. The defect is acting on priors without reconciliation.

## 3. Failure taxonomy of the zero-score models

| model | fingerprint | protocol-shaped? |
|---|---|---|
| V3-0324 | bimodal: ~100% malformed actions in 7/12 runs (chat text instead of tool calls); otherwise acts but grinds to cap | No — same wire format carries V3.2/v4-pro to 5/10 and 12/12; one crashed run solved |
| R1-0528 | well-formed calls (~0.1 malformed), ~5 edits/run, then false DONE in 12/12; placeholder overwrites; test weakening | No — pipe demonstrably works; model quits and claims |
| o1 | 0.0 malformed everywhere, 10+ edits, 700×-size rewrites, 7/12 confabulated, 1 genuine solve | No — same wire format carries o3 to 9/12 |

## 4. Robustness (round-2 audit, 2026-08-03)

1. 133-run re-grade on golden-gated images: zero model-run flips, exact
   per-test count reproduction (one golden fixture healed from the known
   broken window).
2. False-solve audit of all 73 resolved runs: no assert weakening, all
   patches touch non-test source, no gold-mining in transcripts.
3. Per-run runtime-env validity map (transcript scan for the 3.12
   `import imp` crash) — source of the validity adjustments above.
4. Crash exclusions all provider-side; crashed cells re-run to 12 usable.
5. Independent recount matches reports; leave-one-task-out flips no pair's
   sign. Caveat: the o3→5.5 *solve* delta lives entirely in sympy-13757;
   cite that pair on its efficiency deltas (turns −73%, tokens −91%,
   turns-to-first-green 32→13.5), which are task-general.

## 5. Limitations

- 4 tasks × 3 seeds per model; intervals are task-clustered bootstraps and
  all zeros are ≤~25%-at-95% statements, not point facts.
- Single minimal harness by design; within-lab contrasts only (wire format
  held fixed per pair). Cross-lab rows are not comparable claims.
- Behavioral (not solve) metrics for the July-12/19 arms on pytest-5262
  reflect the broken runtime (e.g. `green_observed` was unattainable);
  footnote or rerun before citing verification behavior on that task.
- Caps varied by arm ($2.50 vs $10) and run-time cost accounting ignored
  cache discounts (fixed 2026-08-02; see freeze READMEs) — treat recorded
  `cost_usd` comparisons across labs as approximate.
