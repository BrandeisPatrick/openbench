# exp-09-effort-dial results [unvalidated instrument]

Runs: 48. Levels (effort): low, medium, high, xhigh.
Tasks: sympy__sympy-13757, astropy__astropy-12907, pydata__xarray-2905, pytest-dev__pytest-10051, scikit-learn__scikit-learn-10297, sphinx-doc__sphinx-10466.

## V1 coverage

| level | runs | commands other | segments other | edits unknown | flag |
|---|---|---|---|---|---|
| low | 12 | 0.000 | 0.000 | 0.000 |  |
| medium | 12 | 0.000 | 0.009 | 0.000 |  |
| high | 12 | 0.000 | 0.020 | 0.000 |  |
| xhigh | 12 | 0.000 | 0.077 | 0.021 |  |

## V2 runner start

| task | runs | runner failed | after edit | dropped |
|---|---|---|---|---|
| astropy__astropy-12907 | 22 | 0 | 0 |  |
| pydata__xarray-2905 | 22 | 0 | 0 |  |
| pytest-dev__pytest-10051 | 22 | 0 | 0 |  |
| scikit-learn__scikit-learn-10297 | 22 | 0 | 0 |  |
| sphinx-doc__sphinx-10466 | 22 | 0 | 0 |  |
| sympy__sympy-13757 | 22 | 0 | 0 |  |

## A1 variance split

Balanced design.

| id | measure | level | task | lvl:task | repeat | p_main* | p_cell | label |
|---|---|---|---|---|---|---|---|---|
| M1 | n_cmds | 0.38 | 0.45 | 0.14 | 0.03 | 0.002 | 0.000 | model habit |
| M2 | first_edit_frac | 0.30 | 0.05 | 0.40 | 0.25 | 0.327 | 0.006 | indeterminate |
| M3 | early_edit_share | 0.05 | 0.44 | 0.22 | 0.29 | 1.000 | 0.339 | repeat noise |
| M4 | test_share | 0.08 | 0.46 | 0.29 | 0.18 | 1.000 | 0.031 | indeterminate |
| M5 | exec_share | 0.03 | 0.37 | 0.33 | 0.28 | 1.000 | 0.094 | repeat noise |
| M6 | wrote_new_test | 0.51 | 0.06 | 0.18 | 0.25 | 0.040 | 0.021 | model habit |
| M7 | wrote_scratch_script | 0.08 | 0.33 | 0.41 | 0.18 | 1.000 | 0.422 | repeat noise |
| M8 | repeat_cmd_share | - | - | - | - | - | - | indeterminate |
| M9 | noop_retest_share | - | - | - | - | - | - | indeterminate |
| M10 | reread_share | 0.09 | 0.16 | 0.43 | 0.32 | 1.000 | 0.140 | repeat noise |
| M11 | search_miss_share | 0.07 | 0.10 | 0.28 | 0.55 | 1.000 | 1.000 | repeat noise |
| M12 | extra_files | 0.73 | 0.07 | 0.14 | 0.06 | 0.001 | 0.000 | model habit |
| M13 | patch_lines | 0.69 | 0.15 | 0.14 | 0.03 | 0.001 | 0.000 | model habit |
| M14 | backed_done | 0.05 | 0.53 | 0.21 | 0.21 | 1.000 | 0.263 | repeat noise |
| M15 | multi_call_share | 0.04 | 0.17 | 0.38 | 0.42 | 1.000 | 0.245 | repeat noise |

## A2-A4 trend test

Holm over the tested measures.

| id | measure | blocks | L - E0 | p | p Holm | agree/disagree/no sign | label | shape | low | medium | high | xhigh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | n_cmds | 6 | 21.0 | 0.0012 | 0.0156 | 6/0/0 | responds to effort | step-like | 1.294 | 1.295 | 1.595 | 2.266 |
| M2 | first_edit_frac | 6 | -15.5 | 0.0283 | 0.3113 | 5/1/0 | candidate | gradual | 0.453 | 0.538 | 0.392 | 0.283 |
| M3 | early_edit_share | 6 | -11.0 | 0.1256 | 0.9943 | 4/2/0 | not shown to respond |  | 0.382 | 0.366 | 0.374 | 0.294 |
| M4 | test_share | 6 | 11.0 | 0.1243 | 0.9943 | 4/2/0 | not shown to respond |  | 0.328 | 0.300 | 0.409 | 0.432 |
| M5 | exec_share | 6 | 2.5 | 0.7600 | 1.0000 | 3/2/1 | not shown to respond |  | 0.462 | 0.393 | 0.437 | 0.460 |
| M6 | wrote_new_test | 6 | 15.0 | 0.0017 | 0.0204 | 5/0/1 | responds to effort | step-like | 0.000 | 0.000 | 0.000 | 0.583 |
| M7 | wrote_scratch_script | 6 | 3.5 | 0.3264 | 1.0000 | 1/0/5 | not shown to respond |  | 0.000 | 0.000 | 0.167 | 0.083 |
| M8 | repeat_cmd_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/0/6 | not shown to respond |  | 0.000 | 0.000 | 0.000 | 0.000 |
| M9 | noop_retest_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/0/6 | not shown to respond |  | 0.000 | 0.000 | 0.000 | 0.000 |
| M10 | reread_share | 6 | 6.5 | 0.0886 | 0.8859 | 2/0/4 | not shown to respond |  | 0.000 | 0.000 | 0.042 | 0.079 |
| M11 | search_miss_share | 6 | 8.0 | 0.1051 | 0.9458 | 4/0/2 | not shown to respond |  | 0.000 | 0.033 | 0.021 | 0.066 |
| M12 | extra_files | 6 | 25.0 | 0.0002 | 0.0028 | 6/0/0 | responds to effort | gradual | 0.083 | 0.167 | 1.000 | 2.000 |
| M13 | patch_lines | 6 | 26.5 | 0.0001 | 0.0015 | 6/0/0 | responds to effort | gradual | 1.649 | 1.693 | 2.326 | 3.734 |
| M14 | backed_done | 6 | 6.0 | 0.3349 | 1.0000 | 3/2/1 | not shown to respond |  | 0.417 | 0.417 | 0.417 | 0.667 |
| M15 | multi_call_share | 6 | -8.0 | 0.2812 | 1.0000 | 3/2/1 | not shown to respond |  | 0.109 | 0.132 | 0.089 | 0.092 |

## Context (not tested)

| | low | medium | high | xhigh |
|---|---|---|---|---|
| runs | 12 | 12 | 12 | 12 |
| resolved | 11/12 | 12/12 | 12/12 | 12/12 |
| turns | 5.1 | 5.1 | 7.0 | 13.1 |
| thinking_tokens_per_reply | 6.5 | 23.9 | 38.0 | 142.1 |
| output_tokens_per_reply | 169.8 | 181.5 | 221.2 | 384.9 |
| max_tokens_replies_total | 0 | 0 | 0 | 0 |
| cost_usd_total | 0.2 | 0.2 | 0.4 | 1.3 |
| U (completed, edited) | 6/11 | 6/11 | 7/12 | 2/10 |

## A5 thinking actually changed

Trend test on thinking tokens per reply: p 0.0001, direction +1 -> passes.

## A6 exp-08 through the dial

| id | measure | exp-08 | exp-09 | reading of exp-08 none |
|---|---|---|---|---|
| M1 | n_cmds | trend | responds to effort |  |
| M2 | first_edit_frac | candidate | candidate |  |
| M3 | early_edit_share | trend | not shown to respond |  |
| M4 | test_share | candidate | not shown to respond |  |
| M5 | exec_share | none | not shown to respond | instrument not shown to be sensitive |
| M6 | wrote_new_test | none | responds to effort | informative |
| M7 | wrote_scratch_script | none | not shown to respond | instrument not shown to be sensitive |
| M8 | repeat_cmd_share | none | not shown to respond | instrument not shown to be sensitive |
| M9 | noop_retest_share | none | not shown to respond | instrument not shown to be sensitive |
| M10 | reread_share | candidate | not shown to respond |  |
| M11 | search_miss_share | none | not shown to respond | instrument not shown to be sensitive |
| M12 | extra_files | trend | responds to effort |  |
| M13 | patch_lines | trend | responds to effort |  |
| M14 | backed_done | none | not shown to respond | instrument not shown to be sensitive |
| M15 | multi_call_share | none | not shown to respond | instrument not shown to be sensitive |

Thinking tokens per reply by Opus generation: claude-opus-4-6 15, claude-opus-4-7 64, claude-opus-4-8 47, claude-opus-5 140, claude-opus-5-5 46

## Predictions

- P1. `n_cmds` rises with effort (responds or candidate). -> **held** (label trend, direction +1, p 0.0012)
- P2. `test_share` rises with effort (responds or candidate). -> **not held** (label none, direction +1, p 0.1243)
- P3. `backed_done` rises with effort (responds or candidate). -> **not held** (label none, direction +1, p 0.3349)
- P4. `reread_share` and `repeat_cmd_share` are not shown to respond. -> **held** (reread_share none, repeat_cmd_share none)
- P5. Thinking tokens per reply rise with effort (A5 passes). -> **held** (p 9.999e-05, direction +1)
- P6. At least three of the 15 measures respond to effort. -> **held** (4 labelled trend of 15 tested)
