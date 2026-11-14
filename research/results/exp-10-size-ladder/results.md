# exp-10 results — size ladder

Run 2026-11-14 from freeze commit `a51b148`. Spec: [exp-10-size-ladder.md](../../experiments/exp-10-size-ladder.md). Full tables: `tables.md`. Run facts, spend and caveats of the round: [exp-08 results](../exp-08-opus-line/results.md).

**Status: unvalidated instrument.**

48 runs at effort high: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-2` (a separate product line, the top of the ladder, not a member of the 5.5 family), six tasks, two repeats. The Sonnet runs are exp-09's high arm and the Opus runs are exp-08's Opus 5.5 row. No drop was applied, so the ladder has all four levels. 47 resolved (not resolved: Haiku on sympy, r2). Four runs ended on a cap, all on sympy: Haiku twice on the turn cap, Fable twice on the wall clock.

## Findings

Two measures are labelled **moves with size** (Holm-adjusted p < 0.05, all six tasks agree):

| measure | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 | Fable 5.2 | shape | p (Holm) |
|---|---|---|---|---|---|---|
| files changed beyond the needed ones (M12) | 0.92 | 1.00 | 1.75 | 2.08 | step-like | 0.0045 |
| patch lines (M13, median) | 13.5 | 10.5 | 28.5 | 90 | gradual | 0.031 |

Nothing else shows an ordered pattern. Commands per run: 9.8, 5.8, 7.4, 11.9. A new test file was written in 33%, 0%, 42% and 75% of runs (not ordered: Sonnet wrote none).

**A5, generation against size.**

- Patch size and extra files trend in both experiments in the same direction: they follow capability, and generation and size cannot be separated.
- Commands per run and early editing trend across Opus generations but show no pattern across sizes: they follow the generation.
- The other eleven measures: no ordered pattern, or not classified because of a candidate label.

Descriptive, not tested: `backed_done` is lowest for Fable 5.2 (0.33) and Sonnet 5.5 (0.42) and highest for Haiku 5.5 and Opus 5.5 (0.83). Two of Fable's twelve runs ended on the wall clock, which scores 0 by definition; of its eight completed runs with an edit, four ended without a passing test after the last change.

## Predictions

| | prediction | result |
|---|---|---|
| P1 | `backed_done` rises with size | not held (none, direction down) |
| P2 | `repeat_cmd_share` falls with size | not held (zero everywhere) |
| P3 | `n_cmds` shows no ordered pattern | held |
| P4 | Haiku 5.5 has the lowest `backed_done` | not held (Fable 5.2 is lowest) |
| P5 | at least one measure moves with size | held (two) |

Two of five held.
