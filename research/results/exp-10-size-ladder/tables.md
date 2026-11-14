# exp-10-size-ladder results [unvalidated instrument]

Runs: 48. Levels (size): claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-2.
Tasks: sympy__sympy-13757, astropy__astropy-12907, pydata__xarray-2905, pytest-dev__pytest-10051, scikit-learn__scikit-learn-10297, sphinx-doc__sphinx-10466.

## V1 coverage

| level | runs | commands other | segments other | edits unknown | flag |
|---|---|---|---|---|---|
| claude-haiku-5-5 | 12 | 0.000 | 0.049 | 0.000 |  |
| claude-sonnet-5-5 | 12 | 0.000 | 0.020 | 0.000 |  |
| claude-opus-5-5 | 12 | 0.000 | 0.004 | 0.057 |  |
| claude-fable-5-2 | 12 | 0.013 | 0.128 | 0.042 |  |

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
| M1 | n_cmds | 0.17 | 0.53 | 0.23 | 0.06 | 0.262 | 0.000 | task-dependent model habit |
| M2 | first_edit_frac | 0.16 | 0.29 | 0.47 | 0.08 | 0.833 | 0.001 | task-dependent model habit |
| M3 | early_edit_share | 0.19 | 0.18 | 0.38 | 0.25 | 0.509 | 0.012 | indeterminate |
| M4 | test_share | 0.04 | 0.39 | 0.38 | 0.19 | 1.000 | 0.009 | indeterminate |
| M5 | exec_share | 0.17 | 0.33 | 0.29 | 0.21 | 0.385 | 0.012 | indeterminate |
| M6 | wrote_new_test | 0.30 | 0.16 | 0.36 | 0.18 | 0.378 | 0.004 | task-dependent model habit |
| M7 | wrote_scratch_script | 0.01 | 0.46 | 0.40 | 0.13 | 1.000 | 0.065 | repeat noise |
| M8 | repeat_cmd_share | - | - | - | - | - | - | indeterminate |
| M9 | noop_retest_share | - | - | - | - | - | - | indeterminate |
| M10 | reread_share | 0.28 | 0.15 | 0.44 | 0.13 | 0.385 | 0.000 | task-dependent model habit |
| M11 | search_miss_share | 0.03 | 0.07 | 0.37 | 0.53 | 1.000 | 1.000 | repeat noise |
| M12 | extra_files | 0.45 | 0.07 | 0.34 | 0.14 | 0.096 | 0.000 | task-dependent model habit |
| M13 | patch_lines | 0.52 | 0.12 | 0.23 | 0.14 | 0.010 | 0.000 | model habit |
| M14 | backed_done | 0.22 | 0.25 | 0.31 | 0.22 | 0.378 | 0.019 | indeterminate |
| M15 | multi_call_share | 0.43 | 0.07 | 0.26 | 0.24 | 0.055 | 0.021 | indeterminate |

## A2-A4 trend test

Holm over the tested measures.

| id | measure | blocks | L - E0 | p | p Holm | agree/disagree/no sign | label | shape | claude-haiku-5-5 | claude-sonnet-5-5 | claude-opus-5-5 | claude-fable-5-2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M1 | n_cmds | 6 | -2.0 | 0.8339 | 1.0000 | 3/2/1 | none |  | 2.211 | 1.595 | 1.960 | 2.145 |
| M2 | first_edit_frac | 6 | -7.0 | 0.3742 | 1.0000 | 4/2/0 | none |  | 0.372 | 0.392 | 0.266 | 0.488 |
| M3 | early_edit_share | 6 | 9.5 | 0.1890 | 1.0000 | 4/2/0 | none |  | 0.227 | 0.374 | 0.331 | 0.306 |
| M4 | test_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/6/0 | none |  | 0.461 | 0.409 | 0.477 | 0.409 |
| M5 | exec_share | 6 | -8.0 | 0.2953 | 1.0000 | 4/1/1 | none |  | 0.595 | 0.437 | 0.589 | 0.501 |
| M6 | wrote_new_test | 6 | 9.0 | 0.1810 | 1.0000 | 4/1/1 | none |  | 0.333 | 0.000 | 0.417 | 0.750 |
| M7 | wrote_scratch_script | 6 | 1.5 | 0.7604 | 1.0000 | 2/1/3 | none |  | 0.250 | 0.167 | 0.167 | 0.250 |
| M8 | repeat_cmd_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/0/6 | none |  | 0.000 | 0.000 | 0.000 | 0.000 |
| M9 | noop_retest_share | 6 | 0.0 | 1.0000 | 1.0000 | 0/0/6 | none |  | 0.000 | 0.000 | 0.000 | 0.000 |
| M10 | reread_share | 6 | 3.5 | 0.6315 | 1.0000 | 4/2/0 | none |  | 0.247 | 0.042 | 0.049 | 0.314 |
| M11 | search_miss_share | 6 | -1.0 | 1.0000 | 1.0000 | 2/1/3 | none |  | 0.028 | 0.021 | 0.000 | 0.013 |
| M12 | extra_files | 6 | 22.0 | 0.0003 | 0.0045 | 6/0/0 | moves with size | step-like | 0.917 | 1.000 | 1.750 | 2.083 |
| M13 | patch_lines | 6 | 21.0 | 0.0022 | 0.0308 | 6/0/0 | moves with size | gradual | 2.672 | 2.326 | 3.229 | 4.435 |
| M14 | backed_done | 6 | -8.5 | 0.1644 | 1.0000 | 4/2/0 | none |  | 0.833 | 0.417 | 0.833 | 0.333 |
| M15 | multi_call_share | 6 | -2.5 | 0.6856 | 1.0000 | 4/1/1 | none |  | 0.000 | 0.089 | 0.007 | 0.002 |

## Context (not tested)

| | claude-haiku-5-5 | claude-sonnet-5-5 | claude-opus-5-5 | claude-fable-5-2 |
|---|---|---|---|---|
| runs | 12 | 12 | 12 | 12 |
| resolved | 11/12 | 12/12 | 12/12 | 12/12 |
| turns | 24.8 | 7.0 | 8.6 | 12.8 |
| thinking_tokens_per_reply | 159.4 | 38.0 | 46.1 | 172.7 |
| output_tokens_per_reply | 407.5 | 221.2 | 283.3 | 584.0 |
| max_tokens_replies_total | 0 | 0 | 0 | 0 |
| cost_usd_total | 0.1 | 0.4 | 1.1 | 8.6 |
| U (completed, edited) | 0/10 | 7/12 | 2/12 | 4/8 |

## A5 generation against size

Fable 5.2 is a separate product line, not a member of the 5.5 family.

| id | measure | exp-08 | dir | exp-10 | dir | reading |
|---|---|---|---|---|---|---|
| M1 | n_cmds | trend | -1 | none | -1 | follows the generation |
| M2 | first_edit_frac | candidate | -1 | none | -1 | not classified (candidate) |
| M3 | early_edit_share | trend | +1 | none | +1 | follows the generation |
| M4 | test_share | candidate | +1 | none | +0 | not classified (candidate) |
| M5 | exec_share | none | +1 | none | -1 | no ordered pattern found |
| M6 | wrote_new_test | none | +1 | none | +1 | no ordered pattern found |
| M7 | wrote_scratch_script | none | -1 | none | +1 | no ordered pattern found |
| M8 | repeat_cmd_share | none | -1 | none | +0 | no ordered pattern found |
| M9 | noop_retest_share | none | +0 | none | +0 | no ordered pattern found |
| M10 | reread_share | candidate | -1 | none | +1 | not classified (candidate) |
| M11 | search_miss_share | none | -1 | none | -1 | no ordered pattern found |
| M12 | extra_files | trend | +1 | trend | +1 | follows capability; generation and size cannot be separated |
| M13 | patch_lines | trend | +1 | trend | +1 | follows capability; generation and size cannot be separated |
| M14 | backed_done | none | -1 | none | -1 | no ordered pattern found |
| M15 | multi_call_share | none | +1 | none | -1 | no ordered pattern found |

## Predictions

- P1. `backed_done` rises with size (moves or candidate). -> **not held** (label none, direction -1, p 0.1644)
- P2. `repeat_cmd_share` falls with size (moves or candidate). -> **not held** (label none, direction +0, p 1)
- P3. `n_cmds` shows no ordered pattern. -> **held** (label none)
- P4. Haiku 5.5 has the lowest `backed_done` of the four. -> **not held** (means claude-haiku-5-5 0.833, claude-sonnet-5-5 0.417, claude-opus-5-5 0.833, claude-fable-5-2 0.333)
- P5. At least one of the 15 measures moves with size. -> **held** (2 labelled trend of 15 tested)
