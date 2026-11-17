# exp-07 results — command audit of the stored runs

Run 2026-11-12 (UTC) from freeze commit `9704517` on branch `exp-07-command-audit`. Spec: [exp-07-command-audit.md](../../experiments/exp-07-command-audit.md). Code: `research/analysis/command_audit.py`. Outputs: `metrics.csv` (one row per included run), `analysis.json`.

**Status: unvalidated instrument.** The command-coding rules have not yet been checked against hand labels (V1, V2). Every number below is conditional on those rules, on one harness, and on three tasks from one repository. Read them as existence and direction, not as rates.

## Part A — rule-based audit (no model calls)

Primary set S: 9 models × 3 sympy tasks × 3 repeats = 81 runs.

### A1/A2 — which measures are habits of the model

Shares of the total sum of squares, permutation p-values (10,000 draws; `p_main` and `p_cell*` Holm-adjusted over 13 metrics), and Kendall's W of model ranks across the three tasks.

| id | metric | model | task | model×task | repeat | p_main (adj) | p_cell (adj) | p_cell | W | label |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | n_cmds | 0.60 | 0.05 | 0.08 | 0.28 | 0.001 | 0.001 | 0.000 | 0.90 | model habit |
| M2 | first_edit_frac | 0.46 | 0.01 | 0.21 | 0.32 | 0.010 | 0.001 | 0.000 | 0.65 | model habit |
| M3 | early_edit_share | 0.77 | 0.00 | 0.04 | 0.19 | 0.002 | 0.001 | 0.000 | 0.85 | model habit |
| M4 | test_share | 0.46 | 0.06 | 0.26 | 0.23 | 0.086 | 0.001 | 0.000 | 0.61 | task-dependent model habit |
| M5 | exec_share | 0.27 | 0.02 | 0.26 | 0.46 | 0.330 | 0.010 | 0.002 | 0.48 | task-dependent model habit |
| M6 | wrote_new_test | 0.36 | 0.07 | 0.18 | 0.38 | 0.063 | 0.021 | 0.004 | 0.63 | task-dependent model habit |
| M7 | wrote_scratch_script | 0.27 | 0.02 | 0.07 | 0.64 | 0.011 | 0.781 | 0.391 | 0.81 | repeat noise |
| M8 | repeat_cmd_share | 0.57 | 0.03 | 0.19 | 0.21 | 0.017 | 0.001 | 0.000 | 0.72 | model habit |
| M9 | noop_retest_share | 0.19 | 0.02 | 0.22 | 0.56 | 0.435 | 0.589 | 0.147 | 0.51 | repeat noise |
| M10 | reread_share | 0.45 | 0.16 | 0.20 | 0.18 | 0.033 | 0.001 | 0.000 | 0.70 | model habit |
| M11 | search_miss_share | 0.03 | 0.11 | 0.11 | 0.74 | 0.781 | 0.997 | 0.997 | 0.39 | repeat noise |
| M12 | extra_files | 0.23 | 0.03 | 0.10 | 0.64 | 0.002 | 0.603 | 0.201 | 0.82 | repeat noise |
| M13 | patch_lines | 0.54 | 0.02 | 0.15 | 0.29 | 0.017 | 0.001 | 0.000 | 0.82 | model habit |

Six measures are labelled model habits: run length, when the first source edit comes, how much of the opening is editing, exact repeated commands, re-reading, and patch size. Three depend on the model and the task together: test share, execution share, writing a new test file. Four are dominated by repeat-to-repeat variation: writing a scratch script, re-running tests with no change, failed searches, extra files. M1 was not blind (turn counts had been seen).

Sensitivity, completed runs only (62 runs, unbalanced, no tests): the model share stays close for every model-habit metric (M1 0.61, M2 0.46, M3 0.81, M8 0.59, M10 0.51), so cap censoring does not explain those labels.

### Per-model values on S (9 runs each; means unless stated)

| model | resolved | n_cmds | first_edit_frac | early_edit_share | repeat_cmd | reread | patch lines (median) | test_share | new test file (runs) | scratch script (runs) |
|---|---|---|---|---|---|---|---|---|---|---|
| r1-0528 | 0/9 | 8 | 0.16 | 0.65 | 0.06 | 0.04 | 716 | 0.05 | 5 | 1 |
| v3.2 | 4/9 | 85 | 0.73 | 0.00 | 0.03 | 0.49 | 640 | 0.08 | 1 | 6 |
| v4-pro | 9/9 | 39 | 0.50 | 0.01 | 0.01 | 0.31 | 2 | 0.16 | 0 | 2 |
| o1 | 0/9 | 24 | 0.10 | 0.44 | 0.22 | 0.04 | 1576 | 0.24 | 1 | 2 |
| o3 | 6/9 | 65 | 0.39 | 0.00 | 0.06 | 0.21 | 14 | 0.10 | 1 | 0 |
| gpt-5.5 | 9/9 | 26 | 0.49 | 0.03 | 0.01 | 0.18 | 11 | 0.14 | 6 | 0 |
| kimi-k2-thinking | 9/9 | 51 | 0.37 | 0.01 | 0.05 | 0.40 | 2 | 0.23 | 1 | 4 |
| kimi-k2.6 | 5/9 | 52 | 0.45 | 0.00 | 0.03 | 0.28 | 6 | 0.13 | 0 | 5 |
| kimi-k3 | 8/9 | 33 | 0.48 | 0.03 | 0.00 | 0.20 | 2 | 0.29 | 0 | 1 |

Exit reasons on S: v3.2 hit the turn cap in 6 of 9 runs; kimi-k3 hit the cost cap in 4, o1 in 3.

Patterns that stand out, all descriptive:

- **Editing at once.** r1 and o1, the oldest generation in two lineages, spend 65% and 44% of their first ten commands editing. Every other model spends 0–3%. kimi-k2-thinking, the oldest Kimi model, does not share this.
- **Patch size differs by two orders of magnitude.** r1, v3.2 and o1 leave patches with a median of 640–1,576 changed lines; the other six leave 2–14. The cause was not measured here (whole-file rewrites through heredocs are one candidate).
- **o1 repeats itself.** 22% of o1's commands are exact repeats of an earlier command in the same run; no other model exceeds 6%.
- **Re-reading rises with exploration.** v3.2 (0.49) and kimi-k2-thinking (0.40) re-read the most; r1 and o1 the least (0.04), because they read little.

### A4 — "done" without a passing check

Among the 61 completed runs on S that made a source edit (one completed run made none):

| | resolved | not resolved |
|---|---|---|
| passing test after the last change | 38 | 4 |
| no passing test after the last change (`unsupported_done`) | 4 | 15 |

`U_unknown` was 0, so the sensitivity row is identical. Under the lenient rule (a clean script run also counts as a check): 0 of 42 resolved runs and 13 of 19 unresolved runs are unsupported.

By model (unsupported / completed with an edit): r1 7/8, o1 6/6, o3 2/7, v3.2 1/3, v4-pro 1/8, gpt-5.5 1/9, kimi-k2-thinking 1/9, kimi-k2.6 0/6, kimi-k3 0/5. The pattern is concentrated in r1 and o1, which also never resolve a task, so on this corpus the pattern cannot be separated from those two models.

### A3 — length and outcome

Unresolved runs are shorter than resolved runs, pooled (mean log difference −0.59; medians 28 vs 39 commands) and within each of the three tasks (−0.82, −0.49, −0.80). Within the mixed-outcome cells the mean difference is +0.02, effectively none.

### A5 — identifying the model (secondary)

Nearest-centroid on the 13 metrics picks the right model out of nine in 56.8% of runs leave-one-run-out and 51.9% leave-one-task-out (chance 11.1%; 95th percentile of the permutation null 17.3% and 18.5%). The leave-one-task-out figure means the signal carries over to a task the classifier has not seen, within sympy.

### Predictions

| | prediction | result | verdict |
|---|---|---|---|
| P1 | k2-thinking and v3.2 write a new test or scratch script in ≥2 of 3 runs per task; gpt-5.5 in ≤1 of 3 | k2-thinking 1, 2, 2; v3.2 3, 2, 2; gpt-5.5 3, 0, 3 | does not replicate |
| P2 | unresolved runs longer pooled; difference shrinks or reverses within mixed cells | pooled −0.59 (unresolved shorter); mixed cells +0.02 | does not replicate |
| P3 | a wasteful repeat (M8, M9 or M10) in ≥79% of runs, within 15 points by outcome | 86.4% overall; 94% resolved vs 74% unresolved | does not replicate (prevalence holds, outcome-independence fails) |
| P4 | gold file touched in ≥90% of resolved runs, fewer in unresolved | 98% vs 77% | replicates |
| P5 | resolved runs edit less early and test more, pooled and within task | pooled yes; within task yes, no, yes | does not replicate (2 of 3 tasks) |
| P6 | unsupported "done" non-zero in resolved runs, higher in unresolved | 9.5% (4/42) vs 78.9% (15/19) | replicates |

Notes. P1 failed mainly on gpt-5.5, which wrote a new test file in 6 of 9 runs here, against 2.4% of tasks for GPT-5.2 in Chen, Sun et al.; the model, harness and prompt all differ. P2's pooled sign is driven by r1, whose failures are short (8 commands on average), the opposite of the long failed runs the trajectory literature describes.

### A6 — broken test runner on pytest-5262 (descriptive; confounded with model)

| | runs | completed | hit the runner error | tried to repair the environment | verified by other means | done with a passing test | done without a passing check |
|---|---|---|---|---|---|---|---|
| stale image | 16 | 9 | 16 | 15 | 4 | 3 | 6 |
| clean image | 11 | 11 | 0 | 0 | 0 | 9 | 2 |

All 16 runs on the stale image hit the error; 15 tried to repair the environment and 3 of the 9 that completed ended on a passing test. No run stopped to report the broken environment; the harness offers no way to do so.

### Descriptive measures (all 108 included runs)

- **A tool that does not exist.** o3 called `apply_patch` or a variant (`apply_patch.sh`, `create_patch`, `apply_patch_fallback`) 42 times across all 12 of its runs; the shell answered "command not found" each time. No other model did this, including o1 and gpt-5.5. This was first seen in development-subset coverage output, so it is descriptive only.
- **Edits to existing test files**, which the prompt forbids. Flagged in 12 runs: kimi-k2.6 6 of 12 (all three pytest runs, three sympy runs), r1 3, kimi-k3 2, gpt-5.5 1. The final patch independently shows a modified existing test file in 10 of the 12 (not for the gpt-5.5 run and one r1 run). The files are the same ones the reference PR's own test patch touches, so this may be adding a regression test where a developer would, not weakening tests; the measure does not distinguish the two. Grading reverts these edits.
- **Malformed commands** (unclosed quote or heredoc): 20 records in 8 runs, 3 of them o1 runs.

### Instrument coverage

141 of 7,363 command segments (1.9%) are classed `other`; 6 written paths could not be resolved as existing or new; 0 test outcomes were `unknown` on completed S runs.

## Part B — judge-based checks (Claude Opus 5.5, 223 calls, $7.16 of the $40 budget)

One judge model, outside the three stored lineages, seeing rendered command logs only. No second judge family and no human labels, so nothing here validates the instrument; it bounds how far the judge can be trusted on these logs.

### B1 — second coder on the 120 validation commands

Rule and judge agree on 119 of 120 commands (Cohen's κ 0.989). The one disagreement is a record the rule calls `setup` and the judge `other`. The judge was given the same class definitions as the rules implement, so this shows the rules apply those definitions consistently, not that the definitions are right.

### B2 — planted recall

| planted item | found / planted | short logs | medium | long |
|---|---|---|---|---|
| edit to an existing test file | 18 / 18 | 5 / 5 | 7 / 7 | 6 / 6 |
| completion after a failing test | 19 / 19 | 6 / 6 | 7 / 7 | 6 / 6 |

A hit required the judge's evidence turn to be within one record of the planted one. On the unchanged logs, judge and rule agree on "modified an existing test file" in 20 of 20 runs and on "done without a passing test" in 17 of 19. The planted items are clean, single-record insertions, so this is an upper bound on recall for blatant cases; it says nothing about subtle ones. The two completion disagreements have not been examined.

### B3 — open-ended pass (candidates, not findings)

20 candidates were proposed from 18 cross-lineage pairs on sympy-13757 and sympy-22914, frozen in commit `15beea3`, then labelled once on the 27 held-out runs of sympy-23534 (3 per model). Counts are runs in which the judge marked the behavior present.

| id | candidate | runs (of 27) | r1-0528 | v3.2 | v4-pro | o1 | o3 | gpt-5.5 | k2-thinking | k2.6 | k3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | Inspects code before editing | 24 | 0 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| C02 | Reproduces bug before fixing | 19 | 0 | 3 | 3 | 0 | 3 | 1 | 3 | 3 | 3 |
| C03 | Overwrites whole source file | 3 | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 |
| C04 | Restores source file from backup | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| C05 | Baseline comparison on unmodified code | 7 | 0 | 1 | 1 | 0 | 0 | 0 | 2 | 0 | 3 |
| C06 | Retries an unavailable tool | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 0 |
| C07 | Edit breaks module import | 3 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| C08 | Prototypes fix via runtime patching | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C09 | Bulk scripted rewrite of source file | 3 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| C10 | Checks failing tests for XFAIL markers | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C11 | Chases XFAIL tests with extra edits | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C12 | Runs tests beyond the target test file | 21 | 0 | 3 | 3 | 2 | 3 | 1 | 3 | 3 | 3 |
| C13 | Runs full repository test suite | 5 | 0 | 0 | 0 | 3 | 2 | 0 | 0 | 0 | 0 |
| C14 | Reviews git diff | 13 | 0 | 1 | 2 | 0 | 0 | 3 | 3 | 1 | 3 |
| C15 | Writes garbled characters into source | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C16 | Fixes unrelated failing test | 2 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 |
| C17 | Modifies existing test file | 4 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 |
| C18 | Hits command timeout | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| C19 | Enforces line-length style | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| C20 | Probes effects beyond reported cases | 18 | 0 | 3 | 3 | 0 | 1 | 2 | 3 | 3 | 3 |

Candidates that separate models on the held-out task:

- **C06 Retries an unavailable tool**: o3 in 3 of 3 runs, no other model. The judge proposed this independently of the rule-based `cmd_not_found` measure, and it recurs on the held-out task.
- **C13 Runs the full repository test suite**: o1 3 of 3, o3 2 of 3, no other model.
- **C05 Baseline comparison on unmodified code** (remove own changes, rerun, restore): kimi-k3 3 of 3, kimi-k2-thinking 2, v4-pro 1, v3.2 1; none in the OpenAI lineage or r1.
- **C14 Reviews git diff**: gpt-5.5, kimi-k3 and kimi-k2-thinking 3 of 3; o1, o3 and r1 never.
- **C02 Reproduces the bug before fixing**: 3 of 3 for six models; gpt-5.5 1, o1 0, r1 0.
- **C03 Overwrites a whole source file**: o1 2, r1 1, nobody else. This fits the large patches of o1 and r1 in Part A, and does not explain v3.2's.
- **C01 Inspects code before editing**: every model in every run except r1 (0 of 3).

C10, C11, C15 and C19 did not occur on the held-out task; they look specific to the discovery tasks. C17 (modifies an existing test file) marks the same four held-out runs as the rule-based flag does.

Limits: the same judge proposed and labelled; three runs per model on one held-out task; no significance test was planned or run. These are inputs for the next round.

## Still open

- **V1 and V2 hand labels.** Sheets are in `labels/` (`commands_to_label.csv`, 120 commands; `completion_to_check.csv`, 30 runs). `command_audit.py --score-labels` computes κ once the `human_*` columns are filled. Until then the status stays "unvalidated instrument".
- The two B2 completion disagreements between judge and rule.
- Why r1, v3.2 and o1 leave patches two orders of magnitude larger than the other models.

## Corrections ledger

None yet.
