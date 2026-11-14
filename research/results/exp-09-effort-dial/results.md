# exp-09 results — effort dial on Sonnet 5.5

Run 2026-11-14 from freeze commit `a51b148`. Spec: [exp-09-effort-dial.md](../../experiments/exp-09-effort-dial.md). Full tables: `tables.md`. Run facts, spend and caveats of the round: [exp-08 results](../exp-08-opus-line/results.md).

**Status: unvalidated instrument.**

48 runs: `claude-sonnet-5-5` at effort low, medium, high, xhigh, six tasks, two repeats. 47 resolved (not resolved: low on xarray, r1). One run ended on the wall clock (xhigh on sympy, r2).

## Findings

**A5, the dial works.** Thinking tokens per reply rise with the setting (6.5, 24, 38, 142; p = 0.0001), so the experiment is informative.

Four measures are labelled **responds to effort** (Holm-adjusted p < 0.05):

| measure | low | medium | high | xhigh | shape | p (Holm) |
|---|---|---|---|---|---|---|
| commands per run (M1, mean) | 3.8 | 4.0 | 5.8 | 12.1 | step-like | 0.016 |
| wrote a new test file (M6, share of runs) | 0.00 | 0.00 | 0.00 | 0.58 | step-like | 0.020 |
| files changed beyond the needed ones (M12) | 0.08 | 0.17 | 1.00 | 2.00 | gradual | 0.0028 |
| patch lines (M13, median) | 5.5 | 5.5 | 10.5 | 46 | gradual | 0.0015 |

One candidate: the first edit comes earlier at higher effort (M2).

Low and medium are nearly the same run; most of the change sits between high and xhigh. Ten measures were not shown to respond, among them early editing, test share and `backed_done`.

**A6, reading exp-08 through the dial.** Of exp-08's four trends, three also respond to effort (commands, extra files, patch size) and one does not (early editing). Commands per run respond in the opposite direction: more effort means longer runs, while newer Opus generations run shorter. For exp-08's eight "none" labels, only `wrote_new_test` responds here, so only that "none" is informative; the other seven are measures this instrument was not shown to be sensitive on.

## Predictions

| | prediction | result |
|---|---|---|
| P1 | `n_cmds` rises with effort | held |
| P2 | `test_share` rises | not held (none) |
| P3 | `backed_done` rises | not held (none) |
| P4 | `reread_share` and `repeat_cmd_share` do not respond | held |
| P5 | thinking tokens per reply rise | held |
| P6 | at least three measures respond | held (four) |

Four of six held.
