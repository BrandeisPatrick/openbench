# exp-08-opus-line results [unvalidated instrument]

Runs: 60. Levels (generation): claude-opus-4-6, claude-opus-4-7, claude-opus-4-8, claude-opus-5, claude-opus-5-5.
Tasks: sympy__sympy-13757, astropy__astropy-12907, pydata__xarray-2905, pytest-dev__pytest-10051, scikit-learn__scikit-learn-10297, sphinx-doc__sphinx-10466.

## V1 coverage

| level | runs | commands other | segments other | edits unknown | flag |
|---|---|---|---|---|---|
| claude-opus-4-6 | 12 | 0.000 | 0.000 | 0.000 |  |
| claude-opus-4-7 | 12 | 0.000 | 0.007 | 0.000 |  |
| claude-opus-4-8 | 12 | 0.000 | 0.003 | 0.000 |  |
| claude-opus-5 | 12 | 0.000 | 0.022 | 0.000 |  |
| claude-opus-5-5 | 12 | 0.000 | 0.004 | 0.057 |  |

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
| M1 | n_cmds | 0.23 | 0.52 | 0.18 | 0.07 | 0.031 | 0.000 | model habit |
| M2 | first_edit_frac | 0.30 | 0.09 | 0.42 | 0.18 | 0.099 | 0.001 | task-dependent model habit |
| M3 | early_edit_share | 0.43 | 0.19 | 0.25 | 0.12 | 0.004 | 0.000 | model habit |
| M4 | test_share | 0.29 | 0.24 | 0.35 | 0.13 | 0.079 | 0.000 | task-dependent model habit |
| M5 | exec_share | 0.27 | 0.38 | 0.19 | 0.16 | 0.014 | 0.001 | task-dependent model habit |
| M6 | wrote_new_test | 0.36 | 0.11 | 0.42 | 0.11 | 0.239 | 0.013 | indeterminate |
| M7 | wrote_scratch_script | 0.03 | 0.83 | 0.14 | 0.00 | 1.000 | 0.112 | repeat noise |
| M8 | repeat_cmd_share | 0.35 | 0.09 | 0.37 | 0.19 | 0.239 | 0.012 | indeterminate |
| M9 | noop_retest_share | - | - | - | - | - | - | indeterminate |
| M10 | reread_share | 0.12 | 0.15 | 0.65 | 0.07 | 1.000 | 0.000 | task-dependent model habit |
| M11 | search_miss_share | 0.06 | 0.08 | 0.46 | 0.40 | 1.000 | 0.115 | repeat noise |
| M12 | extra_files | 0.66 | 0.05 | 0.18 | 0.12 | 0.001 | 0.000 | model habit |
| M13 | patch_lines | 0.41 | 0.20 | 0.18 | 0.20 | 0.005 | 0.003 | task-dependent model habit |
| M14 | backed_done | 0.16 | 0.33 | 0.23 | 0.28 | 0.099 | 0.255 | repeat noise |
| M15 | multi_call_share | 0.14 | 0.14 | 0.54 | 0.18 | 1.000 | 0.118 | repeat noise |

## A2-A4 trend test

Holm over the tested measures.

| id | measure | blocks | L - E0 | p | p Holm | agree/disagree/no sign | label | shape | claude-opus-4-6 | claude-opus-4-7 | claude-opus-4-8 | claude-opus-5 | claude-opus-5-5 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | n_cmds | 6 | -36.5 | 0.0030 | 0.0360 | 6/0/0 | trend | gradual | 2.770 | 2.749 | 2.107 | 2.425 | 1.960 |
| M2 | first_edit_frac | 6 | -25.0 | 0.0450 | 0.3150 | 5/1/0 | candidate | step-like | 0.393 | 0.388 | 0.404 | 0.266 | 0.266 |
| M3 | early_edit_share | 6 | 44.0 | 0.0001 | 0.0015 | 6/0/0 | trend | gradual | 0.090 | 0.112 | 0.222 | 0.204 | 0.331 |
| M4 | test_share | 6 | 32.0 | 0.0100 | 0.1100 | 5/0/1 | candidate | gradual | 0.288 | 0.311 | 0.255 | 0.392 | 0.477 |
| M5 | exec_share | 6 | 24.0 | 0.0516 | 0.3150 | 5/1/0 | none |  | 0.451 | 0.447 | 0.368 | 0.475 | 0.589 |
| M6 | wrote_new_test | 6 | 15.0 | 0.0150 | 0.1440 | 3/0/3 | none |  | 0.000 | 0.000 | 0.000 | 0.000 | 0.417 |
| M7 | wrote_scratch_script | 6 | -5.0 | 0.4007 | 0.8013 | 1/0/5 | none |  | 0.333 | 0.167 | 0.167 | 0.167 | 0.167 |
| M8 | repeat_cmd_share | 6 | -15.0 | 0.0144 | 0.1440 | 3/0/3 | none |  | 0.013 | 0.000 | 0.000 | 0.000 | 0.000 |
| M9 | noop_retest_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/0/6 | none |  | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| M10 | reread_share | 6 | -24.5 | 0.0187 | 0.1496 | 5/1/0 | candidate | gradual | 0.137 | 0.207 | 0.097 | 0.012 | 0.049 |
| M11 | search_miss_share | 6 | -10.5 | 0.1442 | 0.5767 | 2/0/4 | none |  | 0.039 | 0.048 | 0.021 | 0.000 | 0.000 |
| M12 | extra_files | 6 | 44.5 | 0.0001 | 0.0015 | 6/0/0 | trend | gradual | 0.000 | 0.167 | 0.167 | 0.833 | 1.750 |
| M13 | patch_lines | 6 | 37.5 | 0.0006 | 0.0078 | 6/0/0 | trend | gradual | 1.511 | 1.716 | 1.724 | 2.176 | 3.229 |
| M14 | backed_done | 6 | -10.5 | 0.2303 | 0.6908 | 4/0/2 | none |  | 1.000 | 0.667 | 0.833 | 0.500 | 0.833 |
| M15 | multi_call_share | 6 | 10.5 | 0.0825 | 0.4125 | 2/0/4 | none |  | 0.000 | 0.000 | 0.000 | 0.026 | 0.007 |

## Context (not tested)

| | claude-opus-4-6 | claude-opus-4-7 | claude-opus-4-8 | claude-opus-5 | claude-opus-5-5 |
|---|---|---|---|---|---|
| runs | 12 | 12 | 12 | 12 | 12 |
| resolved | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 |
| turns | 20.2 | 20.2 | 12.2 | 14.8 | 8.6 |
| thinking_tokens_per_reply | 15.4 | 64.3 | 47.0 | 139.7 | 46.1 |
| output_tokens_per_reply | 159.3 | 239.7 | 185.0 | 310.5 | 283.3 |
| max_tokens_replies_total | 0 | 0 | 0 | 0 | 0 |
| cost_usd_total | 3.2 | 5.3 | 1.7 | 4.0 | 1.1 |
| U (completed, edited) | 0/12 | 3/11 | 2/12 | 6/12 | 2/12 |

## A5 profile drift

LOTO accuracy 0.550 (chance 0.200, null q95 0.300, p 0.0001); rank error 0.550 (null mean 1.602, p 0.0001).

## A6 outcome check

Resolved per generation: claude-opus-4-6 12/12, claude-opus-4-7 12/12, claude-opus-4-8 12/12, claude-opus-5 12/12, claude-opus-5-5 12/12. Differs: False.

## A7 bridge (sympy__sympy-13757; descriptive only; different providers, settings and dates; analysis scale)

| run set | n | resolved | n_cmds | first_edit_frac | early_edit_share | test_share | exec_share | wrote_new_test | wrote_scratch_script | repeat_cmd_share | noop_retest_share | reread_share | search_miss_share | extra_files | patch_lines | backed_done | multi_call_share |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| round2: claude-opus-4-6 | 2 | 1.00 | 3.52 | 0.34 | 0.00 | 0.38 | 0.50 | 0.00 | 0.00 | 0.03 | 0.00 | 0.12 | 0.24 | 0.00 | 0.90 | 1.00 | 0.00 |
| round2: claude-opus-4-7 | 2 | 1.00 | 3.75 | 0.30 | 0.00 | 0.34 | 0.53 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 | 0.04 | 0.00 | 0.69 | 0.00 | 0.00 |
| round2: claude-opus-4-8 | 2 | 1.00 | 3.31 | 0.37 | 0.05 | 0.30 | 0.46 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.50 | 1.98 | 0.00 | 0.00 |
| round2: claude-opus-5 | 2 | 1.00 | 3.43 | 0.21 | 0.15 | 0.45 | 0.60 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | 2.19 | 0.00 | 0.00 |
| round2: claude-opus-5-5 | 2 | 1.00 | 2.05 | 0.33 | 0.25 | 0.45 | 0.59 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.50 | 1.50 | 0.50 | 0.00 |
| round1: gpt-5.5 | 3 | 1.00 | 3.75 | 0.35 | 0.00 | 0.19 | 0.36 | 1.00 | 0.00 | 0.02 | 0.05 | 0.03 | 0.11 | 1.33 | 2.91 | 1.00 | - |
| round1: kimi-k2-thinking | 3 | 1.00 | 4.11 | 0.42 | 0.00 | 0.22 | 0.43 | 0.00 | 0.33 | 0.06 | 0.03 | 0.22 | 0.18 | 0.00 | 0.69 | 0.67 | - |
| round1: kimi-k2.6 | 3 | 0.67 | 4.60 | 0.27 | 0.00 | 0.09 | 0.48 | 0.00 | 0.67 | 0.03 | 0.00 | 0.23 | 0.14 | 0.00 | 1.39 | 0.00 | - |
| round1: kimi-k3 | 3 | 0.67 | 3.69 | 0.59 | 0.00 | 0.19 | 0.35 | 0.00 | 0.33 | 0.01 | 0.00 | 0.00 | 0.13 | 0.00 | 1.36 | 0.00 | - |
| round1: o1 | 3 | 0.00 | 2.40 | 0.14 | 0.57 | 0.08 | 0.08 | 0.33 | 0.33 | 0.10 | 0.00 | 0.00 | 0.20 | 2.67 | 6.75 | 0.00 | - |
| round1: o3 | 3 | 0.00 | 4.20 | 0.34 | 0.00 | 0.12 | 0.50 | 0.00 | 0.00 | 0.07 | 0.00 | 0.09 | 0.16 | 0.67 | 2.71 | 0.00 | - |
| round1: r1-0528 | 3 | 0.00 | 1.71 | 0.14 | 0.71 | 0.00 | 0.55 | 0.67 | 0.33 | 0.00 | 0.00 | 0.00 | 0.33 | 2.00 | 7.16 | 0.00 | - |
| round1: v3.2 | 3 | 0.33 | 4.61 | 0.71 | 0.00 | 0.04 | 0.37 | 0.33 | 0.67 | 0.02 | 0.00 | 0.34 | 0.16 | 1.67 | 8.88 | 0.00 | - |
| round1: v4-pro | 3 | 1.00 | 4.07 | 0.39 | 0.00 | 0.19 | 0.42 | 0.00 | 0.33 | 0.01 | 0.00 | 0.14 | 0.09 | 0.00 | 1.82 | 0.33 | - |

## Predictions

- P1. `backed_done` rises with generation (trend or candidate). -> **not held** (label none, direction -1, p 0.2303)
- P2. `test_share` rises with generation (trend or candidate). -> **held** (label candidate, direction +1, p 0.009999)
- P3. `n_cmds` shows no trend: run length is a per-model quirk, as in exp-07. -> **not held** (label trend)
- P4. `early_edit_share` is near zero for all five models, so it cannot show a trend. -> **not held** (max generation mean 0.331 (near zero <= 0.05); label trend)
- P5. `multi_call_share` falls with generation (older models in the settings check sent two calls in one reply more often). -> **not held** (label none, direction +1, p 0.08249)
- P6. At least one and at most three of the 15 measures are labelled trend. -> **not held** (4 labelled trend of 15 tested)
- P7. A5: identification is above chance, and the rank error is below its null (p < 0.05). -> **held** (accuracy 0.550 vs null q95 0.300; rank error p 9.999e-05)
