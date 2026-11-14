# Claude round (round 2) runs, November 2026

The 132 runs of exp-08 (Opus line), exp-09 (effort dial) and exp-10 (size ladder), made on 2026-11-14 between 11:28 and 17:42 EST from harness commit `a51b148` (branch `claude-round`). Spec: `research/experiments/exp-08-opus-line.md` ("Design shared by round 2"). Results: `research/results/exp-08-opus-line/`, `exp-09-effort-dial/`, `exp-10-size-ladder/`.

## What is here

- `round.json`: the round config (tasks, caps, seed, budget rule). `drops` is empty: no drop was applied.
- `ledger.jsonl`: every start, attempt, grade and spend entry, written by `openbench run-round`. It is the index of the runs: cell = `model|effort|task|repeat`.
- One folder per run (`<task>--claude-native--<model>--<timestamp>`): `run.json`, `raw_transcript.jsonl`, `workspace.patch`, `grade.json`. The effort level is in `run.json` and in the ledger, not in the folder name.
- `image-checks/`: the golden and null run made on each task image right before its runs (12 runs, no API calls). Not model runs: never include them in a behavioral or solve-rate analysis.

## Conditions

Runner `claude-native`, request settings as in the spec. 100 turns, 3600 s wall clock, per-run dollar caps.

| stage | model | effort | runs |
|---|---|---|---|
| exp-08 | `claude-opus-4-6`, `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-opus-5-5` | high | 60 |
| exp-09 | `claude-sonnet-5-5` | low, medium, high, xhigh | 48 |
| exp-10 | `claude-haiku-5-5`, `claude-fable-5-2` | high | 24 |

The pilot stage in the ledger is repeat 1 of every model at effort high on the bridge task; those eight runs are counted in the rows above.

## Tasks and images

Run task by task in this order, one image at a time (10 GB disk budget on the host). Each image was built from the freeze commit, passed a golden run (resolved) and a null run (unresolved), was used for all of the task's runs and then deleted.

| task | image id | size |
|---|---|---|
| `sympy__sympy-13757` (bridge) | `d27ab838beb6` | 3.79 GB |
| `astropy__astropy-12907` | `c86e385bbbeb` | 4.11 GB |
| `pydata__xarray-2905` | `3787ac1fb3ea` | 5.54 GB |
| `pytest-dev__pytest-10051` | `8fcb172471e8` | 3.49 GB |
| `scikit-learn__scikit-learn-10297` | `810ab5096855` | 4.21 GB |
| `sphinx-doc__sphinx-10466` | `14aa6980c2d2` | 3.82 GB |

The images no longer exist; the recipes are the tasks' `task.json` and `src/openbench/envs/templates/Dockerfile.j2` at the freeze commit.

## Outcome and spend

- No crashed run, no rerun. 126 runs exited `completed`, 4 on the wall clock, 2 on the turn cap; all six cap-ended runs are on the sympy task.
- 130 of 132 resolved.
- Spend $26.33 including $0.09 before the freeze: Fable 5.2 $8.61, Opus 4.7 $5.32, Opus 5 $3.98, Opus 4.6 $3.21, Sonnet 5.5 $2.17, Opus 4.8 $1.71, Opus 5.5 $1.09, Haiku 5.5 $0.14.
