# research/ — discovering how coding agents behave

openbench is used to find **patterns in how coding agents work** (what they run,
when they edit, how they check their work) and how those patterns move across
model generations, effort settings and model sizes. It is not used to rank
models. Every experiment is written down, with its measures and predictions,
**before** any run or computation.

Background reading, in order: the two literature reports on agent pattern
discovery ([literature](../reports/Agent%20pattern%20discovery%20literature.md),
[experiments](../reports/Agent%20pattern%20discovery%20experiments.md); their
notes are in `research_notes/`), then the round 1 literature maps in
`background/`.

## Rounds

- **Round 1 (exp-00, exp-07), closed 2026-11-13.** Nine reasoning models from
  three labs, three generations per lab, four SWE-bench Verified tasks, three
  runs per cell. It was first built to read post-training recipes off behavior;
  the owner dropped that aim on 2026-11-11, and the six recipe experiments it
  had proposed (exp-01 to exp-06, never run) were removed on 2026-11-16 (they
  are in git history). exp-07 audited the stored runs for command habits and
  found habits of single models but no trend across generations: with three
  generations per lab an ordered line appears by chance one time in three.
- **Round 2 (exp-08 to exp-10), run 2026-11-14.** One lab, one API, one request
  shape: five Opus generations, an effort dial on Sonnet 5.5, and a size ladder,
  on six tasks from six libraries, two runs per cell, 132 runs. The shared
  design is in [exp-08](experiments/exp-08-opus-line.md); results in
  [results/exp-08-opus-line](results/exp-08-opus-line/results.md).

## Layout

```
research/
  README.md          this guide
  background/        round 1 literature maps: reading and hypotheses, not findings
  corpus/            frozen run corpora, one folder + provenance README per batch
    runs.csv, tasks.csv   generated index of the round 1 batches (analysis/manifest.py)
    runs-2026-11-claude-round/   round 2; indexed by its own ledger.jsonl
  analysis/          measure code; every measure an experiment names exists here,
                     defined in the file header, before results are inspected
  experiments/       one file per experiment
  results/           one sub-folder per experiment once it runs
```

## Experiment index

| id | question | method | status |
|---|---|---|---|
| [exp-00](results/exp-00-findings-verification/results.md) | do the 2026-08 exploratory findings hold on the corpus | re-verification, not pre-registered | done (exploratory) |
| [exp-07](experiments/exp-07-command-audit.md) | which command habits belong to the model, and is "done" backed by the log | rule-coded command audit of the round 1 runs + blind judge | analyzed; hand-label check pending |
| [exp-08](experiments/exp-08-opus-line.md) | which habits move steadily across five Opus generations | command audit + ordered-trend test; blind contrast of the endpoints | analyzed |
| [exp-09](experiments/exp-09-effort-dial.md) | which measures respond to the effort setting on one model | same measures over four effort levels | analyzed |
| [exp-10](experiments/exp-10-size-ladder.md) | does a habit follow the generation or the size of the model | same measures over four current models | analyzed |

The command-coding rules behind exp-07 to exp-10 are still unchecked against
hand labels; the label sheets are in `results/exp-07-command-audit/labels/`.
Until they are filled in, every result carries "unvalidated instrument".

## Rules

1. **Write first, run second.** An experiment file is complete (question,
   protocol, measures, predictions, decision rule) before its first run or
   computation, and is committed before any result exists. Status moves
   `proposed → pre-registered → running → analyzed`.
2. **Measures live in code.** Every measure named in an experiment file has a
   function in `research/analysis/` with its definition in the file header,
   committed before results exist.
3. **Predictions are never edited after results.** Corrections go in the
   results file's ledger; the prediction text stays as written.
4. **Within one lab.** Ordered comparisons (generation, effort, size) stay
   inside one lab and one request shape. Numbers across labs are descriptive.
5. **No pooling across conditions.** Effort levels, raised-cap reruns and
   other variants are separate conditions, never merged into base cells.
6. **Grading hygiene.** `openbench golden-gate` (or a golden and a null run on
   each image) before any new grading batch; crash exits excluded; validity
   markers per the corpus READMEs.
7. **Small rounds.** At most three experiments per round, each round finished
   and reported before the next is chosen.
