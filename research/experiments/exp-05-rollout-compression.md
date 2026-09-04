# exp-05 — Rollout compression at constant reward: the agentic-RL signature

Status: exploratory result in hand (4 tasks); write-up and expansion pending. Cost: $0 now.

## Claim tested

Agentic-RL stages with efficiency pressure — OpenAI's o-series → GPT-5 line;
DeepSeek V3.2 → V4 (RL compute > 10% of pre-training, then on-policy
distillation) — versus Kimi's distillation-first recipe. Literature
signature: rollout length falls during agentic RL while reward holds
([gpt-oss agentic-RL retrospective](https://huggingface.co/blog/LinkedIn/gpt-oss-agentic-rl)).

## Result already verified (findings-verification §second-round)

Billed output tokens on solved runs only:
v3.2 23,780 → v4-pro 7,992 (3.0×); o3 15,689 → gpt-5.5 3,798 (4.1×);
k2.6 11,486 → k3 13,144 (flat). Compression appears in the two lineages that
describe agentic-RL efficiency stages and not in the distillation-first one.

## What remains

- Write-up with per-task values and task-paired intervals in
  `research/results/exp-05-rollout-compression/`.
- Decomposition (from the proposal's H1): is the cut in the post-commitment
  tail (stop when done) or in the novel content (think less)? Commitment
  prefix = first turn at which the final patch is fully present.
- Confirm on the expansion tasks; DeepSeek g1→g2 remains unmeasurable
  within-outcome (r1 never solves).

## Decision rule for the confirmatory version (fixed)

"Compression" for a link iff solved-run token ratio old/new ≥ 1.5 with a
task-paired interval excluding 1. Kimi prediction: ratio in [0.8, 1.25].
