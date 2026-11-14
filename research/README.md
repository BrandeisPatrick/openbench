# research/ — experiments that read post-training recipes off inference behavior

This folder holds the experiments of the openbench reasoning study, one file
per experiment, written **before** any run or computation. The selection
criterion for an experiment to live here:

> Its result must come out differently depending on what the lab did in
> post-training. An experiment that every recipe predicts the same way
> (e.g. "newer models reason more efficiently") is descriptive and is parked.

Background reading, in order: the lab reports and detection literature
([background/literature-map-post-training-signatures.md](background/literature-map-post-training-signatures.md)),
what has already been verified on the corpus
([results/exp-00-findings-verification/results.md](results/exp-00-findings-verification/results.md)),
the reasoning-pattern taxonomy map
([background/reasoning-pattern-literature-map.md](background/reasoning-pattern-literature-map.md)),
and the longer design proposal this folder simplifies
([proposal.md](proposal.md)).

## Rounds

- **Round 1 (exp-00 to exp-07), closed 2026-11-13.** Nine models from three labs, three
  generations per lab, four tasks. It was built to read post-training recipes off behavior
  (the selection criterion above). exp-07 audited it for command habits and found habits of
  single models but no trend across generations; with three generations per lab an ordered
  line appears by chance one time in three, so none could have been established. Its
  corpus, experiment files and results stay as they are.
- **Round 2 (exp-08 to exp-10), pre-registered 2026-11-14.** One lab, one API, one request
  shape: five Opus generations, an effort dial on one model, and a size ladder, on six tasks
  from six libraries. Descriptive on purpose, under the owner's reframing of 2026-11-11:
  openbench is for discovering agent behavior patterns, not for ranking models. The shared
  design is in [exp-08](experiments/exp-08-opus-line.md).

## Layout

```
research/
  README.md                 this guide
  proposal.md               the longer design proposal this folder simplifies
  background/               literature maps: reading and hypotheses, not findings
  corpus/                   frozen run corpora, one folder + provenance README per batch
  analysis/                 metric code; every measure an experiment names
                            must exist here, definitions in the file header,
                            before results are inspected
  experiments/              one file per experiment, fixed template (below)
    exp-01-passk-boundary.md
    exp-02-effort-modes.md
    exp-03-teacher-inheritance.md
    exp-04-think-act-integration.md
    exp-05-rollout-compression.md
    exp-06-priming-elicitation.md
    parked.md               considered and set aside, with the reason
  results/                  one sub-folder per experiment once it runs
    exp-00-findings-verification/results.md
                            exploratory verification of the 2026-08 findings;
                            predates the experiment files
    exp-NN-<slug>/results.md  numbers, tables, corrections ledger
```

## Corpus and lineages (what every experiment runs on)

Three within-lab lineages of reasoning models under one fixed harness,
4 SWE-bench Verified tasks × K=3 repeats per cell (frozen in `research/corpus/`):

| lineage | g1 → g2 → g3 | reasoning channel | serving host |
|---|---|---|---|
| Kimi | k2-thinking → k2.6 → k3 | raw CoT | OpenRouter → Moonshot → Moonshot (g1→g2 crosses hosts) |
| DeepSeek | r1-0528 → v3.2 → v4-pro | raw CoT | OpenRouter → OpenRouter → first-party (g2→g3 crosses) |
| OpenAI | o1 → o3 → gpt-5.5 | summaries only | first-party throughout |

Standing caveats every file inherits: the four current tasks are saturated for
Kimi (Pass@3 = 4/4 at every generation); host-crossing links carry an
unrecorded sampling-default confound; OpenAI reasoning text supports
presence claims only; all current results are exploratory (4 task clusters).

## Experiment index

| id | lab claim tested | protocol source | cost | status |
|---|---|---|---|---|
| [exp-01](experiments/exp-01-passk-boundary.md) | K3 / V4: distillation from specialist teachers expands capability (vs RL sharpening) | limit-of-RLVR pass@k boundary test | expansion budget | proposed |
| [exp-02](experiments/exp-02-effort-modes.md) | K3: three reasoning-effort levels trained as separate teachers | effort-knob A/B, OpenAI as contrast | ~$50–80 | proposed |
| [exp-03](experiments/exp-03-teacher-inheritance.md) | K3 inherits the specialist lineage's procedures | AgentEcho action-graph similarity | $0 | proposed |
| [exp-04](experiments/exp-04-think-act-integration.md) | V3.2: thinking integrated into tool use (vs R1 think-then-act) | interleaving structure, r1 vs v3.2 | $0 | proposed |
| [exp-05](experiments/exp-05-rollout-compression.md) | agentic-RL efficiency pressure (DeepSeek, OpenAI) vs distillation-first (Kimi) | rollout compression at constant reward | $0 | exploratory result in hand |
| [exp-06](experiments/exp-06-priming-elicitation.md) | did post-training add capability or elicit latent behavior | Four Habits priming protocol | ~$30 | proposed |
| [exp-07](experiments/exp-07-command-audit.md) | none — descriptive, admitted under the 2026-11-11 discovery reframing: which command habits belong to the model, and is "done" backed by the log | rule-coded command audit of the stored runs | $0 (Part A), $7.16 (Part B) | analyzed; hand-label validation pending |
| [exp-08](experiments/exp-08-opus-line.md) | none — descriptive (round 2): which command habits move steadily across five Opus generations | rule-coded command audit + ordered-trend test; open contrast of the endpoints | round 2 budget, $125 for exp-08 to exp-10 | pre-registered |
| [exp-09](experiments/exp-09-effort-dial.md) | none — descriptive (round 2): which measures respond to the effort setting on one model | same measures over four effort levels | (round 2 budget) | pre-registered |
| [exp-10](experiments/exp-10-size-ladder.md) | none — descriptive (round 2): does a habit follow the generation or the size of the model | same measures over four current models of different size | (round 2 budget) | pre-registered |

Suggested order: exp-03 and exp-04 now (free, existing traces); exp-05
written up properly (free); exp-02 next (cheap, uniquely diagnostic of a K3
claim); exp-06 (cheap); exp-01 when the expansion budget is approved — it is
the decisive one and it absorbs the harder-task expansion.

## Rules

1. **Write first, run second.** An experiment file is complete — claim,
   protocol, measures, predictions, decision rule — before its first run or
   computation. Status moves `proposed → pre-registered → running → analyzed`.
2. **Measures live in code.** Every measure named in an experiment file has a
   function in `research/analysis/` with its definition in the file header, committed
   before results exist (`research/analysis/convergence.py` is the model).
3. **Predictions are never edited after results.** Corrections go in the
   results file's ledger; the prediction text stays as written.
4. **Within-lineage only.** Cross-lab numbers are descriptive. Host-crossing
   links are labelled in every table.
5. **Action twin.** Any reasoning-text measure is reported beside its
   action-side counterpart; a CoT effect without an action counterpart is
   reported as unsupported.
6. **No pooling across conditions.** Primed runs, effort-level runs,
   host-matched reruns and thinking-off runs are separate conditions, never
   merged into the base cells.
7. **Grading hygiene.** `openbench golden-gate` before any new grading batch;
   crash exits excluded; validity markers per the corpus READMEs.

## Instrumentation needed before the paid experiments

- Harness flag to pass `reasoning_effort` (Moonshot low/high/max; OpenAI
  Responses API levels) and record it in `run.json` (exp-02).
- Record serving provider, request date and any version string per run
  (all; OpenRouter provider capture for exp-01/03).
- Token-based caps, identical across arms (exp-01, exp-06).
- Priming system-prompt variant recorded as a named condition (exp-06).
