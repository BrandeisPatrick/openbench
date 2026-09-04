# exp-06 — Priming test: did post-training add capability, or elicit what was latent?

Status: proposed. Cost: ~$30. Depends on: priming prompt recorded as a named condition.

## Claim tested

The sharpening thesis at the behavior level: if the older generation, told
explicitly to behave like the newer one, matches it, then post-training
sharpened latent behavior; if it cannot, capability was added.

## Protocol source

Four Habits ([2503.01307](https://arxiv.org/abs/2503.01307)): priming a model
with examples of verification, backtracking, subgoal setting and backward
chaining changes what RL can elicit; the behaviors matter more than answer
correctness. Used here as a diagnostic rather than a training intervention.

## Design

- k2.6 primed: system prompt instructing the behaviors observed in k3
  (explore before editing; run the relevant tests after every edit; never
  report completion without a passing test run). 4 tasks × K=3 = 12 runs.
- v3.2 primed with v4-pro's observed behaviors: 12 runs (r1 is too slow;
  optional later).
- Compared with the banked unprimed cells; primed runs are a separate
  condition, never pooled.

## Measures (`analysis/priming.py`)

Solve rate; Layer-A profile distance to the newer generation (JSD over verb
histograms, ordering similarity); edit→verify probability; unsupported
completion rate.

## Predictions

- Elicitation: primed old model's profile distance to the new generation
  falls by ≥ half, and its verification gap closes.
- Capability: profile moves little; solve rate unchanged.

## Decision rule (fixed)

"Elicitation" iff profile distance to the newer generation drops ≥ 50% AND
edit→verify probability rises to within 0.1 of the newer generation's.
"Capability" iff neither. Otherwise "partial".

## Caveats

Priming changes the prompt, hence the condition; results describe what the
old model can do when told, not what it does by default. Saturated tasks
limit the solve-rate reading; the profile reading is the primary one.
