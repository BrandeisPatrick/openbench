# exp-08 results — Opus line (round 2, Part A)

Run 2026-11-14 from freeze commit `a51b148` on branch `claude-round`. Spec: [exp-08-opus-line.md](../../experiments/exp-08-opus-line.md). Code: `research/analysis/claude_round.py`. Outputs: `metrics.csv` (one row per run), `analysis.json`, `tables.md` (every table of A1 to A7, V1, V2 and the scored predictions). Runs: [corpus](../../corpus/runs-2026-11-claude-round/README.md).

**Status: unvalidated instrument.** The command-coding rules are still unchecked against hand labels (exp-07 V1/V2). Every number is conditional on those rules, one harness, six tasks and two repeats.

## What was run (the whole round)

- 132 runs, none crashed, none rerun: 60 for exp-08, 48 for exp-09 (12 of them shared with exp-10), 24 new for exp-10. Every cell has both repeats.
- Spend: $26.33 of the $125 ceiling, including $0.09 before the freeze. The pilot (8 runs) cost $8.66; the projection after it was $117.66, so no drop was applied.
- Order as pre-registered: task by task, one image at a time, each image rebuilt from the freeze commit and re-checked with a golden and a null run before its runs.
- Six runs ended on a cap, all on `sympy__sympy-13757`: wall clock for Opus 4.7 (r1), Fable 5.2 (r1, r2) and Sonnet 5.5 xhigh (r2); turn cap for Haiku 5.5 (r1, r2). They are kept as they are.
- Outcome: 130 of 132 runs resolved. Not resolved: Haiku 5.5 on sympy (r2, turn cap) and Sonnet 5.5 at effort low on xarray (r1).

## Findings of exp-08 (five Opus generations, 60 runs, all resolved)

Four measures are labelled **trend** (Holm-adjusted p < 0.05, all six tasks agree in direction):

| measure | direction with generation | Opus 4.6 | 4.7 | 4.8 | 5 | 5.5 | p (Holm) |
|---|---|---|---|---|---|---|---|
| commands per run (M1, mean) | falls | 19.3 | 19.3 | 11.2 | 13.8 | 7.4 | 0.036 |
| share of the opening that is editing (M3) | rises | 0.09 | 0.11 | 0.22 | 0.20 | 0.33 | 0.0015 |
| files changed beyond the needed ones (M12) | rises | 0.00 | 0.17 | 0.17 | 0.83 | 1.75 | 0.0015 |
| patch lines (M13, median) | rises | 3 | 3 | 3 | 7.5 | 28.5 | 0.0078 |

Raw-scale means and medians are shown for reading; the tests ran on the pre-registered scales (log for M1, log1p for M13), see `tables.md`.

Three measures are **candidates** (unadjusted p < 0.05, named for a later round, not findings): the first edit comes earlier (M2, step-like at Opus 5), the share of test commands rises (M4, 0.29 to 0.48), re-reading falls (M10).

Not labelled but worth a look later: a new test file was written in 5 of 12 Opus 5.5 runs and in none of the 48 runs of the four older generations (M6; three tasks have no sign, so the rule gives "none").

- **A1.** Model habits (more variation between models than between repeats): commands per run, early editing, extra files. Patch size, first edit, test share and execution share depend on model and task together. `backed_done` and `multi_call_share` are repeat noise here.
- **A5.** A run's generation is identified from its 15 measures in 55% of cases (chance 20%, null 95th percentile 30%), and the mean rank error is 0.55 against 1.60 under the null (p = 0.0001). Wrong guesses land on neighboring generations: the whole profile drifts steadily.
- **A6.** Every generation resolved 12 of 12, so the trends are not a by-product of different solve rates. It also means these tasks do not separate the generations by outcome at all.
- **A7.** Bridge table in `tables.md`, descriptive only.
- **V1, V2.** Coverage of the coding rules is high for all five models (at most 5.7% unknown edits, Opus 5.5); no task had a test runner that failed to start.

### Predictions (written before any run)

| | prediction | result |
|---|---|---|
| P1 | `backed_done` rises with generation | not held (none; 1.00, 0.67, 0.83, 0.50, 0.83) |
| P2 | `test_share` rises | held (candidate) |
| P3 | `n_cmds` shows no trend | not held (trend, falling) |
| P4 | `early_edit_share` near zero for all | not held (up to 0.33; trend) |
| P5 | `multi_call_share` falls | not held (none; near zero everywhere) |
| P6 | one to three measures labelled trend | not held (four) |
| P7 | profile identification above chance, rank error below null | held |

Two of seven held. The author's guesses, taken from exp-07 and release notes, were a poor guide.

## Reading across the three experiments

See also [exp-09](../exp-09-effort-dial/results.md) and [exp-10](../exp-10-size-ladder/results.md).

| measure | newer generation (exp-08) | more effort (exp-09) | bigger model (exp-10) |
|---|---|---|---|
| patch lines | rises | rises | rises |
| extra files | rises | rises | rises |
| commands per run | falls | rises | no pattern |
| early editing | rises | no response | no pattern |

- **Bigger patches and more files touched go with everything that makes a model "more"**: a newer generation, a higher effort setting, a larger model. Generation, effort and size cannot be separated for these two.
- **Shorter runs and earlier editing follow the generation only.** Effort pushes run length the other way (more effort, more commands), and size shows no pattern, so "newer models simply think more" does not explain them. Thinking tokens per reply are also not ordered by generation (15, 64, 47, 140, 46).
- **Closing a run with a passing test (`backed_done`) follows none of the three.** exp-09 did not show the measure to be sensitive, so this "none" is weak.

## Caveats

- Six tasks, two repeats. Only strong, consistent effects could pass, and the four that did agree on all six tasks.
- 130 of 132 runs resolved. These are public SWE-bench Verified issues from before 2023 that every model may have seen; behavior on tasks a model cannot solve from memory may differ.
- The six cap-ended runs are all on the sympy task. A run that hits the wall clock scores 0 on `backed_done` by definition.
- One harness, one prompt, one tool, one command per turn.

## Part B

Not yet run when this file was written; its results are appended below when it is.
