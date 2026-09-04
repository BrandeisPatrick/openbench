# research/ — experiments that read post-training recipes off inference behavior

This folder holds the experiments of the openbench reasoning study, one file
per experiment, written **before** any run or computation. The selection
criterion for an experiment to live here:

> Its result must come out differently depending on what the lab did in
> post-training. An experiment that every recipe predicts the same way
> (e.g. "newer models reason more efficiently") is descriptive and is parked.

Background reading, in order: the lab reports and detection literature
([docs/literature-map-post-training-signatures.md](../docs/literature-map-post-training-signatures.md)),
what has already been verified on the corpus
([docs/findings-verification-2026-08.md](../docs/findings-verification-2026-08.md)),
the reasoning-pattern taxonomy map
([docs/reasoning-pattern-literature-map.md](../docs/reasoning-pattern-literature-map.md)),
and the longer design proposal this folder simplifies
([docs/research-proposal-kimi-first.md](../docs/research-proposal-kimi-first.md)).

## Layout

```
research/
  README.md                 this guide
  experiments/              one file per experiment, fixed template (below)
    exp-01-passk-boundary.md
    exp-02-effort-modes.md
    exp-03-teacher-inheritance.md
    exp-04-think-act-integration.md
    exp-05-rollout-compression.md
    exp-06-priming-elicitation.md
    parked.md               considered and set aside, with the reason
  results/                  one sub-folder per experiment once it runs
    exp-NN-<slug>/results.md  numbers, tables, corrections ledger
analysis/                   metric code; every measure an experiment names
                            must exist here, definitions in the file header,
                            before results are inspected
```

## Corpus and lineages (what every experiment runs on)

Three within-lab lineages of reasoning models under one fixed harness,
4 SWE-bench Verified tasks × K=3 repeats per cell (frozen in `data/`):

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

Suggested order: exp-03 and exp-04 now (free, existing traces); exp-05
written up properly (free); exp-02 next (cheap, uniquely diagnostic of a K3
claim); exp-06 (cheap); exp-01 when the expansion budget is approved — it is
the decisive one and it absorbs the harder-task expansion.

## Rules

1. **Write first, run second.** An experiment file is complete — claim,
   protocol, measures, predictions, decision rule — before its first run or
   computation. Status moves `proposed → pre-registered → running → analyzed`.
2. **Measures live in code.** Every measure named in an experiment file has a
   function in `analysis/` with its definition in the file header, committed
   before results exist (`analysis/convergence.py` is the model).
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
