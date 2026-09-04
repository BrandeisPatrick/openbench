# exp-04 — Think–act integration: did V3.2's "thinking inside tool use" change trace structure?

Status: proposed. Cost: $0 (existing traces). Host-uniform link (r1 and v3.2 both via OpenRouter).

## Claim tested

DeepSeek V3.2 ([2512.02556](https://arxiv.org/abs/2512.02556)): first
integration of thinking directly into tool use — thinking and tool calls in
one trajectory, cold-start unification, ~1,800 synthesized agentic
environments. R1 ([2501.12948](https://arxiv.org/abs/2501.12948)): no
agentic stage; single-turn RL.

## Protocol source

No single paper; the constructs are the agentic-RL "thinking vs doing"
literature in the pattern map §1c and the interleaving prediction in the
literature map §2c(iii). Measures below are deterministic from the transcript.

## Design

Existing r1, v3.2, v4-pro traces (4 tasks × 3 repeats); Kimi and OpenAI
reported as descriptive context (OpenAI on billed tokens only).

## Measures (`analysis/interleaving.py`)

- Per-call reasoning coverage: fraction of tool calls preceded by non-empty
  reasoning in the same turn.
- Front-loading: share of total reasoning characters emitted before the
  first command; Gini of reasoning volume across turns.
- Blind-edit rate: edits with no prior read of the edited file.
- Reasoning-per-call distribution (median, 90th percentile).

## Predictions

- Integration (V3.2 claim): v3.2 coverage ≥ 0.9, front-loading share less
  than half of r1's, blind-edit rate near zero; r1 front-loads and edits blind
  (illustrative: one r1 run rewrote a file as its first command with no read).
- Null: no structural difference beyond volume.

## Decision rule (fixed)

"Integration" iff v3.2 coverage ≥ 0.9 AND front-loading share ≤ 0.5 × r1's,
task-paired. Otherwise null.

## Caveats

Reasoning exposure for both models comes through OpenRouter with reasoning
enabled — same host, same protocol, so the link is clean; v3.2's turn-cap
runs (9/12) are included but flagged.
