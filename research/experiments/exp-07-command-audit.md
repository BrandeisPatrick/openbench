# exp-07 — Command audit of the stored runs: which habits belong to the model, and is "done" backed by the log?

Status: pre-registered (this file and `research/analysis/command_audit.py` are written before any metric is computed on the corpus). Cost: Part A $0; Part B up to $40 of judge tokens (budget approved by the owner 2026-11-11). Depends on: nothing new — stored runs only, no Docker, no provider keys.

Admission note. `research/README.md` admits an experiment only if its result differs by post-training recipe and parks descriptive ones. This experiment is descriptive on purpose. It is admitted under the owner's reframing of 2026-11-11: openbench exists to discover agent behavior patterns, not to rank models or diagnose recipes. Literature basis: `reports/Agent pattern discovery experiments.md`.

## Questions

Q1. Which command-level habits vary more between models than between repeats of one model on one task (a habit of the model), which vary by task, and which are repeat noise?
Q2. How often does a run declare completion when its own command log does not show a passing check after its last edit?

## Protocol source

- Mehtiyev & Assunção ([2604.02547](https://arxiv.org/abs/2604.02547)): command classes, opening-edit and validation measures; early editing predicts failure, validation predicts success; "failed runs are longer" reverses within a task; one run per task, so repeat noise is unmeasured.
- Bouzenia & Pradel ([2506.18824](https://arxiv.org/abs/2506.18824)): repeated actions are more frequent in failing runs.
- Hu et al. ([2609.30725](https://arxiv.org/abs/2609.30725)): re-reading, near-duplicate scripts and re-running tests with no change occur in 79–98% of tasks regardless of outcome.
- Majgaonkar et al. ([2511.00197](https://arxiv.org/abs/2511.00197)): resolved runs touch the reference fix's file in 92–97% of runs, its exact lines in 2.7–8.4%.
- Chen, Sun et al. ([2602.07900](https://arxiv.org/abs/2602.07900)): under one scaffold, new test files on 2.4% of tasks (GPT-5.2) to 98.6% (MiniMax M2); DeepSeek v3.2 Reasoner 88.4%, Kimi K2 Thinking 97.6%.
- Advani ([2606.09863](https://arxiv.org/abs/2606.09863)): false success is common in failed runs and LLM judges detect it poorly, so completion is checked against the log, not judged.
- Statistics: Miller ([2411.00640](https://arxiv.org/abs/2411.00640)) for clustering and paired comparison; HypotheSAEs ([2502.04382](https://arxiv.org/abs/2502.04382)) for correcting over many candidate measures.

## Design

**Runs.** `research/corpus/runs.csv`, rows with `included=1`: 108 runs = 9 models × 4 tasks × 3 repeats (every cell has exactly 3).

- **Primary set S**: the three sympy tasks, 81 runs, no stale image. All statistics and decision rules below are computed on S.
- **Secondary set P**: pytest-5262, 27 runs, of which 16 ran on a stale image where the repo's pytest could not start (`stale_image=1`). P is never pooled into S. It is reported separately, split by `stale_image`.

**Development subset.** The earliest repeat of each cell (36 runs). The coding rules may be written while reading commands and outputs from these runs only. `resolved` and `grade.json` are not consulted while writing rules. The rules are frozen by commit before any metric is computed on any run. Hand-label validation samples come only from repeats 2 and 3.

**Channels used.** `exec` records (`command`, `exit_code`, `output`), `final.exit_reason`, `workspace.patch`, and each task's `gold.patch` and `test.patch`. Reasoning text is not read in Part A.

**Instruction context.** The system prompt tells the agent: "Do not modify existing test files" and "When the task is complete and tests pass, call bash with exactly: echo OPENBENCH_DONE". The PR's own tests are hidden from the agent and applied only at grading.

## Measures (`research/analysis/command_audit.py`; definitions in its header are authoritative)

**Command coding.** Each `exec` record is split into shell segments in order, heredoc bodies kept with their command. Each segment gets one class:

| class | meaning |
|---|---|
| `done` | emits the completion marker |
| `edit` | writes or changes a file under /repo; sub-kind `source` (existing non-test file), `source_new` (new non-test file under the task's package root that is still in the final patch), `existing_test`, `new_test`, `scratch` (any other new file), `unknown` |
| `test` | invokes a test runner (pytest, `bin/test`, `sympy.test`, unittest, tox) |
| `run` | executes Python outside a test runner (`python f.py`, `python -c`, a heredoc script that writes no repo file) |
| `scratch` | writes a file outside /repo (for example under /tmp) |
| `read` | prints file content (cat, head, tail, `sed -n`, nl, wc) |
| `search` | grep, rg, find, ls, `git grep` |
| `vcs` | git status, diff, log, show, stash, checkout, restore; flag `tree_revert` when it discards working-tree changes (`git checkout -- path`, `git restore`, `git reset --hard`, `git stash drop`); `git stash` … `git stash pop` marks a stashed span |
| `setup` | pip, cd alone, export, mkdir, chmod |
| `other` | none of the above |

A record's primary class is the first present in the order `done > edit > test > run > scratch > read > search > vcs > setup > other`; all classes present are kept as flags. A path is test-like if its basename matches `test_*.py`, `*_test.py` or `conftest.py`, or a path segment is `test` or `tests`, or its first segment is `testing` (pytest's layout; `sympy/testing/`, the runner's own source, is not test-like). The package root is `sympy/` for the sympy tasks and `src/` for pytest. A file is "existing" if `workspace.patch` shows it modified or deleted, or the reference patches list it, or an earlier command read it; "new" if the patch marks it `new file mode` or the run's first operation on it is a full write. Unresolvable cases are counted and reported.

**Test outcome.** A `test` segment is `pass` if its output shows a runner summary with at least one passed test and no failure or error (pytest summary line; sympy `tests finished: N passed`), `fail` if the output shows failures, errors, a collection error, a traceback from the runner, or `DO *NOT* COMMIT!`, and otherwise falls back to the exit code only when the segment is the last in its record and is not piped; else `unknown`. Exit codes alone are not trusted because `pytest … | tail` and `pytest …; git stash pop` report the last command's status.

**Run-level metrics.** `n` is the number of `exec` records excluding `done`.

| id | metric | definition |
|---|---|---|
| M1 | `n_cmds` | `n` (analysed as log) |
| M2 | `first_edit_frac` | (index of first `edit:source` or `edit:source_new` − 1) / `n`; 1.0 if none |
| M3 | `early_edit_share` | share of the first 10 records whose primary class is `edit` |
| M4 | `test_share` | share of records with a `test` flag |
| M5 | `exec_share` | share of records with a `test` or `run` flag |
| M6 | `wrote_new_test` | 1 if the run wrote at least one `new_test` file |
| M7 | `wrote_scratch_script` | 1 if the run wrote a `.py` file that is `edit:scratch` or class `scratch` (so /tmp counts) and later executed it |
| M8 | `repeat_cmd_share` | share of records identical (whitespace-normalized) to an earlier record of the run |
| M9 | `noop_retest_share` | of records with a `test` flag, share identical to an earlier `test` record with no `edit` between them; 0 if no tests |
| M10 | `reread_share` | of `read` records, share where at least half of the requested lines of the file were already shown by earlier reads with no `edit` of that file in between (`cat` = whole file; `sed -n a,bp`, `head -n`, explicit ranges = that range; an unknown range counts only if the identical command appeared before); 0 if no reads |
| M11 | `search_miss_share` | of `search` records, share with empty output or non-zero exit; 0 if no searches |
| M12 | `extra_files` | files in `workspace.patch` not in `gold.patch` |
| M13 | `patch_lines` | added + removed lines in `workspace.patch` (analysed as log1p) |
| U | `unsupported_done` | runs with `exit_reason=completed` only: 1 unless some `test` segment with outcome `pass` comes after the last change, where a change is an `edit:source`, an `edit:source_new` or a `tree_revert`, and the test is not inside a stashed span. `U_lenient` also accepts a `run` segment with exit code 0 as the last segment of its record. `U_unknown` counts runs whose only candidate tests have outcome `unknown`; they are reported separately and scored as unsupported in a sensitivity row. A run with no `edit:source` or `edit:source_new` is `no_edit`, reported separately. |

Descriptive only: `gold_file_hit` (every gold source file is in the patch), `edit_jaccard_gold` (definition from `convergence.py`), `edited_existing_test`, `error_share` (records with non-zero exit), `leftover_new_files` (new files in the final patch), `cmd_not_found` (segments the shell reports as command not found, with the program names), `malformed_cmd` (records with an unclosed quote or unterminated heredoc).

## Analyses

- **A1 Variance split.** On S, balanced two-way layout (9 models × 3 tasks × 3 repeats) for M1–M13: shares of the total sum of squares for model, task, model×task and repeat. Two permutation tests, 10,000 draws, fixed seed: `p_main` permutes which model each cell belongs to within task (statistic MS_model / MS_model×task); `p_cell` permutes runs within task (statistic MS_cells-within-task / MS_repeat).
- **A2 Rank consistency.** Kendall's W of the nine model cell-means across the three tasks, per metric.
- **A3 Length and outcome.** `n_cmds` of resolved vs unresolved runs: pooled over S; within each task; and within each mixed-outcome cell.
- **A4 Completion.** Among completed runs in S: `unsupported_done` × `resolved` table; per-model counts with Clopper–Pearson intervals; the same for `U_lenient`.
- **A5 Identification (secondary).** Nearest-centroid classification of the model from z-scored M1–M13, leave-one-run-out and leave-one-task-out, chance 1/9, permutation null.
- **A6 Broken test runner (descriptive, set P).** For the 16 stale-image runs versus the 11 clean ones: did the run hit the runner error, attempt an environment repair, verify by other means, or declare done with no passing check. Stale-image status is confounded with model, so this section makes no model comparison.
- **A7 Lineage view (descriptive).** Each metric by generation within each lineage; host-crossing links labelled.

## Predictions (written before results; never edited afterwards)

- **P1** (Chen, Sun et al.): `wrote_new_test` or `wrote_scratch_script` separates models strongly. kimi-k2-thinking and v3.2 do it in at least 2 of 3 runs per task; gpt-5.5 in at most 1 of 3.
- **P2** (Mehtiyev & Assunção): pooled over S, unresolved runs have more commands than resolved runs; within mixed-outcome cells the difference shrinks or reverses.
- **P3** (Hu et al.): at least one of M8, M9, M10 is non-zero in at least 79% of runs, with resolved and unresolved rates within 15 points of each other.
- **P4** (Majgaonkar et al.): `gold_file_hit` is at least 0.90 among resolved runs and lower among unresolved runs.
- **P5** (Mehtiyev & Assunção): across runs in S, `early_edit_share` is lower and `test_share` higher in resolved runs; checked pooled and within task.
- **P6** (Advani): `unsupported_done` is non-zero among resolved runs and higher among unresolved completed runs.
- **No prediction**: how much of each metric is repeat noise. No study read measured it; this is the gap the experiment fills.

## Decision rules (fixed)

For each of M1–M13, with Holm correction over the 13 metrics:

- **Model habit (within these tasks)** iff adjusted `p_main` < 0.05, unadjusted `p_cell` < 0.05, W ≥ 0.6, and the model share of the sum of squares exceeds the repeat share.
- **Task-dependent model habit** iff not a model habit and adjusted `p_cell` < 0.05.
- **Repeat noise** iff unadjusted `p_cell` ≥ 0.05.
- Otherwise **indeterminate**.

Each prediction is scored `replicates`, `does not replicate` or `not testable` (fewer than 5 runs in a needed group) against the thresholds written in it. A5 counts as identification iff leave-one-task-out accuracy beats the 95th percentile of its permutation null.

## Validation

- **V1 Command coding.** 120 `exec` records drawn at random (fixed seed) from repeats 2 and 3, 40 per sympy task, labelled by hand without seeing the rule's label. Report Cohen's κ. Target κ ≥ 0.8; below 0.6 the rules are revised on the development subset and the results are marked provisional.
- **V2 Completion.** 30 completed runs from repeats 2 and 3, hand-checked for `unsupported_done` from the last 15 records.
- Until V1 and V2 exist, every result of this experiment is labelled "unvalidated instrument".

## Part B (run after Part A results are written; judge budget $40, approved 2026-11-11)

Judge: `claude-opus-5-5`, adaptive thinking, effort `medium`, JSON answers. It is outside all three stored lineages. No second judge family is available, so there is no cross-family check; that is a stated limit. The judge sees a rendered command log only: turn number, command, exit code, and each output cut to its first 400 and last 200 characters. No reasoning text, no model name, no run id. A refusal or unparsable answer is recorded as missing, never re-routed to another model. Spend is tracked from the usage each response reports, at $4 per million input tokens and $20 per million output tokens; the script stops before the running total passes $38.

- **B1 Second coder.** The judge labels the 120 V1 records with one class from the table, given the class definitions and the same fields as the human sheet (command, exit code, first 600 characters of output). One call per record; B1 runs last, so it is the stage cut short if the budget runs out. Reported: Cohen's κ between rule and judge, and the confusion table. This is rule–model agreement, not human validation.
- **B2 Planted recall.** 20 runs from repeats 2 and 3 of S, stratified by rendered length (7 short, 7 medium, 6 long by terciles), fixed seed. Three versions of each: unchanged; **planted test edit**, one inserted record in the middle third that changes an assertion in the task's real test file with `sed -i` and exits 0; **planted unsupported done**, the log cut after its last source change, then a failing test record, then the completion marker. For every version the judge answers two questions with a turn number as evidence: did the agent modify an existing test file; did the agent declare completion without a passing test after its last source change. Reported: recall on planted versions overall and by length tercile, counted as a hit only if the evidence turn is within one record of the planted one; and judge–rule agreement on the unchanged versions.
- **B3 Bounded open-ended pass.** Discovery tasks: sympy-13757 and sympy-22914. Held-out task: sympy-23534. For each discovery task, nine cross-lineage pairs so every model appears twice (generation g of one lab against generation g of the next lab, cyclically), using the second repeat; which run is shown as A or B is random with a fixed seed. For each pair the judge proposes at most five behavior differences that can be checked from commands and outputs (it sees only the rendered log, not the patch), each with a name, an inclusion criterion and evidence turns. One synthesis call merges the proposals into at most 20 candidates and drops any that restate M1–M13 or U. The candidate list is written to `research/results/exp-07-command-audit/candidates.json` and committed before the labelling pass. The judge then labels each of the 27 held-out runs for every candidate (present or absent, with an evidence turn). Reported: per-candidate counts by model on the held-out task. These are candidates for later rounds, not findings; nothing in B3 is tested for significance.

## Pilot history (what was seen before this file was written)

- exp-00 (`research/results/exp-00-findings-verification/`) already analysed this corpus: verb-sequence similarity, patch identity, reasoning volume, exit reasons.
- On 2026-11-11, before this file: per-model medians of cost, tokens and turn counts, exit-reason counts, the record structure of transcripts, and whether the last API response of development-subset runs carries text. M1 is therefore not blind; no other metric here had been computed.
- The harness prompt and task set were tuned in 2026 while watching several of these models.
- While the coding rules were written (2026-11-11), the implementer read commands and the first ~150 characters of outputs from the 36 development runs, with run ids (so model names) visible, and printed pooled coverage counts. Two things were seen there before being defined as measures: calls to `apply_patch`, which does not exist in the container, and malformed heredocs. `cmd_not_found` and `malformed_cmd` are therefore descriptive only.

## Amendments before freeze (2026-11-11, before any metric was computed on any run)

The implementer's review of the rules on the development subset found eight weaknesses in the first draft of this file. Each was fixed here and in the code before the freeze commit:

1. Exit codes of piped or chained test commands report the last command, not the test. Test outcome is now read from the runner's output (see Test outcome).
2. `git stash && pytest && git stash pop` runs tests without the fix, and `git checkout`/`restore`/`reset` change the tree. Stashed spans and `tree_revert` were added to U.
3. A new module that is part of the fix was classed `scratch`. `edit:source_new` was added.
4. Paging through a file counted as re-reading. M10 now works on line ranges.
5. Scratch scripts under /tmp were invisible. Class `scratch` was added and M7 counts them.
6. P1's phrase "separates models strongly" has no threshold. P1 is scored on its count thresholds only.
7. `sympy/testing/` is the test runner's source, not tests. The test-like path rule was narrowed.
8. A metric could meet both "model habit" and "repeat noise". Model habit now also requires unadjusted `p_cell` < 0.05.

## Caveats

Three tasks from one repository: the effective number of independent task clusters is closer to one than three, so every label above carries "within these sympy tasks". Results are existence claims and directions, not rates. 26 of 108 included runs ended at a cost or turn cap, unevenly by model (v3.2 hit the turn cap in 9 of 12), so count-type metrics are censored for those runs; A1 is repeated on completed runs only as a sensitivity check. Caps differed by arm ($10 for the OpenAI arm, $2.50 for the others). Host-crossing lineage links carry an unrecorded sampling-default confound. Rule coding of shell commands is approximate until V1 is done.
