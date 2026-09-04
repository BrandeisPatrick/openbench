# exp-02 — Effort-mode test: are K3's reasoning-effort levels discrete trained modes or a budget dial?

Status: proposed. Cost: ~$50–80. Depends on: harness `reasoning_effort` flag recorded in run.json.

## Claim tested

Kimi K3 ([2607.24653](https://arxiv.org/abs/2607.24653)): the nine teachers
span three reasoning-effort levels, distilled into one model; the Moonshot API
exposes `reasoning_effort` ∈ {low, high, max} (default max). Contrast: OpenAI
`reasoning_effort` on gpt-5.5, understood as RL-trained budget control.

## Protocol source

Effort-knob comparisons in HAL ([2510.11977](https://arxiv.org/abs/2510.11977))
and "effort as ceiling" ([2605.16938](https://arxiv.org/abs/2605.16938)) give
the null: more effort yields equal-or-worse accuracy in most settings and
changes volume, not behavior. Our addition is the *discreteness* statistic.

## Design

- k3 × {low, high} × 4 current tasks × K=3 = 24 new runs, first-party
  Moonshot (matches the banked k3 runs, which are the `max` arm).
- gpt-5.5 × {low, high} × 4 tasks × K=3 = 24 new runs; banked gpt-5.5 runs
  are the provider-default arm (record which level that is).
- Optional: DeepSeek v4-pro if its API exposes an effort level.
- All other settings identical to the banked cells; effort recorded per run.

## Measures (`analysis/effort_modes.py`)

- Per run, Layer-A profile: command count, X/E/V composition, edit→verify
  probability, tokens per action, reasoning volume, termination class, solve.
- Discreteness: between-level vs within-level trajectory divergence
  (Jensen–Shannon over verb histograms; ordering similarity), same task.
- Level classifier: can a classifier trained on action features alone
  (no volume features) tell low / high / max apart above chance?

## Predictions

- Distinct trained modes (K3 claim): between-level divergence exceeds
  within-level by a pre-set margin, and the action-only classifier beats
  chance — the levels differ in *how* the agent works, not just how long it
  thinks.
- Budget dial (null, expected for OpenAI): only reasoning volume changes;
  action profiles indistinguishable across levels.

## Decision rule (fixed)

"Discrete modes" iff (between − within) divergence margin ≥ 0.10 and
action-only classifier accuracy ≥ 0.6 (3 classes, chance 0.33) under
leave-one-task-out. Otherwise "dial".

## Caveats

Tasks are saturated for k3, so solve rate is not the outcome — behavior is.
Moonshot locks sampling (temperature 1.0, top_p 0.95); OpenAI reasoning
volume must be read from billed tokens.
